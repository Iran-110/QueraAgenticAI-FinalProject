"""The private claim projection uses the real gateway and disposable accounting."""

import json
import sqlite3
from decimal import Decimal

import httpx
import pytest

from agent_app.contracts import (
    CaseState,
    EvidenceBundle,
    EvidenceHit,
    ProposalRequirements,
    ReasoningContext,
)
from agent_app.llm.budget import BudgetLedger
from agent_app.llm.claims import MetisClaimPlanner
from agent_app.llm.config import MetisConfig
from agent_app.llm.metis import MetisReasoner, request_id_for
from agent_app.orchestration.ports import ReasoningStopped
from agent_app.reasoning.claim_plan import build_claim_messages, build_claim_request
from agent_app.reasoning.grounding import make_grounded_request
from agent_app.reasoning.prompts import build_messages

KEY = "synthetic-claim-gateway-key"


def inputs(*, excerpt="A synthetic documented pattern.\n\nOnly when its conditions hold."):
    case = CaseState(case_id="neutral-claim-case", case_revision=4)
    evidence = EvidenceBundle(
        snapshot_id="neutral-claim-snapshot",
        hits=(
            EvidenceHit(
                chunk_id="neutral-claim-chunk",
                source_id="neutral-claim-source",
                source_type="doc",
                source_url="https://example.org/neutral-claim-document",
                source_span="synthetic paragraphs",
                excerpt=excerpt,
            ),
        ),
    )
    request = build_claim_request(make_grounded_request(case, "A reported symptom.", evidence))
    context = ReasoningContext(
        run_id="neutral-claim-run",
        case_id=case.case_id,
        case_revision=case.case_revision,
        attempt_index=1,
        remaining_model_attempts=1,
    )
    return request, context


@pytest.fixture
def gateway(tmp_path):
    instances = []

    def create(**changes):
        path = tmp_path / f"claims-{len(instances)}.sqlite3"
        ledger = BudgetLedger.create(path, limit_usd=Decimal("1"), opening_spend_usd=Decimal("0"))
        config = MetisConfig(**({"api_key": KEY, "live_enabled": True} | changes))
        calls = []
        response = {"content": "untrusted-claim-plan"}

        def intercepted(request):
            calls.append(request)
            return httpx.Response(
                200,
                json={
                    "model": config.model,
                    "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110},
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"role": "assistant", "content": response["content"]},
                        }
                    ],
                },
            )

        planner = MetisClaimPlanner(config, ledger, transport=httpx.MockTransport(intercepted))
        instances.append(planner)
        return planner, ledger, calls, response, path

    yield create
    for planner in instances:
        planner.close()


def rows(path):
    with sqlite3.connect(path) as db:
        return list(db.execute("select request_id,status,cost_decimal from reservations"))


def test_claim_projection_uses_actual_gateway_payload_identity_and_settlement(gateway):
    planner, _ledger, calls, _response, path = gateway()
    request, context = inputs()
    assert planner.plan(request, context=context) == "untrusted-claim-plan"
    assert len(calls) == 1
    payload = json.loads(calls[0].content)
    assert payload["messages"] == build_claim_messages(request, context)
    assert "response_format" not in payload
    assert KEY not in json.dumps(payload)
    assert rows(path) == [(request_id_for(context), "settled", "0.000023100")]
    assert planner.reasoner._claim_binding is None


def test_context_mismatch_never_reserves_or_sends(gateway):
    planner, _ledger, calls, _response, path = gateway()
    request, context = inputs()
    context = context.model_copy(update={"case_revision": 5})
    with pytest.raises(ValueError):
        planner.plan(request, context=context)
    assert not calls and not rows(path)
    assert planner.reasoner._claim_binding is None


def test_unbound_private_projection_cannot_send(gateway):
    planner, _ledger, calls, _response, path = gateway()
    request, context = inputs()
    with pytest.raises(ValueError, match="ClaimGatewayBindingRequired"):
        planner.reasoner.analyze(
            request.grounded.case,
            request.grounded.user_message,
            request.grounded.evidence,
            context=context,
        )
    assert not calls and not rows(path)


def test_existing_guard_rejects_full_oversize_before_reservation(gateway):
    planner, _ledger, calls, _response, path = gateway(input_token_reserve=4096)
    request, context = inputs(excerpt="Whole synthetic source record. " * 200)
    with pytest.raises(ReasoningStopped) as exc:
        planner.plan(request, context=context)
    assert exc.value.code == "ContextLimitExceeded"
    assert not calls and not rows(path)
    assert planner.reasoner._claim_binding is None


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"live_enabled": False}, "LiveCallsDisabled"),
        ({"model": "unverified-model"}, "UnknownPricing"),
    ],
)
def test_claim_projection_cannot_bypass_normal_live_or_price_gates(gateway, changes, code):
    planner, _ledger, calls, _response, path = gateway(**changes)
    request, context = inputs()
    with pytest.raises(ReasoningStopped) as exc:
        planner.plan(request, context=context)
    assert exc.value.code == code
    assert not calls and not rows(path)
    assert planner.reasoner._claim_binding is None


@pytest.mark.parametrize("escaped", [False, True])
def test_credential_echo_stops_after_settlement_without_exporting_text(gateway, escaped):
    planner, _ledger, calls, response, path = gateway()
    request, context = inputs()
    response["content"] = (
        '{"untrusted":"' + "".join(f"\\u{ord(c):04x}" for c in KEY) + '"}'
        if escaped
        else json.dumps({"untrusted": KEY})
    )
    with pytest.raises(ReasoningStopped) as exc:
        planner.plan(request, context=context)
    assert exc.value.code == "ProviderResponseInvalid"
    assert KEY not in str(exc.value)
    assert len(calls) == 1 and rows(path)[0][1] == "settled"
    assert planner.reasoner._claim_binding is None


@pytest.mark.parametrize(
    "changes",
    [
        {"response_mode": "grounded_plan"},
        {"grounded_json_object": True, "response_mode": "grounded_plan"},
    ],
)
def test_claim_planner_is_explicit_and_rejects_grounded_configuration(gateway, changes):
    with pytest.raises(ValueError):
        gateway(**changes)


def test_legacy_message_projection_remains_exact(tmp_path):
    request, context = inputs()
    context = context.model_copy(
        update={
            "proposal_requirements": ProposalRequirements(
                case_id=request.grounded.case.case_id,
                case_revision=request.grounded.case.case_revision,
            )
        }
    )
    ledger = BudgetLedger.create(
        tmp_path / "legacy.sqlite3", limit_usd=Decimal("1"), opening_spend_usd=Decimal("0")
    )
    config = MetisConfig(api_key=KEY, prompt_policy="compiled_rules")
    with MetisReasoner(config, ledger) as port:
        assert port._analysis_messages(
            request.grounded.case, request.grounded.user_message, request.grounded.evidence, context
        ) == build_messages(
            request.grounded.case,
            request.grounded.user_message,
            request.grounded.evidence,
            context=context,
            feedback=context.output_feedback,
            policy="compiled_rules",
        )
