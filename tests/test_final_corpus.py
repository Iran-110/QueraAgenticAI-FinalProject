"""Final docs/release-note/API corpus profile: provenance, exclusion and loader checks.

Offline only. Uses the pinned seed package and the extracted index exclusion;
no held-out fixture, question or gold is read.
"""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from agent_app.retrieval.pilot_corpus import (
    FINAL_PROTOCOL,
    FINAL_SOURCE_COUNT,
    PilotCorpus,
    PilotCorpusRejected,
    build_final_corpus,
    build_pilot_corpus,
    canonical_json,
    sha256,
)

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "streamlit-data-for-dev-test"
FINAL = ROOT / "experiments/final_corpus_v1"
ALLOWLIST = FINAL / "allowlist.json"
EXCLUSION = FINAL / "exclusion-v1.json"
DENIED = "content/develop/concepts/app-design/custom-classes.md"


@pytest.fixture(scope="module")
def corpus():
    return build_final_corpus(SEED, ALLOWLIST, EXCLUSION)


def _write(tmp_path, name, value):
    path = tmp_path / name
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def _reseal(payload):
    return {
        "snapshot_id": "docs-pilot-" + sha256(canonical_json(payload).encode("utf-8")),
        "corpus": payload,
    }


def test_final_profile_selects_docs_release_notes_and_versioned_api(corpus):
    payload = corpus.manifest["corpus"]
    sources = payload["sources"]
    assert payload["protocol"] == FINAL_PROTOCOL
    assert len(sources) == FINAL_SOURCE_COUNT == 1228
    kinds = {}
    for source in sources:
        kinds.setdefault(source["source_type"], []).append(source)
    assert len(kinds["release_note"]) == 9 and len(kinds["doc"]) == 1219
    for source in kinds["release_note"]:
        assert source["source_pointer"].startswith(
            "content/develop/quick-references/release-notes/"
        )
        assert source["applicable_versions"] == []
    api = [s for s in sources if s["origin_kind"] == "docs_generated"]
    assert len(api) == 1172 and all(len(s["applicable_versions"]) == 1 for s in api)
    assert len({s["applicable_versions"][0] for s in api}) == 43
    assert all(not s["applicable_versions"] for s in sources if s["origin_kind"] == "docs_markdown")
    assert all(s["source_pointer"] != DENIED for s in sources)
    for chunk in payload["chunks"]:
        metadata = chunk["metadata"]
        assert metadata["source_type"] in {"doc", "release_note"}
        assert ("version" in metadata) == (metadata["applicable_versions"] != "[]")


def test_exclusion_is_recorded_and_nothing_from_issues_is_indexed(corpus):
    exclusions = corpus.manifest["corpus"]["exclusions"]
    extracted = json.loads(EXCLUSION.read_text("utf-8"))
    assert exclusions["reserved_issue_ids"] == extracted["issue_ids"]
    assert len(exclusions["reserved_issue_ids"]) == 90
    assert exclusions["indexed_issue_count"] == exclusions["indexed_comment_count"] == 0
    assert DENIED in exclusions["direct_answer_documents"]
    pins = corpus.manifest["corpus"]["source_pins"]
    assert pins["exclusion_manifest_sha256"] == sha256(EXCLUSION.read_bytes())
    assert pins["allowlist_sha256"] == sha256(ALLOWLIST.read_bytes())


def test_build_is_deterministic_and_round_trips_through_the_loader(corpus):
    again = build_final_corpus(SEED, ALLOWLIST, EXCLUSION)
    assert again.snapshot_id == corpus.snapshot_id
    assert PilotCorpus.from_manifest(corpus.manifest).snapshot_id == corpus.snapshot_id


@pytest.mark.parametrize(
    "split,allowlist,expected",
    [
        (
            "data/evaluation/split-manifest.json",
            "experiments/corpus/pilot-allowlist.json",
            "docs-pilot-87bdaf9a3dadcefff48a6775ef616f3d3dd5bf1c8cb23a9521b0e11ccaae160c",
        ),
        (
            "experiments/dev_rag_coverage_v1/split-manifest.json",
            "experiments/dev_rag_coverage_v1/allowlist.json",
            "docs-pilot-12ec2995032ad48dbec2c1f1736fca1f97727478373dd1835043eedf21ab0ee1",
        ),
    ],
)
def test_historical_profiles_are_unchanged(split, allowlist, expected):
    assert build_pilot_corpus(SEED, ROOT / split, ROOT / allowlist).snapshot_id == expected


