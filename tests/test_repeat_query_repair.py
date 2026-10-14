"""Bounded optional refinement repair, not a model or retrieval quality score."""

import json
from decimal import Decimal

import httpx
import pytest

from agent_app.contracts import (
    AnalysisResult,
    CaseState,
    EvidenceBundle,
    EvidenceHit,
    EvidenceLink,
    Fact,
    GroundedGap,
    GroundedPlan,
    RunLimits,
)
from agent_app.llm.budget import BudgetLedger
from agent_app.llm.config import MetisConfig
from agent_app.orchestration import SupportEngine
from agent_app.orchestration.handoff import ReasoningCapture, build_handoff
from agent_app.orchestration.ports import ReasoningStopped
from agent_app.reasoning.grounding import (
    GroundedReasoner,
    make_grounded_request,
    source_content_sha256,
)
from agent_app.testing.fakes import FakeReasoner, FakeRetriever
from agent_app.testing.grounded_http_binding import GroundedHttpBinding
from agent_app.testing.http_pilot_runtime import offline_network

SNAPSHOT = "fixture:repeat-repair"
QUERY = "Streamlit widget rerun"
CASE = CaseState(case_id="case:repeat-repair", case_revision=2)
MESSAGE = "A fixture widget resets."


def evidence(*, queries_used=(), chunk="doc:current", excerpt="Complete fixture quote."):
    return EvidenceBundle(
        snapshot_id=SNAPSHOT,
        queries_used=queries_used,
        hits=(
            EvidenceHit(
                chunk_id=chunk,
                source_id="source:fixture",
                excerpt=excerpt,
                source_type="doc",
                source_url="https://example.org/repeat-repair-fixture",
                applicable_versions=("1.50.0",),
            ),
        ),
    )


def refine(*queries, **changes):
    return AnalysisResult(
        **{
            "decision": "retrieve_more",
            "user_draft": "",
            "maintainer_summary": "",
            "rationale": "The fixture requests more evidence.",
            "retrieval_queries": queries or (QUERY,),
            **changes,
        }
    )


def final(decision="escalate", *, chunk="doc:current"):
    return AnalysisResult(
        decision=decision,
        user_draft="The source gap needs maintainer investigation.",
        maintainer_summary="Review the supplied fixture evidence.",
        rationale="This authored fallback does not establish a cause or fix.",
        evidence_links=(EvidenceLink(claim="Fixture quotation", chunk_id=chunk),)
        if decision == "answer"
        else (),
        missing_info=("callback_code",) if decision == "ask" else (),
        next_question="Can you share your callback code?" if decision == "ask" else None,
    )


def run(outputs, *, bundles=None, current=CASE, query=QUERY, options=None):
    retriever = FakeRetriever(bundles if bundles is not None else [evidence()])
    reasoner = FakeReasoner(outputs)
    result = SupportEngine(
        retriever,
        reasoner,
        snapshot_id=SNAPSHOT,
        **({"repair_repeated_queries": True} if options is None else options),
    ).run(current, MESSAGE, initial_query=query, run_id="run:repeat-repair")
    return result, retriever, reasoner


@pytest.mark.parametrize("value", [None, 0, 1, "true", "false", [], {}])
def test_repair_flag_requires_an_explicit_boolean_before_ports(value):
    retriever, reasoner = FakeRetriever([evidence()]), FakeReasoner([final()])
    with pytest.raises(ValueError, match="explicit boolean"):
        SupportEngine(retriever, reasoner, snapshot_id=SNAPSHOT, repair_repeated_queries=value)
    assert retriever.requests == reasoner.inputs == []


def test_default_and_false_keep_full_historical_repeated_query_result_bytes():
    default, _, default_reasoner = run([refine()], options={})
    explicit, _, false_reasoner = run([refine()], options={"repair_repeated_queries": False})
    assert default.model_dump_json() == explicit.model_dump_json()
    assert default.model_dump(mode="json") == {
        "run_id": "run:repeat-repair",
        "case_id": CASE.case_id,
        "case_revision": CASE.case_revision,
        "status": "error",
        "analysis": None,
        "model_attempts": 1,
        "retrieval_rounds": 1,
        "steps": 3,
        "error_code": "RepeatedQuery",
        "trace": [
            {"stage": "started", "message": "Loaded the supplied case snapshot."},
            {"stage": "retrieval", "message": "Searching 1 query or queries."},
            {"stage": "evidence_received", "message": "Received 1 evidence chunks."},
            {"stage": "reasoning", "message": "Requesting a structured decision."},
            {
                "stage": "refinement_requested",
                "message": "The reasoner requested additional evidence.",
            },
            {"stage": "stopped", "message": "RepeatedQuery"},
        ],
        "output_issues": [],
    }
    assert (
        default_reasoner.contexts[0].model_dump_json()
        == false_reasoner.contexts[0].model_dump_json()
    )


