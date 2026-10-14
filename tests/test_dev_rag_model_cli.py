"""Actual CLI control flow with disposable quarantine ledger and no provider/key.

The method/preflight and planner are explicit test doubles; authorization and
permanent scope closure use the real SQLite budget implementation. Nothing opens
the team ledger or the user's environment file.
"""

import importlib.util
import json
import shutil
import sqlite3
import sys
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_budget_quarantine_scope import multiple_holds as multiple_holds
from test_budget_quarantine_scope import old_rows, slot

from agent_app.llm.budget import BudgetLedger
from agent_app.testing.dev_three_model_probe import ledger_observation
from agent_app.testing.http_pilot_runtime import offline_network

PROJECT = Path(__file__).resolve().parents[1]
SECRET = "synthetic-cli-key-never-a-real-credential"
PRIVATE_ERROR = "synthetic-private-cancellation-do-not-export"


def _module(monkeypatch):
    monkeypatch.syspath_prepend(str(PROJECT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "real_index_cli_disposable_control", PROJECT / "scripts/dev_rag_model_probe.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _scope_count(path):
    with sqlite3.connect(path) as db:
        exists = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='quarantine_scopes'"
        ).fetchone()
        return db.execute("SELECT count(*) FROM quarantine_scopes").fetchone()[0] if exists else 0


@pytest.fixture
def cli(tmp_path, monkeypatch, multiple_holds):
    module = _module(monkeypatch)
    root = tmp_path / "synthetic-project"
    path = root / "runtime/budget.sqlite3"
    path.parent.mkdir(parents=True)
    _, seed, _ = multiple_holds
    shutil.copyfile(seed, path)
    ledger = BudgetLedger(path)
    unknown = json.loads(json.dumps(asdict(ledger.quarantine_observation()), default=str))
    source = {
        "source_commit": "a" * 40,
        "source_clean": True,
        "source_hashes": {"synthetic-owned-source.py": "b" * 64},
    }
    batch = {
        "batch_id": "synthetic-final-batch",
        "scope_id": "synthetic-cli-final-scope",
        "kind": "stability",
        "jobs": [{"job_id": "synthetic-job"}],
        "max_request_slots": 2,
    }
    method = {
        "protocol_id": "synthetic-quality-method",
        "experiment_id": "synthetic-quality-cli-experiment",
        "authorization_ref": "synthetic-explicit-human-authorization",
        "input_pins": {},
        "indexes": {},
        "quarantine_before": unknown,
        "ledger_before": ledger_observation(path),
        "batches": [batch],
    }
    registration = {
        **source,
        "method_sha256": "c" * 64,
        "ledger_before": method["ledger_before"],
        "quarantine_before": unknown,
    }
    calls = {"credentials": 0, "batch_runs": 0, "provider": 0}
    destination = tmp_path / "private-receipts"

    def credential(_path):
        calls["credentials"] += 1
        return SECRET

    def run_batch(_method, current, *_args, **_kwargs):
        calls["batch_runs"] += 1
        return {
            "batch_id": current["batch_id"],
            "planned_jobs": len(current["jobs"]),
            "visited_jobs": len(current["jobs"]),
            "completed_routes": 1,
            "actual_sends": 0,
            "stopped_early": False,
            "original_accounting_preserved": True,
            "accounting": {"accounting_complete": True, "requests": []},
            "jobs": [],
            "provider_sends": [],
        }

    monkeypatch.setattr(module, "ROOT", root)
    monkeypatch.setattr(module, "preflight", lambda *_args: (method, registration))
    monkeypatch.setattr(module, "source_observation", lambda *_args: dict(source))
    monkeypatch.setattr(module, "credential", credential)
    monkeypatch.setattr(module, "validate_registered_indexes", lambda *_args: {})
    monkeypatch.setattr(module, "fixtures_for", lambda *_args: {})
    monkeypatch.setattr(module, "load_user_gap_vocabulary", lambda *_args: ())
    monkeypatch.setattr(module, "quality_slots", lambda *_args: (slot(10), slot(11)))
    monkeypatch.setattr(module, "run_real_index_batch", run_batch)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "quality-followup",
            "--live",
            "--ledger",
            str(path),
            "--method",
            str(root / module.METHOD),
            "--env-file",
            str(root / "unused-synthetic.env"),
            "--output-dir",
            str(destination),
        ],
    )
    return SimpleNamespace(
        module=module,
        root=root,
        path=path,
        ledger=ledger,
        method=method,
        registration=registration,
        source=source,
        calls=calls,
        destination=destination,
        run_batch=run_batch,
    )


def _main(cli):
    with offline_network():
        return cli.module.main()


