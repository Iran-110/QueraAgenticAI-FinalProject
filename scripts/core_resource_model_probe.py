"""Prepare/read-only check first; --live consumes one frozen finite experiment."""

import argparse
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

from core_stability_probe import credential, write_new
from dev_rag_model_probe import (
    build_method as coverage_build_method,
)
from dev_rag_model_probe import (
    validate_registered_indexes as validate_coverage_indexes,
)

from agent_app.contracts import GroundedRequest, ReasoningContext
from agent_app.llm.budget import BudgetLedger, LedgerConflict
from agent_app.llm.config import MetisConfig
from agent_app.llm.pricing import get_price
from agent_app.reasoning.catalog import load_user_gap_vocabulary
from agent_app.reasoning.grounding import build_grounded_messages
from agent_app.reasoning.resource_guidance import add_resource_guidance
from agent_app.reasoning.source_selection import add_source_selection_reminder
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
FOLDER = Path("experiments/core_resource_guidance_v1")
METHOD = FOLDER / "live-method-v2.json"


def payload_preflight(root):
    """Check archived actual requests and repair-capacity variants without calls.

    This covers observed inputs, not every possible future retrieval result;
    the same UTF-8 bound remains enforced before each actual reservation.
    """
    original = json.loads((root / COVERAGE_FOLDER / "model-live-receipt-v1.json").read_bytes())
    rows = []
    for batch in original["batches"]:
        for attempt in batch["attempts"]:
            request = GroundedRequest.model_validate(attempt["request"])
            context = ReasoningContext.model_validate(attempt["context"])
            variants = (
                context,
                ReasoningContext.model_validate(
                    {
                        **context.model_dump(),
                        "attempt_index": 2,
                        "remaining_model_attempts": 0,
                        "can_refine": False,
                        "output_feedback": {"issues": [{"code": "grounded_render_too_large"}]},
                    }
                ),
            )
            for variant in variants:
                base = add_source_selection_reminder(
                    build_grounded_messages(request, variant, decision_contracts=True), True
                )
                guided = add_resource_guidance(
                    base,
                    request,
                    enabled=True,
                    source_gap_handoff=True,
                    source_gap_investigation=True,
                )
                sizes = [
                    len(json.dumps(messages, ensure_ascii=False).encode()) + 1024
                    for messages in (base, guided)
                ]
                if any(size > 32768 for size in sizes):
                    raise ValueError("ResourcePayloadRejected")
                rows.append(sizes)
    if len(rows) != 58:
        raise ValueError("ResourcePayloadRejected")
    return {
        "accepted": True,
        "archived_actual_requests": 29,
        "observed_and_repair_contexts": len(rows),
        "message_size_checks": len(rows) * 2,
        "max_baseline_utf8_with_margin": max(row[0] for row in rows),
        "max_treatment_utf8_with_margin": max(row[1] for row in rows),
        "guard": 32768,
        "full_current_sources_preserved": True,
        "future_unobserved_refinements_covered": False,
        "actual_sends": 0,
    }


def source_matches(registration, current):
    return current == {
        key: registration[key] for key in ("source_commit", "source_clean", "source_hashes")
    }


def batch_complete(batch):
    return (
        batch["original_accounting_preserved"]
        and not batch["stopped_early"]
        and batch["accounting"]["accounting_complete"]
        and batch["visited_jobs"] == batch["planned_jobs"]
    )


def close_owned_scope(ledger, scope_id, protocol_sha256, authorization_ref):
    status = ledger.quarantine_scope_status(scope_id)
    if status.protocol_sha256 != protocol_sha256 or status.authorization_ref != authorization_ref:
        raise ValueError("ResourceScopeOwnershipRejected")
    return ledger.close_quarantine_scope(scope_id)


def build_method(root, ledger_path):
    """Register OFF/ON pairs on one verified corpus; no new source selection."""
    prior = coverage_build_method(root, ledger_path)
    protocol_path = FOLDER / "protocol-v1.json"
    protocol = json.loads((root / protocol_path).read_bytes())
    if protocol["protocol_id"] != "core-resource-guidance-v1":
        raise ValueError("ResourceRegistrationRejected")
    method = {
        **prior,
        "protocol_id": "core-resource-guidance-model-v1",
        "experiment_id": "core-resource-guidance-2026-10-14-v1",
        "authorization_ref": "user-2026-10-14-course-core-evaluation-followup",
        "baseline_main_commit": protocol["baseline_commit"],
        "baseline_model_receipt": "experiments/dev_rag_coverage_v1/model-live-receipt-v1.json",
        "treatment_protocol": protocol,
        "offline_payload_preflight": payload_preflight(root),
    }
    pins = method["input_pins"]
    for name in (
        protocol_path.as_posix(),
        "scripts/core_resource_model_probe.py",
        "experiments/dev_rag_coverage_v1/model-live-receipt-v1.json",
        (FOLDER / "live-method-v1.json").as_posix(),
    ):
        pins[name] = sha((root / name).read_bytes())
    arms = ("resource_guidance_off", "resource_guidance_on")
    binding = prior["indexes"]["new_18_sources"]
    if binding["snapshot_id"] != protocol["planned_model_method"]["index_for_both_arms"]:
        raise ValueError("ResourceRegistrationRejected")
    method["indexes"] = {arm: dict(binding) for arm in arms}
    method["retrieval_scope"]["same_index_both_arms"] = True
    method["batches"] = []
    fixtures = fixtures_for(root, {"protocol_id": "core-stability-v1"})
    ids = []
    for old_batch in prior["batches"]:
        name = old_batch["batch_id"].replace("index-", "resource-")
        jobs = []
        for old_job in old_batch["jobs"]:
            enabled = old_job["arm"] == "new_18_sources"
            arm = arms[int(enabled)]
            job = {**old_job, "arm": arm, "resource_guidance": enabled}
            job["job_id"] = f"r{job['round']}:{job['case_id']}:{arm}"
            jobs.append(job)
        batch = {
            **old_batch,
            "batch_id": name,
            "scope_id": "user-core-resource-v1-" + name,
            "jobs": jobs,
        }
        slots = quality_slots(method, batch, fixtures)
        batch["request_slots_sha256"] = slots_sha256(slots)
        batch["max_request_slots"] = len(slots)
        batch["worst_reserved_usd"] = str(sum(slot.amount_usd for slot in slots))
        ids.extend(slot.request_id for slot in slots)
        method["batches"].append(batch)
    if len(ids) != 48 or len(set(ids)) != 48:
        raise ValueError("ResourceRegistrationRejected")
    validate_registered_indexes(root, method["indexes"])
    return json.loads(json.dumps(method, default=str))