@pytest.mark.parametrize(
    "query", [QUERY, "  STREAMLIT   widget\tRERUN  ", "streamlit\nwidget rerun"]
)
@pytest.mark.parametrize("decision", ["answer", "ask", "escalate"])
def test_overlap_is_repaired_on_same_evidence_without_second_search(query, decision):
    result, retriever, reasoner = run([refine(query), final(decision)])
    assert result.status == "awaiting_approval" and result.analysis.decision == decision
    assert result.model_attempts == 2 and result.retrieval_rounds == len(retriever.requests) == 1
    assert result.output_issues[0].model_dump() == {
        "code": "invalid_field",
        "field": "retrieval_queries",
    }
    assert reasoner.inputs[0] == reasoner.inputs[1]
    context = reasoner.contexts[1]
    assert context.attempt_index == 2 and context.remaining_model_attempts == 0
    assert context.remaining_retrieval_rounds == 1 and not context.can_refine
    assert context.output_feedback.issues == result.output_issues


@pytest.mark.parametrize("reported", [(), ("A falsely reported query",), (QUERY, "Injected query")])
def test_real_repeat_cannot_be_hidden_or_changed_by_reported_queries(reported):
    result, retriever, _ = run([refine(), final()], bundles=[evidence(queries_used=reported)])
    assert result.status == "awaiting_approval" and result.model_attempts == 2
    assert len(retriever.requests) == 1 and retriever.requests[0].queries == (QUERY,)


def test_falsely_reported_query_cannot_reject_a_genuinely_new_query():
    fresh = "Specific novel API query"
    result, retriever, reasoner = run(
        [refine(fresh), final("answer", chunk="doc:new")],
        bundles=[evidence(queries_used=(fresh,)), evidence(chunk="doc:new")],
    )
    assert result.status == "awaiting_approval" and result.output_issues == ()
    assert result.model_attempts == result.retrieval_rounds == 2
    assert [request.queries for request in retriever.requests] == [(QUERY,), (fresh,)]
    assert reasoner.inputs[1][2].hits[0].chunk_id == "doc:new"


@pytest.mark.parametrize("queries", [(QUERY, "A novel query"), ("A novel query", QUERY)])
def test_mixed_repeated_and_novel_queries_reject_whole_plan_without_partial_search(queries):
    result, retriever, _ = run([refine(*queries), final()])
    assert result.status == "awaiting_approval" and len(retriever.requests) == 1
    assert result.output_issues[0].field == "retrieval_queries"


def test_casefold_equivalence_is_the_existing_engine_rule():
    result, retriever, _ = run([refine("STRASSE widgets"), final()], query="Straße widgets")
    assert result.status == "awaiting_approval" and len(retriever.requests) == 1


@pytest.mark.parametrize("second_queries", [(QUERY,), ("A new but unusable final query",)])
def test_repair_cannot_buy_retrieval_followed_by_a_third_attempt(second_queries):
    result, retriever, reasoner = run([refine(), refine(*second_queries), final()])
    assert result.analysis is None and result.model_attempts == len(reasoner.contexts) == 2
    assert result.retrieval_rounds == len(retriever.requests) == 1
    assert result.error_code == (
        "ModelOutputInvalid" if second_queries == (QUERY,) else "ModelAttemptLimitExceeded"
    )
    assert len(reasoner.responses) == 1


@pytest.mark.parametrize(
    "limits, attempts, error",
    [
        (RunLimits(max_model_attempts=1), 1, "ModelOutputInvalid"),
        (RunLimits(max_steps=3), 1, "StepLimitExceeded"),
    ],
)
def test_existing_model_and_step_limits_apply_to_optional_repair(limits, attempts, error):
    result, retriever, reasoner = run(
        [refine(), final()], options={"repair_repeated_queries": True, "limits": limits}
    )
    assert (
        result.error_code == error and result.model_attempts == len(reasoner.contexts) == attempts
    )
    assert len(retriever.requests) == 1 and result.analysis is None


