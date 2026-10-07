"""Offline paired-design, scope and accounting checks with real temporary ledgers."""

import json
import stat
import sys
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from agent_app.contracts import (
    AnalysisResult,
    CaseState,
    EvidenceBundle,
    EvidenceHit,
    EvidenceLink,
    Fact,
)
from agent_app.llm.budget import BudgetLedger
from agent_app.llm.config import MetisConfig
from agent_app.llm.pricing import get_price
from agent_app.orchestration.ports import ReasoningStopped
from agent_app.reasoning import ablations
from agent_app.reasoning.ablations import (
    AblationPlan,
    NormalizationDeclaration,
    SuiteReference,
    ablation_run_id,
    run_ablation,
    schedule_ablation,
    suite_content_sha256,
    validate_ablation_inputs,
    validate_paired_suites,
)
from agent_app.reasoning.experiments import sha256_file
from agent_app.reasoning.probes import DecisionProbe, ProbeExpectations, ProbeSuite

SNAPSHOT = "ablation-test-snapshot"


def suite_variants(case_count=2):
    original_hit = EvidenceHit(
        chunk_id="docs:fixture",
        source_id="doc:fixture",
        excerpt="PRIVATE_SOURCE_MARKER: a synthetic diagnostic example, not a verified fix.",
        source_url="https://example.org/offline-original",
        source_type="doc",
    )
    added_hit = EvidenceHit(
        chunk_id="docs:additional",
        source_id="doc:additional",
        excerpt="Synthetic parameter documentation used only for accounting tests.",
        source_url="https://github.com/streamlit/docs/blob/fixture-commit/synthetic.md",
        source_type="doc",
        source_commit="fixture-commit",
    )
    bundle = EvidenceBundle(snapshot_id=SNAPSHOT, hits=(original_hit,))
    original = ProbeSuite(
        schema_version=1,
        snapshot_id=SNAPSHOT,
        purpose="Synthetic paired-design tests; no real model-quality claims.",
        docs_commit="fixture-commit",
        source_snapshot_date="2026-10-07",
        reserved_issue_ids=(),
        cases=tuple(
            DecisionProbe(
                id=f"probe-{index}",
                kind="synthetic",
                origin_url=None,
                origin_issue_id=None,
                origin_created_at=None,
                description="DESCRIPTION_REVIEWER_ONLY",
                case_state=CaseState(
                    case_id=f"case:probe-{index}",
                    facts=(
                        Fact(
                            name="installed_version",
                            value="fixture-version",
                            source_ref="event:user",
                            turn_id="turn:initial",
                        ),
                    ),
                    unknowns=("browser",),
                    checks_performed=("Observed the mismatch once",),
                ),
                user_message="PRIVATE_USER_MARKER: displayed B differs from persisted A.",
                bundles=(bundle, bundle),
                expectations=ProbeExpectations(
                    acceptable_decisions=("answer",),
                    required_terms=("ORACLE_ONLY",),
                    require_evidence=True,
                    require_uncertainty=True,
                    forbid_repeated_checks=True,
                ),
                reviewer_notes=("REVIEWER_ONLY",),
            )
            for index in range(case_count)
        ),
    )
    enriched = original.model_copy(
        update={
            "purpose": "Synthetic evidence enrichment only.",
            "cases": tuple(
                probe.model_copy(
                    update={
                        "bundles": tuple(
                            item.model_copy(update={"hits": (*item.hits, added_hit)})
                            for item in probe.bundles
                        )
                    }
                )
                for probe in original.cases
            ),
        },
        deep=True,
    )
    normalized = enriched.model_copy(
        update={
            "purpose": "Synthetic user normalization on the same enriched evidence.",
            "cases": tuple(
                probe.model_copy(
                    update={
                        "case_state": probe.case_state.model_copy(
                            update={
                                "facts": (
                                    *probe.case_state.facts,
                                    Fact(
                                        name="reported_frontend_value",
                                        value="B",
                                        source_ref="event:user",
                                        turn_id="turn:initial",
                                    ),
                                )
                            }
                        )
                    }
                )
                for probe in enriched.cases
            ),
        },
        deep=True,
    )
    return {"original": original, "enriched": enriched, "normalized": normalized}


