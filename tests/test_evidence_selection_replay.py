"""Actual retained failures, not a synthetic route/quality success score."""

import json
from pathlib import Path

import httpx
import pytest

from agent_app.contracts import (
    CaseState,
    EvidenceBundle,
    EvidenceHit,
    GroundedRequest,
    ReasoningContext,
)
from agent_app.llm.claims import MetisClaimPlanner
from agent_app.llm.config import MetisConfig
from agent_app.orchestration.ports import ReasoningStopped
from agent_app.reasoning.claim_plan import build_claim_request, render_claim_plan
from agent_app.reasoning.evidence_selection import suggest_evidence_units
from agent_app.reasoning.grounding import GroundingRejected, make_grounded_request
from agent_app.testing.evidence_selection_replay import (
    gateway_input_bytes,
    project_selection,
    replay,
)

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "experiments/core_claim_boundary_v1/model-receipt-v1.json"


def test_quote_heavy_input_matches_actual_gateway_stop_before_reserve_or_transport():
    case = CaseState(case_id="quote-guard")
    evidence = EvidenceBundle(
        snapshot_id="quote-guard",
        hits=(
            EvidenceHit(
                source_id="neutral",
                chunk_id="neutral-chunk",
                source_type="doc",
                source_url="https://example.org/neutral",
                excerpt="# A source\n\n" + '"' * 7000,
            ),
        ),
    )
    request = build_claim_request(
        make_grounded_request(case, "Current report.", evidence), block_mode="sections"
    )
    context = ReasoningContext(
        run_id="offline-quote-guard", case_id=case.case_id, case_revision=0, attempt_index=1
    )
    from agent_app.reasoning.claim_plan import build_claim_messages

    messages = build_claim_messages(request, context)
    assert sum(len(m["content"].encode()) for m in messages) + 1024 <= 32768
    assert gateway_input_bytes(messages) > 32768

    class NoReserve:
        def reserve(self, **_):
            pytest.fail("Oversized input reached reservation")

    def no_transport(_):
        pytest.fail("Oversized input reached transport")

    config = MetisConfig(
        api_key="synthetic-offline-key",
        model="gpt-4o-mini",
        live_enabled=True,
        input_token_reserve=32768,
        max_output_tokens=2048,
    )
    with MetisClaimPlanner(
        config, NoReserve(), transport=httpx.MockTransport(no_transport)
    ) as planner:
        with pytest.raises(ReasoningStopped, match="ContextLimitExceeded"):
            planner.plan(request, context=context)


def observed_enum():
    # This post-hoc regression locator belongs to tests, never runtime selection.
    attempt = json.loads(RECEIPT.read_bytes())["batches"][2]["attempts"][3]
    old = build_claim_request(GroundedRequest.model_validate(attempt["request"]))
    complete = build_claim_request(old.grounded, block_mode="sections")
    return attempt, old, complete


def test_observed_heading_selection_projects_to_complete_body_and_edit_reload_caveat():
    attempt, old, complete = observed_enum()
    prior = render_claim_plan(old, attempt["claim_plan"])
    projected = project_selection(old, complete, attempt["claim_plan"])
    after = render_claim_plan(complete, projected)
    assert "Pattern 1: Define your class in a separate module" in prior.user_draft
    assert "Streamlit only reloads code" not in prior.user_draft
    assert "move class definitions into their own module file" in after.user_draft
    assert "Streamlit only reloads code" in after.user_draft
    assert "new session or restart" in after.user_draft
    assert "Applicability to this environment is unconfirmed" in after.user_draft
    assert prior.decision == after.decision == "answer"
    assert projected.context_sha256 != attempt["claim_plan"]["context_sha256"]
    assert len(after.user_draft) > len(prior.user_draft)  # Completeness can cost verbosity.
    assert after.facts_delta == prior.facts_delta == ()
    assert after.checks_suggested == prior.checks_suggested == ()


def test_observed_source_gap_rejected_plan_is_not_repaired_by_rebinding():
    receipt = json.loads(RECEIPT.read_bytes())
    attempt = receipt["batches"][3]["attempts"][0]
    old = build_claim_request(GroundedRequest.model_validate(attempt["request"]))
    complete = build_claim_request(old.grounded, block_mode="sections")
    with pytest.raises(GroundingRejected, match="grounded_source_mismatch"):
        project_selection(old, complete, attempt["claim_plan"])


def test_original_paid_plan_is_still_invalid_under_new_section_context():
    attempt, _old, complete = observed_enum()
    with pytest.raises(GroundingRejected, match="grounded_context_mismatch"):
        render_claim_plan(complete, attempt["claim_plan"])


def test_projection_rejects_different_current_input_instead_of_using_old_source_positions():
    attempt, old, _complete = observed_enum()
    changed = make_grounded_request(
        old.grounded.case,
        "A corrected current report.",
        old.grounded.evidence,
        gaps=old.grounded.gaps,
        conflict_groups=old.grounded.conflict_groups,
    )
    complete = build_claim_request(changed, block_mode="sections")
    with pytest.raises(GroundingRejected, match="grounded_context_mismatch"):
        project_selection(old, complete, attempt["claim_plan"])


def test_independent_generic_shortlist_can_keep_both_complementary_chunks_of_one_source():
    _attempt, _old, complete = observed_enum()
    shortlist = suggest_evidence_units(complete)
    # Oracle assertions AFTER suggestion; helpers never see these expected IDs.
    assert {source for source, _ in shortlist.passages} == {1, 2}
    assert shortlist.passage_utf8_bytes <= 6000
    assert shortlist.semantic_support is None and shortlist.human_review_required
    assert (
        complete.grounded.evidence.hits[1].source_id == complete.grounded.evidence.hits[2].source_id
    )


def test_full_replay_preserves_every_retained_rejected_and_unavailable_candidate():
    result = replay()
    assert result["all_checks_passed"]
    assert result["checks_passed"] == result["checks_total"]
    assert result["actual_API_calls"] == 0
    assert result["ledger_or_native_index_access"] is False
    assert len(result["snapshot_preflights"]) == 16
    assert result["retained_claim_plans"] == 10
    assert result["unavailable_raw_claim_attempts_not_reconstructed"] == 21
    assert result["original_finals"] == 7
    assert result["original_binding_rejections"] == 3
    assert result["authored_projection_successes"] == 7
    assert result["human_usefulness"] is None
    assert result["model_selection_improvement_claim"] is False
    assert result["semantic_relevance_or_entailment_proven"] is False
    enum = result["retained_claim_candidates"][0]
    assert len(enum["posthoc_observed_span_controls"]) == 2
    assert all(
        not check["original_covers_whole_span"]
        and check["projection_covers_whole_span"]
        and check["independent_shortlist_covers_whole_span"]
        for check in enum["posthoc_observed_span_controls"]
    )
    assert any(row.get("ask_draft_unchanged") for row in result["retained_claim_candidates"])
