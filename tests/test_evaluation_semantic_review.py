"""Synthetic annotation mechanics; no source truth or human review is inferred."""

import json

import pytest

from agent_app.contracts import (
    AnalysisResult,
    CaseState,
    EvidenceBundle,
    EvidenceHit,
    Fact,
    ReasoningContext,
    ReviewClaimBinding,
    ReviewOutputSpan,
    ReviewSourceQuote,
    RunResult,
)
from agent_app.evaluation.semantic_review import (
    QuestionJudgment,
    ReviewScope,
    SemanticReview,
    SemanticReviewRejected,
    aggregate_reviews,
    score_review,
)
from agent_app.orchestration.handoff import ReasoningFrame, build_handoff, edit_handoff
from agent_app.reasoning.review import _surface_texts, review_user_fact_sha256


def make_handoff(
    *,
    case_id="case-one",
    revision=2,
    proposal_id="proposal-one",
    case=None,
    evidence=None,
    analysis=None,
    message="Synthetic widget report.",
):
    case = case or CaseState(
        case_id=case_id,
        case_revision=revision,
        facts=(
            Fact(
                name="streamlit_version",
                value="1.49.0",
                source_ref="user:corrected",
                turn_id="corrected",
            ),
            Fact(
                name="streamlit_version",
                value="1.50.0",
                source_ref="user:old",
                turn_id="old",
                status="superseded",
            ),
            Fact(
                name="inferred_fact",
                value="An unverified inference",
                source_ref="source:doc",
                turn_id="inference",
                provenance_kind="evidence",
            ),
        ),
    )
    evidence = evidence or EvidenceBundle(
        snapshot_id="synthetic-snapshot",
        hits=(
            EvidenceHit(
                chunk_id="doc-current",
                source_id="source:doc",
                excerpt="Synthetic fixture: A widget retains its default.",
                source_url="https://example.org/synthetic-review",
                source_type="doc",
                applicable_versions=("1.49.0",),
            ),
        ),
    )
    analysis = analysis or AnalysisResult(
        decision="answer",
        user_draft="A widget retains its default.",
        maintainer_summary="User reports Streamlit 1.49.0.",
        rationale="The full application's cause is unknown.",
    )
    context = ReasoningContext(
        run_id=proposal_id, case_id=case.case_id, case_revision=case.case_revision, attempt_index=1
    )
    result = RunResult(
        run_id=proposal_id,
        case_id=case.case_id,
        case_revision=case.case_revision,
        status="awaiting_approval",
        analysis=analysis,
        model_attempts=1,
        retrieval_rounds=1,
    )
    return build_handoff(result, ReasoningFrame(case, message, evidence, context))


def scope(**changes):
    return ReviewScope(
        **(
            {
                "run_id": "evaluation-one",
                "config_id": "config-one",
                "config_sha256": "1" * 64,
                "rubric_id": "rubric-one",
                "rubric_sha256": "2" * 64,
                "stratum": "answerable",
                "stratum_registration_sha256": "3" * 64,
                "stratum_registered_before_run": True,
            }
            | changes
        )
    )


def output(handoff, surface="user_draft", selected=None):
    text = _surface_texts(handoff.analysis)[surface]
    selected = text if selected is None else selected
    start = text.index(selected)
    return ReviewOutputSpan(
        surface_id=surface, start=start, end=start + len(selected), text=selected
    )


def source_binding(handoff, *, judgment="supported", surface="user_draft"):
    quote = handoff.evidence.hits[0].excerpt
    return ReviewClaimBinding(
        output=output(handoff, surface),
        judgment=judgment,
        applicability="current",
        source_quote=ReviewSourceQuote(
            chunk_id="doc-current", start=0, end=len(quote), quote=quote
        ),
    )


def fact_binding(handoff, *, fact=None, judgment="supported"):
    return ReviewClaimBinding(
        output=output(handoff, "maintainer_summary", "1.49.0"),
        judgment=judgment,
        applicability="current",
        user_fact_sha256=review_user_fact_sha256(fact or handoff.case.facts[0]),
    )


def question(*, applies=False, necessary="yes", answerable="yes", not_repeating_known="yes"):
    values = dict(
        necessary=necessary, answerable=answerable, not_repeating_known=not_repeating_known
    )
    if not applies:
        values = dict.fromkeys(values, "not_applicable")
    return QuestionJudgment(applies=applies, reason="Synthetic caller judgment.", **values)


