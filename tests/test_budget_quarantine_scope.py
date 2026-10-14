"""Fresh finite user authorization binds all pre-existing uncertain records.

Synthetic ledgers, IDs and provider responses only; no team ledger or key.
Historical grants/holds stay revoked and ordinary live remains halted.
"""

import hashlib
import json
import sqlite3
from dataclasses import asdict, replace
from decimal import Decimal

import httpx
import pytest

from agent_app.contracts import CaseState, EvidenceBundle, ReasoningContext
from agent_app.llm.budget import (
    BudgetDenied,
    BudgetLedger,
    ExperimentRequestSlot,
    LedgerConflict,
    LedgerUnavailable,
)
from agent_app.llm.config import MetisConfig
from agent_app.llm.metis import MetisReasoner, request_id_for
from agent_app.llm.pricing import get_price
from agent_app.orchestration.ports import ReasoningStopped

D = Decimal
SCOPE = "synthetic-fresh-quarantine-scope"


def slot(index=0, *, output=1024, input_limit=16384):
    context = ReasoningContext(
        run_id=f"synthetic-fresh-run-{index}",
        case_id="synthetic-case",
        case_revision=1,
        attempt_index=1,
    )
    return ExperimentRequestSlot(
        request_id=request_id_for(context),
        run_id=context.run_id,
        case_id=context.case_id,
        case_revision=context.case_revision,
        attempt=1,
        input_token_reserve=input_limit,
        max_output_tokens=output,
        amount_usd=get_price("gpt-4o-mini").cost(input_limit, output),
    )


@pytest.fixture
def multiple_holds(tmp_path):
    path = tmp_path / "synthetic.sqlite3"
    ledger = BudgetLedger.create(path, limit_usd=D("4.50"), opening_spend_usd=D("0"))
    ledger.reserve(
        request_id="synthetic-original-mismatch",
        run_id="synthetic-old-run",
        case_id="synthetic-old-case",
        case_revision=0,
        attempt=1,
        model="gpt-4.1-mini",
        phase="development",
        amount_usd=D("0.008560640"),
    )
    ledger.mark_uncertain("synthetic-original-mismatch", error_code="ProviderModelMismatch")
    ledger.halt()
    ledger.authorize_continuation(
        authorization_id="synthetic-old-grant",
        authorization_ref="synthetic-old-user",
        expected_request_id="synthetic-original-mismatch",
        held_usd=D("0.02"),
        additional_cap_usd=D("0.10"),
    )
    legacy = (
        replace(slot(100), request_id="synthetic-legacy-slot"),
        replace(slot(101), request_id="synthetic-legacy-unused"),
    )
    ledger.authorize_experiment_scope(
        authorization_id="synthetic-old-experiment",
        authorization_ref="synthetic-old-user",
        parent_authorization_id="synthetic-old-grant",
        protocol_sha256="a" * 64,
        request_slots=legacy,
        additional_cap_usd=D("0.10"),
    )
    ledger.reserve(**asdict(legacy[0]), continuation_id="synthetic-old-experiment")
    ledger.mark_uncertain(legacy[0].request_id, error_code="ProviderRequestFailed")
    return ledger, path, legacy


def old_rows(path):
    names = (
        "ledger_meta",
        "ledger_continuations",
        "continuation_requests",
        "continuation_events",
        "experiment_scopes",
        "experiment_scope_slots",
        "experiment_scope_requests",
        "experiment_scope_events",
    )
    with sqlite3.connect(path) as connection:
        result = {
            name: connection.execute(f"SELECT * FROM {name} ORDER BY rowid").fetchall()
            for name in names
        }
        result["old_reservations"] = connection.execute(
            "SELECT * FROM reservations WHERE request_id IN ('synthetic-original-mismatch','synthetic-legacy-slot') ORDER BY request_id"
        ).fetchall()
        result["old_events"] = connection.execute(
            "SELECT * FROM ledger_events WHERE request_id IN ('synthetic-original-mismatch','synthetic-legacy-slot') ORDER BY event_id"
        ).fetchall()
        return result


