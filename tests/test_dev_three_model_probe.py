"""Registered model trial wiring with fake provider and disposable accounting."""

import json
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from agent_app.contracts import ReasoningContext
from agent_app.evaluation.runner import collect
from agent_app.llm.budget import BudgetLedger
from agent_app.llm.config import MetisConfig
from agent_app.llm.pricing import get_price
from agent_app.reasoning.catalog import load_user_gap_vocabulary
from agent_app.testing.dev_three_model_probe import (
    CAP,
    INPUT_RESERVE,
    MODEL,
    OUTPUT_LIMIT,
    ScopedPlanner,
    ledger_observation,
    request_slots,
    run_trial,
)
from agent_app.testing.http_pilot_runtime import offline_network

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / "data/evaluation/dev-three-v1"


def preparation(tmp_path):
    ledger = BudgetLedger.create(
        tmp_path / "budget.sqlite3", limit_usd=Decimal("4.5"), opening_spend_usd=Decimal("0")
    )
    ledger.reserve(
        request_id="quarantined",
        run_id="old-run",
        case_id="old-case",
        case_revision=0,
        attempt=1,
        model="gpt-4.1-mini",
        phase="development",
        amount_usd=Decimal("0.02"),
    )
    ledger.mark_uncertain("quarantined", error_code="ProviderModelMismatch")
    ledger.halt()
    ledger.authorize_continuation(
        authorization_id="old-grant",
        authorization_ref="old-user-authorization",
        expected_request_id="quarantined",
        held_usd=Decimal("0.02"),
        additional_cap_usd=Decimal("0.01"),
    )
    protocol = {
        "experiment_id": "synthetic-dev-three-v1",
        "scope_id": "synthetic-scope",
        "protocol_id": "dev-three-controlled-model-v1",
    }
    paths = [
        PACKET / "cases" / name
        for name in ("pilot-12782-v1.json", "icon-9770-v1.json", "enum-8129-v1.json")
    ]
    fixtures = collect(paths, mode="live")
    definitions = load_user_gap_vocabulary(str(PACKET / "user-gap-vocabulary-v1.json"))
    before = ledger_observation(ledger._path)
    slots = request_slots(protocol, fixtures)
    ledger.authorize_experiment_scope(
        authorization_id=protocol["scope_id"],
        authorization_ref="synthetic-user-authorization",
        parent_authorization_id="old-grant",
        protocol_sha256="a" * 64,
        request_slots=slots,
        additional_cap_usd=CAP,
    )
    config = MetisConfig(
        api_key="synthetic-noncredential",
        live_enabled=True,
        model=MODEL,
        phase="development",
        response_mode="grounded_plan",
        continuation_id=protocol["scope_id"],
        input_token_reserve=INPUT_RESERVE,
        max_output_tokens=OUTPUT_LIMIT,
        max_request_usd=get_price(MODEL).cost(INPUT_RESERVE, OUTPUT_LIMIT),
    )
    return protocol, fixtures, definitions, ledger, config, before


