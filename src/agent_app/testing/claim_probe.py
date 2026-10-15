"""Proposal-only comparison of compiled analysis and constrained claim passages.

Each state is an independent caller-authored current snapshot. Nothing here
approves, releases or executes a proposal, or claims an actual conversation route.
The fixed retriever logs requests; it does not perform a search.
"""

import json
from copy import deepcopy
from decimal import Decimal

from agent_app.contracts import (
    CaseState,
    GroundedRequest,
    OutputIssue,
    ProposalRequirements,
    ReasoningContext,
)
from agent_app.evaluation.runner import Usage
from agent_app.llm.budget import ExperimentRequestSlot
from agent_app.llm.claims import MetisClaimPlanner
from agent_app.llm.config import MetisConfig
from agent_app.llm.metis import MetisReasoner, request_id_for
from agent_app.llm.pricing import get_price
from agent_app.orchestration import SupportEngine
from agent_app.orchestration.handoff import ReasoningCapture, build_handoff
from agent_app.orchestration.ports import ReasoningStopped
from agent_app.reasoning.claim_plan import (
    ClaimReasoner,
    build_claim_messages,
    observe_claim_plan,
    parse_claim_plan,
    render_claim_plan,
)
from agent_app.reasoning.grounding import (
    make_grounded_request,
)
from agent_app.reasoning.output import InvalidAnalysis
from agent_app.reasoning.prompts import build_messages
from agent_app.testing.broader_proposals import (
    BroaderProposalRejected as ClaimProbeRejected,
)
from agent_app.testing.broader_proposals import (
    _Analysis,
    _digest,
    _FixedSnapshot,
    _fixtures,
    _message_observation,
    _row,
    state_run_id,
)
from agent_app.testing.dev_three_model_probe import (
    MODEL,
    SharedTransport,
    contains_secret,
    ledger_observation,
    sha,
)
from agent_app.testing.quality_probe import QualityTransport

ARMS = ("compiled_analysis", "claim_cards")
EXPERIMENT_ID = "core-claim-boundary-2026-10-15-v1"
INPUT_LIMIT = 32768
OUTPUT_LIMIT = 2048
_JOB_KEYS = {
    "job_id",
    "arm",
    "scenario_id",
    "snapshot_ids",
    "input_token_reserve",
    "max_output_tokens",
    "round",
}


def _job(job, fixtures):
    if (
        type(job) is not dict
        or set(job) != _JOB_KEYS
        or type(job["job_id"]) is not str
        or not job["job_id"]
        or job["arm"] not in ARMS
        or type(job["scenario_id"]) is not str
        or type(job["snapshot_ids"]) is not list
        or len(job["snapshot_ids"]) != 2
        or any(type(i) is not str or i not in fixtures for i in job["snapshot_ids"])
        or len(set(job["snapshot_ids"])) != 2
        or any(fixtures[i]["scenario_id"] != job["scenario_id"] for i in job["snapshot_ids"])
        or type(job["input_token_reserve"]) is not int
        or job["input_token_reserve"] != INPUT_LIMIT
        or type(job["max_output_tokens"]) is not int
        or job["max_output_tokens"] != OUTPUT_LIMIT
        or type(job["round"]) is not int
        or job["round"] not in (1, 2)
    ):
        raise ClaimProbeRejected()
    return deepcopy(job)


def _jobs(batch, fixtures):
    if (
        type(batch) is not dict
        or batch.get("kind") != "controlled_evidence"
        or type(batch.get("jobs")) is not list
        or len(batch["jobs"]) != 2
        or type(batch.get("scope_id")) is not str
        or not batch["scope_id"]
        or type(batch.get("batch_id")) is not str
        or not batch["batch_id"]
    ):
        raise ClaimProbeRejected()
    jobs = [_job(job, fixtures) for job in batch["jobs"]]
    if (
        len({job["job_id"] for job in jobs}) != 2
        or {job["arm"] for job in jobs} != set(ARMS)
        or len({job["scenario_id"] for job in jobs}) != 1
        or len({job["round"] for job in jobs}) != 1
        or jobs[0]["snapshot_ids"] != jobs[1]["snapshot_ids"]
    ):
        raise ClaimProbeRejected()
    return jobs


