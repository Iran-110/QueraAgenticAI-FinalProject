"""Real local Chroma acceptance, including mutation under unchanged snapshot IDs."""

import json
import socket
import subprocess
import sys
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
from agent_app.retrieval.pilot_corpus import MANIFEST_NAME, build_pilot_corpus, lexical_embedding
from agent_app.retrieval.retriever import StreamlitRetriever
from agent_app.testing.http_pilot_runtime import offline_network

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def corpus():
    return build_pilot_corpus(
        ROOT / "streamlit-data-for-dev-test",
        ROOT / "data/evaluation/split-manifest.json",
        ROOT / "experiments/corpus/pilot-allowlist.json",
    )


@pytest.fixture
def local_index(tmp_path, corpus):
    path = tmp_path / "pilot-index"
    with offline_network():
        snapshot = build_index(corpus, path)
        client, reopened = open_verified_index(path)
    assert reopened == snapshot == corpus.snapshot_id
    return path, client, snapshot


def test_actual_chroma_search_uses_existing_mapper_without_network_or_embedding_model(
    tmp_path, corpus, monkeypatch
):
    from chromadb.api.models.Collection import Collection

    def forbid_embedding(*args, **kwargs):
        raise AssertionError("DefaultEmbeddingForbidden")

    monkeypatch.setattr(Collection, "_embed", forbid_embedding)
    with offline_network():
        with pytest.raises(RuntimeError, match="^OfflineNetworkBlocked$"):
            socket.getaddrinfo("example.invalid", 443)
        path = tmp_path / "pilot"
        build_index(corpus, path)
        client, snapshot = open_verified_index(path)
        retriever = StreamlitRetriever(".", snapshot_id=snapshot, client=client)
        adapter = ChromaRetrieverAdapter(".", snapshot_id=snapshot, core_retriever=retriever)
        bundle = adapter.search(
            RetrievalRequest(
                snapshot_id=snapshot,
                queries=("session state widget rerun", "button click reset"),
                top_k=5,
            )
        )
    assert bundle.snapshot_id == snapshot
    assert bundle.queries_used == ("session state widget rerun", "button click reset")
    assert 0 < len(bundle.hits) <= 5
    chunks = {chunk["chunk_id"]: chunk for chunk in corpus.manifest["corpus"]["chunks"]}
    for hit in bundle.hits:
        chunk = chunks[hit.chunk_id]
        assert hit.excerpt == chunk["document"].strip()
        assert hit.source_type == "doc"
        assert hit.source_span == chunk["metadata"]["source_span"]
        assert hit.applicable_versions == tuple(
            json.loads(chunk["metadata"]["applicable_versions"])
        )
    assert client.get_collection(name="streamlit_issues").query(
        query_texts=["button"], n_results=3
    )["ids"] == [[]]


def test_native_filter_preserves_exact_version_not_docs_commit(local_index):
    _, client, snapshot = local_index
    retriever = StreamlitRetriever(".", snapshot_id=snapshot, client=client)
    adapter = ChromaRetrieverAdapter(".", snapshot_id=snapshot, core_retriever=retriever)
    with offline_network():
        bundle = adapter.search(
            RetrievalRequest(
                snapshot_id=snapshot,
                queries=("button rerun session",),
                top_k=5,
                filters={"version": "1.49.0"},
            )
        )
    assert bundle.hits
    assert all(hit.applicable_versions == ("1.49.0",) for hit in bundle.hits)


@pytest.mark.parametrize(
    "kind",
    [
        "document",
        "metadata",
        "embedding",
        "delete",
        "extra",
        "issues",
        "collection",
        "extra_collection",
    ],
)
def test_same_snapshot_label_does_not_hide_any_persisted_mutation(local_index, corpus, kind):
    path, verified, snapshot = local_index
    raw = _persistent_client(path)
    docs = raw.get_collection(name="streamlit_docs", embedding_function=None)
    chunk = corpus.manifest["corpus"]["chunks"][0]
    id = chunk["chunk_id"]
    if kind == "document":
        docs.update(
            ids=[id], documents=["changed"], embeddings=[lexical_embedding(chunk["document"])]
        )
    elif kind == "metadata":
        docs.update(ids=[id], metadatas=[{**chunk["metadata"], "source_commit": "0" * 40}])
    elif kind == "embedding":
        docs.update(ids=[id], embeddings=[lexical_embedding("different words unrelated")])
    elif kind == "delete":
        docs.delete(ids=[id])
    elif kind in {"extra", "issues"}:
        collection = (
            docs
            if kind == "extra"
            else raw.get_collection(name="streamlit_issues", embedding_function=None)
        )
        collection.add(
            ids=["unapproved"],
            documents=["not approved"],
            metadatas=[{"source_type": "issue"}],
            embeddings=[lexical_embedding("not approved")],
        )
    elif kind == "collection":
        metadata = {key: value for key, value in docs.metadata.items() if key != "hnsw:space"}
        docs.modify(metadata={**metadata, "embedding_kind": "changed", "snapshot_id": snapshot})
    else:
        raw.create_collection(name="unapproved_extra", embedding_function=None)
    assert docs.metadata["snapshot_id"] == snapshot
    with pytest.raises(OfflineIndexRejected, match="^PilotIndexChanged$"):
        verified.get_collection(name="streamlit_docs")
    with pytest.raises(OfflineIndexRejected, match="^PilotIndexChanged$"):
        open_verified_index(path)


