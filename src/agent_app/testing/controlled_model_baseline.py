"""Registered fixed-evidence development baseline, never a RAG or held-out score.

The six inputs share an exposed Issue family. Actual model choices are recorded
separately from authored mock plumbing. An existing immutable continuation may
fund fewer than all six: every attempt independently checks its full reservation.
"""

import argparse
import io
import json
import re
import subprocess
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import get_args
from uuid import uuid4

import httpx

from agent_app.contracts import (
    AnalysisResult,
    EvidenceBundle,
    OutputFeedback,
    OutputIssue,
    ReasoningContext,
    RunLimits,
)
from agent_app.evaluation.live import _DecodedStream
from agent_app.llm.budget import BudgetLedger
from agent_app.llm.config import METIS_CHAT_URL, MetisConfig
from agent_app.llm.grounded import MetisGroundedPlanner
from agent_app.llm.metis import request_id_for
from agent_app.llm.pricing import get_price
from agent_app.orchestration import SupportEngine
from agent_app.orchestration.handoff import ReasoningCapture, build_handoff
from agent_app.orchestration.ports import ReasoningStopCode, ReasoningStopped
from agent_app.reasoning.grounding import (
    GroundedReasoner,
    build_grounded_messages,
    parse_grounded_plan,
    source_content_sha256,
)
from agent_app.reasoning.output import InvalidAnalysis
from agent_app.testing.retrieval_context_live_probe import (
    GRANT,
    INPUT_RESERVE,
    MODEL,
    OUTPUT_LIMIT,
    REQUEST_BOUND,
    _credential,
    _immutable_accounting_preserved,
    _new_request_accounting,
    _plain,
    _sha,
    ledger_observation,
)

ROOT = Path(__file__).resolve().parents[3]
PROTOCOL = Path("experiments/controlled_model_baseline/protocol-v1.json")
PROTOCOL_ID = "controlled-model-baseline-v1"
EXPERIMENT_ID = "controlled-model-baseline-2026-10-13-v1"
BATCH_CAP = Decimal("0.00491479")
MAX_SENDS = 6
TOP_K = 5
_CONDITION_IDS = (
    "controlled-v8-full",
    "controlled-v8-key-evidence-removed",
    "controlled-v8-unknown-version-mixed",
    "controlled-v8-version-correction",
    "controlled-v8-same-version-synthetic-conflict",
    "controlled-v8-refinement-stale-source",
)


@dataclass(frozen=True, slots=True)
class ExecutionPolicy:
    """Two fixed operator configurations; neither is selected by model content."""

    protocol_path: Path
    protocol_id: str
    experiment_id: str
    condition_ids: tuple[str, ...]
    input_reserve: int
    output_limit: int
    request_bound: Decimal
    batch_cap: Decimal
    max_sends: int


BASELINE = ExecutionPolicy(
    PROTOCOL,
    PROTOCOL_ID,
    EXPERIMENT_ID,
    _CONDITION_IDS,
    INPUT_RESERVE,
    OUTPUT_LIMIT,
    REQUEST_BOUND,
    BATCH_CAP,
    MAX_SENDS,
)
OUTPUT_CAP_FOLLOWUP = ExecutionPolicy(
    Path("experiments/controlled_model_baseline/output-cap-followup-v1.json"),
    "controlled-output-cap-followup-v1",
    "controlled-output-cap-2026-10-13-v1",
    ("controlled-v8-unknown-version-mixed",),
    15360,
    512,
    Decimal("0.002872320"),
    Decimal("0.002909545"),
    1,
)
LIMITS = {
    "max_model_attempts": 2,
    "max_retrieval_rounds": 2,
    "max_queries_per_round": 2,
    "max_steps": 8,
}
_TERMINAL = frozenset(
    {
        "ProviderRequestFailed",
        "ProviderResponseInvalid",
        "ProviderUsageUnknown",
        "ProviderModelMismatch",
        "ContextLimitExceeded",
        "DuplicateModelRequest",
        "LedgerUnavailable",
        "LiveCallsDisabled",
        "UnknownPricing",
        "BudgetExceeded",
        "CostBoundExceeded",
    }
)


class BaselineRejected(ValueError):
    def __init__(self):
        super().__init__("ControlledModelBaselineRejected")


def _inputs():
    from agent_app.testing import controlled_decision_inputs

    return controlled_decision_inputs


def _validated_policy(policy):
    if type(policy) is not ExecutionPolicy or policy not in (BASELINE, OUTPUT_CAP_FOLLOWUP):
        raise BaselineRejected()
    if get_price(MODEL).cost(policy.input_reserve, policy.output_limit) != policy.request_bound:
        raise BaselineRejected()
    return policy


