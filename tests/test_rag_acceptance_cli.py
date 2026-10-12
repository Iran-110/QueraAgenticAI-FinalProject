"""Offline CLI boundaries and transparent binding; no actual RAG backend."""

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/rag_acceptance.py"
PRIVATE = "PRIVATE_CLI_BINDING_DIAGNOSTIC"


@pytest.fixture
def cli():
    specification = importlib.util.spec_from_file_location("rag_acceptance_cli_test_target", SCRIPT)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def read_receipt(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_default_cli_runs_offline_fixture_and_reports_release_fingerprints(tmp_path):
    output = tmp_path / "receipt.json"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--output", str(output)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    summary = json.loads(result.stdout)
    receipt = read_receipt(output)
    assert result.stderr == ""
    assert summary["accepted"] is True and summary["quality_claim"] is False
    assert receipt["mode"] == "reference_fixture_adapter"
    assert receipt["actual_rag_accepted"] is False
    assert receipt["production_index_or_embedding_tested"] is False
    assert receipt["real_model_tested"] is False
    assert receipt["pilot"]["total_retrieval_calls"] == 5
    assert len(receipt["pilot"]["turns"]) == 4
    assert len(receipt["release_before"]["git_commit"]) == 40
    assert type(receipt["release_before"]["git_dirty"]) is bool
    assert receipt["source_unchanged_during_run"] is True
    assert (
        receipt["release_before"]["source_sha256"]["scripts/rag_acceptance.py"]
        == hashlib.sha256(SCRIPT.read_bytes()).hexdigest()
    )


def test_default_path_does_not_import_chroma_or_candidate_module(cli, tmp_path, capsys):
    before = set(sys.modules)
    assert cli.main(["--output", str(tmp_path / "receipt.json")]) == 0
    imported = set(sys.modules) - before
    assert not any(
        name == "chromadb" or name.startswith("chromadb.") or name.startswith("agent_app.retrieval")
        for name in imported
    )
    assert json.loads(capsys.readouterr().out)["mode"] == "reference_fixture_adapter"


@pytest.mark.parametrize(
    ("content", "code"),
    [
        (None, "CandidateMissing"),
        (" \n\t", "CandidateEmpty"),
        ("class ChromaRetrieverAdapter:\n    pass\n", "CandidateInterfaceMissing"),
        ("class ChromaRetrieverAdapter(:", "CandidateSyntaxInvalid"),
    ],
)
def test_candidate_preflight_failure_stops_before_factory_or_runner(
    cli, tmp_path, capsys, monkeypatch, content, code
):
    candidate = tmp_path / "candidate.py"
    if content is not None:
        candidate.write_text(content, encoding="utf-8")
    calls = []

    def forbidden_factory(*args):
        calls.append(args)
        raise AssertionError("PreflightMustStopBeforeFactory")

    monkeypatch.setattr(cli, "_resolve_factory", forbidden_factory)
    output = tmp_path / "receipt.json"
    assert cli.main(["--output", str(output), "--check-candidate", str(candidate)]) == 1
    summary = json.loads(capsys.readouterr().out)
    assert calls == []
    assert summary["error_code"] == code
    assert read_receipt(output)["error_code"] == code
    assert summary["mode"] == "not_run"


def test_candidate_preflight_is_static_and_does_not_claim_actual_rag(cli, tmp_path, capsys):
    candidate, marker = tmp_path / "candidate.py", tmp_path / "executed.txt"
    content = (
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('unwanted')\n"
        f"raise RuntimeError({PRIVATE!r})\n"
        "class ChromaRetrieverAdapter:\n"
        "    def search(self, request):\n"
        "        raise AssertionError('MustNotExecute')\n"
    )
    candidate.write_text(content, encoding="utf-8")
    output = tmp_path / "receipt.json"
    assert cli.main(["--output", str(output), "--check-candidate", str(candidate)]) == 0
    receipt = read_receipt(output)
    assert not marker.exists()
    assert (
        receipt["candidate_preflight"]["candidate_source_sha256"]
        == hashlib.sha256(candidate.read_bytes()).hexdigest()
    )
    assert receipt["candidate_preflight"]["mode"] == "static_ast_only"
    assert receipt["candidate_preflight"]["runtime_readiness_proved"] is False
    assert receipt["actual_rag_accepted"] is False
    assert receipt["mode"] == "reference_fixture_adapter"
    assert PRIVATE not in output.read_text() + capsys.readouterr().out


def test_existing_output_is_preserved_before_even_startup_or_factory(
    cli, tmp_path, capsys, monkeypatch
):
    output = tmp_path / "receipt.json"
    output.write_bytes(b"existing receipt must survive\n")
    calls = []

    def forbidden(*args):
        calls.append(args)
        raise AssertionError("ExistingReceiptMustNotExecute")

    monkeypatch.setattr(cli, "_release_identity", forbidden)
    monkeypatch.setattr(cli, "_resolve_factory", forbidden)
    assert cli.main(["--output", str(output), "--factory", "unreviewed_binding:factory"]) == 1
    assert calls == []
    assert output.read_bytes() == b"existing receipt must survive\n"
    summary = json.loads(capsys.readouterr().out)
    assert summary["error_code"] == "ReceiptAlreadyExists" and summary["mode"] == "not_run"


@pytest.mark.parametrize(
    ("factory", "code"),
    [
        ("not a valid factory", "AdapterFactoryInvalid"),
        ("no_such_offline_cli_binding:factory", "AdapterFactoryUnavailable"),
    ],
)
def test_invalid_factory_produces_safe_failed_receipt(cli, tmp_path, capsys, factory, code):
    output = tmp_path / "receipt.json"
    assert cli.main(["--output", str(output), "--factory", factory]) == 1
    receipt = read_receipt(output)
    summary = json.loads(capsys.readouterr().out)
    assert receipt["accepted"] is False and receipt["error_code"] == code
    assert summary["error_code"] == code
    assert factory not in output.read_text()


def test_factory_import_fault_does_not_export_prints_or_exception(
    cli, tmp_path, capsys, monkeypatch
):
    module = tmp_path / "cli_private_import_failure.py"
    module.write_text(
        f"import sys\nprint({PRIVATE!r})\nprint({PRIVATE!r}, file=sys.stderr)\nraise RuntimeError({PRIVATE!r})\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    output = tmp_path / "receipt.json"
    assert (
        cli.main(["--output", str(output), "--factory", "cli_private_import_failure:factory"]) == 1
    )
    streams = capsys.readouterr()
    receipt = read_receipt(output)
    assert receipt["error_code"] == "AdapterFactoryUnavailable"
    assert receipt["adapter_stdout_captured"] is receipt["adapter_stderr_captured"] is True
    assert PRIVATE not in output.read_text() + streams.out + streams.err


def test_noncallable_factory_is_rejected_before_acceptance(cli, tmp_path, capsys, monkeypatch):
    (tmp_path / "cli_noncallable_factory.py").write_text("factory = 7\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    output = tmp_path / "receipt.json"
    assert cli.main(["--output", str(output), "--factory", "cli_noncallable_factory:factory"]) == 1
    assert read_receipt(output)["error_code"] == "AdapterFactoryInvalid"
    assert json.loads(capsys.readouterr().out)["accepted"] is False


def test_reviewed_offline_binding_retains_its_own_mapping_and_identity(
    cli, tmp_path, capsys, monkeypatch
):
    module = tmp_path / "cli_reviewed_binding.py"
    module.write_text(
        "from agent_app.contracts import EvidenceBundle, EvidenceHit\n"
        "class OfflineReviewedMapping:\n"
        "    def __init__(self, probe):\n"
        "        self.probe = probe\n"
        "    def search(self, request):\n"
        f"        print({PRIVATE!r})\n"
        "        if request.snapshot_id != self.probe.snapshot_id:\n"
        "            raise ValueError('SnapshotMismatch')\n"
        "        hits = {}\n"
        "        for query in request.queries:\n"
        "            for row in self.probe.backend.search(query, top_k=request.top_k, filters=request.filters):\n"
        "                hit = EvidenceHit.model_validate(row)\n"
        "                hits.setdefault(hit.chunk_id, hit)\n"
        "        return EvidenceBundle(snapshot_id=self.probe.snapshot_id, hits=tuple(hits.values())[:request.top_k], queries_used=request.queries)\n"
        "def factory(probe):\n"
        "    return OfflineReviewedMapping(probe)\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    output = tmp_path / "receipt.json"
    assert cli.main(["--output", str(output), "--factory", "cli_reviewed_binding:factory"]) == 0
    receipt = read_receipt(output)
    summary = json.loads(capsys.readouterr().out)
    assert receipt["mode"] == "candidate_adapter_with_fixture_backend"
    assert receipt["factory"]["module"] == "cli_reviewed_binding"
    assert all(
        item["module"] == "cli_reviewed_binding" and item["name"] == "OfflineReviewedMapping"
        for item in receipt["delegate_sources"]
    )
    assert receipt["factory"]["source_sha256"] == hashlib.sha256(module.read_bytes()).hexdigest()
    assert receipt["adapter_stdout_captured"] is True
    assert receipt["pilot"]["adapter_constructions"] == 4
    assert receipt["actual_rag_accepted"] is receipt["real_model_tested"] is False
    assert summary["accepted"] is True
    assert PRIVATE not in output.read_text() + json.dumps(summary)


def test_failed_adapter_exits_one_with_allowlisted_summary(cli, tmp_path, capsys, monkeypatch):
    (tmp_path / "cli_empty_port.py").write_text(
        "from agent_app.contracts import EvidenceBundle\n"
        "class EmptyPort:\n"
        "    def __init__(self, probe):\n"
        "        self.snapshot_id = probe.snapshot_id\n"
        "    def search(self, request):\n"
        "        return EvidenceBundle(snapshot_id=self.snapshot_id)\n"
        "def factory(probe):\n"
        "    return EmptyPort(probe)\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    output = tmp_path / "receipt.json"
    assert cli.main(["--output", str(output), "--factory", "cli_empty_port:factory"]) == 1
    receipt = read_receipt(output)
    summary = json.loads(capsys.readouterr().out)
    assert receipt["accepted"] is False and receipt["checks_passed"] < receipt["checks_total"]
    assert receipt["error_code"] == summary["error_code"] == "AdapterAcceptanceFailed"
    assert set(summary) == {
        "protocol",
        "accepted",
        "mode",
        "checks_passed",
        "checks_total",
        "error_code",
        "quality_claim",
    }
