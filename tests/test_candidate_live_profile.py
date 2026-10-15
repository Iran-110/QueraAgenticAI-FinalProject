"""Named product profile on real local Chroma; intercepted HTTP and temp ledgers."""

import json
from copy import deepcopy

import httpx
import pytest
from fastapi.testclient import TestClient
from test_evaluation_live import CALLBACK, KEY, CountedMock, config
from test_evaluation_live import index as index
from test_evaluation_live import ledger as ledger
from test_persistent_live_factory import AUTH, REVIEWERS, decision, message
from test_real_index_probe import ARMS
from test_real_index_probe import native_indexes as native_indexes

from agent_app import api, live_backend
from agent_app.evaluation import live
from agent_app.orchestration.retrieval_profile import (
    retrieval_profile_options,
    validate_retrieval_profile,
)
from agent_app.orchestration.service import CoreAdapters, CoreTurnService
from agent_app.persistent_api import create_app
from agent_app.testing.fakes import FakeReasoner, FakeRetriever
from agent_app.testing.http_pilot_runtime import offline_network
from agent_app.tracker.dummy_tracker import DummyTracker
from agent_app.tracker.sqlite_tracker import SQLiteCaseTracker

PROFILE = "candidate_relevance_v1"
WARNING = "Evidence is bounded by the configured whole-record byte budget."


def candidate_factory(binding, ledger, respond, **changes):
    transports = []

    def allocate():
        transport = CountedMock(respond)
        transports.append(transport)
        return transport

    return (
        live.LiveEvaluationAdapters(
            index_path=binding["path"],
            snapshot_id=binding["snapshot_id"],
            manifest_sha256=binding["manifest_sha256"],
            ledger=ledger,
            config=config(),
            transport_factory=allocate,
            top_k=5,
            user_gaps=(CALLBACK,),
            retrieval_profile=PROFILE,
            **changes,
        ),
        transports,
    )


def ask_response(request, seen):
    body = json.loads(request.content)
    payload = json.loads(body["messages"][1]["content"])
    supplied = payload["request"]
    seen.append(deepcopy(supplied))
    hits = supplied["evidence"]["hits"]
    # Select a complete currently supplied exact-version source if available.
    active = next(
        fact["value"]
        for fact in supplied["case"]["facts"]
        if fact["name"] == "streamlit_version" and fact["status"] == "active"
    )
    selected = next(
        (index for index, hit in enumerate(hits) if active in hit["applicable_versions"]), 0
    )
    plan = {
        "context_sha256": supplied["context_sha256"],
        "decision": "ask",
        "question_name": "parent_callback_code",
        "sources": [payload["source_references"][selected]] if hits else [],
    }
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


def observe_native_queries(monkeypatch):
    from chromadb.api.models.Collection import Collection

    calls = []
    original = Collection.query

    def observe(collection, *args, **kwargs):
        calls.append((collection.name, deepcopy(kwargs)))
        return original(collection, *args, **kwargs)

    monkeypatch.setattr(Collection, "query", observe)
    return calls


def assert_current_evidence(supplied, version):
    hits = supplied["evidence"]["hits"]
    assert 0 < len(hits) <= 5
    assert all(
        not hit["applicable_versions"] or version in hit["applicable_versions"] for hit in hits
    )
    assert WARNING in supplied["evidence"]["warnings"]
    from agent_app.contracts import EvidenceBundle

    assert (
        len(EvidenceBundle.model_validate(supplied["evidence"]).model_dump_json().encode()) <= 12000
    )


@pytest.mark.parametrize("value", ["", "candidate", "native ", None, True, 1, [], {}])
def test_named_profile_rejects_nonregistered_values(value):
    with pytest.raises(ValueError, match="^RetrievalProfileInvalid$"):
        retrieval_profile_options(value)


@pytest.mark.parametrize("top_k", [1, 3, True, 5.0, "5", None])
def test_candidate_profile_requires_exact_five_final_records(top_k):
    with pytest.raises(ValueError, match="^RetrievalProfileInvalid$"):
        validate_retrieval_profile(PROFILE, top_k=top_k)


