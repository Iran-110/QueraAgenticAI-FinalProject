"""Small HTTP client the Streamlit UI uses to talk to the FastAPI backend."""

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, get_args
from uuid import uuid4

import httpx

from agent_app.contracts import (
    ApprovedReplyQuestion,
    ProposalHandoff,
    RunResult,
    TrackerTurnReceipt,
)
from agent_app.orchestration.conversation import ConversationCode
from agent_app.orchestration.handoff import HandoffCode, validate_handoff
from agent_app.orchestration.ports import ReasoningStopCode

DEFAULT_BASE_URL = "http://127.0.0.1:8000"

# Allowlisted API codes mapped to text a user or reviewer can act on.
ERROR_TEXT = {
    "StaleRevision": "The case changed before this message arrived. Review the latest state "
    "and send it again.",
    "EventConflict": "This message ID was already used with different content. Start a new "
    "message.",
    "PendingReplyMissing": "There is no approved question to reply to.",
    "PendingProposalMismatch": "The question you replied to is no longer current.",
    "InvalidVersionQuestion": "Only the approved Streamlit version question accepts a short "
    "version reply.",
    "VersionAlreadyKnown": "The Streamlit version is already confirmed. Use a correction instead.",
    "VersionReplyUnclear": "Reply with a release number only, for example 1.50.0.",
    "StructuredTurnNotAllowed": "A version reply cannot include other updates.",
    "StateLimitExceeded": "The case has too many recorded facts or checks.",
    "CaseMismatch": "This update belongs to a different case.",
    "RequestInvalid": "The request was rejected as invalid. Check for duplicate or empty fields.",
    "EditedProposalInvalid": "The edited draft is not a valid proposal.",
    "ReviewerUnauthorized": "Maintainer authorization is missing or was rejected. Check the "
    "trusted UI configuration before retrying.",
    "HandoffDigestMismatch": "The reviewed proposal no longer matches this request. Review the "
    "latest proposal before making a new decision.",
    "ReviewConflict": "This review ID was already used with different content.",
    "TrackerUnavailable": "The tracker could not confirm this request. Retry the identical "
    "request to check its receipt.",
    "TrackerIngressUnknown": "The update was not confirmed. Retry the identical message.",
    "RunOutcomeUnavailable": "The update may be recorded, but its result was not confirmed. "
    "Retry the identical message.",
    "BackendResponseInvalid": "The backend returned an unreadable response. The request may "
    "already be recorded; retry the identical request.",
    "BackendCapabilitiesInvalid": "The backend does not advertise a supported offline API. "
    "Check the backend configuration.",
    "BackendCapabilityMismatch": "The backend changed its review protocol. Restore the "
    "original backend before retrying this review.",
    "SavedCaseIdInvalid": "Use a case ID of 1–200 letters, numbers, dots, underscores or "
    "hyphens, starting with a letter or number.",
    "SavedCasesUnavailable": "This backend does not support opening saved cases.",
    "SavedCaseNotFound": "No saved case was found for that ID.",
}

OUTCOME_STATUSES = frozenset(
    {
        "interrupted",
        "proposal_staged",
        "core_stopped",
        "proposal_not_pending",
        "superseded_before_run",
        "staging_unknown",
    }
)
OUTCOME_CODES = frozenset(
    {
        "RunInterrupted",
        "RunOutcomeUnavailable",
        "AdapterSetupFailed",
        "AdapterCleanupFailed",
        "AdapterSetupUnavailable",
        "CoreRunFailed",
        "InvalidTrackerReceipt",
        "TrackerLifecycleChanged",
        "TrackerStagingUnknown",
        "CaseReadFailed",
        "ProposalConflict",
        "StepLimitExceeded",
        "InvalidInput",
        "ModelAttemptLimitExceeded",
        "RetrievalRoundLimitExceeded",
        "QueryLimitExceeded",
        "RepeatedQuery",
        "InvalidRetrievalQuery",
        "RetrievalUnavailable",
        "RetrievalResultInvalid",
        "ModelOutputInvalid",
        "GroundedSourceMismatch",
        "ReasoningUnavailable",
        "UnknownEvidenceReference",
        "AnswerWithoutEvidence",
        "UnsupportedFactUpdate",
        "UnsupportedUserFact",
        "UnknownFactSource",
        "ConflictingEvidenceFact",
        "KnownFactMarkedMissing",
        "RepeatedCheck",
        *get_args(HandoffCode.__value__),
        *get_args(ConversationCode.__value__),
        *get_args(ReasoningStopCode.__value__),
    }
)
SYSTEM_NOTICES = frozenset(
    {
        "The maintainer edited the draft. It needs approval.",
        "The maintainer rejected the proposal. Nothing was sent.",
        "The input was committed, but no run outcome is recorded. Replay will not resume it automatically.",
    }
)


