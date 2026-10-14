"""Read-only observations for controlled development-model receipts.

This does not grade entailment or usefulness. Exact reconstruction establishes
what the configured renderer produced, not whether selected sources answer the
question. Full current sources, questions and output surfaces remain available
for a separately declared semantic review.
"""

import hashlib
import json
from collections import Counter, defaultdict
from itertools import combinations

from agent_app.contracts import AnalysisResult, GroundedPlan, GroundedRequest, ReasoningContext
from agent_app.reasoning.grounding import (
    render_grounded_plan,
    source_content_sha256,
    source_scope,
)

__all__ = ["StabilityReviewRejected", "summarize_receipt"]

_ANALYSIS_FIELDS = tuple(AnalysisResult.model_fields)
_DECISIONS = frozenset(("answer", "ask", "escalate", "retrieve_more"))
_ERROR_CODES = frozenset(
    (
        "BudgetExceeded",
        "ContextLimitExceeded",
        "CostBoundExceeded",
        "DuplicateModelRequest",
        "LedgerUnavailable",
        "ProviderModelMismatch",
        "ProviderRequestFailed",
        "ProviderResponseInvalid",
        "ProviderUsageUnknown",
    )
)


class StabilityReviewRejected(ValueError):
    def __init__(self):
        super().__init__("StabilityReviewRejected")