def _gateway_policy(policy=BASELINE):
    policy = _validated_policy(policy)
    return {
        "model": MODEL,
        "phase": "development",
        "input_token_reserve": policy.input_reserve,
        "max_output_tokens": policy.output_limit,
        "max_request_usd": str(policy.request_bound),
        "batch_actual_cost_cap_usd": str(policy.batch_cap),
        "max_actual_sends_including_repair": policy.max_sends,
    }


def _source_paths(root, fixture_pins, review_relative, policy=BASELINE):
    return sorted(
        set(
            [str(path.relative_to(root)) for path in (root / "src/agent_app").rglob("*.py")]
            + [
                "scripts/controlled_model_baseline.py",
                str(policy.protocol_path),
                fixture_pins["suite_path"],
                fixture_pins["protocol_path"],
                review_relative,
                "pyproject.toml",
                "uv.lock",
            ]
        )
    )


def source_observation(root, fixture_pins, review_relative, policy=BASELINE):
    policy = _validated_policy(policy)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    upstream = subprocess.check_output(
        ["git", "rev-parse", "@{upstream}"], cwd=root, text=True, stderr=subprocess.DEVNULL
    ).strip()
    return {
        "source_commit": head,
        "upstream_commit": upstream,
        "source_clean": not subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=root, text=True
        ).strip(),
        "source_pushed": head == upstream,
        "source_hashes": {
            relative: _sha((root / relative).read_bytes())
            for relative in _source_paths(root, fixture_pins, review_relative, policy)
        },
    }


def load_registration(root, ledger_path, policy=BASELINE):
    policy = _validated_policy(policy)
    raw = (root / policy.protocol_path).read_bytes()
    protocol = json.loads(raw)
    if policy == OUTPUT_CAP_FOLLOWUP and (
        type(protocol.get("baseline_prompt_sha256")) is not str
        or re.fullmatch(r"[0-9a-f]{64}", protocol["baseline_prompt_sha256"]) is None
    ):
        raise BaselineRejected()
    fixture_pins = _inputs().registration_inputs()
    conditions = _inputs().load_conditions()
    full_order = [condition.condition_id for condition in conditions]
    order = list(policy.condition_ids)
    review_relative = protocol["review_pins"]["path"]
    review_path = (root / review_relative).resolve()
    if not review_path.is_relative_to(root.resolve()) or review_path.suffix != ".json":
        raise BaselineRejected()
    review_bytes = review_path.read_bytes()
    review_order = json.loads(review_bytes)["ordered_condition_ids"]
    before = ledger_observation(ledger_path)
    source = source_observation(root, fixture_pins, review_relative, policy)
    if (
        protocol["protocol_id"] != policy.protocol_id
        or protocol["experiment_id"] != policy.experiment_id
        or re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", protocol["experiment_id"]) is None
        or protocol["continuation_id"] != GRANT
        or protocol["ledger"]["path"] != "runtime/budget.sqlite3"
        or Path(ledger_path).resolve() != (root / "runtime/budget.sqlite3").resolve()
        or protocol["ledger"]["sha256_before"] != before["fingerprints"]["db"]
        or protocol["ledger"]["unknown_records_sha256"] != before["unknown_records_sha256"]
        or not before["halted"]
        or Decimal(before["limit_usd"]) != Decimal("4.5")
        or before["counts"].get("reserved", 0)
        or before["counts"].get("uncertain", 0) != 1
        or before["unknown_models"] != ["gpt-4.1-mini"]
        or before["unknown_error_codes"] != ["ProviderModelMismatch"]
        or Decimal(before["uncertain_usd"]) != Decimal("0.02")
        or Decimal(before["limit_usd"])
        - Decimal(before["opening_usd"])
        - Decimal(before["settled_estimated_usd"])
        - Decimal(before["reserved_usd"])
        - Decimal(before["uncertain_usd"])
        < policy.request_bound
        or not before["continuation"]["active"]
        or before["continuation"]["allowed_model"] != MODEL
        or Decimal(before["continuation"]["remaining_usd"]) != policy.batch_cap
        or protocol["gateway"] != _gateway_policy(policy)
        or protocol["limits"] != LIMITS
        or protocol["evidence_scope"] != "all"
        or protocol["top_k"] != TOP_K
        or protocol["fixture_pins"] != fixture_pins
        or protocol["ordered_condition_ids"] != order
        or tuple(full_order) != _CONDITION_IDS
        or review_order != full_order
        or _sha(review_bytes) != protocol["review_pins"]["sha256"]
        or not source["source_clean"]
        or not source["source_pushed"]
    ):
        raise BaselineRejected()
    for relative, expected in protocol["source_pins"].items():
        if source["source_hashes"].get(relative) != expected:
            raise BaselineRejected()
    for relative, expected in source["source_hashes"].items():
        committed = subprocess.check_output(
            ["git", "show", f"HEAD:{relative}"], cwd=root, stderr=subprocess.DEVNULL
        )
        if _sha(committed) != expected:
            raise BaselineRejected()
    return protocol, {
        **source,
        "protocol_sha256": _sha(raw),
        "fixture_pins": fixture_pins,
        "review_pins": protocol["review_pins"],
        "ordered_condition_ids": order,
        "ledger_before": before,
        "execution_policy": "baseline" if policy == BASELINE else "output_cap_followup",
        "gateway": _gateway_policy(policy),
    }


