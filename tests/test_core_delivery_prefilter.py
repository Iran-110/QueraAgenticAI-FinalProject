"""Explicit prefilter recipe wiring, with neutral controls and disposable storage."""

import builtins
import hashlib
import json
import socket
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import SecretStr
from test_configuration_freeze import arguments, rehash
from test_core_delivery import PrivateMapping, actual
from test_evaluation_live import CountedMock
from test_evaluation_live import index as index
from test_evaluation_live import ledger as ledger

from agent_app.contracts import CaseState, EvidenceBundle, ReasoningContext
from agent_app.evaluation import live
from agent_app.evaluation.provider_metadata import optional_provider_metadata
from agent_app.llm.budget import BudgetLedger
from agent_app.orchestration.configuration_freeze import (
    compare_candidate_configuration,
    describe_candidate_configuration,
)
from agent_app.orchestration.core_delivery import (
    DELIVERY_PROFILE_ID,
    PREFILTER_DELIVERY_PROFILE_ID,
    delivery_recipe,
    delivery_values,
    validate_delivery_configuration,
    validated_delivery_binding,
)
from agent_app.orchestration.ports import ReasoningStopped
from agent_app.orchestration.retrieval_profile import (
    retrieval_profile_options,
    validate_retrieval_profile,
)
from agent_app.testing.http_pilot_runtime import offline_network

ROOT = Path(__file__).resolve().parents[1]
PROFILE = "candidate_version_prefilter_v1"
ERROR = "CoreDeliveryConfigurationMismatch"
PAIRS = (
    (DELIVERY_PROFILE_ID, "candidate_relevance_v1"),
    (PREFILTER_DELIVERY_PROFILE_ID, PROFILE),
)
V1_RAW_SHA256 = "b013ffb865ddce90229e85de3f4fff6407be29dffbbbf3c6ddcf243d6699c36e"
V1_RECIPE_SHA256 = "a356238d62acfed9ae5087828548460fd7119893218e874fa228940a2fc63ed4"
V2_RECIPE_SHA256 = "ae7b2d04202324bda360b478dd2dd6dff79a3482395fc5dd1e0deade1d9491c4"
# Recorded before adding this profile; no changes to legacy descriptor fields.
LEGACY_DESCRIPTORS = {
    ("native", "memory_api"): "814931141adabbd17f120f2a3909c5c6fedeb18234e1822ea15170d8d9e82a93",
    (
        "native",
        "persistent_service",
    ): "291b5d611afd1b22c0a829287fbdfbede71289eeb0946de83fd39a8e65979e75",
    (
        "candidate_relevance_v1",
        "memory_api",
    ): "639d28551b2143ee6ca0eebc946be101fecaa8b82b046e8cd0fbd936a8ea1395",
    (
        "candidate_relevance_v1",
        "persistent_service",
    ): "11f1e641d3378f7b3989a19ddcfef07fb0707b71bc46dd197de869ad1620c38d",
}


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def selected(profile_id=PREFILTER_DELIVERY_PROFILE_ID, retrieval_profile=PROFILE, **changes):
    return actual(profile_id=profile_id, retrieval_profile=retrieval_profile, **changes)


def test_new_committed_recipe_is_additive_and_preserves_default_recipe_bytes():
    old_path = ROOT / "config/core-delivery-grounded-v1.json"
    old = json.loads(old_path.read_bytes())
    new = delivery_recipe(profile_id=PREFILTER_DELIVERY_PROFILE_ID)
    assert hashlib.sha256(old_path.read_bytes()).hexdigest() == V1_RAW_SHA256
    assert delivery_recipe() == delivery_recipe(profile_id=DELIVERY_PROFILE_ID) == old
    assert old["recipe_sha256"] == V1_RECIPE_SHA256
    assert new == json.loads(
        (ROOT / "config/core-delivery-grounded-prefilter-v2.json").read_bytes()
    )
    assert new["recipe_sha256"] == V2_RECIPE_SHA256 != V1_RECIPE_SHA256
    projected = deepcopy(new)
    projected["profile_id"] = old["profile_id"]
    projected["retrieval_profile"] = old["retrieval_profile"]
    projected["engine_policy"].pop("retrieval_version_prefilter")
    projected["recipe_sha256"] = old["recipe_sha256"]
    assert projected == old
    new["metis"]["model"] = "caller-mutation"
    new["engine_policy"]["retrieval_version_prefilter"] = False
    assert (
        delivery_recipe(profile_id=PREFILTER_DELIVERY_PROFILE_ID)["recipe_sha256"]
        == V2_RECIPE_SHA256
    )
    assert delivery_recipe()["recipe_sha256"] == V1_RECIPE_SHA256


