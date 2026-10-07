"""Strict model-output parsing and diagnostics that never copy untrusted text."""

import json

import pytest
from pydantic import ValidationError

from agent_app.contracts import (
    AnalysisResult,
    EvidenceLink,
    Fact,
    OutputFeedback,
    OutputIssue,
    ReasoningContext,
    RunResult,
)
from agent_app.reasoning.output import InvalidAnalysis, parse_analysis

SECRET = "secret-marker-DO-NOT-COPY"
KNOWN_FIELDS = {
    "decision",
    "user_draft",
    "maintainer_summary",
    "rationale",
    "evidence_links",
    "missing_info",
    "next_question",
    "retrieval_queries",
    "facts_delta",
    "checks_suggested",
}


def payload(**changes):
    return {
        "decision": "answer",
        "user_draft": "A proposed reply for review.",
        "maintainer_summary": "A synthetic support case.",
        "rationale": "The supplied source supports the draft.",
        "evidence_links": [{"claim": "A synthetic claim.", "chunk_id": "docs:1"}],
    } | changes


def rejected(raw):
    with pytest.raises(InvalidAnalysis) as caught:
        parse_analysis(raw)
    error = caught.value
    assert error.issues
    for issue in error.issues:
        assert isinstance(issue, OutputIssue)
        assert issue.field is None or issue.field in KNOWN_FIELDS
    return error


def issue_pairs(error):
    return {(issue.code, issue.field) for issue in error.issues}


def assert_private(error):
    serialized = json.dumps([issue.model_dump(mode="json") for issue in error.issues])
    assert SECRET not in str(error)
    assert SECRET not in repr(error)
    assert SECRET not in serialized
    assert SECRET not in repr(error.issues)


@pytest.mark.parametrize("kind", ["mapping", "json", "model"])
def test_accepts_the_same_valid_analysis_from_supported_boundaries(kind):
    expected = AnalysisResult.model_validate(payload())
    raw = {
        "mapping": payload(),
        "json": " \n" + json.dumps(payload()) + "\t ",
        "model": expected,
    }[kind]
    assert parse_analysis(raw) == expected


def test_parsing_does_not_mutate_the_callers_mapping():
    raw = payload()
    before = json.loads(json.dumps(raw))
    result = parse_analysis(raw)
    assert raw == before
    assert result.evidence_links[0].chunk_id == "docs:1"


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "  ",
        "not JSON",
        "```json\n" + json.dumps(payload()) + "\n```",
        "Here is the decision: " + json.dumps(payload()),
        json.dumps(payload()) + "\nExplanation follows.",
        json.dumps(payload()) + json.dumps(payload()),
        "\ufeff" + json.dumps(payload()),
        '{"decision": "answer",}',
    ],
)
def test_requires_one_bare_json_document(raw):
    assert ("invalid_json", None) in issue_pairs(rejected(raw))


@pytest.mark.parametrize("raw", ["[]", "null", "true", "1", '"text"', [], None, 1, True])
def test_requires_an_object_at_the_root(raw):
    assert ("invalid_shape", None) in issue_pairs(rejected(raw))


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
@pytest.mark.parametrize("location", ["top", "nested"])
def test_rejects_non_json_numeric_constants_even_in_nested_values(constant, location):
    extra = '"extra": ' + constant
    if location == "nested":
        extra = '"extra": {"nested": ' + constant + "}"
    raw = json.dumps(payload())[:-1] + "," + extra + "}"
    assert ("invalid_json", None) in issue_pairs(rejected(raw))


@pytest.mark.parametrize(
    "raw",
    [
        '{"decision":"ask","decision":"answer"}',
        '{"rationale":"one","rationale":"two"}',
        '{"evidence_links":[{"chunk_id":"one","chunk_id":"two"}]}',
        '{"extra":{"key":"one","key":"two"}}',
    ],
)
def test_rejects_duplicate_keys_before_validation_or_last_value_wins(raw):
    assert any(issue.code == "duplicate_field" for issue in rejected(raw).issues)


