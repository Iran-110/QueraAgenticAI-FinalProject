"""A registered real-Issue development anchor, through offline HTTP/core ports."""

import hashlib
import importlib.util
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

from agent_app import api
from agent_app.contracts import CaseState, Fact

_REPLAY_PATH = Path(__file__).resolve().parents[1] / "experiments/user_intake/replay.py"
_SPEC = importlib.util.spec_from_file_location("user_intake_replay", _REPLAY_PATH)
assert _SPEC is not None and _SPEC.loader is not None
replay = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(replay)


@pytest.fixture(scope="module")
def receipt():
    return replay.replay_pilot()


def test_registered_pilot_connects_user_facts_corrections_and_separate_approval(receipt):
    assert receipt["result"] == "passed_registered_software_assertions"
    assert receipt["summary"] == {
        "accepted_primary_turns": 7,
        "reasoner_calls": 7,
        "retrieval_calls": 7,
        "fixture_seed_checkpoints": 3,
        "whole_registered_source_quotes_checked": 2,
        "approved_releases": 3,
        "paid_requests": 0,
        "API_cost_USD": "0",
        "real_model_calls": 0,
        "real_RAG_queries": 0,
    }
    turns = {turn["turn_id"]: turn for turn in receipt["turns"]}
    # This is the actual case observed by the reasoning port, after intake.
    corrected = turns["intake-3"]["reasoner_input_case"]
    assert [
        (fact["value"], fact["status"], fact["turn_id"])
        for fact in corrected["facts"]
        if fact["name"] == "streamlit_version"
    ] == [
        ("1.50.0", "superseded", "intake-2"),
        ("1.49.1", "active", "intake-3"),
    ]
    withdrawn = turns["intake-4"]["reasoner_input_case"]
    assert "streamlit_version" in withdrawn["unknowns"]
    assert not any(
        fact["name"] == "streamlit_version" and fact["status"] == "active"
        for fact in withdrawn["facts"]
    )
    new_environment = turns["intake-5"]["reasoner_input_case"]
    assert {
        (fact["name"], fact["value"], fact["source_ref"])
        for fact in new_environment["facts"]
        if fact["status"] == "active" and fact["provenance_kind"] == "user"
    } == {
        ("streamlit_version", "1.50.0", "user:intake-5"),
        ("python_version", "3.13", "user:intake-5"),
    }
    check_only = turns["intake-6"]["reasoner_input_case"]
    assert check_only["evidence_refs"] == []
    assert "prior_evidence_observation" in check_only["unknowns"]
    repeated = turns["intake-7"]["reasoner_input_case"]
    assert repeated["evidence_refs"] == ["release-150-multiselect-key-identity-v8"]
    assert "prior_evidence_observation" not in repeated["unknowns"]
    assert check_only["checks_performed"] == repeated["checks_performed"]
    assert receipt["final_view"]["status"] == "escalated"
    assert [entry["role"] for entry in receipt["final_view"]["log"]].count("assistant") == 3
    assert len(receipt["final_view"]["decisions"]) == 3
    probes = Counter(probe["probe"] for probe in receipt["ingress_and_review_probes"])
    assert probes["identical_replay_and_changed_event_conflict"] == 7
    assert probes["previous_proposal_approval"] == 6
    assert probes["approved_once_repeated_approval_rejected"] == 3
    assert probes["reply_before_question_approval"] == 1
    assert probes["stale_new_user_event"] == 1


