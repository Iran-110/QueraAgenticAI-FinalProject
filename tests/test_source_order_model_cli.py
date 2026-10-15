"""Fresh controlled-study CLI/lifecycle with disposable SQLite and no API/key."""

import importlib.util
import json
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
import test_dev_rag_model_cli as controls
import test_enum_evidence_model_cli as parent_controls
import test_source_capacity_model_cli as lifecycle
from test_budget_quarantine_scope import SCOPE, authorize, reserve, slot
from test_budget_quarantine_scope import multiple_holds as multiple_holds

from agent_app.contracts import RetrievalRequest
from agent_app.reasoning.source_selection import COMPLEMENTARY_SOURCE_POLICY
from agent_app.testing.enum_evidence import EnumEvidenceRejected
from agent_app.testing.enum_evidence import fixture_retriever_factory as parent_factory
from agent_app.testing.finite_controlled_probe import actual_json_wire_observation
from agent_app.testing.http_pilot_runtime import offline_network
from agent_app.testing.source_order import SourceOrderRejected, fixture_retriever_factory

ROOT = Path(__file__).resolve().parents[1]


def _module(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "source_order_cli_disposable_control", ROOT / "scripts/core_source_order_probe.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def cli(tmp_path, monkeypatch, multiple_holds):
    module = _module(monkeypatch)
    monkeypatch.setattr(parent_controls, "_module", lambda *_args: module)
    value = parent_controls.cli.__wrapped__(tmp_path, monkeypatch, multiple_holds)
    monkeypatch.setattr(module, "load_packet", lambda: {})
    return value


def test_complete_run_closes_scope_preserves_journal_and_separates_quality(cli):
    controls.test_cli_complete_final_batch_closes_real_scope_and_binds_ledger_journal(cli)
    receipt = controls._read(cli.destination / "receipt.json")
    assert receipt["same_complete_record_set_both_arms"] is True
    assert receipt["common_evidence_condition"] == "fixed_guide_added"
    assert receipt["common_prompt_both_arms"] is True
    assert receipt["real_RAG_retrieval"] is False
    assert receipt["controlled_fixed_evidence"] is True
    assert receipt["human_usefulness"] is None and receipt["held_out_test"] is False
    assert receipt["old_journal_preserved"] and receipt["no_pending_reservations"]
    assert receipt["old_holds_and_authorization_history_preserved"]


@pytest.mark.parametrize("failure", ["incomplete_accounting", "stopped", "unvisited_job"])
def test_incomplete_accounting_or_unvisited_jobs_cannot_complete(cli, monkeypatch, failure):
    controls.test_cli_incomplete_last_batch_never_returns_success(cli, monkeypatch, failure)


def test_settled_accounting_is_not_semantic_route_success(cli, monkeypatch):
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
def test_source_protected_bytes_and_checkpoint_guards(cli, monkeypatch, scenario):
    getattr(controls, scenario)(cli, monkeypatch)


@pytest.mark.parametrize("interrupt", [KeyboardInterrupt, SystemExit])
def test_cancellation_after_authorization_always_closes_owned_scope(
    cli, monkeypatch, capsys, interrupt
):
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
def test_all_old_history_and_new_uncertainty_guards(cli, monkeypatch, scenario):
    getattr(lifecycle, scenario)(cli, monkeypatch)


@pytest.mark.parametrize("interrupt", [KeyboardInterrupt, SystemExit])
def test_cancelled_reserved_slot_remains_durable_and_cannot_resume(cli, monkeypatch, interrupt):
    lifecycle.test_cancel_after_reservation_keeps_pending_hold_and_permanently_closes(
        cli, monkeypatch, interrupt
    )


@pytest.mark.parametrize("inside_root", [False, True])
def test_rejected_destination_never_claims_or_mutates_foreign_folder(cli, monkeypatch, inside_root):
    lifecycle.test_rejected_output_folder_is_never_claimed_or_mutated(cli, monkeypatch, inside_root)


def test_foreign_scope_not_closed_even_if_presented_id_matches(cli):
    controls.test_cli_existing_foreign_scope_is_rejected_without_closing_it(cli)


def test_exact_digest_and_authorization_required_for_cleanup(cli):
    parent_controls.test_cleanup_requires_exact_scope_digest_and_authorization(cli)


@pytest.mark.parametrize(
    "change", ["method", "ledger", "prepare_and_live", "missing_env", "missing_output"]
)
def test_invalid_arguments_before_key_and_scope(cli, monkeypatch, change):
    parent_controls.test_invalid_live_arguments_never_read_credentials_or_register_scope(
        cli, monkeypatch, change
    )


def test_noargs_status_readonly(cli, monkeypatch, capsys):
    parent_controls.test_read_only_status_reports_single_arm_cap_without_credentials(
        cli, monkeypatch, capsys
    )


def test_prepare_exclusive_without_key_or_ledger_mutation(cli, monkeypatch, capsys):
    parent_controls.test_prepare_writes_only_one_new_method_without_reading_credentials(
        cli, monkeypatch, capsys
    )


def test_transport_checkpoint_owns_full_journal(cli, monkeypatch):
    parent_controls.test_transport_checkpoint_records_only_owned_preserved_journal(cli, monkeypatch)


@pytest.mark.parametrize("wire_format", ["absent", "other", None])
def test_wrong_actual_wire_stops_campaign(cli, monkeypatch, wire_format):
    cli.method["batches"].append(
        {
            **cli.method["batches"][0],
            "batch_id": "never-visited",
            "scope_id": "never-authorized",
        }
    )

    def wrong_wire(*args, **kwargs):
        result = cli.run_batch(*args, **kwargs)
        result["actual_sends"] = 1
        result["provider_sends"] = [
            {
                "http_send_started": True,
                "wire_response_format": wire_format,
            }
        ]
        return result

    monkeypatch.setattr(cli.module, "run_real_index_batch", wrong_wire)
    assert controls._main(cli) == 2
    receipt = controls._read(cli.destination / "receipt.json")
    assert receipt["batches"][0]["json_object_wire_observed"] is False
    assert receipt["completed_batches"] == 1 and receipt["planned_batches"] == 2
    assert controls._scope_count(cli.path) == 1


def test_zero_dispatch_wire_not_observed(cli, monkeypatch):
    parent_controls.test_pre_dispatch_zero_is_not_a_JSON_transport_observation(cli, monkeypatch)


@pytest.fixture
def method_inputs(tmp_path, monkeypatch, multiple_holds):
    from registered_native_inputs import registered_method_inputs

    module = _module(monkeypatch)
    root = tmp_path / "synthetic-registered-inputs"
    value = registered_method_inputs(module, ROOT, root, monkeypatch, multiple_holds)
    # The actual-replay regression reloads through this test module's ROOT.
    # Keep its complete real replay content, with the temporary protocol pin,
    # inside the same hermetic registered tree used by production validation.
    monkeypatch.setitem(globals(), "ROOT", root)
    return value


def test_fresh_method_48_slots_6_pairs_same_record_set_common_prompt_only_order_differs(
    method_inputs,
):
    module, root, path, fixtures = method_inputs
    before = path.read_bytes()
    with offline_network():
        method = module.build_method(root, path)
    assert path.read_bytes() == before
    assert method["protocol_id"] == "core-source-order-model-v1"
    assert method["experiment_id"] == "core-source-order-2026-10-15-v1"
    assert method["scope_cap_usd"] == "0.06" and method["campaign_scope_cap_usd"] == "0.36"
    assert method["real_RAG_retrieval"] is False and "indexes" not in method
    assert len(method["fresh_request_ids"]) == len(set(method["fresh_request_ids"])) == 48
    assert len(method["fresh_scope_ids"]) == len(set(method["fresh_scope_ids"])) == 6
    old = controls._read(ROOT / module.PARENT_FOLDER / "live-method-v1.json")
    assert not set(method["fresh_request_ids"]) & set(old["fresh_request_ids"])
    assert not set(method["fresh_scope_ids"]) & set(old["fresh_scope_ids"])
    assert [b["jobs"][0]["case_id"] for b in method["batches"]] == [
        "dev-case-a",
        "dev-case-b",
        "dev-case-c",
        "dev-case-c",
        "dev-case-b",
        "dev-case-a",
    ]
    for index, batch in enumerate(method["batches"]):
        expected = ["original_order", "rotate_left_one"]
        assert [j["arm"] for j in batch["jobs"]] == (expected if index % 2 == 0 else expected[::-1])
        assert batch["kind"] == "controlled_evidence" and batch["max_request_slots"] == 8
        assert Decimal(batch["worst_reserved_usd"]) == Decimal("0.048660480")
        assert batch["request_slots_sha256"] == module.slots_sha256(
            module.quality_slots(method, batch, fixtures)
        )
        jobs = sorted(batch["jobs"], key=lambda j: j["arm"])
        for job in jobs:
            assert job["evidence_condition"] == "fixed_guide_added"
            assert job["complementary_sources"] is False
            assert job["evidence_order"] == job["arm"]
            assert all(
                job[k] is True
                for k in (
                    "grounded_json_object",
                    "concise_user_draft",
                    "ask_source_background",
                    "compact_plan",
                    "source_capacity",
                    "decision_contracts",
                    "source_selection_reminder",
                )
            )
            assert job["repair_repeated_queries"] is False and job["resource_guidance"] is False
        ignored = {"job_id", "arm", "evidence_order"}
        assert {k: v for k, v in jobs[0].items() if k not in ignored} == {
            k: v for k, v in jobs[1].items() if k not in ignored
        }
    assert len(method["protected_files"]) == 19
    assert all(not name.startswith("runtime/") for name in method["input_pins"])
    assert method["ledger_journal_before"] == module.ledger_journal_snapshot(path)


@pytest.mark.parametrize("change", ["extra", "bool_count", "scope_cap", "model", "arm_order"])
def test_protocol_any_unregistered_change_rejected_before_packet(
    method_inputs, monkeypatch, change
):
    module, root, path, _ = method_inputs
    p = root / module.FOLDER / "protocol-v1.json"
    value = controls._read(p)
    if change == "extra":
        value["unregistered"] = True
    elif change == "bool_count":
        value["schema_version"] = True
    elif change == "scope_cap":
        value["live"]["scope_cap_usd"] = "1.00"
    elif change == "model":
        value["live"]["model"] = "other"
    else:
        value["live"]["paired_arm_order"][0].reverse()
    p.write_text(json.dumps(value))
    monkeypatch.setattr(module, "load_source_packet", lambda *_args: pytest.fail("packet accessed"))
    before = path.read_bytes()
    with (
        offline_network(),
        pytest.raises(ValueError, match="^SourceOrderRegistrationRejected$"),
    ):
        module.build_method(root, path)
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "target",
    [
        "runtime/dev-rag-coverage-2026-10-14-v1/coverage-18/chroma.sqlite3",
        "data/evaluation/dev-three-v1/cases/enum-8129-v1.json",
        "experiments/core_complementary_sources_v1/model-live-receipt-v1.json",
        "experiments/core_enum_evidence_v1/source-packet-v1.json",
        "experiments/core_enum_evidence_v1/protected-inputs-v1.json",
    ],
)
def test_protected_history_drift_blocks_registration(method_inputs, target):
    module, root, path, _ = method_inputs
    (root / target).write_text("{}")
    before = path.read_bytes()
    with offline_network(), pytest.raises((ValueError, KeyError)):
        module.build_method(root, path)
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "key,value",
    [
        ("accepted", False),
        ("actual_sends", False),
        ("actual_sends", 1),
        ("historical_contexts", True),
        ("historical_contexts", 23),
        ("common_prompt", False),
        ("common_SYSTEM_policy", False),
        ("complete_record_set_unchanged", False),
        ("held_out_test", True),
        ("human_usefulness", 1),
    ],
)
def test_offline_readiness_is_required_strict_and_not_model_quality(method_inputs, key, value):
    module, root, path, _ = method_inputs
    target = root / module.FOLDER / "offline-replay-v1.json"
    report = controls._read(target)
    report[key] = value
    target.write_text(json.dumps(report))
    before = path.read_bytes()
    with (
        offline_network(),
        pytest.raises(ValueError, match="^SourceOrderRegistrationRejected$"),
    ):
        module.build_method(root, path)
    assert path.read_bytes() == before


