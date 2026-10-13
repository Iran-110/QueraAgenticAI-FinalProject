"""Additional offline continuity boundaries, outside the frozen fourteen controls."""

from copy import deepcopy

import pytest
from test_conflict_continuity import CurrentPoolFactory, latest_pool

from agent_app.contracts import (
    GroundedGap,
    GroundedPlan,
    GroundedSourceRef,
    OutputFeedback,
    OutputIssue,
    ReasoningContext,
    RunLimits,
)
from agent_app.orchestration import SupportEngine
from agent_app.orchestration.handoff import (
    HandoffRejected,
    ReasoningCapture,
    build_handoff,
    validate_handoff,
)
from agent_app.orchestration.ports import ReasoningStopped
from agent_app.reasoning.grounding import GroundedReasoner, source_content_sha256
from agent_app.reasoning.output import InvalidAnalysis
from agent_app.testing.controlled_decision_inputs import load_conditions
from agent_app.testing.fakes import FakeRetriever

STATUS = "unresolved_prior_source_conflict"


@pytest.fixture
def condition():
    return next(
        item
        for item in load_conditions()
        if item.condition_id == "controlled-v8-same-version-synthetic-conflict"
    )


def context(case, run_id, attempt=1, *, repair=False):
    return ReasoningContext(
        run_id=run_id,
        case_id=case.case_id,
        case_revision=case.case_revision,
        attempt_index=attempt,
        remaining_model_attempts=2 - attempt,
        remaining_retrieval_rounds=1 if attempt == 1 else 0,
        can_refine=attempt == 1,
        output_feedback=(
            OutputFeedback(issues=(OutputIssue(code="invalid_grounded_plan"),)) if repair else None
        ),
    )


class Planner:
    def __init__(self, route="retrieve_more"):
        self.route = route
        self.requests = []
        self.contexts = []
        self.mutate_status = False
        self.after_plan = None

    def plan(self, request, *, context):
        self.requests.append(request.model_copy(deep=True))
        self.contexts.append(context.model_copy(deep=True))
        if self.route == "port_failure":
            raise ReasoningStopped("ProviderResponseInvalid")
        if self.route == "runtime_failure":
            raise RuntimeError("Scripted offline adapter failure")
        if self.route == "port_invalid_output":
            raise InvalidAnalysis((OutputIssue(code="invalid_grounded_plan"),))
        if self.route == "invalid_output":
            return "not a JSON plan"
        if self.route in {"bad_context", "bad_source"}:
            first = request.evidence.hits[0]
            return GroundedPlan(
                context_sha256="0" * 64 if self.route == "bad_context" else request.context_sha256,
                decision="escalate",
                sources=(
                    GroundedSourceRef(
                        chunk_id=first.chunk_id,
                        content_sha256="0" * 64
                        if self.route == "bad_source"
                        else source_content_sha256(first),
                    ),
                ),
            )
        if self.route == "retrieve_more":
            plan = GroundedPlan(
                context_sha256=request.context_sha256,
                decision="retrieve_more",
                retrieval_queries=("current widget key identity documentation",),
            )
        else:
            sources = tuple(
                GroundedSourceRef(chunk_id=hit.chunk_id, content_sha256=source_content_sha256(hit))
                for hit in request.evidence.hits[:1]
            )
            plan = GroundedPlan(
                context_sha256=request.context_sha256,
                decision="ask" if self.route == "ask_status" else self.route,
                sources=sources,
                question_name=(
                    STATUS
                    if self.route == "ask_status"
                    else "parent_callback_code"
                    if self.route == "ask"
                    else None
                ),
            )
        if self.mutate_status:
            object.__setattr__(
                request, "gaps", tuple(gap for gap in request.gaps if gap.name != STATUS)
            )
        if self.after_plan is not None:
            self.after_plan()
        return plan


def analyze(reasoner, condition, evidence, *, run_id, attempt=1, case=None, repair=False):
    current = case or condition.case
    return reasoner.analyze(
        current,
        condition.user_message,
        evidence,
        context=context(current, run_id, attempt, repair=repair),
    )


def seed(reasoner, planner, condition, run_id):
    planner.route = "retrieve_more"
    result = analyze(reasoner, condition, condition.bundles[0], run_id=run_id)
    assert result.decision == "retrieve_more"


