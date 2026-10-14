"""Prepare/read-only check first; --live consumes one frozen finite experiment."""

import argparse
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

from core_stability_probe import credential, write_new

from agent_app.llm.budget import BudgetLedger, LedgerConflict
from agent_app.llm.config import MetisConfig
from agent_app.llm.pricing import get_price
from agent_app.reasoning.catalog import load_user_gap_vocabulary
from agent_app.testing.dev_three_model_probe import ledger_observation, sha
from agent_app.testing.quality_probe import quality_slots, run_quality_batch
from agent_app.testing.stability_probe import (
    PACKET,
    VOCABULARY,
    fixtures_for,
    slots_sha256,
    source_observation,
)

ROOT = Path(__file__).resolve().parents[1]
FOLDER = Path("experiments/core_quality_followup")
METHOD = FOLDER / "live-method-v1.json"


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
        raise ValueError("QualityScopeOwnershipRejected")
    return ledger.close_quarantine_scope(scope_id)


def build_method(root, ledger_path):
    """No credentials, network or authorization; freeze jobs and observed holds."""
    adversarial = json.loads((root / FOLDER / "adversarial-live-protocol-v1.json").read_bytes())
    packet = json.loads((root / PACKET / "adversarial-packet-v1.json").read_bytes())
    conditions = {job["job_id"]: job for job in packet["jobs"]}
    batches = []
    for repetition, families in (
        (1, ("dev-case-a", "dev-case-b", "dev-case-c")),
        (2, ("dev-case-c", "dev-case-b", "dev-case-a")),
    ):
        arms = (("baseline_1024", 1024), ("candidate_2048", 2048))
        if repetition == 2:
            arms = tuple(reversed(arms))
        for case_id in families:
            name = f"cap-r{repetition}-{case_id}"
            batches.append(
                {
                    "batch_id": name,
                    "kind": "stability",
                    "scope_id": "user-core-quality-v1-" + name,
                    "jobs": [
                        {
                            "job_id": f"r{repetition}:{case_id}:{arm}",
                            "case_id": case_id,
                            "arm": arm,
                            "round": repetition,
                            "decision_contracts": True,
                            "max_output_tokens": bound,
                            "source_selection_reminder": False,
                        }
                        for arm, bound in arms
                    ],
                }
            )
    for index in range(2):
        jobs = []
        for job in adversarial["jobs"][index * 6 : (index + 1) * 6]:
            condition = conditions[job["condition_job_id"]]
            jobs.append(
                {
                    **job,
                    "round": job["condition_job_id"],
                    "max_output_tokens": 2048,
                    "conflict_groups": condition["conflict_groups"],
                    "catalog_overrides": condition["catalog_overrides"],
                }
            )
        name = f"adversarial-{index + 1}"
        batches.append(
            {
                "batch_id": name,
                "kind": "adversarial",
                "scope_id": "user-core-quality-v1-" + name,
                "jobs": jobs,
            }
        )
    pins = {
        path.relative_to(root).as_posix(): sha(path.read_bytes())
        for path in (root / "data/evaluation/dev-three-v1").rglob("*.json")
    }
    for name in (
        "output-cap-protocol-v1.json",
        "renderer-investigation-protocol-v1.json",
        "adversarial-live-protocol-v1.json",
        "quarantine-scope-protocol-v1.json",
        "public-pricing-observation-v1.json",
    ):
        path = root / FOLDER / name
        pins[path.relative_to(root).as_posix()] = sha(path.read_bytes())
    pins.update(adversarial["input_pins"])
    pins["scripts/core_quality_followup.py"] = sha(
        (root / "scripts/core_quality_followup.py").read_bytes()
    )
    observation = asdict(BudgetLedger(ledger_path).quarantine_observation())
    quarantine_policy = json.loads(
        (root / FOLDER / "quarantine-scope-protocol-v1.json").read_bytes()
    )
    if tuple(observation["unknown_ids"]) != tuple(quarantine_policy["known_uncertain_request_ids"]):
        raise ValueError("QualityRegistrationRejected")
    method = {
        "schema_version": 1,
        "protocol_id": "core-quality-followup-v1",
        "experiment_id": "core-quality-followup-2026-10-14-v1",
        "authorization_ref": "user-2026-10-14-deadline-extension-online-tests",
        "input_pins": pins,
        "baseline_main_commit": "9704fdcf69da640d6200a83902fb9ef9da2193ee",
        "registration_erratum": "The immutable adversarial subprotocol baseline_main_commit field records 1dc9476, a feature preregistration commit, not main. The actual baseline main is 9704fd here; no input, oracle, treatment or ordered job changed.",
        "renderer_source_gap_handoff": True,
        "renderer_source_gap_investigation": True,
        "model": "gpt-4o-mini",
        "scope_cap_usd": "0.06",
        "batches": batches,
        "quarantine_before": observation,
        "ledger_before": ledger_observation(ledger_path),
        "ordinary_halt_retained": True,
        "c5_reconciled": False,
        "stop_policy": "Any new uncertainty, overrun, changed quarantine/history, pending request or ledger failure stops all unvisited jobs. Do not re-register with another snapshot or retry spent identities.",
    }
    fixtures = fixtures_for(root, {"protocol_id": "new-fixed-evidence"})
    ids = []
    for batch in batches:
        slots = quality_slots(method, batch, fixtures)
        batch["request_slots_sha256"] = slots_sha256(slots)
        batch["max_request_slots"] = len(slots)
        batch["worst_reserved_usd"] = str(sum(slot.amount_usd for slot in slots))
        ids.extend(slot.request_id for slot in slots)
    if len(ids) != len(set(ids)):
        raise ValueError("QualityRegistrationRejected")
    return json.loads(json.dumps(method, default=str))


