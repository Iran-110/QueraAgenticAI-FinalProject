"""Public core input and HTTP setup failure regressions; offline only."""

from fastapi.testclient import TestClient

from agent_app import api
from agent_app.contracts import CaseState, EvidenceBundle, GroundedPlan
from agent_app.orchestration import SupportEngine
from agent_app.orchestration.handoff import (
    HandoffRejected,
    ReasoningCapture,
    build_handoff,
    validate_handoff,
)
from agent_app.reasoning.grounding import GroundedReasoner, make_grounded_request
from agent_app.testing.fakes import FakeRetriever
from agent_app.tracker.dummy_tracker import DummyTracker


def test_valid_outer_whitespace_preserves_original_message_and_canonical_grounded_request():
    prepared = []
    original_message = "  Widget reset after rerun.\n"

    def factory(case, message, evidence):
        request = make_grounded_request(case, message, evidence)
        prepared.append(request)
        return request

    class Planner:
        def plan(self, request, *, context):
            return GroundedPlan(context_sha256=request.context_sha256, decision="escalate")

    capture = ReasoningCapture(GroundedReasoner(Planner(), request_factory=factory))
    result = SupportEngine(
        FakeRetriever([EvidenceBundle(snapshot_id="boundary-fixture")]),
        capture,
        snapshot_id="boundary-fixture",
    ).run(CaseState(case_id="boundary-case"), original_message)
    assert result.status == "awaiting_approval"
    handoff = build_handoff(result, capture.last, grounded_request=prepared[-1])
    assert handoff.user_message == original_message
    assert handoff.grounded_request.user_message == original_message.strip()
    assert validate_handoff(handoff) == handoff
    # Only outer whitespace is canonicalized. A changed message body remains
    # a different input even if someone builds a valid new request digest.
    different_request = make_grounded_request(
        handoff.case, "Widget reset BEFORE rerun.", handoff.evidence
    )
    try:
        build_handoff(result, capture.last, grounded_request=different_request)
    except HandoffRejected as error:
        assert error.code == "GroundedContextMismatch"
    else:
        raise AssertionError("Changed message content was accepted")


def test_adapter_setup_failure_is_recorded_without_leaking_or_replaying(monkeypatch):
    monkeypatch.setattr(api, "_cases", {})
    monkeypatch.setattr(api, "tracker", DummyTracker())
    calls = []

    def unavailable(_scenario):
        calls.append(_scenario)
        raise RuntimeError("PRIVATE_SETUP_MARKER")

    monkeypatch.setattr(api, "_adapters", unavailable)
    request = {"message": "Widget reset.", "turn_id": "setup-event", "expected_revision": 0}
    with TestClient(api.app, raise_server_exceptions=False) as client:
        failed = client.post("/cases/setup-case/messages", json=request)
        assert failed.status_code == 200
        view = failed.json()
        assert view["case_revision"] == 1 and view["status"] == "open"
        assert view["pending"] is None and view["decisions"] == []
        assert view["log"][-1] == {
            "role": "system",
            "text": "The run stopped (error: AdapterSetupUnavailable). Nothing was proposed.",
        }
        assert "PRIVATE_SETUP_MARKER" not in failed.text
        replay = client.post("/cases/setup-case/messages", json=request)
        assert replay.status_code == 200 and replay.json()["intake"]["replayed"] is True
        assert replay.json()["log"] == view["log"]
        assert replay.json()["case_revision"] == 1 and calls == ["ask"]


def test_setup_failure_after_correction_cannot_release_previous_proposal(monkeypatch):
    monkeypatch.setattr(api, "_cases", {})
    monkeypatch.setattr(api, "tracker", DummyTracker())
    with TestClient(api.app) as client:
        original = client.post(
            "/cases/setup-case/messages", json={"message": "Which version applies?"}
        ).json()["pending"]

        def unavailable(_scenario):
            raise RuntimeError("PRIVATE_SETUP_MARKER")

        monkeypatch.setattr(api, "_adapters", unavailable)
        failed = client.post(
            "/cases/setup-case/messages",
            json={
                "message": "Correction: version 1.49.1.",
                "turn_id": "setup-correction",
                "expected_revision": 1,
                "reported_facts": [{"name": "streamlit_version", "value": "1.49.1"}],
            },
        )
        assert failed.status_code == 200
        view = failed.json()
        assert view["case_revision"] == 2 and view["pending"]["stale"] is True
        assert api._cases["setup-case"].pending_handoff is None
        assert api._cases["setup-case"].state.pending_proposal_id is None
        rejected = client.post(
            "/cases/setup-case/decision",
            json={
                "decision": "approve",
                "proposal_id": original["proposal_id"],
                "case_revision": original["case_revision"],
            },
        )
        assert rejected.status_code == 409
        assert view["decisions"] == []
        assert all(item["role"] != "assistant" for item in view["log"])
