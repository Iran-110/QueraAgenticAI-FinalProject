"""Optional plan messages share the intercepted, single-send accounting gateway."""

import json
import sqlite3
from decimal import Decimal

import httpx
import pytest
from pydantic import ValidationError

from agent_app.contracts import (
    CaseState,
    EvidenceBundle,
    EvidenceHit,
    GroundedGap,
    GroundedPlan,
    OutputFeedback,
    OutputIssue,
    ProposalRequirements,
    ReasoningContext,
)
from agent_app.llm.budget import BudgetLedger
from agent_app.llm.config import MetisConfig
from agent_app.llm.grounded import MetisGroundedPlanner
from agent_app.llm.metis import MetisReasoner, request_id_for
from agent_app.orchestration.ports import ReasoningStopped
from agent_app.reasoning.grounding import build_grounded_messages, make_grounded_request
from agent_app.reasoning.prompts import build_messages

SYNTHETIC_KEY = "offline-grounded-gateway-key"
CASE = CaseState(case_id="case:grounded-gateway", case_revision=2, unknowns=("streamlit_version",))
MESSAGE = "The counter resets after rerunning the app."
EVIDENCE = EvidenceBundle(
    snapshot_id="fixture:grounded-gateway",
    hits=(
        EvidenceHit(
            chunk_id="chunk:gateway",
            source_id="doc:gateway",
            excerpt="Synthetic source excerpt for inspecting the gateway payload.",
            source_url="https://example.org/grounded-gateway-fixture",
            source_type="doc",
            source_span="synthetic paragraph 1",
        ),
    ),
)
GAP = GroundedGap(
    name="streamlit_version",
    kind="user",
    description="The affected application's Streamlit version is not reported.",
    necessity="The installed version selects which documentation applies.",
    question="Which Streamlit version is running in the affected environment?",
)


def grounded_request(**changes):
    return make_grounded_request(
        **({"case": CASE, "user_message": MESSAGE, "evidence": EVIDENCE, "gaps": (GAP,)} | changes)
    )


def context(**changes):
    return ReasoningContext(
        **(
            {
                "run_id": "run:grounded-gateway",
                "case_id": CASE.case_id,
                "case_revision": CASE.case_revision,
                "attempt_index": 1,
                "remaining_model_attempts": 1,
                "remaining_retrieval_rounds": 1,
                "can_refine": True,
            }
            | changes
        )
    )


def response_body(content="raw-plan-output", *, model="gpt-4o-mini"):
    return {
        "model": model,
        "usage": {"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": 130},
        "choices": [
            {"finish_reason": "stop", "message": {"role": "assistant", "content": content}}
        ],
    }


def reservations(path):
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        return connection.execute("SELECT * FROM reservations ORDER BY rowid").fetchall()


def observed_cost():
    return 100 * Decimal("0.000000165") + 30 * Decimal("0.000000660")


@pytest.fixture
def gateway_factory(tmp_path):
    ports = []

    def create(*, planner=True, config_changes=None, responses=None):
        path = tmp_path / f"grounded-gateway-{len(ports)}.sqlite3"
        ledger = BudgetLedger.create(path, limit_usd=Decimal("1"), opening_spend_usd=Decimal("0"))
        config = MetisConfig(
            **(
                {
                    "api_key": SYNTHETIC_KEY,
                    "live_enabled": True,
                    "response_mode": "grounded_plan" if planner else "analysis",
                }
                | (config_changes or {})
            )
        )
        calls = []
        scripted = list(responses or [response_body()])

        def intercepted(request):
            calls.append(request)
            return httpx.Response(200, json=scripted.pop(0))

        port = (MetisGroundedPlanner if planner else MetisReasoner)(
            config, ledger, transport=httpx.MockTransport(intercepted)
        )
        ports.append(port)
        return port, ledger, calls, path

    yield create
    for port in ports:
        port.close()


@pytest.mark.parametrize(
    "policy",
    [
        "baseline",
        "decision_rubric",
        "bounded_rubric",
        "structured_rules",
        "diagnostic_rules",
        "grounded_rules",
        "compiled_rules",
        "fidelity_rules",
    ],
)
def test_default_analysis_mode_keeps_each_existing_policy_payload(gateway_factory, policy):
    port, ledger, calls, _ = gateway_factory(
        planner=False, config_changes={"prompt_policy": policy}
    )
    attribution = context(
        proposal_requirements=ProposalRequirements(
            case_id=CASE.case_id, case_revision=CASE.case_revision
        )
    )
    assert port.config.response_mode == "analysis"
    assert port.analyze(CASE, MESSAGE, EVIDENCE, context=attribution) == "raw-plan-output"
    payload = json.loads(calls[0].content)
    assert payload["messages"] == list(
        build_messages(
            CASE,
            MESSAGE,
            EVIDENCE,
            feedback=attribution.output_feedback,
            policy=policy,
            context=attribution,
        )
    )
    assert (
        json.loads(payload["messages"][1]["content"])["response_schema"]["title"]
        == "AnalysisResult"
    )
    assert ledger.snapshot().settled_usd == observed_cost()


