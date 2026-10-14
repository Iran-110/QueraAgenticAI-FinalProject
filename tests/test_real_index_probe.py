"""Native Chroma + HTTP + finite synthetic ledger; never a paid quality score."""

import hashlib
import json
from copy import deepcopy
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from test_budget_quarantine_scope import multiple_holds as multiple_holds

from agent_app.contracts import EvidenceHit, GroundedRequest, ReasoningContext
from agent_app.evaluation.runner import Fixture
from agent_app.llm.config import MetisConfig
from agent_app.llm.pricing import get_price
from agent_app.reasoning.catalog import load_user_gap_vocabulary
from agent_app.reasoning.grounding import build_grounded_messages, source_content_sha256
from agent_app.reasoning.source_selection import add_source_selection_reminder
from agent_app.retrieval.offline_index import _persistent_client, build_index
from agent_app.retrieval.pilot_corpus import MANIFEST_NAME, build_pilot_corpus, lexical_embedding
from agent_app.testing.dev_three_model_probe import DevProbeRejected, ledger_observation
from agent_app.testing.http_pilot_runtime import offline_network
from agent_app.testing.quality_probe import quality_slots
from agent_app.testing.real_index_probe import (
    RealIndexProbeRejected,
    run_real_index_batch,
    validate_index_bindings,
)
from agent_app.testing.stability_probe import VOCABULARY, fixtures_for

ROOT = Path(__file__).resolve().parents[1]
ARMS = ("historical_14_sources", "new_18_sources")


@pytest.fixture(scope="module")
def native_indexes(tmp_path_factory):
    folder = tmp_path_factory.mktemp("real-index-probe")
    registrations = {}
    for arm, split, allowlist in (
        (
            ARMS[0],
            "data/evaluation/dev-three-v1/split-manifest.json",
            "experiments/corpus/pilot-allowlist.json",
        ),
        (
            ARMS[1],
            "experiments/dev_rag_coverage_v1/split-manifest.json",
            "experiments/dev_rag_coverage_v1/allowlist.json",
        ),
    ):
        with offline_network():
            corpus = build_pilot_corpus(
                ROOT / "streamlit-data-for-dev-test", ROOT / split, ROOT / allowlist
            )
            path = folder / arm
            snapshot = build_index(corpus, path)
        registrations[arm] = {
            "path": str(path),
            "snapshot_id": snapshot,
            "manifest_sha256": hashlib.sha256((path / MANIFEST_NAME).read_bytes()).hexdigest(),
        }
    return registrations


def prepare(multiple_holds, case_id="dev-case-a", *, fixture=None, arms=ARMS):
    ledger, _path, _old = multiple_holds
    fixtures = fixtures_for(ROOT, {"protocol_id": "core-stability-v1"})
    if fixture is not None:
        fixtures[case_id] = fixture
    protocol = {"experiment_id": "synthetic-native-index-development"}
    batch = {
        "batch_id": "synthetic-real-index",
        "kind": "real_index",
        "scope_id": "synthetic-real-index-scope",
        "jobs": [
            {
                "job_id": f"synthetic:{case_id}:{arm}",
                "case_id": case_id,
                "arm": arm,
                "round": 1,
                "decision_contracts": True,
                "source_selection_reminder": True,
                "input_token_reserve": 32768,
                "max_output_tokens": 1024,
            }
            for arm in arms
        ],
    }
    slots = quality_slots(protocol, batch, fixtures)
    observed = asdict(ledger.quarantine_observation())
    ledger.authorize_quarantine_scope(
        authorization_id=batch["scope_id"],
        authorization_ref="synthetic-explicit-user-index-tests",
        expected_unknown_ids=observed["unknown_ids"],
        expected_unknown_fingerprints=observed["unknown_fingerprints"],
        expected_meta_sha256=observed["meta_sha256"],
        expected_authorization_history_sha256=observed["authorization_history_sha256"],
        protocol_sha256="f" * 64,
        request_slots=slots,
        additional_cap_usd=Decimal(".06"),
        allow_full_context=True,
    )
    config = MetisConfig(
        api_key="synthetic-index-probe-key",
        live_enabled=True,
        response_mode="grounded_plan",
        continuation_id=batch["scope_id"],
        grounded_decision_contracts=True,
        grounded_source_selection_reminder=True,
        grounded_source_gap_handoff=True,
        grounded_source_gap_investigation=True,
        input_token_reserve=32768,
        max_output_tokens=1024,
        max_request_usd=get_price("gpt-4o-mini").cost(32768, 1024),
    )
    return ledger, protocol, batch, fixtures, config


