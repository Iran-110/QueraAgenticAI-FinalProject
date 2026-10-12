"""Durable review envelopes preserve original authority without touching fixture/gold."""

import json
import os
from copy import deepcopy

import httpx
import pytest

from agent_app import api
from agent_app.testing import http_pilot_acceptance as kit
from agent_app.testing.http_pilot_runtime import HTTPRuntime, Observations
from agent_app.testing.http_pilot_worker import run as worker_run


@pytest.fixture(scope="module")
def durable_receipt():
    return kit.run_acceptance(kit.SQLITE_FACTORY, protocol_path=kit.PROTOCOL_V2)


def test_registered_pilot_passes_after_actual_sqlite_process_restart(durable_receipt):
    result = durable_receipt
    assert result["accepted"] is True
    assert result["same_process_accepted"] is True and result["restart_accepted"] is True
    assert result["checks_passed"] == result["checks_total"]
    assert result["tracker_backend"] == "sqlite_case_tracker"
    assert len(result["checkpoints"]) == 4
    for checkpoint in result["checkpoints"]:
        assert checkpoint["restarted_pid"] != os.getpid()
        assert checkpoint["before"] == checkpoint["after_restart"]
        assert checkpoint["durable_review"] is True
    assert result["interrupted"]["restarted_pid"] != os.getpid()
    assert result["interrupted"]["before"] == result["interrupted"]["after_restart"]
    assert result["api_cost_usd"] == 0 and result["quality_claim"] is False
    assert result["production_ledger_used"] is False


def test_durable_acceptance_requires_auth_exact_receipts_and_actual_actions(durable_receipt):
    checks = durable_receipt["checks"]
    for name in (
        "durable:required_review_binding",
        "durable:auth_missing_refused",
        "durable:auth_wrong_refused",
        "durable:wrong_handoff_digest_refused",
        "durable:same_process_exact_review_receipt",
        "durable:altered_review_identity_refused",
        "durable:exactly_two_local_actions",
        "durable:unique_action_ids",
        "durable:released_text_matches_local_actions",
        "restart2:pending_review_exact_retry_receipt",
    ):
        assert checks[name], name
    for index in range(1, 5):
        assert checks[f"durable:prefix{index}:actual_sqlite_actions"]
        assert checks[f"restart{index}:actual_database_actions_match_projection"]
    output = json.dumps(durable_receipt)
    assert "offline-http-pilot-synthetic-reviewer-token" not in output
    assert "Authorization" not in output


def proposal(digest="a" * 64):
    return {
        "proposal_id": "original-proposal",
        "case_revision": 2,
        "decision": "answer",
        "review_handoff": {"handoff_sha256": digest},
    }


class RecordedClient:
    def __init__(self):
        self.view = {"pending": proposal(), "intake": None, "log": []}
        self.requests = []

    def get(self, _path):
        return httpx.Response(200, json=deepcopy(self.view))

    def post(self, path, *, json, headers=None):
        self.requests.append((path, deepcopy(json), deepcopy(headers)))
        return httpx.Response(409, json={"detail": "StaleRevision"})


def observed(raw):
    runtime = HTTPRuntime(
        api.app,
        "sqlite_case_tracker",
        durable_review=True,
        review_headers={"Authorization": "Bearer synthetic-private-marker"},
    )
    return kit.ObservedClient(raw, Observations(), kit.Checks(), runtime=runtime)


def test_old_proposal_digest_is_never_rebuilt_from_current_display():
    raw = RecordedClient()
    client = observed(raw)
    client.get("/cases/dev")
    raw.view["pending"] = proposal("b" * 64)
    client.get("/cases/dev")
    client.post("/cases/dev/decision", json=kit._review(proposal()))
    assert raw.requests[-1][1]["expected_handoff_sha256"] == "a" * 64


def test_independent_review_probes_receive_distinct_review_ids():
    raw = RecordedClient()
    client = observed(raw)
    for _ in range(2):
        client.post("/cases/dev/decision", json=kit._review(proposal()))
    assert raw.requests[0][1]["review_id"] != raw.requests[1][1]["review_id"]
    assert (
        raw.requests[0][1]["expected_handoff_sha256"]
        == raw.requests[1][1]["expected_handoff_sha256"]
    )


