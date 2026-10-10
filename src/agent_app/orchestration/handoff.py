"""Complete, detached proposal handoffs; content integrity is never authority.

Capture belongs to one invocation. The caller supplies any GroundedRequest from
its own per-invocation factory. Neither a handoff nor a review packet authenticates
the reviewer, authorizes an action, or proves a claim true.
"""

import hashlib
import json
from dataclasses import dataclass
from typing import Literal, get_args

from pydantic import TypeAdapter, ValidationError

from agent_app.contracts import (
    AnalysisResult,
    CaseState,
    Contract,
    EvidenceBundle,
    GroundedRequest,
    Identifier,
    ProposalHandoff,
    ReasoningContext,
    RunResult,
    SourceReviewEntry,
)
from agent_app.orchestration.ports import Reasoner, ReasoningOutput
from agent_app.reasoning.grounding import (
    source_content_sha256,
    source_scope,
    validate_grounded_request,
)
from agent_app.reasoning.review import build_proposal_review_packet

type HandoffCode = Literal[
    "InvalidHandoffInput",
    "FinalProposalRequired",
    "ReasoningContextMismatch",
    "HandoffMismatch",
    "GroundedContextMismatch",
    "CaseMismatch",
    "StaleRevision",
    "PendingProposalMismatch",
    "CaseContentMismatch",
]

_INPUT_ERRORS = (ValidationError, ValueError, TypeError, AttributeError, RecursionError)


class HandoffRejected(ValueError):
    def __init__(self, code: HandoffCode) -> None:
        if code not in get_args(HandoffCode.__value__):
            raise ValueError("Unsupported handoff rejection code.")
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ReasoningFrame:
    """Input copied before the delegate can mutate any supplied objects."""

    case: CaseState
    user_message: str
    evidence: EvidenceBundle
    context: ReasoningContext


def _detached[T: Contract](model: type[T], value: T) -> T:
    # model_copy can bypass extra="forbid" and model_dump can silently omit
    # injected attributes. Reject them before trusting the serialized snapshot.
    if set(value.__dict__) - set(model.model_fields):
        raise ValueError
    return model.model_validate(value.model_dump(warnings=False))


def _frame(frame: ReasoningFrame | None) -> ReasoningFrame:
    try:
        if not isinstance(frame, ReasoningFrame):
            raise ValueError
        case = _detached(CaseState, frame.case)
        evidence = _detached(EvidenceBundle, frame.evidence)
        context = _detached(ReasoningContext, frame.context)
        message = frame.user_message
        if type(message) is not str or not message.strip() or len(message) > 20_000:
            raise ValueError
        message.encode("utf-8")
    except _INPUT_ERRORS:
        raise HandoffRejected("InvalidHandoffInput") from None
    if context.case_id != case.case_id or context.case_revision != case.case_revision:
        raise HandoffRejected("ReasoningContextMismatch")
    if case.pending_proposal_id is not None:
        raise HandoffRejected("PendingProposalMismatch")
    return ReasoningFrame(case, message, evidence, context)


class ReasoningCapture:
    """Transparent per-run decorator; performs no extra retrieval/model attempt."""

    def __init__(self, reasoner: Reasoner) -> None:
        self.reasoner = reasoner
        self.last: ReasoningFrame | None = None

    def analyze(
        self,
        case: CaseState,
        user_message: str,
        evidence: EvidenceBundle,
        *,
        context: ReasoningContext,
    ) -> ReasoningOutput:
        self.last = None
        self.last = _frame(ReasoningFrame(case, user_message, evidence, context))
        return self.reasoner.analyze(case, user_message, evidence, context=context)


def _inventory(case: CaseState, evidence: EvidenceBundle) -> tuple[SourceReviewEntry, ...]:
    return tuple(
        SourceReviewEntry(
            chunk_id=hit.chunk_id,
            content_sha256=source_content_sha256(hit),
            version_scope=source_scope(case, hit),
        )
        for hit in evidence.hits
    )


def _digest(payload: object) -> str:
    try:
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(("proposal-handoff-v1:" + serialized).encode("utf-8")).hexdigest()
    except _INPUT_ERRORS:
        raise HandoffRejected("InvalidHandoffInput") from None


def _grounded(request: GroundedRequest | None, frame: ReasoningFrame) -> GroundedRequest | None:
    if request is None:
        return None
    try:
        request = validate_grounded_request(request)
    except _INPUT_ERRORS:
        raise HandoffRejected("GroundedContextMismatch") from None
    if (
        request.case != frame.case
        or request.user_message != frame.user_message
        or request.evidence != frame.evidence
    ):
        raise HandoffRejected("GroundedContextMismatch")
    return request


