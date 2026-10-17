"""Run registered evaluation fixtures through the UI's HTTP API.

Each case is replayed turn by turn: the API only ever receives the current
turn's ``visible`` input, so later turns, gold labels and expectations never
reach the agent early. Checks read the API's stored state, not response text.

Two modes write separate receipts:

- ``offline`` uses each turn's scripted ``agent_script`` and the fixture's
  frozen evidence. It shows operational behaviour only, never decision quality.
- ``live`` uses caller-supplied real adapters (``--adapters module:factory``).
  Scripted outputs are ignored. Cost and tokens come from the shared ledger the
  factory exposes; live runs must follow the team budget rules.

Decision labels and operational checks do not establish claim support or gap
necessity. Both modes leave semantic quality unmeasured. Live conversations
follow a fixed fixture path; an incompatible approved question stops that path
as incomplete coverage. Accounting joins observed reasoning attempts only and
keeps settled cost separate from uncertain or reserved amounts.
"""

import argparse
import hashlib
import importlib
import json
import re
import subprocess
import sys
import time
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, Protocol, get_args
from unittest.mock import patch
from uuid import NAMESPACE_URL, uuid4, uuid5

from fastapi.testclient import TestClient

from agent_app import api
from agent_app.contracts import AnalysisResult, EvidenceBundle, ReasoningContext
from agent_app.evaluation.preflight import validate_final_bundle
from agent_app.evaluation.provider_metadata import optional_provider_metadata
from agent_app.evaluation.routes import ConditionalRoutesRejected, RouteGraph
from agent_app.llm.budget import BudgetLedger
from agent_app.llm.metis import request_id_for
from agent_app.llm.pricing import get_price, same_verified_price
from agent_app.orchestration import engine as engine_module
from agent_app.orchestration.intake import STREAMLIT_VERSION_QUESTION
from agent_app.orchestration.ports import Reasoner, ReasoningStopCode, Retriever
from agent_app.testing.fakes import FakeReasoner, FakeRetriever
from agent_app.tracker.dummy_tracker import DummyTracker

ROOT = Path(__file__).resolve().parents[3]
Mode = Literal["offline", "live"]


class LiveAdapters(Protocol):
    """Real adapters for one evaluation run.

    ``for_case`` receives only the case ID: fixtures, gold and scripted outputs
    are never passed to a live agent. ``config`` (model, prompt policy, snapshot)
    is copied through a public metadata allowlist; credentials are forbidden.
    """

    ledger: BudgetLedger
    config: dict[str, Any]

    def for_case(self, case_id: str) -> api.RunAdapters: ...


@dataclass
class Fixture:
    path: Path
    data: dict[str, Any]
    bundles: dict[str, EvidenceBundle]
    sha256: str

    @property
    def case(self) -> dict[str, Any]:
        return self.data["case"]


def load_fixture(path: Path, *, mode: Mode = "offline") -> Fixture:
    raw = path.read_bytes()
    data = json.loads(raw)
    source = data["evidence_source"]
    evidence_path = (ROOT / source["path"]).resolve()
    if not evidence_path.is_relative_to(ROOT.resolve()) or evidence_path.suffix != ".json":
        raise ValueError("EvidenceSourcePathRejected")
    evidence = evidence_path.read_bytes()
    if hashlib.sha256(evidence).hexdigest() != source["sha256"]:
        raise ValueError("Evidence source does not match its registered SHA-256.")
    bundles = {
        name: EvidenceBundle.model_validate(json.loads(evidence)["evidence_bundles"][name])
        for name in source["bundles_used"]
    }
    case_ids = {data["case"]["case_id"], *data["case"].get("extra_case_ids", [])}
    for turn in data["turns"]:
        faults = turn.get("faults", {})
        if set(faults) - {"retrieval", "reasoning_errors"}:
            raise ValueError(f"{turn['id']}: unknown fault.")
        stops_early = faults.get("retrieval") or faults.get("reasoning_errors", 0) >= 2
        if mode == "offline" and turn.get("agent_script") is not None:
            AnalysisResult.model_validate(turn["agent_script"])
        elif mode == "offline" and not stops_early:
            raise ValueError(
                f"{turn['id']}: agent_script is required unless a fault stops the run."
            )
        if turn["evidence_bundle"] not in bundles:
            raise ValueError(f"{turn['id']}: unknown evidence bundle.")
        if turn.get("case_id", data["case"]["case_id"]) not in case_ids:
            raise ValueError(f"{turn['id']}: case_id is not declared in the fixture.")
    return Fixture(path, data, bundles, hashlib.sha256(raw).hexdigest())


def collect(paths: list[Path], *, mode: Mode = "offline") -> list[Fixture]:
    """Load fixtures from files or split directories and guard split integrity."""
    files: list[Path] = []
    for path in paths:
        files.extend(sorted(path.glob("*.json")) if path.is_dir() else [path])
    fixtures = [load_fixture(path, mode=mode) for path in files]
    if not fixtures:
        raise ValueError("No fixtures found.")
    seen: dict[str, Path] = {}
    family_split: dict[int, str] = {}
    for fixture in fixtures:
        case = fixture.case
        for case_id in (case["case_id"], *case.get("extra_case_ids", [])):
            if case_id in seen:
                raise ValueError(f"Duplicate case_id {case_id}.")
            seen[case_id] = fixture.path
        if case["split"] == "test" and not case["test_eligible"]:
            raise ValueError(f"{case['case_id']} is not eligible for the test split.")
        for issue in case["family_issue_ids"]:
            if family_split.setdefault(issue, case["split"]) != case["split"]:
                raise ValueError(f"Issue #{issue} appears in both dev and test.")
    return fixtures


class Recorder:
    def __init__(self) -> None:
        self.checks: list[dict[str, Any]] = []

    def check(self, step: str, name: str, passed: bool, detail: Any = None) -> None:
        self.checks.append({"step": step, "check": name, "passed": bool(passed), "detail": detail})


