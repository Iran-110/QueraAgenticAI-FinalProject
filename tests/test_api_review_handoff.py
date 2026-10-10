"""HTTP review boundary regressions; authored offline adapters, no quality score."""

import pytest
from fastapi.testclient import TestClient

from agent_app import api
from agent_app.demo import _answer, _evidence
from agent_app.tracker.dummy_tracker import DummyTracker


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(api, "_cases", {})
    monkeypatch.setattr(api, "tracker", DummyTracker())
    return TestClient(api.app)


def send(client):
    response = client.post(
        "/cases/review-case/messages", json={"message": "A widget reset.", "scenario": "answer"}
    )
    assert response.status_code == 200
    return response.json()["pending"]


def decide(client, pending, decision, **extra):
    return client.post(
        "/cases/review-case/decision",
        json={
            "proposal_id": pending["proposal_id"],
            "case_revision": pending["case_revision"],
            "decision": decision,
            **extra,
        },
    )


def test_unused_bundle_cannot_shadow_the_source_actually_consumed(client, monkeypatch):
    consumed = _evidence("same-id", "The source the reasoner actually consumed.")
    unused = _evidence("same-id", "An unused prepared response with the same chunk ID.")
    unused = unused.model_copy(update={"warnings": ("UnusedResponseWarning",)})
    monkeypatch.setattr(api, "_script", lambda _: ([consumed, unused], [_answer("same-id")]))
    pending = send(client)
    assert pending["evidence"][0]["excerpt"] == consumed.hits[0].excerpt
    assert "UnusedResponseWarning" not in pending["warnings"]


def test_review_exports_full_source_metadata_and_not_just_a_url(client):
    pending = send(client)
    source = pending["evidence"][0]
    assert source["source_id"]
    assert "source_commit" in source and "applicable_versions" in source and "score" in source
    assert len(source["content_sha256"]) == 64
    assert source["version_scope"] == "unconfirmed"


def test_review_handoff_contains_full_analysis_case_and_consumed_bundle(client):
    pending = send(client)
    exported = pending["review_handoff"]
    from agent_app.contracts import ProposalHandoff

    handoff = ProposalHandoff.model_validate(exported)
    assert handoff.proposal_id == pending["proposal_id"]
    assert handoff.case.pending_proposal_id is None
    assert handoff.case.case_revision == pending["case_revision"]
    assert handoff.evidence.retrieval_round == pending["retrieval_rounds"]
    assert pending["analysis"] == handoff.analysis.model_dump(mode="json")
    assert handoff.packet.analysis_sha256
    assert handoff.reasoning_context.run_id == pending["proposal_id"]


def test_identical_text_edit_gets_new_bound_handoff_and_requires_approval(client):
    original = send(client)
    response = decide(client, original, "edit", edited_draft=original["user_draft"])
    assert response.status_code == 200
    revised = response.json()["pending"]
    assert (
        revised["review_handoff"]["handoff_sha256"] != original["review_handoff"]["handoff_sha256"]
    )
    assert revised["review_handoff"]["packet"] == original["review_handoff"]["packet"]
    assert revised["review_handoff"]["proposal_id"] == revised["proposal_id"]
    assert (
        revised["review_handoff"]["reasoning_context"]
        == original["review_handoff"]["reasoning_context"]
    )
    assert decide(client, original, "approve").status_code == 409
    assert [entry["role"] for entry in response.json()["log"]] == ["user", "system"]
