"""Exercise Git checkout itself against a real byte-pinned seed package file."""

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "streamlit-data-for-dev-test"
PACKAGED_FILE = "sources/docs_scope_candidates.jsonl"
TRACKED_FILE = "streamlit-data-for-dev-test/" + PACKAGED_FILE


def _git(repository: Path, *arguments: str, autocrlf: bool = False) -> bytes:
    # An isolated repository/config prevents the developer's Git settings,
    # attributes file or enclosing worktree from changing this regression.
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment.update(
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_SYSTEM=os.devnull,
        GIT_CONFIG_GLOBAL=os.devnull,
    )
    result = subprocess.run(
        [
            "git",
            "-c",
            "core.autocrlf=" + str(autocrlf).lower(),
            "-c",
            "core.eol=lf",
            "-c",
            "core.safecrlf=false",
            "-c",
            "core.attributesFile=" + os.devnull,
            *arguments,
        ],
        cwd=repository,
        env=environment,
        check=True,
        capture_output=True,
    )
    return result.stdout


def _checkout(tmp_path: Path, *, with_attributes: bool, autocrlf: bool) -> tuple[bytes, bytes]:
    original = (SEED / PACKAGED_FILE).read_bytes()
    _git(tmp_path, "init", "--quiet")
    file = tmp_path / TRACKED_FILE
    file.parent.mkdir(parents=True)
    file.write_bytes(original)
    if with_attributes:
        (tmp_path / ".gitattributes").write_bytes((ROOT / ".gitattributes").read_bytes())
        _git(tmp_path, "add", "--", ".gitattributes", TRACKED_FILE)
        assert (
            _git(tmp_path, "check-attr", "text", "--", TRACKED_FILE)
            .strip()
            .endswith(b": text: unset")
        )
        # The byte policy belongs to the seed package, not to application code.
        assert (
            _git(tmp_path, "check-attr", "text", "--", "src/agent_app/retrieval/adapter.py")
            .strip()
            .endswith(b": text: unspecified")
        )
    else:
        _git(tmp_path, "add", "--", TRACKED_FILE)
    assert _git(tmp_path, "show", ":" + TRACKED_FILE) == original
    file.unlink()
    _git(tmp_path, "checkout-index", "--force", "--", TRACKED_FILE, autocrlf=autocrlf)
    return original, file.read_bytes()


@pytest.mark.parametrize("autocrlf", [False, True])
def test_packaged_seed_checkout_keeps_exact_manifest_bytes(tmp_path, autocrlf):
    original, checked_out = _checkout(tmp_path, with_attributes=True, autocrlf=autocrlf)
    manifest = json.loads((SEED / "manifest.json").read_bytes())
    pin = next(item for item in manifest["files"] if item["path"] == PACKAGED_FILE)
    assert len(original) == pin["bytes"]
    assert hashlib.sha256(original).hexdigest() == pin["sha256"]
    assert checked_out == original
    assert len(checked_out) == pin["bytes"]
    assert hashlib.sha256(checked_out).hexdigest() == pin["sha256"]


def test_without_byte_policy_autocrlf_reproduces_seed_manifest_breakage(tmp_path):
    original, checked_out = _checkout(tmp_path, with_attributes=False, autocrlf=True)
    assert b"\r\n" not in original
    assert original.count(b"\n") == 56
    assert checked_out == original.replace(b"\n", b"\r\n")
    assert len(checked_out) == len(original) + 56
    assert hashlib.sha256(checked_out).hexdigest() != hashlib.sha256(original).hexdigest()
