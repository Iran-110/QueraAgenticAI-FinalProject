"""One explicitly selected core recipe, checked by the existing live factory.

Selection is local deployment configuration, never permission to spend. The
ordinary halt/index/credential guards retain authority. This binds actual public
settings and vocabulary, not physical code/build, source sufficiency or quality.
"""

import hashlib
import json
from collections import ChainMap
from collections.abc import Mapping
from pathlib import Path

from agent_app.contracts import GroundedGap
from agent_app.orchestration.configuration_freeze import _public_config
from agent_app.orchestration.retrieval_profile import retrieval_profile_options
from agent_app.orchestration.validation import detached_contract
from agent_app.reasoning.catalog import validate_user_gaps

DELIVERY_PROFILE_ID = "grounded_candidate_v1"
_ERROR = "CoreDeliveryConfigurationMismatch"
_ROOT = Path(__file__).resolve().parents[3]
_VOCABULARY = _ROOT / "config/user-gap-support-dev-v1.json"
# This is the reviewed caller vocabulary, not questions inferred from test gold.
_VOCABULARY_SEMANTIC_SHA256 = "56e6180928536534e99284c270e0a272568b32e3a2fb07a1ff7b441d289a7cd8"
_PUBLIC = {
    "live_enabled": True,
    "model": "gpt-4o-mini",
    "prompt_policy": "baseline",
    "response_mode": "grounded_plan",
    "grounded_decision_contracts": True,
    "grounded_source_gap_handoff": True,
    "grounded_source_gap_investigation": True,
    "grounded_source_selection_reminder": True,
    "grounded_complementary_sources": False,
    "grounded_resource_guidance": False,
    "grounded_source_capacity": False,
    "grounded_compact_plan": True,
    "grounded_json_object": False,
    "continuation_id": None,
    "max_output_tokens": 1024,
    "input_token_reserve": 32768,
    "max_request_usd": "0.02",
}
_ENVIRONMENT = {
    "METIS_MODEL": "gpt-4o-mini",
    "METIS_PROMPT_POLICY": "baseline",
    "METIS_RESPONSE_MODE": "grounded_plan",
    "AGENT_EVAL_TOP_K": "5",
    "AGENT_RETRIEVAL_PROFILE": "candidate_relevance_v1",
    "AGENT_GROUNDED_ASK_SOURCE_BACKGROUND": "false",
    "AGENT_GROUNDED_CONCISE_USER_DRAFT": "false",
    "METIS_INPUT_TOKEN_RESERVE": "32768",
    "METIS_MAX_OUTPUT_TOKENS": "1024",
    "METIS_MAX_REQUEST_USD": "0.02",
    **{
        "METIS_" + name.upper(): str(value).lower()
        for name, value in _PUBLIC.items()
        if name.startswith("grounded_")
    },
}


def _digest(value):
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    ).hexdigest()


def delivery_recipe() -> dict:
    """Return a detached selected recipe; no file/env/credential/ledger access."""
    material = {
        "schema_version": 1,
        "profile_id": DELIVERY_PROFILE_ID,
        "metis": dict(_PUBLIC),
        "allowed_phases": ["development", "evaluation"],
        "retrieval_profile": "candidate_relevance_v1",
        "adapter_top_k": 5,
        "engine_policy": {"top_k": 5, **retrieval_profile_options("candidate_relevance_v1")},
        "renderer_policy": "legacy_v1",
        "ask_source_background": False,
        "concise_user_draft": False,
        "vocabulary_semantic_sha256": _VOCABULARY_SEMANTIC_SHA256,
        "live_authorization": False,
        "quality_claim": False,
        "final_corpus_selected": False,
    }
    return {**material, "recipe_sha256": _digest(material)}


