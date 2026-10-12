"""Source provenance and lossless chunking checks for the bounded docs pilot."""

import json
import shutil
from pathlib import Path

import pytest

from agent_app.retrieval.pilot_corpus import (
    PilotCorpus,
    PilotCorpusRejected,
    _chunk_id,
    build_pilot_corpus,
    canonical_json,
    embedding_sha256,
    lexical_embedding,
    sha256,
)

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "streamlit-data-for-dev-test"
SPLIT = ROOT / "data/evaluation/split-manifest.json"
ALLOWLIST = ROOT / "experiments/corpus/pilot-allowlist.json"


def _write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _repackage(seed, relative, data):
    path = seed / relative
    path.write_bytes(data)
    manifest = json.loads((seed / "manifest.json").read_text())
    item = next(item for item in manifest["files"] if item["path"] == relative)
    item.update(bytes=len(data), sha256=sha256(data))
    _write_json(seed / "manifest.json", manifest)


@pytest.fixture
def edited_seed(tmp_path):
    destination = tmp_path / "seed"
    shutil.copytree(SEED, destination)
    return destination


def _edit_selected(seed, origin, edit):
    relative = f"sources/{origin}_scope_candidates.jsonl"
    rows = [json.loads(line) for line in (seed / relative).read_text().splitlines()]
    wanted = (
        "docs:content/develop/concepts/architecture/session-state.md"
        if origin == "docs"
        else "docstring:1.49.0:streamlit.button"
    )
    record = next(row for row in rows if row["source_id"] == wanted)
    edit(record)
    data = ("\n".join(canonical_json(row) for row in rows) + "\n").encode("utf-8")
    _repackage(seed, relative, data)


def test_registered_scope_hash_pins_and_exact_lossless_source_spans():
    corpus = build_pilot_corpus(SEED, SPLIT, ALLOWLIST)
    manifest = corpus.manifest["corpus"]
    assert len(manifest["sources"]) == 14
    assert len(manifest["chunks"]) == 30
    assert manifest["source_pins"]["allowlist_sha256"] == sha256(ALLOWLIST.read_bytes())
    assert manifest["source_pins"]["split_manifest_sha256"] == sha256(SPLIT.read_bytes())
    assert manifest["source_pins"]["package_manifest_sha256"] == sha256(
        (SEED / "manifest.json").read_bytes()
    )
    assert len(manifest["source_pins"]["packaged_files"]) == 14
    assert manifest["exclusions"]["split_status"] == "draft_not_frozen"
    assert manifest["exclusions"]["family_review_complete"] is False
    assert manifest["exclusions"]["reserved_issue_ids"] == [8061, 8901, 12629, 12782, 16914]
    originals = {
        row["source_id"]: row["text"]
        for name in ("docs_scope_candidates.jsonl", "docstrings_scope_candidates.jsonl")
        for line in (SEED / "sources" / name).read_text().splitlines()
        if (row := json.loads(line))
    }
    for source in manifest["sources"]:
        chunks = [
            chunk
            for chunk in manifest["chunks"]
            if chunk["metadata"]["source_id"] == source["source_id"]
        ]
        assert "".join(chunk["document"] for chunk in chunks) == originals[source["source_id"]]
        position = 0
        for chunk in chunks:
            span = chunk["span"]
            assert span["start"] == position
            assert span["end"] <= position + 4_000
            assert span["unit"] == "unicode_codepoint"
            assert chunk["document"] == originals[source["source_id"]][position : span["end"]]
            assert chunk["metadata"]["source_type"] == "doc"
            assert chunk["metadata"]["source_text_sha256"] == source["text_sha256"]
            assert chunk["metadata"]["source_commit"] == manifest["source_pins"]["docs_commit"]
            assert chunk["embedding_sha256"] == embedding_sha256(
                lexical_embedding(chunk["document"])
            )
            position = span["end"]
        assert position == source["characters"]
    assert {source["origin_kind"] for source in manifest["sources"]} == {
        "docs_markdown",
        "docs_generated",
    }


def test_versions_remain_exact_and_markdown_applicability_stays_unknown():
    manifest = build_pilot_corpus(SEED, SPLIT, ALLOWLIST).manifest["corpus"]
    ids = []
    for chunk in manifest["chunks"]:
        metadata = chunk["metadata"]
        versions = json.loads(metadata["applicable_versions"])
        if metadata["origin_kind"] == "docs_generated":
            assert versions == [metadata["version"]]
            assert versions[0] in {"1.49.0", "1.50.0", "1.64.0"}
            assert chunk["chunk_id"].startswith("doc:" + versions[0] + ":")
            assert metadata["source_pointer"].startswith("python/streamlit.json/" + versions[0])
        else:
            assert versions == []
            assert "version" not in metadata
        ids.append(chunk["chunk_id"])
    assert len(ids) == len(set(ids))


