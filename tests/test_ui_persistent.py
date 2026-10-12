"""Streamlit → thin HTTP client → actual SQLite, with scripted offline ports.

These tests exercise browser reruns and application recreation, not process
restart or model quality. The separate HTTP pilot covers interpreter restart.
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
from agent_app.contracts import UserTurn
from agent_app.persistent_api import create_app
from agent_app.tracker.sqlite_tracker import SQLiteCaseTracker

PAGE = str(Path(__file__).resolve().parent.parent / "app_pages" / "assistant.py")
TOKEN = "synthetic-streamlit-maintainer-token"
REVIEWERS = {"ui-fixture-maintainer": TOKEN}


@pytest.fixture(autouse=True)
def fresh_cache():
    st.cache_resource.clear()
    yield
    st.cache_resource.clear()


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    path = tmp_path / "ui.sqlite3"
    tracker = SQLiteCaseTracker(path, reviewer_tokens=REVIEWERS)
    backend = TestClient(create_app(tracker, reviewer_tokens=REVIEWERS), base_url="http://backend")
    state = SimpleNamespace(
        path=path,
        tracker=tracker,
        backend=backend,
        loss=None,
        requests=[],
        message_requests=[],
        client_creations=0,
        configured=True,
        health=None,
    )

    def handler(request):
        if request.url.path == "/health" and state.health is not None:
            return httpx.Response(200, json=state.health)
        response = state.backend.request(
            request.method, request.url.path, content=request.content, headers=request.headers
        )
        if request.method == "POST" and request.url.path.endswith("/messages"):
            state.message_requests.append((request.url.path, json.loads(request.content)))
        if request.method == "POST" and request.url.path.endswith("/decision"):
            state.requests.append(
                (request.url.path, json.loads(request.content), dict(request.headers))
            )
            if state.loss:
                # The real tracker committed first. Only its HTTP acknowledgment is lost.
                loss, state.loss = state.loss, None
                assert response.status_code == 200
                if loss == "timeout":
                    raise httpx.ReadTimeout("synthetic-lost-ack")
                if loss == "503":
                    return httpx.Response(503, json={"detail": "TrackerUnavailable"})
                if loss == "invalid200":
                    return httpx.Response(200, json={"private-corrupt-body": "not a view"})
                if loss == "altered_proposal200":
                    body = response.json()
                    body["pending"]["user_draft"] = (
                        "Unreviewed content must never become approvable."
                    )
                    return httpx.Response(200, json=body)
                raise AssertionError("Unknown fixture loss")
        return httpx.Response(
            response.status_code, content=response.content, headers=response.headers
        )

    def make_client():
        state.client_creations += 1
        return ui_client.BackendClient(
            httpx.Client(base_url="http://backend", transport=httpx.MockTransport(handler)),
            reviewer_token=TOKEN if state.configured else None,
        )

    monkeypatch.setattr(ui_client, "make_client", make_client)
    yield state
    state.backend.close()


def current(runtime, case_id):
    response = runtime.backend.get(f"/cases/{case_id}")
    assert response.status_code == 200
    return response.json()


def send_message(at, text="My widget loses its value."):
    at.chat_input[0].set_value(text).run()
    assert not at.exception


def button(at, label):
    return next(item for item in at.button if item.label == label)


def review_click(at, decision):
    if decision == "edit":
        at.button(key="edit").click().run()
        at.text_area(key="edited_draft").set_value("Which Streamlit version is deployed?")
        button(at, "Save as new proposal").click().run()
    else:
        at.button(key=decision).click().run()
    assert not at.exception


def send_correction(at, version="1.49.1"):
    generation = at.session_state.form_gen
    at.text_area(key=f"update_message_{generation}").set_value(
        "Correction: that version was wrong."
    )
    at.text_input(key=f"fact_name_0_{generation}").set_value("streamlit_version")
    at.text_input(key=f"fact_value_0_{generation}").set_value(version)
    button(at, "Send update").click().run()
    assert not at.exception


@pytest.mark.parametrize("decision", ["approve", "reject", "edit"])
@pytest.mark.parametrize("loss", ["timeout", "503", "invalid200"])
def test_review_lost_ack_retries_exact_payload_once_in_sqlite(runtime, decision, loss):
    at = AppTest.from_file(PAGE).run()
    case_id = at.session_state.case_id
    send_message(at)
    displayed = current(runtime, case_id)["pending"]
    runtime.loss = loss
    review_click(at, decision)
    operation = at.session_state.unsent_reviews[case_id]
    original_request = runtime.requests[0]
    assert operation.payload() == original_request[1]
    assert (
        original_request[1]["expected_handoff_sha256"]
        == displayed["review_handoff"]["handoff_sha256"]
    )
    assert original_request[1]["proposal_id"] == displayed["proposal_id"]
    assert original_request[2]["authorization"] == f"Bearer {TOKEN}"
    assert TOKEN not in operation.body_json
    assert TOKEN not in repr(at.session_state)
    committed = current(runtime, case_id)
    assert len(committed["decisions"]) == 1
    assert len(committed["actions"]) == (1 if decision == "approve" else 0)
    if decision == "edit":
        assert at.button(key="approve").disabled
        assert at.button(key="edit").disabled
        assert at.button(key="reject").disabled
    button(at, "Retry review").click().run()
    assert not at.exception
    assert at.session_state.unsent_reviews == {}
    assert runtime.requests[1][:2] == original_request[:2]
    assert "original review is confirmed" in at.info[0].value
    after = current(runtime, case_id)
    assert len(after["decisions"]) == 1
    assert len(after["actions"]) == (1 if decision == "approve" else 0)
    assert after["review"]["replayed"] is False  # GET preserves the original stored receipt.
    assert after["pending"] == committed["pending"]
    if decision == "edit":
        assert after["pending"]["edited"]
        assert after["pending"]["proposal_id"] != displayed["proposal_id"]


def test_uncertain_old_approval_retry_after_correction_preserves_new_proposal(runtime):
    at = AppTest.from_file(PAGE).run()
    at.sidebar.selectbox(key="scenario").set_value("answer").run()
    case_id = at.session_state.case_id
    send_message(at)
    runtime.loss = "timeout"
    review_click(at, "approve")
    original = at.session_state.unsent_reviews[case_id].payload()
    send_correction(at)
    latest = current(runtime, case_id)
    assert latest["case_revision"] == 2
    assert latest["pending"]["proposal_id"] != original["proposal_id"]
    assert at.button(key="approve").disabled
    assert at.session_state.unsent_reviews[case_id].payload() == original
    button(at, "Retry review").click().run()
    assert not at.exception
    assert runtime.requests[1][1] == original
    assert "current case" in at.info[0].value
    after = current(runtime, case_id)
    assert after["case_revision"] == 2
    assert after["pending"] == latest["pending"]
    assert len(after["actions"]) == len(after["decisions"]) == 1
    assert after["facts"][0]["value"] == "1.49.1"
    assert at.button(key="approve") and not at.button(key="approve").disabled


def test_review_retry_stays_with_case_and_survives_backend_application_recreation(runtime):
    at = AppTest.from_file(PAGE).run()
    first = at.session_state.case_id
    send_message(at)
    runtime.loss = "503"
    review_click(at, "edit")
    original = at.session_state.unsent_reviews[first].payload()
    button(at, "New case").click().run()
    second = at.session_state.case_id
    assert second != first
    assert "Retry review" not in [item.label for item in at.button]
    send_message(at, "A separate issue in case B.")
    assert not at.button(key="approve").disabled
    review_click(at, "approve")
    assert list(at.session_state.unsent_reviews) == [first]
    runtime.backend.close()
    runtime.tracker = SQLiteCaseTracker(runtime.path, reviewer_tokens=REVIEWERS)
    runtime.backend = TestClient(
        create_app(runtime.tracker, reviewer_tokens=REVIEWERS), base_url="http://backend"
    )
    at.sidebar.selectbox(key="case_id").set_value(first).run()
    assert not at.exception
    assert at.button(key="approve").disabled
    button(at, "Retry review").click().run()
    assert not at.exception
    assert runtime.requests[-1][0] == f"/cases/{first}/decision"
    assert runtime.requests[-1][1] == original
    assert at.session_state.unsent_reviews == {}
    assert len(current(runtime, first)["decisions"]) == 1
    assert len(current(runtime, first)["actions"]) == 0
    assert len(current(runtime, second)["actions"]) == 1


def test_missing_credential_disables_review_but_allows_chat_and_corrections(runtime):
    runtime.configured = False
    at = AppTest.from_file(PAGE).run()
    send_message(at)
    assert not at.exception
    for decision in ("approve", "edit", "reject"):
        assert at.button(key=decision).disabled
    assert any("authorization is not configured" in item.value for item in at.warning)
    send_correction(at)
    view = current(runtime, at.session_state.case_id)
    assert view["case_revision"] == 2
    assert view["facts"][0]["value"] == "1.49.1"
    assert runtime.requests == []
    assert at.session_state.unsent_reviews == {}


def test_unknown_health_cannot_fall_back_to_legacy_review(runtime):
    runtime.health = {"status": "ok", "mode": "synthetic_offline_sqlite"}
    at = AppTest.from_file(PAGE).run()
    assert not at.exception
    assert "does not advertise a supported" in at.error[0].value
    assert not at.chat_input and not at.button
    assert runtime.message_requests == runtime.requests == []


def test_client_resource_is_per_browser_session(runtime, monkeypatch):
    # AppTest uses one constant session ID for every instance. Give its two
    # browser harnesses distinct IDs at the cache boundary, as real sessions have.
    from streamlit.runtime.caching import cache_resource_api

    session = {"id": "synthetic-browser-a"}
    monkeypatch.setattr(cache_resource_api, "get_session_id_or_throw", lambda: session["id"])
    first = AppTest.from_file(PAGE).run()
    first.run()
    session["id"] = "synthetic-browser-b"
    second = AppTest.from_file(PAGE).run()
    assert not first.exception and not second.exception
    assert runtime.client_creations == 2


def test_local_index_health_label_does_not_claim_model_quality(runtime):
    health = runtime.backend.get("/health").json()
    runtime.health = {**health, "retrieval_label": "local_chroma_hash"}
    at = AppTest.from_file(PAGE).run()
    assert not at.exception
    captions = " ".join(item.value for item in at.sidebar.caption)
    assert "Local indexed docs" in captions
    assert "scripted ask-then-escalate" in captions and "no model quality result" in captions
    assert "no retrieval index" not in captions
    assert "scenario" not in [item.key for item in at.sidebar.selectbox]
    assert at.session_state.scenario == "ask"


def test_backend_protocol_change_keeps_original_uncertain_review_without_post(runtime):
    at = AppTest.from_file(PAGE).run()
    case_id = at.session_state.case_id
    send_message(at)
    runtime.loss = "timeout"
    review_click(at, "approve")
    original = at.session_state.unsent_reviews[case_id]
    runtime.health = {"status": "ok", "mode": "synthetic_offline"}
    button(at, "Retry review").click().run()
    assert not at.exception
    assert at.session_state.unsent_reviews[case_id] == original
    assert len(runtime.requests) == 1
    assert button(at, "Retry review").disabled
    assert "changed its review protocol" in at.error[0].value
    runtime.health = None
    at.run()
    button(at, "Retry review").click().run()
    assert not at.exception
    assert at.session_state.unsent_reviews == {}
    assert runtime.requests[0][:2] == runtime.requests[1][:2]
    assert len(current(runtime, case_id)["actions"]) == 1


def test_corrupted_valid_200_review_projection_keeps_original_edit_operation(runtime):
    at = AppTest.from_file(PAGE).run()
    case_id = at.session_state.case_id
    send_message(at)
    runtime.loss = "altered_proposal200"
    review_click(at, "edit")
    original = at.session_state.unsent_reviews[case_id]
    assert "unreadable response" in at.error[0].value
    assert "Unreviewed content" not in " ".join(item.value for item in at.markdown)
    assert at.button(key="approve").disabled
    button(at, "Retry review").click().run()
    assert not at.exception
    assert at.session_state.unsent_reviews == {}
    assert runtime.requests[1][1] == original.payload()
    assert len(current(runtime, case_id)["decisions"]) == 1
    assert (
        current(runtime, case_id)["pending"]["user_draft"] == "Which Streamlit version is deployed?"
    )


def test_unknown_health_during_review_retry_preserves_operation_until_backend_restored(runtime):
    at = AppTest.from_file(PAGE).run()
    case_id = at.session_state.case_id
    send_message(at)
    runtime.loss = "timeout"
    review_click(at, "approve")
    original = at.session_state.unsent_reviews[case_id]
    runtime.health = {"status": "ok", "mode": "unsupported"}
    button(at, "Retry review").click().run()
    assert not at.exception
    assert at.session_state.unsent_reviews[case_id] == original
    assert len(runtime.requests) == 1
    runtime.health = None
    at.run()
    # AppTest may replay the still-clicked button when restoring the page after
    # st.stop. Either delivery keeps exactly the same saved operation.
    if at.session_state.unsent_reviews:
        button(at, "Retry review").click().run()
    assert not at.exception
    assert at.session_state.unsent_reviews == {}
    assert runtime.requests[1][1] == original.payload()


def test_unfinished_run_marker_is_not_a_crash_claim_and_retry_does_not_resume(runtime, monkeypatch):
    at = AppTest.from_file(PAGE).run()
    case_id = at.session_state.case_id
    event = ui_client.new_event(
        "This update committed before a result was recorded.", expected_revision=0, scenario="ask"
    )
    runtime.tracker.apply_turn(
        UserTurn(
            case_id=case_id,
            turn_id=event["turn_id"],
            source_ref=f"user:{event['turn_id']}",
            expected_revision=0,
            message=event["message"],
        ),
        event_context={"scenario": "ask"},
    )
    at.session_state.unsent[case_id] = event

    def forbidden(_scenario):
        raise AssertionError("Replaying committed ingress must not resume the agent")

    monkeypatch.setattr(api, "_adapters", forbidden)
    at.run()
    assert not at.exception
    assert any("may still be in progress" in warning.value for warning in at.warning)
    button(at, "Retry sending").click().run()
    assert not at.exception
    assert at.session_state.unsent == {}
    assert "original message receipt is confirmed" in at.info[0].value
    view = current(runtime, case_id)
    assert view["run_outcome"]["status"] == "interrupted"
    assert view["pending"] is None and view["case_revision"] == 1
    assert view["actions"] == view["decisions"] == []
