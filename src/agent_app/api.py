"""HTTP boundary for the Streamlit UI: offline agent runs plus maintainer review.

Every run uses scripted offline adapters: no retrieval index, no network and no
paid model calls. The case state below lives in this process only; the tracker
owner will replace it with durable storage, event deduplication and atomic
approval checks. Until then a restart or reload clears every case.
"""

import hashlib
import json
import threading
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Path
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import Field, StringConstraints, ValidationError, model_validator

from agent_app.contracts import (
    AnalysisResult,
    ApprovedReplyQuestion,
    CaseState,
    Contract,
    EvidenceBundle,
    Identifier,
    NonnegativeInt,
    ReportedFact,
    RunResult,
    ShortText,
    Text,
    UserTurn,
)
from agent_app.demo import SNAPSHOT_ID, _answer, _ask, _evidence
from agent_app.orchestration import SupportEngine
from agent_app.orchestration.intake import IntakeRejected, prepare_approved_version_reply
from agent_app.orchestration.turns import UserTurnRejected, propose_user_turn
from agent_app.testing.fakes import FakeReasoner, FakeRetriever
from agent_app.tracker.dummy_tracker import tracker

app = FastAPI(title="Streamlit support assistant backend")

Scenario = Literal["ask", "answer", "refine", "escalate", "error"]
CaseId = Annotated[
    str, Path(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")
]
CaseStatus = Literal["new", "awaiting_review", "awaiting_user", "answer_sent", "escalated", "open"]


class MessageRequest(Contract):
    message: Annotated[
        str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=4_000)
    ]
    scenario: Scenario = "ask"
    # Leave room for the server-owned `user:` source prefix.
    turn_id: Annotated[Identifier, Field(max_length=195)] | None = None
    expected_revision: NonnegativeInt | None = None
    reported_facts: tuple[ReportedFact, ...] = Field(default=(), max_length=50)
    unknowns: tuple[ShortText, ...] = Field(default=(), max_length=100)
    checks_performed: tuple[Text, ...] = Field(default=(), max_length=100)
    context_changed: Annotated[bool, Field(strict=True)] = False
    reply_to_proposal_id: Identifier | None = None

    @property
    def structured(self) -> bool:
        return bool(
            self.reported_facts or self.unknowns or self.checks_performed or self.context_changed
        )

    def user_turn(self, case_id: str, revision: int) -> UserTurn:
        turn_id = self.turn_id or f"legacy-{uuid4()}"
        return UserTurn(
            case_id=case_id,
            expected_revision=(
                revision if self.expected_revision is None else self.expected_revision
            ),
            turn_id=turn_id,
            source_ref=f"user:{turn_id}",
            message=self.message,
            reported_facts=self.reported_facts,
            unknowns=self.unknowns,
            checks_performed=self.checks_performed,
            context_changed=self.context_changed,
        )

    @model_validator(mode="after")
    def _validate_ingress(self) -> "MessageRequest":
        if (self.turn_id is None) != (self.expected_revision is None):
            raise ValueError("Stable events require both identity and revision.")
        if (self.structured or self.reply_to_proposal_id is not None) and self.turn_id is None:
            raise ValueError("Structured events require identity and revision.")
        if self.reply_to_proposal_id is not None and self.structured:
            raise ValueError("A narrow reply cannot contain structured updates.")
        # Validate cross-field duplicates/bounds before touching case storage.
        self.user_turn("request-validation", 0)
        self.model_dump_json().encode("utf-8")
        return self


@app.exception_handler(RequestValidationError)
async def request_invalid(_request, _error: RequestValidationError) -> JSONResponse:
    """Do not echo raw request values, unknown fields or validation internals."""
    return JSONResponse(status_code=422, content={"detail": "RequestInvalid"})


