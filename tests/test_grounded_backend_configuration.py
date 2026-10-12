"""Explicit offline composition and truthful capability boundaries."""

import httpx
import pytest
from fastapi.testclient import TestClient

from agent_app.offline_backend import configured_app
from agent_app.ui_client import BackendClient, BackendError


def config(tmp_path):
    return {
        "AGENT_TRACKER_DB": str(tmp_path / "grounded.sqlite3"),
        "AGENT_REVIEWER_TOKEN": "synthetic-grounded-private-review-token",
        "AGENT_PILOT_REASONING": "grounded_fake_gateway",
    }


@pytest.mark.parametrize("mode", ["metis_grounded_live", "unknown", "", None])
def test_ordinary_launcher_rejects_live_or_unknown_reasoning_before_storage(tmp_path, mode):
    with pytest.raises(ValueError, match="^OfflineBackendConfigurationInvalid$"):
        configured_app({**config(tmp_path), "AGENT_PILOT_REASONING": mode})
    assert not (tmp_path / "grounded.sqlite3").exists()


def test_explicit_fake_backend_uses_grounded_request_without_real_provider(tmp_path, monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Real provider transport is forbidden")

    monkeypatch.setattr(httpx.HTTPTransport, "__init__", forbidden)
    with TestClient(configured_app(config(tmp_path))) as backend:
        client = BackendClient(backend)
        capabilities = client.discover_capabilities()
        assert capabilities.reasoning_label == "grounded_fake_gateway"
        assert capabilities.durable_reviews
        result = backend.post(
            "/cases/explicit-fake/messages",
            json={
                "message": "A widget loses its value.",
                "turn_id": "event-1",
                "expected_revision": 0,
                # The authored policy does not accept this as reasoning authority.
                "scenario": "answer",
            },
        )
        assert result.status_code == 200
        view = result.json()
        assert view["reasoning_label"] == "grounded_fake_gateway"
        assert view["quality_claim"] is False
        assert view["pending"]["decision"] == "ask"
        handoff = view["pending"]["review_handoff"]
        assert handoff["grounded_request"]["evidence"] == handoff["evidence"]
        assert handoff["grounded_request"]["case"] == handoff["case"]
        assert view["actions"] == []


@pytest.mark.parametrize(
    "label,mode",
    [
        ("unknown", "synthetic_offline_sqlite"),
        ("metis_grounded_live", "synthetic_offline_sqlite"),
        ("grounded_fake_gateway", "development_live_sqlite"),
    ],
)
def test_client_refuses_unknown_or_mislabelled_backend(tmp_path, label, mode):
    with TestClient(configured_app(config(tmp_path))) as backend:
        health = backend.get("/health").json()
    health.update(reasoning_label=label, mode=mode)
    with httpx.Client(
        base_url="http://local",
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=health)),
    ) as transport:
        with pytest.raises(BackendError) as error:
            BackendClient(transport).discover_capabilities()
        assert error.value.code == "BackendCapabilitiesInvalid"