def proposal_slots(method, batch, fixtures):
    fixtures = _fixtures(fixtures)
    slots = []
    for job in _jobs(batch, fixtures):
        for snapshot in job["snapshot_ids"]:
            row = fixtures[snapshot]
            case = CaseState.model_validate(row["case"])
            for attempt in (1, 2):
                context = ReasoningContext(
                    run_id=state_run_id(method, job, row),
                    case_id=case.case_id,
                    case_revision=case.case_revision,
                    attempt_index=attempt,
                )
                slots.append(
                    ExperimentRequestSlot(
                        request_id=request_id_for(context),
                        run_id=context.run_id,
                        case_id=case.case_id,
                        case_revision=case.case_revision,
                        attempt=attempt,
                        input_token_reserve=INPUT_LIMIT,
                        max_output_tokens=OUTPUT_LIMIT,
                        amount_usd=get_price(MODEL).cost(INPUT_LIMIT, OUTPUT_LIMIT),
                    )
                )
    if len(slots) != 8 or len({slot.request_id for slot in slots}) != 8:
        raise ClaimProbeRejected()
    if sum(slot.amount_usd for slot in slots) > Decimal("0.06"):
        raise ClaimProbeRejected()
    return tuple(slots)


def fixed_snapshot_factory(packet, fixtures, records):
    fixtures = _fixtures(fixtures)
    if (
        type(packet) is not dict
        or type(packet.get("snapshots")) is not list
        or type(records) is not list
    ):
        raise ClaimProbeRejected()
    validated = [_row(row) for row in packet["snapshots"]]
    supplied = {row["id"]: row for row in validated}
    if len(supplied) != len(packet["snapshots"]) or supplied != fixtures:
        raise ClaimProbeRejected()

    def factory(job, row):
        job = _job(job, fixtures)
        row = _row(row)
        if row["id"] not in job["snapshot_ids"] or row != fixtures[row["id"]]:
            raise ClaimProbeRejected()
        return _FixedSnapshot(job, row, records), row["evidence"]["snapshot_id"]

    return factory


def _config(config, arm, scope_id):
    values = config.model_dump()
    values.update({key: False for key in MetisConfig.model_fields if key.startswith("grounded_")})
    values.update(
        response_mode="analysis",
        prompt_policy="compiled_rules",
        continuation_id=scope_id,
        input_token_reserve=INPUT_LIMIT,
        max_output_tokens=OUTPUT_LIMIT,
        max_request_usd=get_price(MODEL).cost(INPUT_LIMIT, OUTPUT_LIMIT),
    )
    return MetisConfig.model_validate(values)


def _claim_reasoner(planner, registered):
    return ClaimReasoner(
        planner,
        request_factory=lambda case, message, evidence: make_grounded_request(
            case,
            message,
            evidence,
            gaps=registered.gaps,
            conflict_groups=registered.conflict_groups,
        ),
    )


class _ClaimPlanner:
    """Observe the actual private request without changing reasoner validation."""

    def __init__(self, gateway, counted, records):
        self.gateway, self.counted, self.records = gateway, counted, records

    def plan(self, request, *, context):
        messages = build_claim_messages(request, context)
        record = {
            "context": context.model_dump(mode="json"),
            "request": request.grounded.model_dump(mode="json"),
            "claim_context_sha256": request.context_sha256,
            "claim_input": json.loads(messages[1]["content"]),
            "claim_plan": None,
            "rendered_analysis": None,
            "error_code": None,
            **_message_observation(messages),
        }
        self.records.append(record)
        try:
            if not self.counted.ledger.quarantine_scope_status(self.counted.scope_id).active:
                raise ReasoningStopped("BudgetExceeded", "budget_stopped")
            self.counted.current = request_id_for(context)
            raw = self.gateway.plan(request, context=context)
            record["output_sha256"] = sha(raw.encode())
            try:
                decoded = json.loads(raw)
            except (ValueError, RecursionError):
                decoded = raw
            try:
                echo = contains_secret(decoded, self.gateway.config.api_key.get_secret_value())
            except RecursionError:
                # An unrepresentable nested candidate is never retained. Return
                # its original bytes to the real strict parser/repair boundary.
                record["schema_observation"] = {
                    "syntactic_valid": False,
                    "validation_error_count": None,
                }
                record["plan_observation"] = observe_claim_plan(raw)
                return raw
            if echo:
                record["credential_echo_rejected"] = True
                raise ReasoningStopped("ProviderResponseInvalid")
            # Added after the stopped V1 paid cohort. Historical receipts keep
            # their original observations; this safe projection distinguishes
            # future parse stages without retaining untrusted output text.
            record["plan_observation"] = observe_claim_plan(raw)
            try:
                parsed = parse_claim_plan(raw)
                record["claim_plan"] = parsed.model_dump(mode="json")
                record["schema_observation"] = {
                    "syntactic_valid": True,
                    "validation_error_count": 0,
                }
                try:
                    record["rendered_analysis"] = render_claim_plan(request, raw).model_dump(
                        mode="json"
                    )
                except (ValueError, TypeError, AttributeError):
                    # A parsed but rejected candidate remains visible; the real
                    # reasoner owns terminal codes, repair and the final decision.
                    record["rendering_rejected"] = True
            except (ValueError, TypeError, AttributeError):
                record["schema_observation"] = {
                    "syntactic_valid": False,
                    "validation_error_count": None,
                }
            return raw
        except ReasoningStopped as error:
            record["error_code"] = error.code
            raise
        finally:
            self.counted.current = None


