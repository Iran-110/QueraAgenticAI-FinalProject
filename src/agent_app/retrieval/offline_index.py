"""Build real Chroma storage with local lexical vectors and verified read access."""

import math
from copy import deepcopy
from pathlib import Path
from threading import RLock
from typing import Any

from agent_app.retrieval.pilot_corpus import (
    COLLECTION_NAMES,
    EMBEDDING_DIMENSIONS,
    MANIFEST_NAME,
    PilotCorpus,
    canonical_json,
    embedding_sha256,
    lexical_embedding,
)

_ADD_BATCH = 500


class OfflineIndexRejected(RuntimeError):
    """Fixed fail-closed diagnostics, without raw database or source errors."""


def _persistent_client(path: Path) -> Any:
    # Import lazily; no default embedding function or model is instantiated.
    from chromadb import PersistentClient
    from chromadb.config import Settings

    return PersistentClient(path=str(path), settings=Settings(anonymized_telemetry=False))


def _collection_metadata(corpus: PilotCorpus) -> dict[str, str | int | bool]:
    return {
        "snapshot_id": corpus.snapshot_id,
        "embedding_kind": "lexical_hash_v1",
        "embedding_dimensions": EMBEDDING_DIMENSIONS,
        "embedding_quality_claim": False,
        "chunk_characters": 4_000,
        "protocol": corpus.manifest["corpus"]["protocol"],
        "corpus_sha256": corpus.snapshot_id.removeprefix("docs-pilot-"),
        "hnsw:space": "l2",
    }


class VerifiedChromaClient:
    """Read facade bound to exact manifest bytes and exact persisted records.

    A snapshot label alone is insufficient: every read checks membership, full
    documents, scalar metadata, vectors and both collection metadata dictionaries.
    This catches a writer reusing the same snapshot ID. It does not claim an
    interprocess transaction or make the database file itself read-only.
    """

    def __init__(self, path: Path, client: Any, corpus: PilotCorpus, raw_manifest: bytes):
        self._path = path
        self._client = client
        self._corpus = corpus
        self._raw_manifest = raw_manifest
        self._lock = RLock()
        self._expected = {chunk["chunk_id"]: chunk for chunk in corpus.manifest["corpus"]["chunks"]}
        # Expected vectors are a pure function of the frozen documents. Computing
        # them once keeps every later verification exactly as strict, but makes
        # it independent of corpus size times the number of reads per search.
        self._vectors = {
            chunk_id: lexical_embedding(chunk["document"])
            for chunk_id, chunk in self._expected.items()
        }
        self.snapshot_id = corpus.snapshot_id
        self.verify()

    @property
    def manifest(self) -> dict[str, Any]:
        with self._lock:
            self.verify()
            return self._corpus.manifest

    def verify(self) -> None:
        with self._lock:
            try:
                if (self._path / MANIFEST_NAME).read_bytes() != self._raw_manifest:
                    raise ValueError
                names = {
                    item if isinstance(item, str) else item.name
                    for item in self._client.list_collections()
                }
                if names != set(COLLECTION_NAMES):
                    raise ValueError
                for name in COLLECTION_NAMES:
                    collection = self._client.get_collection(name=name, embedding_function=None)
                    if collection.metadata != _collection_metadata(self._corpus):
                        raise ValueError
                    rows = collection.get(include=["documents", "metadatas", "embeddings"])
                    ids = rows["ids"]
                    expected = self._expected if name == "streamlit_docs" else {}
                    if collection.count() != len(expected) or len(ids) != len(expected):
                        raise ValueError
                    if len(set(ids)) != len(ids) or set(ids) != set(expected):
                        raise ValueError
                    if not ids:
                        continue
                    for column in ("documents", "metadatas", "embeddings"):
                        if rows[column] is None or len(rows[column]) != len(ids):
                            raise ValueError
                    for index, chunk_id in enumerate(ids):
                        chunk = expected[chunk_id]
                        if rows["documents"][index] != chunk["document"]:
                            raise ValueError
                        if rows["metadatas"][index] != chunk["metadata"]:
                            raise ValueError
                        vector = [float(value) for value in rows["embeddings"][index]]
                        if len(vector) != EMBEDDING_DIMENSIONS:
                            raise ValueError
                        if vector != self._vectors[chunk_id]:
                            raise ValueError
                        if embedding_sha256(vector) != chunk["embedding_sha256"]:
                            raise ValueError
            except Exception:
                raise OfflineIndexRejected("PilotIndexChanged") from None

    def get_collection(self, *, name: str) -> "VerifiedCollection":
        if name not in COLLECTION_NAMES:
            raise OfflineIndexRejected("PilotCollectionRejected")
        with self._lock:
            self.verify()
            return VerifiedCollection(self, name)


