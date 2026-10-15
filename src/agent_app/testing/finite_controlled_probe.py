"""Finite controlled-study lifecycle with explicit, testable dependency seams.

A new study supplies immutable registration and evidence callbacks. Shared controls
retain exact journal ownership, transport checkpoints and conservative cleanup;
this module never resolves credentials, a ledger or a provider on import.
"""

import argparse
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path


def actual_json_wire_observation(result):
    """Only an actual outbound send observes a wire format, never a checkpoint.

    Transport records can exist before the on-send guard; all zero-send states
    therefore report null. Inconsistent counters fail conservatively rather than
    treating a missing/unfinished observation as a successful JSON request.
    """
    records, count = result["provider_sends"], result["actual_sends"]
    if (
        type(records) is not list
        or type(count) is not int
        or count < 0
        or any(
            type(row) is not dict or type(row.get("http_send_started")) is not bool
            for row in records
        )
    ):
        raise ValueError("FiniteWireObservationRejected")
    sent = [row for row in records if row["http_send_started"]]
    if len(sent) != count:
        raise ValueError("FiniteWireObservationRejected")
    return all(row.get("wire_response_format") == "json_object" for row in sent) if sent else None


def run_finite_cli(
    h,
    argv=None,
    *,
    wire_observer=actual_json_wire_observation,
):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--method", type=Path, default=h.ROOT / h.METHOD)
    parser.add_argument("--ledger", type=Path, default=h.ROOT / "runtime/budget.sqlite3")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    destination, secret, ledger, active = (None, None, None, None)
    active_digest, active_ref = (None, None)
    batches, registration, method = ([], None, None)
    try:
        if not callable(wire_observer):
            raise ValueError("FiniteRegistrationRejected")
        if args.ledger.resolve() != (h.ROOT / "runtime/budget.sqlite3").resolve():
            raise ValueError(h.ERROR_PREFIX + "LedgerPathRejected")
        if args.method.resolve() != (h.ROOT / h.METHOD).resolve():
            raise ValueError(h.ERROR_PREFIX + "MethodPathRejected")
        if args.prepare:
            if args.live:
                raise ValueError(h.ERROR_PREFIX + "RegistrationRejected")
            h.write_new(args.method, h.build_method(h.ROOT, args.ledger))
            print(json.dumps({"prepared": True, "actual_sends": 0}))
            return 0
        method, registration = h.preflight(h.ROOT, args.ledger, args.method)
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
            raise ValueError(h.ERROR_PREFIX + "RegistrationRejected")
        candidate = args.output_dir.resolve()
        if candidate.is_relative_to(h.ROOT):
            raise ValueError(h.ERROR_PREFIX + "PrivateOutputRequired")
        candidate.mkdir(parents=True, exist_ok=False, mode=448)
        destination = candidate
        h.write_new(destination / "registration.json", registration)
        if (
            not h.source_matches(
                registration,
                h.source_observation(h.ROOT, args.method.relative_to(h.ROOT), method["input_pins"]),
            )
            or h.ledger_observation(args.ledger) != method["ledger_before"]
        ):
            raise ValueError(h.ERROR_PREFIX + "RegistrationRejected")
        h.validate_registered_inputs(h.ROOT, method["protected_files"])
        h.validate_ledger_journal(
            args.ledger,
            method["ledger_journal_before"],
            set(method["fresh_request_ids"]),
            set(method["fresh_scope_ids"]),
        )
        h.validate_fresh_identities(
            args.ledger, set(method["fresh_request_ids"]), set(method["fresh_scope_ids"])
        )
        secret = h.credential(args.env_file)
        ledger = h.BudgetLedger(args.ledger)
        fixtures = h.fixtures_for(h.ROOT, {"protocol_id": "core-stability-v1"})
        definitions = h.load_user_gap_vocabulary(str(h.ROOT / h.VOCABULARY))
        packet = h.load_packet()
        if h.ledger_observation(args.ledger) != method["ledger_before"]:
            raise ValueError(h.ERROR_PREFIX + "RegistrationRejected")
        for batch in method["batches"]:
            if not h.source_matches(
                registration,
                h.source_observation(h.ROOT, args.method.relative_to(h.ROOT), method["input_pins"]),
            ):
                raise ValueError(h.ERROR_PREFIX + "RegistrationRejected")
            observed = json.loads(json.dumps(asdict(ledger.quarantine_observation()), default=str))
            if observed != method["quarantine_before"]:
                break
            h.validate_registered_inputs(h.ROOT, method["protected_files"])
            h.validate_ledger_journal(
                args.ledger,
                method["ledger_journal_before"],
                set(method["fresh_request_ids"]),
                set(method["fresh_scope_ids"]),
            )
            slots = h.quality_slots(method, batch, fixtures)
            before = h.ledger_observation(args.ledger)
            scope_registration = {
                "method_sha256": registration["method_sha256"],
                "batch": batch,
                "source_commit": registration["source_commit"],
                "source_hashes": registration["source_hashes"],
                "ledger_before": before,
                "quarantine_before": observed,
            }
            digest = h.sha(json.dumps(scope_registration, sort_keys=True).encode())
            folder = destination / batch["batch_id"]
            folder.mkdir(mode=448)
            h.write_new(folder / "registration.json", scope_registration, secret)
            try:
                ledger.quarantine_scope_status(batch["scope_id"])
            except h.LedgerConflict:
                pass
            else:
                raise ValueError(h.ERROR_PREFIX + "ScopeAlreadyRegistered")
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
            config = h.MetisConfig(
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
                max_request_usd=h.get_price("gpt-4o-mini").cost(32768, 1024),
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
                    if not h.source_matches(
                        registration,
                        h.source_observation(
                            h.ROOT, args.method.relative_to(h.ROOT), method["input_pins"]
                        ),
                    ):
                        raise ValueError(h.ERROR_PREFIX + "RegistrationRejected")
                    status = ledger.quarantine_scope_status(scope_id)
                    if (
                        status.protocol_sha256 != scope_digest
                        or status.authorization_ref != scope_ref
                        or json.loads(
                            json.dumps(asdict(ledger.quarantine_observation()), default=str)
                        )
                        != method["quarantine_before"]
                    ):
                        raise ValueError(h.ERROR_PREFIX + "RegistrationRejected")
                    h.validate_registered_inputs(h.ROOT, method["protected_files"])
                    journal = h.validate_ledger_journal(
                        args.ledger,
                        method["ledger_journal_before"],
                        set(method["fresh_request_ids"]),
                        set(method["fresh_scope_ids"]),
                    )
                    value = {
                        **value,
                        "ledger_before_transport": h.ledger_observation(args.ledger),
                        "ledger_journal_sha256": h.sha(
                            json.dumps(journal, sort_keys=True).encode()
                        ),
                    }
                checkpoints.append(len(checkpoints))
                h.write_new(folder / f"checkpoint-{len(checkpoints):03d}.json", value, secret)

            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                records = []
                result = h.run_quality_batch(
                    method,
                    batch,
                    fixtures,
                    definitions,
                    ledger,
                    config,
                    before,
                    checkpoint=checkpoint,
                    retriever_factory=h.fixture_retriever_factory(packet, fixtures, records),
                )
            result["actual_fixed_evidence_calls"] = records
            # Save the original returned observations before any derived
            # transport/completion verdict can reject the batch.
            h.write_new(folder / "model-result.json", result, secret)
            result["json_object_wire_observed"] = wire_observer(result)
            result["real_RAG_retrieval"] = False
            result["controlled_fixed_evidence"] = True
            disposition = h.close_owned_scope(ledger, active, active_digest, active_ref)
            result["scope_disposition"] = json.loads(json.dumps(asdict(disposition), default=str))
            batches.append(result)
            h.write_new(folder / "receipt.json", result, secret)
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
            if not h.batch_complete(result) or result["json_object_wire_observed"] is False:
                break
        h.validate_registered_inputs(h.ROOT, method["protected_files"])
        h.validate_ledger_journal(
            args.ledger,
            method["ledger_journal_before"],
            set(method["fresh_request_ids"]),
            set(method["fresh_scope_ids"]),
        )
        source_after = h.source_observation(
            h.ROOT, args.method.relative_to(h.ROOT), method["input_pins"]
        )
        quarantine_preserved = (
            json.loads(json.dumps(asdict(ledger.quarantine_observation()), default=str))
            == method["quarantine_before"]
        )
        after = h.ledger_observation(args.ledger)
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
            "old_journal_preserved": True,
            "old_holds_and_authorization_history_preserved": quarantine_preserved,
            "no_pending_reservations": no_pending,
            "own_scopes_closed_without_new_block": scopes_closed_cleanly,
            **h.receipt_metadata(method),
            "c5_reconciled": False,
            "human_reviewed": False,
            "human_usefulness": None,
            "source_after": source_after,
            "source_unchanged": h.source_matches(registration, source_after),
        }
        h.write_new(destination / "receipt.json", receipt, secret)
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
                h.batch_complete(b) and b["json_object_wire_observed"] is not False for b in batches
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
                            asdict(h.close_owned_scope(ledger, active, active_digest, active_ref)),
                            default=str,
                        )
                    )
                except Exception:
                    disposition = {"status": "unknown; reservation retained"}
            try:
                h.write_new(
                    destination / "failure.json",
                    {
                        "error_code": h.ERROR_PREFIX + "ExperimentStopped",
                        "registration": registration,
                        "method": method,
                        "batches": batches,
                        "active_scope_disposition": disposition,
                        "ledger_after": h.ledger_observation(args.ledger),
                    },
                    secret,
                )
            except Exception:
                pass
        print(
            json.dumps(
                {
                    "error_code": h.ERROR_PREFIX + "ExperimentStopped",
                    "raw_diagnostics_exported": False,
                }
            )
        )
        return 2
    finally:
        if active is not None and ledger is not None:
            try:
                status = h.close_owned_scope(ledger, active, active_digest, active_ref)
                if destination is not None:
                    h.write_new(
                        destination / "cleanup.json",
                        json.loads(json.dumps(asdict(status), default=str)),
                        secret,
                    )
            except BaseException:
                pass
