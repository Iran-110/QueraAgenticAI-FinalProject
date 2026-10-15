"""Finite controlled-evidence campaign controls use disposable ledgers.

Shared lifecycle scenarios run against the actual retrieval CLI. The baseline
method and provider are explicit doubles; registration slots, journal checks,
authorization, closure and the archived payload preflight remain real.
"""

import importlib.util
import json
import sqlite3
import sys
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
ARMS = ("candidate_profile",)
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
        "enum_evidence_cli_disposable_control", ROOT / "scripts/core_enum_evidence_probe.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def cli(tmp_path, monkeypatch, multiple_holds):
    module = _module(monkeypatch)
    # Test-only bridges let the old shared lifecycle controls patch their
    # historical hook names while the new production CLI calls only the fixed
    # supplier/quality runner and protected-file hashing functions.
    monkeypatch.setattr(module, "validate_registered_indexes", lambda *_args: {}, raising=False)
    monkeypatch.setattr(module, "run_real_index_batch", module.run_quality_batch, raising=False)
    monkeypatch.setattr(controls, "_module", lambda *_args: module)
    value = controls.cli.__wrapped__(tmp_path, monkeypatch, multiple_holds)
    monkeypatch.setattr(
        module,
        "validate_registered_inputs",
        lambda *args: module.validate_registered_indexes(*args),
    )
    monkeypatch.setattr(
        module,
        "run_quality_batch",
        lambda *args, **kwargs: module.run_real_index_batch(*args, **kwargs),
    )
    monkeypatch.setattr(module, "load_source_packet", lambda *_args: {})
    monkeypatch.setattr(module, "fixture_retriever_factory", lambda *_args: None)
    value.method["protected_files"] = {}
    value.method["ledger_journal_before"] = value.module.ledger_journal_snapshot(value.path)
    value.method["fresh_request_ids"] = [slot(10).request_id, slot(11).request_id]
    value.method["fresh_scope_ids"] = [value.method["batches"][0]["scope_id"]]
    return value


def test_complete_run_closes_scope_and_preserves_prior_ledger(cli):
    controls.test_cli_complete_final_batch_closes_real_scope_and_binds_ledger_journal(cli)
    receipt = controls._read(cli.destination / "receipt.json")
    assert receipt["renderer_ask_source_background"]
    assert receipt["real_RAG_retrieval"] is False
    assert receipt["controlled_fixed_evidence"] is True
    assert receipt["answer_linked_guide_fixture_only"] is True
    assert receipt["renderer_concise_user_draft"] and receipt["same_core_policy_both_arms"]
    assert receipt["grounded_json_object"] is True
    assert receipt["compact_plan"] is True
    assert receipt["resource_guidance"] is False and receipt["source_capacity"] is True
    assert receipt["repair_repeated_queries"] is False
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
def method_inputs(tmp_path, monkeypatch, multiple_holds):
    from registered_native_inputs import registered_method_inputs

    module = _module(monkeypatch)
    root = tmp_path / "synthetic-registered-inputs"
    value = registered_method_inputs(module, ROOT, root, monkeypatch, multiple_holds)
    return value