def test_cli_complete_final_batch_closes_real_scope_and_binds_ledger_journal(cli):
    before = old_rows(cli.path)
    assert _main(cli) == 0
    scope = cli.ledger.quarantine_scope_status(cli.method["batches"][0]["scope_id"])
    assert scope.block_reason == "ExperimentClosed" and not scope.active
    assert old_rows(cli.path) == before
    assert cli.calls == {"credentials": 1, "batch_runs": 1, "provider": 0}
    receipt = _read(cli.destination / "receipt.json")
    assert receipt["source_unchanged"] is True
    assert receipt["source_after"] == cli.source
    assert receipt["batches"][0]["scope_disposition"]["block_reason"] == "ExperimentClosed"
    assert type(receipt["batches"][0]["scope_disposition"]["remaining_usd"]) is str
    registration = _read(cli.destination / "synthetic-final-batch/registration.json")
    assert registration["ledger_before"] == cli.method["ledger_before"]
    assert registration["source_hashes"] == cli.source["source_hashes"]
    assert scope.protocol_sha256 == cli.module.sha(
        json.dumps(registration, sort_keys=True).encode()
    )
    assert SECRET not in json.dumps(receipt)


@pytest.mark.parametrize("failure", ["incomplete_accounting", "stopped", "unvisited_job"])
def test_cli_incomplete_last_batch_never_returns_success(cli, monkeypatch, failure):
    def run(*args, **kwargs):
        result = cli.run_batch(*args, **kwargs)
        if failure == "incomplete_accounting":
            result["accounting"]["accounting_complete"] = False
        elif failure == "stopped":
            result["stopped_early"] = True
        else:
            result["visited_jobs"] = 0
        return result

    monkeypatch.setattr(cli.module, "run_real_index_batch", run)
    assert _main(cli) == 2
    receipt = _read(cli.destination / "receipt.json")
    # Last-batch failure is retained even though the number of visited batches
    # equals the planned batch count and the old quarantine stayed unchanged.
    assert receipt["completed_batches"] == receipt["planned_batches"] == 1
    assert not cli.module.batch_complete(receipt["batches"][0])
    assert not cli.ledger.quarantine_scope_status(cli.method["batches"][0]["scope_id"]).active
    assert cli.calls["provider"] == 0


def test_cli_semantic_route_failure_is_separate_from_complete_operational_accounting(
    cli, monkeypatch
):
    def run(*args, **kwargs):
        result = cli.run_batch(*args, **kwargs)
        result["completed_routes"] = 0
        return result

    monkeypatch.setattr(cli.module, "run_real_index_batch", run)
    assert _main(cli) == 0
    receipt = _read(cli.destination / "receipt.json")
    assert receipt["batches"][0]["completed_routes"] == 0
    assert receipt["human_reviewed"] is False
    assert receipt["human_usefulness"] is None


def test_cli_source_drift_before_credentials_stops_without_authorization(cli, monkeypatch):
    before = ledger_observation(cli.path)
    monkeypatch.setattr(
        cli.module, "source_observation", lambda *_args: {**cli.source, "source_clean": False}
    )
    assert _main(cli) == 2
    assert cli.calls == {"credentials": 0, "batch_runs": 0, "provider": 0}
    assert ledger_observation(cli.path) == before
    assert _scope_count(cli.path) == 0


def test_cli_source_drift_before_next_batch_cannot_authorize_or_run_it(cli, monkeypatch):
    cli.method["batches"].append(
        {
            "batch_id": "synthetic-next-batch",
            "scope_id": "synthetic-next-scope",
            "kind": "stability",
            "jobs": [{"job_id": "synthetic-next-job"}],
            "max_request_slots": 2,
        }
    )
    observed = []

    def source(*_args):
        observed.append(True)
        return {**cli.source, "source_clean": len(observed) < 3}

    monkeypatch.setattr(cli.module, "source_observation", source)
    assert _main(cli) == 2
    assert cli.calls["batch_runs"] == 1 and cli.calls["provider"] == 0
    assert _scope_count(cli.path) == 1
    assert not (cli.destination / "synthetic-next-batch").exists()
    failure = _read(cli.destination / "failure.json")
    assert len(failure["batches"]) == 1
    assert failure["batches"][0]["scope_disposition"]["block_reason"] == "ExperimentClosed"


def test_cli_final_source_drift_is_saved_and_changes_exit_status(cli, monkeypatch):
    observed = []

    def source(*_args):
        observed.append(True)
        return {
            **cli.source,
            "source_hashes": cli.source["source_hashes"]
            if len(observed) < 3
            else {"synthetic-owned-source.py": "d" * 64},
        }

    monkeypatch.setattr(cli.module, "source_observation", source)
    assert _main(cli) == 2
    receipt = _read(cli.destination / "receipt.json")
    assert receipt["source_unchanged"] is False
    assert receipt["source_after"]["source_hashes"] != cli.registration["source_hashes"]
    assert not cli.ledger.quarantine_scope_status(cli.method["batches"][0]["scope_id"]).active


