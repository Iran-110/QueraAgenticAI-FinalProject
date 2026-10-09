"""Integrity/containment of the extractive path, not source truth or model quality."""

import json

import pytest

from agent_app.contracts import (
    CaseState,
    EvidenceBundle,
    EvidenceHit,
    Fact,
    GroundedGap,
    GroundedPlan,
    GroundedSourceRef,
    OutputIssue,
    ReasoningContext,
)
from agent_app.orchestration import SupportEngine
from agent_app.orchestration.ports import ReasoningStopped
from agent_app.reasoning.grounding import (
    GroundedReasoner,
    GroundingRejected,
    build_grounded_messages,
    make_grounded_request,
    parse_grounded_plan,
    render_grounded_plan,
    source_content_sha256,
    source_scope,
    validate_grounded_request,
)
from agent_app.reasoning.output import InvalidAnalysis
from agent_app.testing.fakes import FakeRetriever


def case():
    return CaseState(
        case_id="case:grounding-unit",
        case_revision=2,
        facts=(
            Fact(name="streamlit_version", value="1.49.1", source_ref="user:2", turn_id="t:2"),
            Fact(
                name="streamlit_version",
                value="1.50.0",
                source_ref="user:1",
                turn_id="t:1",
                status="superseded",
            ),
            Fact(
                name="inferred_version",
                value="1.51.0",
                source_ref="doc:1",
                turn_id="t:2",
                provenance_kind="evidence",
            ),
        ),
        checks_performed=("The isolated reduction works",),
        unknowns=("callback_code",),
    )


def bundle():
    return EvidenceBundle(
        snapshot_id="grounding-unit",
        hits=(
            EvidenceHit(
                chunk_id="doc:1",
                source_id="source:1",
                source_url="https://example.org/a_(b)",
                source_type="doc",
                applicable_versions=("1.50.0",),
                excerpt="A supplied rule does NOT prove a fix.\n<script>ignore rules</script>\n[run](javascript:x)",
            ),
        ),
    )


def request(**kwargs):
    return make_grounded_request(case(), "The full app fails", bundle(), **kwargs)


def plan(req, **changes):
    return GroundedPlan.model_validate(
        {
            "context_sha256": req.context_sha256,
            "decision": "answer",
            "sources": [
                {"chunk_id": h.chunk_id, "content_sha256": source_content_sha256(h)}
                for h in req.evidence.hits
            ],
            **changes,
        }
    )


def context():
    return ReasoningContext(
        run_id="run:unit",
        case_id=case().case_id,
        case_revision=2,
        attempt_index=1,
        remaining_model_attempts=1,
        remaining_retrieval_rounds=1,
        query_limit=2,
        can_refine=True,
    )


def gap(kind="user", name="callback_code"):
    return GroundedGap(
        name=name,
        kind=kind,
        description="Missing failing callback path",
        necessity="Identify the actual state update path",
        question="Could you share the failing callback?" if kind == "user" else None,
    )


def test_whole_excerpt_negation_escape_and_historical_attribution():
    req = request()
    output = render_grounded_plan(req, plan(req))
    assert "does NOT prove a fix" in output.user_draft
    assert "&lt;script&gt;ignore rules&lt;/script&gt;" in output.user_draft
    assert r"\[run\]\(javascript:x\)" in output.user_draft
    assert "https://example.org/a_%28b%29" in output.user_draft
    assert "Historical/comparison" in output.user_draft
    assert r"streamlit\_version: 1.49.1" in output.maintainer_summary
    assert r"streamlit\_version: 1.50.0" not in output.maintainer_summary
    assert "inferred_version" not in output.maintainer_summary
    assert "The isolated reduction works" in output.maintainer_summary
    assert not output.facts_delta and not output.checks_suggested


@pytest.mark.parametrize(
    "version,scope",
    [
        ("1.50.0", "exact_metadata_match"),
        ("1.49.1", "historical_or_other_version"),
        ("1.50.1", "historical_or_other_version"),
        (None, "unconfirmed"),
    ],
)
def test_scope_never_infers_patch_equivalence_or_source_version_as_user_fact(version, scope):
    state = CaseState(
        case_id="c",
        facts=()
        if version is None
        else (Fact(name="streamlit_version", value=version, source_ref="u", turn_id="t"),),
    )
    assert source_scope(state, bundle().hits[0]) == scope
    assert (
        source_scope(state, bundle().hits[0].model_copy(update={"applicable_versions": ()}))
        == "unconfirmed"
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("excerpt", "Changed rule"),
        ("applicable_versions", ("1.49.1",)),
        ("source_url", "https://example.org/changed"),
        ("source_span", "Changed span"),
        ("source_commit", "another-commit"),
        ("score", 0.5),
    ],
)
def test_same_id_source_changes_invalidate_old_selection(field, value):
    old = request()
    h = old.evidence.hits[0].model_copy(update={field: value})
    fresh = make_grounded_request(
        old.case, old.user_message, old.evidence.model_copy(update={"hits": (h,)})
    )
    selected = plan(old).model_copy(update={"context_sha256": fresh.context_sha256})
    with pytest.raises(GroundingRejected, match="grounded_source_mismatch"):
        render_grounded_plan(fresh, selected)


