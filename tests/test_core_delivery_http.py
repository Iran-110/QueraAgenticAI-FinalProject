"""Actual selected factory/backend on disposable index/SQLite and mock wires.

Plans below are authored neutral integration controls, not model-quality scores.
The primary ledger/index, real credentials and held-out fixtures are never used.
"""

import json
from copy import deepcopy
from decimal import Decimal

import httpx
import pytest
from fastapi.testclient import TestClient
from test_candidate_live_profile import observe_native_queries
from test_evaluation_live import KEY, CountedMock
from test_persistent_live_factory import decision, message
from test_real_index_probe import ARMS
from test_real_index_probe import native_indexes as native_indexes

from agent_app import live_backend
from agent_app.contracts import EvidenceBundle, GroundedRequest, ProposalHandoff
from agent_app.evaluation import live, runner
from agent_app.llm.budget import BudgetLedger
from agent_app.orchestration import service
from agent_app.orchestration.core_delivery import (
    DELIVERY_PROFILE_ID,
    delivery_recipe,
    validate_delivery_configuration,
)
from agent_app.orchestration.handoff import validate_handoff
from agent_app.reasoning.compact_plan import expand_compact_plan
from agent_app.reasoning.grounding import render_grounded_plan
from agent_app.reasoning.source_selection import SOURCE_SELECTION_REMINDER
from agent_app.testing.http_pilot_runtime import offline_network

TOKEN = "synthetic-core-delivery-review-token"
AUTH = {"Authorization": "Bearer " + TOKEN}
PROFILE = "candidate_relevance_v1"


class ObservedValues(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.key_reads = []

    def get(self, key, *args):
        if key == "METIS_API_KEY":
            self.key_reads.append(key)
        return super().get(key, *args)

    def __getitem__(self, key):
        if key == "METIS_API_KEY":
            self.key_reads.append(key)
        return super().__getitem__(key)


def runtime(tmp_path, native_indexes, monkeypatch):
    (tmp_path / "runtime").mkdir()
    ledger = BudgetLedger.create(
        tmp_path / "runtime/budget.sqlite3",
        limit_usd=Decimal("1"),
        opening_spend_usd=Decimal("0"),
    )
    monkeypatch.setattr(live, "ROOT", tmp_path)
    index = native_indexes[ARMS[1]]
    values = ObservedValues(
        {
            "AGENT_CORE_PROFILE": DELIVERY_PROFILE_ID,
            "METIS_LIVE_ENABLED": "true",
            "METIS_API_KEY": KEY,
            "AGENT_EVAL_INDEX": index["path"],
            "AGENT_EVAL_SNAPSHOT": index["snapshot_id"],
            "AGENT_EVAL_MANIFEST_SHA256": index["manifest_sha256"],
            "AGENT_TRACKER_DB": str(tmp_path / "selected-tracker.sqlite3"),
            "AGENT_REVIEWER_TOKEN": TOKEN,
            "AGENT_REVIEWER_ID": "fixture-maintainer",
        }
    )
    return ledger, values


def authored_response(request, records):
    body = json.loads(request.content)
    payload = json.loads(body["messages"][1]["content"])
    current = payload["request"]
    question = next((gap for gap in current["gaps"] if gap["kind"] == "user"), None)
    plan = {
        "context_sha256": current["context_sha256"],
        "decision": "ask" if question else "escalate",
        "sources": [0] if current["evidence"]["hits"] else [],
    }
    if question:
        plan["question_name"] = question["name"]
    records.append({"body": body, "payload": payload, "plan": plan})
    return httpx.Response(
        200,
        json={
            "model": "gpt-4o-mini-2024-07-18",
            "usage": {"prompt_tokens": 125, "completion_tokens": 75, "total_tokens": 200},
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": json.dumps(plan)},
                }
            ],
        },
    )


def observe_engines(monkeypatch):
    constructed = []
    original = service.SupportEngine

    def observe(*args, **kwargs):
        engine = original(*args, **kwargs)
        constructed.append(
            {
                "top_k": engine.top_k,
                "evidence_scope": engine.evidence_scope,
                "retrieval_candidate_multiplier": engine.retrieval_candidate_multiplier,
                "evidence_utf8_budget_bytes": engine.evidence_utf8_budget_bytes,
                "repair_repeated_queries": engine.repair_repeated_queries,
                "proposal_checks": engine.proposal_checks,
                "run_limits": engine.limits.model_dump(mode="json"),
            }
        )
        return engine

    monkeypatch.setattr(service, "SupportEngine", observe)
    return constructed


