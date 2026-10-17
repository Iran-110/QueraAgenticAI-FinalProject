"""Independent pre-read and pre-dispatch regression controls; synthetic only."""

from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from test_budget_quarantine_scope import multiple_holds as multiple_holds
from test_core_delivery_http import authored_response
from test_presentation_runtime import AUTH, body
from test_presentation_runtime import final_v3 as final_v3
from test_presentation_runtime import registered as registered

from agent_app import presentation_runtime as runtime
from agent_app.testing.http_pilot_runtime import offline_network


def test_private_protocol_name_is_rejected_before_payload_read(tmp_path, monkeypatch):
    reads = []
    original = Path.read_bytes

    def observed(path):
        reads.append(path)
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", observed)
    # No dotenv file is created or opened: a public-role validator should reject
    # this name before attempting its first content read, even if nonexistent.
    with pytest.raises(ValueError, match="PresentationConfigurationRejected"):
        runtime.read_protocol(tmp_path / ".env")
    assert reads == []


def test_mutation_between_reservation_and_dispatch_blocks_http(registered, monkeypatch):
    ledger, path, _, values = registered
    records = []
    app = runtime.configured_app(
        path,
        values,
        transport_factory=lambda: httpx.MockTransport(
            lambda request: authored_response(request, records)
        ),
    )
    owner = app.state.presentation_runtime
    reserve = ledger.reserve

    def reserve_and_mutate(**kwargs):
        result = reserve(**kwargs)
        owner.binding["retrieval_profile"] = "native"
        return result

    # MetisReasoner uses the runtime's own ledger instance. Swap its reserve
    # method only after construction, without altering protocol/source files.
    monkeypatch.setattr(owner.ledger, "reserve", reserve_and_mutate)
    try:
        with TestClient(app) as client, offline_network():
            result = client.post(
                "/cases/synthetic-presentation-0/messages",
                json=body("What does st.button return?", 0, "reservation-mutation"),
                headers=AUTH,
            )
            assert result.status_code == 200
            assert result.json()["pending"] is None
            assert records == []
    finally:
        owner.close()
