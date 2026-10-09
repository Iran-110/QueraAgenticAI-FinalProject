"""Content-bound review records do not perform semantic evaluation or actions."""

import pytest
from pydantic import ValidationError

from agent_app.contracts import (
    AnalysisResult,
    CaseState,
    EvidenceBundle,
    EvidenceHit,
    EvidenceLink,
    Fact,
    ReviewAttestation,
    ReviewClaimBinding,
    ReviewDimension,
    ReviewOutputSpan,
    ReviewSourceQuote,
)
from agent_app.reasoning import review
from agent_app.reasoning.review import (
    REVIEW_DIMENSIONS,
    build_proposal_review_packet,
    review_user_fact_sha256,
    validate_proposal_review,
)


@pytest.fixture
def objects():
    case = CaseState(
        case_id="review-case",
        case_revision=2,
        facts=(
            Fact(
                name="streamlit_version",
                value="1.49.1",
                source_ref="user:correction",
                turn_id="correction",
            ),
            Fact(
                name="reported_reduction",
                value="Small example works",
                source_ref="user:initial",
                turn_id="initial",
            ),
        ),
    )
    evidence = EvidenceBundle(
        snapshot_id="review-snapshot",
        hits=(
            EvidenceHit(
                chunk_id="release-150",
                source_id="docs:release-150",
                excerpt="Version 1.50.0\n  Keyed multiselect identity uses the key. \nFooter",
                source_url="https://example.org/authored-review-fixture",
                source_type="release_note",
                source_span="paragraph 1",
                source_commit="fixture-commit",
                applicable_versions=("1.50.0",),
            ),
        ),
    )
    analysis = AnalysisResult(
        decision="answer",
        user_draft=(
            "The 1.50.0 release note describes key identity. The current deployment is 1.49.1."
        ),
        maintainer_summary="Reporter: small example works.",
        rationale="The historical note does not prove the full-app cause.",
        evidence_links=(
            EvidenceLink(claim="1.50.0 notes describe key identity.", chunk_id="release-150"),
        ),
        facts_delta=(case.facts[0],),
        checks_suggested=("Inspect the missing parent callback.",),
    )
    return case, evidence, analysis


def span(surface_id, text, selected=None):
    selected = text if selected is None else selected
    start = text.index(selected)
    return ReviewOutputSpan(
        surface_id=surface_id, start=start, end=start + len(selected), text=selected
    )


def source_binding(analysis, evidence, **changes):
    text = analysis.evidence_links[0].claim
    quote = evidence.hits[0].excerpt
    data = {
        "output": span("evidence_links.0.claim", text),
        "judgment": "supported",
        "applicability": "historical",
        "source_quote": ReviewSourceQuote(
            chunk_id=evidence.hits[0].chunk_id, start=0, end=len(quote), quote=quote
        ),
    }
    return ReviewClaimBinding(**(data | changes))


def attestation(packet, bindings=(), **changes):
    data = {
        "reviewer_id": "reviewer:human-1",
        "packet_sha256": packet.packet_sha256,
        "disposition": "approved",
        "reviewed_surfaces": tuple(surface.surface_id for surface in packet.surfaces),
        "dimensions": tuple(ReviewDimension(name=name, passed=True) for name in REVIEW_DIMENSIONS),
        "claim_bindings": bindings,
    }
    return ReviewAttestation(**(data | changes))


def validate(packet, record, objects, reviewer="reviewer:human-1"):
    return validate_proposal_review(packet, record, *objects, authenticated_reviewer_id=reviewer)


def test_complete_bound_historical_review_passes_without_granting_action(objects):
    case, evidence, analysis = objects
    before = [obj.model_dump() for obj in objects]
    packet = build_proposal_review_packet(*objects)
    source = source_binding(analysis, evidence)
    fact = ReviewClaimBinding(
        output=span("user_draft", analysis.user_draft, "1.49.1"),
        judgment="supported",
        applicability="current",
        user_fact_sha256=review_user_fact_sha256(case.facts[0]),
    )
    record = attestation(packet, (source, fact))
    result = validate(packet, record, objects)
    assert result.status == "pass"
    assert result.codes == ()
    assert set(result.model_dump()) == {"status", "codes"}
    assert before == [obj.model_dump() for obj in objects]


