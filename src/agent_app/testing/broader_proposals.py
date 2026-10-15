"""Proposal-only comparison of two existing reasoning contracts.

Each state is an independent caller-authored current snapshot. Nothing here
approves, releases or executes a proposal, or claims an actual conversation route.
The fixed retriever logs requests; it does not perform a search.
"""

import json
from copy import deepcopy
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from pydantic import ValidationError

from agent_app.contracts import (
    AnalysisResult,
    CaseState,
    EvidenceBundle,
    GroundedRequest,
    OutputIssue,
    ProposalRequirements,
    ReasoningContext,
)
from agent_app.evaluation.runner import Usage
from agent_app.llm.budget import ExperimentRequestSlot
from agent_app.llm.config import MetisConfig
from agent_app.llm.grounded import MetisGroundedPlanner
from agent_app.llm.metis import MetisReasoner, configured_grounded_messages, request_id_for
from agent_app.llm.pricing import get_price
from agent_app.orchestration import SupportEngine
from agent_app.orchestration.handoff import ReasoningCapture, build_handoff
from agent_app.orchestration.ports import ReasoningStopped
from agent_app.reasoning.grounding import (
    GroundedReasoner,
    make_grounded_request,
    validate_grounded_request,
)
from agent_app.reasoning.output import InvalidAnalysis
from agent_app.reasoning.prompts import build_messages
from agent_app.testing.dev_three_model_probe import (
    MODEL,
    SharedTransport,
    contains_secret,
    ledger_observation,
    sha,
)
from agent_app.testing.quality_probe import QualityPlanner, QualityTransport

ARMS = ("grounded_quotes", "compiled_analysis")
INPUT_LIMIT = 32768
OUTPUT_LIMIT = 2048
_ROW_KEYS = {
    "id",
    "scenario_id",
    "turn_id",
    "case",
    "user_message",
    "evidence",
    "catalog_request",
    "proposal_requirements",
}
_JOB_KEYS = {
    "job_id",
    "arm",
    "scenario_id",
    "snapshot_ids",
    "input_token_reserve",
    "max_output_tokens",
    "round",
}


class BroaderProposalRejected(ValueError):
    def __init__(self):
        super().__init__("BroaderProposalRejected")


def _digest(value):
    return sha(json.dumps(value, ensure_ascii=False, sort_keys=True).encode())


def _row(value):
    try:
        if type(value) is not dict or set(value) != _ROW_KEYS:
            raise ValueError
        value = deepcopy(value)
        if any(type(value[k]) is not str or not value[k] for k in ("id", "scenario_id", "turn_id")):
            raise ValueError
        case = CaseState.model_validate(value["case"])
        evidence = EvidenceBundle.model_validate(value["evidence"])
        catalog = validate_grounded_request(
            GroundedRequest.model_validate(value["catalog_request"])
        )
        requirements = ProposalRequirements.model_validate(value["proposal_requirements"])
        if (
            case.pending_proposal_id is not None
            or catalog.case != case
            or catalog.evidence != evidence
            or type(value["user_message"]) is not str
            or catalog.user_message != value["user_message"].strip()
            or not value["user_message"].strip()
            or len(value["user_message"]) > 20000
            or requirements.case_id != case.case_id
            or requirements.case_revision != case.case_revision
            or [(t.name, t.question) for t in requirements.question_targets]
            != [(g.name, g.question) for g in catalog.gaps if g.kind == "user"]
        ):
            raise ValueError
        active = {
            f.name.casefold()
            for f in case.facts
            if f.status == "active" and f.provenance_kind == "user"
        }
        if any(t.name.casefold() in active for t in requirements.question_targets):
            raise ValueError
        return value
    except (ValueError, TypeError, AttributeError, RecursionError):
        raise BroaderProposalRejected() from None


def _fixtures(fixtures):
    if type(fixtures) is not dict or not fixtures:
        raise BroaderProposalRejected()
    rows = {key: _row(value) for key, value in fixtures.items()}
    if any(key != row["id"] for key, row in rows.items()):
        raise BroaderProposalRejected()
    return rows


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
        raise BroaderProposalRejected()
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
        raise BroaderProposalRejected()
    jobs = [_job(job, fixtures) for job in batch["jobs"]]
    if (
        len({job["job_id"] for job in jobs}) != 2
        or {job["arm"] for job in jobs} != set(ARMS)
        or len({job["scenario_id"] for job in jobs}) != 1
        or len({job["round"] for job in jobs}) != 1
        or jobs[0]["snapshot_ids"] != jobs[1]["snapshot_ids"]
    ):
        raise BroaderProposalRejected()
    return jobs


def state_run_id(method, job, row):
    experiment = method.get("experiment_id")
    if type(experiment) is not str or not experiment:
        raise BroaderProposalRejected()
    return str(uuid5(NAMESPACE_URL, json.dumps([experiment, job["job_id"], row["id"]])))


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
        raise BroaderProposalRejected()
    if sum(slot.amount_usd for slot in slots) > Decimal("0.06"):
        raise BroaderProposalRejected()
    return tuple(slots)


class _FixedSnapshot:
    def __init__(self, job, row, records):
        self.job, self.row, self.records = deepcopy(job), deepcopy(row), records
        self.calls = 0

    def search(self, request):
        bundle = EvidenceBundle.model_validate(self.row["evidence"])
        if self.calls >= 2 or request.snapshot_id != bundle.snapshot_id:
            raise BroaderProposalRejected()
        self.calls += 1
        self.records.append(
            {
                "job_id": self.job["job_id"],
                "arm": self.job["arm"],
                "snapshot_id": self.row["id"],
                "case_revision": self.row["case"]["case_revision"],
                "supplier_call": self.calls,
                "queries": list(request.queries),
                "request": request.model_dump(mode="json"),
                "returned_bundle_sha256": _digest(bundle.model_dump(mode="json")),
                "actual_search": False,
                "complete_current_record_set": True,
            }
        )
        return bundle.model_copy(deep=True)


