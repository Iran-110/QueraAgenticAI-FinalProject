"""Prepare/read-only check first; --live consumes one frozen finite experiment."""

import argparse
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

# Share the closed campaign's read-only journal/identity controls; no old scope
# or method is resumed. These helpers accept the exact fresh identities below.
from core_repeat_model_probe import (
    close_owned_scope,
    ledger_journal_snapshot,
    validate_fresh_identities,
    validate_ledger_journal,
)
from core_stability_probe import credential, write_new
from dev_rag_model_probe import (
    batch_complete,
    source_matches,
)

from agent_app.llm.budget import BudgetLedger, LedgerConflict
from agent_app.llm.config import MetisConfig
from agent_app.llm.pricing import get_price
from agent_app.reasoning.catalog import load_user_gap_vocabulary
from agent_app.testing.dev_three_model_probe import ledger_observation, sha
from agent_app.testing.enum_evidence import fixture_retriever_factory, load_source_packet
from agent_app.testing.quality_probe import quality_slots, run_quality_batch
from agent_app.testing.stability_probe import (
    VOCABULARY,
    fixtures_for,
    slots_sha256,
    source_observation,
)

ROOT = Path(__file__).resolve().parents[1]
FOLDER = Path("experiments/core_enum_evidence_v1")
PARENT_FOLDER = Path("experiments/core_json_readability_v1")
PROTOCOL_SHA256 = "687f9cc328d466369778e623e1285d225d372cc387667ba849a02b254644cf0e"
CAPACITY_AMENDMENT_SHA256 = "1aa970bc29d200c70613fbb83b8f5ea16f061e554c8b2d2ca3031f35430c646f"
METHOD = FOLDER / "live-method-v1.json"


def registered_protocol(root):
    raw = (root / FOLDER / "protocol-v1.json").read_bytes()
    if sha(raw) != PROTOCOL_SHA256:
        raise ValueError("EnumEvidenceRegistrationRejected")
    protocol = json.loads(raw)
    if (
        type(protocol["schema_version"]) is not int
        or protocol["schema_version"] != 1
        or protocol["protocol_id"] != "core-enum-evidence-v1"
        or protocol["registered_before_implementation"] is not True
        or protocol["registered_before_paid_calls"] is not True
    ):
        raise ValueError("EnumEvidenceRegistrationRejected")
    return protocol


def registered_capacity_amendment(root):
    raw = (root / FOLDER / "capacity-amendment-v1.json").read_bytes()
    if sha(raw) != CAPACITY_AMENDMENT_SHA256:
        raise ValueError("EnumEvidenceRegistrationRejected")
    value = json.loads(raw)
    if (
        type(value["schema_version"]) is not int
        or value["schema_version"] != 1
        or value["amendment_id"] != "core-enum-evidence-render-capacity-v1"
        or value["registered_before_paid_calls"] is not True
        or value["registered_before_experiment_flag_activation"] is not True
        or value["original_protocol_sha256"] != PROTOCOL_SHA256
        or value["original_protocol_sha256"]
        != sha((root / FOLDER / "protocol-v1.json").read_bytes())
        or value["no_source_excerpt_or_metadata_shortening"] is not True
        or value["all_source_records_still_available"] is not True
    ):
        raise ValueError("EnumEvidenceRegistrationRejected")
    return value


def validate_registered_inputs(root, protected):
    """Check protected file bytes only; never open Chroma, a retriever or native search."""
    if type(protected) is not dict or not protected:
        raise ValueError("EnumEvidenceRegistrationRejected")
    for name, digest in protected.items():
        if type(name) is not str or type(digest) is not str:
            raise ValueError("EnumEvidenceRegistrationRejected")
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or sha(path.read_bytes()) != digest:
            raise ValueError("EnumEvidenceRegistrationRejected")
    return protected


