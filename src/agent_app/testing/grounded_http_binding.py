"""Fixture-only binding of the real grounded gateway to persistent HTTP.

The caller owns a freshly created temporary ledger and explicit fixture ports.
There is no environment configuration, real HTTP transport or provider key.
Authored plans are mock responses, never an independent decision-quality test.
"""

import json
from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import asdict
from decimal import Decimal
from threading import RLock
from typing import Literal, get_args

import httpx

from agent_app import api
from agent_app.contracts import (
    CaseState,
    EvidenceBundle,
    GroundedPlan,
    GroundedRequest,
)
from agent_app.llm.budget import BudgetLedger
from agent_app.llm.config import MetisConfig
from agent_app.llm.grounded import MetisGroundedPlanner
from agent_app.llm.metis import request_id_for
from agent_app.orchestration.ports import GroundedPlanner, Retriever
from agent_app.reasoning.catalog import runtime_catalog as runtime_catalog
from agent_app.reasoning.grounding import (
    GroundedReasoner,
    validate_grounded_request,
)

type GatewayFault = Literal[
    "normal", "malformed_first", "malformed_all", "model_mismatch", "timeout"
]
type RequestFactory = Callable[[CaseState, str, EvidenceBundle], GroundedRequest]


def _plain(value):
    return json.loads(
        json.dumps(
            value, default=lambda item: str(item) if isinstance(item, Decimal) else asdict(item)
        )
    )


def _best_effort_close(value):
    try:
        cleanup = getattr(value, "close", None)
        if callable(cleanup):
            cleanup()
    except Exception:
        pass


class _GatewayBridge:
    """One run's synchronous transport state; never shared with another case."""

    def __init__(self, authored: GroundedPlanner, ledger: BudgetLedger, fault: GatewayFault):
        self.authored = authored
        self.ledger = ledger
        self.fault = fault
        self.lock = RLock()
        self.records = []
        self.current = None
        self.request = None
        self.context = None
        self.latest_request = None
        self.closed = False
        self.gateway = MetisGroundedPlanner(
            MetisConfig(
                api_key="public-synthetic-persistent-grounded-key",
                live_enabled=True,
                model="gpt-4o-mini",
                phase="development",
                response_mode="grounded_plan",
                input_token_reserve=32768,
                max_output_tokens=1024,
                max_request_usd=Decimal("0.02"),
            ),
            ledger,
            transport=httpx.MockTransport(self.respond),
        )

    def capture(self, factory: RequestFactory, case, message, evidence):
        request = validate_grounded_request(factory(case, message, evidence))
        self.latest_request = request.model_copy(deep=True)
        return request

    def supplied_request(self):
        with self.lock:
            return self.latest_request.model_copy(deep=True) if self.latest_request else None

    def respond(self, incoming: httpx.Request) -> httpx.Response:
        # Only the JSON body is observed. Authorization and request headers are
        # deliberately absent from both fixture callbacks and receipt records.
        if self.current is None or self.request is None or self.context is None:
            raise ValueError("MockGatewayContextMissing")
        payload = json.loads(incoming.content)
        self.current["provider_payload"] = payload
        self.current["transport_called"] = True
        reservation = self.ledger.get(self.current["request_id"])
        if reservation is None or reservation.status != "reserved":
            raise ValueError("MockGatewayReservationMissing")
        self.current["reservation_before_response"] = _plain(reservation)
        data = json.loads(payload["messages"][1]["content"])
        if set(data) != {
            "capacity",
            "repair_issue_codes",
            "request",
            "response_schema",
            "source_references",
        }:
            raise ValueError("MockGatewayPayloadInvalid")
        prepared = GroundedRequest.model_validate(data["request"])
        if prepared != self.request or data["response_schema"]["title"] != "GroundedPlan":
            raise ValueError("MockGatewayRequestMismatch")
        if self.fault == "timeout":
            raise httpx.ReadTimeout("Fixture timeout", request=incoming)
        output = self.authored.plan(
            prepared.model_copy(deep=True), context=self.context.model_copy(deep=True)
        )
        if isinstance(output, GroundedPlan):
            output = output.model_dump_json()
        elif isinstance(output, Mapping):
            output = json.dumps(dict(output))
        if self.fault == "malformed_all" or (
            self.fault == "malformed_first" and self.context.attempt_index == 1
        ):
            output = "{not-plan-json"
        return httpx.Response(
            200,
            json={
                "model": "gpt-4.1-mini"
                if self.fault == "model_mismatch"
                else "gpt-4o-mini-2024-07-18",
                "usage": {"prompt_tokens": 125, "completion_tokens": 75, "total_tokens": 200},
                "choices": [
                    {"finish_reason": "stop", "message": {"role": "assistant", "content": output}}
                ],
            },
        )

    def plan(self, request, *, context):
        with self.lock:
            if self.gateway.reasoner.client.is_closed:
                raise ValueError("MockGatewayClosed")
            self.request = request.model_copy(deep=True)
            self.context = context.model_copy(deep=True)
            record = {
                "request_id": request_id_for(context),
                "context": context.model_dump(mode="json"),
                "transport_called": False,
            }
            self.current = record
            try:
                return self.gateway.plan(request, context=context)
            finally:
                record["reservation_after_attempt"] = _plain(self.ledger.get(record["request_id"]))
                self.records.append(record)
                self.current = self.request = self.context = None

    def close(self):
        with self.lock:
            if self.closed:
                return
            self.closed = True
            try:
                self.gateway.close()
            finally:
                cleanup = getattr(self.authored, "close", None)
                if callable(cleanup):
                    cleanup()