class DecisionRequest(Contract):
    proposal_id: Identifier
    case_revision: NonnegativeInt
    decision: Literal["approve", "reject", "edit"]
    edited_draft: str | None = Field(default=None, max_length=20_000)

    @model_validator(mode="after")
    def _edit_needs_draft(self) -> "DecisionRequest":
        if self.decision == "edit" and not (self.edited_draft or "").strip():
            raise ValueError("An edit requires a non-empty edited_draft.")
        self.model_dump_json().encode("utf-8")
        return self


@dataclass
class _Case:
    state: CaseState
    status: CaseStatus = "new"
    log: list[dict[str, Any]] = field(default_factory=list)
    awaiting_reply: ApprovedReplyQuestion | None = None
    pending_analysis: AnalysisResult | None = None
    ingress: dict[str, dict[str, Any]] = field(default_factory=dict)
    last_intake: dict[str, Any] | None = None


_cases: dict[str, _Case] = {}
_lock = threading.Lock()


def _script(scenario: Scenario) -> tuple[list[EvidenceBundle | Exception], list[AnalysisResult]]:
    """Scripted retrieval and reasoning outputs; synthetic, never a quality result."""
    first = _evidence("demo-initial", "Synthetic background about a Streamlit user session.")
    if scenario == "ask":
        return [first], [_ask()]
    if scenario == "answer":
        return [first], [_answer("demo-initial")]
    if scenario == "refine":
        second = _evidence("demo-refined", "Synthetic evidence returned by the second search.")
        more = AnalysisResult(
            decision="retrieve_more",
            user_draft="",
            maintainer_summary="",
            rationale="A more specific query could supply the missing evidence.",
            retrieval_queries=("Streamlit widget key Session State rerun",),
        )
        return [first, second], [more, _answer("demo-refined")]
    if scenario == "escalate":
        escalate = AnalysisResult(
            decision="escalate",
            user_draft="This demo has insufficient evidence; a maintainer should review the case.",
            maintainer_summary="The synthetic evidence does not establish a safe next fix.",
            rationale="Further product investigation is required.",
        )
        return [first], [escalate]
    return [RuntimeError("Synthetic retrieval failure")], []


def _proposal(result: RunResult, bundles: list[EvidenceBundle]) -> dict[str, Any]:
    analysis = result.analysis
    assert analysis is not None
    hits = {hit.chunk_id: hit for bundle in bundles for hit in bundle.hits}
    evidence = []
    for link in analysis.evidence_links:
        hit = hits[link.chunk_id]  # The engine already rejected unknown citations.
        evidence.append(
            {
                "claim": link.claim,
                "chunk_id": hit.chunk_id,
                "source_url": hit.source_url,
                "source_type": hit.source_type,
                "source_span": hit.source_span,
                "excerpt": hit.excerpt,
            }
        )
    return {
        "proposal_id": result.run_id,
        "case_id": result.case_id,
        "case_revision": result.case_revision,
        "decision": analysis.decision,
        "user_draft": analysis.user_draft,
        "next_question": analysis.next_question,
        "maintainer_summary": analysis.maintainer_summary,
        "rationale": analysis.rationale,
        "missing_info": list(analysis.missing_info),
        "evidence": evidence,
        "warnings": sorted({warning for bundle in bundles for warning in bundle.warnings}),
        "model_attempts": result.model_attempts,
        "retrieval_rounds": result.retrieval_rounds,
        "steps": result.steps,
        "edited": False,
        "synthetic": True,
    }


def _pending(case_id: str) -> dict[str, Any] | None:
    session = tracker.get_session_state(case_id)
    return session.get("proposed_action") if session.get("is_paused") else None


