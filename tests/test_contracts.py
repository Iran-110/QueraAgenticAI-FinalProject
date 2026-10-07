"""Boundary validation protects the engine from malformed model/tool outputs."""

import json

import pytest
from pydantic import ValidationError

from agent_app.contracts import (
    AnalysisResult,
    CaseState,
    EvidenceBundle,
    EvidenceHit,
    EvidenceLink,
    Fact,
    ReasoningContext,
    RetrievalRequest,
    RunLimits,
    RunResult,
    TraceEvent,
)


def hit(**changes):
    data = {
        "chunk_id": "docs:session-state:1",
        "source_id": "docs:session-state",
        "excerpt": "Each rerun begins by executing the script from top to bottom.",
        "source_url": "https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state",
        "source_type": "doc",
        "source_commit": "abc123",
        "source_span": "paragraph 2",
        "applicable_versions": ("1.50",),
        "score": 4.3,
        "score_kind": "bm25",
    }
    return EvidenceHit(**(data | changes))


def fact(**changes):
    data = {
        "name": "streamlit_version",
        "value": "1.50",
        "source_ref": "event:user:1",
        "turn_id": "turn:1",
    }
    return Fact(**(data | changes))


def analysis(**changes):
    data = {
        "decision": "answer",
        "user_draft": "Use Session State to preserve the value across reruns.",
        "maintainer_summary": "The user needs persistence across script reruns.",
        "rationale": "The supplied documentation describes the relevant API.",
        "evidence_links": (
            EvidenceLink(
                claim="Session State persists values across reruns.",
                chunk_id="docs:session-state:1",
            ),
        ),
    }
    return AnalysisResult(**(data | changes))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("decision", "close_case"),
        ("user_draft", None),
        ("rationale", "  "),
        ("rationale", "x" * 2_001),
        ("confidence", 1.0),
        ("actions", [{"tool": "delete_case"}]),
    ],
)
def test_rejects_malformed_or_unrecognized_model_output(field, value):
    with pytest.raises(ValidationError):
        analysis(**{field: value})


@pytest.mark.parametrize("field", ["user_draft", "maintainer_summary"])
@pytest.mark.parametrize("decision", ["answer", "ask", "escalate"])
def test_final_decisions_require_both_drafts(field, decision):
    kwargs = {"decision": decision, field: "  "}
    if decision == "ask":
        kwargs["next_question"] = "Which Streamlit version are you running?"
    with pytest.raises(ValidationError, match="requires user_draft"):
        analysis(**kwargs)


def test_ask_requires_a_specific_nonempty_question():
    with pytest.raises(ValidationError, match="ask requires"):
        analysis(decision="ask")
    with pytest.raises(ValidationError):
        analysis(decision="ask", next_question=" ")
    result = analysis(decision="ask", next_question="Which Streamlit version are you running?")
    assert result.next_question == "Which Streamlit version are you running?"


@pytest.mark.parametrize("decision", ["answer", "escalate", "retrieve_more"])
def test_question_is_exclusive_to_ask(decision):
    kwargs = {"decision": decision, "next_question": "What is the version?"}
    if decision == "retrieve_more":
        kwargs |= {
            "user_draft": "",
            "maintainer_summary": "",
            "retrieval_queries": ("session state version",),
        }
    with pytest.raises(ValidationError):
        analysis(**kwargs)


def test_retrieve_more_is_an_intermediate_decision():
    with pytest.raises(ValidationError, match="requires retrieval_queries"):
        analysis(decision="retrieve_more", user_draft="", maintainer_summary="")
    with pytest.raises(ValidationError, match="must not contain a final draft"):
        analysis(decision="retrieve_more", retrieval_queries=("session state widget rerun",))
    result = analysis(
        decision="retrieve_more",
        user_draft="",
        maintainer_summary="",
        retrieval_queries=("session state widget rerun",),
    )
    assert result.retrieval_queries == ("session state widget rerun",)


@pytest.mark.parametrize("decision", ["answer", "ask", "escalate"])
def test_final_decision_cannot_also_request_retrieval(decision):
    kwargs = {"decision": decision, "retrieval_queries": ("session state",)}
    if decision == "ask":
        kwargs["next_question"] = "What is the version?"
    with pytest.raises(ValidationError, match="only retrieve_more"):
        analysis(**kwargs)


@pytest.mark.parametrize(
    "queries",
    [(), ("  ",), ("x" * 501,), ("one", "two", "three"), ("same query", "Same query")],
)
def test_retrieval_queries_are_bounded_nonempty_and_unique(queries):
    with pytest.raises(ValidationError):
        RetrievalRequest(queries=queries, snapshot_id="snapshot:1")


@pytest.mark.parametrize("queries", [(" ",), ("one", "two", "three"), ("same", "Same")])
def test_model_cannot_request_empty_excessive_or_duplicate_queries(queries):
    with pytest.raises(ValidationError):
        analysis(
            decision="retrieve_more",
            user_draft="",
            maintainer_summary="",
            retrieval_queries=queries,
        )