def assert_legacy_handoff(view, record):
    pending = view["pending"]
    assert pending is not None
    handoff = validate_handoff(ProposalHandoff.model_validate(pending["review_handoff"]))
    supplied = GroundedRequest.model_validate(record["payload"]["request"])
    assert handoff.grounded_request == supplied
    plan = expand_compact_plan(json.dumps(record["plan"]), supplied)
    expected = render_grounded_plan(
        supplied, plan, source_gap_handoff=True, source_gap_investigation=True
    )
    assert handoff.analysis == expected
    assert "Review proposal only: USER records" not in handoff.analysis.maintainer_summary
    return pending, handoff


def test_selected_actual_factory_backend_current_evidence_and_durable_review(
    tmp_path, native_indexes, monkeypatch, record_testsuite_property
):
    record_property = record_testsuite_property
    ledger, values = runtime(tmp_path, native_indexes, monkeypatch)
    records, transports, factories = [], [], []
    engines = observe_engines(monkeypatch)
    queries = observe_native_queries(monkeypatch)

    def allocate(*_args, **_kwargs):
        transport = CountedMock(lambda request: authored_response(request, records))
        transports.append(transport)
        return transport

    monkeypatch.setattr(httpx, "HTTPTransport", allocate)

    def configured(configuration):
        factory = live.configured_factory(configuration)
        factories.append(factory)
        return factory

    def backend():
        return live_backend.configured_app(values, adapters_factory=configured)

    with offline_network():
        with TestClient(backend()) as client:
            assert transports == records == engines == queries == []
            assert client.get("/health").status_code == 200
            assert not transports
            first = client.post(
                "/cases/core-delivery-neutral/messages", json=message("selected-first", 0)
            )
            assert first.status_code == 200
            old, first_handoff = assert_legacy_handoff(first.json(), records[0])
            assert old["decision"] == "ask" and old["missing_info"] == ["parent_callback_code"]
            assert old["user_draft"] == old["next_question"]
            corrected = client.post(
                "/cases/core-delivery-neutral/messages",
                json=message(
                    "selected-correction",
                    1,
                    message="Correction: Streamlit is 1.49.0; the parent callback is still unknown.",
                    reported_facts=[{"name": "streamlit_version", "value": "1.49.0"}],
                ),
            )
            assert corrected.status_code == 200
            current, corrected_handoff = assert_legacy_handoff(corrected.json(), records[1])
            assert current["proposal_id"] != old["proposal_id"]
            assert corrected_handoff.handoff_sha256 != first_handoff.handoff_sha256
            before_stale = len(records), len(transports), len(queries)
            stale = client.post(
                "/cases/core-delivery-neutral/decision",
                json=decision(old, "selected-stale"),
                headers=AUTH,
            )
            assert stale.status_code == 409
            assert (len(records), len(transports), len(queries)) == before_stale
            supplied = client.post(
                "/cases/core-delivery-neutral/messages",
                json=message(
                    "selected-code",
                    2,
                    message="Here is the current callback; its runtime effect remains unverified.",
                    reported_facts=[
                        {"name": "parent_callback_code", "value": "def on_change():\n    pass"}
                    ],
                ),
            )
            assert supplied.status_code == 200
            final, final_handoff = assert_legacy_handoff(supplied.json(), records[2])
            assert final["decision"] == "escalate" and final["next_question"] is None
            assert not any(
                gap["kind"] == "user" for gap in records[2]["payload"]["request"]["gaps"]
            )
            operation = decision(final, "selected-approve")
            approved = client.post(
                "/cases/core-delivery-neutral/decision", json=operation, headers=AUTH
            )
            assert approved.status_code == 200
            approved_view = approved.json()
            assert len(approved_view["actions"]) == 1
            assert approved_view["actions"][0]["body"] == final["user_draft"]
            counts = len(records), len(transports), len(queries), len(engines)
            observations = deepcopy(factories[0]._observations)
            binding = deepcopy(factories[0].core_binding)
        with TestClient(backend()) as client:
            assert client.get("/cases/core-delivery-neutral").json() == approved_view
            replay = client.post(
                "/cases/core-delivery-neutral/decision", json=operation, headers=AUTH
            )
            assert replay.status_code == 200 and replay.json()["review"]["replayed"]
            assert len(replay.json()["actions"]) == 1
            assert (len(records), len(transports), len(queries), len(engines)) == counts

    assert len(records) == len(transports) == len(engines) == len(observations) == 3
    assert queries and {arguments["n_results"] for _, arguments in queries} == {25}
    assert all(transport.close_calls == 1 for transport in transports)
    assert all(factory.active_clients == 0 for factory in factories)
    for record, version in zip(records, ("1.50.0", "1.49.0", "1.49.0"), strict=True):
        body, payload = record["body"], record["payload"]
        assert body["model"] == "gpt-4o-mini" and body["max_tokens"] == 1024
        assert "response_format" not in body
        assert SOURCE_SELECTION_REMINDER in body["messages"][0]["content"]
        assert payload["wire_format"] == "grounded-indexed-plan-v1"
        assert payload["decision_contracts"]["schema_id"] == "grounded-indexed-decision-fields-v1"
        assert all(type(item) is int for item in record["plan"]["sources"])
        request = payload["request"]
        assert [
            fact["value"]
            for fact in request["case"]["facts"]
            if fact["name"] == "streamlit_version" and fact["status"] == "active"
        ] == [version]
        evidence = EvidenceBundle.model_validate(request["evidence"])
        assert 0 < len(evidence.hits) <= 5
        assert all(
            not hit.applicable_versions or version in hit.applicable_versions
            for hit in evidence.hits
        )
        assert len(evidence.model_dump_json().encode()) <= 12_000
    assert all(
        engine
        == {
            "top_k": 5,
            "evidence_scope": "exact_user_version",
            "retrieval_candidate_multiplier": 5,
            "evidence_utf8_budget_bytes": 12000,
            "repair_repeated_queries": True,
            "proposal_checks": False,
            "run_limits": {
                "max_model_attempts": 2,
                "max_retrieval_rounds": 2,
                "max_queries_per_round": 2,
                "max_steps": 8,
            },
        }
        for engine in engines
    )
    assert binding["profile_id"] == DELIVERY_PROFILE_ID
    assert binding["recipe_sha256"] == delivery_recipe()["recipe_sha256"]
    assert binding["renderer_policy"] == "legacy_v1" and binding["quality_claim"] is False
    assert all(item["wire_output"]["canonical_binding_valid"] for item in observations)
    assert all(item["core_binding"] == binding for item in observations)
    assert ledger.snapshot().reserved_usd == ledger.snapshot().uncertain_usd == 0
    assert KEY not in json.dumps(approved_view)
    record_property("selected_core_binding", json.dumps(binding, sort_keys=True))
    record_property("effective_engine_policy", json.dumps(engines[0], sort_keys=True))
    record_property("actual_mock_provider_sends", len(records))
    record_property("actual_native_candidate_read_limit", 25)
    record_property("new_human_or_model_quality_score", False)
    projected, projection_error = runner._provider_observations(
        factories[0].observations_for_contexts,
        (
            first_handoff.reasoning_context,
            corrected_handoff.reasoning_context,
            final_handoff.reasoning_context,
        ),
        ledger,
    )
    record_property("runner_projection_error", str(projection_error))
    record_property("actual_observation_fields", json.dumps(sorted(observations[0])))
    assert projection_error is None and projected == observations


