"""Temporary guard registries work without any ignored native runtime storage."""

import importlib
import json
import shutil
from pathlib import Path

import pytest
from registered_native_inputs import ENUM_FOLDER, registered_method_inputs, sha
from test_budget_quarantine_scope import multiple_holds as multiple_holds

from agent_app.testing.http_pilot_runtime import offline_network

ROOT = Path(__file__).resolve().parents[1]
STUDIES = ("enum_evidence", "complementary", "source_order")


@pytest.mark.parametrize("study", STUDIES)
def test_missing_native_runtime_is_registered_then_mutation_rejected(
    tmp_path, monkeypatch, multiple_holds, study
):
    tests = importlib.import_module(f"test_{study}_model_cli")
    module = tests._module(monkeypatch)
    original_protocol_sha = module.PROTOCOL_SHA256
    assert sha((ROOT / module.FOLDER / "protocol-v1.json").read_bytes()) == original_protocol_sha
    original_validate = module.validate_registered_inputs
    original_sha = module.sha
    original_read = Path.read_bytes

    def no_original_runtime_reads(path):
        if path.is_relative_to(ROOT / "runtime"):
            pytest.fail("The test helper read ignored original native storage")
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", no_original_runtime_reads)
    source = tmp_path / "tracked-only-checkout"
    registered_method_inputs(module, ROOT, source, monkeypatch, multiple_holds)
    shutil.rmtree(source / "runtime")
    assert not (source / "runtime").exists()
    target = tmp_path / "registered"
    _, _, ledger_path, _ = registered_method_inputs(
        module, source, target, monkeypatch, multiple_holds
    )
    assert not (source / "runtime").exists()
    assert module.validate_registered_inputs is original_validate
    assert module.sha is original_sha
    before_ledger = ledger_path.read_bytes()
    with offline_network():
        method = module.build_method(target, ledger_path)
    assert ledger_path.read_bytes() == before_ledger
    native = [name for name in method["protected_files"] if name.startswith("runtime/")]
    assert len(native) == 6
    for name in native:
        raw = (target / name).read_bytes()
        assert raw.startswith(b"SYNTHETIC guard-registry test input")
        assert sha(raw) == method["protected_files"][name]
    # The protected schema/criteria remain historical; only its temporary byte
    # registry and necessary binding digests describe the synthetic test set.
    source_protected = json.loads((source / ENUM_FOLDER / "protected-inputs-v1.json").read_bytes())
    protected = json.loads((target / ENUM_FOLDER / "protected-inputs-v1.json").read_bytes())
    assert {k: v for k, v in protected.items() if k != "files"} == {
        k: v for k, v in source_protected.items() if k != "files"
    }
    target_protocol = json.loads((target / module.FOLDER / "protocol-v1.json").read_bytes())
    registered_protocol = json.loads((ROOT / module.FOLDER / "protocol-v1.json").read_bytes())
    if "parent" in registered_protocol:
        registered_protocol["parent"]["protected_inputs_sha256"] = target_protocol["parent"][
            "protected_inputs_sha256"
        ]
    assert target_protocol == registered_protocol
    native_path = target / native[0]
    native_path.write_bytes(native_path.read_bytes() + b"changed after registration")
    with offline_network(), pytest.raises(ValueError, match="RegistrationRejected$"):
        module.build_method(target, ledger_path)
    assert ledger_path.read_bytes() == before_ledger


@pytest.mark.parametrize("study", STUDIES)
def test_original_protocol_pin_is_checked_before_temporary_registration(
    tmp_path, monkeypatch, multiple_holds, study
):
    tests = importlib.import_module(f"test_{study}_model_cli")
    module = tests._module(monkeypatch)
    monkeypatch.setattr(module, "PROTOCOL_SHA256", "0" * 64)
    target = tmp_path / "not-registered"
    with pytest.raises(AssertionError):
        registered_method_inputs(module, ROOT, target, monkeypatch, multiple_holds)
    assert not target.exists()
