"""Independent physical-runtime preflight regressions; temporary data and GET only."""

import json
import shutil
import subprocess
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from test_budget_quarantine_scope import multiple_holds as multiple_holds
from test_presentation_healthcheck import CHECK, verified_index_observation
from test_presentation_runtime import ROOT
from test_presentation_runtime import final_v3 as final_v3
from test_presentation_runtime import registered as registered

from agent_app.persistent_api import create_app
from agent_app.retrieval import offline_index
from agent_app.retrieval.pilot_corpus import MANIFEST_NAME
from agent_app.tracker.sqlite_tracker import SQLiteCaseTracker


@pytest.mark.parametrize(
    "fault", ["missing_directory", "changed_manifest", "changed_native_record", "none"]
)
def test_broken_physical_index_cannot_look_ready_with_valid_scope_and_get_surfaces(
    registered, tmp_path, monkeypatch, fault
):
    _, protocol_path, protocol, _ = registered
    index = Path(protocol["index"]["path"])
    assert index.is_relative_to(tmp_path) and not index.is_relative_to(ROOT)
    # Delete only the disposable registered reader copy, after authorizing its
    # synthetic finite scope. The protocol bytes/pins and source still match.
    if fault == "missing_directory":
        shutil.rmtree(index)
    elif fault == "changed_manifest":
        with (index / MANIFEST_NAME).open("ab") as stream:
            stream.write(b"\n")
    elif fault == "changed_native_record":
        native = offline_index._persistent_client(index)
        docs = native.get_collection(name="streamlit_docs", embedding_function=None)
        first = docs.get(limit=1, include=["embeddings"])
        docs.update(
            ids=first["ids"],
            documents=["Synthetic native-storage mutation after registration."],
            embeddings=[[float(value) for value in first["embeddings"][0]]],
        )

    def no_ledger(_):
        pytest.fail("Invalid physical storage must be rejected before the budget ledger is opened")

    if fault != "none":
        monkeypatch.setattr(CHECK, "BudgetLedger", no_ledger)
    tracker = SQLiteCaseTracker(protocol["tracker_path"], reviewer_tokens={"synthetic": "s" * 32})
    app = create_app(
        tracker,
        reviewer_tokens={"synthetic": "s" * 32},
        case_adapters=lambda *_: pytest.fail("Preflight must not allocate a model adapter"),
        require_message_auth=True,
        reasoning_label="metis_grounded_live",
        retrieval_label="local_chroma_hash",
    )
    requests = []
    with TestClient(app) as backend:

        def dispatch(request):
            requests.append(request)
            assert request.method == "GET" and "authorization" not in request.headers
            if request.url.port == 8502:
                return httpx.Response(200, content=b"ok")
            response = backend.get(request.url.path)
            return httpx.Response(response.status_code, content=response.content)

        report = CHECK.session_checks(
            protocol_path,
            api_url="http://127.0.0.1:8001",
            ui_url="http://127.0.0.1:8502",
            transport=httpx.MockTransport(dispatch),
        )
    if fault == "none":
        assert report["ready"] and len(requests) == 5
        assert report["index_verification"] == "verified_physical_manifest_snapshot_and_records"
        assert report["provider_probe"] == "not_performed"
        assert report["index_probe"] == verified_index_observation()
    else:
        assert not report["ready"], (
            "Valid declarations/GETs cannot replace physical retrieval verification"
        )
        assert requests == [], "An invalid public index should fail before any HTTP or credentials"


def test_child_receives_only_public_pins_with_neutral_cwd_and_whitelisted_environment(monkeypatch):
    for name in ("METIS_API_KEY", "AGENT_REVIEWER_TOKEN", "HTTPS_PROXY", "PYTHONSTARTUP"):
        monkeypatch.setenv(name, "synthetic-private-do-not-inherit")
    working_directory = []

    def run(command, **kwargs):
        assert command == [
            CHECK.sys.executable,
            "-c",
            CHECK._INDEX_CHILD,
            "/synthetic/public-index",
            "synthetic-snapshot",
            "a" * 64,
        ]
        working = Path(kwargs["cwd"])
        assert working.is_dir() and not (working / ".env").exists()
        assert not working.is_relative_to(CHECK.ROOT)
        working_directory.append(working)
        environment = kwargs["env"]
        assert set(environment) <= {
            "HOME",
            "USER",
            "LOGNAME",
            "TMPDIR",
            "LANG",
            "LC_ALL",
            "TZ",
            "SYSTEMROOT",
            "WINDIR",
            "PATH",
            "PYTHONPATH",
            "PYTHONUTF8",
            "PYTHONDONTWRITEBYTECODE",
            "ANONYMIZED_TELEMETRY",
        }
        assert "synthetic-private-do-not-inherit" not in environment.values()
        assert environment["PYTHONPATH"] == str(CHECK.ROOT / "src")
        assert environment["ANONYMIZED_TELEMETRY"] == "False"
        assert kwargs["timeout"] == 40 and kwargs["capture_output"] is True
        assert kwargs["check"] is False
        # Only the fixed receipt survives; arbitrary child diagnostics do not.
        return subprocess.CompletedProcess(
            command,
            0,
            "synthetic-private-diagnostic\n" + json.dumps(verified_index_observation()),
            "synthetic-private-stderr",
        )

    monkeypatch.setattr(CHECK.subprocess, "run", run)
    assert (
        CHECK._verify_physical_index("/synthetic/public-index", "synthetic-snapshot", "a" * 64)
        == verified_index_observation()
    )
    assert not working_directory[0].exists(), "Neutral verifier directory must be cleaned"