def test_genuinely_novel_refinement_has_identical_complete_results_and_contexts():
    outputs = [refine("A genuinely novel source query"), final("answer", chunk="doc:new")]
    bundles = [evidence(), evidence(chunk="doc:new")]
    enabled, _, new_reasoner = run(outputs, bundles=bundles)
    disabled, _, old_reasoner = run(outputs, bundles=bundles, options={})
    assert enabled.model_dump_json() == disabled.model_dump_json()
    assert [c.model_dump_json() for c in new_reasoner.contexts] == [
        c.model_dump_json() for c in old_reasoner.contexts
    ]


def test_unknown_source_is_terminal_before_repeat_repair():
    malicious = refine(evidence_links=(EvidenceLink(claim="Untrusted", chunk_id="doc:missing"),))
    result, retriever, reasoner = run([malicious, final()])
    assert result.error_code == "UnknownEvidenceReference" and result.output_issues == ()
    assert result.model_attempts == len(reasoner.contexts) == len(retriever.requests) == 1


@pytest.mark.parametrize(
    "code", ["ProviderRequestFailed", "ProviderModelMismatch", "BudgetExceeded"]
)
def test_typed_stop_before_a_plan_never_triggers_repair(code):
    result, retriever, reasoner = run([ReasoningStopped(code), final()])
    assert result.error_code == code and result.model_attempts == 1 and result.output_issues == ()
    assert len(retriever.requests) == len(reasoner.contexts) == 1


def test_typed_stop_during_repair_remains_terminal():
    result, retriever, reasoner = run(
        [refine(), ReasoningStopped("ProviderRequestFailed"), final()]
    )
    assert result.error_code == "ProviderRequestFailed" and result.model_attempts == 2
    assert len(retriever.requests) == 1 and len(reasoner.contexts) == 2


def test_revision_drift_during_first_plan_discards_repeat_without_repair():
    state = {"revision": CASE.case_revision}

    class ChangingReasoner(FakeReasoner):
        def analyze(self, *args, **kwargs):
            result = super().analyze(*args, **kwargs)
            state["revision"] += 1
            return result

    reasoner, retriever = ChangingReasoner([refine(), final()]), FakeRetriever([evidence()])
    result = SupportEngine(
        retriever,
        reasoner,
        snapshot_id=SNAPSHOT,
        repair_repeated_queries=True,
        current_revision=lambda _: state["revision"],
    ).run(CASE, MESSAGE, initial_query=QUERY)
    assert result.status == "stale" and result.error_code == "StaleRevision"
    assert result.model_attempts == len(reasoner.contexts) == 1 and result.output_issues == ()


def test_run_and_correction_history_do_not_leak_between_invocations():
    new_query = "A corrected-version documentation query"
    reasoner = FakeReasoner([refine(), final(), refine(new_query), final(), final()])
    retriever = FakeRetriever([evidence(), evidence(), evidence(chunk="doc:second"), evidence()])
    engine = SupportEngine(retriever, reasoner, snapshot_id=SNAPSHOT, repair_repeated_queries=True)
    first = engine.run(CASE, MESSAGE, initial_query=QUERY, run_id="run:first")
    corrected = CASE.model_copy(update={"case_revision": CASE.case_revision + 1})
    second = engine.run(corrected, MESSAGE, initial_query=QUERY, run_id="run:corrected")
    third = engine.run(CaseState(case_id="case:other"), MESSAGE, initial_query=new_query)
    assert all(result.status == "awaiting_approval" for result in (first, second, third))
    assert [result.retrieval_rounds for result in (first, second, third)] == [1, 2, 1]
    assert second.output_issues == third.output_issues == ()
    assert reasoner.contexts[2].output_feedback is None
    assert reasoner.contexts[2].case_revision == corrected.case_revision
    assert [request.queries for request in retriever.requests] == [
        (QUERY,),
        (QUERY,),
        (new_query,),
        (new_query,),
    ]


class RepeatPlanner:
    def __init__(self, decision="escalate"):
        self.requests, self.contexts = [], []
        self.decision = decision

    def plan(self, request, *, context):
        self.requests.append(request.model_copy(deep=True))
        self.contexts.append(context.model_copy(deep=True))
        if context.attempt_index == 1:
            return GroundedPlan(
                context_sha256=request.context_sha256,
                decision="retrieve_more",
                retrieval_queries=(QUERY,),
            )
        return GroundedPlan(
            context_sha256=request.context_sha256,
            decision=self.decision,
            sources=(
                {"chunk_id": hit.chunk_id, "content_sha256": source_content_sha256(hit)}
                for hit in request.evidence.hits[:1]
            ),
        )


