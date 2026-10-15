"""Reproduce structural observations, never infer usefulness or source support.

The raw provider text is not retained: wire diagnostics are recorded gateway
observations, not an independent reparse. Cost review is a separately prepared
read-only audit. All planned, stale, empty and unvisited turns stay visible.
"""

import argparse
import hashlib
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path
from statistics import median

from agent_app.contracts import GroundedRequest
from agent_app.evaluation.review_workbench import load_workbench
from agent_app.reasoning.grounding import GroundingRejected, render_grounded_plan

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "experiments/retrieval_relevance_v1"
RECEIPT_SHA = "edf56d75266d97466666224738e2d5c95e2cbbc32e396188714d00c4fbdafd17"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def build_report(workbench_path, cost_review_path):
    receipt_path = FOLDER / "model-live-receipt-v1.json"
    assert sha(receipt_path.read_bytes()) == RECEIPT_SHA
    receipt = json.loads(receipt_path.read_bytes())
    workbench = load_workbench(workbench_path)
    cost = json.loads(cost_review_path.read_bytes())
    assert workbench["inputs"]["receipt"]["sha256"] == RECEIPT_SHA
    assert cost["original_receipt_sha256"] == RECEIPT_SHA and cost["all_checks_passed"]
    assert receipt["protocol_id"] == "retrieval-relevance-model-v1"
    arms, pairs, render_checks, turns = {}, [], [], []
    for arm in ("native_top5", "candidate_relevance"):
        jobs = [j for b in receipt["batches"] for j in b["jobs"] if j["arm"] == arm]
        run_ids = {run for job in jobs for run in job["run_ids"]}
        attempts = [
            a
            for batch in receipt["batches"]
            for a in batch["attempts"]
            if a["context"]["run_id"] in run_ids
        ]
        rows = [row for row in workbench["rows"] if row["arm"] == arm]
        sends = [row for row in cost["wire_and_usage_reviews"] if row["arm"] == arm]
        latencies = [
            step["usage"]["latency_ms"]
            for job in jobs
            for step in job["steps"]
            if "request" in step
        ]
        decisions = Counter(
            row["original_proposal"]["handoff"]["analysis"]["decision"]
            for row in rows
            if row["status"] == "fresh_proposal"
        )
        render_errors = Counter()
        for attempt in attempts:
            if not attempt.get("plan"):
                continue
            try:
                render_grounded_plan(
                    GroundedRequest.model_validate(attempt["request"]),
                    attempt["plan"],
                    source_gap_handoff=True,
                    source_gap_investigation=True,
                )
            except GroundingRejected as error:
                render_errors[error.code] += 1
        arms[arm] = {
            "jobs": len(jobs),
            "complete_routes": sum(job["coverage_complete"] for job in jobs),
            "turn_statuses": dict(Counter(row["status"] for row in rows)),
            "fresh_decisions": dict(decisions),
            "attempts": len(attempts),
            "actual_sends": len(sends),
            "canonical_schema_observations": dict(
                Counter(
                    a.get("schema_observation", {}).get("diagnostic", "unobserved")
                    for a in attempts
                )
            ),
            "recorded_compact_wire_valid": sum(
                bool(a.get("wire_output", {}).get("wire_schema_valid"))
                for a in attempts
                if a.get("wire_output")
            ),
            "recorded_compact_binding_valid": sum(
                bool(a.get("wire_output", {}).get("canonical_binding_valid"))
                for a in attempts
                if a.get("wire_output")
            ),
            "recorded_raw_wire_schema_invalid": sum(
                not a["wire_output"]["wire_schema_valid"] for a in attempts if a.get("wire_output")
            ),
            "visited_turn_latency_ms": {
                "observations": len(latencies),
                "median": median(latencies),
                "sum": round(sum(latencies), 1),
                "scope": "HTTP-turn observations; includes empty visited turns, excludes unvisited",
            },
            "finish_reasons": dict(Counter(row["finish_reason"] for row in sends)),
            "renderer_rejection_codes": dict(render_errors),
            "terminal_error_codes": dict(
                Counter(a["error_code"] for a in attempts if a.get("error_code"))
            ),
            "output_tokens_total": sum(row["output_tokens"] for row in sends),
            "output_tokens_median": median(row["output_tokens"] for row in sends),
            "estimated_cost_usd": str(
                sum(Decimal(row["local_list_price_cost_usd"]) for row in sends)
            ),
        }
    for batch in receipt["batches"]:
        initial = []
        for job in batch["jobs"]:
            initial.append(
                next(
                    a["request"]
                    for a in batch["attempts"]
                    if a["context"]["run_id"] in job["run_ids"]
                )
            )
        initial_queries = [
            next(
                record["requested"]["queries"]
                for record in batch["actual_retrievals"]
                if record["job_id"] == job["job_id"]
            )
            for job in batch["jobs"]
        ]
        pairs.append(
            {
                "batch": batch["batch_id"],
                "initial_user_state_equal": all(
                    initial[0][name] == initial[1][name] for name in ("case", "user_message")
                ),
                "initial_queries_equal": initial_queries[0] == initial_queries[1],
            }
        )
    for row in workbench["rows"]:
        turns.append({key: row[key] for key in ("job_id", "arm", "case_id", "turn_id", "status")})
        if row["status"] != "fresh_proposal":
            continue
        handoff = row["original_proposal"]["handoff"]
        current = GroundedRequest.model_validate(handoff["grounded_request"])
        reconstructed = False
        for attempt in row["actual_model_attempts"]:
            if not attempt.get("plan") or attempt["request"] != current.model_dump(mode="json"):
                continue
            try:
                reconstructed |= (
                    render_grounded_plan(
                        current,
                        attempt["plan"],
                        source_gap_handoff=True,
                        source_gap_investigation=True,
                    ).model_dump(mode="json")
                    == handoff["analysis"]
                )
            except GroundingRejected:
                pass
        render_checks.append(
            {"item_id": row["item_id"], "original_analysis_reconstructed": reconstructed}
        )
    assert all(pair["initial_user_state_equal"] and pair["initial_queries_equal"] for pair in pairs)
    assert all(check["original_analysis_reconstructed"] for check in render_checks)
    return {
        "schema_version": 1,
        "review_id": "retrieval-relevance-structural-review-v1",
        "receipt_sha256": RECEIPT_SHA,
        "cost_review_sha256": sha(cost_review_path.read_bytes()),
        "workbench_sha256": workbench["workbench_sha256"],
        "source_commit": receipt["registration"]["source_commit"],
        "quality_claim": False,
        "human_usefulness": None,
        "raw_wire_schema_independently_reparsed": False,
        "summary": workbench["summary"],
        "arms": arms,
        "paired_initial_requests": pairs,
        "render_checks": render_checks,
        "turns": turns,
        "interpretation": [
            "Compound treatment, exposed three-dev data, two rounds; no component-level causal claim or held-out result.",
            "Both arms use the same compact wire/core flags. Raw wire validity is separate from canonical expansion and semantic guidance.",
            "Answer labels, route completion, byte-exact rendering and source binding do not establish semantic support or usefulness.",
            "Neither arm hit provider length; this study cannot establish a reduction in length failures.",
            "All native candidate reads, adapter selection, USER version scope and whole-record packing are separately reconstructed in the cost/provenance audit.",
            "Median tokens are descriptive of different realized paths, not a controlled same-response efficiency estimate.",
            "Latency is observed per reached HTTP turn with different paths/attempts; unvisited turns have no zero-latency imputation.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbench", type=Path, required=True)
    parser.add_argument("--cost-review", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_report(args.workbench, args.cost_review)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"summary": report["summary"], "arms": report["arms"]}))


if __name__ == "__main__":
    main()
