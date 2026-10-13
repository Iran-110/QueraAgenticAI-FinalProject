"""Compare invocation-scoped conflict controls on actual archived and current code.

Only the frozen authored test helpers/planner and public V9 packet are used.
No provider, credentials, tracker store, index build, or production ledger is used.
The old arm executes Git source; baseline outcomes are never fabricated.
"""

import argparse
import hashlib
import io
import json
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "03225e2b513d059ffbe7e0ad82ecf323757187a7"
TEST = "tests/test_conflict_continuity.py"
FIXTURES = (
    "experiments/decision_quality/cases-controlled-v8.json",
    "experiments/decision_quality/protocol-controlled-v8.json",
    "experiments/decision_quality/cases-grounding-v9.json",
    "experiments/decision_quality/protocol-grounding-v9.json",
)

CHILD = r"""
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import socket
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root / "src"))
sys.meta_path.insert(0, importlib.machinery.PathFinder)

def no_network(*args, **kwargs):
    raise RuntimeError("OfflineNetworkDisabled")

socket.create_connection = no_network
socket.getaddrinfo = no_network
socket.gethostbyname = no_network
socket.gethostbyname_ex = no_network
socket.gethostbyaddr = no_network
socket.socket.connect = no_network
socket.socket.connect_ex = no_network

import pytest

class Outcomes:
    def __init__(self):
        self.items = {}

    def pytest_collection_modifyitems(self, items):
        self.items = {item.nodeid: "not_run" for item in items}

    def pytest_runtest_logreport(self, report):
        if report.failed:
            self.items[report.nodeid] = "failed" if report.when == "call" else "error"
        elif report.skipped and self.items.get(report.nodeid) not in {"error", "failed"}:
            self.items[report.nodeid] = "skipped"
        elif report.when == "call" and report.passed:
            self.items[report.nodeid] = "passed"

outcomes = Outcomes()
with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    exit_code = int(pytest.main([
        str(root / "tests/test_conflict_continuity.py"),
        "--rootdir", str(root), "-q", "-p", "no:cacheprovider",
    ], plugins=[outcomes]))
if exit_code not in {0, 1} or len(outcomes.items) != 14:
    raise RuntimeError("ControlInventoryInvalid")

spec = importlib.util.spec_from_file_location(
    "registered_conflict_controls", root / "tests/test_conflict_continuity.py"
)
helpers = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = helpers
spec.loader.exec_module(helpers)
from agent_app.testing.controlled_decision_inputs import load_conditions
from agent_app.orchestration.handoff import build_handoff, validate_handoff
condition = next(
    item for item in load_conditions()
    if item.condition_id == "controlled-v8-same-version-synthetic-conflict"
)

details = []
target_cases = [
    ("missing_member", "answer"),
    ("changed_same_id", "answer"),
    ("warning_resolution", "answer"),
    ("missing_member", "ask"),
    ("missing_member", "escalate"),
    ("changed_same_id", "ask"),
    ("changed_same_id", "escalate"),
]
for mode, decision in target_cases:
    result, factory, planner, capture = helpers.run_two_rounds(condition, mode, decision)
    handoff = None
    if result.status == "awaiting_approval":
        handoff = validate_handoff(build_handoff(
            result, capture.last, grounded_request=planner.requests[-1]
        ))
    details.append({
        "control_id": mode + ":" + decision,
        "authored_plan_decisions": ["retrieve_more", decision],
        "run_result": result.model_dump(mode="json"),
        "valid_final_handoff": handoff.model_dump(mode="json") if handoff else None,
        "caller_current_requests": [item.model_dump(mode="json") for item in factory.requests],
        "actual_planner_requests": [item.model_dump(mode="json") for item in planner.requests],
        "actual_planner_contexts": [item.model_dump(mode="json") for item in planner.contexts],
    })

import agent_app
assert Path(agent_app.__file__).resolve().is_relative_to(root / "src")
for name, module in tuple(sys.modules.items()):
    if name.startswith("agent_app.") and getattr(module, "__file__", None):
        assert Path(module.__file__).resolve().is_relative_to(root / "src")
print(json.dumps({
    "pytest_exit_code": exit_code,
    "test_outcomes": [{"node_id": key, "status": value} for key, value in outcomes.items.items()],
    "target_controls": details,
    "imports_bound_to_snapshot": True,
    "network_disabled": True,
}))
"""


class ComparisonRejected(ValueError):
    """Stable diagnostics; child tracebacks/source inputs are never exported."""


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _digest(value: object) -> str:
    return _sha(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def _git(*arguments: str) -> bytes:
    result = subprocess.run(["git", *arguments], cwd=ROOT, capture_output=True, check=False)
    if result.returncode:
        raise ComparisonRejected("GitSnapshotUnavailable")
    return result.stdout


def _archive(revision: str, target: Path) -> None:
    data = _git("archive", revision, "src/agent_app", "experiments/decision_quality")
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        archive.extractall(target, filter="data")


def _sources(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): _sha(path.read_bytes())
        for path in sorted((root / "src/agent_app").rglob("*.py"))
    }


