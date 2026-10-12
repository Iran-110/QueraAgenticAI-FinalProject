"""Receipt-bound core composition for an existing persistent tracker.

This service does not own HTTP, reviewer authentication, storage, or a durable
run journal. Ingress replay never resumes reasoning. Uncertain staging can be
recovered only by reading the exact complete pending handoff, without new ports.
"""

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal, get_args
from uuid import uuid4

from pydantic import TypeAdapter

from agent_app.contracts import (
    CaseState,
    Contract,
    GroundedRequest,
    Identifier,
    ProposalHandoff,
    ProposalRequirements,
    ReportedFact,
    RetrievalRequest,
    RunLimits,
    RunResult,
    TrackerCaseView,
    TrackerStageReceipt,
    TrackerTurnReceipt,
    TurnConversation,
    UserTurn,
)
from agent_app.orchestration.conversation import ConversationRejected, build_reasoning_message
from agent_app.orchestration.engine import SupportEngine
from agent_app.orchestration.handoff import (
    HandoffCode,
    HandoffRejected,
    ReasoningCapture,
    build_handoff,
    ensure_handoff_current,
    validate_handoff,
)
from agent_app.orchestration.ports import CaseTracker, Reasoner, Retriever
from agent_app.orchestration.validation import detached_contract


@dataclass(frozen=True)
class CoreAdapters:
    """Fresh ports for one trusted run ID; live reasoning must still use llm/ledger."""

    retriever: Retriever
    reasoner: Reasoner
    snapshot_id: str
    grounded_request_supplier: Callable[[], GroundedRequest | None] | None = None


type CoreAdapterFactory = Callable[[CaseState, str, str], CoreAdapters]
type StageWithResult = Callable[[ProposalHandoff, RunResult, str], Mapping[str, object]]
type TurnStatus = Literal[
    "ingress_rejected",
    "ingress_unknown",
    "replay_only",
    "superseded_before_run",
    "core_stopped",
    "proposal_staged",
    "proposal_not_pending",
    "staging_unknown",
]


@dataclass(frozen=True)
class CoreTurnOutcome:
    """Only proposal_staged exposes a confirmed review candidate in handoff.

    candidate_handoff is an unconfirmed recovery input, never approval authority.
    run_result preserves attempts and diagnostics even when staging fails. The
    snapshot is point-in-time; approval must always check the tracker again.
    """

    status: TurnStatus
    receipt: TrackerTurnReceipt | None = None
    snapshot: TrackerCaseView | None = None
    run_result: RunResult | None = None
    handoff: ProposalHandoff | None = None
    candidate_handoff: ProposalHandoff | None = None
    stage_receipt: TrackerStageReceipt | None = None
    error_code: str | None = None
    recovered_ack: bool = False


_INGRESS_CODES = frozenset(
    {
        "EventConflict",
        "InvalidEventContext",
        "StaleRevision",
        "PendingReplyMissing",
        "InvalidInput",
        "CaseMismatch",
        "PendingProposalMismatch",
        "InvalidVersionQuestion",
        "VersionAlreadyKnown",
        "StructuredTurnNotAllowed",
        "VersionReplyUnclear",
        "StateLimitExceeded",
    }
)
_STAGE_CODES = frozenset(
    {"StaleRevision", "PendingProposalMismatch", "CaseContentMismatch", "ProposalConflict"}
)
_HANDOFF_CODES = frozenset(get_args(HandoffCode.__value__))


def _code(error: Exception, allowed: frozenset[str], fallback: str) -> str:
    # A third-party adapter exception must never export raw text or unknown codes.
    try:
        value = getattr(error, "code", None)
        return value if type(value) is str and value in allowed else fallback
    except Exception:
        return fallback


def _copy[T: Contract](model: type[T], value: T) -> T:
    return detached_contract(model, value)