def _event(turn: dict[str, Any], revision: int, reply_to: str | None) -> dict[str, Any]:
    visible = turn["visible"]
    event = {
        "message": visible["message"],
        "scenario": "ask",  # Ignored: the runner supplies its own adapters.
        "turn_id": turn["id"],
        "expected_revision": revision,
    }
    if visible.get("reply_to_approved_question"):
        event["reply_to_proposal_id"] = reply_to
        return event
    for name in ("reported_facts", "unknowns", "checks_performed", "context_changed"):
        if name in visible:
            event[name] = visible[name]
    return event


def _facts(view: dict[str, Any], status: str) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for fact in view["facts"]:
        if fact["status"] == status:
            found.setdefault(fact["name"], []).append(fact["value"])
    return found


def _assistant_texts(view: dict[str, Any]) -> list[str]:
    return [entry["text"] for entry in view["log"] if entry["role"] == "assistant"]


def _decide(client: TestClient, case_id: str, pending: dict[str, Any], decision: str, **extra):
    return client.post(
        f"/cases/{case_id}/decision",
        json={
            "proposal_id": pending["proposal_id"],
            "case_revision": pending["case_revision"],
            "decision": decision,
            **extra,
        },
    )


@dataclass
class Usage:
    """Join only observed model attempts to durable ledger entries."""

    ledger: BudgetLedger | None

    def measure(self, contexts: list[ReasoningContext]) -> dict[str, Any]:
        records = []
        totals = {"cost_usd": Decimal(0), "reserved_usd": Decimal(0), "uncertain_usd": Decimal(0)}
        tokens: dict[str, int | None] = {"input_tokens": 0, "output_tokens": 0}
        if self.ledger is None:
            return {
                **{name: str(value) for name, value in totals.items()},
                **tokens,
                "settled_usd": "0",
                "accounting_complete": True,
                "requests": [],
                "ledger_halted": None,
            }
        seen = set()
        for context in contexts:
            request_id = request_id_for(context)
            if request_id in seen:
                continue
            seen.add(request_id)
            reservation = self.ledger.get(request_id)
            record = {"request_id": request_id, "context": context.model_dump(mode="json")}
            if reservation is not None and (
                reservation.run_id != context.run_id
                or reservation.case_id != context.case_id
                or reservation.case_revision != context.case_revision
                or reservation.attempt != context.attempt_index
            ):
                reservation = None
                record["status"] = "identity_mismatch"
            elif reservation is None:
                record["status"] = "unrecorded"
            if reservation is not None:
                record.update(
                    status=reservation.status,
                    cost_usd=(
                        str(reservation.cost_usd) if reservation.cost_usd is not None else None
                    ),
                    reserved_amount_usd=str(reservation.amount_usd),
                    input_tokens=reservation.input_tokens,
                    output_tokens=reservation.output_tokens,
                    error_code=(
                        reservation.error_code
                        if reservation.error_code is None
                        or reservation.error_code in get_args(ReasoningStopCode.__value__)
                        else "UnrecognizedLedgerCode"
                    ),
                )
                if reservation.status == "settled":
                    totals["cost_usd"] += reservation.cost_usd or Decimal(0)
                elif reservation.status in {"reserved", "uncertain"}:
                    totals[f"{reservation.status}_usd"] += reservation.amount_usd
            records.append(record)
            for name, total in tokens.items():
                value = getattr(reservation, name, None)
                tokens[name] = None if value is None or total is None else total + value
        complete = all(record["status"] in {"settled", "released"} for record in records)
        return {
            **{name: str(value) for name, value in totals.items()},
            **tokens,
            "cost_usd": str(totals["cost_usd"]) if complete else None,
            "settled_usd": str(totals["cost_usd"]),
            "accounting_complete": complete,
            "requests": records,
            "ledger_halted": self.ledger.snapshot().halted,
        }


@dataclass
class AttemptRecorder:
    reasoner: Reasoner
    contexts: list[ReasoningContext]
    snapshots: set[str]

    def analyze(self, case, user_message, evidence, *, context):
        self.contexts.append(context.model_copy(deep=True))
        self.snapshots.add(evidence.snapshot_id)
        return self.reasoner.analyze(case, user_message, evidence, context=context)


@dataclass
class RetrievalRecorder:
    retriever: Retriever
    rounds: list[int]

    def search(self, request):
        self.rounds.append(len(self.rounds) + 1)
        return self.retriever.search(request)


