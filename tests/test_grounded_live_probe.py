"""Bounded paid-probe controls with a disposable ledger and mock wire only."""

import gzip
import importlib.util
import json
import sqlite3
import sys
import zlib
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from agent_app.llm.budget import BudgetLedger
from agent_app.llm.config import MetisConfig
from agent_app.orchestration.ports import ReasoningStopped
from agent_app.testing.http_pilot_runtime import offline_network

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "grounded_live_probe", ROOT / "scripts/grounded_live_probe.py"
)
PROBE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROBE)


@pytest.fixture
def ledger(tmp_path):
    # Reproduce only the grant guards, never open/copy the team's real ledger.
    path = tmp_path / "disposable-budget.sqlite3"
    ledger = BudgetLedger.create(path, limit_usd=Decimal("4.5"), opening_spend_usd=Decimal("0"))
    ledger.reserve(
        request_id="call:old-mismatch",
        run_id="run:old",
        case_id="case:old",
        case_revision=1,
        attempt=1,
        model="gpt-4.1-mini",
        phase="development",
        amount_usd=Decimal("0.008"),
    )
    ledger.mark_uncertain("call:old-mismatch", error_code="ProviderModelMismatch")
    ledger.halt()
    ledger.authorize_continuation(
        authorization_id=PROBE.GRANT,
        authorization_ref="test:explicit-authorization",
        expected_request_id="call:old-mismatch",
        held_usd=Decimal("0.02"),
        additional_cap_usd=Decimal("0.1"),
    )
    return path, ledger


def config():
    return MetisConfig(
        api_key="public-synthetic-live-probe-test-key",
        live_enabled=True,
        model=PROBE.MODEL,
        phase="development",
        response_mode="grounded_plan",
        continuation_id=PROBE.GRANT,
        input_token_reserve=PROBE.INPUT_RESERVE,
        max_output_tokens=PROBE.OUTPUT_LIMIT,
        max_request_usd=PROBE.REQUEST_BOUND,
    )


def fixture():
    return json.loads((ROOT / PROBE.FIXTURE).read_bytes())


def response(request, *, malformed=False, model="gpt-4o-mini-2024-07-18"):
    payload = json.loads(request.content)
    model_input = json.loads(payload["messages"][1]["content"])["request"]
    content = (
        "{broken"
        if malformed
        else json.dumps(
            {
                "context_sha256": model_input["context_sha256"],
                "decision": "ask",
                "question_name": "streamlit_version",
            }
        )
    )
    return httpx.Response(
        200,
        json={
            "model": model,
            "usage": {"prompt_tokens": 125, "completion_tokens": 75, "total_tokens": 200},
            "choices": [
                {"finish_reason": "stop", "message": {"role": "assistant", "content": content}}
            ],
        },
    )


def execute(tmp_path, ledger, respond, *, data=None):
    path, _ledger = ledger
    before = PROBE.ledger_observation(path)
    state = tmp_path / "private-state"
    state.mkdir()
    with offline_network():
        return PROBE.run_probe(
            data or fixture(),
            ledger_path=path,
            state_dir=state,
            config=config(),
            before=before,
            underlying=httpx.MockTransport(respond),
        )


def test_live_shape_runs_entire_real_http_path_but_keeps_review_pending(tmp_path, ledger):
    receipt = execute(tmp_path, ledger, response)
    assert receipt["accepted_operations"] is True
    assert receipt["actual_sends"] == 1
    assert receipt["canonical_pending_handoff"]["analysis"]["decision"] == "ask"
    assert receipt["proposal_auto_approved"] is False
    assert (
        receipt["provider_observations"][0]["verified_returned_model"] == "gpt-4o-mini-2024-07-18"
    )
    assert receipt["new_cost_estimated_usd"] == "0.000070125"
    assert receipt["actual_account_charge_usd"] is None
    assert receipt["ledger_after"]["halted"] is True
    assert receipt["ledger_after"]["uncertain_usd"] == "0.02"
    serialized = json.dumps(receipt)
    assert "public-synthetic-live-probe-test-key" not in serialized
    assert "Authorization" not in serialized and "provider_payload" not in serialized
    assert receipt["quality_claim"] is False and receipt["heldout_claim"] is False


def test_repair_consumes_second_send_and_same_original_run(tmp_path, ledger):
    seen = []

    def respond(request):
        seen.append(1)
        return response(request, malformed=len(seen) == 1)

    receipt = execute(tmp_path, ledger, respond)
    assert receipt["accepted_operations"] is True and receipt["actual_sends"] == 2
    assert [item["attempt_index"] for item in receipt["reasoning_attempts"]] == [1, 2]
    assert len({item["run_id"] for item in receipt["reasoning_attempts"]}) == 1
    assert Decimal(receipt["new_cost_estimated_usd"]) == Decimal("0.000140250")
    assert len(seen) == 2


