"""Public core input and HTTP setup failure regressions; offline only."""

from fastapi.testclient import TestClient

from agent_app import api
from agent_app.contracts import CaseState, EvidenceBundle, GroundedPlan
from agent_app.orchestration import SupportEngine
from agent_app.orchestration.handoff import ReasoningCapture, build_handoff, validate_handoff
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
