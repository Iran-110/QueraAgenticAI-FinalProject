"""The actual gateway wire, accounting and core handoff compose without live I/O."""

import importlib.util
import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from agent_app import api
from agent_app.contracts import GroundedRequest, ReasoningContext
from agent_app.llm import metis
from agent_app.llm.budget import BudgetLedger
from agent_app.llm.config import MetisConfig

REPLAY_PATH = Path(__file__).resolve().parents[1] / "experiments/gateway_handoff/replay.py"
SPEC = importlib.util.spec_from_file_location("gateway_handoff_pilot", REPLAY_PATH)
assert SPEC is not None and SPEC.loader is not None
replay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(replay)


@pytest.fixture(scope="module")
def receipt():
    return replay.replay_gateway()


def test_actual_wire_uses_current_case_latest_sources_and_bound_catalog(receipt):
    primary = receipt["primary_C3_receipt"]
    attempts = receipt["primary_provider_attempts"]
    assert receipt["summary"] == {
        "primary_gateway_requests": 7,
        "control_gateway_requests": 4,
        "actual_paid_requests": 0,
        "actual_API_cost_USD": "0",
        "real_model_calls": 0,
        "primary_simulated_settled_USD": "0.000490875",
    }
    assert primary["summary"]["event_replays_without_additional_calls"] == 4
    assert len(attempts) == 7
    # Five HTTP reasoning attempts, including one correction/refinement, then
    # two attempts in the separately disclosed conflict-routing control.
    assert [item["context"]["case_revision"] for item in attempts] == [1, 2, 3, 3, 4, 0, 0]
    for index, turn in zip((0, 1, 3, 4), primary["turns"], strict=True):
        sent = json.loads(attempts[index]["provider_payload"]["messages"][1]["content"])
        assert (
            GroundedRequest.model_validate(sent["request"]).model_dump(mode="json")
            == (turn["handoff"]["grounded_request"])
        )
    before, after = [
        json.loads(attempts[index]["provider_payload"]["messages"][1]["content"])["request"]
        for index in (2, 3)
    ]
    assert before["case"] == after["case"]
    assert after["evidence"]["retrieval_round"] == 2
    assert [len(item["evidence"]["hits"]) for item in (before, after)] == [5, 4]
    assert before["context_sha256"] != after["context_sha256"]
    assert "release-150-multiselect-key-identity-v8" not in {
        hit["chunk_id"] for hit in after["evidence"]["hits"]
    }
    assert primary["turns"][1]["handoff"]["analysis"]["decision"] == "answer"
    assert primary["turns"][2]["handoff"]["analysis"]["decision"] == "escalate"
    assert receipt["all_clients_closed"]


def test_real_attempt_ids_reserve_before_transport_and_settle_mock_usage(receipt):
    accounting = receipt["primary_simulated_accounting"]
    assert accounting["settled_reservations"] == 7
    assert accounting["reserved_reservations"] == accounting["uncertain_reservations"] == 0
    assert not accounting["ledger"]["halted"]
    ids = set()
    for item in receipt["primary_provider_attempts"]:
        context = ReasoningContext.model_validate(item["context"])
        assert item["request_id"] == metis.request_id_for(context)
        ids.add(item["request_id"])
        reserved, settled = item["reservation_before_response"], item["reservation_after_attempt"]
        assert reserved["status"] == "reserved" and settled["status"] == "settled"
        assert reserved["request_id"] == settled["request_id"] == item["request_id"]
        assert (settled["input_tokens"], settled["output_tokens"]) == (125, 75)
        assert Decimal(settled["cost_usd"]) == Decimal("0.000070125")
    assert len(ids) == 7


def test_accounted_mock_repair_feedback_stays_in_same_run_and_uses_next_attempt(receipt):
    repaired = receipt["controls"][0]
    first, second = repaired["provider_attempts"]
    assert repaired["control_id"] == "malformed_plan_repair"
    assert repaired["result"]["model_attempts"] == 2
    assert repaired["handoff"]["analysis"] == (
        replay.c3.load_expected_analyses()["handoff-1"].model_dump(mode="json")
    )
    assert first["context"]["run_id"] == second["context"]["run_id"]
    assert first["request_id"] != second["request_id"]
    assert [item["context"]["attempt_index"] for item in (first, second)] == [1, 2]
    assert first["context"]["output_feedback"] is None
    sent = json.loads(second["provider_payload"]["messages"][1]["content"])
    assert sent["repair_issue_codes"] == ["invalid_grounded_plan"]
    assert sent["capacity"]["remaining_model_attempts"] == 0
    assert repaired["simulated_accounting"]["settled_reservations"] == 2
    assert Decimal(repaired["simulated_accounting"]["ledger"]["settled_usd"]) == Decimal(
        "0.000140250"
    )