def _provider_observations(observer, contexts, ledger):
    """Project exact caller identities; malformed optional metadata stays private."""
    fields = {
        "request_id",
        "run_id",
        "case_id",
        "case_revision",
        "attempt_index",
        "prompt_sha256",
        "requested_model",
        "verified_returned_model",
        "http_send_started",
        "http_status",
        "ledger_status",
        "input_tokens",
        "output_tokens",
        "cost_estimated_usd",
        "held_usd",
        "error_code",
    }
    try:
        rows = observer(tuple(context.model_copy(deep=True) for context in contexts))
        expected = {request_id_for(context): context for context in contexts}
        if type(rows) is not list or len(rows) > len(expected):
            raise ValueError
        output, seen = [], set()
        for row in rows:
            optional = {"core_binding", "wire_output"}
            if type(row) is not dict or not fields <= set(row) or set(row) - fields - optional:
                raise ValueError
            identifier = row["request_id"]
            context = expected.get(identifier)
            if context is None or identifier in seen:
                raise ValueError
            seen.add(identifier)
            if any(
                row[key] != getattr(context, key)
                for key in ("run_id", "case_id", "case_revision", "attempt_index")
            ):
                raise ValueError
            if any(type(row[key]) is not int for key in ("case_revision", "attempt_index")):
                raise ValueError
            if (
                type(row["prompt_sha256"]) is not str
                or re.fullmatch(r"[0-9a-f]{64}", row["prompt_sha256"]) is None
            ):
                raise ValueError
            requested, serving = row["requested_model"], row["verified_returned_model"]
            if type(requested) is not str or get_price(requested) is None:
                raise ValueError
            if serving is not None and (
                type(serving) is not str or not same_verified_price(requested, serving)
            ):
                raise ValueError
            if type(row["http_send_started"]) is not bool or (
                row["http_status"] is not None
                and (type(row["http_status"]) is not int or not 100 <= row["http_status"] <= 599)
            ):
                raise ValueError
            if not row["http_send_started"] and (
                row["http_status"] is not None or serving is not None
            ):
                raise ValueError
            if serving is not None and row["http_status"] != 200:
                raise ValueError
            if row["ledger_status"] not in {None, "reserved", "settled", "uncertain", "released"}:
                raise ValueError
            for name in ("input_tokens", "output_tokens"):
                if row[name] is not None and (type(row[name]) is not int or row[name] < 0):
                    raise ValueError
            for name in ("cost_estimated_usd", "held_usd"):
                if row[name] is not None:
                    if type(row[name]) is not str:
                        raise ValueError
                    amount = Decimal(row[name])
                    if not amount.is_finite() or not 0 <= amount <= 5:
                        raise ValueError
            if row["error_code"] is not None and row["error_code"] not in get_args(
                ReasoningStopCode.__value__
            ):
                raise ValueError
            reservation = ledger.get(identifier) if ledger is not None else None
            if reservation is not None:
                if (
                    reservation.run_id != context.run_id
                    or reservation.case_id != context.case_id
                    or reservation.case_revision != context.case_revision
                    or reservation.attempt != context.attempt_index
                ):
                    raise ValueError
                if row["ledger_status"] != reservation.status or requested != reservation.model:
                    raise ValueError
                if (
                    row["input_tokens"] != reservation.input_tokens
                    or row["output_tokens"] != reservation.output_tokens
                ):
                    raise ValueError
                cost = (
                    Decimal(row["cost_estimated_usd"])
                    if row["cost_estimated_usd"] is not None
                    else None
                )
                if cost != reservation.cost_usd:
                    raise ValueError
                if reservation.status in {"reserved", "uncertain"}:
                    if (
                        row["held_usd"] is None
                        or Decimal(row["held_usd"]) != reservation.amount_usd
                    ):
                        raise ValueError
                elif row["held_usd"] is not None and Decimal(row["held_usd"]) != 0:
                    raise ValueError
            elif any(
                row[key] is not None
                for key in (
                    "ledger_status",
                    "input_tokens",
                    "output_tokens",
                    "cost_estimated_usd",
                    "held_usd",
                )
            ):
                raise ValueError
            metadata = optional_provider_metadata(row, request_id=identifier)
            if (
                reservation is not None
                and "core_binding" in metadata
                and metadata["core_binding"]["observed_metis"]["phase"] != reservation.phase
            ):
                raise ValueError
            output.append(
                {
                    **deepcopy({key: value for key, value in row.items() if key in fields}),
                    **metadata,
                }
            )
        return output, None
    except Exception:
        return [], "ProviderObservationsUnavailable"