def test_receipt_is_reproducible_and_replay_restores_existing_api_globals(receipt):
    cases, tracker, script, uuid_factory = (
        api._cases,
        api.tracker,
        api._script,
        replay.engine_module.uuid4,
    )
    second = replay.replay_pilot()
    assert second == receipt
    assert api._cases is cases and api.tracker is tracker and api._script is script
    assert replay.engine_module.uuid4 is uuid_factory
    unsigned = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    assert receipt["receipt_sha256"] == replay._digest(unsigned)
    manifest = receipt["executed_code_sha256"]
    assert set(manifest) == set(replay.CODE_PATHS)
    assert (
        manifest["src/agent_app/api.py"]
        == hashlib.sha256((replay.ROOT / "src/agent_app/api.py").read_bytes()).hexdigest()
    )
    assert receipt["code_sha256"] == replay._digest(manifest)
    assert receipt["runtime"]["packages"]["fastapi"]
    assert receipt["turns"][1]["wire_request"]["reply_to_proposal_id"] == "proposal:intake-1"
    assert all(
        turn["hash_verification"]
        == {"original_ingress_verified": True, "prepared_turn_verified": True}
        for turn in receipt["turns"]
    )


def test_changed_registered_expectations_are_rejected_before_replay(tmp_path):
    fixture = json.loads(replay.FIXTURE_PATH.read_text())
    fixture["turns"][2]["expected"]["active_user_version"] = "1.50.0"
    path = tmp_path / "changed-fixture.json"
    path.write_text(json.dumps(fixture))
    with pytest.raises(ValueError, match="Registered user-intake fixture hash mismatch"):
        replay.replay_pilot(path)


def test_receipt_write_keeps_previous_audit_file_intact(tmp_path, receipt):
    path = tmp_path / "pilot.json"
    replay.write_receipt(path, receipt)
    first = path.read_bytes()
    assert json.loads(first) == receipt
    with pytest.raises(FileExistsError):
        replay.write_receipt(path, {"unexpected": "replacement"})
    assert path.read_bytes() == first


def test_optimized_python_cannot_claim_assertions_passed_or_write_receipt(tmp_path):
    path = tmp_path / "false-success.json"
    result = subprocess.run(
        [sys.executable, "-O", str(_REPLAY_PATH), "--output", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert json.loads(result.stdout) == {"error_code": "AssertionChecksDisabled"}
    assert not path.exists()


def test_changed_code_during_replay_cannot_receive_a_success_receipt(monkeypatch):
    original = replay.code_manifest
    calls = 0

    def changed_manifest():
        nonlocal calls
        calls += 1
        manifest = original()
        if calls > 1:
            manifest["src/agent_app/api.py"] = "0" * 64
        return manifest

    monkeypatch.setattr(replay, "code_manifest", changed_manifest)
    with pytest.raises(RuntimeError, match="CodeChangedDuringReplay"):
        replay.replay_pilot()


def test_pilot_fails_if_correction_keeps_stale_evidence(monkeypatch):
    original = api.propose_user_turn

    def broken_correction(case, turn):
        result = original(case, turn)
        if turn.turn_id != "intake-3":
            return result
        facts = [
            Fact.model_validate({**fact.model_dump(mode="json"), "status": "active"})
            if fact.name == "prior_evidence_observation"
            else fact
            for fact in result.candidate.facts
        ]
        candidate = CaseState.model_validate(
            {
                **result.candidate.model_dump(mode="json"),
                "facts": [fact.model_dump(mode="json") for fact in facts],
                "evidence_refs": list(case.evidence_refs),
            }
        )
        return result.model_copy(update={"candidate": candidate})

    monkeypatch.setattr(api, "propose_user_turn", broken_correction)
    with pytest.raises(AssertionError, match="Stale inference retained"):
        replay.replay_pilot()


def test_existing_citation_id_cannot_hide_changed_source_claim_from_pilot(monkeypatch):
    class UnsupportedClaimReasoner(replay.FakeReasoner):
        def analyze(self, *args, **kwargs):
            result = super().analyze(*args, **kwargs)
            if result.decision == "answer":
                links = tuple(
                    link.model_copy(update={"claim": "This proves the app fix."})
                    for link in result.evidence_links
                )
                return result.model_copy(update={"evidence_links": links})
            return result

    monkeypatch.setattr(replay, "FakeReasoner", UnsupportedClaimReasoner)
    with pytest.raises(AssertionError, match="Answer must quote the complete registered excerpt"):
        replay.replay_pilot()
