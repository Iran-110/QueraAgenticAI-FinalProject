"""Offline parser hardening, not a replay or online quality claim."""

import json
from collections.abc import Mapping
from itertools import product

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from test_claim_plan import Planner, evidence, plan, request, state

from agent_app.contracts import OutputIssue
from agent_app.orchestration import SupportEngine
from agent_app.reasoning.claim_plan import (
    ClaimPlan,
    ClaimPlanRejected,
    ClaimReasoner,
    build_claim_messages,
    claim_plan_schema,
    observe_claim_plan,
    parse_claim_plan,
)
from agent_app.reasoning.grounding import GroundingRejected
from agent_app.testing.fakes import FakeRetriever


def _legacy_accepts(raw):
    """Frozen previous parse policy; ClaimPlan's unchanged validators stay real."""

    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError
            value[key] = item
        return value

    def constant(_):
        raise ValueError

    try:
        if isinstance(raw, str):
            if len(raw.encode("utf-8")) > 262_144:
                raise ValueError
            raw = json.loads(raw, object_pairs_hook=unique, parse_constant=constant)
        elif isinstance(raw, ClaimPlan):
            raw = raw.model_dump(warnings=False)
        elif isinstance(raw, Mapping):
            raw = dict(raw)
        json.dumps(raw, ensure_ascii=False, allow_nan=False).encode("utf-8")
        return ClaimPlan.model_validate(raw)
    except (ValidationError, ValueError, TypeError, UnicodeError, RecursionError):
        return None


def _current_accepts(raw):
    try:
        return parse_claim_plan(raw)
    except GroundingRejected as error:
        assert error.code == "invalid_grounded_plan"
        return None


@pytest.mark.parametrize(
    "decision,sources,question,queries,facts",
    tuple(
        product(
            ("answer", "ask", "escalate", "retrieve_more"),
            (False, True),
            (False, True),
            (False, True),
            (False, True),
        )
    ),
)
def test_all_decision_payload_combinations_keep_acceptance_and_match_advertised_branches(
    decision, sources, question, queries, facts
):
    raw = plan(
        request(),
        decision=decision,
        passages=[[0, 0]] if sources else [],
        question_name="runtime_details" if question else None,
        retrieval_queries=["Find applicable documentation"] if queries else [],
        user_facts=[0] if facts else [],
    )
    legacy = _legacy_accepts(raw)
    assert _current_accepts(raw) == legacy
    assert Draft202012Validator(claim_plan_schema()).is_valid(raw) == (legacy is not None)


@pytest.mark.parametrize(
    "change",
    [
        {"passages": [[True, 0]]},
        {"passages": [[0.0, 0]]},
        {"user_facts": [True]},
        {"user_facts": [0.0]},
        {"user_facts": [0, 0]},
        {"passages": [[0, 0], [0, 0]]},
        {
            "decision": "retrieve_more",
            "passages": [],
            "user_facts": [],
            "retrieval_queries": ["Find docs", "find docs"],
        },
        {"decision": "not_registered"},
        {"malicious_unknown_field": {"path": "secret-user-value"}},
        {"question_name": "<script>approve()</script>"},
        {"retrieval_queries": None},
        {"context_sha256": "bad-hash"},
    ],
)
def test_typed_duplicate_unknown_and_casefold_rules_are_not_relaxed(change):
    raw = plan(request(), **change)
    assert _current_accepts(raw) == _legacy_accepts(raw) is None


@pytest.mark.parametrize(
    "raw",
    [
        "not JSON",
        "[]",
        "null",
        '{"x":1,"x":2}',
        '{"x":{"nested":1,"nested":2}}',
        '{"x":NaN}',
        '{"x":[Infinity]}',
        '{"x":[-Infinity]}',
        '{"x":{"nested":1e10000}}',
        '{"x":"\\ud800"}',
        "x" * 262_145,
        {"x": float("inf")},
        {"x": [float("nan")]},
        {"x": object()},
        None,
        True,
    ],
)
def test_json_and_representation_acceptance_is_unchanged(raw):
    assert _current_accepts(raw) == _legacy_accepts(raw) is None