@pytest.mark.parametrize(
    ("index", "code", "halted"),
    [(1, "ProviderModelMismatch", True), (2, "ProviderRequestFailed", False)],
)
def test_terminal_mock_failures_keep_uncertainty_without_second_send(receipt, index, code, halted):
    control = receipt["controls"][index]
    accounting = control["simulated_accounting"]
    assert control["handoff"] is None and control["result"]["analysis"] is None
    assert control["result"]["error_code"] == code and control["result"]["model_attempts"] == 1
    assert accounting["transport_calls"] == accounting["uncertain_reservations"] == 1
    assert accounting["settled_reservations"] == accounting["reserved_reservations"] == 0
    assert Decimal(accounting["ledger"]["uncertain_usd"]) == Decimal("0.006082560")
    assert accounting["ledger"]["halted"] is halted
    assert Decimal(accounting["ledger"]["settled_usd"]) == 0


def test_expected_labels_oracle_and_auth_headers_never_enter_emitted_messages(receipt):
    attempts = receipt["primary_provider_attempts"] + [
        item for control in receipt["controls"] for item in control["provider_attempts"]
    ]
    for item in attempts:
        payload = item["provider_payload"]
        assert set(payload) == {"model", "messages", "max_tokens", "stream"}
        assert not payload["stream"] and payload["model"] == "gpt-4o-mini"
        assert set(json.loads(payload["messages"][1]["content"])) == {
            "capacity",
            "repair_issue_codes",
            "request",
            "response_schema",
            "source_references",
        }
        serialized = json.dumps(payload)
        for forbidden in (
            "authored_plan_sequence",
            "acceptable_decisions",
            "expected-analysis-v1.json",
            "introduced_after_original_C3_first_replay",
            "public-synthetic-gateway-handoff-key",
        ):
            assert forbidden not in serialized
        assert not any("header" in key.lower() or "authorization" in key.lower() for key in item)
    assert "public-synthetic-gateway-handoff-key" not in json.dumps(receipt)


def test_transport_environment_and_real_ledger_are_unavailable_and_state_restored(
    monkeypatch, receipt
):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Live I/O is forbidden in this pilot")

    paths, create = [], BudgetLedger.create

    def isolated_create(path, *args, **kwargs):
        path = Path(path)
        assert path.parent.name.startswith("offline-gateway-handoff-")
        paths.append(path)
        return create(path, *args, **kwargs)

    monkeypatch.setattr(httpx.HTTPTransport, "__init__", forbidden)
    monkeypatch.setattr(MetisConfig, "from_env", forbidden)
    monkeypatch.setattr(BudgetLedger, "create", isolated_create)
    old = (api._cases, api.tracker, api._adapters, replay.c3.GroundedReasoner)
    assert replay.replay_gateway() == receipt
    assert (api._cases, api.tracker, api._adapters, replay.c3.GroundedReasoner) == old
    assert len(paths) == 4 and all(not path.exists() for path in paths)


def test_wire_substitution_cannot_receive_success_receipt(monkeypatch):
    original = metis.build_grounded_messages

    def substituted(request, context):
        messages = list(original(request, context))
        data = json.loads(messages[1]["content"])
        data["request"]["user_message"] += " Changed on the wire."
        messages[1] = {**messages[1], "content": json.dumps(data)}
        return messages

    monkeypatch.setattr(metis, "build_grounded_messages", substituted)
    with pytest.raises(AssertionError, match="Final proposal was lost"):
        replay.replay_gateway()


def test_protocol_drift_exclusive_receipt_and_disabled_checks_are_rejected(tmp_path, receipt):
    protocol = replay.load_protocol()
    protocol["expected_primary_accounting"]["transport_calls"] = 1
    changed = tmp_path / "protocol.json"
    changed.write_text(json.dumps(protocol))
    with pytest.raises(ValueError, match="RegisteredGatewayProtocolMismatch"):
        replay.replay_gateway(changed)
    path = tmp_path / "receipt.json"
    replay.c3.write_receipt(path, receipt)
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        replay.c3.write_receipt(path, {"changed": True})
    assert path.read_bytes() == original
    blocked = tmp_path / "disabled.json"
    process = subprocess.run(
        [sys.executable, "-O", str(REPLAY_PATH), "--output", str(blocked)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert process.returncode == 2
    assert json.loads(process.stdout) == {"error_code": "AssertionChecksDisabled"}
    assert not blocked.exists()


def test_changed_sources_cannot_receive_success_receipt(monkeypatch):
    original, calls = replay.code_manifest, 0

    def changed_manifest():
        nonlocal calls
        calls += 1
        result = original()
        if calls > 1:
            result["src/agent_app/llm/metis.py"] = "0" * 64
        return result

    monkeypatch.setattr(replay, "code_manifest", changed_manifest)
    with pytest.raises(RuntimeError, match="CodeChangedDuringReplay"):
        replay.replay_gateway()
