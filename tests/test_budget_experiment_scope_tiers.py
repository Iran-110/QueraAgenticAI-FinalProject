"""Two frozen input tiers preserve complete evidence under the same scope cap.

These synthetic controls are additive to the unchanged 69 V2 accounting tests.
They do not justify shortening facts, excerpts or repair context to fit a grant.
"""

import json
from decimal import Decimal

import httpx
import pytest
from pydantic import SecretStr
from test_budget_experiment_scope import BOUND, SCOPE, authorize, historical_rows, reserve, slot
from test_budget_experiment_scope import quarantined as quarantined

from agent_app.contracts import CaseState, EvidenceBundle, ReasoningContext
from agent_app.llm.budget import BudgetDenied
from agent_app.llm.config import MetisConfig
from agent_app.llm.metis import MetisReasoner, request_id_for
from agent_app.llm.pricing import get_price

HIGH_BOUND = Decimal("0.004730880")


def high_slot(index=0, **changes):
    return slot(index, **({"input_token_reserve": 24576, "amount_usd": HIGH_BOUND} | changes))


def test_registered_mixed_tiers_fit_original_cap_and_preserve_historical_rows(quarantined):
    ledger, path = quarantined
    assert get_price("gpt-4o-mini").cost(24576, 1024) == HIGH_BOUND
    slots = tuple(slot(i) for i in range(16)) + tuple(high_slot(i) for i in range(16, 24))
    assert sum(item.amount_usd for item in slots) == Decimal("0.091914240")
    before = historical_rows(path)
    scope = authorize(ledger, request_slots=slots)
    assert scope.active and scope.max_requests == 24
    assert scope.additional_cap_usd == Decimal("0.10")
    assert historical_rows(path) == before
    reserve(ledger, slots[-1])
    assert ledger.get(slots[-1].request_id).amount_usd == HIGH_BOUND
    assert ledger.snapshot().reserved_usd == HIGH_BOUND
    assert ledger.snapshot().halted


@pytest.mark.parametrize(
    "changes",
    [
        {"input_token_reserve": 16384},
        {"amount_usd": BOUND},
        {"input_token_reserve": 24576.0},
    ],
)
def test_high_tier_slot_rejects_a_different_tier_amount_or_type_before_reserving(
    quarantined, changes
):
    ledger, _ = quarantined
    registered = high_slot()
    authorize(ledger, request_slots=(registered,))
    with pytest.raises(BudgetDenied):
        reserve(ledger, registered, **changes)
    assert ledger.experiment_scope_status(SCOPE).consumed_requests == 0
    assert ledger.get(registered.request_id) is None


def test_higher_tier_slots_cannot_expand_the_immutable_scope_money_cap(quarantined):
    ledger, path = quarantined
    before = historical_rows(path)
    with pytest.raises(ValueError):
        authorize(ledger, request_slots=tuple(high_slot(i) for i in range(24)))
    assert historical_rows(path) == before


@pytest.mark.parametrize("tier", [24575, 32768])
def test_unregistered_input_tiers_remain_invalid(quarantined, tier):
    ledger, _ = quarantined
    with pytest.raises(ValueError):
        authorize(ledger, request_slots=(high_slot(input_token_reserve=tier),))


def test_gateway_passes_exact_registered_higher_input_tier_and_preserves_output_cap(quarantined):
    ledger, _ = quarantined
    case = CaseState(case_id="case:higher-tier")
    context = ReasoningContext(
        run_id="run:higher-tier", case_id=case.case_id, case_revision=0, attempt_index=1
    )
    registered = high_slot(
        request_id=request_id_for(context), run_id=context.run_id, case_id=case.case_id
    )
    authorize(ledger, request_slots=(registered,))
    wires = []

    def handler(request):
        wires.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "model": "gpt-4o-mini",
                "usage": {"prompt_tokens": 17000, "completion_tokens": 20, "total_tokens": 17020},
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "synthetic higher-tier reply"},
                    }
                ],
            },
        )

    config = MetisConfig(
        api_key=SecretStr("synthetic-not-a-provider-key"),
        live_enabled=True,
        continuation_id=SCOPE,
        input_token_reserve=24576,
        max_output_tokens=1024,
    )
    with MetisReasoner(config, ledger, transport=httpx.MockTransport(handler)) as reasoner:
        assert (
            reasoner.analyze(
                case,
                "Synthetic full-context tier control",
                EvidenceBundle(snapshot_id="synthetic"),
                context=context,
            )
            == "synthetic higher-tier reply"
        )
    assert len(wires) == 1 and wires[0]["max_tokens"] == 1024
    row = ledger.get(registered.request_id)
    assert row.status == "settled" and row.input_tokens == 17000
    assert ledger.snapshot().halted
