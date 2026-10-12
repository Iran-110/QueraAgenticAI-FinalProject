"""Per-run cleanup preserves handoff custody and the durable HTTP boundary."""

import json

import pytest
from fastapi.testclient import TestClient

from agent_app import api
from agent_app.contracts import UserTurn
from agent_app.demo import SNAPSHOT_ID, _answer, _evidence
from agent_app.orchestration import service as service_module
from agent_app.orchestration.service import CoreAdapters, CoreTurnService
from agent_app.persistent_api import create_app
from agent_app.testing.fakes import FakeReasoner, FakeRetriever
from agent_app.testing.http_pilot_runtime import offline_network
from agent_app.tracker.dummy_tracker import DummyTracker
from agent_app.tracker.sqlite_tracker import SQLiteCaseTracker

CASE = "case-cleanup"
TOKEN = "public-synthetic-cleanup-review-token"
REVIEWERS = {"fixture-maintainer": TOKEN}


def tracker(path):
    return SQLiteCaseTracker(path, reviewer_tokens=REVIEWERS)


def event():
    return UserTurn(
        case_id=CASE,
        expected_revision=0,
        turn_id="event-cleanup",
        source_ref="user:event-cleanup",
        message="The widget resets after rerun.",
    )


def ports(cleanup, *, supplier=None, retrieval=None, reasoner=None, snapshot=SNAPSHOT_ID):
    return CoreAdapters(
        FakeRetriever(
            retrieval
            if retrieval is not None
            else [_evidence("chunk:cleanup", "Authored source excerpt.")]
        ),
        reasoner or FakeReasoner([_answer("chunk:cleanup")]),
        snapshot,
        grounded_request_supplier=supplier,
        cleanup=cleanup,
    )


def test_supplier_consumed_before_cleanup_and_stage_only_after_cleanup(tmp_path):
    storage = tracker(tmp_path / "case.sqlite3")
    order = []

    def supplier():
        order.append("supplier")
        return None

    def cleanup():
        assert order == ["supplier"]
        order.append("cleanup")

    def stage(handoff, result, turn_id):
        assert order == ["supplier", "cleanup"]
        order.append("stage")
        return storage.stage_run_proposal(handoff, result, turn_id)

    with offline_network():
        outcome = CoreTurnService(
            storage, lambda *_: ports(cleanup, supplier=supplier), stage_with_result=stage
        ).submit(event())
    assert outcome.status == "proposal_staged"
    assert order == ["supplier", "cleanup", "stage"]
    assert storage.read_case(CASE)["pending_handoff"] == outcome.handoff.model_dump(mode="json")


@pytest.mark.parametrize(
    ("failure", "error"),
    [
        ("setup", "AdapterSetupFailed"),
        ("retrieval", "RetrievalUnavailable"),
        ("source", "UnknownEvidenceReference"),
        ("supplier", "InvalidHandoffInput"),
        ("engine", "CoreRunFailed"),
    ],
)
def test_failures_cleanup_once_without_staging_or_exposing_raw_error(
    tmp_path, monkeypatch, failure, error
):
    storage = tracker(tmp_path / "failure.sqlite3")
    calls = []

    def cleanup():
        calls.append("cleanup")

    def supplier():
        calls.append("supplier")
        if failure == "supplier":
            raise ValueError("private-supplier-error-input")
        return None

    def factory(*_args):
        calls.append("factory")
        return ports(
            cleanup,
            supplier=supplier,
            retrieval=[RuntimeError("private-retrieval-error-input")]
            if failure == "retrieval"
            else None,
            reasoner=FakeReasoner([_answer("chunk:missing")]) if failure == "source" else None,
            snapshot="" if failure == "setup" else SNAPSHOT_ID,
        )

    def stage(*_args):
        calls.append("stage")
        raise AssertionError("No failed run may stage")

    if failure == "engine":

        def run_failure(*_args, **_kwargs):
            raise ValueError("private-engine-error-input")

        monkeypatch.setattr(service_module.SupportEngine, "run", run_failure)
    with offline_network():
        outcome = CoreTurnService(storage, factory, stage_with_result=stage).submit(event())
    assert outcome.status == "core_stopped" and outcome.error_code == error
    assert calls.count("cleanup") == 1 and "stage" not in calls
    assert storage.read_case(CASE)["pending_handoff"] is None
    assert "private" not in outcome.error_code
    if outcome.run_result is not None:
        assert "private" not in outcome.run_result.model_dump_json()


