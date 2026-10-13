"""Case-aware persistent composition; real index/SQLite, mandatory mock wires."""

import json
import os
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import streamlit as st
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest
from test_evaluation_live import CALLBACK, KEY, adapters, provider_response
from test_evaluation_live import index as index
from test_evaluation_live import ledger as ledger

from agent_app import api, live_backend, ui_client
from agent_app.persistent_api import create_app
from agent_app.retrieval.pilot_corpus import MANIFEST_NAME
from agent_app.testing.http_pilot_runtime import offline_network
from agent_app.tracker.sqlite_tracker import SQLiteCaseTracker

TOKEN = "synthetic-private-review-token-for-local-test"
REVIEWERS = {"fixture-maintainer": TOKEN}
AUTH = {"Authorization": "Bearer " + TOKEN}


def message(turn_id, revision, **changes):
    return {
        "message": "My multiselect loses its value. The parent callback is not provided.",
        "turn_id": turn_id,
        "expected_revision": revision,
        "scenario": "answer",
        "reported_facts": [{"name": "streamlit_version", "value": "1.50.0"}],
        "unknowns": ["parent_callback_code"],
        **changes,
    }


def decision(pending, review_id, kind="approve", **changes):
    return {
        "proposal_id": pending["proposal_id"],
        "case_revision": pending["case_revision"],
        "expected_handoff_sha256": pending["review_handoff"]["handoff_sha256"],
        "review_id": review_id,
        "decision": kind,
        **changes,
    }


def test_two_case_live_ports_bind_committed_state_and_replay_allocates_nothing(
    tmp_path, index, ledger
):
    seen, bound = [], []

    def respond(request):
        prepared = json.loads(json.loads(request.content)["messages"][1]["content"])["request"]
        seen.append(prepared)
        return provider_response(request, question="parent_callback_code")

    with offline_network():
        factory, transports = adapters(index, ledger, respond, user_gaps=(CALLBACK,))
        database = tmp_path / "persistent-live.sqlite3"

        def ports(case, scenario):
            bound.append((case.case_id, case.case_revision, scenario))
            assert case.pending_proposal_id is None
            return factory.for_case(case.case_id)

        def app():
            return create_app(
                SQLiteCaseTracker(database, reviewer_tokens=REVIEWERS),
                reviewer_tokens=REVIEWERS,
                case_adapters=ports,
                retrieval_label="local_chroma_hash",
                reasoning_label="metis_grounded_live",
            )

        with TestClient(app()) as client:
            payload = message("case-a-first", 0)
            first = client.post("/cases/case-a/messages", json=payload).json()
            untouched = client.get("/cases/case-b").json()
            second = client.post("/cases/case-b/messages", json=message("case-b-first", 0)).json()
            assert untouched["case_revision"] == 0
            assert first["pending"]["missing_info"] == ["parent_callback_code"]
            assert second["pending"]["review_handoff"]["case"]["case_id"] == "case-b"
            assert bound == [("case-a", 1, "answer"), ("case-b", 1, "answer")]
            assert [item["case"]["case_id"] for item in seen] == ["case-a", "case-b"]
            old = first["pending"]
            correction = client.post(
                "/cases/case-a/messages",
                json=message(
                    "case-a-correction",
                    1,
                    message="Correction: Streamlit is 1.49.0, same environment and missing callback.",
                    reported_facts=[{"name": "streamlit_version", "value": "1.49.0"}],
                ),
            ).json()
            assert bound[-1] == ("case-a", 2, "answer")
            current = correction["pending"]
            assert current["proposal_id"] != old["proposal_id"]
            assert (
                next(
                    fact["value"]
                    for fact in seen[-1]["case"]["facts"]
                    if fact["name"] == "streamlit_version" and fact["status"] == "active"
                )
                == "1.49.0"
            )
            stale = client.post(
                "/cases/case-a/decision", json=decision(old, "stale-review"), headers=AUTH
            )
            assert stale.status_code == 409
            assert client.get("/cases/case-b").json() == second
            approved = client.post(
                "/cases/case-a/decision",
                json=decision(current, "stable-approval"),
                headers=AUTH,
            )
            assert approved.status_code == 200
            assert len(approved.json()["actions"]) == 1
            counted = len(transports), len(seen), len(bound)
            replay = client.post("/cases/case-a/messages", json=payload)
            assert replay.status_code == 200 and replay.json()["intake"]["replayed"]
            assert (len(transports), len(seen), len(bound)) == counted
        with TestClient(app()) as client:
            retried = client.post(
                "/cases/case-a/decision",
                json=decision(current, "stable-approval"),
                headers=AUTH,
            )
            assert retried.status_code == 200 and retried.json()["review"]["replayed"]
            assert len(retried.json()["actions"]) == 1
            assert (len(transports), len(seen), len(bound)) == counted
        assert factory.active_clients == 0
        assert all(transport.close_calls == 1 for transport in transports)
        factory.close()
        assert all(transport.close_calls == 1 for transport in transports)
        assert TOKEN not in json.dumps(correction) and KEY not in json.dumps(correction)


