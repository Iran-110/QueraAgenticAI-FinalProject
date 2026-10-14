"""Reconstruct the explicitly registered renderer; never rescore older receipts."""

from unittest.mock import patch

from agent_app.reasoning.grounding import render_grounded_plan
from agent_app.testing import stability_review


def summarize_quality(receipt):
    if receipt.get("renderer_source_gap_investigation") is not True:
        raise stability_review.StabilityReviewRejected()

    def registered_render(request, raw, *, source_gap_handoff=False):
        return render_grounded_plan(
            request,
            raw,
            source_gap_handoff=source_gap_handoff,
            source_gap_investigation=source_gap_handoff,
        )

    with patch.object(stability_review, "render_grounded_plan", registered_render):
        summary = stability_review.summarize_receipt(receipt)
    summary["renderer_mode"] = "explicit_common_source_gap_handoff_and_investigation_true"
    summary["comparison_scope"] = (
        "Fixed exposed development evidence; model route and semantic support are separate."
    )
    return summary