@dataclass
class CaseRun:
    fixture: Fixture
    adapters: Callable[[str, dict[str, Any]], api.RunAdapters]
    usage: Usage
    mode: Mode = "offline"
    invocation_id: str | None = None
    record: Recorder = field(default_factory=Recorder)
    steps: list[dict[str, Any]] = field(default_factory=list)
    observed_snapshots: set[str] = field(default_factory=set)
    route_graph: RouteGraph | None = None
    route_complete: bool = False
    route_visits: list[str] = field(default_factory=list)
    provider_observer: Callable | None = None

    def _adapters(self, case_id, turn, contexts, rounds):
        ports = self.adapters(case_id, turn)
        return api.RunAdapters(
            RetrievalRecorder(ports.retriever, rounds),
            AttemptRecorder(ports.reasoner, contexts, self.observed_snapshots),
            snapshot_id=ports.snapshot_id,
            grounded_request_supplier=ports.grounded_request_supplier,
            cleanup=ports.cleanup,
            retrieval_profile=ports.retrieval_profile,
        )

    def run(self, client: TestClient) -> None:
        if self.route_graph is not None:
            self._run_conditional(client)
            return
        data = self.fixture.data
        primary = self.fixture.case["case_id"]
        case_ids = [primary, *self.fixture.case.get("extra_case_ids", [])]
        views = {cid: client.get(f"/cases/{cid}").json() for cid in case_ids}
        events: list[tuple[str, dict[str, Any]]] = []
        for turn in data["turns"]:
            case_id = turn.get("case_id", primary)
            others = {cid: views[cid] for cid in case_ids if cid != case_id}
            view, event = self._turn(client, case_id, turn, views[case_id], views)
            views[case_id] = view
            for cid, before in others.items():
                after = client.get(f"/cases/{cid}").json()
                self.record.check(
                    turn["id"], f"case {cid} untouched", after == before, after["case_revision"]
                )
                views[cid] = after
            if event is None:
                return
            events.append((case_id, event))
        self._replay(client, case_ids, events)

    def _replay(self, client, case_ids, events):
        # Every accepted event must replay its original receipt without side effects.
        before = {cid: client.get(f"/cases/{cid}").json() for cid in case_ids}
        for case_id, event in events:
            response = client.post(f"/cases/{case_id}/messages", json=event)
            body = response.json() if response.status_code == 200 else {}
            self.record.check(
                "probe",
                f"replay {event['turn_id']}: replayed receipt",
                response.status_code == 200 and body["intake"]["replayed"],
                response.status_code,
            )
            self.record.check(
                "probe",
                f"replay {event['turn_id']}: revision and log unchanged",
                body.get("case_revision") == before[case_id]["case_revision"]
                and body.get("log") == before[case_id]["log"],
            )

    def _run_conditional(self, client):
        graph = self.route_graph
        data = self.fixture.data
        primary = self.fixture.case["case_id"]
        case_ids = [primary, *self.fixture.case.get("extra_case_ids", [])]
        views = {cid: client.get(f"/cases/{cid}").json() for cid in case_ids}
        turns = {turn["id"]: turn for turn in data["turns"]}
        events = []
        node = graph.node_ids[0]
        while node is not None:
            # A validated forward DAG visits at most its registered 64 nodes;
            # the engine's existing two-attempt/two-round limits remain in force.
            self.route_visits.append(node)
            turn = turns[node]
            case_id = turn.get("case_id", primary)
            others = {cid: views[cid] for cid in case_ids if cid != case_id}
            view, event = self._turn(client, case_id, turn, views[case_id], views)
            views[case_id] = view
            for cid, before in others.items():
                after = client.get(f"/cases/{cid}").json()
                self.record.check(
                    node, f"case {cid} untouched", after == before, after["case_revision"]
                )
                views[cid] = after
            if event is None:
                break
            events.append((case_id, event))
            step = self.steps[-1]
            route = graph.select(node, step, view)
            if route is None:
                self.steps.append(
                    {
                        "turn": node,
                        "runner_stop": "FixtureBranchUnavailable",
                        "coverage": "No unique registered route fits the current proposal and released question.",
                    }
                )
                break
            effective = step.get("edited_proposal") or step["proposal"]
            step["route_selection"] = {
                "from_turn": node,
                "to_turn": route.target,
                "decision": route.decision,
                "question_target": route.question_target,
                "proposal_id": effective["proposal_id"],
                "question_was_released": bool(view.get("awaiting_reply"))
                if route.decision == "ask"
                else None,
                "edited_proposal_selected": step.get("edited_proposal") is not None,
            }
            node = route.target
            if node is None:
                self.route_complete = True
        self._replay(client, case_ids, events)

    def _turn(self, client, case_id, turn, view, views):
        check = self.record.check
        step = turn["id"]
        expect = turn["expect"] if self.mode == "offline" else {}
        reply_to = (view["awaiting_reply"] or {}).get("proposal_id")
        if self.mode == "live" and turn["visible"].get("reply_to_approved_question"):
            question = (view["awaiting_reply"] or {}).get("question", {})
            if not reply_to or not (
                question.get("decision") == "ask"
                and question.get("missing_info") == [STREAMLIT_VERSION_QUESTION.name]
                and question.get("next_question") == STREAMLIT_VERSION_QUESTION.question
                and question.get("user_draft") == STREAMLIT_VERSION_QUESTION.question
            ):
                self.steps.append(
                    {
                        "turn": step,
                        "runner_stop": "FixtureBranchUnavailable",
                        "coverage": "The registered version reply does not fit the approved question.",
                    }
                )
                return view, None
        event = _event(turn, view["case_revision"], reply_to)
        previous_assistant = _assistant_texts(view)
        previous_pending = view["pending"]
        contexts: list[ReasoningContext] = []
        rounds: list[int] = []
        if self.usage.ledger is not None:
            snapshot = self.usage.ledger.snapshot()
            stop = _budget_stop(snapshot)
            if stop:
                check(step, "live ledger permits another turn", False, stop)
                self.steps.append({"turn": step, "runner_stop": stop})
                return view, None
        identity = f"{self.fixture.data['fixture_id']}:{case_id}:{step}"
        if self.invocation_id is not None:
            identity = f"{self.invocation_id}:{identity}"
        stable = uuid5(NAMESPACE_URL, identity)
        with (
            patch.object(
                api, "_adapters", lambda _scenario: self._adapters(case_id, turn, contexts, rounds)
            ),
            patch.object(engine_module, "uuid4", lambda: stable),
        ):
            started = time.perf_counter()
            response = client.post(f"/cases/{case_id}/messages", json=event)
            latency_ms = round((time.perf_counter() - started) * 1000, 1)
        check(step, "event accepted", response.status_code == 200, response.status_code)
        if response.status_code != 200:
            self.steps.append({"turn": step, "request": event, "status": response.status_code})
            return view, None
        view = response.json()
        pending = view["pending"] or {}
        decision = pending.get("decision")
        if expect:
            check(
                step, "revision", view["case_revision"] == expect["revision"], view["case_revision"]
            )
            check(step, "pending decision", decision == expect["pending_decision"], decision)
        check(
            step,
            "decision is acceptable (gold)",
            (decision or "stopped") in turn["gold"]["acceptable_decisions"],
            decision,
        )
        if "stop_code" in expect:
            notes = [entry["text"] for entry in view["log"] if entry["role"] == "system"]
            check(
                step,
                "stop reason logged",
                bool(notes) and expect["stop_code"] in notes[-1],
                notes[-1] if notes else None,
            )
        if "model_attempts" in expect:
            got = pending.get("model_attempts")
            check(step, "model attempts", got == expect["model_attempts"], got)
        if "cross_case_approval_from" in expect:
            foreign = views[expect["cross_case_approval_from"]]["pending"]
            check(step, "other case has a pending proposal", foreign is not None)
            response = _decide(
                client, case_id, foreign or {"proposal_id": "none", "case_revision": 0}, "approve"
            )
            check(
                step,
                "other case's proposal refused here",
                response.status_code == 409,
                response.status_code,
            )
            after = client.get(f"/cases/{case_id}").json()
            check(step, "refused approval changed nothing", after == view)
        check(
            step, "no draft released before approval", _assistant_texts(view) == previous_assistant
        )
        if "preparation" in expect:
            got = view["intake"]["preparation"]
            check(step, "intake preparation", got == expect["preparation"], got)
        active = {name: values[-1] for name, values in _facts(view, "active").items()}
        for name, value in expect.get("active_facts", {}).items():
            check(step, f"active fact {name}", active.get(name) == value, active.get(name))
        for name, values in expect.get("superseded_values", {}).items():
            got = _facts(view, "superseded").get(name, [])
            check(step, f"superseded {name}", all(value in got for value in values), got)
        if "changed_fact_names" in expect:
            got = view["intake"]["changed_fact_names"]
            check(step, "changed facts", set(expect["changed_fact_names"]) <= set(got), got)
        for name in expect.get("unknowns_include", []):
            check(step, f"unknown {name}", name in view["unknowns"], view["unknowns"])
            check(step, f"{name} not active", name not in active, active.get(name))
        cited = {item["chunk_id"] for item in pending.get("evidence", [])}
        for chunk in expect.get("cited_chunks", []):
            check(step, f"cites {chunk}", chunk in cited, sorted(cited))
        if pending:
            handoff = pending["review_handoff"]
            supplied = {hit["chunk_id"] for hit in handoff["evidence"]["hits"]}
            scopes = {e["chunk_id"]: e["version_scope"] for e in handoff["source_inventory"]}
            for chunk, scope in expect.get("version_scope", {}).items():
                check(step, f"version scope {chunk}", scopes.get(chunk) == scope, scopes.get(chunk))
            for chunk in expect.get("excluded_chunks", []):
                check(step, f"latest bundle excludes {chunk}", chunk not in supplied)
        if expect.get("previous_proposal_now_stale") and previous_pending:
            response = _decide(client, case_id, previous_pending, "approve")
            check(
                step,
                "stale proposal approval refused",
                response.status_code == 409,
                response.status_code,
            )
            view = client.get(f"/cases/{case_id}").json()
            check(
                step,
                "stale draft never released",
                previous_pending["user_draft"] not in _assistant_texts(view),
            )

        usage = {
            "latency_ms": latency_ms,
            "model_attempts": len(contexts),
            "retrieval_rounds": len(rounds),
            "steps": pending.get("steps"),
            **self.usage.measure(contexts),
        }
        if self.mode == "live":
            check(step, "model attempt accounting is complete", usage["accounting_complete"])
        if self.provider_observer is not None:
            observations, error = _provider_observations(
                self.provider_observer, contexts, self.usage.ledger
            )
            usage["provider_observations"] = observations
            usage["provider_observations_error"] = error
            check(step, "provider observation metadata valid", error is None, error)
        view, edited = self._maintain(
            client, case_id, step, turn, pending, view, previous_assistant
        )
        self.steps.append(
            {
                "turn": step,
                "conversation_source": turn["conversation_source"],
                "request": event,
                "proposal": deepcopy(pending)
                or {
                    key: pending.get(key)
                    for key in ("proposal_id", "case_revision", "decision", "user_draft")
                },
                "edited_proposal": edited,
                "cited_chunks": sorted(cited),
                "maintainer": turn["maintainer"]["decision"],
                "usage": usage,
                "released_outputs": deepcopy(
                    [entry for entry in view["log"] if entry["role"] == "assistant"][
                        len(previous_assistant) :
                    ]
                ),
                "view_after": deepcopy(view),
            }
        )
        return view, event

    def _maintain(self, client, case_id, step, turn, pending, view, previous_assistant):
        check = self.record.check
        maintainer = turn["maintainer"]
        decision = maintainer["decision"]
        edited = None
        if decision != "none" and not pending:
            check(step, f"{decision}: proposal available", False)
            return view, edited
        if decision == "approve":
            response = _decide(client, case_id, pending, "approve")
            check(step, "approve", response.status_code == 200, response.status_code)
            if response.status_code != 200:
                return client.get(f"/cases/{case_id}").json(), edited
            view = response.json()
            again = _decide(client, case_id, pending, "approve")
            check(step, "double approval refused", again.status_code == 409, again.status_code)
        elif decision == "edit":
            response = _decide(
                client, case_id, pending, "edit", edited_draft=maintainer["edited_draft"]
            )
            check(step, "edit", response.status_code == 200, response.status_code)
            if response.status_code != 200:
                return client.get(f"/cases/{case_id}").json(), edited
            edited = response.json()["pending"]
            check(
                step,
                "edit creates new proposal",
                edited["proposal_id"] != pending["proposal_id"] and edited["edited"],
            )
            old = _decide(client, case_id, pending, "approve")
            check(step, "pre-edit approval refused", old.status_code == 409, old.status_code)
            if maintainer.get("then") == "approve":
                response = _decide(client, case_id, edited, "approve")
                check(step, "approve edited", response.status_code == 200, response.status_code)
                if response.status_code != 200:
                    return client.get(f"/cases/{case_id}").json(), deepcopy(edited)
                view = response.json()
            else:
                view = client.get(f"/cases/{case_id}").json()
        elif decision == "reject":
            response = _decide(client, case_id, pending, "reject")
            check(step, "reject", response.status_code == 200, response.status_code)
            if response.status_code != 200:
                return client.get(f"/cases/{case_id}").json(), edited
            view = response.json()
        after = turn["expect"].get("after_decision") if self.mode == "offline" else None
        if after:
            check(step, "status after decision", view["status"] == after["status"], view["status"])
            released = _assistant_texts(view)[len(previous_assistant) :]
            wanted = {
                "agent": [pending.get("user_draft")],
                "edited": [maintainer.get("edited_draft")],
                None: [],
            }[after["released_draft"]]
            check(step, "released drafts", released == wanted, released)
            if after.get("awaiting_reply"):
                check(
                    step,
                    "approved question awaits reply",
                    (view["awaiting_reply"] or {}).get("proposal_id") == pending["proposal_id"],
                )
        return view, deepcopy(edited)


