"""Build the registered documentation-only local pilot with no network or provider."""

import argparse
import json
from pathlib import Path

from agent_app.retrieval.offline_index import build_index, open_verified_index
from agent_app.retrieval.pilot_corpus import build_pilot_corpus
from agent_app.testing.http_pilot_runtime import offline_network


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--seed-root", type=Path, default=Path("streamlit-data-for-dev-test"))
    parser.add_argument(
        "--split-manifest", type=Path, default=Path("data/evaluation/split-manifest.json")
    )
    parser.add_argument(
        "--allowlist", type=Path, default=Path("experiments/corpus/pilot-allowlist.json")
    )
    options = parser.parse_args()
    try:
        with offline_network():
            corpus = build_pilot_corpus(
                options.seed_root, options.split_manifest, options.allowlist
            )
            snapshot = build_index(corpus, options.destination)
            client, verified_snapshot = open_verified_index(options.destination)
            manifest = client.manifest["corpus"]
            if snapshot != verified_snapshot:
                raise ValueError
    except Exception:
        print(json.dumps({"accepted": False, "diagnostic": "OfflinePilotBuildRejected"}))
        return 1
    print(
        json.dumps(
            {
                "accepted": True,
                "snapshot_id": snapshot,
                "sources": len(manifest["sources"]),
                "chunks": len(manifest["chunks"]),
                "indexed_issues": 0,
                "indexed_comments": 0,
                "embedding": manifest["config"]["embedding"],
                "split_status": manifest["exclusions"]["split_status"],
                "scope": manifest["scope"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
