"""Offline three-condition runner checks with intercepted HTTP and scoped accounting."""

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
    ProposalRequirements,
    QuestionTarget,
)
from agent_app.llm.budget import BudgetLedger, LedgerConflict
from agent_app.llm.config import MetisConfig
from agent_app.llm.pricing import get_price
from agent_app.reasoning import quality_experiments
from agent_app.reasoning.experiments import sha256_file
from agent_app.reasoning.probes import DecisionProbe, ProbeExpectations, ProbeSuite
from agent_app.reasoning.quality_experiments import (
    CONTINUATION_ID,
    VARIANTS,
    QualityExperimentPlan,
    catalog_content_sha256,
    quality_run_id,
    run_quality_experiment,
    schedule_quality,
    suite_content_sha256,
    validate_quality_data,
    validate_quality_inputs,
)

QUESTION = "What diagnostic context has not yet been supplied?"


def fixture_inputs(case_count=1):
    bundle = EvidenceBundle(
        snapshot_id="quality-offline-snapshot",
        hits=(
            EvidenceHit(
                chunk_id="docs:fixture",
                source_id="source:fixture",
                excerpt="PRIVATE_SOURCE_MARKER synthetic evidence for transport tests.",
                source_url="https://example.org/offline",
                source_type="doc",
            ),
        ),
    )
    suite = ProbeSuite(
        schema_version=1,
        snapshot_id=bundle.snapshot_id,
        purpose="Offline runner tests, no model-quality evidence.",
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
                    case_id=f"case:quality-{index}",
                    unknowns=("diagnostic_context",),
                    facts=(
                        Fact(
                            name="streamlit_version",
                            value="1.64.0",
                            source_ref="user:fixture",
                            turn_id="initial",
                        ),
                    ),
                ),
                user_message="PRIVATE_USER_MARKER: Streamlit 1.64.0 is installed; context is missing.",
                bundles=(bundle, bundle.model_copy(update={"retrieval_round": 2})),
                expectations=ProbeExpectations(
                    acceptable_decisions=("answer", "ask"),
                    required_terms=("EXPECTED_ORACLE_ONLY",),
                    require_evidence=True,
                    require_uncertainty=True,
                    forbid_repeated_checks=True,
                ),
                reviewer_notes=("REVIEWER_NOTE_ONLY",),
            )
            for index in range(case_count)
        ),
    )
    catalog = {
        probe.id: ProposalRequirements(
            case_id=probe.case_state.case_id,
            case_revision=probe.case_state.case_revision,
            question_targets=(QuestionTarget(name="diagnostic_context", question=QUESTION),),
        )
        for probe in suite.cases
    }
    return suite, catalog


def fixture_plan(suite, catalog, **changes):
    return QualityExperimentPlan(
        **(
            {
                "experiment_id": "offline-quality-test",
                "suite_sha256": "a" * 64,
                "suite_content_sha256": suite_content_sha256(suite),
                "requirements_sha256": "b" * 64,
                "requirements_content_sha256": catalog_content_sha256(catalog),
                "catalog": catalog,
                "case_count": len(suite.cases),
                "scope": "Offline intercepted-HTTP synthetic guard tests only.",
            }
            | changes
        )
    )


def answer_body(*, usage=True, content=None):
    analysis = AnalysisResult(
        decision="answer",
        user_draft="Synthetic source-backed proposal for human review.",
        maintainer_summary="Offline transport and accounting test only.",
        rationale="Checks runner behavior without establishing model quality.",
        evidence_links=(EvidenceLink(claim="Synthetic source", chunk_id="docs:fixture"),),
    )
    body = {
        "model": "gpt-4o-mini",
        "choices": [
            {
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": analysis.model_dump_json() if content is None else content,
                },
            }
        ],
    }
    if usage:
        body["usage"] = {"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": 130}
    return body


def intercepted(responses):
    calls = []
    scripted = iter(responses)

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json=next(scripted))

    return httpx.MockTransport(handler), calls


