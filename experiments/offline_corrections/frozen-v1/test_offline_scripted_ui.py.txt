"""Real no-index UI/SQLite conversations; only acknowledgment loss is simulated.

AppTest uses the actual configured application and client with outgoing sockets
blocked. The second test also recreates the backend in fresh TCP interpreters.
Neither test constructs an index, model gateway, or paid ledger.
"""

import copy
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import streamlit as st
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest
from test_persistent_tcp import server

from agent_app import ui_client
from agent_app.contracts import ProposalHandoff
from agent_app.offline_backend import configured_app
from agent_app.orchestration.handoff import validate_handoff
from agent_app.orchestration.intake import STREAMLIT_VERSION_QUESTION
from agent_app.testing.http_pilot_runtime import offline_network
from agent_app.tracker.sqlite_tracker import SQLiteCaseTracker

PAGE = str(Path(__file__).resolve().parents[1] / "app_pages/assistant.py")
TOKEN = "synthetic-no-index-page-review-credential"
WIDGET_QUESTION = "Can you share the widget's key and code?"
WIDGET = "st.multiselect('Conversation', ['a'], key='conversation_multiselect')"


def _config(database):
    return {
        "AGENT_TRACKER_DB": str(database),
        "AGENT_REVIEWER_TOKEN": TOKEN,
        "AGENT_PILOT_REASONING": "scripted",
    }


def _button(at, label):
    return next(button for button in at.button if button.label == label)


def _pending(view, decision, question=None, missing=()):
    assert view["quality_claim"] is False
    assert view["retrieval_label"] == view["reasoning_label"] == "scripted"
    assert view["run_outcome"]["status"] == "proposal_staged"
    assert view["run_outcome"]["error_code"] is None
    proposal = view["pending"]
    assert proposal is not None and proposal["decision"] == decision
    assert proposal["next_question"] == question
    assert proposal["missing_info"] == list(missing)
    handoff = validate_handoff(ProposalHandoff.model_validate(proposal["review_handoff"]))
    assert handoff.case.case_revision == view["case_revision"]
    assert TOKEN not in str(view)
    return proposal


def _active_user_version(view):
    return [
        fact["value"]
        for fact in view["facts"]
        if fact["name"] == "streamlit_version"
        and fact["status"] == "active"
        and fact["provenance_kind"] == "user"
    ]


def _update(at, name, value, message):
    generation = at.session_state.form_gen
    at.text_area(key=f"update_message_{generation}").set_value(message)
    at.text_input(key=f"fact_name_0_{generation}").set_value(name)
    at.text_input(key=f"fact_value_0_{generation}").set_value(value)
    _button(at, "Send update").click().run()
    assert not at.exception


def test_no_index_app_page_follows_user_facts_and_retries_exact_review_after_recreation(
    tmp_path, monkeypatch
):
    st.cache_resource.clear()
    state = SimpleNamespace(backend=None, lose_ack=False, reviews=[])
    config = _config(tmp_path / "page.sqlite3")

    class Transport:
        def request(self, method, path, **arguments):
            response = state.backend.request(method, path, **arguments)
            if method == "POST" and path.endswith("/decision"):
                state.reviews.append(copy.deepcopy(arguments["json"]))
                if state.lose_ack and response.status_code == 200:
                    state.lose_ack = False
                    raise httpx.ReadTimeout("Synthetic committed acknowledgment lost")
            return response

    client = ui_client.BackendClient(Transport(), reviewer_token=TOKEN)
    monkeypatch.setattr(ui_client, "make_client", lambda: client)
    try:
        with offline_network():
            state.backend = TestClient(configured_app(config)).__enter__()
            at = AppTest.from_file(PAGE, default_timeout=15).run()
            assert not at.exception
            assert at.sidebar.selectbox(key="scenario").value == "ask"
            at.chat_input[0].set_value("My widget resets on rerun; version unknown.").run()
            assert not at.exception
            case_id = at.session_state.case_id

            def current():
                response = state.backend.get(f"/cases/{case_id}")
                assert response.status_code == 200
                return response.json()

            initial = current()
            _pending(
                initial,
                "ask",
                STREAMLIT_VERSION_QUESTION.question,
                ("streamlit_version",),
            )
            assert initial["actions"] == []
            at.button(key="approve").click().run()
            assert not at.exception
            assert len(current()["actions"]) == 1
            # The canonical question and approval must be loaded from SQLite,
            # rather than an in-memory question belonging to the first app.
            state.backend.__exit__(None, None, None)
            state.backend = TestClient(configured_app(config)).__enter__()
            at.text_input(key="version_reply").set_value("1.50.0")
            _button(at, "Send reply").click().run()
            assert not at.exception
            known = current()
            widget_proposal = _pending(known, "ask", WIDGET_QUESTION, ("widget_definition",))
            assert known["case_revision"] == 2
            assert _active_user_version(known) == ["1.50.0"]
            stale_operation = client.prepare_review(case_id, widget_proposal, "approve")

            _update(at, "streamlit_version", "1.49.1", "Correction: version was 1.49.1.")
            corrected = current()
            _pending(corrected, "ask", WIDGET_QUESTION, ("widget_definition",))
            assert corrected["case_revision"] == 3
            assert _active_user_version(corrected) == ["1.49.1"]
            assert any(
                fact["name"] == "streamlit_version"
                and fact["value"] == "1.50.0"
                and fact["status"] == "superseded"
                for fact in corrected["facts"]
            )
            with pytest.raises(ui_client.BackendError) as rejected:
                client.send_review(stale_operation)
            assert rejected.value.code == "StaleRevision"
            assert current()["pending"] == corrected["pending"]
            assert len(current()["actions"]) == 1

            state.lose_ack = True
            at.button(key="approve").click().run()
            assert not at.exception
            operation = at.session_state.unsent_reviews[case_id]
            payload = operation.payload()
            committed = current()
            assert len(committed["actions"]) == 2
            assert at.button(key="approve").disabled
            state.backend.__exit__(None, None, None)
            state.backend = TestClient(configured_app(config)).__enter__()
            _button(at, "Retry review").click().run()
            assert not at.exception
            assert at.session_state.unsent_reviews == {}
            assert state.reviews[-2:] == [payload, payload]
            retried = current()
            assert retried["review"] == committed["review"]
            assert len(retried["actions"]) == 2
            assert retried["case_revision"] == 3

            _update(at, "widget_definition", WIDGET, "Here is the widget's key and code.")
            completed = current()
            _pending(completed, "escalate")
            assert completed["case_revision"] == 4
            assert _active_user_version(completed) == ["1.49.1"]
            assert len(completed["actions"]) == 2
            assert any(
                fact["name"] == "widget_definition"
                and fact["value"] == WIDGET
                and fact["status"] == "active"
                and fact["provenance_kind"] == "user"
                for fact in completed["facts"]
            )
            assert TOKEN not in repr(at.session_state)
            assert len(SQLiteCaseTracker(config["AGENT_TRACKER_DB"]).comments(case_id)) == 2
    finally:
        if state.backend is not None:
            state.backend.__exit__(None, None, None)
        st.cache_resource.clear()