def test_duplicate_unknown_field_does_not_reveal_the_field_name_or_value():
    raw = '{"' + SECRET + '":"' + SECRET + '","' + SECRET + '":{}}'
    error = rejected(raw)
    assert any(issue.code == "duplicate_field" for issue in error.issues)
    assert_private(error)


@pytest.mark.parametrize("field", ["decision", "user_draft", "maintainer_summary", "rationale"])
def test_reports_only_the_known_name_of_a_missing_required_field(field):
    raw = payload()
    del raw[field]
    assert ("missing_field", field) in issue_pairs(rejected(raw))


def test_unknown_top_level_fields_are_diagnosed_without_copying_their_names():
    error = rejected(payload(**{SECRET: {SECRET: SECRET}}))
    assert ("unknown_field", None) in issue_pairs(error)
    assert_private(error)


@pytest.mark.parametrize("field", ["evidence_links", "facts_delta"])
def test_nested_unknown_fields_are_attributed_to_a_known_parent_only(field):
    nested = (
        {"claim": "Synthetic", "chunk_id": "docs:1"}
        if field == "evidence_links"
        else {"name": "version", "value": "1.0", "source_ref": "event:1", "turn_id": "turn:1"}
    )
    nested[SECRET] = {SECRET: SECRET}
    error = rejected(payload(**{field: [nested]}))
    assert ("unknown_field", field) in issue_pairs(error)
    assert_private(error)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("decision", SECRET),
        ("user_draft", {SECRET: SECRET}),
        ("rationale", None),
        ("next_question", {SECRET: SECRET}),
        ("retrieval_queries", [SECRET, SECRET]),
        ("evidence_links", [{"claim": SECRET, "chunk_id": "invalid " + SECRET}]),
        (
            "facts_delta",
            [{"name": SECRET, "value": SECRET, "source_ref": {SECRET: SECRET}, "turn_id": "t:1"}],
        ),
    ],
)
def test_invalid_values_produce_static_codes_without_inputs_or_validator_context(field, value):
    error = rejected(payload(**{field: value}))
    assert ("invalid_field", field) in issue_pairs(error)
    assert_private(error)


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        (
            {"decision": "retrieve_more", "user_draft": "", "maintainer_summary": ""},
            "retrieve_more_queries_required",
        ),
        (
            {"decision": "retrieve_more", "retrieval_queries": ["source query"]},
            "retrieve_more_final_payload_forbidden",
        ),
        ({"user_draft": ""}, "final_drafts_required"),
        ({"maintainer_summary": " "}, "final_drafts_required"),
        ({"retrieval_queries": ["source query"]}, "final_queries_forbidden"),
        ({"decision": "ask"}, "ask_question_required"),
        ({"next_question": "Which version?"}, "question_forbidden"),
    ],
)
def test_decision_rules_have_actionable_static_diagnostics(changes, code):
    assert any(issue.code == code for issue in rejected(payload(**changes)).issues)


def test_revalidates_model_copy_instead_of_trusting_its_python_type():
    valid = AnalysisResult.model_validate(payload())
    bypass = valid.model_copy(update={"decision": SECRET})
    error = rejected(bypass)
    assert ("invalid_field", "decision") in issue_pairs(error)
    assert_private(error)


def test_revalidates_a_constructed_model_with_missing_fields():
    bypass = AnalysisResult.model_construct(decision="answer", user_draft=SECRET)
    error = rejected(bypass)
    assert ("missing_field", "rationale") in issue_pairs(error)
    assert ("missing_field", "maintainer_summary") in issue_pairs(error)
    assert_private(error)