def test_fresh_controlled_method_has_exact48_fresh_slots_and_no_native_retriever(method_inputs):
    module, root, path, fixtures = method_inputs
    before = path.read_bytes()
    with offline_network():
        method = module.build_method(root, path)
    assert path.read_bytes() == before
    assert method["protocol_id"] == "core-enum-evidence-model-v1"
    assert method["experiment_id"] == "core-enum-evidence-2026-10-15-v1"
    assert method["campaign_scope_cap_usd"] == "0.36"
    assert method["controlled_fixed_evidence"] is True and method["real_RAG_retrieval"] is False
    assert method["answer_linked_guide_fixture_only"] is True
    assert "indexes" not in method
    assert len(method["fresh_request_ids"]) == len(set(method["fresh_request_ids"])) == 48
    assert len(method["fresh_scope_ids"]) == len(set(method["fresh_scope_ids"])) == 6
    parent = controls._read(ROOT / module.PARENT_FOLDER / "live-method-v1.json")
    assert not set(method["fresh_request_ids"]) & set(parent["fresh_request_ids"])
    assert [b["jobs"][0]["case_id"] for b in method["batches"]] == [
        "dev-case-a",
        "dev-case-b",
        "dev-case-c",
        "dev-case-c",
        "dev-case-b",
        "dev-case-a",
    ]
    expected = ["fixed_baseline", "fixed_guide_added"]
    for i, batch in enumerate(method["batches"]):
        assert batch["kind"] == "controlled_evidence" and batch["max_request_slots"] == 8
        assert [job["arm"] for job in batch["jobs"]] == (
            expected if i % 2 == 0 else list(reversed(expected))
        )
        slots = module.quality_slots(method, batch, fixtures)
        assert batch["request_slots_sha256"] == module.slots_sha256(slots)
        assert Decimal(batch["worst_reserved_usd"]) == Decimal("0.048660480")
        for job in batch["jobs"]:
            assert (
                job["grounded_json_object"]
                and job["concise_user_draft"]
                and job["ask_source_background"]
            )
            assert (
                job["compact_plan"]
                and job["source_selection_reminder"]
                and job["decision_contracts"]
            )
            assert job["repair_repeated_queries"] is False and job["source_capacity"] is True
            assert job["resource_guidance"] is False
            assert job["input_token_reserve"] == 32768 and job["max_output_tokens"] == 1024
            assert "retrieval_profile" not in job and "retrieval_candidate_multiplier" not in job
    assert len(method["protected_files"]) == 19
    assert all(not name.startswith("runtime/") for name in method["input_pins"])
    for name, digest in method["protected_files"].items():
        assert module.sha((root / name).read_bytes()) == digest
    assert method["ledger_journal_before"] == module.ledger_journal_snapshot(path)


@pytest.mark.parametrize("change", ["extra", "bool_count", "scope_cap", "model", "arm_order"])
def test_protocol_drift_rejected_before_packet_or_ledger_work(method_inputs, monkeypatch, change):
    module, root, path, _fixtures = method_inputs
    protocol_path = root / module.FOLDER / "protocol-v1.json"
    value = json.loads(protocol_path.read_bytes())
    if change == "extra":
        value["unregistered"] = True
    elif change == "bool_count":
        value["schema_version"] = True
    elif change == "scope_cap":
        value["live"]["campaign_cap_usd"] = "5.00"
    elif change == "model":
        value["live"]["model"] = "different-model"
    else:
        value["live"]["paired_arm_order"][0].reverse()
    protocol_path.write_text(json.dumps(value))
    monkeypatch.setattr(module, "load_source_packet", lambda *_args: pytest.fail("packet read"))
    before = path.read_bytes()
    with offline_network(), pytest.raises(ValueError, match="^EnumEvidenceRegistrationRejected$"):
        module.build_method(root, path)
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "change", ["real_index", "fixture_gold", "parent_receipt", "offline_rejected", "packet"]
)
def test_protected_or_source_drift_blocks_new_registration(method_inputs, change):
    module, root, path, _fixtures = method_inputs
    if change == "real_index":
        target = root / "runtime/dev-rag-coverage-2026-10-14-v1/coverage-18/chroma.sqlite3"
    elif change == "fixture_gold":
        target = root / "data/evaluation/dev-three-v1/cases/enum-8129-v1.json"
    elif change == "parent_receipt":
        target = root / module.PARENT_FOLDER / "model-live-receipt-v1.json"
    elif change == "offline_rejected":
        target = root / module.FOLDER / "offline-boundary-review-v1.json"
    else:
        target = root / module.FOLDER / "source-packet-v1.json"
    target.write_text("{}")
    before = path.read_bytes()
    with offline_network(), pytest.raises((ValueError, KeyError)):
        module.build_method(root, path)
    assert path.read_bytes() == before


def test_changed_frozen_method_does_not_silently_regenerate(method_inputs):
    module, root, path, _fixtures = method_inputs
    method = module.build_method(root, path)
    method["batches"][0]["jobs"][0]["grounded_json_object"] = False
    method_path = root / module.METHOD
    method_path.write_text(json.dumps(method))
    with offline_network(), pytest.raises(ValueError, match="^EnumEvidenceRegistrationRejected$"):
        module.preflight(root, path, method_path)


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