def _prompt_size(request, context):
    messages = build_grounded_messages(request, context)
    encoded = json.dumps(messages, ensure_ascii=False).encode()
    return len(encoded) + 1024, _sha(encoded)


def prepare(conditions=None, *, policy=BASELINE):
    """Size both frozen rounds and the largest repair-code frame before any key."""
    policy = _validated_policy(policy)
    conditions = tuple(
        conditions
        if conditions is not None
        else (
            item
            for item in _inputs().load_conditions()
            if item.condition_id in policy.condition_ids
        )
    )
    if tuple(item.condition_id for item in conditions) != policy.condition_ids:
        raise BaselineRejected()
    longest = max(get_args(OutputIssue.model_fields["code"].annotation), key=len)
    repair = OutputFeedback(issues=tuple(OutputIssue(code=longest) for _ in range(8)))
    prepared = []
    for condition in conditions:
        if condition.case.pending_proposal_id is not None or len(condition.bundles) != 2:
            raise BaselineRejected()
        if any(len(bundle.hits) > TOP_K for bundle in condition.bundles):
            raise BaselineRejected()
        requests, prompts = [], []
        for round_index, original in enumerate(condition.bundles, 1):
            evidence = EvidenceBundle.model_validate(
                {**original.model_dump(), "retrieval_round": round_index}
            )
            request = _inputs().grounded_request(
                condition, condition.case, condition.user_message, evidence
            )
            requests.append(request)
            variants = [(1, None)] if round_index == 1 else []
            variants.append((2, repair if round_index == 1 else None))
            for attempt, feedback in variants:
                context = ReasoningContext(
                    run_id="controlled-baseline-dry",
                    case_id=condition.case.case_id,
                    case_revision=condition.case.case_revision,
                    attempt_index=attempt,
                    output_feedback=feedback,
                    remaining_model_attempts=2 - attempt,
                    remaining_retrieval_rounds=2 - round_index,
                    can_refine=attempt == 1,
                    query_limit=2,
                )
                size, digest = _prompt_size(request, context)
                if size > policy.input_reserve:
                    raise BaselineRejected()
                prompts.append(
                    {
                        "retrieval_round": round_index,
                        "attempt_index": attempt,
                        "repair_frame": feedback is not None,
                        "prompt_bytes_plus_margin": size,
                        "prompt_sha256": digest,
                        "grounded_context_sha256": request.context_sha256,
                    }
                )
        prepared.append({"condition": condition, "requests": tuple(requests), "prompts": prompts})
    return tuple(prepared)


