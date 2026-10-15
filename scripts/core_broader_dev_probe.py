"""Freeze a bounded proposal-only comparison; no approvals or real RAG at runtime."""

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
from dev_rag_model_probe import source_matches

from agent_app.contracts import CaseState, EvidenceBundle, GroundedRequest, ProposalRequirements
from agent_app.llm.budget import BudgetLedger, LedgerConflict
from agent_app.llm.config import MetisConfig
from agent_app.llm.pricing import get_price
from agent_app.reasoning.catalog import load_user_gap_vocabulary
from agent_app.reasoning.grounding import validate_grounded_request
from agent_app.testing.broader_proposals import (
    fixed_snapshot_factory as fixture_retriever_factory,
)
from agent_app.testing.broader_proposals import (
    offline_preflight,
)
from agent_app.testing.broader_proposals import (
    proposal_slots as quality_slots,
)
from agent_app.testing.broader_proposals import (
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
FOLDER = Path("experiments/core_broader_dev_v1")
METHOD = FOLDER / "live-method-v1.json"
PROTOCOL_SHA256 = "504d34bac87142adf9a09b2ab56117d3c752ea7b6b306b2a89ba61acf003b3f6"
PREPARATION_AMENDMENT_SHA256 = "ebfd1aee7d9b002f7ff5b95769288bb70e878fbd4f0632d1086f3a627eafa7bb"
ERROR_PREFIX = "BroaderDev"


def reject():
    raise ValueError("BroaderDevRegistrationRejected")


def validate_registered_inputs(root, protected):
    if type(protected) is not dict or not protected:
        reject()
    for name, digest in protected.items():
        path = (root / name).resolve()
        if (
            not path.is_relative_to(root.resolve())
            or type(digest) is not str
            or len(digest) != 64
            or sha(path.read_bytes()) != digest
        ):
            reject()
    return protected


def load_packet():
    return json.loads((ROOT / FOLDER / "snapshots-v1.json").read_bytes())


def fixtures_for(root, _protocol):
    packet = json.loads((root / FOLDER / "snapshots-v1.json").read_bytes())
    protected_path = root / FOLDER / "protected-inputs-v1.json"
    preparation = json.loads((root / FOLDER / "preparation-v1.json").read_bytes())
    if (
        preparation.get("accepted") is not True
        or preparation.get("registered_before_model") is not True
        or preparation.get("actual_sends") != 0
        or preparation.get("snapshot_count") != 16
        or preparation.get("unique_report_families") != 7
        or preparation.get("current_epoch19_files_unchanged") is not True
        or preparation.get("historical_original19_files_unchanged") is not False
        or preparation.get("original18_sources36_chunks_metadata_vectors_exclusions_equal")
        is not True
        or preparation.get("native_client_isolated_copy_only") is not True
        or preparation.get("native_issues_comments_guide_excluded") is not True
        or preparation.get("snapshot_packet_sha256")
        != sha((root / FOLDER / "snapshots-v1.json").read_bytes())
        or preparation.get("protected_epoch_sha256") != sha(protected_path.read_bytes())
    ):
        reject()
    rows = packet["snapshots"]
    if type(rows) is not list or len(rows) != 16:
        reject()
    fixtures = {}
    for row in rows:
        case = CaseState.model_validate(row["case"])
        evidence = EvidenceBundle.model_validate(row["evidence"])
        request = validate_grounded_request(GroundedRequest.model_validate(row["catalog_request"]))
        requirements = ProposalRequirements.model_validate(row["proposal_requirements"])
        if (
            row["id"] in fixtures
            or request.case != case
            or request.evidence != evidence
            or request.user_message != row["user_message"].strip()
            or requirements.case_id != case.case_id
            or requirements.case_revision != case.case_revision
            or {(g.name, g.question) for g in request.gaps if g.kind == "user"}
            != {(q.name, q.question) for q in requirements.question_targets}
        ):
            reject()
        fixtures[row["id"]] = row
    return fixtures


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
        "existing_pipeline_comparison_not_single_factor_prompt": True,
        "default_promotion": False,
        "expected_response_format_field": None,
    }


