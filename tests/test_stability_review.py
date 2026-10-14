"""Receipt observations retain failure denominators and every output surface."""

from copy import deepcopy

import pytest

from agent_app.contracts import (
    CaseState,
    EvidenceBundle,
    EvidenceHit,
    Fact,
    GroundedGap,
    GroundedPlan,
    GroundedSourceRef,
    ReasoningContext,
)
from agent_app.reasoning.grounding import (
    make_grounded_request,
    render_grounded_plan,
    source_content_sha256,
)
from agent_app.testing.plan_observation import observe_plan_output
from agent_app.testing.stability_review import StabilityReviewRejected, summarize_receipt


def recorded_job(arm, *, request=None, decision="answer"):
    if request is None:
        case = CaseState(
            case_id="review-case",
            case_revision=1,
            facts=(
                Fact(
                    name="streamlit_version",
                    value="1.39.0",
                    source_ref="user:initial",
                    turn_id="initial",
                ),
            ),
        )
        bundle = EvidenceBundle(
            snapshot_id="registered-fixture",
            hits=(
                EvidenceHit(
                    chunk_id="button-139",
                    source_id="reviewed-button-record",
                    excerpt="icon accepts a single character emoji; مثال فارسی",
                    source_url="https://docs.streamlit.io/develop/api-reference/widgets/st.button",
                    source_type="doc",
                    applicable_versions=("1.39.0",),
                ),
            ),
        )
        request = make_grounded_request(
            case,
            "What does the button support?",
            bundle,
            gaps=(
                GroundedGap(
                    name="warning_support",
                    kind="source",
                    description="Warning is not documented in the supplied button record.",
                    necessity="Retrieve a warning reference or ask a maintainer to investigate.",
                ),
            ),
        )
    context = ReasoningContext(
        run_id=f"registered-{arm}", case_id="review-case", case_revision=1, attempt_index=1
    )
    refs = tuple(
        GroundedSourceRef(chunk_id=hit.chunk_id, content_sha256=source_content_sha256(hit))
        for hit in request.evidence.hits
    )
    plan = GroundedPlan(
        context_sha256=request.context_sha256,
        decision=decision,
        sources=refs,
        question_name=next((gap.name for gap in request.gaps if gap.kind == "user"), None)
        if decision == "ask"
        else None,
    )
    analysis = render_grounded_plan(request, plan, source_gap_handoff=True).model_dump(mode="json")
    proposal = {
        **{name: value for name, value in analysis.items() if name != "evidence_links"},
        "proposal_id": context.run_id,
        "case_id": "review-case",
        "case_revision": 1,
        "analysis": deepcopy(analysis),
        "review_handoff": {
            "reasoning_context": context.model_dump(mode="json"),
            "grounded_request": request.model_dump(mode="json"),
            "analysis": deepcopy(analysis),
        },
    }
    job = {
        "job_id": f"round1-{arm}",
        "arm": arm,
        "round": 1,
        "case_id": "review-case",
        "fixture_id": "fixed-input",
        "fixture_sha256": "a" * 64,
        "coverage_complete": True,
        "selected_turns": ["initial"],
        "checks": [{"check": "recorded check", "passed": True}],
        "run_ids": [context.run_id],
        "steps": [
            {
                "turn": "initial",
                "proposal": proposal,
                "edited_proposal": None,
                "released_outputs": [{"role": "assistant", "text": analysis["user_draft"]}],
                "usage": {"model_attempts": 1},
            },
        ],
    }
    attempt = {
        "context": context.model_dump(mode="json"),
        "request": request.model_dump(mode="json"),
        "plan": plan.model_dump(mode="json"),
        "schema_observation": observe_plan_output(plan.model_dump_json()),
        "error_code": None,
    }
    return job, attempt, request


def receipt_pair():
    left, left_attempt, request = recorded_job("B")
    right, right_attempt, _ = recorded_job("C", request=request)
    return {
        "batches": [
            {
                "batch_id": "round1",
                "kind": "stability",
                "jobs": [left, right],
                "attempts": [left_attempt, right_attempt],
                "provider_sends": [],
            }
        ],
    }


