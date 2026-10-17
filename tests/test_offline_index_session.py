"""Per-search verification session: same guarantees, two full checks per search.

The in-memory client below mirrors the small part of Chroma's API the verified
reader uses, so these checks run without chromadb. A real-Chroma variant at the
end is skipped when chromadb is unavailable.
"""

import math
from copy import deepcopy
from pathlib import Path

import pytest

from agent_app.retrieval.offline_index import OfflineIndexRejected, VerifiedChromaClient
from agent_app.retrieval.pilot_corpus import (
    MANIFEST_NAME,
    build_pilot_corpus,
    canonical_json,
    lexical_embedding,
)
from agent_app.retrieval.retriever import StreamlitRetriever

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "streamlit-data-for-dev-test"
SPLIT = ROOT / "data/evaluation/split-manifest.json"
ALLOWLIST = ROOT / "experiments/corpus/pilot-allowlist.json"


class MemoryCollection:
    def __init__(self, name, metadata, rows):
        self.name, self.metadata, self.rows = name, dict(metadata), rows
        self.get_calls = 0
        self.after_query = None

    def count(self):
        return len(self.rows)

    def get(self, include):
        self.get_calls += 1
        ids = list(self.rows)
        return {
            "ids": ids,
            "documents": [self.rows[i][0] for i in ids],
            "metadatas": [deepcopy(self.rows[i][1]) for i in ids],
            "embeddings": [list(self.rows[i][2]) for i in ids],
        }

    def query(self, query_embeddings, n_results, include, where=None):
        result = {key: [] for key in ("ids", "documents", "metadatas", "distances")}
        for vector in query_embeddings:
            ranked = sorted((math.dist(vector, row[2]), i) for i, row in self.rows.items())
            ranked = ranked[:n_results]
            result["ids"].append([i for _, i in ranked])
            result["distances"].append([d for d, _ in ranked])
            result["documents"].append([self.rows[i][0] for _, i in ranked])
            result["metadatas"].append([deepcopy(self.rows[i][1]) for _, i in ranked])
        if self.after_query is not None:
            self.after_query(self, result)
        return result


class MemoryClient:
    def __init__(self, corpus):
        metadata = {
            "snapshot_id": corpus.snapshot_id,
            "embedding_kind": "lexical_hash_v1",
            "embedding_dimensions": 256,
            "embedding_quality_claim": False,
            "chunk_characters": 4_000,
            "protocol": corpus.manifest["corpus"]["protocol"],
            "corpus_sha256": corpus.snapshot_id.removeprefix("docs-pilot-"),
            "hnsw:space": "l2",
        }
        rows = {
            chunk["chunk_id"]: (
                chunk["document"],
                deepcopy(chunk["metadata"]),
                lexical_embedding(chunk["document"]),
            )
            for chunk in corpus.manifest["corpus"]["chunks"]
        }
        self.collections = {
            "streamlit_docs": MemoryCollection("streamlit_docs", metadata, rows),
            "streamlit_issues": MemoryCollection("streamlit_issues", metadata, {}),
        }

    def list_collections(self):
        return list(self.collections)

    def get_collection(self, name, embedding_function=None):
        return self.collections[name]

    def full_reads(self):
        return sum(c.get_calls for c in self.collections.values())


@pytest.fixture(scope="module")
def corpus():
    return build_pilot_corpus(SEED, SPLIT, ALLOWLIST)


@pytest.fixture
def opened(tmp_path, corpus):
    raw = (canonical_json(corpus.manifest) + "\n").encode("utf-8")
    (tmp_path / MANIFEST_NAME).write_bytes(raw)
    memory = MemoryClient(corpus)
    client = VerifiedChromaClient(tmp_path, memory, corpus, raw)
    retriever = StreamlitRetriever("", snapshot_id=corpus.snapshot_id, client=client)
    for collection in memory.collections.values():
        collection.get_calls = 0
    return memory, client, retriever


def test_one_search_runs_exactly_two_full_verifications(opened):
    memory, _, retriever = opened
    result = retriever.search("session state widget key", n_results=5)
    assert len(result["docs"]["ids"][0]) == 5
    # One full verification reads both collections: before + after = 2 x 2.
    assert memory.full_reads() == 4


def test_access_outside_a_session_keeps_per_access_verification(opened):
    memory, client, _ = opened
    collection = client.get_collection(name="streamlit_docs")
    collection.query(query_texts=["session state"], n_results=3)
    # get_collection, then before and after the query: three full checks.
    assert memory.full_reads() == 6


def test_nested_sessions_verify_only_at_the_outermost_level(opened):
    memory, client, _ = opened
    with client.read_session():
        with client.read_session():
            client.get_collection(name="streamlit_docs").metadata  # noqa: B018
        client.verify()
    assert memory.full_reads() == 4


def test_storage_mutation_during_a_search_is_rejected_at_the_closing_check(opened, corpus):
    memory, client, retriever = opened
    docs = memory.collections["streamlit_docs"]
    chunk = corpus.manifest["corpus"]["chunks"][0]

    def mutate(collection, result):
        document, metadata, vector = collection.rows[chunk["chunk_id"]]
        collection.rows[chunk["chunk_id"]] = (document, {**metadata, "source_span": "x"}, vector)

    docs.after_query = mutate
    with pytest.raises(OfflineIndexRejected, match="^PilotIndexChanged$"):
        retriever.search("session state", n_results=3)
    docs.after_query = None
    with pytest.raises(OfflineIndexRejected, match="^PilotIndexChanged$"):
        client.verify()


def test_changed_returned_rows_are_still_rejected_inside_a_session(opened):
    memory, client, retriever = opened

    def tamper(collection, result):
        result["documents"][0][0] = "excluded evaluation answer"

    memory.collections["streamlit_docs"].after_query = tamper
    # The retriever maps any rejected read to its fixed code, as before.
    with pytest.raises(RuntimeError, match="^RetrievalUnavailable$"):
        retriever.search("session state", n_results=3)
    with pytest.raises(OfflineIndexRejected, match="^PilotQueryChanged$"):
        with client.read_session():
            client.get_collection(name="streamlit_docs").query(
                query_texts=["session state"], n_results=3
            )


def test_failure_inside_a_session_restores_full_verification(opened):
    memory, client, _ = opened
    with pytest.raises(RuntimeError):
        with client.read_session():
            raise RuntimeError("caller failure")
    before = memory.full_reads()
    client.verify()
    assert memory.full_reads() == before + 2


def test_real_chroma_search_uses_two_full_verifications(tmp_path, corpus, monkeypatch):
    pytest.importorskip("chromadb")
    from agent_app.retrieval import offline_index

    destination = tmp_path / "index"
    snapshot = offline_index.build_index(corpus, destination)
    client, _ = offline_index.open_verified_index(destination)
    calls = []
    original = offline_index.VerifiedChromaClient._full_verify

    def counted(self):
        calls.append(True)
        return original(self)

    monkeypatch.setattr(offline_index.VerifiedChromaClient, "_full_verify", counted)
    retriever = StreamlitRetriever("", snapshot_id=snapshot, client=client)
    calls.clear()
    retriever.search("session state widget key", n_results=5)
    assert len(calls) == 2