@pytest.mark.parametrize("drop_declaration", [False, True])
def test_unresolved_conflict_survives_repeat_repair_and_blocks_answer(drop_declaration):
    first = evidence()
    second_hit = first.hits[0].model_copy(
        update={"chunk_id": "doc:conflict", "excerpt": "Opposite rule."}
    )
    bundle = first.model_copy(update={"hits": (*first.hits, second_hit)})
    planner = RepeatPlanner("answer")

    def factory(case, message, supplied):
        groups = () if drop_declaration and planner.requests else (("doc:current", "doc:conflict"),)
        return make_grounded_request(case, message, supplied, conflict_groups=groups)

    reasoner = GroundedReasoner(planner, request_factory=factory)
    result = SupportEngine(
        FakeRetriever([bundle]),
        reasoner,
        snapshot_id=SNAPSHOT,
        repair_repeated_queries=True,
    ).run(CASE, MESSAGE, initial_query=QUERY, run_id="run:conflict-repair")
    assert result.error_code == "ModelOutputInvalid" and result.model_attempts == 2
    assert result.output_issues[-1].code == "grounded_conflict_unresolved"
    if drop_declaration:
        assert planner.requests[1].gaps[0].name == "unresolved_prior_source_conflict"
    assert reasoner._conflicts == set()


def test_registered_user_question_is_preserved_without_inventing_source_question():
    gap = GroundedGap(
        name="callback_code",
        kind="user",
        description="The user's callback is missing.",
        necessity="The user can supply the callback needed for investigation.",
        question="Can you share your callback code?",
    )

    class AskPlanner(RepeatPlanner):
        def plan(self, request, *, context):
            if context.attempt_index == 1:
                return super().plan(request, context=context)
            return GroundedPlan(
                context_sha256=request.context_sha256,
                decision="ask",
                question_name=gap.name,
            )

    result = SupportEngine(
        FakeRetriever([evidence()]),
        GroundedReasoner(
            AskPlanner(),
            request_factory=lambda case, message, supplied: make_grounded_request(
                case,
                message,
                supplied,
                gaps=(gap,),
            ),
        ),
        snapshot_id=SNAPSHOT,
        repair_repeated_queries=True,
    ).run(CASE, MESSAGE, initial_query=QUERY)
    assert result.status == "awaiting_approval" and result.analysis.next_question == gap.question
    assert result.analysis.missing_info == (gap.name,)


@pytest.mark.parametrize("kind", ["context", "source"])
def test_grounded_binding_violation_cannot_buy_a_second_plan(kind):
    class BindingViolationPlanner(RepeatPlanner):
        def plan(self, request, *, context):
            self.contexts.append(context)
            hit = request.evidence.hits[0]
            return GroundedPlan(
                context_sha256="0" * 64 if kind == "context" else request.context_sha256,
                decision="answer",
                sources=(
                    {
                        "chunk_id": hit.chunk_id,
                        "content_sha256": "0" * 64
                        if kind == "source"
                        else source_content_sha256(hit),
                    },
                ),
            )

    planner = BindingViolationPlanner()
    retriever = FakeRetriever([evidence()])
    result = SupportEngine(
        retriever,
        GroundedReasoner(planner),
        snapshot_id=SNAPSHOT,
        repair_repeated_queries=True,
    ).run(CASE, MESSAGE, initial_query=QUERY)
    assert result.error_code == (
        "GroundedContextMismatch" if kind == "context" else "GroundedSourceMismatch"
    )
    assert result.model_attempts == len(planner.contexts) == len(retriever.requests) == 1


