"""Explicit held-cost exceptions keep the global halt and every prior charge."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

import pytest

from agent_app.llm.budget import BudgetDenied, BudgetLedger, LedgerConflict, LedgerUnavailable

D = Decimal
OLD_REQUEST = "call:quarantined-41"
AUTHORIZATION = "continuation:paid-tests-2026-10-07"


def reserve(ledger, request_id="call:new", **changes):
    return ledger.reserve(
        **(
            {
                "request_id": request_id,
                "run_id": "run:continuation",
                "case_id": "case:continuation",
                "case_revision": 0,
                "attempt": 1,
                "model": "gpt-4o-mini",
                "phase": "development",
                "amount_usd": D("0.01"),
                "continuation_id": AUTHORIZATION,
            }
            | changes
        )
    )


def authorize(ledger, **changes):
    return ledger.authorize_continuation(
        **(
            {
                "authorization_id": AUTHORIZATION,
                "authorization_ref": "user:2026-10-07-continue-paid-tests",
                "expected_request_id": OLD_REQUEST,
                "held_usd": D("0.02"),
                "additional_cap_usd": D("0.05"),
            }
            | changes
        )
    )


def create_quarantine(path, *, amount=None, halt=True, error="ProviderModelMismatch"):
    amount = D("0.008560640") if amount is None else amount
    ledger = BudgetLedger.create(path, limit_usd=D("4.50"), opening_spend_usd=D("0"))
    reserve(
        ledger,
        OLD_REQUEST,
        model="gpt-4.1-mini",
        amount_usd=amount,
        continuation_id=None,
    )
    ledger.mark_uncertain(OLD_REQUEST, error_code=error)
    if halt:
        ledger.halt()
    return ledger


@pytest.fixture
def quarantined(tmp_path):
    path = tmp_path / "existing-ledger.sqlite3"
    return create_quarantine(path), path


def test_authorization_adds_audited_scope_and_hold_without_unhalting_or_reinitializing(quarantined):
    ledger, path = quarantined
    original = ledger.get(OLD_REQUEST)
    scope = authorize(ledger)
    snapshot = ledger.snapshot()

    assert scope.active
    assert scope.block_reason is None
    assert scope.held_usd == snapshot.uncertain_usd == D("0.02")
    assert scope.additional_cap_usd == scope.remaining_usd == D("0.05")
    assert scope.used_usd == D("0")
    assert snapshot.halted
    assert snapshot.limit_usd == D("4.50")
    assert snapshot.opening_spend_usd == snapshot.settled_usd == D("0")
    assert ledger.get(OLD_REQUEST).status == original.status == "uncertain"
    assert ledger.get(OLD_REQUEST).error_code == "ProviderModelMismatch"
    with sqlite3.connect(path) as connection:
        grant = connection.execute(
            "SELECT authorization_ref, prior_held_nanos, held_nanos FROM ledger_continuations"
        ).fetchone()
        assert grant == (scope.authorization_ref, 8_560_640, 20_000_000)
        assert connection.execute("SELECT status FROM continuation_events").fetchall() == [
            ("authorized",)
        ]
    with pytest.raises(BudgetDenied):
        reserve(ledger, continuation_id=None)
    with pytest.raises(LedgerConflict):
        BudgetLedger.create(path, limit_usd=D("4.50"), opening_spend_usd=D("0"))


def test_matching_authorization_replays_are_idempotent_and_cannot_refresh_budget(quarantined):
    ledger, path = quarantined
    first = authorize(ledger)
    assert authorize(ledger) == first
    reserve(ledger)
    ledger.settle("call:new", cost_usd=D("0.004"), input_tokens=100, output_tokens=30)
    repeated = authorize(ledger)

    assert repeated.used_usd == D("0.004")
    assert repeated.remaining_usd == D("0.046")
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM ledger_continuations").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM continuation_events").fetchone()[0] == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"authorization_ref": "user:different-authorization"},
        {"additional_cap_usd": D("0.06")},
        {"held_usd": D("0.03")},
        {"authorization_id": "continuation:replacement"},
    ],
)
def test_changed_scope_or_another_id_for_the_same_incident_is_not_an_idempotent_replay(
    quarantined, changes
):
    ledger, _ = quarantined
    authorize(ledger)
    before = ledger.snapshot()

    with pytest.raises(LedgerConflict):
        authorize(ledger, **changes)

    assert ledger.snapshot() == before


def test_hold_has_a_conservative_floor_and_can_never_decrease(tmp_path):
    floor_ledger = create_quarantine(tmp_path / "floor.sqlite3")
    before = floor_ledger.snapshot()
    with pytest.raises(ValueError):
        authorize(floor_ledger, held_usd=D("0.019999999"))
    assert floor_ledger.snapshot() == before

    larger = create_quarantine(tmp_path / "larger.sqlite3", amount=D("0.03"))
    with pytest.raises(ValueError):
        authorize(larger, held_usd=D("0.02"))
    assert larger.snapshot().uncertain_usd == D("0.03")
    assert authorize(larger, held_usd=D("0.03")).held_usd == D("0.03")


def test_scope_and_attributed_usage_survive_reopening(quarantined):
    ledger, path = quarantined
    authorize(ledger)
    reopened = BudgetLedger(path)
    assert reopened.continuation_status(AUTHORIZATION).active
    reserve(reopened)
    assert reopened.continuation_status(AUTHORIZATION).block_reason == "PendingRequest"
    reopened.settle("call:new", cost_usd=D("0.003"), input_tokens=100, output_tokens=30)
    after_restart = BudgetLedger(path).continuation_status(AUTHORIZATION)

    assert after_restart.active
    assert after_restart.used_usd == D("0.003")
    assert after_restart.remaining_usd == D("0.047")
    assert BudgetLedger(path).snapshot().halted


@pytest.mark.parametrize(
    "changes",
    [
        {"model": "gpt-4.1-mini"},
        {"model": "gpt-4o-mini-2024-07-18"},
        {"phase": "evaluation"},
        {"phase": "demo"},
        {"continuation_id": "continuation:unknown"},
        {"continuation_id": None},
        {"amount_usd": D("0.020000001")},
    ],
)
def test_out_of_scope_model_phase_grant_and_per_request_cap_are_denied(quarantined, changes):
    ledger, _ = quarantined
    authorize(ledger)

    with pytest.raises(BudgetDenied):
        reserve(ledger, **changes)

    assert ledger.get("call:new") is None
    assert ledger.continuation_status(AUTHORIZATION).used_usd == D("0")


def test_duplicate_attempt_identity_is_still_rejected_under_a_grant(quarantined):
    ledger, _ = quarantined
    authorize(ledger)
    reserve(ledger)
    ledger.settle("call:new", cost_usd=D("0.003"), input_tokens=100, output_tokens=30)

    with pytest.raises(LedgerConflict):
        reserve(ledger)

    assert ledger.continuation_status(AUTHORIZATION).used_usd == D("0.003")


def test_new_uncertainty_revokes_the_grant_and_retains_both_holds(quarantined):
    ledger, path = quarantined
    authorize(ledger)
    reserve(ledger)
    ledger.mark_uncertain("call:new", error_code="ProviderRequestFailed")
    reopened = BudgetLedger(path)
    status = reopened.continuation_status(AUTHORIZATION)

    assert not status.active
    assert status.block_reason == "NewUncertainty"
    assert reopened.snapshot().uncertain_usd == D("0.03")
    assert reopened.snapshot().halted
    assert not authorize(reopened).active
    with pytest.raises(BudgetDenied):
        reserve(reopened, "call:another")


def test_a_new_explicit_halt_revokes_without_allowing_authorization_replay_to_unhalt(quarantined):
    ledger, path = quarantined
    authorize(ledger)
    ledger.halt()
    ledger.halt()

    status = BudgetLedger(path).continuation_status(AUTHORIZATION)
    assert not status.active
    assert status.block_reason == "HaltedAgain"
    assert not authorize(ledger).active
    with pytest.raises(BudgetDenied):
        reserve(ledger)
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT status FROM continuation_events").fetchall() == [
            ("authorized",),
            ("revoked",),
        ]


def test_old_reconciliation_does_not_expand_the_attributed_continuation_allowance(quarantined):
    ledger, _ = quarantined
    authorize(ledger)
    reserve(ledger)
    ledger.settle("call:new", cost_usd=D("0.004"), input_tokens=100, output_tokens=30)
    before = ledger.continuation_status(AUTHORIZATION)
    ledger.settle(OLD_REQUEST, cost_usd=D("0.001"), input_tokens=100, output_tokens=30)
    after = ledger.continuation_status(AUTHORIZATION)

    assert not after.active
    assert after.block_reason == "QuarantineChanged"
    assert after.used_usd == before.used_usd == D("0.004")
    assert after.remaining_usd == before.remaining_usd == D("0.046")
    assert ledger.snapshot().halted
    with pytest.raises(BudgetDenied):
        reserve(ledger, "call:after-reconciliation")


def test_changed_quarantine_fingerprint_blocks_the_scope_without_resetting_it(quarantined):
    ledger, path = quarantined
    authorize(ledger)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE reservations SET error_code = 'ProviderUsageUnknown' WHERE request_id = ?",
            (OLD_REQUEST,),
        )

    assert ledger.continuation_status(AUTHORIZATION).block_reason == "QuarantineChanged"
    with pytest.raises(BudgetDenied):
        reserve(ledger)
    assert ledger.snapshot().halted


@pytest.mark.parametrize("error", ["ProviderUsageUnknown", "ProviderRequestFailed"])
def test_other_unknown_accounting_failures_cannot_use_the_identity_mismatch_exception(
    tmp_path, error
):
    ledger = create_quarantine(tmp_path / "different-failure.sqlite3", error=error)
    before = ledger.snapshot()

    with pytest.raises(BudgetDenied):
        authorize(ledger)

    assert ledger.snapshot() == before


def test_authorization_refuses_pending_work_and_never_writes_partial_control_tables(tmp_path):
    path = tmp_path / "pending.sqlite3"
    ledger = create_quarantine(path, halt=False)
    reserve(ledger, "call:pending", continuation_id=None, amount_usd=D("0"))
    ledger.halt()
    before = ledger.snapshot()

    with pytest.raises(BudgetDenied):
        authorize(ledger)

    assert ledger.snapshot() == before
    with sqlite3.connect(path) as connection:
        assert (
            connection.execute(
                "SELECT 1 FROM sqlite_master WHERE name = 'ledger_continuations'"
            ).fetchone()
            is None
        )


def test_an_unrelated_halt_without_the_expected_uncertainty_is_not_resumed(tmp_path):
    ledger = BudgetLedger.create(
        tmp_path / "unrelated.sqlite3", limit_usd=D("4.50"), opening_spend_usd=D("0")
    )
    ledger.halt()

    with pytest.raises(LedgerConflict):
        authorize(ledger)

    assert ledger.snapshot().halted
    assert ledger.snapshot().uncertain_usd == D("0")


def test_an_observed_cost_overrun_disallows_authorization(tmp_path):
    ledger = create_quarantine(tmp_path / "overrun.sqlite3", halt=False)
    reserve(ledger, "call:overrun", continuation_id=None, amount_usd=D("0.001"))
    ledger.settle("call:overrun", cost_usd=D("0.002"), input_tokens=100, output_tokens=30)
    before = ledger.snapshot()

    with pytest.raises(BudgetDenied):
        authorize(ledger)

    assert ledger.snapshot() == before


def test_new_observed_overrun_revokes_an_existing_scope_and_records_full_cost(quarantined):
    ledger, _ = quarantined
    authorize(ledger)
    reserve(ledger, amount_usd=D("0.001"))
    ledger.settle("call:new", cost_usd=D("0.002"), input_tokens=100, output_tokens=30)

    assert ledger.continuation_status(AUTHORIZATION).block_reason == "CostOverrun"
    assert ledger.snapshot().settled_usd == D("0.002")
    assert ledger.snapshot().uncertain_usd == D("0.02")
    with pytest.raises(BudgetDenied):
        reserve(ledger, "call:after-overrun")


def test_grant_authorization_still_fits_within_the_original_global_budget(quarantined):
    ledger, _ = quarantined
    before = ledger.snapshot()

    with pytest.raises(BudgetDenied):
        authorize(ledger, additional_cap_usd=D("4.49"))

    assert ledger.snapshot() == before


def test_atomic_reservations_cannot_race_past_the_scoped_cap(quarantined):
    ledger, path = quarantined
    authorize(ledger, additional_cap_usd=D("0.02"))
    barrier = Barrier(2)

    def attempt(index):
        reopened = BudgetLedger(path)
        barrier.wait()
        try:
            reserve(reopened, f"call:concurrent-{index}", amount_usd=D("0.015"))
        except BudgetDenied:
            return False
        reopened.settle(
            f"call:concurrent-{index}", cost_usd=D("0.015"), input_tokens=100, output_tokens=30
        )
        return True

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(attempt, range(2)))

    assert sum(outcomes) == 1
    assert ledger.continuation_status(AUTHORIZATION).used_usd == D("0.015")
    assert ledger.continuation_status(AUTHORIZATION).remaining_usd == D("0.005")
    assert ledger.snapshot().halted


def test_audit_failure_rolls_back_top_up_and_authorization_atomically(quarantined):
    ledger, path = quarantined
    before = ledger.snapshot()
    with sqlite3.connect(path) as connection:
        connection.execute(
            """CREATE TRIGGER fail_audit BEFORE INSERT ON ledger_events
            BEGIN SELECT RAISE(ABORT, 'test audit failure'); END"""
        )

    with pytest.raises(LedgerUnavailable):
        authorize(ledger)

    assert ledger.snapshot() == before
    with pytest.raises(LedgerConflict):
        ledger.continuation_status(AUTHORIZATION)
