"""Offline experiment safety using intercepted HTTP and real temporary accounting."""

import hashlib
import json
import sys
from decimal import Decimal

import httpx
import pytest
from pydantic import SecretStr

from agent_app.contracts import (
    AnalysisResult,
    CaseState,
    EvidenceBundle,
    EvidenceHit,
    EvidenceLink,
    OutputFeedback,
    OutputIssue,
    ReasoningContext,
)
from agent_app.llm.budget import BudgetLedger
from agent_app.llm.config import MetisConfig
from agent_app.llm.metis import MetisReasoner, request_id_for
from agent_app.llm.pricing import get_price
from agent_app.orchestration.ports import ReasoningStopped
from agent_app.reasoning import experiments
from agent_app.reasoning.experiments import (
    ExperimentPlan,
    experiment_run_id,
    run_experiment,
    schedule,
)
from agent_app.reasoning.probes import DecisionProbe, ProbeExpectations, ProbeSuite

SNAPSHOT = "experiment-test-snapshot"
POLICIES = ("baseline", "decision_rubric", "bounded_rubric")


def bundle():
    return EvidenceBundle(
        snapshot_id=SNAPSHOT,
        hits=(
            EvidenceHit(
                chunk_id="docs:fixture",
                source_id="source:fixture",
                excerpt="A synthetic example provides no proof of a successful user fix.",
                source_url="https://example.org/offline-experiment-source",
                source_type="doc",
            ),
        ),
    )


def suite(case_count=1):
    return ProbeSuite(
        schema_version=1,
        snapshot_id=SNAPSHOT,
        purpose="Synthetic experiment accounting tests, not model-quality evaluation.",
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
                description="DESCRIPTION_NOT_MODEL_INPUT",
                case_state=CaseState(case_id=f"case:probe-{index}"),
                user_message="How should I investigate the counter reset?",
                bundles=(bundle(), bundle()),
                expectations=ProbeExpectations(
                    acceptable_decisions=("answer",),
                    required_terms=("ORACLE_EXPECTATION_ONLY",),
                    require_evidence=True,
                    require_uncertainty=True,
                    forbid_repeated_checks=True,
                ),
                reviewer_notes=("REVIEWER_NOTE_ONLY",),
            )
            for index in range(case_count)
        ),
    )


def plan(**changes):
    return ExperimentPlan(
        **(
            {
                "experiment_id": "offline-test",
                "suite_sha256": "a" * 64,
                "policies": ("baseline",),
                "scope": "Offline intercepted-HTTP experiment tests only.",
            }
            | changes
        )
    )


def answer():
    return AnalysisResult(
        decision="answer",
        user_draft="A synthetic answer proposed for human review.",
        maintainer_summary="Synthetic operational test only.",
        rationale="This checks output acceptance rather than factual quality.",
        evidence_links=(EvidenceLink(claim="Synthetic example", chunk_id="docs:fixture"),),
    )


def response_body(content=None, *, usage=True):
    body = {
        "model": "gpt-4o-mini",
        "choices": [
            {
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": content if content is not None else answer().model_dump_json(),
                },
            }
        ],
    }
    if usage:
        body["usage"] = {"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": 130}
    return body


@pytest.fixture
def setup_experiment(tmp_path):
    ledger = BudgetLedger.create(
        tmp_path / "budget.sqlite3", limit_usd=Decimal("1"), opening_spend_usd=Decimal("0")
    )
    config = MetisConfig(api_key=SecretStr("offline-test-key"), live_enabled=True)
    return ledger, config, tmp_path / "observations"


def transport_with(scripted):
    calls = []
    responses = iter(scripted)

    def handler(request):
        calls.append(json.loads(request.content))
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        return httpx.Response(200, json=response)

    return httpx.MockTransport(handler), calls


def request_reserve():
    price = get_price("gpt-4o-mini")
    return price.cost(16384, 768)


def settled_cost():
    return get_price("gpt-4o-mini").cost(100, 30)


