"""Pre-send accounting is narrow; no provider, key or designated ledger used."""

import json
from copy import deepcopy
from decimal import Decimal

import httpx
import pytest
from test_budget_quarantine_scope import (
    SCOPE,
    authorize,
    reserve,
    slot,
)
from test_budget_quarantine_scope import (
    multiple_holds as multiple_holds,
)

from agent_app.contracts import CaseState, EvidenceBundle, EvidenceHit, Fact, ReasoningContext
from agent_app.evaluation.runner import Usage
from agent_app.llm.config import MetisConfig
from agent_app.llm.grounded import MetisGroundedPlanner
from agent_app.llm.metis import request_id_for
from agent_app.llm.pricing import get_price
from agent_app.orchestration.ports import ReasoningStopped
from agent_app.reasoning.grounding import make_grounded_request
from agent_app.testing.dev_three_model_probe import SharedTransport, ledger_observation
from agent_app.testing.pre_dispatch_usage import PreDispatchUsage, attest_pre_dispatch_stop
from agent_app.testing.quality_probe import QualityPlanner, QualityTransport


def context_for(registered):
    return ReasoningContext(
        run_id=registered.run_id,
        case_id=registered.case_id,
        case_revision=registered.case_revision,
        attempt_index=registered.attempt,
    )


def fixture_gateway(multiple_holds, handler, *, oversized=True):
    ledger, _path, _ = multiple_holds
    authorize(ledger)
    context = context_for(slot())
    facts = (
        (Fact(name="supplied_code", value="x" * 18_000, source_ref="user", turn_id="initial"),)
        if oversized
        else ()
    )
    case = CaseState(case_id=context.case_id, case_revision=context.case_revision, facts=facts)
    request = make_grounded_request(
        case,
        "A local synthetic support problem.",
        EvidenceBundle(snapshot_id="synthetic-empty", hits=(), queries_used=(), retrieval_round=1),
    )
    config = MetisConfig(
        api_key="synthetic-private-no-real-key",
        live_enabled=True,
        response_mode="grounded_plan",
        continuation_id=SCOPE,
        grounded_source_gap_handoff=True,
        input_token_reserve=16384,
        max_output_tokens=1024,
        max_request_usd=get_price("gpt-4o-mini").cost(16384, 1024),
    )
    counted = QualityTransport(
        httpx.MockTransport(handler),
        ledger,
        SCOPE,
        ledger_observation(ledger._path),
        input_profiles={context.case_id: 16384},
    )
    gateway = MetisGroundedPlanner(config, ledger, transport=SharedTransport(counted))
    records = []
    return (
        ledger,
        context,
        request,
        gateway,
        counted,
        records,
        QualityPlanner(gateway, counted, records),
    )


def oversized_stop(multiple_holds):
    sent = []

    def forbidden(request):
        sent.append(request)
        raise AssertionError("No HTTP should be invoked")

    values = fixture_gateway(multiple_holds, forbidden)
    ledger, context, request, gateway, counted, records, planner = values
    with pytest.raises(ReasoningStopped, match="ContextLimitExceeded"):
        planner.plan(request, context=context)
    assert sent == [] and counted.records == []
    return values


def test_actual_oversized_gateway_zero_send_zero_reservation_is_complete(multiple_holds):
    ledger, context, _request, gateway, counted, records, _planner = oversized_stop(multiple_holds)
    before = ledger_observation(ledger._path)
    try:
        assert records[0]["error_code"] == "ContextLimitExceeded"
        assert records[0]["pre_dispatch_stop"]["request_id"] == request_id_for(context)
        assert ledger.get(request_id_for(context)) is None
        result = PreDispatchUsage(ledger, records, counted.records).measure([context])
        assert result["accounting_complete"] is True
        assert result["cost_usd"] == result["settled_usd"] == "0"
        assert result["input_tokens"] == result["output_tokens"] == 0
        assert result["requests"][0]["status"] == "skipped_before_reservation"
        assert result["requests"][0]["error_code"] == "ContextLimitExceeded"
        assert ledger_observation(ledger._path) == before
        assert ledger.quarantine_scope_status(SCOPE).consumed_requests == 0
        assert ledger.snapshot().halted
        assert Usage(ledger).measure([context])["accounting_complete"] is False
    finally:
        gateway.close()
        counted.close()