def test_real_user_version_correction_uses_only_current_evidence_and_fresh_handoff():
    old_fact = Fact(
        name="streamlit_version", value="1.50.0", source_ref="user:old", turn_id="turn:old"
    )
    original = CASE.model_copy(update={"facts": (old_fact,)})
    corrected = original.model_copy(
        update={
            "case_revision": original.case_revision + 1,
            "facts": (
                old_fact.model_copy(update={"status": "superseded"}),
                Fact(
                    name="streamlit_version",
                    value="1.49.0",
                    source_ref="user:corrected",
                    turn_id="turn:corrected",
                ),
            ),
        }
    )
    old = evidence(chunk="doc:old", excerpt="The complete original fixture quotation.")
    new = evidence(chunk="doc:corrected", excerpt="The complete corrected fixture quotation.")
    new = new.model_copy(
        update={"hits": (new.hits[0].model_copy(update={"applicable_versions": ("1.49.0",)}),)}
    )
    planner = RepeatPlanner("answer")
    capture = ReasoningCapture(GroundedReasoner(planner))
    engine = SupportEngine(
        FakeRetriever([old, new]),
        capture,
        snapshot_id=SNAPSHOT,
        repair_repeated_queries=True,
        evidence_scope="exact_user_version",
    )
    first = engine.run(original, MESSAGE, initial_query=QUERY, run_id="run:old-version")
    first_handoff = build_handoff(first, capture.last, grounded_request=planner.requests[-1])
    second = engine.run(corrected, MESSAGE, initial_query=QUERY, run_id="run:corrected-version")
    handoff = build_handoff(second, capture.last, grounded_request=planner.requests[-1])
    assert first.status == second.status == "awaiting_approval"
    assert first.retrieval_rounds == second.retrieval_rounds == 1
    assert first.model_attempts == second.model_attempts == 2
    assert first_handoff.case.facts[0].value == "1.50.0"
    assert [fact.value for fact in handoff.case.facts if fact.status == "active"] == ["1.49.0"]
    assert handoff.case == corrected and handoff.reasoning_context.case_revision == 3
    assert old.hits[0].excerpt not in handoff.analysis.model_dump_json()
    assert new.hits[0].excerpt in handoff.analysis.user_draft
    assert handoff.analysis.evidence_links[0].chunk_id == "doc:corrected"
    assert planner.contexts[2].output_feedback is None
    assert handoff.handoff_sha256 != first_handoff.handoff_sha256


@pytest.mark.parametrize("fault", ["normal", "timeout", "model_mismatch"])
def test_real_gateway_mock_wire_repair_handoff_and_uncertainty(tmp_path, monkeypatch, fault):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Real provider transport and environment config are forbidden")

    monkeypatch.setattr(httpx.HTTPTransport, "__init__", forbidden)
    monkeypatch.setattr(MetisConfig, "from_env", forbidden)
    ledger = BudgetLedger.create(
        tmp_path / "fixture.sqlite3", limit_usd=Decimal("1"), opening_spend_usd=Decimal("0")
    )
    retriever = FakeRetriever([evidence()])
    binding = GroundedHttpBinding(
        ledger,
        snapshot_id=SNAPSHOT,
        retriever_factory=lambda: retriever,
        planner_factory=RepeatPlanner,
        fault=fault,
    )
    current = CASE.model_copy(
        update={
            "facts": (
                Fact(
                    name="streamlit_version",
                    value="1.50.0",
                    source_ref="user:version",
                    turn_id="turn:2",
                ),
            )
        }
    )
    ports = binding.adapters("fixture")
    capture = ReasoningCapture(ports.reasoner)
    try:
        with offline_network():
            result = SupportEngine(
                ports.retriever,
                capture,
                snapshot_id=SNAPSHOT,
                repair_repeated_queries=True,
            ).run(current, MESSAGE, initial_query=QUERY, run_id="run:mock-repeat")
        if fault == "normal":
            handoff = build_handoff(
                result, capture.last, grounded_request=ports.grounded_request_supplier()
            )
            assert result.status == "awaiting_approval" and handoff.analysis.decision == "escalate"
            assert result.model_attempts == 2 and result.retrieval_rounds == 1
            first, second = binding.records
            first_payload = json.loads(first["provider_payload"]["messages"][1]["content"])
            second_payload = json.loads(second["provider_payload"]["messages"][1]["content"])
            assert first_payload["request"] == second_payload["request"]
            assert second_payload["request"] == handoff.grounded_request.model_dump(mode="json")
            assert second_payload["repair_issue_codes"] == ["invalid_field"]
            assert not second_payload["capacity"]["can_refine"]
            assert second["context"]["output_feedback"]["issues"] == [
                {"code": "invalid_field", "field": "retrieval_queries"}
            ]
            assert first["request_id"] != second["request_id"]
            assert all(
                record["reservation_after_attempt"]["status"] == "settled"
                for record in binding.records
            )
            assert evidence().hits[0].excerpt in handoff.analysis.maintainer_summary
        else:
            assert result.error_code == (
                "ProviderRequestFailed" if fault == "timeout" else "ProviderModelMismatch"
            )
            assert result.model_attempts == 1 and result.output_issues == ()
            assert binding.snapshot()["uncertain_reservations"] == 1
            assert binding.snapshot()["settled_reservations"] == 0
        assert len(retriever.requests) == 1 and binding.snapshot()["actual_paid_requests"] == 0
    finally:
        ports.cleanup()
    assert binding.all_clients_closed
