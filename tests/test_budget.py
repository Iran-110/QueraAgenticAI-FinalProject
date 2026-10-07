"""Durable accounting and fail-closed state transitions without paid requests."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

import pytest

from agent_app.llm import budget
from agent_app.llm.budget import BudgetDenied, BudgetLedger, LedgerConflict, LedgerUnavailable

D = Decimal


@pytest.fixture
def ledger(tmp_path):
    return BudgetLedger.create(
        tmp_path / "team-budget.sqlite3", limit_usd=D("5"), opening_spend_usd=D("0")
    )


def reserve(ledger, **changes):
    fields = {
        "request_id": "request:1",
        "run_id": "run:1",
        "case_id": "case:1",
        "case_revision": 0,
        "attempt": 1,
        "model": "gpt-4.1-mini",
        "phase": "analysis",
        "amount_usd": D("0.50"),
    }
    return ledger.reserve(**(fields | changes))


def settle(ledger, **changes):
    fields = {"cost_usd": D("0.20"), "input_tokens": 100, "output_tokens": 50}
    return ledger.settle("request:1", **(fields | changes))


def test_opening_spend_is_explicit_and_does_not_disappear_on_reopen(tmp_path):
    path = tmp_path / "team.sqlite3"
    ledger = BudgetLedger.create(path, limit_usd=D("5"), opening_spend_usd=D("1.25"))
    reserve(ledger)
    snapshot = BudgetLedger(path).snapshot()
    assert snapshot.limit_usd == D("5")
    assert snapshot.opening_spend_usd == D("1.25")
    assert snapshot.reserved_usd == D("0.50")
    assert snapshot.available_usd == D("3.25")
    assert snapshot.settled_usd == snapshot.uncertain_usd == D("0")


def test_constructor_never_creates_a_missing_database(tmp_path):
    path = tmp_path / "missing.sqlite3"
    with pytest.raises(LedgerUnavailable, match="^Budget ledger unavailable.$"):
        BudgetLedger(path)
    assert not path.exists()


@pytest.mark.parametrize("contents", [b"", b"unrelated or corrupt database"])
def test_uninitialized_or_corrupt_database_is_not_treated_as_zero_spend(tmp_path, contents):
    path = tmp_path / "broken.sqlite3"
    path.write_bytes(contents)
    with pytest.raises(LedgerUnavailable):
        BudgetLedger(path)
    assert path.read_bytes() == contents


def test_create_cannot_reset_an_existing_ledger_even_with_identical_configuration(tmp_path):
    path = tmp_path / "team.sqlite3"
    ledger = BudgetLedger.create(path, limit_usd=D("5"), opening_spend_usd=D("0"))
    reserve(ledger)
    settle(ledger)
    for limit in (D("5"), D("4")):
        with pytest.raises(LedgerConflict):
            BudgetLedger.create(path, limit_usd=limit, opening_spend_usd=D("0"))
    assert BudgetLedger(path).snapshot().settled_usd == D("0.20")


def test_budget_denial_does_not_create_a_request_record(ledger):
    reserve(ledger, amount_usd=D("4.5"))
    with pytest.raises(BudgetDenied):
        reserve(ledger, request_id="request:2", amount_usd=D("0.5000000001"))
    assert ledger.get("request:2") is None
    assert ledger.snapshot().reserved_usd == D("4.5")


def test_reservations_and_costs_round_up_while_limit_rounds_down(tmp_path):
    path = tmp_path / "tiny.sqlite3"
    ledger = BudgetLedger.create(path, limit_usd=D("0.0000000019"), opening_spend_usd=D("0"))
    reservation = reserve(ledger, amount_usd=D("0.0000000000000000000000000001"))
    assert reservation.amount_usd == D("0.000000001")
    assert ledger.snapshot().limit_usd == D("0.000000001")
    with pytest.raises(BudgetDenied):
        reserve(ledger, request_id="request:2", amount_usd=D("0.0000000001"))
    result = settle(ledger, cost_usd=D("0.0000000001"))
    assert result.cost_usd == D("0.000000001")
    assert not ledger.snapshot().halted


def test_rounding_uses_all_decimal_digits_instead_of_context_precision(ledger):
    reservation = reserve(ledger, amount_usd=D("0.12345678900000000000000000000000000001"))
    assert reservation.amount_usd == D("0.123456790")


def test_exact_repeated_settlement_is_idempotent_but_conflicting_details_are_rejected(ledger):
    reserve(ledger)
    first = settle(ledger)
    assert settle(ledger, cost_usd=D("0.200")) == first
    for changed in ({"cost_usd": D("0.21")}, {"input_tokens": 101}, {"output_tokens": 51}):
        with pytest.raises(LedgerConflict):
            settle(ledger, **changed)
    assert ledger.snapshot().settled_usd == D("0.20")
    assert ledger.snapshot().reserved_usd == D("0")
    assert ledger.snapshot().available_usd == D("4.80")


def test_settlement_conflict_cannot_hide_beneath_nano_dollar_rounding(ledger):
    reserve(ledger)
    settle(ledger, cost_usd=D("0.20000000001"))
    with pytest.raises(LedgerConflict):
        settle(ledger, cost_usd=D("0.20000000002"))


def test_pending_and_uncertain_reservations_survive_restart_without_expiry(tmp_path):
    path = tmp_path / "team.sqlite3"
    ledger = BudgetLedger.create(path, limit_usd=D("5"), opening_spend_usd=D("0"))
    reserved = reserve(ledger, amount_usd=D("3"))
    reserve(ledger, request_id="request:2", amount_usd=D("2"))
    uncertain = ledger.mark_uncertain("request:2", error_code="ProviderTimeout")
    reopened = BudgetLedger(path)
    assert reopened.get("request:1") == reserved
    assert reopened.get("request:2") == uncertain
    snapshot = reopened.snapshot()
    assert snapshot.reserved_usd == D("3")
    assert snapshot.uncertain_usd == D("2")
    assert snapshot.available_usd == D("0")
    with pytest.raises(BudgetDenied):
        reserve(reopened, request_id="request:3", amount_usd=D("0.01"))
    result = reopened.settle("request:2", cost_usd=D("1"), input_tokens=2, output_tokens=1)
    assert result.status == "settled"
    assert reopened.snapshot().available_usd == D("1")


def test_uncertainty_mark_is_idempotent_and_cannot_refund_reservation(ledger):
    reserve(ledger)
    first = ledger.mark_uncertain("request:1", error_code="ProviderTimeout")
    assert ledger.mark_uncertain("request:1", error_code="ProviderTimeout") == first
    with pytest.raises(LedgerConflict):
        ledger.mark_uncertain("request:1", error_code="DifferentFailure")
    with pytest.raises(LedgerConflict):
        ledger.release_unsent("request:1", error_code="DefinitelyUnsent")
    assert ledger.snapshot().uncertain_usd == D("0.50")
    assert ledger.snapshot().available_usd == D("4.50")


def test_definitely_unsent_release_preserves_record_and_audit_but_returns_budget(ledger, tmp_path):
    reserve(ledger)
    result = ledger.release_unsent("request:1", error_code="UnsentConfigurationError")
    assert result.status == "released"
    assert result.amount_usd == D("0.50")
    assert result.error_code == "UnsentConfigurationError"
    assert ledger.get("request:1") == result
    assert ledger.snapshot().available_usd == D("5")
    with sqlite3.connect(tmp_path / "team-budget.sqlite3") as connection:
        assert connection.execute(
            "SELECT status FROM ledger_events ORDER BY event_id"
        ).fetchall() == [
            ("reserved",),
            ("released",),
        ]
    with pytest.raises(LedgerConflict):
        ledger.release_unsent("request:1", error_code="UnsentConfigurationError")
    with pytest.raises(LedgerConflict):
        settle(ledger)


@pytest.mark.parametrize("status", ["reserved", "settled", "uncertain", "released"])
def test_duplicate_request_ids_always_conflict_instead_of_authorizing_another_send(ledger, status):
    reserve(ledger)
    if status == "settled":
        settle(ledger)
    elif status == "uncertain":
        ledger.mark_uncertain("request:1", error_code="ProviderTimeout")
    elif status == "released":
        ledger.release_unsent("request:1", error_code="DefinitelyUnsent")
    with pytest.raises(LedgerConflict):
        reserve(ledger, case_id="case:different", amount_usd=D("0"))


def test_duplicate_request_conflict_takes_precedence_over_invalid_replacement_metadata(ledger):
    reserve(ledger)
    with pytest.raises(LedgerConflict):
        reserve(ledger, case_revision=-1, amount_usd=float("nan"))


@pytest.mark.parametrize("cost", [D("0.60"), D("6")])
def test_overrun_cost_is_recorded_and_new_reservations_remain_halted_on_reopen(tmp_path, cost):
    path = tmp_path / "team.sqlite3"
    ledger = BudgetLedger.create(path, limit_usd=D("5"), opening_spend_usd=D("0"))
    reserve(ledger)
    result = settle(ledger, cost_usd=cost)
    assert result.cost_usd == cost
    snapshot = BudgetLedger(path).snapshot()
    assert snapshot.settled_usd == cost
    assert snapshot.available_usd == max(D("0"), D("5") - cost)
    assert snapshot.halted
    with pytest.raises(BudgetDenied):
        reserve(BudgetLedger(path), request_id="request:2", amount_usd=D("0"))


def test_explicit_halt_persists_blocks_new_requests_and_still_allows_reconciliation(tmp_path):
    path = tmp_path / "team.sqlite3"
    ledger = BudgetLedger.create(path, limit_usd=D("5"), opening_spend_usd=D("0"))
    reserve(ledger)
    ledger.halt()
    ledger.halt()
    reopened = BudgetLedger(path)
    assert reopened.snapshot().halted
    with pytest.raises(BudgetDenied):
        reserve(reopened, request_id="request:2", amount_usd=D("0.01"))
    assert settle(reopened).status == "settled"
    assert reopened.snapshot().settled_usd == D("0.20")
    assert reopened.snapshot().halted


def test_multiple_known_overruns_can_be_reconciled_without_sqlite_sum_overflow(ledger):
    reserve(ledger, amount_usd=D("1"))
    reserve(ledger, request_id="request:2", amount_usd=D("1"))
    settle(ledger, cost_usd=D("9000000000"))
    ledger.settle("request:2", cost_usd=D("9000000000"), input_tokens=0, output_tokens=0)
    snapshot = ledger.snapshot()
    assert snapshot.settled_usd == D("18000000000")
    assert snapshot.available_usd == D("0")
    assert snapshot.halted


def test_distinct_connections_cannot_concurrently_reserve_more_than_available(tmp_path):
    path = tmp_path / "team.sqlite3"
    BudgetLedger.create(path, limit_usd=D("1"), opening_spend_usd=D("0"))
    barrier = Barrier(2)

    def attempt(index):
        ledger = BudgetLedger(path)
        barrier.wait(timeout=5)
        try:
            reserve(ledger, request_id=f"request:{index}", amount_usd=D("0.60"))
            return "reserved"
        except BudgetDenied:
            return "denied"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(attempt, [1, 2]))
    assert sorted(results) == ["denied", "reserved"]
    snapshot = BudgetLedger(path).snapshot()
    assert snapshot.reserved_usd == D("0.60")
    assert snapshot.available_usd == D("0.40")


@pytest.mark.parametrize("invalid", [0.1, True, "0.1", D("-1"), D("NaN"), D("Infinity"), D("1e20")])
def test_money_validation_rejects_unsafe_values_without_reserving_or_settling(ledger, invalid):
    with pytest.raises(ValueError):
        reserve(ledger, amount_usd=invalid)
    assert ledger.get("request:1") is None
    reserve(ledger)
    with pytest.raises(ValueError):
        settle(ledger, cost_usd=invalid)
    assert ledger.get("request:1").status == "reserved"


@pytest.mark.parametrize(
    ("limit", "opening"),
    [
        (D("5.0000000001"), D("0")),
        (D("5"), D("5.01")),
        (D("1"), D("1.0000000001")),
        (D("5"), D("-0.1")),
        (5.0, D("0")),
        (D("5"), False),
    ],
)
def test_invalid_initialization_never_creates_a_database(tmp_path, limit, opening):
    path = tmp_path / "bad.sqlite3"
    with pytest.raises(ValueError):
        BudgetLedger.create(path, limit_usd=limit, opening_spend_usd=opening)
    assert not path.exists()


@pytest.mark.parametrize(
    "changes",
    [
        {"case_revision": -1},
        {"case_revision": True},
        {"case_revision": "0"},
        {"attempt": 0},
        {"attempt": 3},
        {"attempt": 1.0},
        {"attempt": True},
        {"request_id": ""},
        {"request_id": "x" * 201},
        {"model": "model with spaces"},
        {"phase": "../../secret"},
        {"phase": "analysis\n"},
    ],
)
def test_invalid_reservation_metadata_is_rejected_before_writes(ledger, changes):
    with pytest.raises(ValueError):
        reserve(ledger, **changes)
    assert ledger.snapshot().reserved_usd == D("0")


@pytest.mark.parametrize("field", ["input_tokens", "output_tokens"])
@pytest.mark.parametrize("invalid", [-1, True, "1", 1.0, 2**63])
def test_usage_counts_are_nonnegative_strict_integers(ledger, field, invalid):
    reserve(ledger)
    with pytest.raises(ValueError):
        settle(ledger, **{field: invalid})
    assert ledger.get("request:1").status == "reserved"


def test_unknown_requests_do_not_implicitly_create_reservations(ledger):
    assert ledger.get("missing:1") is None
    for action in (
        lambda: ledger.settle("missing:1", cost_usd=D("0"), input_tokens=0, output_tokens=0),
        lambda: ledger.mark_uncertain("missing:1", error_code="ProviderTimeout"),
        lambda: ledger.release_unsent("missing:1", error_code="DefinitelyUnsent"),
    ):
        with pytest.raises(LedgerConflict):
            action()
    assert ledger.snapshot().available_usd == D("5")


def test_database_errors_are_static_and_do_not_leak_sensitive_messages(ledger, monkeypatch):
    def broken_connect(*args, **kwargs):
        raise sqlite3.OperationalError("private path /secret/key sk-do-not-display")

    monkeypatch.setattr(budget.sqlite3, "connect", broken_connect)
    with pytest.raises(LedgerUnavailable) as caught:
        ledger.snapshot()
    assert str(caught.value) == "Budget ledger unavailable."
    assert caught.value.__suppress_context__


def test_failure_during_audit_rolls_back_the_reservation_and_exposes_no_raw_error(ledger, tmp_path):
    with sqlite3.connect(tmp_path / "team-budget.sqlite3") as connection:
        connection.execute(
            """CREATE TRIGGER fail_audit BEFORE INSERT ON ledger_events
            BEGIN SELECT RAISE(ABORT, 'secret internal error'); END"""
        )
    with pytest.raises(LedgerUnavailable, match="^Budget ledger unavailable.$"):
        reserve(ledger)
    assert ledger.get("request:1") is None
    assert ledger.snapshot().available_usd == D("5")


def test_invalid_persisted_record_fails_closed_instead_of_ignoring_spend(ledger, tmp_path):
    reserve(ledger)
    with sqlite3.connect(tmp_path / "team-budget.sqlite3") as connection:
        connection.execute("PRAGMA ignore_check_constraints = ON")
        connection.execute(
            "UPDATE reservations SET status = 'unknown' WHERE request_id = 'request:1'"
        )
    with pytest.raises(LedgerUnavailable):
        ledger.snapshot()
    with pytest.raises(LedgerUnavailable):
        BudgetLedger(tmp_path / "team-budget.sqlite3")
