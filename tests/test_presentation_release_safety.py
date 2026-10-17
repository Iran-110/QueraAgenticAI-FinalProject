"""Independent release failure/concurrency controls, using synthetic funded state.

Real final-v3 Chroma readers are disposable copies. HTTP provider responses are
mocked, user text is authored and no held-out/project runtime/private file is read.
These are integration controls, not model quality or OS process crash evidence.
"""

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import httpx
import pytest
from fastapi.testclient import TestClient
from test_budget_quarantine_scope import multiple_holds as multiple_holds
from test_budget_quarantine_scope import old_rows
from test_core_delivery_http import authored_response
from test_presentation_runtime import AUTH, body
from test_presentation_runtime import final_v3 as final_v3
from test_presentation_runtime import registered as registered

from agent_app import presentation_runtime as runtime
from agent_app.llm.budget import LedgerUnavailable
from agent_app.testing.http_pilot_runtime import offline_network


def create(registered, handler):
    _, path, _, values = registered
    return runtime.configured_app(
        path, values, transport_factory=lambda: httpx.MockTransport(handler)
    )


def post(client, case=0, revision=0, turn="first", **updates):
    return client.post(
        f"/cases/synthetic-presentation-{case}/messages",
        json=body(
            "An authored question about st.button and Session State.", revision, turn, **updates
        ),
        headers=AUTH,
    )


def test_same_event_retry_while_provider_runs_never_allocates_again(registered):
    ledger, _, protocol, _ = registered
    started, release = Event(), Event()
    records = []

    def handler(request):
        started.set()
        assert release.wait(10)
        return authored_response(request, records)

    app = create(registered, handler)
    owner = app.state.presentation_runtime
    try:
        with TestClient(app) as client, offline_network(), ThreadPoolExecutor(1) as pool:
            first = pool.submit(post, client)
            try:
                assert started.wait(10)
                retry = post(client)
                assert retry.status_code == 200
                assert retry.json()["intake"]["replayed"]
                assert retry.json()["case_revision"] == 1
                assert retry.json()["pending"] is None
                assert ledger.quarantine_scope_status(protocol["scope_id"]).consumed_requests == 1
            finally:
                release.set()
            complete = first.result(timeout=10)
            assert complete.status_code == 200 and complete.json()["pending"] is not None
            assert len(records) == 1
            current = client.get("/cases/synthetic-presentation-0").json()
            assert current["pending"] == complete.json()["pending"]
    finally:
        owner.close()


def test_parallel_different_case_is_preserved_but_pending_budget_refuses_model(registered):
    ledger, _, protocol, _ = registered
    started, release = Event(), Event()
    records = []

    def handler(request):
        started.set()
        assert release.wait(10)
        return authored_response(request, records)

    app = create(registered, handler)
    owner = app.state.presentation_runtime
    try:
        with TestClient(app) as client, offline_network(), ThreadPoolExecutor(1) as pool:
            first = pool.submit(post, client)
            try:
                assert started.wait(10)
                parallel = post(client, case=1, turn="parallel")
                assert parallel.status_code == 200
                view = parallel.json()
                assert view["case_revision"] == 1
                assert view["pending"] is None
                assert view["run_outcome"]["status"] == "core_stopped"
                assert view["run_outcome"]["error_code"] == "AdapterSetupFailed"
                assert ledger.quarantine_scope_status(protocol["scope_id"]).consumed_requests == 1
            finally:
                release.set()
            assert first.result(timeout=10).json()["pending"] is not None
            assert len(records) == 1
            # This exact failed ingress is recovery-only; it does not resume.
            retried = post(client, case=1, turn="parallel").json()
            assert retried["intake"]["replayed"] and retried["pending"] is None
            assert len(records) == 1
    finally:
        owner.close()


