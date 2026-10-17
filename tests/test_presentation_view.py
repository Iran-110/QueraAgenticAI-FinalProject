"""GET-only presentation projection; synthetic SQLite/provider and no paid data."""

from copy import deepcopy
from pathlib import Path

import httpx
import pytest
import streamlit as st
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from agent_app import presentation_view as module
from agent_app.persistent_api import create_app
from agent_app.tracker.sqlite_tracker import SQLiteCaseTracker
from agent_app.ui_client import BackendError

PAGE = str(Path(__file__).resolve().parents[1] / "presentation_view.py")
CASES = ("viewer-case-a", "viewer-case-b")


@pytest.fixture(autouse=True)
def clear_cache():
    st.cache_resource.clear()
    yield
    st.cache_resource.clear()


@pytest.fixture
def backend(tmp_path):
    tracker = SQLiteCaseTracker(
        tmp_path / "viewer.sqlite3", reviewer_tokens={"viewer-test": "synthetic-viewer-token"}
    )
    client = TestClient(
        create_app(tracker, reviewer_tokens={"viewer-test": "synthetic-viewer-token"})
    )
    payload = {
        "message": "A free-text problem. <script>untrusted</script> ![remote](https://example.invalid/image)",
        "turn_id": "viewer-first",
        "expected_revision": 0,
        "scenario": "answer",
        "reported_facts": [{"name": "streamlit_version", "value": "1.49.0"}],
    }
    response = client.post(f"/cases/{CASES[0]}/messages", json=payload)
    assert response.status_code == 200
    return client, response.json(), payload


def observed_viewer(backend, *, change=None, origin=None):
    backend, view, _ = backend
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path == "/health":
            body = backend.get("/health").json()
            if origin is not None:
                body["display_origin"] = origin
        else:
            body = deepcopy(view)
            if change:
                change(body)
        return httpx.Response(200, json=body)

    viewer = module.PresentationViewer(
        "http://127.0.0.1:8009", CASES, transport=httpx.MockTransport(handler)
    )
    return viewer, requests


@pytest.mark.parametrize(
    "cases",
    [
        None,
        (),
        [],
        ["a", "a"],
        ["a/b"],
        ["../x"],
        [1],
        ["-a"],
        ["x" * 201],
        [f"a{x}" for x in range(8)],
    ],
)
def test_invalid_pool_rejected_before_transport(cases):
    with pytest.raises(ValueError, match="PresentationViewRejected"):
        module.PresentationViewer("http://127.0.0.1:8009", cases)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.org",
        "http://user:pass@127.0.0.1:8001",
        "http://127.0.0.1",
        "http://127.0.0.1:8001/x",
        "http://127.0.0.1:8001?x=y",
        "file:///tmp/file",
        "http://127.0.0.1:99999",
    ],
)
def test_remote_or_credentialed_url_rejected(url):
    with pytest.raises(ValueError, match="PresentationViewRejected"):
        module.PresentationViewer(url, CASES)


def test_exact_gets_without_credentials_or_environment_proxy(backend, monkeypatch):
    monkeypatch.setenv("AGENT_REVIEWER_TOKEN", "must-never-be-read-or-forwarded")
    monkeypatch.setenv("METIS_API_KEY", "must-never-be-read-or-forwarded")
    monkeypatch.setenv("HTTP_PROXY", "http://must-not-be-used.invalid:99")
    viewer, requests = observed_viewer(backend)
    snapshot = viewer.load(CASES[0])
    assert [(request.method, request.url.path) for request in requests] == [
        ("GET", "/health"),
        ("GET", f"/cases/{CASES[0]}"),
    ]
    assert all(
        "authorization" not in request.headers and not request.content for request in requests
    )
    assert snapshot.active_user_facts == ({"name": "streamlit_version", "value": "1.49.0"},)
    assert snapshot.origin == "api"
    assert snapshot.view == backend[1]
    changed = snapshot.view
    changed["pending"]["user_draft"] = "forged"
    assert snapshot.view == backend[1]


@pytest.mark.parametrize("case_id", ["outside", "../outside", "a/b", None, True])
def test_non_pool_case_cannot_trigger_any_http(backend, case_id):
    viewer, requests = observed_viewer(backend)
    with pytest.raises(ValueError, match="PresentationViewRejected"):
        viewer.load(case_id)
    assert requests == []


@pytest.mark.parametrize(
    "method,path,kwargs",
    [
        ("POST", "/health", {}),
        ("GET", "/outside", {}),
        ("GET", "/health", {"headers": {"Authorization": "forbidden"}}),
        ("DELETE", f"/cases/{CASES[0]}", {}),
    ],
)
def test_transport_boundary_blocks_writes_extra_paths_and_headers(backend, method, path, kwargs):
    viewer, requests = observed_viewer(backend)
    with pytest.raises(ValueError, match="PresentationViewRejected"):
        viewer._read_only.request(method, path, **kwargs)
    assert requests == []