@pytest.mark.parametrize(
    "fault", ["timeout", "nonzero", "malformed", "blocked", "network", "boolean_count"]
)
def test_child_timeout_failed_or_blocked_observations_fail_closed_without_raw_diagnostics(
    monkeypatch, fault
):
    def run(command, **_):
        observation = verified_index_observation()
        if fault == "timeout":
            raise subprocess.TimeoutExpired(command, 40, output="synthetic-private-timeout")
        if fault == "blocked":
            observation["blocked"] = ["ProtectedInputRejected"]
        elif fault == "network":
            observation["network_connect_attempts"] = 1
        elif fault == "boolean_count":
            observation["network_connect_attempts"] = False
        return subprocess.CompletedProcess(
            command,
            7 if fault == "nonzero" else 0,
            "synthetic-private-invalid-output" if fault == "malformed" else json.dumps(observation),
            "synthetic-private-error",
        )

    monkeypatch.setattr(CHECK.subprocess, "run", run)
    with pytest.raises(ValueError, match="^PhysicalIndexUnverified$") as failure:
        CHECK._verify_physical_index("/synthetic/index", "snapshot", "a" * 64)
    assert failure.value.__cause__ is None


@pytest.mark.parametrize("fault", ["protected", "network", "close_failure", "none"])
def test_isolated_child_own_audit_blocks_private_reads_and_connections(monkeypatch, fault):
    # Deliberately synthetic import stand-in inside a real subprocess: its own
    # audit must refuse the attempted operation before filesystem/network I/O.
    action = {
        "protected": "open('.env', 'rb').read()",
        "network": "__import__('socket').socket().connect(('203.0.113.1', 443))",
        "close_failure": "pass",
        "none": "pass",
    }[fault]
    close = "raise ValueError('synthetic-close-error')" if fault == "close_failure" else "pass"
    setup = f"""
import sys, types
module = types.ModuleType('agent_app.evaluation.live')
class SyntheticClient:
    def verify(self):
        {action}
    def close(self):
        {close}
module._verified_index = lambda *args: SyntheticClient()
sys.modules['agent_app.evaluation.live'] = module
"""
    monkeypatch.setattr(CHECK, "_INDEX_CHILD", setup + CHECK._INDEX_CHILD)
    # The caller may be in the repository, where Chroma would discover .env.
    # Verification must still execute in its fresh, credential-free directory.
    monkeypatch.chdir(ROOT)
    completed = []
    real_run = CHECK.subprocess.run

    def capture(*args, **kwargs):
        result = real_run(*args, **kwargs)
        completed.append(result)
        return result

    monkeypatch.setattr(CHECK.subprocess, "run", capture)
    if fault == "none":
        report = CHECK._verify_physical_index("/synthetic/index", "snapshot", "a" * 64)
        assert report["client_close_available"] is True
    else:
        with pytest.raises(ValueError, match="^PhysicalIndexUnverified$"):
            CHECK._verify_physical_index("/synthetic/index", "snapshot", "a" * 64)
    assert completed[0].returncode == 0
    observed = json.loads(completed[0].stdout.strip().splitlines()[-1])
    assert observed["client_close_available"] is True
    assert observed["cleanup"] == "verifier_process_exit"
    assert (
        observed["blocked"]
        == {
            "protected": ["ProtectedInputRejected"],
            "network": ["NetworkRejected"],
            "close_failure": [],
            "none": [],
        }[fault]
    )
    assert observed["network_connect_attempts"] == int(fault == "network")
    assert observed["verified"] is (fault == "none")