@pytest.mark.parametrize("marker", [False, True])
def test_any_matching_transport_record_including_unsent_marker_prevents_zero(
    multiple_holds, marker
):
    ledger, context, _request, gateway, counted, records, _ = oversized_stop(multiple_holds)
    try:
        counted.records.append({"request_id": request_id_for(context), "http_send_started": marker})
        ordinary = Usage(ledger).measure([context])
        assert PreDispatchUsage(ledger, records, counted.records).measure([context]) == ordinary
        assert ordinary["cost_usd"] is None and not ordinary["accounting_complete"]
        assert (
            attest_pre_dispatch_stop(
                gateway,
                counted,
                context,
                ReasoningStopped("ContextLimitExceeded"),
                ledger_absent_before=True,
                transport_absent_before=True,
            )
            is None
        )
    finally:
        gateway.close()


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_attestation",
        "unknown_code",
        "false_before",
        "false_after",
        "context_hash",
        "wrong_id",
        "extra_field",
        "string_version",
        "gateway_kind",
        "missing_attempt",
    ],
)
def test_unattested_or_inconsistent_absence_never_becomes_free(multiple_holds, mutation):
    ledger, context, _request, gateway, counted, records, _ = oversized_stop(multiple_holds)
    try:
        mutated = deepcopy(records)
        attestation = mutated[0]["pre_dispatch_stop"]
        if mutation == "missing_attestation":
            mutated[0].pop("pre_dispatch_stop")
        elif mutation == "unknown_code":
            mutated[0]["error_code"] = "ProviderUsageUnknown"
        elif mutation == "false_before":
            attestation["ledger_absent_before"] = False
        elif mutation == "false_after":
            attestation["transport_absent_after"] = False
        elif mutation == "context_hash":
            attestation["context_sha256"] = "0" * 64
        elif mutation == "wrong_id":
            attestation["request_id"] = "different"
        elif mutation == "extra_field":
            attestation["SECRET-FIELD"] = "SECRET-VALUE"
        elif mutation == "string_version":
            attestation["schema_version"] = "1"
        elif mutation == "gateway_kind":
            attestation["gateway_kind"] = "ScriptedPlanner"
        else:
            mutated = []
        assert PreDispatchUsage(ledger, mutated, counted.records).measure([context]) == Usage(
            ledger
        ).measure([context])
    finally:
        gateway.close()


@pytest.mark.parametrize("status", ["reserved", "uncertain", "settled", "released"])
def test_existing_ledger_row_is_never_zeroed_by_claimed_pre_send_attestation(
    multiple_holds, status
):
    ledger, context, _request, gateway, counted, records, _ = oversized_stop(multiple_holds)
    try:
        reserve(ledger)
        request_id = request_id_for(context)
        if status == "uncertain":
            ledger.mark_uncertain(request_id, error_code="ProviderUsageUnknown")
        elif status == "settled":
            ledger.settle(
                request_id, cost_usd=Decimal("0.000020"), input_tokens=10, output_tokens=20
            )
        elif status == "released":
            ledger.release_unsent(request_id, error_code="ProviderRequestFailed")
        assert PreDispatchUsage(ledger, records, counted.records).measure([context]) == Usage(
            ledger
        ).measure([context])
        assert ledger.get(request_id).status == status
    finally:
        gateway.close()


