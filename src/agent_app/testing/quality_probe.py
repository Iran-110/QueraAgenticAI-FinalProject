"""Fresh finite model experiments using fixed evidence and explicit quarantine funding.

The existing conditional HTTP runner owns future user replies. The actual ledger
and provider gateway are used; no old authorization is relabelled or restarted.
"""

import json
from dataclasses import asdict
from decimal import Decimal
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from agent_app import api
from agent_app.contracts import GroundedGap, GroundedPlan, ReasoningContext
from agent_app.evaluation.routes import RouteGraph
from agent_app.evaluation.runner import CaseRun, _decide
from agent_app.llm.budget import ExperimentRequestSlot
from agent_app.llm.config import METIS_CHAT_URL, MetisConfig
from agent_app.llm.grounded import MetisGroundedPlanner
from agent_app.llm.metis import request_id_for
from agent_app.llm.pricing import get_price
from agent_app.orchestration import SupportEngine
from agent_app.orchestration.ports import ReasoningStopped
from agent_app.reasoning.catalog import caller_catalog
from agent_app.reasoning.grounding import GroundedReasoner, make_grounded_request
from agent_app.testing.dev_three_model_probe import (
    INPUT_PROFILES,
    MODEL,
    DevProbeRejected,
    SharedTransport,
    contains_secret,
    ledger_observation,
    sha,
)
from agent_app.testing.fakes import FakeRetriever
from agent_app.testing.plan_observation import observe_plan_output
from agent_app.testing.pre_dispatch_usage import (
    PreDispatchUsage,
    attest_pre_dispatch_stop,
    transport_absent,
)
from agent_app.testing.provider_observation import ObservedStream, transport_category
from agent_app.testing.stability_probe import invocation
from agent_app.testing.stability_probe import slots_for_batch as historical_slots
from agent_app.tracker.dummy_tracker import DummyTracker


def quality_slots(protocol, batch, fixtures):
    slots = []
    for job in batch["jobs"]:
        original = historical_slots(protocol, {**batch, "jobs": [job]}, fixtures)
        for slot in original:
            output = job["max_output_tokens"]
            reserve = job.get("input_token_reserve", slot.input_token_reserve)
            if (
                type(reserve) is not int
                or reserve not in (16384, 24576, 32768)
                or (reserve == 32768 and batch["kind"] != "real_index")
            ):
                raise DevProbeRejected()
            slots.append(
                ExperimentRequestSlot(
                    **{
                        **asdict(slot),
                        "input_token_reserve": reserve,
                        "max_output_tokens": output,
                        "amount_usd": get_price(MODEL).cost(reserve, output),
                    }
                )
            )
    if (
        len(slots) > 24
        or len({s.request_id for s in slots}) != len(slots)
        or sum(s.amount_usd for s in slots) > Decimal("0.06")
    ):
        raise DevProbeRejected()
    return tuple(slots)


class QualityTransport(httpx.BaseTransport):
    def __init__(self, underlying, ledger, scope_id, before, *, input_profiles=None):
        self.underlying, self.ledger, self.scope_id, self.before = (
            underlying,
            ledger,
            scope_id,
            before,
        )
        self.current = None
        self.records = []
        self.on_send = None
        self.input_profiles = INPUT_PROFILES if input_profiles is None else dict(input_profiles)

    def handle_request(self, request):
        row = self.ledger.get(self.current) if self.current else None
        scope = self.ledger.quarantine_scope_status(self.scope_id)
        now = ledger_observation(self.ledger._path)
        payload = json.loads(request.content)
        if (
            len(self.records) >= scope.max_requests
            or str(request.url) != METIS_CHAT_URL
            or request.method != "POST"
            or row is None
            or row.status != "reserved"
            or row.model != MODEL
            or row.phase != "development"
            or payload.get("model") != MODEL
            or payload.get("stream") is not False
            or payload.get("max_tokens") not in (1024, 2048)
            or row.amount_usd
            != get_price(MODEL).cost(self.input_profiles[row.case_id], payload["max_tokens"])
            or scope.block_reason != "PendingRequest"
            or now["counts"].get("reserved") != 1
            or any(
                now[name] != self.before[name]
                for name in ("meta_sha256", "unknown_sha256", "old_grants_sha256")
            )
        ):
            raise ReasoningStopped("BudgetExceeded", "budget_stopped")
        record = {
            "request_id": self.current,
            "http_send_started": False,
            "verified_returned_model": None,
            "wire_messages_sha256": sha(
                json.dumps(payload["messages"], ensure_ascii=False, sort_keys=True).encode()
            ),
            "wire_max_output_tokens": payload["max_tokens"],
        }
        self.records.append(record)
        if self.on_send:
            self.on_send()
        record["http_send_started"] = True
        try:
            response = self.underlying.handle_request(request)
        except Exception as error:
            record["transport_error_category"] = transport_category(error)
            raise
        record["http_status"] = response.status_code
        headers = dict(response.headers)
        headers.pop("content-encoding", None)
        headers.pop("content-length", None)
        return httpx.Response(
            response.status_code,
            headers=headers,
            stream=ObservedStream(response, record, MODEL),
            extensions=response.extensions,
            request=request,
        )

    def close(self):
        self.underlying.close()