@pytest.fixture
def runtime(tmp_path):
    ledger = BudgetLedger.create(
        tmp_path / "budget.sqlite3", limit_usd=Decimal("4.50"), opening_spend_usd=Decimal("0")
    )
    ledger.reserve(
        request_id="request:offline-quarantine",
        run_id="run:offline-quarantine",
        case_id="case:offline-quarantine",
        case_revision=0,
        attempt=1,
        model="gpt-4.1-mini",
        phase="development",
        amount_usd=Decimal("0.008560640"),
    )
    ledger.mark_uncertain("request:offline-quarantine", error_code="ProviderModelMismatch")
    ledger.halt()
    ledger.authorize_continuation(
        authorization_id=CONTINUATION_ID,
        authorization_ref="user:offline-test-only",
        expected_request_id="request:offline-quarantine",
        held_usd=Decimal("0.02"),
        additional_cap_usd=Decimal("0.10"),
    )
    return (
        ledger,
        MetisConfig(api_key="synthetic-offline-key", live_enabled=True),
        tmp_path / "runs",
    )


def run(runtime, suite, catalog, plan, responses, *, progress=None):
    ledger, config, output = runtime
    transport, calls = intercepted(responses)
    summary = run_quality_experiment(
        suite,
        catalog,
        plan,
        config=config,
        ledger=ledger,
        output_dir=output,
        transport=transport,
        progress=progress,
    )
    return summary, calls


def test_repository_registration_pins_nine_cases_and_caller_inputs():
    suite, catalog, plan = validate_quality_inputs(
        Path("experiments/decision_quality/protocol-guards-v4.json")
    )
    assert len(suite.cases) == 9
    assert len(list(schedule_quality(suite, plan))) == 27
    assert plan.cap_usd == Decimal("0.055")
    assert plan.continuation_id == CONTINUATION_ID
    assert sum(value.require_fresh_widget_value for value in catalog.values()) == 2
    assert not catalog["synthetic-previous-value-snapshot-control"].require_fresh_widget_value


@pytest.mark.parametrize("changed_file", ["suite", "requirements"])
def test_byte_drift_is_rejected_even_when_json_contents_are_unchanged(tmp_path, changed_file):
    suite, catalog = fixture_inputs()
    suite_path = tmp_path / "cases-guards-v4.json"
    requirements_path = tmp_path / "requirements-guards-v4.json"
    suite_path.write_text(suite.model_dump_json())
    requirements_path.write_text(
        json.dumps({name: value.model_dump() for name, value in catalog.items()})
    )
    plan = fixture_plan(
        suite,
        catalog,
        suite_sha256=sha256_file(suite_path),
        requirements_sha256=sha256_file(requirements_path),
    )
    plan_path = tmp_path / "protocol.json"
    plan_path.write_text(plan.model_dump_json())
    validate_quality_inputs(plan_path)
    path = suite_path if changed_file == "suite" else requirements_path
    path.write_text(path.read_text() + "\n")
    with pytest.raises(ValueError, match="file changed"):
        validate_quality_inputs(plan_path)


@pytest.mark.parametrize("change", ["revision", "known_fact", "unregistered_unknown"])
def test_catalog_must_bind_revision_and_genuinely_absent_user_detail(change):
    suite, catalog = fixture_inputs()
    requirements = catalog["probe-0"]
    if change == "revision":
        requirements = requirements.model_copy(update={"case_revision": 1})
    else:
        name = "streamlit_version" if change == "known_fact" else "unregistered_detail"
        requirements = requirements.model_copy(
            update={"question_targets": (QuestionTarget(name=name, question=QUESTION),)}
        )
    catalog = {"probe-0": requirements}
    plan = fixture_plan(suite, catalog)
    with pytest.raises(ValueError, match="revision|missing user details"):
        validate_quality_data(suite, catalog, plan)


def test_active_evidence_fact_does_not_make_a_user_detail_known():
    suite, catalog = fixture_inputs()
    probe = suite.cases[0]
    case = probe.case_state.model_copy(
        update={
            "facts": (
                *probe.case_state.facts,
                Fact(
                    name="diagnostic_context",
                    value="Source observation only",
                    source_ref="docs:fixture",
                    turn_id="retrieval",
                    provenance_kind="evidence",
                ),
            )
        }
    )
    suite = suite.model_copy(update={"cases": (probe.model_copy(update={"case_state": case}),)})
    validate_quality_data(suite, catalog, fixture_plan(suite, catalog))


