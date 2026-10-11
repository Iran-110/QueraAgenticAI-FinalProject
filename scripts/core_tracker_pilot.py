"""Registered dev #12782 through CoreTurnService and actual local SQLite.

Authored ports and fixture review actions only; not HTTP/UI, real retrieval,
model evaluation, or held-out quality. Source snippets are never executed.
"""

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

from agent_app.contracts import AnalysisResult, EvidenceBundle, ProposalHandoff, UserTurn
from agent_app.orchestration.service import CoreAdapters, CoreTurnService
from agent_app.testing.fakes import FakeReasoner, FakeRetriever
from agent_app.tracker.sqlite_tracker import SQLiteCaseTracker, TrackerRejected

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "data/evaluation/dev/pilot-12782.json"
TOKEN = "offline-core-pilot-fixture-token"


def _fingerprint():
    return {
        path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((ROOT / "src/agent_app").rglob("*.py"))
    }


def run_pilot(database: Path) -> dict:
    fixture_bytes = FIXTURE.read_bytes()
    fixture = json.loads(fixture_bytes)
    source_path = ROOT / fixture["evidence_source"]["path"]
    source_bytes = source_path.read_bytes()
    checks = {}

    def check(name, condition):
        checks[name] = bool(condition)
        if not condition:
            raise RuntimeError("PilotConformanceFailed")

    check("fixture_is_exposed_dev", fixture["case"]["split"] == "dev")
    check("fixture_is_not_held_out", fixture["case"]["test_eligible"] is False)
    check(
        "fixed_evidence_hash",
        hashlib.sha256(source_bytes).hexdigest() == fixture["evidence_source"]["sha256"],
    )
    bundles = {
        name: EvidenceBundle.model_validate(payload)
        for name, payload in json.loads(source_bytes)["evidence_bundles"].items()
    }
    # Gold/expect/probes stay outside every runtime port and factory input.
    steps = [
        {
            name: step[name]
            for name in ("id", "visible", "evidence_bundle", "agent_script", "maintainer")
        }
        for step in fixture["turns"]
    ]
    case_id = fixture["case"]["case_id"]

    def new_tracker():
        return SQLiteCaseTracker(database, reviewer_tokens={"fixture-maintainer": TOKEN})

    t = new_tracker()
    if t.read_case(case_id)["state"]["case_revision"] != 0:
        raise RuntimeError("PilotDatabaseNotFresh")
    code_before = _fingerprint()
    records = []
    previous = None
    approved_question = None
    envelopes = []
    factory_calls = []

    def review(handoff, decision, review_id, **kwargs):
        return t.review(
            case_id,
            review_id=review_id,
            proposal_id=handoff.proposal_id,
            expected_revision=handoff.case.case_revision,
            expected_handoff_sha256=handoff.handoff_sha256,
            decision=decision,
            reviewer_id="fixture-maintainer",
            reviewer_token=TOKEN,
            **kwargs,
        )

    for index, step in enumerate(steps):
        visible = dict(step["visible"])
        bound_reply = visible.pop("reply_to_approved_question", False)
        incoming = UserTurn(
            case_id=case_id,
            expected_revision=t.read_case(case_id)["state"]["case_revision"],
            turn_id=step["id"],
            source_ref=f"user:{step['id']}",
            **visible,
        )
        binding = {"reply_to_proposal_id": approved_question} if bound_reply else {}
        envelopes.append((incoming, binding))
        final_bundle = bundles[step["evidence_bundle"]]
        responses = [AnalysisResult.model_validate(step["agent_script"])]
        retrieval = [final_bundle]
        if index == 2:
            retrieval.insert(0, previous.evidence)
            responses.insert(
                0,
                AnalysisResult(
                    decision="retrieve_more",
                    user_draft="",
                    maintainer_summary="",
                    rationale="Search fixed excerpts for the corrected user version.",
                    retrieval_queries=(
                        f"Streamlit {incoming.reported_facts[0].value} multiselect fragment identity",
                    ),
                ),
            )
        retriever = FakeRetriever(retrieval)
        reasoner = FakeReasoner(responses)

        def factory(
            case,
            message,
            run_id,
            retriever=retriever,
            reasoner=reasoner,
            snapshot=final_bundle.snapshot_id,
        ):
            factory_calls.append(run_id)
            return CoreAdapters(retriever, reasoner, snapshot)

        service = CoreTurnService(t, factory)
        comments_before = t.comments(case_id)
        outcome = service.submit(incoming, **binding)
        check(f"{index}:proposal_staged", outcome.status == "proposal_staged")
        handoff = outcome.handoff
        check(f"{index}:no_action_before_review", t.comments(case_id) == comments_before)
        check(f"{index}:exact_pending", service.recover_exact_pending(handoff) == handoff)
        check(f"{index}:current_revision", handoff.case.case_revision == index + 1)
        check(f"{index}:final_bundle_only", handoff.evidence.hits == final_bundle.hits)
        check(
            f"{index}:original_problem_in_input",
            steps[0]["visible"]["message"] in handoff.user_message,
        )
        if bound_reply:
            check(
                "short_reply_retains_query_subject",
                "multiselect" in retriever.requests[0].queries[0],
            )
            check(
                "short_reply_binds_user_version",
                outcome.receipt.preparation == "canonical_version_reply",
            )
            check(
                "short_reply_ingress_unchanged",
                t.read_case(case_id)["history"][-1]["text"] == incoming.message,
            )
        if index == 2:
            check(
                "corrected_version_active",
                [
                    f.value
                    for f in handoff.case.facts
                    if f.name == "streamlit_version" and f.status == "active"
                ]
                == [incoming.reported_facts[0].value],
            )
            check(
                "old_checks_invalidated",
                list(outcome.receipt.invalidated_checks) == steps[0]["visible"]["checks_performed"],
            )
            check(
                "refinement_within_limits",
                outcome.run_result.model_attempts == outcome.run_result.retrieval_rounds == 2,
            )
            removed = {hit.chunk_id for hit in previous.evidence.hits} - {
                hit.chunk_id for hit in handoff.evidence.hits
            }
            check(
                "old_evidence_removed",
                bool(removed)
                and not removed & {entry.chunk_id for entry in handoff.source_inventory},
            )
            try:
                review(previous, "approve", "obsolete-approval")
                check("obsolete_approval_rejected", False)
            except TrackerRejected as error:
                check("obsolete_approval_rejected", error.code == "StaleRevision")

        action = step["maintainer"]["decision"]
        edited_handoff = None
        released_handoff = None
        review_receipts = []
        if action == "approve":
            done = review(handoff, "approve", f"{step['id']}:approve")
            review_receipts.append(done)
            check("approved_question_persisted", done["status"] == "awaiting_user")
            approved_question = handoff.proposal_id
            released_handoff = handoff
        elif action == "edit":
            draft = step["maintainer"]["edited_draft"]
            edited = review(handoff, "edit", f"{step['id']}:edit", edited_draft=draft)
            review_receipts.append(edited)
            edited_handoff = ProposalHandoff.model_validate(t.read_case(case_id)["pending_handoff"])
            check("edit_new_proposal", edited_handoff.proposal_id != handoff.proposal_id)
            check("edit_has_no_action", t.comments(case_id) == comments_before)
            t = new_tracker()
            try:
                review(handoff, "approve", "obsolete-before-edit")
                check("obsolete_edit_approval_rejected", False)
            except TrackerRejected as error:
                check("obsolete_edit_approval_rejected", error.code == "PendingProposalMismatch")
            done = review(edited_handoff, "approve", f"{step['id']}:approve-edited")
            review_receipts.append(done)
            released_handoff = edited_handoff
            t = new_tracker()
            replay = review(edited_handoff, "approve", f"{step['id']}:approve-edited")
            review_receipts.append(replay)
            check(
                "review_retry_same_action",
                replay["replayed"] and replay["action_id"] == done["action_id"],
            )
            check("review_retry_one_action", len(t.comments(case_id)) == len(comments_before) + 1)
        elif action == "reject":
            done = review(handoff, "reject", f"{step['id']}:reject")
            review_receipts.append(done)
            check(
                "reject_no_action",
                done["action_id"] is None and t.comments(case_id) == comments_before,
            )
        else:
            check("registered_review_action", action == "none")
        records.append(
            {
                "turn_id": incoming.turn_id,
                "ingress": incoming.model_dump(mode="json"),
                "receipt": outcome.receipt.model_dump(mode="json"),
                "run_result": outcome.run_result.model_dump(mode="json"),
                "retrieval_requests": [r.model_dump(mode="json") for r in retriever.requests],
                "original_handoff": handoff.model_dump(mode="json"),
                "edited_handoff": edited_handoff.model_dump(mode="json")
                if edited_handoff
                else None,
                "released_handoff": released_handoff.model_dump(mode="json")
                if released_handoff
                else None,
                "reviews": review_receipts,
            }
        )
        previous = handoff
        t = new_tracker()
    before_replay = t.read_case(case_id)

    def forbidden_factory(*args):
        raise AssertionError("ReplayMustNotConstructPorts")

    replay = CoreTurnService(t, forbidden_factory).submit(envelopes[2][0], **envelopes[2][1])
    check(
        "old_event_replay_only",
        replay.status == "replay_only" and replay.receipt.committed_revision == 3,
    )
    check("replay_preserves_current_state", t.read_case(case_id) == before_replay)
    check(
        "withdrawal_leaves_no_active_version",
        not any(
            f["name"] == "streamlit_version" and f["status"] == "active"
            for f in before_replay["state"]["facts"]
        ),
    )
    check("four_distinct_run_ids", len(factory_calls) == len(set(factory_calls)) == 4)
    check("two_approved_local_comments", len(t.comments(case_id)) == 2)
    code_after = _fingerprint()
    check("source_unchanged_during_run", code_before == code_after)
    return {
        "schema_version": 1,
        "mode": "fixed_evidence_core_sqlite_scripted_ports",
        "quality_claim": False,
        "model_quality_claim": False,
        "rag_quality_claim": False,
        "held_out_test": False,
        "api_ui_connected": False,
        "real_api_calls": 0,
        "actual_cost_usd": 0,
        "git_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "git_dirty": bool(
            subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()
        ),
        "source_fingerprint": code_after,
        "fixture_id": fixture["fixture_id"],
        "fixture_sha256": hashlib.sha256(fixture_bytes).hexdigest(),
        "evidence_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "exposure": fixture["case"]["exposure"],
        "checks": checks,
        "turns": records,
        "final_snapshot": before_replay,
        "local_actions": t.comments(case_id),
        "event_replay": replay.receipt.model_dump(mode="json"),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, required=True, help="New receipt path; never overwritten."
    )
    args = parser.parse_args()
    # Refuse an existing receipt before running the pilot. SQLite is always a
    # fresh temporary local DB; no production tracker or ledger is touched.
    with args.output.open("x", encoding="utf-8") as destination:
        with tempfile.TemporaryDirectory(prefix="core-tracker-pilot-") as directory:
            receipt = run_pilot(Path(directory) / "pilot.db")
        destination.write(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "mode": receipt["mode"],
                "turns": len(receipt["turns"]),
                "checks_passed": len(receipt["checks"]),
                "quality_claim": False,
                "actual_cost_usd": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
