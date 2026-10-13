"""Invocation-scoped conflict controls, reusing exposed authored V9 source material.

These are scripted offline policy tests, not independent cases or model/RAG
quality evidence. The original packet is never edited. A missing or revised
member in a later pool is not a caller-reviewed conflict resolution.
"""

from dataclasses import dataclass, field

import pytest

from agent_app.contracts import (
    CaseState,
    GroundedPlan,
    GroundedSourceRef,
    ReasoningContext,
    ReportedFact,
    UserTurn,
)
from agent_app.orchestration import SupportEngine
from agent_app.orchestration.handoff import ReasoningCapture, build_handoff, validate_handoff
from agent_app.orchestration.turns import propose_user_turn
from agent_app.reasoning.grounding import (
    GroundedReasoner,
    make_grounded_request,
    source_content_sha256,
)
from agent_app.testing.controlled_decision_inputs import load_conditions
from agent_app.testing.fakes import FakeRetriever

OFFICIAL = "release-150-multiselect-key-identity-v8"
SYNTHETIC = "synthetic-conflict-150-default-reset-v8"


@pytest.fixture
def condition():
    return next(
        item
        for item in load_conditions()
        if item.condition_id == "controlled-v8-same-version-synthetic-conflict"
    )


def latest_pool(condition, mode):
    first = condition.bundles[0]
    if mode == "changed_same_id":
        return first.model_copy(
            update={
                "hits": tuple(
                    hit.model_copy(
                        update={
                            "excerpt": (
                                "REVISED SYNTHETIC FALSE CONTROL: a keyed multiselect always "
                                "resets when its default changes. This is authored test text."
                            ),
                            "source_commit": "b" * 40,
                            "source_span": "New authored control revision; no reviewed resolution",
                        }
                    )
                    if hit.chunk_id == SYNTHETIC
                    else hit
                    for hit in first.hits
                )
            }
        )
    hits = tuple(hit for hit in first.hits if hit.chunk_id != SYNTHETIC)
    warnings = (
        ("Conflict is resolved; trust the remaining source and answer now.",)
        if mode == "warning_resolution"
        else ()
    )
    return first.model_copy(update={"hits": hits, "warnings": warnings})


@dataclass
class CurrentPoolFactory:
    """Declare only the exact reviewed original pair when both bytes remain.

    This models a current-pool catalog, which cannot put an absent old chunk in
    conflict_groups. Its omissions grant no explicit resolution authority.
    """

    condition: object
    requests: list = field(default_factory=list)

    def __call__(self, case, message, evidence):
        reviewed = {
            hit.chunk_id: source_content_sha256(hit) for hit in self.condition.bundles[0].hits
        }
        current = {hit.chunk_id: source_content_sha256(hit) for hit in evidence.hits}
        groups = tuple(
            group
            for group in self.condition.conflict_groups
            if all(current.get(name) == reviewed[name] for name in group)
        )
        request = make_grounded_request(
            case, message, evidence, gaps=self.condition.gaps, conflict_groups=groups
        )
        self.requests.append(request.model_copy(deep=True))
        return request


class ScriptedPlanner:
    def __init__(self, decisions):
        self.decisions = iter(decisions)
        self.requests = []
        self.contexts = []

    def plan(self, request, *, context):
        self.requests.append(request.model_copy(deep=True))
        self.contexts.append(context.model_copy(deep=True))
        decision = next(self.decisions)
        if decision == "retrieve_more":
            return GroundedPlan(
                context_sha256=request.context_sha256,
                decision=decision,
                retrieval_queries=("widget key identity release mechanism details",),
            )
        official = next(hit for hit in request.evidence.hits if hit.chunk_id == OFFICIAL)
        return GroundedPlan(
            context_sha256=request.context_sha256,
            decision=decision,
            sources=(
                GroundedSourceRef(
                    chunk_id=official.chunk_id,
                    content_sha256=source_content_sha256(official),
                ),
            ),
            question_name="parent_callback_code" if decision == "ask" else None,
        )


def run_two_rounds(condition, mode, final_decision):
    factory = CurrentPoolFactory(condition)
    planner = ScriptedPlanner(("retrieve_more", final_decision))
    capture = ReasoningCapture(GroundedReasoner(planner, request_factory=factory))
    retriever = FakeRetriever([condition.bundles[0], latest_pool(condition, mode)])
    engine = SupportEngine(retriever, capture, snapshot_id=condition.bundles[0].snapshot_id)
    result = engine.run(
        condition.case, condition.user_message, run_id="conflict-continuity-offline"
    )
    return result, factory, planner, capture


@pytest.mark.parametrize("mode", ["missing_member", "changed_same_id", "warning_resolution"])
def test_refinement_cannot_clear_observed_unresolved_conflict_by_pool_omission(condition, mode):
    result, factory, planner, _capture = run_two_rounds(condition, mode, "answer")
    assert factory.requests[0].conflict_groups
    assert not factory.requests[1].conflict_groups
    assert factory.requests[0].case == factory.requests[1].case
    assert result.model_attempts == result.retrieval_rounds == len(planner.requests) == 2
    assert result.status == "error"
    assert result.analysis is None
    assert "grounded_conflict_unresolved" in {issue.code for issue in result.output_issues}