def test_replay_does_not_allocate_ports_or_cleanup_again_even_after_tracker_recreation(tmp_path):
    path = tmp_path / "replay.sqlite3"
    storage = tracker(path)
    calls = []

    def factory(*_args):
        calls.append("factory")
        return ports(lambda: calls.append("cleanup"))

    with offline_network():
        first = CoreTurnService(
            storage, factory, stage_with_result=storage.stage_run_proposal
        ).submit(event(), run_id="run-original")
        assert first.status == "proposal_staged"
        fresh = tracker(path)
        repeated = CoreTurnService(
            fresh, factory, stage_with_result=fresh.stage_run_proposal
        ).submit(event(), run_id="run-would-create-another-attempt")
    assert repeated.status == "replay_only" and repeated.receipt.replayed
    assert calls == ["factory", "cleanup"]
    assert fresh.read_case(CASE)["pending_handoff"] == first.handoff.model_dump(mode="json")


def test_http_cleanup_failure_is_terminal_safe_and_survives_recreation_and_event_retry(tmp_path):
    path = tmp_path / "http.sqlite3"
    calls = []

    def cleanup():
        calls.append("cleanup")
        raise RuntimeError("private-cleanup-key-or-source-input")

    def adapters(_scenario):
        calls.append("factory")
        prepared = ports(cleanup)
        return api.RunAdapters(
            prepared.retriever, prepared.reasoner, prepared.snapshot_id, cleanup=prepared.cleanup
        )

    payload = {
        "message": event().message,
        "scenario": "answer",
        "turn_id": event().turn_id,
        "expected_revision": 0,
    }
    storage = tracker(path)
    with (
        offline_network(),
        TestClient(create_app(storage, reviewer_tokens=REVIEWERS, adapters=adapters)) as client,
    ):
        response = client.post(f"/cases/{CASE}/messages", json=payload)
        assert response.status_code == 200
        body = response.json()
        assert body["pending"] is None and body["actions"] == []
        assert body["run_outcome"]["status"] == "core_stopped"
        assert body["run_outcome"]["error_code"] == "AdapterCleanupFailed"
        assert body["run_outcome"]["result"]["model_attempts"] == 1
        assert "private" not in json.dumps(body)
    fresh = tracker(path)
    with (
        offline_network(),
        TestClient(create_app(fresh, reviewer_tokens=REVIEWERS, adapters=adapters)) as client,
    ):
        saved = client.get(f"/cases/{CASE}").json()
        repeated = client.post(f"/cases/{CASE}/messages", json=payload).json()
    assert saved["run_outcome"] == body["run_outcome"] == repeated["run_outcome"]
    assert repeated["intake"]["replayed"] and repeated["case_revision"] == 1
    assert calls == ["factory", "cleanup"]
    with fresh._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM proposals").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM local_comments").fetchone()[0] == 0


@pytest.mark.parametrize("interrupt", [KeyboardInterrupt, SystemExit])
@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_interrupted_engine_still_closes_resources_and_never_stages(
    tmp_path, interrupt, cleanup_fails
):
    storage = tracker(tmp_path / "interrupt.sqlite3")
    calls = []

    class InterruptedReasoner:
        def analyze(self, *_args, **_kwargs):
            raise interrupt("Fixture cancellation")

    def factory(*_args):
        calls.append("factory")
        return ports(cleanup, reasoner=InterruptedReasoner())

    def cleanup():
        calls.append("cleanup")
        if cleanup_fails:
            raise ValueError("Fixture cleanup failure must not swallow cancellation")

    with offline_network(), pytest.raises(interrupt):
        CoreTurnService(storage, factory, stage_with_result=storage.stage_run_proposal).submit(
            event()
        )
    assert calls == ["factory", "cleanup"]
    assert storage.read_case(CASE)["pending_handoff"] is None


