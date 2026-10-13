"""Frozen input projection and round integrity, without executing authored gold."""

import hashlib
import json
from dataclasses import asdict, fields, replace

import pytest

from agent_app.contracts import GroundedGap, ReasoningContext, RetrievalRequest
from agent_app.reasoning import grounding_experiments
from agent_app.reasoning.grounding import (
    build_grounded_messages,
    make_grounded_request,
    source_content_sha256,
)
from agent_app.testing import controlled_decision_inputs as inputs


@pytest.fixture(scope="module")
def pack():
    return grounding_experiments.load_grounding_pack()


def condition(name="controlled-v8-full"):
    return next(item for item in inputs.load_conditions() if item.condition_id == name)


def request(item, query="Authored query for fixed evidence.", **changes):
    return RetrievalRequest(
        **({"queries": (query,), "snapshot_id": item.bundles[0].snapshot_id, "top_k": 5} | changes)
    )


def encoded(value):
    return json.dumps(
        value,
        default=lambda model: model.model_dump(mode="json"),
        sort_keys=True,
        ensure_ascii=False,
    )


def test_all_six_original_material_cases_and_complete_source_bytes_are_retained(pack):
    actual = inputs.load_conditions()
    assert len(actual) == 6
    assert [item.condition_id for item in actual] == [case["id"] for case in pack.suite["cases"]]
    for index, (item, original) in enumerate(
        zip(actual, pack.suite["cases"], strict=True), start=1
    ):
        actual_case = item.case.model_dump(mode="json")
        assert actual_case["case_id"] == f"c4-condition-{index:02d}"
        assert {key: value for key, value in actual_case.items() if key != "case_id"} == {
            key: value for key, value in original["case_state"].items() if key != "case_id"
        }
        assert item.user_message.encode() == original["user_message"].encode()
        assert [gap.model_dump(mode="json") for gap in item.gaps if gap.kind == "user"] == [
            gap for gap in original["grounding_catalog"]["gaps"] if gap["kind"] == "user"
        ]
        if item.condition_id not in {
            "controlled-v8-key-evidence-removed",
            "controlled-v8-refinement-stale-source",
        }:
            assert [gap.model_dump(mode="json") for gap in item.gaps] == original[
                "grounding_catalog"
            ]["gaps"]
        assert [list(group) for group in item.conflict_groups] == original["grounding_catalog"][
            "conflict_groups"
        ]
        for supplied, raw in zip(item.bundles, original["bundles"], strict=True):
            actual_bundle = supplied.model_dump(mode="json")
            assert {key: value for key, value in actual_bundle.items() if key != "hits"} == {
                key: value for key, value in raw.items() if key != "hits"
            }
            for hit, record in zip(supplied.hits, raw["hits"], strict=True):
                actual_hit = hit.model_dump(mode="json")
                assert {key: actual_hit[key] for key in record} == record
                assert all(value is None for key, value in actual_hit.items() if key not in record)
                assert hit.excerpt.encode() == record["excerpt"].encode()
                assert hit.source_url == record["source_url"]
                assert hit.source_span == record["source_span"]
                assert hit.source_commit == record["source_commit"]


def test_runtime_class_contains_only_material_not_gold_replay_or_future_user_answers():
    allowed = {"condition_id", "case", "user_message", "bundles", "gaps", "conflict_groups"}
    assert {field.name for field in fields(inputs.ControlledCondition)} == allowed
    for item in inputs.load_conditions():
        assert not hasattr(item, "__dict__")
        assert set(asdict(item)) == allowed
        serialized = encoded(asdict(item))
        for excluded in (
            '"authored_replays"',
            '"expectations"',
            '"inventory"',
            '"reviewer_notes"',
            '"positive_plan_mappings"',
            '"structured_probes"',
            '"transition_input"',
            "st.session_state[_key] = st.session_state.selected_conversation",
        ):
            assert excluded not in serialized