def registered_plan(suites, **changes):
    return AblationPlan(
        **(
            {
                "experiment_id": "offline-ablation-test",
                "suite_sha256": "a" * 64,
                "case_count": len(suites["original"].cases),
                "suites": {
                    name: SuiteReference(
                        filename=f"{name}.json",
                        sha256="a" * 64,
                        content_sha256=suite_content_sha256(suite),
                    )
                    for name, suite in suites.items()
                },
                "source_change_case_ids": tuple(probe.id for probe in suites["original"].cases),
                "normalizations": {
                    probe.id: NormalizationDeclaration(
                        source_ref="event:user",
                        turn_id="turn:initial",
                        fact_names=("reported_frontend_value",),
                    )
                    for probe in suites["original"].cases
                },
                "scope": "Offline intercepted-HTTP paired safety tests only.",
            }
            | changes
        )
    )


def rehash(suites, plan):
    return plan.model_copy(
        update={
            "suites": {
                name: reference.model_copy(
                    update={"content_sha256": suite_content_sha256(suites[name])}
                )
                for name, reference in plan.suites.items()
            }
        }
    )


def response(content=None, *, usage=True, model="gpt-4o-mini", input_tokens=100):
    if content is None:
        content = AnalysisResult(
            decision="answer",
            user_draft="Synthetic diagnostic proposal for human review.",
            maintainer_summary="This is an offline operational test.",
            rationale="Citation presence is tested, not semantic correctness.",
            evidence_links=(EvidenceLink(claim="Synthetic example", chunk_id="docs:fixture"),),
        ).model_dump_json()
    body = {
        "model": model,
        "choices": [
            {"finish_reason": "stop", "message": {"role": "assistant", "content": content}}
        ],
    }
    if usage:
        body["usage"] = {
            "prompt_tokens": input_tokens,
            "completion_tokens": 30,
            "total_tokens": input_tokens + 30,
        }
    return body


def intercepted(responses):
    calls = []
    scripted = iter(responses)

    def handler(request):
        calls.append(json.loads(request.content))
        body = next(scripted)
        if isinstance(body, Exception):
            raise body
        return httpx.Response(200, json=body)

    return httpx.MockTransport(handler), calls


@pytest.fixture
def runtime(tmp_path):
    ledger = BudgetLedger.create(
        tmp_path / "budget.sqlite3", limit_usd=Decimal("1"), opening_spend_usd=Decimal("0")
    )
    config = MetisConfig(api_key="offline-ablation-key", live_enabled=True)
    return ledger, config, tmp_path / "receipts"


def reserve():
    return get_price("gpt-4o-mini").cost(32768, 768)


def cost():
    return get_price("gpt-4o-mini").cost(100, 30)


def test_registered_repository_protocol_pins_all_three_input_files_and_the_fixed_grid():
    path = Path("experiments/decision_quality/protocol-ablation-v3.json")
    suites, plan = validate_ablation_inputs(path)
    assert plan.case_count == 8
    assert plan.cap_usd == Decimal("0.10")
    assert plan.model == "gpt-4o-mini"
    assert plan.input_token_reserve == 32768
    assert plan.max_output_tokens == 768
    assert plan.continuation_id == "user-continuation-2026-10-07-v3"
    assert len(list(schedule_ablation(suites, plan))) == 32
    for name, reference in plan.suites.items():
        assert sha256_file(path.parent / reference.filename) == reference.sha256
        assert suite_content_sha256(suites[name]) == reference.content_sha256


def test_byte_hash_drift_is_rejected_even_when_the_parsed_suite_is_unchanged(tmp_path):
    suites = suite_variants(1)
    plan = registered_plan(suites)
    references = {}
    for name, reference in plan.suites.items():
        path = tmp_path / reference.filename
        path.write_text(suites[name].model_dump_json() + "\n")
        references[name] = reference.model_copy(update={"sha256": sha256_file(path)})
    plan = plan.model_copy(
        update={"suites": references, "suite_sha256": references["original"].sha256}
    )
    protocol_path = tmp_path / "protocol.json"
    protocol_path.write_text(plan.model_dump_json())
    validate_ablation_inputs(protocol_path)
    changed = tmp_path / references["normalized"].filename
    changed.write_text(changed.read_text() + "\n")
    with pytest.raises(ValueError, match="Suite file changed"):
        validate_ablation_inputs(protocol_path)


def test_schedule_rotates_cells_and_preserves_the_right_paired_input_for_every_observation():
    suites = suite_variants(4)
    plan = registered_plan(suites)
    scheduled = list(schedule_ablation(suites, plan))
    assert [cell.cell_id for _, cell in scheduled] == list("ABCDBCDACDABDABC")
    for probe, cell in scheduled:
        index = int(probe.id.split("-")[1])
        assert probe is suites[cell.suite].cases[index]
    assert scheduled == list(schedule_ablation(suites, plan))


