#!/usr/bin/env python3
"""Read-only pinned loader/chunker audit; no retriever, embedding or index execution."""

import argparse
import ast
import hashlib
import json
import subprocess
import zipfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

RAG_COMMIT = "c0d450a57769b4513b6b99f2e75ed506c483363d"
REPO = Path.cwd()
PACKAGE_DIR = Path.cwd()
SEED = Path.cwd()
ZIP = Path.cwd()
DEFAULT_OUTPUT = Path(__file__).with_name("data-audit.json")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_json(rel):
    return json.loads((SEED / rel).read_text(encoding="utf-8"))


def read_jsonl(rel):
    return [
        json.loads(line)
        for line in (SEED / rel).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def source(path):
    return subprocess.check_output(["git", "show", f"{RAG_COMMIT}:{path}"], cwd=REPO)


def load_reviewed_class(raw, path, name):
    # Only these two reviewed, pinned modules execute. They import json/os/typing
    # and declare pure readers; corpus text itself is never evaluated as code.
    text = raw.decode("utf-8-sig")
    tree = ast.parse(text, filename=path)
    imports = [node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))]
    names = {name.name for node in imports if isinstance(node, ast.Import) for name in node.names}
    names.update(node.module for node in imports if isinstance(node, ast.ImportFrom))
    if not names <= {"json", "os", "typing"}:
        raise RuntimeError("UnexpectedReviewedModuleImport")
    if not all(isinstance(node, (ast.Import, ast.ImportFrom, ast.ClassDef)) for node in tree.body):
        raise RuntimeError("UnexpectedReviewedModuleTopLevel")
    scope = {"__name__": "read_only_reviewed_data_audit"}
    exec(compile(tree, path, "exec"), scope)
    return scope[name]


def record_summary(rows):
    return {
        "records": len(rows),
        "source_field_names": sorted({key for row in rows for key in row}),
    }


def chunk_summary(raw_rows, chunks):
    lengths = [len(row["text"]) for row in chunks]
    oversized = [
        {"source_id": row["id"], "chars": len(row["text"])}
        for row in chunks
        if len(row["text"]) > 20_000
    ]
    return {
        **record_summary(raw_rows),
        "chunks_produced_by_reviewed_code": len(chunks),
        "output_metadata_keys": sorted({key for row in chunks for key in row["metadata"]}),
        "duplicate_chunk_ids": len(chunks) - len({row["id"] for row in chunks}),
        "minimum_chunk_chars": min(lengths, default=0),
        "maximum_chunk_chars": max(lengths, default=0),
        "oversized_for_core_20k": oversized,
        "source_metadata_present": {
            key: sum(bool(row.get(key)) for row in raw_rows)
            for key in (
                "source_id",
                "pinned_source_url",
                "docs_commit",
                "file",
                "json_pointer",
                "version",
            )
        },
        "output_metadata_present": {
            key: sum(bool(row["metadata"].get(key)) for row in chunks)
            for key in (
                "source_url",
                "source_commit",
                "source_span",
                "applicable_versions",
                "version",
            )
        },
    }