def batch_complete(batch):
    return (
        batch["original_accounting_preserved"] is True
        and batch["stopped_early"] is False
        and batch["accounting"]["accounting_complete"] is True
        and batch["visited_jobs"] == batch["planned_jobs"]
    )


def observe_no_json_format(result):
    # Reuse the existing strict actual-started/count check, not its mode verdict.
    actual_json_wire_observation(result)
    sent = [r for r in result["provider_sends"] if r["http_send_started"]]
    if any(r.get("wire_response_format") != "absent" for r in sent):
        reject()
    result["actual_no_response_format_field"] = True if sent else None
    # Absence of a JSON-mode request is never reported as successful JSON mode.
    return None


def build_method(root, ledger_path):
    raw = (root / FOLDER / "protocol-v1.json").read_bytes()
    if sha(raw) != PROTOCOL_SHA256:
        reject()
    protocol = json.loads(raw)
    amendment_path = root / FOLDER / "bound-amendment-v1.json"
    if (
        sha(amendment_path.read_bytes())
        != "bec06875449f7940e5490207108c4459ebe0e3bda37d7b67c150e75bf00adcdd"
    ):
        reject()
    amendment = json.loads(amendment_path.read_bytes())
    physical_amendment_path = root / FOLDER / "preparation-amendment-v1.json"
    if sha(physical_amendment_path.read_bytes()) != PREPARATION_AMENDMENT_SHA256:
        reject()
    physical_amendment = json.loads(physical_amendment_path.read_bytes())
    protected_path = root / physical_amendment["effective_protected_inputs_path"]
    if sha(protected_path.read_bytes()) != physical_amendment["effective_protected_inputs_sha256"]:
        reject()
    protected_epoch = json.loads(protected_path.read_bytes())
    if (
        protected_epoch["original_physical_matches"] != 17
        or len(protected_epoch["original_physical_mismatches"]) != 2
        or not protected_epoch[
            "full_original_manifest_corpus_metadata_vectors_and_exclusions_equal"
        ]
        or sha((root / protected_epoch["logical_review_path"]).read_bytes())
        != protected_epoch["logical_review_sha256"]
        or protected_epoch["logical_review_checks_passed"] != 182
    ):
        reject()
    fixtures = fixtures_for(root, protocol)
    old = json.loads((root / protocol["inputs"]["original_protected_inputs"]).read_bytes())
    if old["files"] != protected_epoch["original_files"]:
        reject()
    protected = protected_epoch["files"]
    if len(protected) != 19:
        reject()
    validate_registered_inputs(root, protected)
    if (
        sha((root / protocol["inputs"]["old_Enum_source_packet"]).read_bytes())
        != protocol["inputs"]["old_Enum_source_packet_sha256"]
    ):
        reject()
    packet = json.loads((root / FOLDER / "snapshots-v1.json").read_bytes())
    offline = offline_preflight(packet)
    frozen_offline = json.loads((root / FOLDER / "offline-preflight-v1.json").read_bytes())
    if offline != frozen_offline or offline.get("accepted") is not True:
        reject()
    names = {
        *(
            value
            for key, value in protocol["inputs"].items()
            if not key.endswith("sha256") and isinstance(value, str)
        ),
        "scripts/core_broader_dev_probe.py",
        "scripts/prepare_broader_dev_snapshots.py",
        "src/agent_app/testing/broader_proposals.py",
        "src/agent_app/testing/finite_controlled_probe.py",
        "experiments/core_quality_followup/quarantine-scope-protocol-v1.json",
        (FOLDER / "protocol-v1.json").as_posix(),
        (FOLDER / "bound-amendment-v1.json").as_posix(),
        (FOLDER / "preparation-amendment-v1.json").as_posix(),
        (FOLDER / "preparation-first-failure-v1.json").as_posix(),
        (FOLDER / "protected-inputs-v1.json").as_posix(),
        (FOLDER / "index-recovery-review-v1.json").as_posix(),
    }
    pins = {name: sha((root / name).read_bytes()) for name in sorted(names)}
    observation = json.loads(
        json.dumps(asdict(BudgetLedger(ledger_path).quarantine_observation()), default=str)
    )
    known = json.loads(
        (root / "experiments/core_quality_followup/quarantine-scope-protocol-v1.json").read_bytes()
    )
    if observation["unknown_ids"] != known["known_uncertain_request_ids"]:
        reject()
    planned = {**protocol["live"], **amendment["effective_live_overrides"]}
    method = {
        "schema_version": 1,
        "protocol_id": planned["protocol_id"],
        "experiment_id": planned["experiment_id"],
        "authorization_ref": protocol["authorization_ref"],
        "baseline_main_commit": protocol["baseline_commit"],
        "treatment_protocol": protocol,
        "prospective_bound_amendment": amendment,
        "prospective_physical_preparation_amendment": physical_amendment,
        "input_pins": pins,
        "protected_files": protected,
        "model": planned["model"],
        "scope_cap_usd": planned["scope_cap_usd"],
        "campaign_scope_cap_usd": planned["campaign_cap_usd"],
        "quarantine_before": observation,
        "ledger_before": ledger_observation(ledger_path),
        "ledger_journal_before": ledger_journal_snapshot(ledger_path),
        "ordinary_halt_retained": True,
        "c5_reconciled": False,
        "offline_payload_preflight": offline,
        "batches": [],
        **receipt_metadata(None),
    }
    scopes, ids = [], []
    scenarios = protocol["scenarios"]
    for round_number in (1, 2):
        for scenario in scenarios if round_number == 1 else scenarios[::-1]:
            index = scenarios.index(scenario)
            order = protocol["arms"] if (index + round_number) % 2 else protocol["arms"][::-1]
            selected = [row["id"] for row in packet["snapshots"] if row["scenario_id"] == scenario]
            if len(selected) != 2:
                reject()
            batch = {
                "batch_id": f"broader-r{round_number}-{scenario}",
                "scope_id": f"user-core-broader-v1-r{round_number}-{scenario}",
                "kind": "controlled_evidence",
                "jobs": [
                    {
                        "job_id": f"r{round_number}:{scenario}:{arm}",
                        "arm": arm,
                        "scenario_id": scenario,
                        "snapshot_ids": selected,
                        "round": round_number,
                        "input_token_reserve": planned["input_token_reserve"],
                        "max_output_tokens": planned["max_output_tokens"],
                    }
                    for arm in order
                ],
            }
            slots = quality_slots(method, batch, fixtures)
            total = sum(slot.amount_usd for slot in slots)
            if len(slots) != 8 or total > Decimal(method["scope_cap_usd"]):
                reject()
            batch.update(
                max_request_slots=len(slots),
                request_slots_sha256=slots_sha256(slots),
                worst_reserved_usd=str(total),
            )
            method["batches"].append(batch)
            ids.extend(slot.request_id for slot in slots)
            scopes.append(batch["scope_id"])
    if len(ids) != 128 or len(set(ids)) != 128 or len(scopes) != 16:
        reject()
    validate_fresh_identities(ledger_path, set(ids), set(scopes))
    method["fresh_request_ids"], method["fresh_scope_ids"] = ids, scopes
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
    return method, {
        **source,
        "method_sha256": sha(method_path.read_bytes()),
        "quarantine_before": method["quarantine_before"],
        "ledger_before": observation,
        "ledger_journal_before": method["ledger_journal_before"],
    }


class _RuntimeBindings:
    def __getattr__(self, name):
        return globals()[name]


def main(argv=None):
    return run_finite_cli(_RuntimeBindings(), argv, wire_observer=observe_no_json_format)


if __name__ == "__main__":
    raise SystemExit(main())
