"""Controlled C3 HTTP review handoff with an exposed real-Issue development anchor."""

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from agent_app import api
from agent_app.contracts import GroundedRequest
from agent_app.reasoning import grounding

REPLAY_PATH = Path(__file__).resolve().parents[1] / "experiments/review_handoff/replay.py"
SPEC = importlib.util.spec_from_file_location("review_handoff_replay", REPLAY_PATH)
assert SPEC is not None and SPEC.loader is not None
replay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(replay)


@pytest.fixture(scope="module")
def receipt():
    return replay.replay_handoff()


def test_current_case_latest_bundle_full_sources_and_catalog_reach_review(receipt):
    assert receipt["result"] == "passed_registered_software_assertions"
    assert receipt["summary"] == {
        "primary_turns": 4,
        "primary_reasoning_calls": 5,
        "primary_retrieval_calls": 5,
        "approved_releases": 2,
        "event_replays_without_additional_calls": 4,
        "conflict_control_reasoning_calls": 2,
        "conflict_control_retrieval_calls": 1,
        "paid_requests": 0,
        "API_cost_USD": "0",
        "real_model_calls": 0,
        "real_RAG_queries": 0,
    }
    initial, confirmed, corrected, withdrawn = receipt["turns"]
    assert "streamlit_version" in {
        item["name"] for item in initial["handoff"]["grounded_request"]["gaps"]
    }
    assert "streamlit_version" not in {
        item["name"] for item in confirmed["handoff"]["grounded_request"]["gaps"]
    }
    assert confirmed["handoff"]["case"]["facts"][-1]["value"] == "1.50.0"
    assert [
        (fact["value"], fact["status"])
        for fact in corrected["handoff"]["case"]["facts"]
        if fact["name"] == "streamlit_version"
    ] == [("1.50.0", "superseded"), ("1.49.1", "active")]
    assert corrected["handoff"]["evidence"]["retrieval_round"] == 2
    assert all(
        item["version_scope"] != "exact_metadata_match"
        for item in corrected["handoff"]["source_inventory"]
    )
    assert "release-150-multiselect-key-identity-v8" not in {
        hit["chunk_id"] for hit in corrected["handoff"]["evidence"]["hits"]
    }
    assert "streamlit_version" in withdrawn["handoff"]["case"]["unknowns"]
    assert not any(
        fact["name"] == "streamlit_version" and fact["status"] == "active"
        for fact in withdrawn["handoff"]["case"]["facts"]
    )
    assert all(
        hit["source_id"] and hit["source_commit"] and "applicable_versions" in hit
        for hit in confirmed["handoff"]["evidence"]["hits"]
    )
    assert set(confirmed["handoff"]["analysis"]) == {
        "decision",
        "user_draft",
        "maintainer_summary",
        "rationale",
        "evidence_links",
        "missing_info",
        "next_question",
        "retrieval_queries",
        "facts_delta",
        "checks_suggested",
    }


def test_actual_old_git_code_reproduces_same_four_handoff_gaps(receipt):
    baseline = receipt["baseline"]
    assert baseline["git_commit"] == "3f22ef9"
    assert baseline["actual_git_archive_import"]
    assert baseline["missing_source_fields"] == [
        "applicable_versions",
        "score",
        "score_kind",
        "source_commit",
        "source_id",
    ]
    assert baseline["missing_analysis_fields"] == [
        "checks_suggested",
        "evidence_links",
        "facts_delta",
        "retrieval_queries",
    ]
    assert receipt["comparison"] == {
        "baseline_complete_source_metadata": False,
        "candidate_complete_source_metadata": True,
        "baseline_complete_analysis": False,
        "candidate_complete_analysis": True,
        "baseline_case_latest_evidence_handoff": False,
        "candidate_case_latest_evidence_handoff": True,
        "baseline_catalog_bound_review_envelope": False,
        "candidate_catalog_bound_review_envelope": True,
    }


def test_catalog_change_is_visible_even_when_analysis_and_legacy_packet_match(receipt):
    probe = next(
        item for item in receipt["probes"] if item["probe"] == "same_analysis_new_source_gap"
    )
    assert probe == {
        "probe": "same_analysis_new_source_gap",
        "analysis_unchanged": True,
        "legacy_packet_unchanged": True,
        "outer_handoff_changes": True,
        "catalog_substitution_rejected": True,
    }
    control = receipt["conflict_routing_control"]
    assert control["control_type"] == "authored_routing_control_not_an_observed_document_conflict"
    assert control["rejected_answer_code"] == "grounded_conflict_unresolved"
    assert {
        link["chunk_id"] for link in control["final_handoff"]["analysis"]["evidence_links"]
    } == {"multiselect-149-signature-v8", "release-150-multiselect-key-identity-v8"}


