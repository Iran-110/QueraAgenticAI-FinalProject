"""Register a fresh finite claim-passage comparison; never resume closed studies."""

import json
import sqlite3
from contextlib import closing
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

from core_broader_dev_probe import fixtures_for as broader_fixtures
from core_broader_dev_probe import validate_registered_inputs
from core_repeat_model_probe import (
    close_owned_scope,
    ledger_journal_snapshot,
    validate_fresh_identities,
    validate_ledger_journal,
)
from core_stability_probe import credential, write_new
from dev_rag_model_probe import source_matches

from agent_app.llm.budget import BudgetLedger, LedgerConflict
from agent_app.llm.config import MetisConfig
from agent_app.llm.pricing import get_price
from agent_app.reasoning.catalog import load_user_gap_vocabulary
from agent_app.testing.claim_probe import (
    EXPERIMENT_ID,
    offline_preflight,
)
from agent_app.testing.claim_probe import (
    fixed_snapshot_factory as fixture_retriever_factory,
)
from agent_app.testing.claim_probe import (
    proposal_slots as quality_slots,
)
from agent_app.testing.claim_probe import (
    run_proposal_batch as run_quality_batch,
)
from agent_app.testing.dev_three_model_probe import ledger_observation, sha
from agent_app.testing.finite_controlled_probe import (
    actual_json_wire_observation,
    run_finite_cli,
)
from agent_app.testing.stability_probe import VOCABULARY, slots_sha256, source_observation

__all__ = [
    "BudgetLedger",
    "LedgerConflict",
    "MetisConfig",
    "VOCABULARY",
    "close_owned_scope",
    "credential",
    "fixture_retriever_factory",
    "get_price",
    "load_user_gap_vocabulary",
    "run_quality_batch",
    "source_matches",
    "validate_ledger_journal",
    "write_new",
]
ROOT = Path(__file__).resolve().parents[1]
FOLDER = Path("experiments/core_claim_boundary_v1")
OLD_FOLDER = Path("experiments/core_broader_dev_v1")
METHOD = FOLDER / "live-method-v1.json"
PROTOCOL_SHA256 = "c8f716f930bd14a946499d212429f5334e4ca4f371c873e8f8d3278b426d691a"
MATRIX_SHA256 = "63f830a68f96a60f920a1b5694112469f08037754bacda71bfd5fc48c4921261"
EPOCH_SHA256 = "658583614304bf99c6890973274d2e683068302fd897422b64e1942773506727"
PREPARATION_SHA256 = "2742cf7955ac1443bf24b176b0179b5452cad6025f43f767384f4cc99424b195"
CLOSED_RECEIPT_SHA256 = "477012c7eae6e216a50408530045c3f78619c02f21f743ce19bc8eaadbc817e4"
ERROR_PREFIX = "ClaimBoundary"


def reject():
    raise ValueError("ClaimBoundaryRegistrationRejected")


def load_packet():
    return json.loads((ROOT / OLD_FOLDER / "snapshots-v1.json").read_bytes())


def fixtures_for(root, _protocol):
    return broader_fixtures(root, _protocol)


def receipt_metadata(_method):
    return {
        "proposal_only": True,
        "controlled_fixed_evidence": True,
        "real_RAG_retrieval": False,
        "no_automatic_approval_or_release": True,
        "no_route_success_claim": True,
        "tracker_actions_executed": 0,
        "held_out_test": False,
        "human_reviewed": False,
        "human_usefulness": None,
        "same_complete_current_inputs_both_arms": True,
        "existing_compiled_vs_constrained_passages_not_single_factor_prompt": True,
        "default_promotion": False,
        "expected_response_format_field": None,
        "schema_or_exact_passage_is_not_automatic_entailment": True,
    }


def batch_complete(batch):
    return (
        batch["original_accounting_preserved"] is True
        and batch["stopped_early"] is False
        and batch["accounting"]["accounting_complete"] is True
        and batch["visited_jobs"] == batch["planned_jobs"]
    )


def observe_no_json_format(result):
    actual_json_wire_observation(result)
    sent = [row for row in result["provider_sends"] if row["http_send_started"]]
    if any(row.get("wire_response_format") != "absent" for row in sent):
        reject()
    result["actual_no_response_format_field"] = True if sent else None
    return None


