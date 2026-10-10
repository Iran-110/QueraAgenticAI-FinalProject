"""Replay one registered evaluation fixture through the UI's HTTP API, offline.

The agent is scripted per turn, so a receipt shows operational behaviour only:
revisions, fact history, stale proposals, approval binding, edits, rejection
and event replay. It is not evidence of decision or retrieval quality.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import NAMESPACE_URL, uuid5

from fastapi.testclient import TestClient

from agent_app import api
from agent_app.contracts import AnalysisResult, EvidenceBundle
from agent_app.orchestration import engine as engine_module
from agent_app.testing.fakes import FakeReasoner, FakeRetriever
from agent_app.tracker.dummy_tracker import DummyTracker

ROOT = Path(__file__).resolve().parents[3]


class Recorder:
    def __init__(self) -> None:
        self.checks: list[dict[str, Any]] = []

    def check(self, step: str, name: str, passed: bool, detail: Any = None) -> None:
        self.checks.append({"step": step, "check": name, "passed": bool(passed), "detail": detail})


def load(path: Path) -> tuple[dict[str, Any], dict[str, EvidenceBundle]]:
    fixture = json.loads(path.read_text(encoding="utf-8"))
    source = fixture["evidence_source"]
    raw = (ROOT / source["path"]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != source["sha256"]:
        raise ValueError("Evidence source does not match its registered SHA-256.")
    bundles = {
        name: EvidenceBundle.model_validate(json.loads(raw)["evidence_bundles"][name])
        for name in source["bundles_used"]
    }
    for turn in fixture["turns"]:
        AnalysisResult.model_validate(turn["agent_script"])
    return fixture, bundles


def _event(turn: dict[str, Any], revision: int, reply_to: str | None) -> dict[str, Any]:
    visible = turn["visible"]
    event = {
        "message": visible["message"],
        "scenario": "ask",  # Ignored: the pilot supplies its own adapters.
        "turn_id": turn["id"],
        "expected_revision": revision,
    }
    if visible.get("reply_to_approved_question"):
        event["reply_to_proposal_id"] = reply_to
        return event
    for field in ("reported_facts", "unknowns", "checks_performed", "context_changed"):
        if field in visible:
            event[field] = visible[field]
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


def run(path: Path) -> dict[str, Any]:
    fixture, bundles = load(path)
    case_id = fixture["case"]["case_id"]
    record = Recorder()
    current: dict[str, Any] = {}

    def adapters(_scenario: str) -> api.RunAdapters:
        turn = current["turn"]
        return api.RunAdapters(
            FakeRetriever([bundles[turn["evidence_bundle"]]]),
            FakeReasoner([AnalysisResult.model_validate(turn["agent_script"])]),
            snapshot_id=bundles[turn["evidence_bundle"]].snapshot_id,
        )

    def stable_id(label: str):
        return lambda: uuid5(NAMESPACE_URL, f"{fixture['fixture_id']}:{label}")

    steps: list[dict[str, Any]] = []
    with (
        patch.object(api, "_cases", {}),
        patch.object(api, "tracker", DummyTracker()),
        patch.object(api, "_adapters", adapters),
        patch.object(api, "uuid4", stable_id("edit")),
    ):
        client = TestClient(api.app)
        view = client.get(f"/cases/{case_id}").json()
        stale: dict[str, Any] | None = None
        replay_event: dict[str, Any] | None = None
        for turn in fixture["turns"]:
            step = turn["id"]
            expect = turn["expect"]
            current["turn"] = turn
            reply_to = (view["awaiting_reply"] or {}).get("proposal_id")
            event = _event(turn, view["case_revision"], reply_to)
            previous_assistant = _assistant_texts(view)
            previous_pending = view["pending"]
            with patch.object(engine_module, "uuid4", stable_id(step)):
                response = client.post(f"/cases/{case_id}/messages", json=event)
            record.check(step, "event accepted", response.status_code == 200, response.status_code)
            if response.status_code != 200:
                steps.append({"turn": step, "request": event, "status": response.status_code})
                break
            view = response.json()
            pending = view["pending"] or {}
            record.check(
                step, "revision", view["case_revision"] == expect["revision"], view["case_revision"]
            )
            record.check(
                step,
                "pending decision",
                pending.get("decision") == expect["pending_decision"],
                pending.get("decision"),
            )
            record.check(
                step,
                "decision is acceptable (gold)",
                pending.get("decision") in turn["gold"]["acceptable_decisions"],
                pending.get("decision"),
            )
            record.check(
                step,
                "no draft released before approval",
                _assistant_texts(view) == previous_assistant,
            )
            if "preparation" in expect:
                record.check(
                    step,
                    "intake preparation",
                    view["intake"]["preparation"] == expect["preparation"],
                    view["intake"]["preparation"],
                )
            active = {name: values[-1] for name, values in _facts(view, "active").items()}
            for name, value in expect.get("active_facts", {}).items():
                record.check(
                    step, f"active fact {name}", active.get(name) == value, active.get(name)
                )
            if expect.get("active_facts") == {}:
                record.check(
                    step,
                    "version not active",
                    "streamlit_version" not in active,
                    active.get("streamlit_version"),
                )
            for name, values in expect.get("superseded_values", {}).items():
                got = _facts(view, "superseded").get(name, [])
                record.check(step, f"superseded {name}", all(v in got for v in values), got)
            if "changed_fact_names" in expect:
                got = view["intake"]["changed_fact_names"]
                record.check(
                    step, "changed facts", set(expect["changed_fact_names"]) <= set(got), got
                )
            for name in expect.get("unknowns_include", []):
                record.check(step, f"unknown {name}", name in view["unknowns"], view["unknowns"])
            cited = {item["chunk_id"] for item in pending.get("evidence", [])}
            for chunk in expect.get("cited_chunks", []):
                record.check(step, f"cites {chunk}", chunk in cited, sorted(cited))
            if pending:
                supplied = {
                    hit["chunk_id"] for hit in pending["review_handoff"]["evidence"]["hits"]
                }
                scopes = {
                    e["chunk_id"]: e["version_scope"]
                    for e in pending["review_handoff"]["source_inventory"]
                }
                for chunk, scope in expect.get("version_scope", {}).items():
                    record.check(
                        step,
                        f"version scope {chunk}",
                        scopes.get(chunk) == scope,
                        scopes.get(chunk),
                    )
                for chunk in expect.get("excluded_chunks", []):
                    record.check(step, f"latest bundle excludes {chunk}", chunk not in supplied)
            if expect.get("previous_proposal_now_stale") and previous_pending:
                stale = previous_pending
                response = _decide(client, case_id, stale, "approve")
                record.check(
                    step,
                    "probe approve_stale_turn_2_proposal: 409",
                    response.status_code == 409,
                    response.status_code,
                )
                view = client.get(f"/cases/{case_id}").json()
                record.check(
                    step,
                    "stale draft never released",
                    stale["user_draft"] not in _assistant_texts(view),
                )

            maintainer = turn["maintainer"]
            decision = maintainer["decision"]
            if decision == "approve":
                response = _decide(client, case_id, pending, "approve")
                record.check(step, "approve", response.status_code == 200, response.status_code)
                view = response.json()
                again = _decide(client, case_id, pending, "approve")
                record.check(
                    step, "probe double_approve: 409", again.status_code == 409, again.status_code
                )
            elif decision == "edit":
                response = _decide(
                    client, case_id, pending, "edit", edited_draft=maintainer["edited_draft"]
                )
                record.check(step, "edit", response.status_code == 200, response.status_code)
                edited = response.json()["pending"]
                record.check(
                    step,
                    "edit creates new proposal",
                    edited["proposal_id"] != pending["proposal_id"] and edited["edited"],
                )
                old = _decide(client, case_id, pending, "approve")
                record.check(
                    step,
                    "probe approve_pre_edit_proposal: 409",
                    old.status_code == 409,
                    old.status_code,
                )
                response = _decide(client, case_id, edited, "approve")
                record.check(
                    step, "approve edited", response.status_code == 200, response.status_code
                )
                view = response.json()
            elif decision == "reject":
                response = _decide(client, case_id, pending, "reject")
                record.check(step, "reject", response.status_code == 200, response.status_code)
                view = response.json()
            after = expect.get("after_decision")
            if after:
                record.check(
                    step, "status after decision", view["status"] == after["status"], view["status"]
                )
                released = _assistant_texts(view)[len(previous_assistant) :]
                wanted = {
                    "agent": [pending.get("user_draft")],
                    "edited": [maintainer.get("edited_draft")],
                    None: [],
                }[after["released_draft"]]
                record.check(step, "released drafts", released == wanted, released)
                if after.get("awaiting_reply"):
                    record.check(
                        step,
                        "approved question awaits reply",
                        (view["awaiting_reply"] or {}).get("proposal_id") == pending["proposal_id"],
                    )
            if step == "p1-turn-3":
                replay_event = event
            steps.append(
                {
                    "turn": step,
                    "conversation_source": turn["conversation_source"],
                    "request": event,
                    "proposal": {
                        k: pending.get(k)
                        for k in ("proposal_id", "case_revision", "decision", "user_draft")
                    },
                    "cited_chunks": sorted(cited),
                    "maintainer": decision,
                    "view_after": {
                        "case_revision": view["case_revision"],
                        "status": view["status"],
                        "facts": [
                            {k: f[k] for k in ("name", "value", "status", "turn_id")}
                            for f in view["facts"]
                        ],
                        "unknowns": view["unknowns"],
                        "intake": view["intake"],
                        "log": view["log"],
                    },
                }
            )

        if replay_event is not None:
            before = client.get(f"/cases/{case_id}").json()
            response = client.post(f"/cases/{case_id}/messages", json=replay_event)
            body = response.json()
            record.check(
                "probe",
                "replay_turn_3_event: replayed receipt",
                response.status_code == 200 and body["intake"]["replayed"],
                response.status_code,
            )
            record.check(
                "probe",
                "replay leaves revision and log unchanged",
                body["case_revision"] == before["case_revision"] and body["log"] == before["log"],
            )

    passed = sum(check["passed"] for check in record.checks)
    return {
        "fixture_id": fixture["fixture_id"],
        "fixture_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "mode": "offline_scripted_agent",
        "real_model_calls": 0,
        "api_cost_usd": 0,
        "storage": "API process memory",
        "quality_claim": False,
        "summary": {
            "checks": len(record.checks),
            "passed": passed,
            "failed": len(record.checks) - passed,
        },
        "checks": record.checks,
        "steps": steps,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--output", type=Path, help="Write the receipt; refuses to overwrite.")
    args = parser.parse_args(argv)
    receipt = run(args.fixture)
    text = json.dumps(receipt, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        if args.output.exists():
            parser.error(f"{args.output} exists; receipts are not overwritten.")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    summary = receipt["summary"]
    print(json.dumps(summary) if args.output else text, end="" if not args.output else "\n")
    for check in receipt["checks"]:
        if not check["passed"]:
            print(f"FAILED {check['step']}: {check['check']} ({check['detail']})", file=sys.stderr)
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
