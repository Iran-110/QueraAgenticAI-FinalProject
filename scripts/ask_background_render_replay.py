"""Pair local renderers on actual plans; no provider, key or ledger is opened."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from agent_app.contracts import GroundedRequest, ProposalHandoff
from agent_app.orchestration.handoff import validate_handoff
from agent_app.reasoning.grounding import GroundingRejected, render_grounded_plan
from agent_app.testing.stability_probe import fixtures_for

ROOT = Path(__file__).resolve().parents[1]
PROTOCOLS = {"retrieval-relevance-model-v1", "core-ask-background-model-v1"}


def sha(value):
    return hashlib.sha256(value).hexdigest()


def render_pair(request, plan):
    """Compare exact full analyses; default/failing records are not discarded."""
    outcomes = []
    for enabled in (False, True):
        try:
            analysis = render_grounded_plan(
                request,
                plan,
                source_gap_handoff=True,
                source_gap_investigation=True,
                ask_source_background=enabled,
            )
            outcomes.append((analysis, None))
        except GroundingRejected as error:
            outcomes.append((None, error.code))
    off, on = (outcome[0] for outcome in outcomes)
    assert outcomes[0][1] == outcomes[1][1], "Renderer outcome changed outside display contract"
    record = {
        "off_error": outcomes[0][1],
        "on_error": outcomes[1][1],
        "background_added": False,
    }
    if off is None:
        return record, off, on
    off_value, on_value = off.model_dump(mode="json"), on.model_dump(mode="json")
    assert {k: v for k, v in off_value.items() if k != "user_draft"} == {
        k: v for k, v in on_value.items() if k != "user_draft"
    }
    if off.decision != "ask":
        assert off_value == on_value
    changed = off.user_draft != on.user_draft
    if changed:
        assert off.decision == "ask" and on.user_draft.startswith(off.user_draft + "\n\n")
        assert on.next_question == off.next_question == off.user_draft
        assert len(on.user_draft) <= 20_000
    record.update(
        decision=off.decision,
        question_name=off.missing_info[0] if off.missing_info else None,
        background_added=changed,
        off_analysis_sha256=sha(off.model_dump_json().encode()),
        on_analysis_sha256=sha(on.model_dump_json().encode()),
        off_draft_chars=len(off.user_draft),
        on_draft_chars=len(on.user_draft),
        non_draft_fields_equal=True,
        off_analysis=off_value,
        on_analysis=on_value,
    )
    return record, off, on


def build_report(receipt_path):
    raw = receipt_path.read_bytes()
    receipt = json.loads(raw)
    assert receipt["protocol_id"] in PROTOCOLS
    on_observed = receipt["protocol_id"] == "core-ask-background-model-v1"
    if not on_observed:
        protocol = json.loads(
            (ROOT / "experiments/core_ask_background_v1/protocol-v1.json").read_bytes()
        )
        assert sha(raw) == protocol["offline"]["receipt_sha256"]
    if on_observed:
        assert receipt["renderer_ask_source_background"] is True
        assert receipt["single_paid_model_condition"] is True
        assert receipt["no_model_prompt_treatment"] is True
        method_path = ROOT / "experiments/core_ask_background_v1/live-method-v1.json"
        assert json.loads(method_path.read_bytes()) == receipt["method"]
        assert sha(method_path.read_bytes()) == receipt["registration"]["method_sha256"]
    method = receipt["method"]
    fixtures = fixtures_for(ROOT, {"protocol_id": "core-stability-v1"})
    batches = {batch["batch_id"]: batch for batch in receipt["batches"]}
    assert len(batches) == len(receipt["batches"])
    assert set(batches) <= {batch["batch_id"] for batch in method["batches"]}
    rows, attempts = [], []
    for registered in method["batches"]:
        batch = batches.get(registered["batch_id"])
        jobs = {job["job_id"]: job for job in batch["jobs"]} if batch else {}
        assert len(jobs) == (len(batch["jobs"]) if batch else 0)
        assert set(jobs) <= {job["job_id"] for job in registered["jobs"]}
        for attempt in batch["attempts"] if batch else ():
            pair = None
            if attempt.get("plan") is not None:
                current = GroundedRequest.model_validate(attempt["request"])
                pair, _, _ = render_pair(current, attempt["plan"])
            attempts.append(
                {
                    "context": attempt["context"],
                    "request_sha256": sha(json.dumps(attempt["request"], sort_keys=True).encode()),
                    "schema_observation": attempt.get("schema_observation"),
                    "wire_output": attempt.get("wire_output"),
                    "canonical_plan_observed": attempt.get("plan") is not None,
                    "paired_render": pair,
                }
            )
        for job_plan in registered["jobs"]:
            job = jobs.get(job_plan["job_id"])
            if job:
                assert all(job[key] == value for key, value in job_plan.items())
            fixture = fixtures[job_plan.get("fixture_id", job_plan["case_id"])]
            steps = [step for step in job["steps"] if "request" in step] if job else []
            by_turn = {step["turn"]: step for step in steps}
            assert len(by_turn) == len(steps)
            assert set(by_turn) <= {turn["id"] for turn in fixture.data["turns"]}
            for turn in fixture.data["turns"]:
                step = by_turn.get(turn["id"])
                row = {
                    "job_id": job_plan["job_id"],
                    "case_id": job_plan["case_id"],
                    "arm": job_plan["arm"],
                    "round": job_plan["round"],
                    "turn_id": turn["id"],
                    "status": "unvisited" if step is None else "no_fresh_proposal",
                    "background_added": False,
                }
                proposal = step.get("proposal") if step else None
                if proposal and proposal.get("review_handoff"):
                    handoff = validate_handoff(
                        ProposalHandoff.model_validate(proposal["review_handoff"])
                    )
                    if (
                        proposal.get("stale") is False
                        and proposal["case_revision"] == step["request"]["expected_revision"] + 1
                    ):
                        matches = [
                            attempt
                            for attempt in batch["attempts"]
                            if attempt["context"]
                            == handoff.reasoning_context.model_dump(mode="json")
                            and attempt["request"]
                            == handoff.grounded_request.model_dump(mode="json")
                        ]
                        assert len(matches) == 1 and matches[0].get("plan") is not None
                        pair, off, on = render_pair(handoff.grounded_request, matches[0]["plan"])
                        assert handoff.analysis == (on if on_observed else off)
                        row.update(
                            status="fresh_proposal",
                            handoff_sha256=handoff.handoff_sha256,
                            actual_analysis_reconstructed=True,
                            **pair,
                        )
                    else:
                        row["status"] = "stale_observation"
                rows.append(row)
    counts = Counter(row["status"] for row in rows)
    return {
        "schema_version": 1,
        "review_id": "core-ask-background-paired-render-v1",
        "receipt_path": str(receipt_path),
        "receipt_sha256": sha(raw),
        "actual_condition": "ON" if on_observed else "OFF",
        "new_provider_calls": 0,
        "model_quality_claim": False,
        "human_usefulness": None,
        "held_out_test": False,
        "paired_same_actual_request_plan": True,
        "planned_jobs": sum(len(batch["jobs"]) for batch in method["batches"]),
        "planned_turns": len(rows),
        "turn_statuses": dict(counts),
        "fresh_background_additions": sum(row["background_added"] for row in rows),
        "background_additions_by_case": dict(
            Counter(row["case_id"] for row in rows if row["background_added"])
        ),
        "turns": rows,
        "actual_attempts_including_unparsed": attempts,
        "interpretation": [
            "Same-plan local renderer comparison isolates display, not a model capability improvement.",
            "Fresh model routing/selection is observational replication on exposed dev cases.",
            "Background presence does not establish relevance, usefulness, diagnosis or a fix; inspect all actual passages and claims.",
            "All planned, empty, stale and unvisited turns remain; no source, gold or closed receipt is changed.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_report(args.receipt)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(
        json.dumps(
            {
                key: report[key]
                for key in ("planned_turns", "turn_statuses", "fresh_background_additions")
            }
        )
    )


if __name__ == "__main__":
    main()
