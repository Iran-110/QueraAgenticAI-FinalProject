"""Actual opt-in v2 composition on a fresh final corpus and intercepted wires.

The shared writer builds 1228 sources/1827 chunks once. Runtime readers only
open disposable copies. Authored neutral plans establish integration/custody,
not model quality, semantic support, a shared freeze or live authorization.
"""

import hashlib
import json
import shutil
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient
from test_candidate_live_profile import observe_native_queries
from test_core_delivery_http import (
    AUTH,
    TOKEN,
    ObservedValues,
    assert_legacy_handoff,
    authored_response,
)
from test_core_delivery_runner import (
    FUTURE_CANARY,
    GOLD_CANARY,
    SCRIPT_CANARY,
    authored_fixture,
)
from test_evaluation_live import KEY, CountedMock
from test_persistent_live_factory import message

from agent_app import api, live_backend, ui_client
from agent_app.contracts import EvidenceBundle, ProposalHandoff
from agent_app.evaluation import live, runner
from agent_app.llm.budget import BudgetLedger
from agent_app.orchestration import service
from agent_app.orchestration.core_delivery import PREFILTER_DELIVERY_PROFILE_ID, delivery_recipe
from agent_app.orchestration.handoff import validate_handoff
from agent_app.reasoning.source_selection import SOURCE_SELECTION_REMINDER
from agent_app.retrieval import offline_index
from agent_app.retrieval.pilot_corpus import FINAL_PROTOCOL, MANIFEST_NAME, build_final_corpus
from agent_app.testing.http_pilot_runtime import offline_network

ROOT = Path(__file__).resolve().parents[1]
FINAL = ROOT / "experiments/final_corpus_v1"
# Cross-checked against the independent pre-freeze v1 rebuild, not a claim
# that evaluation's future post-freeze build/packet has been approved.
FINAL_SNAPSHOT = "docs-pilot-da1a891b5e3c1d587d0a013327c166f6ae51ab907426f86455b239d5489812c4"
FINAL_MANIFEST_SHA256 = "d5158882f0c266820425f7ab82627939b9af77ae07f70b5b967c5abdb8fd0cf4"
ENGINE_FIELDS = (
    "top_k",
    "evidence_scope",
    "retrieval_candidate_multiplier",
    "evidence_utf8_budget_bytes",
    "repair_repeated_queries",
    "retrieval_version_prefilter",
)


