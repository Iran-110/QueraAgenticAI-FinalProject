"""T1–T4 persistence, atomic review, and idempotency regressions (no paid API)."""

import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from agent_app.contracts import (
    AnalysisResult,
    CaseState,
    EvidenceBundle,
    ProposalHandoff,
    ReportedFact,
    UserTurn,
)
from agent_app.demo import SNAPSHOT_ID, _answer, _ask, _evidence
from agent_app.orchestration import SupportEngine
from agent_app.orchestration.handoff import ReasoningCapture, build_handoff
from agent_app.orchestration.intake import STREAMLIT_VERSION_QUESTION
from agent_app.testing.fakes import FakeReasoner, FakeRetriever
from agent_app.tracker.sqlite_tracker import SQLiteCaseTracker, TrackerRejected

TOKEN = "test-only-unique-reviewer-credential"


def tracker(path):
    return SQLiteCaseTracker(path, reviewer_tokens={"maintainer": TOKEN})


def turn(case="case-a", revision=0, turn_id="event-1", version=None, **kwargs):
    return UserTurn(
        case_id=case,
        expected_revision=revision,
        turn_id=turn_id,
        source_ref=f"user:{turn_id}",
        message="My Streamlit widget loses its value.",
        reported_facts=(ReportedFact(name="streamlit_version", value=version),)
        if version is not None
        else (),
        **kwargs,
    )


def stage(t, case="case-a", decision="answer", override_analysis=None):
    state = CaseState.model_validate(t.read_case(case)["state"])
    analysis = override_analysis or (_answer("demo-initial") if decision == "answer" else _ask())
    capture = ReasoningCapture(FakeReasoner([analysis]))
    engine = SupportEngine(
        FakeRetriever([_evidence("demo-initial", "Synthetic Streamlit evidence.")]),
        capture,
        snapshot_id=SNAPSHOT_ID,
    )
    result = engine.run(state, "My Streamlit widget loses its value.")
    assert result.status == "awaiting_approval"
    handoff = build_handoff(result, capture.last)
    t.stage_proposal(handoff)
    return handoff


def review(t, handoff, decision="approve", *, review_id="review-1", **kwargs):
    return t.review(
        handoff.case.case_id,
        review_id=review_id,
        proposal_id=handoff.proposal_id,
        expected_revision=handoff.case.case_revision,
        expected_handoff_sha256=handoff.handoff_sha256,
        decision=decision,
        reviewer_id="maintainer",
        reviewer_token=TOKEN,
        **kwargs,
    )


def test_persistence_pending_history_actions_and_restart(tmp_path):
    file = tmp_path / "tracker.sqlite3"
    t = tracker(file)
    receipt = t.apply_turn(turn(version="1.49.0", checks_performed=("Reinstalled Streamlit",)))
    assert receipt["committed_revision"] == 1
    h = stage(t)
    after_restart = tracker(file)
    before = after_restart.read_case("case-a")
    assert before["state"]["case_revision"] == 1
    assert [entry["actor"] for entry in before["history"]] == ["user"]
    assert before["state"]["facts"][0]["value"] == "1.49.0"
    assert before["state"]["checks_performed"] == ["Reinstalled Streamlit"]
    assert before["pending_handoff"]["handoff_sha256"] == h.handoff_sha256
    done = review(after_restart, h)
    assert done["status"] == "answer_sent"
    assert len(tracker(file).comments("case-a")) == 1
    assert [entry["actor"] for entry in tracker(file).read_case("case-a")["history"]] == [
        "user",
        "assistant",
    ]
    assert tracker(file).read_case("case-a")["pending_handoff"] is None
    assert len(tracker(file).audit_trace("case-a")) == 3


