"""Core/SQLite failure conformance with authored offline ports.

Recovery checks below are caller-policy examples, not implemented HTTP recovery
or durable scheduling. They exercise the existing contracts without an API,
real retrieval, provider request, production ledger or source-code execution.
"""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from agent_app.contracts import CaseState, ProposalHandoff, ReportedFact, UserTurn
from agent_app.demo import SNAPSHOT_ID, _answer, _evidence
from agent_app.orchestration import SupportEngine
from agent_app.orchestration.handoff import (
    HandoffRejected,
    ReasoningCapture,
    ReasoningFrame,
    build_handoff,
    ensure_handoff_current,
    validate_handoff,
)
from agent_app.testing.fakes import FakeReasoner, FakeRetriever
from agent_app.tracker.sqlite_tracker import SQLiteCaseTracker, TrackerRejected

CASE_ID = "core-tracker-failure-fixture"
MESSAGE = "An authored fixture widget loses its value after rerun."
TOKEN = "offline-conformance-reviewer-token"


def tracker(path):
    return SQLiteCaseTracker(path, reviewer_tokens={"fixture-maintainer": TOKEN})


def event(*, revision=0, event_id="initial", version="1.50.0"):
    return UserTurn(
        case_id=CASE_ID,
        expected_revision=revision,
        turn_id=event_id,
        source_ref=f"user:{event_id}",
        message=MESSAGE,
        reported_facts=(ReportedFact(name="streamlit_version", value=version),),
    )


def run_core(t, reasoner=None, *, retriever=None, state=None, message=MESSAGE):
    state = state if state is not None else CaseState.model_validate(t.read_case(CASE_ID)["state"])
    retriever = (
        retriever
        if retriever is not None
        else FakeRetriever([_evidence("conformance-source", "Authored offline evidence.")])
    )
    capture = ReasoningCapture(
        reasoner if reasoner is not None else FakeReasoner([_answer("conformance-source")])
    )
    result = SupportEngine(
        retriever,
        capture,
        snapshot_id=SNAPSHOT_ID,
        current_revision=lambda case_id: t.read_case(case_id)["state"]["case_revision"],
    ).run(state, message, run_id="conformance-run")
    return result, capture, retriever


def coordinate_fresh_event_example(
    t, incoming, lazy_ports, *, after_commit=None, before_stage=None
):
    """Test-only fresh-event policy; production API/run recovery remains open.

    Replay never constructs ports. A newer committed revision stops before the
    factory, so an old event message cannot run against a different turn's facts.
    Hooks inject interruptions at specific commit boundaries, never source data.
    """
    receipt = t.apply_turn(incoming)
    if receipt["replayed"]:
        return {"status": "replay_only", "receipt": receipt, "snapshot": t.read_case(CASE_ID)}
    if after_commit is not None:
        after_commit(receipt)
    snapshot = t.read_case(CASE_ID)
    state = CaseState.model_validate(snapshot["state"])
    if receipt["committed_revision"] != state.case_revision:
        return {"status": "superseded_before_run", "receipt": receipt, "snapshot": snapshot}
    retriever, reasoner = lazy_ports()
    result, capture, _ = run_core(
        t, reasoner, retriever=retriever, state=state, message=incoming.message
    )
    if result.status != "awaiting_approval":
        return {"status": "core_stopped", "receipt": receipt, "result": result}
    handoff = build_handoff(result, capture.last)
    if before_stage is not None:
        before_stage(handoff)
    t.stage_proposal(handoff)
    return {"status": "proposal_staged", "receipt": receipt, "handoff": handoff}


def approve(t, handoff, *, review_id="approve"):
    return t.review(
        CASE_ID,
        review_id=review_id,
        proposal_id=handoff.proposal_id,
        expected_revision=handoff.case.case_revision,
        expected_handoff_sha256=handoff.handoff_sha256,
        decision="approve",
        reviewer_id="fixture-maintainer",
        reviewer_token=TOKEN,
    )


def read_exact_pending_example(t, expected):
    """Example lost-ack check; no port invocation and no HTTP recovery claim."""
    expected = validate_handoff(expected)
    snapshot = t.read_case(expected.case.case_id)
    state = CaseState.model_validate(snapshot["state"])
    if snapshot["pending_handoff"] is None:
        raise HandoffRejected("PendingProposalMismatch")
    saved = validate_handoff(ProposalHandoff.model_validate(snapshot["pending_handoff"]))
    ensure_handoff_current(saved, state, expected.proposal_id)
    if saved != expected:
        raise HandoffRejected("HandoffMismatch")
    return saved