def test_experiment_cap_refuses_the_first_call_before_http_or_receipt_creation(setup_experiment):
    ledger, config, output_dir = setup_experiment
    transport, calls = transport_with([response_body()])

    with pytest.raises(ReasoningStopped) as stopped:
        run_experiment(
            suite(),
            plan(cap_usd=request_reserve() / 2),
            config=config,
            ledger=ledger,
            output_dir=output_dir,
            transport=transport,
        )

    assert stopped.value.code == "BudgetExceeded"
    assert calls == []
    assert not output_dir.exists()
    assert ledger.snapshot().available_usd == Decimal("1")


def test_cap_is_checked_again_before_a_schema_repair_http_attempt(setup_experiment):
    ledger, config, output_dir = setup_experiment
    transport, calls = transport_with([response_body("not valid JSON"), response_body()])
    summary = run_experiment(
        suite(),
        plan(cap_usd=request_reserve() + settled_cost() / 2),
        config=config,
        ledger=ledger,
        output_dir=output_dir,
        transport=transport,
    )
    observation = json.loads((output_dir / "observation-00.json").read_text())

    assert len(calls) == 1
    assert observation["result"]["model_attempts"] == 2
    assert observation["result"]["error_code"] == "BudgetExceeded"
    assert observation["result"]["analysis"] is None
    assert len(observation["ledger_entries"]) == 1
    assert observation["ledger_entries"][0]["status"] == "settled"
    assert summary["stop_reason"] == "BudgetExceeded"
    assert ledger.snapshot().settled_usd == settled_cost()
    assert ledger.snapshot().reserved_usd == Decimal("0")


def test_cap_stops_before_the_next_case_without_another_http_request(setup_experiment):
    ledger, config, output_dir = setup_experiment
    transport, calls = transport_with([response_body(), response_body()])
    summary = run_experiment(
        suite(2),
        plan(cap_usd=request_reserve() + settled_cost() / 2),
        config=config,
        ledger=ledger,
        output_dir=output_dir,
        transport=transport,
    )

    assert len(calls) == summary["completed_observations"] == 1
    assert summary["planned_observations"] == 2
    assert summary["stop_reason"] == "BudgetExceeded"
    assert not (output_dir / "observation-01.json").exists()


@pytest.mark.parametrize(
    ("first_response", "stop_code", "halted"),
    [
        (httpx.ReadTimeout("simulated timeout"), "ProviderRequestFailed", False),
        (response_body(usage=False), "ProviderUsageUnknown", True),
    ],
)
def test_uncertain_accounting_stops_the_entire_batch_without_retry(
    setup_experiment, first_response, stop_code, halted
):
    ledger, config, output_dir = setup_experiment
    transport, calls = transport_with([first_response, response_body()])
    summary = run_experiment(
        suite(2),
        plan(policies=POLICIES),
        config=config,
        ledger=ledger,
        output_dir=output_dir,
        transport=transport,
    )
    observation = json.loads((output_dir / "observation-00.json").read_text())

    assert len(calls) == summary["completed_observations"] == 1
    assert summary["planned_observations"] == 6
    assert summary["stop_reason"] == "UnreconciledLedger"
    assert observation["result"]["model_attempts"] == 1
    assert observation["result"]["error_code"] == stop_code
    assert ledger.snapshot().uncertain_usd == request_reserve()
    assert ledger.snapshot().halted is halted
    assert not (output_dir / "observation-01.json").exists()


@pytest.mark.parametrize("reservation_status", ["reserved", "uncertain"])
def test_an_existing_unreconciled_request_refuses_experiment_start(
    setup_experiment, reservation_status
):
    ledger, config, output_dir = setup_experiment
    ledger.reserve(
        request_id="call:interrupted",
        run_id="run:interrupted",
        case_id="case:interrupted",
        case_revision=0,
        attempt=1,
        model="gpt-4o-mini",
        phase="development",
        amount_usd=Decimal("0.01"),
    )
    if reservation_status == "uncertain":
        ledger.mark_uncertain("call:interrupted", error_code="ProviderRequestFailed")
    before = ledger.snapshot()
    transport, calls = transport_with([response_body()])

    with pytest.raises(ReasoningStopped) as stopped:
        run_experiment(
            suite(),
            plan(),
            config=config,
            ledger=ledger,
            output_dir=output_dir,
            transport=transport,
        )

    assert stopped.value.code == "LedgerUnavailable"
    assert calls == []
    assert not output_dir.exists()
    assert ledger.snapshot() == before