def test_changed_method_cannot_silently_regenerate_new_ids_or_treatment(method_inputs):
    module, root, path, _ = method_inputs
    method = module.build_method(root, path)
    method["batches"][0]["jobs"][0]["evidence_order"] = "rotate_left_one"
    method_path = root / module.METHOD
    method_path.write_text(json.dumps(method))
    with (
        offline_network(),
        pytest.raises(ValueError, match="^SourceOrderRegistrationRejected$"),
    ):
        module.preflight(root, path, method_path)


@pytest.mark.parametrize("state", ["unused_closed", "reserved", "settled", "uncertain"])
def test_no_closed_or_allocated_slot_identity_can_be_reused(multiple_holds, monkeypatch, state):
    module = _module(monkeypatch)
    ledger, path, _ = multiple_holds
    authorize(ledger, registered=(slot(10),))
    if state == "unused_closed":
        ledger.close_quarantine_scope(SCOPE)
    else:
        reserve(ledger, slot(10))
        if state == "settled":
            ledger.settle(
                slot(10).request_id, cost_usd=Decimal(".001"), input_tokens=10, output_tokens=1
            )
        elif state == "uncertain":
            ledger.mark_uncertain(slot(10).request_id, error_code="Synthetic")
    before = path.read_bytes()
    with pytest.raises(ValueError, match="^RepeatIdentityAlreadyAllocated$"):
        module.validate_fresh_identities(path, {slot(10).request_id}, {"fresh-scope"})
    assert path.read_bytes() == before