def test_native_profile_is_empty_and_candidate_options_are_detached():
    assert retrieval_profile_options("native") == {}
    expected = {
        "retrieval_candidate_multiplier": 5,
        "evidence_utf8_budget_bytes": 12000,
        "repair_repeated_queries": True,
        "evidence_scope": "exact_user_version",
    }
    supplied = retrieval_profile_options(PROFILE)
    assert supplied == expected
    supplied["evidence_utf8_budget_bytes"] = 999999
    assert retrieval_profile_options(PROFILE) == expected


def test_candidate_persistent_http_correction_restart_and_retry_bind_current_text(
    tmp_path, native_indexes, ledger, monkeypatch
):
    seen, calls = [], observe_native_queries(monkeypatch)
    binding = native_indexes[ARMS[1]]
    factory, transports = candidate_factory(
        binding, ledger, lambda request: ask_response(request, seen), ask_source_background=True
    )
    database = tmp_path / "candidate-runtime.sqlite3"

    def app():
        return create_app(
            SQLiteCaseTracker(database, reviewer_tokens=REVIEWERS),
            reviewer_tokens=REVIEWERS,
            case_adapters=lambda case, _scenario: factory.for_case(case.case_id),
            retrieval_label="local_chroma_hash",
            reasoning_label="metis_grounded_live",
            # Candidate's fixed current-installation scope must override this.
            evidence_scope="all",
        )

    with offline_network(), TestClient(app()) as client:
        original = client.post("/cases/candidate-case/messages", json=message("first", 0)).json()
        assert original["pending"] is not None
        old = original["pending"]
        assert_current_evidence(seen[0], "1.50.0")
        assert any(hit["applicable_versions"] == ["1.50.0"] for hit in seen[0]["evidence"]["hits"])
        original_text = old["user_draft"]
        correction = client.post(
            "/cases/candidate-case/messages",
            json=message(
                "correction",
                1,
                message="Correction: Streamlit 1.49.0, same multiselect and callback environment.",
                reported_facts=[{"name": "streamlit_version", "value": "1.49.0"}],
            ),
        ).json()
        current = correction["pending"]
        assert current is not None and current["proposal_id"] != old["proposal_id"]
        assert_current_evidence(seen[1], "1.49.0")
        assert current["user_draft"] != original_text
        assert len(calls) >= 4 and {kwargs["n_results"] for _, kwargs in calls} == {25}
        count = len(seen), len(calls), len(transports)
        stale = client.post(
            "/cases/candidate-case/decision", json=decision(old, "stale"), headers=AUTH
        )
        assert stale.status_code == 409
        approved = client.post(
            "/cases/candidate-case/decision",
            json=decision(current, "approve-current"),
            headers=AUTH,
        )
        assert approved.status_code == 200 and len(approved.json()["actions"]) == 1
        assert approved.json()["log"][-1]["text"] == current["user_draft"]
        assert approved.json()["actions"][0]["body"] == current["user_draft"]
    with offline_network(), TestClient(app()) as client:
        restored = client.get("/cases/candidate-case").json()
        retried = client.post(
            "/cases/candidate-case/decision",
            json=decision(current, "approve-current"),
            headers=AUTH,
        )
        assert retried.status_code == 200 and retried.json()["review"]["replayed"]
        assert retried.json()["actions"] == restored["actions"]
        assert len(retried.json()["actions"]) == 1
        assert (len(seen), len(calls), len(transports)) == count
    factory.close()
    assert all(item.close_calls == 1 for item in transports)
    assert KEY not in json.dumps(correction)


@pytest.mark.parametrize("with_runner_wrapper", [False, True])
def test_memory_api_used_by_evaluation_runner_forwards_same_candidate_profile(
    native_indexes, ledger, monkeypatch, with_runner_wrapper
):
    seen, calls = [], observe_native_queries(monkeypatch)
    factory, transports = candidate_factory(
        native_indexes[ARMS[1]], ledger, lambda request: ask_response(request, seen)
    )
    monkeypatch.setattr(api, "_cases", {})
    monkeypatch.setattr(api, "tracker", DummyTracker())
    if with_runner_wrapper:
        from agent_app.evaluation.runner import CaseRun

        case_run = CaseRun(None, lambda case_id, _turn: factory.for_case(case_id), None)
        monkeypatch.setattr(
            api,
            "_adapters",
            lambda _scenario: case_run._adapters("memory-profile", {}, [], []),
        )
    else:
        monkeypatch.setattr(api, "_adapters", lambda _scenario: factory.for_case("memory-profile"))
    with offline_network(), TestClient(api.app) as client:
        result = client.post("/cases/memory-profile/messages", json=message("first", 0))
    assert result.status_code == 200 and result.json()["pending"] is not None
    assert_current_evidence(seen[0], "1.50.0")
    assert calls and {kwargs["n_results"] for _, kwargs in calls} == {25}
    assert transports and factory.active_clients == 0
    factory.close()