def validate_registered_indexes(root, indexes):
    """The two treatment arms must use the identical native18/36 binding."""
    try:
        if type(indexes) is not dict or set(indexes) != {
            "resource_guidance_off",
            "resource_guidance_on",
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
        raise ValueError("ResourceRegistrationRejected") from None


def preflight(root, ledger_path, method_path):
    method = json.loads(method_path.read_bytes())
    if method != build_method(root, ledger_path):
        raise ValueError("ResourceRegistrationRejected")
    observation = method["ledger_before"]
    if (
        not observation["halted"]
        or observation["counts"].get("reserved", 0)
        or observation["counts"].get("uncertain", 0) != 2
        or observation["limit_nanos"] != 4_500_000_000
    ):
        raise ValueError("ResourceRegistrationRejected")
    for name, digest in method["input_pins"].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or sha(path.read_bytes()) != digest:
            raise ValueError("ResourceRegistrationRejected")
    source = source_observation(root, method_path.relative_to(root), method["input_pins"])
    if not source["source_clean"]:
        raise ValueError("ResourceRegistrationRejected")
    validate_registered_indexes(root, method["indexes"])
    return method, {
        **source,
        "method_sha256": sha(method_path.read_bytes()),
        "quarantine_before": method["quarantine_before"],
        "ledger_before": observation,
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
            raise ValueError("ResourceLedgerPathRejected")
        if args.prepare:
            if args.live:
                raise ValueError("ResourceRegistrationRejected")
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
            raise ValueError("ResourceRegistrationRejected")
        destination = args.output_dir.resolve()
        if destination.is_relative_to(ROOT):
            raise ValueError("ResourcePrivateOutputRequired")
        destination.mkdir(parents=True, exist_ok=False, mode=0o700)
        write_new(destination / "registration.json", registration)
        if (
            not source_matches(
                registration,
                source_observation(ROOT, args.method.relative_to(ROOT), method["input_pins"]),
            )
            or ledger_observation(args.ledger) != method["ledger_before"]
        ):
            raise ValueError("ResourceRegistrationRejected")
        validate_registered_indexes(ROOT, method["indexes"])
        secret = credential(args.env_file)
        ledger = BudgetLedger(args.ledger)
        fixtures = fixtures_for(ROOT, {"protocol_id": "core-stability-v1"})
        definitions = load_user_gap_vocabulary(str(ROOT / VOCABULARY))
        if ledger_observation(args.ledger) != method["ledger_before"]:
            raise ValueError("ResourceRegistrationRejected")
        for batch in method["batches"]:
            if not source_matches(
                registration,
                source_observation(ROOT, args.method.relative_to(ROOT), method["input_pins"]),
            ):
                raise ValueError("ResourceRegistrationRejected")
            # Prior finite scopes can close, but no new uncertainty/history is silently accepted.
            observed = json.loads(json.dumps(asdict(ledger.quarantine_observation()), default=str))
            if observed != method["quarantine_before"]:
                break
            validate_registered_indexes(ROOT, method["indexes"])
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
                raise ValueError("ResourceScopeAlreadyRegistered")
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
                input_token_reserve=32768,
                max_output_tokens=1024,
                max_request_usd=get_price("gpt-4o-mini").cost(32768, 1024),
            )
            checkpoints = []

            def checkpoint(value, checkpoints=checkpoints, folder=folder):
                if value.get("event") == "reserved_before_transport":
                    if not source_matches(
                        registration,
                        source_observation(
                            ROOT, args.method.relative_to(ROOT), method["input_pins"]
                        ),
                    ):
                        raise ValueError("ResourceRegistrationRejected")
                    validate_registered_indexes(ROOT, method["indexes"])
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
        source_after = source_observation(ROOT, args.method.relative_to(ROOT), method["input_pins"])
        receipt = {
            "protocol_id": method["protocol_id"],
            "registration": registration,
            "method": method,
            "batches": batches,
            "completed_batches": len(batches),
            "planned_batches": len(method["batches"]),
            "ledger_after": ledger_observation(args.ledger),
            "renderer_source_gap_investigation": True,
            "resource_guidance_comparison": True,
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
                        "error_code": "ResourceExperimentStopped",
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
                {"error_code": "ResourceExperimentStopped", "raw_diagnostics_exported": False}
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
