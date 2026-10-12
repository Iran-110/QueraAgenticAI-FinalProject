"""Local TCP UI client across fresh backend interpreters; no outgoing connections."""

import os
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import httpx

from agent_app import ui_client
from agent_app.retrieval.offline_index import build_index
from agent_app.retrieval.pilot_corpus import build_pilot_corpus
from agent_app.testing.http_pilot_runtime import offline_network
from agent_app.tracker.sqlite_tracker import SQLiteCaseTracker

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "synthetic-loopback-review-credential-for-tests"
WORKER = """
import sys
import uvicorn
from agent_app.testing.http_pilot_runtime import offline_network
with offline_network():
    uvicorn.run('agent_app.offline_backend:application_factory', factory=True,
                fd=int(sys.argv[1]), log_level='critical', access_log=False)
"""


@contextmanager
def server(listener, config):
    process = subprocess.Popen(
        [sys.executable, "-c", WORKER, str(listener.fileno())],
        cwd=ROOT,
        env={**os.environ, **config},
        pass_fds=(listener.fileno(),),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    http = httpx.Client(
        base_url=f"http://127.0.0.1:{listener.getsockname()[1]}", timeout=2, trust_env=False
    )
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise AssertionError("Offline worker failed before readiness")
            try:
                if http.get("/health").status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.02)
        else:
            raise AssertionError("Offline worker readiness timed out")
        yield http
    finally:
        http.close()
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def test_actual_index_and_ui_client_retry_over_tcp_after_fresh_process_restart(tmp_path):
    with offline_network():
        corpus = build_pilot_corpus(
            ROOT / "streamlit-data-for-dev-test",
            ROOT / "data/evaluation/split-manifest.json",
            ROOT / "experiments/corpus/pilot-allowlist.json",
        )
        snapshot = build_index(corpus, tmp_path / "index")
    config = {
        "AGENT_TRACKER_DB": str(tmp_path / "tcp.sqlite3"),
        "AGENT_REVIEWER_TOKEN": TOKEN,
        "AGENT_PILOT_INDEX": str(tmp_path / "index"),
        "AGENT_PILOT_SNAPSHOT": snapshot,
    }
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        with server(listener, config) as http:
            client = ui_client.BackendClient(http, reviewer_token=TOKEN)
            assert client.discover_capabilities().retrieval_label == "local_chroma_hash"
            view = client.send_event(
                "tcp-pilot",
                {
                    "message": "My widget resets on rerun; version unknown.",
                    "turn_id": "tcp-original",
                    "expected_revision": 0,
                },
            )
            operation = client.prepare_review("tcp-pilot", view["pending"], "approve")
            committed = client.send_review(operation)
            assert len(committed["actions"]) == 1
        with server(listener, config) as fresh:
            client = ui_client.BackendClient(fresh, reviewer_token=TOKEN)
            corrected = client.send_event(
                "tcp-pilot",
                {
                    "message": "Correction: installed version is 1.49.0.",
                    "turn_id": "tcp-correction",
                    "expected_revision": 1,
                    "reported_facts": [{"name": "streamlit_version", "value": "1.49.0"}],
                    "context_changed": True,
                },
            )
            assert corrected["pending"]["decision"] == "escalate"
            replay = client.send_review(operation)
            assert replay["review"] == {**committed["review"], "replayed": True}
            assert replay["case_revision"] == 2
            assert len(replay["actions"]) == 1
            assert TOKEN not in str(replay)
    assert len(SQLiteCaseTracker(config["AGENT_TRACKER_DB"]).comments("tcp-pilot")) == 1