@pytest.mark.parametrize("kind", ["evidence", "fact"])
def test_revalidates_nested_models_that_bypassed_validation(kind):
    changes = (
        {
            "evidence_links": [
                EvidenceLink.model_construct(claim=SECRET, chunk_id="invalid " + SECRET)
            ]
        }
        if kind == "evidence"
        else {
            "facts_delta": [
                Fact.model_construct(
                    name=SECRET, value=SECRET, source_ref="invalid " + SECRET, turn_id="t:1"
                )
            ]
        }
    )
    bypass = AnalysisResult.model_validate(payload()).model_copy(update=changes)
    error = rejected(bypass)
    assert any(issue.code == "invalid_field" for issue in error.issues)
    assert_private(error)


@pytest.mark.parametrize("text", ["x" * 262_145, "🙂" * 65_537])
def test_byte_limit_precedes_parsing_and_counts_utf8_bytes(text):
    assert issue_pairs(rejected(text)) == {("output_too_large", None)}


@pytest.mark.parametrize("draft", ["A proposed reply for review.", "🙂" * 100])
def test_a_valid_json_document_at_the_exact_byte_limit_is_accepted(draft):
    raw = json.dumps(payload(user_draft=draft), ensure_ascii=False)
    raw += " " * (262_144 - len(raw.encode("utf-8")))
    assert len(raw.encode("utf-8")) == 262_144
    assert parse_analysis(raw).user_draft == draft


def test_malformed_json_never_copies_response_content_into_diagnostics():
    error = rejected('{"rationale":"' + SECRET)
    assert issue_pairs(error) == {("invalid_json", None)}
    assert_private(error)


def test_invalid_unicode_is_a_sanitized_parse_failure():
    error = rejected('{"rationale":"\ud800' + SECRET + '"}')
    assert ("invalid_json", None) in issue_pairs(error)
    assert_private(error)


def test_excessive_json_nesting_is_a_sanitized_parse_failure():
    depth = 10_000
    raw = '{"extra":' + "[" * depth + '"' + SECRET + '"' + "]" * depth + "}"
    error = rejected(raw)
    assert ("invalid_json", None) in issue_pairs(error)
    assert_private(error)


def test_diagnostics_are_bounded_for_a_large_number_of_unknown_fields():
    raw = payload(**{f"untrusted_{index}_{SECRET}": SECRET for index in range(100)})
    error = rejected(raw)
    assert 1 <= len(error.issues) <= 8
    assert_private(error)


@pytest.mark.parametrize("changes", [{"code": SECRET}, {"field": SECRET}, {SECRET: SECRET}])
def test_diagnostics_accept_only_allowlisted_codes_and_fields(changes):
    with pytest.raises(ValidationError):
        OutputIssue.model_validate({"code": "invalid_json", "field": None} | changes)


@pytest.mark.parametrize("count", [0, 9])
def test_repair_feedback_is_nonempty_and_bounded(count):
    issue = OutputIssue(code="invalid_json", field=None)
    with pytest.raises(ValidationError):
        OutputFeedback(issues=(issue,) * count)


def test_only_second_attempt_context_can_carry_repair_feedback():
    feedback = OutputFeedback(issues=(OutputIssue(code="missing_field", field="rationale"),))
    common = {
        "run_id": "run:1",
        "case_id": "case:1",
        "case_revision": 2,
        "output_feedback": feedback,
    }
    with pytest.raises(ValidationError):
        ReasoningContext(**common, attempt_index=1)
    assert ReasoningContext(**common, attempt_index=2).output_feedback == feedback


def test_run_receipt_can_keep_diagnostics_from_both_bounded_attempts():
    issue = OutputIssue(code="invalid_json", field=None)
    result = RunResult(
        run_id="run:1",
        case_id="case:1",
        case_revision=2,
        status="error",
        error_code="ModelOutputInvalid",
        output_issues=(issue,) * 16,
    )
    assert len(result.output_issues) == 16
    with pytest.raises(ValidationError):
        RunResult.model_validate(result.model_dump() | {"output_issues": (issue,) * 17})