@pytest.mark.parametrize("mutation", ["old_event", "foreign_scope", "schema", "deleted_row"])
def test_full14table_journal_old_history_immutable(multiple_holds, monkeypatch, mutation):
    parent_controls.test_full_journal_rejects_old_history_or_foreign_append(
        multiple_holds, monkeypatch, mutation
    )


@pytest.mark.parametrize("case_id", ["dev-case-a", "dev-case-b", "dev-case-c"])
def test_same_guide_record_set_uniform_order_both_trial_arms_keep_actual_job_identity(
    monkeypatch, case_id
):
    module = _module(monkeypatch)
    packet = module.load_packet()
    fixtures = module.fixtures_for(ROOT, {"protocol_id": "core-stability-v1"})
    records = []
    factory = fixture_retriever_factory(packet, fixtures, records)
    parent_records = []
    original = parent_factory(packet, fixtures, parent_records)
    fixture = fixtures[case_id]
    for turn in fixture.data["turns"]:
        expected, snapshot = original({"arm": "fixed_guide_added", "case_id": case_id}, turn)
        request = RetrievalRequest(queries=("fixed source control",), top_k=5, snapshot_id=snapshot)
        expected_bundle = expected.search(request)
        for arm in ("original_order", "rotate_left_one"):
            job = {
                "job_id": f"r1:{case_id}:{arm}",
                "case_id": case_id,
                "arm": arm,
                "complementary_sources": False,
                "evidence_order": arm,
                "evidence_condition": "fixed_guide_added",
            }
            supplier, selected = factory(job, turn)
            assert selected == snapshot
            actual = supplier.search(request)
            expected_hits = expected_bundle.hits
            if arm == "rotate_left_one" and len(expected_hits) > 1:
                expected_hits = (*expected_hits[1:], expected_hits[0])
            expected_ordered = expected_bundle.model_copy(update={"hits": expected_hits})
            assert actual.model_dump_json() == expected_ordered.model_dump_json()
            assert records[-1]["arm"] == arm and records[-1]["job_id"] == job["job_id"]
            assert records[-1]["evidence_condition"] == "fixed_guide_added"
            assert records[-1]["actual_search"] is False
            assert records[-1]["evidence_order"] == arm
            assert records[-1]["same_complete_record_set"] is True
            supplier.search(request)
            with pytest.raises(EnumEvidenceRejected):
                supplier.search(request)


