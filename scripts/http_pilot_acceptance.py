"""Accept the registered pilot over HTTP; no real model/index or durable claim by default."""

import argparse
import contextlib
import hashlib
import io
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def release_identity():
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = bool(
        subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()
    )
    sources = sorted((ROOT / "src/agent_app").rglob("*.py")) + [Path(__file__).resolve()]
    return {
        "git_commit": commit,
        "git_dirty": dirty,
        "source_sha256": {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--factory",
        help="Reviewed offline module:factory; actual app, same temporary storage after restart.",
    )
    parser.add_argument(
        "--expect-memory-gap",
        action="store_true",
        help="CI negative control: requires same-process success and rejected memory persistence, never acceptance.",
    )
    options = parser.parse_args(argv)
    if options.expect_memory_gap and options.factory:
        parser.error("The expected gap applies only to the default memory binding.")
    try:
        destination = options.output.open("x", encoding="utf-8")
    except FileExistsError:
        print(json.dumps({"accepted": False, "error_code": "ReceiptAlreadyExists"}))
        return 1
    except OSError:
        print(json.dumps({"accepted": False, "error_code": "ReceiptUnavailable"}))
        return 1
    receipt = {
        "schema_version": 1,
        "protocol": "http-pilot-acceptance-v1",
        "accepted": False,
        "quality_claim": False,
        "api_cost_usd": 0,
    }
    console = io.StringIO()
    with destination:
        try:
            with contextlib.redirect_stdout(console), contextlib.redirect_stderr(console):
                receipt["release_before"] = release_identity()
                from agent_app.testing.http_pilot_acceptance import MEMORY_FACTORY, run_acceptance

                receipt.update(run_acceptance(options.factory or MEMORY_FACTORY))
                receipt["release_after"] = release_identity()
                unchanged = (
                    receipt["release_before"]["source_sha256"]
                    == receipt["release_after"]["source_sha256"]
                )
                receipt["source_unchanged_during_run"] = unchanged
                if not unchanged:
                    receipt["accepted"] = False
                    receipt["error_code"] = "SourceChangedDuringRun"
        except Exception:
            receipt["accepted"] = False
            receipt["error_code"] = "HTTPAcceptanceFailed"
        expected_gap = bool(
            options.expect_memory_gap
            and receipt.get("same_process_accepted") is True
            and receipt.get("restart_accepted") is False
            and receipt.get("source_unchanged_during_run") is True
            and receipt.get("error_code") is None
            and receipt.get("tracker_backend") == "process_memory_dummy_tracker"
        )
        receipt["expected_memory_gap_reproduced"] = expected_gap
        receipt["console_output_discarded"] = bool(console.getvalue())
        destination.write(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                key: receipt.get(key)
                for key in (
                    "accepted",
                    "same_process_accepted",
                    "restart_accepted",
                    "checks_passed",
                    "checks_total",
                    "expected_memory_gap_reproduced",
                    "error_code",
                    "quality_claim",
                )
            }
        )
    )
    return 0 if receipt["accepted"] or expected_gap else 1


if __name__ == "__main__":
    raise SystemExit(main())
