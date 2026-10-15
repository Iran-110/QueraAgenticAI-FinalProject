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
from dev_rag_model_probe import (
    build_method as coverage_build_method,
)
from dev_rag_model_probe import (
    validate_registered_indexes as validate_coverage_indexes,
)

from agent_app.contracts import GroundedRequest, ReasoningContext
from agent_app.llm.budget import BudgetLedger, LedgerConflict
from agent_app.llm.config import MetisConfig
from agent_app.llm.metis import configured_grounded_messages
from agent_app.llm.pricing import get_price
from agent_app.reasoning.catalog import load_user_gap_vocabulary
from agent_app.testing.dev_three_model_probe import ledger_observation, sha
from agent_app.testing.quality_probe import quality_slots
from agent_app.testing.real_index_probe import run_real_index_batch, validate_index_bindings
from agent_app.testing.stability_probe import (
    VOCABULARY,
    fixtures_for,
    slots_sha256,
    source_observation,
)

ROOT = Path(__file__).resolve().parents[1]
COVERAGE_FOLDER = Path("experiments/dev_rag_coverage_v1")
FOLDER = Path("experiments/retrieval_relevance_v1")
METHOD = FOLDER / "live-method-v1.json"


def payload_preflight(root):
    """Check common compact wire on archived contexts, not new retrieval sufficiency."""
    paths = (
        COVERAGE_FOLDER / "model-live-receipt-v1.json",
        Path("experiments/core_resource_guidance_v1/model-live-receipt-v1.json"),
        Path("experiments/core_repeat_repair_v1/model-live-receipt-v1.json"),
        Path("experiments/core_source_capacity_v1/model-live-receipt-v1.json"),
    )
    sizes, count = [], 0
    config = MetisConfig(
        api_key="public-offline-preflight-placeholder",
        response_mode="grounded_plan",
        grounded_decision_contracts=True,
        grounded_source_selection_reminder=True,
        grounded_source_gap_handoff=True,
        grounded_source_gap_investigation=True,
        grounded_compact_plan=True,
    )
    for path in paths:
        original = json.loads((root / path).read_bytes())
        for batch in original["batches"]:
            for attempt in batch["attempts"]:
                request = GroundedRequest.model_validate(attempt["request"])
                context = ReasoningContext.model_validate(attempt["context"])
                repair = ReasoningContext.model_validate(
                    {
                        **context.model_dump(),
                        "attempt_index": 2,
                        "remaining_model_attempts": 0,
                        "can_refine": False,
                        "output_feedback": {"issues": [{"code": "invalid_grounded_plan"}]},
                    }
                )
                for variant in (context, repair):
                    messages = configured_grounded_messages(config, request, variant)
                    if json.loads(messages[1]["content"])["request"] != request.model_dump(
                        mode="json"
                    ):
                        raise ValueError("RelevancePayloadRejected")
                    size = len(json.dumps(messages, ensure_ascii=False).encode()) + 1024
                    if size > 32768:
                        raise ValueError("RelevancePayloadRejected")
                    sizes.append(size)
                count += 1
    if count != 107:
        raise ValueError("RelevancePayloadRejected")
    return {
        "accepted": True,
        "archived_actual_requests": count,
        "common_wire_size_checks": len(sizes),
        "max_utf8_with_margin": max(sizes),
        "guard": 32768,
        "compact_plan_both_arms": True,
        "source_capacity": False,
        "resource_guidance": False,
        "full_current_request_preserved": True,
        "actual_sends": 0,
        "future_unobserved_refinements_covered": False,
    }