@pytest.mark.parametrize(
    "field,value",
    [
        ("arm", "fixed_baseline"),
        ("arm", "fixed_guide_added"),
        ("complementary_sources", True),
        ("complementary_sources", 0),
        ("evidence_condition", "fixed_baseline"),
        ("evidence_order", "rotate_left_one"),
        ("job_id", ""),
    ],
)
def test_source_condition_cannot_be_selected_by_wrong_job_or_source_flags(
    monkeypatch, field, value
):
    module = _module(monkeypatch)
    fixtures = module.fixtures_for(ROOT, {"protocol_id": "core-stability-v1"})
    supply = fixture_retriever_factory(module.load_packet(), fixtures, [])
    job = {
        "job_id": "registered-control",
        "case_id": "dev-case-c",
        "arm": "original_order",
        "complementary_sources": False,
        "evidence_order": "original_order",
        "evidence_condition": "fixed_guide_added",
    }
    job[field] = value
    with pytest.raises(SourceOrderRejected):
        supply(job, fixtures["dev-case-c"].data["turns"][0])


@pytest.mark.parametrize("format_value", ["json_object", "other"])
def test_unsent_transport_record_observes_no_JSON_wire(cli, monkeypatch, format_value):
    def checkpoint_only(*args, **kwargs):
        result = cli.run_batch(*args, **kwargs)
        result["provider_sends"] = [
            {
                "http_send_started": False,
                "wire_response_format": format_value,
            }
        ]
        result["completed_routes"] = 0
        return result

    monkeypatch.setattr(cli.module, "run_real_index_batch", checkpoint_only)
    assert controls._main(cli) == 0
    receipt = controls._read(cli.destination / "receipt.json")
    assert receipt["batches"][0]["json_object_wire_observed"] is None
    assert receipt["batches"][0]["completed_routes"] == 0