def preflight(root, ledger_path, method_path):
    method = json.loads(method_path.read_bytes())
    if method != build_method(root, ledger_path):
        raise ValueError("QualityRegistrationRejected")
    observation = method["ledger_before"]
    if (
        not observation["halted"]
        or observation["counts"].get("reserved", 0)
        or observation["counts"].get("uncertain", 0) != 2
        or observation["limit_nanos"] != 4_500_000_000
    ):
        raise ValueError("QualityRegistrationRejected")
    for name, digest in method["input_pins"].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or sha(path.read_bytes()) != digest:
            raise ValueError("QualityRegistrationRejected")
    # Original official source records remain pinned outside the model payload.
    evidence = json.loads((root / "data/evaluation/dev-three-v1/evidence-v1.json").read_bytes())
    for name, digest in evidence["source_pins"].items():
        path = (root / name).resolve()
        if (
            not path.is_relative_to((root / "streamlit-data-for-dev-test").resolve())
            or sha(path.read_bytes()) != digest
        ):
            raise ValueError("QualityRegistrationRejected")
    source = source_observation(root, method_path.relative_to(root), method["input_pins"])
    if not source["source_clean"]:
        raise ValueError("QualityRegistrationRejected")
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
            raise ValueError("QualityLedgerPathRejected")
        if args.prepare:
            if args.live:
                raise ValueError("QualityRegistrationRejected")
            write_new(args.method, build_method(ROOT, args.ledger))
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
                        "cap_usd": "0.48",
                        "actual_sends": 0,
                        "c5_reconciled": False,
                    }
                )
            )
            return 0
        if args.env_file is None or args.output_dir is None:
            raise ValueError("QualityRegistrationRejected")
        destination = args.output_dir.resolve()
        if destination.is_relative_to(ROOT):
            raise ValueError("QualityPrivateOutputRequired")
        destination.mkdir(parents=True, exist_ok=False, mode=0o700)
        write_new(destination / "registration.json", registration)
        if (
            not source_matches(
                registration,
                source_observation(ROOT, args.method.relative_to(ROOT), method["input_pins"]),
            )
            or ledger_observation(args.ledger) != method["ledger_before"]
        ):
            raise ValueError("QualityRegistrationRejected")
        secret = credential(args.env_file)
        ledger = BudgetLedger(args.ledger)
        fixtures = fixtures_for(ROOT, {"protocol_id": "new-fixed-evidence"})
        definitions = load_user_gap_vocabulary(str(ROOT / VOCABULARY))
        if ledger_observation(args.ledger) != method["ledger_before"]:
            raise ValueError("QualityRegistrationRejected")
        for batch in method["batches"]:
            if not source_matches(
                registration,
                source_observation(ROOT, args.method.relative_to(ROOT), method["input_pins"]),
            ):
                raise ValueError("QualityRegistrationRejected")
            # Prior finite scopes can close, but no new uncertainty/history is silently accepted.
            observed = json.loads(json.dumps(asdict(ledger.quarantine_observation()), default=str))
            if observed != method["quarantine_before"]:
                break
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
                raise ValueError("QualityScopeAlreadyRegistered")
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
                input_token_reserve=16384,
                max_output_tokens=2048,
                max_request_usd=get_price("gpt-4o-mini").cost(16384, 2048),
            )
            checkpoints = []

            def checkpoint(value, checkpoints=checkpoints, folder=folder):
                checkpoints.append(len(checkpoints))
                write_new(folder / f"checkpoint-{len(checkpoints):03d}.json", value, secret)

            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                result = run_quality_batch(
                    method,
                    batch,
                    fixtures,
                    definitions,
                    ledger,
                    config,
                    before,
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
                        "error_code": "QualityExperimentStopped",
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
                {"error_code": "QualityExperimentStopped", "raw_diagnostics_exported": False}
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
