"""Explicit saved-case GETs across fresh UI sessions and recreated temp SQLite apps."""

import sqlite3
from copy import deepcopy

import httpx
import pytest
import streamlit as st
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest
from test_persistent_tcp import server
from test_ui_client import durable_health, empty_view
from test_ui_persistent import (
    PAGE,
    REVIEWERS,
    button,
    current,
    review_click,
    send_correction,
    send_message,
)
from test_ui_persistent import fresh_cache as fresh_cache
from test_ui_persistent import runtime as runtime

from agent_app import api, ui_client
from agent_app.persistent_api import create_app
from agent_app.tracker.sqlite_tracker import SQLiteCaseTracker


def mock_client(handler):
    return ui_client.BackendClient(
        httpx.Client(base_url="http://backend", transport=httpx.MockTransport(handler))
    )


@pytest.mark.parametrize(
    "case_id",
    [
        "",
        " ",
        ".hidden",
        "-case",
        "_case",
        "a/b",
        "a:b",
        "a?b",
        "a%b",
        "a#b",
        "a\\b",
        "a\nb",
        "//other.example/case",
        "é",
        "１",
        "a" * 201,
        None,
        True,
        1,
        b"case",
    ],
)
def test_manual_case_ids_are_rejected_before_any_http_request(case_id):
    requests = []

    def forbidden(request):
        requests.append(request)
        raise AssertionError("An invalid manual ID must not reach HTTP")

    with pytest.raises(ui_client.BackendError) as caught:
        mock_client(forbidden).get_saved_case(case_id)
    assert caught.value.code == "SavedCaseIdInvalid"
    assert not caught.value.retryable and requests == []


@pytest.mark.parametrize("case_id", ["A", "0", "saved.Case_01-7", "x" * 200])
def test_valid_manual_id_loads_only_health_and_the_exact_validated_case(case_id):
    requests = []

    def handler(request):
        requests.append(request)
        body = durable_health() if request.url.path == "/health" else empty_view(case_id)
        return httpx.Response(200, json=body)

    view = mock_client(handler).get_saved_case(case_id)
    assert view == empty_view(case_id)
    assert [(request.method, request.url.path) for request in requests] == [
        ("GET", "/health"),
        ("GET", f"/cases/{case_id}"),
    ]
    assert all("authorization" not in request.headers for request in requests)


def test_memory_backend_cannot_be_mistaken_for_durable_saved_case_storage():
    requests = []

    def handler(request):
        requests.append((request.method, request.url.path))
        return httpx.Response(200, json={"status": "ok", "mode": "synthetic_offline"})

    with pytest.raises(ui_client.BackendError) as caught:
        mock_client(handler).get_saved_case("saved-case")
    assert caught.value.code == "SavedCasesUnavailable"
    assert requests == [("GET", "/health")]


def test_reopen_rechecks_a_previously_durable_backend_before_reading_a_case():
    requests = []
    health = [durable_health()]

    def handler(request):
        requests.append((request.method, request.url.path))
        return httpx.Response(200, json=health[0])

    client = mock_client(handler)
    assert client.discover_capabilities().durable_reviews
    health[0] = {"status": "ok", "mode": "synthetic_offline"}
    with pytest.raises(ui_client.BackendError) as caught:
        client.get_saved_case("saved-case")
    assert caught.value.code == "SavedCasesUnavailable"
    assert requests == [("GET", "/health"), ("GET", "/health")]


@pytest.mark.parametrize(
    "mutation", ["foreign_case", "boolean_revision", "missing_log", "bad_pending"]
)
def test_reopen_requires_the_existing_full_case_response_validation(mutation):
    view = empty_view("saved-case")
    if mutation == "foreign_case":
        view["case_id"] = "another-case"
    elif mutation == "boolean_revision":
        view["case_revision"] = True
    elif mutation == "missing_log":
        view.pop("log")
    else:
        view["pending"] = {"proposal_id": "unbound"}

    def handler(request):
        return httpx.Response(200, json=durable_health() if request.url.path == "/health" else view)

    with pytest.raises(ui_client.BackendError) as caught:
        mock_client(handler).get_saved_case("saved-case")
    assert caught.value.code == "BackendResponseInvalid"