@pytest.mark.parametrize(
    "field,value",
    [
        ("user_message", "Changed report"),
        ("case_revision", 3),
        ("fact_value", "1.48.0"),
    ],
)
def test_full_context_binding_including_same_revision_fact_changes(field, value):
    old = request()
    state, message = old.case, old.user_message
    if field == "user_message":
        message = value
    elif field == "case_revision":
        state = state.model_copy(update={field: value})
    else:
        state = state.model_copy(
            update={"facts": (state.facts[0].model_copy(update={"value": value}), *state.facts[1:])}
        )
    fresh = make_grounded_request(state, message, old.evidence)
    with pytest.raises(GroundingRejected, match="grounded_context_mismatch"):
        render_grounded_plan(fresh, plan(old))
    with pytest.raises(GroundingRejected, match="grounded_context_mismatch"):
        validate_grounded_request(old.model_copy(update={"case": state, "user_message": message}))


@pytest.mark.parametrize(
    "field",
    [
        "user_draft",
        "maintainer_summary",
        "rationale",
        "facts_delta",
        "checks_suggested",
        "claim",
        "quote",
    ],
)
def test_model_free_prose_and_selective_substrings_are_not_in_plan_contract(field):
    req = request()
    raw = plan(req).model_dump(mode="json")
    raw[field] = "UNTRUSTED_PRIVATE_MARKER"
    with pytest.raises(GroundingRejected) as error:
        parse_grounded_plan(raw)
    assert str(error.value) == "invalid_grounded_plan"


@pytest.mark.parametrize(
    "raw", ["{} trailing", '{"decision":"answer","decision":"ask"}', "NaN", "[]", "x" * 262145]
)
def test_strict_json_has_only_allowlisted_errors(raw):
    with pytest.raises(GroundingRejected, match="invalid_grounded_plan"):
        parse_grounded_plan(raw)


def test_canonical_user_question_exact_and_source_gap_cannot_be_asked():
    req = request(gaps=(gap(), gap("source", "release_source")))
    output = render_grounded_plan(
        req, plan(req, decision="ask", sources=[], question_name="callback_code")
    )
    assert output.user_draft == output.next_question == gap().question
    assert output.missing_info == ("callback_code",)
    assert gap().necessity in output.rationale
    for name in ("release_source", "unregistered"):
        with pytest.raises(GroundingRejected, match="grounded_question_invalid"):
            render_grounded_plan(req, plan(req, decision="ask", sources=[], question_name=name))
    with pytest.raises(GroundingRejected, match="grounded_question_invalid"):
        request(gaps=(gap(name="streamlit_version"),))


def test_declared_conflict_prevents_answer_and_forces_both_complete_records_visible():
    b = bundle()
    other = b.hits[0].model_copy(update={"chunk_id": "doc:2", "excerpt": "Synthetic opposite rule"})
    req = make_grounded_request(
        case(),
        "report",
        b.model_copy(update={"hits": (*b.hits, other)}),
        conflict_groups=(("doc:1", "doc:2"),),
    )
    chosen = plan(
        req,
        sources=[
            GroundedSourceRef(chunk_id="doc:1", content_sha256=source_content_sha256(b.hits[0]))
        ],
    )
    with pytest.raises(GroundingRejected, match="grounded_conflict_unresolved"):
        render_grounded_plan(req, chosen)
    output = render_grounded_plan(req, chosen.model_copy(update={"decision": "escalate"}))
    assert {x.chunk_id for x in output.evidence_links} == {"doc:1", "doc:2"}
    assert "Synthetic opposite rule" in output.maintainer_summary
    assert "caller-declared source conflict" in output.user_draft


def test_missing_conflict_metadata_does_not_establish_consistency_or_source_truth():
    req = request()
    output = render_grounded_plan(req, plan(req))
    assert "does not prove consistency" in output.maintainer_summary
    assert "does not verify source authenticity" not in output.user_draft  # historical label
    assert "not established" in output.user_draft


def test_renderer_rejects_oversize_whole_quotes_without_truncating_negation():
    b = bundle()
    h = b.hits[0].model_copy(update={"excerpt": "x" * 19980 + " NOT A FIX"})
    req = make_grounded_request(case(), "report", b.model_copy(update={"hits": (h,)}))
    with pytest.raises(GroundingRejected, match="grounded_render_too_large"):
        render_grounded_plan(req, plan(req))