def review(handoff, **changes):
    bindings = (
        changes.pop("claim_bindings")
        if "claim_bindings" in changes
        else (source_binding(handoff), fact_binding(handoff))
    )
    payload = {
        "review_id": "review-one",
        "scope": scope(),
        "handoff_sha256": handoff.handoff_sha256,
        "reviewer_id": "declared-reviewer",
        "reviewer_kind": "human",
        "response_origin": "model",
        "declared_material_claim_count": len(bindings),
        "claim_inventory_complete": True,
        "reviewed_surfaces": tuple(_surface_texts(handoff.analysis)),
        "claim_bindings": bindings,
        "decision_judgment": "acceptable",
        "decision_reason": "Synthetic caller judgment.",
        "question": question(),
        "usefulness_score": 2,
        "usefulness_reason": "Synthetic usefulness judgment.",
    }
    return SemanticReview(**(payload | changes))


def score(handoff=None, **changes):
    handoff = handoff or make_handoff()
    record = review(handoff, **changes)
    return score_review(handoff, record, scope=record.scope)


def rejects(code, function, *args, **kwargs):
    with pytest.raises(SemanticReviewRejected) as caught:
        function(*args, **kwargs)
    assert caught.value.code == str(caught.value) == code


def test_complete_exact_annotations_record_positive_gate_without_quality_or_authority():
    handoff = make_handoff()
    before = handoff.model_dump_json()
    result = score(handoff)
    assert result.support_gate == 1 and result.support_status == "pass"
    assert result.claims.model_dump() == {
        "total": 2,
        "reviewed": 2,
        "supported": 2,
        "unsupported": 0,
        "insufficient": 0,
        "unreviewed": 0,
        "review_coverage": 1.0,
        "supported_fraction": 1.0,
    }
    assert result.question_gate is None and result.question_status == "not_applicable"
    assert result.quality_claim is False and result.authorizes_action is False
    assert handoff.model_dump_json() == before
    exported = result.model_dump_json()
    for private in [
        "Synthetic fixture:",
        "A widget retains",
        "User reports",
        "Synthetic caller judgment",
        "declared-reviewer",
    ]:
        assert private not in exported


def test_json_sidecar_is_supported_without_exposing_validation_details():
    handoff = make_handoff()
    record = review(handoff)
    parsed = json.loads(record.model_dump_json())
    assert score_review(handoff, parsed, scope=record.scope) == score_review(
        handoff, record, scope=record.scope
    )


@pytest.mark.parametrize(
    "field",
    [
        "run_id",
        "config_id",
        "config_sha256",
        "rubric_id",
        "rubric_sha256",
        "stratum",
        "stratum_registration_sha256",
    ],
)
def test_review_cannot_change_the_callers_registered_identity(field):
    handoff = make_handoff()
    changes = {field: "0" * 64 if "sha256" in field else "different"}
    if field == "stratum":
        changes[field] = "ambiguous"
    record = review(handoff, scope=scope(**changes))
    rejects("ReviewScopeMismatch", score_review, handoff, record, scope=scope())


def test_posthoc_stratum_is_not_eligible():
    handoff = make_handoff()
    record = review(handoff, scope=scope(stratum_registered_before_run=False))
    rejects("UnregisteredStratum", score_review, handoff, record, scope=record.scope)


def test_stale_handoff_hash_is_rejected():
    handoff = make_handoff()
    record = review(handoff, handoff_sha256="0" * 64)
    rejects("ReviewHandoffMismatch", score_review, handoff, record, scope=record.scope)


def test_changed_handoff_content_cannot_keep_old_hash():
    handoff = make_handoff()
    record = review(handoff)
    changed = handoff.model_copy(update={"user_message": "SECRET-RAW-INPUT"})
    rejects("InvalidSemanticReviewInput", score_review, changed, record, scope=record.scope)