def test_correction_inside_reasoner_discards_output_using_actual_tracker_revision(tmp_path):
    file = tmp_path / "during-reasoning.db"
    t = tracker(file)
    t.apply_turn(event())
    other_connection = tracker(file)

    class CorrectingReasoner(FakeReasoner):
        def analyze(self, case, user_message, evidence, *, context):
            response = super().analyze(case, user_message, evidence, context=context)
            other_connection.apply_turn(event(revision=1, event_id="correction", version="1.49.1"))
            return response

    result, capture, retriever = run_core(t, CorrectingReasoner([_answer("conformance-source")]))
    assert result.status == "stale"
    assert result.error_code == "StaleRevision"
    assert result.analysis is None
    assert result.model_attempts == result.retrieval_rounds == 1
    assert len(capture.reasoner.inputs) == len(retriever.requests) == 1
    with pytest.raises(HandoffRejected, match="FinalProposalRequired"):
        build_handoff(result, capture.last)
    snapshot = tracker(file).read_case(CASE_ID)
    assert snapshot["state"]["case_revision"] == 2
    assert snapshot["state"]["facts"][-1]["value"] == "1.49.1"
    assert snapshot["pending_handoff"] is None
    assert snapshot["state"]["pending_proposal_id"] is None
    assert t.comments(CASE_ID) == []


def test_correction_after_core_before_staging_rejects_the_finished_old_handoff(tmp_path):
    file = tmp_path / "before-staging.db"
    t = tracker(file)
    t.apply_turn(event())
    result, capture, retriever = run_core(t)
    assert result.status == "awaiting_approval"
    handoff = build_handoff(result, capture.last)
    tracker(file).apply_turn(event(revision=1, event_id="correction", version="1.49.1"))
    with pytest.raises(TrackerRejected, match="StaleRevision"):
        t.stage_proposal(handoff)
    snapshot = tracker(file).read_case(CASE_ID)
    assert snapshot["state"]["case_revision"] == 2
    assert snapshot["pending_handoff"] is None
    assert len(capture.reasoner.inputs) == len(retriever.requests) == 1
    assert [entry["event"] for entry in t.audit_trace(CASE_ID)] == [
        "turn_committed",
        "turn_committed",
    ]
    assert t.comments(CASE_ID) == []


def test_lost_staging_ack_recovers_exact_saved_handoff_without_another_model_call(tmp_path):
    file = tmp_path / "lost-staging-ack.db"
    t = tracker(file)
    t.apply_turn(event())
    result, capture, retriever = run_core(t)
    handoff = build_handoff(result, capture.last)
    with pytest.raises(ConnectionError, match="authored lost staging acknowledgment"):
        t.stage_proposal(handoff)
        # The SQLite commit succeeded; only the caller's acknowledgment is lost.
        raise ConnectionError("authored lost staging acknowledgment")
    reopened = tracker(file)
    with pytest.raises(TrackerRejected, match="PendingProposalMismatch"):
        reopened.stage_proposal(handoff)
    recovered = read_exact_pending_example(reopened, handoff)
    assert recovered == handoff
    assert len(capture.reasoner.inputs) == len(retriever.requests) == 1
    assert reopened.comments(CASE_ID) == []
    assert [entry["event"] for entry in reopened.audit_trace(CASE_ID)] == [
        "turn_committed",
        "proposal_staged",
    ]
    assert approve(reopened, recovered)["status"] == "answer_sent"
    assert len(reopened.comments(CASE_ID)) == 1
    assert len(capture.reasoner.inputs) == len(retriever.requests) == 1


