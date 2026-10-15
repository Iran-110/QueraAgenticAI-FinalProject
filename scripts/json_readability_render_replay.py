"""Same-plan presentation audit; no credentials, provider or ledger are opened."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from agent_app.contracts import ProposalHandoff
from agent_app.orchestration.handoff import validate_handoff
from agent_app.reasoning.grounding import render_grounded_plan
from agent_app.testing.stability_probe import fixtures_for

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "experiments/core_json_readability_v1"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pair(request, plan):
    outputs = [
        render_grounded_plan(
            request,
            plan,
            source_gap_handoff=True,
            source_gap_investigation=True,
            ask_source_background=True,
            concise_user_draft=enabled,
        )
        for enabled in (False, True)
    ]
    off, on = [output.model_dump(mode="json") for output in outputs]
    assert {k: v for k, v in off.items() if k not in {"user_draft", "rationale"}} == {
        k: v for k, v in on.items() if k not in {"user_draft", "rationale"}
    }
    if off["rationale"] != on["rationale"]:
        assert off["decision"] in {"answer", "escalate"}
        assert any(gap.kind == "source" for gap in request.gaps)
        original = (
            "The investigation target is the current USER report and any supplied "
            "reproduction/code, displayed as attributed data in the user draft and "
            "maintainer summary. "
        )
        replacement = (
            "The investigation target is the current USER report and any supplied "
            "reproduction/code, displayed as attributed data in the maintainer summary, "
            "with the current USER version and proposed investigation status in the user "
            "draft. "
        )
        assert off["rationale"].count(original) == 1
        assert on["rationale"] == off["rationale"].replace(original, replacement, 1)
    if off["next_question"]:
        assert on["user_draft"] == off["next_question"] or on["user_draft"].startswith(
            off["next_question"] + "\n\n"
        )
    return {
        "decision": off["decision"],
        "off_analysis": off,
        "on_analysis": on,
        "off_draft_chars": len(off["user_draft"]),
        "on_draft_chars": len(on["user_draft"]),
        "changed": off["user_draft"] != on["user_draft"],
        "unchanged_review_summary": off["maintainer_summary"] == on["maintainer_summary"],
        "unchanged_evidence_links": off["evidence_links"] == on["evidence_links"],
        "rationale_presentation_sentence_changed": off["rationale"] != on["rationale"],
        "question_unchanged": off["next_question"] == on["next_question"],
        "source_inventory_is_not_delivered_API_guidance": off["decision"] == "ask"
        and off["user_draft"] != on["user_draft"],
    }, outputs


def build_report(receipt_path):
    raw = receipt_path.read_bytes()
    receipt = json.loads(raw)
    protocol = json.loads((FOLDER / "protocol-v1.json").read_bytes())
    historical = receipt["protocol_id"] == "core-ask-background-model-v1"
    if historical:
        assert sha(raw) == protocol["offline"]["receipt_sha256"]
    else:
        assert receipt["protocol_id"] == "core-json-readability-model-v1"
        method_raw = (FOLDER / "live-method-v1.json").read_bytes()
        assert sha(method_raw) == receipt["registration"]["method_sha256"]
        assert json.loads(method_raw) == receipt["method"]
    fixtures = fixtures_for(ROOT, {"protocol_id": "core-stability-v1"})
    observed = {batch["batch_id"]: batch for batch in receipt["batches"]}
    assert len(observed) == len(receipt["batches"])
    assert set(observed) <= {batch["batch_id"] for batch in receipt["method"]["batches"]}
    rows, attempts = [], []
    for planned_batch in receipt["method"]["batches"]:
        batch = observed.get(planned_batch["batch_id"])
        actual_jobs = {job["job_id"]: job for job in batch["jobs"]} if batch else {}
        assert len(actual_jobs) == (len(batch["jobs"]) if batch else 0)
        assert set(actual_jobs) <= {job["job_id"] for job in planned_batch["jobs"]}
        for attempt in batch["attempts"] if batch else ():
            attempts.append(
                {
                    "context": attempt["context"],
                    "wire_output": attempt.get("wire_output"),
                    "schema_observation": attempt.get("schema_observation"),
                    "canonical_plan_observed": attempt.get("plan") is not None,
                    "error_code": attempt.get("error_code"),
                }
            )
        for planned_job in planned_batch["jobs"]:
            actual_job = actual_jobs.get(planned_job["job_id"])
            if actual_job:
                assert all(actual_job[k] == v for k, v in planned_job.items())
            steps = (
                [step for step in actual_job["steps"] if "request" in step] if actual_job else []
            )
            by_turn = {step["turn"]: step for step in steps}
            assert len(by_turn) == len(steps)
            fixture = fixtures[planned_job.get("fixture_id", planned_job["case_id"])]
            assert set(by_turn) <= {turn["id"] for turn in fixture.data["turns"]}
            for turn in fixture.data["turns"]:
                step = by_turn.get(turn["id"])
                row = {
                    "job_id": planned_job["job_id"],
                    "case_id": planned_job["case_id"],
                    "arm": planned_job["arm"],
                    "round": planned_job["round"],
                    "turn_id": turn["id"],
                    "status": "unvisited" if step is None else "no_fresh_proposal",
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
                        matching = [
                            attempt
                            for attempt in batch["attempts"]
                            if attempt["context"]
                            == handoff.reasoning_context.model_dump(mode="json")
                            and attempt["request"]
                            == handoff.grounded_request.model_dump(mode="json")
                        ]
                        assert len(matching) == 1 and matching[0].get("plan") is not None
                        comparison, outputs = pair(handoff.grounded_request, matching[0]["plan"])
                        assert handoff.analysis == outputs[0 if historical else 1]
                        row.update(
                            status="fresh_proposal",
                            actual_analysis_reconstructed=True,
                            handoff_sha256=handoff.handoff_sha256,
                            **comparison,
                        )
                    else:
                        row["status"] = "stale_observation"
                rows.append(row)
    return {
        "schema_version": 1,
        "review_id": "core-json-readability-paired-render-v1",
        "receipt_sha256": sha(raw),
        "historical_same_plan_replay": historical,
        "new_provider_calls": 0,
        "human_usefulness": None,
        "held_out_test": False,
        "planned_turns": len(rows),
        "turn_statuses": dict(Counter(row["status"] for row in rows)),
        "changed_fresh_drafts": sum(row.get("changed", False) for row in rows),
        "turns": rows,
        "actual_attempts_including_unparsed": attempts,
        "interpretation": "Shorter display is not a model-quality score. Ask source inventories remove full API passages from the released draft; complete quotations remain in unchanged reviewer summary. All answer quotations remain complete. Every planned/stale/unvisited turn and malformed attempt remains.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_report(args.receipt)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(
        json.dumps(
            {key: result[key] for key in ("planned_turns", "turn_statuses", "changed_fresh_drafts")}
        )
    )


if __name__ == "__main__":
    main()
