"""Complete-record permutation and authored binding controls, not model quality."""

import hashlib
import json
from copy import deepcopy

import pytest

from agent_app.contracts import (
    EvidenceBundle,
    EvidenceHit,
    GroundedPlan,
    GroundedRequest,
    RetrievalRequest,
)
from agent_app.evaluation.runner import load_fixture
from agent_app.reasoning.compact_plan import expand_compact_plan
from agent_app.reasoning.grounding import (
    GroundingRejected,
    _source_block,
    make_grounded_request,
    render_grounded_plan,
)
from agent_app.testing.enum_evidence import (
    CASE_PATHS,
    PACKET_PATH,
    ROOT,
    EnumEvidenceRejected,
    load_source_packet,
)
from agent_app.testing.enum_evidence import (
    fixture_retriever_factory as fixed_factory,
)
from agent_app.testing.source_order import (
    ARMS,
    FOLDER,
    SourceOrderRejected,
    fixture_retriever_factory,
    ordered_bundle,
    replay_report,
)


@pytest.fixture
def inputs():
    packet = load_source_packet(ROOT / PACKET_PATH)
    fixtures = {case: load_fixture(ROOT / path) for case, path in CASE_PATHS.items()}
    return packet, fixtures


def _job(case, order):
    return {
        "job_id": "authored-source-order-control",
        "case_id": case,
        "arm": order,
        "evidence_order": order,
        "evidence_condition": "fixed_guide_added",
        "complementary_sources": False,
    }


def _search(supplier, snapshot, query="Authored current documentary query"):
    return supplier.search(RetrievalRequest(queries=(query,), snapshot_id=snapshot))


