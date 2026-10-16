"""R4b review: coverage, relevance and exclusion of evidence that reached the model.

Reads the before/after receipt and a separately authored label file, rebuilds
the registered 18/36 corpus from the pinned seed (no vector store, no network)
and reports, per state and arm:

- required-evidence recall at the final bundle (version-specific records only
  count once the USER version is known; the policy withholds them before);
- the relevance mix of the final bundle (direct / background / off_topic);
- exclusion: no Issue/comment/outcome, reserved or proposed-reserved Issue,
  answer-linked guide or release note can be indexed or reach the model.

Labels are applied after retrieval only and never select evidence. Zero API.
"""

import argparse
import hashlib
import json
from pathlib import Path

from agent_app.retrieval.pilot_corpus import build_pilot_corpus

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "streamlit-data-for-dev-test"
SPLIT = ROOT / "experiments/dev_rag_coverage_v1/split-manifest.json"
ALLOWLIST = ROOT / "experiments/dev_rag_coverage_v1/allowlist.json"
# docs/pr55-evidence-review.fa.md: proposed for the next manifest (46 -> 53).
PROPOSED_RESERVATIONS = (4909, 6985, 7300, 7419, 8734, 13022, 14297)
DENIED_SOURCES = (
    "docs:content/develop/concepts/app-design/custom-classes.md",
    "docs:content/develop/quick-references/release-notes/",
)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def api_of(source_id):
    parts = source_id.split(":")
    if parts[0] == "docstring" and len(parts) == 3:
        return parts[2].removeprefix("streamlit."), parts[1]
    return None, None


def required_met(item, final, version):
    if item["kind"] == "chunk":
        return any(h["chunk_id"] == item["chunk_id"] for h in final)
    return any(
        api_of(h["source_id"]) == (item["api"], version) and version in h["versions"] for h in final
    )


def review(receipt, labels, corpus):
    chunks = {chunk["chunk_id"]: chunk for chunk in corpus["chunks"]}
    exclusions = corpus["exclusions"]
    source_ids = {chunk["metadata"]["source_id"] for chunk in corpus["chunks"]}
    index_checks = {
        "snapshot_matches_receipt": True,
        "indexed_issue_count": exclusions["indexed_issue_count"],
        "indexed_comment_count": exclusions["indexed_comment_count"],
        "reserved_issue_ids": len(exclusions["reserved_issue_ids"]),
        "proposed_reservations_not_yet_in_manifest": sorted(
            set(PROPOSED_RESERVATIONS) - set(exclusions["reserved_issue_ids"])
        ),
        "only_doc_source_types": all(
            chunk["metadata"]["source_type"] == "doc" for chunk in corpus["chunks"]
        ),
        "denied_sources_indexed": sorted(
            s for s in source_ids if any(s.startswith(d) for d in DENIED_SOURCES)
        ),
    }
    rows, unlabeled, leaked = [], [], []
    for obs in receipt["observations"]:
        case, version = obs["case_id"], obs["active_user_version"]
        case_labels = labels["labels"].get(case, {})
        required = labels["required_evidence"].get(case, [])
        row = {
            "case_id": case,
            "turn_id": obs["turn_id"],
            "retrieval_round": obs["retrieval_round"],
            "active_user_version": version,
            "arms": {},
        }
        for arm, data in obs["arms"].items():
            final = data["final_hits"]
            mix = {"direct": 0, "background": 0, "off_topic": 0}
            for hit in final:
                chunk = chunks.get(hit["chunk_id"])
                if (
                    chunk is None
                    or chunk["metadata"]["source_type"] != "doc"
                    or any(hit["source_id"].startswith(d) for d in DENIED_SOURCES)
                ):
                    leaked.append((case, obs["turn_id"], arm, hit["chunk_id"]))
                label = case_labels.get(hit["chunk_id"])
                if label is None:
                    unlabeled.append((case, hit["chunk_id"]))
                else:
                    mix[label[0]] += 1
            eligible = [item for item in required if item["kind"] == "chunk" or version is not None]
            met = [item for item in eligible if required_met(item, final, version)]
            candidates = data.get("candidate_chunk_ids")
            missing_ranks = {
                item["chunk_id"]: (
                    candidates.index(item["chunk_id"]) + 1
                    if item["chunk_id"] in candidates
                    else "not_in_candidates"
                )
                for item in eligible
                if item["kind"] == "chunk" and item not in met and candidates is not None
            }
            row["arms"][arm] = {
                "final_count": len(final),
                "relevance_mix": mix,
                "required_eligible": len(eligible),
                "required_reached": len(met),
                "required_missing": [
                    item.get("chunk_id") or f"{item['api']}@{version}"
                    for item in eligible
                    if item not in met
                ],
                "missing_chunk_candidate_rank": missing_ranks,
            }
        rows.append(row)
    if unlabeled:
        raise SystemExit(f"UnlabeledFinalHits: {sorted(set(unlabeled))}")
    totals = {}
    for row in rows:
        for arm, data in row["arms"].items():
            total = totals.setdefault(
                arm,
                {
                    "required_eligible": 0,
                    "required_reached": 0,
                    "final": 0,
                    "direct": 0,
                    "background": 0,
                    "off_topic": 0,
                },
            )
            total["required_eligible"] += data["required_eligible"]
            total["required_reached"] += data["required_reached"]
            total["final"] += data["final_count"]
            for key, value in data["relevance_mix"].items():
                total[key] += value
    return {
        "index_exclusion_checks": index_checks,
        "final_bundle_exclusion_violations": leaked,
        "states": rows,
        "totals": totals,
    }


