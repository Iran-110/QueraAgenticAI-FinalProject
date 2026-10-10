"""Ingress regressions: explicit reports must reach the existing pure core."""

import pytest
from fastapi.testclient import TestClient

from agent_app import api
from agent_app.tracker.dummy_tracker import DummyTracker


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(api, "_cases", {})
    monkeypatch.setattr(api, "tracker", DummyTracker())
    return TestClient(api.app)


def event(**updates):
    return {
        "message": "The affected environment uses Streamlit 1.50.0.",
        "scenario": "ask",
        "turn_id": "event-1",
        "expected_revision": 0,
        "reported_facts": [{"name": "streamlit_version", "value": "1.50.0"}],
        **updates,
    }


def test_explicit_report_reaches_core_with_user_attribution(client):
    response = client.post("/cases/case-1/messages", json=event())
    assert response.status_code == 200
    facts = response.json()["facts"]
    assert [(f["name"], f["value"], f["provenance_kind"], f["turn_id"]) for f in facts] == [
        ("streamlit_version", "1.50.0", "user", "event-1")
    ]


def test_stale_structured_event_cannot_mutate_case(client):
    client.post("/cases/case-1/messages", json=event())
    before = client.get("/cases/case-1").json()
    stale = event(turn_id="event-2", reported_facts=[{"name": "streamlit_version", "value": "1.42.0"}])
    response = client.post("/cases/case-1/messages", json=stale)
    assert response.status_code == 409
    assert client.get("/cases/case-1").json() == before


def test_same_original_event_replays_without_another_run(client, monkeypatch):
    calls = []
    original = api._script

    def capture(scenario):
        calls.append(scenario)
        return original(scenario)

    monkeypatch.setattr(api, "_script", capture)
    first = client.post("/cases/case-1/messages", json=event()).json()
    replay = client.post("/cases/case-1/messages", json=event()).json()
    assert replay["case_revision"] == first["case_revision"] == 1
    assert replay["pending"]["proposal_id"] == first["pending"]["proposal_id"]
    assert calls == ["ask"]


def test_unknown_authority_fields_are_rejected_before_case_creation(client):
    response = client.post("/cases/case-1/messages", json=event(approved=True, source_ref="fake"))
    assert response.status_code == 422
    assert "case-1" not in api._cases
