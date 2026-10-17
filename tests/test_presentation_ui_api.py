"""Presentation hooks only: real HTTP/SQLite, scripted provider, zero paid calls.

These controls test authorization, fixed identities, and Streamlit delivery;
they do not claim live-model quality or an operating-system/browser restart.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import streamlit as st
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from agent_app import api, ui_client
from agent_app.persistent_api import create_app
from agent_app.tracker.sqlite_tracker import SQLiteCaseTracker

TOKEN = "synthetic-presentation-test-token"
REVIEWERS = {"presentation-maintainer": TOKEN}
POOL = ("presentation-a", "presentation-b")
PAGE = str(Path(__file__).resolve().parent.parent / "app_pages" / "assistant.py")


@pytest.fixture(autouse=True)
def clean_ui(monkeypatch):
    st.cache_resource.clear()
    monkeypatch.delenv("AGENT_PRESENTATION_CASES", raising=False)
    monkeypatch.delenv("AGENT_API_TIMEOUT_SECONDS", raising=False)
    yield
    st.cache_resource.clear()


@pytest.fixture
def scoped(tmp_path):
    path = tmp_path / "presentation.sqlite3"
    state = SimpleNamespace(ports=[], slots=[], requests=[])

    def resolve(case_id, revision):
        state.slots.append((case_id, revision))
        if case_id not in POOL or revision not in range(1, 8):
            raise ValueError("Private allocation detail must not escape.")
        return f"presentation-run-{case_id}-{revision}"

    def ports(_case, _scenario):
        # A mocked provider deliberately ignores the UI scenario. Its actual
        # user-message input and bound run context are inspected below.
        known = any(
            fact.name == "streamlit_version" and fact.status == "active" for fact in _case.facts
        )
        adapters = api._adapters("answer" if known else "ask_version")
        state.ports.append(adapters)
        return adapters

    def app():
        tracker = SQLiteCaseTracker(path, reviewer_tokens=REVIEWERS)
        return create_app(
            tracker,
            reviewer_tokens=REVIEWERS,
            case_adapters=ports,
            reasoning_label="metis_grounded_live",
            run_id_resolver=resolve,
            require_message_auth=True,
        )

    state.app = app
    state.backend = TestClient(app())

    def handler(request):
        state.requests.append(request)
        response = state.backend.request(
            request.method, request.url.path, content=request.content, headers=request.headers
        )
        return httpx.Response(response.status_code, content=response.content)

    state.client = ui_client.BackendClient(
        httpx.Client(base_url="http://backend", transport=httpx.MockTransport(handler)),
        reviewer_token=TOKEN,
    )
    yield state
    state.client._http.close()
    state.backend.close()


def event(*, revision=0, text="A new free-text question about a widget."):
    return ui_client.new_event(text, expected_revision=revision, scenario="answer")


@pytest.mark.parametrize("authorization", [None, "Bearer wrong", "Basic invalid"])
def test_message_auth_precedes_resolver_ingress_and_provider(scoped, authorization):
    headers = {} if authorization is None else {"Authorization": authorization}
    response = scoped.backend.post(f"/cases/{POOL[0]}/messages", json=event(), headers=headers)
    assert response.status_code == 401
    assert response.json() == {"detail": "ReviewerUnauthorized"}
    assert scoped.slots == scoped.ports == []
    assert scoped.backend.get(f"/cases/{POOL[0]}").json()["case_revision"] == 0


@pytest.mark.parametrize("case_id,revision", [("unfunded", 0), (POOL[0], 7)])
def test_out_of_pool_fails_closed_without_ingress_or_private_error(scoped, case_id, revision):
    response = scoped.backend.post(
        f"/cases/{case_id}/messages",
        json=event(revision=revision),
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert response.status_code == 403
    assert response.json() == {"detail": "PresentationSlotUnavailable"}
    assert scoped.ports == []
    assert scoped.backend.get(f"/cases/{case_id}").json()["case_revision"] == 0


@pytest.mark.parametrize("invalid", [None, True, "", " invalid ", "x" * 201, "x?y"])
def test_invalid_resolved_identity_is_rejected_before_ingress(tmp_path, invalid):
    tracker = SQLiteCaseTracker(tmp_path / "invalid.sqlite3", reviewer_tokens=REVIEWERS)
    backend = TestClient(
        create_app(tracker, reviewer_tokens=REVIEWERS, run_id_resolver=lambda *_: invalid)
    )
    response = backend.post(f"/cases/{POOL[0]}/messages", json=event())
    assert response.status_code == 403
    assert response.json() == {"detail": "PresentationSlotUnavailable"}
    assert backend.get(f"/cases/{POOL[0]}").json()["case_revision"] == 0


def test_exact_replay_uses_fixed_run_and_does_not_allocate_again(scoped):
    assert scoped.client.discover_capabilities().message_auth
    payload = event(text="Why does my button icon change after a rerun?")
    first = scoped.client.send_event(POOL[0], payload)
    assert first["pending"]["decision"] == "ask"
    assert len(scoped.ports) == 1
    reasoner = scoped.ports[0].reasoner
    assert payload["message"] in reasoner.inputs[0][1]
    assert reasoner.contexts[0].run_id == f"presentation-run-{POOL[0]}-1"
    assert reasoner.contexts[0].attempt_index == 1
    assert not first["intake"]["replayed"]
    scoped.backend.close()
    scoped.backend = TestClient(scoped.app())
    replay = scoped.client.send_event(POOL[0], payload)
    assert replay["intake"]["replayed"]
    assert len(scoped.ports) == 1
    assert scoped.slots == [(POOL[0], 1), (POOL[0], 1)]
    posts = [request for request in scoped.requests if request.method == "POST"]
    assert posts[0].content == posts[1].content
    assert all(request.headers["authorization"] == f"Bearer {TOKEN}" for request in posts)
    assert all(TOKEN.encode() not in request.content for request in posts)
    assert all(
        "authorization" not in request.headers
        for request in scoped.requests
        if request.method == "GET"
    )


def test_client_does_not_forward_message_token_to_changed_backend(scoped, tmp_path):
    scoped.client.discover_capabilities()
    scoped.backend.close()
    scoped.backend = TestClient(
        create_app(
            SQLiteCaseTracker(tmp_path / "different.sqlite3", reviewer_tokens=REVIEWERS),
            reviewer_tokens=REVIEWERS,
        )
    )
    with pytest.raises(ui_client.BackendError) as caught:
        scoped.client.send_event(POOL[0], event())
    assert caught.value.code == "BackendCapabilityMismatch"
    assert not caught.value.retryable
    assert all(request.method == "GET" for request in scoped.requests)


def test_scoped_correction_stale_review_and_review_retry_keep_one_action(scoped):
    scoped.client.discover_capabilities()
    first = scoped.client.send_event(POOL[0], event())
    old_review = scoped.client.prepare_review(POOL[0], first["pending"], "approve")
    corrected = scoped.client.send_event(
        POOL[0],
        ui_client.new_event(
            "The deployed Streamlit version is 1.50.0.",
            expected_revision=1,
            scenario="answer",
            reported_facts=[{"name": "streamlit_version", "value": "1.50.0"}],
        ),
    )
    assert corrected["case_revision"] == 2
    assert scoped.ports[-1].reasoner.contexts[0].run_id == f"presentation-run-{POOL[0]}-2"
    corrected_again = scoped.client.send_event(
        POOL[0],
        ui_client.new_event(
            "Correction: it is actually Streamlit 1.49.0.",
            expected_revision=2,
            scenario="answer",
            reported_facts=[{"name": "streamlit_version", "value": "1.49.0"}],
        ),
    )
    assert corrected_again["case_revision"] == 3
    facts = corrected_again["facts"]
    assert [(fact["value"], fact["status"]) for fact in facts] == [
        ("1.50.0", "superseded"),
        ("1.49.0", "active"),
    ]
    assert scoped.ports[-1].reasoner.contexts[0].run_id == f"presentation-run-{POOL[0]}-3"
    with pytest.raises(ui_client.BackendError) as caught:
        scoped.client.send_review(old_review)
    assert caught.value.code == "StaleRevision"
    current_review = scoped.client.prepare_review(POOL[0], corrected_again["pending"], "approve")
    approved = scoped.client.send_review(current_review)
    assert len(approved["actions"]) == 1
    scoped.backend.close()
    scoped.backend = TestClient(scoped.app())
    replay = scoped.client.send_review(current_review)
    assert replay["review"]["replayed"]
    assert replay["actions"] == approved["actions"]
    assert len(scoped.ports) == 3


def test_missing_client_token_rejects_before_post(scoped):
    scoped.client._reviewer_token = None
    scoped.client.discover_capabilities()
    with pytest.raises(ui_client.BackendError) as caught:
        scoped.client.send_event(POOL[0], event())
    assert caught.value.code == "ReviewerUnauthorized"
    assert all(request.method == "GET" for request in scoped.requests)
    assert scoped.slots == scoped.ports == []


def test_default_api_health_and_unauthed_offline_ingress_are_unchanged(tmp_path):
    tracker = SQLiteCaseTracker(tmp_path / "ordinary.sqlite3", reviewer_tokens=REVIEWERS)
    backend = TestClient(create_app(tracker, reviewer_tokens=REVIEWERS))
    assert backend.get("/health").json() == {
        "status": "ok",
        "mode": "synthetic_offline_sqlite",
        "tracker_backend": "sqlite_case_tracker",
        "capabilities": {
            "stable_event_ids": True,
            "durable_reviews": True,
            "reviewer_auth": "bearer",
        },
        "retrieval_label": "scripted",
        "reasoning_label": "scripted",
        "quality_claim": False,
    }
    assert backend.post(f"/cases/{POOL[0]}/messages", json=event()).status_code == 200


@pytest.mark.parametrize(
    "value", ["[]", "null", '"x"', '["a", "a"]', '["a/b"]', "[1]", '["-a"]', "invalid"]
)
def test_invalid_public_pool_is_rejected(value, monkeypatch):
    monkeypatch.setenv("AGENT_PRESENTATION_CASES", value)
    with pytest.raises(ui_client.BackendError) as caught:
        ui_client.presentation_cases()
    assert caught.value.code == "PresentationConfigurationInvalid"
    assert str(caught.value) == ui_client.ERROR_TEXT["PresentationConfigurationInvalid"]


def test_valid_pool_and_default_timeout(monkeypatch):
    assert ui_client.presentation_cases() is None
    monkeypatch.setenv("AGENT_PRESENTATION_CASES", json.dumps(POOL))
    assert ui_client.presentation_cases() == POOL
    client = ui_client.make_client()
    assert client._http.timeout.read == 10.0
    client._http.close()


@pytest.mark.parametrize("value", ["nan", "inf", "0", "91", "secret-invalid-value"])
def test_invalid_timeout_fails_sanitized(value, monkeypatch):
    monkeypatch.setenv("AGENT_API_TIMEOUT_SECONDS", value)
    with pytest.raises(ui_client.BackendError) as caught:
        ui_client.make_client()
    assert caught.value.code == "PresentationConfigurationInvalid"
    assert value not in str(caught.value)


def test_live_timeout_is_explicit_and_bounded(monkeypatch):
    monkeypatch.setenv("AGENT_API_TIMEOUT_SECONDS", "90")
    client = ui_client.make_client()
    assert client._http.timeout.read == 90.0
    client._http.close()


def button(at, label):
    return next(item for item in at.button if item.label == label)


def test_streamlit_pool_free_text_no_script_selector_and_session_reopen(scoped, monkeypatch):
    monkeypatch.setenv("AGENT_PRESENTATION_CASES", json.dumps(POOL))
    monkeypatch.setattr(ui_client, "make_client", lambda: scoped.client)
    first = AppTest.from_file(PAGE, default_timeout=15).run()
    assert not first.exception
    assert first.session_state.case_id == POOL[0]
    assert "scenario" not in [item.key for item in first.sidebar.selectbox]
    first.chat_input[0].set_value("A fresh judge question about st.button.").run()
    assert not first.exception
    assert len(scoped.ports) == 1
    assert "A fresh judge question about st.button." in scoped.ports[0].reasoner.inputs[0][1]
    assert first.button(key="approve")
    button(first, "New case").click().run()
    assert first.session_state.case_id == POOL[1]
    assert button(first, "New case").disabled
    assert len(scoped.ports) == 1
    st.cache_resource.clear()
    reopened = AppTest.from_file(PAGE, default_timeout=15).run()
    assert not reopened.exception
    assert reopened.session_state.case_id == POOL[0]
    assert reopened.button(key="approve")
    assert len(scoped.ports) == 1


def test_pool_prevents_opening_arbitrary_saved_ids(scoped, monkeypatch):
    monkeypatch.setenv("AGENT_PRESENTATION_CASES", json.dumps(POOL))
    monkeypatch.setattr(ui_client, "make_client", lambda: scoped.client)
    at = AppTest.from_file(PAGE, default_timeout=15).run()
    scoped.requests.clear()
    at.text_input(key="saved_case_id").set_value("unfunded-case")
    button(at, "Open saved case").click().run()
    assert not at.exception
    assert at.session_state.case_id == POOL[0]
    assert not any("unfunded-case" in request.url.path for request in scoped.requests)
    assert scoped.ports == []


def test_live_ui_without_credential_disables_paid_inputs(scoped, monkeypatch):
    monkeypatch.setenv("AGENT_PRESENTATION_CASES", json.dumps(POOL))
    scoped.client._reviewer_token = None
    monkeypatch.setattr(ui_client, "make_client", lambda: scoped.client)
    at = AppTest.from_file(PAGE, default_timeout=15).run()
    assert not at.exception
    assert at.chat_input[0].disabled
    assert button(at, "Send update").disabled
    assert scoped.slots == scoped.ports == []