def test_legacy_http_consumes_supplier_then_closes_before_proposing_and_replay_does_neither(
    monkeypatch,
):
    calls = []
    monkeypatch.setattr(api, "_cases", {})

    class OrderedTracker(DummyTracker):
        def pause_for_approval(self, case_id, proposal):
            assert calls == ["factory", "supplier", "cleanup"]
            calls.append("stage")
            return super().pause_for_approval(case_id, proposal)

    monkeypatch.setattr(api, "tracker", OrderedTracker())

    def supplier():
        calls.append("supplier")
        return None

    def adapters(_scenario):
        calls.append("factory")
        prepared = ports(lambda: calls.append("cleanup"), supplier=supplier)
        return api.RunAdapters(
            prepared.retriever,
            prepared.reasoner,
            prepared.snapshot_id,
            prepared.grounded_request_supplier,
            prepared.cleanup,
        )

    monkeypatch.setattr(api, "_adapters", adapters)
    payload = {
        "message": event().message,
        "scenario": "answer",
        "turn_id": event().turn_id,
        "expected_revision": 0,
    }
    with offline_network(), TestClient(api.app) as client:
        first = client.post(f"/cases/{CASE}/messages", json=payload)
        repeated = client.post(f"/cases/{CASE}/messages", json=payload)
    assert first.status_code == repeated.status_code == 200
    assert first.json()["pending"] == repeated.json()["pending"]
    assert first.json()["pending"] is not None and repeated.json()["intake"]["replayed"]
    assert calls == ["factory", "supplier", "cleanup", "stage"]


@pytest.mark.parametrize("failure", ["setup", "supplier", "cleanup", "source"])
def test_legacy_http_failed_runs_cleanup_once_and_never_propose(monkeypatch, failure):
    calls = []
    monkeypatch.setattr(api, "_cases", {})
    storage = DummyTracker()
    monkeypatch.setattr(api, "tracker", storage)

    def cleanup():
        calls.append("cleanup")
        if failure == "cleanup":
            raise RuntimeError("private-legacy-cleanup-error")

    def supplier():
        if failure == "supplier":
            raise RuntimeError("private-legacy-supplier-error")
        return None

    def adapters(_scenario):
        calls.append("factory")
        prepared = ports(
            cleanup,
            supplier=supplier,
            snapshot="" if failure == "setup" else SNAPSHOT_ID,
            reasoner=FakeReasoner([_answer("chunk:missing")]) if failure == "source" else None,
        )
        return api.RunAdapters(
            prepared.retriever,
            prepared.reasoner,
            prepared.snapshot_id,
            prepared.grounded_request_supplier,
            prepared.cleanup,
        )

    monkeypatch.setattr(api, "_adapters", adapters)
    payload = {
        "message": event().message,
        "scenario": "answer",
        "turn_id": event().turn_id,
        "expected_revision": 0,
    }
    with offline_network(), TestClient(api.app) as client:
        first = client.post(f"/cases/{CASE}/messages", json=payload)
        repeated = client.post(f"/cases/{CASE}/messages", json=payload)
    assert first.status_code == repeated.status_code == 200
    assert first.json()["pending"] is None and repeated.json()["pending"] is None
    assert "private" not in first.text
    assert storage.get_session_state(CASE)["proposed_action"] is None
    assert calls == ["factory", "cleanup"]
    if failure == "cleanup":
        assert "AdapterCleanupFailed" in first.text


def test_legacy_cancellation_closes_resources_before_propagating(monkeypatch):
    calls = []
    monkeypatch.setattr(api, "_cases", {})
    monkeypatch.setattr(api, "tracker", DummyTracker())

    class InterruptedReasoner:
        def analyze(self, *_args, **_kwargs):
            raise KeyboardInterrupt("Fixture cancellation")

    def adapters(_scenario):
        prepared = ports(lambda: calls.append("cleanup"), reasoner=InterruptedReasoner())
        return api.RunAdapters(
            prepared.retriever, prepared.reasoner, prepared.snapshot_id, cleanup=prepared.cleanup
        )

    monkeypatch.setattr(api, "_adapters", adapters)
    with offline_network(), pytest.raises(KeyboardInterrupt):
        api.post_message(
            CASE,
            api.MessageRequest(
                message=event().message,
                scenario="answer",
                turn_id=event().turn_id,
                expected_revision=0,
            ),
        )
    assert calls == ["cleanup"]
    assert api._view(CASE)["pending"] is None