def test_new_retrieval_options_only_add_the_explicit_prefilter_flag():
    old = retrieval_profile_options("candidate_relevance_v1")
    new = retrieval_profile_options(PROFILE)
    assert retrieval_profile_options("native") == {}
    assert "retrieval_version_prefilter" not in old
    assert new == {**old, "retrieval_version_prefilter": True}
    new["retrieval_version_prefilter"] = False
    assert retrieval_profile_options(PROFILE)["retrieval_version_prefilter"] is True


@pytest.mark.parametrize("value", [1, 3, True, 5.0, "5", None])
def test_new_candidate_profile_retains_the_exact_five_record_contract(value):
    with pytest.raises(ValueError, match="^RetrievalProfileInvalid$"):
        validate_retrieval_profile(PROFILE, top_k=value)


@pytest.mark.parametrize("value", ["prefilter", "grounded_candidate_prefilter_v1", True, None, {}])
def test_recipe_accepts_only_the_two_registered_core_ids(value):
    with pytest.raises(ValueError, match=f"^{ERROR}$"):
        delivery_recipe(profile_id=value)


@pytest.mark.parametrize(("profile_id", "retrieval_profile"), PAIRS)
def test_overlay_remains_lazy_and_does_not_supply_live_authority(profile_id, retrieval_profile):
    original = PrivateMapping({"AGENT_CORE_PROFILE": profile_id})
    overlaid = delivery_values(original)
    assert overlaid["AGENT_RETRIEVAL_PROFILE"] == retrieval_profile
    assert overlaid["METIS_MODEL"] == "gpt-4o-mini"
    assert overlaid["AGENT_EVAL_TOP_K"] == "5"
    for absent in ("METIS_LIVE_ENABLED", "AGENT_EVAL_INDEX", "AGENT_EVAL_LEDGER"):
        assert overlaid.get(absent) is None
    overlaid.maps[0]["AGENT_RETRIEVAL_PROFILE"] = "caller-mutation"
    assert delivery_values(original)["AGENT_RETRIEVAL_PROFILE"] == retrieval_profile
    plain = PrivateMapping({})
    assert delivery_values(plain) is plain


@pytest.mark.parametrize(("profile_id", "retrieval_profile"), PAIRS)
def test_cross_pair_environment_conflict_stops_before_ledger_or_key(
    monkeypatch, profile_id, retrieval_profile
):
    other = PROFILE if retrieval_profile != PROFILE else "candidate_relevance_v1"
    values = PrivateMapping(
        {
            "AGENT_CORE_PROFILE": profile_id,
            "AGENT_RETRIEVAL_PROFILE": other,
            "METIS_LIVE_ENABLED": "true",
        }
    )
    monkeypatch.setattr(live, "_budget_guard", lambda _: pytest.fail("No ledger needed"))
    with pytest.raises(ValueError, match=f"^{ERROR}$"):
        live.configured_factory(values)


@pytest.mark.parametrize(("profile_id", "retrieval_profile"), PAIRS)
@pytest.mark.parametrize("phase", ["development", "evaluation"])
def test_bindings_are_profile_specific_strictly_projected_and_detached(
    profile_id, retrieval_profile, phase
):
    values = selected(profile_id, retrieval_profile)
    values["config"] = values["config"].model_copy(update={"phase": phase})
    binding = validate_delivery_configuration(**values)
    assert binding["profile_id"] == profile_id
    assert binding["retrieval_profile"] == retrieval_profile
    assert binding["recipe_sha256"] == delivery_recipe(profile_id=profile_id)["recipe_sha256"]
    projected = optional_provider_metadata(
        {"core_binding": binding, "requested_model": "gpt-4o-mini"}, request_id="neutral"
    )["core_binding"]
    assert projected == binding and projected is not binding
    projected["observed_metis"]["model"] = "caller-mutation"
    assert validated_delivery_binding(binding) == binding


