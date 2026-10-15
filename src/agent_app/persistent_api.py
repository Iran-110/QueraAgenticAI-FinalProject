"""Opt-in HTTP composition of the existing core and SQLite tracker.

SQLite owns all state, run outcomes, review receipts and local actions. HTTP
never mirrors state into api._cases, resumes an original event, or releases a
comment itself. Default ports remain scripted and offline.
"""

import secrets
from collections.abc import Callable, Mapping
from typing import Annotated, Any, Literal

from fastapi import FastAPI, Header, HTTPException
from fastapi.exceptions import RequestValidationError
from pydantic import model_validator

from agent_app import api
from agent_app.contracts import CaseState, Identifier, RunResult, Sha256, TrackerCaseView
from agent_app.orchestration import engine as engine_module
from agent_app.orchestration.handoff import ensure_handoff_current
from agent_app.orchestration.service import CoreAdapters, CoreTurnService
from agent_app.tracker.sqlite_tracker import SQLiteCaseTracker, TrackerRejected

BACKEND = "sqlite_case_tracker"
_CONFLICTS = frozenset(
    {
        "EventConflict",
        "StaleRevision",
        "CaseMismatch",
        "PendingReplyMissing",
        "PendingProposalMismatch",
        "ReviewConflict",
        "HandoffDigestMismatch",
        "CaseContentMismatch",
        "ProposalConflict",
        "RunOutcomeConflict",
        "RunOutcomeMissing",
    }
)
_INVALID = frozenset(
    {
        "InvalidInput",
        "InvalidEventContext",
        "InvalidVersionQuestion",
        "VersionAlreadyKnown",
        "StructuredTurnNotAllowed",
        "VersionReplyUnclear",
        "StateLimitExceeded",
        "DecisionInvalid",
        "ReviewIdInvalid",
        "EditedProposalInvalid",
        "RunResultInvalid",
    }
)


class DurableDecisionRequest(api.DecisionRequest):
    """The exact displayed proposal and one client-created review operation."""

    review_id: Identifier
    expected_handoff_sha256: Sha256

    @model_validator(mode="after")
    def reject_unused_edit(self):
        if self.decision != "edit" and self.edited_draft is not None:
            raise ValueError("Only an edit supplies a draft.")
        return self


def _raise_tracker(error: Exception) -> None:
    # Tracker exception objects are mutable; unknown values never escape.
    try:
        code = getattr(error, "code", None) if isinstance(error, TrackerRejected) else None
    except Exception:
        code = None
    if type(code) is not str:
        code = None
    if type(code) is str and code in _CONFLICTS:
        raise HTTPException(status_code=409, detail=code) from None
    if type(code) is str and code in _INVALID:
        raise HTTPException(status_code=422, detail=code) from None
    if code == "ReviewerUnauthorized":
        raise HTTPException(status_code=401, detail="ReviewerUnauthorized") from None
    raise HTTPException(status_code=503, detail="TrackerUnavailable") from None


