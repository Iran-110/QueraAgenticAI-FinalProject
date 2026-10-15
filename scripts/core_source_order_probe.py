"""Freeze/check a fresh finite controlled evidence-order comparison before explicit --live."""

import json
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

from core_repeat_model_probe import (
    close_owned_scope,
    ledger_journal_snapshot,
    validate_fresh_identities,
    validate_ledger_journal,
)
from core_stability_probe import credential, write_new
from dev_rag_model_probe import batch_complete, source_matches

from agent_app.llm.budget import BudgetLedger, LedgerConflict
from agent_app.llm.config import MetisConfig
from agent_app.llm.pricing import get_price
from agent_app.reasoning.catalog import load_user_gap_vocabulary
from agent_app.testing.dev_three_model_probe import ledger_observation, sha
from agent_app.testing.enum_evidence import load_source_packet
from agent_app.testing.finite_controlled_probe import run_finite_cli
from agent_app.testing.quality_probe import quality_slots, run_quality_batch
from agent_app.testing.source_order import fixture_retriever_factory
from agent_app.testing.stability_probe import (
    VOCABULARY,
    fixtures_for,
    slots_sha256,
    source_observation,
)

# These named exports form the finite lifecycle's explicit dependency interface.
__all__ = [
    "BudgetLedger",
    "LedgerConflict",
    "MetisConfig",
    "VOCABULARY",
    "batch_complete",
    "close_owned_scope",
    "credential",
    "get_price",
    "load_user_gap_vocabulary",
    "run_quality_batch",
    "source_matches",
    "validate_ledger_journal",
    "write_new",
]

ROOT = Path(__file__).resolve().parents[1]
FOLDER = Path("experiments/core_source_order_v1")
PARENT_FOLDER = Path("experiments/core_enum_evidence_v1")
METHOD = FOLDER / "live-method-v1.json"
PROTOCOL_SHA256 = "2ec9f8b3f0adfc7bf889b05ffa6aacad996f661d9f90c42c0bed99ade7910bee"
ERROR_PREFIX = "SourceOrder"


def reject():
    raise ValueError("SourceOrderRegistrationRejected")


def registered_protocol(root):
    raw = (root / FOLDER / "protocol-v1.json").read_bytes()
    if sha(raw) != PROTOCOL_SHA256:
        reject()
    protocol = json.loads(raw)
    if (
        type(protocol["schema_version"]) is not int
        or protocol["schema_version"] != 1
        or protocol["protocol_id"] != "core-source-order-v1"
        or protocol["registered_before_implementation"] is not True
        or protocol["registered_before_paid_calls"] is not True
    ):
        reject()
    return protocol


def validate_registered_inputs(root, protected):
    """Hash complete protected bytes without opening the real RAG index."""
    if type(protected) is not dict or not protected:
        reject()
    for name, digest in protected.items():
        if (
            type(name) is not str
            or type(digest) is not str
            or len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest)
        ):
            reject()
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or sha(path.read_bytes()) != digest:
            reject()
    return protected


def load_packet():
    return load_source_packet(ROOT / PARENT_FOLDER / "source-packet-v1.json")


def receipt_metadata(_method):
    return {
        "renderer_source_gap_investigation": True,
        "renderer_ask_source_background": True,
        "renderer_concise_user_draft": True,
        "grounded_json_object": True,
        "compact_plan": True,
        "source_capacity": True,
        "resource_guidance": False,
        "repair_repeated_queries": False,
        "evidence_dependent_source_count_bounds": True,
        "same_complete_record_set_both_arms": True,
        "common_prompt_both_arms": True,
        "common_evidence_condition": "fixed_guide_added",
        "only_complete_record_order_differs": True,
        "ordered_USER_payload_and_context_may_differ": True,
        "complementary_sources": False,
        "real_RAG_retrieval": False,
        "controlled_fixed_evidence": True,
        "answer_linked_guide_fixture_only": True,
        "original_fixture_gold_unchanged": True,
        "held_out_test": False,
    }


