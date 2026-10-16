"""Independent controls for hidden config state and catalog identity boundaries."""

import json
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


def selected_inputs():
    return {
        "profile_id": DELIVERY_PROFILE_ID,
        "config": MetisConfig(
            api_key="neutral-review-key",
            **(delivery_recipe()["metis"] | {"max_request_usd": Decimal("0.02")}),
        ),
        "top_k": 5,
        "retrieval_profile": "candidate_relevance_v1",
        "ask_source_background": False,
        "concise_user_draft": False,
        "user_gaps": load_user_gap_vocabulary(str(ROOT / "config/user-gap-support-dev-v1.json")),
    }


@pytest.mark.parametrize("hidden_slot", ["attribute", "extra", "private"])
def test_metis_hidden_state_cannot_receive_a_clean_selected_receipt(hidden_slot, monkeypatch):
    values = selected_inputs()
    config = values["config"]
    if hidden_slot == "attribute":
        config.__dict__["undeclared_authority"] = "must-not-escape"
    else:
        object.__setattr__(config, f"__pydantic_{hidden_slot}__", {"authority": "must-not-escape"})

    def forbidden_secret(*args, **kwargs):
        raise AssertionError("Receipt validation must not open the credential")

    monkeypatch.setattr(SecretStr, "get_secret_value", forbidden_secret)
    with pytest.raises(ValueError, match=f"^{ERROR}$") as caught:
        validate_delivery_configuration(**values)
    assert "must-not-escape" not in str(caught.value)


@pytest.mark.parametrize("hidden_slot", ["attribute", "extra", "private"])
def test_catalog_hidden_state_is_rejected_before_dumping_it_away(hidden_slot):
    values = selected_inputs()
    gap = values["user_gaps"][0]
    if hidden_slot == "attribute":
        gap.__dict__["undeclared_authority"] = "must-not-escape"
    else:
        object.__setattr__(gap, f"__pydantic_{hidden_slot}__", {"authority": "must-not-escape"})
    with pytest.raises(ValueError, match=f"^{ERROR}$"):
        validate_delivery_configuration(**values)


@pytest.mark.parametrize("field", ["name", "question", "necessity"])
def test_valid_but_changed_catalog_text_cannot_reuse_the_selected_identity(field):
    values = selected_inputs()
    gaps = values["user_gaps"]
    replacements = {
        "name": "neutral_new_question",
        "question": "Which neutral information is missing?",
        "necessity": "A different caller-authored reason for asking.",
    }
    values["user_gaps"] = (
        gaps[0].model_copy(update={field: replacements[field]}),
        *gaps[1:],
    )
    with pytest.raises(ValueError, match=f"^{ERROR}$"):
        validate_delivery_configuration(**values)


def test_profile_overlay_freezes_public_values_but_not_permission_or_private_inputs():
    class CallerMapping(Mapping):
        def __init__(self):
            self.values = {"AGENT_CORE_PROFILE": DELIVERY_PROFILE_ID}

        def __getitem__(self, key):
            if key in {"METIS_API_KEY", "AGENT_REVIEWER_TOKEN"}:
                raise AssertionError("Premature private input access")
            return self.values[key]

        def __iter__(self):
            raise AssertionError("Private caller mapping must not be enumerated")

        def __len__(self):
            raise AssertionError("Private caller mapping must not be enumerated")

    caller = CallerMapping()
    selected = delivery_values(caller)
    caller.values["METIS_MODEL"] = "later-conflict"
    caller.values["AGENT_EVAL_TOP_K"] = "1"
    assert selected["METIS_MODEL"] == "gpt-4o-mini"
    assert selected["AGENT_EVAL_TOP_K"] == "5"
    assert selected.get("METIS_LIVE_ENABLED") is None
    assert selected.get("AGENT_EVAL_LEDGER") is None


def test_receipt_is_an_observation_without_a_secret_or_engine_attestation():
    receipt = validate_delivery_configuration(**selected_inputs())
    assert receipt["scope"] == "actual_public_factory_settings_and_catalog"
    assert receipt["engine_profile_required"] is True
    assert receipt["physical_code_or_build_attested"] is False
    assert receipt["quality_claim"] is False
    assert receipt["live_authorization"] is False
    encoded = json.dumps(receipt)
    assert "neutral-review-key" not in encoded and "api_key" not in encoded