def test_event_replay_checks_original_identity_before_stale_revision(tmp_path):
    t = tracker(tmp_path / "events.db")
    original = turn(version="1.49.0")
    first = t.apply_turn(original, event_context={"scenario": "answer"})
    replay = t.apply_turn(original, event_context={"scenario": "answer"})
    assert replay["replayed"] and replay["committed_revision"] == first["committed_revision"]
    assert t.read_case("case-a")["state"]["case_revision"] == 1
    assert len(t.read_case("case-a")["history"]) == 1
    with pytest.raises(TrackerRejected, match="EventConflict"):
        t.apply_turn(original, event_context={"scenario": "ask"})
    with pytest.raises(TrackerRejected, match="StaleRevision"):
        t.apply_turn(turn(turn_id="other", revision=0))


def test_correction_invalidates_old_approval_atomically(tmp_path):
    t = tracker(tmp_path / "correction.db")
    t.apply_turn(turn(version="1.49.0"))
    old = stage(t)
    next_turn = turn(revision=1, turn_id="correction", version="1.50.0")
    updated = t.apply_turn(next_turn)
    assert updated["committed_revision"] == 2
    state = t.read_case("case-a")["state"]
    assert state["pending_proposal_id"] is None
    assert [f["status"] for f in state["facts"]] == ["superseded", "active"]
    with pytest.raises(TrackerRejected, match="StaleRevision"):
        review(t, old)
    assert t.comments("case-a") == []
    # Same event replay does not rebuild a stale proposal or increment revision.
    assert t.apply_turn(next_turn)["replayed"] is True
    stage(t)


def test_reviewer_authentication_and_exact_proposal(tmp_path):
    t = tracker(tmp_path / "permission.db")
    t.apply_turn(turn())
    h = stage(t)
    with pytest.raises(TrackerRejected, match="ReviewerUnauthorized"):
        t.review(
            "case-a",
            review_id="x",
            proposal_id=h.proposal_id,
            expected_revision=1,
            expected_handoff_sha256=h.handoff_sha256,
            decision="approve",
            reviewer_id="maintainer",
            reviewer_token="incorrect",
        )
    with pytest.raises(TrackerRejected, match="PendingProposalMismatch"):
        t.review(
            "case-a",
            review_id="x",
            proposal_id="different",
            expected_revision=1,
            expected_handoff_sha256=h.handoff_sha256,
            decision="approve",
            reviewer_id="maintainer",
            reviewer_token=TOKEN,
        )
    assert t.comments("case-a") == []
    assert TOKEN not in str(t.audit_trace("case-a"))


def test_approve_once_retry_same_review_id_and_reject_other_review(tmp_path):
    file = tmp_path / "once.db"
    t = tracker(file)
    t.apply_turn(turn())
    h = stage(t)
    first = review(t, h)
    replay = review(tracker(file), h)
    assert replay["replayed"] is True
    assert replay["action_id"] == first["action_id"]
    with pytest.raises(TrackerRejected, match="PendingProposalMismatch"):
        review(t, h, review_id="second-review")
    assert len(t.comments("case-a")) == 1
    with pytest.raises(TrackerRejected, match="ReviewConflict"):
        review(t, h, decision="reject")


def test_reject_never_writes_local_comment(tmp_path):
    t = tracker(tmp_path / "reject.db")
    t.apply_turn(turn())
    h = stage(t)
    receipt = review(t, h, decision="reject")
    assert receipt["status"] == "open"
    assert receipt["action_id"] is None
    assert t.comments("case-a") == []
    with pytest.raises(TrackerRejected, match="PendingProposalMismatch"):
        review(t, h, review_id="another")