@pytest.mark.parametrize(
    "mutation", ["wrong_text", "wrong_offset", "unknown_surface", "not_reviewed"]
)
def test_output_span_must_bind_an_actually_reviewed_surface(mutation):
    handoff = make_handoff()
    binding = source_binding(handoff)
    changes = {}
    if mutation == "wrong_text":
        binding = binding.model_copy(
            update={
                "output": binding.output.model_copy(update={"text": "X" * len(binding.output.text)})
            }
        )
    elif mutation == "wrong_offset":
        binding = binding.model_copy(
            update={
                "output": binding.output.model_copy(
                    update={"start": 1, "end": binding.output.end + 1}
                )
            }
        )
    elif mutation == "unknown_surface":
        binding = binding.model_copy(
            update={"output": binding.output.model_copy(update={"surface_id": "not-real"})}
        )
    else:
        changes["reviewed_surfaces"] = tuple(
            name for name in _surface_texts(handoff.analysis) if name != "user_draft"
        )
    record = review(handoff, claim_bindings=(binding,), **changes)
    rejects(
        "OutputSpanMismatch"
        if mutation in {"wrong_text", "wrong_offset"}
        else "UnknownReviewSurface",
        score_review,
        handoff,
        record,
        scope=record.scope,
    )


@pytest.mark.parametrize("mutation", ["text", "offset", "unknown_chunk"])
def test_source_quote_must_match_final_supplied_evidence(mutation):
    handoff = make_handoff()
    binding = source_binding(handoff)
    quote = binding.source_quote
    update = (
        {"quote": "X" * len(quote.quote)}
        if mutation == "text"
        else {"start": 1, "end": quote.end + 1}
    )
    if mutation == "unknown_chunk":
        update = {"chunk_id": "retired-source"}
    binding = binding.model_copy(update={"source_quote": quote.model_copy(update=update)})
    record = review(handoff, claim_bindings=(binding,))
    rejects(
        "UnknownReviewSource" if mutation == "unknown_chunk" else "SourceQuoteMismatch",
        score_review,
        handoff,
        record,
        scope=record.scope,
    )


@pytest.mark.parametrize("index", [1, 2])
def test_supported_fact_must_be_active_and_user_attributed(index):
    handoff = make_handoff()
    record = review(
        handoff, claim_bindings=(fact_binding(handoff, fact=handoff.case.facts[index]),)
    )
    rejects("InactiveUserFactReference", score_review, handoff, record, scope=record.scope)


@pytest.mark.parametrize("identical", [True, False])
def test_overlapping_or_duplicate_claim_spans_cannot_inflate_coverage(identical):
    handoff = make_handoff()
    first = source_binding(handoff)
    duplicate = (
        first
        if identical
        else first.model_copy(update={"output": output(handoff, selected="widget retains")})
    )
    record = review(handoff, claim_bindings=(first, duplicate))
    rejects("OverlappingClaimBindings", score_review, handoff, record, scope=record.scope)


def test_different_nonoverlapping_occurrences_in_same_surface_can_be_reviewed():
    handoff = make_handoff()
    first = source_binding(handoff).model_copy(
        update={"output": output(handoff, selected="A widget")}
    )
    second = source_binding(handoff).model_copy(
        update={"output": output(handoff, selected="its default.")}
    )
    assert score(handoff, claim_bindings=(first, second)).claims.reviewed == 2


def test_one_unsupported_claim_sets_zero_even_when_rest_of_review_incomplete():
    handoff = make_handoff()
    unsupported = ReviewClaimBinding(
        output=output(handoff, "maintainer_summary", "1.49.0"),
        judgment="unsupported",
        applicability="unknown",
    )
    result = score(
        handoff,
        claim_bindings=(source_binding(handoff), unsupported),
        declared_material_claim_count=3,
        claim_inventory_complete=False,
    )
    assert result.support_gate == 0 and result.support_status == "fail"
    assert result.claims.unsupported == result.claims.unreviewed == 1
    assert result.claims.review_coverage == 2 / 3
    assert result.claims.supported_fraction == 1 / 3


@pytest.mark.parametrize("incomplete", ["inventory", "surface", "annotations", "insufficient"])
def test_incomplete_or_insufficient_review_is_unassessed_not_pass(incomplete):
    handoff = make_handoff()
    changes = {"claim_inventory_complete": False}
    if incomplete == "surface":
        changes = {
            "reviewed_surfaces": tuple(
                name for name in _surface_texts(handoff.analysis) if name != "rationale"
            )
        }
    elif incomplete == "annotations":
        changes = {"declared_material_claim_count": 3}
    elif incomplete == "insufficient":
        changes = {"claim_bindings": (source_binding(handoff, judgment="insufficient"),)}
    result = score(handoff, **changes)
    assert result.support_gate is None and result.support_status == "unassessed"


