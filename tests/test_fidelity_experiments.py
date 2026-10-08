"""Fixed fidelity runner checks using temporary ledgers and intercepted HTTP only."""

import json
import stat
import sys
from decimal import Decimal

import httpx
import pytest
from pydantic import ValidationError

from agent_app.contracts import (
    AnalysisResult,
    CaseState,
    EvidenceBundle,
    EvidenceHit,
    EvidenceLink,
    ReasoningContext,
)
from agent_app.llm.budget import BudgetLedger, LedgerConflict
from agent_app.llm.config import MetisConfig
from agent_app.llm.metis import request_id_for
from agent_app.llm.pricing import get_price
from agent_app.orchestration.ports import ReasoningStopped
from agent_app.reasoning import fidelity_experiments
from agent_app.reasoning.experiments import sha256_file
from agent_app.reasoning.fidelity_experiments import (
    CONTINUATION_ID,
    POLICIES,
    FidelityExperimentPlan,
    fidelity_run_id,
    fidelity_schedule,
    run_fidelity_experiment,
    schedule_content_sha256,
    suite_content_sha256,
    validate_fidelity_data,
    validate_fidelity_inputs,
)
from agent_app.reasoning.probes import DecisionProbe, ProbeExpectations, ProbeSuite


def fixture_suite(case_count=1):
    bundle = EvidenceBundle(
        snapshot_id="fidelity-offline-snapshot",
        hits=(
            EvidenceHit(
                chunk_id="docs:fixture",
                source_id="source:fixture",
                excerpt="PRIVATE_SOURCE_MARKER synthetic transport fixture.",
                source_url="https://example.org/offline",
                source_type="doc",
            ),
        ),
    )
    return ProbeSuite(
        schema_version=1,
        snapshot_id=bundle.snapshot_id,
        purpose="Offline runner tests only; no model-quality evidence.",
        docs_commit="fixture-commit",
        source_snapshot_date="2026-10-08",
        reserved_issue_ids=(),
        cases=tuple(
            DecisionProbe(
                id=f"probe-{index}",
                kind="synthetic",
                origin_url=None,
                origin_issue_id=None,
                origin_created_at=None,
                description="DESCRIPTION_REVIEWER_ONLY",
                case_state=CaseState(case_id=f"case:fidelity-{index}"),
                user_message="PRIVATE_USER_MARKER: explain this synthetic observation.",
                bundles=(bundle, bundle.model_copy(update={"retrieval_round": 2})),
                expectations=ProbeExpectations(
                    acceptable_decisions=("answer",),
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


def fixture_plan(suite, **changes):
    schedule = fidelity_schedule(suite)
    return FidelityExperimentPlan(
        **(
            {
                "experiment_id": "offline-fidelity-test",
                "suite_sha256": "a" * 64,
                "suite_content_sha256": suite_content_sha256(suite),
                "case_count": len(suite.cases),
                "schedule": schedule,
                "schedule_sha256": schedule_content_sha256(schedule),
                "scope": "Offline intercepted-HTTP synthetic fidelity runner tests only.",
            }
            | changes
        )
    )


def write_registration(tmp_path, suite):
    suite_path = tmp_path / "cases-fidelity-v7.json"
    suite_path.write_text(suite.model_dump_json())
    plan = fixture_plan(suite, suite_sha256=sha256_file(suite_path))
    plan_path = tmp_path / "protocol.json"
    plan_path.write_text(plan.model_dump_json())
    return plan_path, suite_path


def answer_body(*, usage=True, content=None):
    analysis = AnalysisResult(
        decision="answer",
        user_draft="Synthetic source-backed proposal for human review.",
        maintainer_summary="Offline transport and accounting test only.",
        rationale="Verifies runner behavior, not semantic model quality.",
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


def run(runtime, suite, plan, responses, *, progress=None):
    ledger, config, output = runtime
    transport, calls = intercepted(responses)
    summary = run_fidelity_experiment(
        suite,
        plan,
        config=config,
        ledger=ledger,
        output_dir=output,
        transport=transport,
        progress=progress,
    )
    return summary, calls


def test_six_case_schedule_completes_first_pairs_before_repeats_with_flipped_order():
    suite = fixture_suite(6)
    schedule = fidelity_schedule(suite)
    assert len(schedule) == 24
    assert [entry.replicate for entry in schedule] == [1] * 12 + [2] * 12
    for index, probe in enumerate(suite.cases):
        first = schedule[2 * index : 2 * index + 2]
        repeat = schedule[12 + 2 * index : 12 + 2 * index + 2]
        assert [entry.case_id for entry in first + repeat] == [probe.id] * 4
        assert [entry.policy for entry in first] == list(POLICIES[:: 1 if index % 2 == 0 else -1])
        assert [entry.policy for entry in repeat] == [entry.policy for entry in first][::-1]
    assert schedule_content_sha256(schedule) != schedule_content_sha256(schedule[::-1])


def test_repeated_draw_request_identities_are_distinct_without_changing_case_or_attempt():
    suite = fixture_suite(6)
    identities = set()
    for entry in fidelity_schedule(suite):
        probe = next(probe for probe in suite.cases if probe.id == entry.case_id)
        run_id = fidelity_run_id("registered-run", entry.replicate, entry.policy, probe.id)
        identities.add(
            request_id_for(
                ReasoningContext(
                    run_id=run_id,
                    case_id=probe.case_state.case_id,
                    case_revision=probe.case_state.case_revision,
                    attempt_index=1,
                    remaining_model_attempts=1,
                    remaining_retrieval_rounds=1,
                    can_refine=True,
                    query_limit=2,
                )
            )
        )
    assert len(identities) == 24


@pytest.mark.parametrize(
    "change",
    [
        {"policies": ("fidelity_rules", "structured_rules")},
        {"policies": ("structured_rules",)},
        {"policies": ("structured_rules", "grounded_rules")},
        {"proposal_checks": True},
        {"proposal_checks": 0},
        {"replicates": 1},
        {"replicates": 2.0},
        {"model": "gpt-4.1-mini"},
        {"input_token_reserve": 16384},
        {"input_token_reserve": 32768.0},
        {"max_output_tokens": 1024},
        {"max_output_tokens": 768.0},
        {"continuation_id": "newly-refreshed-scope"},
        {"cap_usd": Decimal("0.030000001")},
        {"cap_usd": Decimal("0")},
        {"cap_usd": Decimal("NaN")},
        {"case_count": 7},
        {"suite_filename": "../elsewhere.json"},
    ],
)
def test_fixed_design_rejects_policy_flag_scope_and_reservation_changes(change):
    with pytest.raises(ValidationError):
        fixture_plan(fixture_suite(), **change)


def test_schedule_hash_and_fixed_algorithm_both_have_to_match():
    suite = fixture_suite(2)
    schedule = fidelity_schedule(suite)[::-1]
    with pytest.raises(ValidationError, match="schedule does not match"):
        fixture_plan(suite, schedule=schedule)
    forged_plan = fixture_plan(
        suite, schedule=schedule, schedule_sha256=schedule_content_sha256(schedule)
    )
    with pytest.raises(ValueError, match="schedule differs"):
        validate_fidelity_data(suite, forged_plan)


def test_file_bytes_are_frozen_even_when_json_contents_are_unchanged(tmp_path):
    suite = fixture_suite()
    plan_path, suite_path = write_registration(tmp_path, suite)
    validate_fidelity_inputs(plan_path)
    suite_path.write_text(suite_path.read_text() + "\n")
    with pytest.raises(ValueError, match="file changed"):
        validate_fidelity_inputs(plan_path)


def test_synthetic_boundary_rejects_report_attribution_even_with_updated_hash():
    suite = fixture_suite()
    probe = suite.cases[0].model_copy(update={"origin_url": "https://example.org/issues/123"})
    suite = suite.model_copy(update={"cases": (probe,)})
    with pytest.raises(ValueError, match="synthetic development"):
        validate_fidelity_data(suite, fixture_plan(suite))


def test_complete_replicates_record_separate_pairs_private_receipts_and_original_hold(runtime):
    suite = fixture_suite(2)
    plan = fixture_plan(suite)
    progress = []
    original_hold = runtime[0].get("request:offline-quarantine")
    summary, calls = run(
        runtime, suite, plan, [answer_body() for _ in range(8)], progress=progress.append
    )
    assert len(calls) == summary["completed_observations"] == summary["planned_observations"] == 8
    assert summary["stop_reason"] is None
    assert summary["completed_case_replicate_pairs"] == [
        {"case_id": "probe-0", "replicate": 1},
        {"case_id": "probe-1", "replicate": 1},
        {"case_id": "probe-0", "replicate": 2},
        {"case_id": "probe-1", "replicate": 2},
    ]
    assert summary["fully_repeated_case_ids"] == ["probe-0", "probe-1"]
    assert all(group["observations"] == 4 for group in summary["automatic_results"].values())
    assert summary["repeated_draws_are_independent_cases"] is False
    for call in calls:
        payload = json.loads(call["messages"][1]["content"])
        assert "proposal_requirements" not in payload
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
    observations = [
        json.loads((output / f"observation-{index:02d}.json").read_text()) for index in range(8)
    ]
    assert len({item["ledger_entries"][0]["request_id"] for item in observations}) == 8
    assert all(item["http_attempts"] == [{"status": 200}] for item in observations)
    assert all(item["proposal_checks"] is False for item in observations)
    assert ledger.snapshot().halted and ledger.snapshot().uncertain_usd == Decimal("0.02")
    assert ledger.get("request:offline-quarantine") == original_hold
    assert "PRIVATE_USER_MARKER" not in json.dumps(progress)
    assert "PRIVATE_SOURCE_MARKER" not in json.dumps(progress)
    start = json.loads((output / "start.json").read_text())
    assert start["schedule_sha256"] == plan.schedule_sha256
    assert len(start["code_sha256"]) == 64
    assert stat.S_IMODE(output.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in output.iterdir())


def test_all_twenty_four_draws_fit_with_known_simulated_usage_under_registered_cap(runtime):
    suite = fixture_suite(6)
    responses = []
    for _ in range(24):
        response = answer_body()
        response["usage"] = {"prompt_tokens": 4000, "completion_tokens": 400, "total_tokens": 4400}
        responses.append(response)
    summary, calls = run(runtime, suite, fixture_plan(suite), responses)
    assert len(calls) == summary["paid_http_requests"] == summary["attempted_observations"] == 24
    assert summary["accepted_observations"] == 24
    assert len(summary["completed_case_replicate_pairs"]) == 12
    assert len(summary["accepted_case_replicate_pairs"]) == 12
    assert summary["fully_repeated_case_ids"] == [probe.id for probe in suite.cases]
    assert Decimal(summary["estimated_exposure_delta_usd"]) == Decimal("0.022176000")
    assert summary["stop_reason"] is None


@pytest.mark.parametrize("recover", [True, False])
def test_format_repair_uses_same_two_attempt_allowance_without_a_third_request(runtime, recover):
    suite = fixture_suite()
    second = answer_body() if recover else answer_body(content="{invalid-json}")
    summary, calls = run(
        runtime,
        suite,
        fixture_plan(suite),
        [answer_body(content="{invalid-json}"), second] + [answer_body() for _ in range(3)],
    )
    assert len(calls) == 5 and summary["completed_observations"] == 4
    first = json.loads((runtime[2] / "observation-00.json").read_text())
    assert first["automatic"]["model_attempts"] == 2
    assert first["automatic"]["accepted"] is recover
    assert [context["attempt_index"] for context in first["contexts"]] == [1, 2]
    assert len({context["run_id"] for context in first["contexts"]}) == 1
    assert len({entry["request_id"] for entry in first["ledger_entries"]}) == 2
    assert "Your previous attempt failed output validation" in calls[1]["messages"][0]["content"]


@pytest.mark.parametrize("completed", [1, 2])
def test_cap_denies_next_http_and_honestly_reports_incomplete_pairs(runtime, completed):
    suite = fixture_suite(2)
    price = get_price("gpt-4o-mini")
    reserve = price.cost(32768, 768)
    settled_cost = price.cost(100, 30)
    cap = reserve + settled_cost * (Decimal(completed) - Decimal("0.5"))
    plan = fixture_plan(suite, cap_usd=cap)
    summary, calls = run(runtime, suite, plan, [answer_body() for _ in range(completed)])
    assert len(calls) == summary["completed_observations"] == completed
    assert summary["stop_reason"] == "BudgetExceeded"
    assert summary["completed_case_replicate_pairs"] == (
        [{"case_id": "probe-0", "replicate": 1}] if completed == 2 else []
    )
    assert summary["fully_repeated_case_ids"] == []
    assert runtime[0].snapshot().uncertain_usd == Decimal("0.02")


def test_cap_below_one_reservation_cannot_send_http_or_create_receipts(runtime):
    suite = fixture_suite()
    plan = fixture_plan(suite, cap_usd=Decimal("0.001"))
    transport, calls = intercepted([])
    with pytest.raises(ReasoningStopped, match="BudgetExceeded"):
        run_fidelity_experiment(
            suite,
            plan,
            config=runtime[1],
            ledger=runtime[0],
            output_dir=runtime[2],
            transport=transport,
        )
    assert calls == [] and not runtime[2].exists()


def test_budget_denied_repair_is_recorded_as_attempted_with_one_paid_http(runtime):
    suite = fixture_suite()
    reserve = get_price("gpt-4o-mini").cost(32768, 768)
    plan = fixture_plan(suite, cap_usd=reserve + Decimal("0.00001"))
    summary, calls = run(runtime, suite, plan, [answer_body(content="{invalid-json}")])
    assert len(calls) == summary["paid_http_requests"] == 1
    assert summary["attempted_observations"] == summary["completed_observations"] == 1
    assert summary["accepted_observations"] == 0
    assert summary["stop_reason"] == "BudgetExceeded"
    assert summary["completed_case_replicate_pairs"] == []
    assert summary["accepted_case_replicate_pairs"] == []
    first = json.loads((runtime[2] / "observation-00.json").read_text())
    assert first["result"]["status"] == "budget_stopped"
    assert first["automatic"]["model_attempts"] == 2
    assert len(first["ledger_entries"]) == 1
    assert first["result"]["analysis"] is None


def test_original_scope_cap_denies_before_http_despite_large_global_available_balance(runtime):
    ledger = runtime[0]
    for index in range(5):
        request_id = f"request:prior-scoped-{index}"
        ledger.reserve(
            request_id=request_id,
            run_id=f"run:prior-scoped-{index}",
            case_id=f"case:prior-scoped-{index}",
            case_revision=0,
            attempt=1,
            model="gpt-4o-mini",
            phase="development",
            amount_usd=Decimal("0.019"),
            continuation_id=CONTINUATION_ID,
        )
        ledger.settle(request_id, cost_usd=Decimal("0.019"), input_tokens=1, output_tokens=1)
    scope_before = ledger.continuation_status(CONTINUATION_ID)
    assert scope_before.remaining_usd == Decimal("0.005")
    assert ledger.snapshot().available_usd > Decimal("4")
    suite = fixture_suite()
    transport, calls = intercepted([])
    with pytest.raises(ReasoningStopped, match="BudgetExceeded"):
        run_fidelity_experiment(
            suite,
            fixture_plan(suite),
            config=runtime[1],
            ledger=ledger,
            output_dir=runtime[2],
            transport=transport,
        )
    assert calls == [] and not runtime[2].exists()
    assert ledger.continuation_status(CONTINUATION_ID) == scope_before
    assert ledger.snapshot().halted and ledger.snapshot().uncertain_usd == Decimal("0.02")


def test_new_unknown_usage_revokes_scope_and_preserves_original_and_new_holds(runtime):
    suite = fixture_suite(2)
    original_hold = runtime[0].get("request:offline-quarantine")
    summary, calls = run(runtime, suite, fixture_plan(suite), [answer_body(usage=False)])
    assert len(calls) == summary["completed_observations"] == 1
    assert summary["stop_reason"] == "LedgerUnavailable"
    assert summary["completed_case_replicate_pairs"] == []
    ledger = runtime[0]
    assert not ledger.continuation_status(CONTINUATION_ID).active
    assert ledger.snapshot().halted and ledger.snapshot().uncertain_usd > Decimal("0.02")
    assert ledger.get("request:offline-quarantine") == original_hold


def test_pending_request_blocks_batch_without_releasing_reservation(runtime):
    suite = fixture_suite()
    ledger = runtime[0]
    pending = ledger.reserve(
        request_id="request:pending",
        run_id="run:pending",
        case_id="case:pending",
        case_revision=0,
        attempt=1,
        model="gpt-4o-mini",
        phase="development",
        amount_usd=Decimal("0.001"),
        continuation_id=CONTINUATION_ID,
    )
    transport, calls = intercepted([])
    with pytest.raises(ReasoningStopped, match="LedgerUnavailable"):
        run_fidelity_experiment(
            suite,
            fixture_plan(suite),
            config=runtime[1],
            ledger=ledger,
            output_dir=runtime[2],
            transport=transport,
        )
    assert calls == [] and not runtime[2].exists()
    assert ledger.get("request:pending") == pending


def test_existing_receipts_are_never_overwritten_or_resubmitted(runtime):
    suite = fixture_suite()
    plan = fixture_plan(suite)
    run(runtime, suite, plan, [answer_body() for _ in range(4)])
    original = (runtime[2] / "start.json").read_bytes()
    transport, calls = intercepted([])
    with pytest.raises(FileExistsError):
        run_fidelity_experiment(
            suite,
            plan,
            config=runtime[1],
            ledger=runtime[0],
            output_dir=runtime[2],
            transport=transport,
        )
    assert calls == [] and (runtime[2] / "start.json").read_bytes() == original


@pytest.mark.parametrize("change", ["suite", "plan", "live_opt_in"])
def test_bypassed_registration_or_absent_opt_in_fails_before_http_or_receipts(runtime, change):
    suite = fixture_suite()
    plan = fixture_plan(suite)
    config = runtime[1]
    if change == "suite":
        probe = suite.cases[0].model_copy(update={"user_message": "Changed after registration"})
        suite = suite.model_copy(update={"cases": (probe,)})
    elif change == "plan":
        plan = plan.model_copy(update={"proposal_checks": True})
    else:
        config = config.model_copy(update={"live_enabled": False})
    transport, calls = intercepted([])
    with pytest.raises(ValueError, match="changed|design|opt-in"):
        run_fidelity_experiment(
            suite,
            plan,
            config=config,
            ledger=runtime[0],
            output_dir=runtime[2],
            transport=transport,
        )
    assert calls == [] and not runtime[2].exists()


def test_scope_without_existing_authorization_cannot_start_or_create_receipts(tmp_path):
    suite = fixture_suite()
    ledger = BudgetLedger.create(
        tmp_path / "unapproved.sqlite3", limit_usd=Decimal("4.5"), opening_spend_usd=Decimal("0")
    )
    transport, calls = intercepted([])
    output = tmp_path / "unapproved-run"
    with pytest.raises(LedgerConflict):
        run_fidelity_experiment(
            suite,
            fixture_plan(suite),
            config=MetisConfig(api_key="synthetic-offline-key", live_enabled=True),
            ledger=ledger,
            output_dir=output,
            transport=transport,
        )
    assert calls == [] and not output.exists()


def test_cli_offline_default_reads_no_key_configuration_or_ledger(tmp_path, monkeypatch, capsys):
    plan_path, _ = write_registration(tmp_path, fixture_suite(6))
    monkeypatch.delenv("METIS_API_KEY", raising=False)
    monkeypatch.setattr(sys, "argv", ["fidelity_experiments", "--plan", str(plan_path)])
    monkeypatch.setattr(
        fidelity_experiments,
        "run_fidelity_experiment",
        lambda *args, **kwargs: pytest.fail("Offline validation invoked the paid runner"),
    )
    monkeypatch.setattr(
        fidelity_experiments.MetisConfig,
        "from_env",
        lambda *args, **kwargs: pytest.fail("Offline validation accessed key configuration"),
    )
    monkeypatch.setattr(
        fidelity_experiments,
        "BudgetLedger",
        lambda *args, **kwargs: pytest.fail("Offline validation accessed a ledger"),
    )
    fidelity_experiments.main()
    result = json.loads(capsys.readouterr().out)
    assert result["planned_observations"] == 24 and result["paid_requests"] == 0
    assert result["cases"] == 6 and result["replicates"] == 2


def test_cli_errors_disclose_only_exception_type(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        sys, "argv", ["fidelity_experiments", "--plan", str(tmp_path / "missing.json")]
    )
    with pytest.raises(SystemExit, match="1"):
        fidelity_experiments.main()
    assert json.loads(capsys.readouterr().out) == {
        "failed": True,
        "error_type": "FileNotFoundError",
    }