def test_grounded_plan_uses_same_context_ledger_and_single_send_with_raw_output(gateway_factory):
    request = grounded_request()
    raw = GroundedPlan(
        context_sha256=request.context_sha256, decision="ask", question_name=GAP.name
    ).model_dump_json()
    planner, ledger, calls, path = gateway_factory(
        config_changes={"prompt_policy": "compiled_rules"}, responses=[response_body(raw)]
    )
    attribution = context()
    assert planner.plan(request, context=attribution) == raw
    assert len(calls) == len(reservations(path)) == 1
    payload = json.loads(calls[0].content)
    assert payload["messages"] == list(build_grounded_messages(request, attribution))
    schema = json.loads(payload["messages"][1]["content"])["response_schema"]
    assert schema["title"] == "GroundedPlan"
    assert "user_draft" not in schema["properties"]
    assert schema["additionalProperties"] is False
    row = reservations(path)[0]
    assert row["request_id"] == request_id_for(attribution)
    assert (row["run_id"], row["case_id"], row["case_revision"], row["attempt"]) == (
        attribution.run_id,
        CASE.case_id,
        CASE.case_revision,
        1,
    )
    assert row["status"] == "settled"
    assert (row["input_tokens"], row["output_tokens"]) == (100, 30)
    assert ledger.snapshot().settled_usd == observed_cost()
    assert ledger.snapshot().reserved_usd == ledger.snapshot().uncertain_usd == 0


def test_grounded_output_is_charged_and_returned_without_parsing_rendering_or_repair(
    gateway_factory,
):
    planner, ledger, calls, path = gateway_factory(responses=[response_body("not plan JSON")])
    assert planner.plan(grounded_request(), context=context()) == "not plan JSON"
    assert len(calls) == len(reservations(path)) == 1
    assert ledger.snapshot().settled_usd == observed_cost()
    assert not ledger.snapshot().halted


def test_grounded_feedback_changes_do_not_create_another_billable_identity(gateway_factory):
    planner, ledger, calls, path = gateway_factory()
    attribution = context(
        attempt_index=2,
        remaining_model_attempts=0,
        can_refine=False,
        output_feedback=OutputFeedback(issues=(OutputIssue(code="invalid_grounded_plan"),)),
    )
    planner.plan(grounded_request(), context=attribution)
    changed_feedback = attribution.model_copy(
        update={
            "output_feedback": OutputFeedback(
                issues=(OutputIssue(code="grounded_context_mismatch"),)
            )
        }
    )
    with pytest.raises(ReasoningStopped) as caught:
        planner.plan(grounded_request(), context=changed_feedback)
    assert caught.value.code == "DuplicateModelRequest"
    assert len(calls) == len(reservations(path)) == 1
    assert ledger.snapshot().settled_usd == observed_cost()


def test_terminal_model_mismatch_preserves_uncertainty_and_halts_without_retry(gateway_factory):
    planner, ledger, calls, path = gateway_factory(
        responses=[response_body(model="gpt-4.1-mini"), response_body()]
    )
    with pytest.raises(ReasoningStopped) as caught:
        planner.plan(grounded_request(), context=context())
    assert caught.value.code == "ProviderModelMismatch"
    assert len(calls) == len(reservations(path)) == 1
    snapshot = ledger.snapshot()
    assert snapshot.halted
    assert snapshot.uncertain_usd > 0
    assert snapshot.settled_usd == snapshot.reserved_usd == 0
    assert reservations(path)[0]["status"] == "uncertain"
    with pytest.raises(ReasoningStopped) as caught:
        planner.plan(
            grounded_request(),
            context=context(attempt_index=2, remaining_model_attempts=0, can_refine=False),
        )
    assert caught.value.code == "BudgetExceeded"
    assert len(calls) == 1
    assert ledger.snapshot().uncertain_usd == snapshot.uncertain_usd


@pytest.mark.parametrize("field", ["case", "user_message", "evidence"])
def test_plan_request_cannot_replace_the_explicit_gateway_inputs(gateway_factory, field):
    port, ledger, calls, path = gateway_factory(
        planner=False, config_changes={"response_mode": "grounded_plan"}
    )
    if field == "case":
        request = grounded_request(
            case=CASE.model_copy(update={"unknowns": ("python_version",)}), gaps=()
        )
    elif field == "user_message":
        request = grounded_request(user_message="private-other-user-message")
    else:
        hit = EVIDENCE.hits[0].model_copy(update={"excerpt": "private-other-source-excerpt"})
        request = grounded_request(evidence=EVIDENCE.model_copy(update={"hits": (hit,)}))
    with pytest.raises(ValueError, match="Invalid grounded request or context") as caught:
        port.analyze(CASE, MESSAGE, EVIDENCE, context=context(), grounded_request=request)
    assert "private-other" not in str(caught.value)
    assert calls == reservations(path) == []
    assert ledger.snapshot().available_usd == Decimal("1")