def _allowlist():
    return json.loads(ALLOWLIST.read_text("utf-8"))


@pytest.mark.parametrize(
    "edit",
    [
        lambda a: a["markdown_source_ids"].append("docs:" + DENIED),
        lambda a: a["api_source_ids"].pop(),
        lambda a: a["release_note_source_ids"].pop(),
        lambda a: a.update(denied_document_paths=[]),
        lambda a: a.update(excluded_source_types=["comment", "evaluation", "fixture"]),
        lambda a: a.update(protocol="docs-only-dev-coverage-v1"),
    ],
    ids=["denied-doc", "missing-api", "release-list", "no-denylist", "issues-allowed", "protocol"],
)
def test_allowlist_changes_are_rejected(tmp_path, edit):
    allowlist = _allowlist()
    edit(allowlist)
    with pytest.raises(PilotCorpusRejected):
        build_final_corpus(SEED, _write(tmp_path, "allowlist.json", allowlist), EXCLUSION)


def test_profiles_cannot_be_swapped_between_builders(tmp_path):
    with pytest.raises(PilotCorpusRejected):
        build_pilot_corpus(SEED, ROOT / "data/evaluation/split-manifest.json", ALLOWLIST)
    with pytest.raises(PilotCorpusRejected):
        build_final_corpus(SEED, ROOT / "experiments/corpus/pilot-allowlist.json", EXCLUSION)


@pytest.mark.parametrize(
    "edit",
    [
        lambda e: e["issue_ids"].remove(12782),
        lambda e: e["issue_ids"].reverse(),
        lambda e: e.update(direct_answer_documents=[]),
        lambda e: e.update(source_manifest_sha256="not-a-hash"),
    ],
    ids=["exposed-issue-dropped", "unsorted", "no-direct-answer-docs", "bad-hash"],
)
def test_exclusion_changes_are_rejected(tmp_path, edit):
    exclusion = json.loads(EXCLUSION.read_text("utf-8"))
    edit(exclusion)
    with pytest.raises(PilotCorpusRejected):
        build_final_corpus(SEED, ALLOWLIST, _write(tmp_path, "exclusion.json", exclusion))


def _first(payload, source_type):
    return next(c for c in payload["chunks"] if c["metadata"]["source_type"] == source_type)


@pytest.mark.parametrize(
    "edit",
    [
        lambda p: _first(p, "release_note")["metadata"].update(source_type="doc"),
        lambda p: _first(p, "release_note")["metadata"].update(source_type="issue"),
        lambda p: _first(p, "release_note")["metadata"].update(
            applicable_versions='["1.50.0"]', version="1.50.0"
        ),
        lambda p: p["exclusions"].update(indexed_issue_count=1),
        lambda p: p["sources"].pop(),
        lambda p: _first(p, "doc").update(document=_first(p, "doc")["document"] + " "),
    ],
    ids=["type-flip", "issue-type", "inferred-version", "issue-indexed", "source-dropped", "text"],
)
def test_loader_rejects_tampered_final_manifests(corpus, edit):
    payload = deepcopy(corpus.manifest["corpus"])
    edit(payload)
    with pytest.raises(PilotCorpusRejected):
        PilotCorpus.from_manifest(_reseal(payload))


def test_final_index_builds_opens_and_serves_release_notes(tmp_path, corpus):
    pytest.importorskip("chromadb")
    from agent_app.contracts import RetrievalRequest
    from agent_app.retrieval.adapter import ChromaRetrieverAdapter
    from agent_app.retrieval.offline_index import build_index, open_verified_index
    from agent_app.retrieval.retriever import StreamlitRetriever

    destination = tmp_path / "final-index"
    snapshot = build_index(corpus, destination)
    client, verified = open_verified_index(destination)
    assert verified == snapshot == corpus.snapshot_id
    backend = StreamlitRetriever("", snapshot_id=snapshot, client=client)
    adapter = ChromaRetrieverAdapter("", snapshot_id=snapshot, core_retriever=backend)
    bundle = adapter.search(
        RetrievalRequest(queries=("release notes multiselect key",), snapshot_id=snapshot, top_k=25)
    )
    assert bundle.hits and {h.source_type for h in bundle.hits} <= {"doc", "release_note"}
    assert any(h.source_type == "release_note" for h in bundle.hits)
    filtered = backend.search("st.button", n_results=5, filters={"version": "1.50.0"})
    versions = {m["version"] for m in filtered["docs"]["metadatas"][0]}
    assert versions == {"1.50.0"}
