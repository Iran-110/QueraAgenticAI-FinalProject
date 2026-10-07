"""Offline CLI entry point; real-provider flags are intentionally absent."""

import argparse
import json
from dataclasses import asdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

from agent_app.demo import run_demo


def _decimal(value: str) -> Decimal:
    try:
        result = Decimal(value)
    except InvalidOperation:
        raise argparse.ArgumentTypeError("Use a finite nonnegative USD amount") from None
    if not result.is_finite() or result < 0:
        raise argparse.ArgumentTypeError("Use a finite nonnegative USD amount")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Streamlit support assistant: offline core demo")
    subcommands = parser.add_subparsers(dest="command", required=True)
    demo = subcommands.add_parser(
        "demo", help="Run a synthetic scenario with no network or API key"
    )
    demo.add_argument(
        "--scenario", choices=("ask", "answer", "escalate", "refine", "error"), default="ask"
    )
    gateway = subcommands.add_parser(
        "gateway-demo", help="Exercise model accounting with synthetic HTTP and no paid requests"
    )
    gateway.add_argument(
        "--scenario", choices=("success", "repair", "timeout", "budget"), default="success"
    )
    budget = subcommands.add_parser(
        "budget", help="Initialize or inspect the local shared-runner ledger"
    )
    budget_commands = budget.add_subparsers(dest="budget_command", required=True)
    initialize = budget_commands.add_parser(
        "init", help="Create a new ledger once; existing files are never reset"
    )
    initialize.add_argument("--path", type=Path, required=True)
    initialize.add_argument("--limit-usd", type=_decimal, required=True)
    initialize.add_argument("--opening-spend-usd", type=_decimal, required=True)
    status = budget_commands.add_parser(
        "status", help="Read existing accounting without a network request"
    )
    status.add_argument("--path", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "budget":
        from agent_app.llm.budget import BudgetLedger, LedgerConflict, LedgerUnavailable

        try:
            if args.budget_command == "init":
                args.path.parent.mkdir(parents=True, exist_ok=True)
            ledger = (
                BudgetLedger.create(
                    args.path, limit_usd=args.limit_usd, opening_spend_usd=args.opening_spend_usd
                )
                if args.budget_command == "init"
                else BudgetLedger(args.path)
            )
            output = asdict(ledger.snapshot())
        except (OSError, ValueError, LedgerConflict, LedgerUnavailable):
            print(json.dumps({"error": "BudgetLedgerOperationFailed"}))
            return 1
        print(json.dumps(output, indent=2, default=str))
        return 0
    if args.command == "gateway-demo":
        from agent_app.llm.demo import run_gateway_demo

        output = run_gateway_demo(args.scenario)
    else:
        output = run_demo(args.scenario)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if output["result"]["status"] == "awaiting_approval" else 1