class _ScopedTransport(httpx.BaseTransport):
    def __init__(self, underlying, ledger, before, source_guard, policy=BASELINE):
        self.underlying, self.ledger, self.before = underlying, ledger, before
        self.source_guard, self.current, self.records = source_guard, None, []
        self.last_stop_reason = None
        self.policy = _validated_policy(policy)

    def _deny(self, reason):
        self.last_stop_reason = reason
        raise ReasoningStopped("BudgetExceeded", "budget_stopped")

    def guard(self):
        self.source_guard()
        now = ledger_observation(self.ledger._path)
        available = (
            Decimal(now["limit_usd"])
            - Decimal(now["opening_usd"])
            - Decimal(now["settled_estimated_usd"])
            - Decimal(now["reserved_usd"])
            - Decimal(now["uncertain_usd"])
        )
        delta = Decimal(now["settled_estimated_usd"]) - Decimal(
            self.before["settled_estimated_usd"]
        )
        for failed, reason in (
            (
                not now["halted"] or not _immutable_accounting_preserved(now, self.before),
                "ImmutableAccountingChanged",
            ),
            (bool(now["counts"].get("reserved", 0)), "PendingRequest"),
            (
                now["unknown_records_sha256"] != self.before["unknown_records_sha256"],
                "UncertaintyChanged",
            ),
            (
                not now["continuation"]["active"] or now["continuation"]["allowed_model"] != MODEL,
                "ContinuationInactive",
            ),
            (len(self.records) >= self.policy.max_sends, "SendLimitReached"),
            (
                Decimal(now["continuation"]["remaining_usd"]) < self.policy.request_bound,
                "RemainingAuthorizationInsufficient",
            ),
            (available < self.policy.request_bound, "GlobalBudgetInsufficient"),
            (delta < 0, "AccountingChanged"),
            (delta + self.policy.request_bound > self.policy.batch_cap, "BatchCostCapInsufficient"),
        ):
            if failed:
                self._deny(reason)

    def handle_request(self, request):
        self.source_guard()
        record = self.current
        row = self.ledger.get(record["request_id"]) if record else None
        now = ledger_observation(self.ledger._path)
        used = (
            Decimal(now["opening_usd"])
            + Decimal(now["settled_estimated_usd"])
            + Decimal(now["reserved_usd"])
            + Decimal(now["uncertain_usd"])
        )
        if (
            record is None
            or len(self.records) >= self.policy.max_sends
            or request.method != "POST"
            or str(request.url) != METIS_CHAT_URL
            or row is None
            or row.status != "reserved"
            or row.model != MODEL
            or row.phase != "development"
            or row.amount_usd != self.policy.request_bound
            or row.run_id != record["run_id"]
            or row.case_id != record["case_id"]
            or row.case_revision != record["case_revision"]
            or row.attempt != record["attempt_index"]
            or not now["halted"]
            or not _immutable_accounting_preserved(now, self.before)
            or now["counts"].get("reserved", 0) != 1
            or now["unknown_records_sha256"] != self.before["unknown_records_sha256"]
            or now["continuation"]["block_reason"] != "PendingRequest"
            or used > Decimal(now["limit_usd"])
            or Decimal(now["settled_estimated_usd"])
            - Decimal(self.before["settled_estimated_usd"])
            + Decimal(now["reserved_usd"])
            > self.policy.batch_cap
        ):
            self._deny("PreSendAccountingChanged")
        self.records.append(record)
        record["http_send_started"] = True
        response = self.underlying.handle_request(request)
        record["http_status"] = response.status_code
        headers = dict(response.headers)
        headers.pop("content-encoding", None)
        headers.pop("content-length", None)
        return httpx.Response(
            response.status_code,
            headers=headers,
            stream=_FinishStream(response, record, MODEL),
            extensions=response.extensions,
            request=request,
        )

    def close(self):
        self.underlying.close()


class _SharedTransport(httpx.BaseTransport):
    def __init__(self, scoped):
        self.scoped = scoped

    def handle_request(self, request):
        return self.scoped.handle_request(request)

    def close(self):
        pass


class _FinishStream(_DecodedStream):
    """Same decoded envelope as the gateway; only known finish reasons are retained."""

    def __iter__(self):
        bounded, overflow = bytearray(), False
        for chunk in super().__iter__():
            if len(bounded) + len(chunk) > 262_144:
                bounded.clear()
                overflow = True
            elif not overflow:
                bounded.extend(chunk)
            yield chunk
        if not overflow:
            try:
                choices = json.loads(bounded).get("choices")
                if isinstance(choices, list) and len(choices) == 1 and isinstance(choices[0], dict):
                    value = choices[0].get("finish_reason")
                    self.record["finish_reason_observed"] = True
                    if type(value) is str and value in {
                        "stop",
                        "length",
                        "tool_calls",
                        "content_filter",
                    }:
                        self.record["finish_reason"] = value
                        self.record["finish_reason_unknown"] = False
                    else:
                        self.record["finish_reason_unknown"] = True
            except (ValueError, TypeError, AttributeError):
                pass


class _Planner:
    def __init__(self, gateway, scoped, prepared):
        self.gateway, self.scoped, self.prepared = gateway, scoped, prepared
        self.latest, self.attempts, self.requests = None, [], []

    def plan(self, request, *, context):
        if self.gateway.reasoner.client.is_closed:
            raise ReasoningStopped("LiveCallsDisabled")
        if (
            len(self.attempts) >= 2
            or context.attempt_index != len(self.attempts) + 1
            or request not in self.prepared["requests"]
        ):
            raise ReasoningStopped("ProviderRequestFailed")
        size, digest = _prompt_size(request, context)
        if size > self.scoped.policy.input_reserve:
            raise ReasoningStopped("ContextLimitExceeded")
        self.latest = request.model_copy(deep=True)
        self.requests.append(self.latest)
        self.scoped.guard()
        record = {
            "condition_id": self.prepared["condition"].condition_id,
            "request_id": request_id_for(context),
            "run_id": context.run_id,
            "case_id": context.case_id,
            "case_revision": context.case_revision,
            "attempt_index": context.attempt_index,
            "retrieval_round": request.evidence.retrieval_round,
            "prompt_bytes_plus_margin": size,
            "prompt_sha256": digest,
            "verified_returned_model": None,
            "http_send_started": False,
            "model_selection": None,
            "finish_reason": None,
            "finish_reason_observed": False,
            "finish_reason_unknown": True,
        }
        self.attempts.append(record)
        self.scoped.current = record
        try:
            raw = self.gateway.plan(request, context=context)
            record["model_selection"] = _selection_observation(request, raw)
            return raw
        finally:
            self.scoped.current = None