@pytest.mark.parametrize(
    "identifier",
    [
        "controlled-v8-full",
        "controlled-v8-key-evidence-removed",
        "controlled-v8-unknown-version-mixed",
        "controlled-v8-version-correction",
        "controlled-v8-same-version-synthetic-conflict",
        "controlled-v8-refinement-stale-source",
    ],
)
def test_actual_registered_case_message_and_each_current_round_are_bound(identifier):
    item = condition(identifier)
    for bundle in item.bundles:
        actual = inputs.grounded_request(item, item.case, item.user_message, bundle)
        if identifier == "controlled-v8-refinement-stale-source" and bundle.retrieval_round == 2:
            assert "lacks the key-identity release-mechanism excerpt" in actual.gaps[-2].description
            assert actual.gaps[-1].description == "Full-app root cause remains unresolved"
            assert all(gap.question is None for gap in actual.gaps if gap.kind == "source")
            expected_gaps = actual.gaps
        else:
            expected_gaps = item.gaps
        expected = make_grounded_request(
            item.case,
            item.user_message,
            bundle,
            gaps=expected_gaps,
            conflict_groups=item.conflict_groups,
        )
        assert actual == expected
        assert actual.case == item.case and actual.user_message == item.user_message
        assert actual.evidence == bundle
        assert [gap for gap in actual.gaps if gap.kind == "user"] == [
            gap for gap in item.gaps if gap.kind == "user"
        ]


def test_first_round_does_not_receive_later_round_warnings_or_earlier_positive_plans():
    item = condition("controlled-v8-refinement-stale-source")
    first = inputs.grounded_request(item, item.case, item.user_message, item.bundles[0])
    second = inputs.grounded_request(item, item.case, item.user_message, item.bundles[1])
    assert first.evidence.warnings == ()
    assert second.evidence.warnings == ("The release-note hit was removed from this latest bundle",)
    assert second.evidence.retrieval_round == 2
    first_ids = {hit.chunk_id for hit in first.evidence.hits}
    second_ids = {hit.chunk_id for hit in second.evidence.hits}
    assert first_ids - second_ids == {"release-150-multiselect-key-identity-v8"}
    assert "source_chunk_ids" not in encoded(first.model_dump(mode="json"))


def test_full_and_stale_first_requests_match_except_the_opaque_case_alias():
    full, stale = condition(), condition("controlled-v8-refinement-stale-source")
    full_request = inputs.grounded_request(full, full.case, full.user_message, full.bundles[0])
    stale_request = inputs.grounded_request(stale, stale.case, stale.user_message, stale.bundles[0])
    full_data = full_request.model_dump(mode="json")
    stale_data = stale_request.model_dump(mode="json")
    full_data.pop("context_sha256")
    stale_data.pop("context_sha256")
    assert full_data["case"].pop("case_id") == "c4-condition-01"
    assert stale_data["case"].pop("case_id") == "c4-condition-06"
    assert full_data == stale_data
    for item, actual in ((full, full_request), (stale, stale_request)):
        context = ReasoningContext(
            run_id="opaque-run",
            case_id=item.case.case_id,
            case_revision=item.case.case_revision,
            attempt_index=1,
        )
        prompt = encoded(build_grounded_messages(actual, context))
        for forbidden in (
            item.condition_id,
            "case-controlled-v8",
            "deliberately",
            "latest bundle",
            "stale",
            "future",
        ):
            assert forbidden not in prompt


def test_second_round_missing_source_is_a_current_gap_without_removal_or_future_label():
    item = condition("controlled-v8-refinement-stale-source")
    first = inputs.grounded_request(item, item.case, item.user_message, item.bundles[0])
    second = inputs.grounded_request(item, item.case, item.user_message, item.bundles[1])
    source_first = [gap.description for gap in first.gaps if gap.kind == "source"]
    source_second = [gap.description for gap in second.gaps if gap.kind == "source"]
    assert not any("lacks" in text for text in source_first)
    assert any("currently supplied evidence lacks" in text for text in source_second)
    assert all(
        "deliberately" not in text and "latest bundle" not in text and "future" not in text
        for text in source_second
    )


@pytest.mark.parametrize(
    "change",
    [
        "case",
        "message",
        "source_text",
        "source_scope",
        "same_id_hash",
        "round",
        "snapshot",
        "warning",
        "nested_extra",
    ],
)
def test_mutated_actual_runtime_input_cannot_enter_a_registered_request(change):
    item = condition()
    case, message, bundle = item.case, item.user_message, item.bundles[0]
    if change == "case":
        case = case.model_copy(update={"case_revision": case.case_revision + 1})
    elif change == "message":
        message += " PRIVATE_GOLD_OR_FUTURE_INPUT"
    elif change in {"source_text", "source_scope", "same_id_hash"}:
        old = bundle.hits[0]
        delta = (
            {"applicable_versions": ("9.99.0",)}
            if change == "source_scope"
            else {"excerpt": "PRIVATE_MUTATED_SOURCE"}
        )
        replacement = old.model_copy(update=delta)
        if change == "same_id_hash":
            assert source_content_sha256(replacement) != source_content_sha256(old)
        bundle = bundle.model_copy(update={"hits": (replacement, *bundle.hits[1:])})
    elif change == "round":
        bundle = bundle.model_copy(update={"retrieval_round": 3})
    elif change == "snapshot":
        bundle = bundle.model_copy(update={"snapshot_id": "private-other-snapshot"})
    elif change == "warning":
        bundle = bundle.model_copy(update={"warnings": ("PRIVATE_NEW_WARNING",)})
    else:
        bundle = bundle.model_copy(update={"PRIVATE_EXTRA": "PRIVATE_SOURCE"})
    with pytest.raises(inputs.ControlledInputsRejected) as error:
        inputs.grounded_request(item, case, message, bundle)
    assert str(error.value) == "ControlledDecisionInputsRejected"


