"""Opt-in changes reach actual configured HTTP proposals, without live authority."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient
from test_evaluation_live import CountedMock, provider_response
from test_evaluation_live import index as index
from test_grounded_configuration_flags import configuration

from agent_app import live_backend
from agent_app.evaluation import live
from agent_app.llm.config import MetisConfig
from agent_app.reasoning.source_selection import SOURCE_SELECTION_REMINDER
from agent_app.testing.http_pilot_runtime import offline_network


@pytest.mark.parametrize(
    "investigation,reminder", [(False, False), (False, True), (True, False), (True, True)]
)
def test_new_flags_reach_wire_and_target_without_action(
    tmp_path, index, monkeypatch, investigation, reminder
):
    ledger, values = configuration(tmp_path, index, monkeypatch)
    values.update(
        METIS_GROUNDED_DECISION_CONTRACTS="true",
        METIS_GROUNDED_SOURCE_GAP_HANDOFF="true",
        METIS_GROUNDED_SOURCE_GAP_INVESTIGATION=str(investigation).lower(),
        METIS_GROUNDED_SOURCE_SELECTION_REMINDER=str(reminder).lower(),
    )
    wires = []

    def respond(request):
        wires.append(json.loads(request.content))
        return provider_response(request)

    monkeypatch.setattr(httpx, "HTTPTransport", lambda *a, **k: CountedMock(respond))
    with offline_network(), TestClient(live_backend.configured_app(values)) as client:
        response = client.post(
            "/cases/quality-case/messages",
            json={
                "message": "The supplied reproduction still needs investigation.",
                "turn_id": "current-turn",
                "expected_revision": 0,
                "reported_facts": [{"name": "streamlit_version", "value": "1.50.0"}],
                "unknowns": [],
            },
        )
        assert response.status_code == 200
        view = response.json()
        pending = view["pending"]
        assert pending["decision"] == "escalate"
        assert (
            "Investigation target from current USER records" in pending["user_draft"]
        ) is investigation
        assert (
            "Investigation target from current USER records" in pending["maintainer_summary"]
        ) is investigation
        assert (SOURCE_SELECTION_REMINDER in wires[0]["messages"][0]["content"]) is reminder
        assert json.loads(wires[0]["messages"][1]["content"])["decision_contracts"]
        assert view["actions"] == []
        assert pending["missing_info"] == [] and pending["next_question"] is None
    assert len(wires) == 1 and ledger.snapshot().reserved_usd == 0


@pytest.mark.parametrize(
    "name", ["METIS_GROUNDED_SOURCE_GAP_INVESTIGATION", "METIS_GROUNDED_SOURCE_SELECTION_REMINDER"]
)
def test_bad_flag_before_key_access(tmp_path, index, monkeypatch, name):
    _, values = configuration(tmp_path, index, monkeypatch)
    values[name] = "enabled"

    class Sensitive(dict):
        def __getitem__(self, key):
            if key == "METIS_API_KEY":
                raise AssertionError("credential read before invalid configuration")
            return super().__getitem__(key)

    with offline_network(), pytest.raises(ValueError):
        live.configured_factory(Sensitive(values))


def test_all_new_flags_preserve_ordinary_halt_before_key_access(tmp_path, index, monkeypatch):
    ledger, values = configuration(tmp_path, index, monkeypatch)
    ledger.halt()
    values.update(
        METIS_GROUNDED_SOURCE_GAP_HANDOFF="true",
        METIS_GROUNDED_SOURCE_GAP_INVESTIGATION="true",
        METIS_GROUNDED_SOURCE_SELECTION_REMINDER="true",
    )

    class Sensitive(dict):
        def __getitem__(self, key):
            if key == "METIS_API_KEY":
                raise AssertionError("credential read while halted")
            return super().__getitem__(key)

    with offline_network(), pytest.raises(ValueError, match="LiveLedgerHalted"):
        live.configured_factory(Sensitive(values))


@pytest.mark.parametrize(
    "field", ["grounded_source_gap_investigation", "grounded_source_selection_reminder"]
)
@pytest.mark.parametrize("bad", ["true", 1, None])
def test_flags_are_strict_bool(field, bad):
    with pytest.raises(ValueError):
        MetisConfig(
            api_key="synthetic",
            response_mode="grounded_plan",
            grounded_source_gap_handoff=True,
            **{field: bad},
        )


def test_investigation_requires_handoff_and_does_not_enable_live():
    with pytest.raises(ValueError):
        MetisConfig(
            api_key="synthetic",
            response_mode="grounded_plan",
            grounded_source_gap_investigation=True,
        )
    cfg = MetisConfig(
        api_key="synthetic",
        response_mode="grounded_plan",
        grounded_source_gap_handoff=True,
        grounded_source_gap_investigation=True,
        grounded_source_selection_reminder=True,
    )
    assert not cfg.live_enabled and cfg.continuation_id is None
