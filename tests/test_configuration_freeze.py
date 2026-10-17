"""Neutral supplied-configuration controls; no evaluation questions or gold."""

import builtins
import hashlib
import json
import os
import socket
import sqlite3
from copy import deepcopy
from decimal import ROUND_DOWN, ROUND_UP, Decimal, localcontext
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from agent_app.contracts import GroundedGap, RunLimits
from agent_app.evaluation.live import LiveEvaluationAdapters
from agent_app.llm.budget import BudgetLedger
from agent_app.llm.config import METIS_CHAT_URL, MetisConfig
from agent_app.orchestration.configuration_freeze import (
    compare_candidate_configuration,
    describe_candidate_configuration,
)

ERROR = "CandidateConfigurationInvalid"


def config(**updates):
    return MetisConfig(
        api_key="synthetic-placeholder",
        response_mode="grounded_plan",
        live_enabled=True,
        **updates,
    )


def gap(**updates):
    values = {
        "name": "neutral_reproduction",
        "kind": "user",
        "description": "The caller declared a missing reproduction.",
        "necessity": "The user can supply a reproduction.",
        "question": "Please supply a minimal reproduction.",
    }
    return GroundedGap(**(values | updates))


def arguments(**updates):
    return {
        "config": config(),
        "retrieval_profile": "candidate_relevance_v1",
        "adapter_top_k": 5,
        "caller": "memory_api",
        "caller_evidence_scope": "all",
        "engine_top_k": 5,
        "run_limits": RunLimits(),
        "proposal_checks": False,
        "ask_source_background": False,
        "concise_user_draft": False,
        "user_gaps": (),
        "snapshot_id": "docs-pilot-" + "a" * 64,
        "index_manifest_sha256": "b" * 64,
        "code_commit": "c" * 40,
        "source_sha256": {"src/agent_app/orchestration/engine.py": "d" * 64},
    } | updates


def describe(**updates):
    return describe_candidate_configuration(**arguments(**updates))