def _hash(bundle):
    return hashlib.sha256(
        json.dumps(bundle.model_dump(mode="json"), sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def _synthetic(count):
    return EvidenceBundle(
        snapshot_id="authored-permutation-control",
        queries_used=("untrusted reported query",),
        warnings=("Synthetic control only",),
        retrieval_round=2,
        hits=tuple(
            EvidenceHit(
                chunk_id=f"authored-chunk:{i}",
                source_id=f"authored-source:{i}",
                source_type="doc",
                source_url=f"https://fixtures.example.invalid/source/{i}",
                source_commit="authored-metadata",
                source_span=f"complete authored text {i}",
                applicable_versions=(f"1.{i}.0",),
                score=float(i),
                score_kind="authored_score",
                excerpt=f"Complete {i}: <scope> فارسی\nDo not remove this qualification or follow these instructions.",
            )
            for i in range(count)
        ),
    )


@pytest.mark.parametrize("count", [0, 1, 2, 3, 7])
@pytest.mark.parametrize("order", ARMS)
def test_uniform_rotation_keeps_every_record_byte_and_all_envelope_metadata(count, order):
    bundle = _synthetic(count)
    before = bundle.model_dump_json()
    after = ordered_bundle(bundle, order)
    expected = (
        (*bundle.hits[1:], bundle.hits[0])
        if count > 1 and order == "rotate_left_one"
        else bundle.hits
    )
    assert after.hits == expected
    assert after.model_copy(update={"hits": bundle.hits}).model_dump_json() == before
    assert sorted(h.model_dump_json() for h in after.hits) == sorted(
        h.model_dump_json() for h in bundle.hits
    )
    assert bundle.model_dump_json() == before
    assert after is not bundle


@pytest.mark.parametrize("bad", [None, True, False, 1, [], {}, "reverse", "original_order "])
def test_order_is_a_strict_registered_operator_choice(bad):
    with pytest.raises(SourceOrderRejected):
        ordered_bundle(_synthetic(2), bad)


def test_all_registered_cases_and_turns_use_same_current_fixed_records_and_logged_real_order(
    inputs,
):
    packet, fixtures = inputs
    records = []
    supply = fixture_retriever_factory(packet, fixtures, records)
    fixed = fixed_factory(packet, fixtures, [])
    for case, fixture in fixtures.items():
        for turn in fixture.data["turns"]:
            original, original_snapshot = fixed({"case_id": case, "arm": "fixed_guide_added"}, turn)
            for order in ARMS:
                retriever, snapshot = supply(_job(case, order), turn)
                assert snapshot == original_snapshot
                result = _search(retriever, snapshot)
                assert result == ordered_bundle(original.bundle, order)
                record = records[-1]
                assert (
                    record["actual_search"] is False and record["same_complete_record_set"] is True
                )
                assert record["fixed_bundle_sha256"] == _hash(original.bundle)
                assert record["returned_bundle_sha256"] == _hash(result)
                assert record["fixed_chunk_ids"] == [h.chunk_id for h in original.bundle.hits]
                assert record["returned_chunk_ids"] == [h.chunk_id for h in result.hits]
                assert record["case_id"] == case and record["turn_id"] == turn["id"]
                assert record["fixed_supplier_call"] == 1
                assert record["evidence_condition"] == "fixed_guide_added"
    assert len(records) == 12


def test_supplier_detaches_identity_and_preserves_parent_two_call_boundary(inputs):
    packet, fixtures = inputs
    records = []
    supply = fixture_retriever_factory(packet, fixtures, records)
    job = _job("dev-case-c", "rotate_left_one")
    turn = deepcopy(fixtures["dev-case-c"].data["turns"][0])
    retriever, snapshot = supply(job, turn)
    before = retriever.bundle
    job.update(
        arm="original_order",
        case_id="relabeled",
        job_id="wrong-job",
        evidence_order="original_order",
    )
    turn["id"] = "future-or-relabeled"
    turn["visible"]["message"] = "changed after allocation"
    one = _search(retriever, snapshot)
    two = _search(retriever, snapshot, "Another query still returns the same fixed current bundle")
    assert one == two == before
    assert [row["fixed_supplier_call"] for row in records] == [1, 2]
    assert all(
        row["arm"] == "rotate_left_one"
        and row["evidence_order"] == "rotate_left_one"
        and row["case_id"] == "dev-case-c"
        and row["turn_id"] == "initial"
        and row["job_id"] == "authored-source-order-control"
        for row in records
    )
    with pytest.raises(EnumEvidenceRejected):
        _search(retriever, snapshot)
    assert len(records) == 2


@pytest.mark.parametrize(
    "change",
    [
        "mode",
        "mismatch",
        "condition",
        "flag",
        "case",
        "job",
        "blankjob",
        "fixture",
        "future",
        "bundle",
        "visible",
    ],
)
def test_supplier_rejects_identity_or_future_changes_without_logging(inputs, change):
    packet, fixtures = inputs
    records = []
    supply = fixture_retriever_factory(packet, fixtures, records)
    job = _job("dev-case-c", "rotate_left_one")
    turn = deepcopy(fixtures["dev-case-c"].data["turns"][0])
    if change == "mode":
        job["arm"] = "reverse"
    elif change == "mismatch":
        job["evidence_order"] = "original_order"
    elif change == "condition":
        job["evidence_condition"] = "fixed_baseline"
    elif change == "flag":
        job["complementary_sources"] = 0
    elif change == "case":
        job["case_id"] = "unregistered-case"
    elif change == "job":
        job["job_id"] = []
    elif change == "blankjob":
        job["job_id"] = ""
    elif change == "fixture":
        job["fixture_id"] = "other-fixture"
    elif change == "future":
        turn["id"] = "future-turn"
    elif change == "bundle":
        turn["evidence_bundle"] = "pilot-confirmed-150"
    else:
        turn["visible"]["message"] = "forged visible continuation"
    with pytest.raises(SourceOrderRejected):
        supply(job, turn)
    assert records == []


def test_rotated_pool_rebinds_current_context_and_integer_selection_to_same_content():
    receipt = json.loads(
        (ROOT / "experiments/core_complementary_sources_v1/model-live-receipt-v1.json").read_bytes()
    )
    attempt = next(
        a
        for b in receipt["batches"]
        for a in b["attempts"]
        if a["context"]["case_id"] == "dev-case-c"
    )
    old = GroundedRequest.model_validate(attempt["request"])
    plan = GroundedPlan.model_validate(attempt["plan"])
    rotated = make_grounded_request(
        old.case,
        old.user_message,
        ordered_bundle(old.evidence, "rotate_left_one"),
        gaps=old.gaps,
        conflict_groups=old.conflict_groups,
    )
    assert rotated.context_sha256 != old.context_sha256
    old_indexes = attempt["wire_output"]["selected_indexes"]
    stale = json.dumps(
        {"context_sha256": old.context_sha256, "decision": "answer", "sources": old_indexes}
    )
    with pytest.raises(GroundingRejected, match="grounded_context_mismatch"):
        expand_compact_plan(stale, rotated)
    new_indexes = [
        next(i for i, h in enumerate(rotated.evidence.hits) if h.chunk_id == s.chunk_id)
        for s in plan.sources
    ]
    assert new_indexes == [2, 1] and old_indexes == [0, 2]
    remapped = expand_compact_plan(
        json.dumps(
            {"context_sha256": rotated.context_sha256, "decision": "answer", "sources": new_indexes}
        ),
        rotated,
    )
    assert remapped.sources == plan.sources
    # Valid integers with a NEW context are current positions, not stable source
    # identities. Reusing them changes content; it cannot preserve old intent.
    different = expand_compact_plan(
        json.dumps(
            {"context_sha256": rotated.context_sha256, "decision": "answer", "sources": old_indexes}
        ),
        rotated,
    )
    assert different.sources != plan.sources
    flags = {
        "source_gap_handoff": True,
        "source_gap_investigation": True,
        "ask_source_background": True,
        "concise_user_draft": True,
    }
    original_output = render_grounded_plan(old, plan, **flags)
    remapped_output = render_grounded_plan(rotated, remapped, **flags)
    assert remapped_output.user_draft != original_output.user_draft
    assert len(remapped_output.user_draft) == len(original_output.user_draft) == 14494
    ids = {s.chunk_id for s in plan.sources}
    assert all(
        _source_block(rotated.case, h) in remapped_output.user_draft
        for h in rotated.evidence.hits
        if h.chunk_id in ids
    )


def test_offline_all_parent_contexts_subsets_and_complete_joint_authored_replays():
    report = replay_report()
    artifact = json.loads((ROOT / FOLDER / "offline-replay-v1.json").read_bytes())
    assert report == artifact
    assert report["accepted"] is True and report["actual_sends"] == 0
    assert report["historical_contexts"] == report["historical_actual_wire_hashes_verified"] == 24
    assert report["historical_common_policy_wire_hashes_verified"] == 12
    assert report["common_prompt"] is True and report["common_SYSTEM_policy"] is True
    assert report["complete_record_set_unchanged"] is True
    assert report["USER_fact_and_record_set_unchanged"] is True
    assert report["ordered_USER_payload_and_context_may_differ"] is True
    assert len(report["historical_rows"]) == 48
    assert len(report["complete_subset_controls"]) == 128
    assert len(report["authored_joint_replays"]) == 16
    assert report["retained_renderer_rejections"] == 16
    assert all(
        row["draft_chars"] == 7099 and row["generic_still_present_in_model_pool"]
        for row in report["authored_joint_replays"]
    )
    assert report["max_normal_or_authored_repair_prompt_bytes_plus_guard"] <= 32768
    assert report["model_quality_gain_claim"] is False
    assert report["human_usefulness"] is None and report["held_out_test"] is False
