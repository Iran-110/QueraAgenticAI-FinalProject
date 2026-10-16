"""Authored annotation controls, never automatic claim or native quality judgments."""

import pytest
from test_evaluation_semantic_review import make_handoff, output, review

from agent_app.contracts import AnalysisResult, EvidenceLink, ReviewClaimBinding, ReviewSourceQuote
from agent_app.evaluation.semantic_review import SemanticReviewRejected, score_review

CLAIM = "The widget accepts image files."


def _proposal(*, disclaimer):
    return make_handoff(
        analysis=AnalysisResult(
            decision="answer",
            user_draft=("Not found in the supplied sources: " if disclaimer else "") + CLAIM,
            maintainer_summary="Synthetic review control.",
            rationale="The annotations are authored test inputs.",
            evidence_links=(EvidenceLink(claim=CLAIM, chunk_id="doc-current"),),
        )
    )


def _unsupported(handoff, *, quote):
    hit = handoff.evidence.hits[0]
    return ReviewClaimBinding(
        output=output(handoff, selected=CLAIM),
        judgment="unsupported",  # Authored label; the scorer discovers no semantics.
        applicability="current",
        source_quote=ReviewSourceQuote(
            chunk_id=hit.chunk_id, start=0, end=len(hit.excerpt), quote=hit.excerpt
        )
        if quote
        else None,
    )


@pytest.mark.parametrize("disclaimer", [False, True])
@pytest.mark.parametrize("quote", [False, True])
def test_present_cited_source_and_disclaimer_do_not_override_unsupported_annotation(
    disclaimer, quote
):
    handoff = _proposal(disclaimer=disclaimer)
    record = review(
        handoff,
        claim_bindings=(_unsupported(handoff, quote=quote),),
        reviewer_kind="assistant",
        decision_judgment="acceptable",
        usefulness_score=2,
    )

    result = score_review(handoff, record, scope=record.scope)

    assert handoff.analysis.evidence_links[0].chunk_id == handoff.evidence.hits[0].chunk_id
    assert result.claims.total == result.claims.unsupported == 1
    assert result.support_gate == 0 and result.support_status == "fail"
    assert result.decision_judgment == "acceptable" and result.usefulness_score == 2
    assert result.quality_claim is result.authorizes_action is False


@pytest.mark.parametrize("rebind_handoff", [False, True])
def test_same_chunk_id_cannot_reuse_review_of_different_consumed_source_bytes(rebind_handoff):
    old = _proposal(disclaimer=True)
    record = review(old, claim_bindings=(_unsupported(old, quote=True),), reviewer_kind="assistant")
    hit = old.evidence.hits[0].model_copy(update={"excerpt": "A different supplied passage."})
    current = make_handoff(
        analysis=old.analysis, evidence=old.evidence.model_copy(update={"hits": (hit,)})
    )
    assert current.evidence.hits[0].chunk_id == old.evidence.hits[0].chunk_id
    assert current.handoff_sha256 != old.handoff_sha256
    if rebind_handoff:
        record = record.model_copy(update={"handoff_sha256": current.handoff_sha256})

    with pytest.raises(SemanticReviewRejected) as caught:
        score_review(current, record, scope=record.scope)

    assert caught.value.code == (
        "SourceQuoteMismatch" if rebind_handoff else "ReviewHandoffMismatch"
    )
