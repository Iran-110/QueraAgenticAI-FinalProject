import pytest
from fastapi.testclient import TestClient

from agent_app import api
from agent_app.tracker.dummy_tracker import DummyTracker


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(api, "_cases", {})
    monkeypatch.setattr(api, "tracker", DummyTracker())
    return TestClient(api.app)


def send(client, case_id="case-1", message="My widget loses its value.", scenario="ask"):
    response = client.post(
        f"/cases/{case_id}/messages", json={"message": message, "scenario": scenario}
    )
    assert response.status_code == 200
    return response.json()


def decide(client, pending, decision, case_id="case-1", **extra):
    payload = {
        "proposal_id": pending["proposal_id"],
        "case_revision": pending["case_revision"],
        "decision": decision,
        **extra,
    }
    return client.post(f"/cases/{case_id}/decision", json=payload)


def test_message_creates_pending_proposal_without_releasing_draft(client):
    view = send(client)
    assert view["status"] == "awaiting_review"
    assert view["case_revision"] == 1
    assert view["pending"]["decision"] == "ask"
    assert view["pending"]["stale"] is False
    assert [entry["role"] for entry in view["log"]] == ["user"]


def test_answer_proposal_carries_cited_evidence(client):
    pending = send(client, scenario="answer")["pending"]
    assert pending["evidence"][0]["chunk_id"] == "demo-initial"
    assert pending["evidence"][0]["source_url"].startswith("https://")
    assert pending["synthetic"] is True


def test_approve_releases_draft_once(client):
    pending = send(client)["pending"]
    approved = decide(client, pending, "approve")
    assert approved.status_code == 200
    view = approved.json()
    assert view["pending"] is None
    assert view["status"] == "awaiting_user"
    assert view["log"][-1] == {
        "role": "assistant",
        "text": pending["user_draft"],
        "decision": "ask",
        "edited": False,
    }
    again = decide(client, pending, "approve")
    assert again.status_code == 409
    assert len(client.get("/cases/case-1").json()["log"]) == 2


def test_reject_sends_nothing(client):
    pending = send(client, scenario="answer")["pending"]
    view = decide(client, pending, "reject").json()
    assert view["status"] == "open"
    assert [entry["role"] for entry in view["log"]] == ["user", "system"]
    assert view["decisions"][-1]["decision"] == "reject"


def test_edit_creates_new_proposal_that_needs_approval(client):
    pending = send(client)["pending"]
    view = decide(client, pending, "edit", edited_draft="Which version do you use?").json()
    revised = view["pending"]
    assert revised["proposal_id"] != pending["proposal_id"]
    assert revised["edited"] is True
    assert revised["user_draft"] == revised["next_question"] == "Which version do you use?"
    assert view["status"] == "awaiting_review"
    assert decide(client, pending, "approve").status_code == 409
    final = decide(client, revised, "approve").json()
    assert final["log"][-1]["text"] == "Which version do you use?"
    assert final["log"][-1]["edited"] is True


def test_edit_requires_draft(client):
    pending = send(client)["pending"]
    assert decide(client, pending, "edit", edited_draft="  ").status_code == 422


def test_new_message_makes_old_proposal_stale(client):
    old = send(client)["pending"]
    view = send(client, message="Correction: version 1.51.", scenario="error")
    assert view["pending"]["stale"] is True
    assert view["status"] == "open"
    assert decide(client, old, "approve").status_code == 409


def test_stopped_run_proposes_nothing(client):
    view = send(client, scenario="error")
    assert view["pending"] is None
    assert view["log"][-1]["role"] == "system"


def test_decision_errors(client):
    fake = {"proposal_id": "x", "case_revision": 0}
    assert decide(client, fake, "approve", case_id="missing").status_code == 404
    send(client, scenario="error")
    assert decide(client, fake, "approve").status_code == 409
    assert decide(client, fake, "delete").status_code == 422


def test_cases_are_isolated(client):
    send(client, case_id="case-a")
    assert client.get("/cases/case-b").json()["pending"] is None


def test_invalid_case_id_rejected(client):
    assert client.get("/cases/-bad").status_code == 422