def _selection_observation(request, raw):
    """Record validated routing and match flags, never unknown names or raw JSON."""
    try:
        plan = parse_grounded_plan(raw)
    except Exception:
        return {"status": "invalid_plan_shape", "issue_codes": ["invalid_grounded_plan"]}
    hits = {hit.chunk_id: hit for hit in request.evidence.hits}
    gaps = {gap.name: gap for gap in request.gaps}
    return {
        "status": "valid_plan_shape",
        "decision": plan.decision,
        "context_matches": plan.context_sha256 == request.context_sha256,
        "known_selected_sources": [
            {
                "chunk_id": hits[reference.chunk_id].chunk_id,
                "content_sha256_matches": reference.content_sha256
                == source_content_sha256(hits[reference.chunk_id]),
            }
            for reference in plan.sources
            if reference.chunk_id in hits
        ],
        "unknown_source_count": sum(reference.chunk_id not in hits for reference in plan.sources),
        "known_question_name": gaps[plan.question_name].name
        if plan.question_name in gaps
        else None,
        "question_registered_as_user": (
            gaps[plan.question_name].kind == "user" if plan.question_name in gaps else False
        ),
        "unknown_question_present": plan.question_name is not None
        and plan.question_name not in gaps,
        "retrieval_query_count": len(plan.retrieval_queries),
        "declared_conflict_present": bool(request.conflict_groups),
        "semantic_validity_claim": False,
    }


class _OutputCapture:
    """Transparent port observations before engine validation; no extra model call."""

    def __init__(self, reasoner, planner):
        self.reasoner, self.planner, self.outputs = reasoner, planner, []

    def analyze(self, case, user_message, evidence, *, context):
        entry = {
            "request_id": request_id_for(context),
            "run_id": context.run_id,
            "case_id": context.case_id,
            "case_revision": context.case_revision,
            "attempt_index": context.attempt_index,
            "retrieval_round": evidence.retrieval_round,
            "grounded_context_sha256": None,
            "status": "unavailable",
            "analysis": None,
            "issue_codes": [],
            "error_code": None,
        }
        self.outputs.append(entry)
        try:
            analysis = self.reasoner.analyze(case, user_message, evidence, context=context)
            valid = AnalysisResult.model_validate(analysis.model_dump(warnings=False))
            entry["status"] = "valid_rendered_analysis"
            entry["analysis"] = valid.model_dump(mode="json")
            return analysis
        except InvalidAnalysis as error:
            feedback = SupportEngine._safe_output_feedback(error)
            entry["status"] = "invalid_analysis"
            entry["issue_codes"] = [issue.code for issue in feedback.issues]
            raise
        except ReasoningStopped as error:
            entry["status"] = "stopped"
            entry["error_code"] = (
                error.code
                if type(error.code) is str and error.code in get_args(ReasoningStopCode.__value__)
                else "ReasoningUnavailable"
            )
            raise
        except Exception:
            entry["error_code"] = "ReasoningUnavailable"
            raise
        finally:
            latest = self.planner.latest
            if (
                latest is not None
                and latest.case == case
                and latest.user_message == user_message.strip()
                and latest.evidence == evidence
            ):
                entry["grounded_context_sha256"] = latest.context_sha256