def build_method(root, ledger_path):
    """Register a new fixed-evidence comparison with unchanged real-RAG exclusion."""
    protocol = registered_protocol(root)
    capacity_amendment = registered_capacity_amendment(root)
    planned = protocol["live"]
    parent_path = root / PARENT_FOLDER / "model-live-receipt-v1.json"
    if sha(parent_path.read_bytes()) != protocol["parent_observation"]["receipt_sha256"]:
        raise ValueError("EnumEvidenceRegistrationRejected")
    fixtures = fixtures_for(root, {"protocol_id": "core-stability-v1"})
    packet = load_source_packet(root / FOLDER / "source-packet-v1.json")
    fixture_retriever_factory(packet, fixtures, [])
    pins = {
        path.relative_to(root).as_posix(): sha(path.read_bytes())
        for path in (root / "data/evaluation/dev-three-v1").rglob("*.json")
    }
    for name in (
        (FOLDER / "protocol-v1.json").as_posix(),
        (FOLDER / "capacity-amendment-v1.json").as_posix(),
        (FOLDER / "offline-boundary-initial-v1.json").as_posix(),
        (FOLDER / "source-packet-v1.json").as_posix(),
        (FOLDER / "offline-boundary-review-v1.json").as_posix(),
        (FOLDER / "semantic-review-preparation-v1.json").as_posix(),
        (FOLDER / "protected-inputs-v1.json").as_posix(),
        (PARENT_FOLDER / "protocol-v1.json").as_posix(),
        (PARENT_FOLDER / "model-live-receipt-v1.json").as_posix(),
        "experiments/core_quality_followup/quarantine-scope-protocol-v1.json",
        "docs/pr55-evidence-review.fa.md",
        "scripts/core_enum_evidence_probe.py",
        "scripts/core_repeat_model_probe.py",
        "src/agent_app/testing/enum_evidence.py",
    ):
        pins[name] = sha((root / name).read_bytes())
    protected_artifact = json.loads((root / FOLDER / "protected-inputs-v1.json").read_bytes())
    protected = protected_artifact["files"]
    if (
        type(protected_artifact["schema_version"]) is not int
        or protected_artifact["schema_version"] != 1
        or type(protected_artifact["actual_sends"]) is not int
        or protected_artifact["actual_sends"] != 0
        or protected_artifact["real_index_source_count"] != 18
        or protected_artifact["real_index_chunk_count"] != 36
        or protected_artifact["answer_linked_guide_absent_from_index"] is not True
        or protected_artifact["real_index_binding"]["manifest_sha256"]
        != protocol["exclusion_boundary"]["real_RAG_index_unchanged"]["manifest_sha256"]
    ):
        raise ValueError("EnumEvidenceRegistrationRejected")
    validate_registered_inputs(root, protected)
    offline = json.loads((root / FOLDER / "offline-boundary-review-v1.json").read_bytes())
    initial = json.loads((root / FOLDER / "offline-boundary-initial-v1.json").read_bytes())
    if (
        offline.get("accepted") is not True
        or offline.get("source_capacity") is not True
        or type(offline.get("actual_sends")) is not int
        or offline["actual_sends"] != 0
        or offline.get("actual_search") is not False
        or offline.get("is_model_quality_score") is not False
        or offline.get("human_usefulness") is not None
        or type(offline.get("permitted_bound_violations")) is not int
        or offline["permitted_bound_violations"] != 0
        or initial.get("accepted") is not False
        or initial.get("source_capacity") is not False
        or type(initial.get("actual_sends")) is not int
        or initial["actual_sends"] != 0
        or initial.get("actual_search") is not False
        or type(initial.get("permitted_bound_violations")) is not int
        or initial["permitted_bound_violations"] <= 0
        or initial.get("actual_renderer_rejections") != offline.get("actual_renderer_rejections")
        or len(initial["subset_outcomes"]) != len(offline["subset_outcomes"])
    ):
        raise ValueError("EnumEvidenceRegistrationRejected")
    observation = asdict(BudgetLedger(ledger_path).quarantine_observation())
    known = json.loads(
        (root / "experiments/core_quality_followup/quarantine-scope-protocol-v1.json").read_bytes()
    )
    if tuple(observation["unknown_ids"]) != tuple(known["known_uncertain_request_ids"]):
        raise ValueError("EnumEvidenceRegistrationRejected")
    method = {
        "schema_version": 1,
        "protocol_id": planned["protocol_id"],
        "experiment_id": planned["experiment_id"],
        "authorization_ref": protocol["authorization_ref"],
        "baseline_main_commit": protocol["baseline_commit"],
        "treatment_protocol": protocol,
        "treatment_capacity_amendment": capacity_amendment,
        "source_capacity": True,
        "same_core_policy_both_arms": True,
        "evidence_dependent_source_count_bounds": True,
        "baseline_model_receipt": parent_path.relative_to(root).as_posix(),
        "input_pins": pins,
        "protected_files": protected,
        "batches": [],
        "model": "gpt-4o-mini",
        "scope_cap_usd": "0.06",
        "campaign_scope_cap_usd": "0.36",
        "quarantine_before": observation,
        "ledger_before": ledger_observation(ledger_path),
        "ledger_journal_before": ledger_journal_snapshot(ledger_path),
        "ordinary_halt_retained": True,
        "c5_reconciled": False,
        "human_reviewed": False,
        "human_usefulness": None,
        "real_RAG_retrieval": False,
        "controlled_fixed_evidence": True,
        "answer_linked_guide_fixture_only": True,
        "resource_guidance": False,
        "renderer_ask_source_background": True,
        "renderer_concise_user_draft": True,
        "grounded_json_object": True,
        "original_fixture_gold_unchanged": True,
        "offline_payload_preflight": offline,
    }
    ids, pair_index = [], 0
    for round_number, case_order in enumerate(planned["case_order"], start=1):
        for case_id in case_order:
            name = f"enum-evidence-r{round_number}-{case_id}"
            jobs = [
                {
                    "job_id": f"r{round_number}:{case_id}:{arm}",
                    "case_id": case_id,
                    "arm": arm,
                    "round": round_number,
                    "decision_contracts": True,
                    "source_selection_reminder": True,
                    "ask_source_background": True,
                    "concise_user_draft": True,
                    "grounded_json_object": True,
                    "repair_repeated_queries": False,
                    "source_capacity": True,
                    "compact_plan": True,
                    "resource_guidance": False,
                    "max_output_tokens": 1024,
                    "input_token_reserve": 32768,
                }
                for arm in planned["paired_arm_order"][pair_index]
            ]
            batch = {
                "batch_id": name,
                "kind": "controlled_evidence",
                "scope_id": "user-core-enum-evidence-v1-" + name,
                "jobs": jobs,
            }
            slots = quality_slots(method, batch, fixtures)
            total = sum(slot.amount_usd for slot in slots)
            if len(slots) != 8 or total > Decimal("0.06"):
                raise ValueError("EnumEvidenceRegistrationRejected")
            batch.update(
                request_slots_sha256=slots_sha256(slots),
                max_request_slots=len(slots),
                worst_reserved_usd=str(total),
            )
            ids.extend(slot.request_id for slot in slots)
            method["batches"].append(batch)
            pair_index += 1
    if len(ids) != 48 or len(set(ids)) != 48 or len(method["batches"]) != 6:
        raise ValueError("EnumEvidenceRegistrationRejected")
    method["fresh_request_ids"] = ids
    method["fresh_scope_ids"] = [batch["scope_id"] for batch in method["batches"]]
    validate_fresh_identities(ledger_path, set(ids), set(method["fresh_scope_ids"]))
    return json.loads(json.dumps(method, default=str))