@pytest.mark.parametrize("top_k", [0, 51, True, "5"])
def test_retrieval_top_k_rejects_invalid_or_coerced_values(top_k):
    with pytest.raises(ValidationError):
        RetrievalRequest(queries=("session state",), snapshot_id="snapshot:1", top_k=top_k)


@pytest.mark.parametrize("score", [float("nan"), float("inf"), -float("inf"), True, "0.7"])
def test_nonfinite_retrieval_scores_are_rejected(score):
    with pytest.raises(ValidationError):
        hit(score=score)


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "javascript:alert(1)",
        "https://",
        "https://example.com:broken",
        "https://user:secret@example.com",
        "https://example.com/a b",
    ],
)
def test_source_urls_are_reviewable_web_links(url):
    with pytest.raises(ValidationError):
        hit(source_url=url)


def test_retrieval_score_is_not_assumed_to_be_a_probability():
    assert hit(score=42.5, score_kind="bm25").score == 42.5


def test_duplicate_chunk_ids_are_rejected_but_same_source_can_have_many_chunks():
    with pytest.raises(ValidationError, match="unique chunk_id"):
        EvidenceBundle(snapshot_id="snapshot:1", hits=(hit(), hit(excerpt="Different text.")))
    result = EvidenceBundle(
        snapshot_id="snapshot:1", hits=(hit(), hit(chunk_id="docs:session-state:2"))
    )
    assert len(result.hits) == 2


def test_corrected_fact_retains_history_but_cannot_have_two_active_values():
    old = fact(value="1.49", status="superseded")
    new = fact(value="1.50", source_ref="event:user:2", turn_id="turn:2")
    state = CaseState(case_id="case:1", case_revision=2, facts=(old, new))
    assert state.facts == (old, new)
    with pytest.raises(ValidationError, match="only one active fact"):
        CaseState(case_id="case:1", facts=(fact(value="1.49"), new))
    with pytest.raises(ValidationError, match="only one active fact"):
        analysis(facts_delta=(fact(value="1.49"), new))


def test_duplicate_citations_are_rejected_but_a_claim_can_have_multiple_sources():
    link = EvidenceLink(claim="The value persists.", chunk_id="chunk:1")
    with pytest.raises(ValidationError, match="duplicate claim/chunk"):
        analysis(evidence_links=(link, link))
    assert (
        len(
            analysis(
                evidence_links=(link, EvidenceLink(claim=link.claim, chunk_id="chunk:2"))
            ).evidence_links
        )
        == 2
    )


@pytest.mark.parametrize("revision", [-1, True, "1", 1.0])
def test_case_revision_rejects_invalid_or_coerced_numbers(revision):
    with pytest.raises(ValidationError):
        CaseState(case_id="case:1", case_revision=revision)


@pytest.mark.parametrize("attempt_index", [0, 3, True, "1", 1.0])
def test_reasoning_context_rejects_out_of_budget_and_coerced_attempt_indices(attempt_index):
    with pytest.raises(ValidationError):
        ReasoningContext(
            run_id="run:1", case_id="case:1", case_revision=0, attempt_index=attempt_index
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [("run_id", " "), ("case_id", " "), ("case_revision", -1), ("case_revision", True)],
)
def test_reasoning_context_requires_valid_case_attribution(field, value):
    data = {"run_id": "run:1", "case_id": "case:1", "case_revision": 0, "attempt_index": 1}
    with pytest.raises(ValidationError):
        ReasoningContext(**(data | {field: value}))


def test_reasoning_context_roundtrip_is_immutable_and_forbids_model_chosen_permission():
    context = ReasoningContext(run_id="run:1", case_id="case:1", case_revision=2, attempt_index=2)
    assert ReasoningContext.model_validate_json(context.model_dump_json()) == context
    with pytest.raises(ValidationError, match="frozen"):
        context.attempt_index = 1
    with pytest.raises(ValidationError, match="Extra inputs"):
        ReasoningContext.model_validate(context.model_dump() | {"approved": True})


def test_reasoning_context_constructed_without_validation_must_be_revalidated_at_boundary():
    valid = ReasoningContext(run_id="run:1", case_id="case:1", case_revision=0, attempt_index=1)
    unsafe_contexts = (
        valid.model_copy(update={"attempt_index": 3}),
        ReasoningContext.model_construct(**(valid.model_dump() | {"case_revision": -1})),
    )
    for unsafe in unsafe_contexts:
        with pytest.raises(ValidationError):
            ReasoningContext.model_validate(unsafe.model_dump(warnings=False))


@pytest.mark.parametrize("field", ["model_attempts", "retrieval_rounds", "steps"])
def test_run_counters_cannot_be_negative(field):
    with pytest.raises(ValidationError):
        RunResult(run_id="run:1", case_id="case:1", case_revision=0, status="error", **{field: -1})


