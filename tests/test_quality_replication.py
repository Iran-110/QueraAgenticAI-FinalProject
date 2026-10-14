"""Complete preregistered reverse-order slice; no real ledger or model."""

import json
from pathlib import Path
from types import SimpleNamespace

from test_quality_cli import _module

from agent_app.testing.quality_probe import quality_slots
from agent_app.testing.stability_probe import fixtures_for


def test_replication_reverses_all_conditions_with_new_bound_slots(monkeypatch):
    module = _module(monkeypatch)
    root = Path(__file__).resolve().parents[1]
    ids = tuple(
        json.loads((root / module.FOLDER / "quarantine-scope-protocol-v1.json").read_bytes())[
            "known_uncertain_request_ids"
        ]
    )
    observation = SimpleNamespace(
        unknown_ids=ids,
        unknown_fingerprints=tuple((i, "a" * 64) for i in ids),
        meta_sha256="b" * 64,
        authorization_history_sha256="c" * 64,
        held_usd="0.0233792",
    )
    # The generator serializes dataclasses; mock only the observation conversion,
    # never read or authorize against the designated runner database.
    monkeypatch.setattr(module, "asdict", lambda obj: vars(obj))
    monkeypatch.setattr(
        module,
        "BudgetLedger",
        lambda _: SimpleNamespace(quarantine_observation=lambda: observation),
    )
    monkeypatch.setattr(
        module,
        "ledger_observation",
        lambda _: {
            "halted": True,
            "counts": {"settled": 296, "uncertain": 2},
            "db_sha256": "d" * 64,
        },
    )
    first = module.build_method(root, Path("synthetic-nonexistent-ledger"))
    second = module.build_method(root, Path("synthetic-nonexistent-ledger"), replication_only=True)
    original = [
        j["job_id"] for b in first["batches"] if b["kind"] == "adversarial" for j in b["jobs"]
    ]
    replicated = [j["job_id"] for b in second["batches"] for j in b["jobs"]]
    assert replicated == list(reversed(original)) and len(replicated) == 12
    assert len(first["batches"]) == 8 and len(second["batches"]) == 2
    assert sum(b["max_request_slots"] for b in second["batches"]) == 24
    assert all(j["max_output_tokens"] == 2048 for b in second["batches"] for j in b["jobs"])
    fixtures = fixtures_for(root, {"protocol_id": "fixed-evidence"})
    old = {s.request_id for b in first["batches"] for s in quality_slots(first, b, fixtures)}
    fresh = {s.request_id for b in second["batches"] for s in quality_slots(second, b, fixtures)}
    assert len(fresh) == 24 and not old & fresh
    assert second["input_pins"]["experiments/core_quality_followup/model-live-receipt-v1.json"]