class QualityPlanner:
    def __init__(self, gateway, counted, records):
        self.gateway, self.counted, self.records = gateway, counted, records
        self.latest = None

    def supplied_request(self):
        return self.latest.model_copy(deep=True) if self.latest else None

    def plan(self, request, *, context):
        record = {
            "context": context.model_dump(mode="json"),
            "request": request.model_dump(mode="json"),
            "plan": None,
            "error_code": None,
        }
        self.records.append(record)
        self.latest = request.model_copy(deep=True)
        try:
            if not self.counted.ledger.quarantine_scope_status(self.counted.scope_id).active:
                raise ReasoningStopped("BudgetExceeded", "budget_stopped")
            self.counted.current = request_id_for(context)
            ledger_absent_before = self.counted.ledger.get(self.counted.current) is None
            transport_absent_before = transport_absent(self.counted.records, self.counted.current)
            try:
                raw = self.gateway.plan(request, context=context)
            except ReasoningStopped as error:
                attestation = attest_pre_dispatch_stop(
                    self.gateway,
                    self.counted,
                    context,
                    error,
                    ledger_absent_before=ledger_absent_before,
                    transport_absent_before=transport_absent_before,
                )
                if attestation is not None:
                    record["pre_dispatch_stop"] = attestation
                raise
            record["output_sha256"] = sha(raw.encode())
            secret = self.gateway.config.api_key.get_secret_value()
            try:
                decoded = json.loads(raw)
            except ValueError:
                decoded = raw
            if contains_secret(decoded, secret):
                record["credential_echo_rejected"] = True
                raise ReasoningStopped("ProviderResponseInvalid")
            record["schema_observation"] = observe_plan_output(raw)
            try:
                record["plan"] = GroundedPlan.model_validate_json(raw).model_dump(mode="json")
            except ValueError:
                record["plan"] = None
            return raw
        except ReasoningStopped as error:
            record["error_code"] = error.code
            raise
        finally:
            self.counted.current = None


