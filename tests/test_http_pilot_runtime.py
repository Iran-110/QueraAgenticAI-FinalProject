"""Offline HTTP bindings, observations and fresh-process worker boundaries."""

import json
import os
import socket
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from agent_app import api
from agent_app.contracts import CaseState, ReasoningContext, RetrievalRequest
from agent_app.evaluation import runner
from agent_app.testing.http_pilot_runtime import (
    DEFAULT_FACTORY,
    HTTPRuntimeRejected,
    Observations,
    load_runtime,
    memory_factory,
    offline_network,
)
from agent_app.testing.http_pilot_worker import run

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "data/evaluation/dev/pilot-12782.json"
PRIVATE = "PRIVATE_HTTP_FACTORY_DIAGNOSTIC"
ZERO = {"factory_calls": 0, "retrieval_calls": 0, "reasoning_calls": 0}


@pytest.fixture
def fixture():
    return runner.load_fixture(FIXTURE, mode="offline")


def payload(directory, fixture, *, requests=None, **extra):
    cid = fixture.case["case_id"]
    event = runner._event(fixture.data["turns"][0], 0, None)
    return {
        "factory": DEFAULT_FACTORY,
        "fixture": str(FIXTURE),
        "state_dir": str(directory),
        "requests": requests
        or [
            {"method": "GET", "path": f"/cases/{cid}"},
            {"method": "POST", "path": f"/cases/{cid}/messages", "json": event},
            {"method": "POST", "path": f"/cases/{cid}/messages", "json": event},
        ],
        **extra,
    }


def process(raw):
    result = subprocess.run(
        [sys.executable, "-m", "agent_app.testing.http_pilot_worker"],
        input=raw,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=20,
    )
    assert result.stderr == ""
    # Decoding the entire stdout also rejects any extra console output or JSON.
    return result.returncode, json.loads(result.stdout)


def test_actual_fresh_interpreters_start_empty_and_count_exact_retry(tmp_path, fixture):
    control = payload(tmp_path, fixture)
    first_status, first = process(json.dumps(control))
    second_status, second = process(json.dumps(control))
    assert first_status == second_status == 0
    assert first["pid"] != second["pid"]
    assert first["pid"] != os.getpid() and second["pid"] != os.getpid()
    for receipt in (first, second):
        assert receipt["error_code"] is None
        assert receipt["tracker_backend"] == "process_memory_dummy_tracker"
        initial, proposed, retried = receipt["responses"]
        assert initial["status_code"] == 200 and initial["body"]["case_revision"] == 0
        assert initial["body"]["log"] == []
        assert proposed["status_code"] == retried["status_code"] == 200
        assert proposed["body"]["case_revision"] == retried["body"]["case_revision"] == 1
        assert not proposed["body"]["intake"]["replayed"]
        assert retried["body"]["intake"]["replayed"]
        assert proposed["body"]["pending"] == retried["body"]["pending"]
        assert proposed["body"]["log"] == retried["body"]["log"]
        assert retried["counts_before"] == retried["counts_after"] == receipt["counts"]
        assert receipt["counts"] == {
            "factory_calls": 1,
            "retrieval_calls": 1,
            "reasoning_calls": 1,
        }
        observed = receipt["reasoning_inputs"]
        assert len(observed) == 1
        assert observed[0]["user_message"] == control["requests"][1]["json"]["message"]
        assert observed[0]["case_id"] == fixture.case["case_id"]
        assert observed[0]["case_revision"] == 1
        assert observed[0]["evidence_chunk_ids"] == [
            hit.chunk_id
            for hit in fixture.bundles[fixture.data["turns"][0]["evidence_bundle"]].hits
        ]
    # Reusing the same directory does not grant the memory factory persistence:
    # each new process accepts the original event as a NEW event, not a replay.
    assert not second["responses"][1]["body"]["intake"]["replayed"]