@pytest.mark.parametrize("final_decision", ["ask", "escalate"])
def test_empty_latest_pool_keeps_status_without_old_quotes(condition, final_decision):
    factory = CurrentPoolFactory(condition)
    planner = Planner()
    capture = ReasoningCapture(GroundedReasoner(planner, request_factory=factory))
    empty = condition.bundles[0].model_copy(update={"hits": ()})

    class TwoDecisions:
        def analyze(self, *args, **kwargs):
            planner.route = "retrieve_more" if not planner.requests else final_decision
            return capture.analyze(*args, **kwargs)

    result = SupportEngine(
        FakeRetriever([condition.bundles[0], empty]),
        TwoDecisions(),
        snapshot_id=empty.snapshot_id,
    ).run(condition.case, condition.user_message, run_id="empty-latest-pool")
    assert result.status == "awaiting_approval" and result.analysis.decision == final_decision
    assert "unresolved" in result.analysis.maintainer_summary.casefold()
    assert "No conflict has been declared" not in result.analysis.maintainer_summary
    assert not result.analysis.evidence_links
    assert not planner.requests[-1].evidence.hits
    assert any(gap.name == STATUS and gap.kind == "source" for gap in planner.requests[-1].gaps)
    handoff = validate_handoff(
        build_handoff(result, capture.last, grounded_request=planner.requests[-1])
    )
    assert handoff.evidence.hits == ()
    assert "SYNTHETIC CONFLICT CONTROL" not in handoff.analysis.maintainer_summary


def test_same_round_invalid_output_repair_cannot_forget_declared_conflict(condition):
    current_factory = CurrentPoolFactory(condition)

    def disappearing_declaration(case, message, evidence):
        request = current_factory(case, message, evidence)
        if len(current_factory.requests) == 1:
            return request
        from agent_app.reasoning.grounding import make_grounded_request

        return make_grounded_request(case, message, evidence, gaps=request.gaps)

    planner = Planner("invalid_output")
    reasoner = GroundedReasoner(planner, request_factory=disappearing_declaration)
    with pytest.raises(InvalidAnalysis):
        analyze(reasoner, condition, condition.bundles[0], run_id="same-round-repair")
    planner.route = "answer"
    with pytest.raises(InvalidAnalysis) as error:
        analyze(
            reasoner,
            condition,
            condition.bundles[0],
            run_id="same-round-repair",
            attempt=2,
            repair=True,
        )
    assert {issue.code for issue in error.value.issues} == {"grounded_conflict_unresolved"}
    assert planner.requests[0].evidence == planner.requests[1].evidence
    assert planner.contexts[-1].output_feedback.issues[0].code == "invalid_grounded_plan"
    assert any(gap.name == STATUS for gap in planner.requests[-1].gaps)


@pytest.mark.parametrize("failure", ["runtime_failure", "port_invalid_output"])
def test_engine_retry_after_nonterminal_port_failure_keeps_known_conflict(condition, failure):
    factory = CurrentPoolFactory(condition)

    def disappearing_declaration(case, message, evidence):
        request = factory(case, message, evidence)
        if len(factory.requests) == 1:
            return request
        from agent_app.reasoning.grounding import make_grounded_request

        return make_grounded_request(case, message, evidence, gaps=request.gaps)

    class RepairPort(Planner):
        def plan(self, request, *, context):
            self.route = failure if not self.requests else "answer"
            return super().plan(request, context=context)

    planner = RepairPort()
    result = SupportEngine(
        FakeRetriever([condition.bundles[0]]),
        GroundedReasoner(planner, request_factory=disappearing_declaration),
        snapshot_id=condition.bundles[0].snapshot_id,
    ).run(condition.case, condition.user_message, run_id=f"repairable-{failure}")
    assert result.model_attempts == len(planner.requests) == 2
    assert result.retrieval_rounds == 1
    assert result.status == "error" and result.analysis is None
    assert "grounded_conflict_unresolved" in {issue.code for issue in result.output_issues}
    assert any(gap.name == STATUS for gap in planner.requests[-1].gaps)


