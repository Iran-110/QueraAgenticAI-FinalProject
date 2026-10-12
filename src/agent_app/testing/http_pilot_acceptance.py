"""Offline HTTP pilot checks; a fresh interpreter is required for restart.

Reuse the registered fixture and CaseRun. Neither a new TestClient nor an empty
case after restart counts as persistence. No replacement API/tracker is built.
"""

import hashlib
import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import NAMESPACE_URL, uuid5

from fastapi.testclient import TestClient

from agent_app import api
from agent_app.evaluation import runner
from agent_app.testing.http_pilot_runtime import Observations, load_runtime, offline_network

ROOT = runner.ROOT
PROTOCOL = ROOT / "experiments/http_pilot_acceptance/protocol-v1.json"
MEMORY_FACTORY = "agent_app.testing.http_pilot_runtime:memory_factory"


def digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class Checks:
    def __init__(self):
        self.values: dict[str, bool] = {}

    def check(self, name: str, condition: bool):
        if name in self.values:
            raise ValueError("DuplicateHTTPAcceptanceCheck")
        self.values[name] = bool(condition)


class ObservedClient:
    """Observe actual routes, including CaseRun's own stale/replay probes."""

    def __init__(self, client, observations: Observations, checks: Checks, *, namespace="http"):
        self.client = client
        self.observations = observations
        self.checks = checks
        self.namespace = namespace
        self.trace: list[dict] = []
        self.get_count = 0

    def get(self, path, **kwargs):
        counts = self.observations.snapshot()
        response = self.client.get(path, **kwargs)
        self.checks.check(
            f"{self.namespace}:get{self.get_count}:no_ports",
            self.observations.snapshot() == counts,
        )
        self.get_count += 1
        return response

    def post(self, path, *, json: dict):
        case_path = path.rsplit("/", 1)[0]
        before = self.get(case_path).json()
        counts = self.observations.snapshot()
        response = self.client.post(path, json=json)
        after = self.get(case_path).json()
        final_counts = self.observations.snapshot()
        label = f"{self.namespace}:{len(self.trace)}"
        self.trace.append(
            {
                "path": path,
                "request_sha256": digest(json),
                "status_code": response.status_code,
                "before_sha256": digest(before),
                "after_sha256": digest(after),
                "counts_before": counts,
                "counts_after": final_counts,
            }
        )
        if response.status_code >= 400:
            self.checks.check(f"{label}:refusal_preserves_whole_view", after == before)
            self.checks.check(f"{label}:refusal_no_ports", final_counts == counts)
        body = response.json()
        if path.endswith("/decision"):
            self.checks.check(f"{label}:review_no_ports", final_counts == counts)
        if response.status_code == 200 and (body.get("intake") or {}).get("replayed"):
            self.checks.check(f"{label}:replay_preserves_whole_view", after == before)
            self.checks.check(f"{label}:replay_no_ports", final_counts == counts)
            self.checks.check(
                f"{label}:replay_current_view",
                {k: v for k, v in body.items() if k != "intake"}
                == {k: v for k, v in after.items() if k != "intake"},
            )
        if path.endswith("/decision") and json.get("decision") == "edit":
            if response.status_code == 200:
                self.checks.check(
                    f"{label}:edit_releases_nothing",
                    runner._assistant_texts(before) == runner._assistant_texts(after),
                )
                old, new = before["pending"], after["pending"]
                self.checks.check(
                    f"{label}:edit_new_identity_and_handoff",
                    bool(old and new)
                    and old["proposal_id"] != new["proposal_id"]
                    and digest(old["review_handoff"]) != digest(new["review_handoff"]),
                )
        return response


def _summary(view: dict) -> dict:
    return {
        "case_revision": view.get("case_revision"),
        "status": view.get("status"),
        "facts": view.get("facts"),
        "unknowns": view.get("unknowns"),
        "checks_performed": view.get("checks_performed"),
        "intake": view.get("intake"),
        "awaiting_reply_sha256": digest(view.get("awaiting_reply")),
        "pending_sha256": digest(view.get("pending")),
        "log_sha256": digest(view.get("log")),
        "decisions_sha256": digest(view.get("decisions")),
        "released_count": len(runner._assistant_texts(view)) if "log" in view else None,
        "whole_view_sha256": digest(view),
    }


