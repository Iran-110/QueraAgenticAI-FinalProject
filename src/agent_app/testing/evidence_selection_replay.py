"""Offline structural replay of retained selections, not a new model experiment.

Only tracked JSON artifacts are read. Original paid identities, choices and
receipts are not reused or rewritten. New section plans are explicitly authored
span projections, and advisory shortlists are separate deterministic suggestions.
No gateway, ledger, Chroma or tracker client is constructed.
"""

import argparse
import hashlib
import json
import statistics
from dataclasses import asdict
from pathlib import Path

from agent_app.contracts import (
    GroundedRequest,
    OutputIssue,
    ProposalRequirements,
    ReasoningContext,
)
from agent_app.orchestration import SupportEngine
from agent_app.reasoning.claim_plan import (
    ClaimReasoner,
    build_claim_messages,
    build_claim_request,
    parse_claim_plan,
    render_claim_plan,
    validate_claim_request,
)
from agent_app.reasoning.evidence_selection import (
    inspect_claim_selection,
    rank_evidence_units,
    suggest_evidence_units,
)
from agent_app.reasoning.grounding import GroundingRejected, make_grounded_request
from agent_app.reasoning.output import InvalidAnalysis
from agent_app.testing.fakes import FakeRetriever

ROOT = Path(__file__).resolve().parents[3]
PACKET = "experiments/core_evidence_selection_v1"
SNAPSHOTS = "experiments/core_broader_dev_v1/snapshots-v1.json"
RECEIPT = "experiments/core_claim_boundary_v1/model-receipt-v1.json"


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def gateway_input_bytes(messages):
    """Match MetisReasoner's existing JSON framing/escaping guard exactly."""
    return len(json.dumps(messages, ensure_ascii=False).encode("utf-8")) + 1024


def engine_section_preflight(snapshots):
    """Actual engine normal/repair/refinement contexts with authored outcomes.

    These are fixed fake retrieval and synthetic parser failures/escalations,
    not new model choices or successful user conversations. The four-issue
    repair exercises the maximum allowed safe feedback size without a send.
    """
    observations = []
    runs = []
    for snapshot in snapshots:
        registered = GroundedRequest.model_validate(snapshot["catalog_request"])
        for path in ("four_issue_repair", "retrieve_more"):

            class Probe:
                def __init__(self, snapshot_id, path):
                    self.snapshot_id, self.path = snapshot_id, path

                def plan(self, request, *, context):
                    messages = build_claim_messages(request, context)
                    observations.append(
                        {
                            "snapshot_id": self.snapshot_id,
                            "path": self.path,
                            "attempt": context.attempt_index,
                            "feedback_issues": len(context.output_feedback.issues)
                            if context.output_feedback
                            else 0,
                            "input_bytes_plus_existing_1024_guard": gateway_input_bytes(messages),
                            "source_count": len(request.grounded.evidence.hits),
                            "actual_API_calls": 0,
                        }
                    )
                    if context.attempt_index == 1 and self.path == "four_issue_repair":
                        raise InvalidAnalysis(
                            tuple(
                                OutputIssue(code=code)
                                for code in (
                                    "invalid_json",
                                    "missing_field",
                                    "unknown_field",
                                    "invalid_field",
                                )
                            )
                        )
                    refine = context.attempt_index == 1 and self.path == "retrieve_more"
                    return {
                        "context_sha256": request.context_sha256,
                        "decision": "retrieve_more" if refine else "escalate",
                        "passages": [],
                        "user_facts": [],
                        "question_name": None,
                        "retrieval_queries": ["Additional current documentation"] if refine else [],
                    }

            retriever = FakeRetriever([registered.evidence, registered.evidence])
            reasoner = ClaimReasoner(
                Probe(snapshot["id"], path),
                block_mode="sections",
                request_factory=lambda case, message, evidence, registered=registered: (
                    make_grounded_request(
                        case,
                        message,
                        evidence,
                        gaps=registered.gaps,
                        conflict_groups=registered.conflict_groups,
                    )
                ),
            )
            result = SupportEngine(
                retriever,
                reasoner,
                snapshot_id=registered.evidence.snapshot_id,
                proposal_checks=True,
                evidence_scope="all",
                top_k=max(5, len(registered.evidence.hits)),
            ).run(
                registered.case,
                registered.user_message,
                run_id=f"offline-sections-{snapshot['id']}-{path}",
                proposal_requirements=ProposalRequirements.model_validate(
                    snapshot["proposal_requirements"]
                ),
            )
            runs.append(
                {
                    "snapshot_id": snapshot["id"],
                    "path": path,
                    "status": result.status,
                    "error_code": result.error_code,
                    "model_attempts": result.model_attempts,
                    "retrieval_rounds": result.retrieval_rounds,
                    "steps": result.steps,
                    "authored_outcomes_not_model_quality": True,
                }
            )
    return {"contexts": observations, "runs": runs, "actual_API_calls": 0}