def test_edit_creates_new_identity_new_approval(tmp_path):
    file = tmp_path / "edit.db"
    t = tracker(file)
    t.apply_turn(turn())
    first = stage(t, decision="ask")
    edit = review(t, first, decision="edit", edited_draft="Which version?", review_id="edit-1")
    new_id = edit["new_proposal_id"]
    assert new_id and new_id != first.proposal_id
    assert t.comments("case-a") == []
    assert t.read_case("case-a")["pending_handoff"]["analysis"]["user_draft"] == "Which version?"
    with pytest.raises(TrackerRejected, match="PendingProposalMismatch"):
        review(t, first, review_id="old-approve")
    new = t.read_case("case-a")["pending_handoff"]
    assert new["reasoning_context"]["run_id"] == first.reasoning_context.run_id
    assert new["handoff_sha256"] != first.handoff_sha256
    # Approval with edited proposal identity succeeds exactly once after restart.
    done = t.review(
        "case-a",
        review_id="approve-edited",
        proposal_id=new_id,
        expected_revision=1,
        expected_handoff_sha256=new["handoff_sha256"],
        decision="approve",
        reviewer_id="maintainer",
        reviewer_token=TOKEN,
    )
    assert done["status"] == "awaiting_user"
    assert len(tracker(file).comments("case-a")) == 1


def test_two_cases_are_isolated_even_same_event_id(tmp_path):
    t = tracker(tmp_path / "cases.db")
    t.apply_turn(turn(case="case-a", version="1.49"))
    t.apply_turn(turn(case="case-b", version="1.50"))
    a = stage(t, case="case-a")
    stage(t, case="case-b")
    review(t, a)
    assert t.read_case("case-b")["status"] == "awaiting_review"
    assert t.comments("case-b") == []
    assert t.read_case("case-a")["state"]["facts"][0]["value"] == "1.49"
    assert t.read_case("case-b")["state"]["facts"][0]["value"] == "1.50"


def test_tool_failure_rolls_back_approval_and_comment(tmp_path):
    file = tmp_path / "failure.db"
    t = tracker(file)
    t.apply_turn(turn())
    h = stage(t)

    def raise_tool_failure(*args, **kwargs):
        raise RuntimeError("synthetic local tool failure")

    t._record_local_comment = raise_tool_failure
    with pytest.raises(RuntimeError, match="synthetic local tool failure"):
        review(t, h)
    assert tracker(file).read_case("case-a")["status"] == "awaiting_review"
    assert tracker(file).comments("case-a") == []
    assert review(tracker(file), h)["status"] == "answer_sent"


def test_concurrent_reviews_only_one_local_action(tmp_path):
    file = tmp_path / "race.db"
    t = tracker(file)
    t.apply_turn(turn())
    h = stage(t)

    def attempt(i):
        try:
            return review(tracker(file), h, review_id=f"review-{i}")
        except TrackerRejected as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, (1, 2)))
    assert len([r for r in results if isinstance(r, dict)]) == 1
    assert len(t.comments("case-a")) == 1


def test_no_pending_approval_survives_same_revision_tamper(tmp_path):
    file = tmp_path / "tamper.db"
    t = tracker(file)
    t.apply_turn(turn())
    h = stage(t)
    with sqlite3.connect(file) as db:
        state = CaseState.model_validate(t.read_case("case-a")["state"])
        mutated = state.model_copy(update={"unknowns": ("injected",)})
        db.execute(
            "UPDATE cases SET state_json=? WHERE case_id=?", (mutated.model_dump_json(), "case-a")
        )
    with pytest.raises(TrackerRejected, match="CaseContentMismatch"):
        review(t, h)
    assert t.comments("case-a") == []


def test_reset_requires_explicit_confirmation(tmp_path):
    file = tmp_path / "reset.db"
    t = tracker(file)
    t.apply_turn(turn())
    with pytest.raises(TrackerRejected, match="ResetConfirmationRequired"):
        t.reset_all(confirmation="reset")
    assert t.read_case("case-a")["state"]["case_revision"] == 1
    t.reset_all(confirmation="RESET LOCAL TRACKER")
    assert tracker(file).read_case("case-a")["state"]["case_revision"] == 0
    assert tracker(file).audit_trace("case-a") == []