def summary(result):
    lines = ["| arm | required reached | final hits | direct | background | off_topic |"]
    lines.append("|---|---|---|---|---|---|")
    for arm, t in result["totals"].items():
        lines.append(
            f"| {arm} | {t['required_reached']}/{t['required_eligible']} | {t['final']} | "
            f"{t['direct']} | {t['background']} | {t['off_topic']} |"
        )
    lines.append("")
    for row in result["states"]:
        for arm, data in row["arms"].items():
            if data["required_missing"]:
                ranks = data["missing_chunk_candidate_rank"]
                lines.append(
                    f"missing {row['case_id']}/{row['turn_id']}/{arm}: "
                    + ", ".join(data["required_missing"])
                    + (f"  candidate_rank={ranks}" if ranks else "")
                )
    lines.append("")
    lines.append(f"index checks: {json.dumps(result['index_exclusion_checks'])}")
    lines.append(
        f"final-bundle exclusion violations: {result['final_bundle_exclusion_violations']}"
    )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("ReviewOutputExists")
    receipt_raw, labels_raw = args.receipt.read_bytes(), args.labels.read_bytes()
    receipt, labels = json.loads(receipt_raw), json.loads(labels_raw)
    corpus_obj = build_pilot_corpus(SEED, SPLIT, ALLOWLIST)
    if corpus_obj.snapshot_id != receipt["index"]["snapshot_id"]:
        raise SystemExit("CorpusSnapshotMismatch")
    result = {
        "schema_version": 1,
        "review_id": "r4b-coverage-relevance-review-v1",
        "task": "R4b",
        "receipt_sha256": sha(receipt_raw),
        "labels_sha256": sha(labels_raw),
        "labels_reviewer_kind": labels["reviewer_kind"],
        "labels_human_confirmed": labels["human_confirmed"],
        "snapshot_id": corpus_obj.snapshot_id,
        **review(receipt, labels, corpus_obj.manifest["corpus"]),
        "known_out_of_corpus": labels["known_out_of_corpus"],
        "provider_calls": 0,
        "quality_claim": False,
        "human_usefulness": None,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(summary(result))


if __name__ == "__main__":
    main()
