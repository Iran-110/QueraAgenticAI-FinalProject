"""The new docs profile adds four exact records without changing the old epoch."""

import json
import shutil
from pathlib import Path

import pytest

from agent_app.contracts import RetrievalRequest
from agent_app.retrieval.adapter import ChromaRetrieverAdapter
from agent_app.retrieval.offline_index import (
    OfflineIndexRejected,
    _persistent_client,
    build_index,
    open_verified_index,
)
from agent_app.retrieval.pilot_corpus import (
    DEV_COVERAGE_PROTOCOL,
    DEV_COVERAGE_REQUIRED_ISSUE_IDS,
    DEV_COVERAGE_SOURCE_PINS,
    PROTOCOL,
    PilotCorpus,
    PilotCorpusRejected,
    build_pilot_corpus,
    canonical_json,
    lexical_embedding,
    sha256,
)
from agent_app.retrieval.retriever import StreamlitRetriever
from agent_app.testing.http_pilot_runtime import offline_network

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "streamlit-data-for-dev-test"
SPLIT = ROOT / "data/evaluation/dev-three-v1/split-manifest.json"
OLD_SPLIT = ROOT / "data/evaluation/split-manifest.json"
ALLOWLIST = ROOT / "experiments/dev_rag_coverage_v1/allowlist.json"
OLD_ALLOWLIST = ROOT / "experiments/corpus/pilot-allowlist.json"
ADDITIONAL_IDS = tuple(sorted(DEV_COVERAGE_SOURCE_PINS))


def _write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _rehashed_manifest(manifest):
    manifest["snapshot_id"] = "docs-pilot-" + sha256(
        canonical_json(manifest["corpus"]).encode("utf-8")
    )
    return manifest


@pytest.fixture(scope="module")
def corpus():
    return build_pilot_corpus(SEED, SPLIT, ALLOWLIST)


@pytest.fixture
def edited_seed(tmp_path):
    destination = tmp_path / "seed"
    shutil.copytree(SEED, destination)
    return destination


def _edit_added_record(seed, source_id, edit, *, duplicate=False):
    relative = "sources/docstrings_scope_candidates.jsonl"
    path = seed / relative
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    row = next(row for row in rows if row["source_id"] == source_id)
    edit(row)
    if duplicate:
        rows.append(row)
    raw = ("\n".join(canonical_json(row) for row in rows) + "\n").encode("utf-8")
    path.write_bytes(raw)
    manifest_path = seed / "manifest.json"
    package = json.loads(manifest_path.read_bytes())
    entry = next(entry for entry in package["files"] if entry["path"] == relative)
    entry.update(bytes=len(raw), sha256=sha256(raw))
    _write_json(manifest_path, package)