def run_proposal_batch(
    protocol,
    batch,
    fixtures,
    definitions,
    ledger,
    config,
    before,
    *,
    underlying=None,
    checkpoint=None,
    retriever_factory=None,
):
    import httpx

    fixtures = _fixtures(fixtures)
    jobs = _jobs(batch, fixtures)
    proposal_slots(protocol, batch, fixtures)
    if (
        config.model != MODEL
        or config.phase != "development"
        or config.continuation_id != batch["scope_id"]
        or (retriever_factory is not None and not callable(retriever_factory))
    ):
        raise ClaimProbeRejected()
    counted = QualityTransport(
        underlying or httpx.HTTPTransport(retries=0),
        ledger,
        batch["scope_id"],
        before,
        input_profiles={row["case"]["case_id"]: INPUT_LIMIT for row in fixtures.values()},
    )
    visited, attempts, stopped = [], [], False
    if checkpoint:
        counted.on_send = lambda: checkpoint(
            {
                "event": "reserved_before_transport",
                "jobs": visited,
                "attempts": attempts,
                "provider_sends": counted.records,
            }
        )
    try:
        for job in jobs:
            if not ledger.quarantine_scope_status(batch["scope_id"]).active:
                stopped = True
                break
            states = []
            for snapshot in job["snapshot_ids"]:
                if not ledger.quarantine_scope_status(batch["scope_id"]).active:
                    stopped = True
                    break
                row = fixtures[snapshot]
                case = CaseState.model_validate(row["case"])
                registered = GroundedRequest.model_validate(row["catalog_request"])
                requirements = ProposalRequirements.model_validate(row["proposal_requirements"])
                retriever, snapshot_id = (
                    retriever_factory(job, deepcopy(row))
                    if retriever_factory
                    else (_FixedSnapshot(job, row, []), row["evidence"]["snapshot_id"])
                )
                cfg = _config(config, job["arm"], batch["scope_id"])
                gateway = (
                    MetisClaimPlanner(cfg, ledger, transport=SharedTransport(counted))
                    if job["arm"] == "claim_cards"
                    else MetisReasoner(cfg, ledger, transport=SharedTransport(counted))
                )
                start = len(attempts)
                planner = None
                try:
                    if job["arm"] == "claim_cards":
                        planner = _ClaimPlanner(gateway, counted, attempts)
                        reasoner = _claim_reasoner(planner, registered)
                    else:
                        reasoner = _Analysis(gateway, counted, attempts)
                    capture = ReasoningCapture(reasoner)
                    result = SupportEngine(
                        retriever,
                        capture,
                        snapshot_id=snapshot_id,
                        proposal_checks=True,
                        current_revision=lambda _cid, revision=case.case_revision: revision,
                        current_case=lambda _cid, current=case: current.model_copy(deep=True),
                        evidence_scope="all",
                        top_k=max(5, len(row["evidence"]["hits"])),
                    ).run(
                        case,
                        row["user_message"],
                        run_id=state_run_id(protocol, job, row),
                        proposal_requirements=requirements,
                    )
                    handoff, handoff_error = None, None
                    if result.status == "awaiting_approval":
                        try:
                            handoff = build_handoff(
                                result,
                                capture.last,
                                grounded_request=reasoner.last_request.grounded
                                if planner
                                else None,
                            ).model_dump(mode="json")
                        except ValueError:
                            handoff_error = "HandoffRejected"
                    states.append(
                        {
                            "snapshot_id": snapshot,
                            "scenario_id": row["scenario_id"],
                            "turn_id": row["turn_id"],
                            "run_id": result.run_id,
                            "result": result.model_dump(mode="json"),
                            "handoff": handoff,
                            "handoff_error": handoff_error,
                            "proposal_pending_review": handoff is not None,
                            "approved": False,
                            "released": False,
                            "actions_executed": 0,
                            "attempt_start": start,
                            "attempt_count": len(attempts) - start,
                        }
                    )
                finally:
                    gateway.close()
                if checkpoint:
                    checkpoint(
                        {
                            "jobs": [*visited, {**job, "states": states}],
                            "attempts": attempts,
                            "provider_sends": counted.records,
                        }
                    )
            visited.append(
                {
                    **job,
                    "states": states,
                    "coverage_complete": False,
                    "completed_states": len(states),
                    "run_ids": [s["run_id"] for s in states],
                }
            )
            if stopped:
                break
    finally:
        counted.close()
    after = ledger_observation(ledger._path)
    return {
        "batch_id": batch["batch_id"],
        "kind": batch["kind"],
        "scope_id": batch["scope_id"],
        "jobs": visited,
        "attempts": attempts,
        "provider_sends": counted.records,
        "actual_sends": sum(r["http_send_started"] for r in counted.records),
        "accounting": Usage(ledger).measure(
            [ReasoningContext.model_validate(a["context"]) for a in attempts]
        ),
        "planned_jobs": len(jobs),
        "visited_jobs": len(visited),
        "completed_routes": 0,
        "planned_states": sum(len(j["snapshot_ids"]) for j in jobs),
        "completed_states": sum(len(j["states"]) for j in visited),
        "unvisited_states": sum(len(j["snapshot_ids"]) for j in jobs)
        - sum(len(j["states"]) for j in visited),
        "unvisited_job_ids": [
            j["job_id"] for j in jobs if j["job_id"] not in {v["job_id"] for v in visited}
        ],
        "pending_proposals": sum(
            s["proposal_pending_review"] for j in visited for s in j["states"]
        ),
        "actions_executed": 0,
        "stopped_early": stopped,
        "ledger_after": after,
        "original_accounting_preserved": all(
            after[k] == before[k]
            for k in (
                "meta_sha256",
                "unknown_sha256",
                "old_grants_sha256",
            )
        ),
    }


