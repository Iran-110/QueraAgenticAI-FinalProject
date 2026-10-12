"""Durable HTTP metadata shares the existing tracker transactions and snapshots."""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from agent_app.contracts import AnalysisResult, CaseState, ReportedFact, RunResult, UserTurn
from agent_app.demo import SNAPSHOT_ID, _answer, _evidence
from agent_app.orchestration import SupportEngine
from agent_app.orchestration.handoff import ReasoningCapture, build_handoff
from agent_app.orchestration.intake import STREAMLIT_VERSION_QUESTION
from agent_app.orchestration.service import CoreTurnService
from agent_app.testing.fakes import FakeReasoner, FakeRetriever
from agent_app.tracker.sqlite_tracker import SQLiteCaseTracker, TrackerRejected

CASE = "runtime-fixture"
TOKEN = "offline-runtime-review-token"
PRIVATE = "PRIVATE_RUNTIME_ERROR_DIAGNOSTIC"
MESSAGE = "The multiselect loses its default after the parent selector changes."


def tracker(path, cls=SQLiteCaseTracker):
    return cls(path, reviewer_tokens={"maintainer": TOKEN})


def turn(revision=0, turn_id="initial", version=None):
    return UserTurn(
        case_id=CASE,
        expected_revision=revision,
        turn_id=turn_id,
        source_ref=f"user:{turn_id}",
        message=MESSAGE,
        reported_facts=(ReportedFact(name="streamlit_version", value=version),) if version else (),
    )


def proposal(t, analysis=None):
    state = CaseState.model_validate(t.read_case(CASE)["state"])
    capture = ReasoningCapture(FakeReasoner([analysis or _answer("runtime-source")]))
    result = SupportEngine(
        FakeRetriever([_evidence("runtime-source", "Authored offline Streamlit source.")]),
        capture,
        snapshot_id=SNAPSHOT_ID,
    ).run(state, MESSAGE)
    assert result.status == "awaiting_approval"
    return build_handoff(result, capture.last), result


def review(t, handoff, decision="approve", review_id="review-1", **extra):
    return t.review(
        CASE,
        review_id=review_id,
        proposal_id=handoff.proposal_id,
        expected_revision=handoff.case.case_revision,
        expected_handoff_sha256=handoff.handoff_sha256,
        decision=decision,
        reviewer_id="maintainer",
        reviewer_token=TOKEN,
        **extra,
    )


def stored_rows(path):
    with sqlite3.connect(path) as db:
        return {
            table: db.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
            for table in (
                "cases",
                "events",
                "proposals",
                "reviews",
                "local_comments",
                "conversation",
                "audit",
            )
        }


def test_ingress_atomically_records_interruption_and_replay_never_runs_model(tmp_path):
    path = tmp_path / "interrupted.db"
    t = tracker(path)
    original = turn()
    receipt = t.apply_turn(original)
    saved = t.read_runtime_view(CASE)
    assert saved["intake"] == receipt
    assert saved["run_outcome"] == {
        "status": "interrupted",
        "error_code": "RunInterrupted",
        "result": None,
    }
    assert saved["pending_result"] is None and saved["actions"] == []
    assert "no run outcome is recorded" in saved["log"][-1]["text"]
    calls = []

    def forbidden(*args):
        calls.append(args)
        raise AssertionError("Interrupted ingress must not resume reasoning")

    restarted = tracker(path)
    assert restarted.read_runtime_view(CASE) == saved
    replay = CoreTurnService(restarted, forbidden).submit(original)
    assert replay.status == "replay_only" and replay.receipt.replayed
    assert calls == [] and restarted.read_runtime_view(CASE) == saved


def test_failed_ingress_rolls_back_placeholder_and_event_together(tmp_path):
    class Failure(SQLiteCaseTracker):
        @staticmethod
        def _audit(db, case_id, event, data):
            SQLiteCaseTracker._audit(db, case_id, event, data)
            if event == "turn_committed":
                raise RuntimeError(PRIVATE)

    path = tmp_path / "ingress-rollback.db"
    with pytest.raises(RuntimeError, match=PRIVATE):
        tracker(path, Failure).apply_turn(turn())
    saved = tracker(path).read_runtime_view(CASE)
    assert saved["view"]["state"]["case_revision"] == 0
    assert saved["intake"] is saved["run_outcome"] is None
    assert saved["log"] == []
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT count(*) FROM events").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM run_outcomes").fetchone()[0] == 0