def project_selection(original, complete, raw):
    """Author a NEW span projection; never relabel it as model-selected output.

    An invalid old binding is rejected first. Projection only covers already
    selected original spans; it cannot decide which new sources are relevant.
    If one paragraph crosses a section boundary, all overlapping whole units
    are required. Existing selection/render limits still reject excess output.
    """
    original = validate_claim_request(original)
    complete = validate_claim_request(complete)
    if original.grounded != complete.grounded or complete.block_mode != "sections":
        raise GroundingRejected("grounded_context_mismatch")
    plan = parse_claim_plan(raw)
    render_claim_plan(original, plan)
    selections = []
    for source, block in plan.passages:
        old = original.blocks[source][block]
        for unit, span in enumerate(complete.blocks[source]):
            if span.start < old.end and old.start < span.end and (source, unit) not in selections:
                selections.append((source, unit))
    result = {
        **plan.model_dump(mode="json"),
        "context_sha256": complete.context_sha256,
        "passages": selections,
    }
    # Re-parse rather than use unvalidated model_copy(update=...).
    return parse_claim_plan(result)


def _passages(request, plan):
    return [
        {
            "source_index": source,
            "block_index": block,
            "start": request.blocks[source][block].start,
            "end": request.blocks[source][block].end,
            "source_excerpt_sha256": _sha(request.grounded.evidence.hits[source].excerpt.encode()),
        }
        for source, block in plan.passages
    ]


def _contains(request, passages, target):
    # Oracle labels are read ONLY here, after source-derived selection. They
    # never influence units, ranking, model messages or projection.
    return any(
        source == target["source_index"]
        and _sha(request.grounded.evidence.hits[source].excerpt.encode())
        == target["source_full_excerpt_sha256"]
        and request.blocks[source][block].start <= target["start"]
        and request.blocks[source][block].end >= target["end"]
        for source, block in passages
    )


def _baseline_context(row):
    case = row["catalog_request"]["case"]
    return ReasoningContext(
        run_id="offline-selection-baseline",
        case_id=case["case_id"],
        case_revision=case["case_revision"],
        attempt_index=1,
        remaining_model_attempts=1,
        remaining_retrieval_rounds=1,
        can_refine=True,
        proposal_requirements=ProposalRequirements.model_validate(row["proposal_requirements"]),
    )