def test_existing_receipt_directory_cannot_restart_or_resend_the_batch(setup_experiment):
    ledger, config, output_dir = setup_experiment
    transport, calls = transport_with([response_body(), response_body()])
    arguments = {
        "config": config,
        "ledger": ledger,
        "output_dir": output_dir,
        "transport": transport,
    }
    run_experiment(suite(), plan(), **arguments)
    first_summary = (output_dir / "summary.json").read_bytes()
    before = ledger.snapshot()

    with pytest.raises(FileExistsError):
        run_experiment(suite(), plan(), **arguments)

    assert len(calls) == 1
    assert ledger.snapshot() == before
    assert (output_dir / "summary.json").read_bytes() == first_summary


def test_expectation_and_reviewer_oracles_never_enter_any_policy_prompt(setup_experiment):
    ledger, config, output_dir = setup_experiment
    transport, calls = transport_with([response_body()] * 3)
    summary = run_experiment(
        suite(),
        plan(policies=POLICIES),
        config=config,
        ledger=ledger,
        output_dir=output_dir,
        transport=transport,
    )

    assert summary["completed_observations"] == len(calls) == 3
    for call in calls:
        serialized = json.dumps(call["messages"])
        assert "ORACLE_EXPECTATION_ONLY" not in serialized
        assert "REVIEWER_NOTE_ONLY" not in serialized
        assert "DESCRIPTION_NOT_MODEL_INPUT" not in serialized
        payload = json.loads(call["messages"][1]["content"])
        assert "expectations" not in payload
        assert "reviewer_notes" not in payload
        assert payload["evidence"] == bundle().model_dump(mode="json")


def test_feedback_and_workflow_hints_cannot_create_a_fresh_billable_identity(setup_experiment):
    ledger, config, _ = setup_experiment
    probe = suite().cases[0]
    base = ReasoningContext(
        run_id="run:stable-attempt",
        case_id=probe.case_state.case_id,
        case_revision=0,
        attempt_index=2,
    )
    hinted = base.model_copy(
        update={
            "query_limit": 1,
            "remaining_retrieval_rounds": 1,
            "output_feedback": OutputFeedback(issues=(OutputIssue(code="invalid_json"),)),
        }
    )
    transport, calls = transport_with([response_body(), response_body()])
    with MetisReasoner(config, ledger, transport=transport) as first:
        first.analyze(probe.case_state, probe.user_message, bundle(), context=base)
    with MetisReasoner(
        config.model_copy(update={"prompt_policy": "bounded_rubric"}),
        ledger,
        transport=transport,
    ) as second:
        with pytest.raises(ReasoningStopped) as stopped:
            second.analyze(probe.case_state, probe.user_message, bundle(), context=hinted)

    assert request_id_for(base) == request_id_for(hinted)
    legacy_identity = json.dumps(
        {
            "run_id": base.run_id,
            "case_id": base.case_id,
            "case_revision": base.case_revision,
            "attempt_index": base.attempt_index,
        },
        separators=(",", ":"),
    )
    assert request_id_for(base) == "call:" + hashlib.sha256(legacy_identity.encode()).hexdigest()
    assert stopped.value.code == "DuplicateModelRequest"
    assert len(calls) == 1
    assert ledger.get(request_id_for(base)).status == "settled"


