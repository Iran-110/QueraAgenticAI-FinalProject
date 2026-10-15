"""Replay archived queries through real native storage and current scope; zero API.

No case/source-ID filter is applied. Report evidence availability and prompt
sizes only, not semantic support. Full source records stay unchanged.
"""

import argparse
import hashlib
import json
from pathlib import Path

from agent_app.contracts import GroundedRequest, ReasoningContext, RunLimits
from agent_app.llm.config import MetisConfig
from agent_app.llm.metis import configured_grounded_messages
from agent_app.orchestration.engine import SupportEngine, _Progress
from agent_app.reasoning.catalog import caller_catalog, load_user_gap_vocabulary
from agent_app.retrieval.adapter import ChromaRetrieverAdapter
from agent_app.retrieval.offline_index import open_verified_index
from agent_app.retrieval.retriever import StreamlitRetriever

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "experiments/retrieval_relevance_v1"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class ObservedBackend:
    def __init__(self, backend):
        self.backend = backend
        self.snapshot_id = backend.snapshot_id
        self.calls = []

    def search(self, **kwargs):
        result = self.backend.search(**kwargs)
        self.calls.append(
            {
                "query": kwargs["query"],
                "n_results": kwargs["n_results"],
                "filters": kwargs["filters"],
                "collections": {
                    name: [
                        {
                            "rank": i + 1,
                            "chunk_id": meta["chunk_id"],
                            "source_id": meta["source_id"],
                            "text_sha256": sha(text.encode()),
                            "metadata_sha256": sha(json.dumps(meta, sort_keys=True).encode()),
                        }
                        for i, (text, meta) in enumerate(
                            zip(
                                result[name]["documents"][0],
                                result[name]["metadatas"][0],
                                strict=True,
                            )
                        )
                    ]
                    for name in ("docs", "issues")
                },
            }
        )
        return result


class ObservedAdapter:
    def __init__(self, adapter):
        self.adapter = adapter
        self.request = None
        self.bundle = None

    def search(self, request):
        self.request = request
        self.bundle = self.adapter.search(request)
        return self.bundle


def probe():
    receipt_path = ROOT / "experiments/core_compact_plan_v1/model-live-receipt-v1.json"
    receipt = json.loads(receipt_path.read_bytes())
    registration = json.loads(
        (ROOT / "experiments/dev_rag_coverage_v1/index-receipt-v1.json").read_bytes()
    )["indexes"]["new_18_sources"]
    path = Path(registration["path"])
    manifest = path / "pilot-manifest.json"
    before = manifest.read_bytes()
    assert sha(before) == registration["manifest_sha256"]
    client, snapshot = open_verified_index(path)
    assert snapshot == registration["snapshot_id"]
    definitions = load_user_gap_vocabulary(
        str(ROOT / "data/evaluation/dev-three-v1/user-gap-vocabulary-v1.json")
    )
    config = MetisConfig(
        api_key="offline-public-placeholder",
        response_mode="grounded_plan",
        grounded_decision_contracts=True,
        grounded_source_selection_reminder=True,
        grounded_source_gap_handoff=True,
        grounded_source_gap_investigation=True,
        grounded_compact_plan=True,
    )
    observations = []
    seen = set()
    for batch in receipt["batches"]:
        attempts = batch["attempts"]
        for retrieval in batch["actual_retrievals"]:
            if not retrieval.get("executed"):
                continue
            related = [
                a
                for a in attempts
                if a["context"]["run_id"]
                in next(j["run_ids"] for j in batch["jobs"] if j["job_id"] == retrieval["job_id"])
                and a["request"]["evidence"]["retrieval_round"]
                == retrieval["logical_retrieval_round"]
                and a["context"]["case_revision"] == (1 if retrieval["turn_id"] == "initial" else 2)
            ]
            if not related:
                continue
            old = GroundedRequest.model_validate(related[0]["request"])
            ctx = ReasoningContext.model_validate(related[0]["context"])
            queries = tuple(retrieval["executed"]["queries"])
            key = (
                old.case.model_dump_json(),
                old.user_message,
                queries,
                retrieval["logical_retrieval_round"],
            )
            if key in seen:
                continue
            seen.add(key)
            row = {
                "case_id": old.case.case_id,
                "turn_id": retrieval["turn_id"],
                "queries": list(queries),
                "retrieval_round": retrieval["logical_retrieval_round"],
                "arms": {},
            }
            for policy, multiplier, arm in [
                ("native", 1, "native_top5"),
                ("query_relevance_v1", 5, "candidate_relevance"),
            ]:
                backend = ObservedBackend(
                    StreamlitRetriever("", snapshot_id=snapshot, client=client)
                )
                adapter = ObservedAdapter(
                    ChromaRetrieverAdapter(
                        "", snapshot_id=snapshot, core_retriever=backend, selection_policy=policy
                    )
                )
                engine = SupportEngine(
                    adapter,
                    None,
                    snapshot_id=snapshot,
                    evidence_scope="exact_user_version",
                    retrieval_candidate_multiplier=multiplier,
                    evidence_utf8_budget_bytes=12000 if multiplier == 5 else None,
                )
                progress = _Progress(
                    RunLimits(), retrieval_rounds=retrieval["logical_retrieval_round"] - 1
                )
                evidence = engine._retrieve(old.case, queries, set(), progress)
                current = caller_catalog(
                    old.case, old.user_message, evidence, definitions=definitions
                )
                sizes = []
                for context in (
                    ctx,
                    ReasoningContext.model_validate(
                        {
                            **ctx.model_dump(),
                            "attempt_index": 2,
                            "remaining_model_attempts": 0,
                            "can_refine": False,
                            "output_feedback": {"issues": [{"code": "invalid_grounded_plan"}]},
                        }
                    ),
                ):
                    sizes.append(
                        len(
                            json.dumps(
                                configured_grounded_messages(config, current, context),
                                ensure_ascii=False,
                            ).encode()
                        )
                        + 1024
                    )
                row["arms"][arm] = {
                    "requested_top_k": adapter.request.top_k,
                    "native_calls": backend.calls,
                    "candidate_hit_ids": [h.chunk_id for h in adapter.bundle.hits],
                    "post_scope_evidence": evidence.model_dump(mode="json"),
                    "current_request_sha256": current.context_sha256,
                    "common_compact_prompt_sizes": sizes,
                    "all_observed_contexts_fit": max(sizes) <= 32768,
                }
            observations.append(row)
    client.verify()
    assert manifest.read_bytes() == before
    return {
        "schema_version": 1,
        "receipt_id": "retrieval-relevance-archived-query-replay-v1",
        "archive_sha256": sha(receipt_path.read_bytes()),
        "index_binding": registration,
        "snapshot_unchanged": True,
        "provider_calls": 0,
        "quality_claim": False,
        "human_usefulness": None,
        "observations": observations,
        "states": len(observations),
        "interpretation": "Actual native replay of archived observed states/queries. No guarantee over future model refinements; prompt overflow is retained, not truncated. API identifiers/lexical rank do not prove semantic support.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = probe()
    with args.output.open("x") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(
        json.dumps(
            {
                "states": result["states"],
                "fits": {
                    arm: sum(
                        z["arms"][arm]["all_observed_contexts_fit"] for z in result["observations"]
                    )
                    for arm in ("native_top5", "candidate_relevance")
                },
                "provider_calls": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
