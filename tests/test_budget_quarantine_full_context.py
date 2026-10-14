"""A newly registered full-input tier never expands historical scopes or credit.

Disposable synthetic ledgers, existing synthetic multiple-hold fixtures and
mocked provider transports only. No team ledger, real credential or paid call.
"""

import json
import sqlite3
from dataclasses import replace
from decimal import Decimal

import httpx
import pytest
from test_budget_quarantine_scope import SCOPE, old_rows, reserve, slot
from test_budget_quarantine_scope import authorize as authorize_historical
from test_budget_quarantine_scope import multiple_holds as multiple_holds

from agent_app.contracts import CaseState, EvidenceBundle, EvidenceHit, ReasoningContext
from agent_app.llm.budget import BudgetDenied, BudgetLedger, LedgerConflict
from agent_app.llm.config import MetisConfig
from agent_app.llm.metis import MetisReasoner
from agent_app.llm.pricing import get_price
from agent_app.orchestration.ports import ReasoningStopped

D = Decimal


def authorize(ledger, **changes):
    return authorize_historical(ledger, **({"allow_full_context": True} | changes))


def full_slot(index=0, *, output=1024):
    return slot(index + 200, input_limit=32768, output=output)


@pytest.mark.parametrize(
    "output,expected_bound", [(1024, D("0.006082560")), (2048, D("0.006758400"))]
)
def test_new_quarantine_tier_reopens_reserves_and_settles_exact_bound(
    multiple_holds, output, expected_bound
):
    ledger, path, _ = multiple_holds
    before = old_rows(path)
    observed = ledger.quarantine_observation()
    registered = full_slot(output=output)
    assert registered.amount_usd == expected_bound
    status = authorize(ledger, registered=(registered,))
    assert status.active and status.max_requests == 1
    reopened = BudgetLedger(path)
    assert reopened.quarantine_scope_status(SCOPE) == status
    reserve(reopened, registered)
    assert reopened.get(registered.request_id).amount_usd == expected_bound
    assert reopened.snapshot().reserved_usd == expected_bound
    cost = get_price("gpt-4o-mini").cost(28000, 20)
    reopened.settle(registered.request_id, cost_usd=cost, input_tokens=28000, output_tokens=20)
    final = reopened.quarantine_scope_status(SCOPE)
    assert final.consumed_requests == 1 and final.used_usd == cost
    assert final.remaining_usd == D("0.10") - cost
    assert reopened.get(registered.request_id).status == "settled"
    assert reopened.snapshot().halted and reopened.snapshot().limit_usd == D("4.50")
    assert reopened.quarantine_observation() == observed
    assert old_rows(path) == before


@pytest.mark.parametrize("input_limit", [32767, 32769, 65536, 32768.0, True, False])
def test_nonregistered_or_nonstrict_input_tiers_are_rejected_before_funding(
    multiple_holds, input_limit
):
    ledger, path, _ = multiple_holds
    before = old_rows(path)
    registered = replace(full_slot(), input_token_reserve=input_limit)
    with pytest.raises(ValueError, match=r"^Invalid experiment request bounds\.$"):
        authorize(ledger, registered=(registered,))
    assert old_rows(path) == before
    with sqlite3.connect(path) as connection:
        assert (
            connection.execute(
                "SELECT 1 FROM sqlite_master WHERE name='quarantine_scopes'"
            ).fetchone()
            is None
        )


@pytest.mark.parametrize("amount", [D("0.006082559"), D("0.006082561"), D("0.004730880")])
def test_full_input_tier_keeps_exact_model_price_bound(multiple_holds, amount):
    ledger, _, _ = multiple_holds
    with pytest.raises(ValueError, match=r"^Invalid experiment request bounds\.$"):
        authorize(ledger, registered=(replace(full_slot(), amount_usd=amount),))


@pytest.mark.parametrize(
    "changes",
    [
        {"model": "gpt-4.1-mini"},
        {"phase": "evaluation"},
        {"max_output_tokens": 4096},
        {"max_output_tokens": 1024.0},
        {"max_output_tokens": True},
    ],
)
def test_new_tier_does_not_change_other_registered_constraints(multiple_holds, changes):
    ledger, _, _ = multiple_holds
    with pytest.raises(ValueError):
        authorize(ledger, registered=(replace(full_slot(), **changes),))