def test_default_validation_cli_needs_neither_credentials_nor_a_ledger(
    tmp_path, monkeypatch, capsys
):
    suite_path = tmp_path / "suite.json"
    suite_path.write_text(suite().model_dump_json())
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(plan(suite_sha256=experiments.sha256_file(suite_path)).model_dump_json())
    missing_ledger = tmp_path / "never-create.sqlite3"
    monkeypatch.delenv("METIS_API_KEY", raising=False)
    monkeypatch.setenv("METIS_LIVE_ENABLED", "true")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "experiments",
            "--suite",
            str(suite_path),
            "--plan",
            str(plan_path),
            "--ledger",
            str(missing_ledger),
        ],
    )

    def forbid_credentials():
        pytest.fail("Default validation must not read credentials")

    monkeypatch.setattr(MetisConfig, "from_env", forbid_credentials)
    experiments.main()
    output = json.loads(capsys.readouterr().out)

    assert output["validated"] is True
    assert output["paid_requests"] == 0
    assert not missing_ledger.exists()


def test_allowed_decision_agreement_does_not_claim_semantic_correctness(setup_experiment):
    ledger, config, output_dir = setup_experiment
    unsupported = answer().model_copy(
        update={"user_draft": "This unverified change is guaranteed to resolve the issue."}
    )
    transport, _ = transport_with([response_body(unsupported.model_dump_json())])
    summary = run_experiment(
        suite(),
        plan(),
        config=config,
        ledger=ledger,
        output_dir=output_dir,
        transport=transport,
    )
    observation = json.loads((output_dir / "observation-00.json").read_text())

    assert observation["automatic"]["allowed_final_decision"] is True
    assert observation["semantic_review"] is None
    assert summary["automatic_results"]["baseline"]["allowed_final_decisions"] == 1
    assert summary["semantic_quality"] == "Requires source-backed review"
    assert "quality_score" not in summary
    assert "best_policy" not in summary


def test_policy_order_rotates_while_each_policy_receives_the_same_fixed_case():
    probe_suite = suite(3)
    planned = list(schedule(probe_suite, plan(policies=POLICIES)))
    repeated = list(schedule(probe_suite, plan(policies=POLICIES)))

    assert planned == repeated
    assert [(probe.id, policy) for probe, policy in planned] == [
        ("probe-0", "baseline"),
        ("probe-0", "decision_rubric"),
        ("probe-0", "bounded_rubric"),
        ("probe-1", "decision_rubric"),
        ("probe-1", "bounded_rubric"),
        ("probe-1", "baseline"),
        ("probe-2", "bounded_rubric"),
        ("probe-2", "baseline"),
        ("probe-2", "decision_rubric"),
    ]
    for probe in probe_suite.cases:
        assert sum(scheduled is probe for scheduled, _ in planned) == 3


def test_protocol_validation_rejects_changed_suite_before_any_run(tmp_path):
    suite_path = tmp_path / "suite.json"
    suite_path.write_text(suite().model_dump_json())
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(plan(suite_sha256=experiments.sha256_file(suite_path)).model_dump_json())
    suite_path.write_text(suite(2).model_dump_json())

    with pytest.raises(ValueError, match="Suite changed"):
        experiments.validate_inputs(suite_path, plan_path)


def test_long_valid_probe_ids_use_stable_bounded_distinct_run_identities(setup_experiment):
    ledger, config, output_dir = setup_experiment
    long_id = "p" * 200
    initial = suite()
    long_probe = initial.cases[0].model_copy(update={"id": long_id})
    long_suite = initial.model_copy(update={"cases": (long_probe,)})
    run_id = experiment_run_id("offline-test", "baseline", long_id)
    assert run_id == experiment_run_id("offline-test", "baseline", long_id)
    assert len(run_id) <= 200
    assert (
        len(
            {
                run_id,
                experiment_run_id("other-test", "baseline", long_id),
                experiment_run_id("offline-test", "decision_rubric", long_id),
                experiment_run_id("offline-test", "baseline", "q" * 200),
            }
        )
        == 4
    )
    transport, calls = transport_with([response_body()])
    summary = run_experiment(
        long_suite,
        plan(),
        config=config,
        ledger=ledger,
        output_dir=output_dir,
        transport=transport,
    )
    observation = json.loads((output_dir / "observation-00.json").read_text())

    assert len(calls) == summary["completed_observations"] == 1
    assert observation["case_id"] == long_id
    assert observation["result"]["status"] == "awaiting_approval"
    assert observation["contexts"][0]["run_id"] == run_id