def test_manifest_detached_deterministic_and_includes_draft_pins(tmp_path):
    first = build_pilot_corpus(SEED, SPLIT, ALLOWLIST)
    assert first.manifest == build_pilot_corpus(SEED, SPLIT, ALLOWLIST).manifest
    altered = first.manifest
    altered["corpus"]["chunks"][0]["document"] = "tampered"
    assert altered != first.manifest
    split = json.loads(SPLIT.read_text())
    split["updated_on"] = "2026-10-12"
    changed = tmp_path / "split.json"
    _write_json(changed, split)
    second = build_pilot_corpus(SEED, changed, ALLOWLIST)
    assert second.snapshot_id != first.snapshot_id
    assert second.manifest["corpus"]["chunks"] == first.manifest["corpus"]["chunks"]


def test_even_excluded_packaged_comment_file_checksum_must_match(edited_seed):
    file = edited_seed / "sources/github-snapshot-2026-10-06/catalog/comment_records.jsonl"
    file.write_bytes(file.read_bytes() + b"\n")
    with pytest.raises(PilotCorpusRejected, match="^PilotCorpusRejected$"):
        build_pilot_corpus(edited_seed, SPLIT, ALLOWLIST)


@pytest.mark.parametrize("origin", ["docs", "docstrings"])
@pytest.mark.parametrize("mutation", ["text", "commit", "type", "pointer"])
def test_selected_source_checks_survive_repackaged_outer_checksum(edited_seed, origin, mutation):
    def edit(record):
        if mutation == "text":
            record["text"] += " changed"
            if origin == "docs":
                record["bytes"] = len(record["text"].encode("utf-8"))
        elif mutation == "commit":
            record["docs_commit"] = "0" * 40
        elif mutation == "type":
            record["type"] = "issue"
        else:
            record["file" if origin == "docs" else "json_pointer"] = "wrong"

    _edit_selected(edited_seed, origin, edit)
    with pytest.raises(PilotCorpusRejected, match="^PilotCorpusRejected$"):
        build_pilot_corpus(edited_seed, SPLIT, ALLOWLIST)


def test_selected_oversized_unicode_document_remains_lossless(edited_seed):
    text = "متن🌱 Streamlit session state 𐍈\n" * 1_300

    def edit(record):
        record.update(
            text=text, bytes=len(text.encode("utf-8")), sha256=sha256(text.encode("utf-8"))
        )

    _edit_selected(edited_seed, "docs", edit)
    chunks = [
        chunk
        for chunk in build_pilot_corpus(edited_seed, SPLIT, ALLOWLIST).manifest["corpus"]["chunks"]
        if chunk["metadata"]["source_id"]
        == "docs:content/develop/concepts/architecture/session-state.md"
    ]
    assert len(chunks) > 5
    assert "".join(chunk["document"] for chunk in chunks) == text
    assert all(0 < len(chunk["document"]) <= 4_000 for chunk in chunks)
    assert chunks[-1]["span"]["end"] == len(text)


@pytest.mark.parametrize("mutation", ["exclusions", "embedding", "missing_version"])
def test_scope_cannot_silently_expand_or_drop_exclusion_policy(tmp_path, mutation):
    allowlist = json.loads(ALLOWLIST.read_text())
    if mutation == "exclusions":
        allowlist["excluded_source_types"] = []
    elif mutation == "embedding":
        allowlist["embedding"]["quality_claim"] = True
    else:
        allowlist["api_versions"][-1] = "9.99.0"
    path = tmp_path / "allowlist.json"
    _write_json(path, allowlist)
    with pytest.raises(PilotCorpusRejected, match="^PilotCorpusRejected$"):
        build_pilot_corpus(SEED, SPLIT, path)


def test_registered_allowlist_rejects_an_internally_valid_release_notes_substitution(
    edited_seed, tmp_path
):
    original = "docs:content/develop/concepts/architecture/session-state.md"
    replacement_file = "content/develop/quick-reference/release-notes.md"
    replacement = "docs:" + replacement_file
    allowlist = json.loads(ALLOWLIST.read_text())
    allowlist["markdown_source_ids"] = [
        replacement if source_id == original else source_id
        for source_id in allowlist["markdown_source_ids"]
    ]

    def edit(record):
        # Keep the valid source type, commit, text and text hash. Only the source
        # identity/pointer changes; the complete package is checksummed again.
        record["source_id"] = replacement
        record["file"] = replacement_file
        record["pinned_source_url"] = (
            f"https://github.com/streamlit/docs/blob/{record['docs_commit']}/{replacement_file}"
        )

    _edit_selected(edited_seed, "docs", edit)
    path = tmp_path / "release-notes-allowlist.json"
    _write_json(path, allowlist)
    with pytest.raises(PilotCorpusRejected, match="^PilotCorpusRejected$"):
        build_pilot_corpus(edited_seed, SPLIT, path)


@pytest.mark.parametrize("mutation", ["existing_version", "existing_function", "commit"])
def test_registered_scope_is_not_replaced_by_another_valid_source_matrix(tmp_path, mutation):
    allowlist = json.loads(ALLOWLIST.read_text())
    if mutation == "existing_version":
        allowlist["api_versions"][0] = "1.48.0"
    elif mutation == "existing_function":
        allowlist["api_functions"][0] = "streamlit.slider"
    else:
        allowlist["docs_commit"] = "0" * 40
    path = tmp_path / "changed-registered-scope.json"
    _write_json(path, allowlist)
    with pytest.raises(PilotCorpusRejected, match="^PilotCorpusRejected$"):
        build_pilot_corpus(SEED, SPLIT, path)


