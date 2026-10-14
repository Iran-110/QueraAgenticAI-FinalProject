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
from agent_app.retrieval.offline_index import open_verified_index
from agent_app.retrieval.pilot_corpus import build_pilot_corpus
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
FOLDER = Path("experiments/dev_rag_coverage_v1")
METHOD = FOLDER / "live-method-v1.json"


def validate_registered_indexes(root, indexes):
    """Bind both arm names to their actual frozen corpus, before credentials."""
    root = Path(root).resolve()
    try:
        arms = ("historical_14_sources", "new_18_sources")
        if type(indexes) is not dict or set(indexes) != set(arms):
            raise ValueError
        bindings = validate_index_bindings(indexes)
        if len({Path(binding["path"]).resolve() for binding in bindings.values()}) != 2:
            raise ValueError
        profiles = {
            arms[0]: (
                root / "data/evaluation/dev-three-v1/split-manifest.json",
                root / "experiments/corpus/pilot-allowlist.json",
                "docs-only-local-pilot-v1",
                14,
                30,
            ),
            arms[1]: (
                root / FOLDER / "split-manifest.json",
                root / FOLDER / "allowlist.json",
                "docs-only-dev-coverage-v1",
                18,
                36,
            ),
        }
        for arm, (split, allowlist, protocol, sources, chunks) in profiles.items():
            expected = build_pilot_corpus(root / "streamlit-data-for-dev-test", split, allowlist)
            client, snapshot = open_verified_index(bindings[arm]["path"])
            actual = client.manifest
            if (
                snapshot != bindings[arm]["snapshot_id"]
                or actual != expected.manifest
                or actual["corpus"]["protocol"] != protocol
                or len(actual["corpus"]["sources"]) != sources
                or len(actual["corpus"]["chunks"]) != chunks
            ):
                raise ValueError
        return bindings
    except Exception:
        raise ValueError("RealIndexRegistrationRejected") from None


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
        raise ValueError("RealIndexScopeOwnershipRejected")
    return ledger.close_quarantine_scope(scope_id)


def build_method(root, ledger_path):
    """Freeze all six old/new pairs, actual index bindings and unchanged holds."""
    protocol = json.loads((root / FOLDER / "protocol-v1.json").read_bytes())
    receipt = json.loads((root / FOLDER / "index-receipt-v1.json").read_bytes())
    if protocol["protocol_id"] != "dev-real-rag-coverage-v1" or receipt["accepted"] is not True:
        raise ValueError("RealIndexRegistrationRejected")
    indexes = {arm: receipt["indexes"][arm] for arm in ("historical_14_sources", "new_18_sources")}
    if receipt["index_counts"]["historical_14_sources"] != {
        "source_count": 14,
        "chunk_count": 30,
    } or receipt["index_counts"]["new_18_sources"] != {"source_count": 18, "chunk_count": 36}:
        raise ValueError("RealIndexRegistrationRejected")
    validate_registered_indexes(root, indexes)
    pins = dict(protocol["unchanged_input_sha256"])
    for name in (
        "protocol-v1.json",
        "input-bound-amendment-v1.json",
        "allowlist.json",
        "split-manifest.json",
        "index-receipt-v1.json",
    ):
        relative = (FOLDER / name).as_posix()
        pins[relative] = sha((root / relative).read_bytes())
    for name in ("scripts/dev_rag_model_probe.py", "scripts/dev_rag_coverage_acceptance.py"):
        pins[name] = sha((root / name).read_bytes())
    for name, digest in protocol["unchanged_input_sha256"].items():
        if sha((root / name).read_bytes()) != digest:
            raise ValueError("RealIndexRegistrationRejected")
    observed = asdict(BudgetLedger(ledger_path).quarantine_observation())
    old = json.loads(
        (root / "experiments/core_quality_followup/quarantine-scope-protocol-v1.json").read_bytes()
    )
    if tuple(observed["unknown_ids"]) != tuple(old["known_uncertain_request_ids"]):
        raise ValueError("RealIndexRegistrationRejected")
    method = {
        "schema_version": 1,
        "protocol_id": "dev-real-index-model-v1",
        "experiment_id": "dev-real-index-model-2026-10-14-v1",
        "authorization_ref": "user-2026-10-14-build-four-sources-real-retrieval-online-tests",
        "baseline_main_commit": protocol["baseline_commit"],
        "input_pins": pins,
        "indexes": indexes,
        "batches": [],
        "model": "gpt-4o-mini",
        "scope_cap_usd": "0.06",
        "allow_full_context": True,
        "quarantine_before": observed,
        "ledger_before": ledger_observation(ledger_path),
        "ordinary_halt_retained": True,
        "c5_reconciled": False,
        "human_reviewed": False,
        "human_usefulness": None,
        "retrieval_scope": protocol["retrieval"],
        "stop_policy": protocol["model_method"][
            "stop_entire_campaign_on_new_uncertainty_or_changed_source_index_inputs_accounting"
        ],
    }
    families = ("dev-case-a", "dev-case-b", "dev-case-c")
    arms = ("historical_14_sources", "new_18_sources")
    fixtures = fixtures_for(root, {"protocol_id": "core-stability-v1"})
    ids = []
    for round_number in (1, 2):
        for case_id in families if round_number == 1 else tuple(reversed(families)):
            order = arms if case_id != "dev-case-b" else tuple(reversed(arms))
            if round_number == 2:
                order = tuple(reversed(order))
            name = f"index-r{round_number}-{case_id}"
            batch = {
                "batch_id": name,
                "kind": "real_index",
                "scope_id": "user-dev-real-index-v1-" + name,
                "jobs": [
                    {
                        "job_id": f"r{round_number}:{case_id}:{arm}",
                        "case_id": case_id,
                        "arm": arm,
                        "round": round_number,
                        "decision_contracts": True,
                        "source_selection_reminder": True,
                        "max_output_tokens": 1024,
                        "input_token_reserve": 32768,
                    }
                    for arm in order
                ],
            }
            validate_registered_indexes(root, method["indexes"])
            slots = quality_slots(method, batch, fixtures)
            batch["request_slots_sha256"] = slots_sha256(slots)
            batch["max_request_slots"] = len(slots)
            batch["worst_reserved_usd"] = str(sum(slot.amount_usd for slot in slots))
            ids.extend(slot.request_id for slot in slots)
            method["batches"].append(batch)
    if len(ids) != 48 or len(set(ids)) != 48:
        raise ValueError("RealIndexRegistrationRejected")
    return json.loads(json.dumps(method, default=str))