def test_same_initial_request_pair_and_full_renderer_are_observations_not_quality():
    receipt = receipt_pair()
    before = deepcopy(receipt)
    review = summarize_receipt(receipt, strata={"review-case": "answerable"})
    assert receipt == before
    assert review["common_initial_state_comparisons"][0]["current_initial_request_equal"] is True
    for job in review["jobs"]:
        result = job["proposal_reviews"][0]
        verification = result["render_verification"]
        assert verification["matching_recorded_attempt"] is True
        assert verification["enriched_request_matches_handoff"] is True
        assert verification["proposal_analysis_matches"] is True
        assert verification["handoff_analysis_matches"] is True
        assert verification["top_level_analysis_surfaces_match"] is True
        assert verification["recorded_released_outputs_match_unedited_draft"] is True
        assert result["all_current_sources"][0]["excerpt"].endswith("مثال فارسی")
        assert result["all_current_sources"][0]["version_scope"] == "exact_metadata_match"
        assert (
            result["qualification_observations"]["source_gap_handoff_changes_renderer_output"]
            is True
        )
        assert result["qualification_observations"]["material_claim_entailment_review"] is None
        assert result["semantic_admissibility"] is None
    assert review["quality_claim"] is False
    assert review["human_usefulness"] is None and review["human_reviewed"] is False
    assert review["arm_totals"]["B"]["by_stratum"]["answerable"]["case_arm_jobs"] == 1


@pytest.mark.parametrize(
    "surface", ["user_draft", "maintainer_summary", "rationale", "facts_delta", "evidence_links"]
)
def test_all_analysis_surfaces_detect_recorded_drift(surface):
    receipt = receipt_pair()
    proposal = receipt["batches"][0]["jobs"][0]["steps"][0]["proposal"]
    proposal["analysis"][surface] = "unrecorded mutation"
    result = summarize_receipt(receipt)["jobs"][0]["proposal_reviews"][0]
    assert result["render_verification"]["proposal_analysis_matches"] is False
    assert result["render_verification"]["handoff_analysis_matches"] is True


def test_released_or_top_level_drift_cannot_hide_behind_intact_handoff():
    receipt = receipt_pair()
    step = receipt["batches"][0]["jobs"][0]["steps"][0]
    step["proposal"]["rationale"] += " This issue is fixed."
    step["released_outputs"][0]["text"] = "Different released text"
    verification = summarize_receipt(receipt)["jobs"][0]["proposal_reviews"][0][
        "render_verification"
    ]
    assert verification["proposal_analysis_matches"] is True
    assert verification["top_level_analysis_surfaces_match"] is False
    assert verification["recorded_released_outputs_match_unedited_draft"] is False


def test_recorded_renderer_without_source_gap_handoff_is_preserved_as_mismatch():
    receipt = receipt_pair()
    batch = receipt["batches"][0]
    attempt = batch["attempts"][0]
    old = render_grounded_plan(
        make_grounded_request(
            CaseState.model_validate(attempt["request"]["case"]),
            attempt["request"]["user_message"],
            EvidenceBundle.model_validate(attempt["request"]["evidence"]),
            gaps=tuple(GroundedGap.model_validate(gap) for gap in attempt["request"]["gaps"]),
        ),
        GroundedPlan.model_validate(attempt["plan"]),
    ).model_dump(mode="json")
    batch["jobs"][0]["steps"][0]["proposal"]["analysis"] = old
    verification = summarize_receipt(receipt)["jobs"][0]["proposal_reviews"][0][
        "render_verification"
    ]
    assert verification["proposal_analysis_matches"] is False


def test_repairs_invalid_first_attempt_and_unobserved_provider_errors_have_separate_denominators():
    receipt = receipt_pair()
    batch = receipt["batches"][0]
    valid = batch["attempts"][0]
    invalid = deepcopy(valid)
    invalid["plan"] = None
    invalid["schema_observation"] = observe_plan_output("{")
    valid["context"]["attempt_index"] = 2
    batch["jobs"][0]["steps"][0]["proposal"]["review_handoff"]["reasoning_context"] = deepcopy(
        valid["context"]
    )
    batch["attempts"].insert(0, invalid)
    no_response = batch["attempts"][2]
    no_response.pop("schema_observation")
    no_response["plan"] = None
    no_response["error_code"] = "ProviderRequestFailed"
    batch["jobs"][1]["coverage_complete"] = False
    batch["jobs"][1]["steps"][0]["proposal"] = {}
    review = summarize_receipt(receipt)
    assert review["arm_totals"]["B"]["first_attempts"]["schema_invalid"] == 1
    assert review["arm_totals"]["B"]["first_attempts"]["schema_valid"] == 0
    assert review["arm_totals"]["B"]["all_attempts"]["schema_valid"] == 1
    assert review["arm_totals"]["C"]["all_attempts"]["schema_unobserved"] == 1
    assert review["arm_totals"]["C"]["all_attempts"]["errors"] == {"ProviderRequestFailed": 1}
    assert review["arm_totals"]["C"]["conditional_routes_completed"] == 0