def test_staged_handoff_and_measured_result_survive_restart(tmp_path):
    path = tmp_path / "staged.db"
    t = tracker(path)
    t.apply_turn(turn())
    handoff, result = proposal(t)
    receipt = t.stage_run_proposal(handoff, result, "initial")
    assert receipt == {"case_id": CASE, "proposal_id": result.run_id, "revision": 1}
    saved = tracker(path).read_runtime_view(CASE)
    assert saved["view"] == t.read_case(CASE)
    assert saved["view"]["pending_handoff"] == handoff.model_dump(mode="json")
    assert saved["pending_result"] == result.model_dump(mode="json")
    assert saved["run_outcome"] == {
        "status": "proposal_staged",
        "error_code": None,
        "result": result.model_dump(mode="json"),
    }
    assert saved["log"] == [{"role": "user", "text": MESSAGE}]
    assert saved["pending_edited_from"] is None
    assert saved["decisions"] == saved["actions"] == []
    assert saved["review"] is None
    assert set(saved["view"]) == {"state", "history", "status", "pending_handoff", "awaiting_reply"}


def test_run_metadata_failure_rolls_back_proposal_and_case_changes(tmp_path):
    class Failure(SQLiteCaseTracker):
        @staticmethod
        def _write_run_outcome(*args, **kwargs):
            SQLiteCaseTracker._write_run_outcome(*args, **kwargs)
            raise RuntimeError(PRIVATE)

    path = tmp_path / "stage-rollback.db"
    t = tracker(path, Failure)
    t.apply_turn(turn())
    before = t.read_runtime_view(CASE)
    handoff, result = proposal(t)
    with pytest.raises(RuntimeError, match=PRIVATE):
        t.stage_run_proposal(handoff, result, "initial")
    reopened = tracker(path)
    assert reopened.read_runtime_view(CASE) == before
    assert [entry["event"] for entry in reopened.audit_trace(CASE)] == ["turn_committed"]
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT count(*) FROM proposals").fetchone()[0] == 0
    reopened.stage_run_proposal(handoff, result, "initial")
    assert reopened.read_case(CASE)["status"] == "awaiting_review"


@pytest.mark.parametrize(
    "changed",
    [
        {"case_id": "another-case"},
        {"case_revision": 2},
        {"run_id": "another-run"},
        {"analysis": _answer("another-source")},
        {"model_attempts": 2},
        {"retrieval_rounds": 2},
        {"steps": 9},
        {"status": "error", "analysis": None, "error_code": "ModelOutputInvalid"},
        {"private_runtime_field": PRIVATE},
    ],
)
def test_stage_requires_exact_run_case_revision_and_analysis(tmp_path, changed):
    t = tracker(tmp_path / "invalid-result.db")
    t.apply_turn(turn())
    handoff, result = proposal(t)
    before = t.read_runtime_view(CASE)
    malformed = result.model_copy(update=changed)
    with pytest.raises(TrackerRejected, match="^RunResultInvalid$"):
        t.stage_run_proposal(handoff, malformed, "initial")
    assert t.read_runtime_view(CASE) == before


def test_stage_result_must_bind_to_existing_same_revision_event(tmp_path):
    t = tracker(tmp_path / "missing-event.db")
    t.apply_turn(turn())
    handoff, result = proposal(t)
    with pytest.raises(TrackerRejected, match="^RunOutcomeMissing$"):
        t.stage_run_proposal(handoff, result, "another-event")
    assert t.read_case(CASE)["pending_handoff"] is None


def test_terminal_outcome_is_idempotent_across_restart_and_conflict_safe(tmp_path):
    path = tmp_path / "terminal.db"
    t = tracker(path)
    original = turn()
    t.apply_turn(original)
    finished = t.finish_run(CASE, "initial", status="core_stopped", error_code="AdapterSetupFailed")
    before = t.read_runtime_view(CASE)
    restarted = tracker(path)
    assert restarted.apply_turn(original)["replayed"]
    assert (
        restarted.finish_run(
            CASE, "initial", status="core_stopped", error_code="AdapterSetupFailed"
        )
        == finished
    )
    assert restarted.read_runtime_view(CASE) == before
    with pytest.raises(TrackerRejected, match="^RunOutcomeConflict$"):
        restarted.finish_run(CASE, "initial", status="core_stopped", error_code="CoreRunFailed")
    assert restarted.read_runtime_view(CASE) == before
    assert [entry["event"] for entry in restarted.audit_trace(CASE)] == [
        "turn_committed",
        "run_finished",
    ]


