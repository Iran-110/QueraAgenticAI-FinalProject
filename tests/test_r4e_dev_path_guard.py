"""R4e fixture custody is checked before payload reads; all targets are synthetic."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NATIVE = "data/evaluation/split-e1-v1/native"


@pytest.fixture
def benchmark(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "r4e_dev_path_guard_subject", ROOT / "scripts/r4e_dev_availability.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "REGISTRATION", tmp_path / "registration.json")
    return module


def register(module, path, raw=b"synthetic forbidden fixture"):
    module.REGISTRATION.write_text(
        json.dumps({"fixtures": [{"path": path, "sha256": hashlib.sha256(raw).hexdigest()}]}),
        encoding="utf-8",
    )


def spy_reads(monkeypatch):
    reads = []
    original = Path.read_bytes

    def captured(path):
        reads.append(path)
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", captured)
    return reads


@pytest.mark.parametrize(
    "entry",
    [
        f"{NATIVE}/test/blocked.json",
        f"{NATIVE}/native-test-gold-review-v1.json",
        "data/evaluation/split-e1-v1/test/blocked.json",
        f"{NATIVE}/dev/../test/blocked.json",
        f"{NATIVE}/dev-v2/../../test/blocked.json",
        f"{NATIVE}/dev-extra/blocked.json",
        f"{NATIVE}/dev/blocked.txt",
        f"{NATIVE}/dev/blocked.JSON",
        f"{NATIVE}/dev/missing.json",
        f"{NATIVE}/dev\\blocked.json",
        f"{NATIVE}/dev/native-test-exposure-decision-v1.json",
        f"{NATIVE}/dev/native-test-gold-review-v1.json",
        f"{NATIVE}/dev-v2/test-card-review-v1.json",
        f"{NATIVE}/dev/evidence-test-v1.json",
        f"{NATIVE}/dev-v2/evidence-test.json",
        f"{NATIVE}/dev/NATIVE-TEST-GOLD-REVIEW-V1.json",
        f"{NATIVE}/dev/Evidence-Test-v2.json",
        "../outside.json",
        "",
        None,
        7,
        [],
        {},
    ],
    ids=[
        "native-test",
        "gold-review",
        "fixed-test",
        "traversal-from-dev",
        "traversal-from-dev-v2",
        "prefix-lookalike",
        "wrong-extension",
        "uppercase-extension",
        "missing",
        "backslash",
        "exposure-decision-basename",
        "native-gold-basename",
        "test-review-basename",
        "evidence-test-prefix",
        "evidence-test-basename",
        "casefold-protected-basename",
        "casefold-protected-prefix",
        "root-traversal",
        "empty",
        "null",
        "integer",
        "list",
        "object",
    ],
)
def test_rejected_entry_is_not_read(benchmark, monkeypatch, entry):
    # Forbidden targets stay nonexistent: the read spy proves rejection first.
    register(benchmark, entry)
    reads = spy_reads(monkeypatch)
    original_resolve = Path.resolve

    def reject_protected_resolution(path, *args, **kwargs):
        name = path.name.casefold()
        if name in {
            "native-test-exposure-decision-v1.json",
            "native-test-gold-review-v1.json",
            "test-card-review-v1.json",
        } or name.startswith("evidence-test"):
            pytest.fail("A protected basename must be rejected before filesystem resolution.")
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", reject_protected_resolution)
    with pytest.raises(SystemExit, match="^DevFixtureMismatch$"):
        list(benchmark.dev_turns())
    assert reads == [benchmark.REGISTRATION]


def test_absolute_entry_is_rejected_before_read(benchmark, tmp_path, monkeypatch):
    target = tmp_path / NATIVE / "dev" / "case.json"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"synthetic forbidden fixture")
    register(benchmark, str(target))
    reads = spy_reads(monkeypatch)
    with pytest.raises(SystemExit, match="^DevFixtureMismatch$"):
        list(benchmark.dev_turns())
    assert reads == [benchmark.REGISTRATION]


@pytest.mark.parametrize("directory_link", [False, True], ids=["file", "directory"])
def test_symlink_escape_target_is_not_read(benchmark, tmp_path, monkeypatch, directory_link):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "blocked.json").write_bytes(b"synthetic forbidden fixture")
    dev = tmp_path / NATIVE / "dev"
    dev.mkdir(parents=True)
    try:
        if directory_link:
            (dev / "link").symlink_to(outside, target_is_directory=True)
            entry = f"{NATIVE}/dev/link/blocked.json"
        else:
            (dev / "blocked.json").symlink_to(outside / "blocked.json")
            entry = f"{NATIVE}/dev/blocked.json"
    except (NotImplementedError, OSError):
        pytest.skip("This host cannot create symbolic links for the custody test.")
    register(benchmark, entry)
    reads = spy_reads(monkeypatch)
    with pytest.raises(SystemExit, match="^DevFixtureMismatch$"):
        list(benchmark.dev_turns())
    assert reads == [benchmark.REGISTRATION]


def test_json_directory_is_not_a_fixture(benchmark, tmp_path, monkeypatch):
    entry = f"{NATIVE}/dev/directory.json"
    (tmp_path / entry).mkdir(parents=True)
    register(benchmark, entry)
    reads = spy_reads(monkeypatch)
    with pytest.raises(SystemExit, match="^DevFixtureMismatch$"):
        list(benchmark.dev_turns())
    assert reads == [benchmark.REGISTRATION]


def fixture_bytes():
    return json.dumps(
        {
            "case": {"split": "dev", "case_id": "synthetic-dev"},
            "turns": [
                {
                    "id": "first",
                    "visible": {
                        "message": "Synthetic widget report.",
                        "reported_facts": [{"name": "streamlit_version", "value": "1.50.0"}],
                    },
                    "gold": {
                        "native_passages": {
                            "answer_required": {"requirements": [{"requirement_id": "initial"}]}
                        }
                    },
                },
                {
                    "id": "reply",
                    "visible": {
                        "message": "1.49.0",
                        "reply_to_approved_question": "synthetic-question",
                    },
                    "gold": {
                        "native_passages": {
                            "answer_required": {"requirements": [{"requirement_id": "reply"}]}
                        }
                    },
                },
            ],
        },
        ensure_ascii=False,
    ).encode("utf-8")


@pytest.mark.parametrize("directory", ["dev", "dev-v2"])
def test_regular_dev_fixtures_keep_the_existing_turn_projection(
    benchmark, tmp_path, monkeypatch, directory
):
    entry = f"{NATIVE}/{directory}/synthetic.json"
    raw = fixture_bytes()
    path = tmp_path / entry
    path.parent.mkdir(parents=True)
    path.write_bytes(raw)
    register(benchmark, entry, raw)
    reads = spy_reads(monkeypatch)
    rows = list(benchmark.dev_turns())
    assert reads == [benchmark.REGISTRATION, path]
    assert [(case_id, turn, message, required) for case_id, turn, _, message, required in rows] == [
        (
            "synthetic-dev",
            "first",
            "Synthetic widget report.",
            [{"requirement_id": "initial"}],
        ),
        (
            "synthetic-dev",
            "reply",
            "Synthetic widget report.",
            [{"requirement_id": "reply"}],
        ),
    ]
    assert [row[2].facts[0].value for row in rows] == ["1.50.0", "1.49.0"]
    assert [row[2].facts[0].source_ref for row in rows] == ["user:first", "user:reply"]


def test_valid_path_still_requires_the_registered_hash(benchmark, tmp_path, monkeypatch):
    entry = f"{NATIVE}/dev/synthetic.json"
    path = tmp_path / entry
    path.parent.mkdir(parents=True)
    path.write_bytes(fixture_bytes())
    register(benchmark, entry, b"different bytes")
    reads = spy_reads(monkeypatch)
    with pytest.raises(SystemExit, match="^DevFixtureMismatch$"):
        list(benchmark.dev_turns())
    assert reads == [benchmark.REGISTRATION, path]