@pytest.mark.parametrize(
    "change", ["id", "case", "message", "bundles", "gaps", "conflicts", "list"]
)
def test_condition_material_itself_cannot_be_replaced_even_with_valid_new_contracts(change):
    item = condition()
    if change == "id":
        changed = replace(item, condition_id="private-unregistered-case")
    elif change == "case":
        changed = replace(item, case=item.case.model_copy(update={"case_revision": 99}))
    elif change == "message":
        changed = replace(item, user_message="PRIVATE_NEW_MESSAGE")
    elif change == "bundles":
        changed = replace(item, bundles=tuple(reversed(item.bundles)))
    elif change == "gaps":
        changed = replace(
            item,
            gaps=item.gaps
            + (
                GroundedGap(
                    name="private-gap",
                    kind="user",
                    description="Private extra gap",
                    necessity="Not a registered condition",
                    question="PRIVATE_NEW_QUESTION?",
                ),
            ),
        )
    elif change == "conflicts":
        changed = replace(
            item,
            conflict_groups=((item.bundles[0].hits[0].chunk_id, item.bundles[0].hits[1].chunk_id),),
        )
    else:
        changed = replace(item, bundles=list(item.bundles))
    with pytest.raises(inputs.ControlledInputsRejected) as error:
        inputs.grounded_request(changed, changed.case, changed.user_message, item.bundles[0])
    assert str(error.value) == "ControlledDecisionInputsRejected"


def test_latest_round_cannot_relabel_or_restore_an_old_bundle_with_removed_source():
    item = condition("controlled-v8-refinement-stale-source")
    stale = item.bundles[0].model_copy(update={"retrieval_round": 2})
    with pytest.raises(inputs.ControlledInputsRejected):
        inputs.grounded_request(item, item.case, item.user_message, stale)
    current = inputs.grounded_request(item, item.case, item.user_message, item.bundles[1])
    assert "release-150-multiselect-key-identity-v8" not in {
        hit.chunk_id for hit in current.evidence.hits
    }


def test_fixed_retriever_records_queries_returns_fresh_rounds_and_never_repeats_on_exhaustion():
    item = condition("controlled-v8-refinement-stale-source")
    retriever = inputs.FixedRetriever(item.bundles)
    first_request = request(item)
    first = retriever.search(first_request)
    assert first == item.bundles[0] and first is not item.bundles[0]
    object.__setattr__(first.hits[0], "excerpt", "PRIVATE_CALLER_MUTATION")
    assert retriever.returned[0] == item.bundles[0]
    second_request = request(item, "A genuinely distinct follow-up query.")
    second = retriever.search(second_request)
    assert second == item.bundles[1] and second.retrieval_round == 2
    assert retriever.requests == [first_request, second_request]
    object.__setattr__(first_request, "queries", ("private-request-mutation",))
    assert retriever.requests[0].queries != first_request.queries
    with pytest.raises(inputs.FixedEvidenceUnavailable, match="^FixedEvidenceUnavailable$"):
        retriever.search(request(item, "No third bundle registered."))
    assert len(retriever.returned) == 2 and len(retriever.requests) == 3
    assert retriever.returned[-1] == item.bundles[1]


@pytest.mark.parametrize("change", ["snapshot", "top_k", "invalid"])
def test_invalid_retrieval_does_not_consume_or_restore_a_registered_round(change):
    item = condition()
    retriever = inputs.FixedRetriever(item.bundles)
    invalid = (
        request(item, snapshot_id="wrong-snapshot")
        if change == "snapshot"
        else request(item, top_k=1)
    )
    if change == "invalid":
        invalid = request(item).model_copy(update={"PRIVATE_EXTRA": "PRIVATE_REQUEST"})
    with pytest.raises(inputs.FixedEvidenceUnavailable) as error:
        retriever.search(invalid)
    assert "PRIVATE" not in str(error.value) and retriever.returned == []
    assert retriever.search(request(item)).retrieval_round == 1


