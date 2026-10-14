"""Prepare/score offline review sidecars; no credentials or model invocation."""

import argparse
import json
from pathlib import Path

from agent_app.evaluation.review_workbench import (
    WorkbenchRejected,
    prepare_workbench,
    score_workbench,
    write_score,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument(
        "--receipt",
        type=Path,
        default=Path("experiments/dev_rag_coverage_v1/model-live-receipt-v1.json"),
    )
    prepare.add_argument(
        "--fixtures",
        type=Path,
        nargs="+",
        default=sorted(Path("data/evaluation/dev-three-v1/cases").glob("*.json")),
    )
    prepare.add_argument(
        "--scenario",
        type=Path,
        default=Path("data/evaluation/dev-three-v1/scenario-review-v1.json"),
    )
    prepare.add_argument("--rubric", type=Path, default=Path("docs/evaluation-rubric.md"))
    prepare.add_argument("--output", type=Path, required=True)
    score = commands.add_parser("score")
    score.add_argument("--workbench", type=Path, required=True)
    score.add_argument("--reviews", type=Path, nargs="+", required=True)
    score.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare_workbench(
                args.receipt, args.fixtures, args.scenario, args.rubric, args.output
            )
        else:
            result = score_workbench(args.workbench, args.reviews)
            write_score(args.output, result)
    except WorkbenchRejected as error:
        print(json.dumps({"accepted": False, "code": error.code}))
        return 2
    print(json.dumps({"accepted": True, "quality_claim": False, "summary": result["summary"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