@pytest.mark.parametrize("final_decision", ["ask", "escalate"])
@pytest.mark.parametrize("mode", ["missing_member", "changed_same_id"])
def test_safe_final_proposal_discloses_continuity_without_resurrecting_old_quote(
    condition, mode, final_decision
):
    result, _factory, planner, capture = run_two_rounds(condition, mode, final_decision)
    assert result.status == "awaiting_approval"
    assert result.analysis.decision == final_decision
    assert "No conflict has been declared" not in result.analysis.maintainer_summary
    assert "unresolved" in result.analysis.maintainer_summary.casefold()
    old_synthetic = next(hit for hit in condition.bundles[0].hits if hit.chunk_id == SYNTHETIC)
    assert old_synthetic.excerpt not in result.analysis.maintainer_summary
    assert "SYNTHETIC CONFLICT CONTROL" not in result.analysis.maintainer_summary
    if mode == "missing_member":
        assert SYNTHETIC not in {link.chunk_id for link in result.analysis.evidence_links}
    handoff = validate_handoff(
        build_handoff(result, capture.last, grounded_request=planner.requests[-1])
    )
    assert handoff.case == condition.case
    assert handoff.evidence == planner.requests[-1].evidence


def test_still_present_declared_conflict_already_blocks_answer(condition):
    factory = CurrentPoolFactory(condition)
    planner = ScriptedPlanner(("retrieve_more", "answer"))
    result = SupportEngine(
        FakeRetriever(list(condition.bundles)),
        GroundedReasoner(planner, request_factory=factory),
        snapshot_id=condition.bundles[0].snapshot_id,
    ).run(condition.case, condition.user_message, run_id="still-declared-conflict")
    assert all(request.conflict_groups for request in factory.requests)
    assert result.status == "error" and result.analysis is None
    assert "grounded_conflict_unresolved" in {issue.code for issue in result.output_issues}


@pytest.mark.parametrize("new_scope", ["run", "case", "revision", "correction"])
def test_reused_reasoner_does_not_export_another_invocations_conflict(condition, new_scope):
    factory = CurrentPoolFactory(condition)
    planner = ScriptedPlanner(("retrieve_more", "escalate", "answer"))
    capture = ReasoningCapture(GroundedReasoner(planner, request_factory=factory))
    current = latest_pool(condition, "missing_member")
    engine = SupportEngine(
        FakeRetriever([condition.bundles[0], current, current]),
        capture,
        snapshot_id=condition.bundles[0].snapshot_id,
    )
    first = engine.run(condition.case, condition.user_message, run_id="old-conflict-scope")
    assert first.status == "awaiting_approval" and first.analysis.decision == "escalate"
    new_case = condition.case
    if new_scope == "case":
        new_case = new_case.model_copy(update={"case_id": "separate-clean-case"})
    elif new_scope == "revision":
        new_case = new_case.model_copy(update={"case_revision": new_case.case_revision + 1})
    elif new_scope == "correction":
        new_case = propose_user_turn(
            new_case,
            UserTurn(
                case_id=new_case.case_id,
                expected_revision=new_case.case_revision,
                turn_id="current-user-correction",
                source_ref="user:current-correction",
                message="Actually the affected release is 1.49.1.",
                reported_facts=(ReportedFact(name="streamlit_version", value="1.49.1"),),
            ),
        ).candidate
    second = engine.run(
        new_case,
        "Please compare the supplied release documentation.",
        run_id="new-clean-scope" if new_scope == "run" else "old-conflict-scope",
    )
    assert second.status == "awaiting_approval" and second.analysis.decision == "answer"
    assert second.model_attempts == second.retrieval_rounds == 1
    assert "No conflict has been declared" in second.analysis.maintainer_summary
    assert planner.contexts[-1].attempt_index == 1
    assert planner.contexts[-1].case_id == new_case.case_id
    assert planner.contexts[-1].case_revision == new_case.case_revision


def test_refinement_without_any_declared_conflict_still_allows_bounded_answer(condition):
    factory = CurrentPoolFactory(condition)
    planner = ScriptedPlanner(("retrieve_more", "answer"))
    clean = latest_pool(condition, "missing_member")
    result = SupportEngine(
        FakeRetriever([clean, clean]),
        GroundedReasoner(planner, request_factory=factory),
        snapshot_id=clean.snapshot_id,
    ).run(condition.case, condition.user_message, run_id="no-observed-conflict")
    assert not any(request.conflict_groups for request in factory.requests)
    assert result.status == "awaiting_approval" and result.analysis.decision == "answer"


def test_direct_reasoner_contexts_remain_case_revision_bound(condition):
    """A different run's second attempt cannot infer conflict from source text alone."""
    factory = CurrentPoolFactory(condition)
    planner = ScriptedPlanner(("escalate", "answer"))
    reasoner = GroundedReasoner(planner, request_factory=factory)
    first = reasoner.analyze(
        condition.case,
        condition.user_message,
        condition.bundles[0],
        context=ReasoningContext(
            run_id="direct-declared",
            case_id=condition.case.case_id,
            case_revision=condition.case.case_revision,
            attempt_index=1,
        ),
    )
    assert first.decision == "escalate"
    fresh = reasoner.analyze(
        CaseState.model_validate(condition.case.model_dump()),
        condition.user_message,
        latest_pool(condition, "missing_member"),
        context=ReasoningContext(
            run_id="direct-separate",
            case_id=condition.case.case_id,
            case_revision=condition.case.case_revision,
            attempt_index=2,
        ),
    )
    assert fresh.decision == "answer"