def main():
    global REPO, PACKAGE_DIR, SEED, ZIP
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--seed-zip", type=Path, required=True)
    parser.add_argument(
        "--seed-dir", type=Path, help="Already extracted seed; defaults to ZIP path without .zip"
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    REPO = args.repo_root.resolve()
    ZIP = args.seed_zip.resolve()
    PACKAGE_DIR = ZIP.parent
    SEED = args.seed_dir.resolve() if args.seed_dir else ZIP.with_suffix("")
    if args.output.exists():
        raise RuntimeError("ReceiptAlreadyExists")

    captured = datetime.now(UTC).isoformat()
    loader_path = "data_scripts/data_loader.py"
    chunker_path = "data_scripts/chunking.py"
    retriever_path = "src/agent_app/retrieval/retriever.py"
    originals = {path: source(path) for path in (loader_path, chunker_path, retriever_path)}
    manifest = read_json("manifest.json")
    exposure = read_json("development_exposure.json")
    source_files = [entry["path"] for entry in manifest["files"]] + ["manifest.json"]
    before = {rel: sha((SEED / rel).read_bytes()) for rel in source_files}
    zip_before = sha(ZIP.read_bytes())
    manifest_verified = all(
        before[entry["path"]] == entry["sha256"]
        and (SEED / entry["path"]).stat().st_size == entry["bytes"]
        for entry in manifest["files"]
    )
    with zipfile.ZipFile(ZIP) as archive:
        member_names = [name for name in archive.namelist() if not name.endswith("/")]
        extracted_matches_zip = all(
            sha(archive.read(name)) == sha((SEED.parent / name).read_bytes())
            for name in member_names
        )

    loader_class = load_reviewed_class(originals[loader_path], loader_path, "StreamlitDataLoader")
    chunker_class = load_reviewed_class(
        originals[chunker_path], chunker_path, "StreamlitDocChunker"
    )
    contexts = loader_class(str(SEED)).build_full_issue_context()
    chunker = chunker_class(str(SEED))
    api_chunks = chunker.extract_docstring_chunks()
    markdown_chunks = chunker.extract_markdown_chunks()
    issues = read_jsonl("sources/github-snapshot-2026-10-06/catalog/issue_records.jsonl")
    comments = read_jsonl("sources/github-snapshot-2026-10-06/catalog/comment_records.jsonl")
    api_rows = read_jsonl("sources/docstrings_scope_candidates.jsonl")
    markdown_rows = read_jsonl("sources/docs_scope_candidates.jsonl")
    exposed_ids = set(exposure["issue_numbers"])
    excluded_ids = sorted(row["number"] for row in issues if row["number"] in exposed_ids)
    context_comments = sum(len(row["comments"]) for row in contexts)
    # This is a source-level observation, not a Chroma indexing result.
    retriever_tree = ast.parse(
        originals[retriever_path].decode("utf-8-sig"), filename=retriever_path
    )
    index_func = next(
        node
        for node in ast.walk(retriever_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "index_data"
    )
    issue_fields = sorted(
        {
            node.slice.value
            for node in ast.walk(index_func)
            if isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and node.value.id == "issue"
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, str)
        }
    )
    mention_candidates = []
    for row in markdown_rows:
        mentions = sorted(
            number
            for number in exposed_ids
            if f"/issues/{number}" in row["text"] or f"#{number}" in row["text"]
        )
        if mentions:
            mention_candidates.append(
                {
                    "source_id": row["source_id"],
                    "file": row["file"],
                    "issue_ids": mentions,
                    "classification": "linkage_review_candidate_not_proven_duplicate_or_answer_leakage",
                }
            )
    after = {rel: sha((SEED / rel).read_bytes()) for rel in source_files}
    zip_after = sha(ZIP.read_bytes())
    receipt = {
        "schema_version": 1,
        "audit_id": "rag-pure-data-audit-2026-10-11-v1",
        "captured_at_utc": captured,
        "quality_claim": False,
        "scope": {
            "reviewed_loader_chunker_executed": True,
            "retriever_chroma_embedding_index_executed": False,
            "corpus_build": False,
            "provider_calls": 0,
            "ledger_access": False,
            "env_or_key_access": False,
            "executed_source_paths": [loader_path, chunker_path],
            "retriever_ast_only": True,
        },
        "pinned_sources": {
            "rag_commit": RAG_COMMIT,
            "source_sha256": {path: sha(raw) for path, raw in originals.items()},
            "script_sha256": sha(Path(__file__).read_bytes()),
        },
        "seed_provenance": {
            key: manifest[key]
            for key in (
                "package",
                "packaged_on",
                "github_snapshot_date",
                "source_repository",
                "docs_repository",
                "docs_commit",
                "purpose",
                "counts",
                "api_versions",
                "checksum_scope",
            )
        },
        "integrity": {
            "zip_filename": ZIP.name,
            "zip_sha256": zip_before,
            "zip_regular_members": len(member_names),
            "manifest_file_hashes_and_bytes_verified": manifest_verified,
            "extracted_members_match_zip": extracted_matches_zip,
            "seed_unchanged_during_audit": before == after,
            "zip_unchanged_during_audit": zip_before == zip_after,
            "seed_file_sha256": before,
        },
        "issues": {
            **record_summary(issues),
            "loader_contexts_after_exposure_filter": len(contexts),
            "exposure_list_ids": sorted(exposed_ids),
            "excluded_ids_present_in_seed": excluded_ids,
            "exposure_ids_absent_from_seed": sorted(
                exposed_ids - {row["number"] for row in issues}
            ),
            "original_exposure_purpose": exposure["purpose"],
            "family_split_filter_implemented": False,
        },
        "comments": {
            **record_summary(comments),
            "comments_returned_inside_allowed_issue_contexts": context_comments,
            "filtered_nonbot_comments_for_exposed_issues": sum(
                not (row.get("is_bot") or row.get("author_type") == "Bot")
                and row["issue_number"] in exposed_ids
                for row in comments
            ),
            "index_source_issue_fields_referenced": issue_fields,
            "index_source_consumes_issue_comments": "comments" in issue_fields,
            "observation_kind": "loader_executed_and_indexer_AST_reviewed_no_actual_index_run",
            "actual_indexed_comment_count": None,
        },
        "api_docstrings": chunk_summary(api_rows, api_chunks),
        "markdown": chunk_summary(markdown_rows, markdown_chunks),
        "api_versions_observed": dict(sorted(Counter(row["version"] for row in api_rows).items())),
        "docs_linkage_review_candidates": mention_candidates,
        "acceptance_boundaries": {
            "R1_seed_provenance_and_pure_loader_preview_recorded": True,
            "R2_frozen_split_allowlist_exclusion_not_implemented": True,
            "R3_typed_core_adapter_not_implemented": True,
            "pilot_possible_after_bounded_adapter_and_pilot_family_exclusion": True,
            "held_out_model_or_RAG_evaluation": False,
        },
    }
    if not all(
        (manifest_verified, extracted_matches_zip, before == after, zip_before == zip_after)
    ):
        raise RuntimeError("SourceIntegrityCheckFailed")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(
        json.dumps(
            {
                "receipt": args.output.name,
                "receipt_sha256": sha(args.output.read_bytes()),
                "rag_commit": RAG_COMMIT,
                "zip_sha256": zip_before,
                "issue_contexts": len(contexts),
                "comments_in_contexts": context_comments,
                "oversized_markdown_chunks": len(receipt["markdown"]["oversized_for_core_20k"]),
                "integrity_verified": True,
                "index_executed": False,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