def test_completed_proposal_outcome_cannot_be_overwritten_by_failure(tmp_path):
    t = tracker(tmp_path / "completed.db")
    t.apply_turn(turn())
    handoff, result = proposal(t)
    t.stage_run_proposal(handoff, result, "initial")
    before = t.read_runtime_view(CASE)
    with pytest.raises(TrackerRejected, match="^RunOutcomeConflict$"):
        t.finish_run(CASE, "initial", status="core_stopped", error_code="CoreRunFailed")
    with pytest.raises(TrackerRejected, match="^RunOutcomeConflict$"):
        t.stage_run_proposal(handoff, result, "initial")
    assert t.read_runtime_view(CASE) == before


def test_unknown_diagnostics_are_normalized_without_losing_measured_counts(tmp_path):
    path = tmp_path / "safe-error.db"
    t = tracker(path)
    t.apply_turn(turn())
    result = RunResult(
        run_id="offline-failed-run",
        case_id=CASE,
        case_revision=1,
        status="error",
        error_code=PRIVATE,
        model_attempts=1,
        retrieval_rounds=1,
        steps=3,
    )
    finished = t.finish_run(
        CASE, "initial", status="core_stopped", error_code=PRIVATE, run_result=result
    )
    assert finished["error_code"] == finished["result"]["error_code"] == "RunOutcomeUnavailable"
    assert finished["result"]["model_attempts"] == finished["result"]["retrieval_rounds"] == 1
    assert finished["result"]["steps"] == 3
    assert PRIVATE not in json.dumps(t.read_runtime_view(CASE))
    assert PRIVATE.encode() not in path.read_bytes()


@pytest.mark.parametrize("status", ["proposal_staged", "interrupted", PRIVATE, None])
def test_finish_accepts_only_terminal_outcome_statuses(tmp_path, status):
    t = tracker(tmp_path / "status.db")
    t.apply_turn(turn())
    before = t.read_runtime_view(CASE)
    with pytest.raises(TrackerRejected, match="^RunOutcomeUnavailable$"):
        t.finish_run(CASE, "initial", status=status, error_code=PRIVATE)
    assert t.read_runtime_view(CASE) == before


def test_terminal_failure_storage_is_transactional(tmp_path):
    class Failure(SQLiteCaseTracker):
        @staticmethod
        def _audit(db, case_id, event, data):
            SQLiteCaseTracker._audit(db, case_id, event, data)
            if event == "run_finished":
                raise RuntimeError(PRIVATE)

    path = tmp_path / "finish-rollback.db"
    t = tracker(path, Failure)
    t.apply_turn(turn())
    before = t.read_runtime_view(CASE)
    with pytest.raises(RuntimeError, match=PRIVATE):
        t.finish_run(CASE, "initial", status="core_stopped", error_code="AdapterSetupFailed")
    assert tracker(path).read_runtime_view(CASE) == before


@pytest.mark.parametrize("decision", ["approve", "reject"])
def test_same_revision_closed_lifecycle_cannot_stage_second_root_proposal(tmp_path, decision):
    t = tracker(tmp_path / "aba.db")
    t.apply_turn(turn())
    initial_state = t.read_case(CASE)["state"]
    first, result = proposal(t)
    t.stage_run_proposal(first, result, "initial")
    review(t, first, decision)
    assert t.read_case(CASE)["state"] == initial_state
    second, _ = proposal(t)
    assert second.proposal_id != first.proposal_id
    before = t.read_runtime_view(CASE)
    with pytest.raises(TrackerRejected, match="^(ProposalConflict|PendingProposalMismatch)$"):
        t.stage_proposal(second)
    assert t.read_runtime_view(CASE) == before
    assert len(t.comments(CASE)) == int(decision == "approve")