class _OfflineProbe:
    def __init__(self, row, arm, config, rows):
        self.row, self.arm, self.config, self.rows = row, arm, config, rows

    def _record(self, messages, context, evidence):
        observed = _message_observation(messages)
        self.rows.append(
            {
                "snapshot_id": self.row["id"],
                "arm": self.arm,
                "attempt": context.attempt_index,
                "context": context.model_dump(mode="json"),
                "evidence_sha256": _digest(evidence.model_dump(mode="json")),
                **observed,
                "fits": observed["input_bytes_plus_guard"] <= INPUT_LIMIT,
            }
        )
        raise InvalidAnalysis((OutputIssue(code="invalid_shape"),))

    def plan(self, request, *, context):
        self._record(build_claim_messages(request, context), context, request.grounded.evidence)

    def analyze(self, case, user_message, evidence, *, context):
        self._record(
            build_messages(
                case,
                user_message,
                evidence,
                context=context,
                feedback=context.output_feedback,
                policy="compiled_rules",
            ),
            context,
            evidence,
        )


def offline_preflight(packet):
    """Actual engine normal/author-invalid-shape repair; no key/ledger/provider."""
    if type(packet) is not dict or type(packet.get("snapshots")) is not list:
        raise ClaimProbeRejected()
    validated = [_row(row) for row in packet["snapshots"]]
    fixtures = _fixtures({row["id"]: row for row in validated})
    if len(fixtures) != len(packet["snapshots"]):
        raise ClaimProbeRejected()
    base = MetisConfig(api_key="authored-public-preflight-key")
    rows = []
    for row in fixtures.values():
        case = CaseState.model_validate(row["case"])
        request = GroundedRequest.model_validate(row["catalog_request"])
        requirements = ProposalRequirements.model_validate(row["proposal_requirements"])
        for arm in ARMS:
            config = _config(base, arm, "authored-preflight-scope")
            probe = _OfflineProbe(row, arm, config, rows)
            reasoner = _claim_reasoner(probe, request) if arm == "claim_cards" else probe
            SupportEngine(
                _FixedSnapshot({"job_id": "authored-preflight", "arm": arm}, row, []),
                reasoner,
                snapshot_id=row["evidence"]["snapshot_id"],
                proposal_checks=True,
                evidence_scope="all",
                top_k=max(5, len(row["evidence"]["hits"])),
            ).run(
                case,
                row["user_message"],
                run_id=state_run_id(
                    {"experiment_id": EXPERIMENT_ID},
                    {"job_id": f"r1:{row['scenario_id']}:{arm}"},
                    row,
                ),
                proposal_requirements=requirements,
            )
    return {
        "schema_version": 1,
        "accepted": len(rows) == 4 * len(fixtures) and all(r["fits"] for r in rows),
        "actual_sends": 0,
        "snapshots": len(fixtures),
        "input_token_reserve": INPUT_LIMIT,
        "max_output_tokens": OUTPUT_LIMIT,
        "rows": rows,
        "max_input_bytes_plus_guard": max((r["input_bytes_plus_guard"] for r in rows), default=0),
        "proposal_only": True,
        "human_usefulness": None,
        "held_out_test": False,
        "no_sources_cropped": True,
        "no_release_or_action": True,
        "uses_registered_round1_run_ids": True,
        "round2_run_ids_have_same_encoded_length": True,
    }
