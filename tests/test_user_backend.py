"""User live backend: separate capped ledger, selected profile, mock provider only."""

import json
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from test_evaluation_live import KEY, CountedMock, provider_response
from test_evaluation_live import index as index

from agent_app import user_backend
from agent_app.llm.budget import BudgetLedger
from agent_app.orchestration.core_delivery import PREFILTER_DELIVERY_PROFILE_ID
from agent_app.testing.http_pilot_runtime import offline_network

TOKEN = "synthetic-private-review-token-for-user-test"


def values(index, **changes):
    return {
        "METIS_LIVE_ENABLED": "true",
        "METIS_API_KEY": KEY,
        "AGENT_EVAL_INDEX": str(index[0]),
        "AGENT_EVAL_SNAPSHOT": index[1],
        "AGENT_EVAL_MANIFEST_SHA256": index[2],
        **changes,
    }


@pytest.fixture
def user_ledger(tmp_path):
    return BudgetLedger.create(
        tmp_path / "user-budget.sqlite3", limit_usd=Decimal("1"), opening_spend_usd=Decimal("0")
    )


def test_user_message_is_reserved_and_settled_on_the_user_ledger(tmp_path, index, user_ledger):
    transports = []

    def allocate():
        transports.append(CountedMock(provider_response))
        return transports[-1]

    app = user_backend.configured_user_app(
        values(
            index,
            AGENT_TRACKER_DB=str(tmp_path / "cases.sqlite3"),
            AGENT_REVIEWER_TOKEN=TOKEN,
        ),
        ledger_path=user_ledger._path,
        transport_factory=allocate,
    )
    with offline_network(), TestClient(app) as client:
        view = client.post(
            "/cases/user-case/messages",
            json={
                "message": "My multiselect loses its value. The parent callback is not provided.",
                "turn_id": "user-turn",
                "expected_revision": 0,
                "scenario": "answer",
                "reported_facts": [{"name": "streamlit_version", "value": "1.50.0"}],
                "unknowns": ["parent_callback_code"],
            },
        ).json()
        assert "pending" in view, view
        assert TOKEN not in json.dumps(view) and KEY not in json.dumps(view)
    snapshot = user_ledger.snapshot()
    assert transports and snapshot.settled_usd > 0
    assert snapshot.reserved_usd == snapshot.uncertain_usd == 0


def test_adapters_use_the_selected_profile(index, user_ledger):
    with offline_network():
        factory = user_backend.user_adapters(values(index), ledger_path=user_ledger._path)
    try:
        assert factory.core_binding["profile_id"] == PREFILTER_DELIVERY_PROFILE_ID
        assert factory.ledger._path == user_ledger._path
    finally:
        factory.close()


def test_rejects_disabled_missing_team_or_oversized_ledger(tmp_path, index, user_ledger):
    with pytest.raises(ValueError, match="^LiveCallsDisabled$"):
        user_backend.user_adapters(
            values(index, METIS_LIVE_ENABLED="false"), ledger_path=user_ledger._path
        )
    with pytest.raises(ValueError, match="^UserApiKeyMissing$"):
        user_backend.user_adapters(values(index, METIS_API_KEY=""), ledger_path=user_ledger._path)
    for path in (tmp_path / "missing.sqlite3", user_backend.TEAM_LEDGER):
        with pytest.raises(ValueError, match="^UserLedgerUnavailable$"):
            user_backend.user_adapters(values(index), ledger_path=path)
    large = BudgetLedger.create(
        tmp_path / "large.sqlite3", limit_usd=Decimal("2"), opening_spend_usd=Decimal("0")
    )
    with pytest.raises(ValueError, match="^UserLedgerLimitInvalid$"):
        user_backend.user_adapters(values(index), ledger_path=large._path)


def test_halted_user_ledger_stops_before_any_provider_client(index, user_ledger):
    user_ledger.halt()
    with offline_network(), pytest.raises(ValueError, match="^LiveLedgerHalted$"):
        user_backend.user_adapters(
            values(index),
            ledger_path=user_ledger._path,
            transport_factory=lambda: pytest.fail("No provider client"),
        )