@pytest.mark.parametrize(
    "changes",
    [
        {"input_token_reserve": 24576},
        {"input_token_reserve": 32768.0},
        {"amount_usd": D("0.004730880")},
        {"max_output_tokens": 2048},
    ],
)
def test_full_input_slot_cannot_be_reserved_under_different_runtime_bounds(multiple_holds, changes):
    ledger, _, _ = multiple_holds
    registered = full_slot()
    authorized = authorize(ledger, registered=(registered,))
    with pytest.raises(BudgetDenied):
        reserve(ledger, registered, **changes)
    assert ledger.quarantine_scope_status(SCOPE) == authorized
    assert ledger.get(registered.request_id) is None


def _context(registered):
    return ReasoningContext(
        run_id=registered.run_id,
        case_id=registered.case_id,
        case_revision=registered.case_revision,
        attempt_index=registered.attempt,
    )


@pytest.mark.parametrize("runtime_input,runtime_output", [(24576, 1024), (32768, 2048)])
def test_gateway_mismatch_cannot_reach_transport_or_consume_slot(
    multiple_holds, runtime_input, runtime_output
):
    ledger, _, _ = multiple_holds
    registered = full_slot()
    status = authorize(ledger, registered=(registered,))
    requests = []

    def forbidden(request):
        requests.append(request)
        raise AssertionError("UnregisteredBoundMustNotReachTransport")

    config = MetisConfig(
        api_key="synthetic-not-a-provider-key",
        live_enabled=True,
        continuation_id=SCOPE,
        input_token_reserve=runtime_input,
        max_output_tokens=runtime_output,
    )
    with MetisReasoner(config, ledger, transport=httpx.MockTransport(forbidden)) as reasoner:
        with pytest.raises(ReasoningStopped) as stopped:
            reasoner.analyze(
                CaseState(case_id=registered.case_id, case_revision=registered.case_revision),
                "Synthetic bound mismatch",
                EvidenceBundle(snapshot_id="synthetic"),
                context=_context(registered),
            )
    assert stopped.value.code == "BudgetExceeded"
    assert requests == []
    assert ledger.quarantine_scope_status(SCOPE) == status
    assert ledger.get(registered.request_id) is None


@pytest.mark.parametrize("output", [1024, 2048])
def test_mocked_gateway_preserves_full_input_and_settles_new_tier(multiple_holds, output):
    ledger, path, _ = multiple_holds
    before = old_rows(path)
    registered = full_slot(output=output)
    authorize(ledger, registered=(registered,))
    full_text = "Synthetic user payload: " + "x" * 7000
    source_text = "Synthetic full source: " + "y" * 14000
    evidence = EvidenceBundle(
        snapshot_id="synthetic",
        hits=(
            EvidenceHit(
                chunk_id="synthetic-chunk",
                source_id="synthetic-source",
                excerpt=source_text,
                source_url="https://example.invalid/synthetic",
                source_type="doc",
            ),
        ),
    )
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "model": "gpt-4o-mini-2024-07-18",
                "usage": {"prompt_tokens": 28000, "completion_tokens": 20, "total_tokens": 28020},
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "synthetic result"},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    config = MetisConfig(
        api_key="synthetic-not-a-provider-key",
        live_enabled=True,
        continuation_id=SCOPE,
        input_token_reserve=32768,
        max_output_tokens=output,
    )
    with MetisReasoner(config, ledger, transport=httpx.MockTransport(handler)) as reasoner:
        assert (
            reasoner.analyze(
                CaseState(case_id=registered.case_id, case_revision=registered.case_revision),
                full_text,
                evidence,
                context=_context(registered),
            )
            == "synthetic result"
        )
    assert len(requests) == 1 and requests[0]["max_tokens"] == output
    assert full_text in requests[0]["messages"][-1]["content"]
    assert source_text in requests[0]["messages"][-1]["content"]
    actual_guard = (
        len(json.dumps(requests[0]["messages"], ensure_ascii=False).encode("utf-8")) + 1024
    )
    assert 24576 < actual_guard <= 32768
    row = ledger.get(registered.request_id)
    assert row.status == "settled" and row.input_tokens == 28000
    assert row.amount_usd == registered.amount_usd
    assert row.cost_usd == get_price("gpt-4o-mini").cost(28000, 20)
    assert old_rows(path) == before