@pytest.fixture
def observed_runtime(runtime, monkeypatch):
    runtime.allocations = []
    runtime.ui_requests = []
    runtime.view_override = None
    original_factory = api._adapters
    original_request = ui_client.BackendClient._request

    def adapters(scenario):
        runtime.allocations.append(scenario)
        return original_factory(scenario)

    def request(client, method, path, **kwargs):
        runtime.ui_requests.append((method, path))
        response = original_request(client, method, path, **kwargs)
        if (
            runtime.view_override is not None
            and method == "GET"
            and path == runtime.view_override[0]
        ):
            return deepcopy(runtime.view_override[1])
        return response

    monkeypatch.setattr(api, "_adapters", adapters)
    monkeypatch.setattr(ui_client.BackendClient, "_request", request)
    return runtime


def fresh_session(runtime):
    """Recreate storage facade/backend and browser state, without a process-restart claim."""
    runtime.backend.close()
    runtime.tracker = SQLiteCaseTracker(runtime.path, reviewer_tokens=REVIEWERS)
    runtime.backend = TestClient(
        create_app(runtime.tracker, reviewer_tokens=REVIEWERS), base_url="http://backend"
    )
    st.cache_resource.clear()
    at = AppTest.from_file(PAGE).run()
    assert not at.exception
    return at


def open_case(at, case_id):
    at.sidebar.text_input(key="saved_case_id").set_value(case_id)
    button(at, "Open saved case").click().run()
    assert not at.exception


def assert_read_only_since(runtime, before):
    request_count, allocations, messages, reviews = before
    assert runtime.allocations == allocations
    assert runtime.message_requests == messages
    assert runtime.requests == reviews
    assert runtime.ui_requests[request_count:]
    assert all(method == "GET" for method, _ in runtime.ui_requests[request_count:])
    assert all(
        path == "/health" or path.startswith("/cases/")
        for _, path in runtime.ui_requests[request_count:]
    )


def before_open(runtime):
    return (
        len(runtime.ui_requests),
        list(runtime.allocations),
        deepcopy(runtime.message_requests),
        deepcopy(runtime.requests),
    )


def test_fresh_session_reopens_current_pending_handoff_facts_log_and_revision(observed_runtime):
    runtime = observed_runtime
    first = AppTest.from_file(PAGE).run()
    first.sidebar.selectbox(key="scenario").set_value("answer").run()
    case_id = first.session_state.case_id
    send_message(first, "A neutral saved report.")
    obsolete = current(runtime, case_id)["pending"]["proposal_id"]
    send_correction(first, "1.49.1")
    saved = current(runtime, case_id)
    assert saved["case_revision"] == 2 and saved["pending"]["proposal_id"] != obsolete

    reopened = fresh_session(runtime)
    assert case_id not in reopened.session_state.cases
    before = before_open(runtime)
    open_case(reopened, case_id)
    assert_read_only_since(runtime, before)
    assert reopened.session_state.case_id == reopened.session_state.active_case_id == case_id
    assert reopened.session_state.cases.count(case_id) == 1
    assert current(runtime, case_id) == saved
    facts = next(table.value for table in reopened.dataframe if "Status" in table.value.columns)
    assert list(facts["Name"]) == ["streamlit_version"]
    assert list(facts["Value"]) == ["1.49.1"]
    assert any("Revision 2" in item.value for item in reopened.markdown)
    assert any(saved["pending"]["user_draft"] == item.value for item in reopened.markdown)
    assert obsolete not in " ".join(item.value for item in reopened.caption)
    assert [
        message.markdown[0].value
        for message in reopened.chat_message
        if not any("Waiting for approval" in md.value for md in message.markdown)
    ] == [entry["text"] for entry in saved["log"] if entry["role"] != "system"]


@pytest.mark.parametrize("decision", ["edit", "reject", "approve"])
def test_reopen_uses_saved_edited_rejected_or_already_approved_state(observed_runtime, decision):
    runtime = observed_runtime
    first = AppTest.from_file(PAGE).run()
    first.sidebar.selectbox(key="scenario").set_value("answer").run()
    case_id = first.session_state.case_id
    send_message(first)
    original = current(runtime, case_id)["pending"]["proposal_id"]
    review_click(first, decision)
    saved = current(runtime, case_id)
    reopened = fresh_session(runtime)
    before = before_open(runtime)
    open_case(reopened, case_id)
    assert_read_only_since(runtime, before)
    assert current(runtime, case_id) == saved
    assert len(saved["decisions"]) == 1
    if decision == "edit":
        assert saved["pending"]["edited"] and saved["pending"]["proposal_id"] != original
        assert not reopened.button(key="approve").disabled
        assert any("Edited by maintainer" in item.value for item in reopened.markdown)
    else:
        assert saved["pending"] is None
        assert "approve" not in [item.key for item in reopened.button]
        assert len(saved["actions"]) == (1 if decision == "approve" else 0)