def respond(request, *, refine=False):
    wire = json.loads(request.content)
    payload = json.loads(wire["messages"][1]["content"])
    supplied = payload["request"]
    user = [gap for gap in supplied["gaps"] if gap["kind"] == "user"]
    if refine and payload["capacity"]["can_refine"]:
        decision, question, refs = "retrieve_more", None, []
        queries = [
            "streamlit.button icon emoji material symbol company logo custom image",
            "button icon company logo emoji",
        ]
    else:
        decision, question = ("ask", user[0]["name"]) if user else ("escalate", None)
        hits = supplied["evidence"]["hits"]
        refs = []
        if not user and hits:
            hit = EvidenceHit.model_validate(hits[0])
            refs = [{"chunk_id": hit.chunk_id, "content_sha256": source_content_sha256(hit)}]
        queries = []
    content = json.dumps(
        {
            "decision": decision,
            "context_sha256": supplied["context_sha256"],
            "sources": refs,
            "question_name": question,
            "retrieval_queries": queries,
        }
    )
    return httpx.Response(
        200,
        json={
            "model": "gpt-4o-mini-2024-07-18",
            "usage": {"prompt_tokens": 100, "completion_tokens": 80, "total_tokens": 180},
            "choices": [
                {"finish_reason": "stop", "message": {"role": "assistant", "content": content}}
            ],
        },
    )


def run(prepared, indexes, handler=respond, checkpoint=None):
    ledger, protocol, batch, fixtures, config = prepared
    with offline_network():
        return run_real_index_batch(
            protocol,
            batch,
            fixtures,
            load_user_gap_vocabulary(str(ROOT / VOCABULARY)),
            ledger,
            config,
            ledger_observation(ledger._path),
            indexes,
            underlying=httpx.MockTransport(handler),
            checkpoint=checkpoint,
        )


@pytest.mark.parametrize("case_id", ("dev-case-a", "dev-case-b", "dev-case-c"))
def test_native_bundles_replace_fixture_evidence_and_preserve_quarantines(
    multiple_holds, native_indexes, case_id
):
    prepared = prepare(multiple_holds, case_id)
    receipt = run(prepared, native_indexes)
    assert receipt["visited_jobs"] == receipt["completed_routes"] == 2
    assert receipt["original_accounting_preserved"] and not receipt["stopped_early"]
    assert receipt["fixed_fixture_evidence_used"] is False
    assert receipt["human_reviewed"] is False and receipt["held_out_test"] is False
    assert {arm: r["source_count"] for arm, r in receipt["index_bindings"].items()} == {
        ARMS[0]: 14,
        ARMS[1]: 18,
    }
    records = receipt["actual_retrievals"]
    assert len(records) == 4 and all(record["error_code"] is None for record in records)
    for record in records:
        assert record["requested"] == record["executed"]
        assert record["requested"]["filters"] == {} and record["requested"]["top_k"] == 5
        binding = native_indexes[record["arm"]]
        assert record["evidence"]["snapshot_id"] == binding["snapshot_id"]
        assert record["evidence"]["queries_used"] == record["executed"]["queries"]
        assert record["logical_retrieval_round"] == 1
        assert all(hit["source_type"] == "doc" for hit in record["evidence"]["hits"])
    for attempt in receipt["attempts"]:
        supplied = attempt["request"]
        messages = add_source_selection_reminder(
            build_grounded_messages(
                GroundedRequest.model_validate(supplied),
                ReasoningContext.model_validate(attempt["context"]),
                decision_contracts=True,
            ),
            enabled=True,
        )
        assert len(json.dumps(messages, ensure_ascii=False).encode()) + 1024 <= 32768
        current = [
            fact["value"]
            for fact in supplied["case"]["facts"]
            if fact["name"] == "streamlit_version" and fact["status"] == "active"
        ]
        for hit in supplied["evidence"]["hits"]:
            assert not hit["applicable_versions"] or hit["applicable_versions"] == current
        assert supplied["evidence"]["retrieval_round"] == 1
        assert supplied["evidence"]["snapshot_id"] in {
            binding["snapshot_id"] for binding in native_indexes.values()
        }
    ledger = prepared[0]
    assert ledger.snapshot().halted and ledger.snapshot().reserved_usd == 0
    assert len(ledger.quarantine_observation().unknown_ids) == 2
    assert "synthetic-index-probe-key" not in json.dumps(receipt)


