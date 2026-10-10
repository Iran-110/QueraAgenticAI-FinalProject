"""Small HTTP client the Streamlit UI uses to talk to the FastAPI backend."""

import os
from typing import Any
from uuid import uuid4

import httpx

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
}


class BackendError(Exception):
    """A user-presentable failure; never carries request bodies or credentials.

    ``retryable`` is true only when the request may not have reached the server,
    so resending the identical event is safe and returns the original receipt.
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
    def __init__(self, http: httpx.Client) -> None:
        self._http = http

    def get_case(self, case_id: str) -> dict[str, Any]:
        return self._request("GET", f"/cases/{case_id}")

    def send_event(self, case_id: str, event: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", f"/cases/{case_id}/messages", json=event)

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
        return self._request("POST", f"/cases/{case_id}/decision", json=payload)

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self._http.request(method, path, **kwargs)
        except httpx.HTTPError:
            raise BackendError(
                f"Cannot reach the backend at {self._http.base_url}.", retryable=True
            ) from None
        if response.is_success:
            return response.json()
        detail = None
        try:
            detail = response.json().get("detail")
        except ValueError:
            pass
        if not isinstance(detail, str):
            raise BackendError(
                f"The backend rejected the request (HTTP {response.status_code}).",
                retryable=response.status_code >= 500,
            )
        raise BackendError(ERROR_TEXT.get(detail, detail), code=detail)


def make_client() -> BackendClient:
    base_url = os.environ.get("AGENT_API_URL", DEFAULT_BASE_URL)
    return BackendClient(httpx.Client(base_url=base_url, timeout=10.0))
