"""Replay frozen caller-vocabulary controls on actual before/after Git source.

All selections are authored, with intercepted provider wires and temporary
storage. This compares question availability/configuration, not model quality.
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

from offline_correction_comparison import ORIGIN_GUARD, SAFE_ENV

ROOT = Path(__file__).resolve().parents[1]
PACKET = Path("experiments/user_gap_configuration")
PROTOCOL = PACKET / "protocol-v1.json"
TESTS = ("tests/test_configured_user_gap_catalog.py", "tests/test_user_gap_configuration_http.py")
ARCHIVE = (
    "src/agent_app",
    "pyproject.toml",
    "tests/test_evaluation_live.py",
    "streamlit-data-for-dev-test",
    "data/evaluation/split-manifest.json",
    "experiments/corpus/pilot-allowlist.json",
)
CHILD = r"""
import contextlib, io, json, socket, sys
from pathlib import Path
root = Path(sys.argv[1]).resolve()
exec(sys.argv[2].replace("SNAPSHOT_ROOT", repr(str(root))))
sys.path.insert(0, str(root / 'tests'))
original_connect, original_connect_ex = socket.socket.connect, socket.socket.connect_ex
original_create, original_getaddrinfo = socket.create_connection, socket.getaddrinfo
def deny(*args, **kwargs):
    raise RuntimeError('ExternalNetworkDisabled')
def local(address):
    return isinstance(address, tuple) and len(address) >= 2 and address[0] in ('127.0.0.1', '::1')
socket.socket.connect = lambda sock,address: original_connect(sock,address) if local(address) else deny()
socket.socket.connect_ex = lambda sock,address: original_connect_ex(sock,address) if local(address) else deny()
socket.create_connection = lambda address,*args,**kwargs: original_create(address,*args,**kwargs) if local(address) else deny()
def getaddrinfo(host,port,family=0,type=0,proto=0,flags=0):
    if host not in ('127.0.0.1', '::1'):
        return deny()
    return original_getaddrinfo(host,port,family,type,proto,flags | socket.AI_NUMERICHOST)
socket.getaddrinfo = getaddrinfo
socket.gethostbyname = socket.gethostbyname_ex = socket.gethostbyaddr = deny
socket.socket.sendto = deny
class Outcomes:
    def __init__(self): self.items = {}
    def pytest_collection_modifyitems(self, items): self.items = {item.nodeid:'not_run' for item in items}
    def pytest_runtest_logreport(self, report):
        if report.failed: self.items[report.nodeid] = 'failed' if report.when == 'call' else 'error'
        elif report.skipped: self.items[report.nodeid] = 'skipped'
        elif report.when == 'call': self.items[report.nodeid] = 'passed'
outcomes = Outcomes()
with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    import pytest
    code = pytest.main(['-q', '-p', 'no:cacheprovider', *json.loads(sys.argv[3])], plugins=[outcomes])
    import agent_app.evaluation.live, agent_app.reasoning.catalog, test_evaluation_live
    assert Path(test_evaluation_live.__file__).resolve() == root / 'tests/test_evaluation_live.py'
    assert all(Path(module.__file__).resolve().is_relative_to(root / 'src') for module in (agent_app.evaluation.live, agent_app.reasoning.catalog))