def test_exact_review_retry_keeps_all_fields_and_headers_stay_private():
    raw = RecordedClient()
    client = observed(raw)
    original = kit._durable_review(proposal(), "original-review")
    client.post("/cases/dev/decision", json=original)
    client.post("/cases/dev/decision", json=original)
    assert raw.requests[0][1] == raw.requests[1][1] == original
    assert raw.requests[0][2]["Authorization"] == "Bearer synthetic-private-marker"
    assert "synthetic-private-marker" not in json.dumps(client.trace)
    assert "synthetic-private-marker" not in json.dumps(client.review_requests)
    assert "synthetic-private-marker" not in repr(client.runtime)


def test_missing_auth_probe_really_omits_the_trusted_header():
    raw = RecordedClient()
    client = observed(raw)
    client.post("/cases/dev/decision", json=kit._review(proposal()), headers={})
    assert raw.requests[-1][2] is None


def test_unknown_original_proposal_cannot_borrow_the_current_digest():
    client = observed(RecordedClient())
    request = {**kit._review(proposal()), "proposal_id": "never-observed"}
    with pytest.raises(KeyError):
        client.post("/cases/dev/decision", json=request)


def test_v2_worker_rejects_wrong_protocol_hash_before_loading_sqlite(tmp_path):
    data = json.loads(kit.PROTOCOL_V2.read_text())
    result = worker_run(
        {
            "factory": kit.SQLITE_FACTORY,
            "fixture": str(kit.ROOT / data["fixture"]),
            "state_dir": str(tmp_path),
            "protocol": str(kit.PROTOCOL_V2),
            "protocol_sha256": "0" * 64,
            "requests": [{"method": "GET", "path": "/health"}],
        }
    )
    assert result["error_code"] == "WorkerFailed"
    assert result["tracker_backend"] == "not_started"
    assert result["responses"] == []
    assert not list(tmp_path.iterdir())


def test_unregistered_protocol_is_not_executed(tmp_path):
    path = tmp_path / "protocol-v2.json"
    path.write_bytes(kit.PROTOCOL_V2.read_bytes())
    with pytest.raises(ValueError, match="HTTPProtocolUnregistered"):
        kit.run_acceptance(kit.SQLITE_FACTORY, protocol_path=path)


def test_v2_weak_runtime_cannot_pass_by_omitting_durable_checks(monkeypatch):
    def weak_probe(_fixture, _factory, _state_dir, length, checks, _protocol):
        checks.check(f"weak:{length}", True)
        return {"tracker_backend": "sqlite_case_tracker", "durable_review": False}

    monkeypatch.setattr(kit, "_restart_probe", weak_probe)
    monkeypatch.setattr(kit, "_interrupted_probe", lambda *_args: {})
    result = kit.run_acceptance(kit.SQLITE_FACTORY, protocol_path=kit.PROTOCOL_V2)
    assert result["checks"]["durable:required_review_binding"] is False
    assert result["accepted"] is False


def test_replayed_flag_cannot_hide_changed_durable_review_action():
    original = {
        "review_id": "first",
        "proposal_id": "proposal",
        "action_id": "action",
        "replayed": False,
    }
    exact = {"review": {**original, "replayed": True}}
    mutant = {"review": {**original, "action_id": "second-action", "replayed": True}}
    assert kit._exact_review_receipt(exact, original)
    assert not kit._exact_review_receipt(mutant, original)


def test_ambiguous_server_error_does_not_claim_a_rolled_back_refusal():
    class LostAck(RecordedClient):
        def post(self, _path, *, json, headers=None):
            self.view["committed"] = True
            return httpx.Response(503, json={"detail": "RunOutcomeUnavailable"})

    client = observed(LostAck())
    result = client.post("/cases/dev/decision", json=kit._review(proposal()))
    assert result.status_code == 503
    assert not any("refusal_preserves" in key for key in client.checks.values)
