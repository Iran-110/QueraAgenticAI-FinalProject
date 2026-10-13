"""State-aware scripted questions in the no-index persistent development app.

HTTP, the UI's client and SQLite are real; reasoning/evidence remain authored
offline fixtures. Provenance controls seed validated states only into a fresh
temporary test database. This is neither model quality nor held-out evidence.
"""

import json
import sqlite3
from contextlib import contextmanager
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from agent_app import api, ui_client
from agent_app.contracts import CaseState, Fact
from agent_app.llm.config import MetisConfig
from agent_app.offline_backend import configured_app
from agent_app.orchestration import SupportEngine
from agent_app.orchestration.intake import STREAMLIT_VERSION_QUESTION
from agent_app.testing.http_pilot_runtime import offline_network
from agent_app.tracker.sqlite_tracker import SQLiteCaseTracker

TOKEN = "synthetic-private-offline-correction-review-token"
WIDGET_QUESTION = "Can you share the widget's key and code?"


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    state = SimpleNamespace(
        config={
            "AGENT_TRACKER_DB": str(tmp_path / "offline-corrections.sqlite3"),
            "AGENT_REVIEWER_TOKEN": TOKEN,
        },
        runs=[],
        requests=[],
    )
    original_run = SupportEngine.run

    def observed_run(engine, *args, **kwargs):
        state.runs.append((args[0].case_id, args[0].case_revision))
        return original_run(engine, *args, **kwargs)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("No provider/environment configuration or real HTTP transport")

    monkeypatch.setattr(SupportEngine, "run", observed_run)
    monkeypatch.setattr(MetisConfig, "from_env", forbidden)
    monkeypatch.setattr(httpx.HTTPTransport, "__init__", forbidden)

    @contextmanager
    def connect():
        with TestClient(
            configured_app(state.config), base_url="http://offline-backend"
        ) as api_client:

            def handle(request):
                response = api_client.request(
                    request.method,
                    request.url.path,
                    content=request.content,
                    headers=request.headers,
                )
                # Observe public operation bodies/status, never bearer headers.
                state.requests.append(
                    (request.method, request.url.path, request.content, response.status_code)
                )
                return httpx.Response(
                    response.status_code,
                    content=response.content,
                    headers={"content-type": "application/json"},
                )

            with httpx.Client(
                base_url="http://offline-backend", transport=httpx.MockTransport(handle)
            ) as http:
                client = ui_client.BackendClient(http, reviewer_token=TOKEN)
                capabilities = client.discover_capabilities()
                assert capabilities.durable_reviews and capabilities.retrieval_label == "scripted"
                assert capabilities.reasoning_label == "scripted"
                yield client

    state.connect = connect
    with offline_network():
        yield state


def event(revision=0, scenario="ask", *, facts=None, **changes):
    return ui_client.new_event(
        "The widget resets on rerun.",
        expected_revision=revision,
        scenario=scenario,
        reported_facts=facts,
        **changes,
    )


def version(value="1.50.0", name="streamlit_version"):
    return {"name": name, "value": value}


def widget(name="widget_definition"):
    return {"name": name, "value": "st.multiselect('Conversation', options, key='conversation')"}


def assert_version_question(view):
    pending = view["pending"]
    assert pending is not None and pending["decision"] == "ask"
    assert pending["missing_info"] == ["streamlit_version"]
    assert pending["next_question"] == pending["user_draft"] == STREAMLIT_VERSION_QUESTION.question
    assert view["run_outcome"]["error_code"] is None


def assert_widget_question(view):
    pending = view["pending"]
    assert pending is not None and pending["decision"] == "ask"
    assert pending["missing_info"] == ["widget_definition"]
    assert pending["next_question"] == pending["user_draft"] == WIDGET_QUESTION
    assert "version" not in pending["next_question"].casefold()
    assert view["run_outcome"]["error_code"] is None


