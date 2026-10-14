"""Replay identical frozen controls on real archived renderer commits, offline.

Observed V3 plans remain historical. This is a deterministic software comparison,
not another model run or model-quality score. Raw failures stay in disposable storage.
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
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = "experiments/dev_three_baseline/source-gap-handoff-protocol-v1.json"
CANDIDATE = "b5a6d922d6ff67ef1af64220044868629acc103c"
CANDIDATE_GROUNDING = "5ae551979f5e99f5eb055bd91842c55516d3364c037b5076ec39d1420b387287"
GROUNDING = "src/agent_app/reasoning/grounding.py"
WORKER = r"""
import contextlib, importlib.machinery, io, json, socket, sys
from pathlib import Path
root, test, xml = Path(sys.argv[1]).resolve(), sys.argv[2], sys.argv[3]
sys.path.insert(0, str(root / 'src'))
sys.meta_path.insert(0, importlib.machinery.PathFinder)
def blocked(*args, **kwargs):
    raise RuntimeError('OfflineNetworkDisabled')
for name in ('create_connection','getaddrinfo','gethostbyname','gethostbyname_ex','gethostbyaddr'):
    setattr(socket, name, blocked)
socket.socket.connect = socket.socket.connect_ex = blocked
import pytest
with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    code = int(pytest.main([test, '--rootdir', str(root), '-q', '-p', 'no:cacheprovider', '--junitxml', xml]))
import agent_app
for name, module in tuple(sys.modules.items()):
    if name == 'agent_app' or name.startswith('agent_app.'):
        if getattr(module, '__file__', None):
            assert Path(module.__file__).resolve().is_relative_to(root / 'src')
        for path in getattr(module, '__path__', ()):
            assert Path(path).resolve().is_relative_to(root / 'src')
