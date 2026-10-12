import hashlib
import importlib.util
import json
import shutil
import socket
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "seed_profile_test_target", ROOT / "data_scripts/seed_profile.py"
)
assert SPEC is not None and SPEC.loader is not None
profiler = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(profiler)
SEED = ROOT / "streamlit-data-for-dev-test"
SPLIT = ROOT / "data/evaluation/split-manifest.json"


@pytest.fixture
def seed(tmp_path):
    target = tmp_path / "seed"
    shutil.copytree(SEED, target)
    return target


def repackage(seed, relative, content):
    """Update only the package envelope, so deeper checks are exercised."""
    if isinstance(content, list):
        rendered = "\n".join(json.dumps(row) for row in content) + "\n"
    elif isinstance(content, dict):
        rendered = json.dumps(content)
    else:
        rendered = content
    raw = rendered.encode()
    (seed / relative).write_bytes(raw)
    manifest = json.loads((seed / "manifest.json").read_text())
    entry = next(item for item in manifest["files"] if item["path"] == relative)
    entry.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    (seed / "manifest.json").write_text(json.dumps(manifest))


def records(seed, kind):
    return [json.loads(line) for line in (seed / profiler.FILES[kind]).read_text().splitlines()]


def test_current_seed_profile_is_reproducible_and_does_not_claim_corpus_or_quality(monkeypatch):
    def reject_network(*args, **kwargs):
        raise AssertionError("The offline profile attempted a network call")

    monkeypatch.setattr(socket, "create_connection", reject_network)
    monkeypatch.setattr(socket, "getaddrinfo", reject_network)
    monkeypatch.setattr(socket.socket, "connect", reject_network)
    first = profiler.profile_seed(SEED, SPLIT)
    assert first == profiler.profile_seed(SEED, SPLIT)
    assert first["accepted"] and first["seed_integrity_verified"]
    assert not first["pilot_ingestion_approved"] and not first["final_corpus_ready"]
    assert not first["quality_claim"] and not first["real_model_tested"]
    assert first["actual_cost_usd"] == 0
    assert {kind: row["row_count"] for kind, row in first["datasets"].items()} == {
        "issues": 240,
        "comments": 1178,
        "catalog": 403,
        "markdown": 56,
        "api": 1172,
    }
    assert first["joins"] == {
        "orphan_comments": 0,
        "comment_count_mismatches": 0,
        "markdown_catalog_mismatches": 0,
        "bot_comment_count": 173,
    }
    assert first["api_versions"]["distinct_text_hashes"] == 472
    assert first["api_versions"]["records_repeating_existing_text"] == 700
    assert first["api_versions"]["version_identity_preserved"]
    assert first["api_versions"]["absent_version_function_combinations"] == 290
    exclusion = first["exclusion"]
    assert exclusion["selected_counts"] == {"dev": 1, "test": 0}
    assert exclusion["known_ids_missing_from_seed"] == [12629]
    assert exclusion["known_linked_docs"] == [
        {
            "source_id": "docs:content/develop/quick-references/release-notes/2026.md",
            "issue_numbers": [8901],
        }
    ]
    assert exclusion["family_candidate_edges"] == 34
    assert not exclusion["candidate_links_are_confirmed_duplicates"]
    assert len(first["datasets"]["markdown"]["over_20000_chars"]) == 5
    assert first["datasets"]["issues"]["updated_after_created"] == 240
    assert first["datasets"]["catalog"]["null_counts"]["source_url"] == 2
    assert first["source"]["split_sha256"] == hashlib.sha256(SPLIT.read_bytes()).hexdigest()
    assert "text" not in json.dumps(first["source"])
    codes = {item["code"] for item in first["findings"]}
    assert {
        "EvaluationSplitNotFrozen",
        "KnownExposureLinkedFromDocs",
        "CurrentIssueMetadataIsNotInitialBody",
    }.issubset(codes)


