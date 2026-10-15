"""Fresh finite comparison lifecycle: disposable history, no network or real key."""

import importlib.util
import json
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
import test_claim_probe as proposal_controls
import test_dev_rag_model_cli as controls
import test_enum_evidence_model_cli as parent_controls
import test_source_capacity_model_cli as lifecycle
from test_budget_quarantine_scope import multiple_holds as multiple_holds

from agent_app.testing.claim_probe import (
    fixed_snapshot_factory,
    proposal_slots,
    run_proposal_batch,
)

ROOT = Path(__file__).resolve().parents[1]


def _module(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "claim_cli_disposable_control", ROOT / "scripts/core_claim_boundary_probe.py"
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
    with pytest.raises(ValueError, match="ClaimBoundaryRegistrationRejected"):
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


def _json_write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


@pytest.fixture
def registered_inputs(tmp_path, monkeypatch, multiple_holds):
    """A wholly disposable byte registry; never read ignored native files.

    Production protocol pins are checked first. Only temporary registry bindings,
    the temporary synthetic history and their real digest constants are rebound.
    SHA validation functions, ownership checks and drift rejection remain real.
    """
    from dataclasses import asdict

    from registered_native_inputs import synthetic_native_bytes
    from test_budget_quarantine_scope import slot

    from agent_app.testing.dev_three_model_probe import ledger_observation

    module = _module(monkeypatch)
    ledger, ledger_path, _ = multiple_holds
    protocol_path = module.FOLDER / "protocol-v1.json"
    original_protocol = (ROOT / protocol_path).read_bytes()
    assert module.sha(original_protocol) == module.PROTOCOL_SHA256
    protocol = json.loads(original_protocol)
    epoch_path = Path(protocol["inputs"]["current_epoch"])
    epoch = controls._read(ROOT / epoch_path)
    assert module.sha((ROOT / epoch_path).read_bytes()) == module.EPOCH_SHA256
    assert (
        module.sha((ROOT / protocol["inputs"]["preparation"]).read_bytes())
        == module.PREPARATION_SHA256
    )
    assert (
        module.sha((ROOT / module.OLD_FOLDER / "model-receipt-v1.json").read_bytes())
        == module.CLOSED_RECEIPT_SHA256
    )
    assert (
        module.sha((ROOT / protocol["inputs"]["new_acceptance_matrix"]).read_bytes())
        == module.MATRIX_SHA256
    )
    root = tmp_path / "registered-claim-inputs"
    names = {
        *(p.relative_to(ROOT).as_posix() for p in (ROOT / module.OLD_FOLDER).glob("*.json")),
        *epoch["files"],
        *(
            value
            for key, value in protocol["inputs"].items()
            if not key.endswith("sha256") and isinstance(value, str)
        ),
        protocol_path.as_posix(),
        "experiments/core_enum_evidence_v1/protected-inputs-v1.json",
        "experiments/core_quality_followup/quarantine-scope-protocol-v1.json",
        "scripts/core_claim_boundary_probe.py",
        "scripts/core_broader_dev_probe.py",
        "scripts/core_repeat_model_probe.py",
        "scripts/core_stability_probe.py",
        "src/agent_app/testing/claim_probe.py",
        "src/agent_app/testing/broader_proposals.py",
        "src/agent_app/testing/finite_controlled_probe.py",
        "src/agent_app/reasoning/claim_plan.py",
        "src/agent_app/llm/claims.py",
        "src/agent_app/llm/metis.py",
    }
    for name in names:
        relative = Path(name)
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        raw = (
            synthetic_native_bytes(relative)
            if relative.parts[0] == "runtime"
            else (ROOT / relative).read_bytes()
        )
        destination.write_bytes(raw)
    for name, digest in epoch["files"].items():
        actual = module.sha((root / name).read_bytes())
        if Path(name).parts[0] == "runtime":
            epoch["files"][name] = actual
        else:
            assert actual == digest
    _json_write(root / epoch_path, epoch)
    epoch_digest = module.sha((root / epoch_path).read_bytes())
    monkeypatch.setattr(module, "EPOCH_SHA256", epoch_digest)
    prep_path = root / protocol["inputs"]["preparation"]
    prep = controls._read(prep_path)
    prep["protected_epoch_sha256"] = epoch_digest
    _json_write(prep_path, prep)
    monkeypatch.setattr(module, "PREPARATION_SHA256", module.sha(prep_path.read_bytes()))
    # Register and close every historical dummy scope using actual public ledger
    # methods. No provider call/reservation/settlement or old-scope waiver occurs.
    observed = asdict(ledger.quarantine_observation())
    for index in range(91):
        scope = f"synthetic-closed-prior-scope-{index}"
        ledger.authorize_quarantine_scope(
            authorization_id=scope,
            authorization_ref="synthetic-prior-user",
            expected_unknown_ids=observed["unknown_ids"],
            expected_unknown_fingerprints=observed["unknown_fingerprints"],
            expected_meta_sha256=observed["meta_sha256"],
            expected_authorization_history_sha256=observed["authorization_history_sha256"],
            protocol_sha256=module.sha(scope.encode()),
            request_slots=(slot(1000 + index),),
            additional_cap_usd=Decimal("0.06"),
            allow_full_context=True,
        )
        ledger.close_quarantine_scope(scope)
    current = ledger_observation(ledger_path)
    with __import__("sqlite3").connect(ledger_path) as db:
        held = db.execute(
            "SELECT sum(amount_nanos) FROM reservations WHERE status='uncertain'"
        ).fetchone()[0]
    protocol["live"]["expected_before"] = {
        "reservations": 2,
        "settled": 0,
        "uncertain": 2,
        "settled_local_estimate_usd": "0",
        "old_hold_usd": str(Decimal(held) / 1_000_000_000),
        "halted": True,
        "ceiling_usd": "4.50",
    }
    _json_write(root / protocol_path, protocol)
    protocol_digest = module.sha((root / protocol_path).read_bytes())
    monkeypatch.setattr(module, "PROTOCOL_SHA256", protocol_digest)
    matrix_path = root / protocol["inputs"]["new_acceptance_matrix"]
    matrix = controls._read(matrix_path)
    matrix["protocol_sha256"] = protocol_digest
    _json_write(matrix_path, matrix)
    monkeypatch.setattr(module, "MATRIX_SHA256", module.sha(matrix_path.read_bytes()))
    closed_path = root / module.OLD_FOLDER / "model-receipt-v1.json"
    closed = controls._read(closed_path)
    closed["ledger_after"] = current
    _json_write(closed_path, closed)
    monkeypatch.setattr(module, "CLOSED_RECEIPT_SHA256", module.sha(closed_path.read_bytes()))
    policy_path = root / "experiments/core_quality_followup/quarantine-scope-protocol-v1.json"
    policy = controls._read(policy_path)
    policy["known_uncertain_request_ids"] = observed["unknown_ids"]
    _json_write(policy_path, policy)
    packet = controls._read(root / protocol["inputs"]["snapshots"])
    offline_path = root / module.FOLDER / "offline-preflight-v1.json"
    _json_write(offline_path, module.offline_preflight(packet))
    return module, root, ledger_path


def test_fresh_registered_method_has_balanced128_slots_and_preserves_real_guards(registered_inputs):
    module, root, path = registered_inputs
    method = module.build_method(root, path)
    assert len(method["batches"]) == len(set(method["fresh_scope_ids"])) == 16
    assert len(method["fresh_request_ids"]) == len(set(method["fresh_request_ids"])) == 128
    assert method["scope_cap_usd"] == "0.06" and method["campaign_scope_cap_usd"] == "0.96"
    assert method["schema_or_exact_passage_is_not_automatic_entailment"]
    assert len(method["ledger_journal_before"]["tables"]) == 14
    assert len(method["protected_files"]) == 19
    orders = {}
    for batch in method["batches"]:
        assert batch["max_request_slots"] == 8 and len(batch["scope_id"]) <= 64
        assert Decimal(batch["worst_reserved_usd"]) < Decimal(".06")
        scenario = batch["jobs"][0]["scenario_id"]
        orders.setdefault(scenario, []).append([j["arm"] for j in batch["jobs"]])
        assert all(
            j["input_token_reserve"] == 32768 and j["max_output_tokens"] == 2048
            for j in batch["jobs"]
        )
    assert all(first == second[::-1] for first, second in orders.values())


@pytest.mark.parametrize("target", ["protocol", "protected", "offline", "matrix", "closed_receipt"])
def test_registered_input_mutation_fails_before_fresh_slots(registered_inputs, target):
    module, root, path = registered_inputs
    candidates = {
        "protocol": root / module.FOLDER / "protocol-v1.json",
        "offline": root / module.FOLDER / "offline-preflight-v1.json",
        "matrix": root / module.FOLDER / "acceptance-matrix-v1.json",
        "closed_receipt": root / module.OLD_FOLDER / "model-receipt-v1.json",
    }
    if target == "protected":
        epoch = controls._read(root / module.OLD_FOLDER / "protected-inputs-v1.json")
        victim = root / next(iter(epoch["files"]))
    else:
        victim = candidates[target]
    if target == "offline":
        value = controls._read(victim)
        value["accepted"] = False
        _json_write(victim, value)
    else:
        victim.write_bytes(victim.read_bytes() + b" ")
    with pytest.raises(ValueError):
        module.build_method(root, path)
