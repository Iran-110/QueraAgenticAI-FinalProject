"""Replay registered offline correction controls on archived before/after source.

Both arms use identical amended test bytes, temporary SQLite and authored
reasoning. Loopback TCP is permitted for fresh-interpreter controls; external
connections/DNS and inherited provider credentials are excluded. No index,
provider, .env, production ledger, quality score or original PR40 case is used.
"""

import argparse
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "a6ec28d9c19a68152778028e0aae936d7716b7e1"
PRE_PRODUCTION = "ab6ed0498c079365658d4741bc8e9df37537a075"
PROTOCOL = "experiments/offline_corrections/protocol-v1.json"
AMENDMENT = "experiments/offline_corrections/amendment-v2.json"
TESTS = (
    "tests/test_offline_scripted_corrections.py",
    "tests/test_offline_correction_upgrade.py",
    "tests/test_offline_scripted_ui.py",
)
HELPER = "tests/test_persistent_tcp.py"
ARCHIVE_PATHS = ("src/agent_app", "app_pages", "pyproject.toml", HELPER)
CONTROLS = 19
SAFE_ENV = (
    "PATH",
    "SystemRoot",
    "SYSTEMROOT",
    "WINDIR",
    "COMSPEC",
    "PATHEXT",
    "TEMP",
    "TMP",
    "TMPDIR",
    "HOME",
    "USERPROFILE",
    "APPDATA",
    "LOCALAPPDATA",
    "LANG",
    "LC_ALL",
)

# Installed before package imports in both the pytest child and fresh TCP workers.
ORIGIN_GUARD = r"""
import importlib.machinery
import sys
from pathlib import Path
snapshot_root = Path(SNAPSHOT_ROOT).resolve()
sys.path.insert(0, str(snapshot_root / "src"))
class SnapshotOrigin:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "agent_app" or fullname.startswith("agent_app."):
            spec = importlib.machinery.PathFinder.find_spec(fullname, path)
            if spec is None or spec.origin is None or not Path(spec.origin).resolve().is_relative_to(snapshot_root / "src"):
                raise RuntimeError("SnapshotOriginInvalid")
            return spec
        return None
sys.meta_path.insert(0, importlib.machinery.PathFinder)
sys.meta_path.insert(0, SnapshotOrigin())
"""

