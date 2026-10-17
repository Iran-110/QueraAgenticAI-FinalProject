"""Read-only projection for a separate optional presentation screen.

This module cannot submit messages or reviews. Existing API response validation
binds every displayed draft/reference to its complete original handoff. Compact
labels are UI projections, never model answers or evidence-quality judgments.
"""

import re
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

import httpx

from agent_app.ui_client import BackendCapabilities, BackendClient, BackendError

_CASE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}\Z")
_ERROR = "PresentationViewRejected"


def validate_pool(cases: object) -> tuple[str, ...]:
    if (
        not isinstance(cases, (tuple, list))
        or not 1 <= len(cases) <= 7
        or any(type(case) is not str or _CASE.fullmatch(case) is None for case in cases)
        or len(set(cases)) != len(cases)
    ):
        raise ValueError(_ERROR)
    return tuple(cases)


def validate_local_url(value: str) -> str:
    try:
        url = urlsplit(value)
        if (
            url.scheme != "http"
            or url.hostname not in {"127.0.0.1", "localhost"}
            or url.username is not None
            or url.password is not None
            or url.path not in {"", "/"}
            or url.query
            or url.fragment
            or url.port is None
        ):
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError(_ERROR) from None
    return value.rstrip("/")


def source_link(value: object) -> str | None:
    """A displayed current source may become a link only with a plain web URL."""
    try:
        if (
            type(value) is not str
            or not 1 <= len(value) <= 2000
            or any(ord(char) <= 32 or ord(char) == 127 for char in value)
        ):
            raise ValueError
        url = urlsplit(value)
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or url.username is not None
            or url.password is not None
        ):
            raise ValueError
        _ = url.port
        return value
    except (TypeError, ValueError):
        return None


class _GetOnlyHTTP:
    """A second boundary: even accidental BackendClient writes cannot escape."""

    def __init__(self, client: httpx.Client, cases: tuple[str, ...]):
        self._http = client
        self._paths = frozenset(("/health", *(f"/cases/{case}" for case in cases)))
        self.origin = "api"

    def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        if method != "GET" or path not in self._paths or kwargs:
            raise ValueError(_ERROR)
        response = self._http.request("GET", path)
        if path == "/health" and response.is_success:
            try:
                origin = response.json().get("display_origin", "api")
                if origin not in {"api", "recorded_rehearsal"}:
                    raise ValueError
                self.origin = origin
            except (AttributeError, TypeError, ValueError):
                raise ValueError(_ERROR) from None
        return response


@dataclass(frozen=True)
class CaseSnapshot:
    capabilities: BackendCapabilities
    _data: dict[str, Any] = field(repr=False)
    origin: str = "api"

    @property
    def view(self) -> dict[str, Any]:
        return deepcopy(self._data)

    @property
    def active_user_facts(self) -> tuple[dict[str, str], ...]:
        return tuple(
            {"name": fact["name"], "value": fact["value"]}
            for fact in self._data["facts"]
            if fact["status"] == "active" and fact["provenance_kind"] == "user"
        )


class PresentationViewer:
    """Only health/case GETs, without credential lookup, header or paid method."""

    def __init__(
        self,
        base_url: str,
        cases: object,
        *,
        transport: httpx.BaseTransport | None = None,
    ):
        self.cases = validate_pool(cases)
        self._http = httpx.Client(
            base_url=validate_local_url(base_url),
            transport=transport,
            timeout=10,
            trust_env=False,
            follow_redirects=False,
        )
        self._read_only = _GetOnlyHTTP(self._http, self.cases)
        self._client = BackendClient(self._read_only)

    def load(self, case_id: str) -> CaseSnapshot:
        if type(case_id) is not str or case_id not in self.cases:
            raise ValueError(_ERROR)
        capabilities = self._client.discover_capabilities()
        if not capabilities.durable_reviews:
            raise BackendError("This presentation view requires a durable local backend.")
        view = self._client.get_case(case_id)
        return CaseSnapshot(capabilities, deepcopy(view), self._read_only.origin)

    def close(self):
        self._http.close()