def test_new_testclient_is_only_reconnect_and_keeps_same_process_state(tmp_path, fixture):
    observations = Observations()
    scripted = runner._scripted(fixture)
    cid = fixture.case["case_id"]
    event = runner._event(fixture.data["turns"][0], 0, None)
    with (
        offline_network(),
        memory_factory(tmp_path) as runtime,
        patch.object(
            api,
            "_adapters",
            lambda _: observations.wrap(scripted(cid, fixture.data["turns"][0])),
        ),
    ):
        with TestClient(runtime.app) as first_client:
            before = first_client.post(f"/cases/{cid}/messages", json=event).json()
        counts = observations.snapshot()
        with TestClient(runtime.app) as reconnected_client:
            after = reconnected_client.get(f"/cases/{cid}").json()
            retry = reconnected_client.post(f"/cases/{cid}/messages", json=event).json()
        assert after == before
        assert retry["intake"]["replayed"]
        assert retry["pending"] == before["pending"] and retry["log"] == before["log"]
        assert observations.snapshot() == counts


def test_factory_isolates_and_restores_both_original_memory_owners(tmp_path):
    original_cases, original_tracker = api._cases, api.tracker
    with memory_factory(tmp_path) as runtime:
        assert runtime.app is api.app
        assert api._cases == {} and api._cases is not original_cases
        assert api.tracker is not original_tracker
    assert api._cases is original_cases and api.tracker is original_tracker


def test_setup_failure_receipt_replays_without_constructing_ports(tmp_path, fixture):
    status, receipt = process(json.dumps(payload(tmp_path, fixture, setup_failure=True)))
    assert status == 0 and receipt["error_code"] is None
    initial, stopped, retry = receipt["responses"]
    assert initial["counts_after"] == ZERO
    assert stopped["body"]["case_revision"] == retry["body"]["case_revision"] == 1
    assert stopped["body"]["pending"] is retry["body"]["pending"] is None
    assert "AdapterSetupUnavailable" in stopped["body"]["log"][-1]["text"]
    assert retry["body"]["intake"]["replayed"]
    assert stopped["body"]["log"] == retry["body"]["log"]
    assert receipt["reasoning_inputs"] == []
    assert (
        retry["counts_before"]
        == retry["counts_after"]
        == receipt["counts"]
        == {
            "factory_calls": 1,
            "retrieval_calls": 0,
            "reasoning_calls": 0,
        }
    )


@pytest.mark.parametrize(
    "requests",
    [
        [],
        [{"method": "GET", "path": "/health"}] * 21,
        [{"method": "DELETE", "path": "/health"}],
        [{"method": "GET", "path": "/unregistered"}],
        [{"method": "GET", "path": "/health?ignored=true"}],
        [{"method": "GET", "path": "/health", "json": {"private": PRIVATE}}],
        [{"method": "GET", "path": "/health", "headers": {"X-Test": 12}}],
    ],
)
def test_invalid_request_sets_fail_before_any_factory_or_port(tmp_path, fixture, requests):
    control = payload(tmp_path, fixture)
    control["requests"] = requests
    receipt = run(control)
    assert receipt["error_code"] == "WorkerFailed"
    assert receipt["responses"] == [] and receipt["counts"] == ZERO
    assert receipt["tracker_backend"] == "not_started"
    assert receipt["reasoning_inputs"] == []
    assert PRIVATE not in json.dumps(receipt)


def test_unknown_turn_fails_before_attempting_script_lookup(tmp_path, fixture):
    control = payload(tmp_path, fixture)
    control["requests"][1]["json"] = {
        **control["requests"][1]["json"],
        "turn_id": "unregistered-turn",
    }
    receipt = run(control)
    assert receipt["error_code"] == "WorkerFailed"
    assert receipt["counts"] == ZERO and receipt["responses"] == []


@pytest.mark.parametrize("raw", ['{"factory":', "", "not-json", "[1, 2, 3]"])
def test_truncated_or_malformed_stdin_returns_one_safe_failed_envelope(raw):
    status, receipt = process(raw)
    assert status == 1 and receipt["error_code"] == "WorkerFailed"
    assert receipt["responses"] == [] and receipt["counts"] == ZERO


def test_worker_pins_registered_fixture_before_loading_factory(tmp_path, fixture):
    alternate = tmp_path / "copied-fixture.json"
    alternate.write_bytes(FIXTURE.read_bytes())
    control = payload(tmp_path, fixture, factory=f"{PRIVATE}:factory")
    control["fixture"] = str(alternate)
    receipt = run(control)
    assert receipt["error_code"] == "WorkerFailed" and receipt["counts"] == ZERO
    assert receipt["tracker_backend"] == "not_started"
    assert PRIVATE not in json.dumps(receipt)