def test_zero_skip_mixed_with_actual_settled_usage_preserves_true_cost_and_tokens(multiple_holds):
    ledger, context, _request, gateway, counted, records, _ = oversized_stop(multiple_holds)
    try:
        other = slot(1)
        reserve(ledger, other)
        ledger.settle(
            other.request_id, cost_usd=Decimal("0.000050"), input_tokens=100, output_tokens=20
        )
        counted.records.append({"request_id": other.request_id, "http_send_started": True})
        result = PreDispatchUsage(ledger, records, counted.records).measure(
            [context, context_for(other)]
        )
        assert result["accounting_complete"] is True
        assert Decimal(result["cost_usd"]) == Decimal(result["settled_usd"]) == Decimal("0.000050")
        assert result["input_tokens"] == 100 and result["output_tokens"] == 20
        assert [row["status"] for row in result["requests"]] == [
            "skipped_before_reservation",
            "settled",
        ]
    finally:
        gateway.close()


def test_zero_skip_cannot_mask_new_uncertain_hold(multiple_holds):
    ledger, context, _request, gateway, counted, records, _ = oversized_stop(multiple_holds)
    try:
        other = slot(1)
        reserve(ledger, other)
        ledger.mark_uncertain(other.request_id, error_code="ProviderRequestFailed")
        result = PreDispatchUsage(ledger, records, counted.records).measure(
            [context, context_for(other)]
        )
        assert result["cost_usd"] is None and not result["accounting_complete"]
        assert Decimal(result["uncertain_usd"]) == other.amount_usd
        assert result["requests"][1]["status"] == "uncertain"
        assert ledger.get(other.request_id).amount_usd == other.amount_usd
    finally:
        gateway.close()


def test_duplicate_context_attestations_are_not_accepted(multiple_holds):
    ledger, context, _request, gateway, counted, records, _ = oversized_stop(multiple_holds)
    try:
        assert PreDispatchUsage(ledger, records + records, []).measure([context]) == Usage(
            ledger
        ).measure([context])
        assert PreDispatchUsage(
            ledger, [{"context": {"SECRET-FIELD": "SECRET-VALUE"}}], []
        ).measure([context]) == Usage(ledger).measure([context])
    finally:
        gateway.close()


@pytest.mark.parametrize("marker", [None, {}, {"request_id": None}, {"request_id": ""}])
def test_malformed_transport_evidence_cannot_attest_absence(multiple_holds, marker):
    ledger, context, _request, gateway, _counted, records, _ = oversized_stop(multiple_holds)
    try:
        assert PreDispatchUsage(ledger, records, [marker]).measure([context]) == Usage(
            ledger
        ).measure([context])
    finally:
        gateway.close()


def test_normal_actual_send_usage_and_attempt_bytes_stay_unchanged(multiple_holds):
    sent = []

    def success(request):
        sent.append(request)
        content = json.dumps(
            {
                "decision": "escalate",
                "context_sha256": "a" * 64,
                "sources": [],
                "question_name": None,
                "retrieval_queries": [],
            }
        )
        return httpx.Response(
            200,
            json={
                "model": "gpt-4o-mini-2024-07-18",
                "usage": {"prompt_tokens": 100, "completion_tokens": 20},
                "choices": [
                    {"finish_reason": "stop", "message": {"role": "assistant", "content": content}}
                ],
            },
        )

    ledger, context, request, gateway, counted, records, planner = fixture_gateway(
        multiple_holds, success, oversized=False
    )
    try:
        planner.plan(request, context=context)
        assert len(sent) == 1
        assert "pre_dispatch_stop" not in records[0]
        assert PreDispatchUsage(ledger, records, counted.records).measure([context]) == Usage(
            ledger
        ).measure([context])
        assert ledger.get(request_id_for(context)).status == "settled"
    finally:
        gateway.close()