def execute(
    prepared, *, ledger_path, config, before, underlying=None, source_guard=None, policy=BASELINE
):
    policy = _validated_policy(policy)
    mocked = isinstance(underlying, httpx.MockTransport)
    if (
        config.model != MODEL
        or config.phase != "development"
        or config.response_mode != "grounded_plan"
        or config.continuation_id != GRANT
        or not config.live_enabled
        or config.input_token_reserve != policy.input_reserve
        or config.max_output_tokens != policy.output_limit
        or config.max_request_usd != policy.request_bound
        or (underlying is None and source_guard is None)
        or (underlying is not None and not mocked)
        or (
            not mocked
            and Path(ledger_path).resolve() != (ROOT / "runtime/budget.sqlite3").resolve()
        )
        or (
            underlying is None
            and [item["condition"].condition_id for item in prepared] != list(policy.condition_ids)
        )
    ):
        raise BaselineRejected()
    ledger = BudgetLedger(ledger_path)
    scoped = _ScopedTransport(
        underlying or httpx.HTTPTransport(retries=0),
        ledger,
        before,
        source_guard or (lambda: None),
        policy,
    )
    results, gateways, planners, skipped = [], [], [], []
    stop_code = None
    try:
        for position, item in enumerate(prepared):
            scoped.last_stop_reason = None
            try:
                scoped.guard()
            except Exception as error:
                stop_code = (
                    error.code if isinstance(error, ReasoningStopped) else "ProviderRequestFailed"
                )
                skipped = [
                    {
                        "condition_id": rest["condition"].condition_id,
                        "reason": stop_code,
                        "guard_stop_reason": scoped.last_stop_reason,
                    }
                    for rest in prepared[position:]
                ]
                break
            gateway = MetisGroundedPlanner(config, ledger, transport=_SharedTransport(scoped))
            gateways.append(gateway)
            planner = _Planner(gateway, scoped, item)
            planners.append(planner)
            condition = item["condition"]
            retriever = _inputs().FixedRetriever(condition.bundles)
            outputs = _OutputCapture(
                GroundedReasoner(
                    planner,
                    request_factory=lambda case, message, evidence, condition=condition: (
                        _inputs().grounded_request(condition, case, message, evidence)
                    ),
                ),
                planner,
            )
            capture = ReasoningCapture(outputs)
            try:
                result = SupportEngine(
                    retriever,
                    capture,
                    snapshot_id=condition.bundles[0].snapshot_id,
                    limits=RunLimits(**LIMITS),
                    top_k=TOP_K,
                    evidence_scope="all",
                ).run(
                    condition.case,
                    condition.user_message,
                    run_id=f"controlled-{policy.experiment_id}-{position + 1}-{uuid4().hex[:8]}",
                )
                handoff, handoff_error = None, None
                if result.status == "awaiting_approval":
                    try:
                        handoff = build_handoff(
                            result, capture.last, grounded_request=planner.latest
                        )
                    except Exception:
                        handoff_error = "InvalidHandoffInput"
                results.append(
                    {
                        "condition_id": condition.condition_id,
                        "result": result.model_dump(mode="json"),
                        "canonical_handoff": handoff.model_dump(mode="json") if handoff else None,
                        "handoff_error": handoff_error,
                        "guard_stop_reason": scoped.last_stop_reason,
                        "grounded_requests": [
                            request.model_dump(mode="json") for request in planner.requests
                        ],
                        "reasoning_attempts": planner.attempts,
                        "reasoning_outputs": outputs.outputs,
                        "retrieval_requests": [
                            request.model_dump(mode="json") for request in retriever.requests
                        ],
                        "returned_evidence": [
                            bundle.model_dump(mode="json") for bundle in retriever.returned
                        ],
                    }
                )
            finally:
                gateway.close()
            if result.error_code in _TERMINAL or handoff_error:
                stop_code = handoff_error or result.error_code
                skipped = [
                    {
                        "condition_id": rest["condition"].condition_id,
                        "reason": stop_code,
                        "guard_stop_reason": scoped.last_stop_reason,
                    }
                    for rest in prepared[position + 1 :]
                ]
                break
    except Exception:
        stop_code = "ProviderRequestFailed"
        attempted = {planner.prepared["condition"].condition_id for planner in planners}
        skipped = [
            {"condition_id": item["condition"].condition_id, "reason": stop_code}
            for item in prepared
            if item["condition"].condition_id not in attempted
        ]
    finally:
        for gateway in gateways:
            gateway.close()
        scoped.close()
    after = ledger_observation(ledger_path)
    attempts = [record for planner in planners for record in planner.attempts]
    for record in attempts:
        record["reservation"] = _plain(ledger.get(record["request_id"]))
    accounting = _new_request_accounting(attempts)
    try:
        scoped.source_guard()
        source_preserved = True
    except Exception:
        source_preserved = False
    checks = {
        "at_most_six_actual_sends": len(scoped.records) <= MAX_SENDS,
        "actual_send_limit_respected": len(scoped.records) <= policy.max_sends,
        "at_most_two_attempts_per_condition": all(
            len(planner.attempts) <= 2 for planner in planners
        ),
        "clients_closed": all(gateway.reasoner.client.is_closed for gateway in gateways),
        "immutable_grant_and_global_budget_preserved": _immutable_accounting_preserved(
            after, before
        ),
        "original_halt_preserved": after["halted"],
        "only_original_uncertainty": after["unknown_records_sha256"]
        == before["unknown_records_sha256"],
        "no_pending_requests": after["counts"].get("reserved", 0) == 0,
        "batch_actual_estimate_bound": Decimal(after["settled_estimated_usd"])
        - Decimal(before["settled_estimated_usd"])
        <= policy.batch_cap,
        "new_request_accounting_complete": accounting["new_request_accounting_complete"],
        "registered_source_unchanged": source_preserved,
    }
    finals = sum(item["canonical_handoff"] is not None for item in results)
    unfunded_reasons = {
        "RemainingAuthorizationInsufficient",
        "BatchCostCapInsufficient",
        "GlobalBudgetInsufficient",
    }
    return {
        "schema_version": 1,
        "protocol_id": policy.protocol_id,
        "experiment_id": policy.experiment_id,
        "execution_policy": "baseline" if policy == BASELINE else "output_cap_followup",
        "gateway": _gateway_policy(policy),
        "evidence_scope": "all",
        "top_k": TOP_K,
        "limits": LIMITS,
        "registered_conditions": len(prepared),
        "attempted_conditions": len(planners),
        "final_proposals": finals,
        "recorded_condition_results": len(results),
        "skipped_conditions": skipped,
        "unfunded_condition_count": sum(
            item.get("guard_stop_reason") in unfunded_reasons for item in (*skipped, *results)
        ),
        "unfunded_skipped_condition_count": sum(
            item.get("guard_stop_reason") in unfunded_reasons for item in skipped
        ),
        "complete": len(results) == len(prepared) and finals == len(prepared),
        "stop_code": stop_code,
        "checks": checks,
        "source_guard_installed": source_guard is not None,
        "accepted_operations": all(checks.values()),
        "actual_sends": len(scoped.records),
        "execution_mode": "mocked_model_fixed_evidence" if mocked else "live_model_fixed_evidence",
        "real_provider_requests": 0 if mocked else len(scoped.records),
        "intercepted_mock_sends": len(scoped.records) if mocked else 0,
        "paid_api_cost_usd": "0" if mocked else None,
        "accounting_scope": "disposable_mock_ledger" if mocked else "designated_shared_ledger",
        "cost_kind": "synthetic_usage_estimate" if mocked else "validated_provider_usage_estimate",
        "condition_results": results,
        "provider_observations": scoped.records,
        "model_request_observations": attempts,
        **accounting,
        "ledger_before": before,
        "ledger_after": after,
        "ledger_settled_delta_estimated_usd": str(
            Decimal(after["settled_estimated_usd"]) - Decimal(before["settled_estimated_usd"])
        ),
        "ledger_delta_scope": "Whole shared ledger; request-attributed costs and holds are separate.",
        "actual_account_charge_usd": None,
        "tracker_actions": 0,
        "tracker_staging": False,
        "proposal_auto_approved": False,
        "model_choice_quality_review": "pending separate preregistered whole-output review",
        "reasoning_output_boundary": "Valid rendered analyses are observed before engine validation. Plan shape/match flags establish neither acceptance nor semantic quality; invalid model payloads and unknown identifiers are omitted.",
        "fixed_evidence_only": True,
        "exposed_development_only": True,
        "rag_quality_claim": False,
        "heldout_claim": False,
        "quality_claim": False,
        "c5_reconciled": False,
    }


