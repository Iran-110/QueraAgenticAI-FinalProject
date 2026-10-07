"""Offline continuation integration with intercepted HTTP and temporary ledgers."""

import json
from decimal import Decimal

import httpx
import pytest
from pydantic import SecretStr

from agent_app.contracts import AnalysisResult, CaseState, EvidenceBundle, ReasoningContext
from agent_app.llm.budget import BudgetLedger
from agent_app.llm.config import MetisConfig
from agent_app.llm.metis import MetisReasoner, request_id_for
from agent_app.orchestration.ports import ReasoningStopped
from agent_app.reasoning.experiments import ExperimentPlan, run_experiment
from agent_app.reasoning.probes import DecisionProbe, ProbeExpectations, ProbeSuite

GRANT = "offline-continued-experiment"
INCIDENT = "request:quarantined-provider-mismatch"
HOLD = Decimal("0.02")
REQUEST_RESERVE = Decimal("0.003210240")
OBSERVED_COST = Decimal("0.000214500")
SNAPSHOT = "continuation-integration-fixture"


def probe_suite():
    return ProbeSuite(
        schema_version=1,
        snapshot_id=SNAPSHOT,
        purpose="Synthetic accounting integration only, not model quality.",
        docs_commit="offline-fixture",
        source_snapshot_date="2026-10-07",
        reserved_issue_ids=(),
        cases=(
            DecisionProbe(
                id="continuation-probe",
                kind="synthetic",
                origin_url=None,
                origin_issue_id=None,
                origin_created_at=None,
                description="Offline explicit-grant experiment.",
                case_state=CaseState(case_id="case:continuation"),
                user_message="The counter resets. What information is needed?",
                bundles=(
                    EvidenceBundle(snapshot_id=SNAPSHOT, retrieval_round=1),
                    EvidenceBundle(snapshot_id=SNAPSHOT, retrieval_round=2),
                ),
                expectations=ProbeExpectations(
                    acceptable_decisions=("ask",),
                    require_evidence=False,
                    require_uncertainty=True,
                    forbid_repeated_checks=True,
                ),
                reviewer_notes=("Synthetic transport and accounting test only.",),
            ),
        ),
    )


def plan(**changes):
    return ExperimentPlan(
        **(
            {
                "experiment_id": "offline-continuation",
                "suite_sha256": "c" * 64,
                "policies": ("baseline",),
                "continuation_id": GRANT,
                "scope": "Offline temporary-ledger continuation tests only.",
            }
            | changes
        )
    )