def test_cells_sharing_a_prompt_have_distinct_stable_bounded_run_identities():
    values = {ablation_run_id("offline-test", cell, "p" * 200) for cell in "ABCD"}
    assert len(values) == 4
    assert all(len(value) <= 200 for value in values)
    assert ablation_run_id("offline-test", "A", "probe") == ablation_run_id(
        "offline-test", "A", "probe"
    )
    assert ablation_run_id("other-test", "A", "probe") != ablation_run_id(
        "offline-test", "A", "probe"
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "message",
        "expectation",
        "case_order",
        "original_fact",
        "unknowns",
        "old_evidence",
        "evidence_provenance",
        "normalized_attribution",
    ],
)
def test_paired_boundary_checks_reject_user_label_fact_and_source_changes_even_if_rehashed(
    mutation,
):
    suites = suite_variants()
    plan = registered_plan(suites)
    variant = (
        "enriched"
        if mutation
        in {"message", "expectation", "case_order", "old_evidence", "evidence_provenance"}
        else "normalized"
    )
    data = suites[variant].model_dump()
    if mutation == "message":
        data["cases"][0]["user_message"] = "Different user report"
    elif mutation == "expectation":
        data["cases"][0]["expectations"]["acceptable_decisions"] = ("ask",)
    elif mutation == "case_order":
        data["cases"] = data["cases"][::-1]
    elif mutation == "original_fact":
        data["cases"][0]["case_state"]["facts"][0]["value"] = "changed-version"
    elif mutation == "unknowns":
        data["cases"][0]["case_state"]["unknowns"] = ()
    elif mutation == "old_evidence":
        data["cases"][0]["bundles"][0]["hits"][0]["excerpt"] = "Replaced original evidence"
    elif mutation == "evidence_provenance":
        data["cases"][0]["bundles"][0]["hits"][1]["source_url"] = "https://example.org/mislabelled"
    elif mutation == "normalized_attribution":
        data["cases"][0]["case_state"]["facts"][1]["source_ref"] = "event:invented"
    suites[variant] = ProbeSuite.model_validate(data)
    with pytest.raises(ValueError):
        validate_paired_suites(suites, rehash(suites, plan))


def test_runtime_rejects_content_hash_changes_before_receipts_or_http(runtime):
    ledger, config, output = runtime
    suites = suite_variants()
    plan = registered_plan(suites)
    suites["normalized"] = suites["normalized"].model_copy(
        update={"purpose": "Changed after registration"}
    )
    transport, calls = intercepted([response()])
    before = ledger.snapshot()
    with pytest.raises(ValueError, match="Suite content changed"):
        run_ablation(
            suites, plan, config=config, ledger=ledger, output_dir=output, transport=transport
        )
    assert calls == []
    assert not output.exists()
    assert ledger.snapshot() == before


@pytest.mark.parametrize(
    "changes",
    [
        {"cap_usd": Decimal("0.11")},
        {"model": "gpt-4.1-mini"},
        {"input_token_reserve": 16384},
        {"case_count": 9},
    ],
)
def test_protocol_rejects_broader_than_registered_cost_model_context_or_batch_scope(changes):
    with pytest.raises(ValidationError):
        registered_plan(suite_variants(), **changes)


def test_global_cap_covers_all_cells_and_stops_before_the_next_http(runtime):
    ledger, config, output = runtime
    suites = suite_variants()
    plan = registered_plan(suites, cap_usd=reserve() + cost() / 2)
    transport, calls = intercepted([response()] * 8)
    summary = run_ablation(
        suites, plan, config=config, ledger=ledger, output_dir=output, transport=transport
    )
    assert len(calls) == summary["completed_observations"] == 1
    assert summary["planned_observations"] == 8
    assert summary["stop_reason"] == "BudgetExceeded"
    assert summary["paired_completed_case_ids"] == []
    assert ledger.snapshot().settled_usd == cost()


def test_final_success_does_not_require_reserving_a_nonexistent_next_observation(runtime):
    ledger, config, output = runtime
    suites = suite_variants(1)
    plan = registered_plan(suites, cap_usd=reserve() + Decimal("3.5") * cost())
    transport, calls = intercepted([response()] * 4)
    summary = run_ablation(
        suites, plan, config=config, ledger=ledger, output_dir=output, transport=transport
    )
    assert len(calls) == summary["completed_observations"] == 4
    assert summary["stop_reason"] is None
    assert ledger.snapshot().settled_usd == 4 * cost()


