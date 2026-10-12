"""Native Chroma result mapping tested without an index, embeddings, or network."""

import builtins
from copy import deepcopy

import pytest

from agent_app.contracts import EvidenceBundle, EvidenceHit, RetrievalRequest
from agent_app.retrieval.adapter import ChromaRetrieverAdapter

SNAPSHOT = "offline-adapter-snapshot"


def native_collection(rows=()):
    """Represent stored document IDs independently from canonical source identities."""
    return {
        "ids": [[row[0] for row in rows]],
        "documents": [[row[1] for row in rows]],
        "metadatas": [[deepcopy(row[2]) for row in rows]],
        "distances": [[0.42 for _ in rows]],
    }


class RawReadBackend:
    def __init__(self, results):
        self.results = results
        self.calls = []

    def search(self, query, n_results=3, *, filters=None):
        self.calls.append((query, n_results, deepcopy(filters)))
        result = self.results[query]
        if isinstance(result, Exception):
            raise result
        return deepcopy(result)


def result(docs=(), issues=()):
    return {"docs": native_collection(docs), "issues": native_collection(issues)}


def row(chunk_id="doc-chunk-1", *, excerpt="A documented behavior.", **metadata):
    return (
        "storage-record-1",
        excerpt,
        {
            "chunk_id": chunk_id,
            "source_id": "official-document-1",
            "source_type": "doc",
            "source_url": "https://docs.streamlit.io/develop/api-reference/widgets",
            **metadata,
        },
    )


def adapter(tmp_path, backend):
    return ChromaRetrieverAdapter(
        str(tmp_path / "unused-data"), snapshot_id=SNAPSHOT, core_retriever=backend
    )


def request(*queries, top_k=5, snapshot_id=SNAPSHOT, **filters):
    return RetrievalRequest(queries=queries, snapshot_id=snapshot_id, top_k=top_k, filters=filters)


def test_native_mapping_preserves_source_identity_and_provenance(tmp_path):
    stored = row(
        source_type="release_note",
        source_commit="695e6ce2fb1b23afc6df66b40420ab0013ad72fd",
        source_span="release-notes.md:44-51",
        applicable_versions='["1.49.0", "1.49.1"]',
        score=0.77,
        score_kind="offline-reranker",
    )
    backend = RawReadBackend({"version behavior": result(docs=(stored,))})
    output = adapter(tmp_path, backend).search(request("version behavior"))
    assert isinstance(output, EvidenceBundle)
    assert output.hits == (
        EvidenceHit(
            chunk_id="doc-chunk-1",
            source_id="official-document-1",
            source_type="release_note",
            source_url="https://docs.streamlit.io/develop/api-reference/widgets",
            excerpt="A documented behavior.",
            source_commit="695e6ce2fb1b23afc6df66b40420ab0013ad72fd",
            source_span="release-notes.md:44-51",
            applicable_versions=("1.49.0", "1.49.1"),
            score=0.77,
            score_kind="offline-reranker",
        ),
    )
    assert output.snapshot_id == SNAPSHOT
    assert output.queries_used == ("version behavior",)
    assert not (tmp_path / "unused-data").exists()


def test_unknown_metadata_stays_unknown_despite_backend_distance(tmp_path):
    backend = RawReadBackend({"unknown version": result(docs=(row(),))})
    hit = adapter(tmp_path, backend).search(request("unknown version")).hits[0]
    assert hit.source_commit is None
    assert hit.source_span is None
    assert hit.applicable_versions == ()
    assert hit.score is None
    assert hit.score_kind is None


def test_multiquery_global_cap_and_dedup_do_not_mutate_request(tmp_path):
    duplicate = row()
    second = row("doc-chunk-2", source_id="official-document-2")
    third = row("issue-chunk-3", source_id="issue-42", source_type="comment")
    backend = RawReadBackend(
        {
            "first": result(docs=(duplicate,), issues=(third,)),
            "second": result(docs=(duplicate, second)),
        }
    )
    original = request("first", "second", top_k=2, source_type=("doc", "comment"))
    saved = original.model_dump()
    output = adapter(tmp_path, backend).search(original)
    assert original.model_dump() == saved
    assert len(output.hits) == 2
    assert len({hit.chunk_id for hit in output.hits}) == 2
    assert output.queries_used == ("first", "second")
    assert backend.calls == [
        ("first", 2, {"source_type": ("doc", "comment")}),
        ("second", 2, {"source_type": ("doc", "comment")}),
    ]


def test_snapshot_mismatch_rejected_before_any_backend_read(tmp_path):
    backend = RawReadBackend({})
    with pytest.raises(ValueError):
        adapter(tmp_path, backend).search(request("query", snapshot_id="other-snapshot"))
    assert backend.calls == []


def test_character_limit_preserves_complete_valid_quote(tmp_path):
    excerpt = "x" * 20_000
    backend = RawReadBackend({"boundary": result(docs=(row(excerpt=excerpt),))})
    output = adapter(tmp_path, backend).search(request("boundary"))
    assert output.hits[0].excerpt == excerpt
    assert len(output.hits[0].excerpt) == 20_000


@pytest.mark.parametrize(
    "stored",
    [
        row(excerpt="x" * 20_001),
        row(source_url="not-a-url"),
        row(source_url=None),
        row(source_type="made-up-type"),
        row(applicable_versions="not-json"),
        row(applicable_versions='["1.49.0", "1.49.0"]'),
    ],
    ids=[
        "oversize",
        "invalid-url",
        "missing-url",
        "invalid-type",
        "invalid-versions",
        "duplicate-versions",
    ],
)
def test_invalid_indexed_records_fail_closed_instead_of_rewriting(tmp_path, stored):
    backend = RawReadBackend({"invalid": result(docs=(stored,))})
    with pytest.raises(ValueError):
        adapter(tmp_path, backend).search(request("invalid"))