def test_cancel_after_reserve_with_false_send_marker_keeps_real_unknown_hold(multiple_holds):
    sent = []

    def forbidden(request):
        sent.append(request)
        raise AssertionError("on_send cancels before underlying wire")

    ledger, context, request, gateway, counted, records, planner = fixture_gateway(
        multiple_holds, forbidden, oversized=False
    )

    def cancel():
        raise ReasoningStopped("ContextLimitExceeded")

    counted.on_send = cancel
    try:
        with pytest.raises(ReasoningStopped, match="ProviderRequestFailed"):
            planner.plan(request, context=context)
        assert sent == []
        assert counted.records[0]["http_send_started"] is False
        assert "pre_dispatch_stop" not in records[0]
        assert ledger.get(request_id_for(context)).status == "uncertain"
        result = PreDispatchUsage(ledger, records, counted.records).measure([context])
        assert not result["accounting_complete"] and result["cost_usd"] is None
        assert Decimal(result["uncertain_usd"]) == slot().amount_usd
    finally:
        gateway.close()


def test_before_observations_and_gateway_identity_are_required(multiple_holds):
    ledger, context, _request, gateway, counted, _records, _ = oversized_stop(multiple_holds)
    try:
        error = ReasoningStopped("ContextLimitExceeded")
        assert (
            attest_pre_dispatch_stop(
                gateway,
                counted,
                context,
                error,
                ledger_absent_before=False,
                transport_absent_before=True,
            )
            is None
        )
        assert (
            attest_pre_dispatch_stop(
                gateway,
                counted,
                context,
                error,
                ledger_absent_before=True,
                transport_absent_before=False,
            )
            is None
        )
        assert (
            attest_pre_dispatch_stop(
                object(),
                counted,
                context,
                error,
                ledger_absent_before=True,
                transport_absent_before=True,
            )
            is None
        )
        assert (
            attest_pre_dispatch_stop(
                gateway,
                counted,
                context,
                ReasoningStopped("ProviderUsageUnknown"),
                ledger_absent_before=True,
                transport_absent_before=True,
            )
            is None
        )
    finally:
        gateway.close()


def test_real_conditional_http_batch_accounts_free_stops_but_does_not_claim_route_success(
    multiple_holds,
):
    from pathlib import Path

    from test_quality_probe import prepare

    from agent_app.reasoning.catalog import load_user_gap_vocabulary
    from agent_app.testing.fakes import FakeRetriever
    from agent_app.testing.quality_probe import run_quality_batch
    from agent_app.testing.stability_probe import VOCABULARY

    ledger, protocol, batch, fixtures, config = prepare(multiple_holds)
    bundle = EvidenceBundle(
        snapshot_id="synthetic-oversized-test-only",
        hits=(
            EvidenceHit(
                chunk_id="synthetic-oversized-doc",
                source_id="synthetic-doc",
                excerpt="x" * 19_000,
                source_url="https://example.test/synthetic",
                source_type="doc",
            ),
        ),
    )
    sent = []

    def forbidden(request):
        sent.append(request)
        raise AssertionError("pre-dispatch guard must stop both planned jobs")

    def retriever_factory(_job, _turn):
        return FakeRetriever([bundle, bundle]), bundle.snapshot_id

    before = ledger_observation(ledger._path)
    result = run_quality_batch(
        protocol,
        batch,
        fixtures,
        load_user_gap_vocabulary(str(Path(__file__).resolve().parents[1] / VOCABULARY)),
        ledger,
        config,
        before,
        underlying=httpx.MockTransport(forbidden),
        retriever_factory=retriever_factory,
    )
    assert sent == [] and result["provider_sends"] == [] and result["actual_sends"] == 0
    assert result["visited_jobs"] == 2 and result["completed_routes"] == 0
    assert result["accounting"]["accounting_complete"] is True
    assert result["accounting"]["cost_usd"] == "0"
    assert all(attempt["error_code"] == "ContextLimitExceeded" for attempt in result["attempts"])
    assert all(
        row["status"] == "skipped_before_reservation" for row in result["accounting"]["requests"]
    )
    turn_usage = [
        step["usage"] for job in result["jobs"] for step in job["steps"] if "usage" in step
    ]
    assert len(turn_usage) == 2 and all(usage["accounting_complete"] for usage in turn_usage)
    assert ledger_observation(ledger._path) == before