def test_quote_offsets_preserve_interior_leading_and_trailing_whitespace(objects):
    _, evidence, analysis = objects
    packet = build_proposal_review_packet(*objects)
    excerpt = evidence.hits[0].excerpt
    start = excerpt.index("\n") + 1
    end = excerpt.index("Footer")
    quote = ReviewSourceQuote(
        chunk_id="release-150", start=start, end=end, quote=excerpt[start:end]
    )
    assert quote.quote.startswith("  ")
    assert quote.quote.endswith(" \n")
    binding = source_binding(analysis, evidence, source_quote=quote)
    assert validate(packet, attestation(packet, (binding,)), objects).status == "pass"


def test_packet_inventory_includes_every_free_text_and_fact_surface(objects):
    case, evidence, analysis = objects
    ask = analysis.model_copy(
        update={
            "decision": "ask",
            "missing_info": ("callback",),
            "next_question": "Can you share the callback?",
        }
    )
    packet = build_proposal_review_packet(case, evidence, ask)
    assert {surface.surface_id for surface in packet.surfaces} == {
        "decision",
        "user_draft",
        "maintainer_summary",
        "rationale",
        "evidence_links.0.claim",
        "missing_info.0",
        "next_question",
        "facts_delta.0",
        "checks_suggested.0",
    }
    dumped = packet.model_dump_json()
    assert analysis.user_draft not in dumped
    assert evidence.hits[0].excerpt not in dumped
    assert "1.49.1" not in dumped


@pytest.mark.parametrize(
    "field,value",
    [
        ("user_draft", "Changed user-visible claim."),
        ("maintainer_summary", "Changed maintainer claim."),
        ("rationale", "Changed justification."),
        (
            "evidence_links",
            (EvidenceLink(claim="Changed citation claim.", chunk_id="release-150"),),
        ),
        ("checks_suggested", ("A different proposed check.",)),
        ("facts_delta", ()),
        ("decision", "escalate"),
    ],
)
def test_any_proposal_surface_or_fact_change_invalidates_old_record(objects, field, value):
    case, evidence, analysis = objects
    packet = build_proposal_review_packet(*objects)
    changed = analysis.model_copy(update={field: value})
    result = validate(packet, attestation(packet), (case, evidence, changed))
    assert result.status == "needs_review"
    assert "ReviewPacketMismatch" in result.codes
    assert "AttestationPacketMismatch" in result.codes


@pytest.mark.parametrize("field", ["next_question", "missing_info"])
def test_question_and_missing_target_drift_invalidates_old_record(objects, field):
    case, evidence, analysis = objects
    ask = analysis.model_copy(
        update={
            "decision": "ask",
            "missing_info": ("callback",),
            "next_question": "Can you share the callback?",
        }
    )
    packet = build_proposal_review_packet(case, evidence, ask)
    change = "Can you find documentation?" if field == "next_question" else ("documentation",)
    changed = ask.model_copy(update={field: change})
    result = validate(packet, attestation(packet), (case, evidence, changed))
    assert "AttestationPacketMismatch" in result.codes


@pytest.mark.parametrize(
    "change",
    [
        {"case_revision": 3},
        {"case_id": "another-case"},
        {"checks_performed": ("An additional reported check.",)},
        {"unknowns": ("another_gap",)},
        {"pending_proposal_id": "another-pending-proposal"},
    ],
)
def test_case_changes_even_at_same_revision_invalidate_review(objects, change):
    case, evidence, analysis = objects
    packet = build_proposal_review_packet(*objects)
    changed = case.model_copy(update=change)
    result = validate(packet, attestation(packet), (changed, evidence, analysis))
    assert "ReviewPacketMismatch" in result.codes
    assert "AttestationPacketMismatch" in result.codes


@pytest.mark.parametrize(
    "change",
    [
        {"excerpt": "A replaced excerpt with the identical chunk ID."},
        {"source_url": "https://example.org/another-fixture"},
        {"source_commit": "different-commit"},
        {"source_span": "different paragraph"},
        {"applicable_versions": ("1.49.1",)},
        {"source_id": "different-source"},
    ],
)
def test_source_bytes_and_provenance_cannot_change_behind_same_chunk_id(objects, change):
    case, evidence, analysis = objects
    packet = build_proposal_review_packet(*objects)
    changed = evidence.model_copy(update={"hits": (evidence.hits[0].model_copy(update=change),)})
    result = validate(packet, attestation(packet), (case, changed, analysis))
    assert "ReviewPacketMismatch" in result.codes
    assert "AttestationPacketMismatch" in result.codes


