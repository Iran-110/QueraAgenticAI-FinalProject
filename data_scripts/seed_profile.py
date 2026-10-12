"""Verify the supplied seed offline; physical integrity is not corpus approval."""

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
FILES = {
    "issues": "sources/github-snapshot-2026-10-06/catalog/issue_records.jsonl",
    "comments": "sources/github-snapshot-2026-10-06/catalog/comment_records.jsonl",
    "catalog": "sources/docs_catalog.jsonl",
    "markdown": "sources/docs_scope_candidates.jsonl",
    "api": "sources/docstrings_scope_candidates.jsonl",
}
FAMILIES = "sources/github-snapshot-2026-10-06/catalog/family_review_candidates.json"
LINKS = "sources/docs_issue_links.json"
EXPOSURE = "development_exposure.json"
COMMON_DOC = {
    "source_id": str,
    "file": str,
    "title": (str, type(None)),
    "source_url": (str, type(None)),
    "pinned_source_url": str,
    "docs_commit": str,
    "sha256": str,
    "bytes": int,
    "suggested_scope": bool,
    "autofunctions": list,
    "headings": list,
}
SCHEMAS = {
    "issues": {
        "number": int,
        "id": int,
        "html_url": str,
        "title": str,
        "body": str,
        "created_at": str,
        "updated_at": str,
        "closed_at": (str, type(None)),
        "state": str,
        "state_reason": (str, type(None)),
        "author_association": str,
        "comments": int,
        "labels": list,
    },
    "comments": {
        "id": int,
        "body": str,
        "created_at": str,
        "updated_at": str,
        "html_url": str,
        "issue_url": str,
        "author_association": str,
        "issue_number": int,
        "author_type": str,
        "is_bot": bool,
    },
    "catalog": COMMON_DOC,
    "markdown": {**COMMON_DOC, "type": str, "text": str},
    "api": {
        "source_id": str,
        "type": str,
        "version": str,
        "function": str,
        "docs_commit": str,
        "source_url": str,
        "function_source_url": str,
        "pinned_source_url": str,
        "json_pointer": str,
        "text_sha256": str,
        "text": str,
    },
}


class SeedProfileRejected(ValueError):
    """Only fixed diagnostics may leave this data-checking boundary."""


def _reject(code):
    raise SeedProfileRejected(code)


def _sha(content):
    return hashlib.sha256(content).hexdigest()


def _bytes(path):
    try:
        return path.read_bytes()
    except (OSError, ValueError):
        _reject("SeedSourceUnavailable")


def _json(content):
    try:
        return json.loads(content)
    except (ValueError, UnicodeError):
        _reject("SeedSourceInvalid")


def _file(seed, relative):
    if type(relative) is not str or not relative or "\\" in relative:
        _reject("SeedManifestInvalid")
    path = Path(relative)
    if (
        path.is_absolute()
        or path.as_posix() != relative
        or any(part in (".", "..", "") for part in relative.split("/"))
    ):
        _reject("SeedManifestInvalid")
    target = seed / path
    if not target.resolve().is_relative_to(seed.resolve()) or target.is_symlink():
        _reject("SeedManifestInvalid")
    return target


def _integers(values, code):
    if not isinstance(values, list) or any(type(x) is not int or x <= 0 for x in values):
        _reject(code)
    if len(set(values)) != len(values):
        _reject(code)
    return values


def _records(content, kind):
    try:
        rows = [_json(line) for line in content.decode("utf-8").splitlines() if line.strip()]
    except UnicodeError:
        _reject("SeedSourceInvalid")
    schema = SCHEMAS[kind]
    if not rows:
        _reject("SeedSchemaMismatch")
    for row in rows:
        if not isinstance(row, dict) or set(row) != set(schema):
            _reject("SeedSchemaMismatch")
        for key, expected in schema.items():
            accepted = expected if isinstance(expected, tuple) else (expected,)
            if type(row[key]) not in accepted:
                _reject("SeedSchemaMismatch")
        if any(
            type(value) is list and any(type(x) is not str for x in value) for value in row.values()
        ):
            _reject("SeedSchemaMismatch")
        for key in ("id", "number", "issue_number"):
            if key in row and row[key] <= 0:
                _reject("SeedSchemaMismatch")
        for key in ("comments", "bytes"):
            if key in row and row[key] < 0:
                _reject("SeedSchemaMismatch")
    key = "number" if kind == "issues" else "id" if kind == "comments" else "source_id"
    if len({r[key] for r in rows}) != len(rows):
        _reject("SeedDuplicateKey")
    if kind == "issues" and len({r["id"] for r in rows}) != len(rows):
        _reject("SeedDuplicateKey")
    return rows