def authorize(ledger, *, registered=None, observation=None, **changes):
    observed = ledger.quarantine_observation() if observation is None else observation
    values = {
        "authorization_id": SCOPE,
        "authorization_ref": "synthetic-fresh-explicit-user",
        "expected_unknown_ids": observed.unknown_ids,
        "expected_unknown_fingerprints": observed.unknown_fingerprints,
        "expected_meta_sha256": observed.meta_sha256,
        "expected_authorization_history_sha256": observed.authorization_history_sha256,
        "protocol_sha256": "d" * 64,
        "request_slots": (slot(), slot(1)) if registered is None else registered,
        "additional_cap_usd": D("0.10"),
    }
    return ledger.authorize_quarantine_scope(**(values | changes))


def reserve(ledger, registered=None, **changes):
    registered = slot() if registered is None else registered
    return ledger.reserve(**(asdict(registered) | {"continuation_id": SCOPE} | changes))


def test_existing_singleton_apis_cannot_reactivate_revoked_two_hold_state(multiple_holds):
    ledger, path, legacy = multiple_holds
    before = old_rows(path)
    assert ledger.continuation_status("synthetic-old-grant").block_reason == "NewUncertainty"
    with pytest.raises(LedgerConflict):
        ledger.authorize_continuation(
            authorization_id="synthetic-new-name",
            authorization_ref="synthetic-new-user",
            expected_request_id="synthetic-original-mismatch",
            held_usd=D("0.02"),
            additional_cap_usd=D("0.10"),
        )
    with pytest.raises(BudgetDenied):
        ledger.authorize_experiment_scope(
            authorization_id="synthetic-new-legacy",
            authorization_ref="synthetic-new-user",
            parent_authorization_id="synthetic-old-grant",
            protocol_sha256="b" * 64,
            request_slots=(slot(99),),
            additional_cap_usd=D("0.10"),
        )
    assert old_rows(path) == before


def test_new_scope_preserves_old_holds_revocations_and_global_halt(multiple_holds):
    ledger, path, _legacy = multiple_holds
    before = old_rows(path)
    file_before = hashlib.sha256(path.read_bytes()).hexdigest()
    observed = ledger.quarantine_observation()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == file_before
    assert observed.unknown_ids == tuple(
        sorted(("synthetic-original-mismatch", "synthetic-legacy-slot"))
    )
    assert observed.held_usd == D("0.0233792")
    scope = authorize(ledger)
    assert scope.active and scope.unknown_ids == observed.unknown_ids
    assert scope.max_requests == 2 and scope.consumed_requests == 0
    assert scope.held_usd == observed.held_usd and scope.additional_cap_usd == D("0.10")
    assert old_rows(path) == before
    assert ledger.quarantine_observation() == observed
    assert ledger.snapshot().halted and ledger.snapshot().limit_usd == D("4.50")
    assert ledger.continuation_status("synthetic-old-grant").block_reason == "NewUncertainty"
    with pytest.raises(BudgetDenied):
        reserve(ledger, continuation_id=None)


@pytest.mark.parametrize(
    "changes",
    [
        {"authorization_ref": "synthetic-different-user"},
        {"protocol_sha256": "e" * 64},
        {"additional_cap_usd": D("0.09")},
        {"expected_meta_sha256": "e" * 64},
        {"expected_authorization_history_sha256": "e" * 64},
    ],
)
def test_changed_reauthorization_never_refreshes_credit(multiple_holds, changes):
    ledger, _path, _legacy = multiple_holds
    original = authorize(ledger)
    with pytest.raises(LedgerConflict):
        authorize(ledger, **changes)
    assert ledger.quarantine_scope_status(SCOPE) == original


def test_normal_settlement_keeps_quarantine_binding_and_exact_replay_does_not_refill(
    multiple_holds,
):
    ledger, path, _legacy = multiple_holds
    before = old_rows(path)
    observed = ledger.quarantine_observation()
    authorize(ledger)
    reserve(ledger)
    ledger.settle(slot().request_id, cost_usd=D("0.001"), input_tokens=100, output_tokens=20)
    status = authorize(BudgetLedger(path))
    assert status.active and status.used_usd == D("0.001") and status.remaining_usd == D("0.099")
    assert status.consumed_requests == 1 and ledger.quarantine_observation() == observed
    assert old_rows(path) == before
    with pytest.raises(LedgerConflict):
        reserve(ledger)