def test_approved_bare_version_correction_replay_case_isolation_and_review_restart(runtime):
    case_id = "state-aware-question"
    with runtime.connect() as client:
        other = client.get_case("separate-case")
        initial = client.send_event(case_id, event())
        assert_version_question(initial)
        first_operation = client.prepare_review(case_id, initial["pending"], "approve")
        approved = client.send_review(first_operation)
        assert len(approved["actions"]) == 1
        assert approved["awaiting_reply"]["proposal_id"] == initial["pending"]["proposal_id"]
        reply = ui_client.new_event(
            "1.50.0",
            expected_revision=1,
            scenario="ask",
            reply_to_proposal_id=initial["pending"]["proposal_id"],
        )
        known = client.send_event(case_id, reply)
        assert_widget_question(known)
        assert known["intake"]["preparation"] == "canonical_version_reply"
        old_operation = client.prepare_review(case_id, known["pending"], "approve")
        correction = event(2, facts=[version("1.49.0")])
        corrected = client.send_event(case_id, correction)
        assert_widget_question(corrected)
        assert corrected["case_revision"] == 3
        assert corrected["pending"]["proposal_id"] != known["pending"]["proposal_id"]
        facts = [fact for fact in corrected["facts"] if fact["name"] == "streamlit_version"]
        assert [(fact["value"], fact["status"]) for fact in facts] == [
            ("1.50.0", "superseded"),
            ("1.49.0", "active"),
        ]
        assert facts[-1]["provenance_kind"] == "user"
        assert facts[-1]["turn_id"] == correction["turn_id"]
        with pytest.raises(ui_client.BackendError) as stale:
            client.send_review(old_operation)
        assert stale.value.code == "StaleRevision"
        assert runtime.requests[-1][3] == 409
        assert client.get_case("separate-case") == other
        run_count = len(runtime.runs)
        for original in (reply, correction):
            replay = client.send_event(case_id, original)
            assert replay["intake"]["replayed"]
            assert replay["case_revision"] == 3
            assert replay["pending"] == corrected["pending"]
            assert len(runtime.runs) == run_count
        current_operation = client.prepare_review(case_id, corrected["pending"], "approve")
        current = client.send_review(current_operation)
        actions = current["actions"]
        assert len(actions) == 2  # One approved version question, one approved widget question.
    with runtime.connect() as client:
        current = client.get_case(case_id)
        assert current["case_revision"] == 3 and current["actions"] == actions
        for operation in (current_operation, first_operation):
            retried = client.send_review(operation)
            assert retried["review"]["replayed"] and retried["actions"] == actions
            assert len(runtime.runs) == run_count
        assert client.get_case("separate-case") == other
        replay = client.send_event(case_id, correction)
        assert replay["intake"]["replayed"] and replay["actions"] == actions
        assert len(runtime.runs) == run_count
        assert TOKEN not in json.dumps(replay)
        assert TOKEN not in current_operation.body_json and TOKEN not in first_operation.body_json


@pytest.mark.parametrize("name", ["streamlit_version", "STREAMLIT_VERSION"])
def test_known_version_on_first_turn_asks_only_for_widget(runtime, name):
    with runtime.connect() as client:
        view = client.send_event("known-first-turn", event(facts=[version(name=name)]))
    assert_widget_question(view)
    assert view["actions"] == [] and view["case_revision"] == 1
    assert len(runtime.runs) == 1


@pytest.mark.parametrize(
    "names",
    [("streamlit_version", "widget_definition"), ("STREAMLIT_VERSION", "Widget_Definition")],
)
def test_both_user_facts_known_escalates_without_reasking_or_inventing_answer(runtime, names):
    with runtime.connect() as client:
        view = client.send_event(
            "known-both", event(facts=[version(name=names[0]), widget(name=names[1])])
        )
    assert view["pending"] is not None and view["pending"]["decision"] == "escalate"
    assert view["pending"]["missing_info"] == [] and view["pending"]["next_question"] is None
    assert view["run_outcome"]["error_code"] is None and view["actions"] == []
    assert view["quality_claim"] is False and view["pending"]["synthetic"] is True


def test_version_only_scenario_does_not_introduce_widget_question_when_version_known(runtime):
    with runtime.connect() as client:
        view = client.send_event(
            "known-version-only", event(scenario="ask_version", facts=[version()])
        )
    assert view["pending"] is not None and view["pending"]["decision"] == "escalate"
    assert view["pending"]["missing_info"] == [] and view["pending"]["next_question"] is None
    assert view["run_outcome"]["error_code"] is None