def _hash(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _list(value):
    if type(value) is not list:
        raise StabilityReviewRejected()
    return value


def _dict(value):
    if type(value) is not dict:
        raise StabilityReviewRejected()
    return value


def _identity(value):
    if type(value) is not str or not value or len(value) > 256:
        raise StabilityReviewRejected()
    return value


def _attempt_observation(attempt):
    context = ReasoningContext.model_validate(attempt["context"])
    observed = attempt.get("schema_observation")
    validity = observed.get("syntactic_valid") if type(observed) is dict else None
    if validity is not None and type(validity) is not bool:
        raise StabilityReviewRejected()
    parsed = attempt.get("plan")
    plan = GroundedPlan.model_validate(parsed) if parsed is not None else None
    error = attempt.get("error_code")
    return {
        "run_id": context.run_id,
        "case_revision": context.case_revision,
        "attempt_index": context.attempt_index,
        "syntactic_valid": validity,
        "parsed_plan_present": plan is not None,
        "plan_decision": plan.decision if plan else None,
        "error_code": error if error is None or error in _ERROR_CODES else "UnclassifiedStop",
        "request_sha256": _hash(attempt["request"]),
        "output_sha256": attempt.get("output_sha256"),
    }


def _counts(observations):
    counts = Counter(item["syntactic_valid"] for item in observations)
    return {
        "observed_attempts": len(observations),
        "schema_valid": counts[True],
        "schema_invalid": counts[False],
        "schema_unobserved": counts[None],
        "plan_decisions": dict(
            sorted(
                Counter(
                    item["plan_decision"] for item in observations if item["plan_decision"]
                ).items()
            )
        ),
        "errors": dict(
            sorted(
                Counter(item["error_code"] for item in observations if item["error_code"]).items()
            )
        ),
    }


def _proposal_review(step, attempts):
    proposal = _dict(step.get("proposal", {}))
    if not proposal.get("proposal_id"):
        return {
            "turn_id": step.get("turn"),
            "proposal_present": False,
            "render_verification": "NoTerminalProposal",
            "semantic_admissibility": None,
        }
    handoff = _dict(proposal.get("review_handoff", {}))
    context = ReasoningContext.model_validate(handoff["reasoning_context"])
    request = GroundedRequest.model_validate(handoff["grounded_request"])
    candidates = [
        attempt
        for attempt in attempts
        if attempt["context"] == context.model_dump(mode="json") and attempt.get("plan") is not None
    ]
    matching_request = len(candidates) == 1 and candidates[0]["request"] == request.model_dump(
        mode="json"
    )
    verification = {
        "matching_recorded_attempt": len(candidates) == 1,
        "enriched_request_matches_handoff": matching_request,
        "proposal_analysis_matches": False,
        "handoff_analysis_matches": False,
        "top_level_analysis_surfaces_match": False,
        "all_recorded_analysis_fields_present": set(_ANALYSIS_FIELDS)
        <= set(proposal.get("analysis", {})),
        "recorded_released_outputs_match_unedited_draft": None,
        "rendered_with_source_gap_handoff": True,
        "render_rejected": False,
    }
    rendered = None
    baseline = None
    plan = None
    if matching_request:
        plan = GroundedPlan.model_validate(candidates[0]["plan"])
        try:
            rendered = render_grounded_plan(request, plan, source_gap_handoff=True)
            baseline = render_grounded_plan(request, plan)
        except ValueError:
            verification["render_rejected"] = True
    if rendered is not None:
        expected = rendered.model_dump(mode="json")
        verification["proposal_analysis_matches"] = proposal.get("analysis") == expected
        verification["handoff_analysis_matches"] = handoff.get("analysis") == expected
        # evidence_links are exposed through analysis/evidence rather than a
        # same-named top-level proposal field; all other analysis fields are direct.
        fields = [field for field in _ANALYSIS_FIELDS if field != "evidence_links"]
        verification["top_level_analysis_surfaces_match"] = all(
            field in proposal and proposal[field] == expected[field] for field in fields
        )
        released = _list(step.get("released_outputs", []))
        if step.get("edited_proposal") is None:
            verification["recorded_released_outputs_match_unedited_draft"] = (
                all(
                    item.get("role") == "assistant" and item.get("text") == expected["user_draft"]
                    for item in released
                )
                if released
                else None
            )
    sources = [
        {
            **hit.model_dump(mode="json"),
            "content_sha256": source_content_sha256(hit),
            "version_scope": source_scope(request.case, hit),
            "selected_by_model": bool(
                plan and any(ref.chunk_id == hit.chunk_id for ref in plan.sources)
            ),
            "rendered_as_evidence_link": bool(
                rendered and any(ref.chunk_id == hit.chunk_id for ref in rendered.evidence_links)
            ),
        }
        for hit in request.evidence.hits
    ]
    question = next((gap for gap in request.gaps if plan and gap.name == plan.question_name), None)
    active = [
        fact.model_dump(mode="json")
        for fact in request.case.facts
        if fact.status == "active" and fact.provenance_kind == "user"
    ]
    return {
        "turn_id": step.get("turn"),
        "proposal_id": proposal["proposal_id"],
        "proposal_present": True,
        "case_revision": context.case_revision,
        "decision": proposal.get("decision"),
        "render_verification": verification,
        "analysis": proposal.get("analysis"),
        "proposal_surfaces": {
            field: proposal.get(field) for field in _ANALYSIS_FIELDS if field != "evidence_links"
        },
        "handoff_analysis": handoff.get("analysis"),
        "edited_proposal": step.get("edited_proposal"),
        "released_outputs": step.get("released_outputs", []),
        "user_message": request.user_message,
        "all_current_sources": sources,
        "model_selected_source_references": plan.model_dump(mode="json")["sources"]
        if plan
        else None,
        "active_user_facts": active,
        "superseded_facts": [
            fact.model_dump(mode="json") for fact in request.case.facts if fact.status != "active"
        ],
        "checks_performed": list(request.case.checks_performed),
        "unknowns": list(request.case.unknowns),
        "caller_registered_gaps": [gap.model_dump(mode="json") for gap in request.gaps],
        "caller_declared_conflict_groups": [list(group) for group in request.conflict_groups],
        "question_observations": {
            "selected_registered_gap": question.model_dump(mode="json") if question else None,
            "selected_gap_is_user_kind": question.kind == "user" if question else None,
            "selected_gap_repeats_active_user_fact": (
                any(fact["name"].casefold() == question.name.casefold() for fact in active)
                if question
                else None
            ),
            "question_matches_registered_canonical_text": (
                proposal.get("next_question") == question.question
                and proposal.get("user_draft") == question.question
                if question
                else None
            ),
            "necessity_review": None,
            "user_answerability_review": None,
        },
        "qualification_observations": {
            "source_gap_handoff_changes_renderer_output": (
                rendered != baseline if rendered is not None else None
            ),
            "source_gap_names": [gap.name for gap in request.gaps if gap.kind == "source"],
            "cause_fix_execution_claim_review": None,
            "material_claim_entailment_review": None,
        },
        "semantic_admissibility": None,
        "unnecessary_abstention_review": None,
        "human_reviewed": False,
        "human_usefulness": None,
    }


def _summarize(receipt, strata):
    jobs, observations, paired = [], [], []
    batches = _list(_dict(receipt)["batches"])
    all_run_ids = set()
    batch_ids = set()
    for batch in batches:
        batch = _dict(batch)
        batch_id = _identity(batch["batch_id"])
        if batch_id in batch_ids:
            raise StabilityReviewRejected()
        batch_ids.add(batch_id)
        attempt_records = _list(batch["attempts"])
        batch_jobs = _list(batch["jobs"])
        owner = {}
        job_ids = set()
        for job in batch_jobs:
            job = _dict(job)
            job_id = _identity(job["job_id"])
            if job_id in job_ids:
                raise StabilityReviewRejected()
            job_ids.add(job_id)
            for run_id in _list(job["run_ids"]):
                run_id = _identity(run_id)
                if run_id in all_run_ids:
                    raise StabilityReviewRejected()
                owner[run_id] = (job_id, job["case_id"])
                all_run_ids.add(run_id)
        indexed = defaultdict(list)
        attempt_ids = set()
        for attempt in attempt_records:
            attempt = _dict(attempt)
            observation = _attempt_observation(attempt)
            if (
                observation["run_id"] not in owner
                or attempt["context"]["case_id"] != owner[observation["run_id"]][1]
                or (observation["run_id"], observation["attempt_index"]) in attempt_ids
            ):
                raise StabilityReviewRejected()
            attempt_ids.add((observation["run_id"], observation["attempt_index"]))
            observation.update({"batch_id": batch_id, "job_id": owner[observation["run_id"]][0]})
            observations.append(observation)
            indexed[owner[observation["run_id"]][0]].append(attempt)
        groups = defaultdict(list)
        for job in batch_jobs:
            case_id, arm = _identity(job["case_id"]), _identity(job["arm"])
            job_id = job["job_id"]
            if type(job["coverage_complete"]) is not bool:
                raise StabilityReviewRejected()
            job_observations = [
                item
                for item in observations
                if item["batch_id"] == batch_id and item["job_id"] == job_id
            ]
            first = [item for item in job_observations if item["attempt_index"] == 1]
            initial = [
                attempt
                for attempt in indexed[job_id]
                if attempt["context"]["attempt_index"] == 1
                and attempt["context"]["case_revision"] == 1
            ]
            if len(initial) > 1:
                raise StabilityReviewRejected()
            if initial:
                groups[(job.get("round"), case_id)].append(
                    {"arm": arm, "job_id": job_id, "request_sha256": _hash(initial[0]["request"])}
                )
            checks = _list(job["checks"])
            steps = _list(job["steps"])
            review = [_proposal_review(step, indexed[job_id]) for step in steps if "usage" in step]
            jobs.append(
                {
                    "batch_id": batch_id,
                    "kind": batch.get("kind"),
                    "job_id": job_id,
                    "arm": arm,
                    "round": job.get("round"),
                    "case_id": case_id,
                    "stratum": strata.get(case_id, "unspecified"),
                    "fixture_id": job.get("fixture_id"),
                    "fixture_sha256": job.get("fixture_sha256"),
                    "coverage_complete": job["coverage_complete"],
                    "selected_turns": job.get("selected_turns", []),
                    "mechanical_checks": {
                        "count": len(checks),
                        "passed": sum(item.get("passed") is True for item in checks),
                        "failed_or_unobserved": sum(
                            item.get("passed") is not True for item in checks
                        ),
                    },
                    "first_attempts": _counts(first),
                    "all_attempts": _counts(job_observations),
                    "attempt_observations": job_observations,
                    "terminal_decisions": dict(
                        sorted(
                            Counter(
                                step.get("proposal", {}).get("decision")
                                for step in steps
                                if step.get("proposal", {}).get("decision")
                                in _DECISIONS - {"retrieve_more"}
                            ).items()
                        )
                    ),
                    "proposal_reviews": review,
                }
            )
        for (round_id, case_id), members in sorted(groups.items(), key=lambda item: str(item[0])):
            for left, right in combinations(members, 2):
                if left["arm"] == right["arm"]:
                    raise StabilityReviewRejected()
                paired.append(
                    {
                        "batch_id": batch_id,
                        "round": round_id,
                        "case_id": case_id,
                        "arms": [left["arm"], right["arm"]],
                        "jobs": [left["job_id"], right["job_id"]],
                        "request_sha256": [left["request_sha256"], right["request_sha256"]],
                        "current_initial_request_equal": left["request_sha256"]
                        == right["request_sha256"],
                    }
                )
    arm_totals = {}
    for arm in sorted({job["arm"] for job in jobs}):
        selected = [job for job in jobs if job["arm"] == arm]
        selected_ids = {(job["batch_id"], job["job_id"]) for job in selected}
        attempts = [
            item for item in observations if (item["batch_id"], item["job_id"]) in selected_ids
        ]
        arm_totals[arm] = {
            "case_arm_jobs": len(selected),
            "conditional_routes_completed": sum(job["coverage_complete"] for job in selected),
            "first_attempts": _counts([item for item in attempts if item["attempt_index"] == 1]),
            "all_attempts": _counts(attempts),
            "by_stratum": {
                stratum: {
                    "case_arm_jobs": sum(job["stratum"] == stratum for job in selected),
                    "conditional_routes_completed": sum(
                        job["coverage_complete"] for job in selected if job["stratum"] == stratum
                    ),
                    "first_attempts": _counts(
                        [
                            item
                            for job in selected
                            if job["stratum"] == stratum
                            for item in job["attempt_observations"]
                            if item["attempt_index"] == 1
                        ]
                    ),
                    "all_attempts": _counts(
                        [
                            item
                            for job in selected
                            if job["stratum"] == stratum
                            for item in job["attempt_observations"]
                        ]
                    ),
                }
                for stratum in sorted({job["stratum"] for job in selected})
            },
        }
    return {
        "schema_version": 1,
        "review_kind": "read_only_mechanical_receipt_observations",
        "receipt_sha256": _hash(receipt),
        "quality_claim": False,
        "actual_rag_quality": False,
        "final_test_quality": False,
        "human_reviewed": False,
        "human_usefulness": None,
        "semantic_admissibility": None,
        "renderer_mode": "same_source_gap_handoff_true_for_both_arms",
        "arm_totals": arm_totals,
        "common_initial_state_comparisons": paired,
        "jobs": jobs,
        "limitations": [
            "Schema validity, route completion and exact rendering are distinct observations; none grades entailment or usefulness.",
            "Unreached continuation turns remain unobserved; early registered terminal routes are not equivalent to two-turn paths.",
            "Complete current excerpts are untrusted attributed input; hashes and matching metadata do not authenticate their claims.",
            "Semantic adequacy, question necessity, unnecessary abstention and human usefulness require a separately declared review.",
        ],
    }


def summarize_receipt(receipt, *, strata=None):
    """Inspect only supplied recorded data; never read credentials or call APIs.

    Malformed receipt diagnostics use a fixed code and never include provider
    text or validation inputs. Full valid source/output records are intentional
    review material, not error diagnostics.
    """
    try:
        return _summarize(receipt, _dict(strata if strata is not None else {}))
    except Exception:
        raise StabilityReviewRejected() from None