def test_selected_halt_stops_actual_factory_before_key_index_transport_or_tracker(
    tmp_path, native_indexes, monkeypatch
):
    ledger, values = runtime(tmp_path, native_indexes, monkeypatch)
    ledger.halt()
    index_checks, transports = [], []
    original = live._verified_index

    def verified(*args):
        index_checks.append(1)
        return original(*args)

    monkeypatch.setattr(live, "_verified_index", verified)
    monkeypatch.setattr(httpx, "HTTPTransport", lambda **kwargs: transports.append(kwargs))
    with offline_network(), pytest.raises(ValueError, match="^LiveLedgerHalted$"):
        live.configured_factory(values)
    assert not values.key_reads and not index_checks and not transports
    with offline_network(), pytest.raises(ValueError, match="^LiveBackendConfigurationInvalid$"):
        live_backend.configured_app(values)
    assert not values.key_reads and not index_checks and not transports
    assert not (tmp_path / "selected-tracker.sqlite3").exists()


@pytest.mark.parametrize(
    "conflict",
    ({"METIS_GROUNDED_JSON_OBJECT": "true"}, {"AGENT_EVAL_TOP_K": "3"}),
)
def test_selected_conflict_stops_actual_factory_before_key_or_send(
    tmp_path, native_indexes, monkeypatch, conflict
):
    _, values = runtime(tmp_path, native_indexes, monkeypatch)
    values.update(conflict)
    transports = []
    monkeypatch.setattr(httpx, "HTTPTransport", lambda **kwargs: transports.append(kwargs))
    with offline_network(), pytest.raises(ValueError):
        live.configured_factory(values)
    assert not values.key_reads and not transports


