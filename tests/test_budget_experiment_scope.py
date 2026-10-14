"""New user authorization funds one frozen experiment without replenishing history.

All ledgers, credentials, transports and provider observations here are synthetic.
The designated team ledger is never opened by these controls.
"""

import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from decimal import Decimal
from threading import Barrier

import httpx
import pytest
from pydantic import SecretStr

from agent_app.contracts import CaseState, EvidenceBundle, ReasoningContext
from agent_app.llm import budget
from agent_app.llm.budget import BudgetDenied, BudgetLedger, LedgerConflict, LedgerUnavailable
from agent_app.llm.config import MetisConfig
from agent_app.llm.metis import MetisReasoner, request_id_for
from agent_app.llm.pricing import get_price
from agent_app.orchestration.ports import ReasoningStopped

D = Decimal
OLD = "call:original-mismatch"
PARENT = "original-immutable-grant"
SCOPE = "new-user-experiment-2026-10-14"
PROTOCOL = "d" * 64
BOUND = D("0.003379200")


def slot(index=0, **changes):
    slot_type = getattr(budget, "ExperimentRequestSlot", None)
    assert callable(slot_type), "Frozen experiment request slots are required."
    values = {
        "request_id": f"call:registered-{index}",
        "run_id": f"run:registered-{index}",
        "case_id": f"case:registered-{index}",
        "case_revision": 0,
        "attempt": 1,
        "model": "gpt-4o-mini",
        "phase": "development",
        "input_token_reserve": 16384,
        "max_output_tokens": 1024,
        "amount_usd": BOUND,
    }
    return slot_type(**(values | changes))


def authorize(ledger, **changes):
    method = getattr(ledger, "authorize_experiment_scope", None)
    assert callable(method), "Explicit additive experiment authorization is required."
    values = {
        "authorization_id": SCOPE,
        "authorization_ref": "user:2026-10-14:explicit-quality-experiment",
        "parent_authorization_id": PARENT,
        "protocol_sha256": PROTOCOL,
        "request_slots": (slot(0), slot(1)),
        "additional_cap_usd": D("0.10"),
    }
    return method(**(values | changes))


def reserve(ledger, registered=None, **changes):
    registered = slot() if registered is None else registered
    return ledger.reserve(**(asdict(registered) | {"continuation_id": SCOPE} | changes))


def historical_rows(path):
    with sqlite3.connect(path) as connection:
        tables = (
            "ledger_meta",
            "reservations",
            "ledger_events",
            "ledger_continuations",
            "continuation_requests",
            "continuation_events",
        )
        return {
            name: connection.execute(f"SELECT * FROM {name} ORDER BY rowid").fetchall()
            for name in tables
        }


@pytest.fixture
def quarantined(tmp_path):
    path = tmp_path / "synthetic-existing.sqlite3"
    ledger = BudgetLedger.create(path, limit_usd=D("4.50"), opening_spend_usd=D("0"))
    ledger.reserve(
        request_id=OLD,
        run_id="run:old",
        case_id="case:old",
        case_revision=0,
        attempt=1,
        model="gpt-4.1-mini",
        phase="development",
        amount_usd=D("0.008560640"),
    )
    ledger.mark_uncertain(OLD, error_code="ProviderModelMismatch")
    ledger.halt()
    ledger.authorize_continuation(
        authorization_id=PARENT,
        authorization_ref="user:historical",
        expected_request_id=OLD,
        held_usd=D("0.02"),
        additional_cap_usd=D("0.10"),
    )
    # The historical cap is nearly exhausted. New authorization must not refill it.
    for index, amount in enumerate((D("0.02"),) * 4 + (D("0.018"),)):
        rid = f"call:historical-{index}"
        ledger.reserve(
            request_id=rid,
            run_id=f"run:historical-{index}",
            case_id="case:history",
            case_revision=0,
            attempt=1,
            model="gpt-4o-mini",
            phase="development",
            amount_usd=amount,
            continuation_id=PARENT,
        )
        ledger.settle(rid, cost_usd=amount, input_tokens=10, output_tokens=10)
    return ledger, path