def _scripted(fixture: Fixture) -> Callable[[str, dict[str, Any]], api.RunAdapters]:
    """Offline adapters; ``faults`` inject tool failures before scripted output."""

    def adapters(_case_id: str, turn: dict[str, Any]) -> api.RunAdapters:
        bundle = fixture.bundles[turn["evidence_bundle"]]
        faults = turn.get("faults", {})
        retrieval = (
            [RuntimeError("Injected retrieval failure")] if faults.get("retrieval") else [bundle]
        )
        reasoning: list[Any] = [RuntimeError("Injected reasoning failure")] * faults.get(
            "reasoning_errors", 0
        )
        if turn.get("agent_script") is not None:
            reasoning.append(AnalysisResult.model_validate(turn["agent_script"]))
        return api.RunAdapters(
            FakeRetriever(retrieval), FakeReasoner(reasoning), snapshot_id=bundle.snapshot_id
        )

    return adapters


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    return str(resolved.relative_to(ROOT)) if resolved.is_relative_to(ROOT) else str(resolved)


def _git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip()


def _source_hashes() -> dict[str, str]:
    return {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((ROOT / "src/agent_app").rglob("*.py"))
    }


def _live_config(live: LiveAdapters) -> dict[str, str | None]:
    allowed = {
        "model",
        "snapshot_id",
        "prompt_policy",
        "response_mode",
        "phase",
        "adapter_id",
        "prompt_sha256",
        "retriever_id",
    }
    config = live.config
    if (
        not isinstance(config, dict)
        or set(config) - allowed
        or any(
            value is not None and (type(value) is not str or len(value) > 200)
            for value in config.values()
        )
    ):
        raise ValueError("LiveConfigInvalid")
    return deepcopy(config)