def _pins() -> dict:
    return {
        "script_sha256": _sha(Path(__file__).read_bytes()),
        "test_sha256": _sha((ROOT / TEST).read_bytes()),
        "fixture_sha256": {name: _sha((ROOT / name).read_bytes()) for name in FIXTURES},
        "source_sha256": _sources(ROOT),
    }


def _assert_pins(pins: dict) -> None:
    if _pins() != pins:
        raise ComparisonRejected("InputsChangedDuringComparison")


def _copy_test(target: Path, test_bytes: bytes) -> None:
    destination = target / TEST
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(test_bytes)


def _execute(target: Path) -> dict:
    child = subprocess.run(
        [sys.executable, "-I", "-B", "-c", CHILD, str(target)],
        cwd=target,
        env={"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "PYTHONUTF8": "1"},
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
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
            len(report["test_outcomes"]) != 14
            or len(report["target_controls"]) != 7
            or counts["error"]
            or counts["not_run"]
            or not report["imports_bound_to_snapshot"]
            or not report["network_disabled"]
        ):
            raise ValueError
    except (ValueError, TypeError, KeyError):
        raise ComparisonRejected("SnapshotReplayInvalid") from None
    return {"counts": counts, **report}


def compare(*, arm: str = "both") -> dict:
    if arm not in {"baseline", "current", "both"}:
        raise ComparisonRejected("UnsupportedComparisonArm")
    pins = _pins()
    test_bytes = (ROOT / TEST).read_bytes()
    head = _git("rev-parse", "HEAD").decode().strip()
    reports = {}
    with tempfile.TemporaryDirectory(prefix="core-conflict-continuity-") as temporary:
        temporary = Path(temporary)
        for selected in ("baseline", "current"):
            if arm not in {selected, "both"}:
                continue
            _assert_pins(pins)
            snapshot = temporary / selected
            snapshot.mkdir()
            revision = BASELINE if selected == "baseline" else head
            _archive(revision, snapshot)
            archived_sources = _sources(snapshot)
            if selected == "current":
                # Snapshot exact tested working-tree bytes, including uncommitted source.
                for name in archived_sources.keys() - pins["source_sha256"].keys():
                    (snapshot / name).unlink()
                for name in pins["source_sha256"]:
                    destination = snapshot / name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes((ROOT / name).read_bytes())
            source_pins = _sources(snapshot)
            fixture_pins = {name: _sha((snapshot / name).read_bytes()) for name in FIXTURES}
            if fixture_pins != pins["fixture_sha256"]:
                raise ComparisonRejected("OriginalFixtureChanged")
            _copy_test(snapshot, test_bytes)
            report = _execute(snapshot)
            _assert_pins(pins)
            reports[selected] = {
                "git_commit_at_capture": revision,
                "source_matches_git_commit": source_pins == archived_sources,
                "source_sha256": source_pins,
                "source_inventory_sha256": _digest(source_pins),
                "test_sha256": pins["test_sha256"],
                "fixture_sha256": fixture_pins,
                **report,
            }
    _assert_pins(pins)
    if arm == "both" and [item["node_id"] for item in reports["baseline"]["test_outcomes"]] != [
        item["node_id"] for item in reports["current"]["test_outcomes"]
    ]:
        raise ComparisonRejected("ControlInventoryChanged")
    return {
        "mode": "offline_authored_conflict_continuity_code_comparison",
        "baseline_git_commit": BASELINE,
        "initial_pins": pins,
        "real_provider_requests": 0,
        "paid_api_cost_usd": "0",
        "tracker_actions": 0,
        "quality_claim": False,
        "human_usefulness_score": None,
        "scope": (
            "Fourteen authored software controls reuse one exposed answer-informed V9 family. "
            "Seven target controls force first-round retrieval with an authored planner; "
            "no model selected these routes and no real RAG or independent final case is measured."
        ),
        "arms": reports,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", choices=("baseline", "current", "both"), default="both")
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    if arguments.output and arguments.output.exists():
        parser.error("OutputAlreadyExists")
    try:
        result = compare(arm=arguments.arm)
        encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if arguments.output:
            with arguments.output.open("x", encoding="utf-8") as destination:
                destination.write(encoded)
    except (OSError, subprocess.TimeoutExpired, ComparisonRejected) as error:
        code = str(error) if isinstance(error, ComparisonRejected) else "ComparisonUnavailable"
        parser.exit(1, code + "\n")
    print(encoded, end="")


if __name__ == "__main__":
    main()
