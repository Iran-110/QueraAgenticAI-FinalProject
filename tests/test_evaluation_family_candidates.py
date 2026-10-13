"""Metadata reservations protect held-out questions without claiming a frozen split."""

import hashlib
import importlib.util
import json
import shutil
import socket
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "evaluation_family_candidates", ROOT / "scripts/propose_evaluation_families.py"
)
assert SPEC is not None and SPEC.loader is not None
candidates = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(candidates)
SEED = ROOT / "streamlit-data-for-dev-test"
REGISTERED = ROOT / "data/evaluation/candidates/reservations-v1.json"


@pytest.fixture
def seed(tmp_path):
    target = tmp_path / "seed"
    target.mkdir()
    for relative in ("manifest.json", *candidates.FILES.values()):
        dest = target / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SEED / relative, dest)
    return target


def update_package(seed, relative, raw):
    (seed / relative).write_bytes(raw)
    path = seed / "manifest.json"
    manifest = json.loads(path.read_bytes())
    entry = next(entry for entry in manifest["files"] if entry["path"] == relative)
    entry.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    path.write_text(json.dumps(manifest), encoding="utf-8")


def test_registered_candidates_are_byte_reproducible_offline_and_not_final(monkeypatch):
    def deny_network(*_args, **_kwargs):
        raise AssertionError("Metadata-only reservation attempted network access")

    monkeypatch.setattr(socket, "create_connection", deny_network)
    monkeypatch.setattr(socket.socket, "connect", deny_network)
    first = candidates.propose(SEED)
    assert candidates.encoded(first) == candidates.encoded(candidates.propose(SEED))
    assert candidates.encoded(first) == REGISTERED.read_bytes()
    assert first["reservation_counts"] == {"dev": 15, "test": 15}
    assert first["status"] == "candidate_reservations_not_frozen"
    assert not first["e1_complete"] and not first["quality_claim"]
    assert first["validated_multi_turn_cases"] == 0
    assert not first["partial_corpus_denylist"]["complete"]
    assert not first["partial_corpus_denylist"]["may_be_used_as_final_allowlist"]
    for relative, digest in first["source"]["input_sha256"].items():
        assert hashlib.sha256((SEED / relative).read_bytes()).hexdigest() == digest
    assert (
        first["source"]["generator_sha256"]
        == hashlib.sha256(Path(candidates.__file__).read_bytes()).hexdigest()
    )


def test_exposure_closure_and_entire_candidate_components_are_disjoint():
    proposal = candidates.propose(SEED)
    exposure = {8061, 8901, 9031, 11012, 12629, 12782, 16914, 17030}
    assert set(proposal["known_exposure_candidate_closure"]) == exposure
    membership = {}
    for row in proposal["candidates"]:
        for number in row["issue_ids"]:
            assert number not in membership
            membership[number] = row["candidate_family_id"]
        if row["proposed_split"] == "test":
            assert not exposure.intersection(row["issue_ids"])
    links = json.loads((SEED / candidates.FILES["links"]).read_bytes())
    for row in links:
        for target in row["linked_selected_issue_numbers"]:
            if row["number"] in membership or target in membership:
                assert membership.get(row["number"]) == membership.get(target)
    known = next(row for row in proposal["candidates"] if row["known_exposed_dev_family"])
    assert known["proposed_split"] == "dev" and known["issue_ids"] == [12629, 12782]
    assert exposure <= set(proposal["partial_corpus_denylist"]["issue_ids"])


def test_query_domains_are_balanced_and_human_review_is_pending():
    proposal = candidates.propose(SEED)
    for split in ("dev", "test"):
        counts = Counter(
            row["sampling_domain"]
            for row in proposal["candidates"]
            if row["proposed_split"] == split and not row["known_exposed_dev_family"]
        )
        assert set(counts) == set(candidates.DOMAINS)
        assert max(counts.values()) - min(counts.values()) <= 1
    assert len(proposal["human_review_tasklist"]) == 30
    assert all(task["status"] == "pending" for task in proposal["human_review_tasklist"])
    forbidden = {
        "body",
        "title",
        "labels",
        "state",
        "state_reason",
        "gold",
        "visible",
        "agent_script",
        "answer",
        "text",
    }

    def safe(value):
        if isinstance(value, dict):
            assert not forbidden.intersection(value)
            for item in value.values():
                safe(item)
        elif isinstance(value, list):
            for item in value:
                safe(item)

    safe(proposal)


def test_question_and_outcome_mutation_cannot_change_candidate_selection(seed):
    original = candidates.propose(seed)
    relative = candidates.FILES["issues"]
    records = [
        json.loads(line) for line in (seed / relative).read_text(encoding="utf-8").splitlines()
    ]
    for row in records:
        row.update(
            body="PRIVATE_HELDOUT_ANSWER",
            title="PRIVATE_HELDOUT_QUESTION",
            state_reason="PRIVATE_OUTCOME",
            labels=["PRIVATE_LABEL"],
        )
    raw = ("\n".join(json.dumps(row) for row in records) + "\n").encode()
    update_package(seed, relative, raw)
    changed = candidates.propose(seed)
    assert changed["candidates"] == original["candidates"]
    assert changed["source"]["input_sha256"] != original["source"]["input_sha256"]
    assert "PRIVATE" not in candidates.encoded(changed).decode()


def test_changed_metadata_bytes_without_repackaging_fail_closed(seed):
    (seed / candidates.FILES["issues"]).write_text("PRIVATE_TAMPERED_SOURCE")
    with pytest.raises(
        candidates.CandidateReservationRejected, match="^CandidateChecksumMismatch$"
    ):
        candidates.propose(seed)


def test_insufficient_eligible_pool_never_returns_partial_or_fake_complete_split():
    with pytest.raises(
        candidates.CandidateReservationRejected, match="^InsufficientEligibleCandidateFamilies$"
    ):
        candidates.propose(SEED, test_count=1000)


def test_writer_never_overwrites_a_prior_reservation(tmp_path):
    output = tmp_path / "reservations.json"
    assert candidates.main(["--output", str(output)]) == 0
    prior = output.read_bytes()
    with pytest.raises(
        candidates.CandidateReservationRejected, match="^CandidateOutputAlreadyExists$"
    ):
        candidates.main(["--output", str(output)])
    assert output.read_bytes() == prior