def replay(root: Path = ROOT):
    folder = root / PACKET
    protocol = json.loads((folder / "protocol-v1.json").read_bytes())
    checks = []

    def check(name, passed):
        checks.append({"name": name, "passed": bool(passed)})

    immutable = {
        path: expected
        for path, expected in protocol["input_pins"].items()
        if not path.startswith("src/")
    }
    before = {path: _sha((root / path).read_bytes()) for path in immutable}
    for path, expected in immutable.items():
        if before[path] != expected:
            raise ValueError("FrozenSelectionInputMismatch")
        check("input_pin:" + path, True)
    snapshots = json.loads((root / SNAPSHOTS).read_bytes())["snapshots"]
    baseline = json.loads((folder / "default-baseline-v1.json").read_bytes())
    expected = {row["snapshot_id"]: row for row in baseline["rows"]}
    check(
        "same16baseline_ids", set(expected) == {s["id"] for s in snapshots} and len(expected) == 16
    )
    current_rows = []
    for snapshot in snapshots:
        grounded = GroundedRequest.model_validate(snapshot["catalog_request"])
        old = build_claim_request(grounded)
        sections = build_claim_request(grounded, block_mode="sections")
        context = _baseline_context(snapshot)
        messages = build_claim_messages(old, context)
        original = {
            "context_sha256": old.context_sha256,
            "decision": "escalate",
            "passages": [[0, 0]] if old.blocks else [],
            "user_facts": [],
            "question_name": None,
            "retrieval_queries": [],
        }
        rendered = render_claim_plan(old, original)
        actual = {
            "snapshot_id": snapshot["id"],
            "claim_context_sha256": old.context_sha256,
            "messages_sha256": _sha(_encoded(messages)),
            "rendered_sha256": _sha(rendered.model_dump_json().encode()),
        }
        check("default_byte_parity:" + snapshot["id"], actual == expected[snapshot["id"]])
        source_equal = all(
            "".join(hit.excerpt[span.start : span.end] for span in sections.blocks[i])
            == hit.excerpt
            for i, hit in enumerate(grounded.evidence.hits)
        )
        check("whole_sources:" + snapshot["id"], source_equal)
        section_messages = build_claim_messages(sections, context)
        # Match the existing gateway, including JSON escaping/framing overhead.
        size = gateway_input_bytes(section_messages)
        check("section_full_input_bound:" + snapshot["id"], size <= 32768)
        shortlist = suggest_evidence_units(sections)
        current_rows.append(
            {
                "snapshot_id": snapshot["id"],
                "paragraph_units": sum(len(spans) for spans in old.blocks),
                "section_units": sum(len(spans) for spans in sections.blocks),
                "all_source_bytes_retained": source_equal,
                "messages_bytes_plus_existing_1024_guard": size,
                "independent_advisory_shortlist": asdict(shortlist),
                "lexical_hints": [asdict(h) for h in rank_evidence_units(sections)],
                "not_a_model_decision_or_proposal": True,
            }
        )
    engine = engine_section_preflight(snapshots)
    check("all64actual_engine_normal_repair_refinement_contexts", len(engine["contexts"]) == 64)
    check(
        "all_engine_full_inputs_within_unchanged_gateway_guard",
        all(row["input_bytes_plus_existing_1024_guard"] <= 32768 for row in engine["contexts"]),
    )
    check(
        "all16_max_four_issue_repairs_exercised",
        sum(row["feedback_issues"] == 4 for row in engine["contexts"]) == 16,
    )
    check(
        "all32bounded_authored_runs",
        len(engine["runs"]) == 32
        and all(
            row["model_attempts"] == 2
            and row["retrieval_rounds"] <= 2
            and row["steps"] <= 8
            and row["status"] == "awaiting_approval"
            for row in engine["runs"]
        ),
    )
    receipt = json.loads((root / RECEIPT).read_bytes())
    inventory = json.loads((folder / "failure-inventory-v1.json").read_bytes())
    observations = {
        row["original_receipt"].get("attempt_json_pointer"): row
        for row in inventory["observed_inventory"]
        if row["original_receipt"]["path"] == RECEIPT
    }
    retained = []
    unavailable = 0
    for bi, batch in enumerate(receipt["batches"]):
        for ai, attempt in enumerate(batch["attempts"]):
            if "claim_plan" not in attempt:
                continue
            if attempt["claim_plan"] is None:
                unavailable += 1
                continue
            pointer = f"/batches/{bi}/attempts/{ai}"
            old = build_claim_request(GroundedRequest.model_validate(attempt["request"]))
            sections = build_claim_request(old.grounded, block_mode="sections")
            plan = parse_claim_plan(attempt["claim_plan"])
            row = {
                "original_receipt": RECEIPT,
                "attempt_pointer": pointer,
                "original_model_plan_unchanged": True,
                "original_rendered_final_available": attempt["rendered_analysis"] is not None,
                "old_binding_sha256": old.context_sha256,
                "old_passages": plan.model_dump(mode="json")["passages"],
                "human_usefulness": None,
                "new_model_calls": 0,
            }
            try:
                prior = render_claim_plan(old, plan)
                row["original_valid"] = True
                row["original_render_sha256"] = _sha(prior.model_dump_json().encode())
                row["original_draft_characters"] = len(prior.user_draft)
                row["original_advisory"] = inspect_claim_selection(old, plan)
                projection = project_selection(old, sections, plan)
                new = render_claim_plan(sections, projection)
                row.update(
                    authored_projection_valid=True,
                    authored_projection_not_model_output=True,
                    projection_passages=projection.model_dump(mode="json")["passages"],
                    projection_spans=_passages(sections, projection),
                    projection_draft_characters=len(new.user_draft),
                    projection_advisory=inspect_claim_selection(sections, projection),
                    projection_decision_unchanged=new.decision == prior.decision,
                    ask_draft_unchanged=(new.user_draft == prior.user_draft)
                    if plan.decision == "ask"
                    else None,
                )
                observation = observations.get(pointer)
                if observation and observation.get("available_but_omitted_review_context"):
                    shortlist = suggest_evidence_units(sections)
                    row["posthoc_observed_span_controls"] = [
                        {
                            "target_source": target["source_index"],
                            "target_start": target["start"],
                            "target_end": target["end"],
                            "source_full_excerpt_sha256": target["source_full_excerpt_sha256"],
                            "original_covers_whole_span": _contains(old, plan.passages, target),
                            "projection_covers_whole_span": _contains(
                                sections, projection.passages, target
                            ),
                            "independent_shortlist_covers_whole_span": _contains(
                                sections, shortlist.passages, target
                            ),
                            "not_a_semantic_quality_label": True,
                        }
                        for target in observation["available_but_omitted_review_context"]
                    ]
            except GroundingRejected as error:
                # A failed original binding never becomes a projection success.
                if "original_valid" not in row:
                    row["original_valid"] = False
                    row["original_error"] = error.code
                    row["authored_projection_attempted"] = False
                else:
                    row["authored_projection_valid"] = False
                    row["projection_error"] = error.code
            retained.append(row)
    check(
        "all10retained_and21unavailable_claim_attempts", len(retained) == 10 and unavailable == 21
    )
    check(
        "original_final7_and_rejected3_preserved",
        sum(row["original_rendered_final_available"] for row in retained) == 7
        and sum(not row["original_valid"] for row in retained) == 3,
    )
    check(
        "same_decisions_for_rendered_projections",
        all(
            row["projection_decision_unchanged"]
            for row in retained
            if row.get("authored_projection_valid")
        ),
    )
    check(
        "canonical_question_preserved",
        any(row.get("ask_draft_unchanged") is True for row in retained)
        and all(
            row["ask_draft_unchanged"] is not False
            for row in retained
            if "ask_draft_unchanged" in row
        ),
    )
    after = {path: _sha((root / path).read_bytes()) for path in immutable}
    check("all_frozen_input_bytes_unchanged", before == after)
    projected = [row for row in retained if row.get("authored_projection_valid")]
    return {
        "schema_version": 1,
        "task": "C4k/E2x",
        "kind": "posthoc_authored_offline_structural_replay_and_advisory",
        "actual_API_calls": 0,
        "ledger_or_native_index_access": False,
        "input_pins": before,
        "default_baseline_sha256": _sha((folder / "default-baseline-v1.json").read_bytes()),
        "snapshot_preflights": current_rows,
        "actual_engine_preflights": engine,
        "retained_claim_candidates": retained,
        "retained_claim_plans": len(retained),
        "unavailable_raw_claim_attempts_not_reconstructed": unavailable,
        "original_finals": sum(row["original_rendered_final_available"] for row in retained),
        "original_binding_rejections": sum(not row["original_valid"] for row in retained),
        "authored_projection_successes": len(projected),
        "authored_projection_errors": sum(
            row.get("authored_projection_valid") is False for row in retained
        ),
        "median_original_draft_characters_for_projected_subset": statistics.median(
            row["original_draft_characters"] for row in projected
        )
        if projected
        else None,
        "median_projected_draft_characters_same_subset": statistics.median(
            row["projection_draft_characters"] for row in projected
        )
        if projected
        else None,
        "checks": checks,
        "checks_passed": sum(row["passed"] for row in checks),
        "checks_total": len(checks),
        "all_checks_passed": all(row["passed"] for row in checks),
        "model_selection_improvement_claim": False,
        "semantic_relevance_or_entailment_proven": False,
        "human_usefulness": None,
        "real_RAG_or_held_out_test": False,
        "production_defaults_promoted": False,
        "limitations": [
            "Projection is authored after observing failures; it is not new model output.",
            "Whole sections may grow output and keep irrelevant, malicious or widget-only text.",
            "A peer/cross-source qualifier can still be omitted; structural subtree is not semantic completeness.",
            "Lexical scores are inspection hints, with false positives, synonyms and historical message contamination possible.",
            "All old errors, unavailable raw attempts, unvisited states and human-null labels remain unchanged.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = replay()
    # Exclusive creation prevents overwriting original or earlier receipts.
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(
        json.dumps(
            {
                "checks_passed": report["checks_passed"],
                "checks_total": report["checks_total"],
                "actual_API_calls": 0,
                "model_quality_claim": False,
            }
        )
    )
    return 0 if report["all_checks_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