def _dates(row):
    dates = {}
    for key in ("created_at", "updated_at", "closed_at"):
        if key not in row or row[key] is None:
            continue
        try:
            value = datetime.fromisoformat(row[key])
        except (ValueError, TypeError):
            _reject("SeedTimestampInvalid")
        if value.tzinfo is None:
            _reject("SeedTimestampInvalid")
        dates[key] = value
    if dates["updated_at"] < dates["created_at"]:
        _reject("SeedTimestampInvalid")


def _url(value, host):
    if type(value) is not str:
        _reject("SeedProvenanceInvalid")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname != host
        or not parsed.path
        or parsed.username is not None
        or parsed.password is not None
    ):
        _reject("SeedProvenanceInvalid")


def _profile_rows(rows, kind):
    key = "number" if kind == "issues" else "id" if kind == "comments" else "source_id"
    texts = [(r["source_id"], r["text"]) for r in rows if "text" in r]
    profile = {
        "row_count": len(rows),
        "primary_key": key,
        "distinct_keys": len(rows),
        "duplicate_keys": 0,
        "columns": list(SCHEMAS[kind]),
        "null_counts": {k: sum(r[k] is None for r in rows) for k in SCHEMAS[kind]},
        "empty_string_counts": {
            k: sum(r[k] == "" for r in rows)
            for k in SCHEMAS[kind]
            if str
            in (SCHEMAS[kind][k] if isinstance(SCHEMAS[kind][k], tuple) else (SCHEMAS[kind][k],))
        },
    }
    if texts:
        profile.update(
            {
                "max_text_chars": max(len(text) for _, text in texts),
                "over_20000_chars": [
                    {"source_id": identity, "chars": len(text)}
                    for identity, text in texts
                    if len(text) > 20000
                ],
            }
        )
    if kind in ("issues", "comments"):
        profile["timestamp_ranges"] = {
            k: {
                "min": min((r[k] for r in rows if r[k]), key=datetime.fromisoformat),
                "max": max((r[k] for r in rows if r[k]), key=datetime.fromisoformat),
            }
            for k in ("created_at", "updated_at")
        }
        profile["updated_after_created"] = sum(
            datetime.fromisoformat(r["updated_at"]) > datetime.fromisoformat(r["created_at"])
            for r in rows
        )
    if kind == "issues":
        profile["alternate_key_distinct_counts"] = {"id": len({r["id"] for r in rows})}
    return profile


def profile_seed(seed: Path, split: Path) -> dict:
    """Reproduce a source-bound profile without reading indexes, env or providers."""
    try:
        return _profile_seed(seed, split)
    except SeedProfileRejected:
        raise
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, AttributeError):
        _reject("SeedSourceInvalid")


