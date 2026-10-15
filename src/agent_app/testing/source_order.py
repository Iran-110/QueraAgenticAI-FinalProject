"""One registered complete-record position diagnostic, confined to test suppliers.

The shared answer-linked guide stays excluded from real RAG. Rotation never
examines record content, identity, version, gold or an expected model response.
"""

import argparse
import hashlib
import itertools
import json
from pathlib import Path

from agent_app.contracts import (
    EvidenceBundle,
    GroundedPlan,
    GroundedRequest,
    OutputFeedback,
    ReasoningContext,
    RetrievalRequest,
)
from agent_app.llm.config import MetisConfig
from agent_app.llm.metis import configured_grounded_messages, request_id_for
from agent_app.reasoning.compact_plan import expand_compact_plan
from agent_app.reasoning.grounding import (
    GroundingRejected,
    _source_block,
    _source_reference_block,
    make_grounded_request,
    render_grounded_plan,
    source_content_sha256,
)
from agent_app.testing.enum_evidence import fixture_retriever_factory as fixed_factory

ROOT = Path(__file__).resolve().parents[3]
FOLDER = Path("experiments/core_source_order_v1")
PROTOCOL_SHA256 = "2ec9f8b3f0adfc7bf889b05ffa6aacad996f661d9f90c42c0bed99ade7910bee"
ARMS = ("original_order", "rotate_left_one")


class SourceOrderRejected(ValueError):
    def __init__(self):
        super().__init__("SourceOrderRejected")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _bundle_digest(bundle):
    return digest(
        json.dumps(bundle.model_dump(mode="json"), sort_keys=True, ensure_ascii=False).encode()
    )


def ordered_bundle(bundle, order):
    """Uniformly move the first complete record to the end, when one exists."""
    if type(order) is not str or order not in ARMS:
        raise SourceOrderRejected()
    original = EvidenceBundle.model_validate(bundle.model_dump())
    hits = original.hits
    if order == "rotate_left_one" and len(hits) > 1:
        hits = (*hits[1:], hits[0])
    return EvidenceBundle.model_validate({**original.model_dump(), "hits": hits})


class _OrderedSupplier:
    def __init__(self, fixed, records, identity):
        self.fixed = fixed
        self.records = records
        # Strings are copied now, so a later caller mutation cannot relabel a send.
        self.identity = dict(identity)

    @property
    def bundle(self):
        return ordered_bundle(self.fixed.bundle, self.identity["evidence_order"])

    def search(self, request: RetrievalRequest):
        request = RetrievalRequest.model_validate(request.model_dump())
        fixed = self.fixed.search(request)
        rotated = ordered_bundle(fixed, self.identity["evidence_order"])
        self.records.append(
            {
                **self.identity,
                "fixed_supplier_call": self.fixed.calls,
                "actual_search": False,
                "requested_queries": list(request.queries),
                "requested_top_k": request.top_k,
                "snapshot_id": rotated.snapshot_id,
                "fixed_chunk_ids": [h.chunk_id for h in fixed.hits],
                "returned_chunk_ids": [h.chunk_id for h in rotated.hits],
                "fixed_bundle_sha256": _bundle_digest(fixed),
                "returned_bundle_sha256": _bundle_digest(rotated),
                "same_complete_record_set": sorted(source_content_sha256(h) for h in fixed.hits)
                == sorted(source_content_sha256(h) for h in rotated.hits),
            }
        )
        return rotated