def test_new_scope_preserves_every_historical_row_and_halt(quarantined):
    ledger, path = quarantined
    before = historical_rows(path)
    prior = ledger.continuation_status(PARENT)
    scope = authorize(ledger)
    assert historical_rows(path) == before
    assert scope.active and scope.block_reason is None
    assert scope.parent_authorization_id == PARENT and scope.protocol_sha256 == PROTOCOL
    assert scope.additional_cap_usd == scope.remaining_usd == D("0.10")
    assert scope.max_requests == 2 and scope.consumed_requests == 0
    assert ledger.continuation_status(PARENT) == prior
    assert ledger.snapshot().halted and ledger.snapshot().limit_usd == D("4.50")
    assert ledger.snapshot().uncertain_usd == D("0.02")
    assert ledger.continuation_status(SCOPE) == scope
    with pytest.raises(BudgetDenied):
        reserve(ledger, continuation_id=None)


def test_exact_authorization_replay_does_not_refill_usage_or_consumed_slots(quarantined):
    ledger, path = quarantined
    first = authorize(ledger)
    assert authorize(ledger) == first
    reserve(ledger)
    ledger.settle("call:registered-0", cost_usd=D("0.001"), input_tokens=100, output_tokens=30)
    status = authorize(BudgetLedger(path))
    assert status.used_usd == D("0.001") and status.remaining_usd == D("0.099")
    assert status.consumed_requests == 1
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM experiment_scopes").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM experiment_scope_events").fetchone()[0] == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"authorization_ref": "user:different"},
        {"protocol_sha256": "a" * 64},
        {"additional_cap_usd": D("0.09")},
        {"parent_authorization_id": "different-parent"},
        {"request_slots": "changed"},
    ],
)
def test_changed_replay_is_conflict_and_never_alters_original_scope(quarantined, changes):
    ledger, path = quarantined
    original = authorize(ledger)
    if changes.get("request_slots") == "changed":
        changes = {"request_slots": (slot(0), slot(2))}
    with pytest.raises((LedgerConflict, ValueError)):
        authorize(ledger, **changes)
    assert BudgetLedger(path).experiment_scope_status(SCOPE) == original


@pytest.mark.parametrize(
    "changes",
    [
        {"request_id": "call:unregistered"},
        {"run_id": "run:changed"},
        {"case_id": "case:changed"},
        {"case_revision": 1},
        {"attempt": 2},
        {"model": "gpt-4.1-mini"},
        {"model": "gpt-4o-mini-2024-07-18"},
        {"phase": "evaluation"},
        {"input_token_reserve": 8192},
        {"max_output_tokens": 512},
        {"input_token_reserve": None},
        {"max_output_tokens": None},
        {"amount_usd": D("0.001")},
        {"amount_usd": BOUND + D("0.000000001")},
    ],
)
def test_request_must_match_exact_frozen_slot_before_any_reservation(quarantined, changes):
    ledger, _ = quarantined
    authorize(ledger)
    before = ledger.snapshot()
    with pytest.raises((BudgetDenied, ValueError)):
        reserve(ledger, **changes)
    assert ledger.snapshot() == before
    assert ledger.experiment_scope_status(SCOPE).consumed_requests == 0


def test_slot_count_caps_paid_attempts_even_when_the_monetary_cap_has_credit(quarantined):
    ledger, _ = quarantined
    authorize(ledger, request_slots=(slot(),))
    reserve(ledger)
    ledger.settle("call:registered-0", cost_usd=D("0.00001"), input_tokens=1, output_tokens=1)
    status = ledger.experiment_scope_status(SCOPE)
    assert status.remaining_usd == D("0.09999")
    assert not status.active and status.block_reason == "ExperimentRequestsExhausted"
    with pytest.raises(BudgetDenied):
        reserve(ledger, slot(1))


def test_released_unsent_slot_is_consumed_forever_and_cannot_be_retried_with_another_id(
    quarantined,
):
    ledger, path = quarantined
    authorize(ledger)
    reserve(ledger)
    ledger.release_unsent("call:registered-0", error_code="VerifiedUnsent")
    status = BudgetLedger(path).experiment_scope_status(SCOPE)
    assert status.used_usd == D("0") and status.consumed_requests == 1
    with pytest.raises(LedgerConflict):
        reserve(ledger)
    with pytest.raises(BudgetDenied):
        reserve(ledger, request_id="call:new-uuid")
    reserve(ledger, slot(1))


