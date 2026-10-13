"""An upgrade cannot reinterpret a durably recorded failed ingress event.

The historical event is created with the unchanged legacy authored port in a
temporary SQLite database. No original PR40 case or provider is contacted.
"""

from fastapi.testclient import TestClient

from agent_app.offline_backend import configured_app
from agent_app.orchestration import SupportEngine
from agent_app.persistent_api import create_app
from agent_app.testing.http_pilot_runtime import offline_network
from agent_app.tracker.sqlite_tracker import SQLiteCaseTracker


def test_failed_legacy_event_is_replayed_after_upgrade_and_new_turn_continues(
    tmp_path, monkeypatch
):
    token = "synthetic-private-upgrade-review-token"
    config = {
        "AGENT_TRACKER_DB": str(tmp_path / "upgrade.sqlite3"),
        "AGENT_REVIEWER_TOKEN": token,
    }
    case_id = "durably-recorded-script-stop"
    url = f"/cases/{case_id}/messages"
    original_event = {
        "message": "The affected app uses Streamlit 1.49.1 and the widget resets.",
        "turn_id": "already-recorded-event",
        "expected_revision": 0,
        "scenario": "ask",
        "reported_facts": [{"name": "streamlit_version", "value": "1.49.1"}],
    }
    calls = []
    original_run = SupportEngine.run

    def observed_run(engine, *args, **kwargs):
        calls.append((args[0].case_id, args[0].case_revision))
        return original_run(engine, *args, **kwargs)

    monkeypatch.setattr(SupportEngine, "run", observed_run)
    with offline_network():
        tracker = SQLiteCaseTracker(
            config["AGENT_TRACKER_DB"], reviewer_tokens={"local-maintainer": token}
        )
        # adapters=None deliberately preserves the historical fixed ask script.
        with TestClient(create_app(tracker, reviewer_tokens={"local-maintainer": token})) as old:
            response = old.post(url, json=original_event)
            assert response.status_code == 200
            failed = response.json()
            assert failed["run_outcome"]["error_code"] == "KnownFactMarkedMissing"
            assert failed["pending"] is None and failed["actions"] == []
            assert len(calls) == 1

        with TestClient(configured_app(config)) as upgraded:
            replay = upgraded.post(url, json=original_event).json()
            assert replay["intake"]["replayed"]
            assert replay["run_outcome"] == failed["run_outcome"]
            assert replay["facts"] == failed["facts"]
            assert replay["case_revision"] == failed["case_revision"]
            assert replay["pending"] is None and replay["actions"] == []
            assert len(calls) == 1

            response = upgraded.post(
                url,
                json={
                    "message": "Continue this case using its current confirmed facts.",
                    "turn_id": "fresh-continuation-event",
                    "expected_revision": failed["case_revision"],
                    "scenario": "ask",
                },
            )
            assert response.status_code == 200
            continued = response.json()
            assert len(calls) == 2
            assert continued["case_revision"] == failed["case_revision"] + 1
            assert continued["run_outcome"]["error_code"] is None
            assert continued["pending"]["decision"] == "ask"
            assert continued["pending"]["missing_info"] == ["widget_definition"]
            assert "version" not in continued["pending"]["next_question"].casefold()
            assert continued["facts"] == failed["facts"]
            assert continued["actions"] == []