def test_historical_experiment_still_rejects_exact_full_input_slot(multiple_holds):
    ledger, path, _ = multiple_holds
    before = old_rows(path)
    with pytest.raises(ValueError, match=r"^Invalid experiment request bounds\.$"):
        ledger.authorize_experiment_scope(
            authorization_id="synthetic-old-api-full-input",
            authorization_ref="synthetic-user",
            parent_authorization_id="synthetic-old-grant",
            protocol_sha256="f" * 64,
            request_slots=(full_slot(),),
            additional_cap_usd=D("0.10"),
        )
    assert old_rows(path) == before


def test_full_context_closed_scope_cannot_refill_or_recycle_unused_identity(multiple_holds):
    ledger, path, _ = multiple_holds
    before = old_rows(path)
    registered = (full_slot(), full_slot(1))
    authorize(ledger, registered=registered)
    reserve(ledger, registered[0])
    ledger.settle(registered[0].request_id, cost_usd=D("0.001"), input_tokens=100, output_tokens=20)
    closed = ledger.close_quarantine_scope(SCOPE)
    assert not closed.active and closed.block_reason == "ExperimentClosed"
    assert closed.consumed_requests == 1
    reopened = BudgetLedger(path)
    assert authorize(reopened, registered=registered) == closed
    assert reopened.close_quarantine_scope(SCOPE) == closed
    with pytest.raises(BudgetDenied):
        reserve(reopened, registered[1])
    with pytest.raises(LedgerConflict):
        reserve(reopened, registered[0])
    with pytest.raises(LedgerConflict):
        authorize(
            reopened,
            registered=registered,
            authorization_id="synthetic-full-input-refill",
            protocol_sha256="f" * 64,
        )
    with pytest.raises(LedgerConflict):
        authorize(reopened, registered=registered, additional_cap_usd=D("0.09"))
    assert old_rows(path) == before


def test_full_context_new_uncertainty_permanently_revokes_other_registered_slot(multiple_holds):
    ledger, path, _ = multiple_holds
    before = old_rows(path)
    registered = (full_slot(), full_slot(1))
    authorize(ledger, registered=registered)
    reserve(ledger, registered[0])
    ledger.mark_uncertain(registered[0].request_id, error_code="ProviderRequestFailed")
    revoked = ledger.quarantine_scope_status(SCOPE)
    assert not revoked.active and revoked.block_reason == "NewUncertainty"
    assert ledger.close_quarantine_scope(SCOPE) == revoked
    with pytest.raises(BudgetDenied):
        reserve(ledger, registered[1])
    assert old_rows(path) == before


@pytest.mark.parametrize("kind", ["too-many-slots", "request-bound-over-cap", "cap-expanded"])
def test_full_input_tier_never_expands_request_count_or_scope_cap(multiple_holds, kind):
    ledger, path, _ = multiple_holds
    before = old_rows(path)
    slots = tuple(
        full_slot(i)
        for i in range(
            25 if kind == "too-many-slots" else 17 if kind == "request-bound-over-cap" else 1
        )
    )
    with pytest.raises(ValueError):
        authorize(
            ledger,
            registered=slots,
            additional_cap_usd=D("0.11") if kind == "cap-expanded" else D("0.10"),
        )
    assert old_rows(path) == before


def test_full_context_permission_is_still_backed_by_original_global_ceiling(multiple_holds):
    ledger, path, _ = multiple_holds
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE ledger_meta SET opening_nanos=4430000000")
    before = old_rows(path)
    with pytest.raises(BudgetDenied):
        authorize(ledger, registered=(full_slot(),), additional_cap_usd=D("0.06"))
    assert ledger.snapshot().limit_usd == D("4.50")
    assert ledger.snapshot().halted
    assert old_rows(path) == before