def _budget_stop(snapshot) -> str | None:
    if snapshot.limit_usd > Decimal("5"):
        return "LiveLedgerLimitInvalid"
    if snapshot.halted:
        return "LiveLedgerHalted"
    if snapshot.available_usd <= 0:
        return "LiveBudgetUnavailable"
    return None


def _final_execution_prerequisites(fixtures: list[Fixture]) -> None:
    """Check local runner inputs before a final-profile provider can be built."""
    fixture_ids = set()
    for fixture in fixtures:
        identifier = fixture.data.get("fixture_id")
        if not isinstance(identifier, str) or not identifier.strip() or identifier in fixture_ids:
            raise ValueError
        fixture_ids.add(identifier)
        for turn in fixture.data["turns"]:
            visible = turn["visible"]
            if (
                "reply_to_approved_question" in visible
                and type(visible["reply_to_approved_question"]) is not bool
            ):
                raise ValueError
            if set(visible) - {
                "message",
                "reported_facts",
                "unknowns",
                "checks_performed",
                "context_changed",
                "reply_to_approved_question",
            }:
                raise ValueError
            if visible.get("reply_to_approved_question") and any(
                visible.get(field)
                for field in ("reported_facts", "unknowns", "checks_performed", "context_changed")
            ):
                raise ValueError
            api.MessageRequest.model_validate(_event(turn, 0, "registered-question"))
            maintainer = turn["maintainer"]
            decision = maintainer["decision"]
            if decision not in {"none", "approve", "reject", "edit"}:
                raise ValueError
            if decision == "edit":
                api.DecisionRequest.model_validate(
                    {
                        "decision": decision,
                        "proposal_id": "registered-proposal",
                        "case_revision": 0,
                        "edited_draft": maintainer["edited_draft"],
                    }
                )
                if maintainer.get("then") not in {None, "approve"}:
                    raise ValueError
            elif "then" in maintainer:
                raise ValueError
            if not isinstance(turn.get("expect"), dict):
                raise ValueError


def final_preflight(
    paths: list[Path],
    manifest: Path | None,
    corpus: Path | None,
    *,
    bundle_paths: list[Path] | None = None,
    trusted_root: Path | None = None,
    conditional_routes: bool = False,
) -> dict[str, Any] | None:
    """Validate the whole packet, then authorize only a pinned execution subset.

    This is mechanical artifact eligibility, not semantic scoring, human review
    authenticity, adaptive route execution or permission to use a paid adapter.
    """
    if manifest is None and corpus is None and bundle_paths is None:
        return None
    if manifest is None or corpus is None:
        raise ValueError("FinalEvaluationPreflightRejected")
    full_paths = bundle_paths if bundle_paths is not None else paths
    report = validate_final_bundle(full_paths, manifest, corpus, trusted_root=trusted_root or ROOT)
    if not report["accepted"]:
        raise ValueError("FinalEvaluationPreflightRejected")

    def files(items):
        return [
            file.resolve()
            for path in items
            for file in (sorted(path.glob("*.json")) if path.is_dir() else [path])
        ]

    selected, complete = files(paths), files(full_paths)
    if not selected or len(selected) != len(set(selected)) or not set(selected) <= set(complete):
        raise ValueError("FinalEvaluationPreflightRejected")
    try:
        for path in complete:
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() not in report["hashes"]["fixtures"]:
                raise ValueError
            source = json.loads(raw)["evidence_source"]
            evidence_path = (ROOT / source["path"]).resolve()
            if not evidence_path.is_relative_to(ROOT.resolve()) or evidence_path.suffix != ".json":
                raise ValueError
        # Even an offline subset must have a loader-compatible whole packet.
        # This reads gold locally; for_case never receives any fixture or gold.
        loaded = collect(full_paths, mode="live")
        _final_execution_prerequisites(loaded)
        if conditional_routes:
            for fixture in loaded:
                RouteGraph.from_fixture(fixture.data)
        by_path = {fixture.path.resolve(): fixture.sha256 for fixture in loaded}
        if set(by_path.values()) != set(report["hashes"]["fixtures"]):
            raise ValueError
        hashes = [by_path[path] for path in selected]
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
        raise ValueError("FinalEvaluationPreflightRejected") from None
    return {**report, "fixture_loader_validated": True, "execution_fixture_hashes": hashes}