def test_version_withdrawal_restores_question_and_keeps_other_user_fact(runtime):
    with runtime.connect() as client:
        known = client.send_event("withdrawal", event(facts=[version(), widget()]))
        withdrawn = client.send_event("withdrawal", event(1, facts=[version(None)]))
    assert known["case_revision"] == 1 and withdrawn["case_revision"] == 2
    assert_version_question(withdrawn)
    assert "streamlit_version" in withdrawn["unknowns"]
    assert not any(
        fact["name"] == "streamlit_version" and fact["status"] == "active"
        for fact in withdrawn["facts"]
    )
    assert any(
        fact["name"] == "widget_definition" and fact["status"] == "active"
        for fact in withdrawn["facts"]
    )


@pytest.mark.parametrize(
    ("name", "kind", "status", "question"),
    [
        ("streamlit_version", "evidence", "active", "version"),
        ("streamlit_version", "user", "superseded", "version"),
        ("widget_definition", "evidence", "active", "widget"),
        ("widget_definition", "user", "superseded", "widget"),
    ],
)
def test_only_active_user_provenance_suppresses_scripted_gap(runtime, name, kind, status, question):
    case_id = "provenance-control"
    other = widget() if name == "streamlit_version" else version()
    value = version()["value"] if name == "streamlit_version" else widget()["value"]
    state = CaseState(
        case_id=case_id,
        facts=(
            Fact(
                name=name,
                value=value,
                source_ref="fixture:explicit-provenance",
                turn_id="fixture-provenance",
                provenance_kind=kind,
                status=status,
            ),
            Fact(
                name=other["name"],
                value=other["value"],
                source_ref="user:fixture",
                turn_id="fixture",
            ),
        ),
    )
    SQLiteCaseTracker(
        runtime.config["AGENT_TRACKER_DB"], reviewer_tokens={"local-maintainer": TOKEN}
    )
    with sqlite3.connect(runtime.config["AGENT_TRACKER_DB"]) as database:
        database.execute(
            "INSERT INTO cases(case_id,state_json,status,awaiting_reply_json) VALUES(?,?,'open',NULL)",
            (case_id, state.model_dump_json()),
        )
    with runtime.connect() as client:
        view = client.send_event(case_id, event())
    (assert_version_question if question == "version" else assert_widget_question)(view)


@pytest.mark.parametrize(
    ("scenario", "decision", "attempts", "rounds"),
    [
        ("answer", "answer", 1, 1),
        ("refine", "answer", 2, 2),
        ("escalate", "escalate", 1, 1),
        ("error", None, 0, 1),
    ],
)
def test_other_explicit_offline_scenarios_keep_existing_scripts(
    runtime, scenario, decision, attempts, rounds
):
    with runtime.connect() as client:
        view = client.send_event(
            "unchanged-explicit", event(scenario=scenario, facts=[version(), widget()])
        )
    if decision is None:
        assert view["pending"] is None
        assert view["run_outcome"]["error_code"] == "RetrievalUnavailable"
    else:
        assert view["pending"]["decision"] == decision
    result = view["run_outcome"]["result"]
    assert result["model_attempts"] == attempts and result["retrieval_rounds"] == rounds
    assert view["actions"] == [] and view["quality_claim"] is False


def test_legacy_scripted_ports_still_trigger_core_known_fact_guard():
    legacy = api._adapters("ask")
    case = CaseState(
        case_id="legacy-known-fact-negative-control",
        facts=(Fact(name="streamlit_version", value="1.50.0", source_ref="user:1", turn_id="1"),),
    )
    with offline_network():
        result = SupportEngine(
            legacy.retriever, legacy.reasoner, snapshot_id=legacy.snapshot_id
        ).run(case, "Widget loses its value.", run_id="legacy-known-fact-control")
    assert result.analysis is None and result.error_code == "KnownFactMarkedMissing"
    assert api._script("ask")[1][0].missing_info == ("streamlit_version", "widget_definition")
