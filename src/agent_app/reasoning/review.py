"""Pure whole-proposal review bindings; no model, storage or action authorization.

Exact spans and hashes establish what a caller-authenticated reviewer saw. They
do not establish entailment, source authenticity or the correctness of a review.
The tracker must authenticate the reviewer and separately authorize any action.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import ValidationError

from agent_app.contracts import (
    AnalysisResult,
    CaseState,
    EvidenceBundle,
    Fact,
    ProposalReviewPacket,
    ProposalReviewResult,
    ReviewAttestation,
    ReviewSurface,
)

REVIEW_DIMENSIONS = (
    "claim_support",
    "version_applicability",
    "fact_fidelity",
    "question_utility",
    "conflict_handling",
    "uncertainty",
)


def _canonical(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (ValueError, TypeError, RecursionError):
        raise ValueError("InvalidReviewInput") from None


def _digest(kind: str, value: Any) -> str:
    try:
        return hashlib.sha256(
            ("proposal-review-v1:" + kind + ":" + _canonical(value)).encode("utf-8")
        ).hexdigest()
    except (ValueError, TypeError, RecursionError):
        raise ValueError("InvalidReviewInput") from None


def review_user_fact_sha256(fact: Fact) -> str:
    """Hash an exact attributed fact identity, including provenance and status."""
    try:
        fact = Fact.model_validate(fact.model_dump(warnings=False))
        return _digest("user-fact", fact.model_dump(mode="json"))
    except (ValidationError, ValueError, TypeError, AttributeError, RecursionError):
        raise ValueError("InvalidReviewInput") from None


def _validated_inputs(
    case: CaseState, evidence: EvidenceBundle, analysis: AnalysisResult
) -> tuple[CaseState, EvidenceBundle, AnalysisResult]:
    return (
        CaseState.model_validate(case.model_dump(warnings=False)),
        EvidenceBundle.model_validate(evidence.model_dump(warnings=False)),
        AnalysisResult.model_validate(analysis.model_dump(warnings=False)),
    )


def _surface_texts(analysis: AnalysisResult) -> dict[str, str]:
    surfaces = {
        "decision": analysis.decision,
        "user_draft": analysis.user_draft,
        "maintainer_summary": analysis.maintainer_summary,
        "rationale": analysis.rationale,
    }
    if analysis.next_question is not None:
        surfaces["next_question"] = analysis.next_question
    for index, link in enumerate(analysis.evidence_links):
        surfaces[f"evidence_links.{index}.claim"] = link.claim
    for name in ("missing_info", "retrieval_queries", "checks_suggested"):
        for index, text in enumerate(getattr(analysis, name)):
            surfaces[f"{name}.{index}"] = text
    for index, fact in enumerate(analysis.facts_delta):
        surfaces[f"facts_delta.{index}"] = _canonical(fact.model_dump(mode="json"))
    return {name: text for name, text in surfaces.items() if text}


def build_proposal_review_packet(
    case: CaseState, evidence: EvidenceBundle, analysis: AnalysisResult
) -> ProposalReviewPacket:
    """Bind a final proposal to the entire case and latest supplied source bundle.

    The caller must supply the actual last retrieval bundle, not an earlier one.
    This pure helper cannot determine which bundle the caller last retrieved.
    """
    try:
        case, evidence, analysis = _validated_inputs(case, evidence, analysis)
    except (ValidationError, ValueError, TypeError, AttributeError, RecursionError):
        raise ValueError("InvalidReviewInput") from None
    if analysis.decision == "retrieve_more":
        raise ValueError("FinalProposalRequired")
    try:
        surfaces = tuple(
            ReviewSurface(surface_id=name, text_sha256=_digest("surface", text), length=len(text))
            for name, text in _surface_texts(analysis).items()
        )
        payload = {
            "schema_version": 1,
            "case_id": case.case_id,
            "case_revision": case.case_revision,
            "case_sha256": _digest("case", case.model_dump(mode="json")),
            "evidence_sha256": _digest("evidence", evidence.model_dump(mode="json")),
            "analysis_sha256": _digest("analysis", analysis.model_dump(mode="json")),
            "surfaces": [surface.model_dump(mode="json") for surface in surfaces],
        }
        return ProposalReviewPacket(**payload, packet_sha256=_digest("packet", payload))
    except (ValidationError, ValueError, TypeError, AttributeError, RecursionError):
        raise ValueError("InvalidReviewInput") from None


def validate_proposal_review(
    packet: ProposalReviewPacket,
    attestation: ReviewAttestation,
    case: CaseState,
    evidence: EvidenceBundle,
    analysis: AnalysisResult,
    *,
    authenticated_reviewer_id: str | None = None,
) -> ProposalReviewResult:
    """Check integrity and completeness of a separately authenticated review.

    ``authenticated_reviewer_id`` must come from the caller's authenticated review
    event, never from model output or retrieved text. ID equality is an integrity
    check, not authentication. A pass establishes a usable review record, never
    tracker approval, execution permission or automatic semantic correctness.
    """
    try:
        case, evidence, analysis = _validated_inputs(case, evidence, analysis)
        packet = ProposalReviewPacket.model_validate(packet.model_dump(warnings=False))
        attestation = ReviewAttestation.model_validate(attestation.model_dump(warnings=False))
    except (ValidationError, ValueError, TypeError, AttributeError, RecursionError):
        return ProposalReviewResult(status="needs_review", codes=("InvalidReviewInput",))
    if analysis.decision == "retrieve_more":
        return ProposalReviewResult(status="needs_review", codes=("FinalProposalRequired",))
    try:
        expected_packet = build_proposal_review_packet(case, evidence, analysis)
    except ValueError:
        return ProposalReviewResult(status="needs_review", codes=("InvalidReviewInput",))
    codes = []
    if packet != expected_packet:
        codes.append("ReviewPacketMismatch")
    if type(authenticated_reviewer_id) is not str or not authenticated_reviewer_id:
        codes.append("UnauthenticatedReviewer")
    elif authenticated_reviewer_id != attestation.reviewer_id:
        codes.append("ReviewerMismatch")
    if attestation.packet_sha256 != expected_packet.packet_sha256:
        codes.append("AttestationPacketMismatch")
    expected_surfaces = {surface.surface_id for surface in expected_packet.surfaces}
    reviewed_surfaces = set(attestation.reviewed_surfaces)
    if expected_surfaces - reviewed_surfaces:
        codes.append("IncompleteSurfaceReview")
    if reviewed_surfaces - expected_surfaces:
        codes.append("UnknownReviewSurface")
    dimensions = {dimension.name: dimension.passed for dimension in attestation.dimensions}
    if set(dimensions) != set(REVIEW_DIMENSIONS):
        codes.append("IncompleteDimensionReview")
    if not all(dimensions.values()):
        codes.append("ReviewDimensionFailed")
    if attestation.disposition != "approved":
        codes.append("ReviewNeedsRevision")
    output_texts = _surface_texts(analysis)
    hits = {hit.chunk_id: hit for hit in evidence.hits}
    active_user_facts = {
        review_user_fact_sha256(fact)
        for fact in case.facts
        if fact.status == "active" and fact.provenance_kind == "user"
    }
    version = next(
        (
            fact.value
            for fact in case.facts
            if fact.status == "active"
            and fact.provenance_kind == "user"
            and fact.name.casefold() == "streamlit_version"
        ),
        None,
    )
    for binding in attestation.claim_bindings:
        output = binding.output
        if output.surface_id not in output_texts:
            codes.append("UnknownReviewSurface")
        elif output_texts[output.surface_id][output.start : output.end] != output.text:
            codes.append("OutputSpanMismatch")
        if binding.judgment != "supported":
            codes.append("ClaimNeedsRevision")
        if binding.user_fact_sha256 is not None:
            if binding.user_fact_sha256 not in active_user_facts:
                codes.append("InactiveUserFactReference")
        if binding.source_quote is not None:
            quote = binding.source_quote
            hit = hits.get(quote.chunk_id)
            if hit is None:
                codes.append("UnknownReviewSource")
            else:
                if hit.excerpt[quote.start : quote.end] != quote.quote:
                    codes.append("SourceQuoteMismatch")
                if binding.applicability == "current" and (
                    version is None or version not in hit.applicable_versions
                ):
                    codes.append("CurrentVersionApplicabilityUnconfirmed")
    unique_codes = tuple(dict.fromkeys(codes))
    return ProposalReviewResult(
        status="needs_review" if unique_codes else "pass", codes=unique_codes
    )