def test_new_user_revision_can_stage_after_prior_rejection(tmp_path):
    t = tracker(tmp_path / "new-lifecycle.db")
    t.apply_turn(turn())
    first, result = proposal(t)
    t.stage_run_proposal(first, result, "initial")
    review(t, first, "reject")
    t.apply_turn(turn(revision=1, turn_id="next"))
    second, result = proposal(t)
    t.stage_run_proposal(second, result, "next")
    assert t.read_case(CASE)["pending_handoff"]["proposal_id"] == second.proposal_id


def test_edit_projection_keeps_measured_original_run_and_releases_only_actual_draft(tmp_path):
    path = tmp_path / "edit.db"
    t = tracker(path)
    t.apply_turn(turn())
    first, result = proposal(t)
    t.stage_run_proposal(first, result, "initial")
    edited = review(t, first, "edit", edited_draft="Reviewed local answer.", review_id="edit")
    snapshot = tracker(path).read_runtime_view(CASE)
    pending = snapshot["view"]["pending_handoff"]
    assert pending["proposal_id"] == edited["new_proposal_id"]
    assert snapshot["pending_edited_from"] == first.proposal_id
    assert snapshot["pending_result"] == result.model_dump(mode="json")
    assert snapshot["review"] == edited and not snapshot["review"]["replayed"]
    assert snapshot["actions"] == []
    assert snapshot["log"][-1] == {
        "role": "system",
        "text": "The maintainer edited the draft. It needs approval.",
    }
    new = type(first).model_validate(pending)
    approved = review(t, new, review_id="edited-approval")
    after = tracker(path).read_runtime_view(CASE)
    assert after["review"] == approved
    assert after["pending_result"] is after["pending_edited_from"] is None
    assert after["log"][-1] == {
        "role": "assistant",
        "text": "Reviewed local answer.",
        "decision": "answer",
        "edited": True,
    }
    assert len(after["actions"]) == 1 and after["actions"][0]["body"] == "Reviewed local answer."
    assert [entry["decision"] for entry in after["decisions"]] == ["edit", "approve"]
    assert after["decisions"][-1]["action"]["review_handoff"] == pending
    assert review(tracker(path), new, review_id="edited-approval")["replayed"]
    assert tracker(path).read_runtime_view(CASE) == after


def test_approved_canonical_question_and_review_receipt_recover_without_projection_memory(tmp_path):
    path = tmp_path / "question.db"
    t = tracker(path)
    t.apply_turn(turn())
    question = STREAMLIT_VERSION_QUESTION.question
    analysis = AnalysisResult(
        decision="ask",
        user_draft=question,
        next_question=question,
        missing_info=("streamlit_version",),
        maintainer_summary="Version unknown.",
        rationale="Version determines applicability.",
    )
    handoff, result = proposal(t, analysis)
    t.stage_run_proposal(handoff, result, "initial")
    approved = review(t, handoff)
    saved = tracker(path).read_runtime_view(CASE)
    assert saved["view"]["awaiting_reply"]["proposal_id"] == handoff.proposal_id
    assert saved["view"]["awaiting_reply"]["question"] == analysis.model_dump(mode="json")
    assert saved["review"] == approved
    assert saved["log"][-1] == {
        "role": "assistant",
        "text": question,
        "decision": "ask",
        "edited": False,
    }


def test_runtime_projection_remains_one_snapshot_during_correction(tmp_path):
    path = tmp_path / "snapshot.db"
    writer = tracker(path)
    initial = writer.apply_turn(turn(version="1.50.0"))
    handoff, result = proposal(writer)
    writer.stage_run_proposal(handoff, result, "initial")
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    corrections = []

    class ConcurrentReader(SQLiteCaseTracker):
        def _read_case(self, db, case_id):
            snapshot = super()._read_case(db, case_id)
            if not corrections:
                corrections.append(writer.apply_turn(turn(1, "correction", "1.49.1")))
            return snapshot

    saved = tracker(path, ConcurrentReader).read_runtime_view(CASE)
    assert saved["view"]["state"]["case_revision"] == 1
    assert saved["view"]["pending_handoff"] == handoff.model_dump(mode="json")
    assert saved["intake"] == initial
    assert saved["run_outcome"]["status"] == "proposal_staged"
    assert saved["pending_result"] == result.model_dump(mode="json")
    assert saved["log"] == [{"role": "user", "text": MESSAGE}]
    assert corrections[0]["committed_revision"] == 2
    current = writer.read_runtime_view(CASE)
    assert current["view"]["state"]["case_revision"] == 2
    assert current["view"]["pending_handoff"] is current["pending_result"] is None
    assert current["intake"] == corrections[0]
    assert current["run_outcome"]["status"] == "interrupted"