def test_quarantine_database_schema_and_row_shape_do_not_change(multiple_holds):
    ledger, path, _ = multiple_holds
    authorize_historical(ledger, registered=(slot(),))
    with sqlite3.connect(path) as connection:
        before = connection.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name"
        ).fetchall()
    authorize(
        ledger,
        registered=(full_slot(),),
        authorization_id="synthetic-full-input-new-scope",
        protocol_sha256="e" * 64,
    )
    with sqlite3.connect(path) as connection:
        after = connection.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name"
        ).fetchall()
    assert before == after
    assert ledger.snapshot().limit_usd == D("4.50") and ledger.snapshot().halted


def test_default_quarantine_authorization_still_rejects_full_context_tier(multiple_holds):
    ledger, path, _ = multiple_holds
    before = old_rows(path)
    with pytest.raises(ValueError, match="^Invalid experiment request bounds\\.$"):
        authorize_historical(ledger, registered=(full_slot(),))
    assert old_rows(path) == before


@pytest.mark.parametrize("flag", [1, 0, "true", None])
def test_full_context_authorization_requires_strict_explicit_boolean(multiple_holds, flag):
    ledger, path, _ = multiple_holds
    before = old_rows(path)
    with pytest.raises(ValueError, match="^Invalid full-context authorization flag\\.$"):
        authorize(ledger, registered=(full_slot(),), allow_full_context=flag)
    assert old_rows(path) == before


def test_opt_in_marker_is_canonical_and_default_binding_bytes_stay_unchanged(multiple_holds):
    ledger, path, _ = multiple_holds
    observed = ledger.quarantine_observation()
    authorize_historical(ledger, registered=(slot(),))
    authorize(
        ledger,
        registered=(full_slot(),),
        authorization_id="synthetic-full-input-new-scope",
        protocol_sha256="e" * 64,
    )
    old_expected = json.dumps(
        {"ids": observed.unknown_ids, "fingerprints": observed.unknown_fingerprints},
        sort_keys=True,
        separators=(",", ":"),
    )
    new_expected = json.dumps(
        {
            "ids": observed.unknown_ids,
            "fingerprints": observed.unknown_fingerprints,
            "full_context": True,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    with sqlite3.connect(path) as connection:
        rows = dict(
            connection.execute("SELECT authorization_id,unknown_binding FROM quarantine_scopes")
        )
    assert rows[SCOPE] == old_expected
    assert rows["synthetic-full-input-new-scope"] == new_expected


def test_flag_cannot_be_changed_on_an_existing_registered_scope(multiple_holds):
    ledger, _, _ = multiple_holds
    original = authorize(ledger, registered=(slot(),))
    # Same IDs/protocol with a changed permission marker is a conflicting replay.
    with pytest.raises(LedgerConflict):
        authorize(ledger, registered=(slot(),), allow_full_context=False)
    assert ledger.quarantine_scope_status(SCOPE) == original


@pytest.mark.parametrize("marker", [False, "true", 1, None, "remove", "extra-key"])
def test_corrupted_opt_in_marker_cannot_relax_persisted_scope_read(multiple_holds, marker):
    from agent_app.llm.budget import LedgerUnavailable, _digest

    ledger, path, _ = multiple_holds
    authorize(ledger, registered=(full_slot(),))
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        row = dict(
            connection.execute(
                "SELECT * FROM quarantine_scopes WHERE authorization_id=?", (SCOPE,)
            ).fetchone()
        )
        binding = json.loads(row["unknown_binding"])
        if marker == "remove":
            binding.pop("full_context")
        elif marker == "extra-key":
            binding["unregistered_permission"] = True
        else:
            binding["full_context"] = marker
        row["unknown_binding"] = json.dumps(binding, sort_keys=True, separators=(",", ":"))
        # Even a self-rehashed accidental/forged row must pass the closed shape
        # and its exact stored input tier. A fingerprint alone is not permission.
        registered = {
            key: value
            for key, value in row.items()
            if key
            not in {
                "recorded_at",
                "registration_fingerprint",
                "terminal_status",
                "terminal_reason",
                "terminal_fingerprint",
            }
        }
        connection.execute(
            "UPDATE quarantine_scopes SET unknown_binding=?,registration_fingerprint=? WHERE authorization_id=?",
            (row["unknown_binding"], _digest(registered), SCOPE),
        )
    with pytest.raises(LedgerUnavailable):
        ledger.quarantine_scope_status(SCOPE)