@pytest.mark.parametrize(
    "mutation", ["omitted", "reversed", "wrong_fingerprint", "meta", "history"]
)
def test_incomplete_or_changed_observation_denied_before_new_schema(multiple_holds, mutation):
    ledger, path, _legacy = multiple_holds
    observed = ledger.quarantine_observation()
    changes = {}
    if mutation == "omitted":
        changes.update(
            expected_unknown_ids=observed.unknown_ids[:1],
            expected_unknown_fingerprints=observed.unknown_fingerprints[:1],
        )
    elif mutation == "reversed":
        changes.update(
            expected_unknown_ids=tuple(reversed(observed.unknown_ids)),
            expected_unknown_fingerprints=tuple(reversed(observed.unknown_fingerprints)),
        )
    elif mutation == "wrong_fingerprint":
        changes["expected_unknown_fingerprints"] = tuple(
            (identity, "c" * 64) for identity, _digest in observed.unknown_fingerprints
        )
    elif mutation == "meta":
        changes["expected_meta_sha256"] = "c" * 64
    else:
        changes["expected_authorization_history_sha256"] = "c" * 64
    before = old_rows(path)
    with pytest.raises((BudgetDenied, ValueError)):
        authorize(ledger, **changes)
    assert old_rows(path) == before
    with sqlite3.connect(path) as connection:
        assert (
            connection.execute(
                "SELECT 1 FROM sqlite_master WHERE name='quarantine_scopes'"
            ).fetchone()
            is None
        )


@pytest.mark.parametrize(
    "output,input_limit", [(1024, 16384), (2048, 16384), (1024, 24576), (2048, 24576)]
)
def test_registered_input_output_profiles_keep_exact_verified_cost(
    multiple_holds, output, input_limit
):
    ledger, _path, _legacy = multiple_holds
    registered = slot(output=output, input_limit=input_limit)
    authorize(ledger, registered=(registered,))
    reserve(ledger, registered)
    assert ledger.get(registered.request_id).amount_usd == get_price("gpt-4o-mini").cost(
        input_limit, output
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"request_id": "synthetic-unbound-id"},
        {"run_id": "synthetic-other-run"},
        {"phase": "test"},
        {"model": "gpt-4.1-mini"},
        {"max_output_tokens": 4096},
        {"max_output_tokens": 2048.0},
        {"input_token_reserve": 32768},
        {"input_token_reserve": 16384.0},
        {"amount_usd": D("0.0033791999")},
    ],
)
def test_unregistered_or_noncaller_request_bounds_fail_before_funding(multiple_holds, changes):
    ledger, path, _legacy = multiple_holds
    before = old_rows(path)
    with pytest.raises(ValueError):
        authorize(ledger, registered=(replace(slot(), **changes),))
    assert old_rows(path) == before


@pytest.mark.parametrize(
    "changes",
    [
        {"run_id": "synthetic-other-run"},
        {"case_revision": 2},
        {"attempt": 2},
        {"model": "gpt-4.1-mini"},
        {"phase": "test"},
        {"max_output_tokens": 2048},
        {"input_token_reserve": 24576},
        {"amount_usd": D("0.0033792001")},
    ],
)
def test_reservation_cannot_change_frozen_slot_or_allocate_an_unlisted_attempt(
    multiple_holds, changes
):
    ledger, _path, _legacy = multiple_holds
    authorize(ledger)
    with pytest.raises(BudgetDenied):
        reserve(ledger, **changes)
    assert ledger.quarantine_scope_status(SCOPE).consumed_requests == 0


def test_closed_scope_is_permanent_and_unused_identities_cannot_be_recycled(multiple_holds):
    ledger, path, _legacy = multiple_holds
    authorize(ledger)
    closed = ledger.close_quarantine_scope(SCOPE)
    assert not closed.active and closed.block_reason == "ExperimentClosed"
    assert authorize(BudgetLedger(path)) == closed
    assert ledger.close_quarantine_scope(SCOPE) == closed
    with pytest.raises(BudgetDenied):
        reserve(ledger)
    with pytest.raises(LedgerConflict):
        authorize(ledger, authorization_id="synthetic-another-name", protocol_sha256="f" * 64)
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT status FROM quarantine_scope_events ORDER BY event_id"
        ).fetchall() == [("authorized",), ("closed",)]


