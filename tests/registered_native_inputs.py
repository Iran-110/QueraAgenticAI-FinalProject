"""Hermetic byte-guard inputs, never a native-index or retrieval-quality fixture.

Historical production registries remain immutable. Disposable test registries bind
explicit synthetic bytes under runtime/ instead of reading ignored local Chroma
files. The real SHA validation and drift rejection code still run unchanged.
"""

import hashlib
import json
from pathlib import Path

ENUM_FOLDER = Path("experiments/core_enum_evidence_v1")
JSON_FOLDER = Path("experiments/core_json_readability_v1")
COMPLEMENTARY_FOLDER = Path("experiments/core_complementary_sources_v1")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _json(path):
    return json.loads(path.read_bytes())


def _write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def synthetic_native_bytes(relative):
    """Deliberately invalid native storage; these tests exercise byte guards only."""
    return (
        b"SYNTHETIC guard-registry test input v1; NOT Chroma or a retrieval index.\n"
        + relative.as_posix().encode("utf-8")
        + b"\n"
    )


def registered_method_inputs(module, source_root, target_root, monkeypatch, multiple_holds):
    """Copy tracked inputs and prospectively register a wholly temporary byte set.

    Only runtime-file hashes in the temporary protected artifact and the resulting
    temporary protocol/preparation/replay binding hashes change. The original
    production protocol is independently checked before any module constant is
    patched; no digest function or production validation function is patched.
    """
    ledger, ledger_path, _ = multiple_holds
    folder = module.FOLDER
    original_protocol = (source_root / folder / "protocol-v1.json").read_bytes()
    assert sha(original_protocol) == module.PROTOCOL_SHA256
    protected_relative = ENUM_FOLDER / "protected-inputs-v1.json"
    protected = _json(source_root / protected_relative)
    paths = {
        *(
            p.relative_to(source_root)
            for p in (source_root / "data/evaluation/dev-three-v1").rglob("*.json")
        ),
        *(Path(name) for name in protected["files"]),
        *(
            ENUM_FOLDER / name
            for name in (
                "protocol-v1.json",
                "capacity-amendment-v1.json",
                "offline-boundary-initial-v1.json",
                "offline-boundary-review-v1.json",
                "source-packet-v1.json",
                "protected-inputs-v1.json",
                "semantic-review-preparation-v1.json",
                "model-live-receipt-v1.json",
                "live-method-v1.json",
            )
        ),
        folder / "protocol-v1.json",
        folder / "semantic-review-preparation-v1.json",
        Path("experiments/core_quality_followup/quarantine-scope-protocol-v1.json"),
        Path("docs/pr55-evidence-review.fa.md"),
        Path("scripts/core_repeat_model_probe.py"),
        Path("src/agent_app/testing/enum_evidence.py"),
    }
    if folder == ENUM_FOLDER:
        paths.update(
            JSON_FOLDER / name
            for name in ("protocol-v1.json", "model-live-receipt-v1.json", "live-method-v1.json")
        )
        paths.add(Path("scripts/core_enum_evidence_probe.py"))
    else:
        paths.update(
            {
                folder / "offline-replay-v1.json",
                Path("src/agent_app/testing/finite_controlled_probe.py"),
            }
        )
        if folder == COMPLEMENTARY_FOLDER:
            paths.update(
                {
                    Path("scripts/core_complementary_sources_probe.py"),
                    Path("src/agent_app/testing/complementary_evidence.py"),
                }
            )
        else:
            paths.update(
                {
                    Path("scripts/core_source_order_probe.py"),
                    Path("src/agent_app/testing/source_order.py"),
                    *(
                        COMPLEMENTARY_FOLDER / name
                        for name in (
                            "protocol-v1.json",
                            "model-live-receipt-v1.json",
                            "live-method-v1.json",
                        )
                    ),
                }
            )
    for relative in sorted(paths):
        destination = target_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        # This branch never reads or stats the original ignored runtime file.
        raw = (
            synthetic_native_bytes(relative)
            if relative.parts[0] == "runtime"
            else (source_root / relative).read_bytes()
        )
        destination.write_bytes(raw)
    for name, registered_digest in protected["files"].items():
        actual_digest = sha((target_root / name).read_bytes())
        if Path(name).parts[0] == "runtime":
            protected["files"][name] = actual_digest
        else:
            assert actual_digest == registered_digest
    _write_json(target_root / protected_relative, protected)
    protocol = json.loads(original_protocol)
    if "parent" in protocol:
        assert protocol["parent"]["protected_inputs_path"] == protected_relative.as_posix()
        protocol["parent"]["protected_inputs_sha256"] = sha(
            (target_root / protected_relative).read_bytes()
        )
        _write_json(target_root / folder / "protocol-v1.json", protocol)
        temporary_protocol_sha = sha((target_root / folder / "protocol-v1.json").read_bytes())
        monkeypatch.setattr(module, "PROTOCOL_SHA256", temporary_protocol_sha)
        for name in ("semantic-review-preparation-v1.json", "offline-replay-v1.json"):
            artifact = target_root / folder / name
            value = _json(artifact)
            assert value["protocol_sha256"] == sha(original_protocol)
            value["protocol_sha256"] = temporary_protocol_sha
            _write_json(artifact, value)
    # Enum's protocol has no parent protected-file digest: preserve its bytes and
    # its capacity-amendment binding exactly, rather than rebinding needlessly.
    policy = target_root / "experiments/core_quality_followup/quarantine-scope-protocol-v1.json"
    value = _json(policy)
    value["known_uncertain_request_ids"] = list(ledger.quarantine_observation().unknown_ids)
    _write_json(policy, value)
    fixtures = module.fixtures_for(source_root, {"protocol_id": "core-stability-v1"})
    monkeypatch.setattr(module, "fixtures_for", lambda *_args: fixtures)
    return module, target_root, ledger_path, fixtures
