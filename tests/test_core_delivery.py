"""Selected recipe checks use reviewed caller config and neutral invalid inputs."""

import builtins
import json
import os
import socket
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import SecretStr

from agent_app.llm.config import MetisConfig
from agent_app.orchestration.core_delivery import (
    DELIVERY_PROFILE_ID,
    delivery_recipe,
    delivery_values,
    validate_delivery_configuration,
)
from agent_app.reasoning.catalog import load_user_gap_vocabulary

ROOT = Path(__file__).resolve().parents[1]
ERROR = "CoreDeliveryConfigurationMismatch"


def actual(**changes):
    recipe = delivery_recipe()
    public = recipe["metis"] | {"max_request_usd": Decimal("0.02")}
    return {
        "profile_id": DELIVERY_PROFILE_ID,
        "config": MetisConfig(api_key="synthetic-selected-core-key", **public),
        "top_k": 5,
        "retrieval_profile": "candidate_relevance_v1",
        "ask_source_background": False,
        "concise_user_draft": False,
        "user_gaps": load_user_gap_vocabulary(str(ROOT / "config/user-gap-support-dev-v1.json")),
    } | changes


def test_committed_recipe_matches_selected_code_and_return_values_are_detached():
    expected = json.loads((ROOT / "config/core-delivery-grounded-v1.json").read_text())
    assert delivery_recipe() == expected
    exported = delivery_recipe()
    exported["metis"]["model"] = "changed"
    exported["engine_policy"]["evidence_scope"] = "all"
    assert delivery_recipe() == expected
    assert expected["engine_policy"] == {
        "top_k": 5,
        "retrieval_candidate_multiplier": 5,
        "evidence_utf8_budget_bytes": 12000,
        "repair_repeated_queries": True,
        "evidence_scope": "exact_user_version",
    }
    assert expected["renderer_policy"] == "legacy_v1"
    assert not expected["quality_claim"] and not expected["live_authorization"]


class PrivateMapping(Mapping):
    """Enumeration or credential reads before the ordinary guards are a failure."""

    def __init__(self, values):
        self.values = values

    def __iter__(self):
        raise AssertionError("Do not enumerate private caller configuration")

    def __len__(self):
        raise AssertionError("Do not enumerate private caller configuration")

    def __getitem__(self, key):
        assert key not in {"METIS_API_KEY", "AGENT_REVIEWER_TOKEN"}
        return self.values[key]


def test_environment_overlay_is_lazy_and_does_not_enable_live_or_supply_build():
    original = PrivateMapping({"AGENT_CORE_PROFILE": DELIVERY_PROFILE_ID})
    selected = delivery_values(original)
    assert selected["METIS_GROUNDED_COMPACT_PLAN"] == "true"
    assert selected["AGENT_EVAL_TOP_K"] == "5"
    assert selected["AGENT_RETRIEVAL_PROFILE"] == "candidate_relevance_v1"
    assert selected.get("METIS_LIVE_ENABLED") is None
    assert selected.get("AGENT_EVAL_INDEX") is None
    assert selected.get("AGENT_EVAL_MANIFEST_SHA256") is None
    assert selected.get("AGENT_EVAL_LEDGER") is None
    assert selected["AGENT_USER_GAP_CATALOG"] == str(ROOT / "config/user-gap-support-dev-v1.json")


