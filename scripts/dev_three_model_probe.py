"""Read-only eligibility by default; --live uses one frozen funded dev experiment."""

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
from agent_app.testing.dev_three_model_probe import (
    CAP,
    INPUT_RESERVE,
    MODEL,
    OUTPUT_LIMIT,
    DevProbeRejected,
    contains_secret,
    ledger_observation,
    preflight,
    run_trial,
    source_observation,
)

ROOT = Path(__file__).resolve().parents[1]


def credential(path):
    """Read a single ignored setting; never log lines, headers or parser errors."""
    path = path.resolve()
    if (
        not path.is_relative_to(ROOT)
        or subprocess.run(["git", "check-ignore", "--quiet", "--", str(path)], cwd=ROOT).returncode
        != 0
    ):
        raise DevProbeRejected()
    if (
        subprocess.run(
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
    if len(values) != 1:
        raise DevProbeRejected()
    return values[0]


def write_new(path, data, *, secret=None):
    if secret is not None and contains_secret(data, secret):
        raise DevProbeRejected()
    with path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=ROOT / "runtime/budget.sqlite3")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--output-dir", type=Path)
    options = parser.parse_args()
    destination = None
    created = False
    scope_ledger = None
    scope_id = None
    private_secret = None
    try:
        protocol, fixtures, definitions, slots, registration = preflight(ROOT, options.ledger)
        if not options.live:
            print(
                json.dumps(
                    {
                        "eligible_read_only": True,
                        "max_sends": len(slots),
                        "cap_usd": str(CAP),
                        "real_model_requests": 0,
                        "c5_reconciled": False,
                    }
                )
            )
            return 0
        if options.env_file is None or options.output_dir is None:
            raise DevProbeRejected()
        destination = options.output_dir.resolve()
        if (
            destination.is_relative_to(ROOT)
            and subprocess.run(
                ["git", "check-ignore", "--quiet", "--", str(destination)], cwd=ROOT
            ).returncode
            != 0
        ):
            raise DevProbeRejected()
        destination.mkdir(parents=True, exist_ok=False, mode=0o700)
        created = True
        write_new(destination / "registration.json", registration)
        # Validate the credential only after all fixed inputs and caller identities.
        config = MetisConfig(
            api_key=credential(options.env_file),
            live_enabled=True,
            model=MODEL,
            phase="development",
            response_mode="grounded_plan",
            continuation_id=protocol["scope_id"],
            input_token_reserve=INPUT_RESERVE,
            max_output_tokens=OUTPUT_LIMIT,
            max_request_usd=get_price(MODEL).cost(INPUT_RESERVE, OUTPUT_LIMIT),
        )
        private_secret = config.api_key.get_secret_value()
        if source_observation(ROOT) != {
            key: registration[key] for key in ("source_commit", "source_clean", "source_hashes")
        }:
            raise DevProbeRejected()
        if ledger_observation(options.ledger) != registration["ledger_before"]:
            raise DevProbeRejected()
        ledger = BudgetLedger(options.ledger)
        # The user explicitly requested useful paid tests in this conversation.
        # This records a fresh finite scope; it does not refill the old grant.
        scope = ledger.authorize_experiment_scope(
            authorization_id=protocol["scope_id"],
            authorization_ref=protocol["authorization_ref"],
            parent_authorization_id=protocol["parent_authorization_id"],
            protocol_sha256=registration["protocol_sha256"],
            request_slots=slots,
            additional_cap_usd=CAP,
        )
        scope_ledger, scope_id = ledger, protocol["scope_id"]
        write_new(
            destination / "authorization.json",
            {
                "scope_id": protocol["scope_id"],
                "authorization_ref": protocol["authorization_ref"],
                "protocol_sha256": registration["protocol_sha256"],
                "request_slots_sha256": registration["request_slots_sha256"],
                "scope_active": scope.active,
                "cap_usd": str(CAP),
                "global_halt_retained": ledger.snapshot().halted,
                "c5_reconciled": False,
            },
            secret=private_secret,
        )
        checkpoints = []

        def checkpoint(value):
            path = destination / f"checkpoint-{len(checkpoints) + 1}.json"
            write_new(path, value, secret=private_secret)
            checkpoints.append(path.name)

        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            try:
                receipt = run_trial(
                    protocol,
                    fixtures,
                    definitions,
                    ledger,
                    config,
                    registration["ledger_before"],
                    checkpoint=checkpoint,
                )
            finally:
                closed_scope = ledger.close_experiment_scope(protocol["scope_id"])
                write_new(
                    destination / "scope-closed.json",
                    {
                        key: str(value) if key.endswith("usd") else value
                        for key, value in asdict(closed_scope).items()
                    },
                    secret=private_secret,
                )
        receipt["scope_closed"] = closed_scope.block_reason == "ExperimentClosed"
        receipt["registration"] = registration
        receipt["source_after"] = source_observation(ROOT)
        receipt["source_unchanged_during_run"] = receipt["source_after"] == {
            key: registration[key] for key in ("source_commit", "source_clean", "source_hashes")
        }
        write_new(destination / "receipt.json", receipt, secret=private_secret)
        print(
            json.dumps(
                {
                    "receipt_written": True,
                    "actual_sends": receipt["actual_sends"],
                    "completed_case_arm_runs": receipt["completed_case_arm_runs"],
                    "estimated_cost_usd": receipt["accounting"]["cost_usd"],
                    "accounting_complete": receipt["accounting"]["accounting_complete"],
                    "quality_claim": False,
                    "c5_reconciled": False,
                }
            )
        )
        return 2 if receipt["stopped_early"] else 0
    except Exception:
        # No raw exception/credential/provider body enters terminal output.
        try:
            if created and not (destination / "failure.json").exists():
                write_new(
                    destination / "failure.json",
                    {
                        "diagnostic": "DevThreeModelProbeRejected",
                        "quality_claim": False,
                        "c5_reconciled": False,
                        "ledger_after": ledger_observation(options.ledger),
                        "note": "Preserve registration/authorization/checkpoints; inspect ledger before any fresh registration.",
                    },
                    secret=private_secret,
                )
        except Exception:
            pass
        print(json.dumps({"accepted": False, "diagnostic": "DevThreeModelProbeRejected"}))
        return 1
    finally:
        if scope_ledger is not None:
            try:
                # Covers authorization-journal/setup failures before run_trial,
                # and is idempotent after the normal close/journal above.
                closed = scope_ledger.close_experiment_scope(scope_id)
            except Exception:
                print(json.dumps({"accepted": False, "diagnostic": "ExperimentClosureUnconfirmed"}))
                return 1
            try:
                if created and not (destination / "scope-closed.json").exists():
                    write_new(
                        destination / "scope-closed.json",
                        {
                            key: str(value) if key.endswith("usd") else value
                            for key, value in asdict(closed).items()
                        },
                        secret=private_secret,
                    )
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
