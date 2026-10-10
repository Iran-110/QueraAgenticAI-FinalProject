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
"""

import argparse
import hashlib
import importlib
import json
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, Protocol
from unittest.mock import patch
from uuid import NAMESPACE_URL, uuid5

from fastapi.testclient import TestClient

from agent_app import api
from agent_app.contracts import AnalysisResult, EvidenceBundle, ReasoningContext
from agent_app.llm.budget import BudgetLedger
from agent_app.llm.metis import request_id_for
from agent_app.orchestration import engine as engine_module
from agent_app.testing.fakes import FakeReasoner, FakeRetriever
from agent_app.tracker.dummy_tracker import DummyTracker

ROOT = Path(__file__).resolve().parents[3]
Mode = Literal["offline", "live"]


class LiveAdapters(Protocol):
    """Real adapters for one evaluation run.

    ``for_case`` receives only the case ID: fixtures, gold and scripted outputs
    are never passed to a live agent. ``config`` (model, prompt policy, snapshot)
    is copied into the receipt; it must not contain credentials.
    """

    ledger: BudgetLedger | None
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


def load_fixture(path: Path) -> Fixture:
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
    for turn in data["turns"]:
        AnalysisResult.model_validate(turn["agent_script"])
        if turn["evidence_bundle"] not in bundles:
            raise ValueError(f"{turn['id']}: unknown evidence bundle.")
    return Fixture(path, data, bundles, hashlib.sha256(raw).hexdigest())


def collect(paths: list[Path]) -> list[Fixture]:
    """Load fixtures from files or split directories and guard split integrity."""
    files: list[Path] = []
    for path in paths:
        files.extend(sorted(path.glob("*.json")) if path.is_dir() else [path])
    fixtures = [load_fixture(path) for path in files]
    if not fixtures:
        raise ValueError("No fixtures found.")
    seen: dict[str, Path] = {}
    family_split: dict[int, str] = {}
    for fixture in fixtures:
        case = fixture.case
        if case["case_id"] in seen:
            raise ValueError(f"Duplicate case_id {case['case_id']}.")
        seen[case["case_id"]] = fixture.path
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
    """Per-turn spend read from the ledger; offline runs are always zero."""

    ledger: BudgetLedger | None

    def total(self) -> Decimal:
        if self.ledger is None:
            return Decimal(0)
        snap = self.ledger.snapshot()
        return snap.settled_usd + snap.reserved_usd + snap.uncertain_usd

    def tokens(self, pending: dict[str, Any]) -> dict[str, int | None]:
        """Sum ledger tokens over the proposal's attempts; ``None`` when unknown."""
        if self.ledger is None:
            return {"input_tokens": 0, "output_tokens": 0}
        if not pending:
            return {"input_tokens": None, "output_tokens": None}
        run_id = pending.get("edited_from") or pending["proposal_id"]
        totals: dict[str, int | None] = {"input_tokens": 0, "output_tokens": 0}
        for attempt in range(1, pending["model_attempts"] + 1):
            context = ReasoningContext(
                run_id=run_id,
                case_id=pending["case_id"],
                case_revision=pending["case_revision"],
                attempt_index=attempt,
            )
            reservation = self.ledger.get(request_id_for(context))
            for name, total in totals.items():
                value = getattr(reservation, name, None)
                totals[name] = None if value is None or total is None else total + value
        return totals