@pytest.mark.parametrize("mutation", ["cross_case", "draft", "excerpt", "handoff"])
def test_unbound_or_tampered_case_is_never_projected(backend, mutation):
    def change(view):
        if mutation == "cross_case":
            view["case_id"] = CASES[1]
        elif mutation == "draft":
            view["pending"]["user_draft"] += " injected advice"
        elif mutation == "excerpt":
            view["pending"]["review_handoff"]["evidence"]["hits"][0]["excerpt"] += " changed"
        else:
            view["pending"]["review_handoff"]["handoff_sha256"] = "0" * 64

    viewer, _ = observed_viewer(backend, change=change)
    with pytest.raises(BackendError) as caught:
        viewer.load(CASES[0])
    assert caught.value.code == "BackendResponseInvalid"


def test_recorded_origin_is_explicit_and_unknown_origin_fails_closed(backend):
    viewer, _ = observed_viewer(backend, origin="recorded_rehearsal")
    assert viewer.load(CASES[0]).origin == "recorded_rehearsal"
    viewer, _ = observed_viewer(backend, origin="pretend_live_model_success")
    with pytest.raises(BackendError):
        viewer.load(CASES[0])


def test_streamlit_plain_untrusted_text_full_draft_and_no_paid_controls(backend, monkeypatch):
    instance, requests = observed_viewer(backend)
    monkeypatch.setenv("AGENT_PRESENTATION_CASES", '["viewer-case-a", "viewer-case-b"]')
    monkeypatch.setattr(module, "PresentationViewer", lambda *args, **kwargs: instance)
    at = AppTest.from_file(PAGE, default_timeout=15).run()
    assert not at.exception
    assert not at.chat_input and not at.text_input and not at.get("form")
    assert not any(
        button.label in {"Approve", "Send", "Reject", "Send update"} for button in at.button
    )
    assert backend[2]["message"] in [item.value for item in at.text]
    assert backend[1]["pending"]["user_draft"] in [item.value for item in at.text]
    assert backend[1]["pending"]["maintainer_summary"] in [item.value for item in at.text]
    assert not any("untrusted" in item.value for item in at.markdown)
    assert not at.get("imgs")
    assert all(
        request.method == "GET" and "authorization" not in request.headers for request in requests
    )


def test_recorded_screen_has_visible_origin_and_manual_refresh_only(backend, monkeypatch):
    instance, requests = observed_viewer(backend, origin="recorded_rehearsal")
    monkeypatch.setenv("AGENT_PRESENTATION_CASES", '["viewer-case-a", "viewer-case-b"]')
    monkeypatch.setattr(module, "PresentationViewer", lambda *args, **kwargs: instance)
    at = AppTest.from_file(PAGE, default_timeout=15).run()
    assert not at.exception
    assert any("نمایش ضبط‌شده" in info.value for info in at.info)
    assert len(requests) == 2
    next(button for button in at.button if button.label == "به‌روزرسانی نما").click().run()
    assert len(requests) == 4


def test_approved_artifact_is_history_not_a_new_pending_reply(backend, monkeypatch):
    http, view, payload = backend
    proposal = view["pending"]
    approved = http.post(
        f"/cases/{CASES[0]}/decision",
        json={
            "decision": "approve",
            "proposal_id": proposal["proposal_id"],
            "case_revision": proposal["case_revision"],
            "review_id": "viewer-approved-reference",
            "expected_handoff_sha256": proposal["review_handoff"]["handoff_sha256"],
        },
        headers={"Authorization": "Bearer synthetic-viewer-token"},
    )
    assert approved.status_code == 200
    assert approved.json()["pending"] is None
    instance, requests = observed_viewer((http, approved.json(), payload))
    monkeypatch.setenv("AGENT_PRESENTATION_CASES", '["viewer-case-a", "viewer-case-b"]')
    monkeypatch.setattr(module, "PresentationViewer", lambda *args, **kwargs: instance)
    at = AppTest.from_file(PAGE, default_timeout=15).run()
    assert not at.exception
    assert any("آخرین پیام ثبت‌شده" in heading.value for heading in at.subheader)
    assert not any("پیشنهاد فعلی ایجنت" in heading.value for heading in at.subheader)
    assert proposal["user_draft"] in [text.value for text in at.text]
    assert all(request.method == "GET" for request in requests)


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "javascript:alert(1)",
        "file:///private/file",
        "https://user:secret@example.com/path",
        "https://example.com/\x00",
        "https://example.com/\x7f",
        "https://example.com/\n",
        "https://example.com/a b",
        "https://example.com:invalid/path",
    ],
)
def test_invalid_source_link_remains_non_clickable(value):
    assert module.source_link(value) is None


def test_plain_known_http_source_link_is_preserved():
    url = "https://github.com/streamlit/docs/blob/commit/docs/page.md#example"
    assert module.source_link(url) == url


def test_session_cache_release_closes_get_client(backend, monkeypatch):
    instance, _ = observed_viewer(backend)
    monkeypatch.setenv("AGENT_PRESENTATION_CASES", '["viewer-case-a", "viewer-case-b"]')
    monkeypatch.setattr(module, "PresentationViewer", lambda *args, **kwargs: instance)
    at = AppTest.from_file(PAGE, default_timeout=15).run()
    assert not at.exception and not instance._http.is_closed
    st.cache_resource.clear()
    assert instance._http.is_closed