@pytest.mark.parametrize(
    "count,records",
    [
        (1, []),
        (0, [{"http_send_started": True, "wire_response_format": "json_object"}]),
        (True, []),
        (0, [{"wire_response_format": "json_object"}]),
    ],
)
def test_inconsistent_send_counters_never_claim_success_or_leave_active_scope(
    cli, monkeypatch, count, records
):
    def inconsistent(*args, **kwargs):
        result = cli.run_batch(*args, **kwargs)
        result["actual_sends"], result["provider_sends"] = count, records
        return result

    monkeypatch.setattr(cli.module, "run_real_index_batch", inconsistent)
    assert controls._main(cli) == 2
    assert not cli.ledger.quarantine_scope_status(cli.method["batches"][0]["scope_id"]).active
    failure = controls._read(cli.destination / "failure.json")
    assert failure["active_scope_disposition"]["block_reason"] == "ExperimentClosed"


@pytest.mark.parametrize(
    "field,value",
    [
        ("registered_before_model", False),
        ("schema_version", True),
        ("protocol_sha256", "f" * 64),
        ("human_reviewed", True),
        ("human_usefulness", 5),
        ("held_out_test", True),
        ("same_guide_available_evidence_both_arms", False),
        ("complete_criteria", {}),
        ("scenarios_before_model", []),
    ],
)
def test_semantic_preparation_frozen_before_model_not_fabricated_scores(
    method_inputs, field, value
):
    module, root, path, _ = method_inputs
    p = root / module.FOLDER / "semantic-review-preparation-v1.json"
    preparation = controls._read(p)
    preparation[field] = value
    p.write_text(json.dumps(preparation))
    before = path.read_bytes()
    with (
        offline_network(),
        pytest.raises(ValueError, match="^SourceOrderRegistrationRejected$"),
    ):
        module.build_method(root, path)
    assert path.read_bytes() == before


def test_same_guide_supplier_rejects_invented_future_visible_content(monkeypatch):
    module = _module(monkeypatch)
    fixtures = module.fixtures_for(ROOT, {"protocol_id": "core-stability-v1"})
    supply = fixture_retriever_factory(module.load_packet(), fixtures, [])
    job = {
        "job_id": "control",
        "case_id": "dev-case-c",
        "arm": "original_order",
        "complementary_sources": False,
        "evidence_order": "original_order",
        "evidence_condition": "fixed_guide_added",
    }
    turn = json.loads(json.dumps(fixtures["dev-case-c"].data["turns"][0]))
    turn["visible"]["message"] += " injected later answer"
    with pytest.raises(SourceOrderRejected):
        supply(job, turn)