def test_24_slots_fit_fixed_price_and_25_cannot_be_authorized(quarantined):
    ledger, _ = quarantined
    assert get_price("gpt-4o-mini").cost(16384, 1024) == BOUND
    assert 24 * BOUND <= D("0.10")
    with pytest.raises(ValueError):
        authorize(ledger, request_slots=tuple(slot(i) for i in range(25)))
    assert authorize(ledger, request_slots=tuple(slot(i) for i in range(24))).max_requests == 24


@pytest.mark.parametrize(
    "changes",
    [
        {"protocol_sha256": "not-a-digest"},
        {"protocol_sha256": "D" * 64},
        {"additional_cap_usd": D("0.100000001")},
        {"additional_cap_usd": D("NaN")},
        {"additional_cap_usd": D("0.001")},
        {"request_slots": ()},
        {"authorization_id": PARENT},
    ],
)
def test_invalid_funding_registration_never_creates_a_partial_scope(quarantined, changes):
    ledger, path = quarantined
    before = historical_rows(path)
    with pytest.raises((ValueError, LedgerConflict)):
        authorize(ledger, **changes)
    assert historical_rows(path) == before
    with pytest.raises(LedgerConflict):
        ledger.experiment_scope_status(SCOPE)


@pytest.mark.parametrize(
    "changes",
    [
        {"attempt": True},
        {"attempt": 3},
        {"case_revision": True},
        {"model": "gpt-4.1-mini"},
        {"phase": "evaluation"},
        {"input_token_reserve": 32768},
        {"max_output_tokens": 768},
        {"amount_usd": D("0.01")},
    ],
)
def test_invalid_slot_registration_is_rejected_before_any_write(quarantined, changes):
    ledger, path = quarantined
    before = historical_rows(path)
    with pytest.raises(ValueError):
        authorize(ledger, request_slots=(slot(**changes),))
    assert historical_rows(path) == before


def test_duplicate_request_id_or_attempt_identity_cannot_multiply_slots(quarantined):
    ledger, _ = quarantined
    first = slot()
    for duplicate in (first, replace(first, request_id="call:other-id")):
        with pytest.raises(ValueError):
            authorize(ledger, request_slots=(first, duplicate))


def test_changed_parent_row_blocks_new_scope_and_preserves_all_credit(quarantined):
    ledger, path = quarantined
    authorize(ledger)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE ledger_continuations SET authorization_ref='user:tampered' WHERE authorization_id=?",
            (PARENT,),
        )
    status = ledger.experiment_scope_status(SCOPE)
    assert not status.active and status.block_reason == "ParentAuthorizationChanged"
    with pytest.raises(BudgetDenied):
        reserve(ledger)


def test_pending_work_blocks_both_authorization_and_other_scope_reservations(quarantined):
    ledger, path = quarantined
    authorize(ledger)
    reserve(ledger)
    pending = ledger.snapshot().reserved_usd
    assert pending == BOUND
    assert ledger.experiment_scope_status(SCOPE).block_reason == "PendingRequest"
    with pytest.raises(BudgetDenied):
        authorize(ledger, authorization_id="second-scope")
    with pytest.raises(BudgetDenied):
        reserve(BudgetLedger(path), slot(1))
    assert ledger.snapshot().reserved_usd == pending


