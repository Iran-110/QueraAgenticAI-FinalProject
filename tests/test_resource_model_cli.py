"""Reuse real disposable-ledger lifecycle controls for the new opt-in campaign.

The shared controls exercise authorization/closure/source drift in both drivers;
the real-index guard below also requires exactly the same corpus in both arms.
No test reads credentials or the designated project ledger.
"""

import importlib.util
import json
import sqlite3
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

import pytest
import test_dev_rag_model_cli as controls
from test_budget_quarantine_scope import multiple_holds as multiple_holds
from test_budget_quarantine_scope import old_rows, slot

from agent_app.testing.dev_three_model_probe import ledger_observation

ROOT = Path(__file__).resolve().parents[1]


def _module(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "resource_cli_disposable_control", ROOT / "scripts/core_resource_model_probe.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def cli(tmp_path, monkeypatch, multiple_holds):
    monkeypatch.setattr(controls, "_module", _module)
    return controls.cli.__wrapped__(tmp_path, monkeypatch, multiple_holds)


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
    pair = {arm: deepcopy(primary) for arm in ("resource_guidance_off", "resource_guidance_on")}
    return module, tmp_path, pair, calls, old


def test_resource_arms_require_same_verified_native_corpus(bindings):
    module, root, pair, calls, _ = bindings
    assert module.validate_registered_indexes(root, pair) == pair
    assert len(calls) == 1


@pytest.mark.parametrize("change", ["old", "path", "snapshot", "hash", "extra", "missing"])
def test_resource_arms_cannot_swap_corpus_or_add_unregistered_treatment(bindings, change):
    module, root, pair, _calls, old = bindings
    if change == "old":
        pair["resource_guidance_on"] = old
    elif change in {"path", "snapshot", "hash"}:
        key = {"path": "path", "snapshot": "snapshot_id", "hash": "manifest_sha256"}[change]
        pair["resource_guidance_on"][key] = "different"
    elif change == "extra":
        pair["unregistered"] = deepcopy(pair["resource_guidance_on"])
    else:
        del pair["resource_guidance_off"]
    with pytest.raises(ValueError, match="^ResourceRegistrationRejected$"):
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