def test_complete_zero_claim_inventory_is_na_not_success():
    result = score(claim_bindings=(), declared_material_claim_count=0)
    assert result.support_gate is None and result.support_status == "not_applicable"
    assert result.claims.review_coverage is result.claims.supported_fraction is None


def test_incomplete_empty_review_is_abstention_not_zero_claim_success():
    result = score(
        claim_bindings=(), declared_material_claim_count=0, claim_inventory_complete=False
    )
    assert result.support_status == "unassessed" and result.support_gate is None


def test_declared_count_cannot_be_lower_than_exact_annotations():
    handoff = make_handoff()
    payload = review(handoff).model_dump()
    payload["declared_material_claim_count"] = 1
    rejects("InvalidSemanticReviewInput", score_review, handoff, payload, scope=scope())


def ask_handoff():
    return make_handoff(
        analysis=AnalysisResult(
            decision="ask",
            user_draft="Can you share the callback?",
            next_question="Can you share the callback?",
            missing_info=("callback_code",),
            maintainer_summary="The callback has not been supplied.",
            rationale="The missing code can clarify state update order.",
        )
    )


def test_ask_cannot_claim_question_dimensions_are_not_applicable():
    handoff = ask_handoff()
    record = review(handoff, claim_bindings=())
    rejects("QuestionApplicabilityMismatch", score_review, handoff, record, scope=record.scope)


@pytest.mark.parametrize("dimension", ["necessary", "answerable", "not_repeating_known"])
def test_question_has_three_explicit_independent_judgments(dimension):
    handoff = ask_handoff()
    no = score(handoff, claim_bindings=(), question=question(applies=True, **{dimension: "no"}))
    unknown = score(
        handoff, claim_bindings=(), question=question(applies=True, **{dimension: "unassessed"})
    )
    yes = score(handoff, claim_bindings=(), question=question(applies=True))
    assert (no.question_gate, no.question_status) == (0, "fail")
    assert (unknown.question_gate, unknown.question_status) == (None, "unassessed")
    assert (yes.question_gate, yes.question_status) == (1, "pass")


def test_nonask_structured_user_check_still_needs_question_review():
    base = make_handoff()
    analysis = base.analysis.model_copy(update={"checks_suggested": ("Share the callback code.",)})
    handoff = make_handoff(analysis=analysis)
    record = review(handoff)
    rejects("QuestionApplicabilityMismatch", score_review, handoff, record, scope=record.scope)
    assert score(handoff, question=question(applies=True)).question_gate == 1


def test_human_edit_has_distinct_binding_and_never_improves_original_model_group():
    original = make_handoff()
    unsupported = source_binding(original, judgment="unsupported")
    model_score = score(original, claim_bindings=(unsupported,), reviewer_kind="assistant")
    edited = edit_handoff(
        original,
        "edited-proposal",
        original.analysis.model_copy(update={"user_draft": "A widget has an initial default."}),
    )
    record = review(
        edited,
        review_id="edit-review",
        response_origin="maintainer_edit",
        original_handoff_sha256=original.handoff_sha256,
        reviewer_kind="assistant",
    )
    edited_score = score_review(edited, record, scope=record.scope, original_handoff=original)
    groups = aggregate_reviews([model_score, edited_score])["groups"]
    assert len(groups) == 2
    by_origin = {group["response_origin"]: group for group in groups}
    assert by_origin["model"]["by_stratum"]["answerable"]["support_statuses"]["fail"] == 1
    assert by_origin["maintainer_edit"]["by_stratum"]["answerable"]["support_statuses"]["pass"] == 1