def test_inconsistent_wire_failure_retains_original_result_and_all_planned_jobs(cli, monkeypatch):
    def inconsistent(*args, **kwargs):
        value = cli.run_batch(*args, **kwargs)
        value["actual_sends"] = 1
        return value

    monkeypatch.setattr(cli.module, "run_real_index_batch", inconsistent)
    assert controls._main(cli) == 2
    original = controls._read(cli.destination / "synthetic-final-batch/model-result.json")
    assert original["actual_sends"] == 1 and original["provider_sends"] == []
    failure = controls._read(cli.destination / "failure.json")
    assert failure["method"]["batches"] == cli.method["batches"]
    assert failure["active_scope_disposition"]["block_reason"] == "ExperimentClosed"


def _actual_config(module, scope_id):
    return module.MetisConfig(
        api_key="public-synthetic-finite-campaign-control",
        live_enabled=True,
        model="gpt-4o-mini",
        phase="development",
        response_mode="grounded_plan",
        continuation_id=scope_id,
        grounded_decision_contracts=True,
        grounded_source_gap_handoff=True,
        grounded_source_gap_investigation=True,
        grounded_resource_guidance=False,
        input_token_reserve=32768,
        max_output_tokens=1024,
        max_request_usd=module.get_price("gpt-4o-mini").cost(32768, 1024),
    )


def test_every_registered_real_scope_fits_MetisConfig_before_authorization(method_inputs):
    module, root, path, _ = method_inputs
    method = module.build_method(root, path)
    for batch in method["batches"]:
        assert len(batch["scope_id"]) <= 64
        assert _actual_config(module, batch["scope_id"]).continuation_id == batch["scope_id"]


@pytest.mark.parametrize("behavior", ["valid", "invalid_shape", "timeout"])
def test_real_finite_batch_registered_slots_actual_gateway_and_bounded_failure(
    method_inputs, behavior
):
    module, root, path, fixtures = method_inputs
    method = module.build_method(root, path)
    batch = method["batches"][2]  # Current/fresh complementary C, with correction.
    ledger = module.BudgetLedger(path)
    observation = ledger.quarantine_observation()
    slots = module.quality_slots(method, batch, fixtures)
    digest = module.sha(json.dumps(batch, sort_keys=True).encode())
    before = module.ledger_observation(path)
    ledger.authorize_quarantine_scope(
        authorization_id=batch["scope_id"],
        authorization_ref=method["authorization_ref"],
        expected_unknown_ids=observation.unknown_ids,
        expected_unknown_fingerprints=observation.unknown_fingerprints,
        expected_meta_sha256=observation.meta_sha256,
        expected_authorization_history_sha256=observation.authorization_history_sha256,
        protocol_sha256=digest,
        request_slots=slots,
        additional_cap_usd=Decimal(".06"),
        allow_full_context=True,
    )
    bodies = []

    def respond(request):
        wire = json.loads(request.content)
        bodies.append(wire)
        if behavior == "timeout":
            raise httpx.ReadTimeout("private-synthetic-timeout")
        payload = json.loads(wire["messages"][1]["content"])
        current = payload["request"]
        assert len(current["evidence"]["hits"]) == 3
        assert all(not hit["applicable_versions"] for hit in current["evidence"]["hits"])
        assert wire["response_format"] == {"type": "json_object"}
        assert len(json.dumps(wire["messages"], ensure_ascii=False).encode()) + 1024 <= 32768
        content = (
            "{}"
            if behavior == "invalid_shape"
            else json.dumps(
                {
                    "context_sha256": current["context_sha256"],
                    "decision": "answer",
                    "sources": [
                        index
                        for index, hit in enumerate(current["evidence"]["hits"])
                        if hit["source_id"].endswith("/custom-classes.md")
                    ],
                }
            )
        )
        return httpx.Response(
            200,
            json={
                "model": "gpt-4o-mini",
                "usage": {"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": 130},
                "choices": [
                    {"finish_reason": "stop", "message": {"role": "assistant", "content": content}}
                ],
            },
        )

    records = []
    with offline_network():
        result = module.run_quality_batch(
            method,
            batch,
            fixtures,
            module.load_user_gap_vocabulary(str(ROOT / module.VOCABULARY)),
            ledger,
            _actual_config(module, batch["scope_id"]),
            before,
            underlying=httpx.MockTransport(respond),
            retriever_factory=fixture_retriever_factory(module.load_packet(), fixtures, records),
        )
    assert actual_json_wire_observation(result) is True
    assert result["actual_sends"] == len(bodies)
    assert all(
        len(
            [
                a
                for a in result["attempts"]
                if a["context"]["run_id"] == attempt["context"]["run_id"]
            ]
        )
        <= 2
        for attempt in result["attempts"]
    )
    if behavior == "valid":
        assert result["completed_routes"] == 2 and result["visited_jobs"] == 2
        assert result["actual_sends"] == 4
        assert all(a["context"]["attempt_index"] == 1 for a in result["attempts"])
        assert [
            COMPLEMENTARY_SOURCE_POLICY in body["messages"][0]["content"] for body in bodies
        ] == [False, False, False, False]
        assert {r["arm"] for r in records} == {"original_order", "rotate_left_one"}
        assert all(r["evidence_condition"] == "fixed_guide_added" for r in records)
        assert result["original_accounting_preserved"] is True
    elif behavior == "invalid_shape":
        assert result["actual_sends"] == 4 and result["completed_routes"] == 0
        assert result["visited_jobs"] == 2
        assert all(a["context"]["case_revision"] == 1 for a in result["attempts"])
    else:
        assert result["actual_sends"] == 1 and result["visited_jobs"] == 1
        assert result["stopped_early"] is True
        assert len(ledger.quarantine_observation().unknown_ids) == 3
        assert ledger.quarantine_scope_status(batch["scope_id"]).block_reason == "NewUncertainty"
        assert "private-synthetic-timeout" not in json.dumps(result)
    disposition = module.close_owned_scope(
        ledger, batch["scope_id"], digest, method["authorization_ref"]
    )
    assert not disposition.active
    assert ledger.snapshot().halted and ledger.snapshot().reserved_usd == 0
    with pytest.raises(ValueError, match="^RepeatIdentityAlreadyAllocated$"):
        module.validate_fresh_identities(
            path, {slot.request_id for slot in slots}, {batch["scope_id"]}
        )