assert Path(agent_app.__file__).resolve().is_relative_to(root / 'src')
print(json.dumps({'pytest_exit_code': code, 'imports_bound_to_snapshot': True, 'network_disabled': True}))
"""


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def git(*arguments):
    result = subprocess.run(["git", *arguments], cwd=ROOT, capture_output=True, check=False)
    if result.returncode:
        raise ValueError("SourceGapReplayRejected")
    return result.stdout


def files(directory):
    return {
        path.relative_to(directory).as_posix(): digest(path.read_bytes())
        for path in directory.rglob("*")
        if path.is_file() and path.suffix == ".py"
    }


def replay(output):
    protocol_raw = (ROOT / PROTOCOL).read_bytes()
    protocol = json.loads(protocol_raw)
    test, observed = protocol["controls_path"], protocol["observed_receipt_path"]
    test_raw = (ROOT / test).read_bytes()
    frozen = {
        PROTOCOL: digest(protocol_raw),
        test: digest(test_raw),
        observed: digest((ROOT / observed).read_bytes()),
    }
    if (
        protocol["protocol_id"] != "source-gap-handoff-replay-v1"
        or protocol["controls"] != 17
        or frozen[test] != protocol["controls_sha256"]
        or frozen[observed] != protocol["observed_receipt_sha256"]
    ):
        raise ValueError("SourceGapReplayRejected")
    output = output.resolve()
    if (
        output.is_relative_to(ROOT)
        and subprocess.run(
            ["git", "check-ignore", "--quiet", "--", str(output)], cwd=ROOT
        ).returncode
    ):
        raise ValueError("SourceGapReplayRejected")
    output.mkdir(parents=True, exist_ok=False)
    arms, inventory = {}, None
    with tempfile.TemporaryDirectory(prefix="source-gap-archived-replay-") as temporary:
        for label, ref, grounding_sha, expected in (
            (
                "baseline",
                protocol["baseline_commit"],
                protocol["baseline_grounding_sha256"],
                {"passed": 8, "failed": 9, "error": 0, "skipped": 0},
            ),
            (
                "candidate",
                CANDIDATE,
                CANDIDATE_GROUNDING,
                {"passed": 17, "failed": 0, "error": 0, "skipped": 0},
            ),
        ):
            commit = git("rev-parse", ref).decode().strip()
            directory = Path(temporary) / label
            directory.mkdir()
            archived = ("src/agent_app", "pyproject.toml", observed)
            with tarfile.open(fileobj=io.BytesIO(git("archive", commit, *archived))) as archive:
                archive.extractall(directory, filter="data")
            before = files(directory)
            if (
                before[GROUNDING] != grounding_sha
                or digest((directory / observed).read_bytes()) != frozen[observed]
            ):
                raise ValueError("SourceGapReplayRejected")
            for name, value in before.items():
                if digest(git("show", f"{commit}:{name}")) != value:
                    raise ValueError("SourceGapReplayRejected")
            (directory / test).parent.mkdir(parents=True, exist_ok=True)
            (directory / test).write_bytes(test_raw)
            xml = directory / "results.xml"
            env = {
                name: os.environ[name]
                for name in ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP")
                if name in os.environ
            }
            env.update(
                PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
                PYTHONUTF8="1",
                PYTHONIOENCODING="utf-8",
                METIS_LIVE_ENABLED="false",
            )
            child = subprocess.run(
                [sys.executable, "-I", "-B", "-c", WORKER, str(directory), test, str(xml)],
                cwd=directory,
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if child.returncode:
                raise ValueError("SourceGapReplayRejected")
            result = json.loads(child.stdout)
            cases = ET.parse(xml).getroot().findall(".//testcase")
            identities = [(case.get("classname"), case.get("name")) for case in cases]
            counts = {"passed": 0, "failed": 0, "error": 0, "skipped": 0}
            for case in cases:
                status = next(
                    (
                        key
                        for key, tag in (
                            ("error", "error"),
                            ("failed", "failure"),
                            ("skipped", "skipped"),
                        )
                        if case.find(tag) is not None
                    ),
                    "passed",
                )
                counts[status] += 1
            if (
                len(cases) != 17
                or len(set(identities)) != 17
                or counts != expected
                or result
                != {
                    "pytest_exit_code": int(bool(expected["failed"])),
                    "imports_bound_to_snapshot": True,
                    "network_disabled": True,
                }
                or inventory is not None
                and inventory != identities
            ):
                raise ValueError("SourceGapReplayRejected")
            inventory = identities
            if (
                {name: digest((directory / name).read_bytes()) for name in before} != before
                or digest((directory / test).read_bytes()) != frozen[test]
                or digest((directory / observed).read_bytes()) != frozen[observed]
            ):
                raise ValueError("SourceGapReplayRejected")
            arms[label] = {
                "commit": commit,
                "counts": counts,
                "pytest_exit_code": result["pytest_exit_code"],
                "grounding_sha256": grounding_sha,
                "archived_source_sha256": before,
                "raw_pytest_xml_sha256": digest(xml.read_bytes()),
                "source_matches_git_commit": True,
                "frozen_controls_sha256": frozen[test],
                "imports_bound_to_snapshot": True,
                "network_disabled": True,
            }
    if any(digest((ROOT / name).read_bytes()) != value for name, value in frozen.items()):
        raise ValueError("SourceGapReplayRejected")
    receipt = {
        "protocol_id": protocol["protocol_id"],
        "accepted": True,
        "input_sha256": frozen,
        "runner_sha256": digest(Path(__file__).read_bytes()),
        "source_commit": git("rev-parse", "HEAD").decode().strip(),
        "source_clean": not bool(git("status", "--porcelain").strip()),
        "arms": arms,
        "registered_controls": 17,
        "real_model_requests": 0,
        "paid_api_cost_usd": "0",
        "quality_claim": False,
        "scope": "Same already observed V3 plans and frozen authored controls; deterministic renderer replay only.",
    }
    with (output / "receipt.json").open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    try:
        receipt = replay(parser.parse_args().output_dir)
    except Exception:
        print(json.dumps({"accepted": False, "diagnostic": "SourceGapReplayRejected"}))
        return 1
    print(
        json.dumps(
            {
                "accepted": True,
                "registered_controls": 17,
                "counts": {key: arm["counts"] for key, arm in receipt["arms"].items()},
                "real_model_requests": 0,
                "quality_claim": False,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
