"""Offline CLI entry point; real-provider flags are intentionally absent."""

import argparse
import json

from agent_app.demo import run_demo


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Streamlit support assistant: offline core demo")
    subcommands = parser.add_subparsers(dest="command", required=True)
    demo = subcommands.add_parser(
        "demo", help="Run a synthetic scenario with no network or API key"
    )
    demo.add_argument(
        "--scenario", choices=("ask", "answer", "escalate", "refine", "error"), default="ask"
    )
    args = parser.parse_args(argv)
    output = run_demo(args.scenario)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if output["result"]["status"] == "awaiting_approval" else 1