def test_variants_cannot_conflate_prompt_metadata_and_enforcement():
    suite, catalog = fixture_inputs()
    with pytest.raises(ValidationError, match="three-variant design"):
        fixture_plan(
            suite,
            catalog,
            variants=(
                VARIANTS[0],
                VARIANTS[1].model_copy(update={"proposal_checks": True}),
                VARIANTS[2],
            ),
        )
    assert quality_run_id("run", "B", "probe") != quality_run_id("run", "C", "probe")


def test_rotated_conditions_get_distinct_requests_and_never_receive_review_oracles(runtime):
    suite, catalog = fixture_inputs(3)
    plan = fixture_plan(suite, catalog)
    progress = []
    summary, calls = run(
        runtime, suite, catalog, plan, [answer_body() for _ in range(9)], progress=progress.append
    )
    assert summary["completed_observations"] == 9
    assert summary["paired_completed_case_ids"] == [probe.id for probe in suite.cases]
    assert set(summary["automatic_results"]) == {"A", "B", "C"}
    assert [item["variant_id"] for item in progress] == [
        "A",
        "B",
        "C",
        "B",
        "C",
        "A",
        "C",
        "A",
        "B",
    ]
    for item, call in zip(progress, calls, strict=True):
        payload = json.loads(call["messages"][1]["content"])
        if item["variant_id"] == "A":
            assert "proposal_requirements" not in payload
        else:
            assert payload["proposal_requirements"] == catalog[item["case_id"]].model_dump(
                mode="json"
            )
        assert call["model"] == "gpt-4o-mini" and call["max_tokens"] == 768
        encoded = json.dumps(call)
        assert all(
            marker not in encoded
            for marker in (
                "DESCRIPTION_REVIEWER_ONLY",
                "EXPECTED_ORACLE_ONLY",
                "REVIEWER_NOTE_ONLY",
            )
        )
    ledger, _, output = runtime
    entries = [
        json.loads((output / f"observation-{index:02d}.json").read_text())["ledger_entries"][0]
        for index in range(9)
    ]
    assert len({entry["request_id"] for entry in entries}) == 9
    assert ledger.snapshot().halted and ledger.snapshot().uncertain_usd == Decimal("0.02")
    assert "PRIVATE_USER_MARKER" not in json.dumps(progress)
    assert "PRIVATE_SOURCE_MARKER" not in json.dumps(progress)
    start = json.loads((output / "start.json").read_text())
    assert start["requirements_content_sha256"] == plan.requirements_content_sha256
    assert len(start["code_sha256"]) == 64
    assert stat.S_IMODE(output.stat().st_mode) == 0o700
    assert stat.S_IMODE((output / "start.json").stat().st_mode) == 0o600


def test_only_guarded_variant_repairs_an_unregistered_question_within_same_allowance(runtime):
    suite, catalog = fixture_inputs()
    bad = AnalysisResult(
        decision="ask",
        user_draft="Could you give some other detail?",
        maintainer_summary="The proposed question is not caller-registered.",
        rationale="Offline guard comparison.",
        next_question="Could you give some other detail?",
        missing_info=("other_detail",),
    )
    good = bad.model_copy(
        update={
            "user_draft": QUESTION,
            "next_question": QUESTION,
            "missing_info": ("diagnostic_context",),
        }
    )
    summary, calls = run(
        runtime,
        suite,
        catalog,
        fixture_plan(suite, catalog),
        [answer_body(content=bad.model_dump_json()) for _ in range(3)]
        + [answer_body(content=good.model_dump_json())],
    )
    assert len(calls) == 4
    assert summary["automatic_results"]["A"]["model_attempts"] == 1
    assert summary["automatic_results"]["B"]["model_attempts"] == 1
    assert summary["automatic_results"]["C"]["model_attempts"] == 2
    assert "ask_unregistered_target" in calls[-1]["messages"][0]["content"]