def preflight(root, ledger_path, method_path):
    method = json.loads(method_path.read_bytes())
    if method != build_method(root, ledger_path):
        raise ValueError("RealIndexRegistrationRejected")
    observation = method["ledger_before"]
    if (
        not observation["halted"]
        or observation["counts"].get("reserved", 0)
        or observation["counts"].get("uncertain", 0) != 2
        or observation["limit_nanos"] != 4_500_000_000
    ):
        raise ValueError("RealIndexRegistrationRejected")
    for name, digest in method["input_pins"].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or sha(path.read_bytes()) != digest:
            raise ValueError("RealIndexRegistrationRejected")
    source = source_observation(root, method_path.relative_to(root), method["input_pins"])
    if not source["source_clean"]:
        raise ValueError("RealIndexRegistrationRejected")
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
            raise ValueError("RealIndexLedgerPathRejected")
        if args.prepare:
            if args.live:
                raise ValueError("RealIndexRegistrationRejected")
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
            raise ValueError("RealIndexRegistrationRejected")
        destination = args.output_dir.resolve()
        if destination.is_relative_to(ROOT):
            raise ValueError("RealIndexPrivateOutputRequired")
        destination.mkdir(parents=True, exist_ok=False, mode=0o700)
        write_new(destination / "registration.json", registration)
        if (
            not source_matches(
                registration,
                source_observation(ROOT, args.method.relative_to(ROOT), method["input_pins"]),
            )
            or ledger_observation(args.ledger) != method["ledger_before"]
        ):
            raise ValueError("RealIndexRegistrationRejected")
        validate_registered_indexes(ROOT, method["indexes"])
        secret = credential(args.env_file)
        ledger = BudgetLedger(args.ledger)
        fixtures = fixtures_for(ROOT, {"protocol_id": "core-stability-v1"})
        definitions = load_user_gap_vocabulary(str(ROOT / VOCABULARY))
        if ledger_observation(args.ledger) != method["ledger_before"]:
            raise ValueError("RealIndexRegistrationRejected")
        for batch in method["batches"]:
            if not source_matches(
                registration,
                source_observation(ROOT, args.method.relative_to(ROOT), method["input_pins"]),
            ):
                raise ValueError("RealIndexRegistrationRejected")
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
                raise ValueError("RealIndexScopeAlreadyRegistered")
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
                        raise ValueError("RealIndexRegistrationRejected")
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
                        "error_code": "RealIndexExperimentStopped",
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
                {"error_code": "RealIndexExperimentStopped", "raw_diagnostics_exported": False}
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