def test_latest_bundle_retirement_invalidates_old_packet_and_quote(objects):
    case, evidence, analysis = objects
    packet = build_proposal_review_packet(*objects)
    record = attestation(packet, (source_binding(analysis, evidence),))
    latest = evidence.model_copy(update={"hits": (), "retrieval_round": 2})
    result = validate(packet, record, (case, latest, analysis))
    assert "AttestationPacketMismatch" in result.codes
    assert "UnknownReviewSource" in result.codes


@pytest.mark.parametrize("reviewer", [None, "", False, "reviewer:another", " reviewer:human-1"])
def test_reviewer_identity_requires_separately_authenticated_caller_provenance(objects, reviewer):
    packet = build_proposal_review_packet(*objects)
    result = validate(packet, attestation(packet), objects, reviewer=reviewer)
    assert result.status == "needs_review"
    assert result.codes == (
        "ReviewerMismatch" if type(reviewer) is str and reviewer else "UnauthenticatedReviewer",
    )


def test_model_cannot_supply_review_attestation_in_analysis_result(objects):
    packet = build_proposal_review_packet(*objects)
    proposal = objects[2].model_dump()
    proposal["review_attestation"] = attestation(packet).model_dump()
    with pytest.raises(ValidationError, match="Extra inputs"):
        AnalysisResult.model_validate(proposal)


@pytest.mark.parametrize("dimension", REVIEW_DIMENSIONS)
def test_each_semantic_review_dimension_is_required(objects, dimension):
    packet = build_proposal_review_packet(*objects)
    record = attestation(
        packet,
        dimensions=tuple(
            ReviewDimension(name=name, passed=True)
            for name in REVIEW_DIMENSIONS
            if name != dimension
        ),
    )
    assert "IncompleteDimensionReview" in validate(packet, record, objects).codes


@pytest.mark.parametrize("dimension", REVIEW_DIMENSIONS)
def test_each_failed_semantic_dimension_blocks_the_review(objects, dimension):
    packet = build_proposal_review_packet(*objects)
    record = attestation(
        packet,
        dimensions=tuple(
            ReviewDimension(name=name, passed=name != dimension) for name in REVIEW_DIMENSIONS
        ),
    )
    assert "ReviewDimensionFailed" in validate(packet, record, objects).codes


def test_incomplete_surface_review_and_extra_surface_are_reported(objects):
    packet = build_proposal_review_packet(*objects)
    ids = tuple(surface.surface_id for surface in packet.surfaces)
    record = attestation(packet, reviewed_surfaces=ids[1:] + ("invented_surface",))
    result = validate(packet, record, objects)
    assert result.codes == ("IncompleteSurfaceReview", "UnknownReviewSurface")


def test_explicit_needs_revision_blocks_even_if_all_dimensions_pass(objects):
    packet = build_proposal_review_packet(*objects)
    assert validate(packet, attestation(packet, disposition="needs_revision"), objects).codes == (
        "ReviewNeedsRevision",
    )


@pytest.mark.parametrize("judgment", ["unsupported", "insufficient"])
def test_unsupported_or_insufficient_claim_judgment_blocks(objects, judgment):
    _, evidence, analysis = objects
    packet = build_proposal_review_packet(*objects)
    binding = source_binding(analysis, evidence, judgment=judgment)
    assert validate(packet, attestation(packet, (binding,)), objects).codes == (
        "ClaimNeedsRevision",
    )


@pytest.mark.parametrize(
    "quote_text", ["Invented supporting text", "Version 1.50.0 Keyed identity"]
)
def test_source_quote_must_be_exact_contiguous_source_span(objects, quote_text):
    _, evidence, analysis = objects
    packet = build_proposal_review_packet(*objects)
    binding = source_binding(
        analysis,
        evidence,
        source_quote=ReviewSourceQuote(
            chunk_id="release-150", start=0, end=len(quote_text), quote=quote_text
        ),
    )
    assert "SourceQuoteMismatch" in validate(packet, attestation(packet, (binding,)), objects).codes