def test_repair_keeps_the_same_cell_two_attempt_allowance_and_real_ledger_attribution(runtime):
    ledger, config, output = runtime
    suites = suite_variants(1)
    transport, calls = intercepted([response("not JSON"), *[response()] * 4])
    summary = run_ablation(
        suites,
        registered_plan(suites),
        config=config,
        ledger=ledger,
        output_dir=output,
        transport=transport,
    )
    first = json.loads((output / "observation-00.json").read_text())
    assert len(calls) == 5
    assert summary["completed_observations"] == 4
    assert first["result"]["status"] == "awaiting_approval"
    assert first["result"]["model_attempts"] == 2
    assert [entry["attempt"] for entry in first["ledger_entries"]] == [1, 2]
    assert len({entry["run_id"] for entry in first["ledger_entries"]}) == 1
    assert first["contexts"][1]["can_refine"] is False
    assert first["contexts"][1]["output_feedback"]["issues"][0]["code"] == "invalid_json"


@pytest.mark.parametrize(
    ("first", "error_code", "halted"),
    [
        (httpx.ReadTimeout("private-provider-marker"), "ProviderRequestFailed", False),
        (response(usage=False), "ProviderUsageUnknown", True),
        (response(model="gpt-4.1-mini"), "ProviderModelMismatch", True),
        (response(input_tokens=50000), "CostBoundExceeded", True),
    ],
)
def test_unknown_usage_or_a_new_halt_stops_all_remaining_cells_without_retry(
    runtime, first, error_code, halted
):
    ledger, config, output = runtime
    suites = suite_variants(1)
    transport, calls = intercepted([first, *[response()] * 4])
    summary = run_ablation(
        suites,
        registered_plan(suites),
        config=config,
        ledger=ledger,
        output_dir=output,
        transport=transport,
    )
    observation = json.loads((output / "observation-00.json").read_text())
    assert len(calls) == summary["completed_observations"] == 1
    assert summary["stop_reason"] == "LedgerUnavailable"
    assert observation["result"]["error_code"] == error_code
    assert ledger.snapshot().halted is halted
    assert not (output / "observation-01.json").exists()
    assert "private-provider-marker" not in json.dumps(observation)


def authorize_test_scope(ledger):
    ledger.reserve(
        request_id="call:quarantined",
        run_id="run:quarantined",
        case_id="case:old",
        case_revision=0,
        attempt=1,
        model="gpt-4.1-mini",
        phase="development",
        amount_usd=Decimal("0.01"),
    )
    ledger.mark_uncertain("call:quarantined", error_code="ProviderModelMismatch")
    ledger.halt()
    ledger.authorize_continuation(
        authorization_id="offline-continuation",
        authorization_ref="human:test-only",
        expected_request_id="call:quarantined",
        held_usd=Decimal("0.02"),
        additional_cap_usd=Decimal("0.10"),
    )


def test_existing_authorized_scope_is_selected_from_plan_without_reset_or_new_grant(
    runtime, monkeypatch
):
    ledger, config, output = runtime
    authorize_test_scope(ledger)
    suites = suite_variants(1)
    plan = registered_plan(suites, continuation_id="offline-continuation")
    config = config.model_copy(update={"continuation_id": "wrong-config-continuation"})
    transport, calls = intercepted([response()] * 4)

    def forbid_grant(**kwargs):
        pytest.fail("The runner must not create or refresh continuation grants")

    monkeypatch.setattr(ledger, "authorize_continuation", forbid_grant)
    summary = run_ablation(
        suites, plan, config=config, ledger=ledger, output_dir=output, transport=transport
    )
    start = json.loads((output / "start.json").read_text())
    assert len(calls) == summary["completed_observations"] == 4
    assert summary["stop_reason"] is None
    assert ledger.snapshot().halted is True
    assert ledger.snapshot().uncertain_usd == Decimal("0.02")
    assert ledger.continuation_status("offline-continuation").used_usd == 4 * cost()
    assert start["continuation"]["authorization_id"] == plan.continuation_id
    assert len(start["code_sha256"]) == 64