def preflight(root, ledger_path, method_path):
    method = json.loads(method_path.read_bytes())
    if method != build_method(root, ledger_path):
        raise ValueError("EnumEvidenceRegistrationRejected")
    observation = method["ledger_before"]
    if (
        not observation["halted"]
        or observation["counts"].get("reserved", 0)
        or observation["counts"].get("uncertain", 0) != 2
        or observation["limit_nanos"] != 4_500_000_000
    ):
        raise ValueError("EnumEvidenceRegistrationRejected")
    for name, digest in method["input_pins"].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or sha(path.read_bytes()) != digest:
            raise ValueError("EnumEvidenceRegistrationRejected")
    source = source_observation(root, method_path.relative_to(root), method["input_pins"])
    if not source["source_clean"]:
        raise ValueError("EnumEvidenceRegistrationRejected")
    validate_registered_inputs(root, method["protected_files"])
    return method, {
        **source,
        "method_sha256": sha(method_path.read_bytes()),
        "quarantine_before": method["quarantine_before"],
        "ledger_before": observation,
        "ledger_journal_before": method["ledger_journal_before"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--method", type=Path, default=ROOT / METHOD)
    parser.add_argument("--ledger", type=Path, default=ROOT / "runtime/budget.sqlite3")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    destination, secret, ledger, active = None, None, None, None
    active_digest, active_ref = None, None
    batches, registration = [], None
    try:
        if args.ledger.resolve() != (ROOT / "runtime/budget.sqlite3").resolve():
            raise ValueError("EnumEvidenceLedgerPathRejected")
        if args.method.resolve() != (ROOT / METHOD).resolve():
            raise ValueError("EnumEvidenceMethodPathRejected")
        if args.prepare:
            if args.live:
                raise ValueError("EnumEvidenceRegistrationRejected")
            write_new(
                args.method,
                build_method(ROOT, args.ledger),
            )
            print(json.dumps({"prepared": True, "actual_sends": 0}))
            return 0
        method, registration = preflight(ROOT, args.ledger, args.method)
        if not args.live:
            print(
                json.dumps(
                    {
                        "eligible_read_only": True,
                        "batches": len(method["batches"]),
                        "max_sends": sum(b["max_request_slots"] for b in method["batches"]),
                        "cap_usd": str(Decimal("0.06") * len(method["batches"])),
                        "actual_sends": 0,
                        "c5_reconciled": False,
                    }
                )
            )
            return 0
        if args.env_file is None or args.output_dir is None:
            raise ValueError("EnumEvidenceRegistrationRejected")
        candidate = args.output_dir.resolve()
        if candidate.is_relative_to(ROOT):
            raise ValueError("EnumEvidencePrivateOutputRequired")
        candidate.mkdir(parents=True, exist_ok=False, mode=0o700)
        destination = candidate
        write_new(destination / "registration.json", registration)
        if (
            not source_matches(
                registration,
                source_observation(ROOT, args.method.relative_to(ROOT), method["input_pins"]),
            )
            or ledger_observation(args.ledger) != method["ledger_before"]
        ):
            raise ValueError("EnumEvidenceRegistrationRejected")
        validate_registered_inputs(ROOT, method["protected_files"])
        validate_ledger_journal(
            args.ledger,
            method["ledger_journal_before"],
            set(method["fresh_request_ids"]),
            set(method["fresh_scope_ids"]),
        )
        validate_fresh_identities(
            args.ledger, set(method["fresh_request_ids"]), set(method["fresh_scope_ids"])
        )
        secret = credential(args.env_file)
        ledger = BudgetLedger(args.ledger)
        fixtures = fixtures_for(ROOT, {"protocol_id": "core-stability-v1"})
        definitions = load_user_gap_vocabulary(str(ROOT / VOCABULARY))
        packet = load_source_packet(ROOT / FOLDER / "source-packet-v1.json")
        if ledger_observation(args.ledger) != method["ledger_before"]:
            raise ValueError("EnumEvidenceRegistrationRejected")
        for batch in method["batches"]:
            if not source_matches(
                registration,
                source_observation(ROOT, args.method.relative_to(ROOT), method["input_pins"]),
            ):
                raise ValueError("EnumEvidenceRegistrationRejected")
            # Prior finite scopes can close, but no new uncertainty/history is silently accepted.
            observed = json.loads(json.dumps(asdict(ledger.quarantine_observation()), default=str))
            if observed != method["quarantine_before"]:
                break
            validate_registered_inputs(ROOT, method["protected_files"])
            validate_ledger_journal(
                args.ledger,
                method["ledger_journal_before"],
                set(method["fresh_request_ids"]),
                set(method["fresh_scope_ids"]),
            )
            slots = quality_slots(method, batch, fixtures)
            before = ledger_observation(args.ledger)
            scope_registration = {
                "method_sha256": registration["method_sha256"],
                "batch": batch,
                "source_commit": registration["source_commit"],
                "source_hashes": registration["source_hashes"],
                "ledger_before": before,
                "quarantine_before": observed,
            }
            digest = sha(json.dumps(scope_registration, sort_keys=True).encode())
            folder = destination / batch["batch_id"]
            folder.mkdir(mode=0o700)
            write_new(folder / "registration.json", scope_registration, secret)
            try:
                ledger.quarantine_scope_status(batch["scope_id"])
            except LedgerConflict:
                pass
            else:
                raise ValueError("EnumEvidenceScopeAlreadyRegistered")
            # Own cleanup before the committing call can be interrupted; close
            # only a registration with our exact digest/ref, never a foreign ID.
            active, active_digest, active_ref = (
                batch["scope_id"],
                digest,
                method["authorization_ref"],
            )
            ledger.authorize_quarantine_scope(
                authorization_id=batch["scope_id"],
                authorization_ref=method["authorization_ref"],
                expected_unknown_ids=tuple(observed["unknown_ids"]),
                expected_unknown_fingerprints=tuple(
                    tuple(pair) for pair in observed["unknown_fingerprints"]
                ),
                expected_meta_sha256=observed["meta_sha256"],
                expected_authorization_history_sha256=observed["authorization_history_sha256"],
                protocol_sha256=digest,
                request_slots=slots,
                additional_cap_usd=Decimal("0.06"),
                allow_full_context=True,
            )
            config = MetisConfig(
                api_key=secret,
                live_enabled=True,
                model="gpt-4o-mini",
                phase="development",
                response_mode="grounded_plan",
                continuation_id=active,
                grounded_decision_contracts=True,
                grounded_source_gap_handoff=True,
                grounded_source_gap_investigation=True,
                grounded_resource_guidance=False,
                input_token_reserve=32768,
                max_output_tokens=1024,
                max_request_usd=get_price("gpt-4o-mini").cost(32768, 1024),
            )
            checkpoints = []

            def checkpoint(
                value,
                checkpoints=checkpoints,
                folder=folder,
                scope_id=active,
                scope_digest=active_digest,
                scope_ref=active_ref,
            ):
                if value.get("event") == "reserved_before_transport":
                    if not source_matches(
                        registration,
                        source_observation(
                            ROOT, args.method.relative_to(ROOT), method["input_pins"]
                        ),
                    ):
                        raise ValueError("EnumEvidenceRegistrationRejected")
                    status = ledger.quarantine_scope_status(scope_id)
                    if (
                        status.protocol_sha256 != scope_digest
                        or status.authorization_ref != scope_ref
                        or json.loads(
                            json.dumps(asdict(ledger.quarantine_observation()), default=str)
                        )
                        != method["quarantine_before"]
                    ):
                        raise ValueError("EnumEvidenceRegistrationRejected")
                    validate_registered_inputs(ROOT, method["protected_files"])
                    journal = validate_ledger_journal(
                        args.ledger,
                        method["ledger_journal_before"],
                        set(method["fresh_request_ids"]),
                        set(method["fresh_scope_ids"]),
                    )
                    value = {
                        **value,
                        "ledger_before_transport": ledger_observation(args.ledger),
                        "ledger_journal_sha256": sha(json.dumps(journal, sort_keys=True).encode()),
                    }
                checkpoints.append(len(checkpoints))
                write_new(folder / f"checkpoint-{len(checkpoints):03d}.json", value, secret)

            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                records = []
                result = run_quality_batch(
                    method,
                    batch,
                    fixtures,
                    definitions,
                    ledger,
                    config,
                    before,
                    checkpoint=checkpoint,
                    retriever_factory=fixture_retriever_factory(packet, fixtures, records),
                )
            result["actual_fixed_evidence_calls"] = records
            result["json_object_wire_observed"] = (
                all(
                    send.get("wire_response_format") == "json_object"
                    for send in result["provider_sends"]
                )
                if result["provider_sends"]
                else None
            )
            result["real_RAG_retrieval"] = False
            result["controlled_fixed_evidence"] = True
            disposition = close_owned_scope(ledger, active, active_digest, active_ref)
            result["scope_disposition"] = json.loads(json.dumps(asdict(disposition), default=str))
            batches.append(result)
            write_new(folder / "receipt.json", result, secret)
            active = None
            print(
                json.dumps(
                    {
                        "batch": batch["batch_id"],
                        "visited_jobs": result["visited_jobs"],
                        "completed_routes": result["completed_routes"],
                        "actual_sends": result["actual_sends"],
                        "stopped_early": result["stopped_early"],
                    }
                ),
                flush=True,
            )
            if not batch_complete(result) or result["json_object_wire_observed"] is False:
                break
        validate_registered_inputs(ROOT, method["protected_files"])
        validate_ledger_journal(
            args.ledger,
            method["ledger_journal_before"],
            set(method["fresh_request_ids"]),
            set(method["fresh_scope_ids"]),
        )
        source_after = source_observation(ROOT, args.method.relative_to(ROOT), method["input_pins"])
        quarantine_preserved = (
            json.loads(json.dumps(asdict(ledger.quarantine_observation()), default=str))
            == method["quarantine_before"]
        )
        after = ledger_observation(args.ledger)
        no_pending = after["counts"].get("reserved", 0) == 0
        scopes_closed_cleanly = all(
            batch["scope_disposition"]["block_reason"] == "ExperimentClosed" for batch in batches
        )
        receipt = {
            "protocol_id": method["protocol_id"],
            "registration": registration,
            "method": method,
            "batches": batches,
            "completed_batches": len(batches),
            "planned_batches": len(method["batches"]),
            "ledger_after": after,
            "renderer_source_gap_investigation": True,
            "renderer_ask_source_background": True,
            "same_core_policy_both_arms": True,
            "evidence_dependent_source_count_bounds": True,
            "renderer_concise_user_draft": True,
            "grounded_json_object": True,
            "answer_linked_guide_fixture_only": True,
            "compact_plan": True,
            "source_capacity": True,
            "repair_repeated_queries": False,
            "resource_guidance": False,
            "old_journal_preserved": True,
            "old_holds_and_authorization_history_preserved": quarantine_preserved,
            "no_pending_reservations": no_pending,
            "own_scopes_closed_without_new_block": scopes_closed_cleanly,
            "real_RAG_retrieval": False,
            "controlled_fixed_evidence": True,
            "original_fixture_gold_unchanged": True,
            "held_out_test": False,
            "c5_reconciled": False,
            "human_reviewed": False,
            "human_usefulness": None,
            "source_after": source_after,
            "source_unchanged": source_matches(registration, source_after),
        }
        write_new(destination / "receipt.json", receipt, secret)
        print(
            json.dumps(
                {
                    "receipt_saved": True,
                    "completed_batches": len(batches),
                    "actual_sends": sum(b["actual_sends"] for b in batches),
                    "c5_reconciled": False,
                }
            )
        )
        return (
            0
            if len(batches) == len(method["batches"])
            and all(
                batch_complete(b) and b["json_object_wire_observed"] is not False for b in batches
            )
            and receipt["source_unchanged"]
            and quarantine_preserved
            and no_pending
            and scopes_closed_cleanly
            else 2
        )
    except BaseException:
        if destination is not None:
            disposition = None
            if active is not None and ledger is not None:
                try:
                    disposition = json.loads(
                        json.dumps(
                            asdict(close_owned_scope(ledger, active, active_digest, active_ref)),
                            default=str,
                        )
                    )
                except Exception:
                    disposition = {"status": "unknown; reservation retained"}
            try:
                write_new(
                    destination / "failure.json",
                    {
                        "error_code": "EnumEvidenceExperimentStopped",
                        "registration": registration,
                        "batches": batches,
                        "active_scope_disposition": disposition,
                        "ledger_after": ledger_observation(args.ledger),
                    },
                    secret,
                )
            except Exception:
                pass
        print(
            json.dumps(
                {"error_code": "EnumEvidenceExperimentStopped", "raw_diagnostics_exported": False}
            )
        )
        return 2
    finally:
        if active is not None and ledger is not None:
            try:
                status = close_owned_scope(ledger, active, active_digest, active_ref)
                if destination is not None:
                    write_new(
                        destination / "cleanup.json",
                        json.loads(json.dumps(asdict(status), default=str)),
                        secret,
                    )
            except BaseException:
                # Pending/uncertain reservations remain durable even if cleanup cannot finish.
                pass


if __name__ == "__main__":
    raise SystemExit(main())