def test_backend_failure_does_not_become_successful_empty_evidence(tmp_path):
    backend = RawReadBackend({"failure": RuntimeError("PRIVATE_BACKEND_ERROR")})
    with pytest.raises((ValueError, RuntimeError)):
        adapter(tmp_path, backend).search(request("failure"))


def test_empty_search_is_valid_bundle_with_no_invented_source(tmp_path):
    backend = RawReadBackend({"empty": result()})
    output = adapter(tmp_path, backend).search(request("empty"))
    assert isinstance(output, EvidenceBundle)
    assert output.hits == ()
    assert output.snapshot_id == SNAPSHOT
    assert output.queries_used == ("empty",)


def test_legacy_issue_metadata_preserves_known_locator_without_invention(tmp_path):
    stored = (
        "42",
        "A historical issue report.",
        {"html_url": "https://github.com/streamlit/streamlit/issues/42", "state": "closed"},
    )
    backend = RawReadBackend({"legacy": result(issues=(stored,))})
    hit = adapter(tmp_path, backend).search(request("legacy")).hits[0]
    assert hit.chunk_id == "issue:42"
    assert hit.source_id == "issue-42"
    assert hit.source_url == "https://github.com/streamlit/streamlit/issues/42"
    assert hit.source_type == "issue"
    assert hit.source_span is None
    assert hit.source_commit is None
    assert hit.applicable_versions == ()


def test_legacy_doc_commit_and_version_are_supported_when_canonical_values_absent(tmp_path):
    stored = (
        "doc-legacy",
        "The legacy ingestion stored this versioned doc.",
        {
            "source_url": "https://docs.streamlit.io/develop",
            "docs_commit": "123abc",
            "version": "1.49.0",
            "function_name": "st.multiselect",
        },
    )
    backend = RawReadBackend({"legacy": result(docs=(stored,))})
    hit = adapter(tmp_path, backend).search(request("legacy")).hits[0]
    assert hit.chunk_id == "doc:doc-legacy"
    assert hit.source_id == "doc-legacy"
    assert hit.source_commit == "123abc"
    assert hit.applicable_versions == ("1.49.0",)
    assert hit.source_span is None


def test_canonical_unknown_values_are_not_overwritten_by_legacy_metadata(tmp_path):
    stored = row(
        source_commit=None,
        docs_commit="123abc",
        applicable_versions="[]",
        version="1.50.0",
    )
    backend = RawReadBackend({"unknown": result(docs=(stored,))})
    hit = adapter(tmp_path, backend).search(request("unknown")).hits[0]
    assert hit.source_commit is None
    assert hit.applicable_versions == ()


def test_same_chunk_with_conflicting_quote_cannot_silently_replace_evidence(tmp_path):
    first = row(excerpt="The original quote.")
    conflicting = row(excerpt="Different content under the same chunk ID.")
    backend = RawReadBackend(
        {"first": result(docs=(first,)), "second": result(docs=(conflicting,))}
    )
    with pytest.raises(ValueError):
        adapter(tmp_path, backend).search(request("first", "second"))


def test_invalid_secondary_collection_is_not_hidden_by_global_cap(tmp_path):
    backend = RawReadBackend(
        {"mixed": result(docs=(row(),), issues=(row("bad-issue", source_url="bad-url"),))}
    )
    with pytest.raises(ValueError):
        adapter(tmp_path, backend).search(request("mixed", top_k=1))


def test_misaligned_backend_columns_cannot_attach_wrong_metadata(tmp_path):
    malformed = result(docs=(row(),))
    malformed["docs"]["documents"][0].append("Text without an aligned ID or metadata.")
    backend = RawReadBackend({"misaligned": malformed})
    with pytest.raises(ValueError):
        adapter(tmp_path, backend).search(request("misaligned"))


def test_injected_backend_snapshot_mismatch_is_rejected_before_reads(tmp_path):
    backend = RawReadBackend({})
    backend.snapshot_id = "backend-other-snapshot"
    with pytest.raises(ValueError):
        adapter(tmp_path, backend)
    assert backend.calls == []


def test_actual_adapter_and_native_retriever_pass_frozen_core_acceptance_without_chroma(
    monkeypatch,
):
    # Both production constructors must use their injected read-only seams.
    # Importing Chroma here would enable its persistent/index/embedding path.
    original_import = builtins.__import__

    def offline_import(name, *args, **kwargs):
        if name == "chromadb" or name.startswith("chromadb."):
            raise AssertionError("Acceptance must not import a real Chroma backend")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", offline_import)
    from agent_app.testing.chroma_binding import factory
    from agent_app.testing.retrieval_acceptance import run_acceptance

    receipt = run_acceptance(factory)
    assert receipt["accepted"] is True
    assert receipt["checks_passed"] == receipt["checks_total"] == 132
    assert len(receipt["cases"]) == 14
    assert all(case["status"] == "passed" for case in receipt["cases"])
    assert receipt["pilot"]["checks"]["refinement_consumes_two_queries_within_budget"] is True
    assert receipt["quality_claim"] is False
    assert receipt["real_model_tested"] is False
    assert receipt["production_index_or_embedding_tested"] is False
    assert receipt["actual_cost_usd"] == 0