def test_changed_current_evidence_is_not_claimed_as_a_matched_pair():
    receipt = receipt_pair()
    receipt["batches"][0]["attempts"][1]["request"]["evidence"]["hits"][0]["excerpt"] = (
        "changed source"
    )
    result = summarize_receipt(receipt)
    assert result["common_initial_state_comparisons"][0]["current_initial_request_equal"] is False
    assert (
        result["jobs"][1]["proposal_reviews"][0]["render_verification"][
            "enriched_request_matches_handoff"
        ]
        is False
    )


def test_source_binding_failure_is_recorded_without_raw_validation_diagnostic():
    receipt = receipt_pair()
    receipt["batches"][0]["attempts"][0]["plan"]["sources"][0]["content_sha256"] = "b" * 64
    verification = summarize_receipt(receipt)["jobs"][0]["proposal_reviews"][0][
        "render_verification"
    ]
    assert verification["render_rejected"] is True
    assert verification["proposal_analysis_matches"] is False


def test_unknown_or_duplicate_run_identity_is_rejected_with_fixed_diagnostic():
    receipt = receipt_pair()
    receipt["batches"][0]["attempts"][0]["context"]["run_id"] = "unregistered-private-value"
    with pytest.raises(StabilityReviewRejected, match="^StabilityReviewRejected$"):
        summarize_receipt(receipt)
    receipt = receipt_pair()
    receipt["batches"][0]["jobs"][1]["run_ids"] = receipt["batches"][0]["jobs"][0]["run_ids"]
    with pytest.raises(StabilityReviewRejected, match="^StabilityReviewRejected$"):
        summarize_receipt(receipt)


def test_edits_and_unreleased_proposals_remain_distinct_review_surfaces():
    receipt = receipt_pair()
    step = receipt["batches"][0]["jobs"][0]["steps"][0]
    step["edited_proposal"] = {"user_draft": "Human edit"}
    step["released_outputs"][0]["text"] = "Human edit"
    right = receipt["batches"][0]["jobs"][1]["steps"][0]
    right["released_outputs"] = []
    result = summarize_receipt(receipt)
    left_review = result["jobs"][0]["proposal_reviews"][0]
    assert left_review["edited_proposal"]["user_draft"] == "Human edit"
    assert (
        left_review["render_verification"]["recorded_released_outputs_match_unedited_draft"] is None
    )
    assert (
        result["jobs"][1]["proposal_reviews"][0]["render_verification"][
            "recorded_released_outputs_match_unedited_draft"
        ]
        is None
    )


def test_duplicate_attempt_or_job_cannot_inflate_results():
    receipt = receipt_pair()
    batch = receipt["batches"][0]
    batch["attempts"].append(deepcopy(batch["attempts"][0]))
    with pytest.raises(StabilityReviewRejected, match="^StabilityReviewRejected$"):
        summarize_receipt(receipt)
    receipt = receipt_pair()
    receipt["batches"][0]["jobs"][1]["job_id"] = receipt["batches"][0]["jobs"][0]["job_id"]
    with pytest.raises(StabilityReviewRejected, match="^StabilityReviewRejected$"):
        summarize_receipt(receipt)


def test_stop_diagnostics_do_not_export_unknown_provider_strings():
    receipt = receipt_pair()
    receipt["batches"][0]["attempts"][0]["error_code"] = "private-provider-error-value"
    review = summarize_receipt(receipt)
    assert review["arm_totals"]["B"]["all_attempts"]["errors"] == {"UnclassifiedStop": 1}
    assert "private-provider-error-value" not in repr(review)


def test_registered_question_observation_does_not_automatically_grade_necessity():
    request = make_grounded_request(
        CaseState(case_id="review-case", case_revision=1, unknowns=("streamlit_version",)),
        "My widget behaves differently; I have not supplied my version.",
        EvidenceBundle(snapshot_id="no-sources", hits=()),
        gaps=(
            GroundedGap(
                name="streamlit_version",
                kind="user",
                description="Installed version is not supplied.",
                necessity="The user can report the installed version for applicability.",
                question="Which Streamlit version is installed?",
            ),
        ),
    )
    job, attempt, _ = recorded_job("C", request=request, decision="ask")
    review = summarize_receipt(
        {
            "batches": [
                {
                    "batch_id": "question-round",
                    "kind": "stability",
                    "jobs": [job],
                    "attempts": [attempt],
                }
            ]
        }
    )
    question = review["jobs"][0]["proposal_reviews"][0]["question_observations"]
    assert question["selected_gap_is_user_kind"] is True
    assert question["selected_gap_repeats_active_user_fact"] is False
    assert question["question_matches_registered_canonical_text"] is True
    assert question["necessity_review"] is None
    assert question["user_answerability_review"] is None