@pytest.mark.parametrize(("profile_id", "retrieval_profile"), PAIRS)
def test_direct_constructor_cross_pair_rejects_before_budget_or_index(
    monkeypatch, profile_id, retrieval_profile
):
    other = PROFILE if retrieval_profile != PROFILE else "candidate_relevance_v1"
    values = selected(profile_id, other)
    monkeypatch.setattr(live, "_budget_guard", lambda _: pytest.fail("No ledger needed"))
    with pytest.raises(ValueError, match=f"^{ERROR}$"):
        live.LiveEvaluationAdapters(
            index_path=Path("not-opened"),
            snapshot_id="not-opened",
            manifest_sha256="a" * 64,
            ledger=object(),
            core_profile=profile_id,
            **{key: values[key] for key in values if key != "profile_id"},
        )


@pytest.mark.parametrize("storage", ["extra", "private", "dict"])
def test_new_binding_does_not_launder_hidden_catalog_state(storage):
    values = selected()
    gap = values["user_gaps"][0].model_copy(deep=True)
    if storage == "dict":
        object.__setattr__(gap, "PRIVATE_NAME", "PRIVATE_VALUE")
    else:
        object.__setattr__(
            gap,
            "__pydantic_extra__" if storage == "extra" else "__pydantic_private__",
            {"PRIVATE_NAME": "PRIVATE_VALUE"},
        )
    values["user_gaps"] = (gap, *values["user_gaps"][1:])
    with pytest.raises(ValueError, match=f"^{ERROR}$"):
        validate_delivery_configuration(**values)


def test_new_binding_validation_reads_no_secret_or_external_state(monkeypatch):
    values = selected()

    def forbidden(*args, **kwargs):
        pytest.fail("Pure binding validation must not access external/private state")

    with monkeypatch.context() as patch:
        patch.setattr(SecretStr, "get_secret_value", forbidden)
        patch.setattr(type(values["config"]), "model_dump", forbidden)
        patch.setattr(builtins, "open", forbidden)
        patch.setattr(Path, "read_bytes", forbidden)
        patch.setattr(socket, "socket", forbidden)
        binding = validate_delivery_configuration(**values)
    assert binding["profile_id"] == PREFILTER_DELIVERY_PROFILE_ID


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("profile_id", DELIVERY_PROFILE_ID),
        ("retrieval_profile", "candidate_relevance_v1"),
        ("recipe_sha256", V1_RECIPE_SHA256),
        ("engine_profile_required", 1),
        ("PRIVATE_NAME", "PRIVATE_VALUE"),
    ],
)
def test_rehashed_inconsistent_or_extra_binding_cannot_enter_provider_metadata(field, value):
    binding = validate_delivery_configuration(**selected())
    binding[field] = value
    binding["binding_sha256"] = digest(
        {key: value for key, value in binding.items() if key != "binding_sha256"}
    )
    with pytest.raises(ValueError, match=f"^{ERROR}$"):
        optional_provider_metadata(
            {"core_binding": binding, "requested_model": "gpt-4o-mini"}, request_id="neutral"
        )


@pytest.mark.parametrize(("profile", "caller"), LEGACY_DESCRIPTORS)
def test_recorded_legacy_full_descriptor_bytes_remain_exact(profile, caller):
    descriptor = describe_candidate_configuration(
        **arguments(retrieval_profile=profile, caller=caller)
    )
    assert digest(descriptor) == LEGACY_DESCRIPTORS[(profile, caller)]


def test_new_descriptor_binds_actual_candidate_window_policy_and_composed_flag():
    old = describe_candidate_configuration(**arguments())
    new = describe_candidate_configuration(**arguments(retrieval_profile=PROFILE))
    retrieval = new["retrieval"]
    assert retrieval["adapter_candidate_limit"] == 25
    assert retrieval["adapter_selection_policy"] == "query_relevance_v1"
    assert retrieval["profile_overrides"] == retrieval_profile_options(PROFILE)
    assert retrieval["composed_engine_policy"]["retrieval_version_prefilter"] is True
    assert compare_candidate_configuration(new, new)["accepted"] is True
    compared = compare_candidate_configuration(old, new)
    assert compared["descriptors_compatible"] is True
    assert compared["differences"] == ["retrieval"] and compared["accepted"] is False
    tampered = deepcopy(new)
    tampered["retrieval"]["composed_engine_policy"].pop("retrieval_version_prefilter")
    rehash(tampered)
    assert compare_candidate_configuration(tampered, new)["descriptors_compatible"] is False