@pytest.mark.parametrize(
    "action, reason",
    [
        ("uncertain", "NewUncertainty"),
        ("halt", "HaltedAgain"),
        ("overrun", "CostOverrun"),
        ("reconcile", "QuarantineChanged"),
    ],
)
def test_append_only_revocation_survives_restart_and_replay_cannot_resurrect(
    quarantined, action, reason
):
    ledger, path = quarantined
    authorize(ledger)
    if action == "halt":
        ledger.halt()
    elif action == "reconcile":
        ledger.settle(OLD, cost_usd=D("0.001"), input_tokens=10, output_tokens=10)
    else:
        reserve(ledger)
        if action == "uncertain":
            ledger.mark_uncertain("call:registered-0", error_code="ProviderRequestFailed")
        else:
            ledger.settle(
                "call:registered-0",
                cost_usd=BOUND + D("0.001"),
                input_tokens=20000,
                output_tokens=1024,
            )
    reopened = BudgetLedger(path)
    status = reopened.experiment_scope_status(SCOPE)
    assert not status.active and status.block_reason == reason
    assert not authorize(reopened).active
    with pytest.raises(BudgetDenied):
        reserve(reopened, slot(1))
    with pytest.raises(BudgetDenied):
        authorize(reopened, authorization_id="cannot-replace-revoked-scope")
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT status FROM experiment_scope_events ORDER BY event_id"
        ).fetchall() == [("authorized",), ("revoked",)]
        assert connection.execute("SELECT COUNT(*) FROM experiment_scopes").fetchone()[0] == 1
    assert reopened.snapshot().halted


def test_changed_quarantine_or_additional_unknown_is_never_tolerated(quarantined):
    ledger, path = quarantined
    authorize(ledger)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE reservations SET error_code='ProviderUsageUnknown' WHERE request_id=?", (OLD,)
        )
    assert ledger.experiment_scope_status(SCOPE).block_reason == "QuarantineChanged"
    with pytest.raises(BudgetDenied):
        reserve(ledger)


def test_revoked_parent_cannot_be_used_for_a_new_grant(quarantined):
    ledger, _ = quarantined
    ledger.halt()
    with pytest.raises(BudgetDenied):
        authorize(ledger)


def test_global_cap_still_backs_old_and_new_remaining_allowances(quarantined):
    ledger, path = quarantined
    with sqlite3.connect(path) as connection:
        # Still valid original ceiling, but insufficient uncommitted room for new0.10.
        connection.execute("UPDATE ledger_meta SET opening_nanos=4300000000")
    before = historical_rows(path)
    with pytest.raises(BudgetDenied):
        authorize(ledger)
    assert historical_rows(path) == before


def test_same_authorization_race_records_one_scope_and_one_event(quarantined):
    _, path = quarantined
    barrier = Barrier(2)

    def worker(_):
        ledger = BudgetLedger(path)
        barrier.wait()
        return authorize(ledger)

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(worker, range(2)))
    assert outcomes[0] == outcomes[1]
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM experiment_scopes").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM experiment_scope_events").fetchone()[0] == 1


def test_concurrent_sends_cannot_ignore_global_pending_or_double_consume_slot(quarantined):
    ledger, path = quarantined
    authorize(ledger)
    barrier = Barrier(2)

    def worker(index):
        reopened = BudgetLedger(path)
        barrier.wait()
        try:
            reserve(reopened, slot(index))
        except BudgetDenied:
            return False
        return True

    with ThreadPoolExecutor(max_workers=2) as executor:
        accepted = list(executor.map(worker, range(2)))
    assert sum(accepted) == 1
    assert ledger.snapshot().reserved_usd == BOUND
    assert ledger.experiment_scope_status(SCOPE).consumed_requests == 1


def test_scope_creation_and_event_write_are_atomic_on_audit_failure(quarantined):
    ledger, path = quarantined
    authorize(ledger)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TRIGGER fail_new_scope_audit BEFORE INSERT ON experiment_scope_events BEGIN SELECT RAISE(ABORT, 'synthetic audit failure'); END"
        )
    before = historical_rows(path)
    with pytest.raises(LedgerUnavailable):
        authorize(ledger, authorization_id="second-scope", protocol_sha256="a" * 64)
    assert historical_rows(path) == before
    with pytest.raises(LedgerConflict):
        ledger.experiment_scope_status("second-scope")