def delivery_values(values: Mapping[str, str]) -> Mapping[str, str]:
    """Overlay only public defaults lazily; never enumerate/read private values.

    Conflicting explicit settings fail closed instead of being silently replaced.
    The live enable switch, phase, index/build pins, ledger and key remain caller
    inputs, governed by their existing guards. No profile means the old mapping.
    """
    try:
        selected = values.get("AGENT_CORE_PROFILE")
        if selected is None:
            return values
        if type(selected) is not str or selected != DELIVERY_PROFILE_ID:
            raise ValueError
        for key, expected in _ENVIRONMENT.items():
            if key in values and (type(values[key]) is not str or values[key] != expected):
                raise ValueError
        if "AGENT_USER_GAP_CATALOG" in values:
            path = values["AGENT_USER_GAP_CATALOG"]
            if type(path) is not str or Path(path).resolve() != _VOCABULARY.resolve():
                raise ValueError
        # ChainMap does not traverse the underlying mapping (which may contain
        # credentials) while installing defaults.
        return ChainMap({**_ENVIRONMENT, "AGENT_USER_GAP_CATALOG": str(_VOCABULARY)}, values)
    except Exception:
        raise ValueError(_ERROR) from None


def validate_delivery_configuration(
    *,
    profile_id,
    config,
    top_k,
    retrieval_profile,
    ask_source_background,
    concise_user_draft,
    user_gaps,
) -> dict | None:
    """Check actual nonsecret constructor settings; no key value is accessed.

    The returned receipt is a local settings observation. The existing caller
    must still verify its index and guards and use the registered engine profile.
    """
    if profile_id is None:
        return None
    try:
        if type(profile_id) is not str or profile_id != DELIVERY_PROFILE_ID:
            raise ValueError
        actual = _public_config(config)
        phase = actual.pop("phase")
        if phase not in {"development", "evaluation"} or actual != _PUBLIC:
            raise ValueError
        if (
            type(top_k) is not int
            or top_k != 5
            or type(retrieval_profile) is not str
            or retrieval_profile != "candidate_relevance_v1"
            or ask_source_background is not False
            or concise_user_draft is not False
            or type(user_gaps) is not tuple
        ):
            raise ValueError
        checked_gaps = tuple(detached_contract(GroundedGap, gap) for gap in user_gaps)
        definitions = [gap.model_dump(mode="json") for gap in validate_user_gaps(checked_gaps)]
        if _digest(definitions) != _VOCABULARY_SEMANTIC_SHA256:
            raise ValueError
        return _binding(phase)
    except Exception:
        raise ValueError(_ERROR) from None


def _binding(phase):
    material = {
        "schema_version": 1,
        "profile_id": DELIVERY_PROFILE_ID,
        "recipe_sha256": delivery_recipe()["recipe_sha256"],
        "observed_metis": {**_PUBLIC, "phase": phase},
        "adapter_top_k": 5,
        "retrieval_profile": "candidate_relevance_v1",
        "renderer_policy": "legacy_v1",
        "ask_source_background": False,
        "concise_user_draft": False,
        "vocabulary_semantic_sha256": _VOCABULARY_SEMANTIC_SHA256,
        "scope": "actual_public_factory_settings_and_catalog",
        "engine_profile_required": True,
        "physical_code_or_build_attested": False,
        "live_authorization": False,
        "quality_claim": False,
    }
    return {**material, "binding_sha256": _digest(material)}


def validated_delivery_binding(value) -> dict:
    """Project only the exact known receipt shape into an execution report.

    Equality checks a declaration; it does not authenticate an arbitrary observer.
    Reconstructing the result prevents untrusted metadata from exporting secrets.
    """
    try:
        if type(value) is not dict or type(value.get("observed_metis")) is not dict:
            raise ValueError
        phase = value["observed_metis"].get("phase")
        if type(phase) is not str or phase not in {"development", "evaluation"}:
            raise ValueError
        expected = _binding(phase)
        # Canonical JSON distinguishes true/1 and other equality-coercible types.
        if _digest(value) != _digest(expected):
            raise ValueError
        return expected
    except Exception:
        raise ValueError(_ERROR) from None