@pytest.mark.parametrize("other_key", ["run", "case", "revision"])
def test_interleaved_clean_scope_does_not_erase_or_inherit_pending_conflict(condition, other_key):
    factory = CurrentPoolFactory(condition)
    planner = Planner()
    reasoner = GroundedReasoner(planner, request_factory=factory)
    seed(reasoner, planner, condition, "interleaved-declared")
    clean = latest_pool(condition, "missing_member")
    other_case = condition.case.model_copy(
        update=(
            {"case_id": "interleaved-other-case"}
            if other_key == "case"
            else {"case_revision": condition.case.case_revision + 1}
            if other_key == "revision"
            else {}
        )
    )
    planner.route = "answer"
    independent = analyze(
        reasoner,
        condition,
        clean,
        run_id="interleaved-other-run" if other_key == "run" else "interleaved-declared",
        case=other_case,
    )
    assert independent.decision == "answer"
    assert not any(gap.name == STATUS for gap in planner.requests[-1].gaps)
    with pytest.raises(InvalidAnalysis) as error:
        analyze(reasoner, condition, clean, run_id="interleaved-declared", attempt=2)
    assert {issue.code for issue in error.value.issues} == {"grounded_conflict_unresolved"}


def test_cache_overflow_fails_closed_without_evicting_unresolved_scopes(condition):
    planner = Planner()
    reasoner = GroundedReasoner(planner, request_factory=CurrentPoolFactory(condition))
    for index in range(32):
        seed(reasoner, planner, condition, f"pending-{index}")
    sends_before = len(planner.requests)
    with pytest.raises(InvalidAnalysis):
        seed(reasoner, planner, condition, "overflow-scope")
    assert len(planner.requests) == sends_before
    planner.route = "answer"
    clean = latest_pool(condition, "missing_member")
    for index in range(32):
        with pytest.raises(InvalidAnalysis) as error:
            analyze(reasoner, condition, clean, run_id=f"pending-{index}", attempt=2)
        assert {issue.code for issue in error.value.issues} == {"grounded_conflict_unresolved"}


@pytest.mark.parametrize("closing_route", ["escalate", "port_failure", "retrieve_more"])
def test_terminal_failure_or_last_attempt_releases_bounded_capacity(condition, closing_route):
    planner = Planner()
    reasoner = GroundedReasoner(planner, request_factory=CurrentPoolFactory(condition))
    for index in range(32):
        seed(reasoner, planner, condition, f"closing-{index}")
    planner.route = closing_route
    if closing_route == "port_failure":
        with pytest.raises(ReasoningStopped):
            analyze(
                reasoner,
                condition,
                latest_pool(condition, "missing_member"),
                run_id="closing-0",
                attempt=2,
            )
    else:
        result = analyze(
            reasoner,
            condition,
            latest_pool(condition, "missing_member"),
            run_id="closing-0",
            attempt=2,
        )
        assert result.decision == closing_route
    seed(reasoner, planner, condition, "new-after-closed-scope")
    assert planner.requests[-1].case == condition.case


def test_full_gap_catalog_fails_closed_instead_of_omitting_a_user_question(condition):
    factory = CurrentPoolFactory(condition)
    extras = tuple(
        GroundedGap(
            name=f"explicit_user_detail_{index}",
            kind="user",
            description="An explicitly registered application detail is absent.",
            necessity="The user owns this application detail; this is an authored control.",
            question=f"What is application detail {index}?",
        )
        for index in range(8 - len(condition.gaps))
    )

    def full_catalog(case, message, evidence):
        from agent_app.reasoning.grounding import make_grounded_request

        original = factory(case, message, evidence)
        return make_grounded_request(
            case,
            message,
            evidence,
            gaps=original.gaps + extras,
            conflict_groups=original.conflict_groups,
        )

    planner = Planner()
    reasoner = GroundedReasoner(planner, request_factory=full_catalog)
    seed(reasoner, planner, condition, "full-catalog")
    assert len(planner.requests[0].gaps) == 8
    before = deepcopy(planner.requests[0].gaps)
    planner.route = "answer"
    with pytest.raises(InvalidAnalysis):
        analyze(
            reasoner,
            condition,
            latest_pool(condition, "missing_member"),
            run_id="full-catalog",
            attempt=2,
        )
    assert len(planner.requests) == 1
    assert planner.requests[0].gaps == before
    assert set(gap.name for gap in extras) <= {gap.name for gap in before}