@pytest.mark.parametrize(("profile_id", "retrieval_profile"), PAIRS)
def test_halt_with_either_selected_profile_precedes_credentials_and_index(
    tmp_path, monkeypatch, profile_id, retrieval_profile
):
    (tmp_path / "runtime").mkdir()
    budget = BudgetLedger.create(
        tmp_path / "runtime/budget.sqlite3",
        limit_usd=Decimal("1"),
        opening_spend_usd=Decimal("0"),
    )
    budget.halt()
    monkeypatch.setattr(live, "ROOT", tmp_path)
    monkeypatch.setattr(live, "_verified_index", lambda *args: pytest.fail("No index needed"))
    values = PrivateMapping(
        {
            "AGENT_CORE_PROFILE": profile_id,
            "AGENT_RETRIEVAL_PROFILE": retrieval_profile,
            "METIS_LIVE_ENABLED": "true",
        }
    )
    with offline_network(), pytest.raises(ValueError, match="^LiveLedgerHalted$"):
        live.configured_factory(values)
    assert budget.snapshot().halted is True


def factory(index, ledger, profile_id, retrieval_profile, transports):
    values = selected(profile_id, retrieval_profile)

    def allocate():
        transport = CountedMock(lambda request: pytest.fail("No provider send expected"))
        transports.append(transport)
        return transport

    return live.LiveEvaluationAdapters(
        index_path=index[0],
        snapshot_id=index[1],
        manifest_sha256=index[2],
        ledger=ledger,
        core_profile=profile_id,
        transport_factory=allocate,
        **{key: values[key] for key in values if key != "profile_id"},
    )


@pytest.mark.parametrize(("profile_id", "retrieval_profile"), PAIRS)
def test_actual_allocation_uses_candidate_adapter_and_distinct_selected_identity(
    index, ledger, profile_id, retrieval_profile
):
    transports = []
    with offline_network():
        owner = factory(index, ledger, profile_id, retrieval_profile, transports)
        try:
            ports = owner.for_case("neutral-selected-prefilter")
            assert ports.retrieval_profile == retrieval_profile
            assert ports.retriever.top_k == 25
            assert ports.retriever.adapter.selection_policy == "query_relevance_v1"
            assert retrieval_profile in owner.config["adapter_id"]
            assert retrieval_profile.removesuffix("_v1") in owner.config["retriever_id"]
            assert owner.core_binding["profile_id"] == profile_id
            assert set(owner.config) == {
                "model",
                "snapshot_id",
                "prompt_policy",
                "response_mode",
                "phase",
                "adapter_id",
                "retriever_id",
            }
            ports.cleanup()
        finally:
            owner.close()
    assert owner.active_clients == 0 and transports[0].close_calls == 1
    assert ledger.snapshot().settled_usd == ledger.snapshot().uncertain_usd == 0


@pytest.mark.parametrize("when", ["allocation", "presend"])
def test_new_selected_profile_drift_rejects_before_transport_or_provider(index, ledger, when):
    transports = []
    with offline_network():
        owner = factory(index, ledger, PREFILTER_DELIVERY_PROFILE_ID, PROFILE, transports)
        try:
            ports = owner.for_case("neutral-prefilter-drift") if when == "presend" else None
            before = ledger.snapshot()
            owner._retrieval_profile = "candidate_relevance_v1"
            if when == "allocation":
                with pytest.raises(ValueError, match=f"^{ERROR}$"):
                    owner.for_case("neutral-prefilter-drift")
                assert transports == []
            else:
                with pytest.raises(ReasoningStopped) as stopped:
                    ports.reasoner.analyze(
                        CaseState(case_id="neutral-prefilter-drift"),
                        "A neutral widget loses its state.",
                        EvidenceBundle(snapshot_id=index[1]),
                        context=ReasoningContext(
                            run_id="neutral-prefilter-run",
                            case_id="neutral-prefilter-drift",
                            case_revision=0,
                            attempt_index=1,
                        ),
                    )
                assert stopped.value.code == "ProviderRequestFailed"
                ports.cleanup()
            assert owner.observations_for_contexts(()) == []
            assert ledger.snapshot() == before
        finally:
            owner.close()
    assert owner.active_clients == 0
    assert all(transport.close_calls == 1 for transport in transports)
