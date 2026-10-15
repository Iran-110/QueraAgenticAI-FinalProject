"""Finite JSON transport/readability study controls use disposable ledgers.

Shared lifecycle scenarios run against the actual retrieval CLI. The baseline
method and provider are explicit doubles; registration slots, journal checks,
authorization, closure and the archived payload preflight remain real.
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
import test_source_capacity_model_cli as lifecycle
from test_budget_quarantine_scope import SCOPE, authorize, old_rows, reserve, slot
from test_budget_quarantine_scope import multiple_holds as multiple_holds
from test_real_index_probe import native_indexes as native_indexes

from agent_app.testing.dev_three_model_probe import ledger_observation
from agent_app.testing.http_pilot_runtime import offline_network

ROOT = Path(__file__).resolve().parents[1]
ARMS = ("json_object_canary", "json_object_off", "json_object_on")
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
        "json_readability_cli_disposable_control", ROOT / "scripts/core_json_readability_probe.py"
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
    assert receipt["renderer_ask_source_background"]
    assert receipt["same_native_index_as_R4c_treatment"]
    assert receipt["json_object_transport_comparison"] and receipt["no_model_prompt_treatment"]
    assert receipt["renderer_concise_user_draft"] is True
    assert receipt["compact_plan"] is True
    assert receipt["named_profile_through_http"] is True
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
        pair["json_object_on"] = old
    elif change in {"path", "snapshot", "hash"}:
        key = {"path": "path", "snapshot": "snapshot_id", "hash": "manifest_sha256"}[change]
        pair["json_object_on"][key] = "different"
    elif change == "extra":
        pair["unregistered"] = deepcopy(pair["json_object_on"])
    else:
        del pair["json_object_on"]
    with pytest.raises(ValueError, match="^JsonReadabilityRegistrationRejected$"):
        module.validate_registered_indexes(root, pair)


@pytest.fixture
def method_inputs(tmp_path, monkeypatch, multiple_holds):
    module = _module(monkeypatch)
    ledger, path, _ = multiple_holds
    prior = controls._read(ROOT / module.COVERAGE_FOLDER / "live-method-v1.json")
    prior["input_pins"] = {}
    prior["ledger_before"] = ledger_observation(path)
    prior["quarantine_before"] = json.loads(
        json.dumps(asdict(ledger.quarantine_observation()), default=str)
    )
    root = tmp_path / "synthetic-method-inputs"
    paths = (
        module.FOLDER / "protocol-v1.json",
        module.FOLDER / "offline-render-replay-v1.json",
        module.FOLDER / "semantic-review-preparation-v1.json",
        module.PARENT_FOLDER / "protocol-v1.json",
        module.PARENT_FOLDER / "model-live-receipt-v1.json",
        module.PARENT_FOLDER / "route-display-amendment-v1.json",
        module.PARENT_FOLDER / "semantic-review-preparation-v1.json",
        Path("experiments/retrieval_relevance_v1/semantic-review-preparation-v1.json"),
        Path("experiments/dev_rag_coverage_v1/model-live-receipt-v1.json"),
        Path("experiments/core_resource_guidance_v1/model-live-receipt-v1.json"),
        Path("experiments/core_repeat_repair_v1/model-live-receipt-v1.json"),
        Path("experiments/core_source_capacity_v1/model-live-receipt-v1.json"),
        Path("docs/pr55-evidence-review.fa.md"),
        Path("scripts/core_json_readability_probe.py"),
        Path("scripts/json_readability_render_replay.py"),
        Path("scripts/core_ask_background_model_probe.py"),
        Path("scripts/retrieval_relevance_model_probe.py"),
        Path("scripts/core_repeat_model_probe.py"),
        Path("scripts/core_compact_model_probe.py"),
        Path("scripts/core_source_capacity_model_probe.py"),
    )
    for relative in paths:
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        original = ROOT / relative
        destination.write_bytes(original.read_bytes() if original.is_file() else b"{}")
    fixtures = module.fixtures_for(ROOT, {"protocol_id": "core-stability-v1"})
    monkeypatch.setattr(module, "fixtures_for", lambda *_args: fixtures)
    monkeypatch.setattr(module, "coverage_build_method", lambda *_args: deepcopy(prior))
    monkeypatch.setattr(module, "validate_registered_indexes", lambda _r, indexes: indexes)
    monkeypatch.setattr(module, "payload_preflight", lambda *_args: {"actual_sends": 0})
    return module, root, path, prior, fixtures


def test_fresh_method_registers_canary_and_all_balanced_pairs_before_any_send(method_inputs):
    module, root, path, prior, fixtures = method_inputs
    before = path.read_bytes()
    with offline_network():
        method = module.build_method(root, path)
    assert path.read_bytes() == before
    assert method["ledger_journal_before"] == module.ledger_journal_snapshot(path)
    assert method["protocol_id"] == "core-json-readability-model-v1"
    assert method["experiment_id"] == "core-json-readability-2026-10-15-v1"
    assert method["authorization_ref"] == "user-2026-10-15-json-readability-quality-comparison"
    assert method["canary_scope_cap_usd"] == "0.03" and method["scope_cap_usd"] == "0.06"
    assert method["campaign_scope_cap_usd"] == "0.39"
    assert method["no_model_prompt_treatment"] and method["json_object_transport_comparison"]
    assert method["renderer_ask_source_background"] and method["renderer_concise_user_draft"]
    assert method["named_profile_through_http"]
    assert set(method["indexes"]) == set(ARMS)
    assert all(
        binding == prior["indexes"]["new_18_sources"] for binding in method["indexes"].values()
    )
    assert len(method["fresh_request_ids"]) == len(set(method["fresh_request_ids"])) == 52
    assert len(method["fresh_scope_ids"]) == len(set(method["fresh_scope_ids"])) == 7
    assert all(
        scope.startswith("user-core-json-readability-v1-") for scope in method["fresh_scope_ids"]
    )
    parent = controls._read(ROOT / module.PARENT_FOLDER / "live-method-v1.json")
    assert not set(method["fresh_request_ids"]) & set(parent["fresh_request_ids"])
    assert not set(method["fresh_scope_ids"]) & set(parent["fresh_scope_ids"])
    canary, *pairs = method["batches"]
    assert canary["stage"] == "canary" and canary["scope_cap_usd"] == "0.03"
    assert canary["batch_id"] == method["canary_batch_id"]
    assert canary["jobs"][0]["case_id"] == "dev-case-a"
    assert canary["jobs"][0]["arm"] == "json_object_canary"
    assert canary["max_request_slots"] == 4
    assert [batch["jobs"][0]["case_id"] for batch in pairs] == [
        "dev-case-a",
        "dev-case-b",
        "dev-case-c",
        "dev-case-c",
        "dev-case-b",
        "dev-case-a",
    ]
    assert [[job["arm"] for job in batch["jobs"]] for batch in pairs] == [
        ["json_object_off", "json_object_on"],
        ["json_object_on", "json_object_off"],
        ["json_object_off", "json_object_on"],
        ["json_object_on", "json_object_off"],
        ["json_object_off", "json_object_on"],
        ["json_object_on", "json_object_off"],
    ]
    assert all(batch["max_request_slots"] == 8 for batch in pairs)
    for batch in method["batches"]:
        slots = module.quality_slots(method, batch, fixtures)
        assert batch["request_slots_sha256"] == module.slots_sha256(slots)
        assert Decimal(batch["worst_reserved_usd"]) <= Decimal(batch["scope_cap_usd"])
        for job in batch["jobs"]:
            assert job["grounded_json_object"] is (job["arm"] != "json_object_off")
            assert (
                job["ask_source_background"] and job["concise_user_draft"] and job["compact_plan"]
            )
            assert job["retrieval_profile"] == "candidate_relevance_v1"
            assert job["retrieval_candidate_multiplier"] == 5
            assert job["retrieval_selection_policy"] == "query_relevance_v1"
            assert job["evidence_utf8_budget_bytes"] == 12000
            assert job["repair_repeated_queries"] and job["record_native_candidates"]
            assert job["resource_guidance"] is False and job["source_capacity"] is False
            assert job["decision_contracts"] and job["source_selection_reminder"]
            assert job["max_output_tokens"] == 1024 and job["input_token_reserve"] == 32768
    assert sum(Decimal(b["scope_cap_usd"]) for b in method["batches"]) == Decimal("0.39")
    for relative in (
        module.FOLDER / "protocol-v1.json",
        module.FOLDER / "offline-render-replay-v1.json",
        module.FOLDER / "semantic-review-preparation-v1.json",
        module.PARENT_FOLDER / "model-live-receipt-v1.json",
        Path("scripts/core_json_readability_probe.py"),
    ):
        assert method["input_pins"][relative.as_posix()] == module.sha(
            (root / relative).read_bytes()
        )


@pytest.mark.parametrize(
    "change", ["extra", "bool_count", "scope_cap", "arm", "round_order", "model"]
)
def test_protocol_mutation_is_rejected_before_old_method_or_ledger_work(
    method_inputs, monkeypatch, change
):
    module, root, path, _prior, _fixtures = method_inputs
    protocol_path = root / module.FOLDER / "protocol-v1.json"
    payload = json.loads(protocol_path.read_bytes())
    if change == "extra":
        payload["unregistered"] = True
    elif change == "bool_count":
        payload["schema_version"] = True
    elif change == "scope_cap":
        payload["live"]["campaign_cap_usd"] = "5.00"
    elif change == "arm":
        payload["live"]["paired_arms"] = ["different"]
    elif change == "round_order":
        payload["live"]["case_order"][0].reverse()
    else:
        payload["live"]["model"] = "different-model"
    protocol_path.write_text(json.dumps(payload))
    monkeypatch.setattr(
        module, "coverage_build_method", lambda *_args: pytest.fail("old method read")
    )
    before = path.read_bytes()
    with (
        offline_network(),
        pytest.raises(ValueError, match="^JsonReadabilityRegistrationRejected$"),
    ):
        module.build_method(root, path)
    assert path.read_bytes() == before


def test_parent_receipt_or_frozen_method_drift_cannot_allocate(method_inputs):
    module, root, path, _prior, _fixtures = method_inputs
    method = module.build_method(root, path)
    method["batches"][0]["jobs"][0]["grounded_json_object"] = False
    method_path = root / module.METHOD
    method_path.write_text(json.dumps(method))
    with (
        offline_network(),
        pytest.raises(ValueError, match="^JsonReadabilityRegistrationRejected$"),
    ):
        module.preflight(root, path, method_path)
    (root / module.PARENT_FOLDER / "model-live-receipt-v1.json").write_text("{}")
    with (
        offline_network(),
        pytest.raises(ValueError, match="^JsonReadabilityRegistrationRejected$"),
    ):
        module.build_method(root, path)


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


@pytest.fixture
def observed_canary():
    # Explicit observation double from the exposed dev receipt; response_format
    # is changed only here. The intercepted real-gateway test below checks the
    # actual new outbound argument independently.
    result = deepcopy(
        controls._read(ROOT / "experiments/core_ask_background_v1/model-live-receipt-v1.json")[
            "batches"
        ][0]
    )
    for row in result["provider_sends"]:
        row["wire_response_format"] = "json_object"
    return result


def test_canary_gate_accepts_complete_observation_and_never_claims_semantic_quality(
    monkeypatch, observed_canary
):
    module = _module(monkeypatch)
    result = module.canary_gate(observed_canary)
    assert result["passed"] and all(result["checks"].values())
    assert result["semantic_quality_claim"] is False


@pytest.mark.parametrize(
    "failure",
    [
        "argument_absent",
        "argument_other",
        "http400",
        "length",
        "unknown_model",
        "wire_schema",
        "binding",
        "no_plan",
        "unknown_accounting",
        "null_cost",
        "stale",
        "unvisited",
        "route_failure",
    ],
)
def test_canary_gate_rejects_unsupported_ambiguous_or_incomplete_observation(
    monkeypatch, observed_canary, failure
):
    module = _module(monkeypatch)
    value = observed_canary
    if failure == "argument_absent":
        value["provider_sends"][0]["wire_response_format"] = "absent"
    elif failure == "argument_other":
        value["provider_sends"][0]["wire_response_format"] = "other"
    elif failure == "http400":
        value["provider_sends"][0]["http_status"] = 400
    elif failure == "length":
        value["provider_sends"][0]["finish_reason"] = "length"
    elif failure == "unknown_model":
        value["provider_sends"][0]["verified_returned_model"] = None
    elif failure == "wire_schema":
        value["attempts"][0]["wire_output"]["wire_schema_valid"] = False
    elif failure == "binding":
        value["attempts"][0]["wire_output"]["canonical_binding_valid"] = False
    elif failure == "no_plan":
        value["attempts"][0]["plan"] = None
    elif failure == "unknown_accounting":
        value["accounting"]["accounting_complete"] = False
    elif failure == "null_cost":
        value["accounting"]["cost_usd"] = None
    elif failure == "stale":
        value["jobs"][0]["steps"][1]["proposal"]["stale"] = True
    elif failure == "unvisited":
        value["visited_jobs"] = 0
    else:
        value["completed_routes"] = 0
    assert module.canary_gate(value)["passed"] is False


@pytest.mark.parametrize("passed", [False, True])
def test_cli_canary_gate_controls_whether_paired_scope_is_ever_allocated(
    cli, monkeypatch, observed_canary, passed
):
    first = cli.method["batches"][0]
    first.update(stage="canary", scope_cap_usd="0.03")
    first["jobs"] = [{"job_id": observed_canary["jobs"][0]["job_id"], "grounded_json_object": True}]
    second = {
        **first,
        "batch_id": "synthetic-paired-batch",
        "scope_id": "synthetic-paired-scope",
        "stage": "paired",
        "scope_cap_usd": "0.06",
    }
    cli.method["batches"].append(second)
    cli.method["fresh_request_ids"].extend([slot(20).request_id, slot(21).request_id])
    cli.method["fresh_scope_ids"].append(second["scope_id"])
    monkeypatch.setattr(
        cli.module,
        "quality_slots",
        lambda _m, b, _f: (slot(10), slot(11)) if b["stage"] == "canary" else (slot(20), slot(21)),
    )
    observed_canary["batch_id"] = first["batch_id"]
    if not passed:
        observed_canary["provider_sends"][0]["http_status"] = 400

    def run(method, batch, *args, **kwargs):
        if batch["stage"] == "canary":
            cli.calls["batch_runs"] += 1
            return deepcopy(observed_canary)
        return cli.run_batch(method, batch, *args, **kwargs)

    monkeypatch.setattr(cli.module, "run_real_index_batch", run)
    assert controls._main(cli) == (0 if passed else 2)
    assert controls._scope_count(cli.path) == (2 if passed else 1)
    assert cli.calls["batch_runs"] == (2 if passed else 1)
    receipt = controls._read(cli.destination / "receipt.json")
    assert receipt["canary_gate"]["passed"] is passed
    assert receipt["planned_batches"] == 2
    assert receipt["completed_batches"] == (2 if passed else 1)
    assert not cli.ledger.quarantine_scope_status(first["scope_id"]).active
    if not passed:
        assert not (cli.destination / second["batch_id"]).exists()
        with pytest.raises(cli.module.LedgerConflict):
            cli.ledger.quarantine_scope_status(second["scope_id"])


@pytest.mark.parametrize("json_mode", [False, True])
def test_canary_gate_reads_actual_intercepted_gateway_wire_and_full_HTTP_route(
    multiple_holds, native_indexes, monkeypatch, json_mode
):
    import test_json_readability_integration as integration

    module = _module(monkeypatch)
    actual = integration.run_real_index_batch
    seen = []

    def observe(*args, **kwargs):
        result = actual(*args, **kwargs)
        seen.append(result)
        return result

    monkeypatch.setattr(integration, "run_real_index_batch", observe)
    integration.test_quality_http_transmits_mode_and_binds_exact_concise_display(
        multiple_holds, native_indexes, json_mode
    )
    assert len(seen) == 1 and seen[0]["actual_sends"] == 2
    gate = module.canary_gate(seen[0])
    assert gate["passed"] is json_mode


@pytest.mark.parametrize(
    "change",
    [
        "swapped_observations",
        "duplicate_observation",
        "duplicate_attempt_context",
        "unregistered_context",
    ],
)
def test_canary_wire_observation_identity_is_one_to_one_with_exact_context(
    monkeypatch, observed_canary, change
):
    module = _module(monkeypatch)
    first, second = observed_canary["attempts"][:2]
    assert first["wire_output"]["request_id"] != second["wire_output"]["request_id"]
    if change == "swapped_observations":
        first["wire_output"], second["wire_output"] = second["wire_output"], first["wire_output"]
    elif change == "duplicate_observation":
        second["wire_output"] = deepcopy(first["wire_output"])
    elif change == "duplicate_attempt_context":
        second["context"] = deepcopy(first["context"])
    else:
        first["context"]["run_id"] = "synthetic-unregistered-run"
    assert module.canary_gate(observed_canary)["passed"] is False
