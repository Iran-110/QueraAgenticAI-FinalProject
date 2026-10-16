"""Verify durable retrieval failure and safe next-turn continuation."""

import sqlite3

from fastapi.testclient import TestClient

from agent_app.offline_backend import configured_app
from agent_app.testing.http_pilot_runtime import offline_network


def test_retrieval_failure_then_next_turn(tmp_path):
    db_path = tmp_path / "failure-next-turn.sqlite3"
    config = {
        "AGENT_TRACKER_DB": str(db_path),
        "AGENT_REVIEWER_TOKEN": "synthetic-private-failure-test-token",
    }

    case_id = "failure-next-turn-case"
    url = f"/cases/{case_id}/messages"

    first_event = {
        "message": "My Streamlit widget resets on rerun.",
        "turn_id": "initial-failing-turn",
        "expected_revision": 0,
        "scenario": "error",
        "reported_facts": [{"name": "streamlit_version", "value": "1.49.1"}],
    }

    with offline_network():
        with TestClient(configured_app(config)) as client:
            response = client.post(url, json=first_event)
            assert response.status_code == 200
            failed = response.json()

            assert failed["case_revision"] == 1
            assert failed["run_outcome"]["error_code"] == "RetrievalUnavailable"
            assert failed["pending"] is None
            assert failed["actions"] == []

            replay_response = client.post(url, json=first_event)
            assert replay_response.status_code == 200
            replay = replay_response.json()

            assert replay["intake"]["replayed"] is True
            assert replay["run_outcome"] == failed["run_outcome"]

            next_event = {
                "message": "Please continue using the confirmed facts.",
                "turn_id": "continuation-after-failure",
                "expected_revision": 1,
                "scenario": "ask",
            }

            response = client.post(url, json=next_event)
            assert response.status_code == 200
            continued = response.json()

            assert continued["case_revision"] == 2
            assert continued["run_outcome"]["error_code"] is None
            assert continued["pending"]["decision"] == "ask"
            assert continued["pending"]["missing_info"] == ["widget_definition"]
            assert continued["actions"] == []

            assert any(
                fact["name"] == "streamlit_version"
                and fact["value"] == "1.49.1"
                and fact["status"] == "active"
                for fact in continued["facts"]
            )

    with sqlite3.connect(db_path) as database:
        previous = database.execute(
            "SELECT error_code FROM run_outcomes WHERE case_id=? AND turn_id=?",
            (case_id, first_event["turn_id"]),
        ).fetchone()

    assert previous == ("RetrievalUnavailable",)


def test_different_prior_failures_same_next_decision(tmp_path, monkeypatch):
    from agent_app.orchestration import SupportEngine

    config = {
        "AGENT_TRACKER_DB": str(tmp_path / "comparison.sqlite3"),
        "AGENT_REVIEWER_TOKEN": "synthetic-comparison-reviewer-token-20261016",
    }

    retrieval_case = "t4-retrieval-failure"
    core_case = "t4-core-failure"
    original_run = SupportEngine.run

    def controlled_run(engine, case, message, *args, **kwargs):
        if case.case_id == core_case and case.case_revision == 1:
            raise RuntimeError("SyntheticCoreFailure")
        return original_run(engine, case, message, *args, **kwargs)

    first_event = {
        "message": "My Streamlit widget resets on rerun.",
        "turn_id": "first-turn",
        "expected_revision": 0,
        "scenario": "error",
        "reported_facts": [{"name": "streamlit_version", "value": "1.49.1"}],
    }

    with offline_network():
        with TestClient(configured_app(config)) as client:
            failures = {}

            with monkeypatch.context() as patch:
                patch.setattr(SupportEngine, "run", controlled_run)

                for case_id in (retrieval_case, core_case):
                    response = client.post(
                        f"/cases/{case_id}/messages",
                        json=first_event,
                    )
                    assert response.status_code == 200
                    failures[case_id] = response.json()

            assert failures[retrieval_case]["run_outcome"]["error_code"] == "RetrievalUnavailable"
            assert failures[core_case]["run_outcome"]["error_code"] == "CoreRunFailed"

            for failed in failures.values():
                assert failed["case_revision"] == 1
                assert failed["pending"] is None
                assert failed["actions"] == []

            assert failures[retrieval_case]["facts"] == failures[core_case]["facts"]
            assert failures[retrieval_case]["unknowns"] == failures[core_case]["unknowns"]

            decisions = {}

            for case_id in (retrieval_case, core_case):
                response = client.post(
                    f"/cases/{case_id}/messages",
                    json={
                        "message": "Please continue using the confirmed facts.",
                        "turn_id": "second-turn",
                        "expected_revision": 1,
                        "scenario": "ask",
                    },
                )
                assert response.status_code == 200

                view = response.json()
                assert view["case_revision"] == 2
                assert view["run_outcome"]["error_code"] is None
                assert view["actions"] == []

                pending = view["pending"]
                assert pending is not None

                decisions[case_id] = (
                    pending["decision"],
                    pending["missing_info"],
                    pending["next_question"],
                )

            assert decisions[retrieval_case] == decisions[core_case]
            assert decisions[retrieval_case][0] == "ask"
            assert decisions[retrieval_case][1] == ["widget_definition"]
