"""Map native retrieval rows to the core port without rewriting source evidence."""

import argparse
import json
from collections.abc import Mapping
from typing import Any

from agent_app.contracts import EvidenceBundle, EvidenceHit, RetrievalRequest
from agent_app.retrieval.relevance import rank_candidates
from agent_app.retrieval.retriever import StreamlitRetriever


class RetrievalAdapterRejected(ValueError):
    """Fixed diagnostic codes; backend inputs/errors never become messages."""


def _versions(metadata: dict) -> tuple:
    if "applicable_versions" in metadata:
        value = metadata["applicable_versions"]
        if isinstance(value, str):
            value = json.loads(value)
        if not isinstance(value, (list, tuple)):
            raise RetrievalAdapterRejected("InvalidEvidenceMetadata")
        return tuple(value)
    version = metadata.get("version")
    return () if version is None else (version,)


def _rows(result: Any, collection: str):
    if not isinstance(result, dict):
        raise RetrievalAdapterRejected("InvalidRetrievalRows")
    columns = []
    for key in ("ids", "documents", "metadatas"):
        batches = result.get(key)
        if not isinstance(batches, list) or len(batches) != 1 or not isinstance(batches[0], list):
            raise RetrievalAdapterRejected("InvalidRetrievalRows")
        columns.append(batches[0])
    if len({len(column) for column in columns}) != 1:
        raise RetrievalAdapterRejected("InvalidRetrievalRows")
    for native_id, text, metadata in zip(*columns, strict=True):
        if type(native_id) is not str or not native_id or not isinstance(metadata, dict):
            raise RetrievalAdapterRejected("InvalidRetrievalRows")
        # Canonical IDs may differ from collection storage keys. Older rows
        # retain deterministic namespaced IDs without inventing provenance.
        prefix = "doc" if collection == "docs" else "issue"
        source_type = metadata.get("source_type", "doc" if collection == "docs" else "issue")
        yield EvidenceHit(
            chunk_id=metadata.get("chunk_id", f"{prefix}:{native_id}"),
            source_id=metadata.get(
                "source_id", native_id if collection == "docs" else f"issue-{native_id}"
            ),
            excerpt=text,
            source_url=metadata.get("source_url", metadata.get("html_url")),
            source_type=source_type,
            source_commit=metadata.get("source_commit", metadata.get("docs_commit")),
            source_span=metadata.get("source_span"),
            applicable_versions=_versions(metadata),
            score=metadata.get("score"),
            score_kind=metadata.get("score_kind"),
        )


class ChromaRetrieverAdapter:
    def __init__(
        self, base_path: str, *, snapshot_id: str, core_retriever=None, selection_policy="native"
    ):
        if type(selection_policy) is not str or selection_policy not in {
            "native",
            "query_relevance_v1",
        }:
            raise RetrievalAdapterRejected("InvalidSelectionPolicy")
        self.selection_policy = selection_policy
        try:
            self.snapshot_id = EvidenceBundle(snapshot_id=snapshot_id).snapshot_id
        except Exception:
            raise RetrievalAdapterRejected("InvalidConfiguredSnapshot") from None
        self.base_path = base_path
        self.core_retriever = (
            core_retriever
            if core_retriever is not None
            else StreamlitRetriever(base_path=base_path, snapshot_id=self.snapshot_id)
        )
        self._check_backend_snapshot()

    def _check_backend_snapshot(self):
        configured = getattr(self.core_retriever, "snapshot_id", self.snapshot_id)
        if configured != self.snapshot_id:
            raise RetrievalAdapterRejected("RetrievalSnapshotMismatch")

    def search(self, request: RetrievalRequest) -> EvidenceBundle:
        if not isinstance(request, RetrievalRequest):
            raise RetrievalAdapterRejected("InvalidRetrievalRequest")
        try:
            request = RetrievalRequest.model_validate(request.model_dump(warnings=False))
        except Exception:
            raise RetrievalAdapterRejected("InvalidRetrievalRequest") from None
        if request.snapshot_id != self.snapshot_id:
            raise RetrievalAdapterRejected("RetrievalSnapshotMismatch")
        self._check_backend_snapshot()
        all_hits = {}
        positions = {}
        for query_index, query in enumerate(request.queries):
            try:
                raw_results = self.core_retriever.search(
                    query=query, n_results=request.top_k, filters=dict(request.filters)
                )
            except Exception:
                raise RetrievalAdapterRejected("RetrievalBackendUnavailable") from None
            try:
                if not isinstance(raw_results, Mapping):
                    raise RetrievalAdapterRejected("InvalidRetrievalRows")
                for collection in ("docs", "issues"):
                    for rank, hit in enumerate(_rows(raw_results[collection], collection), 1):
                        if self.selection_policy == "query_relevance_v1" and rank > request.top_k:
                            raise RetrievalAdapterRejected("InvalidRetrievalRows")
                        previous = all_hits.get(hit.chunk_id)
                        if previous is not None and previous != hit:
                            raise RetrievalAdapterRejected("ConflictingEvidenceChunk")
                        all_hits.setdefault(hit.chunk_id, hit)
                        if self.selection_policy == "query_relevance_v1":
                            positions.setdefault(hit.chunk_id, []).append(
                                (query_index, collection, rank)
                            )
            except RetrievalAdapterRejected:
                raise
            except Exception:
                raise RetrievalAdapterRejected("InvalidEvidenceMetadata") from None
        self._check_backend_snapshot()
        hits = tuple(all_hits.values())
        if self.selection_policy == "query_relevance_v1":
            hits = rank_candidates(hits, request.queries, positions)
        hits = hits[: request.top_k]
        return EvidenceBundle(
            snapshot_id=self.snapshot_id,
            hits=hits,
            queries_used=request.queries,
            warnings=() if hits else ("No evidence found in the configured retrieval snapshot.",),
        )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--smoke", action="store_true", help="Run the fixed offline adapter/core pilot."
    )
    options = parser.parse_args(argv)
    if not options.smoke:
        parser.print_help()
        return 2
    from agent_app.testing.chroma_binding import factory
    from agent_app.testing.retrieval_acceptance import run_acceptance

    receipt = run_acceptance(factory)
    print(
        json.dumps(
            {
                "accepted": receipt["accepted"],
                "checks_passed": receipt["checks_passed"],
                "checks_total": receipt["checks_total"],
                "fixture_backend": True,
                "real_model_tested": False,
                "production_index_or_embedding_tested": False,
                "actual_cost_usd": 0,
                "quality_claim": False,
            }
        )
    )
    return 0 if receipt["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