def test_wrong_output_span_or_unknown_output_surface_blocks(objects):
    _, evidence, analysis = objects
    packet = build_proposal_review_packet(*objects)
    text = "A wrong claim"
    binding = source_binding(
        analysis,
        evidence,
        output=ReviewOutputSpan(surface_id="user_draft", start=0, end=len(text), text=text),
    )
    assert "OutputSpanMismatch" in validate(packet, attestation(packet, (binding,)), objects).codes
    binding = binding.model_copy(
        update={"output": binding.output.model_copy(update={"surface_id": "invented_surface"})}
    )
    assert (
        "UnknownReviewSurface" in validate(packet, attestation(packet, (binding,)), objects).codes
    )


@pytest.mark.parametrize("fact_change", [{"status": "superseded"}, {"provenance_kind": "evidence"}])
def test_only_exact_active_user_fact_identity_can_support_a_claim(objects, fact_change):
    case, evidence, analysis = objects
    original = case.facts[0]
    changed_fact = original.model_copy(update=fact_change)
    case = case.model_copy(update={"facts": (changed_fact, *case.facts[1:])})
    updated = (case, evidence, analysis)
    packet = build_proposal_review_packet(*updated)
    binding = ReviewClaimBinding(
        output=span("user_draft", analysis.user_draft, "1.49.1"),
        judgment="supported",
        applicability="current",
        user_fact_sha256=review_user_fact_sha256(changed_fact),
    )
    assert (
        "InactiveUserFactReference"
        in validate(packet, attestation(packet, (binding,)), updated).codes
    )


def test_new_active_fact_with_same_name_cannot_reuse_old_fact_reference(objects):
    case, evidence, analysis = objects
    old_fact_hash = review_user_fact_sha256(case.facts[0])
    new_fact = case.facts[0].model_copy(update={"value": "1.48.0", "turn_id": "new-correction"})
    updated = (case.model_copy(update={"facts": (new_fact, *case.facts[1:])}), evidence, analysis)
    packet = build_proposal_review_packet(*updated)
    binding = ReviewClaimBinding(
        output=span("user_draft", analysis.user_draft, "1.49.1"),
        judgment="supported",
        applicability="current",
        user_fact_sha256=old_fact_hash,
    )
    assert (
        "InactiveUserFactReference"
        in validate(packet, attestation(packet, (binding,)), updated).codes
    )


@pytest.mark.parametrize("version", [None, "1.49.1"])
def test_current_applicability_requires_explicit_matching_active_user_version(objects, version):
    case, evidence, analysis = objects
    if version is None:
        case = case.model_copy(update={"facts": case.facts[1:]})
    updated = (case, evidence, analysis)
    packet = build_proposal_review_packet(*updated)
    binding = source_binding(analysis, evidence, applicability="current")
    assert (
        "CurrentVersionApplicabilityUnconfirmed"
        in validate(packet, attestation(packet, (binding,)), updated).codes
    )


def test_current_applicability_with_exact_matching_metadata_is_usable(objects):
    case, evidence, analysis = objects
    matched = evidence.model_copy(
        update={"hits": (evidence.hits[0].model_copy(update={"applicable_versions": ("1.49.1",)}),)}
    )
    updated = (case, matched, analysis)
    packet = build_proposal_review_packet(*updated)
    binding = source_binding(analysis, matched, applicability="current")
    assert validate(packet, attestation(packet, (binding,)), updated).status == "pass"


def test_unknown_scope_can_be_reviewed_without_claiming_current_applicability(objects):
    _, evidence, analysis = objects
    packet = build_proposal_review_packet(*objects)
    binding = source_binding(analysis, evidence, applicability="unknown")
    assert validate(packet, attestation(packet, (binding,)), objects).status == "pass"


def test_hash_and_quote_checks_do_not_compute_semantic_entailment(objects):
    case, evidence, analysis = objects
    bad = analysis.model_copy(update={"user_draft": "Removing the key guarantees a fix."})
    updated = (case, evidence, bad)
    packet = build_proposal_review_packet(*updated)
    quote = evidence.hits[0].excerpt
    # This deliberately incorrect reviewer judgment is mechanically well bound.
    # The caller needs a competent source review; hashes cannot detect this error.
    binding = ReviewClaimBinding(
        output=span("user_draft", bad.user_draft),
        judgment="supported",
        applicability="historical",
        source_quote=ReviewSourceQuote(
            chunk_id="release-150", start=0, end=len(quote), quote=quote
        ),
    )
    assert validate(packet, attestation(packet, (binding,)), updated).status == "pass"