def test_native_factory_identity_is_exact_legacy_and_nondefaults_are_distinct(index, ledger):
    from test_evaluation_live import adapters

    with offline_network():
        native, _ = adapters(index, ledger)
        assert native.config == {
            "model": "gpt-4o-mini",
            "snapshot_id": index[1],
            "prompt_policy": "baseline",
            "response_mode": "grounded_plan",
            "phase": "development",
            "adapter_id": "verified_chroma_metis_grounded_v1",
            "retriever_id": "verified_chroma_lexical_hash_top1_v1",
        }
        assert native.for_case("legacy").retrieval_profile == "native"
        native.close()
        candidate, _ = adapters(index, ledger, top_k=5, retrieval_profile=PROFILE)
        assert candidate.config["retriever_id"] != native.config["retriever_id"]
        assert candidate.config["adapter_id"] != native.config["adapter_id"]
        assert candidate.for_case("profile").retrieval_profile == PROFILE
        candidate.close()
        background, _ = adapters(index, ledger, ask_source_background=True)
        assert background.config["adapter_id"] != native.config["adapter_id"]
        background.close()


@pytest.mark.parametrize(
    "changes",
    [
        {"AGENT_RETRIEVAL_PROFILE": "unknown"},
        {"AGENT_RETRIEVAL_PROFILE": True},
        {"AGENT_RETRIEVAL_PROFILE": PROFILE, "AGENT_EVAL_TOP_K": "3"},
        {"AGENT_GROUNDED_ASK_SOURCE_BACKGROUND": "TRUE"},
        {"AGENT_GROUNDED_ASK_SOURCE_BACKGROUND": True},
    ],
)
def test_invalid_profile_or_renderer_setting_rejected_before_credentials(monkeypatch, changes):
    class NoCredentialLookup(dict):
        def get(self, key, *args):
            assert key != "METIS_API_KEY", "credential lookup must follow validated profile"
            return super().get(key, *args)

    monkeypatch.setattr(live, "_budget_guard", lambda _ledger: pytest.fail("no ledger needed"))
    values = NoCredentialLookup({"METIS_LIVE_ENABLED": "true", **changes})
    with pytest.raises(ValueError, match="^LiveEvaluationConfigurationInvalid$"):
        live.configured_factory(values)


def test_profile_setting_never_unhalts_ordinary_factory(tmp_path, index, ledger):
    ledger.halt()
    with offline_network(), pytest.raises(ValueError, match="^LiveLedgerHalted$"):
        from test_evaluation_live import adapters

        adapters(index, ledger, top_k=5, retrieval_profile=PROFILE, ask_source_background=True)
    database = tmp_path / "uncreated.sqlite3"
    with offline_network(), pytest.raises(ValueError, match="^LiveBackendConfigurationInvalid$"):
        live_backend.configured_app(
            {"AGENT_TRACKER_DB": str(database), "AGENT_REVIEWER_TOKEN": "x" * 40},
            adapters_factory=lambda _values: adapters(
                index, ledger, top_k=5, retrieval_profile=PROFILE
            )[0],
        )
    assert not database.exists()


def test_candidate_service_rejects_changed_top_k_before_port_calls(tmp_path):
    from agent_app.contracts import UserTurn

    retriever, reasoner = FakeRetriever([]), FakeReasoner([])
    tracker = SQLiteCaseTracker(tmp_path / "wrong-cap.sqlite3", reviewer_tokens=REVIEWERS)
    service = CoreTurnService(
        tracker,
        lambda *_: CoreAdapters(retriever, reasoner, "synthetic", retrieval_profile=PROFILE),
        top_k=3,
    )
    outcome = service.submit(
        UserTurn(
            case_id="cap-case",
            expected_revision=0,
            turn_id="first",
            source_ref="user:first",
            message="Synthetic issue.",
        )
    )
    assert outcome.error_code == "AdapterSetupFailed"
    assert retriever.requests == reasoner.inputs == []