@pytest.mark.parametrize("case_id", ["unknown-saved-case", "unsafe/other?case"])
def test_failed_reopen_retains_the_selected_case_and_does_not_create_storage(
    observed_runtime, case_id
):
    runtime = observed_runtime
    at = AppTest.from_file(PAGE).run()
    selected = at.session_state.case_id
    send_message(at)
    at.button(key="edit").click().run()
    editor_value = at.text_area(key="edited_draft").value
    cases = list(at.session_state.cases)
    generation = at.session_state.form_gen
    saved = current(runtime, selected)
    with runtime.tracker._connect() as db:
        stored_count = db.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
    before = before_open(runtime)
    open_case(at, case_id)
    assert_read_only_since(runtime, before)
    assert at.session_state.case_id == selected and at.session_state.cases == cases
    assert at.session_state.editing and at.session_state.form_gen == generation
    assert at.text_area(key="edited_draft").value == editor_value
    assert current(runtime, selected) == saved
    assert at.error
    if "/" in case_id:
        assert all(case_id not in path for _, path in runtime.ui_requests)
    with runtime.tracker._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM cases").fetchone()[0] == stored_count


def test_open_callback_resets_form_edits_and_preserves_both_per_case_retry_maps(observed_runtime):
    runtime = observed_runtime
    at = AppTest.from_file(PAGE).run()
    first = at.session_state.case_id
    send_message(at)
    pending = current(runtime, first)["pending"]
    target = "another.saved_case-2"
    response = runtime.backend.post(
        f"/cases/{target}/messages",
        json={
            "message": "Another neutral report.",
            "scenario": "ask",
            "turn_id": "target-input",
            "expected_revision": 0,
        },
    )
    assert response.status_code == 200
    at.button(key="edit").click().run()
    at.text_area(key="edited_draft").set_value("Local draft from the first case.")
    generation = at.session_state.form_gen
    at.text_area(key=f"update_message_{generation}").set_value("Unsent old correction.")
    at.session_state.version_reply = "old local version reply"
    events = {
        first: ui_client.new_event("First retry", expected_revision=1, scenario="ask"),
        target: ui_client.new_event("Second retry", expected_revision=1, scenario="ask"),
    }
    operation = ui_client.ReviewOperation(
        first,
        '{"decision":"approve","proposal_id":"' + pending["proposal_id"] + '","case_revision":1}',
        True,
    )
    at.session_state.unsent = deepcopy(events)
    at.session_state.unsent_reviews = {first: operation}
    before = before_open(runtime)
    open_case(at, target)
    assert_read_only_since(runtime, before)
    assert at.session_state.case_id == target and not at.session_state.editing
    assert at.session_state.form_gen == generation + 1
    assert at.text_area(key=f"update_message_{generation + 1}").value == ""
    assert "edited_draft" not in [item.key for item in at.text_area]
    assert "version_reply" not in [item.key for item in at.text_input]
    assert at.session_state.unsent == events
    assert at.session_state.unsent_reviews == {first: operation}
    assert "Retry sending" in [item.label for item in at.button]
    open_case(at, target)
    assert at.session_state.cases.count(target) == 1
    assert at.session_state.unsent == events


def test_validated_stale_projection_cannot_become_approvable_when_opened(observed_runtime):
    runtime = observed_runtime
    at = AppTest.from_file(PAGE).run()
    case_id = at.session_state.case_id
    send_message(at)
    old_pending = current(runtime, case_id)["pending"]
    send_correction(at)
    stale_view = current(runtime, case_id)
    stale_view["pending"] = {**old_pending, "stale": True}
    # A historical pending projection is allowed by the client contract; its
    # staleness must remain visible even though the real tracker retains v2.
    runtime.view_override = (f"/cases/{case_id}", stale_view)
    reopened = fresh_session(runtime)
    before = before_open(runtime)
    open_case(reopened, case_id)
    assert_read_only_since(runtime, before)
    assert any("can no longer be approved" in item.value for item in reopened.warning)
    assert "approve" not in [item.key for item in reopened.button]


