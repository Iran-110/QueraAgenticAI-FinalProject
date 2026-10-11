"""Fully offline durable-tracker pilot: user turn -> review -> correction -> safe action.

Run from repo root: PYTHONPATH=src python scripts/tracker_pilot.py
Pass --db runtime/tracker-pilot.sqlite3 to keep state for manual inspection.
This never invokes a paid model or writes to GitHub.
"""

from __future__ import annotations

import argparse
import json
import secrets
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_app.contracts import CaseState, ReportedFact, UserTurn
from agent_app.demo import SNAPSHOT_ID, _answer, _ask, _evidence
from agent_app.orchestration import SupportEngine
from agent_app.orchestration.handoff import ReasoningCapture, build_handoff
from agent_app.testing.fakes import FakeReasoner, FakeRetriever
from agent_app.tracker.sqlite_tracker import SQLiteCaseTracker, TrackerRejected


def _propose(t: SQLiteCaseTracker, case_id: str, kind: str) -> tuple[str, str]:
    state = CaseState.model_validate(t.read_case(case_id)["state"])
    capture = ReasoningCapture(FakeReasoner([_ask() if kind == "ask" else _answer("demo-initial")]))
    engine = SupportEngine(
        FakeRetriever([_evidence("demo-initial", "Synthetic widget evidence")]),
        capture,
        snapshot_id=SNAPSHOT_ID,
    )
    result = engine.run(state, "Streamlit widget callback loses state")
    assert result.status == "awaiting_approval"
    handoff = build_handoff(result, capture.last)
    t.stage_proposal(handoff)
    return handoff.proposal_id, handoff.handoff_sha256


def pilot(path: Path) -> dict:
    token = secrets.token_urlsafe(32)
    t = SQLiteCaseTracker(path, reviewer_tokens={"local-maintainer": token})
    case_id = "offline-widget-pilot"
    if t.read_case(case_id)["state"]["case_revision"]:
        raise TrackerRejected("DemoCaseAlreadyExistsUseFreshDatabase")
    first = t.apply_turn(
        UserTurn(
            case_id=case_id,
            expected_revision=0,
            turn_id="turn-1",
            source_ref="user:turn-1",
            message="Widget changes unexpectedly after rerun",
            unknowns=("streamlit_version",),
        )
    )
    proposed_question, question_digest = _propose(t, case_id, "ask")
    approved = t.review(
        case_id,
        review_id="approve-question",
        proposal_id=proposed_question,
        expected_revision=1,
        expected_handoff_sha256=question_digest,
        decision="approve",
        reviewer_id="local-maintainer",
        reviewer_token=token,
    )
    # Answer as explicitly attributed structured input: free text is NOT extracted
    # into a trusted fact by the tracker.
    second = t.apply_turn(
        UserTurn(
            case_id=case_id,
            expected_revision=1,
            turn_id="turn-2",
            source_ref="user:turn-2",
            message="I am using version 1.49.0",
            reported_facts=(ReportedFact(name="streamlit_version", value="1.49.0"),),
        )
    )
    stale_proposal, stale_digest = _propose(t, case_id, "answer")
    corrected = t.apply_turn(
        UserTurn(
            case_id=case_id,
            expected_revision=2,
            turn_id="turn-3",
            source_ref="user:turn-3",
            message="Correction: the affected server uses Streamlit 1.50.0",
            reported_facts=(ReportedFact(name="streamlit_version", value="1.50.0"),),
            context_changed=True,
        )
    )
    stale_blocked = False
    try:
        t.review(
            case_id,
            review_id="try-stale",
            proposal_id=stale_proposal,
            expected_revision=2,
            expected_handoff_sha256=stale_digest,
            decision="approve",
            reviewer_id="local-maintainer",
            reviewer_token=token,
        )
    except TrackerRejected as error:
        stale_blocked = error.code == "StaleRevision"
    if not stale_blocked:
        raise AssertionError("A stale approval must not execute")
    corrected_proposal, corrected_digest = _propose(t, case_id, "answer")
    done = t.review(
        case_id,
        review_id="approve-final",
        proposal_id=corrected_proposal,
        expected_revision=3,
        expected_handoff_sha256=corrected_digest,
        decision="approve",
        reviewer_id="local-maintainer",
        reviewer_token=token,
    )
    reopened = SQLiteCaseTracker(path, reviewer_tokens={"local-maintainer": token})
    repeated = reopened.review(
        case_id,
        review_id="approve-final",
        proposal_id=corrected_proposal,
        expected_revision=3,
        expected_handoff_sha256=corrected_digest,
        decision="approve",
        reviewer_id="local-maintainer",
        reviewer_token=token,
    )
    snapshot = reopened.read_case(case_id)
    comments = reopened.comments(case_id)
    assert repeated["replayed"] is True and len(comments) == 2  # question and final answer
    assert snapshot["state"]["facts"][-1]["value"] == "1.50.0"
    return {
        "mode": "synthetic_offline",
        "db_path": str(path),
        "paid_requests": 0,
        "steps": {
            "initial_revision": first["committed_revision"],
            "question_approved": approved["decision"],
            "fact_revision": second["committed_revision"],
            "correction_revision": corrected["committed_revision"],
            "stale_approval_blocked": stale_blocked,
            "final_status": done["status"],
            "retry_replayed": repeated["replayed"],
            "comment_actions": len(comments),
        },
        "audit": reopened.audit_trace(case_id),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, help="Persist pilot SQLite file to a chosen local path")
    args = parser.parse_args()
    if args.db:
        result = pilot(args.db)
    else:
        with TemporaryDirectory(prefix="quera-tracker-") as temporary:
            result = pilot(Path(temporary) / "pilot.sqlite3")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
