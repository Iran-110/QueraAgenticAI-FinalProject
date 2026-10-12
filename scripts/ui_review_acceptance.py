"""Run one registered offline control; never overwrite a receipt."""

import argparse
import json
import tempfile
from pathlib import Path

from agent_app.testing.ui_review_acceptance import run


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    try:
        with tempfile.TemporaryDirectory(prefix="ui-review-control-") as state:
            receipt = run(root, Path(state), baseline=args.baseline)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(receipt, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        print(
            json.dumps(
                {
                    "passed": receipt["passed"],
                    "total": receipt["total"],
                    "accepted": receipt["accepted"],
                    "quality_claim": False,
                }
            )
        )
        expected = (
            receipt["passed"] == 2 and receipt["accepted"] is False
            if args.baseline
            else receipt["accepted"] is True
        )
        if not expected:
            raise SystemExit("UIReviewAcceptanceRejected")
    except Exception:
        raise SystemExit("UIReviewAcceptanceFailed") from None


if __name__ == "__main__":
    main()