def _mapping[T: Contract](model: type[T], value: Mapping[str, object]) -> T:
    # The port returns JSON-compatible data. Round-tripping rejects constructed
    # nested models, NaN, and mutable aliases before trusting a storage snapshot.
    if not isinstance(value, Mapping):
        raise ValueError
    return model.model_validate_json(json.dumps(dict(value), allow_nan=False))


class CoreTurnService:
    """Apply an original event, then reason only against its committed snapshot."""

    def __init__(
        self,
        tracker: CaseTracker,
        adapters: CoreAdapterFactory,
        *,
        limits: RunLimits | None = None,
        top_k: int = 5,
        proposal_checks: bool = False,
        evidence_scope: Literal["all", "exact_user_version"] = "all",
        stage_with_result: StageWithResult | None = None,
    ) -> None:
        self.tracker = tracker
        self.adapters = adapters
        if not callable(adapters) or not all(
            callable(getattr(tracker, method, None))
            for method in ("apply_turn", "read_case", "stage_proposal")
        ):
            raise ValueError("Invalid core service configuration.")
        self.limits = _copy(RunLimits, limits) if limits is not None else RunLimits()
        # Validate options without constructing a model/retrieval port.
        RetrievalRequest(queries=("configuration-check",), snapshot_id="configuration", top_k=top_k)
        if (
            type(proposal_checks) is not bool
            or type(evidence_scope) is not str
            or evidence_scope not in {"all", "exact_user_version"}
        ):
            raise ValueError("Invalid core service configuration.")
        self.top_k = top_k
        self.proposal_checks = proposal_checks
        self.evidence_scope = evidence_scope
        if stage_with_result is not None and not callable(stage_with_result):
            raise ValueError("Invalid core service configuration.")
        # Trusted integration hook into the SAME tracker transaction. The
        # model cannot select the event identity or persist its own counters.
        self.stage_with_result = stage_with_result

    def _read(self, case_id: str) -> TrackerCaseView:
        view = _mapping(TrackerCaseView, self.tracker.read_case(case_id))
        if view.state.case_id != case_id:
            raise ValueError
        if view.pending_handoff is not None:
            ensure_handoff_current(view.pending_handoff, view.state, view.state.pending_proposal_id)
        return view

    def recover_exact_pending(self, expected: ProposalHandoff) -> ProposalHandoff:
        """Read-only lost-ACK recovery; never stage, reason, approve, or resume."""
        expected = validate_handoff(expected)
        try:
            view = self._read(expected.case.case_id)
        except Exception:
            raise HandoffRejected("InvalidHandoffInput") from None
        if view.pending_handoff is None:
            raise HandoffRejected("PendingProposalMismatch")
        saved = validate_handoff(view.pending_handoff)
        ensure_handoff_current(saved, view.state, expected.proposal_id)
        if saved != expected:
            raise HandoffRejected("HandoffMismatch")
        return saved

    def submit(
        self,
        turn: UserTurn,
        *,
        reply_to_proposal_id: str | None = None,
        event_context: Mapping[str, str] | None = None,
        run_id: str | None = None,
        proposal_requirements: ProposalRequirements | None = None,
    ) -> CoreTurnOutcome:
        # Caller errors fail before ingress. Event identity is always the original
        # turn/reply binding/options; conversation composition happens afterward.
        try:
            turn = _copy(UserTurn, turn)
            if reply_to_proposal_id is not None:
                reply_to_proposal_id = TypeAdapter(Identifier).validate_python(reply_to_proposal_id)
            event_context = dict(event_context) if event_context is not None else {}
            if not all(type(k) is str and type(v) is str for k, v in event_context.items()):
                raise ValueError
            if run_id is not None:
                run_id = TypeAdapter(Identifier).validate_python(run_id)
            if proposal_requirements is not None:
                proposal_requirements = _copy(ProposalRequirements, proposal_requirements)
                if (
                    proposal_requirements.case_id != turn.case_id
                    or proposal_requirements.case_revision != turn.expected_revision + 1
                ):
                    raise ValueError
            event_hash = hashlib.sha256(
                json.dumps(
                    {
                        "turn": turn.model_dump(mode="json"),
                        "reply_to_proposal_id": reply_to_proposal_id,
                        "context": event_context,
                    },
                    sort_keys=True,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8")
            ).hexdigest()
        except Exception:
            raise ValueError("Invalid core turn input.") from None

        try:
            raw_receipt = self.tracker.apply_turn(
                turn.model_copy(deep=True),
                reply_to_proposal_id=reply_to_proposal_id,
                event_context=dict(event_context),
            )
        except Exception as error:
            code = _code(error, _INGRESS_CODES, "TrackerIngressUnknown")
            return CoreTurnOutcome(
                "ingress_unknown" if code == "TrackerIngressUnknown" else "ingress_rejected",
                error_code=code,
            )
        try:
            receipt = _mapping(TrackerTurnReceipt, raw_receipt)
            if (
                receipt.case_id != turn.case_id
                or receipt.turn_id != turn.turn_id
                or receipt.ingress_hash != event_hash
                or receipt.committed_revision != turn.expected_revision + 1
                or (receipt.preparation == "canonical_version_reply")
                != (reply_to_proposal_id is not None)
            ):
                raise ValueError
        except Exception:
            return CoreTurnOutcome("ingress_unknown", error_code="InvalidTrackerReceipt")

        try:
            view = self._read(turn.case_id)
        except Exception:
            return CoreTurnOutcome(
                "replay_only" if receipt.replayed else "core_stopped",
                receipt=receipt,
                error_code="CaseReadFailed",
            )
        if receipt.replayed:
            # Replay is only ingress recovery. Its historical prepared projection
            # remains a tracker-owned receipt; it never triggers new ports.
            return CoreTurnOutcome("replay_only", receipt=receipt, snapshot=view)
        if view.state.case_revision != receipt.committed_revision:
            return CoreTurnOutcome(
                "superseded_before_run", receipt=receipt, snapshot=view, error_code="StaleRevision"
            )
        if view.status != "open" or view.state.pending_proposal_id is not None:
            return CoreTurnOutcome(
                "core_stopped", receipt=receipt, snapshot=view, error_code="TrackerLifecycleChanged"
            )
        try:
            prepared = turn
            if receipt.preparation == "canonical_version_reply":
                versions = [
                    fact
                    for fact in view.state.facts
                    if fact.name == "streamlit_version"
                    and fact.provenance_kind == "user"
                    and fact.status == "active"
                    and fact.turn_id == turn.turn_id
                    and fact.source_ref == turn.source_ref
                ]
                if (
                    len(versions) != 1
                    or turn.message not in {versions[0].value, f"Streamlit {versions[0].value}"}
                    or turn.reported_facts
                    or turn.checks_performed
                    or turn.unknowns
                    or turn.context_changed
                ):
                    raise ValueError
                prepared = turn.model_copy(
                    update={
                        "reported_facts": (
                            ReportedFact(name="streamlit_version", value=versions[0].value),
                        )
                    }
                )
            digest = hashlib.sha256(
                json.dumps(
                    prepared.model_dump(mode="json"),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            if receipt.prepared_hash != digest:
                raise ValueError
        except Exception:
            return CoreTurnOutcome(
                "core_stopped", receipt=receipt, snapshot=view, error_code="InvalidTrackerReceipt"
            )
        try:
            message = build_reasoning_message(
                TurnConversation(
                    entries=view.history,
                    latest_turn_id=turn.turn_id,
                    committed_revision=receipt.committed_revision,
                    latest_message=turn.message,
                    reply_to_proposal_id=reply_to_proposal_id,
                )
            )
        except ConversationRejected as error:
            return CoreTurnOutcome(
                "core_stopped", receipt=receipt, snapshot=view, error_code=error.code
            )
        except Exception:
            return CoreTurnOutcome(
                "core_stopped",
                receipt=receipt,
                snapshot=view,
                error_code="InvalidConversationInput",
            )

        def current_case(case_id: str) -> CaseState:
            current = self._read(case_id)
            if current.state == view.state and current != view:
                # Lifecycle can change without a revision change. This catches
                # changes at reads; closing the final write race needs tracker CAS.
                raise ValueError
            return current.state

        trusted_run_id = run_id if run_id is not None else str(uuid4())
        try:
            # No factory for replay/superseded/invalid input. Its detached arguments
            # cannot mutate the authoritative message or snapshot retained here.
            ports = self.adapters(view.state.model_copy(deep=True), message, trusted_run_id)
            if not isinstance(ports, CoreAdapters):
                raise ValueError
            capture = ReasoningCapture(ports.reasoner)
            engine = SupportEngine(
                ports.retriever,
                capture,
                snapshot_id=ports.snapshot_id,
                limits=self.limits,
                top_k=self.top_k,
                current_case=current_case,
                proposal_checks=self.proposal_checks,
                evidence_scope=self.evidence_scope,
            )
        except Exception:
            return CoreTurnOutcome(
                "core_stopped", receipt=receipt, snapshot=view, error_code="AdapterSetupFailed"
            )
        try:
            result = engine.run(
                view.state,
                message,
                run_id=trusted_run_id,
                proposal_requirements=proposal_requirements,
            )
        except Exception:
            return CoreTurnOutcome(
                "core_stopped", receipt=receipt, snapshot=view, error_code="CoreRunFailed"
            )
        if result.status != "awaiting_approval":
            return CoreTurnOutcome(
                "core_stopped",
                receipt=receipt,
                snapshot=view,
                run_result=result,
                error_code=result.error_code,
            )
        try:
            grounded = (
                ports.grounded_request_supplier() if ports.grounded_request_supplier else None
            )
            candidate = build_handoff(result, capture.last, grounded_request=grounded)
        except Exception as error:
            code = _code(error, _HANDOFF_CODES, "InvalidHandoffInput")
            return CoreTurnOutcome(
                "core_stopped", receipt=receipt, snapshot=view, run_result=result, error_code=code
            )
        try:
            if self._read(turn.case_id) != view:
                return CoreTurnOutcome(
                    "proposal_not_pending",
                    receipt=receipt,
                    run_result=result,
                    error_code="TrackerLifecycleChanged",
                )
        except Exception:
            return CoreTurnOutcome(
                "proposal_not_pending",
                receipt=receipt,
                run_result=result,
                error_code="CaseReadFailed",
            )

        stage_receipt = None
        stage_error = None
        try:
            stage_receipt = _mapping(
                TrackerStageReceipt,
                (
                    self.stage_with_result(
                        candidate.model_copy(deep=True),
                        result.model_copy(deep=True),
                        receipt.turn_id,
                    )
                    if self.stage_with_result is not None
                    else self.tracker.stage_proposal(candidate.model_copy(deep=True))
                ),
            )
            if (
                stage_receipt.case_id != candidate.case.case_id
                or stage_receipt.proposal_id != candidate.proposal_id
                or stage_receipt.revision != candidate.case.case_revision
            ):
                raise ValueError
        except Exception as error:
            stage_error = _code(error, _STAGE_CODES, "TrackerStagingUnknown")
            stage_receipt = None
        # A write acknowledgement alone does not expose a review candidate. Both
        # success and ambiguous ACK paths require the exact authoritative content.
        try:
            saved = self.recover_exact_pending(candidate)
        except HandoffRejected as error:
            unknown = stage_error == "TrackerStagingUnknown" or error.code == "InvalidHandoffInput"
            return CoreTurnOutcome(
                "staging_unknown" if unknown else "proposal_not_pending",
                receipt=receipt,
                run_result=result,
                candidate_handoff=candidate if unknown else None,
                error_code=stage_error or ("CaseReadFailed" if unknown else error.code),
            )
        return CoreTurnOutcome(
            "proposal_staged",
            receipt=receipt,
            run_result=result,
            handoff=saved,
            stage_receipt=stage_receipt,
            recovered_ack=stage_error is not None,
        )
