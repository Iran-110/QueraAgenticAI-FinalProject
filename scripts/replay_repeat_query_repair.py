"""Replay archived repeat plans without a model, credentials, ledger or index."""

import argparse
import json
from pathlib import Path

from agent_app.testing.repeat_query_replay import replay


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = replay(Path(__file__).resolve().parents[1])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps({key: result[key] for key in ("accepted", "checks_passed", "checks_total")}))
    return 0 if result["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