def test_same_id_collection_replacement_fails(local_index, corpus):
    path, verified, snapshot = local_index
    raw = _persistent_client(path)
    metadata = raw.get_collection(name="streamlit_docs", embedding_function=None).metadata
    raw.delete_collection(name="streamlit_docs")
    docs = raw.create_collection(name="streamlit_docs", metadata=metadata, embedding_function=None)
    first = corpus.manifest["corpus"]["chunks"][0]
    docs.add(
        ids=[first["chunk_id"]],
        documents=[first["document"]],
        metadatas=[first["metadata"]],
        embeddings=[lexical_embedding(first["document"])],
    )
    assert docs.metadata["snapshot_id"] == snapshot
    with pytest.raises(OfflineIndexRejected, match="^PilotIndexChanged$"):
        verified.verify()


def test_mutation_during_native_query_rejects_entire_return(local_index, corpus, monkeypatch):
    from chromadb.api.models.Collection import Collection

    path, verified, _ = local_index
    collection = verified.get_collection(name="streamlit_docs")
    native = Collection.query
    chunk = corpus.manifest["corpus"]["chunks"][0]

    def query_then_mutate(self, *args, **kwargs):
        result = native(self, *args, **kwargs)
        self.update(
            ids=[chunk["chunk_id"]], metadatas=[{**chunk["metadata"], "source_span": "wrong"}]
        )
        return result

    monkeypatch.setattr(Collection, "query", query_then_mutate)
    with pytest.raises(OfflineIndexRejected, match="^PilotIndexChanged$"):
        collection.query(query_texts=["session state"], n_results=3)
    with pytest.raises(OfflineIndexRejected, match="^PilotIndexChanged$"):
        open_verified_index(path)


def test_transient_write_query_restore_rejects_unapproved_return_even_with_valid_storage(
    local_index, corpus, monkeypatch
):
    from chromadb.api.models.Collection import Collection

    _, verified, _ = local_index
    collection = verified.get_collection(name="streamlit_docs")
    native = Collection.query
    chunk = corpus.manifest["corpus"]["chunks"][0]
    restored = []

    def swap_query_restore(self, *args, **kwargs):
        self.update(
            ids=[chunk["chunk_id"]],
            documents=["excluded evaluation answer"],
            embeddings=[lexical_embedding(chunk["document"])],
        )
        try:
            result = native(self, *args, **kwargs)
            assert "excluded evaluation answer" in result["documents"][0]
            return result
        finally:
            self.update(
                ids=[chunk["chunk_id"]],
                documents=[chunk["document"]],
                embeddings=[lexical_embedding(chunk["document"])],
            )
            restored.append(True)

    monkeypatch.setattr(Collection, "query", swap_query_restore)
    with pytest.raises(OfflineIndexRejected, match="^PilotQueryChanged$"):
        collection.query(query_texts=[chunk["document"]], n_results=30)
    assert restored == [True]
    # Database pre/post checks pass: rejection must come from returned-row validation.
    verified.verify()


@pytest.mark.parametrize(
    "mutation",
    [
        "id",
        "document",
        "metadata",
        "batch_count",
        "column_length",
        "duplicate",
        "result_limit",
        "distance",
        "issues",
    ],
)
def test_native_result_shapes_and_material_are_checked_independently_of_storage(
    local_index, monkeypatch, mutation
):
    from chromadb.api.models.Collection import Collection

    _, verified, _ = local_index
    name = "streamlit_issues" if mutation == "issues" else "streamlit_docs"
    collection = verified.get_collection(name=name)
    native = Collection.query

    def changed_result(self, *args, **kwargs):
        result = native(self, *args, **kwargs)
        if mutation == "issues":
            result.update(
                ids=[["unapproved"]], documents=[["excluded"]], metadatas=[[{}]], distances=[[0.0]]
            )
        elif mutation == "id":
            result["ids"][0][0] = "unapproved"
        elif mutation == "document":
            result["documents"][0][0] = "excluded answer"
        elif mutation == "metadata":
            result["metadatas"][0][0]["source_commit"] = "0" * 40
        elif mutation == "batch_count":
            for column in ("ids", "documents", "metadatas", "distances"):
                result[column].append([])
        elif mutation == "column_length":
            result["documents"][0].pop()
        elif mutation == "duplicate":
            for column in ("ids", "documents", "metadatas", "distances"):
                result[column][0][1] = result[column][0][0]
        elif mutation == "result_limit":
            for column in ("ids", "documents", "metadatas", "distances"):
                result[column][0].append(result[column][0][0])
        else:
            result["distances"][0][0] = float("nan")
        return result

    monkeypatch.setattr(Collection, "query", changed_result)
    with pytest.raises(OfflineIndexRejected, match="^PilotQueryChanged$"):
        collection.query(query_texts=["session state"], n_results=3)
    verified.verify()


