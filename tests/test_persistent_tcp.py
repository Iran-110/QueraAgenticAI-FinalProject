"""Local TCP UI client across fresh backend interpreters; no outgoing connections."""

import json
import os
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
import json
import socket
from pathlib import Path
import uvicorn
from agent_app.offline_backend import application_factory
from agent_app.testing.http_pilot_runtime import offline_network
with offline_network():
    application = application_factory()
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        with Path(sys.argv[1]).open('x', encoding='ascii') as output:
            json.dump({'port': listener.getsockname()[1]}, output)
        config = uvicorn.Config(application, log_level='critical', access_log=False)
        uvicorn.Server(config).run(sockets=[listener])
"""


@contextmanager
def server(ready_path, config):
    process = subprocess.Popen(
        [sys.executable, "-c", WORKER, str(ready_path)],
        cwd=ROOT,
        env={**os.environ, **config},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    http = None
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise AssertionError("Offline worker failed before readiness")
            if http is None:
                try:
                    port = json.loads(ready_path.read_text(encoding="ascii"))["port"]
                    http = httpx.Client(
                        base_url=f"http://127.0.0.1:{port}",
                        # Match the actual UI's ten-second read allowance; keep
                        # readiness connections short and every wait bounded.
                        timeout=httpx.Timeout(10.0, connect=2.0),
                        trust_env=False,
                    )
                except (OSError, ValueError, KeyError):
                    time.sleep(0.02)
                    continue
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
        if http is not None:
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
    with server(tmp_path / "ready-first.json", config) as http:
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
    with server(tmp_path / "ready-restart.json", config) as fresh:
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
