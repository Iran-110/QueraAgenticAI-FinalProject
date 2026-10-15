"""Recognize narrow version replies to tracker-bound question records.

These helpers neither read storage nor authenticate a proposal. The caller must
load the exact pending or approved question record from the tracker, then commit
the returned user turn through the event-deduplication/revision transaction.
No source text, model response, or free-text instruction grants action authority.
"""

import re
from typing import Literal, get_args

from pydantic import ValidationError

from agent_app.contracts import (
    AnalysisResult,
    ApprovedReplyQuestion,
    CaseState,
    QuestionTarget,
    ReportedFact,
    UserTurn,
)
from agent_app.orchestration.validation import detached_contract

type IntakeRejectionCode = Literal[
    "InvalidInput",
    "CaseMismatch",
    "StaleRevision",
    "PendingProposalMismatch",
    "InvalidVersionQuestion",
    "VersionAlreadyKnown",
    "StructuredTurnNotAllowed",
    "VersionReplyUnclear",
]

_VERSION_REPLY = re.compile(r"(?:Streamlit )?([0-9]+\.[0-9]+\.[0-9]+)")
_VERSION_TARGET_NAME = "streamlit_version"
_VERSION_QUESTION_TEXT = "Which Streamlit version is installed in the affected environment?"
STREAMLIT_VERSION_QUESTION = QuestionTarget(
    name=_VERSION_TARGET_NAME,
    question=_VERSION_QUESTION_TEXT,
)


class IntakeRejected(Exception):
    """An allowlisted code; exception messages never contain user/source text."""

    def __init__(self, code: IntakeRejectionCode) -> None:
        if code not in get_args(IntakeRejectionCode.__value__):
            raise ValueError("Unknown intake rejection code")
        self.code = code
        super().__init__(code)


def prepare_version_reply(
    case: CaseState,
    turn: UserTurn,
    *,
    proposal_id: str,
    question: AnalysisResult,
) -> UserTurn:
    """Attribute a whole release-number reply to its existing user event.

    Only an otherwise unstructured reply to the pending single registered
    ``STREAMLIT_VERSION_QUESTION`` is recognized. Both the next question and the
    displayed user draft must equal that canonical question. The caller can
    import the constant when constructing proposal requirements/display; source
    or model text cannot redefine the canonical target. Other wording and
    ordinary user corrections require explicit ``ReportedFact`` entries and
    ``propose_user_turn`` instead.

    The question contract itself carries no proposal ID or revision. The tracker
    therefore owns the binding of ``question`` to ``proposal_id``; matching the
    state's pending ID alone cannot authenticate the supplied question contents.
    Preparation changes the canonical turn hash. The tracker must deduplicate
    the original ingress turn/hash before calling this helper, atomically retain
    it with the prepared projection/transition, and return its recorded outcome
    on replay instead of preparing again after the pending question is cleared.
    """
    try:
        # Inspect nested bypassed state before dumping can silently drop it.
        # Do not export Pydantic error details.
        case = detached_contract(CaseState, case)
        turn = detached_contract(UserTurn, turn)
        question = detached_contract(AnalysisResult, question)
    except (ValidationError, ValueError, TypeError, AttributeError, RecursionError):
        raise IntakeRejected("InvalidInput") from None

    if turn.case_id != case.case_id:
        raise IntakeRejected("CaseMismatch")
    if turn.expected_revision != case.case_revision:
        raise IntakeRejected("StaleRevision")
    if (
        not isinstance(proposal_id, str)
        or case.pending_proposal_id is None
        or case.pending_proposal_id != proposal_id
    ):
        raise IntakeRejected("PendingProposalMismatch")
    return _prepare_canonical_version_reply(case, turn, question)


def prepare_approved_version_reply(
    case: CaseState,
    turn: UserTurn,
    *,
    reply: ApprovedReplyQuestion,
    proposal_id: str,
) -> UserTurn:
    """Prepare a reply to an exact question already approved and displayed.

    The caller loads ``reply`` from its authoritative approved-question record;
    a client-supplied record cannot authenticate approval. Case, revision and
    requested proposal identity must still match, and no proposal may be pending.
    This does not fabricate pending state or grant permission for an action.

    Before calling, deduplicate the original ingress event, including its reply
    binding. Persist the original event/hash, prepared turn/hash and transition
    atomically. Invalidate the approved-question record when accepting a new
    event; replay must return its recorded outcome without preparing again.
    """
    try:
        case = detached_contract(CaseState, case)
        turn = detached_contract(UserTurn, turn)
        reply = detached_contract(ApprovedReplyQuestion, reply)
    except (ValidationError, ValueError, TypeError, AttributeError, RecursionError):
        raise IntakeRejected("InvalidInput") from None

    if turn.case_id != case.case_id or reply.case_id != case.case_id:
        raise IntakeRejected("CaseMismatch")
    if turn.expected_revision != case.case_revision or reply.case_revision != case.case_revision:
        raise IntakeRejected("StaleRevision")
    if (
        not isinstance(proposal_id, str)
        or proposal_id != reply.proposal_id
        or case.pending_proposal_id is not None
    ):
        raise IntakeRejected("PendingProposalMismatch")
    return _prepare_canonical_version_reply(case, turn, reply.question)


def _prepare_canonical_version_reply(
    case: CaseState, turn: UserTurn, question: AnalysisResult
) -> UserTurn:
    """Shared extraction only after the caller-specific identity checks pass."""
    if (
        question.decision != "ask"
        or question.missing_info != (_VERSION_TARGET_NAME,)
        or question.next_question != _VERSION_QUESTION_TEXT
        or question.user_draft != _VERSION_QUESTION_TEXT
    ):
        raise IntakeRejected("InvalidVersionQuestion")
    if any(
        fact.name.casefold() == _VERSION_TARGET_NAME
        and fact.status == "active"
        and fact.provenance_kind == "user"
        for fact in case.facts
    ):
        raise IntakeRejected("VersionAlreadyKnown")
    if turn.reported_facts or turn.unknowns or turn.checks_performed or turn.context_changed:
        raise IntakeRejected("StructuredTurnNotAllowed")

    match = _VERSION_REPLY.fullmatch(turn.message)
    if match is None:
        raise IntakeRejected("VersionReplyUnclear")
    return UserTurn.model_validate(
        {
            **turn.model_dump(warnings=False),
            "reported_facts": (ReportedFact(name=_VERSION_TARGET_NAME, value=match.group(1)),),
        }
    )