def test_lost_review_ack_then_fresh_reopen_shows_the_original_action_once(observed_runtime):
    runtime = observed_runtime
    first = AppTest.from_file(PAGE).run()
    first.sidebar.selectbox(key="scenario").set_value("answer").run()
    case_id = first.session_state.case_id
    send_message(first)
    runtime.loss = "timeout"
    review_click(first, "approve")
    original_retry = first.session_state.unsent_reviews[case_id]
    saved = current(runtime, case_id)
    assert len(saved["actions"]) == len(saved["decisions"]) == 1
    assert saved["review"]["review_id"] == original_retry.payload()["review_id"]
    reopened = fresh_session(runtime)
    assert reopened.session_state.unsent_reviews == {} and reopened.session_state.unsent == {}
    before = before_open(runtime)
    open_case(reopened, case_id)
    assert_read_only_since(runtime, before)
    assert current(runtime, case_id) == saved
    assert "Retry review" not in [item.label for item in reopened.button]
    assert "approve" not in [item.key for item in reopened.button]
    assert len([message for message in reopened.chat_message if message.name == "assistant"]) == 1
    assert any(
        "earlier browser session are not recovered" in item.value
        for item in reopened.sidebar.caption
    )


def test_reopen_controls_are_absent_for_the_memory_backend(observed_runtime):
    runtime = observed_runtime
    runtime.health = {"status": "ok", "mode": "synthetic_offline"}
    at = AppTest.from_file(PAGE).run()
    assert not at.exception
    assert "Open saved case" not in [item.label for item in at.button]
    assert "saved_case_id" not in [item.key for item in at.text_input]


def test_fresh_app_session_reopens_pending_case_after_actual_tcp_process_restart(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("AGENT_PILOT_INDEX", raising=False)
    monkeypatch.delenv("AGENT_PILOT_SNAPSHOT", raising=False)
    database = tmp_path / "reopen-tcp.sqlite3"
    token = "synthetic-case-reopen-tcp-reviewer"
    config = {
        "AGENT_TRACKER_DB": str(database),
        "AGENT_REVIEWER_TOKEN": token,
        "AGENT_PILOT_REASONING": "scripted",
    }
    state = {"http": None}
    requests = []

    class TCPTransport:
        def request(self, method, path, **kwargs):
            requests.append((method, path))
            return state["http"].request(method, path, **kwargs)

    monkeypatch.setattr(
        ui_client,
        "make_client",
        lambda: ui_client.BackendClient(TCPTransport(), reviewer_token=token),
    )

    def durable_counts():
        with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as db:
            return {
                table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (
                    "cases",
                    "events",
                    "run_outcomes",
                    "proposals",
                    "reviews",
                    "local_comments",
                    "conversation",
                    "audit",
                )
            }

    with server(tmp_path / "first-reopen-ready.json", config) as http:
        state["http"] = http
        first = AppTest.from_file(PAGE, default_timeout=15).run()
        assert not first.exception
        send_message(first, "A neutral report saved before process restart.")
        case_id = first.session_state.case_id
        saved = ui_client.BackendClient(http).get_case(case_id)
        assert saved["case_revision"] == 1 and saved["pending"] is not None
        assert saved["actions"] == saved["decisions"] == []
        before_counts = durable_counts()

    # Each server context launches and terminates a separate Python interpreter.
    with server(tmp_path / "second-reopen-ready.json", config) as http:
        state["http"] = http
        st.cache_resource.clear()
        reopened = AppTest.from_file(PAGE, default_timeout=15).run()
        assert not reopened.exception and case_id not in reopened.session_state.cases
        before_requests = len(requests)
        open_case(reopened, case_id)
        assert all(method == "GET" for method, _ in requests[before_requests:])
        assert ui_client.BackendClient(http).get_case(case_id) == saved
        assert durable_counts() == before_counts
        assert reopened.session_state.case_id == case_id
        assert not reopened.button(key="approve").disabled
        assert reopened.session_state.unsent == reopened.session_state.unsent_reviews == {}
