"""The split-e1-v1 freeze artifacts stay internally consistent.

Reads only freeze metadata, the draft manifest, exposure declarations and the
final allowlist; no held-out fixture, gold or review file is opened.
"""

import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FREEZE = "data/evaluation/split-e1-v1/freeze/"
HELD_OUT_PIN = "data/evaluation/split-e1-v1/native/native-test-exposure-decision-v1.json"
KNOWN_EXPOSURE = {8061, 8901, 9031, 11012, 12629, 12782, 16914, 17030}


def _sha(name):
    return hashlib.sha256((ROOT / name).read_bytes()).hexdigest()


def _load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def record():
    return _load(FREEZE + "freeze-record-v1.json")


def test_record_pins_every_artifact_at_its_current_bytes(record):
    assert record["status"] == "frozen_pending_native_pins"
    for pin in record["artifacts"].values():
        assert pin["sha256"] == _sha(pin["path"]), pin["path"]


def test_rubric_is_frozen_and_pins_both_rubric_documents():
    rubric = _load(FREEZE + "rubric-frozen-v1.json")
    assert rubric["status"] == "frozen" and rubric["rubric_id"] == "e2-rubric-v1"
    assert rubric["judge"] is None
    for document in rubric["documents"]:
        assert document["sha256"] == _sha(document["path"])


def test_frozen_split_keeps_the_draft_and_has_disjoint_reviewed_families():
    split = _load(FREEZE + "split-manifest-frozen-v1.json")
    draft = split["supersedes"]
    assert draft["sha256"] == _sha(draft["path"])
    assert split["status"] == "frozen"
    seen = set()
    for family in split["families"]:
        issues = set(family["exclude_issue_ids"])
        assert family["review_status"] == "complete" and not issues & seen
        seen |= issues
    splits = [family["split"] for family in split["families"]]
    assert splits.count("dev") == 16 and splits.count("test") == 15
    assert seen <= set(split["index_exclusion"]["issue_ids"])


def test_exposure_partitions_known_issues_and_avoids_test_families():
    exposure = _load(FREEZE + "exposure-frozen-v1.json")
    split = _load(FREEZE + "split-manifest-frozen-v1.json")
    exposed = set(exposure["issue_numbers"])
    assert exposure["status"] == "reviewed_complete" and KNOWN_EXPOSURE <= exposed
    grouped = [i for family in exposure["families"] for i in family["issue_ids"]]
    assert sorted(grouped) == sorted(exposed) and len(grouped) == len(set(grouped))
    test_issues = {
        i
        for family in split["families"]
        if family["split"] == "test"
        for i in family["exclude_issue_ids"]
    }
    assert not exposed & test_issues
    assert exposure["separate_gold_exposure"]["decision"]["path"] == HELD_OUT_PIN
    for source in exposure["sources"]:
        assert source["sha256"] == _sha(source["path"])


def test_corpus_excludes_every_blocked_issue_and_matches_the_final_allowlist():
    corpus = _load(FREEZE + "corpus-frozen-v1.json")
    split = _load(FREEZE + "split-manifest-frozen-v1.json")
    exposure = _load(FREEZE + "exposure-frozen-v1.json")
    exclusions = corpus["exclusions"]
    excluded = set(exclusions["excluded_issue_ids"])
    assert excluded == set(split["index_exclusion"]["issue_ids"])
    blocked = set(exposure["issue_numbers"]).union(
        *(family["exclude_issue_ids"] for family in split["families"])
    )
    assert (
        blocked
        <= excluded
        <= blocked
        | set(
            _load("data/evaluation/dev-three-v1/split-manifest.json")["exposure_reserved_issue_ids"]
        )
    )
    assert blocked <= set(exclusions["duplicate_review"]["issue_ids"])
    allowlist = _load(corpus["allowlist"]["path"])
    assert corpus["allowlist"]["sha256"] == _sha(corpus["allowlist"]["path"])
    allowed = set(allowlist["markdown_source_ids"]) | set(allowlist["api_source_ids"])
    ids = [source["source_id"] for source in corpus["sources"]]
    assert len(ids) == len(set(ids)) and set(ids) == allowed
    direct = exclusions["direct_answer_review"]
    assert direct["corpus_source_ids"] == ids
    assert not set(direct["excluded_source_ids"]) & set(ids)
    for source in corpus["sources"]:
        provenance = source["provenance"]
        assert source["kind"] in {"documentation", "release_note"}
        assert "github.com/streamlit/streamlit/issues" not in provenance["url"]
        assert provenance["source_revision"] == corpus["docs_commit"]


def test_every_witness_is_human_and_bound_to_the_frozen_rubric(record):
    rubric_sha = record["artifacts"]["rubric"]["sha256"]
    corpus = _load(FREEZE + "corpus-frozen-v1.json")["exclusions"]
    witnesses = [
        record["review"],
        _load(FREEZE + "exposure-frozen-v1.json")["review"],
        _load(FREEZE + "split-manifest-frozen-v1.json")["family_review"],
        corpus["review"],
        corpus["duplicate_review"]["review"],
        corpus["direct_answer_review"]["review"],
    ]
    for witness in witnesses:
        assert witness["type"] == "human" and witness["reviewer"] == "mhg"
        assert witness["rubric_sha256"] == rubric_sha
        assert witness["independence"] == "assistant_informed"
    assert set(record["review_export"]["decisions"].values()) == {"correct"}
