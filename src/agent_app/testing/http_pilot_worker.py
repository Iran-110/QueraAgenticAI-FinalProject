"""Fresh-interpreter offline HTTP probes, controlled only by the trusted pilot runner."""

import hashlib
import io
import json
import os
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import NAMESPACE_URL, uuid5

ROOT = Path(__file__).resolve().parents[3]
PROTOCOL = ROOT / "experiments/http_pilot_acceptance/protocol-v1.json"
PROTOCOL_V2 = ROOT / "experiments/http_pilot_acceptance/protocol-v2.json"
_PAYLOAD_FIELDS = frozenset(
    {"factory", "fixture", "state_dir", "requests", "setup_failure", "protocol", "protocol_sha256"}
)
_REQUEST_FIELDS = frozenset({"method", "path", "json", "headers"})


def _validate_payload(payload: Any) -> tuple[Path, Path, list[dict[str, Any]]]:
    if (
        type(payload) is not dict
        or set(payload) - _PAYLOAD_FIELDS
        or not {"factory", "fixture", "state_dir", "requests"} <= payload.keys()
        or any(type(payload[name]) is not str for name in ("factory", "fixture", "state_dir"))
        or type(payload.get("setup_failure", False)) is not bool
        or type(payload["requests"]) is not list
        or not 1 <= len(payload["requests"]) <= 20
    ):
        raise ValueError("WorkerPayloadInvalid")
    protocol_path = Path(payload.get("protocol", str(PROTOCOL))).resolve()
    if protocol_path not in {PROTOCOL.resolve(), PROTOCOL_V2.resolve()}:
        raise ValueError("WorkerProtocolInvalid")
    protocol_raw = protocol_path.read_bytes()
    if ("protocol" in payload) != ("protocol_sha256" in payload) or (
        "protocol_sha256" in payload
        and payload["protocol_sha256"] != hashlib.sha256(protocol_raw).hexdigest()
    ):
        raise ValueError("WorkerProtocolInvalid")
    protocol = json.loads(protocol_raw)
    # Both registered protocols reuse the unchanged exposed development fixture.
    original = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    if (protocol["fixture"], protocol["fixture_sha256"]) != (
        original["fixture"],
        original["fixture_sha256"],
    ):
        raise ValueError("WorkerProtocolInvalid")
    fixture_path = Path(payload["fixture"]).resolve()
    if (
        fixture_path != (ROOT / protocol["fixture"]).resolve()
        or hashlib.sha256(fixture_path.read_bytes()).hexdigest() != protocol["fixture_sha256"]
    ):
        raise ValueError("WorkerFixtureInvalid")
    state_dir = Path(payload["state_dir"])
    if not state_dir.is_absolute():
        raise ValueError("WorkerStatePathInvalid")
    return fixture_path, state_dir, payload["requests"]


def _validate_requests(requests: list[dict[str, Any]], fixture) -> None:
    cases = {fixture.case["case_id"], *fixture.case.get("extra_case_ids", [])}
    get_paths = {"/health", *(f"/cases/{case_id}" for case_id in cases)}
    post_paths = {
        f"/cases/{case_id}/{suffix}" for case_id in cases for suffix in ("messages", "decision")
    }
    turns = {turn["id"]: turn for turn in fixture.data["turns"]}
    for request in requests:
        if (
            type(request) is not dict
            or set(request) - _REQUEST_FIELDS
            or not {"method", "path"} <= request.keys()
            or type(request["method"]) is not str
            or type(request["path"]) is not str
        ):
            raise ValueError("WorkerRequestInvalid")
        method, path = request["method"], request["path"]
        if method == "GET":
            if path not in get_paths or request.get("json") is not None:
                raise ValueError("WorkerRequestInvalid")
        elif method == "POST":
            body = request.get("json")
            if path not in post_paths or type(body) is not dict:
                raise ValueError("WorkerRequestInvalid")
            if path.endswith("/messages"):
                turn = turns.get(body.get("turn_id"))
                if turn is None or path != (
                    f"/cases/{turn.get('case_id', fixture.case['case_id'])}/messages"
                ):
                    raise ValueError("WorkerTurnInvalid")
        else:
            raise ValueError("WorkerRequestInvalid")
        headers = request.get("headers", {})
        if (
            type(headers) is not dict
            or len(headers) > 10
            or any(
                type(name) is not str
                or type(value) is not str
                or len(name) > 100
                or len(value) > 1_000
                for name, value in headers.items()
            )
        ):
            raise ValueError("WorkerHeadersInvalid")


