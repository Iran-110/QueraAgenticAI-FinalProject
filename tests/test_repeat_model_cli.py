"""Reuse real disposable-ledger lifecycle controls for the new opt-in campaign.

The shared controls exercise authorization/closure/source drift in both drivers;
the real-index guard below also requires exactly the same corpus in both arms.
No test reads credentials or the designated project ledger.
"""

import importlib.util
import json
import sqlite3
import sys
from copy import deepcopy
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

import pytest
import test_dev_rag_model_cli as controls
from test_budget_quarantine_scope import SCOPE, authorize, old_rows, reserve, slot
from test_budget_quarantine_scope import multiple_holds as multiple_holds

from agent_app.testing.dev_three_model_probe import ledger_observation

ROOT = Path(__file__).resolve().parents[1]


def _module(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "repeat_cli_disposable_control", ROOT / "scripts/core_repeat_model_probe.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def cli(tmp_path, monkeypatch, multiple_holds):
    monkeypatch.setattr(controls, "_module", _module)
    value = controls.cli.__wrapped__(tmp_path, monkeypatch, multiple_holds)
    value.method["ledger_journal_before"] = value.module.ledger_journal_snapshot(value.path)
    value.method["fresh_request_ids"] = [slot(10).request_id, slot(11).request_id]
    value.method["fresh_scope_ids"] = [value.method["batches"][0]["scope_id"]]
    return value


def test_closed_scope_and_preserved_prior_ledger(cli):
    controls.test_cli_complete_final_batch_closes_real_scope_and_binds_ledger_journal(cli)


@pytest.mark.parametrize("failure", ["incomplete_accounting", "stopped", "unvisited_job"])
def test_incomplete_accounting_or_visit_cannot_succeed(cli, monkeypatch, failure):
    controls.test_cli_incomplete_last_batch_never_returns_success(cli, monkeypatch, failure)


def test_route_quality_is_separate_from_settled_accounting(cli, monkeypatch):
    controls.test_cli_semantic_route_failure_is_separate_from_complete_operational_accounting(
        cli, monkeypatch
    )


def test_source_changed_before_key_has_no_authority(cli, monkeypatch):
    controls.test_cli_source_drift_before_credentials_stops_without_authorization(cli, monkeypatch)


@pytest.mark.parametrize("interrupt", [KeyboardInterrupt, SystemExit])
def test_cancellation_closes_fresh_unused_scope(cli, monkeypatch, capsys, interrupt):
    controls.test_cli_cancellation_after_authorization_permanently_closes_scope_and_journals(
        cli, monkeypatch, capsys, interrupt
    )


def test_interruption_after_commit_preserves_finite_ownership(cli, monkeypatch):
    controls.test_cli_authorization_commit_then_interrupt_cannot_leave_unused_scope_active(
        cli, monkeypatch
    )


def test_index_changed_before_key_has_no_authority(cli, monkeypatch):
    controls.test_index_drift_before_key_cannot_allocate_a_scope(cli, monkeypatch)


def test_source_changed_at_send_checkpoint_has_no_send(cli, monkeypatch):
    controls.test_source_drift_after_reservation_checkpoint_blocks_actual_send(cli, monkeypatch)


@pytest.fixture
def bindings(tmp_path, monkeypatch):
    module = _module(monkeypatch)
    primary = {
        "path": "/synthetic/new18",
        "snapshot_id": "synthetic18",
        "manifest_sha256": "a" * 64,
    }
    old = {"path": "/synthetic/old14", "snapshot_id": "synthetic14", "manifest_sha256": "b" * 64}
    folder = tmp_path / module.COVERAGE_FOLDER
    folder.mkdir(parents=True)
    (folder / "index-receipt-v1.json").write_text(
        json.dumps({"indexes": {"historical_14_sources": old, "new_18_sources": primary}})
    )
    calls = []

    def verified(_root, supplied):
        calls.append(deepcopy(supplied))
        assert supplied == {"historical_14_sources": old, "new_18_sources": primary}
        return supplied

    monkeypatch.setattr(module, "validate_coverage_indexes", verified)
    monkeypatch.setattr(module, "validate_index_bindings", lambda supplied: supplied)
    pair = {arm: deepcopy(primary) for arm in ("repeat_repair_off", "repeat_repair_on")}
    return module, tmp_path, pair, calls, old


def test_repeat_arms_require_same_verified_native_corpus(bindings):
    module, root, pair, calls, _ = bindings
    assert module.validate_registered_indexes(root, pair) == pair
    assert len(calls) == 1


@pytest.mark.parametrize("change", ["old", "path", "snapshot", "hash", "extra", "missing"])
def test_repeat_arms_cannot_swap_corpus_or_add_unregistered_treatment(bindings, change):
    module, root, pair, _calls, old = bindings
    if change == "old":
        pair["repeat_repair_on"] = old
    elif change in {"path", "snapshot", "hash"}:
        key = {"path": "path", "snapshot": "snapshot_id", "hash": "manifest_sha256"}[change]
        pair["repeat_repair_on"][key] = "different"
    elif change == "extra":
        pair["unregistered"] = deepcopy(pair["repeat_repair_on"])
    else:
        del pair["repeat_repair_off"]
    with pytest.raises(ValueError, match="^RepeatRegistrationRejected$"):
        module.validate_registered_indexes(root, pair)


def test_unknown_record_changed_after_preflight_never_reads_key_or_allocates(cli, monkeypatch):
    changed = []

    def source(*_args):
        if not changed:
            # An external reconciliation/tamper happened after the frozen
            # preflight observation. The driver must not adopt its new hash.
            with sqlite3.connect(cli.path) as connection:
                connection.execute(
                    "UPDATE reservations SET error_code=? WHERE request_id=?",
                    ("SyntheticChangedUnknown", "synthetic-legacy-slot"),
                )
            changed.append(True)
        return dict(cli.source)

    monkeypatch.setattr(cli.module, "source_observation", source)
    assert controls._main(cli) == 2
    assert cli.calls == {"credentials": 0, "batch_runs": 0, "provider": 0}
    assert controls._scope_count(cli.path) == 0
    assert (
        ledger_observation(cli.path)["unknown_sha256"]
        != cli.method["ledger_before"]["unknown_sha256"]
    )
    with sqlite3.connect(cli.path) as connection:
        assert (
            connection.execute(
                "SELECT error_code FROM reservations WHERE request_id='synthetic-legacy-slot'"
            ).fetchone()[0]
            == "SyntheticChangedUnknown"
        )


def test_new_uncertainty_closes_campaign_without_authorizing_next_pair(cli, monkeypatch):
    before = old_rows(cli.path)
    cli.method["batches"].append(
        {**cli.method["batches"][0], "batch_id": "second-pair", "scope_id": "second-pair-scope"}
    )
    registered = slot(10)

    def uncertain(_method, batch, *_args, **_kwargs):
        result = cli.run_batch(_method, batch)
        cli.ledger.reserve(**asdict(registered), continuation_id=batch["scope_id"])
        cli.ledger.mark_uncertain(registered.request_id, error_code="SyntheticWireUnknown")
        # Even if a faulty observer reports completion, the driver's frozen
        # uncertainty observation must prevent another funded pair.
        return result

    monkeypatch.setattr(cli.module, "run_real_index_batch", uncertain)
    assert controls._main(cli) == 2
    assert cli.calls == {"credentials": 1, "batch_runs": 1, "provider": 0}
    assert controls._scope_count(cli.path) == 1
    assert not (cli.destination / "second-pair").exists()
    assert old_rows(cli.path) == before
    assert cli.ledger.get(registered.request_id).status == "uncertain"
    scope = cli.ledger.quarantine_scope_status(cli.method["batches"][0]["scope_id"])
    assert not scope.active and scope.block_reason == "NewUncertainty"
    receipt = controls._read(cli.destination / "receipt.json")
    assert receipt["completed_batches"] == 1 and receipt["planned_batches"] == 2
    assert receipt["ledger_after"]["counts"]["uncertain"] == 3


def test_final_pair_cannot_succeed_if_observer_misses_actual_new_uncertainty(cli, monkeypatch):
    registered = slot(10)

    def uncertain(_method, batch, *_args, **_kwargs):
        result = cli.run_batch(_method, batch)
        cli.ledger.reserve(**asdict(registered), continuation_id=batch["scope_id"])
        cli.ledger.mark_uncertain(registered.request_id, error_code="SyntheticWireUnknown")
        return result

    monkeypatch.setattr(cli.module, "run_real_index_batch", uncertain)
    assert controls._main(cli) == 2
    receipt = controls._read(cli.destination / "receipt.json")
    assert receipt["completed_batches"] == receipt["planned_batches"] == 1
    assert receipt["batches"][0]["accounting"]["accounting_complete"]
    assert receipt["old_holds_and_authorization_history_preserved"] is False


def test_final_pair_cannot_succeed_if_observer_misses_actual_pending_reservation(cli, monkeypatch):
    registered = slot(10)

    def pending(_method, batch, *_args, **_kwargs):
        result = cli.run_batch(_method, batch)
        cli.ledger.reserve(**asdict(registered), continuation_id=batch["scope_id"])
        return result

    monkeypatch.setattr(cli.module, "run_real_index_batch", pending)
    assert controls._main(cli) == 2
    receipt = controls._read(cli.destination / "receipt.json")
    assert receipt["completed_batches"] == receipt["planned_batches"] == 1
    assert receipt["batches"][0]["accounting"]["accounting_complete"]
    assert receipt["old_holds_and_authorization_history_preserved"] is True
    assert receipt["no_pending_reservations"] is False
    assert cli.ledger.get(registered.request_id).status == "reserved"


@pytest.mark.parametrize("interrupt", [KeyboardInterrupt, SystemExit])
def test_cancel_after_reservation_keeps_pending_hold_and_permanently_closes(
    cli, monkeypatch, interrupt
):
    before = old_rows(cli.path)
    registered = slot(10)

    def reserved_then_cancelled(_method, batch, *_args, **kwargs):
        cli.ledger.reserve(**asdict(registered), continuation_id=batch["scope_id"])
        kwargs["checkpoint"]({"event": "reserved_before_transport"})
        raise interrupt(controls.PRIVATE_ERROR)

    monkeypatch.setattr(cli.module, "run_real_index_batch", reserved_then_cancelled)
    assert controls._main(cli) == 2
    assert cli.calls["provider"] == 0
    assert old_rows(cli.path) == before
    assert cli.ledger.get(registered.request_id).status == "reserved"
    scope = cli.ledger.quarantine_scope_status(cli.method["batches"][0]["scope_id"])
    assert not scope.active and scope.block_reason == "ExperimentClosed"
    failure = controls._read(cli.destination / "failure.json")
    assert failure["ledger_after"]["counts"] == {"reserved": 1, "uncertain": 2}
    assert failure["active_scope_disposition"]["block_reason"] == "ExperimentClosed"
    assert controls.PRIVATE_ERROR not in json.dumps(failure)


def test_archived_wire_inputs_and_repeat_feedback_fit_without_resource_guide(monkeypatch):
    module = _module(monkeypatch)
    report = module.payload_preflight(ROOT)
    assert report["archived_actual_requests"] == 51
    assert report["message_size_checks"] == 102
    assert report["max_utf8_with_margin"] <= 32768
    assert report["resource_guidance"] is False
    assert report["future_unobserved_refinements_covered"] is False
    assert report["actual_sends"] == 0


def test_preflight_size_guard_cannot_be_bypassed_by_repair_feedback(monkeypatch):
    module = _module(monkeypatch)
    monkeypatch.setattr(
        module,
        "build_grounded_messages",
        lambda *_a, **_k: (
            {"role": "system", "content": "x" * 32768},
            {"role": "user", "content": "{}"},
        ),
    )
    with pytest.raises(ValueError, match="^RepeatPayloadRejected$"):
        module.payload_preflight(ROOT)


def test_fresh_method_balances_only_one_factor_and_freezes_old_journal(multiple_holds, monkeypatch):
    module = _module(monkeypatch)
    ledger, path, _ = multiple_holds
    prior = controls._read(ROOT / module.COVERAGE_FOLDER / "live-method-v1.json")
    prior["ledger_before"] = ledger_observation(path)
    prior["quarantine_before"] = json.loads(
        json.dumps(asdict(ledger.quarantine_observation()), default=str)
    )
    monkeypatch.setattr(module, "coverage_build_method", lambda *_args: deepcopy(prior))
    monkeypatch.setattr(module, "validate_registered_indexes", lambda _r, indexes: indexes)
    before = path.read_bytes()
    method = module.build_method(ROOT, path)
    assert path.read_bytes() == before
    assert method["ledger_journal_before"] == module.ledger_journal_snapshot(path)
    assert method["indexes"]["repeat_repair_off"] == method["indexes"]["repeat_repair_on"]
    assert method["authorization_ref"] == "user-2026-10-14-continuation-core-improvement"
    assert method["campaign_scope_cap_usd"] == "0.36"
    assert len(method["fresh_request_ids"]) == len(set(method["fresh_request_ids"])) == 48
    assert len(method["fresh_scope_ids"]) == len(set(method["fresh_scope_ids"])) == 6
    assert [b["jobs"][0]["case_id"] for b in method["batches"]] == [
        "dev-case-a",
        "dev-case-b",
        "dev-case-c",
        "dev-case-c",
        "dev-case-b",
        "dev-case-a",
    ]
    arms = [[job["arm"] for job in b["jobs"]] for b in method["batches"]]
    assert arms == [
        ["repeat_repair_off", "repeat_repair_on"],
        ["repeat_repair_on", "repeat_repair_off"],
        ["repeat_repair_off", "repeat_repair_on"],
        ["repeat_repair_on", "repeat_repair_off"],
        ["repeat_repair_off", "repeat_repair_on"],
        ["repeat_repair_on", "repeat_repair_off"],
    ]
    for batch in method["batches"]:
        assert batch["max_request_slots"] == 8
        assert Decimal(batch["worst_reserved_usd"]) <= Decimal("0.06")
        for job in batch["jobs"]:
            assert job["resource_guidance"] is False
            assert job["repair_repeated_queries"] is (job["arm"] == "repeat_repair_on")
            assert job["decision_contracts"] and job["source_selection_reminder"]
            assert job["max_output_tokens"] == 1024 and job["input_token_reserve"] == 32768
    assert Decimal("0.36") >= sum(
        Decimal(batch["worst_reserved_usd"]) for batch in method["batches"]
    )
    assert (module.FOLDER / "protocol-v1.json").as_posix() in method["input_pins"]
    assert "scripts/core_repeat_model_probe.py" in method["input_pins"]
    assert (
        "experiments/core_resource_guidance_v1/model-live-receipt-v1.json" in method["input_pins"]
    )


def test_journal_is_read_only_and_accepts_only_owned_reservation_settlement_and_closure(
    multiple_holds, monkeypatch
):
    module = _module(monkeypatch)
    ledger, path, _ = multiple_holds
    before = path.read_bytes()
    baseline = module.ledger_journal_snapshot(path)
    assert module.validate_ledger_journal(path, baseline, {slot().request_id}, {SCOPE}) == baseline
    assert path.read_bytes() == before
    authorize(ledger, registered=(slot(),))
    reserve(ledger)
    module.validate_ledger_journal(path, baseline, {slot().request_id}, {SCOPE})
    ledger.settle(slot().request_id, cost_usd=Decimal("0.001"), input_tokens=100, output_tokens=20)
    ledger.close_quarantine_scope(SCOPE)
    module.validate_ledger_journal(path, baseline, {slot().request_id}, {SCOPE})


def test_old_settled_row_change_is_detected_beyond_existing_unknown_hash(
    multiple_holds, monkeypatch
):
    module = _module(monkeypatch)
    ledger, path, _ = multiple_holds
    authorize(ledger, registered=(slot(),))
    reserve(ledger)
    ledger.settle(slot().request_id, cost_usd=Decimal("0.001"), input_tokens=100, output_tokens=20)
    ledger.close_quarantine_scope(SCOPE)
    baseline = module.ledger_journal_snapshot(path)
    observed = ledger_observation(path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE reservations SET output_tokens=21 WHERE request_id=?", (slot().request_id,)
        )
    assert ledger_observation(path)["unknown_sha256"] == observed["unknown_sha256"]
    with pytest.raises(ValueError, match="^RepeatJournalRejected$"):
        module.validate_ledger_journal(path, baseline, {slot(10).request_id}, {"future-scope"})


@pytest.mark.parametrize("mutation", ["old_event", "foreign_scope", "schema", "deleted_row"])
def test_old_history_foreign_scope_or_schema_drift_is_rejected(
    multiple_holds, monkeypatch, mutation
):
    module = _module(monkeypatch)
    ledger, path, _ = multiple_holds
    baseline = module.ledger_journal_snapshot(path)
    if mutation == "foreign_scope":
        authorize(ledger, registered=(slot(20),))
    else:
        with sqlite3.connect(path) as connection:
            if mutation == "old_event":
                connection.execute(
                    "UPDATE ledger_events SET error_code='SyntheticDrift' WHERE request_id='synthetic-legacy-slot'"
                )
            elif mutation == "schema":
                connection.execute("CREATE TABLE synthetic_unowned_rows(value TEXT)")
            else:
                connection.execute(
                    "DELETE FROM ledger_events WHERE request_id='synthetic-legacy-slot'"
                )
    with pytest.raises(ValueError, match="^RepeatJournalRejected$"):
        module.validate_ledger_journal(path, baseline, {slot(10).request_id}, {"future-scope"})


def test_permanently_allocated_unused_identity_cannot_be_reprepared(multiple_holds, monkeypatch):
    module = _module(monkeypatch)
    ledger, path, _ = multiple_holds
    registered = slot(10)
    before = path.read_bytes()
    module.validate_fresh_identities(path, {registered.request_id}, {SCOPE})
    assert path.read_bytes() == before
    authorize(ledger, registered=(registered,))
    ledger.close_quarantine_scope(SCOPE)
    assert ledger.get(registered.request_id) is None
    after = path.read_bytes()
    with pytest.raises(ValueError, match="^RepeatIdentityAlreadyAllocated$"):
        module.validate_fresh_identities(path, {registered.request_id}, {"different-scope"})
    with pytest.raises(ValueError, match="^RepeatIdentityAlreadyAllocated$"):
        module.validate_fresh_identities(path, {slot(20).request_id}, {SCOPE})
    assert path.read_bytes() == after


def test_foreign_journal_append_before_key_cannot_allocate_or_dispatch(cli, monkeypatch):
    def index(*_args):
        authorize(cli.ledger, registered=(slot(20),))
        return {}

    monkeypatch.setattr(cli.module, "validate_registered_indexes", index)
    assert controls._main(cli) == 2
    assert cli.calls == {"credentials": 0, "batch_runs": 0, "provider": 0}
    assert controls._scope_count(cli.path) == 1
    assert cli.ledger.quarantine_scope_status(SCOPE).active


def test_owned_gateway_factory_receives_each_strict_job_flag(multiple_holds, monkeypatch):
    import httpx
    from test_quality_probe import prepare, response

    import agent_app.testing.quality_probe as probe
    from agent_app.reasoning.catalog import load_user_gap_vocabulary
    from agent_app.testing.http_pilot_runtime import offline_network
    from agent_app.testing.stability_probe import VOCABULARY

    ledger, protocol, batch, fixtures, config = prepare(multiple_holds)
    batch["kind"] = "adversarial"
    for job, enabled in zip(batch["jobs"], (False, True), strict=True):
        job["repair_repeated_queries"] = enabled
    original, seen = probe.SupportEngine, []

    def observe(*args, **kwargs):
        seen.append(kwargs["repair_repeated_queries"])
        return original(*args, **kwargs)

    monkeypatch.setattr(probe, "SupportEngine", observe)
    with offline_network():
        receipt = probe.run_quality_batch(
            protocol,
            batch,
            fixtures,
            load_user_gap_vocabulary(str(ROOT / VOCABULARY)),
            ledger,
            config,
            ledger_observation(ledger._path),
            underlying=httpx.MockTransport(response),
        )
    assert seen == [False, False, True, True]
    assert receipt["visited_jobs"] == 2 and receipt["accounting"]["accounting_complete"]
    assert receipt["original_accounting_preserved"]


@pytest.mark.parametrize("invalid", [1, 0, "true", "false", None, []])
def test_non_boolean_job_flag_is_rejected_before_transport_or_reservation(multiple_holds, invalid):
    import httpx
    from test_quality_probe import prepare

    from agent_app.testing.dev_three_model_probe import DevProbeRejected
    from agent_app.testing.quality_probe import run_quality_batch

    ledger, protocol, batch, fixtures, config = prepare(multiple_holds)
    batch["jobs"][0]["repair_repeated_queries"] = invalid
    before, sends = ledger_observation(ledger._path), []
    with pytest.raises(DevProbeRejected):
        run_quality_batch(
            protocol,
            batch,
            fixtures,
            (),
            ledger,
            config,
            before,
            underlying=httpx.MockTransport(lambda request: sends.append(request)),
        )
    assert sends == []
    assert ledger_observation(ledger._path) == before


@pytest.mark.parametrize("inside_root", [False, True])
def test_rejected_output_folder_is_never_claimed_or_mutated(cli, monkeypatch, inside_root):
    candidate = cli.root / "existing-other-work" if inside_root else cli.destination
    candidate.mkdir()
    marker = candidate / "prior-receipt.json"
    marker.write_bytes(b'{"synthetic_immutable":true}\n')
    original = {path.name: path.read_bytes() for path in candidate.iterdir()}
    arguments = list(sys.argv)
    arguments[arguments.index("--output-dir") + 1] = str(candidate)
    monkeypatch.setattr(sys, "argv", arguments)
    before = ledger_observation(cli.path)
    assert controls._main(cli) == 2
    assert {path.name: path.read_bytes() for path in candidate.iterdir()} == original
    assert cli.calls == {"credentials": 0, "batch_runs": 0, "provider": 0}
    assert controls._scope_count(cli.path) == 0
    assert ledger_observation(cli.path) == before