print(json.dumps({'pytest_exit_code':code,'outcomes':outcomes.items,'imports_bound_to_snapshot':True,'external_network_disabled':True}))
"""


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def pins():
    paths = set(ROOT.glob("src/agent_app/**/*.py"))
    paths.update(ROOT.glob("streamlit-data-for-dev-test/**/*"))
    paths.update(
        ROOT / path
        for path in (
            *TESTS,
            "tests/test_evaluation_live.py",
            "pyproject.toml",
            "data/evaluation/split-manifest.json",
            "experiments/corpus/pilot-allowlist.json",
            str(PROTOCOL),
            str(PACKET / "inputs-v1.json"),
            str(PACKET / "scenario-review-v1.json"),
            "scripts/user_gap_configuration_comparison.py",
            "scripts/offline_correction_comparison.py",
        )
    )
    return {str(path.relative_to(ROOT)): sha(path.read_bytes()) for path in paths if path.is_file()}


def ledger_pins():
    return {
        name: sha(path.read_bytes()) if path.exists() else None
        for name in ("budget.sqlite3", "budget.sqlite3-wal", "budget.sqlite3-shm")
        for path in (ROOT / "runtime" / name,)
    }


def arm(commit, destination, registered):
    destination.mkdir()
    with tarfile.open(fileobj=io.BytesIO(git("archive", commit, "--", *ARCHIVE))) as archive:
        archive.extractall(destination, filter="data")
    for relative, expected in registered.items():
        raw = (ROOT / relative).read_bytes()
        if sha(raw) != expected:
            raise ValueError
        path = destination / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    environment = {key: value for key, value in os.environ.items() if key in SAFE_ENV}
    environment.update(PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    result = subprocess.run(
        [sys.executable, "-c", CHILD, str(destination), ORIGIN_GUARD, json.dumps(TESTS)],
        cwd=destination,
        env=environment,
        capture_output=True,
        encoding="utf-8",
        timeout=180,
    )
    if result.returncode != 0:
        raise ValueError
    report = json.loads(result.stdout)
    counts = {
        outcome: sum(value == outcome for value in report["outcomes"].values())
        for outcome in ("passed", "failed", "error", "skipped", "not_run")
    }
    if any(counts[name] for name in ("error", "skipped", "not_run")):
        raise ValueError
    source = {
        str(path.relative_to(destination)): sha(path.read_bytes())
        for path in (destination / "src/agent_app").rglob("*.py")
    }
    if any(git("show", f"{commit}:{path}") != (destination / path).read_bytes() for path in source):
        raise ValueError
    return {
        "source_commit": commit,
        "source_matches_git_commit": True,
        "source_sha256": source,
        "registered_pins": registered,
        "counts": counts,
        **report,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise ValueError
        protocol = json.loads((ROOT / PROTOCOL).read_text(encoding="utf-8"))
        before, accounting = pins(), ledger_pins()
        head = git("rev-parse", "HEAD").decode().strip()
        if git("diff", "HEAD", "--", "src", "tests", "scripts", str(PACKET)):
            raise ValueError
        with tempfile.TemporaryDirectory(prefix="user-gap-compare-") as temporary:
            base = Path(temporary)
            baseline = arm(
                protocol["baseline_source_commit"], base / "baseline", protocol["registered_pins"]
            )
            if pins() != before or ledger_pins() != accounting:
                raise ValueError
            candidate = arm(head, base / "candidate", protocol["registered_pins"])
        if (
            pins() != before
            or ledger_pins() != accounting
            or git("rev-parse", "HEAD").decode().strip() != head
            or set(baseline["outcomes"]) != set(candidate["outcomes"])
            or len(candidate["outcomes"]) != protocol["registered_controls"]
        ):
            raise ValueError
        receipt = {
            "schema_version": 1,
            "protocol_id": protocol["protocol_id"],
            "protocol_sha256": sha((ROOT / PROTOCOL).read_bytes()),
            "runner_sha256": before["scripts/user_gap_configuration_comparison.py"],
            "registered_controls": protocol["registered_controls"],
            "arms": {"baseline": baseline, "candidate": candidate},
            "source_inputs_unchanged_during_run": True,
            "production_ledger_unchanged": True,
            "real_model_requests": 0,
            "paid_api_cost_usd": "0",
            "quality_claim": False,
        }
        with args.output.open("x", encoding="utf-8") as output:
            json.dump(receipt, output, ensure_ascii=False, sort_keys=True, indent=2)
            output.write("\n")
        print(
            json.dumps(
                {
                    "registered_controls": receipt["registered_controls"],
                    "counts": {name: report["counts"] for name, report in receipt["arms"].items()},
                    "quality_claim": False,
                    "paid_api_cost_usd": "0",
                }
            )
        )
    except Exception:
        raise SystemExit("UserGapConfigurationComparisonRejected") from None


if __name__ == "__main__":
    main()
