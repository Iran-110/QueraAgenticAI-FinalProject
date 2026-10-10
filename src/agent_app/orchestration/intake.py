"""Recognize a narrow version reply to a tracker-bound pending question.

This helper neither reads storage nor authenticates a proposal. The caller must
load the exact pending proposal and its ID from the tracker, then commit the
returned user turn through the usual event-deduplication/revision transaction.
No source text, model response, or free-text instruction grants action authority.
"""

import re
from typing import Literal, get_args

from pydantic import ValidationError

from agent_app.contracts import AnalysisResult, CaseState, QuestionTarget, ReportedFact, UserTurn

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
        # Revalidation detaches nested values and rejects bypass-constructed
        # objects before any extraction. Do not export Pydantic error details.
        case = CaseState.model_validate(case.model_dump(warnings=False))
        turn = UserTurn.model_validate(turn.model_dump(warnings=False))
        question = AnalysisResult.model_validate(question.model_dump(warnings=False))
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