def test_packet_tampering_is_detected_even_when_attestation_reuses_original_digest(objects):
    packet = build_proposal_review_packet(*objects)
    altered = packet.model_copy(update={"case_sha256": "a" * 64})
    assert validate(altered, attestation(packet), objects).codes == ("ReviewPacketMismatch",)


def test_invalid_constructed_objects_fail_with_allowlisted_codes(objects):
    packet = build_proposal_review_packet(*objects)
    invalid = attestation(packet).model_copy(update={"reviewer_id": "private arbitrary text!"})
    result = validate(packet, invalid, objects)
    assert result.codes == ("InvalidReviewInput",)
    assert "private arbitrary" not in result.model_dump_json()
    with pytest.raises(ValueError, match="InvalidReviewInput"):
        build_proposal_review_packet(
            objects[0].model_copy(update={"case_revision": -1}), *objects[1:]
        )


@pytest.mark.parametrize("input_kind", ["mutated_fact", "not_fact"])
def test_public_fact_hash_helper_does_not_export_raw_validation_inputs(objects, input_kind):
    marker = "private-fact-hash-probe-marker"
    malformed = (
        objects[0].facts[0].model_copy(update={"value": {marker: "invalid"}})
        if input_kind == "mutated_fact"
        else {marker: "not a fact"}
    )
    with pytest.raises(ValueError, match="^InvalidReviewInput$") as caught:
        review_user_fact_sha256(malformed)
    assert type(caught.value) is ValueError
    assert marker not in str(caught.value)
    assert caught.value.__cause__ is None


def test_unicode_encoding_failure_is_sanitized_at_digest_helper():
    marker = "private-unicode-review-probe-\ud800"
    with pytest.raises(ValueError, match="^InvalidReviewInput$") as caught:
        review._digest("probe", marker)
    assert type(caught.value) is ValueError
    assert "private-unicode" not in str(caught.value)
    assert caught.value.__cause__ is None


@pytest.mark.parametrize("surface", ["case_fact", "evidence_excerpt", "user_draft"])
def test_lone_surrogate_in_constructed_public_packet_inputs_is_sanitized(objects, surface):
    case, evidence, analysis = objects
    marker = "private-public-review-probe-\ud800"
    if surface == "case_fact":
        fact = case.facts[0].model_copy(update={"value": marker})
        case = case.model_copy(update={"facts": (fact, *case.facts[1:])})
    elif surface == "evidence_excerpt":
        hit = evidence.hits[0].model_copy(update={"excerpt": marker})
        evidence = evidence.model_copy(update={"hits": (hit,)})
    else:
        analysis = analysis.model_copy(update={"user_draft": marker})
    with pytest.raises(ValueError, match="^InvalidReviewInput$") as caught:
        build_proposal_review_packet(case, evidence, analysis)
    assert type(caught.value) is ValueError
    assert "private-public" not in str(caught.value)
    assert caught.value.__cause__ is None


def test_oversized_integer_encoding_failure_in_public_packet_is_sanitized(objects):
    import sys

    prior_limit = sys.get_int_max_str_digits()
    try:
        sys.set_int_max_str_digits(4300)
        case, evidence, analysis = objects
        case = case.model_copy(update={"case_revision": 10**5000})
        with pytest.raises(ValueError, match="^InvalidReviewInput$") as caught:
            build_proposal_review_packet(case, evidence, analysis)
        assert type(caught.value) is ValueError
        assert caught.value.__cause__ is None
    finally:
        sys.set_int_max_str_digits(prior_limit)


def test_review_is_for_final_proposals_only(objects):
    case, evidence, _ = objects
    intermediate = AnalysisResult(
        decision="retrieve_more",
        user_draft="",
        maintainer_summary="",
        rationale="Seek the missing official release record.",
        retrieval_queries=("Streamlit multiselect key identity release notes",),
    )
    with pytest.raises(ValueError, match="FinalProposalRequired"):
        build_proposal_review_packet(case, evidence, intermediate)
    packet = build_proposal_review_packet(*objects)
    result = validate(packet, attestation(packet), (case, evidence, intermediate))
    assert result.codes == ("FinalProposalRequired",)
