"""Read existing, snapshot-bound Chroma collections without building an index."""

from copy import deepcopy
from typing import Any

from pydantic import ValidationError

from agent_app.contracts import EvidenceBundle, RetrievalRequest


class StreamlitRetriever:
    def __init__(
        self,
        base_path: str,
        db_path: str = "./.chroma_db",
        *,
        snapshot_id: str,
        client: Any = None,
    ):
        try:
            self.snapshot_id = EvidenceBundle(snapshot_id=snapshot_id).snapshot_id
        except (ValidationError, TypeError, ValueError):
            raise ValueError("InvalidRetrievalConfiguration") from None
        self.base_path = base_path
        if client is None:
            try:
                from chromadb import PersistentClient

                client = PersistentClient(path=db_path)
            except Exception:
                raise RuntimeError("RetrievalUnavailable") from None
        self.client = client
        self._collections()

    def _collections(self):
        # Obtain fresh handles: cached metadata would miss a replaced collection.
        try:
            docs = self.client.get_collection(name="streamlit_docs")
            issues = self.client.get_collection(name="streamlit_issues")
            metadata = (docs.metadata, issues.metadata)
        except Exception:
            raise RuntimeError("RetrievalUnavailable") from None
        if any(
            not isinstance(item, dict) or item.get("snapshot_id") != self.snapshot_id
            for item in metadata
        ):
            raise RuntimeError("RetrievalSnapshotMismatch")
        self.docs_collection = docs
        self.issues_collection = issues
        return docs, issues

    def index_data(self):
        # Ingestion needs a frozen exclusion manifest and a separate index builder.
        # This read adapter must never create or relabel an unverified corpus.
        raise RuntimeError("UnsupportedIndexBuild")

    @staticmethod
    def _where(filters: dict[str, str | tuple[str, ...]]) -> dict | None:
        clauses = []
        for key, value in filters.items():
            if key.startswith("$") or (isinstance(value, tuple) and not value):
                raise ValueError("InvalidRetrievalFilter")
            clauses.append(
                {key: {"$in": list(value)}} if isinstance(value, tuple) else {key: value}
            )
        if len(clauses) > 1:
            return {"$and": clauses}
        return clauses[0] if clauses else None

    def search(
        self,
        query: str,
        n_results: int = 3,
        *,
        filters: dict[str, str | tuple[str, ...]] | None = None,
    ):
        try:
            request = RetrievalRequest(
                queries=(query,),
                snapshot_id=self.snapshot_id,
                top_k=n_results,
                filters={} if filters is None else filters,
            )
        except (ValidationError, TypeError, ValueError):
            raise ValueError("InvalidRetrievalRequest") from None
        where = self._where(request.filters)
        docs, issues = self._collections()
        results = {}
        for name, collection in (("docs", docs), ("issues", issues)):
            arguments = {"query_texts": list(request.queries), "n_results": request.top_k}
            if where is not None:
                arguments["where"] = deepcopy(where)
            try:
                results[name] = collection.query(**arguments)
            except Exception:
                raise RuntimeError("RetrievalUnavailable") from None
        # A metadata update/replacement during either read invalidates this result.
        # This cannot certify immutable content when a writer reuses the same ID.
        self._collections()
        return results