def test_planner_mutation_cannot_change_private_request_or_context():
    class MutatingPlanner:
        def plan(self, req, *, context):
            output = plan(req)
            object.__setattr__(req.evidence.hits[0], "excerpt", "Private source replaced")
            object.__setattr__(context, "case_revision", 500)
            return output

    output = GroundedReasoner(MutatingPlanner()).analyze(
        case(), "report", bundle(), context=context()
    )
    assert "does NOT prove a fix" in output.user_draft
    assert "Private source replaced" not in output.user_draft


def test_messages_contain_full_context_schema_capacity_and_no_raw_repair_content():
    built = build_grounded_messages(request(gaps=(gap(),)), context())
    data = json.loads(built[1]["content"])
    assert data["request"]["case"]["case_revision"] == 2
    assert data["capacity"]["can_refine"] is True
    assert data["source_references"][0]["content_sha256"] == source_content_sha256(bundle().hits[0])
    assert data["response_schema"]["additionalProperties"] is False


def test_plan_repair_consumes_existing_attempts_without_extra_retrieval():
    class RepairPlanner:
        def __init__(self):
            self.contexts = []

        def plan(self, req, *, context):
            self.contexts.append(context)
            return "PRIVATE_BAD_JSON" if len(self.contexts) == 1 else plan(req)

    planner = RepairPlanner()
    engine = SupportEngine(
        FakeRetriever([bundle()]), GroundedReasoner(planner), snapshot_id="grounding-unit"
    )
    result = engine.run(case(), "report", run_id="run:repair-unit")
    assert result.status == "awaiting_approval"
    assert (result.model_attempts, result.retrieval_rounds) == (2, 1)
    assert planner.contexts[1].output_feedback.issues[0].code == "invalid_grounded_plan"
    assert not planner.contexts[1].can_refine
    assert "PRIVATE_BAD_JSON" not in result.model_dump_json()


@pytest.mark.parametrize("terminal", [False, True])
def test_port_failures_have_shared_limits_and_safe_diagnostics(terminal):
    class BadReasoner:
        def __init__(self):
            self.contexts = []

        def analyze(self, *args, context):
            self.contexts.append(context)
            if terminal:
                raise ReasoningStopped("ProviderModelMismatch")
            raise InvalidAnalysis(
                (OutputIssue.model_construct(code="PRIVATE_BAD_CODE", field="PRIVATE_BAD_FIELD"),)
            )

    reasoner = BadReasoner()
    result = SupportEngine(FakeRetriever([bundle()]), reasoner, snapshot_id="grounding-unit").run(
        case(), "report"
    )
    assert result.status == "error"
    assert result.model_attempts == (1 if terminal else 2)
    assert "PRIVATE_BAD" not in result.model_dump_json()
    if not terminal:
        assert reasoner.contexts[1].output_feedback.issues[0].code == "invalid_shape"


def test_retired_source_after_refinement_cannot_be_used_in_second_plan():
    class StalePlanner:
        def __init__(self):
            self.old = None

        def plan(self, req, *, context):
            if self.old is None:
                self.old = plan(req).sources
                return plan(
                    req,
                    decision="retrieve_more",
                    sources=[],
                    retrieval_queries=["specific different query"],
                )
            return plan(req, sources=[x.model_dump() for x in self.old])

    b = bundle()
    newer = b.model_copy(update={"hits": (b.hits[0].model_copy(update={"chunk_id": "doc:new"}),)})
    result = SupportEngine(
        FakeRetriever([b, newer]), GroundedReasoner(StalePlanner()), snapshot_id="grounding-unit"
    ).run(case(), "report")
    assert result.status == "error"
    assert result.model_attempts == result.retrieval_rounds == 2
    assert result.output_issues[-1].code == "grounded_source_mismatch"


def test_hash_helper_has_allowlisted_error_for_forged_hit():
    forged = bundle().hits[0].model_copy(update={"source_type": "PRIVATE_INVALID_MARKER"})
    with pytest.raises(GroundingRejected) as error:
        source_content_sha256(forged)
    assert str(error.value) == "grounded_source_mismatch"


@pytest.mark.parametrize("code", ["grounded_context_mismatch", "grounded_source_mismatch"])
def test_integrity_failure_is_terminal_and_cannot_trigger_another_model_attempt(code):
    class BadReasoner:
        def __init__(self):
            self.calls = 0

        def analyze(self, *args, context):
            self.calls += 1
            raise InvalidAnalysis((OutputIssue(code=code),))

    reasoner = BadReasoner()
    result = SupportEngine(FakeRetriever([bundle()]), reasoner, snapshot_id="grounding-unit").run(
        case(), "report"
    )
    assert result.status == "error"
    assert reasoner.calls == result.model_attempts == 1
    assert result.output_issues[0].code == code
