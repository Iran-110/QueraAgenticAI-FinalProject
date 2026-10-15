"""New policy through existing persistent acceptance; scripted provider only."""

import json
from types import SimpleNamespace

import httpx
import pytest
import test_enum_evidence as existing_acceptance
from test_configured_user_gap_catalog import composition as composition

from agent_app.evaluation import live
from agent_app.evaluation.runner import load_fixture
from agent_app.llm.config import MetisConfig
from agent_app.reasoning.source_selection import COMPLEMENTARY_SOURCE_POLICY
from agent_app.testing.complementary_replay import ROOT, replay_report
from agent_app.testing.enum_evidence import CASE_PATHS, PACKET_PATH, load_source_packet
from agent_app.testing.http_pilot_runtime import offline_network

ACTUAL_ADAPTER_TYPE = live.LiveEvaluationAdapters


@pytest.mark.parametrize("enabled", [False, True])
def test_policy_survives_existing_sqlite_repair_correction_stale_and_restart_retry(
    tmp_path, monkeypatch, enabled
):
    """Reuse the full existing acceptance, adding wire observation for this option."""
    original_config = existing_acceptance._config
    original_gateway = existing_acceptance.MetisGroundedPlanner
    bodies = []

    def config():
        return MetisConfig.model_validate(
            {
                **original_config().model_dump(warnings=False),
                "grounded_source_selection_reminder": True,
                "grounded_complementary_sources": enabled,
            }
        )

    class ObservedTransport(httpx.BaseTransport):
        def __init__(self, underlying):
            self.underlying = underlying

        def handle_request(self, request):
            body = json.loads(request.content)
            bodies.append(body)
            system, user = body["messages"]
            assert (COMPLEMENTARY_SOURCE_POLICY in system["content"]) is enabled
            assert COMPLEMENTARY_SOURCE_POLICY not in user["content"]
            payload = json.loads(user["content"])
            assert len(payload["request"]["evidence"]["hits"]) == 3
            assert "grounded_complementary_sources" not in payload["request"]
            assert body["response_format"] == {"type": "json_object"}
            return self.underlying.handle_request(request)

        def close(self):
            self.underlying.close()

    def gateway(configuration, ledger, *, transport):
        assert configuration.grounded_complementary_sources is enabled
        return original_gateway(configuration, ledger, transport=ObservedTransport(transport))

    monkeypatch.setattr(existing_acceptance, "_config", config)
    monkeypatch.setattr(existing_acceptance, "MetisGroundedPlanner", gateway)
    packet = load_source_packet(ROOT / PACKET_PATH)
    fixtures = {case: load_fixture(ROOT / path) for case, path in CASE_PATHS.items()}
    existing_acceptance.test_actual_http_gateway_keeps_complete_current_sources_and_rejects_old_approval(
        tmp_path, packet, fixtures, "fixed_guide_added"
    )
    assert len(bodies) == 4  # two bounded repair attempts on each of two turns
    assert [json.loads(b["messages"][1]["content"])["repair_issue_codes"] for b in bodies] == [
        [],
        ["invalid_grounded_plan"],
        [],
        ["invalid_grounded_plan"],
    ]


@pytest.mark.parametrize("raw,enabled", [(None, False), ("false", False), ("true", True)])
def test_normal_configured_factory_forwards_only_trusted_policy_and_distinct_identity(
    composition, raw, enabled
):
    values = composition.values
    values["METIS_GROUNDED_SOURCE_SELECTION_REMINDER"] = "true"
    if raw is not None:
        values["METIS_GROUNDED_COMPLEMENTARY_SOURCES"] = raw
    with offline_network():
        factory = live.configured_factory(values)
    configuration = factory.arguments["config"]
    assert configuration.grounded_complementary_sources is enabled
    assert composition.events[:3] == ["ledger", "budget", "index"]
    assert values.reads.count("METIS_API_KEY") == 1
    owner = SimpleNamespace(
        _config=configuration,
        _retrieval_profile="native",
        _top_k=3,
        _ask_source_background=False,
        _concise_user_draft=False,
        _snapshot="synthetic",
    )
    identifier = ACTUAL_ADAPTER_TYPE.config.fget(owner)["adapter_id"]
    assert identifier == "verified_chroma_metis_grounded_v1" + (
        "_complementary_sources_v1" if enabled else ""
    )


@pytest.mark.parametrize("raw", ["True", "1", "", None, True, 1])
def test_bad_trusted_flag_rejected_before_credential_lookup(composition, raw):
    composition.values["METIS_GROUNDED_COMPLEMENTARY_SOURCES"] = raw
    with offline_network(), pytest.raises(ValueError, match="^LiveEvaluationConfigurationInvalid$"):
        live.configured_factory(composition.values)
    assert "METIS_API_KEY" not in composition.values.reads
    assert composition.constructors == []


def test_policy_requires_reminder_before_credential_and_never_bypasses_halt(composition):
    composition.values["METIS_GROUNDED_COMPLEMENTARY_SOURCES"] = "true"
    with offline_network(), pytest.raises(ValueError, match="^LiveEvaluationConfigurationInvalid$"):
        live.configured_factory(composition.values)
    assert "METIS_API_KEY" not in composition.values.reads
    composition.halted = True
    composition.values.reads.clear()
    with offline_network(), pytest.raises(ValueError, match="^LiveLedgerHalted$"):
        live.configured_factory(composition.values)
    assert "METIS_GROUNDED_COMPLEMENTARY_SOURCES" not in composition.values.reads
    assert "METIS_API_KEY" not in composition.values.reads


def test_registered_offline_feasibility_is_reproducible_without_model_or_budget():
    report = replay_report()
    assert report == json.loads(
        (ROOT / "experiments/core_complementary_sources_v1/offline-replay-v1.json").read_bytes()
    )
    assert report["actual_sends"] == 0 and report["historical_contexts"] == 24
    assert report["model_quality_gain_claim"] is False
    assert report["human_usefulness"] is None
    assert all(row["joint_draft_chars"] == 7099 for row in report["authored_joint_replays"])
    assert len(report["complete_subset_controls"]) == 32