def build_method(root, ledger_path):
    protocol = registered_protocol(root)
    planned, parent = protocol["live"], protocol["parent"]
    for name in ("receipt", "source_packet", "protected_inputs"):
        if sha((root / parent[name + "_path"]).read_bytes()) != parent[name + "_sha256"]:
            reject()
    fixtures = fixtures_for(root, {"protocol_id": "core-stability-v1"})
    packet = load_source_packet(root / parent["source_packet_path"])
    fixture_retriever_factory(packet, fixtures, [])
    protected_artifact = json.loads((root / parent["protected_inputs_path"]).read_bytes())
    protected = protected_artifact["files"]
    if (
        type(protected_artifact["schema_version"]) is not int
        or protected_artifact["schema_version"] != 1
        or type(protected_artifact["actual_sends"]) is not int
        or protected_artifact["actual_sends"] != 0
        or protected_artifact["real_index_source_count"] != 18
        or protected_artifact["real_index_chunk_count"] != 36
        or protected_artifact["answer_linked_guide_absent_from_index"] is not True
        or len(protected) != 19
    ):
        reject()
    validate_registered_inputs(root, protected)
    offline = json.loads((root / FOLDER / "offline-replay-v1.json").read_bytes())
    if (
        offline.get("protocol_sha256") != PROTOCOL_SHA256
        or offline.get("parent_receipt_sha256") != parent["receipt_sha256"]
        or offline.get("common_SYSTEM_policy") is not True
        or "human_usefulness" not in offline
        or offline.get("accepted") is not True
        or type(offline.get("actual_sends")) is not int
        or offline["actual_sends"] != 0
        or offline.get("held_out_test") is not False
        or offline.get("human_usefulness") is not None
        or type(offline.get("historical_contexts")) is not int
        or offline["historical_contexts"] != 24
        or offline.get("common_prompt") is not True
        or offline.get("complete_record_set_unchanged") is not True
    ):
        reject()
    preparation = json.loads((root / FOLDER / "semantic-review-preparation-v1.json").read_bytes())
    if (
        type(preparation.get("schema_version")) is not int
        or preparation["schema_version"] != 1
        or preparation.get("registered_before_model") is not True
        or preparation.get("protocol_sha256") != PROTOCOL_SHA256
        or preparation.get("parent_receipt_sha256") != parent["receipt_sha256"]
        or preparation.get("source_packet_sha256") != parent["source_packet_sha256"]
        or preparation.get("human_reviewed") is not False
        or "human_usefulness" not in preparation
        or preparation["human_usefulness"] is not None
        or preparation.get("held_out_test") is not False
        or preparation.get("same_guide_available_evidence_both_arms") is not True
        or preparation.get("common_prompt") is not True
        or preparation.get("complete_criteria") != protocol["prospective_outcomes"]
        or preparation.get("scenarios_before_model") != protocol["scenarios_before_model"]
    ):
        reject()
    pins = {
        path.relative_to(root).as_posix(): sha(path.read_bytes())
        for path in (root / "data/evaluation/dev-three-v1").rglob("*.json")
    }
    names = [
        (FOLDER / "protocol-v1.json").as_posix(),
        (FOLDER / "offline-replay-v1.json").as_posix(),
        (FOLDER / "semantic-review-preparation-v1.json").as_posix(),
        (PARENT_FOLDER / "protocol-v1.json").as_posix(),
        (PARENT_FOLDER / "capacity-amendment-v1.json").as_posix(),
        (PARENT_FOLDER / "offline-boundary-initial-v1.json").as_posix(),
        (PARENT_FOLDER / "offline-boundary-review-v1.json").as_posix(),
        *[parent[name + "_path"] for name in ("receipt", "source_packet", "protected_inputs")],
        "experiments/core_quality_followup/quarantine-scope-protocol-v1.json",
        "docs/pr55-evidence-review.fa.md",
        "scripts/core_source_order_probe.py",
        "scripts/core_repeat_model_probe.py",
        "src/agent_app/testing/finite_controlled_probe.py",
        "src/agent_app/testing/source_order.py",
        "src/agent_app/testing/enum_evidence.py",
        protocol["negative_parent"]["protocol_path"],
    ]
    for name in names:
        pins[name] = sha((root / name).read_bytes())
    observation = asdict(BudgetLedger(ledger_path).quarantine_observation())
    known = json.loads(
        (root / "experiments/core_quality_followup/quarantine-scope-protocol-v1.json").read_bytes()
    )
    if tuple(observation["unknown_ids"]) != tuple(known["known_uncertain_request_ids"]):
        reject()
    method = {
        "schema_version": 1,
        "protocol_id": planned["protocol_id"],
        "experiment_id": planned["experiment_id"],
        "authorization_ref": protocol["authorization_ref"],
        "baseline_main_commit": protocol["baseline_commit"],
        "treatment_protocol": protocol,
        "input_pins": pins,
        "protected_files": protected,
        "batches": [],
        "model": planned["model"],
        "scope_cap_usd": planned["scope_cap_usd"],
        "campaign_scope_cap_usd": planned["campaign_cap_usd"],
        "quarantine_before": observation,
        "ledger_before": ledger_observation(ledger_path),
        "ledger_journal_before": ledger_journal_snapshot(ledger_path),
        "ordinary_halt_retained": True,
        "c5_reconciled": False,
        "human_reviewed": False,
        "human_usefulness": None,
        "offline_payload_preflight": offline,
        **receipt_metadata(None),
    }
    ids, pair_index = [], 0
    for round_number, case_order in enumerate(planned["case_order"], start=1):
        for case_id in case_order:
            name = f"source-order-r{round_number}-{case_id}"
            jobs = [
                {
                    "job_id": f"r{round_number}:{case_id}:{arm}",
                    "case_id": case_id,
                    "arm": arm,
                    "round": round_number,
                    "evidence_condition": "fixed_guide_added",
                    "evidence_order": arm,
                    **{
                        key: value
                        for key, value in planned["common_flags"].items()
                        if key
                        not in {
                            "source_gap_handoff",
                            "source_gap_investigation",
                            "retrieval_profile",
                            "retrieval_candidate_multiplier",
                            "evidence_utf8_budget_bytes",
                        }
                    },
                    "max_output_tokens": planned["max_output_tokens"],
                    "input_token_reserve": planned["input_token_reserve"],
                }
                for arm in planned["paired_arm_order"][pair_index]
            ]
            batch = {
                "batch_id": name,
                "kind": "controlled_evidence",
                "scope_id": f"user-core-source-order-v1-r{round_number}-{case_id}",
                "jobs": jobs,
            }
            slots = quality_slots(method, batch, fixtures)
            total = sum(slot.amount_usd for slot in slots)
            if len(slots) != 8 or total > Decimal(method["scope_cap_usd"]):
                reject()
            batch.update(
                request_slots_sha256=slots_sha256(slots),
                max_request_slots=len(slots),
                worst_reserved_usd=str(total),
            )
            ids.extend(slot.request_id for slot in slots)
            method["batches"].append(batch)
            pair_index += 1
    if len(ids) != 48 or len(set(ids)) != 48 or len(method["batches"]) != 6:
        reject()
    method["fresh_request_ids"] = ids
    method["fresh_scope_ids"] = [batch["scope_id"] for batch in method["batches"]]
    validate_fresh_identities(ledger_path, set(ids), set(method["fresh_scope_ids"]))
    return json.loads(json.dumps(method, default=str))


def preflight(root, ledger_path, method_path):
    method = json.loads(method_path.read_bytes())
    if method != build_method(root, ledger_path):
        reject()
    observation = method["ledger_before"]
    if (
        not observation["halted"]
        or observation["counts"].get("reserved", 0)
        or observation["counts"].get("uncertain", 0) != 2
        or observation["limit_nanos"] != 4_500_000_000
    ):
        reject()
    validate_registered_inputs(root, method["input_pins"])
    source = source_observation(root, method_path.relative_to(root), method["input_pins"])
    if not source["source_clean"]:
        reject()
    validate_registered_inputs(root, method["protected_files"])
    return method, {
        **source,
        "method_sha256": sha(method_path.read_bytes()),
        "quarantine_before": method["quarantine_before"],
        "ledger_before": observation,
        "ledger_journal_before": method["ledger_journal_before"],
    }


class _RuntimeBindings:
    """Named dependency seams remain observable at each transport checkpoint."""

    def __getattr__(self, name):
        return globals()[name]


def main(argv=None):
    return run_finite_cli(_RuntimeBindings(), argv)


if __name__ == "__main__":
    raise SystemExit(main())
