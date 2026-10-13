"""The evaluation wrapper must preserve the API's resource custody boundary."""

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from agent_app import api
from agent_app.contracts import AnalysisResult
from agent_app.evaluation import runner
from agent_app.testing.fakes import FakeReasoner, FakeRetriever
from agent_app.testing.http_pilot_runtime import offline_network
from agent_app.tracker.dummy_tracker import DummyTracker

FIXTURE = runner.ROOT / "data/evaluation/dev/pilot-12782.json"


@pytest.mark.parametrize("failure", [None, "retrieval", "reasoning", "supplier", "cleanup"])
def test_runner_ports_close_once_before_stage_and_event_replay_allocates_nothing(
    monkeypatch, failure
):
    fixture = runner.load_fixture(FIXTURE)
    turn = fixture.data["turns"][0]
    calls = []
    contexts, rounds = [], []

    class OrderedTracker(DummyTracker):
        def pause_for_approval(self, case_id, proposal):
            assert calls == ["factory", "supplier", "cleanup"]
            calls.append("stage")
            return super().pause_for_approval(case_id, proposal)

    def supplier():
        calls.append("supplier")
        if failure == "supplier":
            raise RuntimeError("private-fixture-supplier-detail")
        return None

    def cleanup():
        calls.append("cleanup")
        if failure == "cleanup":
            raise RuntimeError("private-fixture-cleanup-detail")

    def adapters(case_id, actual_turn):
        calls.append("factory")
        ports = runner._scripted(fixture)(case_id, actual_turn)
        if failure == "retrieval":
            ports = replace(ports, retriever=FakeRetriever([RuntimeError("private-retrieval")]))
        if failure == "reasoning":
            ports = replace(ports, reasoner=FakeReasoner([RuntimeError("private-reasoning")] * 2))
        return replace(ports, grounded_request_supplier=supplier, cleanup=cleanup)

    case_run = runner.CaseRun(fixture, adapters, runner.Usage(None))
    monkeypatch.setattr(api, "_cases", {})
    monkeypatch.setattr(api, "tracker", OrderedTracker())
    monkeypatch.setattr(
        api,
        "_adapters",
        lambda _scenario: case_run._adapters(fixture.case["case_id"], turn, contexts, rounds),
    )
    event = runner._event(turn, 0, None)
    endpoint = f"/cases/{fixture.case['case_id']}/messages"
    with offline_network(), TestClient(api.app) as client:
        first = client.post(endpoint, json=event)
        repeated = client.post(endpoint, json=event)
    assert first.status_code == repeated.status_code == 200
    original, replayed = first.json(), repeated.json()
    assert original["pending"] == replayed["pending"]
    assert replayed["intake"]["replayed"] and replayed["case_revision"] == 1
    assert calls.count("factory") == calls.count("cleanup") == 1
    assert "private" not in first.text and "private" not in repeated.text
    if failure is None:
        handoff = original["pending"]["review_handoff"]
        assert calls == ["factory", "supplier", "cleanup", "stage"]
        assert handoff["analysis"] == AnalysisResult.model_validate(
            turn["agent_script"]
        ).model_dump(mode="json")
        assert handoff["evidence"] == fixture.bundles[turn["evidence_bundle"]].model_dump(
            mode="json"
        )
        assert len(contexts) == len(rounds) == 1
    else:
        assert original["pending"] is None and "stage" not in calls
        if failure == "cleanup":
            assert "AdapterCleanupFailed" in first.text
