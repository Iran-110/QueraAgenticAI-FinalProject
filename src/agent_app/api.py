"""HTTP boundary for the Streamlit UI: offline agent runs plus maintainer review.

Every run uses scripted offline adapters: no retrieval index, no network and no
paid model calls. The case state below lives in this process only; the tracker
owner will replace it with durable storage, event deduplication and atomic
approval checks. Until then a restart or reload clears every case.
"""

import threading
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Path
from pydantic import BaseModel, Field, model_validator

from agent_app.contracts import AnalysisResult, CaseState, EvidenceBundle, RunResult, UserTurn
from agent_app.demo import SNAPSHOT_ID, _answer, _ask, _evidence
from agent_app.orchestration import SupportEngine
from agent_app.orchestration.turns import propose_user_turn
from agent_app.testing.fakes import FakeReasoner, FakeRetriever
from agent_app.tracker.dummy_tracker import tracker

app = FastAPI(title="Streamlit support assistant backend")

Scenario = Literal["ask", "answer", "refine", "escalate", "error"]
CaseId = Annotated[
    str, Path(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")
]
CaseStatus = Literal["new", "awaiting_review", "awaiting_user", "answer_sent", "escalated", "open"]


class MessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4_000)
    scenario: Scenario = "ask"


class DecisionRequest(BaseModel):
    proposal_id: str = Field(min_length=1, max_length=200)
    case_revision: int = Field(ge=0)
    decision: Literal["approve", "reject", "edit"]
    edited_draft: str | None = Field(default=None, max_length=20_000)

    @model_validator(mode="after")
    def _edit_needs_draft(self) -> "DecisionRequest":
        if self.decision == "edit" and not (self.edited_draft or "").strip():
            raise ValueError("An edit requires a non-empty edited_draft.")
        return self


@dataclass
class _Case:
    state: CaseState
    status: CaseStatus = "new"
    log: list[dict[str, Any]] = field(default_factory=list)


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
        case = _cases.setdefault(case_id, _Case(state=CaseState(case_id=case_id)))
        turn_id = f"turn-{case.state.case_revision + 1}"
        turn = UserTurn(
            case_id=case_id,
            expected_revision=case.state.case_revision,
            turn_id=turn_id,
            source_ref=f"user:{turn_id}",
            message=request.message,
        )
        # Free-text fact extraction is out of scope; each message is a new revision,
        # which makes any earlier proposal stale.
        case.state = propose_user_turn(case.state, turn).candidate
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
            tracker.submit_decision(case_id, "approve")
            case.state = case.state.model_copy(update={"pending_proposal_id": None})
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
            # An edit is a new proposal: it must be approved on its own.
            tracker.submit_decision(case_id, "edit", revised)
            tracker.pause_for_approval(case_id, revised)
            case.state = case.state.model_copy(
                update={"pending_proposal_id": revised["proposal_id"]}
            )
            case.log.append(
                {"role": "system", "text": "The maintainer edited the draft. It needs approval."}
            )
        return _view(case_id)