@dataclass(frozen=True)
class BackendCapabilities:
    durable_reviews: bool
    retrieval_label: str = "scripted"
    reasoning_label: str = "scripted"


@dataclass(frozen=True)
class ReviewOperation:
    """An immutable public request; no credential belongs in a retry operation."""

    case_id: str
    body_json: str = field(repr=False)
    durable: bool

    def payload(self) -> dict[str, Any]:
        # Each caller gets a detached copy; widget edits cannot change a saved retry.
        return json.loads(self.body_json)


class BackendError(Exception):
    """A user-presentable failure; never carries request bodies or credentials.

    ``retryable`` means delivery or acknowledgment is uncertain. Durable retries
    keep the original identity, even when the first request already committed.
    """

    def __init__(self, message: str, *, code: str | None = None, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


def lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def reported_facts(rows: list[dict[str, Any]]) -> list[dict[str, str | None]]:
    """Turn fact-editor rows into explicit reports; a withdrawal sends ``None``."""
    facts: list[dict[str, str | None]] = []
    for row in rows:
        name = (row.get("name") or "").strip()
        if not name:
            continue
        value = (row.get("value") or "").strip()
        if row.get("withdraw"):
            facts.append({"name": name, "value": None})
        elif value:
            facts.append({"name": name, "value": value})
    return facts


def new_event(
    message: str,
    *,
    expected_revision: int,
    scenario: str,
    reported_facts: list[dict[str, str | None]] | None = None,
    checks_performed: list[str] | None = None,
    unknowns: list[str] | None = None,
    context_changed: bool = False,
    reply_to_proposal_id: str | None = None,
) -> dict[str, Any]:
    """Build one event with a stable ID; a retry must resend this exact payload."""
    event: dict[str, Any] = {
        "message": message,
        "scenario": scenario,
        "turn_id": f"ui-{uuid4().hex}",
        "expected_revision": expected_revision,
    }
    if reply_to_proposal_id is not None:
        event["reply_to_proposal_id"] = reply_to_proposal_id
        return event
    event.update(
        reported_facts=reported_facts or [],
        checks_performed=checks_performed or [],
        unknowns=unknowns or [],
        context_changed=context_changed,
    )
    return event


class BackendClient:
    def __init__(self, http: httpx.Client, *, reviewer_token: str | None = None) -> None:
        self._http = http
        self._reviewer_token = reviewer_token
        self._capabilities: BackendCapabilities | None = None

    @property
    def reviewer_configured(self) -> bool:
        return bool(self._reviewer_token)

    def discover_capabilities(self) -> BackendCapabilities:
        health = self._request("GET", "/health")
        if health == {"status": "ok", "mode": "synthetic_offline"}:
            capabilities = BackendCapabilities(durable_reviews=False)
        elif (
            health.get("status") == "ok"
            and health.get("mode")
            == (
                "development_live_sqlite"
                if health.get("reasoning_label") == "metis_grounded_live"
                else "synthetic_offline_sqlite"
            )
            and health.get("tracker_backend") == "sqlite_case_tracker"
            and health.get("capabilities")
            == {"stable_event_ids": True, "durable_reviews": True, "reviewer_auth": "bearer"}
            and type(health["capabilities"]["stable_event_ids"]) is bool
            and type(health["capabilities"]["durable_reviews"]) is bool
            and isinstance(health.get("retrieval_label"), str)
            and health.get("retrieval_label") in {"scripted", "local_chroma_hash"}
            and isinstance(health.get("reasoning_label"), str)
            and health.get("reasoning_label")
            in {"scripted", "grounded_fake_gateway", "metis_grounded_live"}
            and health.get("quality_claim") is False
        ):
            capabilities = BackendCapabilities(
                durable_reviews=True,
                retrieval_label=health["retrieval_label"],
                reasoning_label=health["reasoning_label"],
            )
        else:
            self._capabilities = None
            raise BackendError(
                ERROR_TEXT["BackendCapabilitiesInvalid"], code="BackendCapabilitiesInvalid"
            )
        self._capabilities = capabilities
        return capabilities

    def prepare_review(
        self,
        case_id: str,
        proposal: dict[str, Any],
        decision: str,
        *,
        edited_draft: str | None = None,
    ) -> ReviewOperation:
        capabilities = self._capabilities or self.discover_capabilities()
        if capabilities.durable_reviews and not self.reviewer_configured:
            raise BackendError(ERROR_TEXT["ReviewerUnauthorized"], code="ReviewerUnauthorized")
        try:
            handoff = self._displayed_proposal(proposal, case_id)
            if proposal["case_id"] != case_id or decision not in {"approve", "reject", "edit"}:
                raise ValueError
            if proposal["stale"]:
                raise BackendError(ERROR_TEXT["StaleRevision"], code="StaleRevision")
            payload = {
                "proposal_id": proposal["proposal_id"],
                "case_revision": proposal["case_revision"],
                "decision": decision,
                "edited_draft": edited_draft if decision == "edit" else None,
            }
            if capabilities.durable_reviews:
                digest = handoff.handoff_sha256
                payload.update(review_id=f"ui-review-{uuid4().hex}", expected_handoff_sha256=digest)
            return ReviewOperation(
                case_id, json.dumps(payload, sort_keys=True), capabilities.durable_reviews
            )
        except (KeyError, TypeError, ValueError):
            raise self._invalid_response() from None

    def send_review(self, operation: ReviewOperation) -> dict[str, Any]:
        # A backend can restart with a different protocol while the browser keeps
        # an old operation. Never send that operation, or its credential, there.
        capabilities = self.discover_capabilities()
        if operation.durable != capabilities.durable_reviews:
            raise BackendError(
                ERROR_TEXT["BackendCapabilityMismatch"], code="BackendCapabilityMismatch"
            )
        headers = {}
        if operation.durable:
            if not self.reviewer_configured:
                raise BackendError(ERROR_TEXT["ReviewerUnauthorized"], code="ReviewerUnauthorized")
            headers["Authorization"] = f"Bearer {self._reviewer_token}"
        payload = operation.payload()
        view = self._case_response(
            self._request(
                "POST", f"/cases/{operation.case_id}/decision", json=payload, headers=headers
            ),
            operation.case_id,
        )
        if operation.durable:
            receipt = view.get("review")
            if (
                not isinstance(receipt, dict)
                or any(
                    receipt.get(key) != value
                    for key, value in {
                        "case_id": operation.case_id,
                        "review_id": payload["review_id"],
                        "proposal_id": payload["proposal_id"],
                        "revision": payload["case_revision"],
                        "decision": payload["decision"],
                    }.items()
                )
                or type(receipt.get("replayed")) is not bool
            ):
                raise self._invalid_response()
        return view

    def get_case(self, case_id: str) -> dict[str, Any]:
        return self._case_response(self._request("GET", f"/cases/{case_id}"), case_id)

    def get_saved_case(self, case_id: str) -> dict[str, Any]:
        """Load a manually named durable case without creating or resuming it."""
        if (
            type(case_id) is not str
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}", case_id) is None
        ):
            raise BackendError(ERROR_TEXT["SavedCaseIdInvalid"], code="SavedCaseIdInvalid")
        if not self.discover_capabilities().durable_reviews:
            raise BackendError(ERROR_TEXT["SavedCasesUnavailable"], code="SavedCasesUnavailable")
        view = self.get_case(case_id)
        # The durable GET deliberately returns an empty view for an unknown ID.
        # Only committed input makes a case eligible for reopening in the UI.
        if view["case_revision"] == 0:
            raise BackendError(ERROR_TEXT["SavedCaseNotFound"], code="SavedCaseNotFound")
        return view

    def send_event(self, case_id: str, event: dict[str, Any]) -> dict[str, Any]:
        view = self._case_response(
            self._request("POST", f"/cases/{case_id}/messages", json=event), case_id
        )
        receipt = view["intake"]
        if (
            receipt is None
            or receipt.get("case_id", case_id) != case_id
            or receipt["turn_id"] != event.get("turn_id")
            or receipt["committed_revision"] != event.get("expected_revision", -1) + 1
        ):
            raise self._invalid_response()
        return view

    def decide(
        self,
        case_id: str,
        *,
        proposal_id: str,
        case_revision: int,
        decision: str,
        edited_draft: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "proposal_id": proposal_id,
            "case_revision": case_revision,
            "decision": decision,
            "edited_draft": edited_draft,
        }
        return self._case_response(
            self._request("POST", f"/cases/{case_id}/decision", json=payload), case_id
        )

    @staticmethod
    def _invalid_response() -> BackendError:
        return BackendError(
            ERROR_TEXT["BackendResponseInvalid"], code="BackendResponseInvalid", retryable=True
        )

    @staticmethod
    def _review_receipt(receipt: Any, case_id: str) -> bool:
        required = {
            "case_id",
            "review_id",
            "proposal_id",
            "revision",
            "reviewer_id",
            "decision",
            "status",
            "action_id",
            "new_proposal_id",
            "replayed",
        }
        return (
            isinstance(receipt, dict)
            and receipt.keys() == required
            and receipt["case_id"] == case_id
            and all(
                isinstance(receipt[key], str) and 0 < len(receipt[key]) <= 200
                for key in ("case_id", "review_id", "proposal_id", "reviewer_id")
            )
            and type(receipt["revision"]) is int
            and receipt["revision"] >= 0
            and receipt["decision"] in {"approve", "reject", "edit"}
            and receipt["status"]
            in {"open", "awaiting_review", "awaiting_user", "answer_sent", "escalated"}
            and all(
                receipt[key] is None or isinstance(receipt[key], str)
                for key in ("action_id", "new_proposal_id")
            )
            and type(receipt["replayed"]) is bool
        )

    @staticmethod
    def _displayed_proposal(proposal: Any, case_id: str) -> ProposalHandoff:
        """Bind every duplicated review field to the complete, checked handoff."""
        required = {
            "proposal_id",
            "case_id",
            "case_revision",
            "decision",
            "user_draft",
            "next_question",
            "missing_info",
            "maintainer_summary",
            "rationale",
            "facts_delta",
            "checks_suggested",
            "retrieval_queries",
            "analysis",
            "review_handoff",
            "evidence",
            "warnings",
            "model_attempts",
            "retrieval_rounds",
            "steps",
            "edited",
            "synthetic",
            "stale",
        }
        if not isinstance(proposal, dict) or not required <= proposal.keys():
            raise ValueError
        handoff = validate_handoff(ProposalHandoff.model_validate(proposal["review_handoff"]))
        analysis = handoff.analysis.model_dump(mode="json")
        rendered = {
            "decision",
            "user_draft",
            "next_question",
            "missing_info",
            "maintainer_summary",
            "rationale",
            "facts_delta",
            "checks_suggested",
            "retrieval_queries",
        }
        hits = {hit.chunk_id: hit for hit in handoff.evidence.hits}
        inventory = {entry.chunk_id: entry for entry in handoff.source_inventory}
        evidence = [
            {
                "claim": link.claim,
                **hits[link.chunk_id].model_dump(mode="json"),
                "content_sha256": inventory[link.chunk_id].content_sha256,
                "version_scope": inventory[link.chunk_id].version_scope,
            }
            for link in handoff.analysis.evidence_links
        ]
        if (
            handoff.case.case_id != case_id
            or proposal["case_id"] != case_id
            or proposal["proposal_id"] != handoff.proposal_id
            or type(proposal["case_revision"]) is not int
            or proposal["case_revision"] != handoff.case.case_revision
            or proposal["analysis"] != analysis
            or any(proposal[key] != analysis[key] for key in rendered)
            or proposal["evidence"] != evidence
            or proposal["warnings"] != sorted(set(handoff.evidence.warnings))
            or any(type(proposal[key]) is not bool for key in ("stale", "edited", "synthetic"))
            or any(
                proposal[key] is not None
                and (type(proposal[key]) is not int or not 0 <= proposal[key] <= limit)
                for key, limit in (("model_attempts", 2), ("retrieval_rounds", 2), ("steps", 8))
            )
        ):
            raise ValueError
        return handoff

    @classmethod
    def _case_response(cls, view: dict[str, Any], case_id: str) -> dict[str, Any]:
        """Reject unusable success bodies without exporting backend data or validators."""
        try:
            if (
                view["case_id"] != case_id
                or type(view["case_revision"]) is not int
                or view["case_revision"] < 0
                or view["status"]
                not in {
                    "new",
                    "open",
                    "awaiting_review",
                    "awaiting_user",
                    "answer_sent",
                    "escalated",
                }
                or not all(
                    isinstance(view[key], list)
                    for key in ("log", "facts", "unknowns", "checks_performed", "decisions")
                )
                or not all(
                    isinstance(item, str)
                    for key in ("unknowns", "checks_performed")
                    for item in view[key]
                )
            ):
                raise ValueError
            for entry in view["log"]:
                if entry["role"] not in {"system", "user", "assistant"} or not isinstance(
                    entry["text"], str
                ):
                    raise ValueError
                if entry["role"] == "system" and entry["text"] not in SYSTEM_NOTICES:
                    # Operational messages are not user/source content. Unknown
                    # diagnostics must never become visible exception text.
                    entry["text"] = "The agent run stopped. No new proposal was produced."
            for fact in view["facts"]:
                if not all(
                    isinstance(fact[key], str)
                    for key in ("name", "value", "status", "provenance_kind", "turn_id")
                ):
                    raise ValueError
            intake = view["intake"]
            if intake is not None:
                bound_receipt = (
                    {"case_id": case_id, **intake}
                    if isinstance(intake, dict) and view.get("mode") == "synthetic_offline"
                    else intake
                )
                if TrackerTurnReceipt.model_validate(bound_receipt).case_id != case_id:
                    raise ValueError
            pending = view["pending"]
            if pending is not None:
                handoff = cls._displayed_proposal(pending, case_id)
                stale = handoff.case.case_revision != view["case_revision"]
                if handoff.case.case_revision > view["case_revision"] or pending["stale"] != stale:
                    raise ValueError
                if not stale:
                    case = handoff.case.model_dump(mode="json")
                    if any(
                        view[key] != case[key]
                        for key in ("facts", "unknowns", "checks_performed", "evidence_refs")
                    ):
                        raise ValueError
            awaiting = view["awaiting_reply"]
            if awaiting is not None:
                if ApprovedReplyQuestion.model_validate(awaiting).case_id != case_id:
                    raise ValueError
            for review in view["decisions"]:
                if view.get("tracker_backend") == "sqlite_case_tracker":
                    if not isinstance(review, dict) or review.keys() != {
                        "action",
                        "decision",
                        "receipt",
                    }:
                        raise ValueError
                    receipt = review["receipt"]
                    action = review["action"]
                    if (
                        not cls._review_receipt(receipt, case_id)
                        or review["decision"] != receipt["decision"]
                    ):
                        raise ValueError
                    handoff = validate_handoff(
                        ProposalHandoff.model_validate(action["review_handoff"])
                    )
                    if (
                        action["case_id"] != case_id
                        or handoff.case.case_id != case_id
                        or action["case_revision"] != receipt["revision"]
                        or handoff.case.case_revision != receipt["revision"]
                        or action["proposal_id"]
                        != (receipt["new_proposal_id"] or receipt["proposal_id"])
                        or action["proposal_id"] != handoff.proposal_id
                        or action["decision"] != handoff.analysis.decision
                        or action["user_draft"] != handoff.analysis.user_draft
                        or type(action["edited"]) is not bool
                    ):
                        raise ValueError
                elif (
                    not isinstance(review, dict)
                    or review.get("decision") not in {"approve", "reject", "edit"}
                    or not isinstance(review.get("action") or {}, dict)
                    or (
                        review.get("action")
                        and review["action"].get("decision") not in {"ask", "answer", "escalate"}
                    )
                ):
                    raise ValueError
            if (
                "review" in view
                and view["review"] is not None
                and not cls._review_receipt(view["review"], case_id)
            ):
                raise ValueError
            if "actions" in view:
                if not isinstance(view["actions"], list):
                    raise ValueError
                for action in view["actions"]:
                    if (
                        not isinstance(action, dict)
                        or action.keys() != {"proposal_id", "action_id", "reviewer_id", "body"}
                        or not all(isinstance(item, str) for item in action.values())
                    ):
                        raise ValueError
            outcome = view.get("run_outcome")
            if outcome is not None:
                if (
                    not isinstance(outcome, dict)
                    or outcome.keys() != {"status", "error_code", "result"}
                    or outcome["status"] not in OUTCOME_STATUSES
                    or (
                        outcome["error_code"] is not None
                        and not isinstance(outcome["error_code"], str)
                    )
                ):
                    raise ValueError
                if outcome["error_code"] is not None and outcome["error_code"] not in OUTCOME_CODES:
                    outcome["error_code"] = "RunOutcomeUnavailable"
                if outcome["result"] is not None:
                    result = RunResult.model_validate(outcome["result"])
                    if result.error_code is not None and result.error_code not in OUTCOME_CODES:
                        result = result.model_copy(update={"error_code": "RunOutcomeUnavailable"})
                    outcome["result"] = result.model_dump(mode="json")
            return view
        except (KeyError, TypeError, ValueError):
            raise cls._invalid_response() from None

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self._http.request(method, path, **kwargs)
        except (httpx.HTTPError, ValueError, UnicodeError):
            raise BackendError(
                "Cannot reach the backend. Delivery was not confirmed.", retryable=True
            ) from None
        if response.is_success:
            try:
                body = response.json()
            except ValueError:
                raise self._invalid_response() from None
            if not isinstance(body, dict):
                raise self._invalid_response()
            return body
        detail = None
        try:
            body = response.json()
            detail = body.get("detail") if isinstance(body, dict) else None
        except ValueError:
            pass
        if not isinstance(detail, str) or detail not in ERROR_TEXT:
            raise BackendError(
                f"The backend rejected the request (HTTP {response.status_code}).",
                retryable=response.status_code >= 500,
            )
        raise BackendError(ERROR_TEXT[detail], code=detail, retryable=response.status_code >= 500)


def make_client() -> BackendClient:
    base_url = os.environ.get("AGENT_API_URL", DEFAULT_BASE_URL)
    return BackendClient(
        httpx.Client(base_url=base_url, timeout=10.0),
        reviewer_token=os.environ.get("AGENT_REVIEWER_TOKEN"),
    )