def test_case_adapter_gets_detached_snapshot_and_legacy_configuration_cannot_compete(tmp_path):
    database = tmp_path / "case-aware.sqlite3"
    tracker = SQLiteCaseTracker(database, reviewer_tokens=REVIEWERS)
    captured = []

    def case_ports(case, scenario):
        captured.append(deepcopy(case.model_dump(mode="json")))
        object.__setattr__(case, "case_revision", 99)
        return api._adapters(scenario)

    app = create_app(tracker, reviewer_tokens=REVIEWERS, case_adapters=case_ports)
    with offline_network(), TestClient(app) as client:
        view = client.post("/cases/snapshot-case/messages", json=message("snapshot-turn", 0)).json()
    assert captured[0]["case_revision"] == 1 and view["case_revision"] == 1
    assert view["pending"]["review_handoff"]["case"]["case_revision"] == 1
    with pytest.raises(ValueError, match="Invalid persistent HTTP configuration"):
        create_app(
            tracker,
            reviewer_tokens=REVIEWERS,
            case_adapters=case_ports,
            adapters=api._adapters,
        )
    with pytest.raises(ValueError, match="Invalid persistent HTTP configuration"):
        create_app(tracker, reviewer_tokens=REVIEWERS, case_adapters="invalid")


def test_wrong_case_gateway_binding_stops_without_provider_request(tmp_path, index, ledger):
    with offline_network():
        factory, transports = adapters(index, ledger)
        app = create_app(
            SQLiteCaseTracker(tmp_path / "wrong-binding.sqlite3", reviewer_tokens=REVIEWERS),
            reviewer_tokens=REVIEWERS,
            case_adapters=lambda _case, _scenario: factory.for_case("different-case"),
            reasoning_label="metis_grounded_live",
        )
        with TestClient(app) as client:
            view = client.post("/cases/actual-case/messages", json=message("actual-turn", 0)).json()
    assert view["pending"] is None and factory.active_clients == 0
    assert ledger.snapshot().settled_usd == 0
    assert not factory.observations_for_contexts(())
    assert len(transports) == 1 and transports[0].close_calls == 1


def test_live_backend_uses_same_case_aware_api_and_closes_on_shutdown(tmp_path, index, ledger):
    with offline_network():
        factory, transports = adapters(index, ledger)
        configured = live_backend.configured_app(
            {
                "AGENT_TRACKER_DB": str(tmp_path / "live-backend.sqlite3"),
                "AGENT_REVIEWER_TOKEN": TOKEN,
            },
            adapters_factory=lambda _values: factory,
        )
        with TestClient(configured) as client:
            health = client.get("/health").json()
            assert health["mode"] == "development_live_sqlite"
            assert health["reasoning_label"] == "metis_grounded_live"
            view = client.post("/cases/live-client/messages", json=message("live-event", 0)).json()
            assert view["pending"]["decision"] == "escalate"
            assert TOKEN not in json.dumps(view) and KEY not in json.dumps(view)
        with pytest.raises(ValueError, match="LiveEvaluationFactoryClosed"):
            factory.for_case("another-case")
        assert len(transports) == 1 and transports[0].close_calls == 1


