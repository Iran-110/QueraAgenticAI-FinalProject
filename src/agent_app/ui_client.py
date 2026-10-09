"""Small HTTP client the Streamlit UI uses to talk to the FastAPI backend."""

import os
from typing import Any

import httpx

DEFAULT_BASE_URL = "http://127.0.0.1:8000"


class BackendError(Exception):
    """A user-presentable failure; never carries request bodies or credentials."""


class BackendClient:
    def __init__(self, http: httpx.Client) -> None:
        self._http = http

    def get_case(self, case_id: str) -> dict[str, Any]:
        return self._request("GET", f"/cases/{case_id}")

    def send_message(self, case_id: str, message: str, scenario: str) -> dict[str, Any]:
        return self._request(
            "POST", f"/cases/{case_id}/messages", json={"message": message, "scenario": scenario}
        )

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
            raise BackendError(f"Cannot reach the backend at {self._http.base_url}.") from None
        if response.is_success:
            return response.json()
        detail = None
        try:
            detail = response.json().get("detail")
        except ValueError:
            pass
        if not isinstance(detail, str):
            detail = f"The backend rejected the request (HTTP {response.status_code})."
        raise BackendError(detail)


def make_client() -> BackendClient:
    base_url = os.environ.get("AGENT_API_URL", DEFAULT_BASE_URL)
    return BackendClient(httpx.Client(base_url=base_url, timeout=10.0))
