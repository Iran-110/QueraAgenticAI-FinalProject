"""Actual execution reporting must retain safe diagnostics and reject unknown text."""

import json
from copy import deepcopy
from decimal import Decimal

import pytest
from test_core_delivery import actual

from agent_app.contracts import CaseState, EvidenceBundle, ReasoningContext
from agent_app.evaluation.runner import _provider_observations
from agent_app.llm.budget import BudgetLedger
from agent_app.llm.metis import request_id_for
from agent_app.orchestration.core_delivery import (
    validate_delivery_configuration,
    validated_delivery_binding,
)
from agent_app.reasoning.catalog import runtime_catalog
from agent_app.reasoning.compact_plan import observe_compact_plan


def neutral_observation():
    context = ReasoningContext(
        run_id="metadata-run", case_id="metadata-case", case_revision=0, attempt_index=1
    )
    request = runtime_catalog(
        CaseState(case_id=context.case_id), "Neutral report", EvidenceBundle(snapshot_id="neutral")
    )
    row = {
        "request_id": request_id_for(context),
        "run_id": context.run_id,
        "case_id": context.case_id,
        "case_revision": 0,
        "attempt_index": 1,
        "prompt_sha256": "a" * 64,
        "requested_model": "gpt-4o-mini",
        "verified_returned_model": None,
        "http_send_started": False,
        "http_status": None,
        "ledger_status": None,
        "input_tokens": None,
        "output_tokens": None,
        "cost_estimated_usd": None,
        "held_usd": None,
        "error_code": None,
    }
    raw = json.dumps(
        {
            "context_sha256": request.context_sha256,
            "decision": "ask",
            "sources": [],
            "question_name": "streamlit_version",
        }
    )
    wire = {"request_id": row["request_id"], **observe_compact_plan(raw, request)}
    binding = validate_delivery_configuration(**actual())
    return context, row, wire, binding


@pytest.mark.parametrize("extras", ["none", "wire", "binding", "both", "no_wire_output"])
def test_optional_projection_retains_exact_safe_metadata_and_legacy_order(extras):
    context, row, wire, binding = neutral_observation()
    if extras in {"wire", "both"}:
        row["wire_output"] = wire
    if extras in {"binding", "both"}:
        row["core_binding"] = binding
    if extras == "no_wire_output":
        row["wire_output"] = None
    projected, error = _provider_observations(lambda contexts: [row], [context], None)
    assert error is None and projected == [row]
    if extras == "none":
        assert json.dumps(projected[0]) == json.dumps(row)
    if extras == "both":
        projected[0]["wire_output"]["selected_indexes"].append(3)
        projected[0]["core_binding"]["observed_metis"]["model"] = "changed"
        assert row["wire_output"]["selected_indexes"] == []
        assert row["core_binding"]["observed_metis"]["model"] == "gpt-4o-mini"


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("private-field", "private-value"),
        ("request_id", "other-request"),
        ("schema_version", True),
        ("wire_format", "private-value"),
        ("raw_output_sha256", "private-value"),
        ("raw_utf8_bytes", True),
        ("json_shape", "private-value"),
        ("decision", "private-value"),
        ("sources_count", -1),
        ("selected_indexes", [True]),
        ("selected_indexes", [100]),
        ("selected_indexes", [0] * 9),
        ("wire_schema_valid", 1),
        ("canonical_binding_valid", 1),
        ("rejection_code", "private-value"),
        ("unexpected_field_count", -1),
        ("json_shape", "invalid"),
        ("decision", None),
        ("raw_output_sha256", None),
        ("raw_utf8_bytes", None),
        ("unexpected_field_count", 1),
        ("sources_count", 1),
        ("selected_indexes", [1, 1]),
        ("decision", "answer"),
    ],
)
def test_bad_wire_metadata_is_rejected_without_exporting_private_fields(key, value):
    context, row, wire, binding = neutral_observation()
    wire[key] = value
    row.update(wire_output=wire, core_binding=binding)
    projected, error = _provider_observations(lambda contexts: [row], [context], None)
    assert projected == [] and error == "ProviderObservationsUnavailable"
    assert "private" not in json.dumps([projected, error])


@pytest.mark.parametrize(
    "mutation", ["extra", "bool_int", "hash", "policy", "phase", "unknown", "model"]
)
def test_forged_or_unknown_core_binding_is_not_exported(mutation):
    context, row, wire, binding = neutral_observation()
    if mutation == "extra":
        binding["private-field"] = "private-value"
    elif mutation == "bool_int":
        binding["live_authorization"] = 0
    elif mutation == "hash":
        binding["binding_sha256"] = "b" * 64
    elif mutation == "policy":
        binding["renderer_policy"] = "review_brief_v1"
    elif mutation == "phase":
        binding["observed_metis"]["phase"] = "demo"
    elif mutation == "unknown":
        binding["profile_id"] = "unreviewed-profile"
    else:
        binding["observed_metis"]["model"] = "private-value"
    with pytest.raises(ValueError, match="^CoreDeliveryConfigurationMismatch$"):
        validated_delivery_binding(binding)
    row["core_binding"] = binding
    projected, error = _provider_observations(lambda contexts: [row], [context], None)
    assert projected == [] and error == "ProviderObservationsUnavailable"


def test_known_binding_does_not_allow_arbitrary_unrecognized_outer_metadata():
    context, row, wire, binding = neutral_observation()
    row.update(wire_output=wire, core_binding=binding)
    before = deepcopy(row)
    row["private-field"] = "private-value"
    assert _provider_observations(lambda contexts: [row], [context], None) == (
        [],
        "ProviderObservationsUnavailable",
    )
    row.pop("private-field")
    assert row == before


@pytest.mark.parametrize("ledger_phase", ["development", "evaluation"])
def test_binding_phase_must_match_authoritative_reservation(tmp_path, ledger_phase):
    context, row, wire, binding = neutral_observation()
    ledger = BudgetLedger.create(
        tmp_path / "metadata.sqlite3", limit_usd=Decimal("1"), opening_spend_usd=Decimal("0")
    )
    ledger.reserve(
        request_id=row["request_id"],
        run_id=context.run_id,
        case_id=context.case_id,
        case_revision=0,
        attempt=1,
        model="gpt-4o-mini",
        phase=ledger_phase,
        amount_usd=Decimal("0.001"),
    )
    ledger.settle(row["request_id"], cost_usd=Decimal("0.0001"), input_tokens=100, output_tokens=20)
    row.update(
        core_binding=binding,
        wire_output=wire,
        http_send_started=True,
        http_status=200,
        ledger_status="settled",
        input_tokens=100,
        output_tokens=20,
        cost_estimated_usd="0.0001",
    )
    before = ledger.snapshot()
    projected, error = _provider_observations(lambda contexts: [row], [context], ledger)
    if ledger_phase == "development":
        assert projected == [row] and error is None
    else:
        assert projected == [] and error == "ProviderObservationsUnavailable"
    assert ledger.snapshot() == before