@pytest.mark.parametrize("mismatch", ["proposal_id", "same_id_different_content"])
def test_lost_ack_example_does_not_accept_identity_or_content_mismatch(tmp_path, mismatch):
    t = tracker(tmp_path / "mismatch.db")
    t.apply_turn(event())
    result, capture, retriever = run_core(t)
    saved = build_handoff(result, capture.last)
    t.stage_proposal(saved)
    changed = (
        result.model_copy(update={"run_id": "different-run"})
        if mismatch == "proposal_id"
        else result.model_copy(
            update={
                "analysis": result.analysis.model_copy(
                    update={"user_draft": "A different authored fixture draft."}
                )
            }
        )
    )
    if mismatch == "proposal_id":
        # A distinct valid caller-owned run identity must not recover this run.
        frame = capture.last
        frame = ReasoningFrame(
            frame.case,
            frame.user_message,
            frame.evidence,
            frame.context.model_copy(update={"run_id": "different-run"}),
        )
    else:
        frame = capture.last
    expected = build_handoff(changed, frame)
    assert expected.handoff_sha256 != saved.handoff_sha256
    code = "PendingProposalMismatch" if mismatch == "proposal_id" else "HandoffMismatch"
    with pytest.raises(HandoffRejected, match=code):
        read_exact_pending_example(t, expected)
    assert ProposalHandoff.model_validate(t.read_case(CASE_ID)["pending_handoff"]) == saved
    assert t.comments(CASE_ID) == []
    assert len(capture.reasoner.inputs) == len(retriever.requests) == 1


def test_interruption_after_ingress_commit_replays_a_receipt_without_a_pending_run(tmp_path):
    """A committed event alone does not prove a model run or pending proposal."""
    file = tmp_path / "ingress-interruption.db"
    t = tracker(file)
    incoming = event()
    receipts = []
    constructed = []

    def bomb_factory():
        constructed.append(True)
        raise AssertionError("No adapter may be constructed for the interrupted event replay.")

    def interrupt(receipt):
        receipts.append(receipt)
        raise InterruptedError("authored interruption before reasoning")

    with pytest.raises(InterruptedError, match="authored interruption before reasoning"):
        coordinate_fresh_event_example(t, incoming, bomb_factory, after_commit=interrupt)
    reopened = tracker(file)
    replay = coordinate_fresh_event_example(reopened, incoming, bomb_factory)
    assert replay["status"] == "replay_only"
    assert replay["receipt"] == {**receipts[0], "replayed": True}
    snapshot = replay["snapshot"]
    assert snapshot["state"]["case_revision"] == 1
    assert snapshot["status"] == "open"
    assert snapshot["pending_handoff"] is None
    assert snapshot["state"]["pending_proposal_id"] is None
    assert [entry["actor"] for entry in snapshot["history"]] == ["user"]
    assert reopened.comments(CASE_ID) == []
    assert constructed == []
    # The example stops here. An API integration still needs an explicit
    # durable run-recovery policy; receipt replay must not imply model success.


def test_fresh_receipt_superseded_before_authoritative_read_stops_before_factory(tmp_path):
    file = tmp_path / "after-commit-before-read.db"
    t = tracker(file)
    other_connection = tracker(file)
    constructed = []

    def bomb_factory():
        constructed.append(True)
        raise AssertionError("Superseded ingress must not construct adapters.")

    def correction_after_commit(receipt):
        assert receipt["committed_revision"] == 1
        other_connection.apply_turn(event(revision=1, event_id="correction", version="1.49.1"))

    outcome = coordinate_fresh_event_example(
        t, event(), bomb_factory, after_commit=correction_after_commit
    )
    assert outcome["status"] == "superseded_before_run"
    assert outcome["receipt"]["replayed"] is False
    assert outcome["receipt"]["committed_revision"] == 1
    assert outcome["snapshot"]["state"]["case_revision"] == 2
    assert outcome["snapshot"]["state"]["facts"][-1]["value"] == "1.49.1"
    assert outcome["snapshot"]["pending_handoff"] is None
    assert constructed == []
    assert t.comments(CASE_ID) == []


def test_interruption_after_core_before_staging_does_not_rerun_on_event_replay(tmp_path):
    file = tmp_path / "after-core-before-stage.db"
    t = tracker(file)
    incoming = event()
    retriever = FakeRetriever([_evidence("conformance-source", "Authored offline evidence.")])
    reasoner = FakeReasoner([_answer("conformance-source")])
    constructed = []
    finished = []

    def ports():
        constructed.append(True)
        return retriever, reasoner

    def interrupt(handoff):
        finished.append(validate_handoff(handoff))
        raise InterruptedError("authored interruption after core before staging")

    with pytest.raises(InterruptedError, match="authored interruption after core before staging"):
        coordinate_fresh_event_example(t, incoming, ports, before_stage=interrupt)
    assert len(constructed) == len(finished) == 1
    assert len(retriever.requests) == len(reasoner.inputs) == 1
    assert finished[0].case.case_revision == 1

    def bomb_factory():
        raise AssertionError("Replay must not repeat the finished but unpersisted core run.")

    replay = coordinate_fresh_event_example(tracker(file), incoming, bomb_factory)
    assert replay["status"] == "replay_only"
    assert replay["receipt"]["replayed"] is True
    assert replay["snapshot"]["state"]["case_revision"] == 1
    assert replay["snapshot"]["pending_handoff"] is None
    assert [entry["actor"] for entry in replay["snapshot"]["history"]] == ["user"]
    assert t.comments(CASE_ID) == []
    assert len(t.audit_trace(CASE_ID)) == 1
    assert len(retriever.requests) == len(reasoner.inputs) == 1