def test_refinement_queries_reach_native_chroma_and_postscope_planner(
    multiple_holds, native_indexes, monkeypatch
):
    from chromadb.api.models.Collection import Collection

    queries = []
    original = Collection.query

    def observed(collection, *args, **kwargs):
        queries.append((collection.name, deepcopy(kwargs["query_embeddings"])))
        return original(collection, *args, **kwargs)

    monkeypatch.setattr(Collection, "query", observed)
    receipt = run(
        prepare(multiple_holds, "dev-case-b", arms=(ARMS[1],)),
        {ARMS[1]: native_indexes[ARMS[1]]},
        handler=lambda request: respond(request, refine=True),
    )
    records = receipt["actual_retrievals"]
    assert receipt["completed_routes"] == 1 and receipt["actual_sends"] == 4
    assert [(r["turn_id"], r["logical_retrieval_round"]) for r in records] == [
        ("initial", 1),
        ("initial", 2),
        ("version", 1),
        ("version", 2),
    ]
    assert len(queries) == 12  # 2 one-query rounds + 2 two-query rounds, both collections.
    assert all(r["requested"]["filters"] == {} for r in records)
    attempts = receipt["attempts"]
    assert [a["request"]["evidence"]["retrieval_round"] for a in attempts] == [1, 2, 1, 2]
    final = attempts[-1]["request"]
    assert any(
        hit["source_id"] == "docstring:1.39.0:streamlit.button" for hit in final["evidence"]["hits"]
    )
    assert all(
        not hit["applicable_versions"] or hit["applicable_versions"] == ["1.39.0"]
        for hit in final["evidence"]["hits"]
    )


def test_actual_version_correction_excludes_old_sources_and_stale_approval(
    multiple_holds, native_indexes
):
    original = fixtures_for(ROOT, {"protocol_id": "core-stability-v1"})["dev-case-c"]
    data = deepcopy(original.data)
    data["fixture_id"] = "synthetic-native-version-correction"
    for turn, version in zip(data["turns"], ("1.50.0", "1.49.0"), strict=True):
        turn["visible"] = {
            "message": (
                "streamlit.button icon emoji material symbol company logo custom image. "
                f"The installed version is {version}."
            ),
            "reported_facts": [{"name": "streamlit_version", "value": version}],
            "unknowns": [],
            "context_changed": False,
        }
    fixture = Fixture(
        original.path,
        data,
        original.bundles,
        hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest(),
    )
    receipt = run(
        prepare(multiple_holds, "dev-case-c", fixture=fixture, arms=(ARMS[1],)),
        {ARMS[1]: native_indexes[ARMS[1]]},
    )
    first, corrected = receipt["attempts"]
    assert any(
        hit["applicable_versions"] == ["1.50.0"] for hit in first["request"]["evidence"]["hits"]
    )
    assert any(
        hit["applicable_versions"] == ["1.49.0"] for hit in corrected["request"]["evidence"]["hits"]
    )
    assert not any(
        hit["applicable_versions"] == ["1.50.0"] for hit in corrected["request"]["evidence"]["hits"]
    )
    assert corrected["context"]["case_revision"] == 2
    version_facts = [
        fact
        for fact in corrected["request"]["case"]["facts"]
        if fact["name"] == "streamlit_version"
    ]
    assert {(fact["status"], fact["value"]) for fact in version_facts} == {
        ("superseded", "1.50.0"),
        ("active", "1.49.0"),
    }
    assert all(check["passed"] for check in receipt["jobs"][0]["checks"])
    assert any(
        check["step"] == "correction" and check["detail"] == 409
        for check in receipt["jobs"][0]["checks"]
    )