def _baseline_health(path, protocol, closed):
    observation = ledger_observation(path)
    if observation != closed["ledger_after"]:
        reject()
    expected = protocol["live"]["expected_before"]
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        rows = db.execute("SELECT status,count(*) FROM reservations GROUP BY status").fetchall()
        counts = dict(rows)
        settled = (
            db.execute(
                "SELECT sum(cost_nanos) FROM reservations WHERE status='settled'"
            ).fetchone()[0]
            or 0
        )
        held = (
            db.execute(
                "SELECT sum(amount_nanos) FROM reservations WHERE status='uncertain'"
            ).fetchone()[0]
            or 0
        )
        scopes = db.execute("SELECT count(*) FROM quarantine_scopes").fetchone()[0]
        open_scopes = db.execute(
            "SELECT count(*) FROM quarantine_scopes WHERE terminal_status IS NULL OR terminal_status!='closed'"
        ).fetchone()[0]
    if (
        sum(counts.values()) != expected["reservations"]
        or counts.get("settled", 0) != expected["settled"]
        or counts.get("uncertain", 0) != expected["uncertain"]
        or counts.get("reserved", 0)
        or Decimal(settled) / 1_000_000_000 != Decimal(expected["settled_local_estimate_usd"])
        or Decimal(held) / 1_000_000_000 != Decimal(expected["old_hold_usd"])
        or observation["halted"] is not expected["halted"]
        or observation["limit_nanos"] != int(Decimal(expected["ceiling_usd"]) * 1_000_000_000)
        or scopes != 91
        or open_scopes
    ):
        reject()
    return observation


