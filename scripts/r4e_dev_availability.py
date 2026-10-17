"""R4e dev availability benchmark on the real final index; zero API, dev only.

For every turn of the 16 registered native dev fixtures that registers
`answer_required` passages, build the first-round query with the engine's own
`build_initial_query` from the visible message and visible USER facts (a
version reply becomes the `streamlit_version` fact and the first message is
reused, as the service does), retrieve with the candidate policy
(query_relevance_v1, 25 candidates, exact USER-version scope, 12000-byte
packing) with and without the version prefilter, and observe the registered
passages in the final bundle. Passages and gold are scoring-only: they never
reach the query, the retriever or the ranking. Native reads use a disposable
copy of the index; every original file is hashed before and after.

Query construction approximates the service's current-query packing; both arms
use the same queries, so the comparison is paired. Later model-authored
refinement rounds are not modelled.
"""

import argparse
import hashlib
import json
import re
from pathlib import Path

from r4b_version_ranking_receipt import disposable_verified_index

from agent_app.contracts import CaseState, Fact, RunLimits
from agent_app.orchestration.engine import SupportEngine, _Progress, build_initial_query
from agent_app.retrieval.adapter import ChromaRetrieverAdapter
from agent_app.retrieval.retriever import StreamlitRetriever
from agent_app.testing.http_pilot_runtime import offline_network

ROOT = Path(__file__).resolve().parents[1]
REGISTRATION = ROOT / "data/evaluation/split-e1-v1/native/native-registration-dev-v2.json"
VERSION = re.compile(r"\d+\.\d+\.\d+")
ARMS = {"scope_after_topk": False, "version_prefilter": True}


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def dev_turns():
    registration = json.loads(REGISTRATION.read_bytes())
    for entry in registration["fixtures"]:
        path = ROOT / entry["path"]
        raw = path.read_bytes()
        if sha(raw) != entry["sha256"] or "/test/" in entry["path"]:
            raise SystemExit("DevFixtureMismatch")
        fixture = json.loads(raw)
        if fixture["case"]["split"] != "dev":
            raise SystemExit("NonDevFixture")
        facts, first = {}, None
        for turn in fixture["turns"]:
            visible = turn["visible"]
            message = visible["message"]
            first = first or message
            if visible.get("reply_to_approved_question") and VERSION.fullmatch(message.strip()):
                facts["streamlit_version"] = message.strip()
                message = first
            for item in visible.get("reported_facts", []):
                facts[item["name"]] = item["value"]
            native = (turn.get("gold") or {}).get("native_passages") or {}
            required = (native.get("answer_required") or {}).get("requirements") or []
            if not required:
                continue
            case = CaseState(
                case_id=fixture["case"]["case_id"],
                facts=tuple(
                    Fact(
                        name=name, value=value, source_ref=f"user:{turn['id']}", turn_id=turn["id"]
                    )
                    for name, value in facts.items()
                ),
            )
            yield fixture["case"]["case_id"], turn["id"], case, message, required


def eligible(requirement, version):
    return any(
        not alt["source_id"].startswith("docstring:") or alt["source_id"].split(":")[1] == version
        for alt in requirement["alternatives"]
    )


def observed(requirement, hits):
    return any(
        hit.source_id == alt["source_id"]
        and hit.source_commit == alt["source_commit"]
        and alt["passage"] in hit.excerpt
        for alt in requirement["alternatives"]
        for hit in hits
    )


def run_arm(client, snapshot, case, query, prefilter):
    adapter = ChromaRetrieverAdapter(
        "",
        snapshot_id=snapshot,
        core_retriever=StreamlitRetriever("", snapshot_id=snapshot, client=client),
        selection_policy="query_relevance_v1",
    )
    captured = {}

    class Recording:
        def search(self, request):
            captured["request"] = request
            captured["candidates"] = adapter.search(request)
            return captured["candidates"]

    engine = SupportEngine(
        Recording(),
        None,
        snapshot_id=snapshot,
        evidence_scope="exact_user_version",
        retrieval_candidate_multiplier=5,
        evidence_utf8_budget_bytes=12000,
        retrieval_version_prefilter=prefilter,
    )
    evidence = engine._retrieve(case, (query,), set(), _Progress(RunLimits(), retrieval_rounds=0))
    return captured, evidence


def probe(index_path, manifest_sha256):
    rows = []
    with offline_network(), disposable_verified_index(index_path, manifest_sha256) as opened:
        client, snapshot, audit = opened
        for case_id, turn_id, case, message, required in dev_turns():
            version = next((f.value for f in case.facts if f.name == "streamlit_version"), None)
            query = build_initial_query(case, message)
            row = {
                "case_id": case_id,
                "turn_id": turn_id,
                "active_user_version": version,
                "query_sha256": sha(query.encode("utf-8")),
                "arms": {},
            }
            for arm, prefilter in ARMS.items():
                captured, evidence = run_arm(client, snapshot, case, query, prefilter)
                candidates = captured["candidates"].hits
                row["arms"][arm] = {
                    "request_filters": captured["request"].model_dump(mode="json")["filters"],
                    "candidates": len(candidates),
                    "eligible_candidates": sum(
                        1
                        for h in candidates
                        if not h.applicable_versions or version in h.applicable_versions
                    ),
                    "final_hits": [
                        {"source_id": h.source_id, "chunk_id": h.chunk_id} for h in evidence.hits
                    ],
                    "requirements": [
                        {
                            "requirement_id": r["requirement_id"],
                            "eligible_under_scope": eligible(r, version),
                            "in_candidates": observed(r, candidates),
                            "reached_model": observed(r, evidence.hits),
                        }
                        for r in required
                    ],
                }
            rows.append(row)
        client.verify()
    totals = {}
    for arm in ARMS:
        items = [r for row in rows for r in row["arms"][arm]["requirements"]]
        totals[arm] = {
            "requirements": len(items),
            "eligible": sum(r["eligible_under_scope"] for r in items),
            "in_candidates": sum(r["in_candidates"] for r in items),
            "reached_model": sum(r["reached_model"] for r in items),
        }
    return {
        "schema_version": 1,
        "receipt_id": "r4e-dev-availability-v1",
        "task": "R4e",
        "registration": REGISTRATION.relative_to(ROOT).as_posix(),
        "registration_sha256": sha(REGISTRATION.read_bytes()),
        "index_snapshot": snapshot,
        "index_manifest_sha256": manifest_sha256,
        "original_index_unchanged": audit["original_physical_files_before"]
        == audit["original_physical_files_after"],
        "turns": len(rows),
        "totals": totals,
        "rows": rows,
        "test_content_read": False,
        "provider_calls": 0,
        "quality_claim": False,
        "interpretation": (
            "First-round availability of registered dev passages in the final bundle. "
            "Not semantic support, answer quality or held-out evaluation; model-authored "
            "refinement rounds are not modelled."
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("ReceiptOutputExists")
    result = probe(args.index, args.manifest_sha256)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps(result["totals"], indent=2))
    print(f"turns={result['turns']} original_index_unchanged={result['original_index_unchanged']}")


if __name__ == "__main__":
    main()