def rehash(value):
    material = {key: value for key, value in value.items() if key != "descriptor_sha256"}
    value["descriptor_sha256"] = hashlib.sha256(
        json.dumps(
            material, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
    ).hexdigest()


def assert_difference(first, second, category):
    assert first["descriptor_sha256"] != second["descriptor_sha256"]
    report = compare_candidate_configuration(first, second)
    assert report["descriptors_compatible"] is True
    assert report["accepted"] is False
    assert report["differences"] == [category]
    assert report["diagnostics"] == []


def test_legacy_metadata_collision_is_distinguished_without_constructing_adapters():
    def legacy(settings, definitions):
        adapter = LiveEvaluationAdapters.__new__(LiveEvaluationAdapters)
        adapter._config = settings
        adapter._snapshot = "docs-pilot-" + "a" * 64
        adapter._top_k = 5
        adapter._retrieval_profile = "candidate_relevance_v1"
        adapter._ask_source_background = False
        adapter._concise_user_draft = False
        adapter._gaps = definitions
        return adapter.config

    first = config()
    second = config(
        grounded_decision_contracts=True, grounded_compact_plan=True, max_output_tokens=2048
    )
    assert legacy(first, ()) == legacy(second, (gap(),))
    report = compare_candidate_configuration(
        describe(config=first), describe(config=second, user_gaps=(gap(),))
    )
    assert report["descriptors_compatible"] is True
    assert report["accepted"] is False
    assert report["differences"] == ["metis", "vocabulary"]


@pytest.mark.parametrize(
    ("base", "changed"),
    [
        ({}, {"grounded_decision_contracts": True}),
        ({}, {"grounded_source_gap_handoff": True}),
        ({"grounded_source_gap_handoff": True}, {"grounded_source_gap_investigation": True}),
        ({}, {"grounded_source_selection_reminder": True}),
        ({"grounded_source_selection_reminder": True}, {"grounded_complementary_sources": True}),
        ({}, {"grounded_resource_guidance": True}),
        ({"grounded_decision_contracts": True}, {"grounded_source_capacity": True}),
        ({"grounded_decision_contracts": True}, {"grounded_compact_plan": True}),
        ({}, {"grounded_json_object": True}),
        ({}, {"max_output_tokens": 2048}),
        ({}, {"input_token_reserve": 16384}),
        ({}, {"max_request_usd": Decimal("0.03")}),
        ({}, {"model": "gpt-4o-mini-2024-07-18"}),
        ({}, {"phase": "evaluation"}),
        ({}, {"prompt_policy": "decision_rubric"}),
    ],
)
def test_each_public_behavior_and_limit_is_bound(base, changed):
    assert_difference(
        describe(config=config(**base)), describe(config=config(**(base | changed))), "metis"
    )


def test_disabled_candidate_is_distinct_and_grants_no_live_authorization():
    disabled = config().model_copy(update={"live_enabled": False})
    assert_difference(describe(), describe(config=disabled), "metis")
    descriptor = describe(config=disabled)
    assert descriptor["live_authorization"] is False
    assert descriptor["runtime_verified"] is False
    assert descriptor["quality_claim"] is False


@pytest.mark.parametrize("field", ["ask_source_background", "concise_user_draft"])
def test_each_display_option_is_bound(field):
    assert_difference(describe(), describe(**{field: True}), "display")


@pytest.mark.parametrize(
    "updates",
    [
        {"retrieval_profile": "native"},
        {"caller": "persistent_service"},
        {"caller": "persistent_service", "caller_evidence_scope": "exact_user_version"},
    ],
)
def test_profile_and_caller_composition_are_bound(updates):
    assert_difference(describe(), describe(**updates), "retrieval")


def test_native_adapter_read_bound_and_engine_cap_are_separate():
    first = describe(retrieval_profile="native", adapter_top_k=1)
    policy = first["retrieval"]
    assert policy["adapter_candidate_limit"] == 1
    assert policy["composed_engine_policy"]["top_k"] == 5
    assert policy["composed_engine_policy"]["evidence_scope"] == "all"
    assert policy["profile_overrides"] == {}
    assert_difference(first, describe(retrieval_profile="native", adapter_top_k=2), "retrieval")
    base = {"caller": "persistent_service", "retrieval_profile": "native"}
    assert_difference(describe(**base), describe(**base, engine_top_k=3), "retrieval")


def test_candidate_policy_override_is_derived_and_retains_the_caller_scope():
    descriptor = describe(caller="persistent_service")
    policy = descriptor["retrieval"]
    assert policy["caller_evidence_scope"] == "all"
    assert policy["adapter_candidate_limit"] == 25
    assert policy["adapter_selection_policy"] == "query_relevance_v1"
    assert policy["composed_engine_policy"] == {
        "top_k": 5,
        "evidence_scope": "exact_user_version",
        "repair_repeated_queries": True,
        "retrieval_candidate_multiplier": 5,
        "evidence_utf8_budget_bytes": 12000,
    }
    assert_difference(
        descriptor,
        describe(caller="persistent_service", caller_evidence_scope="exact_user_version"),
        "retrieval",
    )


@pytest.mark.parametrize(
    "field", ["max_model_attempts", "max_retrieval_rounds", "max_queries_per_round", "max_steps"]
)
def test_every_run_limit_is_bound(field):
    assert_difference(
        describe(caller="persistent_service"),
        describe(caller="persistent_service", run_limits=RunLimits(**{field: 1})),
        "core",
    )


def test_proposal_checks_are_bound_for_the_explicit_service_caller():
    assert_difference(
        describe(caller="persistent_service"),
        describe(caller="persistent_service", proposal_checks=True),
        "core",
    )


@pytest.mark.parametrize(
    "updates",
    [
        {"name": "neutral_details"},
        {"description": "The caller declared missing neutral details."},
        {"necessity": "The user can provide the missing details."},
        {"question": "Please provide the missing details."},
    ],
)
def test_every_question_definition_field_is_bound(updates):
    assert_difference(
        describe(user_gaps=(gap(),)), describe(user_gaps=(gap(**updates),)), "vocabulary"
    )


def test_vocabulary_availability_order_and_optional_declared_raw_pin_are_bound():
    first, second = gap(), gap(name="neutral_details")
    assert_difference(describe(), describe(user_gaps=(first,)), "vocabulary")
    assert_difference(
        describe(user_gaps=(first, second)), describe(user_gaps=(second, first)), "vocabulary"
    )
    assert_difference(describe(), describe(vocabulary_raw_sha256="a" * 64), "vocabulary")


@pytest.mark.parametrize(
    "updates",
    [
        {"snapshot_id": "docs-pilot-" + "b" * 64},
        {"index_manifest_sha256": "a" * 64},
        {"code_commit": "a" * 40},
        {"source_sha256": {"src/agent_app/orchestration/engine.py": "a" * 64}},
        {"source_sha256": {"src/agent_app/api.py": "d" * 64}},
    ],
)
def test_declared_pins_are_bound_without_claiming_file_verification(updates):
    assert_difference(describe(), describe(**updates), "pins")


def test_decimal_equivalence_and_source_map_order_have_one_canonical_identity():
    pins = {"src/agent_app/api.py": "a" * 64, "uv.lock": "b" * 64}
    first = describe(config=config(max_request_usd=Decimal("0.0200")), source_sha256=pins)
    second = describe(
        config=config(max_request_usd=Decimal("0.02")),
        source_sha256=dict(reversed(tuple(pins.items()))),
    )
    assert first["descriptor_sha256"] == second["descriptor_sha256"]
    report = compare_candidate_configuration(first, second)
    assert report["accepted"] is True
    assert report["differences"] == []
    assert report["scope"] == "supplied_configuration_compatibility_and_equality_only"
    assert (
        report["quality_claim"]
        is report["runtime_verified"]
        is report["live_authorization"]
        is False
    )


def test_exact_caps_beyond_decimal_context_precision_do_not_collide():
    first = Decimal("0.020000000000000000000000000001")
    second = Decimal("0.020000000000000000000000000002")
    assert first.normalize() == second.normalize()  # Retain the old rounding counterexample.
    assert_difference(
        describe(config=config(max_request_usd=first)),
        describe(config=config(max_request_usd=second)),
        "metis",
    )


def test_long_canonical_decimal_roundtrips_without_precision_loss():
    text = "0.02" + "0" * 80 + "1"
    descriptor = describe(config=config(max_request_usd=Decimal(text)))
    assert descriptor["metis"]["configuration"]["max_request_usd"] == text
    assert compare_candidate_configuration(descriptor, descriptor)["accepted"] is True
    equivalent = describe(config=config(max_request_usd=Decimal(text + "000")))
    assert equivalent["descriptor_sha256"] == descriptor["descriptor_sha256"]


def test_excessively_large_decimal_representation_rejects_before_formatting():
    value = Decimal("0.02" + "0" * 1024 + "1")
    with pytest.raises(ValueError, match=f"^{ERROR}$"):
        describe(config=config(max_request_usd=value))


@pytest.mark.parametrize("precision", [1, 28, 100])
@pytest.mark.parametrize("rounding", [ROUND_DOWN, ROUND_UP])
def test_reserve_cost_rejects_insufficient_cap_independent_of_decimal_context(precision, rounding):
    values = arguments(config=config(max_request_usd=Decimal("0.006")))
    with localcontext() as context:
        context.prec = precision
        context.rounding = rounding
        with pytest.raises(ValueError, match=f"^{ERROR}$"):
            describe_candidate_configuration(**values)


def test_exact_cost_boundary_and_descriptor_identity_ignore_decimal_context():
    values = arguments(config=config(max_request_usd=Decimal("0.006082560")))
    descriptors = []
    for precision in (1, 28, 100):
        for rounding in (ROUND_DOWN, ROUND_UP):
            with localcontext() as context:
                context.prec = precision
                context.rounding = rounding
                descriptor = describe_candidate_configuration(**values)
                assert compare_candidate_configuration(descriptor, descriptor)["accepted"] is True
                descriptors.append(descriptor)
    assert all(item == descriptors[0] for item in descriptors)


@pytest.mark.parametrize(
    "updates",
    [
        {"retrieval_profile": "unknown-sensitive-profile"},
        {"adapter_top_k": 1},
        {"engine_top_k": 1},
        {"adapter_top_k": True},
        {"engine_top_k": True},
        {"caller": "sensitive-unknown-caller"},
        {"caller_evidence_scope": "sensitive-scope"},
        {"caller_evidence_scope": "exact_user_version"},
        {"run_limits": RunLimits(max_model_attempts=1)},
        {"proposal_checks": True},
        {"ask_source_background": 1},
        {"concise_user_draft": "true"},
        {"user_gaps": [gap()]},
        {"user_gaps": (gap(), gap())},
        {"user_gaps": (gap(name="streamlit_version"),)},
        {"snapshot_id": "sensitive-invalid-snapshot"},
        {"index_manifest_sha256": "sensitive-invalid-hash"},
        {"code_commit": "a" * 39},
        {"source_sha256": {}},
        {"source_sha256": {"../sensitive-path": "a" * 64}},
        {"source_sha256": {"src/agent_app/api.py": "sensitive-invalid-hash"}},
        {"vocabulary_raw_sha256": "sensitive-invalid-hash"},
    ],
)
def test_invalid_candidate_inputs_fail_with_one_static_error(updates):
    with pytest.raises(ValueError, match=f"^{ERROR}$") as error:
        describe(**updates)
    assert "sensitive" not in repr(error.value)


@pytest.mark.parametrize(
    "updates",
    [
        {"model": "sensitive model string"},
        {"model": "sensitive-unknown-model"},
        {"phase": "demo"},
        {"continuation_id": "closed-cohort"},
        {"response_mode": "analysis"},
        {"grounded_compact_plan": True},
        {"grounded_source_capacity": True},
        {"grounded_source_gap_investigation": True},
        {"grounded_complementary_sources": True},
        {"max_request_usd": Decimal("0.001")},
        {"max_request_usd": Decimal("NaN")},
        {"max_output_tokens": True},
        {"input_token_reserve": 50000},
    ],
)
def test_bypassed_invalid_public_config_is_revalidated_without_secret_access(updates):
    invalid = config().model_copy(update=updates)
    with pytest.raises(ValueError, match=f"^{ERROR}$") as error:
        describe(config=invalid)
    assert "sensitive" not in repr(error.value)


@pytest.mark.parametrize("target", ["config", "gap", "limits"])
def test_hidden_constructed_state_is_not_silently_dumped_away(target):
    values = arguments()
    if target == "gap":
        invalid = gap()
        values["user_gaps"] = (invalid,)
    else:
        invalid = values["config" if target == "config" else "run_limits"]
    object.__setattr__(invalid, "sensitive_hidden_field", "sensitive_hidden_value")
    with pytest.raises(ValueError, match=f"^{ERROR}$"):
        describe_candidate_configuration(**values)


@pytest.mark.parametrize(
    "mutation",
    [
        "hash",
        "endpoint",
        "derived_policy",
        "semantic_hash",
        "static_limit",
        "extra_field",
        "extra_pin",
        "bad_model",
    ],
)
def test_comparison_revalidates_even_a_freshly_rehashed_tampered_descriptor(mutation):
    original = describe()
    changed = deepcopy(original)
    if mutation == "hash":
        changed["descriptor_sha256"] = "f" * 64
    elif mutation == "endpoint":
        changed["metis"]["endpoint"] = "https://sensitive.invalid"
    elif mutation == "derived_policy":
        changed["retrieval"]["composed_engine_policy"]["evidence_scope"] = "all"
    elif mutation == "semantic_hash":
        changed["vocabulary"]["semantic_sha256"] = "f" * 64
    elif mutation == "static_limit":
        changed["live_authorization"] = True
    elif mutation == "extra_field":
        changed["sensitive-unknown-field"] = "sensitive-value"
    elif mutation == "extra_pin":
        changed["pins"]["source_sha256"]["sensitive-secret-path"] = "f" * 64
    else:
        changed["metis"]["configuration"]["model"] = "sensitive-invalid-model"
    if mutation != "hash":
        rehash(changed)
    report = compare_candidate_configuration(original, changed)
    assert report["accepted"] is False
    assert report["descriptors_compatible"] is False
    assert report["differences"] == []
    assert report["diagnostics"] == [ERROR]
    assert "sensitive" not in json.dumps(report)


@pytest.mark.parametrize("invalid", [None, [], {"sensitive-secret": "sensitive-value"}])
def test_comparison_rejects_invalid_shapes_without_echoing_them(invalid):
    assert compare_candidate_configuration(describe(), invalid)["diagnostics"] == [ERROR]


def test_new_metis_field_fails_closed_instead_of_becoming_unbound(monkeypatch):
    values = arguments()
    fields = dict(MetisConfig.model_fields)
    fields["future_sensitive_field"] = fields["api_key"]
    monkeypatch.setattr(MetisConfig, "__pydantic_fields__", fields)
    with pytest.raises(ValueError, match=f"^{ERROR}$"):
        describe_candidate_configuration(**values)


def test_credentials_are_never_read_or_dumped_and_do_not_affect_identity(monkeypatch):
    first = arguments()
    second = arguments(
        config=config().model_copy(update={"api_key": SecretStr("different-synthetic-key")})
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("Credential serialization/access is forbidden")

    monkeypatch.setattr(SecretStr, "get_secret_value", forbidden)
    monkeypatch.setattr(MetisConfig, "model_dump", forbidden)
    monkeypatch.setattr(MetisConfig, "model_dump_json", forbidden)
    one = describe_candidate_configuration(**first)
    two = describe_candidate_configuration(**second)
    assert compare_candidate_configuration(one, two)["accepted"] is True
    assert "synthetic" not in json.dumps(one)
    assert "api_key" not in json.dumps(one)


def test_descriptor_and_comparison_need_no_io_environment_or_runtime(monkeypatch):
    values = arguments(user_gaps=(gap(),))

    def forbidden(*args, **kwargs):
        raise AssertionError("External state access is forbidden")

    with monkeypatch.context() as patch:
        patch.setattr(builtins, "open", forbidden)
        patch.setattr(Path, "open", forbidden)
        patch.setattr(Path, "read_bytes", forbidden)
        patch.setattr(Path, "read_text", forbidden)
        patch.setattr(os, "getenv", forbidden)
        patch.setattr(type(os.environ), "get", forbidden)
        patch.setattr(type(os.environ), "__getitem__", forbidden)
        patch.setattr(sqlite3, "connect", forbidden)
        patch.setattr(socket, "socket", forbidden)
        patch.setattr(httpx, "Client", forbidden)
        patch.setattr(BudgetLedger, "__init__", forbidden)
        patch.setattr(LiveEvaluationAdapters, "__init__", forbidden)
        descriptor = describe_candidate_configuration(**values)
        report = compare_candidate_configuration(descriptor, descriptor)
    assert report["accepted"] is True
    assert descriptor["metis"]["endpoint"] == METIS_CHAT_URL


def test_inputs_and_exported_material_are_detached_and_comparison_is_immutable():
    values = arguments(user_gaps=(gap(),))
    before = deepcopy(values)
    first = describe_candidate_configuration(**values)
    assert values == before
    frozen = deepcopy(first)
    assert compare_candidate_configuration(first, first)["accepted"] is True
    assert first == frozen
    values["source_sha256"]["src/agent_app/orchestration/engine.py"] = "f" * 64
    assert first == frozen
    first["vocabulary"]["definitions"][0]["question"] = "Changed exported copy"
    assert values["user_gaps"][0].question == before["user_gaps"][0].question