def test_edit_requires_new_packet_and_rejection_releases_no_draft(receipt):
    probe = next(item for item in receipt["probes"] if item["probe"] == "edited_proposal")
    assert "ReviewPacketMismatch" in probe["old_review_codes"]
    assert probe["old_approval_status"] == 409
    assert probe["rejection_releases_no_draft"]
    assert receipt["final_view"]["pending"] is None
    assert [item["role"] for item in receipt["final_view"]["log"]].count("assistant") == 2


def test_deterministic_replay_restores_all_adapter_and_uuid_state(receipt):
    cases, tracker, adapters, engine_uuid, api_uuid = (
        api._cases,
        api.tracker,
        api._adapters,
        replay.engine_module.uuid4,
        api.uuid4,
    )
    repeated = replay.replay_handoff()
    assert repeated == receipt
    assert api._cases is cases and api.tracker is tracker and api._adapters is adapters
    assert replay.engine_module.uuid4 is engine_uuid and api.uuid4 is api_uuid
    unsigned = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    assert receipt["receipt_sha256"] == replay._digest(unsigned)
    assert set(receipt["executed_code_sha256"]) == set(replay.CODE_PATHS)


def test_fixture_expectations_are_frozen_before_execution(tmp_path):
    fixture = json.loads(replay.FIXTURE_PATH.read_text())
    fixture["turns"][2]["expected"]["active_user_version"] = "1.50.0"
    path = tmp_path / "changed-fixture.json"
    path.write_text(json.dumps(fixture))
    with pytest.raises(ValueError, match="RegisteredHandoffFixtureMismatch"):
        replay.replay_handoff(path)


def test_exclusive_receipt_and_optimized_python_preserve_audit_files(tmp_path, receipt):
    path = tmp_path / "receipt.json"
    replay.write_receipt(path, receipt)
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        replay.write_receipt(path, {"changed": True})
    assert path.read_bytes() == original
    blocked = tmp_path / "disabled-checks.json"
    completed = subprocess.run(
        [sys.executable, "-O", str(REPLAY_PATH), "--output", str(blocked)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2
    assert json.loads(completed.stdout) == {"error_code": "AssertionChecksDisabled"}
    assert not blocked.exists()


def test_source_changed_during_execution_cannot_receive_success_receipt(monkeypatch):
    original = replay.code_manifest
    calls = 0

    def unstable_manifest():
        nonlocal calls
        calls += 1
        manifest = original()
        if calls > 1:
            manifest["src/agent_app/api.py"] = "0" * 64
        return manifest

    monkeypatch.setattr(replay, "code_manifest", unstable_manifest)
    with pytest.raises(RuntimeError, match="CodeChangedDuringReplay"):
        replay.replay_handoff()


def test_valid_handoff_hash_and_citation_cannot_hide_unsupported_added_prose(monkeypatch):
    class UnsupportedClaimReasoner(replay.GroundedReasoner):
        def analyze(self, *args, **kwargs):
            result = super().analyze(*args, **kwargs)
            if result.decision == "answer":
                return result.model_copy(
                    update={
                        "user_draft": result.user_draft + " This proves the exact application fix."
                    }
                )
            return result

    monkeypatch.setattr(replay, "GroundedReasoner", UnsupportedClaimReasoner)
    with pytest.raises(AssertionError, match="Registered rendered output changed"):
        replay.replay_handoff()


def test_old_catalog_and_case_cannot_be_reused_after_correction(monkeypatch):
    original = replay.catalog
    first = None

    def stale_catalog(fixture, case, message, evidence):
        nonlocal first
        prepared = original(fixture, case, message, evidence)
        if first is None:
            first = copy.deepcopy(prepared)
        if case.case_revision == 3:
            return GroundedRequest.model_validate(first.model_dump(mode="json"))
        return prepared

    monkeypatch.setattr(replay, "catalog", stale_catalog)
    with pytest.raises(AssertionError, match="Final proposal was lost"):
        replay.replay_handoff()


def test_shared_renderer_bug_cannot_hide_a_shortened_quote(monkeypatch):
    def broken_source_block(_case, hit):
        return "> " + hit.excerpt.splitlines()[0]

    # Both actual and expected rendering share this mutation. An independent
    # whole-excerpt comparison must still detect it.
    monkeypatch.setattr(grounding, "_source_block", broken_source_block)
    with pytest.raises(AssertionError, match="Whole registered source excerpt missing"):
        replay.replay_handoff()