def physical_files(directory):
    result = {}
    for path in sorted(directory.rglob("*")):
        assert not path.is_symlink()
        assert path.is_dir() or path.is_file()
        if path.is_file():
            result[path.relative_to(directory).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return result


@pytest.fixture(scope="module")
def final_index_build(tmp_path_factory, record_testsuite_property):
    destination = tmp_path_factory.mktemp("final-v2-build") / "writer-index"
    with offline_network():
        corpus = build_final_corpus(
            ROOT / "streamlit-data-for-dev-test",
            FINAL / "allowlist.json",
            FINAL / "exclusion-v1.json",
        )
        payload = corpus.manifest["corpus"]
        assert payload["protocol"] == FINAL_PROTOCOL == "docs-api-release-final-v1"
        assert len(payload["sources"]) == 1228 and len(payload["chunks"]) == 1827
        assert payload["exclusions"]["indexed_issue_count"] == 0
        assert payload["exclusions"]["indexed_comment_count"] == 0
        snapshot = offline_index.build_index(corpus, destination)
        assert snapshot == corpus.snapshot_id == FINAL_SNAPSHOT
        # The writer has finished; no runtime reader opens this baseline.
        offline_index._persistent_client(destination)._system.stop()
    before = physical_files(destination)
    assert before[MANIFEST_NAME] == FINAL_MANIFEST_SHA256
    assert payload["source_pins"]["allowlist_sha256"] == (
        "dd40ac7b6e66566000c90e3409d23f487f09a26ec66b291daf58aae5fa8290e7"
    )
    assert payload["source_pins"]["exclusion_manifest_sha256"] == (
        "f9c4ab62850febeb6981168e2a93c46bec5687a11751ec8be2b01d28a9a1a415"
    )
    binding = {
        "path": destination,
        "snapshot_id": snapshot,
        "manifest_sha256": before[MANIFEST_NAME],
        "source_count": len(payload["sources"]),
        "chunk_count": len(payload["chunks"]),
        "protocol": payload["protocol"],
        "source_pins": payload["source_pins"],
    }
    record_testsuite_property(
        "final_corpus_temporary_build", json.dumps({**binding, "path": "temporary-writer"})
    )
    yield binding
    assert physical_files(destination) == before
    record_testsuite_property("temporary_writer_index_unchanged_after_runtime_reads", True)


@pytest.fixture
def final_index_copy(tmp_path, final_index_build):
    baseline = final_index_build["path"]
    before = physical_files(baseline)
    copied = tmp_path / "disposable-native-read-index"
    shutil.copytree(baseline, copied)
    assert physical_files(copied) == before
    try:
        yield {**final_index_build, "path": str(copied)}
    finally:
        # Runtime factories close provider runs, but native client ownership is
        # explicitly retained here until both backend instances have finished.
        offline_index._persistent_client(copied)._system.stop()
        assert physical_files(baseline) == before


def configured_values(tmp_path, binding, monkeypatch, *, phase="development"):
    (tmp_path / "runtime").mkdir()
    ledger = BudgetLedger.create(
        tmp_path / "runtime/budget.sqlite3",
        limit_usd=Decimal("1"),
        opening_spend_usd=Decimal("0"),
    )
    monkeypatch.setattr(live, "ROOT", tmp_path)
    values = ObservedValues(
        {
            "AGENT_CORE_PROFILE": PREFILTER_DELIVERY_PROFILE_ID,
            "AGENT_EVAL_PHASE": phase,
            "METIS_LIVE_ENABLED": "true",
            "METIS_API_KEY": KEY,
            "AGENT_EVAL_INDEX": binding["path"],
            "AGENT_EVAL_SNAPSHOT": binding["snapshot_id"],
            "AGENT_EVAL_MANIFEST_SHA256": binding["manifest_sha256"],
            "AGENT_TRACKER_DB": str(tmp_path / "neutral-case-tracker.sqlite3"),
            "AGENT_REVIEWER_TOKEN": TOKEN,
            "AGENT_REVIEWER_ID": "fixture-maintainer",
        }
    )
    return ledger, values


def observe_composition(monkeypatch):
    engines, retrievals = [], []
    for module in (service, api):
        original = module.SupportEngine

        def construct(*args, _original=original, **kwargs):
            engine = _original(*args, **kwargs)
            engines.append({name: getattr(engine, name) for name in ENGINE_FIELDS})
            return engine

        monkeypatch.setattr(module, "SupportEngine", construct)
    search = live._BoundedRetriever.search

    def retrieve(adapter, request):
        # This is the actual engine-to-retriever argument, before native reads.
        result = search(adapter, request)
        retrievals.append((request.model_copy(deep=True), result.model_copy(deep=True)))
        return result

    monkeypatch.setattr(live._BoundedRetriever, "search", retrieve)
    return engines, retrievals, observe_native_queries(monkeypatch)


def assert_composition(records, retrievals, native_queries, engines, binding, versions):
    expected_engine = delivery_recipe(profile_id=PREFILTER_DELIVERY_PROFILE_ID)["engine_policy"]
    assert len(records) == len(retrievals) == len(engines) == len(versions)
    assert engines and all(engine == expected_engine for engine in engines)
    assert len(native_queries) == 2 * len(retrievals)
    for index, (record, (request, candidates), version) in enumerate(
        zip(records, retrievals, versions, strict=True)
    ):
        expected = "[]" if version is None else ("[]", json.dumps([version], separators=(",", ":")))
        assert request.filters == {"applicable_versions": expected}
        assert request.top_k == 25 and request.snapshot_id == binding["snapshot_id"]
        where = {"applicable_versions": expected}
        if version is not None:
            where = {"applicable_versions": {"$in": list(expected)}}
        calls = native_queries[2 * index : 2 * index + 2]
        assert {name for name, _ in calls} == {"streamlit_docs", "streamlit_issues"}
        assert all(arguments["n_results"] == 25 for _, arguments in calls)
        assert all(arguments["where"] == where for _, arguments in calls)
        assert all(
            arguments["query_embeddings"]
            == [offline_index.lexical_embedding(query) for query in request.queries]
            for _, arguments in calls
        )
        body, payload = record["body"], record["payload"]
        assert body["model"] == "gpt-4o-mini" and body["max_tokens"] == 1024
        assert "response_format" not in body
        assert SOURCE_SELECTION_REMINDER in body["messages"][0]["content"]
        assert payload["wire_format"] == "grounded-indexed-plan-v1"
        assert payload["decision_contracts"]["schema_id"] == "grounded-indexed-decision-fields-v1"
        current = payload["request"]
        active = [
            fact["value"]
            for fact in current["case"]["facts"]
            if fact["name"] == "streamlit_version" and fact["status"] == "active"
        ]
        assert active == ([] if version is None else [version])
        evidence = EvidenceBundle.model_validate(current["evidence"])
        assert evidence.snapshot_id == binding["snapshot_id"]
        assert 0 < len(evidence.hits) <= 5
        assert len(evidence.model_dump_json().encode("utf-8")) <= 12000
        candidate_hits = {hit.chunk_id: hit for hit in candidates.hits}
        assert 0 < len(candidate_hits) <= 25
        for hit in evidence.hits:
            assert hit.chunk_id in candidate_hits
            assert hit.excerpt == candidate_hits[hit.chunk_id].excerpt
            assert hit.source_id == candidate_hits[hit.chunk_id].source_id
            assert not hit.applicable_versions or version in hit.applicable_versions
        assert all(canary not in json.dumps(record) for canary in (GOLD_CANARY, SCRIPT_CANARY))


def test_final_v2_ui_http_correction_durable_approval_and_retry(
    tmp_path, final_index_copy, monkeypatch, record_testsuite_property
):
    ledger, values = configured_values(tmp_path, final_index_copy, monkeypatch)
    records, transports, factories = [], [], []
    engines, retrievals, queries = observe_composition(monkeypatch)

    def allocate(*args, **kwargs):
        transport = CountedMock(lambda request: authored_response(request, records))
        transports.append(transport)
        return transport

    monkeypatch.setattr(httpx, "HTTPTransport", allocate)

    def configured(configuration):
        factory = live.configured_factory(configuration)
        copied = Path(final_index_copy["path"]).resolve()
        assert factory.index_path == factory._client._path == copied
        factories.append(factory)
        return factory

    def backend():
        return live_backend.configured_app(values, adapters_factory=configured)

    case_id = "neutral-final-v2-http"
    with offline_network():
        with TestClient(backend()) as http:
            ui = ui_client.BackendClient(http, reviewer_token=TOKEN)
            assert ui.discover_capabilities().durable_reviews
            assert records == transports == engines == retrievals == queries == []
            first_view = ui.send_event(
                case_id,
                message(
                    "neutral-initial",
                    0,
                    message="A selector resets after a parent choice; version and callback are unavailable.",
                    reported_facts=[],
                ),
            )
            initial, initial_handoff = assert_legacy_handoff(first_view, records[0])
            assert initial["missing_info"] == ["streamlit_version"]
            known_view = ui.send_event(
                case_id,
                message(
                    "neutral-known",
                    1,
                    message="I checked: this app runs Streamlit 1.50.0. The callback remains unavailable.",
                ),
            )
            known, known_handoff = assert_legacy_handoff(known_view, records[1])
            assert known["missing_info"] == ["parent_callback_code"]
            stale_operation = ui.prepare_review(case_id, known, "approve")
            corrected_view = ui.send_event(
                case_id,
                message(
                    "neutral-correction",
                    2,
                    message="Correction: the running version is 1.49.0; the callback remains unavailable.",
                    reported_facts=[{"name": "streamlit_version", "value": "1.49.0"}],
                ),
            )
            corrected, corrected_handoff = assert_legacy_handoff(corrected_view, records[2])
            assert corrected["missing_info"] == ["parent_callback_code"]
            assert (
                len(
                    {
                        item.handoff_sha256
                        for item in (initial_handoff, known_handoff, corrected_handoff)
                    }
                )
                == 3
            )
            assert (
                len({initial["proposal_id"], known["proposal_id"], corrected["proposal_id"]}) == 3
            )
            counts = len(records), len(transports), len(queries), len(engines)
            stale = http.post(
                f"/cases/{case_id}/decision", json=stale_operation.payload(), headers=AUTH
            )
            assert stale.status_code == 409
            assert (len(records), len(transports), len(queries), len(engines)) == counts
            operation = ui.prepare_review(case_id, corrected, "approve")
            approved = ui.send_review(operation)
            assert approved["review"]["replayed"] is False
            assert len(approved["actions"]) == 1
            assert approved["actions"][0]["body"] == corrected["user_draft"]
            observations = deepcopy(factories[0]._observations)
            core_binding = deepcopy(factories[0].core_binding)
        # New application/tracker/connection objects in this interpreter;
        # this is not a browser or operating-system process restart.
        with TestClient(backend()) as http:
            ui = ui_client.BackendClient(http, reviewer_token=TOKEN)
            assert ui.get_saved_case(case_id) == approved
            retried = ui.send_review(operation)
            assert retried["review"]["replayed"] is True
            assert retried["actions"] == approved["actions"]
            assert (len(records), len(transports), len(queries), len(engines)) == counts

    assert_composition(
        records, retrievals, queries, engines, final_index_copy, (None, "1.50.0", "1.49.0")
    )
    assert len(transports) == len(observations) == 3
    assert all(transport.close_calls == 1 for transport in transports)
    assert all(factory.active_clients == 0 for factory in factories)
    assert core_binding["profile_id"] == PREFILTER_DELIVERY_PROFILE_ID
    assert (
        core_binding["recipe_sha256"]
        == delivery_recipe(profile_id=PREFILTER_DELIVERY_PROFILE_ID)["recipe_sha256"]
    )
    assert core_binding["renderer_policy"] == "legacy_v1" and core_binding["quality_claim"] is False
    assert all(row["core_binding"] == core_binding for row in observations)
    assert all(row["wire_output"]["canonical_binding_valid"] for row in observations)
    projected, error = runner._provider_observations(
        factories[0].observations_for_contexts,
        tuple(
            handoff.reasoning_context
            for handoff in (initial_handoff, known_handoff, corrected_handoff)
        ),
        ledger,
    )
    assert error is None and projected == observations
    assert ledger.snapshot().reserved_usd == ledger.snapshot().uncertain_usd == 0
    assert KEY not in json.dumps(approved)
    record_testsuite_property("final_v2_http_binding", json.dumps(core_binding, sort_keys=True))
    record_testsuite_property(
        "final_v2_effective_http_engine", json.dumps(engines[0], sort_keys=True)
    )
    record_testsuite_property("final_v2_http_mock_sends", len(records))
    record_testsuite_property(
        "final_v2_http_actions_after_reconstruction_retry", len(retried["actions"])
    )


def test_final_v2_complete_conditional_runner_serializes_actual_binding(
    tmp_path, final_index_copy, monkeypatch, record_testsuite_property
):
    ledger, values = configured_values(tmp_path, final_index_copy, monkeypatch, phase="evaluation")
    fixture_root = tmp_path / "neutral-fixture"
    path = authored_fixture(fixture_root, "final-v2")
    original_collect = runner.collect

    def collect_authored(paths, *, mode="offline"):
        with patch.object(runner, "ROOT", fixture_root):
            return original_collect(paths, mode=mode)

    monkeypatch.setattr(runner, "collect", collect_authored)
    records, transports = [], []
    engines, retrievals, queries = observe_composition(monkeypatch)

    def allocate(*args, **kwargs):
        transport = CountedMock(lambda request: authored_response(request, records))
        transports.append(transport)
        return transport

    monkeypatch.setattr(httpx, "HTTPTransport", allocate)
    with offline_network():
        factory = live.configured_factory(values)
        copied = Path(final_index_copy["path"]).resolve()
        assert factory.index_path == factory._client._path == copied
        try:
            receipt = runner.run([path], mode="live", live=factory, conditional_routes=True)
            assert factory.active_clients == 0
        finally:
            factory.close()
    packet = json.loads(json.dumps(receipt))
    assert packet == receipt and packet["quality_claim"] is False
    assert packet["tracker_backend"] == "process_memory_dummy_tracker"
    assert packet["source_unchanged_during_run"] is True
    assert packet["config"] == factory.config and len(packet["config"]) == 7
    case = packet["cases"][0]
    steps = [step for step in case["steps"] if "usage" in step]
    assert len(steps) == 3
    assert packet["summary"]["coverage_complete"] is True
    assert all(check["passed"] for check in case["checks"])
    assert case["conditional_routes"]["executed_turn_ids"] == ["report", "version", "callback"]
    assert case["conditional_routes"]["unvisited_registered_turn_ids"] == []
    assert [step["proposal"]["decision"] for step in steps] == ["ask", "ask", "escalate"]
    assert all(step["usage"]["provider_observations_error"] is None for step in steps)
    observations = [row for step in steps for row in step["usage"]["provider_observations"]]
    assert len(observations) == len(records) == len(transports) == 3
    assert all(transport.close_calls == 1 for transport in transports)
    for row in observations:
        assert row["core_binding"] == factory.core_binding
        assert row["core_binding"]["profile_id"] == PREFILTER_DELIVERY_PROFILE_ID
        assert row["core_binding"]["observed_metis"]["phase"] == "evaluation"
        assert row["wire_output"]["canonical_binding_valid"] is True
        reservation = ledger.get(row["request_id"])
        assert reservation is not None and reservation.phase == "evaluation"
        assert reservation.status == row["ledger_status"] == "settled"
        assert reservation.run_id == row["run_id"] and reservation.attempt == row["attempt_index"]
    for step, record in zip(steps, records, strict=True):
        _, handoff = assert_legacy_handoff({"pending": step["proposal"]}, record)
        validate_handoff(ProposalHandoff.model_validate(step["proposal"]["review_handoff"]))
        assert handoff.grounded_request.model_dump(mode="json") == record["payload"]["request"]
    assert_composition(
        records, retrievals, queries, engines, final_index_copy, (None, "1.50.0", "1.50.0")
    )
    assert all(FUTURE_CANARY not in json.dumps(record) for record in records[:2])
    assert FUTURE_CANARY in json.dumps(records[-1])
    snapshot = ledger.snapshot()
    assert snapshot.reserved_usd == snapshot.uncertain_usd == 0
    assert Decimal(packet["summary"]["cost_usd_total"]) == snapshot.settled_usd > 0
    assert Decimal(packet["summary"]["settled_usd_total"]) == snapshot.settled_usd
    assert Decimal(packet["summary"]["reserved_usd_total"]) == snapshot.reserved_usd
    assert Decimal(packet["summary"]["uncertain_usd_total"]) == snapshot.uncertain_usd
    record_testsuite_property(
        "final_v2_runner_binding", json.dumps(factory.core_binding, sort_keys=True)
    )
    record_testsuite_property(
        "final_v2_effective_runner_engine", json.dumps(engines[0], sort_keys=True)
    )
    record_testsuite_property("final_v2_runner_mock_sends", len(records))
    record_testsuite_property("final_v2_runner_cost_usd", packet["summary"]["cost_usd_total"])
