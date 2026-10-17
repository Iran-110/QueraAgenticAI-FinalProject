"""Build the final docs/release-note/API index offline and write its physical receipt.

No network, provider, embedding service or held-out content. The receipt carries
the five native pins (build, index_snapshot, allowlist, exclusion and the index
manifest hash), source/chunk counts, unchanged historical snapshots, a
deterministic in-memory rebuild and a small adapter smoke on neutral API queries.
"""

import argparse
import hashlib
import json
import time
from collections import Counter
from pathlib import Path

from agent_app.contracts import RetrievalRequest
from agent_app.retrieval.adapter import ChromaRetrieverAdapter
from agent_app.retrieval.offline_index import build_index, open_verified_index
from agent_app.retrieval.pilot_corpus import (
    FINAL_PROTOCOL,
    MANIFEST_NAME,
    build_final_corpus,
    build_pilot_corpus,
)
from agent_app.retrieval.retriever import StreamlitRetriever
from agent_app.testing.http_pilot_runtime import offline_network

# Snapshots of the two historical profiles from current-main inputs, before this
# protocol was added. The final protocol must leave both byte-identical.
HISTORICAL = {
    "pilot_14_sources": (
        "data/evaluation/split-manifest.json",
        "experiments/corpus/pilot-allowlist.json",
        "docs-pilot-87bdaf9a3dadcefff48a6775ef616f3d3dd5bf1c8cb23a9521b0e11ccaae160c",
    ),
    "dev_coverage_18_sources": (
        "experiments/dev_rag_coverage_v1/split-manifest.json",
        "experiments/dev_rag_coverage_v1/allowlist.json",
        "docs-pilot-12ec2995032ad48dbec2c1f1736fca1f97727478373dd1835043eedf21ab0ee1",
    ),
}
# Generic API phrases, not taken from any dev or test case.
SMOKE_QUERIES = ("st.button icon parameter", "session state widget key callback")


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--seed-root", type=Path, default=Path("streamlit-data-for-dev-test"))
    parser.add_argument(
        "--allowlist", type=Path, default=Path("experiments/final_corpus_v1/allowlist.json")
    )
    parser.add_argument(
        "--exclusion", type=Path, default=Path("experiments/final_corpus_v1/exclusion-v1.json")
    )
    args = parser.parse_args()
    if args.receipt.exists():
        raise SystemExit("ReceiptOutputExists")
    started = time.perf_counter()
    with offline_network():
        corpus = build_final_corpus(args.seed_root, args.allowlist, args.exclusion)
        snapshot = build_index(corpus, args.destination)
        build_seconds = time.perf_counter() - started
        opened = time.perf_counter()
        client, verified = open_verified_index(args.destination)
        open_seconds = time.perf_counter() - opened
        if verified != snapshot:
            raise SystemExit("SnapshotMismatch")
        manifest = client.manifest["corpus"]
        rebuilt = build_final_corpus(args.seed_root, args.allowlist, args.exclusion)
        historical = {
            name: {
                "expected": expected,
                "observed": build_pilot_corpus(args.seed_root, split, allowlist).snapshot_id,
            }
            for name, (split, allowlist, expected) in HISTORICAL.items()
        }
        smoke = []
        for query in SMOKE_QUERIES:
            backend = StreamlitRetriever("", snapshot_id=snapshot, client=client)
            adapter = ChromaRetrieverAdapter(
                "",
                snapshot_id=snapshot,
                core_retriever=backend,
                selection_policy="query_relevance_v1",
            )
            began = time.perf_counter()
            bundle = adapter.search(
                RetrievalRequest(queries=(query,), snapshot_id=snapshot, top_k=25)
            )
            smoke.append(
                {
                    "query": query,
                    "seconds": round(time.perf_counter() - began, 3),
                    "hits": len(bundle.hits),
                    "source_types": dict(Counter(h.source_type for h in bundle.hits)),
                    "versioned_hits": sum(1 for h in bundle.hits if h.applicable_versions),
                    "top_sources": [h.source_id for h in bundle.hits[:5]],
                }
            )
        client.verify()
    manifest_raw = (args.destination / MANIFEST_NAME).read_bytes()
    pins = manifest["source_pins"]
    sources = manifest["sources"]
    exclusions = manifest["exclusions"]
    receipt = {
        "schema_version": 1,
        "receipt_id": "final-corpus-build-v1",
        "protocol": FINAL_PROTOCOL,
        "native_pins": {
            "build": "final-corpus-v1-" + snapshot.removeprefix("docs-pilot-")[:16],
            "index_snapshot": snapshot,
            "index_manifest_sha256": sha(manifest_raw),
            "allowlist_sha256": pins["allowlist_sha256"],
            "exclusion_manifest_sha256": pins["exclusion_manifest_sha256"],
            "corpus_manifest_sha256": None,
            "corpus_manifest_note": (
                "Evaluation corpus JSON hash is owned by the evaluation packet; "
                "it is not the physical index manifest hash."
            ),
        },
        "inputs": {
            "allowlist": args.allowlist.as_posix(),
            "exclusion": args.exclusion.as_posix(),
            "split_manifest_sha256": pins["split_manifest_sha256"],
            "package_manifest_sha256": pins["package_manifest_sha256"],
            "development_exposure_sha256": pins["development_exposure_sha256"],
            "docs_commit": pins["docs_commit"],
        },
        "counts": {
            "sources": len(sources),
            "chunks": len(manifest["chunks"]),
            "by_source_type": dict(Counter(s["source_type"] for s in sources)),
            "chunks_by_source_type": dict(
                Counter(c["metadata"]["source_type"] for c in manifest["chunks"])
            ),
            "api_versions": len({v for s in sources for v in s["applicable_versions"]}),
            "unversioned_sources": sum(1 for s in sources if not s["applicable_versions"]),
        },
        "exclusion": {
            "split_manifest_id": exclusions["split_manifest_id"],
            "split_status": exclusions["split_status"],
            "excluded_issue_count": len(exclusions["reserved_issue_ids"]),
            "direct_answer_documents": exclusions["direct_answer_documents"],
            "indexed_issue_count": exclusions["indexed_issue_count"],
            "indexed_comment_count": exclusions["indexed_comment_count"],
            "denied_documents_indexed": sorted(
                s["source_id"]
                for s in sources
                if s["source_pointer"]
                in {d for d in exclusions["direct_answer_documents"] if not d.startswith("http")}
            ),
            "test_content_read": False,
        },
        "deterministic_rebuild": rebuilt.snapshot_id == snapshot,
        "historical_profiles_unchanged": {
            name: value["expected"] == value["observed"] for name, value in historical.items()
        },
        "timing_seconds": {
            "build_including_corpus": round(build_seconds, 2),
            "open_and_verify": round(open_seconds, 2),
        },
        "adapter_smoke": smoke,
        "provider_calls": 0,
        "quality_claim": False,
        "limitations": [
            "Lexical-hash embedding; no semantic retrieval quality claim.",
            "Built before the evaluation freeze; rebuild after freeze with a refreshed exclusion.",
            "Ranking and packing of key-identity evidence are unchanged and tracked separately.",
        ],
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    with args.receipt.open("x", encoding="utf-8") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({k: receipt[k] for k in ("native_pins", "counts")}, indent=2))
    print(
        json.dumps(
            {
                "deterministic_rebuild": receipt["deterministic_rebuild"],
                "historical_profiles_unchanged": receipt["historical_profiles_unchanged"],
                "excluded_issue_count": receipt["exclusion"]["excluded_issue_count"],
                "denied_documents_indexed": receipt["exclusion"]["denied_documents_indexed"],
                "timing_seconds": receipt["timing_seconds"],
                "smoke_seconds": [s["seconds"] for s in smoke],
            }
        )
    )
    ok = (
        receipt["deterministic_rebuild"]
        and all(receipt["historical_profiles_unchanged"].values())
        and not receipt["exclusion"]["denied_documents_indexed"]
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
