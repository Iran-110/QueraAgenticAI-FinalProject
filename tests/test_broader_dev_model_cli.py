"""Fresh finite comparison lifecycle: disposable history, no network or real key."""

import importlib.util
import json
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
import test_broader_proposals as proposal_controls
import test_dev_rag_model_cli as controls
import test_enum_evidence_model_cli as parent_controls
import test_source_capacity_model_cli as lifecycle
from test_budget_quarantine_scope import multiple_holds as multiple_holds

from agent_app.testing.broader_proposals import (
    fixed_snapshot_factory,
    proposal_slots,
    run_proposal_batch,
)

ROOT = Path(__file__).resolve().parents[1]


def _module(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "broader_dev_cli_disposable_control", ROOT / "scripts/core_broader_dev_probe.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def cli(tmp_path, monkeypatch, multiple_holds):
    module = _module(monkeypatch)
    monkeypatch.setattr(module, "load_source_packet", lambda *_: {}, raising=False)
    monkeypatch.setattr(parent_controls, "_module", lambda *_: module)
    value = parent_controls.cli.__wrapped__(tmp_path, monkeypatch, multiple_holds)
    monkeypatch.setattr(module, "load_packet", lambda: {})
    return value


def test_registered_cap_closes_all_owned_slots_without_release(cli):
    controls.test_cli_complete_final_batch_closes_real_scope_and_binds_ledger_journal(cli)
    receipt = controls._read(cli.destination / "receipt.json")
    assert receipt["proposal_only"] and receipt["no_automatic_approval_or_release"]
    assert receipt["tracker_actions_executed"] == 0 and receipt["no_route_success_claim"]
    assert receipt["human_usefulness"] is None and not receipt["held_out_test"]
    status = cli.ledger.quarantine_scope_status(cli.method["batches"][0]["scope_id"])
    assert status.additional_cap_usd == Decimal("0.06")
    assert receipt["batches"][0]["json_object_wire_observed"] is None


@pytest.mark.parametrize(
    "scenario",
    [
        "test_cli_source_drift_before_credentials_stops_without_authorization",
        "test_cli_source_drift_before_next_batch_cannot_authorize_or_run_it",
        "test_source_drift_after_reservation_checkpoint_blocks_actual_send",
        "test_index_drift_before_key_cannot_allocate_a_scope",
    ],
)
def test_source_custody_guards(cli, monkeypatch, scenario):
    getattr(controls, scenario)(cli, monkeypatch)


@pytest.mark.parametrize(
    "scenario",
    [
        "test_unknown_record_changed_after_preflight_never_reads_key_or_allocates",
        "test_new_uncertainty_closes_campaign_without_authorizing_next_pair",
        "test_foreign_journal_append_before_key_cannot_allocate_or_dispatch",
    ],
)
def test_old_history_and_new_uncertainty_guards(cli, monkeypatch, scenario):
    getattr(lifecycle, scenario)(cli, monkeypatch)


@pytest.mark.parametrize("interrupt", [KeyboardInterrupt, SystemExit])
def test_cancelled_authorization_permanently_closes_owned_scope(
    cli, monkeypatch, capsys, interrupt
):
    controls.test_cli_cancellation_after_authorization_permanently_closes_scope_and_journals(
        cli, monkeypatch, capsys, interrupt
    )


def test_non_json_wire_is_observed_as_absent_not_successful_json_mode(monkeypatch):
    module = _module(monkeypatch)
    result = {
        "actual_sends": 1,
        "provider_sends": [{"http_send_started": True, "wire_response_format": "absent"}],
    }
    assert module.observe_no_json_format(result) is None
    assert result["actual_no_response_format_field"] is True
    zero = {"actual_sends": 0, "provider_sends": [{"http_send_started": False}]}
    assert module.observe_no_json_format(zero) is None
    assert zero["actual_no_response_format_field"] is None
    result["provider_sends"][0]["wire_response_format"] = "json_object"
    with pytest.raises(ValueError, match="BroaderDevRegistrationRejected"):
        module.observe_no_json_format(result)


@pytest.mark.parametrize("count", [0, True, "1", 2])
def test_wire_counter_mismatch_does_not_claim_observation(monkeypatch, count):
    module = _module(monkeypatch)
    with pytest.raises(ValueError):
        module.observe_no_json_format(
            {
                "actual_sends": count,
                "provider_sends": [{"http_send_started": True, "wire_response_format": "absent"}],
            }
        )


def test_noargs_reports_registered_cap_without_key_or_scope(cli, capsys):
    assert cli.module.main([]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["cap_usd"] == "0.06" and output["actual_sends"] == 0
    assert cli.calls["credentials"] == 0 and controls._scope_count(cli.path) == 0


@pytest.mark.parametrize("failure", [None, "invalid_shape", "timeout"])
def test_real_proposal_gateway_through_finite_cli_retains_bounds(cli, monkeypatch, failure):
    packet, fixtures, authored_method, batch = proposal_controls._inputs()
    cli.method["experiment_id"] = authored_method["experiment_id"]
    slots = proposal_slots(cli.method, batch, fixtures)
    batch["max_request_slots"] = len(slots)
    cli.method["batches"] = [batch]
    cli.method["fresh_request_ids"] = [s.request_id for s in slots]
    cli.method["fresh_scope_ids"] = [batch["scope_id"]]
    monkeypatch.setattr(cli.module, "quality_slots", proposal_slots)
    monkeypatch.setattr(cli.module, "fixtures_for", lambda *_: fixtures)
    monkeypatch.setattr(cli.module, "load_packet", lambda: packet)
    monkeypatch.setattr(cli.module, "fixture_retriever_factory", fixed_snapshot_factory)

    def respond(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("authored diagnostic timeout")
        payload = json.loads(request.content)
        content = "[]" if failure else proposal_controls._payload(payload)
        return proposal_controls._provider(content)

    def actual(*args, **kwargs):
        return run_proposal_batch(*args, **kwargs, underlying=httpx.MockTransport(respond))

    monkeypatch.setattr(cli.module, "run_quality_batch", actual)
    code = controls._main(cli)
    receipt = controls._read(cli.destination / "receipt.json")
    result = receipt["batches"][0]
    assert code == (2 if failure == "timeout" else 0)
    assert result["completed_routes"] == 0 and result["actions_executed"] == 0
    assert result["json_object_wire_observed"] is None
    assert all(row["wire_response_format"] == "absent" for row in result["provider_sends"])
    assert result["actual_sends"] == (1 if failure == "timeout" else 8 if failure else 4)
    scope = cli.ledger.quarantine_scope_status(batch["scope_id"])
    assert not scope.active
    assert receipt["tracker_actions_executed"] == 0


@pytest.fixture
def registered_inputs(tmp_path, monkeypatch, multiple_holds):
    from registered_native_inputs import broader_registered_inputs

    module = _module(monkeypatch)
    root = tmp_path / "registered-inputs"
    return broader_registered_inputs(module, ROOT, root, monkeypatch, multiple_holds)


def test_registered_design_has128_fresh_valid_slots_no_releases(registered_inputs):
    module, root, path = registered_inputs
    method = module.build_method(root, path)
    assert len(method["batches"]) == 16
    assert len(method["fresh_request_ids"]) == len(set(method["fresh_request_ids"])) == 128
    assert len(set(method["fresh_scope_ids"])) == 16
    assert method["proposal_only"] and method["tracker_actions_executed"] == 0
    assert len(method["protected_files"]) == 19
    for batch in method["batches"]:
        assert len(batch["scope_id"]) <= 64 and batch["max_request_slots"] == 8
        assert Decimal(batch["worst_reserved_usd"]) < Decimal("0.06")
        for job in batch["jobs"]:
            assert job["input_token_reserve"] == 32768
            assert job["max_output_tokens"] == 2048
    rounds = {}
    for batch in method["batches"]:
        scenario = batch["jobs"][0]["scenario_id"]
        rounds.setdefault(scenario, []).append([job["arm"] for job in batch["jobs"]])
    assert all(second == first[::-1] for first, second in rounds.values())


@pytest.mark.parametrize("target", ["protocol", "protected", "offline"])
def test_changed_registered_inputs_fail_before_any_identity_allocation(registered_inputs, target):
    module, root, path = registered_inputs
    if target == "protocol":
        p = root / module.FOLDER / "protocol-v1.json"
    elif target == "offline":
        p = root / module.FOLDER / "offline-preflight-v1.json"
        value = json.loads(p.read_bytes())
        value["accepted"] = False
        p.write_text(json.dumps(value))
    else:
        protected = controls._read(
            root / "experiments/core_enum_evidence_v1/protected-inputs-v1.json"
        )
        p = root / next(iter(protected["files"]))
    if target != "offline":
        p.write_bytes(p.read_bytes() + b" ")
    with pytest.raises(ValueError):
        module.build_method(root, path)
