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
from agent_app.llm.budget import BudgetLedger
from agent_app.llm.metis import request_id_for
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
    evidence = (ROOT / source["path"]).read_bytes()
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

    def _adapters(self, case_id, turn, contexts, rounds):
        ports = self.adapters(case_id, turn)
        return api.RunAdapters(
            RetrievalRecorder(ports.retriever, rounds),
            AttemptRecorder(ports.reasoner, contexts, self.observed_snapshots),
            snapshot_id=ports.snapshot_id,
            grounded_request_supplier=ports.grounded_request_supplier,
        )

    def run(self, client: TestClient) -> None:
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


def run(
    paths: list[Path], *, mode: Mode = "offline", live: LiveAdapters | None = None
) -> dict[str, Any]:
    if mode not in {"offline", "live"}:
        raise ValueError("Invalid evaluation mode.")
    if (mode == "live") != (live is not None):
        raise ValueError("Live mode needs adapters; offline mode must not receive them.")
    if live is not None and not isinstance(live.ledger, BudgetLedger):
        raise ValueError("LiveLedgerRequired")
    config = _live_config(live) if live else {"agent": "scripted agent_script", "model": None}
    if live is not None:
        snapshot = live.ledger.snapshot()
        if stop := _budget_stop(snapshot):
            raise ValueError(stop)
    fixtures = collect(paths, mode=mode)
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
        case_run = CaseRun(fixture, adapters, usage, mode=mode, invocation_id=invocation_id)
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
                },
                "checks": checks,
                "steps": case_run.steps,
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
        "evaluation_run_id": invocation_id,
        "scoring": {
            "operational_checks": True,
            "decision_labels": True,
            "claim_grounding": "unmeasured",
            "gap_necessity": "unmeasured",
            "live_conversation": "fixed fixture path; no adaptive follow-up selection",
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
            "planned_turns": sum(len(fixture.data["turns"]) for fixture in fixtures),
            "coverage_complete": len(turns)
            == sum(len(fixture.data["turns"]) for fixture in fixtures),
            "checks": checks_total,
            "failed": failed,
            "cases_all_passed": sum(case["summary"]["failed"] == 0 for case in cases),
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
        "--output",
        type=Path,
        help="Receipt path. Must sit under a directory named after the mode; never overwritten.",
    )
    args = parser.parse_args(argv)
    if (args.mode == "live") != bool(args.adapters):
        parser.error("--adapters is required for live mode and not allowed offline.")
    if args.output and (args.output.exists() or args.mode not in args.output.parts):
        parser.error("Output must be new and under a directory named after the mode.")
    receipt = run(
        args.paths, mode=args.mode, live=_load_live(args.adapters) if args.adapters else None
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