def restart_worker(payload: dict) -> dict:
    """Never echo child exception text, environment or captured console output."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "agent_app.testing.http_pilot_worker"],
            cwd=ROOT,
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        )
        if len(result.stdout) > 5_000_000:
            raise ValueError
        body = json.loads(result.stdout)
        if body.get("error_code") is not None or type(body.get("pid")) is not int:
            raise ValueError
        if len(body.get("responses", [])) != len(payload["requests"]):
            raise ValueError
        return body
    except (OSError, ValueError, subprocess.SubprocessError):
        raise ValueError("HTTPRestartWorkerFailed") from None


def _request(method, path, body=None):
    return {"method": method, "path": path, "json": body}


def _review(proposal: dict, decision="approve"):
    return {
        "proposal_id": proposal["proposal_id"],
        "case_revision": proposal["case_revision"],
        "decision": decision,
    }


def _replay_checks(checks, prefix, response, original, before, after):
    intake = response["body"].get("intake") or {}
    checks.check(
        f"{prefix}:accepted_as_replay",
        response["status_code"] == 200 and intake.get("replayed") is True,
    )
    checks.check(f"{prefix}:whole_view_unchanged", after == before)
    checks.check(f"{prefix}:no_new_ports", response["counts_before"] == response["counts_after"])
    checks.check(f"{prefix}:original_receipt", intake == {**original, "replayed": True})


def _replay_prefix(fixture, factory, state_dir, length, checks):
    observations = Observations()
    scripted = runner._scripted(fixture)
    case_run = runner.CaseRun(
        fixture, lambda cid, turn: observations.wrap(scripted(cid, turn)), runner.Usage(None)
    )
    edit_count = 0

    def edit_id():
        nonlocal edit_count
        edit_count += 1
        return uuid5(
            NAMESPACE_URL,
            f"offline:{fixture.data['fixture_id']}:{fixture.case['case_id']}:edit:{edit_count}",
        )

    with load_runtime(factory, state_dir) as runtime, patch.object(api, "uuid4", edit_id):
        with TestClient(runtime.app) as raw:
            client = ObservedClient(raw, observations, checks, namespace=f"prefix{length}:http")
            cid = fixture.case["case_id"]
            view = client.get(f"/cases/{cid}").json()
            views = {cid: view}
            events, receipts = [], []
            for turn in fixture.data["turns"][:length]:
                view, event = case_run._turn(client, cid, turn, view, views)
                if event is None:
                    raise ValueError("HTTPPilotPrefixIncomplete")
                events.append(event)
                receipts.append(deepcopy(view["intake"]))
                views[cid] = view
            for item in case_run.record.checks:
                checks.check(f"prefix{length}:{item['step']}:{item['check']}", item["passed"])
            if length == 4:
                _same_process_probes(
                    client, cid, view, events, receipts, case_run, observations, checks
                )
            # Closing/reopening TestClient intentionally preserves this runtime.
            frozen = client.get(f"/cases/{cid}").json()
        with TestClient(runtime.app) as reconnected:
            reconnect_counts = observations.snapshot()
            checks.check(
                f"reconnect{length}:same_process_state",
                reconnected.get(f"/cases/{cid}").json() == frozen,
            )
            checks.check(f"reconnect{length}:no_ports", observations.snapshot() == reconnect_counts)
        return frozen, events, receipts, case_run, observations, runtime.tracker_backend


def _same_process_probes(client, cid, view, events, receipts, case_run, obs, checks):
    path = f"/cases/{cid}"
    for event, original in zip(events, receipts, strict=True):
        before = client.get(path).json()
        counts = obs.snapshot()
        response = client.post(path + "/messages", json=event)
        _replay_checks(
            checks,
            f"same_process:{event['turn_id']}",
            {
                "status_code": response.status_code,
                "body": response.json(),
                "counts_before": counts,
                "counts_after": obs.snapshot(),
            },
            original,
            before,
            client.get(path).json(),
        )
    conflicting = {**events[0], "message": "Different content under the committed event identity."}
    response = client.post(path + "/messages", json=conflicting)
    checks.check(
        "same_process:conflicting_event_refused",
        response.status_code == 409 and response.json().get("detail") == "EventConflict",
    )
    checks.check(
        "same_process:final_revision_preserved", client.get(path).json()["case_revision"] == 4
    )
    correction = case_run.steps[2]["view_after"]
    checks.check("correction:old_checks_invalidated", correction["checks_performed"] == [])
    checks.check("correction:old_evidence_refs_cleared", correction["evidence_refs"] == [])
    current = runner._facts(correction, "active").get("streamlit_version")
    checks.check("correction:only_corrected_version_active", current == ["1.49.1"])
    checks.check(
        "correction:old_version_superseded",
        "1.50.0" in runner._facts(correction, "superseded").get("streamlit_version", []),
    )
    short = obs.observed_inputs[1]["user_message"] if len(obs.observed_inputs) >= 2 else ""
    checks.check(
        "context:short_reply_retains_original_problem",
        fixture_message(case_run.fixture, 0) in short,
    )
    checks.check(
        "context:short_reply_retains_current_reply", fixture_message(case_run.fixture, 1) in short
    )
    checks.check(
        "context:no_future_correction_in_short_reply",
        fixture_message(case_run.fixture, 2) not in short,
    )
    checks.check(
        "same_process:released_exactly_two_outputs", len(runner._assistant_texts(view)) == 2
    )
    edited = case_run.steps[2]["edited_proposal"]
    before = client.get(path).json()
    response = client.post(path + "/decision", json=_review(edited))
    checks.check(
        "same_process:approved_review_retry_safe",
        response.status_code in {200, 409} and client.get(path).json() == before,
    )


def fixture_message(fixture, index):
    return fixture.data["turns"][index]["visible"]["message"]


def _restart_probe(fixture, factory, state_dir, length, checks):
    before, events, receipts, case_run, obs, backend = _replay_prefix(
        fixture, factory, state_dir, length, checks
    )
    cid = fixture.case["case_id"]
    path = f"/cases/{cid}"
    # Both the latest event (possibly a bound reply) and event1's revision0 must
    # replay. A late event merely receiving409 from an empty case is not dedup.
    requests = [_request("GET", path)]
    latest = case_run.steps[-1]
    proposal = latest["edited_proposal"] or latest["proposal"]
    decision = "reject" if length == 4 else "approve"
    requests += [
        _request("POST", path + "/decision", _review(proposal, decision)),
        _request("GET", path),
    ]
    for event in (events[-1], events[0]):
        requests += [_request("POST", path + "/messages", event), _request("GET", path)]
    if length >= 3:
        for old in (case_run.steps[1]["proposal"], case_run.steps[2]["proposal"]):
            requests += [_request("POST", path + "/decision", _review(old)), _request("GET", path)]
    elif length == 2:
        requests += [_request("POST", path + "/decision", _review(proposal)), _request("GET", path)]
    else:
        reply = runner._event(
            fixture.data["turns"][1],
            before["case_revision"],
            before["awaiting_reply"]["proposal_id"],
        )
        requests += [_request("POST", path + "/messages", reply), _request("GET", path)]
    observed = restart_worker(
        {
            "factory": factory,
            "fixture": str(fixture.path),
            "state_dir": str(state_dir),
            "requests": requests,
        }
    )
    label = f"restart{length}"
    _read_review_checks(checks, label, requests, observed["responses"])
    checks.check(f"{label}:fresh_process", observed["pid"] != os.getpid())
    checks.check(f"{label}:backend_label_preserved", observed["tracker_backend"] == backend)
    restored = observed["responses"][0]["body"]
    checks.check(f"{label}:whole_state_preserved", restored == before)
    review, reviewed = observed["responses"][1:3]
    if length == 2:
        # This was still pending: a valid current approval must survive restart.
        checks.check(
            f"{label}:pending_review_survives",
            review["status_code"] == 200 and reviewed["body"].get("status") == "answer_sent",
        )
        checks.check(
            f"{label}:pending_review_releases_once",
            reviewed["body"].get("log", [])
            == before["log"]
            + [
                {
                    "role": "assistant",
                    "text": proposal["user_draft"],
                    "decision": proposal["decision"],
                    "edited": proposal["edited"],
                }
            ],
        )
    else:
        checks.check(
            f"{label}:completed_review_retry_safe",
            review["status_code"] in {200, 409} and reviewed["body"] == restored,
        )
    for index, original in zip((3, 5), (receipts[-1], receipts[0]), strict=True):
        current = observed["responses"][index - 1]["body"]
        _replay_checks(
            checks,
            f"{label}:retry{index}",
            observed["responses"][index],
            original,
            current,
            observed["responses"][index + 1]["body"],
        )
    if length >= 3:
        for index in (7, 9):
            stale = observed["responses"][index]
            checks.check(f"{label}:old_review{index}_refused", stale["status_code"] == 409)
            checks.check(
                f"{label}:old_review{index}_no_mutation",
                observed["responses"][index + 1]["body"]
                == observed["responses"][index - 1]["body"],
            )
            checks.check(
                f"{label}:old_review{index}_no_ports",
                stale["counts_before"] == stale["counts_after"],
            )
    elif length == 2:
        retried_review = observed["responses"][7]
        checks.check(
            f"{label}:approved_review_retry_safe",
            retried_review["status_code"] in {200, 409}
            and observed["responses"][8]["body"] == observed["responses"][6]["body"],
        )
    else:
        replied = observed["responses"][7]
        reply_view = observed["responses"][8]["body"]
        checks.check(
            f"{label}:approved_question_reply_survives",
            replied["status_code"] == 200
            and (reply_view.get("intake") or {}).get("preparation") == "canonical_version_reply"
            and runner._facts(reply_view, "active").get("streamlit_version") == ["1.50.0"],
        )
    return {
        "checkpoint": fixture.data["turns"][length - 1]["id"],
        "parent_pid": os.getpid(),
        "restarted_pid": observed["pid"],
        "tracker_backend": backend,
        "same_storage_path": True,
        "before": _summary(before),
        "after_restart": _summary(restored),
        "responses": [
            {
                "status_code": item["status_code"],
                "view": _summary(item["body"]),
                "counts_before": item["counts_before"],
                "counts_after": item["counts_after"],
            }
            for item in observed["responses"]
        ],
        "port_counts_before_restart": obs.snapshot(),
        "port_counts_after_restart": observed["counts"],
        "fixture_steps": case_run.steps if length == 4 else None,
        "observed_reasoning_inputs": obs.observed_inputs if length == 4 else None,
    }


def _interrupted_probe(fixture, factory, state_dir, checks):
    obs = Observations()
    cid = fixture.case["case_id"]
    path = f"/cases/{cid}"
    event = runner._event(fixture.data["turns"][0], 0, None)

    def stopped(_scenario):
        obs.factory_calls += 1
        raise RuntimeError("Injected setup failure")

    with (
        load_runtime(factory, state_dir) as runtime,
        patch.object(api, "_adapters", stopped),
        TestClient(runtime.app) as raw,
    ):
        client = ObservedClient(raw, obs, checks, namespace="interrupted:http")
        response = client.post(path + "/messages", json=event)
        before = client.get(path).json()
        checks.check(
            "interrupted:ingress_committed_without_proposal",
            response.status_code == 200
            and before["case_revision"] == 1
            and before["pending"] is None,
        )
        checks.check(
            "interrupted:stopped_without_reasoning_or_retrieval",
            obs.snapshot() == {"factory_calls": 1, "retrieval_calls": 0, "reasoning_calls": 0},
        )
        counts = obs.snapshot()
        retry = client.post(path + "/messages", json=event)
        _replay_checks(
            checks,
            "interrupted:same_process_retry",
            {
                "status_code": retry.status_code,
                "body": retry.json(),
                "counts_before": counts,
                "counts_after": obs.snapshot(),
            },
            before["intake"],
            before,
            client.get(path).json(),
        )
    observed = restart_worker(
        {
            "factory": factory,
            "fixture": str(fixture.path),
            "state_dir": str(state_dir),
            "setup_failure": True,
            "requests": [
                _request("GET", path),
                _request("POST", path + "/messages", event),
                _request("GET", path),
            ],
        }
    )
    checks.check("interrupted:restart_fresh_process", observed["pid"] != os.getpid())
    _read_review_checks(
        checks,
        "interrupted:restart",
        [_request("GET", path), _request("POST", path + "/messages", event), _request("GET", path)],
        observed["responses"],
    )
    restored = observed["responses"][0]["body"]
    checks.check("interrupted:restart_preserves_stopped_ingress", restored == before)
    _replay_checks(
        checks,
        "interrupted:restart_retry",
        observed["responses"][1],
        before["intake"],
        restored,
        observed["responses"][2]["body"],
    )
    return {
        "before": _summary(before),
        "after_restart": _summary(restored),
        "restarted_pid": observed["pid"],
        "port_counts_after_restart": observed["counts"],
    }


def _read_review_checks(checks, label, requests, responses):
    for index, (request, response) in enumerate(zip(requests, responses, strict=True)):
        if request["method"] == "GET" or request["path"].endswith("/decision"):
            checks.check(
                f"{label}:request{index}:read_or_review_no_ports",
                response["counts_before"] == response["counts_after"],
            )


def run_acceptance(factory=MEMORY_FACTORY) -> dict:
    protocol_bytes = PROTOCOL.read_bytes()
    protocol = json.loads(protocol_bytes)
    fixture = runner.load_fixture(ROOT / protocol["fixture"])
    if fixture.sha256 != protocol["fixture_sha256"]:
        raise ValueError("HTTPFixtureChanged")
    checks = Checks()
    with offline_network(), TemporaryDirectory(prefix="http-pilot-") as storage:
        checkpoints = [
            _restart_probe(fixture, factory, Path(storage) / f"checkpoint-{n}", n, checks)
            for n in (1, 2, 3, 4)
        ]
        interrupted = _interrupted_probe(fixture, factory, Path(storage) / "interrupted", checks)
    same_process = {
        key: value
        for key, value in checks.values.items()
        if not key.startswith(("restart", "interrupted:restart"))
    }
    persistence = {
        key: value
        for key, value in checks.values.items()
        if key.startswith(("restart", "interrupted:restart"))
    }
    return {
        "schema_version": 1,
        "protocol": protocol["protocol_id"],
        "protocol_sha256": hashlib.sha256(protocol_bytes).hexdigest(),
        "fixture_path": protocol["fixture"],
        "fixture_sha256": fixture.sha256,
        "factory": factory,
        "tracker_backend": checkpoints[0]["tracker_backend"],
        "mode": "offline_http_scripted_ports_with_fresh_process_restart",
        "accepted": all(checks.values.values()),
        "same_process_accepted": all(same_process.values()),
        "restart_accepted": all(persistence.values()),
        "checks": checks.values,
        "checks_passed": sum(checks.values.values()),
        "checks_total": len(checks.values),
        "checkpoints": checkpoints,
        "interrupted": interrupted,
        "quality_claim": False,
        "real_model_tested": False,
        "production_index_or_embedding_tested": False,
        "api_cost_usd": 0,
        "production_ledger_used": False,
        "held_out_test": False,
        "exposure": protocol["exposure"],
        "limitations": [
            "Scripted, answer-informed dev case; no independent grounding or model quality measurement.",
            "HTTP uses in-memory ASGI transport; no browser or external TCP server.",
            "Authenticated stable review IDs, handoff digests, durable outcome journal and lifecycle CAS remain U3/T4 work.",
        ],
    }