def test_failure_after_comment_insert_rolls_back_then_same_review_can_retry(tmp_path, monkeypatch):
    file = tmp_path / "after-insert.db"
    t = tracker(file)
    t.apply_turn(event())
    result, capture, retriever = run_core(t)
    handoff = build_handoff(result, capture.last)
    t.stage_proposal(handoff)
    before = t.read_case(CASE_ID)
    audit_before = t.audit_trace(CASE_ID)
    inserted = []
    original_tool = SQLiteCaseTracker._record_local_comment

    def fail_after_insert(db, **kwargs):
        action_id = original_tool(db, **kwargs)
        assert db.execute("SELECT count(*) FROM local_comments").fetchone()[0] == 1
        inserted.append(action_id)
        raise RuntimeError("authored failure after local INSERT")

    monkeypatch.setattr(t, "_record_local_comment", fail_after_insert)
    with pytest.raises(RuntimeError, match="authored failure after local INSERT"):
        approve(t, handoff, review_id="retry-after-insert")
    reopened = tracker(file)
    assert len(inserted) == 1
    assert reopened.read_case(CASE_ID) == before
    assert reopened.comments(CASE_ID) == []
    assert reopened.audit_trace(CASE_ID) == audit_before
    with sqlite3.connect(file) as db:
        assert db.execute("SELECT count(*) FROM reviews").fetchone()[0] == 0
    done = approve(reopened, handoff, review_id="retry-after-insert")
    assert done["replayed"] is False
    assert done["action_id"] == inserted[0]
    assert approve(tracker(file), handoff, review_id="retry-after-insert")["replayed"] is True
    assert len(reopened.comments(CASE_ID)) == 1
    assert len(capture.reasoner.inputs) == len(retriever.requests) == 1


def test_concurrent_identical_events_have_one_fresh_receipt_after_barrier(tmp_path):
    file = tmp_path / "concurrent-event.db"
    first, second = tracker(file), tracker(file)
    incoming = event()
    gate = Barrier(2)

    def apply(t):
        gate.wait(timeout=10)
        return t.apply_turn(incoming)

    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts = list(pool.map(apply, (first, second)))
    assert sorted(receipt["replayed"] for receipt in receipts) == [False, True]
    assert {name: value for name, value in receipts[0].items() if name != "replayed"} == {
        name: value for name, value in receipts[1].items() if name != "replayed"
    }
    snapshot = tracker(file).read_case(CASE_ID)
    assert snapshot["state"]["case_revision"] == 1
    assert len(snapshot["history"]) == 1
    assert snapshot["history"][0]["reference_id"] == incoming.turn_id
    assert snapshot["pending_handoff"] is None
    assert len(first.audit_trace(CASE_ID)) == 1


def test_concurrent_identical_reviews_have_one_action_and_one_replay_after_barrier(tmp_path):
    file = tmp_path / "concurrent-review.db"
    t = tracker(file)
    t.apply_turn(event())
    result, capture, retriever = run_core(t)
    handoff = build_handoff(result, capture.last)
    t.stage_proposal(handoff)
    first, second = tracker(file), tracker(file)
    gate = Barrier(2)

    def review_after_gate(t):
        gate.wait(timeout=10)
        return approve(t, handoff, review_id="same-concurrent-review")

    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts = list(pool.map(review_after_gate, (first, second)))
    assert sorted(receipt["replayed"] for receipt in receipts) == [False, True]
    assert receipts[0]["action_id"] == receipts[1]["action_id"]
    assert len(t.comments(CASE_ID)) == 1
    assert [entry["actor"] for entry in t.read_case(CASE_ID)["history"]] == ["user", "assistant"]
    assert len(t.audit_trace(CASE_ID)) == 3
    assert len(capture.reasoner.inputs) == len(retriever.requests) == 1