def build_method(root, ledger_path):
    """Register native/candidate pairs on one verified corpus; identical core flags."""
    prior = coverage_build_method(root, ledger_path)
    protocol_path = FOLDER / "protocol-v1.json"
    protocol = json.loads((root / protocol_path).read_bytes())
    planned = protocol["live"]
    amendment_path = FOLDER / "whole-record-budget-amendment-v1.json"
    amendment = json.loads((root / amendment_path).read_bytes())
    if (
        amendment["registered_before_budget_implementation"] is not True
        or amendment["registered_before_paid_comparison"] is not True
        or amendment["original_protocol_sha256"] != sha((root / protocol_path).read_bytes())
        or amendment["offline_diagnosis_sha256"]
        != sha((root / FOLDER / "offline-candidates-before-packing-v1.json").read_bytes())
        or amendment["evidence_utf8_budget_bytes"] != 12000
    ):
        raise ValueError("RelevanceRegistrationRejected")
    if (
        protocol["protocol_id"] != "retrieval-relevance-v1"
        or protocol["registered_before_implementation"] is not True
        or planned["arms"] != ["native_top5", "candidate_relevance"]
        or planned["rounds"] != 2
        or planned["cases"] != ["dev-case-a", "dev-case-b", "dev-case-c"]
        or planned["jobs"] != 12
        or planned["turns"] != 24
        or planned["fresh_request_slots"] != 48
        or planned["model"] != "gpt-4o-mini"
        or planned["max_output_tokens"] != 1024
        or planned["input_token_reserve"] != 32768
        or planned["scope_cap_usd"] != "0.06"
        or planned["campaign_cap_usd"] != "0.36"
        or protocol["treatment"]["engine_candidate_multiplier"] != 5
        or protocol["treatment"]["candidate_cap"] != 50
        or protocol["treatment"]["final_top_k"] != 5
    ):
        raise ValueError("RelevanceRegistrationRejected")
    method = {
        **prior,
        "protocol_id": "retrieval-relevance-model-v1",
        "experiment_id": "retrieval-relevance-2026-10-15-v1",
        "authorization_ref": "user-2026-10-15-retrieval-relevance",
        "baseline_main_commit": protocol["baseline_commit"],
        "baseline_model_receipt": "experiments/dev_rag_coverage_v1/model-live-receipt-v1.json",
        "treatment_protocol": protocol,
        "treatment_amendment": amendment,
        "offline_payload_preflight": payload_preflight(root),
    }
    pins = method["input_pins"]
    for name in (
        protocol_path.as_posix(),
        amendment_path.as_posix(),
        "experiments/retrieval_relevance_v1/offline-candidates-before-packing-v1.json",
        "experiments/retrieval_relevance_v1/offline-candidate-replay-v1.json",
        "scripts/retrieval_relevance_offline_probe.py",
        "experiments/retrieval_relevance_v1/semantic-review-preparation-v1.json",
        "docs/pr55-evidence-review.fa.md",
        "scripts/retrieval_relevance_model_probe.py",
        "scripts/core_repeat_model_probe.py",
        "scripts/core_compact_model_probe.py",
        "experiments/core_compact_plan_v1/model-live-receipt-v1.json",
        "scripts/core_source_capacity_model_probe.py",
        "experiments/core_source_capacity_v1/model-live-receipt-v1.json",
        "experiments/core_repeat_repair_v1/model-live-receipt-v1.json",
        "experiments/dev_rag_coverage_v1/model-live-receipt-v1.json",
        "experiments/core_resource_guidance_v1/model-live-receipt-v1.json",
    ):
        pins[name] = sha((root / name).read_bytes())
    arms = ("native_top5", "candidate_relevance")
    binding = prior["indexes"]["new_18_sources"]
    method["indexes"] = {arm: dict(binding) for arm in arms}
    method["retrieval_scope"]["same_index_both_arms"] = True
    method["batches"] = []
    method["ledger_journal_before"] = ledger_journal_snapshot(ledger_path)
    method["campaign_scope_cap_usd"] = "0.36"
    method["resource_guidance"] = False
    fixtures = fixtures_for(root, {"protocol_id": "core-stability-v1"})
    ids = []
    for old_batch in prior["batches"]:
        name = old_batch["batch_id"].replace("index-", "relevance-")
        jobs = []
        for old_job in old_batch["jobs"]:
            enabled = old_job["arm"] == "new_18_sources"
            arm = arms[int(enabled)]
            job = {
                **old_job,
                "arm": arm,
                "repair_repeated_queries": True,
                "source_capacity": False,
                "compact_plan": True,
                "retrieval_candidate_multiplier": 5 if enabled else 1,
                "record_native_candidates": True,
                "evidence_utf8_budget_bytes": 12000 if enabled else None,
                "retrieval_selection_policy": "query_relevance_v1" if enabled else "native",
                "resource_guidance": False,
            }
            job["job_id"] = f"r{job['round']}:{job['case_id']}:{arm}"
            jobs.append(job)
        batch = {
            **old_batch,
            "batch_id": name,
            "scope_id": "user-rag-relevance-v1-" + name,
            "jobs": jobs,
        }
        slots = quality_slots(method, batch, fixtures)
        batch["request_slots_sha256"] = slots_sha256(slots)
        batch["max_request_slots"] = len(slots)
        batch["worst_reserved_usd"] = str(sum(slot.amount_usd for slot in slots))
        ids.extend(slot.request_id for slot in slots)
        method["batches"].append(batch)
    if len(ids) != 48 or len(set(ids)) != 48:
        raise ValueError("RelevanceRegistrationRejected")
    method["fresh_request_ids"] = ids
    method["fresh_scope_ids"] = [batch["scope_id"] for batch in method["batches"]]
    validate_fresh_identities(ledger_path, set(ids), set(method["fresh_scope_ids"]))
    validate_registered_indexes(root, method["indexes"])
    return json.loads(json.dumps(method, default=str))