def test_configured_factory_validates_then_forwards_named_settings_without_clients(
    tmp_path, index, monkeypatch
):
    from decimal import Decimal

    from agent_app.llm.budget import BudgetLedger

    runtime = tmp_path / "runtime"
    runtime.mkdir()
    BudgetLedger.create(
        runtime / "budget.sqlite3", limit_usd=Decimal("1"), opening_spend_usd=Decimal("0")
    )
    monkeypatch.setattr(live, "ROOT", tmp_path)
    monkeypatch.setattr(
        httpx, "HTTPTransport", lambda **_: pytest.fail("startup allocated transport")
    )
    values = {
        "METIS_LIVE_ENABLED": "true",
        "METIS_API_KEY": KEY,
        "AGENT_EVAL_INDEX": str(index[0]),
        "AGENT_EVAL_SNAPSHOT": index[1],
        "AGENT_EVAL_MANIFEST_SHA256": index[2],
        "AGENT_EVAL_TOP_K": "5",
        "AGENT_RETRIEVAL_PROFILE": PROFILE,
        "AGENT_GROUNDED_ASK_SOURCE_BACKGROUND": "true",
    }
    with offline_network():
        factory = live.configured_factory(values)
        assert factory._retrieval_profile == PROFILE
        assert factory._ask_source_background is True
        assert "candidate_relevance" in factory.config["retriever_id"]
        assert "ask_source_background" in factory.config["adapter_id"]
        assert factory.active_clients == 0
        factory.close()


@pytest.mark.parametrize("changes", [{"retrieval_profile": True}, {"ask_source_background": 1}])
def test_invalid_constructor_flags_fail_before_ledger_or_transport(monkeypatch, changes):
    monkeypatch.setattr(
        live, "_budget_guard", lambda _ledger: pytest.fail("invalid profile reached ledger")
    )
    with pytest.raises(ValueError, match="^LiveEvaluationConfigurationInvalid$"):
        live.LiveEvaluationAdapters(
            index_path="unused",
            snapshot_id="unused",
            manifest_sha256="unused",
            ledger=None,
            config=config(),
            **changes,
        )


@pytest.mark.parametrize("durable", [False, True])
def test_user_cannot_select_a_retrieval_profile_or_engine_options(tmp_path, monkeypatch, durable):
    if durable:
        tracker = SQLiteCaseTracker(tmp_path / "no-user-profile.sqlite3", reviewer_tokens=REVIEWERS)
        app = create_app(
            tracker, reviewer_tokens=REVIEWERS, adapters=lambda _: pytest.fail("USER selected port")
        )
    else:
        monkeypatch.setattr(api, "_cases", {})
        monkeypatch.setattr(api, "_adapters", lambda _: pytest.fail("USER selected port"))
        app = api.app
    with offline_network(), TestClient(app) as client:
        response = client.post(
            "/cases/no-user-profile/messages",
            json=message("first", 0, retrieval_profile=PROFILE, evidence_utf8_budget_bytes=999999),
        )
    assert response.status_code == 422 and response.json() == {"detail": "RequestInvalid"}
    if durable:
        assert tracker.read_case("no-user-profile")["state"]["case_revision"] == 0
    else:
        assert api._cases == {}


def test_configured_live_backend_preserves_profile_and_remains_lazy(
    tmp_path, native_indexes, ledger, monkeypatch
):
    seen, calls = [], observe_native_queries(monkeypatch)
    factory, transports = candidate_factory(
        native_indexes[ARMS[1]], ledger, lambda request: ask_response(request, seen)
    )
    with offline_network():
        app = live_backend.configured_app(
            {
                "AGENT_TRACKER_DB": str(tmp_path / "configured.sqlite3"),
                "AGENT_REVIEWER_TOKEN": "x" * 40,
            },
            adapters_factory=lambda _values: factory,
        )
        assert transports == [] and calls == []
        with TestClient(app) as client:
            assert client.get("/health").status_code == 200
            assert transports == [] and calls == []
            body = client.post(
                "/cases/configured-candidate/messages", json=message("first", 0)
            ).json()
            assert body["pending"] is not None
            assert_current_evidence(seen[0], "1.50.0")
            assert {kwargs["n_results"] for _, kwargs in calls} == {25}
        assert factory.active_clients == 0 and all(item.close_calls == 1 for item in transports)
        with pytest.raises(ValueError, match="^LiveEvaluationFactoryClosed$"):
            factory.for_case("closed")