@dataclass
class CaseRun:
    fixture: Fixture
    adapters: Callable[[dict[str, Any]], api.RunAdapters]
    usage: Usage
    record: Recorder = field(default_factory=Recorder)
    steps: list[dict[str, Any]] = field(default_factory=list)

    def run(self, client: TestClient) -> None:
        data = self.fixture.data
        case_id = self.fixture.case["case_id"]
        view = client.get(f"/cases/{case_id}").json()
        events: list[dict[str, Any]] = []
        for turn in data["turns"]:
            view, event = self._turn(client, case_id, turn, view)
            if event is None:
                return
            events.append(event)
        # Every accepted event must replay its original receipt without side effects.
        before = client.get(f"/cases/{case_id}").json()
        for event in events:
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
                body.get("case_revision") == before["case_revision"]
                and body.get("log") == before["log"],
            )

    def _turn(self, client, case_id, turn, view):
        check = self.record.check
        step = turn["id"]
        expect = turn["expect"]
        reply_to = (view["awaiting_reply"] or {}).get("proposal_id")
        event = _event(turn, view["case_revision"], reply_to)
        previous_assistant = _assistant_texts(view)
        previous_pending = view["pending"]
        spent_before = self.usage.total()
        stable = uuid5(NAMESPACE_URL, f"{self.fixture.data['fixture_id']}:{step}")
        with (
            patch.object(api, "_adapters", lambda _scenario: self.adapters(turn)),
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
        check(step, "revision", view["case_revision"] == expect["revision"], view["case_revision"])
        check(step, "pending decision", decision == expect["pending_decision"], decision)
        check(
            step,
            "decision is acceptable (gold)",
            decision in turn["gold"]["acceptable_decisions"],
            decision,
        )
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
            "model_attempts": pending.get("model_attempts"),
            "retrieval_rounds": pending.get("retrieval_rounds"),
            "steps": pending.get("steps"),
            "cost_usd": str(self.usage.total() - spent_before),
            **self.usage.tokens(pending),
        }
        view = self._maintain(client, case_id, step, turn, pending, view, previous_assistant)
        self.steps.append(
            {
                "turn": step,
                "conversation_source": turn["conversation_source"],
                "request": event,
                "proposal": {
                    key: pending.get(key)
                    for key in ("proposal_id", "case_revision", "decision", "user_draft")
                },
                "cited_chunks": sorted(cited),
                "maintainer": turn["maintainer"]["decision"],
                "usage": usage,
                "view_after": {
                    "case_revision": view["case_revision"],
                    "status": view["status"],
                    "facts": [
                        {key: fact[key] for key in ("name", "value", "status", "turn_id")}
                        for fact in view["facts"]
                    ],
                    "unknowns": view["unknowns"],
                    "intake": view["intake"],
                    "log": view["log"],
                },
            }
        )
        return view, event

    def _maintain(self, client, case_id, step, turn, pending, view, previous_assistant):
        check = self.record.check
        maintainer = turn["maintainer"]
        decision = maintainer["decision"]
        if decision != "none" and not pending:
            check(step, f"{decision}: proposal available", False)
            return view
        if decision == "approve":
            response = _decide(client, case_id, pending, "approve")
            check(step, "approve", response.status_code == 200, response.status_code)
            view = response.json()
            again = _decide(client, case_id, pending, "approve")
            check(step, "double approval refused", again.status_code == 409, again.status_code)
        elif decision == "edit":
            response = _decide(
                client, case_id, pending, "edit", edited_draft=maintainer["edited_draft"]
            )
            check(step, "edit", response.status_code == 200, response.status_code)
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
                view = response.json()
            else:
                view = client.get(f"/cases/{case_id}").json()
        elif decision == "reject":
            response = _decide(client, case_id, pending, "reject")
            check(step, "reject", response.status_code == 200, response.status_code)
            view = response.json()
        after = turn["expect"].get("after_decision")
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
        return view


def _scripted(fixture: Fixture) -> Callable[[dict[str, Any]], api.RunAdapters]:
    def adapters(turn: dict[str, Any]) -> api.RunAdapters:
        bundle = fixture.bundles[turn["evidence_bundle"]]
        return api.RunAdapters(
            FakeRetriever([bundle]),
            FakeReasoner([AnalysisResult.model_validate(turn["agent_script"])]),
            snapshot_id=bundle.snapshot_id,
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


def run(
    paths: list[Path], *, mode: Mode = "offline", live: LiveAdapters | None = None
) -> dict[str, Any]:
    if (mode == "live") != (live is not None):
        raise ValueError("Live mode needs adapters; offline mode must not receive them.")
    fixtures = collect(paths)
    usage = Usage(live.ledger if live else None)
    cases = []
    for fixture in fixtures:
        case_id = fixture.case["case_id"]
        adapters = (
            _scripted(fixture)
            if live is None
            else (lambda _turn, case_id=case_id: live.for_case(case_id))
        )
        case_run = CaseRun(fixture, adapters, usage)
        edit_id = uuid5(NAMESPACE_URL, f"{fixture.data['fixture_id']}:edit")
        with (
            patch.object(api, "_cases", {}),
            patch.object(api, "tracker", DummyTracker()),
            patch.object(api, "uuid4", lambda edit_id=edit_id: edit_id),
        ):
            case_run.run(TestClient(api.app))
        checks = case_run.record.checks
        cases.append(
            {
                "case_id": case_id,
                "split": fixture.case["split"],
                "fixture_id": fixture.data["fixture_id"],
                "fixture_path": _display_path(fixture.path),
                "fixture_sha256": fixture.sha256,
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
        "schema_version": 1,
        "mode": mode,
        "quality_claim": mode == "live",
        "git_commit": _git_commit(),
        "config": live.config if live else {"agent": "scripted agent_script", "model": None},
        "snapshots": sorted(
            {bundle.snapshot_id for f in fixtures for bundle in f.bundles.values()}
            if live is None
            else {live.config.get("snapshot_id", "unrecorded")}
        ),
        "summary": {
            "cases": len(cases),
            "turns": len(turns),
            "checks": checks_total,
            "failed": failed,
            "cases_all_passed": sum(case["summary"]["failed"] == 0 for case in cases),
            "decisions": decisions,
            "latency_ms_total": round(sum(step["usage"]["latency_ms"] for step in turns), 1),
            "cost_usd_total": str(sum(Decimal(step["usage"]["cost_usd"]) for step in turns)),
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
        args.output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps(receipt["summary"], ensure_ascii=False))
    for case in receipt["cases"]:
        for check in case["checks"]:
            if not check["passed"]:
                print(
                    f"FAILED {case['case_id']} {check['step']}: {check['check']} "
                    f"({check['detail']})",
                    file=sys.stderr,
                )
    return 0 if receipt["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