class GroundedHttpBinding:
    """Explicit caller-owned fixture composition, with a fresh bridge per run.

    ``ledger`` must be a newly created ledger in the runner's temporary directory.
    It is supplied directly; this module never resolves or opens any ledger path.
    A binding may be used for multiple cases; each run gets independent planner,
    transport, request capture and counters. The persistent service must invoke
    its returned cleanup callback after consuming the grounded-request supplier.
    """

    def __init__(
        self,
        ledger: BudgetLedger,
        *,
        snapshot_id: str,
        retriever_factory: Callable[[], Retriever],
        planner_factory: Callable[[], GroundedPlanner],
        request_factory: RequestFactory = runtime_catalog,
        fault: GatewayFault = "normal",
        retain_records: bool = True,
    ):
        if (
            not isinstance(ledger, BudgetLedger)
            or not all(
                callable(value) for value in (retriever_factory, planner_factory, request_factory)
            )
            or fault not in get_args(GatewayFault.__value__)
            or type(retain_records) is not bool
        ):
            raise ValueError("InvalidGroundedBindingConfiguration")
        try:
            EvidenceBundle(snapshot_id=snapshot_id)
        except Exception:
            raise ValueError("InvalidGroundedBindingConfiguration") from None
        self.ledger = ledger
        self.snapshot_id = snapshot_id
        self.retriever_factory = retriever_factory
        self.planner_factory = planner_factory
        self.request_factory = request_factory
        self.fault = fault
        self.retain_records = retain_records
        self._bridges = []
        self._retrievers = []
        self._lock = RLock()
        self._closed = False

    def adapters(self, _scenario) -> api.RunAdapters:
        with self._lock:
            if self._closed:
                raise ValueError("GroundedBindingClosed")
            retriever = self.retriever_factory()
            if not callable(getattr(retriever, "search", None)):
                _best_effort_close(retriever)
                raise ValueError("InvalidGroundedBindingConfiguration")
            if any(retriever is prior for prior in self._retrievers):
                # Do not close a resource that belongs to a different active run.
                raise ValueError("InvalidGroundedBindingConfiguration")
            planner = self.planner_factory()
            if any(planner is prior.authored for prior in self._bridges):
                raise ValueError("InvalidGroundedBindingConfiguration")
            if not callable(getattr(planner, "plan", None)):
                _best_effort_close(planner)
                raise ValueError("InvalidGroundedBindingConfiguration")
            try:
                bridge = _GatewayBridge(planner, self.ledger, self.fault)
            except Exception:
                _best_effort_close(planner)
                raise
            self._bridges.append(bridge)
            self._retrievers.append(retriever)
        try:
            reasoner = GroundedReasoner(
                bridge,
                request_factory=lambda case, message, evidence: bridge.capture(
                    self.request_factory, case, message, evidence
                ),
            )
            return api.RunAdapters(
                retriever,
                reasoner,
                snapshot_id=self.snapshot_id,
                grounded_request_supplier=bridge.supplied_request,
                cleanup=lambda: self._release(bridge, retriever),
            )
        except Exception:
            self._release(bridge, retriever)
            raise

    def _release(self, bridge, retriever):
        try:
            bridge.close()
        finally:
            # Acceptance runners keep complete authored traces. The runnable
            # console must release each finished run instead of accumulating
            # user messages, source payloads and closed clients indefinitely.
            if not self.retain_records and bridge.gateway.reasoner.client.is_closed:
                with bridge.lock:
                    bridge.latest_request = None
                    bridge.records.clear()
                with self._lock:
                    self._bridges = [prior for prior in self._bridges if prior is not bridge]
                    self._retrievers = [
                        prior for prior in self._retrievers if prior is not retriever
                    ]

    @property
    def records(self) -> list[dict]:
        with self._lock:
            bridges = list(self._bridges)
        result = []
        for bridge in bridges:
            with bridge.lock:
                result.extend(deepcopy(bridge.records))
        return result

    @property
    def all_clients_closed(self) -> bool:
        with self._lock:
            bridges = list(self._bridges)
        return all(bridge.gateway.reasoner.client.is_closed for bridge in bridges)

    def snapshot(self) -> dict:
        records = self.records
        # DuplicateModelRequest can observe the existing settled reservation;
        # repeated observations must not count it as another settled request.
        rows = {
            record["request_id"]: record["reservation_after_attempt"] for record in records
        }.values()
        rows = list(rows)
        return {
            "record_scope": "this_binding",
            "ledger_scope": "caller_ledger",
            "transport_calls": sum(record["transport_called"] for record in records),
            "settled_reservations": sum(
                row is not None and row["status"] == "settled" for row in rows
            ),
            "reserved_reservations": sum(
                row is not None and row["status"] == "reserved" for row in rows
            ),
            "uncertain_reservations": sum(
                row is not None and row["status"] == "uncertain" for row in rows
            ),
            "ledger": _plain(self.ledger.snapshot()),
            "actual_paid_requests": 0,
            "actual_API_cost_USD": "0",
            "quality_claim": False,
            "records_retained": self.retain_records,
            "all_clients_closed": self.all_clients_closed,
        }

    def close(self):
        with self._lock:
            self._closed = True
            resources = list(zip(self._bridges, self._retrievers, strict=True))
        failed = False
        for bridge, retriever in resources:
            try:
                self._release(bridge, retriever)
            except Exception:
                failed = True
        if failed:
            raise ValueError("GroundedBindingCleanupFailed") from None