@pytest.mark.parametrize("bad", ("snapshot", "digest", "extra", "missing"))
def test_bad_index_binding_is_rejected_before_transport_allocation(
    multiple_holds, native_indexes, monkeypatch, bad
):
    binding = deepcopy(native_indexes[ARMS[1]])
    if bad == "snapshot":
        binding["snapshot_id"] = "wrong-snapshot"
    elif bad == "digest":
        binding["manifest_sha256"] = "0" * 64
    elif bad == "extra":
        binding["query_filter"] = {"source_id": "selected-answer"}
    else:
        binding["path"] = str(Path(binding["path"]).parent / "absent-index")
    allocated = []

    def forbidden(*args, **kwargs):
        allocated.append(True)
        raise AssertionError("Provider allocation forbidden")

    monkeypatch.setattr(httpx, "HTTPTransport", forbidden)
    ledger, protocol, batch, fixtures, config = prepare(
        multiple_holds, "dev-case-b", arms=(ARMS[1],)
    )
    before = ledger_observation(ledger._path)
    with offline_network(), pytest.raises(RealIndexProbeRejected):
        run_real_index_batch(
            protocol, batch, fixtures, (), ledger, config, before, {ARMS[1]: binding}
        )
    assert not allocated and ledger_observation(ledger._path) == before


@pytest.mark.parametrize("override", ("catalog_overrides", "conflict_groups"))
def test_real_index_trials_reject_oracle_gap_or_conflict_injection(
    multiple_holds, native_indexes, override
):
    prepared = prepare(multiple_holds, arms=(ARMS[1],))
    prepared[2]["jobs"][0][override] = {} if override == "catalog_overrides" else []
    with pytest.raises(RealIndexProbeRejected):
        run(prepared, {ARMS[1]: native_indexes[ARMS[1]]})


def test_manifest_change_between_rounds_stops_before_a_second_provider_send(
    multiple_holds, tmp_path
):
    with offline_network():
        corpus = build_pilot_corpus(
            ROOT / "streamlit-data-for-dev-test",
            ROOT / "experiments/dev_rag_coverage_v1/split-manifest.json",
            ROOT / "experiments/dev_rag_coverage_v1/allowlist.json",
        )
        path = tmp_path / "mutable-index"
        snapshot = build_index(corpus, path)
    binding = {
        "path": str(path),
        "snapshot_id": snapshot,
        "manifest_sha256": hashlib.sha256((path / MANIFEST_NAME).read_bytes()).hexdigest(),
    }

    def mutate(request):
        response = respond(request, refine=True)
        with (path / MANIFEST_NAME).open("ab") as destination:
            destination.write(b" ")
        return response

    receipt = run(
        prepare(multiple_holds, "dev-case-b", arms=(ARMS[1],)),
        {ARMS[1]: binding},
        handler=mutate,
    )
    assert receipt["actual_sends"] == 1 and receipt["completed_routes"] == 0
    assert receipt["actual_retrievals"][-1]["error_code"] == "RealIndexRetrievalRejected"
    assert receipt["original_accounting_preserved"]
    assert receipt["jobs"][0]["steps"][0]["proposal"]["decision"] is None


def test_same_snapshot_content_mutation_is_rejected_by_preflight(native_indexes, tmp_path):
    with offline_network():
        corpus = build_pilot_corpus(
            ROOT / "streamlit-data-for-dev-test",
            ROOT / "experiments/dev_rag_coverage_v1/split-manifest.json",
            ROOT / "experiments/dev_rag_coverage_v1/allowlist.json",
        )
        path = tmp_path / "changed-index"
        snapshot = build_index(corpus, path)
        binding = {
            "path": str(path),
            "snapshot_id": snapshot,
            "manifest_sha256": hashlib.sha256((path / MANIFEST_NAME).read_bytes()).hexdigest(),
        }
        assert validate_index_bindings({ARMS[1]: binding}) == {ARMS[1]: binding}
        chunk = corpus.manifest["corpus"]["chunks"][0]
        _persistent_client(path).get_collection(
            name="streamlit_docs", embedding_function=None
        ).update(
            ids=[chunk["chunk_id"]],
            documents=["tampered source"],
            embeddings=[lexical_embedding(chunk["document"])],
        )
        with pytest.raises(RealIndexProbeRejected):
            validate_index_bindings({ARMS[1]: binding})