def test_schema_upgrade_preserves_old_cases_actions_events_and_review_receipts(tmp_path):
    path = tmp_path / "old-schema.db"
    t = tracker(path)
    original = turn()
    receipt = t.apply_turn(original)
    handoff, _ = proposal(t)
    t.stage_proposal(handoff)
    approval = review(t, handoff)
    before = stored_rows(path)
    with sqlite3.connect(path) as db:
        db.execute("DROP TABLE run_outcomes")  # Simulate the pre-runtime tracker schema.
    upgraded = tracker(path)
    assert stored_rows(path) == before
    assert upgraded.apply_turn(original) == {**receipt, "replayed": True}
    assert review(upgraded, handoff) == {**approval, "replayed": True}
    assert stored_rows(path) == before
    runtime = upgraded.read_runtime_view(CASE)
    assert runtime["run_outcome"] is runtime["pending_result"] is None
    assert runtime["intake"] == receipt and runtime["review"] == approval
    assert runtime["log"][-1]["text"] == handoff.analysis.user_draft
    assert len(runtime["actions"]) == 1
    upgraded.apply_turn(turn(1, "after-upgrade"))
    assert upgraded.read_runtime_view(CASE)["run_outcome"]["status"] == "interrupted"


def test_runtime_actions_and_review_receipt_share_case_read_snapshot(tmp_path):
    path = tmp_path / "review-snapshot.db"
    writer = tracker(path)
    first_intake = writer.apply_turn(turn())
    first, result = proposal(writer)
    writer.stage_run_proposal(first, result, "initial")
    first_review = review(writer, first)
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    changes = []

    class ConcurrentReader(SQLiteCaseTracker):
        def _read_case(self, db, case_id):
            saved = super()._read_case(db, case_id)
            if not changes:
                changes.append(writer.apply_turn(turn(1, "next")))
                second, result = proposal(writer)
                writer.stage_run_proposal(second, result, "next")
                changes.append(review(writer, second, review_id="review-2"))
            return saved

    saved = tracker(path, ConcurrentReader).read_runtime_view(CASE)
    assert saved["view"]["state"]["case_revision"] == 1
    assert saved["intake"] == first_intake and saved["review"] == first_review
    assert len(saved["actions"]) == len(saved["decisions"]) == 1
    assert saved["actions"][0]["proposal_id"] == first.proposal_id
    assert len([row for row in saved["log"] if row["role"] == "assistant"]) == 1
    current = writer.read_runtime_view(CASE)
    assert current["view"]["state"]["case_revision"] == 2
    assert current["intake"] == changes[0] and current["review"] == changes[1]
    assert len(current["actions"]) == len(current["decisions"]) == 2


def test_concurrent_equal_terminal_recording_commits_one_outcome_and_audit(tmp_path):
    path = tmp_path / "finish-race.db"
    t = tracker(path)
    t.apply_turn(turn())

    def finish(_):
        return tracker(path).finish_run(
            CASE, "initial", status="core_stopped", error_code="AdapterSetupFailed"
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(finish, (1, 2)))
    assert outcomes[0] == outcomes[1]
    assert len([row for row in t.audit_trace(CASE) if row["event"] == "run_finished"]) == 1


def test_explicit_reset_clears_runtime_outcomes_with_old_tracker_tables(tmp_path):
    path = tmp_path / "reset.db"
    t = tracker(path)
    t.apply_turn(turn())
    t.finish_run(CASE, "initial", status="core_stopped", error_code="AdapterSetupFailed")
    t.reset_all(confirmation="RESET LOCAL TRACKER")
    saved = tracker(path).read_runtime_view(CASE)
    assert saved["intake"] is saved["review"] is saved["run_outcome"] is None
    assert saved["log"] == saved["actions"] == saved["decisions"] == []
    assert t.apply_turn(turn())["committed_revision"] == 1