def test_four_added_records_are_exact_seed_sources_and_lossless_spans(corpus):
    payload = corpus.manifest["corpus"]
    assert payload["protocol"] == DEV_COVERAGE_PROTOCOL
    assert len(payload["sources"]) == 18
    assert len(payload["chunks"]) == 36
    rows = {
        row["source_id"]: row
        for line in (SEED / "sources/docstrings_scope_candidates.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if (row := json.loads(line))
    }
    for source_id in ADDITIONAL_IDS:
        row = rows[source_id]
        source = next(source for source in payload["sources"] if source["source_id"] == source_id)
        assert {key: source[key] for key in DEV_COVERAGE_SOURCE_PINS[source_id]} == (
            DEV_COVERAGE_SOURCE_PINS[source_id]
        )
        assert source["source_pointer"] == "python/streamlit.json" + row["json_pointer"]
        assert source["source_url"] == row["pinned_source_url"]
        assert source["source_commit"] == row["docs_commit"]
        assert source["applicable_versions"] == [row["version"]]
        chunks = [
            chunk for chunk in payload["chunks"] if chunk["metadata"]["source_id"] == source_id
        ]
        assert len(chunks) == (len(row["text"]) + 3999) // 4000
        assert "".join(chunk["document"] for chunk in chunks) == row["text"]
        for chunk in chunks:
            span = chunk["span"]
            assert chunk["document"] == row["text"][span["start"] : span["end"]]
            assert chunk["metadata"]["version"] == row["version"]
            assert chunk["metadata"]["applicable_versions"] == canonical_json([row["version"]])
            assert sha256(chunk["document"].encode("utf-8")) == chunk["text_sha256"]


def test_old_allowlist_and_both_historical_snapshots_remain_exact(corpus):
    assert sha256(OLD_ALLOWLIST.read_bytes()) == (
        "209037d964182070744f608b79b676eb56c072e7655aee440ad75287aa117729"
    )
    original = build_pilot_corpus(SEED, OLD_SPLIT, OLD_ALLOWLIST)
    assert original.snapshot_id == (
        "docs-pilot-87bdaf9a3dadcefff48a6775ef616f3d3dd5bf1c8cb23a9521b0e11ccaae160c"
    )
    old_dev = build_pilot_corpus(SEED, SPLIT, OLD_ALLOWLIST)
    assert old_dev.snapshot_id == (
        "docs-pilot-10e7fc4bf04652d5a8ab5052fe14ef6508d4295b3a6f0d6aa1796ffc77a095aa"
    )
    old_payload = old_dev.manifest["corpus"]
    assert old_payload["protocol"] == PROTOCOL
    assert len(old_payload["sources"]) == 14 and len(old_payload["chunks"]) == 30
    new_payload = corpus.manifest["corpus"]
    assert new_payload["sources"] == sorted(
        old_payload["sources"]
        + [source for source in new_payload["sources"] if source["source_id"] in ADDITIONAL_IDS],
        key=lambda source: source["source_id"],
    )
    assert [
        chunk
        for chunk in new_payload["chunks"]
        if chunk["metadata"]["source_id"] not in ADDITIONAL_IDS
    ] == old_payload["chunks"]


def test_same_multiselect_body_keeps_distinct_versioned_identities(corpus):
    chunks = corpus.manifest["corpus"]["chunks"]
    old, new = (
        [chunk for chunk in chunks if chunk["metadata"]["source_id"] == source_id]
        for source_id in (
            "docstring:1.49.0:streamlit.multiselect",
            "docstring:1.50.0:streamlit.multiselect",
        )
    )
    assert [chunk["document"] for chunk in old] == [chunk["document"] for chunk in new]
    assert {chunk["chunk_id"] for chunk in old}.isdisjoint({chunk["chunk_id"] for chunk in new})
    assert all(chunk["metadata"]["version"] == "1.49.0" for chunk in old)
    assert all(chunk["metadata"]["version"] == "1.50.0" for chunk in new)


def test_full_conservative_exclusion_set_remains_outside_both_collections(corpus):
    payload = corpus.manifest["corpus"]
    assert len(DEV_COVERAGE_REQUIRED_ISSUE_IDS) == 46
    assert DEV_COVERAGE_REQUIRED_ISSUE_IDS == set(payload["exclusions"]["reserved_issue_ids"])
    assert {2379, 8129, 8180, 9770, 12629, 12782} <= DEV_COVERAGE_REQUIRED_ISSUE_IDS
    assert payload["exclusions"]["indexed_issue_count"] == 0
    assert payload["exclusions"]["indexed_comment_count"] == 0
    assert payload["exclusions"]["family_review_complete"] is False
    assert payload["exclusions"]["split_status"] == "draft_not_frozen"
    assert all(
        source["origin_kind"] in {"docs_markdown", "docs_generated"}
        for source in payload["sources"]
    )
    assert all(chunk["metadata"]["source_type"] == "doc" for chunk in payload["chunks"])
    assert not any("direct-answer" in source["source_id"] for source in payload["sources"])


@pytest.mark.parametrize(
    "mutation",
    [
        "protocol",
        "downgrade",
        "matrix-version",
        "matrix-function",
        "added-version",
        "added-source",
        "added-missing",
        "added-duplicate",
        "exclusions",
        "reservation",
        "reservation-duplicate",
    ],
)
def test_profile_cannot_expand_shrink_or_downgrade_silently(tmp_path, mutation):
    allowlist = json.loads(ALLOWLIST.read_bytes())
    if mutation == "protocol":
        allowlist["protocol"] = "unregistered-profile"
    elif mutation == "downgrade":
        allowlist["protocol"] = PROTOCOL
    elif mutation == "matrix-version":
        allowlist["api_versions"].append("1.39.0")
    elif mutation == "matrix-function":
        allowlist["api_functions"].append("streamlit.multiselect")
    elif mutation == "added-version":
        allowlist["additional_api_source_ids"][0] = "docstring:1.38.0:streamlit.button"
    elif mutation == "added-source":
        allowlist["additional_api_source_ids"][0] = "docstring:1.39.0:streamlit.slider"
    elif mutation == "added-missing":
        allowlist["additional_api_source_ids"].pop()
    elif mutation == "added-duplicate":
        allowlist["additional_api_source_ids"][0] = allowlist["additional_api_source_ids"][1]
    elif mutation == "exclusions":
        allowlist["excluded_source_types"].remove("evaluation")
    elif mutation == "reservation":
        allowlist["required_reserved_issue_ids"].remove(268)
    else:
        allowlist["required_reserved_issue_ids"][0] = allowlist["required_reserved_issue_ids"][1]
    path = tmp_path / "allowlist.json"
    _write_json(path, allowlist)
    with pytest.raises(PilotCorpusRejected, match="^PilotCorpusRejected$"):
        build_pilot_corpus(SEED, SPLIT, path)


@pytest.mark.parametrize("number", [268, 2379, 8129, 8180, 9770, 12629, 12782, 17215])
def test_missing_old_candidate_or_current_family_reservation_is_rejected(tmp_path, number):
    split = json.loads(SPLIT.read_bytes())
    split["exposure_reserved_issue_ids"].remove(number)
    path = tmp_path / "split.json"
    _write_json(path, split)
    with pytest.raises(PilotCorpusRejected, match="^PilotCorpusRejected$"):
        build_pilot_corpus(SEED, path, ALLOWLIST)


def test_historical_one_pilot_split_cannot_authorize_new_profile():
    with pytest.raises(PilotCorpusRejected, match="^PilotCorpusRejected$"):
        build_pilot_corpus(SEED, OLD_SPLIT, ALLOWLIST)


@pytest.mark.parametrize("source_id", ADDITIONAL_IDS)
@pytest.mark.parametrize(
    "mutation", ["rehash-text", "version", "pointer", "url", "type", "duplicate"]
)
def test_four_added_source_pins_survive_repackaged_outer_hashes(edited_seed, source_id, mutation):
    def edit(row):
        if mutation == "rehash-text":
            row["text"] += " changed"
            row["text_sha256"] = sha256(row["text"].encode("utf-8"))
        elif mutation == "version":
            row["version"] = "1.99.0"
        elif mutation == "pointer":
            row["json_pointer"] += "/substitute"
        elif mutation == "url":
            row["source_url"] = "https://docs.streamlit.io/develop/api-reference/widgets/st.slider"
        elif mutation == "type":
            row["type"] = "issue"

    _edit_added_record(edited_seed, source_id, edit, duplicate=mutation == "duplicate")
    with pytest.raises(PilotCorpusRejected, match="^PilotCorpusRejected$"):
        build_pilot_corpus(edited_seed, SPLIT, ALLOWLIST)


@pytest.mark.parametrize(
    "mutation",
    ["profile", "old-profile", "source", "version", "span", "reservation", "issue-count"],
)
def test_self_rehashed_manifest_cannot_change_profile_or_provenance(corpus, mutation):
    manifest = corpus.manifest
    payload = manifest["corpus"]
    chunk = next(
        chunk for chunk in payload["chunks"] if chunk["metadata"]["source_id"] in ADDITIONAL_IDS
    )
    if mutation == "profile":
        payload["protocol"] = "unregistered-profile"
    elif mutation == "old-profile":
        payload["protocol"] = PROTOCOL
    elif mutation == "source":
        payload["sources"] = [
            source for source in payload["sources"] if source["source_id"] != ADDITIONAL_IDS[0]
        ]
    elif mutation == "version":
        chunk["metadata"]["version"] = "1.38.0"
    elif mutation == "span":
        chunk["metadata"]["source_span"] = "chars:1:2699;unit:unicode_codepoint"
    elif mutation == "reservation":
        payload["exclusions"]["reserved_issue_ids"].remove(268)
    else:
        payload["exclusions"]["indexed_issue_count"] = 1
    with pytest.raises(PilotCorpusRejected, match="^PilotManifestRejected$"):
        PilotCorpus.from_manifest(_rehashed_manifest(manifest))


def test_rehashed_historical_profile_cannot_claim_added_coverage():
    manifest = build_pilot_corpus(SEED, SPLIT, OLD_ALLOWLIST).manifest
    manifest["corpus"]["protocol"] = DEV_COVERAGE_PROTOCOL
    with pytest.raises(PilotCorpusRejected, match="^PilotManifestRejected$"):
        PilotCorpus.from_manifest(_rehashed_manifest(manifest))


@pytest.fixture(scope="module")
def native_indexes(tmp_path_factory, corpus):
    directory = tmp_path_factory.mktemp("dev-coverage-native")
    first, second = directory / "first", directory / "second"
    with offline_network():
        assert build_index(corpus, first) == build_index(corpus, second)
        first_client, first_snapshot = open_verified_index(first)
        second_client, second_snapshot = open_verified_index(second)
    assert first_snapshot == second_snapshot == corpus.snapshot_id
    assert first_client.manifest == second_client.manifest == corpus.manifest
    assert (first / "pilot-manifest.json").read_bytes() == (
        second / "pilot-manifest.json"
    ).read_bytes()
    return first_client, second_client, corpus.snapshot_id


@pytest.mark.parametrize("source_id", ADDITIONAL_IDS)
def test_two_native_builds_return_exact_added_version_and_source(native_indexes, corpus, source_id):
    first_client, second_client, snapshot = native_indexes
    expected = {
        chunk["chunk_id"]: chunk
        for chunk in corpus.manifest["corpus"]["chunks"]
        if chunk["metadata"]["source_id"] == source_id
    }
    version = source_id.split(":")[1]
    for client in (first_client, second_client):
        with offline_network():
            retriever = StreamlitRetriever(".", snapshot_id=snapshot, client=client)
            adapter = ChromaRetrieverAdapter(".", snapshot_id=snapshot, core_retriever=retriever)
            bundle = adapter.search(
                RetrievalRequest(
                    snapshot_id=snapshot,
                    queries=("button multiselect fragment rerun",),
                    top_k=5,
                    filters={"version": version, "source_id": source_id},
                )
            )
        assert {hit.chunk_id for hit in bundle.hits} == set(expected)
        for hit in bundle.hits:
            assert hit.source_id == source_id
            assert hit.applicable_versions == (version,)
            assert hit.excerpt == expected[hit.chunk_id]["document"].strip()
            assert hit.source_span == expected[hit.chunk_id]["metadata"]["source_span"]


@pytest.mark.parametrize(
    "filters",
    [
        {"version": "1.31.0"},
        {"version": "1.31.1"},
        {"source_id": "docstring:1.39.0:streamlit.slider"},
        {"source_id": "docstring:1.50.0:streamlit.multiselect", "version": "1.49.0"},
    ],
)
def test_native_filter_cannot_invent_missing_or_wrong_version_source(native_indexes, filters):
    first, _, snapshot = native_indexes
    with offline_network():
        retriever = StreamlitRetriever(".", snapshot_id=snapshot, client=first)
        adapter = ChromaRetrieverAdapter(".", snapshot_id=snapshot, core_retriever=retriever)
        bundle = adapter.search(
            RetrievalRequest(
                snapshot_id=snapshot, queries=("session state button",), top_k=5, filters=filters
            )
        )
    assert bundle.hits == ()


def test_actual_issue_collection_remains_empty(native_indexes):
    first, second, _ = native_indexes
    for client in (first, second):
        with offline_network():
            result = client.get_collection(name="streamlit_issues").query(
                query_texts=["12782 9770 Enum Session State"], n_results=5
            )
        assert result["ids"] == [[]]
        assert result["documents"] == [[]]


@pytest.mark.parametrize("kind", ["added-text", "added-version", "issue-row"])
def test_verified_native_index_denies_changed_added_material_or_case_ingestion(
    tmp_path, corpus, kind
):
    path = tmp_path / "mutated"
    with offline_network():
        build_index(corpus, path)
        verified, _ = open_verified_index(path)
        raw = _persistent_client(path)
        chunk = next(
            chunk
            for chunk in corpus.manifest["corpus"]["chunks"]
            if chunk["metadata"]["source_id"] == ADDITIONAL_IDS[0]
        )
        if kind == "issue-row":
            issues = raw.get_collection(name="streamlit_issues", embedding_function=None)
            issues.add(
                ids=["evaluation-case"],
                documents=["Synthetic excluded issue answer"],
                metadatas=[{"source_type": "issue"}],
                embeddings=[lexical_embedding("Synthetic excluded issue answer")],
            )
        else:
            docs = raw.get_collection(name="streamlit_docs", embedding_function=None)
            if kind == "added-text":
                docs.update(
                    ids=[chunk["chunk_id"]],
                    documents=["Substituted source"],
                    embeddings=[lexical_embedding("Substituted source")],
                )
            else:
                docs.update(
                    ids=[chunk["chunk_id"]], metadatas=[{**chunk["metadata"], "version": "1.38.0"}]
                )
        with pytest.raises(OfflineIndexRejected, match="^PilotIndexChanged$"):
            verified.get_collection(name="streamlit_docs")
        with pytest.raises(OfflineIndexRejected, match="^PilotIndexChanged$"):
            open_verified_index(path)