def test_no_index_canonical_reply_and_review_retry_survive_fresh_tcp_processes(
    tmp_path, monkeypatch
):
    # The existing subprocess helper inherits the test environment. Remove only
    # optional index selectors; its application receives our explicit test DB,
    # scripted mode, and synthetic reviewer credential.
    monkeypatch.delenv("AGENT_PILOT_INDEX", raising=False)
    monkeypatch.delenv("AGENT_PILOT_SNAPSHOT", raising=False)
    config = _config(tmp_path / "tcp.sqlite3")
    case_id = "no-index-tcp"
    with server(tmp_path / "first-ready.json", config) as http:
        client = ui_client.BackendClient(http, reviewer_token=TOKEN)
        assert client.discover_capabilities().retrieval_label == "scripted"
        initial = client.send_event(
            case_id,
            {
                "message": "My widget resets on rerun; version unknown.",
                "turn_id": "tcp-initial",
                "expected_revision": 0,
                "scenario": "ask",
            },
        )
        proposal = _pending(
            initial, "ask", STREAMLIT_VERSION_QUESTION.question, ("streamlit_version",)
        )
        version_operation = client.prepare_review(case_id, proposal, "approve")
        committed = client.send_review(version_operation)
        assert len(committed["actions"]) == 1
    with server(tmp_path / "second-ready.json", config) as http:
        client = ui_client.BackendClient(http, reviewer_token=TOKEN)
        replayed = client.send_review(version_operation)
        assert replayed["review"] == {**committed["review"], "replayed": True}
        known = client.send_event(
            case_id,
            {
                "message": "1.50.0",
                "turn_id": "tcp-version-reply",
                "expected_revision": 1,
                "reply_to_proposal_id": proposal["proposal_id"],
                "scenario": "ask",
            },
        )
        widget_proposal = _pending(known, "ask", WIDGET_QUESTION, ("widget_definition",))
        assert _active_user_version(known) == ["1.50.0"]
        stale = client.prepare_review(case_id, widget_proposal, "approve")
        corrected = client.send_event(
            case_id,
            {
                "message": "Correction: version is 1.49.1.",
                "turn_id": "tcp-correction",
                "expected_revision": 2,
                "reported_facts": [{"name": "streamlit_version", "value": "1.49.1"}],
                "scenario": "ask",
            },
        )
        fresh_proposal = _pending(corrected, "ask", WIDGET_QUESTION, ("widget_definition",))
        with pytest.raises(ui_client.BackendError) as rejected:
            client.send_review(stale)
        assert rejected.value.code == "StaleRevision"
        widget_operation = client.prepare_review(case_id, fresh_proposal, "approve")
        widget_commit = client.send_review(widget_operation)
        assert len(widget_commit["actions"]) == 2
    with server(tmp_path / "third-ready.json", config) as http:
        client = ui_client.BackendClient(http, reviewer_token=TOKEN)
        replayed = client.send_review(widget_operation)
        assert replayed["review"] == {**widget_commit["review"], "replayed": True}
        assert len(replayed["actions"]) == 2
        completed = client.send_event(
            case_id,
            {
                "message": "Here is the widget's key and code.",
                "turn_id": "tcp-widget",
                "expected_revision": 3,
                "reported_facts": [{"name": "widget_definition", "value": WIDGET}],
                "scenario": "ask",
            },
        )
        _pending(completed, "escalate")
        assert completed["case_revision"] == 4
        assert len(completed["actions"]) == 2
        assert _active_user_version(completed) == ["1.49.1"]
    assert len(SQLiteCaseTracker(config["AGENT_TRACKER_DB"]).comments(case_id)) == 2