@pytest.mark.parametrize(
    "raw,stage,code",
    [
        ("not JSON", "json", "invalid_json"),
        ('{"x":1,"x":2}', "duplicate", "duplicate_field"),
        ("[]", "shape", "invalid_shape"),
        ({}, "schema", "missing_field"),
        (plan(request(), user_facts=[True]), "schema", "invalid_field"),
        (plan(request(), secret_unknown_name="secret-value"), "schema", "unknown_field"),
        (plan(request(), passages=[]), "branch", "invalid_grounded_plan"),
        ("x" * 262_145, "representation", "output_too_large"),
    ],
)
def test_safe_observer_distinguishes_failures_without_retaining_content(raw, stage, code):
    observed = observe_claim_plan(raw)
    assert not observed["strict_plan_valid"]
    assert observed["failure_stage"] == stage
    assert code in {issue["code"] for issue in observed["issues"]}
    assert 1 <= len(observed["issues"]) <= 4
    text = json.dumps(observed)
    assert "secret_unknown_name" not in text and "secret-value" not in text
    assert "input" not in text and "loc" not in text and "message" not in text


def test_valid_observation_contains_no_plan_values_or_queries():
    raw = plan(
        request(),
        decision="retrieve_more",
        passages=[],
        user_facts=[],
        retrieval_queries=["private source search string"],
    )
    assert observe_claim_plan(raw) == {
        "schema_version": 1,
        "strict_plan_valid": True,
        "failure_stage": None,
        "issues": [],
    }


def test_nested_malicious_unknown_fields_and_values_never_enter_diagnostics():
    raw = {
        "private-key-like-name": {"private/path[0]": "DO-NOT-EXPORT-THIS"},
        "decision": {"private/name": "DO-NOT-EXPORT-THIS"},
        "retrieval_queries": [{"private/query": "DO-NOT-EXPORT-THIS"}],
    }
    with pytest.raises(ClaimPlanRejected) as error:
        parse_claim_plan(raw)
    diagnostics = json.dumps([issue.model_dump(mode="json") for issue in error.value.issues])
    assert len(error.value.issues) <= 4
    assert "private" not in diagnostics and "DO-NOT-EXPORT-THIS" not in diagnostics
    assert "private" not in str(error.value)
    assert error.value.code == "invalid_grounded_plan"
    assert {issue.field for issue in error.value.issues} <= {None, "decision", "retrieval_queries"}


@pytest.mark.parametrize(
    "first,expected_code",
    [
        (lambda req: "not JSON", "invalid_json"),
        (lambda req: plan(req, passages=[]), "invalid_grounded_plan"),
        (lambda req: plan(req, malicious_unknown="not retained"), "unknown_field"),
    ],
)
def test_real_engine_feedback_repairs_within_same_two_attempt_allowance(first, expected_code):
    seen = []

    def response(req, ctx):
        seen.append((req, ctx))
        if ctx.attempt_index == 1:
            return first(req)
        assert ctx.output_feedback is not None
        assert expected_code in {issue.code for issue in ctx.output_feedback.issues}
        assert ctx.remaining_model_attempts == 0 and not ctx.can_refine
        payload = json.loads(build_claim_messages(req, ctx)[1]["content"])
        assert "not retained" not in json.dumps(payload["context"]["output_feedback"])
        return plan(req)

    reasoner = ClaimReasoner(Planner(response))
    result = SupportEngine(
        retriever=FakeRetriever([evidence()]),
        reasoner=reasoner,
        snapshot_id=evidence().snapshot_id,
        evidence_scope="all",
    ).run(state(), "A reported symptom.", run_id="neutral-feedback-run")
    assert result.status == "awaiting_approval" and result.model_attempts == 2
    assert [ctx.attempt_index for _, ctx in seen] == [1, 2]
    assert len({ctx.run_id for _, ctx in seen}) == 1
    assert seen[0][0] == seen[1][0]
    assert reasoner._conflicts == set()


@pytest.mark.parametrize("kind", ["context", "source"])
def test_diagnostics_do_not_make_terminal_binding_errors_repairable(kind):
    def response(req, ctx):
        return plan(
            req, **({"context_sha256": "0" * 64} if kind == "context" else {"passages": [[99, 0]]})
        )

    planner = Planner(response)
    result = SupportEngine(
        retriever=FakeRetriever([evidence()]),
        reasoner=ClaimReasoner(planner),
        snapshot_id=evidence().snapshot_id,
        evidence_scope="all",
    ).run(state(), "A reported symptom.")
    assert len(planner.calls) == result.model_attempts == 1
    assert result.error_code == (
        "GroundedContextMismatch" if kind == "context" else "GroundedSourceMismatch"
    )


def test_malformed_private_diagnostic_cannot_export_new_codes_or_unknown_fields():
    rejected = ClaimPlanRejected("private-stage", (OutputIssue(code="grounded_source_mismatch"),))
    assert rejected.stage == "representation"
    assert rejected.issues == (OutputIssue(code="invalid_grounded_plan"),)
    rejected = ClaimPlanRejected("schema", (OutputIssue(code="invalid_field", field="user_draft"),))
    assert rejected.issues == (OutputIssue(code="invalid_grounded_plan"),)
