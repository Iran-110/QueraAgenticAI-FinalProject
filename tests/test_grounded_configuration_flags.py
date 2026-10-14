"""Actual configured factory: opt-in prompt and handoff without live authority."""

import json
from decimal import Decimal

import httpx
import pytest
from fastapi.testclient import TestClient
from test_evaluation_live import KEY, CountedMock, provider_response
from test_evaluation_live import index as index

from agent_app import live_backend
from agent_app.evaluation import live
from agent_app.llm.budget import BudgetLedger
from agent_app.testing.http_pilot_runtime import offline_network


def configuration(tmp_path, index, monkeypatch):
    monkeypatch.setattr(live, "ROOT", tmp_path)
    (tmp_path / "runtime").mkdir()
    ledger = BudgetLedger.create(
        tmp_path / "runtime/budget.sqlite3", limit_usd=Decimal("1"), opening_spend_usd=Decimal("0")
    )
    return ledger, {
        "METIS_LIVE_ENABLED": "true",
        "METIS_API_KEY": KEY,
        "AGENT_EVAL_INDEX": str(index[0]),
        "AGENT_EVAL_SNAPSHOT": index[1],
        "AGENT_EVAL_MANIFEST_SHA256": index[2],
        "AGENT_TRACKER_DB": str(tmp_path / "tracker.sqlite3"),
        "AGENT_REVIEWER_TOKEN": "synthetic-private-grounded-configuration-review-token",
        "AGENT_REVIEWER_ID": "fixture-maintainer",
    }


@pytest.mark.parametrize(
    "prompt,handoff", [(False, False), (False, True), (True, False), (True, True)]
)
def test_configured_http_flags_reach_wire_and_current_proposal_independently(
    tmp_path, index, monkeypatch, prompt, handoff
):
    ledger, values = configuration(tmp_path, index, monkeypatch)
    values.update(
        METIS_GROUNDED_DECISION_CONTRACTS=str(prompt).lower(),
        METIS_GROUNDED_SOURCE_GAP_HANDOFF=str(handoff).lower(),
    )
    payloads = []
    transports = []

    def respond(request):
        payloads.append(json.loads(json.loads(request.content)["messages"][1]["content"]))
        return provider_response(request)

    def transport(*args, **kwargs):
        actual = CountedMock(respond)
        transports.append(actual)
        return actual

    monkeypatch.setattr(httpx, "HTTPTransport", transport)
    with offline_network(), TestClient(live_backend.configured_app(values)) as client:
        view = client.post(
            "/cases/flag-case/messages",
            json={
                "message": "The reported behaviour needs investigation.",
                "turn_id": "flag-turn",
                "expected_revision": 0,
                "reported_facts": [{"name": "streamlit_version", "value": "1.50.0"}],
                "unknowns": [],
            },
        )
        assert view.status_code == 200
        pending = view.json()["pending"]
        assert pending and pending["decision"] == "escalate"
        assert bool(payloads[0].get("decision_contracts")) is prompt
        assert ("Caller-declared source gaps" in pending["user_draft"]) is handoff
        assert ("Caller-declared source gaps" in pending["maintainer_summary"]) is handoff
        assert pending["missing_info"] == [] and pending["next_question"] is None
        assert view.json()["actions"] == []
    assert len(payloads) == len(transports) == 1
    assert transports[0].close_calls == 1 and ledger.snapshot().uncertain_usd == 0


@pytest.mark.parametrize(
    "name", ["METIS_GROUNDED_DECISION_CONTRACTS", "METIS_GROUNDED_SOURCE_GAP_HANDOFF"]
)
@pytest.mark.parametrize("bad", ["", "TRUE", "1", "false "])
def test_bad_configured_flag_fails_before_credential_lookup(
    tmp_path, index, monkeypatch, name, bad
):
    _, values = configuration(tmp_path, index, monkeypatch)
    values[name] = bad
    reads = []

    class Sensitive(dict):
        def get(self, key, *args):
            if key == "METIS_API_KEY":
                reads.append(key)
            return super().get(key, *args)

    with offline_network(), pytest.raises(ValueError):
        live.configured_factory(Sensitive(values))
    assert reads == []


def test_new_flags_do_not_remove_ordinary_halt(tmp_path, index, monkeypatch):
    ledger, values = configuration(tmp_path, index, monkeypatch)
    ledger.halt()
    values.update(
        METIS_GROUNDED_DECISION_CONTRACTS="true", METIS_GROUNDED_SOURCE_GAP_HANDOFF="true"
    )
    with offline_network(), pytest.raises(ValueError, match="LiveLedgerHalted"):
        live.configured_factory(values)


@pytest.mark.parametrize("bad", ["true", 1, None])
def test_source_gap_mode_is_a_strict_config_boolean(bad):
    from agent_app.llm.config import MetisConfig

    with pytest.raises(ValueError):
        MetisConfig(api_key=KEY, response_mode="grounded_plan", grounded_source_gap_handoff=bad)


def test_source_gap_mode_cannot_silently_enable_analysis_or_live():
    from agent_app.llm.config import MetisConfig

    with pytest.raises(ValueError):
        MetisConfig(api_key=KEY, grounded_source_gap_handoff=True)
    config = MetisConfig(
        api_key=KEY, response_mode="grounded_plan", grounded_source_gap_handoff=True
    )
    assert config.grounded_source_gap_handoff and not config.live_enabled
