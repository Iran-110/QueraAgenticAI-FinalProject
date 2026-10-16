"""R4b before/after receipt: archived real queries on the real 18/36 index; zero API.

Replays every archived retrieval of the C4h2 repeat-repair run (the same 24
requests used in the PR50 review) through the actual Chroma index and the
real engine version scope, in up to three arms:

- ``pr50_head``     PR50 adapter loaded from Git (optional, ``--pr50-ref``)
- ``before_native`` main adapter, native policy, multiplier 1 (legacy top-5)
- ``after_r4b``     query_relevance_v1, multiplier 5 (25 candidates), exact
                    USER-version scope before the final 5, 12000-byte packing

For each state it records what the backend was actually asked for
(``n_results``), the pre-scope rank of the button/multiselect/fragment
records, and the final evidence the model would receive. Source labels are
used only to report outcomes; they never select evidence. No model call,
ledger access, rebuild or index write happens here.
"""

import argparse
import hashlib
import json
import subprocess
import types
from pathlib import Path

from agent_app.contracts import CaseState, RetrievalRequest, RunLimits
from agent_app.orchestration.engine import SupportEngine, _Progress
from agent_app.retrieval.adapter import ChromaRetrieverAdapter
from agent_app.retrieval.offline_index import open_verified_index
from agent_app.retrieval.retriever import StreamlitRetriever
from agent_app.testing.http_pilot_runtime import offline_network

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "experiments/core_repeat_repair_v1/model-live-receipt-v1.json"
REGISTRATION = ROOT / "experiments/dev_rag_coverage_v1/index-receipt-v1.json"
ALLOWLIST = ROOT / "experiments/dev_rag_coverage_v1/allowlist.json"
ADAPTER_PATH = "src/agent_app/retrieval/adapter.py"
# Reporting labels only: which release records each exposed family needs.
FAMILY_APIS = {"dev-case-a": ("multiselect", "fragment"), "dev-case-b": ("button",)}


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_pr50_adapter(ref: str):
    blob = subprocess.check_output(["git", "show", f"{ref}:{ADAPTER_PATH}"], cwd=ROOT)
    module = types.ModuleType("r4b_pr50_adapter")
    exec(compile(blob, f"{ref}:{ADAPTER_PATH}", "exec"), module.__dict__)
    return module.ChromaRetrieverAdapter, sha(blob)


class RecordingBackend:
    def __init__(self, client, snapshot_id):
        self.backend = StreamlitRetriever("", snapshot_id=snapshot_id, client=client)
        self.snapshot_id = snapshot_id
        self.calls = []

    def search(self, **kwargs):
        self.calls.append({"query_sha256": sha(kwargs["query"].encode()), **kwargs})
        return self.backend.search(**kwargs)


class RecordingAdapter:
    def __init__(self, adapter):
        self.adapter = adapter
        self.bundle = None

    def search(self, request):
        self.bundle = self.adapter.search(request)
        return self.bundle


def archived_states(archive):
    """Unique (case state, queries, round) triples with their matched turn."""
    seen, states = set(), []
    for batch in archive["batches"]:
        for retrieval in batch["actual_retrievals"]:
            executed = retrieval.get("executed")
            if not executed:
                continue
            queries = executed["queries"]
            round_ = retrieval["logical_retrieval_round"]
            attempt = next(
                a
                for a in batch["attempts"]
                if a["context"]["case_id"] == retrieval["case_id"]
                and a["request"]["evidence"].get("queries_used") == queries
                and a["request"]["evidence"]["retrieval_round"] == round_
            )
            case = CaseState.model_validate(attempt["request"]["case"])
            key = (case.model_dump_json(), tuple(queries), round_)
            if key in seen:
                continue
            seen.add(key)
            states.append(
                {
                    "case": case,
                    "case_id": retrieval["case_id"],
                    "turn_id": retrieval["turn_id"],
                    "round": round_,
                    "queries": tuple(queries),
                    "request": RetrievalRequest.model_validate(executed),
                    "jobs": [retrieval["job_id"]],
                }
            )
    return states


def user_version(case):
    return next(
        (
            f.value
            for f in case.facts
            if f.name.casefold() == "streamlit_version"
            and f.status == "active"
            and f.provenance_kind == "user"
        ),
        None,
    )


def label(source_id):
    # docstring:<version>:streamlit.<api>  ->  (<api>, <version>)
    parts = source_id.split(":")
    if parts[0] == "docstring" and len(parts) == 3:
        return parts[2].removeprefix("streamlit."), parts[1]
    return None, None