def test_no_profile_preserves_exact_mapping_and_does_not_validate_old_options():
    original = PrivateMapping({"METIS_MAX_OUTPUT_TOKENS": "not-validated-here"})
    assert delivery_values(original) is original
    assert validate_delivery_configuration(**actual(profile_id=None, config=object())) is None


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("AGENT_CORE_PROFILE", "unknown-private-value"),
        ("AGENT_CORE_PROFILE", True),
        ("METIS_MODEL", "unreviewed-model"),
        ("METIS_PROMPT_POLICY", "strict"),
        ("METIS_RESPONSE_MODE", "analysis"),
        ("METIS_GROUNDED_COMPACT_PLAN", "false"),
        ("METIS_GROUNDED_JSON_OBJECT", "true"),
        ("METIS_GROUNDED_RESOURCE_GUIDANCE", "true"),
        ("METIS_GROUNDED_SOURCE_CAPACITY", "true"),
        ("METIS_GROUNDED_COMPLEMENTARY_SOURCES", "true"),
        ("METIS_GROUNDED_SOURCE_GAP_HANDOFF", "false"),
        ("METIS_GROUNDED_SOURCE_GAP_INVESTIGATION", "false"),
        ("METIS_GROUNDED_DECISION_CONTRACTS", "false"),
        ("METIS_GROUNDED_SOURCE_SELECTION_REMINDER", "false"),
        ("AGENT_GROUNDED_ASK_SOURCE_BACKGROUND", "true"),
        ("AGENT_GROUNDED_CONCISE_USER_DRAFT", "true"),
        ("AGENT_EVAL_TOP_K", "3"),
        ("AGENT_RETRIEVAL_PROFILE", "native"),
        ("METIS_INPUT_TOKEN_RESERVE", "4096"),
        ("METIS_MAX_OUTPUT_TOKENS", "2048"),
        ("METIS_MAX_REQUEST_USD", "0.05"),
        ("AGENT_USER_GAP_CATALOG", "unreviewed-vocabulary.json"),
    ],
)
def test_explicit_conflict_fails_before_any_credential_access(name, value):
    values = PrivateMapping({"AGENT_CORE_PROFILE": DELIVERY_PROFILE_ID, name: value})
    with pytest.raises(ValueError, match=f"^{ERROR}$"):
        delivery_values(values)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("model", "different-model"),
        ("phase", "demo"),
        ("live_enabled", False),
        ("prompt_policy", "different-policy"),
        ("response_mode", "analysis"),
        ("grounded_decision_contracts", False),
        ("grounded_source_gap_handoff", False),
        ("grounded_source_gap_investigation", False),
        ("grounded_source_selection_reminder", False),
        ("grounded_complementary_sources", True),
        ("grounded_resource_guidance", True),
        ("grounded_source_capacity", True),
        ("grounded_compact_plan", False),
        ("grounded_json_object", True),
        ("continuation_id", "unreviewed-continuation"),
        ("max_output_tokens", 2048),
        ("input_token_reserve", 4096),
        ("max_request_usd", Decimal("0.05")),
    ],
)
def test_changed_actual_metis_fields_fail_even_when_model_copy_skips_validation(name, value):
    values = actual()
    values["config"] = values["config"].model_copy(update={name: value})
    with pytest.raises(ValueError, match=f"^{ERROR}$"):
        validate_delivery_configuration(**values)


@pytest.mark.parametrize(
    "changes",
    [
        {"profile_id": "other"},
        {"top_k": True},
        {"top_k": 1},
        {"retrieval_profile": "native"},
        {"ask_source_background": True},
        {"ask_source_background": 0},
        {"concise_user_draft": True},
        {"user_gaps": ()},
        {"user_gaps": []},
    ],
)
def test_changed_actual_adapter_or_vocabulary_cannot_keep_the_binding(changes):
    with pytest.raises(ValueError, match=f"^{ERROR}$"):
        validate_delivery_configuration(**actual(**changes))


def test_selected_config_observation_is_pure_nonsecret_and_detached(monkeypatch):
    values = actual()

    def forbidden(*args, **kwargs):
        raise AssertionError("No external state or secret value access is allowed")

    with monkeypatch.context() as patch:
        patch.setattr(SecretStr, "get_secret_value", forbidden)
        patch.setattr(MetisConfig, "model_dump", forbidden)
        patch.setattr(builtins, "open", forbidden)
        patch.setattr(Path, "read_bytes", forbidden)
        patch.setattr(Path, "read_text", forbidden)
        patch.setattr(type(os.environ), "get", forbidden)
        patch.setattr(socket, "socket", forbidden)
        receipt = validate_delivery_configuration(**values)
    assert receipt["recipe_sha256"] == delivery_recipe()["recipe_sha256"]
    assert receipt["observed_metis"]["phase"] == "development"
    assert "api_key" not in json.dumps(receipt) and "synthetic" not in json.dumps(receipt)
    receipt["observed_metis"]["model"] = "caller-mutation"
    assert validate_delivery_configuration(**values)["observed_metis"]["model"] == "gpt-4o-mini"


def test_evaluation_phase_is_explicitly_supported_and_changes_observed_binding():
    values = actual()
    before = validate_delivery_configuration(**values)
    values["config"] = values["config"].model_copy(update={"phase": "evaluation"})
    after = validate_delivery_configuration(**values)
    assert after["recipe_sha256"] == before["recipe_sha256"]
    assert after["binding_sha256"] != before["binding_sha256"]
    assert after["observed_metis"]["phase"] == "evaluation"
