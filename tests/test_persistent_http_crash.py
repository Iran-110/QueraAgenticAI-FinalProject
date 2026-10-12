"""Actual process termination, lost acknowledgments and transactional local actions."""

import json
import os
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from agent_app import api
from agent_app.orchestration.service import CoreAdapters, CoreTurnService
from agent_app.persistent_api import create_app
from agent_app.testing.http_pilot_runtime import Observations, offline_network
from agent_app.tracker.sqlite_tracker import SQLiteCaseTracker

TOKEN = "synthetic-crash-test-reviewer-token"
REVIEWERS = {"fixture-maintainer": TOKEN}
HEADERS = {"Authorization": f"Bearer {TOKEN}"}
EVENT = {
    "turn_id": "crash-turn",
    "expected_revision": 0,
    "message": "A multiselect inside a fragment resets after a parent rerun.",
    "scenario": "ask_version",
}
CHILD = """
import json, os, sys
from fastapi.testclient import TestClient
from agent_app.persistent_api import create_app
from agent_app.testing.http_pilot_runtime import offline_network
from agent_app.tracker.sqlite_tracker import SQLiteCaseTracker
class CrashTracker(SQLiteCaseTracker):
    def apply_turn(self, *args, **kwargs):
        receipt = super().apply_turn(*args, **kwargs)
        if sys.argv[2] == "ingress" and not receipt["replayed"]:
            os._exit(73)
        return receipt
    def stage_run_proposal(self, *args, **kwargs):
        receipt = super().stage_run_proposal(*args, **kwargs)
        if sys.argv[2] == "stage":
            os._exit(74)
        return receipt
with offline_network():
    tracker = CrashTracker(sys.argv[1], reviewer_tokens={"fixture-maintainer": sys.argv[3]})
    with TestClient(create_app(tracker, reviewer_tokens={"fixture-maintainer": sys.argv[3]})) as client:
        client.post("/cases/crash-case/messages", json=json.loads(sys.stdin.read()))
raise AssertionError("Crash boundary was not reached")
"""


def review_payload(pending, *, review_id="stable-review"):
    return {
        "review_id": review_id,
        "proposal_id": pending["proposal_id"],
        "case_revision": pending["case_revision"],
        "decision": "approve",
        "expected_handoff_sha256": pending["review_handoff"]["handoff_sha256"],
    }


@pytest.mark.parametrize("boundary,exit_code", [("ingress", 73), ("stage", 74)])
def test_process_termination_after_commit_never_resumes_original_event(
    tmp_path, boundary, exit_code
):
    path = tmp_path / "crash.sqlite3"
    child = subprocess.Popen(
        [sys.executable, "-c", CHILD, str(path), boundary, TOKEN],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    stdout, stderr = child.communicate(json.dumps(EVENT), timeout=20)
    assert child.pid != os.getpid() and child.returncode == exit_code
    assert stdout == stderr == ""
    tracker = SQLiteCaseTracker(path, reviewer_tokens=REVIEWERS)
    obs = Observations()
    app = create_app(
        tracker,
        reviewer_tokens=REVIEWERS,
        adapters=lambda scenario: obs.wrap(api._adapters(scenario)),
    )
    with offline_network(), TestClient(app) as client:
        before = client.get("/cases/crash-case").json()
        assert before["case_revision"] == 1 and before["actions"] == []
        if boundary == "ingress":
            assert before["run_outcome"]["status"] == "interrupted"
            assert before["pending"] is None
        else:
            assert before["run_outcome"]["status"] == "proposal_staged"
            assert before["pending"]["model_attempts"] == 1
            assert before["pending"]["retrieval_rounds"] == 1
            assert before["pending"]["steps"] > 0
        replay = client.post("/cases/crash-case/messages", json=EVENT)
        assert replay.status_code == 200 and replay.json()["intake"]["replayed"]
        assert client.get("/cases/crash-case").json() == before
        assert obs.snapshot() == {"factory_calls": 0, "retrieval_calls": 0, "reasoning_calls": 0}
        if boundary == "stage":
            payload = review_payload(before["pending"])
            first = client.post("/cases/crash-case/decision", json=payload, headers=HEADERS).json()
            repeated = client.post(
                "/cases/crash-case/decision", json=payload, headers=HEADERS
            ).json()
            assert repeated["review"] == {**first["review"], "replayed": True}
            assert len(tracker.comments("crash-case")) == 1
            assert first["actions"] == repeated["actions"]


def test_local_action_failure_rolls_back_then_identical_http_retry_commits_once(
    tmp_path, monkeypatch
):
    tracker = SQLiteCaseTracker(tmp_path / "rollback.sqlite3", reviewer_tokens=REVIEWERS)
    app = create_app(tracker, reviewer_tokens=REVIEWERS)
    original = tracker._record_local_comment
    fail = True

    def write_then_fail(*args, **kwargs):
        action = original(*args, **kwargs)
        if fail:
            raise RuntimeError("PRIVATE_LOCAL_TOOL_DIAGNOSTIC")
        return action

    monkeypatch.setattr(tracker, "_record_local_comment", write_then_fail)
    with offline_network(), TestClient(app) as client:
        before = client.post("/cases/crash-case/messages", json=EVENT).json()
        payload = review_payload(before["pending"])
        refused = client.post("/cases/crash-case/decision", json=payload, headers=HEADERS)
        assert refused.status_code == 503 and refused.json() == {"detail": "TrackerUnavailable"}
        assert client.get("/cases/crash-case").json() == before
        assert tracker.comments("crash-case") == []
        fail = False
        approved = client.post("/cases/crash-case/decision", json=payload, headers=HEADERS).json()
        assert approved["review"]["replayed"] is False
        assert len(tracker.comments("crash-case")) == 1
        assert (
            client.post("/cases/crash-case/decision", json=payload, headers=HEADERS).json()[
                "review"
            ]["replayed"]
            is True
        )
        assert len(tracker.comments("crash-case")) == 1


def test_atomic_stage_lost_ack_recovers_measured_outcome_without_another_run(tmp_path):
    tracker = SQLiteCaseTracker(tmp_path / "stage-ack.sqlite3", reviewer_tokens=REVIEWERS)
    observations = Observations()

    def factory(_case, _message, _run_id):
        ports = observations.wrap(api._adapters("ask_version"))
        return CoreAdapters(ports.retriever, ports.reasoner, ports.snapshot_id)

    def write_then_lose_ack(handoff, result, turn_id):
        tracker.stage_run_proposal(handoff, result, turn_id)
        raise RuntimeError("PRIVATE_STAGE_ACK")

    service = CoreTurnService(tracker, factory, stage_with_result=write_then_lose_ack)
    turn = api.MessageRequest.model_validate(EVENT).user_turn("crash-case", 0)
    outcome = service.submit(turn, run_id="trusted-crash-run")
    assert outcome.status == "proposal_staged" and outcome.recovered_ack
    persisted = tracker.read_runtime_view("crash-case")
    assert persisted["pending_result"] == outcome.run_result.model_dump(mode="json")
    counts = observations.snapshot()
    assert service.submit(turn, run_id="must-not-run").status == "replay_only"
    assert observations.snapshot() == counts