@pytest.mark.parametrize(
    "bad",
    [
        "missing_original",
        "same_handoff",
        "wrong_hash",
        "changed_case",
        "changed_revision",
        "changed_evidence",
        "changed_message",
    ],
)
def test_edit_must_bind_different_original_with_same_inputs(bad):
    original = make_handoff()
    edited = edit_handoff(original, "edited-proposal", original.analysis)
    supplied = original
    if bad == "missing_original":
        supplied = None
    elif bad == "same_handoff":
        supplied = edited
    elif bad in {"changed_case", "changed_revision", "changed_evidence", "changed_message"}:
        changes = {"proposal_id": original.proposal_id}
        if bad == "changed_case":
            changes["case_id"] = "different-case"
        if bad == "changed_revision":
            changes["revision"] = 3
        if bad == "changed_evidence":
            changes["evidence"] = original.evidence.model_copy(
                update={"snapshot_id": "different-snapshot"}
            )
        if bad == "changed_message":
            changes["message"] = "Different original input."
        supplied = make_handoff(**changes)
    digest = supplied.handoff_sha256 if supplied is not None else original.handoff_sha256
    record = review(
        edited,
        response_origin="maintainer_edit",
        original_handoff_sha256="0" * 64 if bad == "wrong_hash" else digest,
    )
    rejects(
        "EditedOriginMismatch",
        score_review,
        edited,
        record,
        scope=record.scope,
        original_handoff=supplied,
    )


def test_model_record_cannot_silently_attach_an_original_edit_pair():
    original = make_handoff()
    record = review(original)
    rejects(
        "EditedOriginMismatch",
        score_review,
        original,
        record,
        scope=record.scope,
        original_handoff=original,
    )


def test_declared_assistant_and_human_scores_never_share_a_group_or_quality_claim():
    handoff = make_handoff()
    result = aggregate_reviews(
        [score(handoff), score(handoff, reviewer_kind="assistant", review_id="assistant-review")]
    )
    assert {group["reviewer_kind"] for group in result["groups"]} == {"human", "assistant"}
    assert result["quality_claim"] is False and result["authorizes_action"] is False


@pytest.mark.parametrize(
    "change",
    [
        {},
        {"review_id": "second-review"},
        {"reviewer_id": "second-declared-human"},
    ],
)
def test_duplicate_proposal_review_is_not_double_counted(change):
    handoff = make_handoff()
    rejects(
        "DuplicateProposalReview", aggregate_reviews, [score(handoff), score(handoff, **change)]
    )


@pytest.mark.parametrize("change", ["id", "hash", "both"])
def test_same_proposal_under_distinct_frozen_rubrics_has_separate_denominators(change):
    handoff = make_handoff()
    different = scope(
        rubric_id="rubric-two" if change in {"id", "both"} else "rubric-one",
        rubric_sha256="4" * 64 if change in {"hash", "both"} else "2" * 64,
    )
    first = score(handoff)
    second = score(handoff, scope=different, decision_judgment="unacceptable")
    result = aggregate_reviews([first, second])
    assert len(result["groups"]) == 2
    assert all(group["proposal_count"] == 1 for group in result["groups"])
    judgments = [
        group["by_stratum"]["answerable"]["declared_decision_acceptance_fraction"]
        for group in result["groups"]
    ]
    assert sorted(judgments) == [0, 1]
    assert result["quality_claim"] is False
    rejects("DuplicateProposalReview", aggregate_reviews, [first, second, second])


@pytest.mark.parametrize("change", ["config", "rubric", "run"])
def test_different_runs_configurations_and_rubrics_have_separate_denominators(change):
    first = score()
    other = make_handoff(case_id="other-case", proposal_id="other-proposal")
    config = (
        scope(config_id="config-two", config_sha256="4" * 64)
        if change == "config"
        else scope(rubric_id="rubric-two", rubric_sha256="4" * 64)
    )
    if change == "run":
        config = scope(run_id="evaluation-two")
    result = aggregate_reviews([first, score(other, scope=config)])
    assert len(result["groups"]) == 2
    assert all(group["proposal_count"] == 1 for group in result["groups"])


def test_all_escalation_does_not_hide_answerable_and_ambiguous_failures():
    rows = []
    for index, (stratum, judgment) in enumerate(
        [
            ("answerable", "unacceptable"),
            ("ambiguous", "unacceptable"),
            ("needs_escalation", "acceptable"),
        ]
    ):
        analysis = AnalysisResult(
            decision="escalate",
            user_draft="Further maintainer investigation is needed.",
            maintainer_summary="No fix is claimed.",
            rationale="Unresolved uncertainty.",
        )
        handoff = make_handoff(
            case_id=f"case-{index}", proposal_id=f"proposal-{index}", analysis=analysis
        )
        rows.append(
            score(
                handoff, scope=scope(stratum=stratum), claim_bindings=(), decision_judgment=judgment
            )
        )
    strata = aggregate_reviews(rows)["groups"][0]["by_stratum"]
    assert [
        strata[name]["declared_decision_acceptance_fraction"]
        for name in ("answerable", "ambiguous", "needs_escalation")
    ] == [0.0, 0.0, 1.0]
    assert all(strata[name]["decision_judged_denominator"] == 1 for name in strata)
    assert all(strata[name]["actual_decisions"]["escalate"] == 1 for name in strata)