def build_method(root, ledger_path):
    raw = (root / FOLDER / "protocol-v1.json").read_bytes()
    if sha(raw) != PROTOCOL_SHA256:
        reject()
    protocol = json.loads(raw)
    packet_path = root / protocol["inputs"]["snapshots"]
    if sha(packet_path.read_bytes()) != protocol["inputs"]["snapshots_sha256"]:
        reject()
    protected_path = root / protocol["inputs"]["current_epoch"]
    preparation_path = root / protocol["inputs"]["preparation"]
    if (
        sha(protected_path.read_bytes()) != EPOCH_SHA256
        or sha(preparation_path.read_bytes()) != PREPARATION_SHA256
    ):
        reject()
    epoch = json.loads(protected_path.read_bytes())
    original = json.loads(
        (root / "experiments/core_enum_evidence_v1/protected-inputs-v1.json").read_bytes()
    )
    if (
        epoch["original_files"] != original["files"]
        or epoch["original_physical_matches"] != 17
        or len(epoch["original_physical_mismatches"]) != 2
        or epoch["logical_review_checks_passed"] != 182
        or not epoch["full_original_manifest_corpus_metadata_vectors_and_exclusions_equal"]
        or sha((root / epoch["logical_review_path"]).read_bytes()) != epoch["logical_review_sha256"]
        or len(epoch["files"]) != 19
    ):
        reject()
    validate_registered_inputs(root, epoch["files"])
    fixtures = fixtures_for(root, protocol)
    packet = json.loads(packet_path.read_bytes())
    matrix_path = root / protocol["inputs"]["new_acceptance_matrix"]
    if sha(matrix_path.read_bytes()) != MATRIX_SHA256:
        reject()
    matrix = json.loads(matrix_path.read_bytes())
    if (
        matrix["protocol_sha256"] != PROTOCOL_SHA256
        or matrix["snapshot_packet_sha256"] != sha(packet_path.read_bytes())
        or matrix["registered_before_model"] is not True
        or matrix["oracle_only_not_model_payload"] is not True
        or len(matrix["rows"]) != 16
        or {r["snapshot_id"] for r in matrix["rows"]} != set(fixtures)
    ):
        reject()
    for row in matrix["rows"]:
        fixture = fixtures[row["snapshot_id"]]
        if row["snapshot_row_sha256"] != sha(
            json.dumps(fixture, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ):
            reject()
    offline = offline_preflight(packet)
    frozen_offline = json.loads((root / FOLDER / "offline-preflight-v1.json").read_bytes())
    if (
        offline != frozen_offline
        or offline.get("accepted") is not True
        or len(offline["rows"]) != 64
    ):
        reject()
    closed_path = root / OLD_FOLDER / "model-receipt-v1.json"
    if sha(closed_path.read_bytes()) != CLOSED_RECEIPT_SHA256:
        reject()
    before = _baseline_health(ledger_path, protocol, json.loads(closed_path.read_bytes()))
    known_path = root / "experiments/core_quality_followup/quarantine-scope-protocol-v1.json"
    known = json.loads(known_path.read_bytes())
    observation = json.loads(
        json.dumps(asdict(BudgetLedger(ledger_path).quarantine_observation()), default=str)
    )
    if observation["unknown_ids"] != known["known_uncertain_request_ids"]:
        reject()
    names = {
        *(
            value
            for key, value in protocol["inputs"].items()
            if not key.endswith("sha256") and isinstance(value, str)
        ),
        *(str(FOLDER / name) for name in ("protocol-v1.json", "offline-preflight-v1.json")),
        *(
            str(OLD_FOLDER / name)
            for name in (
                "model-receipt-v1.json",
                "index-recovery-review-v1.json",
                "preparation-amendment-v1.json",
                "preparation-first-failure-v1.json",
            )
        ),
        "experiments/core_enum_evidence_v1/protected-inputs-v1.json",
        "experiments/core_quality_followup/quarantine-scope-protocol-v1.json",
        "scripts/core_claim_boundary_probe.py",
        "scripts/core_broader_dev_probe.py",
        "scripts/core_repeat_model_probe.py",
        "scripts/core_stability_probe.py",
        "src/agent_app/testing/claim_probe.py",
        "src/agent_app/testing/broader_proposals.py",
        "src/agent_app/testing/finite_controlled_probe.py",
        "src/agent_app/reasoning/claim_plan.py",
        "src/agent_app/llm/claims.py",
        "src/agent_app/llm/metis.py",
    }
    pins = {name: sha((root / name).read_bytes()) for name in sorted(names)}
    method = {
        "schema_version": 1,
        "protocol_id": protocol["protocol_id"],
        "experiment_id": EXPERIMENT_ID,
        "authorization_ref": protocol["authorization_ref"],
        "baseline_main_commit": protocol["baseline_commit"],
        "treatment_protocol": protocol,
        "input_pins": pins,
        "protected_files": epoch["files"],
        "model": protocol["live"]["model"],
        "scope_cap_usd": "0.06",
        "campaign_scope_cap_usd": "0.96",
        "quarantine_before": observation,
        "ledger_before": before,
        "ledger_journal_before": ledger_journal_snapshot(ledger_path),
        "ordinary_halt_retained": True,
        "c5_reconciled": False,
        "offline_payload_preflight": offline,
        "batches": [],
        **receipt_metadata(None),
    }
    scopes, ids = [], []
    scenarios = protocol["scenarios"]
    for number in (1, 2):
        for scenario in scenarios if number == 1 else scenarios[::-1]:
            index = scenarios.index(scenario)
            order = protocol["arms"] if (index + number) % 2 else protocol["arms"][::-1]
            selected = [row["id"] for row in packet["snapshots"] if row["scenario_id"] == scenario]
            if len(selected) != 2:
                reject()
            batch = {
                "batch_id": f"claim-r{number}-{scenario}",
                "scope_id": f"user-core-claims-v1-r{number}-{scenario}",
                "kind": "controlled_evidence",
                "jobs": [
                    {
                        "job_id": f"r{number}:{scenario}:{arm}",
                        "arm": arm,
                        "scenario_id": scenario,
                        "snapshot_ids": selected,
                        "round": number,
                        "input_token_reserve": 32768,
                        "max_output_tokens": 2048,
                    }
                    for arm in order
                ],
            }
            slots = quality_slots(method, batch, fixtures)
            total = sum(slot.amount_usd for slot in slots)
            if len(slots) != 8 or total > Decimal("0.06"):
                reject()
            batch.update(
                max_request_slots=8,
                request_slots_sha256=slots_sha256(slots),
                worst_reserved_usd=str(total),
            )
            method["batches"].append(batch)
            ids.extend(slot.request_id for slot in slots)
            scopes.append(batch["scope_id"])
    if len(ids) != 128 or len(set(ids)) != 128 or len(set(scopes)) != 16:
        reject()
    validate_fresh_identities(ledger_path, set(ids), set(scopes))
    method["fresh_request_ids"], method["fresh_scope_ids"] = ids, scopes
    return json.loads(json.dumps(method, default=str))


def preflight(root, ledger_path, method_path):
    method = json.loads(method_path.read_bytes())
    if method != build_method(root, ledger_path):
        reject()
    validate_registered_inputs(root, method["input_pins"])
    source = source_observation(root, method_path.relative_to(root), method["input_pins"])
    if not source["source_clean"]:
        reject()
    return method, {
        **source,
        "method_sha256": sha(method_path.read_bytes()),
        "quarantine_before": method["quarantine_before"],
        "ledger_before": method["ledger_before"],
        "ledger_journal_before": method["ledger_journal_before"],
    }


class _RuntimeBindings:
    def __getattr__(self, name):
        return globals()[name]


def main(argv=None):
    return run_finite_cli(_RuntimeBindings(), argv, wire_observer=observe_no_json_format)


if __name__ == "__main__":
    raise SystemExit(main())