def test_halted_live_configuration_stops_before_creating_tracker_or_allocating_ports(
    tmp_path, index, ledger
):
    ledger.halt()
    database = tmp_path / "must-not-exist.sqlite3"
    with offline_network(), pytest.raises(ValueError, match="^LiveBackendConfigurationInvalid$"):
        live_backend.configured_app(
            {"AGENT_TRACKER_DB": str(database), "AGENT_REVIEWER_TOKEN": TOKEN},
            adapters_factory=lambda _values: adapters(index, ledger)[0],
        )
    assert not database.exists()


@pytest.mark.parametrize("alias", ["same_path", "hardlink", "symlink"])
def test_tracker_configuration_cannot_share_the_model_ledger_file(tmp_path, index, ledger, alias):
    database = ledger._path
    if alias != "same_path":
        database = tmp_path / "aliased-case-database.sqlite3"
        try:
            if alias == "hardlink":
                os.link(ledger._path, database)
            else:
                database.symlink_to(ledger._path)
        except OSError:
            pytest.skip("This host does not allow creating a test file alias.")
    before = ledger._path.read_bytes()
    with offline_network():
        factory, transports = adapters(index, ledger)
        with pytest.raises(ValueError, match="^LiveBackendConfigurationInvalid$"):
            live_backend.configured_app(
                {"AGENT_TRACKER_DB": str(database), "AGENT_REVIEWER_TOKEN": TOKEN},
                adapters_factory=lambda _values: factory,
            )
    assert ledger._path.read_bytes() == before and transports == []
    with pytest.raises(ValueError, match="LiveEvaluationFactoryClosed"):
        factory.for_case("case-after-rejection")


@pytest.mark.parametrize("filename", ["chroma.sqlite3", MANIFEST_NAME])
@pytest.mark.parametrize("alias", ["same_path", "hardlink", "symlink", "inside_new"])
def test_tracker_configuration_cannot_modify_verified_index_storage(
    tmp_path, index, ledger, filename, alias
):
    source = index[0] / filename
    database = source
    if alias == "inside_new":
        database = index[0] / "accidental-tracker.sqlite3"
    elif alias != "same_path":
        database = tmp_path / "aliased-index.sqlite3"
        try:
            if alias == "hardlink":
                os.link(source, database)
            else:
                database.symlink_to(source)
        except OSError:
            pytest.skip("This host does not allow creating a test file alias.")
    with offline_network():
        factory, transports = adapters(index, ledger)
        # Index verification itself may touch Chroma; compare after construction.
        before = source.read_bytes()
        with pytest.raises(ValueError, match="^LiveBackendConfigurationInvalid$"):
            live_backend.configured_app(
                {"AGENT_TRACKER_DB": str(database), "AGENT_REVIEWER_TOKEN": TOKEN},
                adapters_factory=lambda _values: factory,
            )
    assert source.read_bytes() == before and transports == []
    if alias == "inside_new":
        assert not database.exists()
    with pytest.raises(ValueError, match="LiveEvaluationFactoryClosed"):
        factory.for_case("case-after-rejection")


def test_case_ports_cleanup_failure_persists_safe_outcome_without_proposal(tmp_path):
    def ports(_case, scenario):
        def cleanup():
            raise RuntimeError("private-case-adapter-secret")

        return replace(api._adapters(scenario), cleanup=cleanup)

    app = create_app(
        SQLiteCaseTracker(tmp_path / "cleanup-case.sqlite3", reviewer_tokens=REVIEWERS),
        reviewer_tokens=REVIEWERS,
        case_adapters=ports,
    )
    with offline_network(), TestClient(app) as client:
        view = client.post("/cases/cleanup-case/messages", json=message("cleanup-turn", 0)).json()
    assert view["pending"] is None
    assert view["run_outcome"]["error_code"] == "AdapterCleanupFailed"
    assert "private-case-adapter-secret" not in json.dumps(view)