def test_correction_during_provider_call_invalidates_old_candidate(registered):
    ledger, _, protocol, _ = registered
    started, release = Event(), Event()
    records = []

    def handler(request):
        started.set()
        assert release.wait(10)
        return authored_response(request, records)

    app = create(registered, handler)
    owner = app.state.presentation_runtime
    try:
        with TestClient(app) as client, offline_network(), ThreadPoolExecutor(1) as pool:
            first = pool.submit(post, client)
            try:
                assert started.wait(10)
                corrected = post(
                    client,
                    revision=1,
                    turn="correction-during-run",
                    reported_facts=[{"name": "streamlit_version", "value": "1.49.0"}],
                )
                assert corrected.status_code == 200
                assert corrected.json()["case_revision"] == 2
                assert corrected.json()["pending"] is None
            finally:
                release.set()
            assert first.result(timeout=10).status_code == 200
            current = client.get("/cases/synthetic-presentation-0").json()
            assert current["case_revision"] == 2 and current["pending"] is None
            assert [f["value"] for f in current["facts"] if f["status"] == "active"] == ["1.49.0"]
            assert current["actions"] == []
            assert len(records) == 1
            assert ledger.quarantine_scope_status(protocol["scope_id"]).consumed_requests == 1
    finally:
        owner.close()


@pytest.mark.parametrize("fault", ["missing_usage", "wrong_model", "http_error", "cost_overrun"])
def test_provider_accounting_fault_stops_scope_without_replay(registered, fault):
    ledger, _, protocol, _ = registered
    historical = old_rows(protocol["ledger_path"])
    records = []

    def handler(request):
        response = authored_response(request, records)
        payload = json.loads(response.content)
        if fault == "missing_usage":
            del payload["usage"]
        elif fault == "wrong_model":
            payload["model"] = "gpt-4.1-mini"
        elif fault == "cost_overrun":
            payload["usage"] = {
                "prompt_tokens": 100000,
                "completion_tokens": 1,
                "total_tokens": 100001,
            }
        return httpx.Response(401 if fault == "http_error" else 200, json=payload)

    app = create(registered, handler)
    owner = app.state.presentation_runtime
    try:
        with TestClient(app) as client, offline_network():
            first = post(client)
            assert first.status_code == 200 and first.json()["pending"] is None
            assert len(records) == 1
            status = ledger.quarantine_scope_status(protocol["scope_id"])
            assert not status.active and status.terminal_status == "revoked"
            replay = post(client).json()
            assert replay["intake"]["replayed"] and replay["pending"] is None
            assert len(records) == 1
            after = post(client, revision=1, turn="after-fault").json()
            assert after["pending"] is None and len(records) == 1
    finally:
        owner.close()
    assert ledger.snapshot().halted
    assert old_rows(protocol["ledger_path"]) == historical


def test_post_response_settlement_failure_keeps_reservation_and_blocks_send(
    registered, monkeypatch
):
    ledger, _, protocol, _ = registered
    records = []
    app = create(registered, lambda request: authored_response(request, records))
    owner = app.state.presentation_runtime

    def settlement_unavailable(*_args, **_kwargs):
        raise LedgerUnavailable()

    monkeypatch.setattr(owner.ledger, "settle", settlement_unavailable)
    try:
        with TestClient(app) as client, offline_network():
            first = post(client)
            assert first.status_code == 200 and first.json()["pending"] is None
            assert len(records) == 1
            observed = owner.observations[0]
            assert observed["ledger"]["status"] == "reserved"
            status = ledger.quarantine_scope_status(protocol["scope_id"])
            assert not status.active and status.block_reason == "PendingRequest"
            assert post(client).json()["intake"]["replayed"]
            assert post(client, revision=1, turn="after-storage-fault").json()["pending"] is None
            assert len(records) == 1
    finally:
        owner.close()


def test_malformed_compact_output_uses_only_second_registered_attempt(registered):
    ledger, _, protocol, _ = registered
    records = []

    def handler(request):
        response = authored_response(request, records)
        if len(records) == 1:
            payload = json.loads(response.content)
            payload["choices"][0]["message"]["content"] = '{"decision":"ask"}'
            return httpx.Response(200, json=payload)
        return response

    app = create(registered, handler)
    owner = app.state.presentation_runtime
    try:
        with TestClient(app) as client, offline_network():
            first = post(client)
            assert first.status_code == 200 and first.json()["pending"] is not None
            assert len(records) == 2
            assert [o["context"]["attempt_index"] for o in owner.observations] == [1, 2]
            assert all(o["ledger"]["status"] == "settled" for o in owner.observations)
            assert owner.observations[0]["wire_observation"]["wire_schema_valid"] is False
            assert owner.observations[1]["wire_observation"]["wire_schema_valid"] is True
            assert ledger.quarantine_scope_status(protocol["scope_id"]).consumed_requests == 2
            assert post(client).json()["intake"]["replayed"]
            assert len(records) == 2
    finally:
        owner.close()
