import importlib.util
import json
import os
from copy import deepcopy

import httpx
import pytest

from agent_app.testing import http_pilot_acceptance as kit
from agent_app.testing.http_pilot_runtime import Observations


@pytest.fixture
def cli():
    spec = importlib.util.spec_from_file_location(
        "http_acceptance_cli", kit.ROOT / "scripts/http_pilot_acceptance.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def receipt():
    return kit.run_acceptance()


def test_current_memory_api_is_rejected_for_actual_restart(receipt):
    assert receipt["accepted"] is False
    assert receipt["restart_accepted"] is False
    assert receipt["tracker_backend"] == "process_memory_dummy_tracker"
    assert len(receipt["checkpoints"]) == 4
    for checkpoint in receipt["checkpoints"]:
        assert checkpoint["restarted_pid"] != os.getpid()
        assert checkpoint["after_restart"]["case_revision"] == 0
        assert checkpoint["after_restart"]["released_count"] == 0
        assert checkpoint["port_counts_after_restart"] == {
            "factory_calls": 1,
            "retrieval_calls": 1,
            "reasoning_calls": 1,
        }
    assert not receipt["checks"]["restart4:retry5:accepted_as_replay"]
    assert not receipt["checks"]["restart4:retry5:no_new_ports"]


def test_same_process_pilot_preserves_original_problem_on_bare_version_reply(receipt):
    assert receipt["checks"]["context:short_reply_retains_original_problem"]
    assert receipt["checks"]["context:short_reply_retains_current_reply"]
    assert receipt["checks"]["context:no_future_correction_in_short_reply"]
    assert receipt["same_process_accepted"]


def test_correction_and_exact_retries_are_stronger_than_json_validity(receipt):
    checks = receipt["checks"]
    assert checks["correction:only_corrected_version_active"]
    assert checks["correction:old_version_superseded"]
    assert checks["correction:old_checks_invalidated"]
    assert checks["correction:old_evidence_refs_cleared"]
    for event in range(1, 5):
        for name in (
            "accepted_as_replay",
            "whole_view_unchanged",
            "no_new_ports",
            "original_receipt",
        ):
            assert checks[f"same_process:p1-turn-{event}:{name}"]
    assert checks["same_process:conflicting_event_refused"]
    assert checks["same_process:approved_review_retry_safe"]
    assert checks["same_process:released_exactly_two_outputs"]
    assert receipt["quality_claim"] is False and receipt["held_out_test"] is False
    assert receipt["api_cost_usd"] == 0 and receipt["production_ledger_used"] is False


def test_interrupted_committed_input_never_automatically_resumes(receipt):
    checks = receipt["checks"]
    assert checks["interrupted:ingress_committed_without_proposal"]
    assert checks["interrupted:stopped_without_reasoning_or_retrieval"]
    assert checks["interrupted:same_process_retry:no_new_ports"]
    assert not checks["interrupted:restart_preserves_stopped_ingress"]
    assert not checks["interrupted:restart_retry:no_new_ports"]
    assert receipt["interrupted"]["port_counts_after_restart"] == {
        "factory_calls": 1,
        "retrieval_calls": 0,
        "reasoning_calls": 0,
    }


class MutantClient:
    def __init__(self, obs, *, mutate_on_refusal=False, silent_reasoning=False):
        self.obs = obs
        self.mutate = mutate_on_refusal
        self.silent = silent_reasoning
        self.view = {"case_revision": 4, "pending": None, "log": [], "intake": None, "facts": []}

    def get(self, _path):
        return httpx.Response(200, json=deepcopy(self.view))

    def post(self, _path, *, json):
        if self.mutate:
            self.view["facts"] = [{"name": "forged", "value": "mutated while refusing"}]
            return httpx.Response(409, json={"detail": "StaleRevision"})
        if self.silent:
            self.obs.reasoning_calls += 1
        return httpx.Response(200, json={**deepcopy(self.view), "intake": {"replayed": True}})


def test_refusal_cannot_mutate_an_unchecked_fact_while_revision_and_log_match():
    obs, checks = Observations(), kit.Checks()
    client = kit.ObservedClient(MutantClient(obs, mutate_on_refusal=True), obs, checks)
    assert client.post("/cases/dev/decision", json={"decision": "approve"}).status_code == 409
    assert checks.values["http:0:refusal_preserves_whole_view"] is False
    assert checks.values["http:0:refusal_no_ports"] is True


def test_replay_with_identical_view_cannot_silently_call_reasoning():
    obs, checks = Observations(), kit.Checks()
    client = kit.ObservedClient(MutantClient(obs, silent_reasoning=True), obs, checks)
    client.post("/cases/dev/messages", json={"turn_id": "same"})
    assert checks.values["http:0:replay_preserves_whole_view"] is True
    assert checks.values["http:0:replay_no_ports"] is False


@pytest.mark.parametrize("changed", [{"committed_revision": 4}, {"invalidated_checks": []}])
def test_replayed_flag_cannot_hide_wrong_original_receipt(changed):
    checks = kit.Checks()
    original = {
        "turn_id": "first",
        "ingress_hash": "a",
        "prepared_hash": "b",
        "committed_revision": 1,
        "preparation": "structured",
        "invalidated_checks": ["old check"],
    }
    response = {
        "status_code": 200,
        "body": {"intake": {**original, "replayed": True, **changed}},
        "counts_before": {},
        "counts_after": {},
    }
    kit._replay_checks(
        checks, "mutant", response, original, {"case_revision": 4}, {"case_revision": 4}
    )
    assert checks.values["mutant:accepted_as_replay"]
    assert checks.values["mutant:original_receipt"] is False


def test_successful_review_cannot_silently_call_reasoning():
    obs, checks = Observations(), kit.Checks()
    client = kit.ObservedClient(MutantClient(obs, silent_reasoning=True), obs, checks)
    client.post("/cases/dev/decision", json={"decision": "approve"})
    assert checks.values["http:0:review_no_ports"] is False


def test_restart_review_cannot_hide_ports_behind_matching_view():
    checks = kit.Checks()
    kit._read_review_checks(
        checks,
        "mutant",
        [{"method": "POST", "path": "/cases/dev/decision"}],
        [{"counts_before": {"reasoning_calls": 0}, "counts_after": {"reasoning_calls": 1}}],
    )
    assert checks.values["mutant:request0:read_or_review_no_ports"] is False


def test_worker_empty_or_failed_output_cannot_be_counted_as_restart(monkeypatch):
    class Result:
        stdout = json.dumps({"pid": os.getpid() + 1, "responses": [], "error_code": None})

    monkeypatch.setattr(kit.subprocess, "run", lambda *a, **kw: Result())
    with pytest.raises(ValueError, match="HTTPRestartWorkerFailed"):
        kit.restart_worker({"requests": [{"method": "GET"}]})


def test_protocol_refuses_a_changed_fixture_before_calling_a_factory(monkeypatch):
    fixture = kit.runner.load_fixture(kit.ROOT / "data/evaluation/dev/pilot-12782.json")
    fixture.sha256 = "0" * 64
    monkeypatch.setattr(kit.runner, "load_fixture", lambda _: fixture)
    with pytest.raises(ValueError, match="HTTPFixtureChanged"):
        kit.run_acceptance()


def test_cli_output_is_exclusive_and_raw_factory_errors_are_private(tmp_path, capsys, cli):
    output = tmp_path / "receipt.json"
    assert cli.main(["--factory", "missing.private:factory", "--output", str(output)]) == 1
    assert "missing.private" not in output.read_text()
    assert "missing.private" not in capsys.readouterr().out
    first = output.read_bytes()
    assert cli.main(["--output", str(output)]) == 1
    assert output.read_bytes() == first


def test_expected_gap_flag_cannot_mask_same_process_or_startup_failure(tmp_path, monkeypatch, cli):
    import agent_app.testing.http_pilot_acceptance as module

    monkeypatch.setattr(
        module,
        "run_acceptance",
        lambda _: {
            "accepted": False,
            "same_process_accepted": False,
            "restart_accepted": False,
            "tracker_backend": "process_memory_dummy_tracker",
        },
    )
    output = tmp_path / "bad.json"
    assert cli.main(["--expect-memory-gap", "--output", str(output)]) == 1
    assert json.loads(output.read_text())["expected_memory_gap_reproduced"] is False


def test_expected_gap_is_a_negative_control_not_acceptance(tmp_path, monkeypatch, cli):
    monkeypatch.setattr(
        kit,
        "run_acceptance",
        lambda _: {
            "accepted": False,
            "same_process_accepted": True,
            "restart_accepted": False,
            "tracker_backend": "process_memory_dummy_tracker",
        },
    )
    output = tmp_path / "gap.json"
    assert cli.main(["--expect-memory-gap", "--output", str(output)]) == 0
    r = json.loads(output.read_text())
    assert r["accepted"] is False
    assert r["expected_memory_gap_reproduced"] is True