def test_socket_guard_blocks_connections_and_dns_but_preserves_socketpair():
    original = (socket.socket.connect, socket.socket.connect_ex, socket.create_connection)
    with offline_network():
        with socket.socket() as candidate:
            for connect in (candidate.connect, candidate.connect_ex):
                with pytest.raises(RuntimeError, match="^OfflineNetworkBlocked$"):
                    connect(("127.0.0.1", 9))
        with pytest.raises(RuntimeError, match="^OfflineNetworkBlocked$"):
            socket.create_connection(("127.0.0.1", 9))
        with pytest.raises(RuntimeError, match="^OfflineNetworkBlocked$"):
            socket.getaddrinfo("never-resolve.invalid", 443)
        left, right = socket.socketpair()
        with left, right:
            left.sendall(b"offline")
            assert right.recv(7) == b"offline"
    assert original == (socket.socket.connect, socket.socket.connect_ex, socket.create_connection)


def plugin(tmp_path, monkeypatch, source):
    name = f"offline_http_factory_{uuid4().hex}"
    (tmp_path / f"{name}.py").write_text(source, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    return f"{name}:factory"


@pytest.mark.parametrize("stage", ["import", "entry", "custom_error", "exit"])
def test_private_factory_diagnostics_and_prints_are_discarded(tmp_path, monkeypatch, capsys, stage):
    prefix = (
        "import sys\n"
        "from contextlib import contextmanager\n"
        "from agent_app import api\n"
        "from agent_app.testing.http_pilot_runtime import HTTPRuntime, HTTPRuntimeRejected\n"
        f"print({PRIVATE!r})\nprint({PRIVATE!r}, file=sys.stderr)\n"
    )
    if stage == "import":
        source = prefix + f"raise RuntimeError({PRIVATE!r})\n"
    else:
        error = (
            f"HTTPRuntimeRejected({PRIVATE!r})"
            if stage == "custom_error"
            else f"RuntimeError({PRIVATE!r})"
        )
        source = prefix + (
            "@contextmanager\n"
            "def factory(state_dir):\n"
            f"    print({PRIVATE!r})\n"
            f"    print({PRIVATE!r}, file=sys.stderr)\n"
            + (
                f"    raise {error}\n    yield\n"
                if stage != "exit"
                else f"    yield HTTPRuntime(api.app, 'offline_fixture')\n    raise {error}\n"
            )
        )
    spec = plugin(tmp_path, monkeypatch, source)
    with pytest.raises(HTTPRuntimeRejected) as raised, load_runtime(spec, tmp_path):
        pass
    assert raised.value.code == str(raised.value) == "HTTPFactoryUnavailable"
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""
    assert PRIVATE not in str(raised.value)


@pytest.mark.parametrize("spec", ["", "bad factory", "module:", "module:factory()"])
def test_factory_syntax_is_rejected_without_exposing_spec(tmp_path, spec):
    with pytest.raises(HTTPRuntimeRejected, match="^HTTPFactoryInvalid$"):
        with load_runtime(spec, tmp_path):
            pytest.fail("Invalid factory executed")


def test_runtime_output_must_be_validated_before_any_probe(tmp_path, monkeypatch):
    spec = plugin(
        tmp_path,
        monkeypatch,
        "from contextlib import contextmanager\n"
        "@contextmanager\n"
        "def factory(state_dir):\n"
        f"    yield {{'private': {PRIVATE!r}}}\n",
    )
    with pytest.raises(HTTPRuntimeRejected, match="^HTTPRuntimeInvalid$"):
        with load_runtime(spec, tmp_path):
            pytest.fail("Invalid runtime reached probe")


def test_cleanup_cannot_suppress_a_failed_probe(tmp_path, monkeypatch, capsys):
    spec = plugin(
        tmp_path,
        monkeypatch,
        "from agent_app import api\n"
        "from agent_app.testing.http_pilot_runtime import HTTPRuntime\n"
        "class Suppressor:\n"
        "    def __enter__(self):\n"
        "        return HTTPRuntime(api.app, 'offline_fixture')\n"
        "    def __exit__(self, kind, error, traceback):\n"
        "        assert kind is RuntimeError and error is not None\n"
        f"        print({PRIVATE!r})\n"
        "        return True\n"
        "def factory(state_dir):\n"
        "    return Suppressor()\n",
    )
    with pytest.raises(RuntimeError, match="^ProbeFailed$"):
        with load_runtime(spec, tmp_path):
            raise RuntimeError("ProbeFailed")
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


def test_uninstrumented_app_is_rejected_before_routes(tmp_path, monkeypatch, fixture):
    spec = plugin(
        tmp_path,
        monkeypatch,
        "from contextlib import contextmanager\n"
        "from fastapi import FastAPI\n"
        "from fastapi.responses import PlainTextResponse\n"
        "from agent_app.testing.http_pilot_runtime import HTTPRuntime\n"
        "app = FastAPI()\n"
        "@app.get('/health')\n"
        "def health():\n"
        f"    return PlainTextResponse({PRIVATE!r})\n"
        "@contextmanager\n"
        "def factory(state_dir):\n"
        "    yield HTTPRuntime(app, 'offline_fixture')\n",
    )
    receipt = run(
        payload(
            tmp_path,
            fixture,
            factory=spec,
            requests=[{"method": "GET", "path": "/health"}],
        )
    )
    assert receipt["error_code"] == "WorkerFailed"
    assert receipt["responses"] == [] and receipt["counts"] == ZERO
    assert receipt["tracker_backend"] == "not_started"
    assert PRIVATE not in json.dumps(receipt)


def test_worker_blocks_network_before_factory_import(tmp_path, monkeypatch, fixture):
    spec = plugin(
        tmp_path,
        monkeypatch,
        "import socket\n"
        "try:\n"
        "    socket.create_connection(('127.0.0.1', 9))\n"
        "except RuntimeError as error:\n"
        "    assert str(error) == 'OfflineNetworkBlocked'\n"
        "else:\n"
        "    raise AssertionError('Factory import network guard was skipped')\n"
        "from agent_app.testing.http_pilot_runtime import memory_factory\n"
        "factory = memory_factory\n",
    )
    receipt = run(
        payload(
            tmp_path,
            fixture,
            factory=spec,
            requests=[{"method": "GET", "path": "/health"}],
        )
    )
    # Startup succeeds only when the import observed the exact network guard.
    # A real connection refusal also fails this assertion instead of passing it.
    assert receipt["error_code"] is None and receipt["counts"] == ZERO
    assert len(receipt["responses"]) == 1 and receipt["responses"][0]["status_code"] == 200


def test_observations_preserve_supplier_and_capture_actual_current_inputs(fixture):
    ports = runner._scripted(fixture)(fixture.case["case_id"], fixture.data["turns"][0])

    def supplier():
        return None

    original = api.RunAdapters(
        ports.retriever,
        ports.reasoner,
        snapshot_id=ports.snapshot_id,
        grounded_request_supplier=supplier,
    )
    observations = Observations()
    wrapped = observations.wrap(original)
    assert wrapped.grounded_request_supplier is supplier
    assert wrapped.snapshot_id == original.snapshot_id
    case = CaseState(case_id=fixture.case["case_id"], case_revision=1)
    message = fixture.data["turns"][0]["visible"]["message"]
    evidence = wrapped.retriever.search(
        RetrievalRequest(queries=(message,), snapshot_id=ports.snapshot_id)
    )
    context = ReasoningContext(
        run_id="offline-observation",
        case_id=case.case_id,
        case_revision=case.case_revision,
        attempt_index=1,
    )
    wrapped.reasoner.analyze(case, message, evidence, context=context)
    assert observations.snapshot() == {
        "factory_calls": 1,
        "retrieval_calls": 1,
        "reasoning_calls": 1,
    }
    assert observations.observed_inputs == [
        {
            "case_id": case.case_id,
            "case_revision": 1,
            "case": case.model_dump(mode="json"),
            "user_message": message,
            "evidence_snapshot_id": evidence.snapshot_id,
            "evidence_chunk_ids": [hit.chunk_id for hit in evidence.hits],
        }
    ]
    # Even an adapter bypassing the frozen model cannot rewrite the detached
    # observation of what was supplied to the reasoner.
    object.__setattr__(case, "case_revision", 2)
    assert observations.observed_inputs[0]["case_revision"] == 1
    assert observations.observed_inputs[0]["case"]["case_revision"] == 1
