"""Replay three immutable observed plans; fallback is authored, not a model score."""

import hashlib
import json
from pathlib import Path

from agent_app.contracts import GroundedPlan, GroundedRequest
from agent_app.orchestration import SupportEngine
from agent_app.reasoning.grounding import GroundedReasoner, make_grounded_request
from agent_app.testing.fakes import FakeRetriever
from agent_app.testing.http_pilot_runtime import offline_network

RECEIPT = "experiments/core_resource_guidance_v1/model-live-receipt-v1.json"
RECEIPT_SHA256 = "9658e30a92246b1bdc514aaa944447ad056a81f19fd5de15f103a55fd780c372"


def _normalized(query):
    return " ".join(query.split()).casefold()


def observed_repeat_plans(root):
    """Link original plans to actual caller requests, not just echoed metadata."""
    raw = (Path(root) / RECEIPT).read_bytes()
    if hashlib.sha256(raw).hexdigest() != RECEIPT_SHA256:
        raise ValueError("RepeatReplayArchiveChanged")
    receipt = json.loads(raw)
    selected = []
    for batch in receipt["batches"]:
        for attempt in batch["attempts"]:
            plan = attempt["plan"]
            context = attempt["context"]
            if not plan or plan["decision"] != "retrieve_more" or context["attempt_index"] != 1:
                continue
            job = next(job for job in batch["jobs"] if context["run_id"] in job["run_ids"])
            native = [
                row
                for row in batch["actual_retrievals"]
                if row["job_id"] == job["job_id"]
                and row["executed"]
                and row["executed"]["queries"] == attempt["request"]["evidence"]["queries_used"]
            ]
            if len(native) != 1 or native[0]["logical_retrieval_round"] != 1:
                raise ValueError("RepeatReplayCallerRequestAmbiguous")
            queries = native[0]["executed"]["queries"]
            if not set(map(_normalized, queries)).intersection(
                map(_normalized, plan["retrieval_queries"])
            ):
                continue
            request = GroundedRequest.model_validate(attempt["request"])
            if (
                len(queries) != 1
                or len(request.gaps) != 1
                or request.gaps[0].kind != "source"
                or request.gaps[0].name != "exact_version_documentation"
                or request.conflict_groups
            ):
                raise ValueError("RepeatReplayScopeChanged")
            selected.append((job["job_id"], request, plan, queries[0]))
    if len(selected) != 3:
        raise ValueError("RepeatReplayScopeChanged")
    return selected


class _Planner:
    def __init__(self, original):
        self.original = original
        self.requests = []
        self.contexts = []

    def plan(self, request, *, context):
        self.requests.append(request.model_copy(deep=True))
        self.contexts.append(context.model_copy(deep=True))
        if len(self.requests) == 1:
            return self.original
        # A caller-authored valid fallback establishes repair feasibility only.
        # The actual model's choice and usefulness require a new live comparison.
        return GroundedPlan(context_sha256=request.context_sha256, decision="escalate")


def replay(root):
    observations = []
    with offline_network():
        for job_id, request, plan, actual_query in observed_repeat_plans(root):
            arms = {}
            for enabled in (False, True):
                planner = _Planner(plan)
                retriever = FakeRetriever([request.evidence])

                def factory(case, message, evidence, original=request):
                    return make_grounded_request(
                        case,
                        message,
                        evidence,
                        gaps=original.gaps,
                        conflict_groups=original.conflict_groups,
                    )

                reasoner = GroundedReasoner(
                    planner,
                    request_factory=factory,
                    source_gap_handoff=True,
                    source_gap_investigation=True,
                )
                result = SupportEngine(
                    retriever,
                    reasoner,
                    snapshot_id=request.evidence.snapshot_id,
                    repair_repeated_queries=enabled,
                ).run(
                    request.case,
                    request.user_message,
                    initial_query=actual_query,
                    run_id="replay:" + job_id,
                )
                final_context = planner.contexts[-1]
                checks = {
                    "one_retrieval_only": result.retrieval_rounds == 1,
                    "within_two_model_attempts": result.model_attempts == (2 if enabled else 1),
                    "complete_evidence_preserved": all(
                        recorded == request for recorded in planner.requests
                    ),
                    "expected_status": result.status
                    == ("awaiting_approval" if enabled else "error"),
                    "expected_stop_or_fallback": (
                        result.analysis is not None and result.analysis.decision == "escalate"
                        if enabled
                        else result.error_code == "RepeatedQuery" and result.analysis is None
                    ),
                    "no_user_documentation_question": (
                        result.analysis is None or result.analysis.next_question is None
                    ),
                    "same_evidence_repair_without_refinement_capacity": (
                        not final_context.can_refine
                        and final_context.remaining_model_attempts == 0
                        and final_context.output_feedback is not None
                        and final_context.output_feedback.model_dump(mode="json")
                        == {"issues": [{"code": "invalid_field", "field": "retrieval_queries"}]}
                        if enabled
                        else final_context.output_feedback is None
                    ),
                }
                arms["on" if enabled else "off"] = {
                    "result": result.model_dump(mode="json"),
                    "contexts": [value.model_dump(mode="json") for value in planner.contexts],
                    "checks": checks,
                }
            observations.append(
                {"original_job_id": job_id, "context_sha256": request.context_sha256, "arms": arms}
            )
    checks = [
        passed
        for observation in observations
        for arm in observation["arms"].values()
        for passed in arm["checks"].values()
    ]
    return {
        "protocol_id": "core-repeat-repair-archived-v1",
        "original_receipt": RECEIPT,
        "original_receipt_sha256": RECEIPT_SHA256,
        "observed_plans": 3,
        "authored_escalation_fallback": True,
        "real_model_calls": 0,
        "actual_cost_usd": "0",
        "index_queried": False,
        "source_support_quality_measured": False,
        "quality_claim": False,
        "checks_passed": sum(checks),
        "checks_total": len(checks),
        "accepted": all(checks),
        "observations": observations,
    }