@pytest.mark.parametrize(
    "change,expected",
    [
        ("missing", "SeedSourceUnavailable"),
        ("tampered", "SeedChecksumMismatch"),
        ("malformed_jsonl", "SeedSourceInvalid"),
        ("malformed_row", "SeedSchemaMismatch"),
        ("unknown_column", "SeedSchemaMismatch"),
        ("boolean_key", "SeedSchemaMismatch"),
        ("duplicate_key", "SeedDuplicateKey"),
        ("duplicate_issue_id", "SeedDuplicateKey"),
        ("orphan_comment", "SeedJoinMismatch"),
        ("wrong_comment_count", "SeedCommentCountMismatch"),
        ("api_text_tamper", "SeedTextHashMismatch"),
        ("markdown_text_tamper", "SeedTextHashMismatch"),
        ("markdown_catalog_mismatch", "SeedJoinMismatch"),
        ("wrong_commit", "SeedProvenanceInvalid"),
        ("wrong_api_pointer", "SeedProvenanceInvalid"),
        ("wrong_source_url", "SeedProvenanceInvalid"),
        ("wrong_timestamp", "SeedTimestampInvalid"),
    ],
)
def test_corrupt_seed_is_rejected_even_if_package_hashes_are_refreshed(seed, change, expected):
    kind = "comments" if change == "orphan_comment" else "issues"
    if change.startswith("api_") or change == "wrong_api_pointer":
        kind = "api"
    if change.startswith("markdown_"):
        kind = "markdown"
    relative = profiler.FILES[kind]
    rows = records(seed, kind)
    if change == "missing":
        (seed / relative).unlink()
    elif change == "tampered":
        (seed / relative).write_text("PRIVATE_SOURCE\n")
    elif change == "malformed_jsonl":
        repackage(seed, relative, "PRIVATE_INVALID_JSON\n")
    elif change == "malformed_row":
        rows[0] = ["PRIVATE_INVALID_ROW"]
    elif change == "unknown_column":
        rows[0]["unexpected"] = "PRIVATE_FIELD"
    elif change == "boolean_key":
        rows[0]["number"] = True
    elif change == "duplicate_key":
        rows.append(rows[0])
    elif change == "duplicate_issue_id":
        rows[1]["id"] = rows[0]["id"]
    elif change == "orphan_comment":
        rows[0]["issue_number"] = 99999999
    elif change == "wrong_comment_count":
        rows[0]["comments"] += 1
    elif change in ("api_text_tamper", "markdown_text_tamper"):
        rows[0]["text"] += "PRIVATE_CONTENT"
    elif change == "markdown_catalog_mismatch":
        rows[0]["title"] += "PRIVATE_TITLE"
    elif change == "wrong_commit":
        kind, relative = "api", profiler.FILES["api"]
        rows = records(seed, kind)
        rows[0]["docs_commit"] = "a" * 40
    elif change == "wrong_api_pointer":
        rows[0]["json_pointer"] = "/wrong/path"
    elif change == "wrong_source_url":
        kind, relative = "api", profiler.FILES["api"]
        rows = records(seed, kind)
        rows[0]["source_url"] = "https://PRIVATE_SOURCE.invalid/doc"
    elif change == "wrong_timestamp":
        rows[0]["updated_at"] = "PRIVATE_DATE"
    if change not in ("missing", "tampered", "malformed_jsonl"):
        repackage(seed, relative, rows)
    with pytest.raises(profiler.SeedProfileRejected) as caught:
        profiler.profile_seed(seed, SPLIT)
    assert str(caught.value) == expected
    assert "PRIVATE" not in str(caught.value)


@pytest.mark.parametrize(
    "change,expected",
    [
        ("unsafe_path", "SeedManifestInvalid"),
        ("noncanonical_path", "SeedManifestInvalid"),
        ("duplicate_entry", "SeedManifestInvalid"),
        ("missing_declared_file", "SeedManifestIncomplete"),
        ("wrong_counts", "SeedCountMismatch"),
        ("malformed_counts", "SeedCountMismatch"),
    ],
)
def test_package_envelope_cannot_hide_missing_sources_or_conflicting_counts(seed, change, expected):
    manifest = json.loads((seed / "manifest.json").read_text())
    if change == "unsafe_path":
        manifest["files"][0]["path"] = "../PRIVATE_OUTSIDE"
    elif change == "noncanonical_path":
        manifest["files"][0]["path"] = "./START_HERE.fa.txt"
    elif change == "duplicate_entry":
        manifest["files"].append(manifest["files"][0])
    elif change == "missing_declared_file":
        manifest["files"] = [
            entry for entry in manifest["files"] if entry["path"] != profiler.EXPOSURE
        ]
    elif change == "wrong_counts":
        manifest["counts"]["issues"] = 239
    else:
        manifest["counts"] = "PRIVATE_COUNTS"
    (seed / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(profiler.SeedProfileRejected, match=f"^{expected}$"):
        profiler.profile_seed(seed, SPLIT)


def test_family_candidates_do_not_authorize_exposed_issue_ingestion(seed):
    candidates = json.loads((seed / profiler.FAMILIES).read_text())
    candidates[0]["linked_selected_issue_numbers"].append(12629)
    repackage(seed, profiler.FAMILIES, json.dumps(candidates))
    with pytest.raises(profiler.SeedProfileRejected, match="^SeedLinkageInvalid$"):
        profiler.profile_seed(seed, SPLIT)


def test_split_requires_valid_disjoint_family_identifiers_and_preserves_hash(tmp_path):
    altered = json.loads(SPLIT.read_text())
    altered["families"].append(
        dict(altered["families"][0], family_id="PRIVATE_FAMILY", split="test")
    )
    split = tmp_path / "split.json"
    split.write_text(json.dumps(altered))
    with pytest.raises(profiler.SeedProfileRejected, match="^SeedSplitInvalid$"):
        profiler.profile_seed(SEED, split)
    altered["families"].pop()
    altered["status"] = "frozen"
    split.write_text(json.dumps(altered))
    result = profiler.profile_seed(SEED, split)
    assert result["source"]["split_sha256"] != hashlib.sha256(SPLIT.read_bytes()).hexdigest()
    assert not result["final_corpus_ready"]  # A label alone is not reviewed exclusion.


def test_cli_creates_exclusive_receipt_and_hides_source_paths(tmp_path, capsys):
    output = tmp_path / "profile.json"
    assert profiler.main(["--output", str(output)]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert json.loads(output.read_text()) == receipt
    original = output.read_bytes()
    assert profiler.main(["--output", str(output)]) == 1
    assert json.loads(capsys.readouterr().out)["error_code"] == "SeedProfileOutputExists"
    assert output.read_bytes() == original
    assert profiler.main(["--seed", str(tmp_path / "PRIVATE_MISSING_SOURCE")]) == 1
    error = capsys.readouterr()
    assert error.err == "" and "PRIVATE" not in error.out
    assert json.loads(error.out)["error_code"] == "SeedSourceUnavailable"


def test_cli_argument_errors_are_safe_fixed_codes(capsys):
    assert profiler.main(["--PRIVATE_UNKNOWN", "PRIVATE_VALUE"]) == 1
    error = capsys.readouterr()
    assert error.err == "" and "PRIVATE" not in error.out
    assert json.loads(error.out)["error_code"] == "SeedProfileArgumentsInvalid"