def test_approved_version_reply_has_durable_binding_and_original_event_replay(tmp_path):
    file = tmp_path / "reply.db"
    t = tracker(file)
    t.apply_turn(turn())
    canonical = STREAMLIT_VERSION_QUESTION.question
    question = AnalysisResult(
        decision="ask",
        user_draft=canonical,
        next_question=canonical,
        missing_info=("streamlit_version",),
        maintainer_summary="The version is unknown.",
        rationale="The version determines which docs apply.",
    )
    h = stage(t, decision="ask", override_analysis=question)
    review(t, h)
    assert t.read_case("case-a")["awaiting_reply"]["proposal_id"] == h.proposal_id
    original = UserTurn(
        case_id="case-a",
        expected_revision=1,
        turn_id="reply-event",
        source_ref="user:reply-event",
        message="Streamlit 1.50.0",
    )
    first = t.apply_turn(original, reply_to_proposal_id=h.proposal_id)
    assert first["preparation"] == "canonical_version_reply"
    assert t.read_case("case-a")["state"]["facts"][0]["value"] == "1.50.0"
    assert t.read_case("case-a")["awaiting_reply"] is None
    assert tracker(file).apply_turn(original, reply_to_proposal_id=h.proposal_id)["replayed"]
    with pytest.raises(TrackerRejected, match="EventConflict"):
        t.apply_turn(original, reply_to_proposal_id="wrong-question")


def test_review_must_match_digest_of_displayed_handoff(tmp_path):
    t = tracker(tmp_path / "digest.db")
    t.apply_turn(turn())
    h = stage(t)
    with pytest.raises(TrackerRejected, match="HandoffDigestMismatch"):
        t.review(
            "case-a",
            review_id="wrong-digest",
            proposal_id=h.proposal_id,
            expected_revision=1,
            expected_handoff_sha256="0" * 64,
            decision="approve",
            reviewer_id="maintainer",
            reviewer_token=TOKEN,
        )
    assert t.comments("case-a") == []
    assert review(t, h)["status"] == "answer_sent"


def test_read_case_uses_one_snapshot_during_concurrent_correction(tmp_path):
    file = tmp_path / "consistent-read.db"
    writer = tracker(file)
    writer.apply_turn(turn(version="1.49.0"))
    original = stage(writer)
    with sqlite3.connect(file) as db:
        # WAL allows the other connection to commit while this read holds its
        # snapshot. No timing sleeps or rollback-journal lock deadlocks.
        assert db.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"

    committed = []

    class ConcurrentReader(SQLiteCaseTracker):
        @staticmethod
        def _load(db, case_id):
            snapshot = SQLiteCaseTracker._load(db, case_id)
            if not committed:
                committed.append(
                    writer.apply_turn(turn(revision=1, turn_id="correction", version="1.50.0"))
                )
            return snapshot

    snapshot = ConcurrentReader(file).read_case("case-a")
    assert committed[0]["committed_revision"] == 2
    assert snapshot["state"]["case_revision"] == 1
    assert snapshot["state"]["facts"][0]["value"] == "1.49.0"
    assert snapshot["pending_handoff"]["handoff_sha256"] == original.handoff_sha256
    assert [entry["revision"] for entry in snapshot["history"]] == [1]
    assert snapshot["status"] == "awaiting_review"
    current = writer.read_case("case-a")
    assert current["state"]["case_revision"] == 2
    assert current["state"]["pending_proposal_id"] is None
    assert current["pending_handoff"] is None
    assert [entry["revision"] for entry in current["history"]] == [1, 2]
    # The read connection releases its transaction, so a later write succeeds.
    assert writer.apply_turn(turn(revision=2, turn_id="later"))["committed_revision"] == 3