def _mock_response(request):
    body = json.loads(request.content)
    data = json.loads(body["messages"][1]["content"])
    users = [gap for gap in data["request"]["gaps"] if gap["kind"] == "user"]
    plan = {
        "context_sha256": data["request"]["context_sha256"],
        "decision": "ask" if users else "escalate",
    }
    if users:
        plan["question_name"] = users[0]["name"]
    return httpx.Response(
        200,
        json={
            "model": "gpt-4o-mini-2024-07-18",
            "usage": {"prompt_tokens": 125, "completion_tokens": 75, "total_tokens": 200},
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": json.dumps(plan)},
                }
            ],
        },
    )


def _config(key, policy=BASELINE):
    policy = _validated_policy(policy)
    return MetisConfig(
        api_key=key,
        live_enabled=True,
        model=MODEL,
        phase="development",
        response_mode="grounded_plan",
        continuation_id=GRANT,
        input_token_reserve=policy.input_reserve,
        max_output_tokens=policy.output_limit,
        max_request_usd=policy.request_bound,
    )


def _mock_ledger(path):
    ledger = BudgetLedger.create(path, limit_usd=Decimal("4.5"), opening_spend_usd=Decimal(0))
    ledger.reserve(
        request_id="call:controlled-baseline-mock-old",
        run_id="run:mock-old",
        case_id="case:mock-old",
        case_revision=1,
        attempt=1,
        model="gpt-4.1-mini",
        phase="development",
        amount_usd=Decimal("0.008"),
    )
    ledger.mark_uncertain("call:controlled-baseline-mock-old", error_code="ProviderModelMismatch")
    ledger.halt()
    ledger.authorize_continuation(
        authorization_id=GRANT,
        authorization_ref="test:controlled-model-baseline-mock-only",
        expected_request_id="call:controlled-baseline-mock-old",
        held_usd=Decimal("0.02"),
        additional_cap_usd=Decimal("0.1"),
    )
    return ledger


def _destination(path):
    destination = path.resolve()
    if (
        destination.is_relative_to(ROOT)
        and subprocess.run(
            ["git", "check-ignore", "--quiet", "--", str(destination)], cwd=ROOT
        ).returncode
        != 0
    ):
        raise BaselineRejected()
    destination.mkdir(parents=True, exist_ok=False, mode=0o700)
    return destination