def test_new_unknown_usage_stops_batch_and_retains_original_and_new_holds(runtime):
    suite, catalog = fixture_inputs(2)
    summary, calls = run(
        runtime, suite, catalog, fixture_plan(suite, catalog), [answer_body(usage=False)]
    )
    assert len(calls) == 1
    assert summary["completed_observations"] == 1
    assert summary["stop_reason"] == "LedgerUnavailable"
    ledger, _, _ = runtime
    assert not ledger.continuation_status(CONTINUATION_ID).active
    assert ledger.snapshot().halted
    assert ledger.snapshot().uncertain_usd > Decimal("0.02")


def test_whole_comparison_cap_denies_next_condition_before_http(runtime):
    suite, catalog = fixture_inputs()
    request_reserve = get_price("gpt-4o-mini").cost(32768, 768)
    plan = fixture_plan(suite, catalog, cap_usd=request_reserve + Decimal("0.00001"))
    summary, calls = run(runtime, suite, catalog, plan, [answer_body()])
    assert len(calls) == 1
    assert summary["stop_reason"] == "BudgetExceeded"
    assert summary["paired_completed_case_ids"] == []
    assert runtime[0].snapshot().uncertain_usd == Decimal("0.02")


def test_existing_receipts_are_never_overwritten_or_resubmitted(runtime):
    suite, catalog = fixture_inputs()
    plan = fixture_plan(suite, catalog)
    run(runtime, suite, catalog, plan, [answer_body() for _ in range(3)])
    output = runtime[2]
    original = (output / "start.json").read_bytes()
    transport, calls = intercepted([])
    with pytest.raises(FileExistsError):
        run_quality_experiment(
            suite,
            catalog,
            plan,
            config=runtime[1],
            ledger=runtime[0],
            output_dir=output,
            transport=transport,
        )
    assert calls == []
    assert (output / "start.json").read_bytes() == original


@pytest.mark.parametrize("change", ["suite", "catalog", "live_opt_in"])
def test_registration_drift_and_absent_live_opt_in_fail_before_http_or_receipts(runtime, change):
    suite, catalog = fixture_inputs()
    plan = fixture_plan(suite, catalog)
    config = runtime[1]
    if change == "suite":
        probe = suite.cases[0].model_copy(update={"user_message": "Changed after registration"})
        suite = suite.model_copy(update={"cases": (probe,)})
    elif change == "catalog":
        catalog = {
            "probe-0": catalog["probe-0"].model_copy(update={"require_fresh_widget_value": True})
        }
    else:
        config = config.model_copy(update={"live_enabled": False})
    transport, calls = intercepted([])
    with pytest.raises(ValueError, match="changed|opt-in"):
        run_quality_experiment(
            suite,
            catalog,
            plan,
            config=config,
            ledger=runtime[0],
            output_dir=runtime[2],
            transport=transport,
        )
    assert calls == [] and not runtime[2].exists()


def test_scope_without_existing_grant_cannot_start_or_create_receipts(tmp_path):
    suite, catalog = fixture_inputs()
    ledger = BudgetLedger.create(
        tmp_path / "unapproved.sqlite3", limit_usd=Decimal("4.5"), opening_spend_usd=Decimal("0")
    )
    transport, calls = intercepted([])
    output = tmp_path / "unapproved-run"
    with pytest.raises(LedgerConflict):
        run_quality_experiment(
            suite,
            catalog,
            fixture_plan(suite, catalog),
            config=MetisConfig(api_key="synthetic-key", live_enabled=True),
            ledger=ledger,
            output_dir=output,
            transport=transport,
        )
    assert calls == [] and not output.exists()


def test_cli_offline_default_needs_neither_key_nor_ledger(monkeypatch, capsys):
    monkeypatch.delenv("METIS_API_KEY", raising=False)
    monkeypatch.setattr(sys, "argv", ["quality_experiments"])
    monkeypatch.setattr(
        quality_experiments,
        "run_quality_experiment",
        lambda *args, **kwargs: pytest.fail("Offline validation invoked a paid runner"),
    )
    quality_experiments.main()
    result = json.loads(capsys.readouterr().out)
    assert result["planned_observations"] == 27 and result["paid_requests"] == 0