def create_app(
    tracker: SQLiteCaseTracker,
    *,
    reviewer_tokens: Mapping[str, str],
    adapters: Callable[[api.Scenario], api.RunAdapters] | None = None,
    case_adapters: Callable[[CaseState, api.Scenario], api.RunAdapters] | None = None,
    evidence_scope: Literal["all", "exact_user_version"] = "all",
    retrieval_label: Literal["scripted", "local_chroma_hash"] = "scripted",
    reasoning_label: Literal[
        "scripted", "grounded_fake_gateway", "metis_grounded_live"
    ] = "scripted",
) -> FastAPI:
    """Caller explicitly supplies storage/config; no .env or default DB is read.

    Reviewer identity is resolved from configured bearer credentials, then the
    existing tracker authenticates it again. Empty configuration fails closed.
    Applications should bind this local prototype to loopback.
    ``case_adapters`` receives a detached authoritative committed case after
    ingress. It is mutually exclusive with legacy scenario-only ``adapters``;
    exact event replay allocates neither. It never receives review gold.
    ``evidence_scope`` is trusted application configuration. Current-installation
    advice may select ``exact_user_version``; comparison workflows retain ``all``.
    """
    if (
        not isinstance(tracker, SQLiteCaseTracker)
        or (adapters is not None and not callable(adapters))
        or (case_adapters is not None and not callable(case_adapters))
        or (adapters is not None and case_adapters is not None)
        or type(evidence_scope) is not str
        or evidence_scope not in {"all", "exact_user_version"}
        or retrieval_label not in {"scripted", "local_chroma_hash"}
        or reasoning_label not in {"scripted", "grounded_fake_gateway", "metis_grounded_live"}
        or (reasoning_label != "scripted" and adapters is None and case_adapters is None)
    ):
        raise ValueError("Invalid persistent HTTP configuration.")
    reviewers = dict(reviewer_tokens)
    if any(
        type(k) is not str or type(v) is not str or not k or not v for k, v in reviewers.items()
    ) or len(set(reviewers.values())) != len(reviewers):
        raise ValueError("Invalid persistent HTTP configuration.")
    mode = (
        "development_live_sqlite"
        if reasoning_label == "metis_grounded_live"
        else "synthetic_offline_sqlite"
    )
    app = FastAPI(title="Streamlit support assistant — SQLite backend")
    app.add_exception_handler(RequestValidationError, api.request_invalid)

    def view(case_id: str) -> dict[str, Any]:
        try:
            stored = tracker.read_runtime_view(case_id)
            snapshot = TrackerCaseView.model_validate(stored["view"])
            state = snapshot.state
            if state.case_id != case_id:
                raise ValueError
            pending = None
            if snapshot.pending_handoff is not None:
                handoff = snapshot.pending_handoff
                ensure_handoff_current(handoff, state, state.pending_proposal_id)
                measured = stored["pending_result"]
                # Older databases may lack measured counters. Unknown stays
                # None; no synthetic RunResult is constructed after restart.
                result = RunResult.model_validate(measured) if measured is not None else None
                pending = api._proposal(handoff, result, edited_from=stored["pending_edited_from"])
                pending["stale"] = False
            return {
                "case_id": state.case_id,
                "case_revision": state.case_revision,
                "status": snapshot.status,
                "facts": [f.model_dump(mode="json") for f in state.facts],
                "unknowns": list(state.unknowns),
                "checks_performed": list(state.checks_performed),
                "evidence_refs": list(state.evidence_refs),
                "awaiting_reply": snapshot.awaiting_reply.model_dump(mode="json")
                if snapshot.awaiting_reply
                else None,
                "intake": stored["intake"],
                "pending": pending,
                "log": stored["log"],
                "decisions": stored["decisions"],
                "review": stored["review"],
                "actions": stored["actions"],
                "run_outcome": stored["run_outcome"],
                "mode": mode,
                "tracker_backend": BACKEND,
                "retrieval_label": retrieval_label,
                "reasoning_label": reasoning_label,
                "quality_claim": False,
            }
        except Exception:
            raise HTTPException(status_code=503, detail="TrackerUnavailable") from None

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "mode": mode,
            "tracker_backend": BACKEND,
            "capabilities": {
                "stable_event_ids": True,
                "durable_reviews": True,
                "reviewer_auth": "bearer",
            },
            "retrieval_label": retrieval_label,
            "reasoning_label": reasoning_label,
            "quality_claim": False,
        }

    @app.get("/cases/{case_id}")
    def get_case(case_id: api.CaseId):
        return view(case_id)

    @app.post("/cases/{case_id}/messages")
    def post_message(case_id: api.CaseId, request: api.MessageRequest):
        if request.turn_id is None or request.expected_revision is None:
            raise HTTPException(status_code=422, detail="RequestInvalid")

        def factory(_case, _message, _run_id):
            ports = (
                case_adapters(_case.model_copy(deep=True), request.scenario)
                if case_adapters is not None
                else (adapters or api._adapters)(request.scenario)
            )
            return CoreAdapters(
                ports.retriever,
                ports.reasoner,
                ports.snapshot_id,
                ports.grounded_request_supplier,
                ports.cleanup,
                ports.retrieval_profile,
            )

        service = CoreTurnService(
            tracker,
            factory,
            stage_with_result=tracker.stage_run_proposal,
            evidence_scope=evidence_scope,
        )
        outcome = service.submit(
            request.user_turn(case_id, request.expected_revision),
            reply_to_proposal_id=request.reply_to_proposal_id,
            event_context={"scenario": request.scenario},
            run_id=str(engine_module.uuid4()),
        )
        if outcome.status == "ingress_rejected":
            _raise_tracker(TrackerRejected(outcome.error_code))
        if outcome.status == "ingress_unknown" or outcome.receipt is None:
            raise HTTPException(status_code=503, detail="TrackerIngressUnknown")
        if not outcome.receipt.replayed and outcome.status != "proposal_staged":
            try:
                tracker.finish_run(
                    case_id,
                    outcome.receipt.turn_id,
                    status=outcome.status,
                    error_code=outcome.error_code,
                    run_result=outcome.run_result,
                )
            except Exception:
                # Ingress may have committed. A503 is an ambiguous acknowledgment,
                # not a rollback claim; retry keeps the original event identity.
                raise HTTPException(status_code=503, detail="RunOutcomeUnavailable") from None
        current = view(case_id)
        return {**current, "intake": outcome.receipt.model_dump(mode="json")}

    @app.post("/cases/{case_id}/decision")
    def post_decision(
        case_id: api.CaseId,
        request: DurableDecisionRequest,
        authorization: Annotated[str | None, Header()] = None,
    ):
        supplied = (
            authorization[7:] if authorization and authorization.startswith("Bearer ") else ""
        )
        reviewer = None
        for name, credential in reviewers.items():
            if secrets.compare_digest(supplied.encode("utf-8"), credential.encode("utf-8")):
                reviewer = name
        if reviewer is None:
            raise HTTPException(status_code=401, detail="ReviewerUnauthorized")
        try:
            receipt = tracker.review(
                case_id,
                review_id=request.review_id,
                proposal_id=request.proposal_id,
                expected_revision=request.case_revision,
                expected_handoff_sha256=request.expected_handoff_sha256,
                decision=request.decision,
                reviewer_id=reviewer,
                reviewer_token=supplied,
                edited_draft=request.edited_draft,
            )
        except Exception as error:
            _raise_tracker(error)
        return {**view(case_id), "review": receipt}

    return app