def test_historical_unused_request_identity_cannot_move_to_new_scope(multiple_holds):
    ledger, _path, legacy = multiple_holds
    # A historical slot with an arbitrary ID remains claimed by its old context.
    old = legacy[1]
    context = ReasoningContext(
        run_id=old.run_id,
        case_id=old.case_id,
        case_revision=old.case_revision,
        attempt_index=old.attempt,
    )
    registered = replace(old, request_id=request_id_for(context))
    with pytest.raises(LedgerConflict):
        authorize(ledger, registered=(registered,))


@pytest.mark.parametrize(
    "operation,expected",
    [
        ("new_uncertainty", "NewUncertainty"),
        ("halt", "HaltedAgain"),
        ("overrun", "CostOverrun"),
        ("reconcile_old", "QuarantineChanged"),
    ],
)
def test_new_failure_or_quarantine_change_terminally_revokes_without_reactivation(
    multiple_holds, operation, expected
):
    ledger, path, _legacy = multiple_holds
    authorize(ledger)
    if operation == "halt":
        ledger.halt()
    elif operation == "reconcile_old":
        ledger.settle(
            "synthetic-legacy-slot", cost_usd=D("0.001"), input_tokens=100, output_tokens=20
        )
    else:
        reserve(ledger)
        if operation == "new_uncertainty":
            ledger.mark_uncertain(slot().request_id, error_code="ProviderRequestFailed")
        else:
            ledger.settle(slot().request_id, cost_usd=D("0.01"), input_tokens=100, output_tokens=20)
    status = ledger.quarantine_scope_status(SCOPE)
    assert not status.active and status.block_reason == expected
    assert ledger.close_quarantine_scope(SCOPE) == status
    with pytest.raises(BudgetDenied):
        reserve(ledger, slot(1))
    assert not ledger.continuation_status("synthetic-old-grant").active
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT status FROM quarantine_scope_events ORDER BY event_id"
        ).fetchall() == [("authorized",), ("revoked",)]


def test_all_outstanding_allowances_are_backed_under_original_global_ceiling(multiple_holds):
    ledger, path, _legacy = multiple_holds
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE ledger_meta SET limit_nanos=50000000")
    authorize(ledger, registered=(slot(),), additional_cap_usd=D("0.02"))
    with pytest.raises(BudgetDenied):
        authorize(
            ledger,
            authorization_id="synthetic-second-scope",
            protocol_sha256="f" * 64,
            registered=(slot(2),),
            additional_cap_usd=D("0.02"),
        )
    ledger.close_quarantine_scope(SCOPE)
    second = authorize(
        ledger,
        authorization_id="synthetic-second-scope",
        protocol_sha256="f" * 64,
        registered=(slot(2),),
        additional_cap_usd=D("0.02"),
    )
    assert second.active


@pytest.mark.parametrize("mutation", ["slot_bounds", "registration", "event"])
def test_corrupt_new_scope_fails_closed_without_private_diagnostics(multiple_holds, mutation):
    ledger, path, _legacy = multiple_holds
    authorize(ledger)
    with sqlite3.connect(path) as connection:
        if mutation == "slot_bounds":
            connection.execute("UPDATE quarantine_scope_slots SET max_output_tokens=4096")
        elif mutation == "registration":
            connection.execute(
                "UPDATE quarantine_scopes SET history_sha256='synthetic-private-corruption'"
            )
        else:
            connection.execute(
                "UPDATE quarantine_scope_events SET reason_code='synthetic-private-corruption'"
            )
    for operation in (
        lambda: ledger.quarantine_scope_status(SCOPE),
        lambda: ledger.close_quarantine_scope(SCOPE),
        lambda: reserve(ledger),
    ):
        with pytest.raises(LedgerUnavailable) as failed:
            operation()
        assert "private-corruption" not in str(failed.value)