def test_bound_supplier_observation_identity_detaches_from_mutable_job(monkeypatch):
    module = _module(monkeypatch)
    fixtures = module.fixtures_for(ROOT, {"protocol_id": "core-stability-v1"})
    records = []
    supply = fixture_retriever_factory(module.load_packet(), fixtures, records)
    job = {
        "job_id": "actual-registered-job",
        "case_id": "dev-case-c",
        "arm": "original_order",
        "complementary_sources": False,
        "evidence_order": "original_order",
        "evidence_condition": "fixed_guide_added",
    }
    supplier, snapshot = supply(job, fixtures["dev-case-c"].data["turns"][0])
    job.update(job_id="mutated", arm="rotate_left_one", evidence_order="rotate_left_one")
    supplier.search(RetrievalRequest(queries=("fixed",), snapshot_id=snapshot))
    assert records[-1]["job_id"] == "actual-registered-job"
    assert records[-1]["arm"] == "original_order"
    assert records[-1]["evidence_order"] == "original_order"


def test_actual_registered_offline_replay_is_eligible_not_only_synthetic_readiness(method_inputs):
    module, root, path, _ = method_inputs
    actual = (ROOT / module.FOLDER / "offline-replay-v1.json").read_bytes()
    (root / module.FOLDER / "offline-replay-v1.json").write_bytes(actual)
    before = path.read_bytes()
    with offline_network():
        method = module.build_method(root, path)
    assert path.read_bytes() == before
    assert method["offline_payload_preflight"] == json.loads(actual)
    assert method["common_prompt_both_arms"] is True
    assert method["same_complete_record_set_both_arms"] is True
    assert method["only_complete_record_order_differs"] is True
    assert method["ordered_USER_payload_and_context_may_differ"] is True
    assert method["complementary_sources"] is False
    assert "only_registered_SYSTEM_guidance_differs" not in method
    parent = controls._read(ROOT / "experiments/core_complementary_sources_v1/live-method-v1.json")
    assert not set(method["fresh_request_ids"]) & set(parent["fresh_request_ids"])
    assert not set(method["fresh_scope_ids"]) & set(parent["fresh_scope_ids"])
    assert "experiments/core_complementary_sources_v1/protocol-v1.json" in method["input_pins"]
    assert (
        "experiments/core_complementary_sources_v1/model-live-receipt-v1.json"
        in method["input_pins"]
    )