def test_registration_pins_and_disclosures_are_separate_from_labels_and_paid_authorization(pack):
    result = inputs.registration_inputs()
    assert result == inputs.registration_inputs()
    assert (
        result["suite_sha256"]
        == hashlib.sha256((inputs.ROOT / inputs.SUITE_PATH).read_bytes()).hexdigest()
    )
    assert (
        result["protocol_sha256"]
        == hashlib.sha256((inputs.ROOT / inputs.PROTOCOL_PATH).read_bytes()).hexdigest()
    )
    assert set(result["material_sha256_by_condition"]) == {
        case["id"] for case in pack.suite["cases"]
    }
    assert len(set(result["material_sha256_by_condition"].values())) == 6
    assert len(result["runtime_case_aliases"]) == 6
    assert list(result["runtime_case_aliases"].values()) == [
        f"c4-condition-{index:02d}" for index in range(1, 7)
    ]
    round_hashes = result["current_catalog_sha256_by_condition"]
    assert (
        round_hashes["controlled-v8-full"]["1"]
        == round_hashes["controlled-v8-refinement-stale-source"]["1"]
    )
    assert (
        round_hashes["controlled-v8-refinement-stale-source"]["1"]
        != round_hashes["controlled-v8-refinement-stale-source"]["2"]
    )
    assert result["source_files"] == pack.suite["provenance"]["source_files"]
    assert len(result["source_files"]) == 3
    assert result["docs_commit"] == "695e6ce2fb1b23afc6df66b40420ab0013ad72fd"
    assert result["reserved_issue_ids"] == [8061, 8901, 12629, 12782, 16914]
    disclosure = result["disclosures"]
    assert disclosure["answer_informed_development_selection"]
    assert disclosure["manually_curated_gaps_and_conflicts"]
    assert disclosure["opaque_runtime_case_ids"]
    assert disclosure["source_catalog_normalized_per_current_round"]
    assert not disclosure["original_catalog_retained_exactly"]
    assert disclosure["normalization_is_prepaid_baseline_amendment"]
    refs = result["retained_label_bearing_fact_attributions"]
    assert len(refs) == 2
    assert {record["condition_id"] for record in refs} == {"controlled-v8-version-correction"}
    assert disclosure["independent_issue_families"] == 1
    assert disclosure["final_evaluation_case_count"] == 0
    assert not disclosure["original_protocol_authorizes_paid_work"]
    assert not disclosure["quarantine_applied_to_real_RAG_claim"]
    assert not disclosure["quality_claim"]
    serialized = json.dumps(result)
    for excluded in (
        "authored_replays",
        "expectations",
        "positive_plan_mappings",
        "targeted_answerable_questions",
        "st.session_state[_key]",
    ):
        assert excluded not in serialized


def test_mutating_a_new_load_does_not_poison_later_material_or_hashes():
    before = inputs.registration_inputs()
    loaded = inputs.load_conditions()
    object.__setattr__(loaded[0].bundles[0].hits[0], "excerpt", "PRIVATE_CHANGED_COPY")
    object.__setattr__(loaded[0].case, "case_revision", 999)
    assert inputs.registration_inputs() == before
    assert inputs.load_conditions()[0].case.case_revision != 999


@pytest.mark.parametrize("mutated", ["suite", "protocol"])
def test_frozen_byte_mutation_is_rejected_without_modifying_originals(
    tmp_path, monkeypatch, mutated
):
    path = tmp_path / "mutated.json"
    original = inputs.ROOT / (inputs.SUITE_PATH if mutated == "suite" else inputs.PROTOCOL_PATH)
    raw = original.read_bytes()
    path.write_bytes(raw + b"\n")
    real_load = grounding_experiments.load_grounding_pack
    monkeypatch.setattr(
        inputs, "load_grounding_pack", lambda: real_load(**{f"{mutated}_path": path})
    )
    with pytest.raises(inputs.ControlledInputsRejected):
        inputs.load_conditions()
    with pytest.raises(inputs.ControlledInputsRejected):
        inputs.registration_inputs()
    assert original.read_bytes() == raw