def _view(case_id: str) -> dict[str, Any]:
    case = _cases.get(case_id) or _Case(state=CaseState(case_id=case_id))
    pending = _pending(case_id)
    if pending is not None:
        pending = {**pending, "stale": pending["case_revision"] != case.state.case_revision}
    return {
        "case_id": case_id,
        "case_revision": case.state.case_revision,
        "status": case.status,
        "facts": [fact.model_dump(mode="json") for fact in case.state.facts],
        "unknowns": list(case.state.unknowns),
        "checks_performed": list(case.state.checks_performed),
        "evidence_refs": list(case.state.evidence_refs),
        "awaiting_reply": (
            case.awaiting_reply.model_dump(mode="json") if case.awaiting_reply else None
        ),
        "intake": dict(case.last_intake) if case.last_intake else None,
        "pending": pending,
        "log": list(case.log),
        "decisions": list(tracker.get_session_state(case_id).get("history", [])),
        "mode": "synthetic_offline",
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "mode": "synthetic_offline"}


@app.get("/cases/{case_id}")
def get_case(case_id: CaseId) -> dict[str, Any]:
    with _lock:
        return _view(case_id)


@app.post("/cases/{case_id}/messages")
def post_message(case_id: CaseId, request: MessageRequest) -> dict[str, Any]:
    with _lock:
        case = _cases.get(case_id) or _Case(state=CaseState(case_id=case_id))
        try:
            turn = request.user_turn(case_id, case.state.case_revision)
            # Identity covers the ORIGINAL validated ingress, including its
            # question binding and offline scenario, before any preparation.
            ingress_hash = hashlib.sha256(
                json.dumps(
                    {
                        "turn": turn.model_dump(mode="json"),
                        "scenario": request.scenario,
                        "reply_to_proposal_id": request.reply_to_proposal_id,
                    },
                    sort_keys=True,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(status_code=422, detail="RequestInvalid") from None

        recorded = case.ingress.get(turn.turn_id) if request.turn_id is not None else None
        if recorded is not None:
            if recorded["ingress_hash"] != ingress_hash:
                raise HTTPException(status_code=409, detail="EventConflict")
            # A replay returns the current view and the ORIGINAL receipt. It
            # neither re-prepares a cleared question nor reruns the agent.
            return {**_view(case_id), "intake": {**recorded, "replayed": True}}
        if turn.expected_revision != case.state.case_revision:
            raise HTTPException(status_code=409, detail="StaleRevision")

        preparation = "structured" if request.structured else "unstructured"
        if request.reply_to_proposal_id is not None:
            if case.awaiting_reply is None:
                raise HTTPException(status_code=409, detail="PendingReplyMissing")
            try:
                turn = prepare_approved_version_reply(
                    case.state,
                    turn,
                    reply=case.awaiting_reply,
                    proposal_id=request.reply_to_proposal_id,
                )
            except IntakeRejected as error:
                status = (
                    409
                    if error.code in {"CaseMismatch", "StaleRevision", "PendingProposalMismatch"}
                    else 422
                )
                raise HTTPException(status_code=status, detail=error.code) from None
            preparation = "canonical_version_reply"
        try:
            transition = propose_user_turn(case.state, turn)
        except UserTurnRejected as error:
            status = 409 if error.code in {"CaseMismatch", "StaleRevision"} else 422
            raise HTTPException(status_code=status, detail=error.code) from None

        case.state = transition.candidate
        case.awaiting_reply = None
        case.pending_analysis = None
        case.status = "open"
        receipt = {
            "turn_id": turn.turn_id,
            "ingress_hash": ingress_hash,
            "prepared_hash": transition.event_hash,
            "committed_revision": case.state.case_revision,
            "changed_fact_names": list(transition.changed_fact_names),
            "context_changed": transition.context_changed,
            "invalidated_checks": list(transition.invalidated_checks),
            "preparation": preparation,
            "replayed": False,
        }
        case.last_intake = receipt
        case.ingress[turn.turn_id] = receipt
        # Commit ingress before running the agent: even a failed run must not
        # accept the same event twice. This is process-local, not durable CAS.
        _cases[case_id] = case
        case.log.append({"role": "user", "text": request.message})

        retrieval, reasoning = _script(request.scenario)
        bundles = [bundle for bundle in retrieval if isinstance(bundle, EvidenceBundle)]
        engine = SupportEngine(
            FakeRetriever(retrieval),
            FakeReasoner(reasoning),
            snapshot_id=SNAPSHOT_ID,
            current_revision=lambda cid: _cases[cid].state.case_revision,
        )
        result = engine.run(case.state, request.message)
        if result.status == "awaiting_approval":
            proposal = _proposal(result, bundles)
            tracker.pause_for_approval(case_id, proposal)
            case.state = case.state.model_copy(update={"pending_proposal_id": result.run_id})
            case.pending_analysis = result.analysis
            case.status = "awaiting_review"
        else:
            case.status = "open"
            case.log.append(
                {
                    "role": "system",
                    "text": f"The run stopped ({result.status}: {result.error_code}). "
                    "Nothing was proposed.",
                }
            )
        return _view(case_id)


@app.post("/cases/{case_id}/decision")
def post_decision(case_id: CaseId, request: DecisionRequest) -> dict[str, Any]:
    with _lock:
        case = _cases.get(case_id)
        if case is None:
            raise HTTPException(status_code=404, detail="Case not found.")
        pending = _pending(case_id)
        if pending is None:
            raise HTTPException(status_code=409, detail="No proposal is awaiting review.")
        if request.proposal_id != pending["proposal_id"]:
            raise HTTPException(
                status_code=409, detail="This proposal was replaced. Review the current one."
            )
        current = case.state.case_revision
        if request.case_revision != current or pending["case_revision"] != current:
            raise HTTPException(
                status_code=409,
                detail="The case changed after this proposal was made. It cannot be approved.",
            )

        if request.decision == "approve":
            if case.pending_analysis is None:
                raise HTTPException(status_code=409, detail="PendingProposalMismatch")
            reply = (
                ApprovedReplyQuestion(
                    case_id=case_id,
                    case_revision=current,
                    proposal_id=pending["proposal_id"],
                    question=case.pending_analysis,
                )
                if pending["decision"] == "ask"
                else None
            )
            tracker.submit_decision(case_id, "approve")
            case.state = case.state.model_copy(update={"pending_proposal_id": None})
            case.awaiting_reply = reply
            case.pending_analysis = None
            case.status = {
                "ask": "awaiting_user",
                "answer": "answer_sent",
                "escalate": "escalated",
            }[pending["decision"]]
            case.log.append(
                {
                    "role": "assistant",
                    "text": pending["user_draft"],
                    "decision": pending["decision"],
                    "edited": pending["edited"],
                }
            )
        elif request.decision == "reject":
            tracker.submit_decision(case_id, "reject")
            case.state = case.state.model_copy(update={"pending_proposal_id": None})
            case.awaiting_reply = None
            case.pending_analysis = None
            case.status = "open"
            case.log.append(
                {
                    "role": "system",
                    "text": "The maintainer rejected the proposal. Nothing was sent.",
                }
            )
        else:
            draft = request.edited_draft.strip()
            revised = {
                **pending,
                "proposal_id": str(uuid4()),
                "user_draft": draft,
                "next_question": draft if pending["decision"] == "ask" else None,
                "edited": True,
                "edited_from": pending["proposal_id"],
            }
            if case.pending_analysis is None:
                raise HTTPException(status_code=409, detail="PendingProposalMismatch")
            edited_analysis = AnalysisResult.model_validate(
                {
                    **case.pending_analysis.model_dump(mode="json"),
                    "user_draft": draft,
                    "next_question": draft if pending["decision"] == "ask" else None,
                }
            )
            # An edit is a new proposal: it must be approved on its own.
            tracker.submit_decision(case_id, "edit", revised)
            tracker.pause_for_approval(case_id, revised)
            case.state = case.state.model_copy(
                update={"pending_proposal_id": revised["proposal_id"]}
            )
            case.awaiting_reply = None
            case.pending_analysis = edited_analysis
            case.log.append(
                {"role": "system", "text": "The maintainer edited the draft. It needs approval."}
            )
        return _view(case_id)