def fixture_retriever_factory(packet, fixtures, records):
    """Use only the immutable guide-present CURRENT-turn supplier, then rotate."""
    parent = fixed_factory(packet, fixtures, [])
    fixture_ids = {f.case["case_id"]: str(f.data["fixture_id"]) for f in fixtures.values()}

    def supply(job, turn):
        try:
            if (
                type(job) is not dict
                or type(job["arm"]) is not str
                or job["arm"] not in ARMS
                or type(job["evidence_order"]) is not str
                or job["evidence_order"] != job["arm"]
                or type(job["evidence_condition"]) is not str
                or job["evidence_condition"] != "fixed_guide_added"
                or job.get("complementary_sources") is not False
                or type(job["case_id"]) is not str
                or (
                    "job_id" in job
                    and (type(job["job_id"]) is not str or not job["job_id"].strip())
                )
                or ("fixture_id" in job and job["fixture_id"] != fixture_ids[job["case_id"]])
            ):
                raise SourceOrderRejected()
            fixed, snapshot = parent({"case_id": job["case_id"], "arm": "fixed_guide_added"}, turn)
            identity = {
                "arm": job["arm"],
                "evidence_order": job["evidence_order"],
                "evidence_condition": "fixed_guide_added",
                "case_id": job["case_id"],
                "fixture_id": fixture_ids[job["case_id"]],
                "turn_id": str(turn["id"]),
            }
            if "job_id" in job:
                identity["job_id"] = job["job_id"]
            return _OrderedSupplier(fixed, records, identity), snapshot
        except (ValueError, KeyError, TypeError):
            raise SourceOrderRejected() from None

    return supply


def _config(complementary=False):
    return MetisConfig(
        api_key="public-source-order-offline-placeholder",
        response_mode="grounded_plan",
        grounded_decision_contracts=True,
        grounded_source_selection_reminder=True,
        grounded_complementary_sources=complementary,
        grounded_source_gap_handoff=True,
        grounded_source_gap_investigation=True,
        grounded_source_capacity=True,
        grounded_compact_plan=True,
        grounded_json_object=True,
    )


def _render(request, plan):
    return render_grounded_plan(
        request,
        plan,
        source_gap_handoff=True,
        source_gap_investigation=True,
        ask_source_background=True,
        concise_user_draft=True,
    )


def _plan(request, content_refs, decision="answer", **other):
    return GroundedPlan(
        context_sha256=request.context_sha256,
        decision=decision,
        sources=tuple(
            {"chunk_id": h.chunk_id, "content_sha256": source_content_sha256(h)}
            for h in content_refs
        ),
        **other,
    )