def run(payload: Any) -> dict[str, Any]:
    """Return fixed errors and partial observations, never a successful empty probe."""
    response: dict[str, Any] = {
        "pid": os.getpid(),
        "tracker_backend": "not_started",
        "responses": [],
        "counts": {"factory_calls": 0, "retrieval_calls": 0, "reasoning_calls": 0},
        "reasoning_inputs": [],
        "error_code": None,
    }
    observations = None
    # All plugin/application output is discarded. The only stdout is main's
    # final JSON envelope; raw exceptions, configuration and prints never escape.
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        try:
            from agent_app.testing.http_pilot_runtime import (
                Observations,
                load_runtime,
                offline_network,
            )

            with offline_network():
                from fastapi.testclient import TestClient

                from agent_app import api
                from agent_app.evaluation import runner
                from agent_app.orchestration import engine as engine_module

                fixture_path, state_dir, requests = _validate_payload(payload)
                fixture = runner.load_fixture(fixture_path, mode="offline")
                _validate_requests(requests, fixture)
                scripted = runner._scripted(fixture)
                turns = {turn["id"]: turn for turn in fixture.data["turns"]}
                observations = Observations()
                with load_runtime(payload["factory"], state_dir) as runtime:
                    response["tracker_backend"] = runtime.tracker_backend
                    with TestClient(runtime.app) as client:
                        for request in requests:
                            before = observations.snapshot()
                            method, path = request["method"], request["path"]
                            body, headers = request.get("json"), request.get("headers", {})
                            if method == "POST" and path.endswith("/decision"):
                                headers = {**runtime.review_headers, **headers}
                            if method == "POST" and path.endswith("/messages"):
                                turn = turns[body["turn_id"]]
                                case_id = turn.get("case_id", fixture.case["case_id"])
                                identity = f"{fixture.data['fixture_id']}:{case_id}:{turn['id']}"
                                run_id = uuid5(NAMESPACE_URL, identity)

                                def adapters(_scenario, turn=turn, case_id=case_id):
                                    if payload.get("setup_failure", False):
                                        observations.factory_calls += 1
                                        raise RuntimeError("InjectedAdapterSetupUnavailable")
                                    return observations.wrap(scripted(case_id, turn))

                                with (
                                    patch.object(api, "_adapters", adapters),
                                    patch.object(engine_module, "uuid4", lambda rid=run_id: rid),
                                ):
                                    result = client.post(path, json=body, headers=headers)
                            elif method == "POST":
                                result = client.post(path, json=body, headers=headers)
                            else:
                                result = client.get(path, headers=headers)
                            response["responses"].append(
                                {
                                    "status_code": result.status_code,
                                    "body": result.json(),
                                    "counts_before": before,
                                    "counts_after": observations.snapshot(),
                                }
                            )
                        if runtime.durable_review:
                            response["local_actions"] = (
                                runtime.local_actions_supplier(fixture.case["case_id"])
                                if runtime.local_actions_supplier is not None
                                else None
                            )
        except Exception:
            response["error_code"] = "WorkerFailed"
        finally:
            if observations is not None:
                response["counts"] = observations.snapshot()
                response["reasoning_inputs"] = observations.observed_inputs
    return response


def main() -> int:
    try:
        # The parent runner already bounds subprocess time. Bound input as well
        # so an accidental enormous control payload cannot allocate indefinitely.
        raw = sys.stdin.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError("WorkerInputTooLarge")
        payload = json.loads(raw)
    except Exception:
        payload = None
    result = run(payload)
    # JSON transport must work with Windows legacy console encodings (e.g. cp1252).
    print(json.dumps(result, ensure_ascii=True, allow_nan=False))
    return 1 if result["error_code"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