def test_checkpoint_contains_actual_retrieval_not_fixed_fixture_bundle(
    multiple_holds, native_indexes
):
    checkpoints = []
    receipt = run(
        prepare(multiple_holds, "dev-case-b", arms=(ARMS[1],)),
        {ARMS[1]: native_indexes[ARMS[1]]},
        checkpoint=lambda value: checkpoints.append(deepcopy(value)),
    )
    assert len(checkpoints) >= 3
    first = checkpoints[0]
    assert first["event"] == "reserved_before_transport"
    assert len(first["actual_retrievals"]) == 1
    assert (
        first["actual_retrievals"][0]["evidence"]["snapshot_id"]
        == native_indexes[ARMS[1]]["snapshot_id"]
    )
    assert first["actual_retrievals"][0]["evidence"]["snapshot_id"] != "dev-three-seed-evidence-v1"
    assert checkpoints[-1]["actual_retrievals"] == receipt["actual_retrievals"]


@pytest.mark.parametrize("reserve", (True, 0, 32767, 49152))
def test_unsupported_reserve_cannot_enter_registered_real_index_slots(reserve):
    fixtures = fixtures_for(ROOT, {"protocol_id": "core-stability-v1"})
    protocol = {"experiment_id": "synthetic-slot-bound-check"}
    batch = {
        "kind": "real_index",
        "jobs": [
            {
                "job_id": "synthetic-invalid-reserve",
                "case_id": "dev-case-a",
                "arm": ARMS[1],
                "input_token_reserve": reserve,
                "max_output_tokens": 1024,
            }
        ],
    }
    with pytest.raises(DevProbeRejected):
        quality_slots(protocol, batch, fixtures)


def test_32768_slots_bind_exact_price_and_do_not_expand_historical_tiers():
    fixtures = fixtures_for(ROOT, {"protocol_id": "core-stability-v1"})
    protocol = {"experiment_id": "synthetic-slot-bound-check"}
    batch = {
        "kind": "real_index",
        "jobs": [
            {
                "job_id": "synthetic-32768-reserve",
                "case_id": "dev-case-a",
                "arm": ARMS[1],
                "input_token_reserve": 32768,
                "max_output_tokens": 1024,
            }
        ],
    }
    slots = quality_slots(protocol, batch, fixtures)
    assert len(slots) == 4
    assert all(slot.input_token_reserve == 32768 for slot in slots)
    assert all(slot.amount_usd == Decimal("0.006082560") for slot in slots)
    batch["kind"] = "stability"
    with pytest.raises(DevProbeRejected):
        quality_slots(protocol, batch, fixtures)


def test_32768_scope_retains_utf8_guard_before_reservation_or_send(multiple_holds, native_indexes):
    original = fixtures_for(ROOT, {"protocol_id": "core-stability-v1"})["dev-case-b"]
    data = deepcopy(original.data)
    data["fixture_id"] = "synthetic-large-utf8-native-context"
    data["turns"][0]["visible"]["message"] = "ف" * 3000
    data["turns"][0]["visible"]["reported_facts"].append(
        {"name": "reported_diagnostics", "value": "ف" * 5000}
    )
    fixture = Fixture(
        original.path,
        data,
        original.bundles,
        hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest(),
    )
    prepared = prepare(multiple_holds, "dev-case-b", fixture=fixture, arms=(ARMS[1],))
    receipt = run(prepared, {ARMS[1]: native_indexes[ARMS[1]]})
    assert receipt["actual_sends"] == 0 and receipt["completed_routes"] == 0
    assert receipt["attempts"][0]["error_code"] == "ContextLimitExceeded"
    assert receipt["original_accounting_preserved"]
    assert prepared[0].snapshot().reserved_usd == 0
    assert prepared[0].quarantine_scope_status(prepared[2]["scope_id"]).consumed_requests == 0