def conditional_preflight(paths: list[Path]) -> dict[Path, RouteGraph]:
    """Compile every registered alternative before any live factory is imported."""
    try:
        fixtures = collect(paths, mode="live")
        _final_execution_prerequisites(fixtures)
        return {
            fixture.path.resolve(): RouteGraph.from_fixture(fixture.data) for fixture in fixtures
        }
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
        raise ConditionalRoutesRejected() from None


def run(
    paths: list[Path],
    *,
    mode: Mode = "offline",
    live: LiveAdapters | None = None,
    final_manifest: Path | None = None,
    final_corpus_manifest: Path | None = None,
    final_bundle: list[Path] | None = None,
    trusted_root: Path | None = None,
    conditional_routes: bool = False,
) -> dict[str, Any]:
    if mode not in {"offline", "live"}:
        raise ValueError("Invalid evaluation mode.")
    if (mode == "live") != (live is not None):
        raise ValueError("Live mode needs adapters; offline mode must not receive them.")
    route_mode = conditional_routes or (mode == "live" and final_manifest is not None)
    eligibility = final_preflight(
        paths,
        final_manifest,
        final_corpus_manifest,
        bundle_paths=final_bundle,
        trusted_root=trusted_root,
        conditional_routes=route_mode,
    )
    if route_mode and eligibility is None:
        conditional_preflight(paths)
    if live is not None and not isinstance(live.ledger, BudgetLedger):
        raise ValueError("LiveLedgerRequired")
    config = _live_config(live) if live else {"agent": "scripted agent_script", "model": None}
    if live is not None:
        snapshot = live.ledger.snapshot()
        if stop := _budget_stop(snapshot):
            raise ValueError(stop)
    fixtures = collect(paths, mode=mode)
    graphs = (
        {
            fixture.path.resolve(): RouteGraph.from_fixture(
                fixture.data,
                allow_source_background=getattr(live, "ask_source_background", False),
                concise_user_draft=getattr(live, "concise_user_draft", False),
            )
            for fixture in fixtures
        }
        if route_mode
        else {}
    )
    if (
        eligibility
        and [fixture.sha256 for fixture in fixtures] != eligibility["execution_fixture_hashes"]
    ):
        raise ValueError("FinalEvaluationPreflightRejected")
    usage = Usage(live.ledger if live else None)
    invocation_id = str(uuid4()) if live else None
    source_hashes = _source_hashes()
    cases = []
    for fixture in fixtures:
        case_id = fixture.case["case_id"]
        adapters = (
            _scripted(fixture)
            if live is None
            else (lambda actual_case_id, _turn: live.for_case(actual_case_id))
        )
        case_run = CaseRun(
            fixture,
            adapters,
            usage,
            mode=mode,
            invocation_id=invocation_id,
            route_graph=graphs.get(fixture.path.resolve()),
            provider_observer=getattr(live, "observations_for_contexts", None)
            if live is not None
            else None,
        )
        edit_counter = 0
        edit_prefix = f"{invocation_id or 'offline'}:{fixture.data['fixture_id']}:{case_id}:edit"

        def next_edit_id(prefix=edit_prefix):
            nonlocal edit_counter
            edit_counter += 1
            return uuid5(NAMESPACE_URL, f"{prefix}:{edit_counter}")

        with (
            patch.object(api, "_cases", {}),
            patch.object(api, "tracker", DummyTracker()),
            patch.object(api, "uuid4", next_edit_id),
        ):
            with TestClient(api.app) as client:
                case_run.run(client)
        checks = case_run.record.checks
        coverage_complete = (
            case_run.route_complete
            if route_mode
            else sum("usage" in step for step in case_run.steps) == len(fixture.data["turns"])
        )
        cases.append(
            {
                "case_id": case_id,
                "split": fixture.case["split"],
                "fixture_id": fixture.data["fixture_id"],
                "fixture_path": _display_path(fixture.path),
                "fixture_sha256": fixture.sha256,
                "snapshots": sorted(case_run.observed_snapshots),
                "summary": {
                    "checks": len(checks),
                    "failed": sum(not check["passed"] for check in checks),
                    "coverage_complete": coverage_complete,
                },
                "checks": checks,
                "steps": case_run.steps,
                **(
                    {
                        "conditional_routes": {
                            "selected_path_complete": case_run.route_complete,
                            "selected_turn_ids": case_run.route_visits,
                            "executed_turn_ids": [
                                step["turn"] for step in case_run.steps if "usage" in step
                            ],
                            "unvisited_registered_turn_ids": [
                                name
                                for name in case_run.route_graph.node_ids
                                if name not in case_run.route_visits
                            ],
                            "registered_nodes": len(fixture.data["turns"]),
                            "max_reasoner_attempts_per_case": 2 * len(fixture.data["turns"]),
                        },
                    }
                    if route_mode
                    else {}
                ),
            }
        )
    turns = [step for case in cases for step in case["steps"] if "usage" in step]
    checks_total = sum(case["summary"]["checks"] for case in cases)
    failed = sum(case["summary"]["failed"] for case in cases)
    decisions: dict[str, int] = {}
    for step in turns:
        name = step["proposal"]["decision"] or "stopped"
        decisions[name] = decisions.get(name, 0) + 1
    return {
        "schema_version": 2,
        "mode": mode,
        "quality_claim": False,
        "final_artifact_preflight": eligibility,
        "evaluation_run_id": invocation_id,
        "scoring": {
            "operational_checks": True,
            "decision_labels": True,
            "claim_grounding": "unmeasured",
            "gap_necessity": "unmeasured",
            "live_conversation": (
                "registered conditional routes; no semantic question matching or quality scoring"
                if route_mode
                else "fixed fixture path; no adaptive follow-up selection"
            ),
        },
        "tracker_backend": "process_memory_dummy_tracker",
        "maintainer": "fixture_scripted",
        "usage_scope": "observed reasoner requests only; excludes retrieval, embeddings and adapter setup",
        "git_commit": _git_commit(),
        "source_sha256": source_hashes,
        "source_unchanged_during_run": source_hashes == _source_hashes(),
        "config": config,
        "snapshots": sorted({snapshot for case in cases for snapshot in case["snapshots"]}),
        "summary": {
            "cases": len(cases),
            "turns": len(turns),
            "planned_turns": (
                sum(len(case["conditional_routes"]["selected_turn_ids"]) for case in cases)
                if route_mode
                else sum(len(fixture.data["turns"]) for fixture in fixtures)
            ),
            "coverage_complete": (
                all(case["summary"]["coverage_complete"] for case in cases)
                if route_mode
                else len(turns) == sum(len(fixture.data["turns"]) for fixture in fixtures)
            ),
            **(
                {
                    "registered_turns": sum(len(fixture.data["turns"]) for fixture in fixtures),
                    "unvisited_registered_turns": sum(
                        len(case["conditional_routes"]["unvisited_registered_turn_ids"])
                        for case in cases
                    ),
                    "selected_path_complete": all(
                        case["conditional_routes"]["selected_path_complete"] for case in cases
                    ),
                    "completed_multi_turn_paths": sum(
                        case["summary"]["coverage_complete"]
                        and len(case["conditional_routes"]["executed_turn_ids"]) > 1
                        for case in cases
                    ),
                    "completed_multi_turn_test_paths": sum(
                        case["split"] == "test"
                        and case["summary"]["coverage_complete"]
                        and len(case["conditional_routes"]["executed_turn_ids"]) > 1
                        for case in cases
                    ),
                }
                if route_mode
                else {}
            ),
            "checks": checks_total,
            "failed": failed,
            "cases_all_passed": sum(
                case["summary"]["failed"] == 0 and case["summary"]["coverage_complete"]
                for case in cases
            ),
            "decisions": decisions,
            "latency_ms_total": round(sum(step["usage"]["latency_ms"] for step in turns), 1),
            "cost_usd_total": (
                str(sum(Decimal(step["usage"]["cost_usd"]) for step in turns))
                if all(step["usage"]["cost_usd"] is not None for step in turns)
                else None
            ),
            "settled_usd_total": str(sum(Decimal(step["usage"]["settled_usd"]) for step in turns)),
            "reserved_usd_total": str(
                sum(Decimal(step["usage"]["reserved_usd"]) for step in turns)
            ),
            "uncertain_usd_total": str(
                sum(Decimal(step["usage"]["uncertain_usd"]) for step in turns)
            ),
            "accounting_complete": all(step["usage"]["accounting_complete"] for step in turns),
            "unaccounted_requests": sum(
                record["status"] in {"unrecorded", "identity_mismatch"}
                for step in turns
                for record in step["usage"]["requests"]
            ),
            "fixture_branches_unavailable": sum(
                step.get("runner_stop") == "FixtureBranchUnavailable"
                for case in cases
                for step in case["steps"]
            ),
        },
        "cases": cases,
    }