@pytest.mark.parametrize(
    "field", ["max_model_attempts", "max_retrieval_rounds", "max_queries_per_round", "max_steps"]
)
def test_run_limits_are_positive(field):
    with pytest.raises(ValidationError):
        RunLimits(**{field: 0})


@pytest.mark.parametrize(
    ("field", "ceiling"),
    [
        ("max_model_attempts", 2),
        ("max_retrieval_rounds", 2),
        ("max_queries_per_round", 2),
        ("max_steps", 8),
    ],
)
@pytest.mark.parametrize("excess", [1, 100])
def test_run_limits_reject_values_above_hard_ceilings(field, ceiling, excess):
    payload = {field: ceiling + excess}
    for validate in (
        RunLimits.model_validate,
        lambda data: RunLimits.model_validate_json(json.dumps(data)),
    ):
        with pytest.raises(ValidationError) as caught:
            validate(payload)
        error = caught.value.errors()[0]
        assert error["loc"] == (field,)
        assert error["type"] == "less_than_equal"
        assert error["ctx"]["le"] == ceiling


@pytest.mark.parametrize(
    ("field", "ceiling"),
    [
        ("max_model_attempts", 2),
        ("max_retrieval_rounds", 2),
        ("max_queries_per_round", 2),
        ("max_steps", 8),
    ],
)
def test_limit_payloads_built_without_validation_are_rejected_at_revalidation(field, ceiling):
    # model_construct and model_copy(update=...) intentionally bypass Pydantic
    # validation. Ports must revalidate serialized values rather than trust type.
    unsafe_limits = (
        RunLimits.model_construct(**{field: ceiling + 1}),
        RunLimits().model_copy(update={field: ceiling + 1}),
    )
    for limits in unsafe_limits:
        with pytest.raises(ValidationError) as caught:
            RunLimits.model_validate(limits.model_dump())
        assert caught.value.errors()[0]["loc"] == (field,)


def test_callers_can_tighten_run_limits_without_exceeding_hard_ceilings():
    limits = RunLimits(
        max_model_attempts=1,
        max_retrieval_rounds=1,
        max_queries_per_round=1,
        max_steps=4,
    )
    assert RunLimits.model_validate_json(limits.model_dump_json()) == limits


def test_awaiting_approval_requires_final_analysis():
    data = {
        "run_id": "run:1",
        "case_id": "case:1",
        "case_revision": 0,
        "status": "awaiting_approval",
    }
    with pytest.raises(ValidationError, match="requires a final analysis"):
        RunResult(**data)
    intermediate = analysis(
        decision="retrieve_more",
        user_draft="",
        maintainer_summary="",
        retrieval_queries=("session state",),
    )
    with pytest.raises(ValidationError, match="requires a final analysis"):
        RunResult(**data, analysis=intermediate)
    assert RunResult(**data, analysis=analysis()).analysis.decision == "answer"


@pytest.mark.parametrize("status", ["error", "stale", "budget_stopped"])
def test_failed_or_stopped_run_does_not_expose_a_draft(status):
    with pytest.raises(ValidationError, match="must not expose"):
        RunResult(
            run_id="run:1", case_id="case:1", case_revision=0, status=status, analysis=analysis()
        )


def test_all_boundary_types_reject_extra_fields_and_field_reassignment():
    with pytest.raises(ValidationError, match="Extra inputs"):
        CaseState(case_id="case:1", approval=True)
    state = CaseState(case_id="case:1")
    with pytest.raises(ValidationError, match="frozen"):
        state.case_revision = 9


def test_nested_json_roundtrip_preserves_contracts_and_tuple_fields():
    bundle = EvidenceBundle(
        snapshot_id="snapshot:1", hits=(hit(),), queries_used=("session state",)
    )
    state = CaseState(case_id="case:1", facts=(fact(),), evidence_refs=(hit().chunk_id,))
    request = RetrievalRequest(
        queries=("session state",),
        snapshot_id=bundle.snapshot_id,
        filters={"source_type": ("doc", "release_note")},
    )
    result = RunResult(
        run_id="run:1",
        case_id=state.case_id,
        case_revision=state.case_revision,
        status="awaiting_approval",
        analysis=analysis(facts_delta=(fact(),)),
        model_attempts=1,
        retrieval_rounds=1,
        steps=3,
        trace=(TraceEvent(stage="analysis", message="Created a draft for human review."),),
    )
    for instance in (bundle, state, request, result, RunLimits()):
        restored = type(instance).model_validate_json(instance.model_dump_json())
        assert restored == instance
        assert json.loads(instance.model_dump_json()) == instance.model_dump(mode="json")
    assert isinstance(EvidenceBundle.model_validate_json(bundle.model_dump_json()).hits, tuple)