def _summary(receipt):
    return {
        key: receipt[key]
        for key in (
            "execution_mode",
            "execution_policy",
            "registered_conditions",
            "attempted_conditions",
            "final_proposals",
            "unfunded_condition_count",
            "complete",
            "accepted_operations",
            "actual_sends",
            "real_provider_requests",
            "intercepted_mock_sends",
            "paid_api_cost_usd",
            "accounting_scope",
            "cost_kind",
            "new_cost_estimated_usd",
            "new_settled_estimated_usd",
            "new_reserved_usd",
            "new_uncertain_usd",
            "new_request_accounting_complete",
            "quality_claim",
            "c5_reconciled",
        )
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--live", action="store_true")
    mode.add_argument("--mock", action="store_true")
    parser.add_argument("--output-cap-followup", action="store_true")
    parser.add_argument("--ledger", type=Path, default=ROOT / "runtime/budget.sqlite3")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    try:
        policy = OUTPUT_CAP_FOLLOWUP if args.output_cap_followup else BASELINE
        if args.mock:
            if args.env_file is not None:
                raise BaselineRejected()
            prepared = prepare(policy=policy)
            with tempfile.TemporaryDirectory(prefix="controlled-baseline-mock-") as temporary:
                ledger = _mock_ledger(Path(temporary) / "budget.sqlite3")
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    receipt = execute(
                        prepared,
                        ledger_path=ledger._path,
                        config=_config("public-synthetic-controlled-baseline-key", policy),
                        before=ledger_observation(ledger._path),
                        underlying=httpx.MockTransport(_mock_response),
                        policy=policy,
                    )
            receipt["execution_mode"] = "mocked_model_fixed_evidence"
            receipt["real_provider_requests"] = 0
            receipt["preflight"] = {
                item["condition"].condition_id: item["prompts"] for item in prepared
            }
            if args.output_dir is not None:
                (_destination(args.output_dir) / "receipt.json").write_text(
                    json.dumps(receipt, indent=2) + "\n"
                )
            print(json.dumps(_summary(receipt)))
            if not receipt["complete"] or not receipt["accepted_operations"]:
                raise BaselineRejected()
            return
        protocol, registration = load_registration(ROOT, args.ledger, policy)
        prepared = prepare(policy=policy)
        if policy == OUTPUT_CAP_FOLLOWUP:
            expected = protocol["baseline_prompt_sha256"]
            if (
                type(expected) is not str
                or re.fullmatch(r"[0-9a-f]{64}", expected) is None
                or prepared[0]["prompts"][0]["prompt_sha256"] != expected
            ):
                raise BaselineRejected()
            registration["baseline_prompt_sha256"] = expected
        registration["preflight"] = {
            item["condition"].condition_id: item["prompts"] for item in prepared
        }

        def source_guard():
            observed = source_observation(
                ROOT, registration["fixture_pins"], registration["review_pins"]["path"], policy
            )
            if observed != {key: registration[key] for key in observed}:
                raise BaselineRejected()

        source_guard()
        if ledger_observation(args.ledger) != registration["ledger_before"]:
            raise BaselineRejected()
        if not args.live:
            print(
                json.dumps(
                    {
                        "eligible_read_only": True,
                        "registered_conditions": len(prepared),
                        "all_prompts_fit": True,
                        "paid_requests": 0,
                        "max_actual_sends": policy.max_sends,
                        "batch_actual_cost_cap_usd": str(policy.batch_cap),
                        "execution_policy": "baseline"
                        if policy == BASELINE
                        else "output_cap_followup",
                        "all_six_funded_claim": False,
                        "quality_claim": False,
                        "c5_reconciled": False,
                    }
                )
            )
            return
        if args.env_file is None or args.output_dir is None:
            raise BaselineRejected()
        destination = _destination(args.output_dir)
        (destination / "registration.json").write_text(json.dumps(registration, indent=2) + "\n")
        source_guard()
        if ledger_observation(args.ledger) != registration["ledger_before"]:
            raise BaselineRejected()
        config = _config(_credential(ROOT, args.env_file), policy)
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            receipt = execute(
                prepared,
                ledger_path=args.ledger,
                config=config,
                before=registration["ledger_before"],
                source_guard=source_guard,
                policy=policy,
            )
        receipt["execution_mode"] = "live_model_fixed_evidence"
        receipt["real_provider_requests"] = receipt["actual_sends"]
        receipt["registration"] = registration
        with (destination / "receipt.json").open("x", encoding="utf-8") as stream:
            json.dump(receipt, stream, ensure_ascii=True, indent=2)
            stream.write("\n")
        print(json.dumps(_summary(receipt)))
        # A safely stopped partial batch is retained, never retried here.
        if not receipt["accepted_operations"]:
            raise BaselineRejected()
    except Exception:
        print(json.dumps({"code": "ControlledModelBaselineRejected", "automatic_retry": False}))
        raise SystemExit(1) from None