def _load_live(spec: str) -> LiveAdapters:
    module, _, name = spec.partition(":")
    factory = getattr(importlib.import_module(module), name)
    return factory()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", type=Path, nargs="+", help="Fixture files or split directories.")
    parser.add_argument("--mode", choices=("offline", "live"), default="offline")
    parser.add_argument("--adapters", help="module:factory returning LiveAdapters (live only).")
    parser.add_argument(
        "--conditional-routes",
        action="store_true",
        help="Select only registered conditional branches; automatic for live final packets.",
    )
    parser.add_argument("--final-manifest", type=Path)
    parser.add_argument("--final-corpus-manifest", type=Path)
    parser.add_argument(
        "--final-bundle",
        type=Path,
        nargs="+",
        help="Whole registered dev/test packet; paths may execute a pinned subset.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Receipt path. Must sit under a directory named after the mode; never overwritten.",
    )
    args = parser.parse_args(argv)
    if (args.mode == "live") != bool(args.adapters):
        parser.error("--adapters is required for live mode and not allowed offline.")
    if args.output and (args.output.exists() or args.mode not in args.output.parts):
        parser.error("Output must be new and under a directory named after the mode.")
    # Reject invalid final packets before importing or constructing a live factory.
    try:
        eligibility = final_preflight(
            args.paths,
            args.final_manifest,
            args.final_corpus_manifest,
            bundle_paths=args.final_bundle,
            conditional_routes=args.conditional_routes
            or (args.mode == "live" and args.final_manifest is not None),
        )
        if eligibility is None and args.conditional_routes:
            conditional_preflight(args.final_bundle or args.paths)
    except ConditionalRoutesRejected:
        print(json.dumps({"code": "ConditionalRoutesRejected"}), file=sys.stderr)
        return 1
    except ValueError:
        print(json.dumps({"code": "FinalEvaluationPreflightRejected"}), file=sys.stderr)
        return 1
    receipt = run(
        args.paths,
        mode=args.mode,
        live=_load_live(args.adapters) if args.adapters else None,
        final_manifest=args.final_manifest,
        final_corpus_manifest=args.final_corpus_manifest,
        final_bundle=args.final_bundle,
        conditional_routes=args.conditional_routes,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as output:
            output.write(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(receipt["summary"], ensure_ascii=False))
    for case in receipt["cases"]:
        for check in case["checks"]:
            if not check["passed"]:
                print(
                    f"FAILED {case['case_id']} {check['step']}: {check['check']} "
                    f"({check['detail']})",
                    file=sys.stderr,
                )
    if receipt["summary"]["failed"]:
        return 1
    return 0 if receipt["summary"]["coverage_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