@pytest.mark.parametrize("encoding,compress", [("gzip", gzip.compress), ("deflate", zlib.compress)])
def test_compressed_envelope_retains_verified_id_without_double_decoding_or_headers(
    tmp_path, ledger, encoding, compress
):
    response_streams = []

    class ChunkedStream(httpx.SyncByteStream):
        def __init__(self, body):
            self.body, self.closed = body, False

        def __iter__(self):
            for index in range(0, len(self.body), 17):
                yield self.body[index : index + 17]

        def close(self):
            self.closed = True

    def respond(request):
        raw = response(request).content
        wire = compress(raw)
        stream = ChunkedStream(wire)
        response_streams.append(stream)
        return httpx.Response(
            200,
            headers={
                "Content-Encoding": encoding,
                "Content-Length": str(len(wire)),
                "Private-Provider-Header": "private-response-header-must-not-escape",
            },
            stream=stream,
            request=request,
        )

    receipt = execute(tmp_path, ledger, respond)
    assert receipt["accepted_operations"] is True and receipt["actual_sends"] == 1
    assert (
        receipt["provider_observations"][0]["verified_returned_model"] == "gpt-4o-mini-2024-07-18"
    )
    assert receipt["provider_observations"][0]["reservation"]["status"] == "settled"
    assert receipt["canonical_pending_handoff"]["analysis"]["decision"] == "ask"
    assert all(stream.closed for stream in response_streams)
    serialized = json.dumps(receipt)
    assert "private-response-header-must-not-escape" not in serialized
    assert "Private-Provider-Header" not in serialized


def test_model_mismatch_stops_and_retains_both_uncertain_records(tmp_path, ledger):
    receipt = execute(tmp_path, ledger, lambda request: response(request, model="unverified-model"))
    assert receipt["actual_sends"] == 1
    assert receipt["canonical_pending_handoff"] is None
    assert receipt["accepted_operations"] is False
    assert receipt["ledger_after"]["counts"]["uncertain"] == 2
    assert receipt["ledger_after"]["halted"] is True
    assert receipt["ledger_after"]["continuation"]["active"] is False
    assert receipt["provider_observations"][0]["verified_returned_model"] is None
    assert "unverified-model" not in json.dumps(receipt)
    assert ledger[1].get("call:old-mismatch").status == "uncertain"


def test_large_prompt_fails_before_any_reservation_or_send(tmp_path, ledger):
    data = fixture()
    data["evidence_bundles"]["official-mixed"]["hits"][0]["excerpt"] = "x" * 19000

    def forbidden(_request):
        raise AssertionError("Provider must not be contacted")

    before = ledger[1].snapshot()
    receipt = execute(tmp_path, ledger, forbidden, data=data)
    assert receipt["actual_sends"] == 0 and receipt["accepted_operations"] is False
    assert ledger[1].snapshot() == before
    assert receipt["canonical_pending_handoff"] is None


def test_read_only_audit_preserves_database_and_missing_path_is_never_created(tmp_path, ledger):
    path, _ledger = ledger
    before = path.read_bytes()
    observation = PROBE.ledger_observation(path)
    assert path.read_bytes() == before
    assert observation["counts"] == {"uncertain": 1}
    missing = tmp_path / "missing.sqlite3"
    with pytest.raises(sqlite3.OperationalError):
        PROBE.ledger_observation(missing)
    assert not missing.exists()


def test_http_failure_after_paid_shape_send_still_returns_cost_and_closed_receipt(
    tmp_path, ledger, monkeypatch
):
    original = PROBE.TestClient.post

    def failed_decision(self, url, **kwargs):
        if url.endswith("/decision"):
            raise RuntimeError("Private error content must not escape")
        return original(self, url, **kwargs)

    monkeypatch.setattr(PROBE.TestClient, "post", failed_decision)
    receipt = execute(tmp_path, ledger, response)
    assert receipt["accepted_operations"] is False
    assert receipt["checks"]["persistent_http_path_completed"] is False
    assert receipt["actual_sends"] == 1
    assert receipt["new_cost_estimated_usd"] == "0.000070125"
    assert receipt["checks"]["gateway_closed"] is True
    assert receipt["ledger_after"]["halted"] is True
    assert "Private error content" not in json.dumps(receipt)


def test_transport_third_send_guard_never_delegates_or_changes_ledger(ledger):
    path, live_shape_ledger = ledger
    before = PROBE.ledger_observation(path)

    def forbidden(_request):
        raise AssertionError("Third send must not be delegated")

    counted = PROBE.CountedTransport(httpx.MockTransport(forbidden), live_shape_ledger, before)
    counted.records = [{"request_id": "prior:1"}, {"request_id": "prior:2"}]
    with pytest.raises(ReasoningStopped) as error:
        counted.handle_request(httpx.Request("POST", PROBE.METIS_CHAT_URL))
    assert error.value.code == "BudgetExceeded"
    assert PROBE.ledger_observation(path) == before
    counted.close()


def test_default_cli_does_not_read_credentials_or_construct_transport(monkeypatch, capsys):
    monkeypatch.setattr(PROBE, "load_registration", lambda *_args: ({}, {}, {}))
    monkeypatch.setattr(sys, "argv", ["grounded_live_probe.py", "--env-file", "private.env"])

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Default CLI is read-only; no key or provider")

    monkeypatch.setattr(PROBE, "_credential", forbidden)
    monkeypatch.setattr(httpx.HTTPTransport, "__init__", forbidden)
    PROBE.main()
    assert json.loads(capsys.readouterr().out)["paid_requests"] == 0


def test_explicit_live_without_required_paths_stops_before_key(monkeypatch, capsys):
    monkeypatch.setattr(PROBE, "load_registration", lambda *_args: ({}, {}, {}))
    monkeypatch.setattr(sys, "argv", ["grounded_live_probe.py", "--live"])

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Invalid live configuration cannot read a key")

    monkeypatch.setattr(PROBE, "_credential", forbidden)
    with pytest.raises(SystemExit) as error:
        PROBE.main()
    assert error.value.code == 1
    assert json.loads(capsys.readouterr().out)["code"] == "GroundedLiveProbeRejected"