def test_na_unassessed_and_empty_strata_are_not_successes_or_zero_scores():
    result = aggregate_reviews(
        [
            score(
                claim_bindings=(),
                declared_material_claim_count=0,
                usefulness_score=None,
                decision_judgment="unassessed",
            )
        ]
    )
    strata = result["groups"][0]["by_stratum"]
    assert strata["answerable"]["support_statuses"]["not_applicable"] == 1
    assert strata["answerable"]["support_judged_denominator"] == 0
    assert strata["answerable"]["declared_support_pass_fraction"] is None
    assert strata["answerable"]["decision_judged_denominator"] == 0
    assert strata["answerable"]["usefulness_unassessed"] == 1
    assert strata["ambiguous"]["proposals"] == 0
    assert strata["ambiguous"]["declared_decision_acceptance_fraction"] is None
    assert aggregate_reviews([])["groups"] == []


def test_aggregate_claim_coverage_and_case_count_do_not_hide_partial_turn_reviews():
    first = score()
    second = score(
        make_handoff(revision=3, proposal_id="proposal-next"), declared_material_claim_count=3
    )
    group = aggregate_reviews([first, second])["groups"][0]["by_stratum"]["answerable"]
    assert group["proposals"] == 2 and group["cases"] == 1
    assert group["claim_counts"] == {
        "total": 5,
        "reviewed": 4,
        "supported": 4,
        "unsupported": 0,
        "insufficient": 0,
        "unreviewed": 1,
    }
    assert group["claim_review_coverage"] == group["declared_supported_claim_fraction"] == 0.8
    assert group["support_judged_denominator"] == 1
    assert group["support_statuses"]["unassessed"] == 1


def test_unassessed_question_has_no_successful_denominator():
    handoff = ask_handoff()
    result = score(
        handoff,
        scope=scope(stratum="ambiguous"),
        claim_bindings=(),
        question=question(applies=True, answerable="unassessed"),
    )
    group = aggregate_reviews([result])["groups"][0]["by_stratum"]["ambiguous"]
    assert group["question_statuses"]["unassessed"] == 1
    assert group["question_judged_denominator"] == 0
    assert group["declared_question_pass_fraction"] is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("declared_material_claim_count", True),
        ("declared_material_claim_count", "2"),
        ("claim_inventory_complete", "true"),
        ("usefulness_score", True),
        ("usefulness_score", 3),
        ("usefulness_score", -1),
    ],
)
def test_sidecar_numbers_and_booleans_are_strict(field, value):
    handoff = make_handoff()
    payload = review(handoff).model_dump()
    payload[field] = value
    rejects("InvalidSemanticReviewInput", score_review, handoff, payload, scope=scope())


def test_unknown_nested_fields_and_bypassed_models_do_not_leak_raw_details():
    handoff = make_handoff()
    record = review(handoff)
    for payload in [
        record.model_dump() | {"SECRET-FIELD-NAME": "SECRET-CREDENTIAL"},
        record.model_copy(update={"SECRET-FIELD-NAME": "SECRET-CREDENTIAL"}),
        record.model_copy(
            update={
                "claim_bindings": (
                    record.claim_bindings[0].model_copy(
                        update={"SECRET-FIELD-NAME": "SECRET-CREDENTIAL"}
                    ),
                )
            }
        ),
    ]:
        with pytest.raises(SemanticReviewRejected) as caught:
            score_review(handoff, payload, scope=scope())
        assert str(caught.value) == "InvalidSemanticReviewInput"
        assert "SECRET" not in str(caught.value)


def test_aggregator_rejects_forged_counts_gates_and_authority():
    result = score()
    for forged in [
        result.model_copy(update={"support_gate": True}),
        result.model_copy(update={"support_status": "fail"}),
        result.model_copy(update={"quality_claim": True}),
        result.model_copy(update={"authorizes_action": True}),
        result.model_copy(update={"claims": result.claims.model_copy(update={"supported": 99})}),
    ]:
        rejects("InvalidSemanticReviewInput", aggregate_reviews, [forged])
