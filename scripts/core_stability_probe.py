"""Default: read-only preregistration check. --live executes exact finite slots."""

import argparse
import io
import json
import subprocess
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict
from pathlib import Path

from agent_app.llm.budget import BudgetLedger
from agent_app.llm.config import MetisConfig
from agent_app.llm.pricing import get_price
from agent_app.testing.dev_three_model_probe import contains_secret
from agent_app.testing.stability_probe import (
    CAP,
    INPUT_RESERVE,
    MODEL,
    OUTPUT_LIMIT,
    PROTOCOL,
    DevProbeRejected,
    ledger_observation,
    preflight,
    run_batch,
    sha,
    slots_sha256,
    source_observation,
)

ROOT = Path(__file__).resolve().parents[1]


def credential(path):
    path = path.resolve()
    if (
        not path.is_relative_to(ROOT)
        or subprocess.run(["git", "check-ignore", "--quiet", "--", str(path)], cwd=ROOT).returncode
        != 0
        or subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", str(path)],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    ):
        raise DevProbeRejected()
    values = []
    for line in path.read_text(encoding="utf-8").splitlines():
        name, separator, value = line.strip().removeprefix("export ").partition("=")
        if separator and name.strip() == "METIS_API_KEY":
            value = value.strip()
            if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
                value = value[1:-1]
            values.append(value)
    if len(values) != 1 or not values[0]:
        raise DevProbeRejected()
    return values[0]


def write_new(path, value, secret=None):
    if secret is not None and contains_secret(value, secret):
        raise DevProbeRejected()
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=PROTOCOL)
    parser.add_argument("--ledger", type=Path, default=ROOT / "runtime/budget.sqlite3")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    destination, ledger, secret = None, None, None
    active_scope, closed = None, None
    try:
        protocol, fixtures, definitions, slots, registration = preflight(
            ROOT, args.ledger, args.protocol
        )
        if not args.live:
            print(
                json.dumps(
                    {
                        "eligible_read_only": True,
                        "batches": len(protocol["batches"]),
                        "max_sends": sum(len(s) for s in slots.values()),
                        "cap_per_batch_usd": str(CAP),
                        "actual_sends": 0,
                        "c5_reconciled": False,
                    }
                )
            )
            return 0
        if args.env_file is None or args.output_dir is None:
            raise DevProbeRejected()
        destination = args.output_dir.resolve()
        if (
            destination.is_relative_to(ROOT)
            and subprocess.run(
                ["git", "check-ignore", "--quiet", "--", str(destination)], cwd=ROOT
            ).returncode
            != 0
        ):
            raise DevProbeRejected()
        destination.mkdir(parents=True, exist_ok=False, mode=0o700)
        write_new(destination / "registration.json", registration)
        secret = credential(args.env_file)
        # Credentials never precede frozen input/source/ledger checks.
        config = MetisConfig(
            api_key=secret,
            live_enabled=True,
            model=MODEL,
            phase="development",
            response_mode="grounded_plan",
            grounded_source_gap_handoff=True,
            input_token_reserve=INPUT_RESERVE,
            max_output_tokens=OUTPUT_LIMIT,
            max_request_usd=get_price(MODEL).cost(INPUT_RESERVE, OUTPUT_LIMIT),
        )
        if ledger_observation(args.ledger) != registration["ledger_before"] or source_observation(
            ROOT, Path(registration["protocol_path"]), protocol["input_pins"]
        ) != {key: registration[key] for key in ("source_commit", "source_clean", "source_hashes")}:
            raise DevProbeRejected()
        ledger = BudgetLedger(args.ledger)
        batches = []
        for batch in protocol["batches"]:
            before = ledger_observation(args.ledger)
            if (
                before["counts"].get("reserved", 0)
                or before["counts"].get("uncertain", 0) != 1
                or any(
                    before[key] != registration["ledger_before"][key]
                    for key in ("meta_sha256", "unknown_sha256", "old_grants_sha256")
                )
            ):
                raise DevProbeRejected()
            batch_registration = {
                "method_protocol_sha256": registration["protocol_sha256"],
                "batch": batch,
                "request_slots_sha256": slots_sha256(slots[batch["batch_id"]]),
                "ledger_before": before,
                "source_commit": registration["source_commit"],
                "source_hashes": registration["source_hashes"],
            }
            batch_sha = sha(json.dumps(batch_registration, sort_keys=True).encode())
            folder = destination / batch["batch_id"]
            folder.mkdir(mode=0o700)
            write_new(
                folder / "registration.json",
                {**batch_registration, "registration_sha256": batch_sha, "ledger_before": before},
                secret,
            )
            status = ledger.authorize_experiment_scope(
                authorization_id=batch["scope_id"],
                authorization_ref=protocol["authorization_ref"],
                parent_authorization_id=protocol["parent_authorization_id"],
                protocol_sha256=batch_sha,
                request_slots=slots[batch["batch_id"]],
                additional_cap_usd=CAP,
            )
            active_scope, closed = batch["scope_id"], None
            write_new(
                folder / "authorization.json",
                {
                    "scope_id": active_scope,
                    "active": status.active,
                    "cap_usd": str(CAP),
                    "global_halt_retained": ledger.snapshot().halted,
                },
                secret,
            )
            counters = []

            def checkpoint(value, folder=folder, counters=counters):
                name = f"checkpoint-{len(counters) + 1}.json"
                write_new(folder / name, value, secret)
                counters.append(name)

            case_config = MetisConfig.model_validate(
                {**config.model_dump(), "continuation_id": active_scope}
            )
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                try:
                    result = run_batch(
                        protocol,
                        batch,
                        fixtures,
                        definitions,
                        ledger,
                        case_config,
                        before,
                        checkpoint=checkpoint,
                    )
                finally:
                    closed = ledger.close_experiment_scope(active_scope)
                    write_new(
                        folder / "scope-closed.json",
                        {
                            key: str(value) if key.endswith("usd") else value
                            for key, value in asdict(closed).items()
                        },
                        secret,
                    )
            result["scope_closed"] = closed.block_reason == "ExperimentClosed"
            result["registration"] = batch_registration
            result["ledger_after_close"] = ledger_observation(args.ledger)
            write_new(folder / "receipt.json", result, secret)
            batches.append(result)
            active_scope = None
            if (
                result["stopped_early"]
                or not result["accounting"]["accounting_complete"]
                or not result["original_accounting_preserved"]
            ):
                break
        receipt = {
            "schema_version": 1,
            "protocol_id": protocol["protocol_id"],
            "registration": registration,
            "batches": batches,
            "tracker": "process_memory_dummy_tracker",
            "evidence": "fixed_registered_bundles",
            "renderer_source_gap_handoff": True,
            "human_review": False,
            "human_usefulness": None,
            "quality_claim": False,
            "actual_rag_quality": False,
            "final_test_cases_added": 0,
            "c5_reconciled": False,
            "actual_sends": sum(b["actual_sends"] for b in batches),
            "completed_routes": sum(b["completed_routes"] for b in batches),
            "source_after": source_observation(
                ROOT, Path(registration["protocol_path"]), protocol["input_pins"]
            ),
            "ledger_after": ledger_observation(args.ledger),
        }
        receipt["source_unchanged_during_run"] = receipt["source_after"] == {
            key: registration[key] for key in ("source_commit", "source_clean", "source_hashes")
        }
        write_new(destination / "receipt.json", receipt, secret)
        print(
            json.dumps(
                {
                    "receipt_written": True,
                    "actual_sends": receipt["actual_sends"],
                    "completed_routes": receipt["completed_routes"],
                    "batches_visited": len(batches),
                    "source_unchanged": receipt["source_unchanged_during_run"],
                    "quality_claim": False,
                }
            )
        )
        return (
            0
            if len(batches) == len(protocol["batches"])
            and receipt["source_unchanged_during_run"]
            and all(
                not batch["stopped_early"]
                and batch["accounting"]["accounting_complete"]
                and batch["original_accounting_preserved"]
                for batch in batches
            )
            else 2
        )
    except Exception:
        if destination is not None and destination.is_dir():
            try:
                write_new(
                    destination / "failure.json",
                    {
                        "diagnostic": "CoreStabilityProbeRejected",
                        "c5_reconciled": False,
                        "ledger_after": ledger_observation(args.ledger),
                    },
                    secret,
                )
            except Exception:
                pass
        print(json.dumps({"accepted": False, "diagnostic": "CoreStabilityProbeRejected"}))
        return 1
    finally:
        if ledger is not None and active_scope is not None:
            try:
                ledger.close_experiment_scope(active_scope)
            except Exception:
                print(json.dumps({"accepted": False, "diagnostic": "ExperimentClosureUnconfirmed"}))
                return 1


if __name__ == "__main__":
    raise SystemExit(main())