def ask_response(*, content=None, model="gpt-4o-mini", usage=True):
    analysis = AnalysisResult(
        decision="ask",
        user_draft="Please provide the installed Streamlit version.",
        maintainer_summary="A user environment fact is still missing.",
        rationale="The installed version helps target the next investigation.",
        missing_info=("streamlit_version",),
        next_question="Which Streamlit version is installed?",
    )
    response = {
        "model": model,
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
        response["usage"] = {
            "prompt_tokens": 500,
            "completion_tokens": 200,
            "total_tokens": 700,
        }
    return response


def intercepted(responses):
    scripted = iter(responses)
    calls = []

    def handle(request):
        calls.append(json.loads(request.content))
        item = next(scripted)
        if isinstance(item, Exception):
            raise item
        return httpx.Response(200, json=item)

    return httpx.MockTransport(handle), calls


@pytest.fixture
def halted_runner(tmp_path):
    ledger = BudgetLedger.create(
        tmp_path / "budget.sqlite3", limit_usd=Decimal("4.50"), opening_spend_usd=Decimal("0")
    )
    ledger.reserve(
        request_id=INCIDENT,
        run_id="run:old-incident",
        case_id="case:old-incident",
        case_revision=0,
        attempt=1,
        model="gpt-4.1-mini",
        phase="development",
        amount_usd=Decimal("0.008560640"),
    )
    ledger.mark_uncertain(INCIDENT, error_code="ProviderModelMismatch")
    ledger.halt()
    config = MetisConfig(api_key=SecretStr("synthetic-offline-credential"), live_enabled=True)
    return ledger, config, tmp_path / "observations"


def authorize(ledger):
    return ledger.authorize_continuation(
        authorization_id=GRANT,
        authorization_ref="user:synthetic-test-authorization",
        expected_request_id=INCIDENT,
        held_usd=HOLD,
        allowed_model="gpt-4o-mini",
        additional_cap_usd=Decimal("0.10"),
    )


def observation(output_dir, index=0):
    return json.loads((output_dir / f"observation-{index:02d}.json").read_text())


def test_normal_experiment_stays_blocked_after_a_grant_exists(halted_runner):
    ledger, config, output_dir = halted_runner
    authorize(ledger)
    transport, calls = intercepted([ask_response()])
    with pytest.raises(ReasoningStopped) as stopped:
        run_experiment(
            probe_suite(),
            plan(continuation_id=None),
            config=config,
            ledger=ledger,
            output_dir=output_dir,
            transport=transport,
        )
    assert stopped.value.code == "LedgerUnavailable"
    assert calls == []
    assert not output_dir.exists()
    assert ledger.snapshot().halted
    assert ledger.continuation_status(GRANT).used_usd == Decimal("0")


@pytest.mark.parametrize("continuation_id", [None, "unrecognized-grant"])
def test_normal_gateway_cannot_use_another_runners_grant(halted_runner, continuation_id):
    ledger, config, _ = halted_runner
    authorize(ledger)
    config = config.model_copy(update={"continuation_id": continuation_id})
    transport, calls = intercepted([ask_response()])
    case = CaseState(case_id="case:ungranted-gateway")
    context = ReasoningContext(
        run_id="run:ungranted-gateway", case_id=case.case_id, case_revision=0, attempt_index=1
    )
    with MetisReasoner(config, ledger, transport=transport) as reasoner:
        with pytest.raises(ReasoningStopped) as stopped:
            reasoner.analyze(
                case,
                "Which environment fact is missing?",
                EvidenceBundle(snapshot_id=SNAPSHOT),
                context=context,
            )
    assert stopped.value.code == "BudgetExceeded"
    assert calls == []
    assert ledger.get(request_id_for(context)) is None
    assert ledger.snapshot().uncertain_usd == HOLD


def test_explicit_grant_runs_a_batch_without_clearing_the_global_halt(halted_runner):
    ledger, config, output_dir = halted_runner
    authorize(ledger)
    transport, calls = intercepted([ask_response(), ask_response()])
    result = run_experiment(
        probe_suite(),
        plan(policies=("baseline", "decision_rubric")),
        config=config,
        ledger=ledger,
        output_dir=output_dir,
        transport=transport,
    )
    assert len(calls) == result["completed_observations"] == 2
    assert result["stop_reason"] is None
    assert all(call["model"] == "gpt-4o-mini" for call in calls)
    start = json.loads((output_dir / "start.json").read_text())
    assert start["continuation"]["authorization_id"] == GRANT
    assert start["continuation"]["expected_request_id"] == INCIDENT
    assert Decimal(start["continuation"]["held_usd"]) == HOLD
    assert start["opening_ledger"]["halted"] is True
    assert ledger.get(INCIDENT).status == "uncertain"
    assert ledger.get(INCIDENT).amount_usd == HOLD
    snapshot = ledger.snapshot()
    assert snapshot.halted
    assert snapshot.uncertain_usd == HOLD
    assert snapshot.settled_usd == OBSERVED_COST * 2
    assert snapshot.reserved_usd == Decimal("0")
    status = ledger.continuation_status(GRANT)
    assert status.active
    assert status.used_usd == OBSERVED_COST * 2
    assert status.remaining_usd == Decimal("0.10") - OBSERVED_COST * 2


def test_both_repair_attempts_are_charged_and_keep_their_original_context(halted_runner):
    ledger, config, output_dir = halted_runner
    authorize(ledger)
    transport, calls = intercepted([ask_response(content="{}"), ask_response()])
    result = run_experiment(
        probe_suite(),
        plan(),
        config=config,
        ledger=ledger,
        output_dir=output_dir,
        transport=transport,
    )
    record = observation(output_dir)
    assert result["completed_observations"] == 1
    assert result["stop_reason"] is None
    assert len(calls) == record["automatic"]["model_attempts"] == 2
    assert record["result"]["status"] == "awaiting_approval"
    assert [item["attempt_index"] for item in record["contexts"]] == [1, 2]
    assert len({item["run_id"] for item in record["contexts"]}) == 1
    assert len(record["ledger_entries"]) == 2
    for entry, context_data in zip(record["ledger_entries"], record["contexts"], strict=True):
        context = ReasoningContext.model_validate(context_data)
        assert entry["request_id"] == request_id_for(context)
        assert entry["attempt"] == context.attempt_index
        assert entry["status"] == "settled"
        assert Decimal(entry["cost_usd"]) == OBSERVED_COST
    assert ledger.continuation_status(GRANT).used_usd == OBSERVED_COST * 2
    assert ledger.snapshot().halted
    assert ledger.snapshot().uncertain_usd == HOLD


@pytest.mark.parametrize(
    ("response", "error_code"),
    [
        (ask_response(usage=False), "ProviderUsageUnknown"),
        (ask_response(model="gpt-4.1-mini"), "ProviderModelMismatch"),
        (httpx.ReadTimeout("Synthetic transport timeout"), "ProviderRequestFailed"),
    ],
)
def test_new_unknown_request_revokes_the_scope_and_stops_the_batch(
    halted_runner, response, error_code
):
    ledger, config, output_dir = halted_runner
    authorize(ledger)
    transport, calls = intercepted([response, ask_response()])
    result = run_experiment(
        probe_suite(),
        plan(policies=("baseline", "decision_rubric")),
        config=config,
        ledger=ledger,
        output_dir=output_dir,
        transport=transport,
    )
    assert len(calls) == result["completed_observations"] == 1
    assert result["planned_observations"] == 2
    assert result["stop_reason"] == "UnreconciledLedger"
    record = observation(output_dir)
    assert record["result"]["error_code"] == error_code
    assert record["automatic"]["model_attempts"] == 1
    assert len(record["ledger_entries"]) == 1
    assert record["ledger_entries"][0]["status"] == "uncertain"
    assert record["ledger_entries"][0]["error_code"] == error_code
    assert not (output_dir / "observation-01.json").exists()
    snapshot = ledger.snapshot()
    assert snapshot.halted
    assert snapshot.uncertain_usd == HOLD + REQUEST_RESERVE
    assert snapshot.settled_usd == snapshot.reserved_usd == Decimal("0")
    status = ledger.continuation_status(GRANT)
    assert not status.active
    assert status.block_reason == "NewUncertainty"
    assert status.used_usd == REQUEST_RESERVE
    assert ledger.get(INCIDENT).amount_usd == HOLD


@pytest.mark.parametrize("blocked_by", ["wrong-model", "pending-request"])
def test_scope_mismatch_or_pending_send_blocks_before_http(halted_runner, blocked_by):
    ledger, config, output_dir = halted_runner
    authorize(ledger)
    selected = plan()
    if blocked_by == "wrong-model":
        selected = plan(model="gpt-4.1-mini")
    else:
        ledger.reserve(
            request_id="request:unfinished-grant-send",
            run_id="run:unfinished-grant-send",
            case_id="case:unfinished-grant-send",
            case_revision=0,
            attempt=1,
            model="gpt-4o-mini",
            phase="development",
            amount_usd=REQUEST_RESERVE,
            continuation_id=GRANT,
        )
    transport, calls = intercepted([ask_response()])
    with pytest.raises(ReasoningStopped) as stopped:
        run_experiment(
            probe_suite(),
            selected,
            config=config,
            ledger=ledger,
            output_dir=output_dir,
            transport=transport,
        )
    assert stopped.value.code == "LedgerUnavailable"
    assert calls == []
    assert not output_dir.exists()
    assert ledger.snapshot().uncertain_usd == HOLD


def test_experiment_cap_still_stops_a_healthy_authorized_batch(halted_runner):
    ledger, config, output_dir = halted_runner
    authorize(ledger)
    transport, calls = intercepted([ask_response(), ask_response()])
    result = run_experiment(
        probe_suite(),
        plan(policies=("baseline", "decision_rubric"), cap_usd=Decimal("0.0033")),
        config=config,
        ledger=ledger,
        output_dir=output_dir,
        transport=transport,
    )
    assert len(calls) == result["completed_observations"] == 1
    assert result["planned_observations"] == 2
    assert result["stop_reason"] == "BudgetExceeded"
    assert ledger.continuation_status(GRANT).active
    assert ledger.continuation_status(GRANT).used_usd == OBSERVED_COST
    assert ledger.snapshot().halted
    assert ledger.snapshot().uncertain_usd == HOLD
    assert ledger.snapshot().reserved_usd == Decimal("0")