CHILD = r"""
import contextlib
import io
import json
import socket
import sys
import tempfile
from pathlib import Path

snapshot_root = Path(sys.argv[1]).resolve()
tests = json.loads(sys.argv[2])
origin_guard = sys.argv[3]
exec(origin_guard.replace("SNAPSHOT_ROOT", repr(str(snapshot_root))))
sys.path.insert(0, str(snapshot_root / "tests"))

original_connect = socket.socket.connect
original_connect_ex = socket.socket.connect_ex
original_create_connection = socket.create_connection
original_getaddrinfo = socket.getaddrinfo
def deny(*args, **kwargs):
    raise RuntimeError("ExternalNetworkDisabled")
def loopback(address):
    return isinstance(address, tuple) and len(address) >= 2 and address[0] in ("127.0.0.1", "::1")
def connect(sock, address):
    return original_connect(sock, address) if loopback(address) else deny()
def connect_ex(sock, address):
    return original_connect_ex(sock, address) if loopback(address) else deny()
def create_connection(address, *args, **kwargs):
    return original_create_connection(address, *args, **kwargs) if loopback(address) else deny()
def getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if host not in ("127.0.0.1", "::1"):
        return deny()
    return original_getaddrinfo(host, port, family, type, proto, flags | socket.AI_NUMERICHOST)
socket.socket.connect = connect
socket.socket.connect_ex = connect_ex
socket.create_connection = create_connection
socket.getaddrinfo = getaddrinfo
socket.gethostbyname = socket.gethostbyname_ex = socket.gethostbyaddr = deny
socket.socket.sendto = deny

import pytest
import test_persistent_tcp
assert Path(test_persistent_tcp.__file__).resolve() == snapshot_root / "tests/test_persistent_tcp.py"
# The file/helper remains byte-identical. Only the worker's import prelude gains
# a fail-closed origin guard; its normal offline_network and server logic remain.
test_persistent_tcp.WORKER = origin_guard.replace("SNAPSHOT_ROOT", repr(str(snapshot_root))) + "\n" + test_persistent_tcp.WORKER

class Outcomes:
    def __init__(self):
        self.items = {}
    def pytest_collection_modifyitems(self, items):
        self.items = {item.nodeid: "not_run" for item in items}
    def pytest_runtest_logreport(self, report):
        if report.failed:
            self.items[report.nodeid] = "failed" if report.when == "call" else "error"
        elif report.skipped and self.items.get(report.nodeid) not in {"failed", "error"}:
            self.items[report.nodeid] = "skipped"
        elif report.when == "call" and report.passed:
            self.items[report.nodeid] = "passed"

outcomes = Outcomes()
with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    exit_code = int(pytest.main(
        [*tests, "--rootdir", str(snapshot_root), "-q", "-p", "no:cacheprovider"],
        plugins=[outcomes],
    ))
    from fastapi.testclient import TestClient
    from agent_app.offline_backend import configured_app
    from agent_app.testing.http_pilot_runtime import offline_network
    samples = []
    with tempfile.TemporaryDirectory(prefix="offline-correction-samples-") as temporary:
        config = {
            "AGENT_TRACKER_DB": str(Path(temporary) / "samples.sqlite3"),
            "AGENT_REVIEWER_TOKEN": "synthetic-local-comparison-review-credential",
        }
        events = [
            {"message": "The app uses Streamlit 1.50.0 and the widget resets.", "turn_id": "sample-known", "expected_revision": 0, "scenario": "ask", "reported_facts": [{"name": "streamlit_version", "value": "1.50.0"}]},
            {"message": "Correction: the installed version is 1.49.1.", "turn_id": "sample-correction", "expected_revision": 1, "scenario": "ask", "reported_facts": [{"name": "streamlit_version", "value": "1.49.1"}]},
            {"message": "Here is the widget's key and code.", "turn_id": "sample-widget", "expected_revision": 2, "scenario": "ask", "reported_facts": [{"name": "widget_definition", "value": "st.multiselect('Conversation', ['a'], key='conversation')"}]},
        ]
        with offline_network(), TestClient(configured_app(config)) as client:
            for event in events:
                response = client.post("/cases/offline-comparison-sample/messages", json=event)
                if response.status_code != 200:
                    raise RuntimeError("SampleHTTPInvalid")
                view = response.json()
                if view["actions"] or view["quality_claim"] or view["reasoning_label"] != "scripted" or view["retrieval_label"] != "scripted":
                    raise RuntimeError("SampleScopeInvalid")
                samples.append({"original_event": event, "http_status": response.status_code, "view": view})

for name, module in tuple(sys.modules.items()):
    if (name == "agent_app" or name.startswith("agent_app.")) and getattr(module, "__file__", None):
        assert Path(module.__file__).resolve().is_relative_to(snapshot_root / "src")
if exit_code not in {0, 1} or len(outcomes.items) != 19:
    raise RuntimeError("ControlInventoryInvalid")
print(json.dumps({
    "pytest_exit_code": exit_code,
    "test_outcomes": [{"node_id": key, "status": value} for key, value in outcomes.items.items()],
    "sample_http_views": samples,
    "imports_bound_to_snapshot": True,
    "fresh_worker_origin_guard_installed": True,
    "network_scope": "numeric_loopback_only; fixture/worker offline_network guards retained",
}))
"""


class ComparisonRejected(ValueError):
    """Only fixed diagnostics escape; child logs/environment never do."""


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _git(*arguments):
    result = subprocess.run(["git", *arguments], cwd=ROOT, capture_output=True, check=False)
    if result.returncode:
        raise ComparisonRejected("GitSnapshotUnavailable")
    return result.stdout


def _sources(root):
    paths = [
        *sorted((root / "src/agent_app").rglob("*.py")),
        *sorted((root / "app_pages").rglob("*.py")),
        root / "pyproject.toml",
        root / HELPER,
    ]
    return {path.relative_to(root).as_posix(): _sha(path.read_bytes()) for path in paths}


def _pins():
    return {
        "runner_sha256": _sha(Path(__file__).read_bytes()),
        "protocol_sha256": _sha((ROOT / PROTOCOL).read_bytes()),
        "amendment_sha256": _sha((ROOT / AMENDMENT).read_bytes()),
        "test_sha256": {name: _sha((ROOT / name).read_bytes()) for name in TESTS},
        "source_sha256": _sources(ROOT),
        "worker_origin_guard_sha256": _sha(ORIGIN_GUARD.encode()),
    }


def _assert_pins(pins):
    if _pins() != pins:
        raise ComparisonRejected("InputsChangedDuringComparison")


