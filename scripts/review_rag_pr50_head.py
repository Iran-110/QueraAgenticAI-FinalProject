"""Offline review of one exact PR head; leaves Hassan's branch/index untouched."""

import argparse
import hashlib
import json
import subprocess
import types
from copy import deepcopy
from pathlib import Path

from agent_app.contracts import RetrievalRequest
from agent_app.retrieval.adapter import ChromaRetrieverAdapter
from agent_app.retrieval.retriever import StreamlitRetriever
from agent_app.testing.http_pilot_runtime import offline_network
from agent_app.testing.real_index_probe import _IndexBinding

ROOT = Path(__file__).resolve().parents[1]
HEAD = "1a18749159e09abd4f19d2417dc7fa1dc9146eb2"
BASE = "71c5eb010bd242c934876c61a18f1fe99d6d17f3"
ADAPTER = "src/agent_app/retrieval/adapter.py"


def git_blob(ref):
    return subprocess.check_output(["git", "show", f"{ref}:{ADAPTER}"], cwd=ROOT)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("ReviewOutputExists")
    candidate = types.ModuleType("pr50_exact_review_candidate")
    blob = git_blob(HEAD)
    exec(compile(blob, f"{HEAD}:{ADAPTER}", "exec"), candidate.__dict__)
    old = json.loads(
        (ROOT / "experiments/rag_pr50_review/review-head-7581dcc-v1.json").read_bytes()
    )
    control = old["ranking_control"]
    synthetic = {}
    for name, adapter in (
        ("baseline", ChromaRetrieverAdapter),
        ("candidate", candidate.ChromaRetrieverAdapter),
    ):
        calls = []

        class Backend:
            def search(self, *, _calls=calls, **kwargs):
                _calls.append(kwargs)
                return deepcopy(control["native_backend_rows"])

        request = RetrievalRequest.model_validate(control["request"])
        result = adapter("", snapshot_id=request.snapshot_id, core_retriever=Backend()).search(
            request
        )
        synthetic[name] = {
            "calls": calls,
            "returned_ids": [h.chunk_id for h in result.hits],
            "current_version_ids": [
                h.chunk_id
                for h in result.hits
                if not h.applicable_versions or "1.39.0" in h.applicable_versions
            ],
        }
    receipt = json.loads(
        (ROOT / "experiments/core_repeat_repair_v1/model-live-receipt-v1.json").read_bytes()
    )
    binding = next(iter(receipt["method"]["indexes"].values()))
    observations = []
    with offline_network():
        index = _IndexBinding(binding)
        for batch in receipt["batches"]:
            for row in batch["actual_retrievals"]:
                request = RetrievalRequest.model_validate(row["executed"])
                results = {}
                for name, adapter in (
                    ("baseline", ChromaRetrieverAdapter),
                    ("candidate", candidate.ChromaRetrieverAdapter),
                ):

                    class RecordingBackend:
                        def __init__(self):
                            self.calls = []
                            self.backend = StreamlitRetriever(
                                "", snapshot_id=index.snapshot_id, client=index.client
                            )

                        def search(self, **kwargs):
                            self.calls.append(deepcopy(kwargs))
                            return self.backend.search(**kwargs)

                    backend = RecordingBackend()
                    bundle = adapter(
                        "", snapshot_id=index.snapshot_id, core_retriever=backend
                    ).search(request)
                    results[name] = {
                        "backend_calls": backend.calls,
                        "evidence": bundle.model_dump(mode="json"),
                    }
                observations.append(
                    {
                        "batch": batch["batch_id"],
                        "job_id": row["job_id"],
                        "turn_id": row["turn_id"],
                        "request": request.model_dump(mode="json"),
                        "results": results,
                        "same_membership": {
                            h["chunk_id"] for h in results["baseline"]["evidence"]["hits"]
                        }
                        == {h["chunk_id"] for h in results["candidate"]["evidence"]["hits"]},
                    }
                )
        index.verify()
    metadata = []
    for row in old["metadata_controls"]:
        native = row["native_metadata"]
        metadata.append(
            {"native_metadata": native, "candidate_versions": candidate._versions(native)}
        )
    report = {
        "head": HEAD,
        "base": BASE,
        "adapter_sha256": hashlib.sha256(blob).hexdigest(),
        "current_baseline_matches_base": (ROOT / ADAPTER).read_bytes() == git_blob(BASE),
        "synthetic_ranking_control": synthetic,
        "metadata_controls": metadata,
        "real_index": index.receipt,
        "native_query_replays": observations,
        "same_membership_count": sum(r["same_membership"] for r in observations),
        "query_replay_count": len(observations),
        "overfetch_implemented": any(
            c["n_results"] > r["request"]["top_k"]
            for r in observations
            for c in r["results"]["candidate"]["backend_calls"]
        ),
        "model_tested": False,
        "paid_api_calls": 0,
        "quality_score": None,
        "merge_ready": False,
        "limitations": [
            "Archived exposed-development queries, not held-out relevance labels.",
            "Synthetic mixed-collection ranking control is separate from actual docs-only native membership.",
            "No model run or ledger/key access; no rebuild or teammate source modification.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)
        file.write("\n")
    print(
        json.dumps(
            {
                k: report[k]
                for k in (
                    "head",
                    "query_replay_count",
                    "same_membership_count",
                    "overfetch_implemented",
                    "paid_api_calls",
                    "merge_ready",
                )
            }
        )
    )


if __name__ == "__main__":
    main()