def validate_registered_indexes(root, indexes):
    """The two treatment arms must use the identical native18/36 binding."""
    try:
        if type(indexes) is not dict or set(indexes) != {
            "native_top5",
            "candidate_relevance",
        }:
            raise ValueError
        receipt = json.loads((root / COVERAGE_FOLDER / "index-receipt-v1.json").read_bytes())
        coverage = {
            arm: receipt["indexes"][arm] for arm in ("historical_14_sources", "new_18_sources")
        }
        checked = validate_coverage_indexes(root, coverage)
        expected = checked["new_18_sources"]
        if any(binding != expected for binding in indexes.values()):
            raise ValueError
        return validate_index_bindings(indexes)
    except Exception:
        raise ValueError("RelevanceRegistrationRejected") from None


def preflight(root, ledger_path, method_path):
    method = json.loads(method_path.read_bytes())
    if method != build_method(root, ledger_path):
        raise ValueError("RelevanceRegistrationRejected")
    observation = method["ledger_before"]
    if (
        not observation["halted"]
        or observation["counts"].get("reserved", 0)
        or observation["counts"].get("uncertain", 0) != 2
        or observation["limit_nanos"] != 4_500_000_000
    ):
        raise ValueError("RelevanceRegistrationRejected")
    for name, digest in method["input_pins"].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or sha(path.read_bytes()) != digest:
            raise ValueError("RelevanceRegistrationRejected")
    source = source_observation(root, method_path.relative_to(root), method["input_pins"])
    if not source["source_clean"]:
        raise ValueError("RelevanceRegistrationRejected")
    validate_registered_indexes(root, method["indexes"])
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
            raise ValueError("RelevanceLedgerPathRejected")
        if args.prepare:
            if args.live:
                raise ValueError("RelevanceRegistrationRejected")
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
            raise ValueError("RelevanceRegistrationRejected")
        candidate = args.output_dir.resolve()
        if candidate.is_relative_to(ROOT):
            raise ValueError("RelevancePrivateOutputRequired")
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
            raise ValueError("RelevanceRegistrationRejected")
        validate_registered_indexes(ROOT, method["indexes"])
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
        if ledger_observation(args.ledger) != method["ledger_before"]:
            raise ValueError("RelevanceRegistrationRejected")
        for batch in method["batches"]:
            if not source_matches(
                registration,
                source_observation(ROOT, args.method.relative_to(ROOT), method["input_pins"]),
            ):
                raise ValueError("RelevanceRegistrationRejected")
            # Prior finite scopes can close, but no new uncertainty/history is silently accepted.
            observed = json.loads(json.dumps(asdict(ledger.quarantine_observation()), default=str))
            if observed != method["quarantine_before"]:
                break
            validate_registered_indexes(ROOT, method["indexes"])
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
                raise ValueError("RelevanceScopeAlreadyRegistered")
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
                        raise ValueError("RelevanceRegistrationRejected")
                    status = ledger.quarantine_scope_status(scope_id)
                    if (
                        status.protocol_sha256 != scope_digest
                        or status.authorization_ref != scope_ref
                        or json.loads(
                            json.dumps(asdict(ledger.quarantine_observation()), default=str)
                        )
                        != method["quarantine_before"]
                    ):
                        raise ValueError("RelevanceRegistrationRejected")
                    validate_registered_indexes(ROOT, method["indexes"])
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
                result = run_real_index_batch(
                    method,
                    batch,
                    fixtures,
                    definitions,
                    ledger,
                    config,
                    before,
                    method["indexes"],
                    checkpoint=checkpoint,
                )
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
            if not batch_complete(result):
                break
        validate_registered_indexes(ROOT, method["indexes"])
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
            "retrieval_relevance_comparison": True,
            "compact_plan_both_arms": True,
            "source_capacity": False,
            "repair_repeated_queries": True,
            "resource_guidance": False,
            "old_journal_preserved": True,
            "old_holds_and_authorization_history_preserved": quarantine_preserved,
            "no_pending_reservations": no_pending,
            "own_scopes_closed_without_new_block": scopes_closed_cleanly,
            "same_native_index_both_arms": True,
            "real_index_retrieval": True,
            "embedding": "lexical_hash_v1",
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
            and all(batch_complete(b) for b in batches)
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
                        "error_code": "RelevanceExperimentStopped",
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
                {"error_code": "RelevanceExperimentStopped", "raw_diagnostics_exported": False}
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