def test_existing_gateway_uses_explicit_new_scope_and_preserves_2048_output_bound(multiple_holds):
    ledger, _path, _legacy = multiple_holds
    registered = slot(output=2048)
    authorize(ledger, registered=(registered,))
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "model": "gpt-4o-mini-2024-07-18",
                "usage": {"prompt_tokens": 1000, "completion_tokens": 25, "total_tokens": 1025},
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "synthetic result"},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    config = MetisConfig(
        api_key="synthetic-noncredential",
        live_enabled=True,
        model="gpt-4o-mini",
        continuation_id=SCOPE,
        input_token_reserve=16384,
        max_output_tokens=2048,
    )
    context = ReasoningContext(
        run_id=registered.run_id,
        case_id=registered.case_id,
        case_revision=registered.case_revision,
        attempt_index=registered.attempt,
    )
    with MetisReasoner(config, ledger, transport=httpx.MockTransport(handler)) as reasoner:
        assert (
            reasoner.analyze(
                CaseState(case_id=registered.case_id, case_revision=registered.case_revision),
                "Synthetic current-input experiment",
                EvidenceBundle(snapshot_id="synthetic"),
                context=context,
            )
            == "synthetic result"
        )
        with pytest.raises(ReasoningStopped) as duplicate:
            reasoner.analyze(
                CaseState(case_id=registered.case_id, case_revision=registered.case_revision),
                "Synthetic current-input experiment",
                EvidenceBundle(snapshot_id="synthetic"),
                context=context,
            )
    assert duplicate.value.code == "DuplicateModelRequest"
    assert len(requests) == 1 and requests[0]["max_tokens"] == 2048
    assert ledger.get(registered.request_id).status == "settled" and ledger.snapshot().halted


# Additional controls prompted by independent review; original 45 expectations
# above remain unchanged. These are not another real-model experiment.
@pytest.mark.parametrize("terminal", ["closed", "revoked"])
@pytest.mark.parametrize("mutation", ["delete_event", "alter_event"])
def test_terminal_event_corruption_cannot_reactivate_unused_credit(
    multiple_holds, terminal, mutation
):
    ledger, path, _legacy = multiple_holds
    authorize(ledger)
    if terminal == "closed":
        ledger.close_quarantine_scope(SCOPE)
    else:
        ledger.halt()
    with sqlite3.connect(path) as connection:
        marker = connection.execute(
            "SELECT terminal_status,terminal_reason,terminal_fingerprint FROM quarantine_scopes WHERE authorization_id=?",
            (SCOPE,),
        ).fetchone()
        assert marker[0] == terminal and len(marker[2]) == 64
        if mutation == "delete_event":
            connection.execute(
                "DELETE FROM quarantine_scope_events WHERE status IN ('closed','revoked')"
            )
        else:
            connection.execute(
                "UPDATE quarantine_scope_events SET reason_code='QuarantineChanged' WHERE status IN ('closed','revoked')"
            )
    for operation in (
        lambda: ledger.quarantine_scope_status(SCOPE),
        lambda: ledger.close_quarantine_scope(SCOPE),
        lambda: reserve(ledger),
        lambda: authorize(ledger),
    ):
        with pytest.raises(LedgerUnavailable):
            operation()
    assert ledger.get(slot().request_id) is None
    with sqlite3.connect(path) as connection:
        assert (
            connection.execute(
                "SELECT terminal_status,terminal_reason,terminal_fingerprint FROM quarantine_scopes WHERE authorization_id=?",
                (SCOPE,),
            ).fetchone()
            == marker
        )


@pytest.mark.parametrize("field", ["terminal_status", "terminal_reason", "terminal_fingerprint"])
def test_terminal_marker_is_one_way_and_cannot_be_cleared_or_altered(multiple_holds, field):
    ledger, path, _legacy = multiple_holds
    authorize(ledger)
    closed = ledger.close_quarantine_scope(SCOPE)
    for value in (None, "synthetic-altered-marker"):
        with sqlite3.connect(path) as connection:
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    f"UPDATE quarantine_scopes SET {field}=? WHERE authorization_id=?",
                    (value, SCOPE),
                )
    assert ledger.quarantine_scope_status(SCOPE) == closed
    with pytest.raises(BudgetDenied):
        reserve(ledger)