def test_real_page_uses_case_bound_backend_and_retries_original_review_after_recreation(
    tmp_path, monkeypatch, index, ledger
):
    """The actual page with an explicitly injected mock provider, never paid UI."""
    state = SimpleNamespace(backend=None, loss=False, reviews=[], transports=[])
    configuration = {
        "AGENT_TRACKER_DB": str(tmp_path / "page.sqlite3"),
        "AGENT_REVIEWER_TOKEN": TOKEN,
    }
    st.cache_resource.clear()

    def backend():
        factory, transports = adapters(index, ledger)
        state.transports.append(transports)
        return TestClient(
            live_backend.configured_app(configuration, adapters_factory=lambda _values: factory)
        )

    class Transport:
        def request(self, method, path, **arguments):
            response = state.backend.request(method, path, **arguments)
            if method == "POST" and path.endswith("/decision"):
                state.reviews.append(deepcopy(arguments["json"]))
                if state.loss and response.status_code == 200:
                    state.loss = False
                    raise httpx.ReadTimeout("Synthetic committed acknowledgment lost")
            return response

    try:
        with offline_network():
            monkeypatch.setattr(
                ui_client,
                "make_client",
                lambda: ui_client.BackendClient(Transport(), reviewer_token=TOKEN),
            )
            state.backend = backend().__enter__()
            page = AppTest.from_file(
                str(Path(__file__).resolve().parents[1] / "app_pages/assistant.py"),
                default_timeout=15,
            ).run()
            assert not page.exception
            assert "scenario" not in [item.key for item in page.sidebar.selectbox]
            page.chat_input[0].set_value(
                "My widget resets; the Streamlit version is unknown."
            ).run()
            assert not page.exception
            case_id = page.session_state.case_id
            initial = state.backend.get(f"/cases/{case_id}").json()
            assert initial["pending"]["missing_info"] == ["streamlit_version"]
            assert initial["pending"]["review_handoff"]["case"]["case_id"] == case_id
            page.button(key="approve").click().run()
            page.text_input(key="version_reply").set_value("1.50.0")
            next(item for item in page.button if item.label == "Send reply").click().run()
            assert not page.exception
            known = state.backend.get(f"/cases/{case_id}").json()
            assert known["pending"]["decision"] == "escalate" and known["case_revision"] == 2
            state.loss = True
            page.button(key="approve").click().run()
            assert not page.exception
            original = page.session_state.unsent_reviews[case_id].payload()
            receipt = state.backend.get(f"/cases/{case_id}").json()["review"]
            generation = page.session_state.form_gen
            page.text_area(key=f"update_message_{generation}").set_value(
                "Correction: Streamlit is 1.49.0 in the same environment."
            )
            page.text_input(key=f"fact_name_0_{generation}").set_value("streamlit_version")
            page.text_input(key=f"fact_value_0_{generation}").set_value("1.49.0")
            next(item for item in page.button if item.label == "Send update").click().run()
            assert not page.exception and page.button(key="approve").disabled
            corrected = state.backend.get(f"/cases/{case_id}").json()
            assert corrected["case_revision"] == 3
            assert corrected["pending"]["proposal_id"] != known["pending"]["proposal_id"]
            assert page.session_state.unsent_reviews[case_id].payload() == original
            state.backend.__exit__(None, None, None)
            state.backend = backend().__enter__()
            allocated = sum(len(items) for items in state.transports)
            next(item for item in page.button if item.label == "Retry review").click().run()
            assert not page.exception and page.session_state.unsent_reviews == {}
            assert state.reviews[-1] == original
            after = state.backend.get(f"/cases/{case_id}").json()
            assert after["review"] == receipt and after["pending"] == corrected["pending"]
            assert len(after["actions"]) == 2 and after["case_revision"] == 3
            assert sum(len(items) for items in state.transports) == allocated
            assert not page.button(key="approve").disabled
            assert len(SQLiteCaseTracker(configuration["AGENT_TRACKER_DB"]).comments(case_id)) == 2
            assert TOKEN not in repr(page.session_state) and KEY not in repr(page.session_state)
    finally:
        if state.backend is not None:
            state.backend.__exit__(None, None, None)
        st.cache_resource.clear()
    assert all(transport.close_calls == 1 for items in state.transports for transport in items)
