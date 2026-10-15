"""Finite retrieval comparison controls use disposable ledgers and offline inputs.

Shared lifecycle scenarios run against the actual retrieval CLI. The baseline
method and provider are explicit doubles; registration slots, journal checks,
authorization, closure and the archived payload preflight remain real.
"""

import importlib.util
import json
import sqlite3
from collections import Counter
from copy import deepcopy
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

import pytest
import test_dev_rag_model_cli as controls
import test_source_capacity_model_cli as lifecycle
from test_budget_quarantine_scope import SCOPE, authorize, old_rows, reserve, slot
from test_budget_quarantine_scope import multiple_holds as multiple_holds

from agent_app.testing.dev_three_model_probe import ledger_observation
from agent_app.testing.http_pilot_runtime import offline_network

ROOT = Path(__file__).resolve().parents[1]
ARMS = ("native_top5", "candidate_relevance")
RECEIPTS = (
    "dev_rag_coverage_v1",
    "core_resource_guidance_v1",
    "core_repeat_repair_v1",
    "core_source_capacity_v1",
    "core_compact_plan_v1",
)


def _module(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "relevance_cli_disposable_control", ROOT / "scripts/retrieval_relevance_model_probe.py"
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


def test_complete_run_closes_scope_and_preserves_prior_ledger(cli):
    controls.test_cli_complete_final_batch_closes_real_scope_and_binds_ledger_journal(cli)
    receipt = controls._read(cli.destination / "receipt.json")
    assert receipt["retrieval_relevance_comparison"] and receipt["same_native_index_both_arms"]
    assert receipt["resource_guidance"] is False and receipt["source_capacity"] is False
    assert receipt["repair_repeated_queries"] is True
    assert receipt["c5_reconciled"] is False and receipt["human_usefulness"] is None


@pytest.mark.parametrize("failure", ["incomplete_accounting", "stopped", "unvisited_job"])
def test_incomplete_accounting_or_visit_cannot_succeed(cli, monkeypatch, failure):
    controls.test_cli_incomplete_last_batch_never_returns_success(cli, monkeypatch, failure)


def test_route_quality_is_separate_from_settled_accounting(cli, monkeypatch):
    controls.test_cli_semantic_route_failure_is_separate_from_complete_operational_accounting(
        cli, monkeypatch
    )


@pytest.mark.parametrize(
    "scenario",
    [
        "test_cli_source_drift_before_credentials_stops_without_authorization",
        "test_cli_source_drift_before_next_batch_cannot_authorize_or_run_it",
        "test_cli_final_source_drift_is_saved_and_changes_exit_status",
        "test_cli_authorization_commit_then_interrupt_cannot_leave_unused_scope_active",
        "test_index_drift_before_key_cannot_allocate_a_scope",
        "test_index_drift_between_batches_closes_first_and_blocks_second",
        "test_source_drift_after_reservation_checkpoint_blocks_actual_send",
    ],
)
def test_source_index_and_committed_scope_guards(cli, monkeypatch, scenario):
    getattr(controls, scenario)(cli, monkeypatch)


@pytest.mark.parametrize("interrupt", [KeyboardInterrupt, SystemExit])
def test_cancel_after_authorization_closes_unused_scope(cli, monkeypatch, capsys, interrupt):
    controls.test_cli_cancellation_after_authorization_permanently_closes_scope_and_journals(
        cli, monkeypatch, capsys, interrupt
    )


@pytest.mark.parametrize(
    "scenario",
    [
        "test_unknown_record_changed_after_preflight_never_reads_key_or_allocates",
        "test_new_uncertainty_closes_campaign_without_authorizing_next_pair",
        "test_final_pair_cannot_succeed_if_observer_misses_actual_new_uncertainty",
        "test_final_pair_cannot_succeed_if_observer_misses_actual_pending_reservation",
        "test_foreign_journal_append_before_key_cannot_allocate_or_dispatch",
    ],
)
def test_frozen_ledger_and_uncertainty_guards(cli, monkeypatch, scenario):
    getattr(lifecycle, scenario)(cli, monkeypatch)


@pytest.mark.parametrize("interrupt", [KeyboardInterrupt, SystemExit])
def test_cancel_after_reservation_retains_pending_hold(cli, monkeypatch, interrupt):
    lifecycle.test_cancel_after_reservation_keeps_pending_hold_and_permanently_closes(
        cli, monkeypatch, interrupt
    )


@pytest.mark.parametrize("inside_root", [False, True])
def test_rejected_output_directory_never_changes_existing_receipts(cli, monkeypatch, inside_root):
    lifecycle.test_rejected_output_folder_is_never_claimed_or_mutated(cli, monkeypatch, inside_root)


def test_existing_foreign_scope_is_rejected_without_closing_it(cli):
    controls.test_cli_existing_foreign_scope_is_rejected_without_closing_it(cli)


def test_cleanup_requires_exact_scope_digest_and_authorization(cli):
    foreign = controls._foreign_scope(cli)
    for digest, reference in (
        ("f" * 64, foreign.authorization_ref),
        (foreign.protocol_sha256, cli.method["authorization_ref"]),
    ):
        with pytest.raises(ValueError, match="^RepeatScopeOwnershipRejected$"):
            cli.module.close_owned_scope(cli.ledger, foreign.authorization_id, digest, reference)
    assert cli.ledger.quarantine_scope_status(foreign.authorization_id) == foreign
    assert foreign.active


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
    pair = {arm: deepcopy(primary) for arm in ARMS}
    return module, tmp_path, pair, calls, old


def test_both_arms_require_identical_verified_native_corpus(bindings):
    module, root, pair, calls, _ = bindings
    assert module.validate_registered_indexes(root, pair) == pair
    assert len(calls) == 1


@pytest.mark.parametrize("change", ["old", "path", "snapshot", "hash", "extra", "missing"])
def test_corpus_swap_or_unregistered_arm_is_rejected(bindings, change):
    module, root, pair, _calls, old = bindings
    if change == "old":
        pair["candidate_relevance"] = old
    elif change in {"path", "snapshot", "hash"}:
        key = {"path": "path", "snapshot": "snapshot_id", "hash": "manifest_sha256"}[change]
        pair["candidate_relevance"][key] = "different"
    elif change == "extra":
        pair["unregistered"] = deepcopy(pair["candidate_relevance"])
    else:
        del pair["native_top5"]
    with pytest.raises(ValueError, match="^RelevanceRegistrationRejected$"):
        module.validate_registered_indexes(root, pair)


def test_archived_actual_and_repair_contexts_check_common_wire_without_mutation(monkeypatch):
    module = _module(monkeypatch)
    paths = [ROOT / "experiments" / folder / "model-live-receipt-v1.json" for folder in RECEIPTS]
    before = {path: path.read_bytes() for path in paths}
    configured = module.configured_grounded_messages
    seen = []

    def observe(config, request, context):
        seen.append((config.grounded_compact_plan, context.attempt_index))
        assert config.grounded_decision_contracts and config.grounded_source_selection_reminder
        assert not config.grounded_source_capacity and not config.grounded_resource_guidance
        return configured(config, request, context)

    monkeypatch.setattr(module, "configured_grounded_messages", observe)
    with offline_network():
        report = module.payload_preflight(ROOT)
    assert report["accepted"] and report["archived_actual_requests"] == 107
    assert report["common_wire_size_checks"] == len(seen) == 214
    assert Counter(compact for compact, _ in seen) == {True: 214}
    assert report["max_utf8_with_margin"] <= report["guard"] == 32768
    assert report["resource_guidance"] is False and report["source_capacity"] is False
    assert report["full_current_request_preserved"] is True
    assert report["future_unobserved_refinements_covered"] is False
    assert report["actual_sends"] == 0
    assert {path: path.read_bytes() for path in paths} == before


def test_preflight_checks_compact_repair_size_under_the_same_input_limit(monkeypatch):
    module = _module(monkeypatch)
    configured = module.configured_grounded_messages
    rejected = []

    def oversized(config, request, context):
        messages = configured(config, request, context)
        if config.grounded_compact_plan and context.attempt_index == 2:
            rejected.append(True)
            return ({"role": "system", "content": "x" * 32768}, messages[1])
        return messages

    monkeypatch.setattr(module, "configured_grounded_messages", oversized)
    with offline_network(), pytest.raises(ValueError, match="^RelevancePayloadRejected$"):
        module.payload_preflight(ROOT)
    assert rejected == [True]


def test_preflight_cannot_reduce_input_by_dropping_current_request_evidence(monkeypatch):
    module = _module(monkeypatch)
    configured = module.configured_grounded_messages

    def dropped(config, request, context):
        messages = configured(config, request, context)
        if not config.grounded_compact_plan:
            return messages
        payload = json.loads(messages[1]["content"])
        assert payload["request"]["evidence"]["hits"]
        payload["request"]["evidence"]["hits"] = []
        return (messages[0], {"role": "user", "content": json.dumps(payload)})

    monkeypatch.setattr(module, "configured_grounded_messages", dropped)
    with offline_network(), pytest.raises(ValueError, match="^RelevancePayloadRejected$"):
        module.payload_preflight(ROOT)


def test_actual_method_balances_only_registered_retrieval_package(multiple_holds, monkeypatch):
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
    with offline_network():
        method = module.build_method(ROOT, path)
    assert path.read_bytes() == before
    assert method["ledger_journal_before"] == module.ledger_journal_snapshot(path)
    assert method["protocol_id"] == "retrieval-relevance-model-v1"
    assert method["experiment_id"] == "retrieval-relevance-2026-10-15-v1"
    assert method["authorization_ref"] == "user-2026-10-15-retrieval-relevance"
    assert method["campaign_scope_cap_usd"] == "0.36"
    assert method["indexes"]["native_top5"] == method["indexes"]["candidate_relevance"]
    assert len(method["fresh_request_ids"]) == len(set(method["fresh_request_ids"])) == 48
    assert len(method["fresh_scope_ids"]) == len(set(method["fresh_scope_ids"])) == 6
    assert all(scope.startswith("user-rag-relevance-v1-") for scope in method["fresh_scope_ids"])
    fixtures = module.fixtures_for(ROOT, {"protocol_id": "core-stability-v1"})
    prior_ids = {
        item.request_id
        for batch in prior["batches"]
        for item in module.quality_slots(prior, batch, fixtures)
    }
    assert not set(method["fresh_request_ids"]) & prior_ids
    assert [b["jobs"][0]["case_id"] for b in method["batches"]] == [
        "dev-case-a",
        "dev-case-b",
        "dev-case-c",
        "dev-case-c",
        "dev-case-b",
        "dev-case-a",
    ]
    assert [[job["arm"] for job in batch["jobs"]] for batch in method["batches"]] == [
        list(ARMS),
        list(reversed(ARMS)),
        list(ARMS),
        list(reversed(ARMS)),
        list(ARMS),
        list(reversed(ARMS)),
    ]
    for batch in method["batches"]:
        assert batch["max_request_slots"] == 8
        assert Decimal(batch["worst_reserved_usd"]) <= Decimal("0.06")
        slots = module.quality_slots(method, batch, fixtures)
        assert batch["request_slots_sha256"] == module.slots_sha256(slots)
        for job in batch["jobs"]:
            assert job["compact_plan"] is True
            assert job["retrieval_candidate_multiplier"] == (
                5 if job["arm"] == "candidate_relevance" else 1
            )
            assert job["retrieval_selection_policy"] == (
                "query_relevance_v1" if job["arm"] == "candidate_relevance" else "native"
            )
            assert job["repair_repeated_queries"] is True
            assert job["resource_guidance"] is False and job["source_capacity"] is False
            assert job["decision_contracts"] and job["source_selection_reminder"]
            assert job["max_output_tokens"] == 1024 and job["input_token_reserve"] == 32768
    assert sum(Decimal(batch["worst_reserved_usd"]) for batch in method["batches"]) <= Decimal(
        "0.36"
    )
    assert (module.FOLDER / "protocol-v1.json").as_posix() in method["input_pins"]
    assert "scripts/retrieval_relevance_model_probe.py" in method["input_pins"]
    for folder in RECEIPTS:
        assert f"experiments/{folder}/model-live-receipt-v1.json" in method["input_pins"]
    assert method["offline_payload_preflight"]["common_wire_size_checks"] == 214


@pytest.mark.parametrize("state", ["unused_closed", "reserved", "settled", "uncertain"])
def test_allocated_identity_is_never_fresh_again_even_without_provider_send(
    multiple_holds, monkeypatch, state
):
    module = _module(monkeypatch)
    ledger, path, _ = multiple_holds
    registered = slot(10)
    before = path.read_bytes()
    module.validate_fresh_identities(path, {registered.request_id}, {SCOPE})
    assert path.read_bytes() == before
    authorize(ledger, registered=(registered,))
    if state == "unused_closed":
        ledger.close_quarantine_scope(SCOPE)
        assert ledger.get(registered.request_id) is None
    else:
        reserve(ledger, registered)
        if state == "settled":
            ledger.settle(
                registered.request_id, cost_usd=Decimal("0.001"), input_tokens=100, output_tokens=20
            )
        elif state == "uncertain":
            ledger.mark_uncertain(registered.request_id, error_code="SyntheticWireUnknown")
    after = path.read_bytes()
    with pytest.raises(ValueError, match="^RepeatIdentityAlreadyAllocated$"):
        module.validate_fresh_identities(path, {registered.request_id}, {"another-scope"})
    with pytest.raises(ValueError, match="^RepeatIdentityAlreadyAllocated$"):
        module.validate_fresh_identities(path, {slot(20).request_id}, {SCOPE})
    assert path.read_bytes() == after


def test_journal_reads_without_mutation_and_accepts_only_owned_new_rows(
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
    ledger.settle(slot().request_id, cost_usd=Decimal("0.001"), input_tokens=100, output_tokens=20)
    ledger.close_quarantine_scope(SCOPE)
    module.validate_ledger_journal(path, baseline, {slot().request_id}, {SCOPE})


@pytest.mark.parametrize("mutation", ["old_event", "foreign_scope", "schema", "deleted_row"])
def test_full_journal_rejects_old_history_or_foreign_append(multiple_holds, monkeypatch, mutation):
    module = _module(monkeypatch)
    ledger, path, _ = multiple_holds
    baseline = module.ledger_journal_snapshot(path)
    if mutation == "foreign_scope":
        authorize(ledger, registered=(slot(20),))
    else:
        with sqlite3.connect(path) as connection:
            if mutation == "old_event":
                connection.execute(
                    "UPDATE ledger_events SET error_code=? WHERE request_id=?",
                    ("SyntheticDrift", "synthetic-legacy-slot"),
                )
            elif mutation == "schema":
                connection.execute("CREATE TABLE synthetic_unowned_rows(value TEXT)")
            else:
                connection.execute(
                    "DELETE FROM ledger_events WHERE request_id=?", ("synthetic-legacy-slot",)
                )
    with pytest.raises(ValueError, match="^RepeatJournalRejected$"):
        module.validate_ledger_journal(path, baseline, {slot(10).request_id}, {"future-scope"})


def test_old_settled_record_drift_is_detected_even_when_unknown_hash_is_unchanged(
    multiple_holds, monkeypatch
):
    module = _module(monkeypatch)
    ledger, path, _ = multiple_holds
    authorize(ledger, registered=(slot(),))
    reserve(ledger)
    ledger.settle(slot().request_id, cost_usd=Decimal("0.001"), input_tokens=100, output_tokens=20)
    ledger.close_quarantine_scope(SCOPE)
    baseline = module.ledger_journal_snapshot(path)
    old = old_rows(path)
    observed = ledger_observation(path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE reservations SET output_tokens=21 WHERE request_id=?", (slot().request_id,)
        )
    assert old_rows(path) == old
    assert ledger_observation(path)["unknown_sha256"] == observed["unknown_sha256"]
    with pytest.raises(ValueError, match="^RepeatJournalRejected$"):
        module.validate_ledger_journal(path, baseline, {slot(10).request_id}, {"future-scope"})