def _environment(snapshot):
    return {
        **{name: os.environ[name] for name in SAFE_ENV if name in os.environ},
        "PYTHONPATH": str(snapshot / "src"),
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def _archive(revision, target):
    with tarfile.open(fileobj=io.BytesIO(_git("archive", revision, *ARCHIVE_PATHS))) as archive:
        archive.extractall(target, filter="data")


def _execute(snapshot):
    child = subprocess.run(
        [sys.executable, "-I", "-B", "-c", CHILD, str(snapshot), json.dumps(TESTS), ORIGIN_GUARD],
        cwd=snapshot,
        env=_environment(snapshot),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=180,
    )
    if child.returncode:
        raise ComparisonRejected("SnapshotReplayFailed")
    try:
        report = json.loads(child.stdout)
        counts = {
            status: sum(item["status"] == status for item in report["test_outcomes"])
            for status in ("passed", "failed", "error", "skipped", "not_run")
        }
        if (
            len(report["test_outcomes"]) != CONTROLS
            or sum(counts.values()) != CONTROLS
            or counts["error"]
            or counts["skipped"]
            or counts["not_run"]
            or len(report["sample_http_views"]) != 3
            or not report["imports_bound_to_snapshot"]
            or not report["fresh_worker_origin_guard_installed"]
        ):
            raise ValueError
    except (ValueError, TypeError, KeyError):
        raise ComparisonRejected("SnapshotReplayInvalid") from None
    return {"counts": counts, **report}


def compare():
    pins = _pins()
    amendment = json.loads((ROOT / AMENDMENT).read_bytes())
    if amendment.get("test_sha256") != pins["test_sha256"]:
        raise ComparisonRejected("AmendedTestsMismatch")
    if _git("diff", "--name-only", BASELINE, PRE_PRODUCTION, "--", *ARCHIVE_PATHS).strip():
        raise ComparisonRejected("BaselineSourceChanged")
    head = _git("rev-parse", "HEAD").decode().strip()
    tests = {name: (ROOT / name).read_bytes() for name in TESTS}
    arms = {}
    with tempfile.TemporaryDirectory(prefix="offline-correction-comparison-") as temporary:
        for arm, revision in (("baseline", BASELINE), ("current", head)):
            _assert_pins(pins)
            snapshot = Path(temporary) / arm
            snapshot.mkdir()
            _archive(revision, snapshot)
            sources = _sources(snapshot)
            if arm == "current" and sources != pins["source_sha256"]:
                raise ComparisonRejected("CurrentSourceNotCommitted")
            for name, content in tests.items():
                destination = snapshot / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
            actual_test_pins = {name: _sha((snapshot / name).read_bytes()) for name in TESTS}
            if actual_test_pins != pins["test_sha256"]:
                raise ComparisonRejected("CopiedTestsMismatch")
            report = _execute(snapshot)
            _assert_pins(pins)
            if _sources(snapshot) != sources:
                raise ComparisonRejected("SnapshotSourceChanged")
            arms[arm] = {
                "source_commit": revision,
                "source_matches_git_commit": True,
                "source_sha256": sources,
                "test_sha256": actual_test_pins,
                **report,
            }
    _assert_pins(pins)
    if [item["node_id"] for item in arms["baseline"]["test_outcomes"]] != [
        item["node_id"] for item in arms["current"]["test_outcomes"]
    ]:
        raise ComparisonRejected("ControlInventoryChanged")
    return {
        "schema_version": 1,
        "mode": "offline_scripted_correction_code_comparison",
        "registered_controls": CONTROLS,
        "baseline_source_equivalent_to": PRE_PRODUCTION,
        "initial_pins": pins,
        "environment_scope": "OS/Python/temp/home allowlist; no inherited provider selectors or credentials",
        "real_provider_requests": 0,
        "paid_api_cost_usd": "0",
        "production_ledger_used": False,
        "production_index_or_embedding_tested": False,
        "sample_tracker_actions": 0,
        "quality_claim": False,
        "heldout_claim": False,
        "human_usefulness_score": None,
        "scope": "Nineteen authored software controls; actual tests may approve synthetic local questions. Sample three-turn views do not approve or execute actions. No model chooses these routes; no original PR40 case is rerun.",
        "arms": arms,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    if arguments.output.exists():
        parser.error("OutputAlreadyExists")
    try:
        result = compare()
        encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        with arguments.output.open("x", encoding="utf-8") as destination:
            destination.write(encoded)
    except (OSError, subprocess.TimeoutExpired, ComparisonRejected, ValueError):
        parser.exit(1, "OfflineCorrectionComparisonRejected\n")
    print(
        json.dumps(
            {
                "mode": result["mode"],
                "receipt_sha256": _sha(encoded.encode()),
                "registered_controls": CONTROLS,
                "counts": {arm: data["counts"] for arm, data in result["arms"].items()},
                "real_provider_requests": 0,
                "paid_api_cost_usd": "0",
                "quality_claim": False,
            }
        )
    )


if __name__ == "__main__":
    main()