def _profile_seed(seed: Path, split: Path) -> dict:
    seed, split = Path(seed), Path(split)
    manifest_bytes = _bytes(seed / "manifest.json")
    manifest = _json(manifest_bytes)
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), list):
        _reject("SeedManifestInvalid")
    entries = manifest["files"]
    contents = {}
    for entry in entries:
        if (
            not isinstance(entry, dict)
            or set(entry) != {"path", "bytes", "sha256"}
            or type(entry["bytes"]) is not int
            or entry["bytes"] < 0
            or type(entry["sha256"]) is not str
            or not re.fullmatch(r"[a-f0-9]{64}", entry["sha256"])
        ):
            _reject("SeedManifestInvalid")
        path = _file(seed, entry["path"])
        if entry["path"] in contents:
            _reject("SeedManifestInvalid")
        content = _bytes(path)
        if len(content) != entry["bytes"] or _sha(content) != entry["sha256"]:
            _reject("SeedChecksumMismatch")
        contents[entry["path"]] = content
    required = {*FILES.values(), FAMILIES, LINKS, EXPOSURE, "schemas.json"}
    if not required.issubset(contents):
        _reject("SeedManifestIncomplete")
    data = {kind: _records(contents[path], kind) for kind, path in FILES.items()}
    schema = _json(contents["schemas.json"])
    for kind, schema_name in (
        ("issues", "issue_records"),
        ("comments", "comment_records"),
        ("catalog", "docs_catalog"),
        ("markdown", "markdown_records"),
        ("api", "api_records"),
    ):
        if (
            not isinstance(schema, dict)
            or not isinstance(schema.get(schema_name), dict)
            or schema[schema_name].get("file") != FILES[kind]
            or schema[schema_name].get("fields") != list(SCHEMAS[kind])
        ):
            _reject("SeedSchemaMismatch")
    commit = manifest.get("docs_commit")
    if (
        type(commit) is not str
        or not re.fullmatch(r"[a-f0-9]{40}", commit)
        or manifest.get("package") != "streamlit-data-for-dev-test"
        or manifest.get("source_repository") != "https://github.com/streamlit/streamlit"
    ):
        _reject("SeedProvenanceInvalid")
    catalog = {r["source_id"]: r for r in data["catalog"]}
    for kind in ("catalog", "markdown", "api"):
        for row in data[kind]:
            if row["docs_commit"] != commit:
                _reject("SeedProvenanceInvalid")
            if row["source_url"] is not None:
                _url(row["source_url"], "docs.streamlit.io")
            if kind == "api":
                _url(row["function_source_url"], "github.com")
                if (
                    row["source_id"] != f"docstring:{row['version']}:{row['function']}"
                    or row["json_pointer"] != f"/{row['version']}/{row['function']}"
                    or not re.fullmatch(r"\d+\.\d+\.\d+", row["version"])
                ):
                    _reject("SeedProvenanceInvalid")
                file = "python/streamlit.json"
                if _sha(row["text"].encode()) != row["text_sha256"]:
                    _reject("SeedTextHashMismatch")
            else:
                file = row["file"]
                if row["source_id"] != f"docs:{file}" or not re.fullmatch(
                    r"[a-f0-9]{64}", row["sha256"]
                ):
                    _reject("SeedProvenanceInvalid")
                if kind == "markdown":
                    if (
                        _sha(row["text"].encode()) != row["sha256"]
                        or len(row["text"].encode()) != row["bytes"]
                    ):
                        _reject("SeedTextHashMismatch")
                    if row["source_id"] not in catalog or any(
                        row[key] != catalog[row["source_id"]][key] for key in COMMON_DOC
                    ):
                        _reject("SeedJoinMismatch")
            if (
                row["pinned_source_url"]
                != f"https://github.com/streamlit/docs/blob/{commit}/{file}"
            ):
                _reject("SeedProvenanceInvalid")
    issues = {r["number"]: r for r in data["issues"]}
    comments = Counter(r["issue_number"] for r in data["comments"])
    if set(comments) - set(issues):
        _reject("SeedJoinMismatch")
    if any(row["comments"] != comments[number] for number, row in issues.items()):
        _reject("SeedCommentCountMismatch")
    for row in data["issues"]:
        _dates(row)
        if (
            row["html_url"] != f"https://github.com/streamlit/streamlit/issues/{row['number']}"
            or row["state"] not in ("open", "closed")
            or (row["closed_at"] is None) != (row["state"] == "open")
        ):
            _reject("SeedProvenanceInvalid")
    for row in data["comments"]:
        _dates(row)
        prefix = f"https://github.com/streamlit/streamlit/issues/{row['issue_number']}"
        if (
            row["html_url"] != f"{prefix}#issuecomment-{row['id']}"
            or row["issue_url"]
            != f"https://api.github.com/repos/streamlit/streamlit/issues/{row['issue_number']}"
        ):
            _reject("SeedProvenanceInvalid")
    exposure = _json(contents[EXPOSURE])
    if not isinstance(exposure, dict):
        _reject("SeedExposureInvalid")
    exposed = set(_integers(exposure.get("issue_numbers"), "SeedExposureInvalid"))
    families = _json(contents[FAMILIES])
    if not isinstance(families, list):
        _reject("SeedLinkageInvalid")
    edges, family_rows = set(), set()
    for row in families:
        if (
            not isinstance(row, dict)
            or set(row) != {"number", "linked_selected_issue_numbers"}
            or type(row["number"]) is not int
            or row["number"] not in issues
            or row["number"] in family_rows
        ):
            _reject("SeedLinkageInvalid")
        family_rows.add(row["number"])
        targets = _integers(row["linked_selected_issue_numbers"], "SeedLinkageInvalid")
        if not set(targets).issubset(issues):
            _reject("SeedLinkageInvalid")
        edges.update((row["number"], target) for target in targets)
    links = _json(contents[LINKS])
    if not isinstance(links, dict):
        _reject("SeedLinkageInvalid")
    for path, values in links.items():
        if type(path) is not str or f"docs:{path}" not in catalog:
            _reject("SeedLinkageInvalid")
        _integers(values, "SeedLinkageInvalid")
    split_bytes = _bytes(split)
    split_data = _json(split_bytes)
    if (
        not isinstance(split_data, dict)
        or split_data.get("status") not in ("draft_not_frozen", "frozen")
        or not isinstance(split_data.get("selected"), dict)
        or not isinstance(split_data.get("targets"), dict)
        or not isinstance(split_data.get("families"), list)
    ):
        _reject("SeedSplitInvalid")
    selected = split_data["selected"]
    for part in ("dev", "test"):
        if (
            not isinstance(selected.get(part), list)
            or any(type(x) is not str or not x for x in selected[part])
            or len(set(selected[part])) != len(selected[part])
            or type(split_data["targets"].get(f"{part}_cases")) is not int
            or split_data["targets"][f"{part}_cases"] <= 0
        ):
            _reject("SeedSplitInvalid")
    if set(selected["dev"]) & set(selected["test"]):
        _reject("SeedSplitInvalid")
    split_ids = set()
    for row in split_data["families"]:
        if not isinstance(row, dict) or row.get("split") not in ("dev", "test"):
            _reject("SeedSplitInvalid")
        members = _integers(row.get("issue_ids"), "SeedSplitInvalid")
        if not members or split_ids.intersection(members):
            _reject("SeedSplitInvalid")
        split_ids.update(members)
    reserved = set(_integers(split_data.get("exposure_reserved_issue_ids"), "SeedSplitInvalid"))
    known_excluded = sorted(exposed | reserved | split_ids)
    known_links = [
        {
            "source_id": row["source_id"],
            "issue_numbers": sorted(set(links.get(row["file"], [])) & set(known_excluded)),
        }
        for row in data["markdown"]
        if set(links.get(row["file"], [])) & set(known_excluded)
    ]
    versions = sorted(
        {r["version"] for r in data["api"]}, key=lambda x: tuple(map(int, x.split(".")))
    )
    functions = sorted({r["function"] for r in data["api"]})
    hashes = Counter(r["text_sha256"] for r in data["api"])
    expected_counts = {
        "issues": len(data["issues"]),
        "comments": len(data["comments"]),
        "documentation_catalog_metadata_records": len(data["catalog"]),
        "full_markdown_records": len(data["markdown"]),
        "full_api_records": len(data["api"]),
        "api_versions": len(versions),
        "api_function_names": len(functions),
    }
    if manifest.get("counts") != expected_counts or manifest.get("api_versions") != versions:
        _reject("SeedCountMismatch")
    findings = [
        {
            "code": "SeedIsNotApprovedCorpus",
            "severity": "high",
            "confidence": "high",
            "evidence": "Package integrity does not authorize ingestion or prove retrieval/model quality.",
        },
        {
            "code": "UnreviewedFamilyCandidates",
            "severity": "high",
            "confidence": "high",
            "evidence": "Issue links are candidates, not confirmed duplicates or a complete family map.",
        },
        {
            "code": "CurrentIssueMetadataIsNotInitialBody",
            "severity": "high",
            "confidence": "high",
            "evidence": "All later updated_at values reflect metadata updates; they do not prove body edits. Curate initial visible information separately.",
        },
        {
            "code": "VersionedRepeatedText",
            "severity": "medium",
            "confidence": "high",
            "evidence": "Repeated API text retains separate version/function source IDs; document version is not installed user version.",
        },
        {
            "code": "CorpusLicenseNotEstablishedByPackage",
            "severity": "medium",
            "confidence": "high",
            "evidence": "No source LICENSE is bundled; this profile does not assign a license to Issue comments or generated documentation.",
        },
    ]
    if split_data["status"] != "frozen":
        findings.append(
            {
                "code": "EvaluationSplitNotFrozen",
                "severity": "high",
                "confidence": "high",
                "evidence": "Selected dev/test counts are draft; final corpus family exclusion cannot close.",
            }
        )
    if known_links:
        findings.append(
            {
                "code": "KnownExposureLinkedFromDocs",
                "severity": "high",
                "confidence": "high",
                "evidence": "Known excluded Issue links occur in Markdown; review or exclude those documents before a pilot index.",
            }
        )
    if any(len(row["text"]) > 20000 for row in data["markdown"]):
        findings.append(
            {
                "code": "WholeDocumentsExceedEvidenceLimit",
                "severity": "medium",
                "confidence": "high",
                "evidence": "Exact bounded source spans are required; truncating whole documents loses reviewable provenance.",
            }
        )
    return {
        "schema_version": 1,
        "profile_id": "streamlit-seed-profile-v1",
        "accepted": True,
        "seed_integrity_verified": True,
        "pilot_ingestion_approved": False,
        "final_corpus_ready": False,
        "real_model_tested": False,
        "quality_claim": False,
        "actual_cost_usd": 0,
        "source": {
            "package": manifest.get("package"),
            "repository": manifest.get("source_repository"),
            "github_snapshot_date": manifest.get("github_snapshot_date"),
            "docs_commit": commit,
            "manifest_sha256": _sha(manifest_bytes),
            "split_sha256": _sha(split_bytes),
            "verified_package_files": len(entries),
            "input_sha256": {path: _sha(contents[path]) for path in sorted(required)},
        },
        "datasets": {kind: _profile_rows(rows, kind) for kind, rows in data.items()},
        "joins": {
            "orphan_comments": 0,
            "comment_count_mismatches": 0,
            "markdown_catalog_mismatches": 0,
            "bot_comment_count": sum(r["is_bot"] for r in data["comments"]),
        },
        "api_versions": {
            "versions": versions,
            "functions": functions,
            "distinct_text_hashes": len(hashes),
            "records_repeating_existing_text": len(data["api"]) - len(hashes),
            "absent_version_function_combinations": len(versions) * len(functions)
            - len(data["api"]),
            "version_identity_preserved": True,
        },
        "exclusion": {
            "declared_exposure_issue_ids": sorted(exposed),
            "known_excluded_issue_ids": known_excluded,
            "known_ids_missing_from_seed": sorted(set(known_excluded) - set(issues)),
            "draft_status": split_data["status"],
            "manifest_id": split_data.get("manifest_id"),
            "selected_counts": {part: len(selected[part]) for part in ("dev", "test")},
            "target_counts": {
                part: split_data["targets"][f"{part}_cases"] for part in ("dev", "test")
            },
            "family_candidate_rows": len(family_rows),
            "family_candidate_edges": len(edges),
            "family_candidate_touched_issues": len({number for edge in edges for number in edge}),
            "candidate_links_are_confirmed_duplicates": False,
            "known_linked_docs": known_links,
            "complete_family_exclusion_verified": False,
        },
        "findings": findings,
    }


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        _reject("SeedProfileArgumentsInvalid")


def main(argv=None):
    parser = _Parser(description=__doc__)
    parser.add_argument("--seed", type=Path, default=ROOT / "streamlit-data-for-dev-test")
    parser.add_argument("--split", type=Path, default=ROOT / "data/evaluation/split-manifest.json")
    parser.add_argument(
        "--output", type=Path, help="Create a new receipt; existing files are preserved."
    )
    try:
        args = parser.parse_args(argv)
        receipt = profile_seed(args.seed, args.split)
        rendered = json.dumps(receipt, ensure_ascii=False, indent=2) + "\n"
        if args.output is not None:
            try:
                with args.output.open("x", encoding="utf-8") as output:
                    output.write(rendered)
            except FileExistsError:
                _reject("SeedProfileOutputExists")
            except OSError:
                _reject("SeedProfileOutputUnavailable")
        print(rendered, end="")
        return 0
    except SeedProfileRejected as exc:
        print(json.dumps({"accepted": False, "error_code": str(exc), "quality_claim": False}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
