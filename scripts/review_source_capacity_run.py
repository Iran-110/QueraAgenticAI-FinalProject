"""Inspect the closed exposed-dev capacity run; no model calls or human scores.

Mechanical checks below establish provenance/rendering, not semantic truth.
The attached qualitative notes are the implementing assistant's disclosed review
of this exact receipt and six selected source excerpts, not an independent judge.
"""

import argparse
import hashlib
import json
from pathlib import Path

from agent_app.contracts import GroundedRequest, ReasoningContext
from agent_app.llm.metis import request_id_for
from agent_app.reasoning.grounding import (
    GroundingRejected,
    build_grounded_messages,
    render_grounded_plan,
)
from agent_app.reasoning.source_capacity import add_source_capacity, source_capacity
from agent_app.reasoning.source_selection import add_source_selection_reminder

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "experiments/core_source_capacity_v1"
FLAGS = {"source_gap_handoff": True, "source_gap_investigation": True}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True).encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbench", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("CapacityReviewExists")
    receipt_path = FOLDER / "model-live-receipt-v1.json"
    assert (
        sha(receipt_path.read_bytes())
        == "0cef6c5c25868de55b207bd0d1162415b91cec54f22b3eb8a0b22693b2746243"
    )
    receipt = json.loads(receipt_path.read_bytes())
    workbench = json.loads(args.workbench.read_bytes())
    assert workbench["inputs"]["receipt"]["sha256"] == sha(receipt_path.read_bytes())
    assert receipt["protocol_id"] == "core-source-capacity-model-v1"
    arms, attempts, pairs, checks = {}, [], [], []
    for arm in ("source_capacity_off", "source_capacity_on"):
        arms[arm] = {
            "jobs": 0,
            "complete_routes": 0,
            "fresh_proposals": 0,
            "ask": 0,
            "escalate": 0,
            "answer": 0,
            "capacity_changed_wire": 0,
            "render_overflow": 0,
        }
    for batch in receipt["batches"]:
        jobs = {run: job for job in batch["jobs"] for run in job["run_ids"]}
        for job in batch["jobs"]:
            arms[job["arm"]]["jobs"] += 1
            arms[job["arm"]]["complete_routes"] += job["coverage_complete"]
        first = []
        for job in batch["jobs"]:
            first.append(
                next(
                    a["request"]
                    for a in batch["attempts"]
                    if a["context"]["run_id"] in job["run_ids"]
                )
            )
        pairs.append(
            {"batch": batch["batch_id"], "first_grounded_request_equal": first[0] == first[1]}
        )
        for attempt in batch["attempts"]:
            context = ReasoningContext.model_validate(attempt["context"])
            request = GroundedRequest.model_validate(attempt["request"])
            job = jobs[context.run_id]
            before = add_source_selection_reminder(
                build_grounded_messages(request, context, decision_contracts=True), True
            )
            after = add_source_capacity(before, request, enabled=job["source_capacity"], **FLAGS)
            bound = source_capacity(request, **FLAGS)
            send = next(
                s for s in batch["provider_sends"] if s["request_id"] == request_id_for(context)
            )
            checks.append(
                {
                    "name": "actual_wire_hash",
                    "request_id": send["request_id"],
                    "passed": sha(canonical(list(after))) == send["wire_messages_sha256"],
                }
            )
            changed = before != after
            arms[job["arm"]]["capacity_changed_wire"] += changed
            render_error = None
            if attempt.get("plan"):
                try:
                    render_grounded_plan(request, attempt["plan"], **FLAGS)
                except GroundingRejected as error:
                    render_error = error.code
            arms[job["arm"]]["render_overflow"] += render_error == "grounded_render_too_large"
            attempts.append(
                {
                    "request_id": send["request_id"],
                    "job_id": job["job_id"],
                    "arm": job["arm"],
                    "revision": context.case_revision,
                    "attempt": context.attempt_index,
                    "capacity": bound,
                    "changed_wire": changed,
                    "render_error": render_error,
                    "provider_error": attempt["error_code"],
                    "finish_reason": send["finish_reason"],
                    "schema_observation": attempt.get("schema_observation"),
                    "utf8_with_margin": len(json.dumps(after, ensure_ascii=False).encode()) + 1024,
                }
            )
    rows, quotes = [], {}
    notes = {
        "dev-case-a": "Initial installed-version question is necessary. After version1.50.0, parent callback/state update code is still absent and the supplied reduction works; that follow-up is answerable and avoids a fabricated fix.",
        "dev-case-b": "Initial version question is necessary. Actual returned evidence lacks exact1.39 button capability; escalation is qualified and does not claim custom-image support, warning capability or future delivery. Generic selected background is not an icon answer.",
        "dev-case-c": "Full code and USER version are present; no version/code reask. Escalation retains the reproduction and explicitly lacks a proven diagnosis/fix. Correction uses current1.31.1;1.31.0 remains only labelled history.",
    }
    for row in workbench["rows"]:
        fresh = row["status"] == "fresh_proposal"
        projection = {
            k: row[k]
            for k in ("job_id", "arm", "case_id", "turn_id", "status", "operational_checks")
        }
        projection.update(
            human_usefulness=None,
            assistant_review=notes[row["case_id"]]
            if fresh
            else "No fresh response or unvisited; retained in the denominator.",
        )
        if fresh:
            handoff = row["original_proposal"]["handoff"]
            analysis = handoff["analysis"]
            current = GroundedRequest.model_validate(handoff["grounded_request"])
            matching = [
                a
                for a in row["actual_model_attempts"]
                if a.get("plan") and a["request"]["context_sha256"] == current.context_sha256
            ]
            reconstructed = False
            for attempt in matching:
                try:
                    reconstructed |= (
                        render_grounded_plan(current, attempt["plan"], **FLAGS).model_dump(
                            mode="json"
                        )
                        == analysis
                    )
                except GroundingRejected:
                    pass
            checks.append(
                {
                    "name": "full_original_analysis_reconstructed",
                    "job_id": row["job_id"],
                    "turn": row["turn_id"],
                    "passed": reconstructed,
                }
            )
            arms[row["arm"]]["fresh_proposals"] += 1
            arms[row["arm"]][analysis["decision"]] += 1
            selected = {r["chunk_id"] for r in analysis["evidence_links"]}
            for hit in handoff["evidence"]["hits"]:
                if hit["chunk_id"] in selected:
                    quotes[hit["chunk_id"]] = {
                        "source_id": hit["source_id"],
                        "excerpt_sha256": sha(hit["excerpt"].encode()),
                        "applicable_versions": hit["applicable_versions"],
                        "assessment": "Complete supplied background excerpt, unconfirmed applicability; not a cause/fix or an icon-capability answer.",
                    }
            projection.update(
                decision=analysis["decision"],
                question=analysis["next_question"],
                proposal_id=handoff["proposal_id"],
                handoff_sha256=handoff["handoff_sha256"],
                all_surfaces_sha256={
                    k: sha(v.encode()) for k, v in row["original_proposal"]["surfaces"].items()
                },
                unsupported_material_claim_found=False,
                technical_answer_provided=False,
                current_user_facts=row["original_proposal"]["active_user_facts"],
                reviewed_question_necessary_and_answerable=True
                if analysis["decision"] == "ask"
                else None,
                selected_chunks=sorted(selected),
            )
        rows.append(projection)
    report = {
        "schema_version": 1,
        "review_id": "core-source-capacity-semantic-review-v1",
        "receipt_sha256": sha(receipt_path.read_bytes()),
        "preparation_sha256": sha((FOLDER / "semantic-review-preparation-v1.json").read_bytes()),
        "reviewer_kind": "assistant",
        "reviewer_implementation_overlap": True,
        "blinded": False,
        "human_reviewed": False,
        "human_usefulness": None,
        "quality_improvement_demonstrated": False,
        "held_out_test": False,
        "source_commit": receipt["registration"]["source_commit"],
        "summary": workbench["summary"],
        "arms": arms,
        "paired_initial_requests": pairs,
        "attempts": attempts,
        "turns": rows,
        "selected_quote_reviews": quotes,
        "checks": checks,
        "mechanical_checks_passed": sum(c["passed"] for c in checks),
        "mechanical_checks_total": len(checks),
        "limitations": [
            "The implementing assistant reviewed these exposed dev outputs; no independent human usefulness score.",
            "Only two ON calls on one correction changed the schema bound; all six paired initial grounded requests and initial wire payloads were unchanged.",
            "No renderer overflow occurred in either arm; no live causal overflow reduction or answer-quality gain can be established.",
            "All technical answer counts are zero. Six escalations and ten necessary questions are not a solved-case rate.",
            "Two length failures, invalid field combinations and source mismatch remain; do not hide four empty and four unvisited turns.",
            "Tests use native retrieval plus TestClient/DummyTracker and scripted approval; not a new browser/SQLite manual report.",
        ],
    }
    assert all(c["passed"] for c in checks)
    with args.output.open("x") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)
        file.write("\n")
    print(
        json.dumps(
            {
                "summary": report["summary"],
                "arms": arms,
                "checks_passed": report["mechanical_checks_passed"],
                "checks_total": len(checks),
            }
        )
    )


if __name__ == "__main__":
    main()