def test_manifest_mutation_is_rejected_even_before_database_changes(local_index):
    path, client, _ = local_index
    manifest_path = path / MANIFEST_NAME
    manifest_path.write_bytes(manifest_path.read_bytes() + b" ")
    with pytest.raises(OfflineIndexRejected, match="^PilotIndexChanged$"):
        client.verify()
    manifest = json.loads(manifest_path.read_text())
    manifest["corpus"]["chunks"][0]["metadata"]["version"] = "9.99.0"
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(OfflineIndexRejected, match="^PilotIndexOpenRejected$"):
        open_verified_index(path)


def test_exclusive_build_refuses_existing_even_empty_directory(tmp_path, corpus, local_index):
    path, client, _ = local_index
    before = (path / MANIFEST_NAME).read_bytes()
    with pytest.raises(OfflineIndexRejected, match="^PilotIndexAlreadyExists$"):
        build_index(corpus, path)
    client.verify()
    assert (path / MANIFEST_NAME).read_bytes() == before
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(OfflineIndexRejected, match="^PilotIndexAlreadyExists$"):
        build_index(corpus, empty)
    assert list(empty.iterdir()) == []


def test_missing_or_partial_index_never_gets_created_by_open(tmp_path):
    absent = tmp_path / "absent"
    with pytest.raises(OfflineIndexRejected, match="^PilotIndexOpenRejected$"):
        open_verified_index(absent)
    assert not absent.exists()
    incomplete = tmp_path / "incomplete"
    incomplete.mkdir()
    (incomplete / "chroma.sqlite3").write_bytes(b"")
    with pytest.raises(OfflineIndexRejected, match="^PilotIndexOpenRejected$"):
        open_verified_index(incomplete)
    assert list(incomplete.iterdir()) == [incomplete / "chroma.sqlite3"]


def test_facade_exposes_only_allowlisted_reads_and_detached_manifest(local_index):
    _, client, _ = local_index
    assert not hasattr(client, "create_collection")
    assert not hasattr(client.get_collection(name="streamlit_docs"), "add")
    with pytest.raises(OfflineIndexRejected, match="^PilotCollectionRejected$"):
        client.get_collection(name="unknown")
    changed = client.manifest
    changed["corpus"]["chunks"][0]["document"] = "wrong"
    assert changed != client.manifest


def test_query_errors_are_fixed_without_echoing_input(local_index):
    _, client, _ = local_index
    docs = client.get_collection(name="streamlit_docs")
    with pytest.raises(OfflineIndexRejected, match="^PilotQueryRejected$"):
        docs.query(query_texts=[" "], n_results=3)
    with pytest.raises(OfflineIndexRejected, match="^PilotQueryUnavailable$"):
        docs.query(query_texts=["secret query"], n_results=3, where={"$unknown": "secret"})


def test_fresh_process_reopens_real_chroma_and_retains_exact_content(local_index):
    path, _, snapshot = local_index
    code = """
import json, sys
from agent_app.retrieval.offline_index import open_verified_index
from agent_app.testing.http_pilot_runtime import offline_network
with offline_network():
    client, snapshot = open_verified_index(sys.argv[1])
    rows = client.get_collection(name='streamlit_docs').query(query_texts=['button rerun'], n_results=3)
    print(json.dumps({'snapshot': snapshot, 'count': len(rows['ids'][0]), 'sources': len(client.manifest['corpus']['sources'])}))
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(path)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0
    assert json.loads(result.stdout) == {"snapshot": snapshot, "count": 3, "sources": 14}


def test_cli_reports_bounded_scope_and_refuses_rebuild(tmp_path):
    destination = tmp_path / "cli-index"
    command = [
        sys.executable,
        str(ROOT / "scripts/build_pilot_index.py"),
        "--destination",
        str(destination),
    ]
    result = subprocess.run(
        command, cwd=ROOT, capture_output=True, text=True, timeout=60, check=False
    )
    assert result.returncode == 0
    receipt = json.loads(result.stdout)
    assert receipt["accepted"] is True
    assert receipt["sources"] == 14 and receipt["chunks"] == 30
    assert receipt["indexed_issues"] == receipt["indexed_comments"] == 0
    assert receipt["split_status"] == "draft_not_frozen"
    assert receipt["embedding"] == {
        "kind": "lexical_hash_v1",
        "dimensions": 256,
        "quality_claim": False,
    }
    before = (destination / MANIFEST_NAME).read_bytes()
    retry = subprocess.run(
        command, cwd=ROOT, capture_output=True, text=True, timeout=60, check=False
    )
    assert retry.returncode == 1
    assert json.loads(retry.stdout) == {
        "accepted": False,
        "diagnostic": "OfflinePilotBuildRejected",
    }
    assert (destination / MANIFEST_NAME).read_bytes() == before