@pytest.mark.parametrize("interrupt", [KeyboardInterrupt, SystemExit])
def test_cli_cancellation_after_authorization_permanently_closes_scope_and_journals(
    cli, monkeypatch, capsys, interrupt
):
    before = old_rows(cli.path)

    def cancelled(*_args, **_kwargs):
        raise interrupt(PRIVATE_ERROR)

    monkeypatch.setattr(cli.module, "run_real_index_batch", cancelled)
    assert _main(cli) == 2
    assert cli.calls["provider"] == 0
    assert old_rows(cli.path) == before
    scope = cli.ledger.quarantine_scope_status(cli.method["batches"][0]["scope_id"])
    assert not scope.active and scope.block_reason == "ExperimentClosed"
    failure = _read(cli.destination / "failure.json")
    cleanup = _read(cli.destination / "cleanup.json")
    assert failure["active_scope_disposition"]["block_reason"] == "ExperimentClosed"
    assert cleanup["block_reason"] == "ExperimentClosed"
    assert PRIVATE_ERROR not in json.dumps(failure)
    assert SECRET not in json.dumps(failure)
    assert PRIVATE_ERROR not in capsys.readouterr().out


def test_cli_authorization_commit_then_interrupt_cannot_leave_unused_scope_active(cli, monkeypatch):
    original = BudgetLedger.authorize_quarantine_scope

    def committed_then_cancelled(self, **values):
        original(self, **values)
        raise KeyboardInterrupt(PRIVATE_ERROR)

    monkeypatch.setattr(BudgetLedger, "authorize_quarantine_scope", committed_then_cancelled)
    assert _main(cli) == 2
    assert cli.calls["batch_runs"] == cli.calls["provider"] == 0
    scope = cli.ledger.quarantine_scope_status(cli.method["batches"][0]["scope_id"])
    assert not scope.active and scope.block_reason == "ExperimentClosed"


def _foreign_scope(cli):
    observed = cli.ledger.quarantine_observation()
    return cli.ledger.authorize_quarantine_scope(
        authorization_id=cli.method["batches"][0]["scope_id"],
        authorization_ref="synthetic-other-authorization",
        expected_unknown_ids=observed.unknown_ids,
        expected_unknown_fingerprints=observed.unknown_fingerprints,
        expected_meta_sha256=observed.meta_sha256,
        expected_authorization_history_sha256=observed.authorization_history_sha256,
        protocol_sha256="e" * 64,
        request_slots=(slot(20), slot(21)),
        additional_cap_usd=Decimal(".06"),
    )


def test_cli_existing_foreign_scope_is_rejected_without_closing_it(cli):
    foreign = _foreign_scope(cli)
    # Emulate a caller presenting a method prepared against this synthetic
    # ledger. The real CLI must still enforce fresh scope IDs before cleanup.
    cli.method["ledger_before"] = ledger_observation(cli.path)
    cli.method["quarantine_before"] = json.loads(
        json.dumps(asdict(cli.ledger.quarantine_observation()), default=str)
    )
    assert _main(cli) == 2
    assert cli.calls["batch_runs"] == cli.calls["provider"] == 0
    assert cli.ledger.quarantine_scope_status(foreign.authorization_id) == foreign
    assert foreign.active


def test_cli_cleanup_rejects_foreign_registration_even_when_id_matches(cli):
    foreign = _foreign_scope(cli)
    with pytest.raises(ValueError, match="^RealIndexScopeOwnershipRejected$"):
        cli.module.close_owned_scope(
            cli.ledger, foreign.authorization_id, "f" * 64, cli.method["authorization_ref"]
        )
    assert cli.ledger.quarantine_scope_status(foreign.authorization_id) == foreign


def test_index_drift_before_key_cannot_allocate_a_scope(cli, monkeypatch):
    before = ledger_observation(cli.path)

    def reject(*_args):
        raise ValueError("synthetic-index-drift-private")

    monkeypatch.setattr(cli.module, "validate_registered_indexes", reject)
    assert _main(cli) == 2
    assert cli.calls == {"credentials": 0, "batch_runs": 0, "provider": 0}
    assert ledger_observation(cli.path) == before
    assert _scope_count(cli.path) == 0


def test_index_drift_between_batches_closes_first_and_blocks_second(cli, monkeypatch):
    cli.method["batches"].append(
        {**cli.method["batches"][0], "batch_id": "second", "scope_id": "second-scope"}
    )
    validations = []

    def validate(*_args):
        validations.append(True)
        if len(validations) == 3:
            raise ValueError("synthetic-index-drift-private")
        return {}

    monkeypatch.setattr(cli.module, "validate_registered_indexes", validate)
    assert _main(cli) == 2
    assert cli.calls == {"credentials": 1, "batch_runs": 1, "provider": 0}
    assert not cli.ledger.quarantine_scope_status(cli.method["batches"][0]["scope_id"]).active
    assert _scope_count(cli.path) == 1


def test_source_drift_after_reservation_checkpoint_blocks_actual_send(cli, monkeypatch):
    def run(_method, _batch, *_args, **kwargs):
        monkeypatch.setattr(
            cli.module, "source_observation", lambda *_args: {**cli.source, "source_clean": False}
        )
        kwargs["checkpoint"]({"event": "reserved_before_transport"})
        cli.calls["provider"] += 1
        return cli.run_batch(_method, _batch)

    monkeypatch.setattr(cli.module, "run_real_index_batch", run)
    assert _main(cli) == 2
    assert cli.calls["provider"] == 0
    assert not cli.ledger.quarantine_scope_status(cli.method["batches"][0]["scope_id"]).active