def fixed_snapshot_factory(packet, fixtures, records):
    fixtures = _fixtures(fixtures)
    if (
        type(packet) is not dict
        or type(packet.get("snapshots")) is not list
        or type(records) is not list
    ):
        raise BroaderProposalRejected()
    validated = [_row(row) for row in packet["snapshots"]]
    supplied = {row["id"]: row for row in validated}
    if len(supplied) != len(packet["snapshots"]) or supplied != fixtures:
        raise BroaderProposalRejected()

    def factory(job, row):
        job = _job(job, fixtures)
        row = _row(row)
        if row["id"] not in job["snapshot_ids"] or row != fixtures[row["id"]]:
            raise BroaderProposalRejected()
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
    if arm == "grounded_quotes":
        values.update(
            response_mode="grounded_plan",
            grounded_decision_contracts=True,
            grounded_source_selection_reminder=True,
            grounded_source_gap_handoff=True,
            grounded_source_gap_investigation=True,
            grounded_source_capacity=True,
            grounded_compact_plan=True,
        )
    return MetisConfig.model_validate(values)


def _message_observation(messages):
    return {
        "messages_sha256": _digest(messages),
        "input_bytes_plus_guard": len(json.dumps(messages, ensure_ascii=False).encode()) + 1024,
    }


def _grounded_reasoner(planner, registered):
    return GroundedReasoner(
        planner,
        request_factory=lambda case, message, evidence: make_grounded_request(
            case,
            message,
            evidence,
            gaps=registered.gaps,
            conflict_groups=registered.conflict_groups,
        ),
        source_gap_handoff=True,
        source_gap_investigation=True,
        ask_source_background=True,
        concise_user_draft=True,
    )


class _Planner(QualityPlanner):
    def plan(self, request, *, context):
        try:
            return super().plan(request, context=context)
        finally:
            if self.records and self.records[-1].get("context") == context.model_dump(mode="json"):
                self.records[-1].update(
                    _message_observation(
                        configured_grounded_messages(
                            self.gateway.config,
                            request,
                            context,
                        )
                    )
                )


class _Analysis:
    def __init__(self, gateway, counted, records):
        self.gateway, self.counted, self.records = gateway, counted, records

    def analyze(self, case, user_message, evidence, *, context):
        record = {
            "context": context.model_dump(mode="json"),
            "case": case.model_dump(mode="json"),
            "user_message": user_message,
            "evidence": evidence.model_dump(mode="json"),
            "analysis": None,
            "error_code": None,
            **_message_observation(
                build_messages(
                    case,
                    user_message,
                    evidence,
                    context=context,
                    feedback=context.output_feedback,
                    policy="compiled_rules",
                )
            ),
        }
        self.records.append(record)
        try:
            if not self.counted.ledger.quarantine_scope_status(self.counted.scope_id).active:
                raise ReasoningStopped("BudgetExceeded", "budget_stopped")
            self.counted.current = request_id_for(context)
            raw = self.gateway.analyze(case, user_message, evidence, context=context)
            record["output_sha256"] = sha(raw.encode())
            try:
                decoded = json.loads(raw)
            except ValueError:
                decoded = raw
            if contains_secret(decoded, self.gateway.config.api_key.get_secret_value()):
                record["credential_echo_rejected"] = True
                raise ReasoningStopped("ProviderResponseInvalid")
            try:
                result = AnalysisResult.model_validate_json(raw)
                record["analysis"] = result.model_dump(mode="json")
                record["schema_observation"] = {
                    "syntactic_valid": True,
                    "validation_error_count": 0,
                }
            except ValidationError as error:
                record["schema_observation"] = {
                    "syntactic_valid": False,
                    "validation_error_count": error.error_count(),
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
        raise BroaderProposalRejected()
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
                    MetisGroundedPlanner(cfg, ledger, transport=SharedTransport(counted))
                    if job["arm"] == "grounded_quotes"
                    else MetisReasoner(cfg, ledger, transport=SharedTransport(counted))
                )
                start = len(attempts)
                planner = None
                try:
                    if job["arm"] == "grounded_quotes":
                        planner = _Planner(gateway, counted, attempts)
                        reasoner = _grounded_reasoner(planner, registered)
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
                                grounded_request=planner.supplied_request() if planner else None,
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
        self._record(
            configured_grounded_messages(self.config, request, context), context, request.evidence
        )

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
        raise BroaderProposalRejected()
    validated = [_row(row) for row in packet["snapshots"]]
    fixtures = _fixtures({row["id"]: row for row in validated})
    if len(fixtures) != len(packet["snapshots"]):
        raise BroaderProposalRejected()
    base = MetisConfig(api_key="authored-public-preflight-key")
    rows = []
    for row in fixtures.values():
        case = CaseState.model_validate(row["case"])
        request = GroundedRequest.model_validate(row["catalog_request"])
        requirements = ProposalRequirements.model_validate(row["proposal_requirements"])
        for arm in ARMS:
            config = _config(base, arm, "authored-preflight-scope")
            probe = _OfflineProbe(row, arm, config, rows)
            reasoner = _grounded_reasoner(probe, request) if arm == "grounded_quotes" else probe
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
                run_id="authored-broader-preflight",
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
    }