def _build(
    proposal_id: str,
    frame: ReasoningFrame,
    analysis: AnalysisResult,
    grounded_request: GroundedRequest | None,
) -> ProposalHandoff:
    frame = _frame(frame)
    try:
        analysis = _detached(AnalysisResult, analysis)
        proposal_id = TypeAdapter(Identifier).validate_python(proposal_id)
    except _INPUT_ERRORS:
        raise HandoffRejected("InvalidHandoffInput") from None
    if analysis.decision == "retrieve_more":
        raise HandoffRejected("FinalProposalRequired")
    grounded_request = _grounded(grounded_request, frame)
    try:
        handoff = ProposalHandoff(
            proposal_id=proposal_id,
            case=frame.case,
            user_message=frame.user_message,
            evidence=frame.evidence,
            analysis=analysis,
            reasoning_context=frame.context,
            grounded_request=grounded_request,
            source_inventory=_inventory(frame.case, frame.evidence),
            packet=build_proposal_review_packet(frame.case, frame.evidence, analysis),
            handoff_sha256="0" * 64,
        )
        digest = _digest(handoff.model_dump(mode="json", exclude={"handoff_sha256"}))
        return ProposalHandoff.model_validate(
            {**handoff.model_dump(warnings=False), "handoff_sha256": digest}
        )
    except HandoffRejected:
        raise
    except _INPUT_ERRORS:
        raise HandoffRejected("InvalidHandoffInput") from None


def build_handoff(
    result: RunResult,
    frame: ReasoningFrame | None,
    *,
    grounded_request: GroundedRequest | None = None,
) -> ProposalHandoff:
    """Bind an engine's final result to the actual final input captured for that run."""
    try:
        result = _detached(RunResult, result)
    except _INPUT_ERRORS:
        raise HandoffRejected("InvalidHandoffInput") from None
    if result.status != "awaiting_approval" or result.analysis is None:
        raise HandoffRejected("FinalProposalRequired")
    frame = _frame(frame)
    if (
        result.run_id != frame.context.run_id
        or result.case_id != frame.case.case_id
        or result.case_revision != frame.case.case_revision
        or result.model_attempts != frame.context.attempt_index
        or result.retrieval_rounds != frame.evidence.retrieval_round
        or not 1 <= result.retrieval_rounds <= 2
    ):
        raise HandoffRejected("ReasoningContextMismatch")
    return _build(result.run_id, frame, result.analysis, grounded_request)


def validate_handoff(handoff: ProposalHandoff) -> ProposalHandoff:
    """Return detached validated content; a checksum cannot authenticate its author."""
    try:
        handoff = _detached(ProposalHandoff, handoff)
    except _INPUT_ERRORS:
        raise HandoffRejected("InvalidHandoffInput") from None
    expected = _build(
        handoff.proposal_id,
        ReasoningFrame(
            handoff.case, handoff.user_message, handoff.evidence, handoff.reasoning_context
        ),
        handoff.analysis,
        handoff.grounded_request,
    )
    if handoff != expected:
        raise HandoffRejected("HandoffMismatch")
    return handoff


def ensure_handoff_current(
    handoff: ProposalHandoff, current_case: CaseState, proposal_id: str
) -> None:
    """Check exact current content after removing only the expected pending ID."""
    handoff = validate_handoff(handoff)
    try:
        current_case = _detached(CaseState, current_case)
        proposal_id = TypeAdapter(Identifier).validate_python(proposal_id)
    except _INPUT_ERRORS:
        raise HandoffRejected("InvalidHandoffInput") from None
    if current_case.case_id != handoff.case.case_id:
        raise HandoffRejected("CaseMismatch")
    if current_case.case_revision != handoff.case.case_revision:
        raise HandoffRejected("StaleRevision")
    if (
        proposal_id != handoff.proposal_id
        or current_case.pending_proposal_id != handoff.proposal_id
    ):
        raise HandoffRejected("PendingProposalMismatch")
    normalized = current_case.model_copy(update={"pending_proposal_id": None})
    if normalized != handoff.case:
        raise HandoffRejected("CaseContentMismatch")


def edit_handoff(
    handoff: ProposalHandoff, new_proposal_id: str, analysis: AnalysisResult
) -> ProposalHandoff:
    """Rebind an edit to a new proposal identity, preserving the original input."""
    handoff = validate_handoff(handoff)
    try:
        new_proposal_id = TypeAdapter(Identifier).validate_python(new_proposal_id)
    except _INPUT_ERRORS:
        raise HandoffRejected("InvalidHandoffInput") from None
    if new_proposal_id == handoff.proposal_id:
        raise HandoffRejected("PendingProposalMismatch")
    return _build(
        new_proposal_id,
        ReasoningFrame(
            handoff.case, handoff.user_message, handoff.evidence, handoff.reasoning_context
        ),
        analysis,
        handoff.grounded_request,
    )