def response(request, payloads):
    wire = json.loads(request.content)
    payload = json.loads(wire["messages"][1]["content"])
    payloads.append(payload)
    actual = payload["request"]
    user_gaps = [gap for gap in actual["gaps"] if gap["kind"] == "user"]
    refs = payload["source_references"]
    if user_gaps:
        question = next(
            (gap for gap in user_gaps if gap["name"] == "streamlit_version"), user_gaps[0]
        )
        plan = {
            "context_sha256": actual["context_sha256"],
            "decision": "ask",
            "question_name": question["name"],
        }
    elif actual["case"]["case_id"] == "dev-case-b":
        plan = {"context_sha256": actual["context_sha256"], "decision": "answer", "sources": refs}
    else:
        plan = {"context_sha256": actual["context_sha256"], "decision": "escalate", "sources": refs}
    return httpx.Response(
        200,
        json={
            "model": "gpt-4o-mini-2024-07-18",
            "choices": [
                {
                    "message": {"role": "assistant", "content": json.dumps(plan)},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 1000, "completion_tokens": 180, "total_tokens": 1180},
        },
    )


def test_registered_trial_consumes_exact_slots_and_keeps_real_cost_and_old_halt(tmp_path):
    protocol, fixtures, definitions, ledger, config, before = preparation(tmp_path)
    payloads = []
    with offline_network():
        receipt = run_trial(
            protocol,
            fixtures,
            definitions,
            ledger,
            config,
            before,
            underlying=httpx.MockTransport(lambda request: response(request, payloads)),
        )
    assert receipt["actual_sends"] == 12
    assert receipt["completed_case_arm_runs"] == 6 and not receipt["stopped_early"]
    assert all(check["passed"] for case in receipt["cases"] for check in case["checks"])
    assert receipt["accounting"]["accounting_complete"] is True
    assert Decimal(receipt["accounting"]["cost_usd"]) > 0
    assert len(receipt["accounting"]["requests"]) == 12
    assert receipt["original_accounting_preserved"] is True
    assert ledger.snapshot().halted and ledger.snapshot().uncertain_usd == Decimal("0.02")
    assert ledger.continuation_status("old-grant").used_usd == 0
    assert ledger.experiment_scope_status(protocol["scope_id"]).consumed_requests == 12
    assert receipt["quality_claim"] is False and receipt["actual_rag_quality"] is False
    assert receipt["human_usefulness"] is None
    enum = [case for case in receipt["cases"] if case["case_id"] == "dev-case-c"]
    assert all(
        any(
            check["check"] == "live stale unexecuted approval rejected" and check["passed"]
            for check in case["checks"]
        )
        for case in enum
    )
    assert all(
        record["verified_returned_model"] == "gpt-4o-mini-2024-07-18"
        for record in receipt["provider_sends"]
    )
    # Evidence and exposed current facts are equal; only the registered vocabulary differs.
    a, b = payloads[1]["request"], payloads[7]["request"]
    assert a["case"] == b["case"] and a["evidence"] == b["evidence"]
    assert not any(gap["kind"] == "user" for gap in a["gaps"])
    assert any(gap["name"] == "parent_callback_code" for gap in b["gaps"])
    assert "1.31.1" not in json.dumps(payloads[4]["request"]["case"]["facts"])
    for payload in payloads:
        assert set(payload["request"]) == {
            "case",
            "user_message",
            "evidence",
            "gaps",
            "conflict_groups",
            "context_sha256",
        }
        assert "gold" not in payload and "agent_script" not in payload
    ledger.close_experiment_scope(protocol["scope_id"])
    assert ledger.experiment_scope_status(protocol["scope_id"]).block_reason == "ExperimentClosed"


def test_oversized_context_is_recorded_as_zero_wire_unfunded_attempt(tmp_path):
    protocol, fixtures, definitions, ledger, config, before = preparation(tmp_path)
    from agent_app.contracts import CaseState, EvidenceBundle
    from agent_app.llm.grounded import MetisGroundedPlanner
    from agent_app.orchestration.ports import ReasoningStopped
    from agent_app.reasoning.grounding import make_grounded_request
    from agent_app.testing.dev_three_model_probe import ScopeTransport, SharedTransport

    counted = ScopeTransport(
        httpx.MockTransport(lambda request: pytest.fail("No send permitted")),
        ledger,
        protocol["scope_id"],
        before,
    )
    gateway = MetisGroundedPlanner(config, ledger, transport=SharedTransport(counted))
    records = []
    planner = ScopedPlanner(gateway, counted, records)
    request = make_grounded_request(
        CaseState(case_id="dev-case-a"), "x" * 18000, EvidenceBundle(snapshot_id="synthetic")
    )
    context = ReasoningContext(
        run_id="unlisted-run", case_id="dev-case-a", case_revision=0, attempt_index=1
    )
    with pytest.raises(ReasoningStopped) as failed:
        planner.plan(request, context=context)
    assert failed.value.code == "ContextLimitExceeded"
    assert len(records) == 1 and records[0]["error_code"] == "ContextLimitExceeded"
    assert records[0]["context"] == context.model_dump(mode="json")
    assert (
        counted.records == []
        and ledger.experiment_scope_status(protocol["scope_id"]).consumed_requests == 0
    )
    gateway.close()
    counted.close()
