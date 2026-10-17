"""Write the closed final allowlist and the index exclusion extracted from the split.

Inputs are read-only: the pinned seed package and the E1 split manifest. Run once
to create the inputs, and again after the split freeze to refresh the exclusion
(the allowlist only changes if the seed selection changes). Never overwrites.
"""

import argparse
import hashlib
import json
from pathlib import Path

from agent_app.retrieval.pilot_corpus import (
    ALWAYS_DENIED_DOCUMENT_PATHS,
    CHUNK_CHARACTERS,
    COLLECTION_NAMES,
    DOCS_COMMIT,
    EMBEDDING_DIMENSIONS,
    FINAL_PROTOCOL,
    RELEASE_NOTES_PREFIX,
)

SCOPE = (
    "Final RAG corpus: every seed scope page (State/Widgets/Forms/Rerun/Fragments docs "
    "and release notes) and every versioned API docstring record at the pinned docs "
    "commit. No Issue, comment, outcome, evaluation fixture or answer-linked document."
)
POLICY = (
    "Select all records of sources/docs_scope_candidates.jsonl and "
    "sources/docstrings_scope_candidates.jsonl except denied_document_paths. Release "
    "notes keep source_type release_note with no inferred version; API records keep "
    "their exact docstring version; product docs are snapshot-dated with no version."
)


def _write_new(path: Path, value) -> str:
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(raw)
    return hashlib.sha256(raw).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-root", type=Path, default=Path("streamlit-data-for-dev-test"))
    parser.add_argument(
        "--split-manifest",
        type=Path,
        default=Path("data/evaluation/split-e1-v1/split-manifest.json"),
    )
    parser.add_argument("--allowlist-out", type=Path)
    parser.add_argument("--exclusion-out", type=Path, required=True)
    args = parser.parse_args()
    report = {}
    if args.allowlist_out is not None:
        sources = args.seed_root / "sources"
        markdown = [
            json.loads(line)["source_id"]
            for line in (sources / "docs_scope_candidates.jsonl").read_text("utf-8").splitlines()
        ]
        markdown = sorted(s for s in markdown if s[5:] not in ALWAYS_DENIED_DOCUMENT_PATHS)
        api = sorted(
            json.loads(line)["source_id"]
            for line in (sources / "docstrings_scope_candidates.jsonl")
            .read_text("utf-8")
            .splitlines()
        )
        allowlist = {
            "protocol": FINAL_PROTOCOL,
            "scope": SCOPE,
            "selection_policy": POLICY,
            "docs_commit": DOCS_COMMIT,
            "chunk_characters": CHUNK_CHARACTERS,
            "embedding": {
                "kind": "lexical_hash_v1",
                "dimensions": EMBEDDING_DIMENSIONS,
                "quality_claim": False,
            },
            "collection_names": list(COLLECTION_NAMES),
            "excluded_source_types": ["comment", "evaluation", "fixture", "issue"],
            "denied_document_paths": sorted(ALWAYS_DENIED_DOCUMENT_PATHS),
            "markdown_source_ids": markdown,
            "release_note_source_ids": [
                s for s in markdown if s[5:].startswith(RELEASE_NOTES_PREFIX)
            ],
            "api_source_ids": api,
        }
        report["allowlist_sha256"] = _write_new(args.allowlist_out, allowlist)
        report["markdown"] = len(markdown)
        report["api"] = len(api)
    raw = args.split_manifest.read_bytes()
    split = json.loads(raw)
    index_exclusion = split["index_exclusion"]
    exclusion = {
        "schema_version": 1,
        "exclusion_id": "final-index-exclusion",
        "source_manifest": args.split_manifest.as_posix(),
        "source_manifest_id": split["manifest_id"],
        "source_manifest_status": split["status"],
        "source_manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "issue_ids": sorted(set(index_exclusion["issue_ids"])),
        "direct_answer_documents": index_exclusion["direct_answer_documents"],
        "scope": index_exclusion["scope"],
        "keep_in_corpus_note": index_exclusion.get("keep_in_corpus_note"),
    }
    report["exclusion_sha256"] = _write_new(args.exclusion_out, exclusion)
    report["excluded_issues"] = len(exclusion["issue_ids"])
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