@pytest.mark.parametrize("storage", ("extra", "private"))
def test_selected_gate_rejects_hidden_loaded_catalog_before_construction(
    tmp_path, native_indexes, monkeypatch, storage
):
    _, values = runtime(tmp_path, native_indexes, monkeypatch)
    original = live.load_user_gap_vocabulary

    def hidden(path):
        definitions = original(path)
        altered = definitions[0].model_copy(deep=True)
        object.__setattr__(
            altered,
            "__pydantic_extra__" if storage == "extra" else "__pydantic_private__",
            {"PRIVATE_NAME": "PRIVATE_VALUE"},
        )
        return (altered, *definitions[1:])

    monkeypatch.setattr(live, "load_user_gap_vocabulary", hidden)
    with offline_network(), pytest.raises(ValueError):
        live.configured_factory(values)
    assert not values.key_reads


def test_selected_provider_gate_rejects_postallocation_setting_drift_without_send(
    tmp_path, native_indexes, monkeypatch
):
    ledger, values = runtime(tmp_path, native_indexes, monkeypatch)
    factories, transports, records = [], [], []

    def allocate(*args, **kwargs):
        intercepted = CountedMock(lambda request: authored_response(request, records))
        transports.append(intercepted)
        return intercepted

    monkeypatch.setattr(httpx, "HTTPTransport", allocate)
    original = live._BoundedRetriever.search
    drifted = []

    def retrieve_then_drift(retriever, request):
        bundle = original(retriever, request)
        factory = factories[0]
        factory._config = factory._config.model_copy(update={"grounded_compact_plan": False})
        drifted.append(1)
        return bundle

    monkeypatch.setattr(live._BoundedRetriever, "search", retrieve_then_drift)

    def configured(configuration):
        factory = live.configured_factory(configuration)
        factories.append(factory)
        return factory

    with (
        offline_network(),
        TestClient(live_backend.configured_app(values, adapters_factory=configured)) as client,
    ):
        response = client.post(
            "/cases/core-delivery-drift/messages", json=message("drift-first", 0)
        )
        assert response.status_code == 200
        assert response.json()["pending"] is None and response.json()["actions"] == []
    assert not records and len(transports) == 1 and transports[0].close_calls == 1
    assert drifted == [1]
    assert factories[0].active_clients == 0
    assert ledger.snapshot().reserved_usd == ledger.snapshot().uncertain_usd == 0


def test_direct_selected_catalog_validation_rejects_private_state(
    tmp_path, native_indexes, monkeypatch
):
    _, values = runtime(tmp_path, native_indexes, monkeypatch)
    with offline_network():
        factory = live.configured_factory(values)
    try:
        original = factory._gaps[0]
        altered = original.model_copy(update={"PRIVATE_NAME": "PRIVATE_VALUE"})
        with pytest.raises(ValueError, match="^CoreDeliveryConfigurationMismatch$"):
            validate_delivery_configuration(
                profile_id=DELIVERY_PROFILE_ID,
                config=factory._config,
                top_k=5,
                retrieval_profile=PROFILE,
                ask_source_background=False,
                concise_user_draft=False,
                user_gaps=(altered, *factory._gaps[1:]),
            )
    finally:
        factory.close()