class VerifiedCollection:
    def __init__(self, client: VerifiedChromaClient, name: str):
        self._owner = client
        self.name = name

    @property
    def metadata(self) -> dict[str, Any]:
        with self._owner._lock:
            self._owner.verify()
            collection = self._owner._client.get_collection(name=self.name, embedding_function=None)
            result = deepcopy(collection.metadata)
            self._owner.verify()
            return result

    def query(
        self, *, query_texts: list[str], n_results: int, where: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if (
            not isinstance(query_texts, list)
            or not query_texts
            or any(not isinstance(text, str) or not text.strip() for text in query_texts)
            or type(n_results) is not int
            or not 1 <= n_results <= 100
        ):
            raise OfflineIndexRejected("PilotQueryRejected")
        with self._owner._lock:
            self._owner.verify()
            try:
                collection = self._owner._client.get_collection(
                    name=self.name, embedding_function=None
                )
                arguments: dict[str, Any] = {
                    "query_embeddings": [lexical_embedding(text) for text in query_texts],
                    "n_results": n_results,
                    "include": ["documents", "metadatas", "distances"],
                }
                if where is not None:
                    arguments["where"] = deepcopy(where)
                result = collection.query(**arguments)
            except Exception:
                raise OfflineIndexRejected("PilotQueryUnavailable") from None
            self._owner.verify()
            self._verify_result(result, len(query_texts), n_results)
            return result

    def _verify_result(self, result: Any, query_count: int, n_results: int) -> None:
        """Validate returned material too: a transient writer may restore storage.

        Pre/post verification establishes the stored corpus at those checkpoints.
        It cannot establish what the native query read between them. Every returned
        source row must independently match its frozen approved material.
        """
        try:
            columns = ("ids", "documents", "metadatas", "distances")
            if not isinstance(result, dict):
                raise ValueError
            for column in columns:
                if not isinstance(result[column], list) or len(result[column]) != query_count:
                    raise ValueError
            expected = self._owner._expected if self.name == "streamlit_docs" else {}
            for batch in range(query_count):
                ids = result["ids"][batch]
                if not isinstance(ids, list) or len(ids) > n_results:
                    raise ValueError
                if any(not isinstance(chunk_id, str) for chunk_id in ids):
                    raise ValueError
                if len(set(ids)) != len(ids):
                    raise ValueError
                for column in columns[1:]:
                    values = result[column][batch]
                    if not isinstance(values, list) or len(values) != len(ids):
                        raise ValueError
                for row, chunk_id in enumerate(ids):
                    chunk = expected[chunk_id]
                    if result["documents"][batch][row] != chunk["document"]:
                        raise ValueError
                    if result["metadatas"][batch][row] != chunk["metadata"]:
                        raise ValueError
                    distance = result["distances"][batch][row]
                    if type(distance) not in (int, float) or not math.isfinite(distance):
                        raise ValueError
        except Exception:
            raise OfflineIndexRejected("PilotQueryChanged") from None


def build_index(corpus: PilotCorpus, destination: str | Path) -> str:
    """Create a new directory exclusively; a failed/previous build is never overwritten."""
    path = Path(destination)
    try:
        # Revalidate even if a caller directly constructed the frozen dataclass.
        corpus = PilotCorpus.from_manifest(corpus.manifest)
        path.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        raise OfflineIndexRejected("PilotIndexAlreadyExists") from None
    except Exception:
        raise OfflineIndexRejected("PilotIndexBuildRejected") from None
    try:
        client = _persistent_client(path)
        metadata = _collection_metadata(corpus)
        docs = client.create_collection(
            name="streamlit_docs", metadata=metadata, embedding_function=None
        )
        client.create_collection(
            name="streamlit_issues", metadata=metadata, embedding_function=None
        )
        chunks = corpus.manifest["corpus"]["chunks"]
        # Bounded batches stay below Chroma's per-call limit for larger profiles;
        # historical profiles fit in one batch, so their writes are unchanged.
        for start in range(0, len(chunks), _ADD_BATCH):
            batch = chunks[start : start + _ADD_BATCH]
            docs.add(
                ids=[chunk["chunk_id"] for chunk in batch],
                documents=[chunk["document"] for chunk in batch],
                metadatas=[chunk["metadata"] for chunk in batch],
                embeddings=[lexical_embedding(chunk["document"]) for chunk in batch],
            )
        raw = (canonical_json(corpus.manifest) + "\n").encode("utf-8")
        with (path / MANIFEST_NAME).open("xb") as output:
            output.write(raw)
        VerifiedChromaClient(path, client, corpus, raw)
    except Exception:
        # Keep a failed build for inspection; retries require a fresh destination.
        raise OfflineIndexRejected("PilotIndexBuildRejected") from None
    return corpus.snapshot_id


def open_verified_index(path: str | Path) -> tuple[VerifiedChromaClient, str]:
    """Open only an existing complete index and verify it before returning a read facade."""
    import json

    directory = Path(path)
    try:
        if not (directory / "chroma.sqlite3").is_file():
            raise ValueError
        raw = (directory / MANIFEST_NAME).read_bytes()
        corpus = PilotCorpus.from_manifest(json.loads(raw))
        client = _persistent_client(directory)
        verified = VerifiedChromaClient(directory, client, corpus, raw)
    except OfflineIndexRejected:
        raise
    except Exception:
        raise OfflineIndexRejected("PilotIndexOpenRejected") from None
    return verified, corpus.snapshot_id