def test_registered_dev_pilot_connects_core_handoffs_to_durable_tracker(tmp_path):
    """Existing answer-informed dev fixture, scripted ports; no RAG/model score.

    Only visible input reaches core. Agent scripts configure the offline fake;
    maintainer actions drive the separate authenticated tracker boundary. Gold,
    acceptable decisions and expected results are never passed to either port.
    This composes the core with SQLite, without claiming an API/UI connection.
    """
    root = Path(__file__).resolve().parents[1]
    fixture = json.loads((root / "data/evaluation/dev/pilot-12782.json").read_text())
    assert fixture["case"]["split"] == "dev"
    assert fixture["case"]["test_eligible"] is False
    source_bytes = (root / fixture["evidence_source"]["path"]).read_bytes()
    assert hashlib.sha256(source_bytes).hexdigest() == fixture["evidence_source"]["sha256"]
    bundles = {
        name: EvidenceBundle.model_validate(payload)
        for name, payload in json.loads(source_bytes)["evidence_bundles"].items()
    }
    # Discard gold/expect/probes before constructing any runtime input.
    steps = [
        {
            name: step[name]
            for name in ("id", "visible", "evidence_bundle", "agent_script", "maintainer")
        }
        for step in fixture["turns"]
    ]
    case_id = fixture["case"]["case_id"]
    file = tmp_path / "registered-dev-pilot.db"
    t = tracker(file)
    previous = None
    approved_question_id = None
    envelopes = []
    staged = []
    correction_receipt = None

    for index, step in enumerate(steps):
        before = t.read_case(case_id)
        visible = dict(step["visible"])
        reply_to_question = visible.pop("reply_to_approved_question", False)
        incoming = UserTurn(
            case_id=case_id,
            expected_revision=before["state"]["case_revision"],
            turn_id=step["id"],
            source_ref=f"user:{step['id']}",
            **visible,
        )
        reply_binding = {"reply_to_proposal_id": approved_question_id} if reply_to_question else {}
        envelopes.append((incoming, reply_binding))
        receipt = t.apply_turn(incoming, **reply_binding)
        state = CaseState.model_validate(t.read_case(case_id)["state"])
        assert state.case_revision == index + 1
        assert state.pending_proposal_id is None
        assert t.read_case(case_id)["awaiting_reply"] is None
        if reply_to_question:
            assert receipt["preparation"] == "canonical_version_reply"
            version = next(fact for fact in state.facts if fact.name == "streamlit_version")
            assert version.value == step["visible"]["message"]
            assert version.provenance_kind == "user"
            assert version.turn_id == incoming.turn_id
        if index == 2:
            correction_receipt = receipt
            assert [
                (fact.value, fact.status)
                for fact in state.facts
                if fact.name == "streamlit_version"
            ] == [
                (steps[1]["visible"]["message"], "superseded"),
                (step["visible"]["reported_facts"][0]["value"], "active"),
            ]
            assert receipt["invalidated_checks"] == steps[0]["visible"]["checks_performed"]
            assert previous is not None
            with pytest.raises(TrackerRejected, match="StaleRevision"):
                review(t, previous, review_id="approve-before-correction")
            assert len(t.comments(case_id)) == 1

        final_bundle = bundles[step["evidence_bundle"]]
        analysis = AnalysisResult.model_validate(step["agent_script"])
        retrieval = [final_bundle]
        responses = [analysis]
        if index == 2:
            # Deliberate transport stress: the first search includes the old
            # release note; only the final search may enter the new handoff.
            retrieval.insert(0, previous.evidence)
            current_version = step["visible"]["reported_facts"][0]["value"]
            responses.insert(
                0,
                AnalysisResult(
                    decision="retrieve_more",
                    user_draft="",
                    maintainer_summary="",
                    rationale="Search the fixed fixture catalog for the corrected version.",
                    retrieval_queries=(
                        f"Streamlit {current_version} multiselect fragment identity",
                    ),
                ),
            )
        retriever = FakeRetriever(retrieval)
        capture = ReasoningCapture(FakeReasoner(responses))
        result = SupportEngine(
            retriever,
            capture,
            snapshot_id=final_bundle.snapshot_id,
            current_revision=lambda cid, current_tracker=t: current_tracker.read_case(cid)["state"][
                "case_revision"
            ],
        ).run(state, incoming.message)
        assert result.status == "awaiting_approval"
        handoff = build_handoff(result, capture.last)
        assert handoff.case == state
        assert handoff.user_message == incoming.message
        assert handoff.analysis == analysis
        assert handoff.evidence.hits == final_bundle.hits
        assert handoff.evidence.retrieval_round == len(retrieval)
        assert len(capture.reasoner.inputs) == len(retriever.requests) == len(retrieval)
        assert all(given_case == state for given_case, _, _ in capture.reasoner.inputs)
        comments_before = t.comments(case_id)
        t.stage_proposal(handoff)
        assert t.comments(case_id) == comments_before
        saved = ProposalHandoff.model_validate(t.read_case(case_id)["pending_handoff"])
        assert saved == handoff
        staged.append(handoff)
        if index == 2:
            removed = {hit.chunk_id for hit in previous.evidence.hits} - {
                hit.chunk_id for hit in saved.evidence.hits
            }
            assert removed
            assert not removed & {entry.chunk_id for entry in saved.source_inventory}
            assert not removed & {link.chunk_id for link in saved.analysis.evidence_links}
            assert saved.packet.evidence_sha256 != previous.packet.evidence_sha256
            assert result.retrieval_rounds == result.model_attempts == 2

        action = step["maintainer"]["decision"]
        if action == "approve":
            assert handoff.analysis.next_question == STREAMLIT_VERSION_QUESTION.question
            approved = review(t, handoff, review_id=f"{step['id']}:approve")
            assert approved["status"] == "awaiting_user"
            approved_question_id = handoff.proposal_id
            t = tracker(file)
            assert t.read_case(case_id)["awaiting_reply"]["proposal_id"] == approved_question_id
        elif action == "edit":
            edit_id = f"{step['id']}:edit"
            draft = step["maintainer"]["edited_draft"]
            edited = review(t, handoff, "edit", review_id=edit_id, edited_draft=draft)
            replacement = ProposalHandoff.model_validate(t.read_case(case_id)["pending_handoff"])
            assert replacement.proposal_id == edited["new_proposal_id"] != handoff.proposal_id
            assert replacement.analysis.user_draft == draft
            assert replacement.handoff_sha256 != handoff.handoff_sha256
            assert replacement.packet.analysis_sha256 != handoff.packet.analysis_sha256
            assert replacement.case == handoff.case
            assert replacement.evidence == handoff.evidence
            assert replacement.reasoning_context == handoff.reasoning_context
            assert t.comments(case_id) == comments_before
            t = tracker(file)
            replay_edit = review(t, handoff, "edit", review_id=edit_id, edited_draft=draft)
            assert replay_edit["replayed"] is True
            assert replay_edit["new_proposal_id"] == replacement.proposal_id
            with pytest.raises(TrackerRejected, match="PendingProposalMismatch"):
                review(t, handoff, review_id="approve-before-edit")
            approve_id = f"{step['id']}:approve-edited"
            approved = review(t, replacement, review_id=approve_id)
            assert approved["status"] == "escalated"
            t = tracker(file)
            replay = review(t, replacement, review_id=approve_id)
            assert replay["replayed"] is True
            assert replay["action_id"] == approved["action_id"]
            assert len(t.comments(case_id)) == len(comments_before) + 1
            assert t.comments(case_id)[-1]["body"] == draft
        elif action == "reject":
            rejected = review(t, handoff, "reject", review_id=f"{step['id']}:reject")
            assert rejected["status"] == "open"
            assert rejected["action_id"] is None
            assert t.comments(case_id) == comments_before
        else:
            assert action == "none"
        previous = handoff

    current = t.read_case(case_id)
    assert current["state"]["case_revision"] == len(steps) == 4
    assert current["pending_handoff"] is None
    assert current["awaiting_reply"] is None
    assert "streamlit_version" in current["state"]["unknowns"]
    assert not any(
        fact["name"] == "streamlit_version" and fact["status"] == "active"
        for fact in current["state"]["facts"]
    )
    assert all(entry.version_scope == "unconfirmed" for entry in staged[-1].source_inventory)
    assert len(t.comments(case_id)) == 2
    replay = tracker(file).apply_turn(envelopes[2][0], **envelopes[2][1])
    assert replay == {**correction_receipt, "replayed": True}
    assert t.read_case(case_id) == current