def test_continuity_status_is_source_only_and_cannot_be_a_user_question(condition):
    planner = Planner()
    reasoner = GroundedReasoner(planner, request_factory=CurrentPoolFactory(condition))
    seed(reasoner, planner, condition, "source-only-status")
    planner.route = "ask_status"
    with pytest.raises(InvalidAnalysis) as error:
        analyze(
            reasoner,
            condition,
            latest_pool(condition, "missing_member"),
            run_id="source-only-status",
            attempt=2,
        )
    assert {issue.code for issue in error.value.issues} == {"grounded_question_invalid"}
    status = next(gap for gap in planner.requests[-1].gaps if gap.name == STATUS)
    assert status.kind == "source" and status.question is None
    assert "SYNTHETIC CONFLICT CONTROL" not in status.description


def test_planner_cannot_clear_private_continuity_by_mutating_emitted_request(condition):
    planner = Planner()
    reasoner = GroundedReasoner(planner, request_factory=CurrentPoolFactory(condition))
    seed(reasoner, planner, condition, "mutated-status")
    planner.route, planner.mutate_status = "answer", True
    with pytest.raises(InvalidAnalysis) as error:
        analyze(
            reasoner,
            condition,
            latest_pool(condition, "missing_member"),
            run_id="mutated-status",
            attempt=2,
        )
    assert {issue.code for issue in error.value.issues} == {"grounded_conflict_unresolved"}
    assert any(gap.name == STATUS for gap in planner.requests[-1].gaps)


@pytest.mark.parametrize(
    ("bad_route", "terminal_code"),
    [("bad_context", "GroundedContextMismatch"), ("bad_source", "GroundedSourceMismatch")],
)
def test_terminal_binding_failures_do_not_leave_completed_invocations_in_cache(
    condition, bad_route, terminal_code
):
    planner = Planner(bad_route)
    reasoner = GroundedReasoner(planner, request_factory=CurrentPoolFactory(condition))

    def run(run_id):
        return SupportEngine(
            FakeRetriever([condition.bundles[0]]),
            reasoner,
            snapshot_id=condition.bundles[0].snapshot_id,
        ).run(condition.case, condition.user_message, run_id=run_id)

    for index in range(32):
        failed = run(f"binding-failed-{index}")
        assert failed.status == "error" and failed.error_code == terminal_code
        assert failed.model_attempts == 1
    assert len(planner.requests) == 32
    planner.route = "escalate"
    fresh = run("fresh-after-terminal-bindings")
    assert fresh.status == "awaiting_approval" and fresh.analysis.decision == "escalate"
    assert fresh.model_attempts == fresh.retrieval_rounds == 1
    assert len(planner.requests) == 33


@pytest.mark.parametrize(
    ("limits", "stop_code"),
    [
        (RunLimits(max_retrieval_rounds=1), "RetrievalRoundLimitExceeded"),
        (RunLimits(max_steps=3), "StepLimitExceeded"),
    ],
)
def test_refinement_capacity_stop_cannot_leave_finished_invocations_cached(
    condition, limits, stop_code
):
    planner = Planner()
    reasoner = GroundedReasoner(planner, request_factory=CurrentPoolFactory(condition))
    for index in range(32):
        stopped = SupportEngine(
            FakeRetriever([condition.bundles[0]]),
            reasoner,
            snapshot_id=condition.bundles[0].snapshot_id,
            limits=limits,
        ).run(condition.case, condition.user_message, run_id=f"capacity-stopped-{index}")
        assert stopped.status == "budget_stopped" and stopped.error_code == stop_code
        assert stopped.model_attempts == stopped.retrieval_rounds == 1
        assert not planner.contexts[-1].can_refine
    assert len(planner.requests) == 32
    planner.route = "escalate"
    fresh = SupportEngine(
        FakeRetriever([condition.bundles[0]]),
        reasoner,
        snapshot_id=condition.bundles[0].snapshot_id,
    ).run(condition.case, condition.user_message, run_id="fresh-after-capacity-stops")
    assert fresh.status == "awaiting_approval" and fresh.analysis.decision == "escalate"
    assert len(planner.requests) == 33


