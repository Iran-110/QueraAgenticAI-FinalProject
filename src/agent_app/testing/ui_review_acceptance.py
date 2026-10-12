"""Registered offline UI-client review control using actual SQLite HTTP routes."""

import hashlib
import importlib.util
import json
import subprocess
import sys
import types
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from agent_app import persistent_api, ui_client
from agent_app.tracker.sqlite_tracker import SQLiteCaseTracker

TOKEN = "synthetic-ui-review-acceptance-credential"
REVIEWERS = {"fixture-maintainer": TOKEN}
PROTOCOL = "experiments/ui_review_acceptance/protocol-v1.json"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _legacy_module(root: Path, commit: str, path: str, name: str):
    data = subprocess.run(
        ["git", "show", f"{commit}:{path}"], cwd=root, check=True, capture_output=True
    ).stdout
    module = types.ModuleType(name)
    module.__spec__ = importlib.util.spec_from_loader(name, loader=None)
    sys.modules[name] = module
    exec(compile(data, path, "exec"), module.__dict__)
    return module, digest(data)


class LostReviewAck:
    def __init__(self, http):
        self.http = http
        self.dropped = False

    def request(self, method, path, **arguments):
        response = self.http.request(method, path, **arguments)
        if method == "POST" and path.endswith("/decision") and response.status_code == 200:
            self.dropped = True
            raise httpx.ReadTimeout("Synthetic lost acknowledgment")
        return response


def run(root: Path, state_dir: Path, *, baseline: bool = False) -> dict:
    protocol_bytes = (root / PROTOCOL).read_bytes()
    protocol = json.loads(protocol_bytes)
    fixture_bytes = (root / protocol["fixture"]).read_bytes()
    if digest(fixture_bytes) != protocol["fixture_sha256"]:
        raise ValueError("UIAcceptanceFixtureMismatch")
    fixture = json.loads(fixture_bytes)
    source_hashes = {}
    if baseline:
        modules = []
        for index, path in enumerate(protocol["baseline_modules"]):
            module, sha = _legacy_module(
                root, protocol["baseline_commit"], path, f"_ui_acceptance_baseline_{index}"
            )
            modules.append(module)
            source_hashes[path] = sha
        client_module, backend_module = modules
    else:
        client_module, backend_module = ui_client, persistent_api
        for path in protocol["baseline_modules"]:
            source_hashes[path] = digest((root / path).read_bytes())
    state_dir.mkdir(parents=True, exist_ok=True)
    database = state_dir / "review.sqlite3"
    if database.exists():
        raise ValueError("UIAcceptanceFreshStateRequired")

    def fresh():
        tracker = SQLiteCaseTracker(database, reviewer_tokens=REVIEWERS)
        return tracker, backend_module.create_app(tracker, reviewer_tokens=REVIEWERS)

    tracker, application = fresh()
    checks = dict.fromkeys(protocol["checks"], False)
    case_id = "ui-pilot-12782"
    with TestClient(application) as http:
        health = http.get("/health").json()
        checks["durable_review_capabilities"] = health.get("capabilities") == {
            "stable_event_ids": True,
            "durable_reviews": True,
            "reviewer_auth": "bearer",
        }
        lossy = LostReviewAck(http)
        client = (
            client_module.BackendClient(lossy)
            if baseline
            else client_module.BackendClient(lossy, reviewer_token=TOKEN)
        )
        event = {
            **fixture["turns"][0]["visible"],
            "turn_id": "ui-pilot-original",
            "expected_revision": 0,
            "scenario": "ask_version",
        }
        initial = client.send_event(case_id, event)
        checks["stable_event_committed"] = initial["case_revision"] == 1
        proposal = initial["pending"]
        operation = None
        if not baseline:
            operation = client.prepare_review(case_id, proposal, "approve")
            operation_before = operation.body_json
        try:
            if baseline:
                client.decide(
                    case_id,
                    proposal_id=proposal["proposal_id"],
                    case_revision=1,
                    decision="approve",
                )
            else:
                client.send_review(operation)
        except client_module.BackendError as error:
            checks["uncertain_ack_keeps_original_review"] = bool(
                not baseline
                and error.retryable
                and lossy.dropped
                and operation.body_json == operation_before
            )
        correction = {
            "message": "Correction: my installed Streamlit version is 1.49.0.",
            "turn_id": "ui-pilot-correction",
            "expected_revision": 1,
            "scenario": "escalate",
            "context_changed": True,
            "reported_facts": [{"name": "streamlit_version", "value": "1.49.0"}],
        }
        if http.post(f"/cases/{case_id}/messages", json=correction).status_code != 200:
            raise ValueError("UIAcceptanceCorrectionRejected")
    tracker, application = fresh()
    with TestClient(application) as http:
        client = (
            client_module.BackendClient(http)
            if baseline
            else client_module.BackendClient(http, reviewer_token=TOKEN)
        )
        try:
            if baseline:
                current = client.decide(
                    case_id,
                    proposal_id=proposal["proposal_id"],
                    case_revision=1,
                    decision="approve",
                )
            else:
                current = client.send_review(operation)
            checks["original_receipt_after_backend_recreation"] = bool(
                not baseline
                and current["review"]["replayed"] is True
                and current["review"]["review_id"] == operation.payload()["review_id"]
                and current["review"]["revision"] == 1
            )
        except client_module.BackendError:
            current = client.get_case(case_id)
        checks["corrected_current_state_preserved"] = bool(
            current["case_revision"] == 2
            and any(
                f["name"] == "streamlit_version" and f["value"] == "1.49.0"
                for f in current["facts"]
            )
        )
        checks["exactly_one_local_action"] = len(tracker.comments(case_id)) == 1
    return {
        "protocol": protocol["protocol"],
        "protocol_sha256": digest(protocol_bytes),
        "fixture_sha256": digest(fixture_bytes),
        "variant": "baseline" if baseline else "current",
        "baseline_commit": protocol["baseline_commit"],
        "runtime_sha256": source_hashes,
        "supporting_runtime_sha256": {
            path: digest((root / path).read_bytes())
            for path in (
                "src/agent_app/contracts.py",
                "src/agent_app/api.py",
                "src/agent_app/tracker/sqlite_tracker.py",
                "src/agent_app/orchestration/service.py",
                "src/agent_app/orchestration/engine.py",
                "src/agent_app/testing/ui_review_acceptance.py",
            )
        },
        "checks": checks,
        "passed": sum(checks.values()),
        "total": len(checks),
        "accepted": all(checks.values()),
        "paid_cost_usd": 0,
        "provider_calls": 0,
        "quality_claim": False,
        "transport": "ASGI TestClient",
        "restart": "same-interpreter backend recreation",
    }
