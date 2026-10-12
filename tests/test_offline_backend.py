from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_app.offline_backend import configured_app


def configuration(tmp_path):
    return {
        "AGENT_TRACKER_DB": str(tmp_path / "case.sqlite3"),
        "AGENT_REVIEWER_TOKEN": "synthetic-private-review-token-for-offline-tests",
    }


@pytest.mark.parametrize(
    "change",
    [
        {"AGENT_TRACKER_DB": ""},
        {"AGENT_TRACKER_DB": ":memory:"},
        {"AGENT_REVIEWER_TOKEN": "short"},
        {"AGENT_REVIEWER_TOKEN": "a" * 32 + "\n" + "b"},
        {"AGENT_REVIEWER_TOKEN": "a" * 32 + "☃"},
        {"AGENT_REVIEWER_TOKEN": "a" * 513},
        {"AGENT_REVIEWER_ID": "not valid"},
        {"AGENT_PILOT_INDEX": ""},
        {"AGENT_PILOT_INDEX": "/missing-index"},
        {"AGENT_PILOT_SNAPSHOT": "docs-pilot-" + "a" * 64},
    ],
)
def test_invalid_explicit_config_fails_before_creating_tracker(tmp_path, change):
    config = {**configuration(tmp_path), **change}
    with pytest.raises(ValueError, match="^OfflineBackendConfigurationInvalid$"):
        configured_app(config)
    assert not (tmp_path / "case.sqlite3").exists()


def test_persistent_launcher_authenticates_and_restarts(tmp_path):
    config = configuration(tmp_path)
    with TestClient(configured_app(config)) as client:
        health = client.get("/health").json()
        assert health["capabilities"] == {
            "stable_event_ids": True,
            "durable_reviews": True,
            "reviewer_auth": "bearer",
        }
        assert health["retrieval_label"] == "scripted"
        assert health["quality_claim"] is False
        result = client.post(
            "/cases/launch/messages",
            json={
                "message": "Widget resets on rerun",
                "turn_id": "event-1",
                "expected_revision": 0,
                "scenario": "ask_version",
            },
        )
        assert result.status_code == 200
        proposal = result.json()["pending"]
        operation = {
            "proposal_id": proposal["proposal_id"],
            "case_revision": 1,
            "decision": "approve",
            "review_id": "review-1",
            "expected_handoff_sha256": proposal["review_handoff"]["handoff_sha256"],
        }
        assert client.post("/cases/launch/decision", json=operation).status_code == 401
        headers = {"Authorization": f"Bearer {config['AGENT_REVIEWER_TOKEN']}"}
        accepted = client.post("/cases/launch/decision", json=operation, headers=headers)
        assert accepted.status_code == 200
    with TestClient(configured_app(config)) as fresh:
        replay = fresh.post("/cases/launch/decision", json=operation, headers=headers)
        assert replay.status_code == 200
        assert replay.json()["review"]["replayed"] is True
        assert len(replay.json()["actions"]) == 1
        assert config["AGENT_REVIEWER_TOKEN"] not in replay.text
    assert Path(config["AGENT_TRACKER_DB"]).is_file()