@pytest.mark.parametrize("stop", ["retrieval_failure", "repeated_query", "stale", "repair_step"])
def test_engine_termination_after_first_port_releases_scope_through_capture(condition, stop):
    planner = Planner("invalid_output" if stop == "repair_step" else "retrieve_more")
    grounded = GroundedReasoner(planner, request_factory=CurrentPoolFactory(condition))
    capture = ReasoningCapture(grounded)
    current = [condition.case]

    class RetrievalFailure:
        def __init__(self):
            self.calls = 0

        def search(self, request):
            self.calls += 1
            if self.calls > 1:
                raise RuntimeError("PRIVATE_RETRIEVAL_FAILURE")
            return condition.bundles[0]

    expected = {
        "retrieval_failure": ("error", "RetrievalUnavailable"),
        "repeated_query": ("error", "RepeatedQuery"),
        "stale": ("stale", "StaleRevision"),
        "repair_step": ("budget_stopped", "StepLimitExceeded"),
    }[stop]
    for index in range(32):
        current[0] = condition.case
        if stop == "stale":
            planner.after_plan = lambda: current.__setitem__(
                0,
                condition.case.model_copy(
                    update={"case_revision": condition.case.case_revision + 1}
                ),
            )
        kwargs = {}
        if stop == "repeated_query":
            kwargs["initial_query"] = "current widget key identity documentation"
        retriever = (
            RetrievalFailure()
            if stop == "retrieval_failure"
            else FakeRetriever([condition.bundles[0]])
        )
        engine = SupportEngine(
            retriever,
            capture,
            snapshot_id=condition.bundles[0].snapshot_id,
            current_case=(lambda _case_id: current[0]) if stop == "stale" else None,
            limits=RunLimits(max_steps=3) if stop == "repair_step" else RunLimits(),
        )
        result = engine.run(
            condition.case, condition.user_message, run_id=f"outer-stopped-{index}", **kwargs
        )
        assert (result.status, result.error_code) == expected
        assert result.model_attempts == 1
        assert capture.last is not None and capture.last.case == condition.case
        assert "PRIVATE_RETRIEVAL_FAILURE" not in result.model_dump_json()
    assert len(planner.requests) == 32
    planner.route, planner.after_plan = "escalate", None
    fresh = SupportEngine(
        FakeRetriever([condition.bundles[0]]),
        capture,
        snapshot_id=condition.bundles[0].snapshot_id,
    ).run(condition.case, condition.user_message, run_id="fresh-after-outer-stops")
    assert fresh.status == "awaiting_approval" and fresh.analysis.decision == "escalate"
    assert len(planner.requests) == 33
    # Releasing the bookkeeping scope must preserve the final captured input
    # and actual emitted request required for whole-proposal review.
    handoff = validate_handoff(
        build_handoff(fresh, capture.last, grounded_request=planner.requests[-1])
    )
    assert handoff.case == condition.case
    assert handoff.grounded_request == planner.requests[-1]


@pytest.mark.parametrize("wrapped", [False, True])
def test_cleanup_failure_is_sanitized_and_cannot_expose_an_approvable_proposal(condition, wrapped):
    planner = Planner("escalate")

    class FailedCleanup(GroundedReasoner):
        def _release_core_scope(self, run_id, case_id, revision):
            raise RuntimeError("PRIVATE_CLEANUP_FAILURE")

    grounded = FailedCleanup(planner, request_factory=CurrentPoolFactory(condition))
    capture = ReasoningCapture(grounded)
    result = SupportEngine(
        FakeRetriever([condition.bundles[0]]),
        capture if wrapped else grounded,
        snapshot_id=condition.bundles[0].snapshot_id,
    ).run(condition.case, condition.user_message, run_id="failed-scope-cleanup")
    assert result.status == "error" and result.error_code == "ReasoningUnavailable"
    assert result.analysis is None
    assert result.model_attempts == result.retrieval_rounds == len(planner.requests) == 1
    assert "PRIVATE_CLEANUP_FAILURE" not in result.model_dump_json()
    if wrapped:
        assert capture.last is not None
        with pytest.raises(HandoffRejected) as error:
            build_handoff(result, capture.last, grounded_request=planner.requests[-1])
        assert error.value.code == "FinalProposalRequired"