def run_quality_batch(
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
    if config.continuation_id != batch["scope_id"] or not config.grounded_source_gap_handoff:
        raise DevProbeRejected()
    if retriever_factory is not None and not callable(retriever_factory):
        raise DevProbeRejected()
    input_profiles = {}
    for job in batch["jobs"]:
        if type(job.get("repair_repeated_queries", False)) is not bool:
            raise DevProbeRejected()
        reserve = job.get("input_token_reserve", INPUT_PROFILES[job["case_id"]])
        if (
            type(reserve) is not int
            or reserve not in (16384, 24576, 32768)
            or (reserve == 32768 and batch["kind"] != "real_index")
            or input_profiles.get(job["case_id"], reserve) != reserve
        ):
            raise DevProbeRejected()
        input_profiles[job["case_id"]] = reserve
    counted = QualityTransport(
        underlying or httpx.HTTPTransport(retries=0),
        ledger,
        batch["scope_id"],
        before,
        input_profiles=input_profiles,
    )
    jobs, attempts = [], []
    stopped = False
    if checkpoint:
        counted.on_send = lambda: checkpoint(
            {
                "event": "reserved_before_transport",
                "jobs": jobs,
                "attempts": attempts,
                "provider_sends": counted.records,
            }
        )
    try:
        for job in batch["jobs"]:
            if not ledger.quarantine_scope_status(batch["scope_id"]).active:
                stopped = True
                break
            fixture = fixtures[job.get("fixture_id", job["case_id"])]
            ports = []
            start = len(attempts)

            def adapters(_case_id, turn, fixture=fixture, job=job, ports=ports):
                if retriever_factory is None:
                    bundle = fixture.bundles[turn["evidence_bundle"]]
                    retriever, snapshot_id = FakeRetriever([bundle, bundle]), bundle.snapshot_id
                else:
                    retriever, snapshot_id = retriever_factory(job, turn)
                reserve = input_profiles[fixture.case["case_id"]]
                case_config = MetisConfig.model_validate(
                    {
                        **config.model_dump(),
                        "grounded_decision_contracts": True,
                        "grounded_source_selection_reminder": job.get(
                            "source_selection_reminder", False
                        ),
                        "grounded_resource_guidance": job.get("resource_guidance", False),
                        "max_output_tokens": job["max_output_tokens"],
                        "input_token_reserve": reserve,
                        "max_request_usd": get_price(MODEL).cost(reserve, job["max_output_tokens"]),
                    }
                )
                gateway = MetisGroundedPlanner(
                    case_config, ledger, transport=SharedTransport(counted)
                )
                ports.append(gateway)
                planner = QualityPlanner(gateway, counted, attempts)

                def request_factory(case, message, evidence):
                    request = caller_catalog(case, message, evidence, definitions=definitions)
                    overrides = job.get("catalog_overrides")
                    gaps = (
                        tuple(GroundedGap.model_validate(gap) for gap in overrides["gaps"])
                        if overrides is not None
                        else request.gaps
                    )
                    groups = tuple(tuple(group) for group in job.get("conflict_groups", ()))
                    if groups or overrides is not None:
                        request = make_grounded_request(
                            case, message, evidence, gaps=gaps, conflict_groups=groups
                        )
                    return request

                return api.RunAdapters(
                    retriever=retriever,
                    reasoner=GroundedReasoner(
                        planner,
                        request_factory=request_factory,
                        source_gap_handoff=True,
                        source_gap_investigation=True,
                    ),
                    snapshot_id=snapshot_id,
                    grounded_request_supplier=planner.supplied_request,
                    cleanup=gateway.close,
                )

            case_run = CaseRun(
                fixture,
                adapters,
                PreDispatchUsage(ledger, attempts, counted.records),
                mode="live",
                invocation_id=invocation(protocol, job),
                route_graph=RouteGraph.from_fixture(fixture.data),
            )
            try:

                def scoped_engine(*args, job=job, **kwargs):
                    return SupportEngine(
                        *args,
                        **kwargs,
                        evidence_scope="exact_user_version",
                        repair_repeated_queries=job.get("repair_repeated_queries", False),
                    )

                engine_factory = (
                    scoped_engine
                    if batch["kind"] in {"adversarial", "real_index"}
                    else SupportEngine
                )
                with (
                    patch.object(api, "_cases", {}),
                    patch.object(api, "tracker", DummyTracker()),
                    patch.object(api, "SupportEngine", engine_factory),
                ):
                    with TestClient(api.app) as client:
                        case_run.run(client)
                        if (
                            len(fixture.data["turns"]) > 1
                            and fixture.data["turns"][1]["expect"].get(
                                "previous_proposal_now_stale"
                            )
                            and len(case_run.steps) >= 2
                        ):
                            first = case_run.steps[0].get("proposal", {})
                            if first.get("proposal_id"):
                                previous = client.get(f"/cases/{fixture.case['case_id']}").json()
                                wires = len(counted.records)
                                refused = _decide(client, fixture.case["case_id"], first, "approve")
                                case_run.record.check(
                                    "correction",
                                    "stale approval rejected without mutation or new model send",
                                    refused.status_code == 409
                                    and client.get(f"/cases/{fixture.case['case_id']}").json()
                                    == previous
                                    and len(counted.records) == wires,
                                    refused.status_code,
                                )
            finally:
                for gateway in ports:
                    gateway.reasoner.client.close()
            for step in case_run.steps:
                step.pop("view_after", None)
            jobs.append(
                {
                    **job,
                    "fixture_id": fixture.data["fixture_id"],
                    "fixture_sha256": fixture.sha256,
                    "coverage_complete": case_run.route_complete,
                    "selected_turns": case_run.route_visits,
                    "checks": case_run.record.checks,
                    "steps": case_run.steps,
                    "run_ids": list(
                        dict.fromkeys(a["context"]["run_id"] for a in attempts[start:])
                    ),
                }
            )
            if checkpoint:
                checkpoint({"jobs": jobs, "attempts": attempts, "provider_sends": counted.records})
            if not ledger.quarantine_scope_status(batch["scope_id"]).active and len(jobs) < len(
                batch["jobs"]
            ):
                stopped = True
                break
    finally:
        counted.close()
    after = ledger_observation(ledger._path)
    return {
        "batch_id": batch["batch_id"],
        "kind": batch["kind"],
        "scope_id": batch["scope_id"],
        "jobs": jobs,
        "attempts": attempts,
        "provider_sends": counted.records,
        "actual_sends": sum(item["http_send_started"] for item in counted.records),
        "accounting": PreDispatchUsage(ledger, attempts, counted.records).measure(
            [ReasoningContext.model_validate(a["context"]) for a in attempts]
        ),
        "planned_jobs": len(batch["jobs"]),
        "visited_jobs": len(jobs),
        "completed_routes": sum(j["coverage_complete"] for j in jobs),
        "stopped_early": stopped,
        "ledger_after": after,
        "original_accounting_preserved": all(
            after[name] == before[name]
            for name in ("meta_sha256", "unknown_sha256", "old_grants_sha256")
        ),
    }