@pytest.mark.parametrize("replacement", ["absent", "ineffective"])
def test_removed_or_replaced_guard_and_reset_terminal_markers_fail_closed(
    multiple_holds, replacement
):
    ledger, path, _legacy = multiple_holds
    authorize(ledger)
    ledger.close_quarantine_scope(SCOPE)
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TRIGGER quarantine_scope_terminal_immutable")
        if replacement == "ineffective":
            connection.execute(
                "CREATE TRIGGER quarantine_scope_terminal_immutable BEFORE UPDATE OF terminal_status ON quarantine_scopes BEGIN SELECT 1; END"
            )
        connection.execute("DELETE FROM quarantine_scope_events WHERE status='closed'")
        connection.execute(
            "UPDATE quarantine_scopes SET terminal_status=NULL,terminal_reason=NULL,terminal_fingerprint=NULL"
        )
    with pytest.raises(LedgerUnavailable):
        ledger.quarantine_scope_status(SCOPE)
    with pytest.raises(LedgerUnavailable):
        reserve(ledger)
    assert ledger.get(slot().request_id) is None


@pytest.mark.parametrize("event", ["reserved", "uncertain"])
def test_quarantined_reservation_audit_changes_invalidate_frozen_observation(multiple_holds, event):
    ledger, path, _legacy = multiple_holds
    observed = ledger.quarantine_observation()
    authorize(ledger)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE ledger_events SET recorded_at='synthetic-altered-history' WHERE request_id='synthetic-original-mismatch' AND status=?",
            (event,),
        )
    after = ledger.quarantine_observation()
    assert after.unknown_ids == observed.unknown_ids
    assert after.unknown_fingerprints == observed.unknown_fingerprints
    assert after.authorization_history_sha256 != observed.authorization_history_sha256
    assert ledger.quarantine_scope_status(SCOPE).block_reason == "AuthorizationHistoryChanged"
    with pytest.raises(BudgetDenied):
        reserve(ledger)
    with pytest.raises(BudgetDenied):
        authorize(
            ledger,
            authorization_id="synthetic-another-scope",
            protocol_sha256="e" * 64,
            registered=(slot(2),),
            observation=observed,
        )


def test_terminal_marker_write_failure_rolls_back_terminal_event_atomically(multiple_holds):
    ledger, path, _legacy = multiple_holds
    original = authorize(ledger)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TRIGGER synthetic_marker_write_failure BEFORE UPDATE OF terminal_status ON quarantine_scopes BEGIN SELECT RAISE(ABORT,'synthetic-failure'); END"
        )
    with pytest.raises(LedgerUnavailable):
        ledger.close_quarantine_scope(SCOPE)
    assert ledger.quarantine_scope_status(SCOPE) == original
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT status FROM quarantine_scope_events ORDER BY event_id"
        ).fetchall() == [("authorized",)]
        assert connection.execute(
            "SELECT terminal_status,terminal_reason,terminal_fingerprint FROM quarantine_scopes"
        ).fetchone() == (None, None, None)


def test_terminal_registration_cannot_be_deleted_after_removing_child_audits(multiple_holds):
    ledger, path, _legacy = multiple_holds
    authorize(ledger)
    closed = ledger.close_quarantine_scope(SCOPE)
    with pytest.raises(sqlite3.IntegrityError):
        with sqlite3.connect(path) as connection:
            connection.execute("DELETE FROM quarantine_scope_events")
            connection.execute("DELETE FROM quarantine_scope_slots")
            connection.execute("DELETE FROM quarantine_scopes")
    assert ledger.quarantine_scope_status(SCOPE) == closed
    with pytest.raises(BudgetDenied):
        reserve(ledger)


def test_missing_registration_guard_cannot_recreate_deleted_closed_credit(multiple_holds):
    ledger, path, _legacy = multiple_holds
    authorize(ledger)
    ledger.close_quarantine_scope(SCOPE)
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TRIGGER quarantine_scope_registration_undeletable")
        connection.execute("DELETE FROM quarantine_scope_events")
        connection.execute("DELETE FROM quarantine_scope_slots")
        connection.execute("DELETE FROM quarantine_scopes")
    with pytest.raises(LedgerUnavailable):
        authorize(ledger)
    assert ledger.get(slot().request_id) is None
