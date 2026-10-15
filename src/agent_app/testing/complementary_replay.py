"""Offline feasibility and whole-message controls; never a model quality score."""

import argparse
import hashlib
import itertools
import json
from pathlib import Path

from agent_app.contracts import GroundedPlan, GroundedRequest, OutputFeedback, ReasoningContext
from agent_app.llm.config import MetisConfig
from agent_app.llm.metis import configured_grounded_messages, request_id_for
from agent_app.reasoning.grounding import (
    GroundingRejected,
    _source_block,
    render_grounded_plan,
    source_content_sha256,
)
from agent_app.reasoning.source_selection import COMPLEMENTARY_SOURCE_POLICY

ROOT = Path(__file__).resolve().parents[3]
FOLDER = Path("experiments/core_complementary_sources_v1")
PARENT = Path("experiments/core_enum_evidence_v1/model-live-receipt-v1.json")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def replay_report(root=ROOT):
    protocol_raw = (root / FOLDER / "protocol-v1.json").read_bytes()
    protocol = json.loads(protocol_raw)
    parent_raw = (root / PARENT).read_bytes()
    if (
        digest(parent_raw) != protocol["parent"]["receipt_sha256"]
        or COMPLEMENTARY_SOURCE_POLICY != protocol["treatment"]["text"]
        or digest(COMPLEMENTARY_SOURCE_POLICY.encode()) != protocol["treatment"]["text_utf8_sha256"]
    ):
        raise ValueError("ComplementaryReplayInputChanged")
    parent = json.loads(parent_raw)
    configs = {
        enabled: MetisConfig(
            api_key="public-complementary-offline-placeholder",
            response_mode="grounded_plan",
            grounded_decision_contracts=True,
            grounded_source_selection_reminder=True,
            grounded_complementary_sources=enabled,
            grounded_source_gap_handoff=True,
            grounded_source_gap_investigation=True,
            grounded_source_capacity=True,
            grounded_compact_plan=True,
            grounded_json_object=True,
        )
        for enabled in (False, True)
    }
    rows, joint, subsets = [], [], []
    for batch in parent["batches"]:
        wires = {row["request_id"]: row for row in batch["provider_sends"]}
        jobs = {run: job for job in batch["jobs"] for run in job["run_ids"]}
        for attempt in batch["attempts"]:
            request = GroundedRequest.model_validate(attempt["request"])
            context = ReasoningContext.model_validate(attempt["context"])
            job = jobs[context.run_id]
            off = configured_grounded_messages(configs[False], request, context)
            actual_hash = digest(json.dumps(off, ensure_ascii=False, sort_keys=True).encode())
            assert actual_hash == wires[request_id_for(context)]["wire_messages_sha256"]
            sizes = []
            for repair in (False, True):
                current = context
                if repair:
                    current = ReasoningContext.model_validate(
                        {
                            **context.model_dump(mode="json"),
                            "attempt_index": 2,
                            "remaining_model_attempts": 0,
                            "remaining_retrieval_rounds": 0,
                            "can_refine": False,
                            "output_feedback": OutputFeedback(
                                issues=({"code": "invalid_shape"},)
                            ).model_dump(mode="json"),
                        }
                    )
                control = configured_grounded_messages(configs[False], request, current)
                treatment = configured_grounded_messages(configs[True], request, current)
                addition = "\n\n" + COMPLEMENTARY_SOURCE_POLICY
                assert treatment[0]["content"].count(addition) == 1
                assert treatment[0]["content"].replace(addition, "", 1) == control[0]["content"]
                assert treatment[1] == control[1]
                size = len(json.dumps(treatment, ensure_ascii=False).encode()) + 1024
                assert size <= 32768
                sizes.append({"repair": repair, "prompt_utf8_bytes_plus_guard": size})
            plan = GroundedPlan.model_validate(attempt["plan"])
            original = render_grounded_plan(
                request,
                plan,
                source_gap_handoff=True,
                source_gap_investigation=True,
                ask_source_background=True,
                concise_user_draft=True,
            )
            rows.append(
                {
                    "job_id": job["job_id"],
                    "case_id": job["case_id"],
                    "historical_arm": job["arm"],
                    "case_revision": request.case.case_revision,
                    "context_sha256": request.context_sha256,
                    "historical_wire_sha256_verified": actual_hash,
                    "SYSTEM_only_treatment": True,
                    "USER_evidence_schema_unchanged": True,
                    "normal_and_authored_repair": sizes,
                    "original_draft_sha256": digest(original.user_draft.encode()),
                }
            )
            if job["case_id"] != "dev-case-c" or job["arm"] != "fixed_guide_added":
                continue
            wire = json.loads(off[1]["content"])
            bound = wire["decision_contracts"]["rules"]["answer"]["sources"]["maxItems"]
            assert bound == 2
            hits = request.evidence.hits
            assert len(hits) == 3
            for count in range(len(hits) + 1):
                for selection in itertools.combinations(hits, count):
                    candidate = GroundedPlan(
                        context_sha256=request.context_sha256,
                        decision="answer" if selection else "escalate",
                        sources=tuple(
                            {"chunk_id": hit.chunk_id, "content_sha256": source_content_sha256(hit)}
                            for hit in selection
                        ),
                    )
                    rejected = False
                    try:
                        result = render_grounded_plan(
                            request,
                            candidate,
                            source_gap_handoff=True,
                            source_gap_investigation=True,
                            ask_source_background=True,
                            concise_user_draft=True,
                        )
                    except GroundingRejected:
                        rejected = True
                        assert count > bound
                    else:
                        assert len(result.user_draft) <= 20000
                        assert len(result.maintainer_summary) <= 20000
                        if selection:
                            assert all(
                                _source_block(request.case, h) in result.user_draft
                                for h in selection
                            )
                    subsets.append(
                        {
                            "job_id": job["job_id"],
                            "revision": request.case.case_revision,
                            "selected": [h.chunk_id for h in selection],
                            "advertised_max_sources": bound,
                            "within_advertised_bound": count <= bound,
                            "renderer_rejected": rejected,
                        }
                    )
                    if tuple(selection) == tuple(hits[1:]):
                        assert not rejected
                        assert all(gap.kind == "source" for gap in request.gaps)
                        joint.append(
                            {
                                "job_id": job["job_id"],
                                "revision": request.case.case_revision,
                                "authored_selection_not_model_output": True,
                                "original_draft_chars": len(original.user_draft),
                                "joint_draft_chars": len(result.user_draft),
                                "summary_chars": len(result.maintainer_summary),
                                "both_complete_guide_blocks": True,
                                "generic_quote_omitted_from_draft_only": True,
                                "original_three_hit_pool_unchanged": True,
                                "source_gap_names": [g.name for g in request.gaps],
                            }
                        )
    assert len(rows) == 24 and len(joint) == 4 and len(subsets) == 32
    return {
        "schema_version": 1,
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": digest(protocol_raw),
        "parent_receipt_sha256": digest(parent_raw),
        "accepted": True,
        "actual_sends": 0,
        "historical_contexts": len(rows),
        "SYSTEM_only_treatment": True,
        "USER_evidence_schema_unchanged": True,
        "renderer_unchanged": True,
        "historical_rows": rows,
        "authored_joint_replays": joint,
        "complete_subset_controls": subsets,
        "max_normal_or_authored_repair_prompt_bytes_plus_guard": max(
            size["prompt_utf8_bytes_plus_guard"]
            for row in rows
            for size in row["normal_and_authored_repair"]
        ),
        "held_out_test": False,
        "real_RAG": False,
        "human_usefulness": None,
        "model_quality_gain_claim": False,
        "note": "Historical contexts include both old availability arms; only the four guide-present C contexts support the authored joint-selection feasibility replay. All current live arms instead receive the same guide-present pool. No historical proposal, release or failure is rewritten.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = replay_report()
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "accepted": report["accepted"],
                "actual_sends": 0,
                "historical_contexts": report["historical_contexts"],
            }
        )
    )


if __name__ == "__main__":
    main()