@pytest.mark.parametrize(
    "change", ["method", "ledger", "prepare_and_live", "missing_env", "missing_output"]
)
def test_invalid_live_arguments_never_read_credentials_or_register_scope(cli, monkeypatch, change):
    arguments = list(sys.argv)
    if change == "method":
        arguments[arguments.index("--method") + 1] = str(cli.destination / "foreign-method.json")
    elif change == "ledger":
        arguments[arguments.index("--ledger") + 1] = str(cli.root / "foreign-ledger.sqlite3")
    elif change == "prepare_and_live":
        arguments.append("--prepare")
    else:
        flag = "--env-file" if change == "missing_env" else "--output-dir"
        position = arguments.index(flag)
        del arguments[position : position + 2]
    monkeypatch.setattr(sys, "argv", arguments)
    before = cli.path.read_bytes()
    assert controls._main(cli) == 2
    assert cli.calls == {"credentials": 0, "batch_runs": 0, "provider": 0}
    assert cli.path.read_bytes() == before
    assert controls._scope_count(cli.path) == 0
    assert not cli.destination.exists()


def test_read_only_status_reports_single_arm_cap_without_credentials(cli, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", [item for item in sys.argv if item != "--live"])
    before = cli.path.read_bytes()
    assert controls._main(cli) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["eligible_read_only"] is True
    assert report["batches"] == 1 and report["max_sends"] == 2
    assert report["cap_usd"] == "0.06" and report["actual_sends"] == 0
    assert report["c5_reconciled"] is False
    assert cli.path.read_bytes() == before
    assert cli.calls == {"credentials": 0, "batch_runs": 0, "provider": 0}
    assert not cli.destination.exists()


def test_prepare_writes_only_one_new_method_without_reading_credentials(cli, monkeypatch, capsys):
    (cli.root / cli.module.METHOD).parent.mkdir(parents=True)
    called = []
    monkeypatch.setattr(
        sys, "argv", [item for item in sys.argv if item != "--live"] + ["--prepare"]
    )
    monkeypatch.setattr(
        cli.module, "build_method", lambda *_args: called.append(True) or cli.method
    )
    before = cli.path.read_bytes()
    assert controls._main(cli) == 0
    assert json.loads(capsys.readouterr().out) == {"prepared": True, "actual_sends": 0}
    assert called == [True]
    method_path = cli.root / cli.module.METHOD
    first = method_path.read_bytes()
    assert controls._read(method_path) == cli.method
    assert cli.path.read_bytes() == before
    assert cli.calls == {"credentials": 0, "batch_runs": 0, "provider": 0}
    assert controls._main(cli) == 2
    assert method_path.read_bytes() == first
    assert controls._scope_count(cli.path) == 0
    assert not cli.destination.exists()


def test_transport_checkpoint_records_only_owned_preserved_journal(cli, monkeypatch):
    expected = []

    def checkpoint_only(method, batch, *args, checkpoint, **kwargs):
        result = cli.run_batch(method, batch, *args, **kwargs)
        expected.append(ledger_observation(cli.path))
        checkpoint({"event": "reserved_before_transport", "synthetic_observation": True})
        return result

    monkeypatch.setattr(cli.module, "run_real_index_batch", checkpoint_only)
    assert controls._main(cli) == 0
    item = controls._read(cli.destination / "synthetic-final-batch/checkpoint-001.json")
    assert item["ledger_before_transport"] == expected[0]
    assert len(item["ledger_journal_sha256"]) == 64
    assert controls.SECRET not in json.dumps(item)


@pytest.mark.parametrize("wire_format", ["absent", "other", None])
def test_wrong_actual_JSON_wire_cannot_complete_a_registered_controlled_batch(
    cli, monkeypatch, wire_format
):
    def wrong_wire(*args, **kwargs):
        value = cli.run_batch(*args, **kwargs)
        value["provider_sends"] = [{"wire_response_format": wire_format}]
        return value

    monkeypatch.setattr(cli.module, "run_real_index_batch", wrong_wire)
    assert controls._main(cli) == 2
    receipt = controls._read(cli.destination / "receipt.json")
    assert receipt["batches"][0]["json_object_wire_observed"] is False
    assert not cli.ledger.quarantine_scope_status(cli.method["batches"][0]["scope_id"]).active


@pytest.mark.parametrize(
    "artifact", ["offline-boundary-review-v1.json", "protected-inputs-v1.json"]
)
def test_readonly_preparation_send_counts_are_strict_integers(method_inputs, artifact):
    module, root, path, _fixtures = method_inputs
    target = root / module.FOLDER / artifact
    value = json.loads(target.read_bytes())
    value["actual_sends"] = False
    target.write_text(json.dumps(value))
    before = path.read_bytes()
    with offline_network(), pytest.raises(ValueError, match="^EnumEvidenceRegistrationRejected$"):
        module.build_method(root, path)
    assert path.read_bytes() == before


@pytest.mark.parametrize("protected", [{}, {"../outside": "a" * 64}, {"safe": None}, {1: "a" * 64}])
def test_protected_input_paths_are_nonempty_current_root_hash_bindings(
    tmp_path, monkeypatch, protected
):
    module = _module(monkeypatch)
    with pytest.raises(ValueError, match="^EnumEvidenceRegistrationRejected$"):
        module.validate_registered_inputs(tmp_path, protected)


@pytest.mark.parametrize(
    "change", ["schema_type", "protocol_hash", "before_paid", "source_integrity", "extra"]
)
def test_capacity_amendment_is_exact_registered_no_excerpt_shortening(method_inputs, change):
    module, root, path, _fixtures = method_inputs
    target = root / module.FOLDER / "capacity-amendment-v1.json"
    value = json.loads(target.read_bytes())
    if change == "schema_type":
        value["schema_version"] = True
    elif change == "protocol_hash":
        value["original_protocol_sha256"] = "f" * 64
    elif change == "before_paid":
        value["registered_before_paid_calls"] = 1
    elif change == "source_integrity":
        value["no_source_excerpt_or_metadata_shortening"] = False
    else:
        value["unregistered"] = True
    target.write_text(json.dumps(value))
    before = path.read_bytes()
    with offline_network(), pytest.raises(ValueError, match="^EnumEvidenceRegistrationRejected$"):
        module.build_method(root, path)
    assert path.read_bytes() == before


def test_pre_dispatch_zero_is_not_a_JSON_transport_observation(cli, monkeypatch):
    def pre_dispatch_zero(*args, **kwargs):
        value = cli.run_batch(*args, **kwargs)
        value["completed_routes"] = 0
        value["attempts"] = [
            {
                "error_code": "ContextLimitExceeded",
                "pre_dispatch_stop": {
                    "stop_code": "ContextLimitExceeded",
                    "transport_absent_before": True,
                    "transport_absent_after": True,
                },
            }
        ]
        value["accounting"]["requests"] = [
            {
                "request_id": slot(10).request_id,
                "status": "skipped_before_reservation",
                "cost_usd": "0",
            }
        ]
        return value

    monkeypatch.setattr(cli.module, "run_real_index_batch", pre_dispatch_zero)
    assert controls._main(cli) == 0
    receipt = controls._read(cli.destination / "receipt.json")
    assert receipt["batches"][0]["actual_sends"] == 0
    assert receipt["batches"][0]["json_object_wire_observed"] is None
    assert receipt["batches"][0]["completed_routes"] == 0
    assert cli.ledger.get(slot(10).request_id) is None


@pytest.mark.parametrize(
    "artifact,field,value",
    [
        ("offline-boundary-review-v1.json", "source_capacity", False),
        ("offline-boundary-review-v1.json", "actual_search", True),
        ("offline-boundary-review-v1.json", "permitted_bound_violations", 1),
        ("offline-boundary-review-v1.json", "is_model_quality_score", True),
        ("offline-boundary-initial-v1.json", "accepted", True),
        ("offline-boundary-initial-v1.json", "permitted_bound_violations", 0),
    ],
)
def test_final_readiness_and_original_offline_failure_are_distinct_pinned_conditions(
    method_inputs, artifact, field, value
):
    module, root, path, _fixtures = method_inputs
    target = root / module.FOLDER / artifact
    report = json.loads(target.read_bytes())
    report[field] = value
    target.write_text(json.dumps(report))
    before = path.read_bytes()
    with offline_network(), pytest.raises(ValueError, match="^EnumEvidenceRegistrationRejected$"):
        module.build_method(root, path)
    assert path.read_bytes() == before