def test_rehashed_manifest_with_consistent_replacement_identity_is_still_not_registered():
    manifest = build_pilot_corpus(SEED, SPLIT, ALLOWLIST).manifest
    payload = manifest["corpus"]
    source = next(
        source for source in payload["sources"] if source["origin_kind"] == "docs_markdown"
    )
    original_id = source["source_id"]
    source["source_pointer"] = "content/develop/quick-reference/release-notes.md"
    source["source_id"] = "docs:" + source["source_pointer"]
    source["source_url"] = (
        f"https://github.com/streamlit/docs/blob/{source['source_commit']}/{source['source_pointer']}"
    )
    for chunk in payload["chunks"]:
        if chunk["metadata"]["source_id"] != original_id:
            continue
        for key in ("source_id", "source_pointer", "source_url"):
            chunk["metadata"][key] = source[key]
        chunk["chunk_id"] = _chunk_id(
            source, chunk["span"]["start"], chunk["span"]["end"], chunk["text_sha256"]
        )
        chunk["metadata"]["chunk_id"] = chunk["chunk_id"]
    manifest["snapshot_id"] = "docs-pilot-" + sha256(canonical_json(payload).encode("utf-8"))
    with pytest.raises(PilotCorpusRejected, match="^PilotManifestRejected$"):
        PilotCorpus.from_manifest(manifest)


def test_missing_exposure_reservation_fails_closed(tmp_path):
    split = json.loads(SPLIT.read_text())
    split["exposure_reserved_issue_ids"] = []
    path = tmp_path / "split.json"
    _write_json(path, split)
    with pytest.raises(PilotCorpusRejected, match="^PilotCorpusRejected$"):
        build_pilot_corpus(SEED, path, ALLOWLIST)


def test_package_traversal_fails_with_fixed_diagnostic(edited_seed):
    manifest = json.loads((edited_seed / "manifest.json").read_text())
    manifest["files"][0]["path"] = "../private-secret"
    _write_json(edited_seed / "manifest.json", manifest)
    with pytest.raises(PilotCorpusRejected, match="^PilotCorpusRejected$"):
        build_pilot_corpus(edited_seed, SPLIT, ALLOWLIST)


def test_manifest_cannot_omit_excluded_packaged_hashes(edited_seed):
    manifest = json.loads((edited_seed / "manifest.json").read_text())
    manifest["files"] = [
        entry for entry in manifest["files"] if not entry["path"].endswith("comment_records.jsonl")
    ]
    _write_json(edited_seed / "manifest.json", manifest)
    with pytest.raises(PilotCorpusRejected, match="^PilotCorpusRejected$"):
        build_pilot_corpus(edited_seed, SPLIT, ALLOWLIST)


@pytest.mark.parametrize("mutation", ["span", "version", "source_hash", "identity", "exclusions"])
def test_even_rehashed_frozen_manifest_must_preserve_structural_provenance(mutation):
    manifest = build_pilot_corpus(SEED, SPLIT, ALLOWLIST).manifest
    payload = manifest["corpus"]
    chunk = payload["chunks"][0]
    if mutation == "span":
        chunk["span"]["start"] += 1
        chunk["span"]["end"] += 1
    elif mutation == "version":
        chunk["metadata"]["version"] = "9.99.0"
    elif mutation == "source_hash":
        chunk["metadata"]["source_text_sha256"] = "0" * 64
    elif mutation == "identity":
        chunk["chunk_id"] = chunk["metadata"]["chunk_id"] = "changed-id"
    else:
        payload["exclusions"]["indexed_issue_count"] = 1
    manifest["snapshot_id"] = "docs-pilot-" + sha256(canonical_json(payload).encode("utf-8"))
    with pytest.raises(PilotCorpusRejected, match="^PilotManifestRejected$"):
        PilotCorpus.from_manifest(manifest)


def test_duplicate_selected_record_is_not_silently_deduplicated(edited_seed):
    relative = "sources/docstrings_scope_candidates.jsonl"
    rows = [json.loads(line) for line in (edited_seed / relative).read_text().splitlines()]
    selected = next(row for row in rows if row["source_id"] == "docstring:1.49.0:streamlit.button")
    rows.append(selected)
    _repackage(
        edited_seed, relative, ("\n".join(canonical_json(row) for row in rows) + "\n").encode()
    )
    with pytest.raises(PilotCorpusRejected, match="^PilotCorpusRejected$"):
        build_pilot_corpus(edited_seed, SPLIT, ALLOWLIST)


def test_lexical_vector_is_stable_float32_and_not_a_semantic_model():
    first = lexical_embedding("SESSION State session")
    assert len(first) == 256
    assert first == lexical_embedding("session state SESSION")
    assert sum(value * value for value in first) == pytest.approx(1.0)
    assert lexical_embedding(" ") == lexical_embedding("!!!")