def test_gateway_sends_only_a_registered_slot_then_settles_under_new_scope(quarantined):
    ledger, path = quarantined
    case = CaseState(case_id="case:gateway")
    context = ReasoningContext(
        run_id="run:gateway", case_id=case.case_id, case_revision=0, attempt_index=1
    )
    registered = slot(
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
                "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "offline synthetic reply"},
                    }
                ],
            },
        )

    config = MetisConfig(
        api_key=SecretStr("synthetic-not-a-provider-key"),
        live_enabled=True,
        continuation_id=SCOPE,
        input_token_reserve=16384,
        max_output_tokens=1024,
    )
    with MetisReasoner(config, ledger, transport=httpx.MockTransport(handler)) as reasoner:
        assert (
            reasoner.analyze(
                case,
                "Synthetic user input",
                EvidenceBundle(snapshot_id="synthetic"),
                context=context,
            )
            == "offline synthetic reply"
        )
        with pytest.raises(ReasoningStopped) as stopped:
            reasoner.analyze(
                case,
                "Synthetic user input",
                EvidenceBundle(snapshot_id="synthetic"),
                context=context,
            )
    assert stopped.value.code == "DuplicateModelRequest"
    assert len(wires) == 1 and wires[0]["max_tokens"] == 1024
    row = BudgetLedger(path).get(registered.request_id)
    assert row.status == "settled" and row.input_tokens == 100 and row.output_tokens == 20
    assert BudgetLedger(path).snapshot().halted
    assert BudgetLedger(path).continuation_status(PARENT).remaining_usd == D("0.002")


def test_wrong_gateway_bound_stops_before_http_without_consuming_a_slot(quarantined):
    ledger, _ = quarantined
    case = CaseState(case_id="case:gateway")
    context = ReasoningContext(
        run_id="run:gateway", case_id=case.case_id, case_revision=0, attempt_index=1
    )
    authorize(
        ledger,
        request_slots=(
            slot(request_id=request_id_for(context), run_id=context.run_id, case_id=case.case_id),
        ),
    )
    calls = []
    config = MetisConfig(
        api_key=SecretStr("synthetic-not-a-provider-key"),
        live_enabled=True,
        continuation_id=SCOPE,
        input_token_reserve=16384,
        max_output_tokens=768,
    )
    with MetisReasoner(
        config, ledger, transport=httpx.MockTransport(lambda request: calls.append(request))
    ) as reasoner:
        with pytest.raises(ReasoningStopped) as stopped:
            reasoner.analyze(
                case, "Synthetic input", EvidenceBundle(snapshot_id="synthetic"), context=context
            )
    assert stopped.value.code == "BudgetExceeded" and calls == []
    assert ledger.experiment_scope_status(SCOPE).consumed_requests == 0


def test_protocol_registration_is_immutable_and_private_values_do_not_enter_errors(quarantined):
    ledger, _ = quarantined
    authorize(ledger)
    marker = "sensitive-protocol-field"
    with pytest.raises((ValueError, LedgerConflict)) as failed:
        authorize(ledger, protocol_sha256=hashlib.sha256(marker.encode()).hexdigest())
    assert marker not in str(failed.value)


def test_same_protocol_cannot_get_fresh_credit_with_another_authorization_id(quarantined):
    ledger, _ = quarantined
    original = authorize(ledger)
    with pytest.raises(LedgerConflict):
        authorize(ledger, authorization_id="new-id-same-protocol")
    assert ledger.experiment_scope_status(SCOPE) == original


def test_two_scopes_cannot_reuse_an_already_consumed_request_slot(quarantined):
    ledger, _ = quarantined
    authorize(ledger)
    reserve(ledger)
    ledger.release_unsent("call:registered-0", error_code="VerifiedUnsent")
    with pytest.raises(LedgerConflict):
        authorize(ledger, authorization_id="new-id-new-protocol", protocol_sha256="a" * 64)


def test_concurrent_different_grants_cannot_overpromise_global_allowances(quarantined):
    ledger, path = quarantined
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE ledger_meta SET opening_nanos=4250000000")
    barrier = Barrier(2)

    def worker(index):
        reopened = BudgetLedger(path)
        barrier.wait()
        try:
            authorize(
                reopened,
                authorization_id=f"scope:concurrent-{index}",
                protocol_sha256=str(index + 1) * 64,
                request_slots=(slot(index),),
            )
        except BudgetDenied:
            return False
        return True

    with ThreadPoolExecutor(max_workers=2) as executor:
        accepted = list(executor.map(worker, range(2)))
    assert sum(accepted) == 1
    assert ledger.snapshot().halted and ledger.snapshot().reserved_usd == D("0")
