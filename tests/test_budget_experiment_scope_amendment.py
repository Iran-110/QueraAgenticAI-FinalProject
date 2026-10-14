"""Additional closure and corrupt-scope controls, separate from frozen V1/V2 tests.

V1's audit-failure fixture reused earlier frozen slots, so it hit a legitimate
identity conflict before the injected audit error. Its V2 amendment changes only
that second grant's request slots to fresh identities, preserving the oracle.
These controls exercise permanent closure and fail-closed boundaries separately.
"""

import sqlite3
from decimal import Decimal

import pytest
from test_budget_experiment_scope import (
    PARENT,
    SCOPE,
    authorize,
    historical_rows,
    reserve,
    slot,
)
from test_budget_experiment_scope import quarantined as quarantined

from agent_app.llm.budget import BudgetDenied, BudgetLedger, LedgerConflict, LedgerUnavailable


def test_close_is_a_permanent_append_only_scope_event_and_does_not_replenish_history(quarantined):
    ledger, path = quarantined
    authorize(ledger)
    before = historical_rows(path)
    original_parent = ledger.continuation_status(PARENT)
    status = ledger.close_experiment_scope(SCOPE)
    assert not status.active and status.block_reason == "ExperimentClosed"
    assert historical_rows(path) == before
    assert ledger.continuation_status(PARENT) == original_parent
    assert ledger.snapshot().halted
    assert not authorize(BudgetLedger(path)).active
    with pytest.raises(BudgetDenied):
        reserve(ledger)
    assert ledger.close_experiment_scope(SCOPE) == status
    ledger.halt()
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT status,reason_code FROM experiment_scope_events ORDER BY event_id"
        ).fetchall() == [
            ("authorized", "UserAuthorizedExperimentScope"),
            ("closed", "ExperimentClosed"),
        ]
        assert connection.execute("SELECT COUNT(*) FROM experiment_scopes").fetchone()[0] == 1


def test_closing_keeps_a_pending_reservation_held_and_allows_known_cost_settlement(quarantined):
    ledger, path = quarantined
    authorize(ledger)
    reserve(ledger)
    reservation = ledger.get("call:registered-0")
    ledger.close_experiment_scope(SCOPE)
    assert ledger.get(reservation.request_id) == reservation
    assert ledger.snapshot().reserved_usd == reservation.amount_usd
    ledger.settle(
        reservation.request_id, cost_usd=Decimal("0.001"), input_tokens=100, output_tokens=10
    )
    status = BudgetLedger(path).experiment_scope_status(SCOPE)
    assert status.block_reason == "ExperimentClosed" and status.used_usd == Decimal("0.001")
    assert status.consumed_requests == 1
    assert ledger.snapshot().reserved_usd == Decimal("0")
    with pytest.raises(BudgetDenied):
        reserve(ledger, slot(1))


def test_unknown_scope_close_is_sanitized_and_has_no_partial_write(quarantined):
    ledger, path = quarantined
    before = historical_rows(path)
    with pytest.raises(LedgerConflict) as failed:
        ledger.close_experiment_scope("scope:unknown-private-marker")
    assert "private-marker" not in str(failed.value)
    assert historical_rows(path) == before
    with sqlite3.connect(path) as connection:
        assert (
            connection.execute(
                "SELECT 1 FROM sqlite_master WHERE name='experiment_scope_events'"
            ).fetchone()
            is None
        )


def test_close_event_failure_rolls_back_and_keeps_scope_active(quarantined):
    ledger, path = quarantined
    authorize(ledger)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TRIGGER fail_close BEFORE INSERT ON experiment_scope_events "
            "BEGIN SELECT RAISE(ABORT, 'synthetic close failure'); END"
        )
    with pytest.raises(LedgerUnavailable):
        ledger.close_experiment_scope(SCOPE)
    assert ledger.experiment_scope_status(SCOPE).active
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM experiment_scope_events").fetchone()[0] == 1


def test_close_after_revocation_does_not_rewrite_the_failure_or_append_another_terminal_event(
    quarantined,
):
    ledger, path = quarantined
    authorize(ledger)
    ledger.halt()
    status = ledger.close_experiment_scope(SCOPE)
    assert not status.active and status.block_reason == "HaltedAgain"
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT status FROM experiment_scope_events ORDER BY event_id"
        ).fetchall() == [
            ("authorized",),
            ("revoked",),
        ]


@pytest.mark.parametrize("mutation", ["slot_bound", "slot_money", "missing_table"])
def test_corrupt_scope_denies_status_close_and_reservation_without_new_writes(
    quarantined, mutation
):
    ledger, path = quarantined
    authorize(ledger)
    with sqlite3.connect(path) as connection:
        if mutation == "slot_bound":
            connection.execute("UPDATE experiment_scope_slots SET max_output_tokens=512")
        elif mutation == "slot_money":
            connection.execute(
                "UPDATE experiment_scope_slots SET amount_nanos='corrupt-private-value'"
            )
        else:
            connection.execute("DROP TABLE experiment_scope_slots")
    for operation in (
        lambda: ledger.experiment_scope_status(SCOPE),
        lambda: ledger.close_experiment_scope(SCOPE),
        lambda: reserve(ledger),
    ):
        with pytest.raises(LedgerUnavailable) as failed:
            operation()
        assert "private-value" not in str(failed.value)
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM experiment_scope_events").fetchone()[0] == 1
        assert (
            connection.execute("SELECT COUNT(*) FROM experiment_scope_requests").fetchone()[0] == 0
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"input_token_reserve": 16384.0},
        {"max_output_tokens": 1024.0},
        {"amount_usd": Decimal("0.00337919999")},
    ],
)
def test_frozen_request_identity_rejects_float_bounds_and_sub_nano_money_changes(
    quarantined, changes
):
    ledger, _ = quarantined
    authorize(ledger)
    with pytest.raises(BudgetDenied):
        reserve(ledger, **changes)
    assert ledger.experiment_scope_status(SCOPE).consumed_requests == 0