def run_arm(arm, adapter_class, policy, multiplier, budget, client, snapshot, state):
    backend = RecordingBackend(client, snapshot)
    kwargs = {"snapshot_id": snapshot, "core_retriever": backend}
    if policy is not None:
        kwargs["selection_policy"] = policy
    adapter = RecordingAdapter(adapter_class("", **kwargs))
    engine = SupportEngine(
        adapter,
        None,
        snapshot_id=snapshot,
        evidence_scope="exact_user_version",
        retrieval_candidate_multiplier=multiplier,
        evidence_utf8_budget_bytes=budget,
    )
    progress = _Progress(RunLimits(), retrieval_rounds=state["round"] - 1)
    error = None
    try:
        evidence = engine._retrieve(state["case"], state["queries"], set(), progress)
        final = evidence.hits
    except Exception as exc:  # recorded, never hidden
        error, final = getattr(exc, "code", type(exc).__name__), ()
    candidates = adapter.bundle.hits if adapter.bundle is not None else ()
    version = user_version(state["case"])
    needed = FAMILY_APIS.get(state["case_id"], ())
    targets = {}
    for api in needed:
        ranks = [
            {"rank": i, "source_id": h.source_id, "versions": list(h.applicable_versions)}
            for i, h in enumerate(candidates, 1)
            if label(h.source_id)[0] == api
        ]
        targets[api] = {
            "pre_scope_ranks": ranks,
            "reached_model_at_user_version": any(
                label(h.source_id)[0] == api and version in h.applicable_versions for h in final
            ),
        }
    return {
        "arm": arm,
        "backend_n_results": [call["n_results"] for call in backend.calls],
        "candidate_count": len(candidates),
        "candidate_chunk_ids": [h.chunk_id for h in candidates],
        "final_hits": [
            {
                "source_id": h.source_id,
                "chunk_id": h.chunk_id,
                "versions": list(h.applicable_versions),
            }
            for h in final
        ],
        "version_safe": all(
            not h.applicable_versions or version in h.applicable_versions for h in final
        ),
        "targets": targets,
        "stop_code": error,
    }


def probe(index_path, pr50_ref):
    archive_raw = ARCHIVE.read_bytes()
    registration = json.loads(REGISTRATION.read_bytes())["indexes"]["new_18_sources"]
    manifest = Path(index_path) / "pilot-manifest.json"
    manifest_before = manifest.read_bytes()
    if sha(manifest_before) != registration["manifest_sha256"]:
        raise SystemExit("IndexManifestMismatch: build the registered 18/36 profile first")
    arms = [
        ("before_native", ChromaRetrieverAdapter, "native", 1, None),
        ("after_r4b", ChromaRetrieverAdapter, "query_relevance_v1", 5, 12000),
    ]
    pr50 = None
    if pr50_ref:
        pr50_class, blob_sha = load_pr50_adapter(pr50_ref)
        pr50 = {"ref": pr50_ref, "adapter_sha256": blob_sha}
        arms.insert(0, ("pr50_head", pr50_class, None, 1, None))
    observations = []
    with offline_network():
        client, snapshot = open_verified_index(index_path)
        if snapshot != registration["snapshot_id"]:
            raise SystemExit("IndexSnapshotMismatch")
        for state in archived_states(json.loads(archive_raw)):
            observations.append(
                {
                    "case_id": state["case_id"],
                    "turn_id": state["turn_id"],
                    "retrieval_round": state["round"],
                    "active_user_version": user_version(state["case"]),
                    "queries_sha256": [sha(q.encode()) for q in state["queries"]],
                    "query_preview": [q[:160] for q in state["queries"]],
                    "arms": {
                        arm: run_arm(arm, cls, pol, mult, bud, client, snapshot, state)
                        for arm, cls, pol, mult, bud in arms
                    },
                }
            )
        client.verify()
    if manifest.read_bytes() != manifest_before:
        raise SystemExit("IndexChangedDuringReplay")
    return {
        "schema_version": 1,
        "receipt_id": "r4b-version-ranking-before-after-v1",
        "task": "R4b",
        "archive": ARCHIVE.relative_to(ROOT).as_posix(),
        "archive_sha256": sha(archive_raw),
        "index": {
            "snapshot_id": snapshot,
            "manifest_sha256": registration["manifest_sha256"],
            "unchanged": True,
        },
        "pr50": pr50,
        "states": len(observations),
        "observations": observations,
        "provider_calls": 0,
        "quality_claim": False,
        "human_usefulness": None,
        "interpretation": (
            "Availability of release-matched records to the model under the engine's exact "
            "USER-version scope; not semantic support, answer quality or held-out evaluation. "
            "Family labels report outcomes only and never select evidence."
        ),
    }


def summary(result):
    arms = list(result["observations"][0]["arms"]) if result["observations"] else []
    lines = ["| case | turn | user version | target | " + " | ".join(arms) + " |"]
    lines.append("|" + "---|" * (4 + len(arms)))
    for row in result["observations"]:
        for api in FAMILY_APIS.get(row["case_id"], ()):
            cells = []
            for arm in arms:
                data = row["arms"][arm]
                target = data["targets"][api]
                ranks = ",".join(str(r["rank"]) for r in target["pre_scope_ranks"]) or "-"
                reached = "YES" if target["reached_model_at_user_version"] else "no"
                cells.append(f"n={data['backend_n_results']} rank={ranks} reached={reached}")
            lines.append(
                f"| {row['case_id']} | {row['turn_id']} | {row['active_user_version'] or 'unknown'}"
                f" | {api} | " + " | ".join(cells) + " |"
            )
    unsafe = [
        (row["case_id"], row["turn_id"], arm)
        for row in result["observations"]
        for arm, data in row["arms"].items()
        if not data["version_safe"]
    ]
    lines.append("")
    lines.append(f"states={result['states']} version_unsafe={unsafe or 'none'} provider_calls=0")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, help="Built 18/36 coverage index directory")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pr50-ref", help="Git ref of the PR50 head, e.g. 1a18749")
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("ReceiptOutputExists")
    result = probe(args.index, args.pr50_ref)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(summary(result))


if __name__ == "__main__":
    main()