def test_a_configured_grant_cannot_bypass_a_plan_without_explicit_scope(runtime):
    ledger, config, output = runtime
    authorize_test_scope(ledger)
    config = config.model_copy(update={"continuation_id": "offline-continuation"})
    suites = suite_variants(1)
    transport, calls = intercepted([response()] * 4)
    before = ledger.snapshot()
    with pytest.raises(ReasoningStopped, match="LedgerUnavailable"):
        run_ablation(
            suites,
            registered_plan(suites),
            config=config,
            ledger=ledger,
            output_dir=output,
            transport=transport,
        )
    assert calls == []
    assert not output.exists()
    assert ledger.snapshot() == before


def test_new_uncertainty_revokes_the_scope_and_stops_other_cells(runtime):
    ledger, config, output = runtime
    authorize_test_scope(ledger)
    suites = suite_variants(1)
    plan = registered_plan(suites, continuation_id="offline-continuation")
    transport, calls = intercepted([response(usage=False), *[response()] * 4])
    summary = run_ablation(
        suites, plan, config=config, ledger=ledger, output_dir=output, transport=transport
    )
    assert len(calls) == summary["completed_observations"] == 1
    assert summary["stop_reason"] == "LedgerUnavailable"
    assert ledger.snapshot().uncertain_usd == Decimal("0.02") + reserve()
    assert ledger.continuation_status("offline-continuation").active is False


def test_private_receipts_cannot_be_overwritten_or_restart_the_same_run(runtime):
    ledger, config, output = runtime
    suites = suite_variants(1)
    plan = registered_plan(suites)
    transport, calls = intercepted([response()] * 8)
    kwargs = dict(config=config, ledger=ledger, output_dir=output, transport=transport)
    run_ablation(suites, plan, **kwargs)
    prior = (output / "summary.json").read_bytes()
    before = ledger.snapshot()
    with pytest.raises(FileExistsError):
        run_ablation(suites, plan, **kwargs)
    assert len(calls) == 4
    assert ledger.snapshot() == before
    assert (output / "summary.json").read_bytes() == prior
    assert stat.S_IMODE(output.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in output.iterdir())


def test_summaries_keep_three_shared_prompt_cells_separate_and_progress_contains_only_metadata(
    runtime,
):
    ledger, config, output = runtime
    suites = suite_variants()
    plan = registered_plan(suites)
    transport, calls = intercepted([response()] * 8)
    progress = []
    summary = run_ablation(
        suites,
        plan,
        config=config,
        ledger=ledger,
        output_dir=output,
        transport=transport,
        progress=progress.append,
    )
    assert summary["completed_observations"] == len(calls) == 8
    assert set(summary["automatic_results"]) == set("ABCD")
    assert all(group["cases"] == 2 for group in summary["automatic_results"].values())
    assert summary["paired_completed_case_ids"] == ["probe-0", "probe-1"]
    assert summary["semantic_quality"] == "Requires source-backed review"
    assert "best_policy" not in summary
    assert "quality_score" not in summary
    assert all(
        set(item)
        == {"index", "case_id", "cell_id", "status", "decision", "http_attempts", "estimated_usd"}
        for item in progress
    )
    for marker in [
        "PRIVATE_SOURCE_MARKER",
        "PRIVATE_USER_MARKER",
        "offline-ablation-key",
        "ORACLE_ONLY",
        "REVIEWER_ONLY",
    ]:
        assert marker not in json.dumps(progress)
    for call in calls:
        serialized = json.dumps(call["messages"])
        assert "ORACLE_ONLY" not in serialized
        assert "REVIEWER_ONLY" not in serialized
        assert "DESCRIPTION_REVIEWER_ONLY" not in serialized
        assert call["model"] == plan.model and call["max_tokens"] == 768
    contexts = [
        json.loads(path.read_text())["contexts"][0]
        for path in sorted(output.glob("observation-*.json"))
    ]
    assert len({item["run_id"] for item in contexts}) == 8


def test_default_cli_validates_protocol_without_reading_credentials_or_opening_a_ledger(
    tmp_path, monkeypatch, capsys
):
    missing = tmp_path / "never-open.sqlite3"
    monkeypatch.setattr(sys, "argv", ["ablations", "--ledger", str(missing)])

    def forbid_credentials():
        pytest.fail("Default ablation validation must not load a key")

    monkeypatch.setattr(MetisConfig, "from_env", forbid_credentials)
    ablations.main()
    result = json.loads(capsys.readouterr().out)
    assert result["validated"] is True
    assert result["planned_observations"] == 32
    assert result["paid_requests"] == 0
    assert not missing.exists()