@pytest.mark.parametrize("malformation", ["digest", "nested_input", "not_request"])
def test_forged_or_mutated_plan_requests_fail_before_reservation_with_safe_errors(
    gateway_factory, malformation
):
    planner, ledger, calls, path = gateway_factory()
    request = grounded_request()
    if malformation == "digest":
        request = request.model_copy(update={"user_message": "private-grounded-message-marker"})
    elif malformation == "nested_input":
        hit = EVIDENCE.hits[0].model_copy(update={"excerpt": {"private-marker": "invalid"}})
        request = request.model_copy(
            update={"evidence": EVIDENCE.model_copy(update={"hits": (hit,)})}
        )
    else:
        request = {"private-marker": "invalid"}
    with pytest.raises(ValueError, match="Invalid grounded request") as caught:
        planner.plan(request, context=context())
    assert not isinstance(caught.value, ValidationError)
    assert "private-" not in str(caught.value)
    assert calls == reservations(path) == []
    assert ledger.snapshot().available_usd == Decimal("1")


@pytest.mark.parametrize(
    "changes",
    [
        {"case_id": "case:other"},
        {"case_revision": 3},
        {"attempt_index": 3},
    ],
)
def test_plan_context_mismatch_or_invalid_attempt_cannot_reserve_or_send(gateway_factory, changes):
    planner, ledger, calls, path = gateway_factory()
    attribution = context().model_copy(update=changes)
    with pytest.raises(ValueError) as caught:
        planner.plan(grounded_request(), context=attribution)
    assert not isinstance(caught.value, ValidationError)
    assert calls == reservations(path) == []
    assert ledger.snapshot().available_usd == Decimal("1")


@pytest.mark.parametrize("mode", ["analysis", "grounded_plan"])
def test_cross_mode_requests_are_denied_before_the_gateway_can_spend(gateway_factory, mode):
    port, ledger, calls, path = gateway_factory(
        planner=False, config_changes={"response_mode": mode}
    )
    extra = {"grounded_request": grounded_request()} if mode == "analysis" else {}
    with pytest.raises(ValueError):
        port.analyze(CASE, MESSAGE, EVIDENCE, context=context(), **extra)
    assert calls == reservations(path) == []
    assert ledger.snapshot().available_usd == Decimal("1")


def test_planner_requires_explicit_mode_and_environment_defaults_remain_analysis(
    tmp_path, monkeypatch
):
    ledger = BudgetLedger.create(
        tmp_path / "not-opted-in.sqlite3", limit_usd=Decimal("1"), opening_spend_usd=Decimal("0")
    )
    calls = []
    with pytest.raises(ValueError, match="requires grounded plan mode"):
        MetisGroundedPlanner(
            MetisConfig(api_key=SYNTHETIC_KEY, live_enabled=True),
            ledger,
            transport=httpx.MockTransport(lambda request: calls.append(request)),
        )
    assert calls == []
    assert ledger.snapshot().available_usd == Decimal("1")
    monkeypatch.setenv("METIS_API_KEY", SYNTHETIC_KEY)
    monkeypatch.delenv("METIS_RESPONSE_MODE", raising=False)
    assert MetisConfig.from_env().response_mode == "analysis"
    monkeypatch.setenv("METIS_RESPONSE_MODE", "grounded_plan")
    assert MetisConfig.from_env().response_mode == "grounded_plan"
    monkeypatch.setenv("METIS_RESPONSE_MODE", "other")
    with pytest.raises(ValidationError):
        MetisConfig.from_env()


def test_grounded_mode_does_not_enable_live_calls_by_itself(gateway_factory):
    planner, ledger, calls, path = gateway_factory(config_changes={"live_enabled": False})
    with pytest.raises(ReasoningStopped) as caught:
        planner.plan(grounded_request(), context=context())
    assert caught.value.code == "LiveCallsDisabled"
    assert calls == reservations(path) == []
    assert ledger.snapshot().available_usd == Decimal("1")


def test_plan_and_analysis_share_duplicate_protection_in_the_same_ledger(gateway_factory):
    analysis, ledger, calls, path = gateway_factory(planner=False)
    analysis.analyze(CASE, MESSAGE, EVIDENCE, context=context())
    grounded_calls = []
    with MetisGroundedPlanner(
        MetisConfig(api_key=SYNTHETIC_KEY, live_enabled=True, response_mode="grounded_plan"),
        ledger,
        transport=httpx.MockTransport(lambda request: grounded_calls.append(request)),
    ) as planner:
        with pytest.raises(ReasoningStopped) as caught:
            planner.plan(grounded_request(), context=context())
    assert caught.value.code == "DuplicateModelRequest"
    assert len(calls) == len(reservations(path)) == 1
    assert grounded_calls == []
    assert ledger.snapshot().settled_usd == observed_cost()