def replay_report(root=ROOT):
    protocol_raw = (root / FOLDER / "protocol-v1.json").read_bytes()
    if digest(protocol_raw) != PROTOCOL_SHA256:
        raise SourceOrderRejected()
    protocol = json.loads(protocol_raw)
    parent_raw = (root / protocol["parent"]["receipt_path"]).read_bytes()
    packet_raw = (root / protocol["parent"]["source_packet_path"]).read_bytes()
    if (
        digest(parent_raw) != protocol["parent"]["receipt_sha256"]
        or digest(packet_raw) != protocol["parent"]["source_packet_sha256"]
    ):
        raise SourceOrderRejected()
    parent, packet = json.loads(parent_raw), json.loads(packet_raw)
    guide_ids = {record["hit"]["chunk_id"] for record in packet["source_records"]}
    rows, subsets, joint = [], [], []
    for batch in parent["batches"]:
        wires = {s["request_id"]: s for s in batch["provider_sends"]}
        jobs = {run: job for job in batch["jobs"] for run in job["run_ids"]}
        for attempt in batch["attempts"]:
            original = GroundedRequest.model_validate(attempt["request"])
            context = ReasoningContext.model_validate(attempt["context"])
            job = jobs[context.run_id]
            actual_messages = configured_grounded_messages(
                _config(job["complementary_sources"]), original, context
            )
            actual_hash = digest(
                json.dumps(actual_messages, ensure_ascii=False, sort_keys=True).encode()
            )
            assert actual_hash == wires[request_id_for(context)]["wire_messages_sha256"]
            old_plan = GroundedPlan.model_validate(attempt["plan"])
            old_output = _render(original, old_plan)
            for arm in ARMS:
                bundle = ordered_bundle(original.evidence, arm)
                request = make_grounded_request(
                    original.case,
                    original.user_message,
                    bundle,
                    gaps=original.gaps,
                    conflict_groups=original.conflict_groups,
                )
                assert (
                    request.case == original.case and request.user_message == original.user_message
                )
                assert (
                    request.gaps == original.gaps
                    and request.conflict_groups == original.conflict_groups
                )
                assert sorted(source_content_sha256(h) for h in bundle.hits) == sorted(
                    source_content_sha256(h) for h in original.evidence.hits
                )
                messages = configured_grounded_messages(_config(), request, context)
                old_messages = configured_grounded_messages(_config(), original, context)
                assert messages[0] == old_messages[0]
                assert (
                    json.loads(messages[1]["content"])["response_schema"]
                    == json.loads(old_messages[1]["content"])["response_schema"]
                )
                hits = {h.chunk_id: h for h in bundle.hits}
                same_content = _plan(
                    request,
                    [hits[s.chunk_id] for s in old_plan.sources],
                    old_plan.decision,
                    question_name=old_plan.question_name,
                    retrieval_queries=old_plan.retrieval_queries,
                )
                output = _render(request, same_content)
                assert len(output.user_draft) == len(old_output.user_draft)
                assert len(output.maintainer_summary) == len(old_output.maintainer_summary)
                assert output.rationale == old_output.rationale
                assert {(x.claim, x.chunk_id) for x in output.evidence_links} == {
                    (x.claim, x.chunk_id) for x in old_output.evidence_links
                }
                for source in old_plan.sources:
                    assert (
                        _source_block(request.case, hits[source.chunk_id])
                        in output.maintainer_summary
                    )
                    if old_plan.decision == "answer":
                        assert (
                            _source_block(request.case, hits[source.chunk_id]) in output.user_draft
                        )
                    if old_plan.decision == "ask":
                        assert (
                            _source_reference_block(request.case, hits[source.chunk_id])
                            in output.user_draft
                        )
                indices = [
                    next(i for i, h in enumerate(bundle.hits) if h.chunk_id == s.chunk_id)
                    for s in old_plan.sources
                ]
                compact = {
                    "context_sha256": request.context_sha256,
                    "decision": old_plan.decision,
                    "sources": indices,
                }
                if old_plan.decision == "ask":
                    compact["question_name"] = old_plan.question_name
                assert expand_compact_plan(json.dumps(compact), request) == same_content
                changed = request.context_sha256 != original.context_sha256
                if changed:
                    stale = {**compact, "context_sha256": original.context_sha256}
                    try:
                        expand_compact_plan(json.dumps(stale), request)
                    except GroundingRejected as error:
                        assert error.code == "grounded_context_mismatch"
                    else:
                        raise AssertionError("Old ordered context must not bind a new request")
                sizes = []
                for repair in (False, True):
                    current = (
                        context
                        if not repair
                        else ReasoningContext.model_validate(
                            {
                                **context.model_dump(),
                                "attempt_index": 2,
                                "remaining_model_attempts": 0,
                                "remaining_retrieval_rounds": 0,
                                "can_refine": False,
                                "output_feedback": OutputFeedback(
                                    issues=({"code": "invalid_shape"},)
                                ),
                            }
                        )
                    )
                    projected = configured_grounded_messages(_config(), request, current)
                    size = len(json.dumps(projected, ensure_ascii=False).encode()) + 1024
                    assert size <= 32768
                    sizes.append({"repair": repair, "prompt_utf8_bytes_plus_guard": size})
                rows.append(
                    {
                        "job_id": job["job_id"],
                        "case_id": job["case_id"],
                        "historical_arm": job["arm"],
                        "evidence_order": arm,
                        "case_revision": request.case.case_revision,
                        "actual_historical_wire_sha256_verified": actual_hash,
                        "historical_actual_complementary_sources": job["complementary_sources"],
                        "common_policy_is_historical_actual_policy": job["complementary_sources"]
                        is False,
                        "ordered_context_rebound": changed,
                        "context_sha256": request.context_sha256,
                        "complete_record_set_unchanged": True,
                        "authored_content_reference_set_unchanged": True,
                        "complete_blocks_and_qualifiers_preserved": True,
                        "authored_original_draft_chars": len(old_output.user_draft),
                        "authored_reordered_draft_chars": len(output.user_draft),
                        "fresh_source_indexes": indices,
                        "normal_and_authored_repair": sizes,
                    }
                )
                if job["case_id"] != "dev-case-c":
                    continue
                assert len(bundle.hits) == 3 and guide_ids <= set(hits)
                bound = json.loads(messages[1]["content"])["decision_contracts"]["rules"]["answer"][
                    "sources"
                ]["maxItems"]
                assert bound == 2
                for count in range(4):
                    for selected in itertools.combinations(bundle.hits, count):
                        authored = _plan(request, selected, "answer" if selected else "escalate")
                        rejected = False
                        try:
                            rendered = _render(request, authored)
                        except GroundingRejected as error:
                            assert error.code == "grounded_render_too_large" and count > bound
                            rejected = True
                        else:
                            assert (
                                len(rendered.user_draft) <= 20000
                                and len(rendered.maintainer_summary) <= 20000
                                and len(rendered.rationale) <= 2000
                            )
                        subsets.append(
                            {
                                "job_id": job["job_id"],
                                "evidence_order": arm,
                                "revision": request.case.case_revision,
                                "selected_chunk_ids": [h.chunk_id for h in selected],
                                "advertised_max_sources": bound,
                                "within_advertised_bound": count <= bound,
                                "renderer_rejected": rejected,
                            }
                        )
                selected_guides = [h for h in bundle.hits if h.chunk_id in guide_ids]
                guided = _render(request, _plan(request, selected_guides))
                assert len(guided.user_draft) == 7099 and all(
                    _source_block(request.case, h) in guided.user_draft for h in selected_guides
                )
                joint.append(
                    {
                        "job_id": job["job_id"],
                        "evidence_order": arm,
                        "revision": request.case.case_revision,
                        "authored_not_model_output": True,
                        "both_complete_guides": True,
                        "generic_still_present_in_model_pool": True,
                        "draft_chars": len(guided.user_draft),
                        "summary_chars": len(guided.maintainer_summary),
                        "source_gap_names": [g.name for g in request.gaps],
                        "advertised_max_sources": bound,
                    }
                )
    assert len(rows) == 48 and len(joint) == 16 and len(subsets) == 128
    return {
        "schema_version": 1,
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": digest(protocol_raw),
        "parent_receipt_sha256": digest(parent_raw),
        "source_packet_sha256": digest(packet_raw),
        "accepted": True,
        "actual_sends": 0,
        "historical_contexts": 24,
        "historical_actual_wire_hashes_verified": 24,
        "historical_common_policy_wire_hashes_verified": 12,
        "common_prompt": True,
        "common_SYSTEM_policy": True,
        "complete_record_set_unchanged": True,
        "USER_fact_and_record_set_unchanged": True,
        "ordered_USER_payload_and_context_may_differ": True,
        "historical_rows": rows,
        "authored_joint_replays": joint,
        "complete_subset_controls": subsets,
        "retained_renderer_rejections": sum(x["renderer_rejected"] for x in subsets),
        "max_normal_or_authored_repair_prompt_bytes_plus_guard": max(
            s["prompt_utf8_bytes_plus_guard"]
            for row in rows
            for s in row["normal_and_authored_repair"]
        ),
        "held_out_test": False,
        "real_RAG": False,
        "human_usefulness": None,
        "model_quality_gain_claim": False,
        "note": "All24 negative-parent contexts revalidated under their actual historical policy. Fresh diagnostic arms both use the old common policy, not the failed suffix. Authored semantic selections preserve complete blocks and length, but quotation order can change; fresh model selection remains unobserved. No original receipt, overflow or release is rewritten.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = replay_report()
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps({"accepted": report["accepted"], "actual_sends": 0, "historical_contexts": 24})
    )


if __name__ == "__main__":
    main()
