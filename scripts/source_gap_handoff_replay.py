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
PROTOCOL = "experiments/dev_three_baseline/source-gap-handoff-protocol-v2.json"
LEGACY_CONTROLS = "experiments/dev_three_baseline/source-gap-handoff-controls-v1.py"
LEGACY_CANDIDATE = "b5a6d922d6ff67ef1af64220044868629acc103c"
LEGACY_GROUNDING = "5ae551979f5e99f5eb055bd91842c55516d3364c037b5076ec39d1420b387287"
REGISTRATIONS = {
    "source-gap-handoff-replay-v1": (
        17,
        "7da3cbcac5018c12edd4f6f24b30fe790cc85d91405d3d6998173c6c87e7ba83",
        8,
        9,
    ),
    "source-gap-handoff-replay-v2": (
        41,
        "812f5d4981fc9fe5bdcd081adce1fc444ba3eafabf287f458096fbc7e87ff6ad",
        20,
        21,
    ),
}
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


def replay(output, protocol_path=PROTOCOL, candidate=None, candidate_grounding_sha256=None):
    protocol_file = (ROOT / protocol_path).resolve()
    if not protocol_file.is_relative_to(ROOT / "experiments/dev_three_baseline"):
        raise ValueError("SourceGapReplayRejected")
    protocol_name = protocol_file.relative_to(ROOT).as_posix()
    protocol_raw = protocol_file.read_bytes()
    protocol = json.loads(protocol_raw)
    test, observed = protocol["controls_path"], protocol["observed_receipt_path"]
    version = protocol["protocol_id"]
    registered_count, registered_sha, passed, failed = REGISTRATIONS[version]
    legacy = version == "source-gap-handoff-replay-v1"
    test_source = LEGACY_CONTROLS if legacy else test
    test_raw = (ROOT / test_source).read_bytes()
    current_source = files(ROOT / "src/agent_app")
    runner_sha = digest(Path(__file__).read_bytes())
    frozen = {
        protocol_name: digest(protocol_raw),
        test_source: digest(test_raw),
        observed: digest((ROOT / observed).read_bytes()),
    }
    if (
        protocol["controls"] != registered_count
        or protocol["controls_sha256"] != registered_sha
        or frozen[test_source] != registered_sha
        or protocol["baseline_counts"] != dict(passed=passed, failed=failed, error=0, skipped=0)
        or frozen[observed] != protocol["observed_receipt_sha256"]
        or frozen[observed] != "6f2cb48dc7a78f05870e63316589d575ed00a431be16f5d81344922d3099b03e"
        or protocol["real_model_requests"] != 0
        or protocol["quality_claim"] is not False
    ):
        raise ValueError("SourceGapReplayRejected")
    if legacy:
        if candidate not in (None, LEGACY_CANDIDATE):
            raise ValueError("SourceGapReplayRejected")
        candidate, candidate_grounding = LEGACY_CANDIDATE, LEGACY_GROUNDING
    else:
        if (
            candidate is None
            or len(candidate) != 40
            or any(c not in "0123456789abcdef" for c in candidate)
        ):
            raise ValueError("SourceGapReplayRejected")
        candidate = git("rev-parse", candidate + "^{commit}").decode().strip()
        candidate_grounding = digest(git("show", f"{candidate}:{GROUNDING}"))
        if (
            candidate_grounding != digest((ROOT / GROUNDING).read_bytes())
            or frozen[protocol_name]
            != "29c5bf4bd506dbd4f5644b870130fd563e0993f2d7969426bcbf097becb54928"
        ):
            raise ValueError("SourceGapReplayRejected")
        for path_key, sha_key in (
            ("original_controls_path", "original_controls_sha256"),
            ("configuration_controls_path", "configuration_controls_sha256"),
        ):
            name = protocol[path_key]
            path = (ROOT / name).resolve()
            if not path.is_relative_to(ROOT) or digest(path.read_bytes()) != protocol[sha_key]:
                raise ValueError("SourceGapReplayRejected")
            frozen[name] = protocol[sha_key]
    if candidate_grounding_sha256 is not None and candidate_grounding_sha256 != candidate_grounding:
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
    arms, inventory, candidate_matches = {}, None, False
    with tempfile.TemporaryDirectory(prefix="source-gap-archived-replay-") as temporary:
        for label, ref, grounding_sha, expected in (
            (
                "baseline",
                protocol["baseline_commit"],
                protocol["baseline_grounding_sha256"],
                {"passed": passed, "failed": failed, "error": 0, "skipped": 0},
            ),
            (
                "candidate",
                candidate,
                candidate_grounding,
                {"passed": registered_count, "failed": 0, "error": 0, "skipped": 0},
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
            if label == "candidate":
                candidate_matches = files(directory / "src/agent_app") == current_source
                if not legacy and not candidate_matches:
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
                len(cases) != registered_count
                or len(set(identities)) != registered_count
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
                or digest((directory / test).read_bytes()) != frozen[test_source]
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
                "frozen_controls_sha256": frozen[test_source],
                "imports_bound_to_snapshot": True,
                "network_disabled": True,
            }
    if (
        any(digest((ROOT / name).read_bytes()) != value for name, value in frozen.items())
        or files(ROOT / "src/agent_app") != current_source
        or digest(Path(__file__).read_bytes()) != runner_sha
    ):
        raise ValueError("SourceGapReplayRejected")
    receipt = {
        "protocol_id": protocol["protocol_id"],
        "accepted": True,
        "input_sha256": frozen,
        "runner_sha256": runner_sha,
        "source_commit": git("rev-parse", "HEAD").decode().strip(),
        "source_clean": not bool(git("status", "--porcelain").strip()),
        "arms": arms,
        "registered_controls": registered_count,
        "candidate_matches_working_source": candidate_matches,
        "controls_copy_target": test,
        "controls_read_source": test_source,
        "configuration_controls_executed": False,
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
    parser.add_argument("--protocol", type=Path, default=Path(PROTOCOL))
    parser.add_argument(
        "--candidate", help="Exact 40-character V2 candidate commit SHA; required for V2."
    )
    parser.add_argument(
        "--candidate-grounding-sha256",
        help="Optional independently verified candidate grounding blob SHA256.",
    )
    try:
        options = parser.parse_args()
        receipt = replay(
            options.output_dir,
            options.protocol,
            options.candidate,
            options.candidate_grounding_sha256,
        )
    except Exception:
        print(json.dumps({"accepted": False, "diagnostic": "SourceGapReplayRejected"}))
        return 1
    print(
        json.dumps(
            {
                "accepted": True,
                "registered_controls": receipt["registered_controls"],
                "counts": {key: arm["counts"] for key, arm in receipt["arms"].items()},
                "real_model_requests": 0,
                "quality_claim": False,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
