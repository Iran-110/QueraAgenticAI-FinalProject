"""Schema diagnostics never quote provider bodies, validation inputs or names."""

import json

import pytest

from agent_app.contracts import GroundedPlan
from agent_app.testing import plan_observation
from agent_app.testing.plan_observation import observe_plan_output

CONTEXT = "a" * 64
PRIVATE = "private-provider-marker"


def raw_plan(**changes):
    return json.dumps({"context_sha256": CONTEXT, "decision": "escalate", **changes})


def assert_private(observation, *private_values):
    serialized = json.dumps(observation)
    for value in private_values:
        assert value not in serialized
    assert set(observation) == {
        "schema_version",
        "syntactic_valid",
        "diagnostic",
        "json_shape",
        "decision",
        "known_field_shapes",
        "missing_known_fields",
        "unexpected_field_count",
        "sources_count",
        "retrieval_queries_count",
        "validation_error_count",
        "validation_errors",
        "unreported_error_count",
    }
    assert set(observation["known_field_shapes"]) == set(GroundedPlan.model_fields)
    for error in observation["validation_errors"]:
        assert set(error) == {"field", "code", "count"}
        assert type(error["count"]) is int and error["count"] > 0


@pytest.mark.parametrize(
    "plan",
    [
        {"decision": "escalate"},
        {"decision": "ask", "question_name": PRIVATE},
        {"decision": "answer", "sources": [{"chunk_id": PRIVATE, "content_sha256": "b" * 64}]},
        {"decision": "retrieve_more", "retrieval_queries": [PRIVATE]},
    ],
)
def test_valid_plan_is_described_without_copying_context_questions_sources_or_queries(plan):
    result = observe_plan_output(raw_plan(**plan))
    assert result["syntactic_valid"] is True and result["diagnostic"] == "GroundedPlanValid"
    assert result["decision"] == plan["decision"]
    assert result["validation_error_count"] == 0 and result["validation_errors"] == []
    assert_private(result, CONTEXT, "b" * 64, PRIVATE)


def test_syntactic_validity_does_not_claim_context_source_or_question_correctness():
    # This arbitrary hash/name satisfies the schema; no current request is supplied.
    result = observe_plan_output(raw_plan(decision="ask", question_name="not-a-reviewed-question"))
    assert result["syntactic_valid"] is True
    assert "grounded" not in result and "quality" not in result
    assert "not-a-reviewed-question" not in json.dumps(result)


def test_missing_known_fields_and_unexpected_field_count_explain_wrapped_outputs_privately():
    result = observe_plan_output(json.dumps({PRIVATE: {"context": PRIVATE, "decision": "ask"}}))
    assert result["syntactic_valid"] is False
    assert result["diagnostic"] == "GroundedPlanSchemaInvalid"
    assert result["missing_known_fields"] == ["context_sha256", "decision"]
    assert result["unexpected_field_count"] == 1 and result["validation_error_count"] == 3
    assert {item["code"] for item in result["validation_errors"]} == {"missing", "extra_forbidden"}
    assert_private(result, PRIVATE)


@pytest.mark.parametrize("decision", [PRIVATE, "ASK", {"private": PRIVATE}, 7, None])
def test_unknown_enum_values_never_appear_in_safe_decision_or_validation_messages(decision):
    result = observe_plan_output(raw_plan(decision=decision))
    assert not result["syntactic_valid"] and result["decision"] is None
    assert result["validation_errors"] == [
        {"field": "decision", "code": "literal_error", "count": 1}
    ]
    assert_private(result, PRIVATE, "ASK")


def test_source_validation_fields_are_known_without_unknown_names_ids_or_inputs():
    result = observe_plan_output(
        raw_plan(decision="answer", sources=[{"chunk_id": "x?" + PRIVATE, PRIVATE: PRIVATE}])
    )
    assert not result["syntactic_valid"]
    assert result["sources_count"] == 1 and result["unexpected_field_count"] == 1
    assert result["missing_known_fields"] == ["sources.content_sha256"]
    assert {item["field"] for item in result["validation_errors"]} == {
        "sources.chunk_id",
        "sources.content_sha256",
        "unrecognized_field",
    }
    assert_private(result, PRIVATE, "x?")


@pytest.mark.parametrize(
    "updates,code,field",
    [
        ({"context_sha256": PRIVATE}, "string_too_short", "context_sha256"),
        (
            {"question_name": "x?" + PRIVATE, "decision": "ask"},
            "string_pattern_mismatch",
            "question_name",
        ),
        ({"sources": PRIVATE}, "tuple_type", "sources"),
        (
            {"retrieval_queries": PRIVATE, "decision": "retrieve_more"},
            "tuple_type",
            "retrieval_queries",
        ),
        ({"decision": "answer", "sources": []}, "value_error", "plan"),
        ({"decision": "ask"}, "value_error", "plan"),
        ({"decision": "escalate", "retrieval_queries": [PRIVATE]}, "value_error", "plan"),
    ],
)
def test_known_validation_codes_are_projected_without_error_messages(updates, code, field):
    result = observe_plan_output(raw_plan(**updates))
    assert not result["syntactic_valid"]
    assert {"field": field, "code": code, "count": 1} in result["validation_errors"]
    assert_private(result, PRIVATE)


@pytest.mark.parametrize(
    "raw", ["", "```json\n" + PRIVATE, "{broken:" + PRIVATE, '"unclosed' + PRIVATE]
)
def test_malformed_json_has_only_fixed_diagnostics(raw):
    result = observe_plan_output(raw)
    assert not result["syntactic_valid"] and result["diagnostic"] == "GroundedPlanJsonInvalid"
    assert result["json_shape"] == "invalid" and result["validation_errors"] == []
    assert_private(result, PRIVATE)


@pytest.mark.parametrize(
    "value,shape",
    [
        ([PRIVATE], "array"),
        (PRIVATE, "string"),
        (None, "null"),
        (False, "boolean"),
        (123, "number"),
    ],
)
def test_nonobject_json_shape_is_fixed_and_its_value_is_not_exported(value, shape):
    result = observe_plan_output(json.dumps(value))
    assert not result["syntactic_valid"] and result["json_shape"] == shape
    assert result["decision"] is None and result["sources_count"] is None
    assert_private(result, PRIVATE)


@pytest.mark.parametrize(
    "value", [None, b"private-provider-marker", 42, [PRIVATE], {PRIVATE: PRIVATE}]
)
def test_nonstring_observer_inputs_do_not_create_raw_errors(value):
    result = observe_plan_output(value)
    assert result["diagnostic"] == "GroundedPlanOutputTypeInvalid"
    assert result["syntactic_valid"] is False
    assert_private(result, PRIVATE)


def test_output_size_guard_is_bounded_before_parsing_and_does_not_echo_content():
    result = observe_plan_output(PRIVATE + "x" * 262_144)
    assert result["diagnostic"] == "GroundedPlanOutputTooLarge"
    assert_private(result, PRIVATE)


def test_invalid_unicode_is_redacted_without_a_codec_exception():
    result = observe_plan_output(PRIVATE + "\ud800")
    assert result["diagnostic"] == "GroundedPlanJsonInvalid"
    assert_private(result, PRIVATE)


def test_many_unknown_fields_are_aggregated_as_counts_without_exporting_names():
    data = {f"{PRIVATE}-{index}": PRIVATE for index in range(200)}
    result = observe_plan_output(json.dumps(data))
    assert result["unexpected_field_count"] == 200
    assert result["validation_error_count"] == 202
    assert len(result["validation_errors"]) == 3
    assert {"field": "unrecognized_field", "code": "extra_forbidden", "count": 200} in result[
        "validation_errors"
    ]
    assert_private(result, PRIVATE)


def test_duplicate_source_references_return_only_a_model_validation_code():
    source = {"chunk_id": PRIVATE, "content_sha256": "b" * 64}
    result = observe_plan_output(raw_plan(decision="answer", sources=[source, source]))
    assert result["validation_errors"] == [{"field": "sources", "code": "value_error", "count": 1}]
    assert_private(result, PRIVATE, "b" * 64)


def test_query_item_error_is_mapped_to_known_field_without_the_query_text():
    result = observe_plan_output(
        raw_plan(decision="retrieve_more", retrieval_queries=[1, PRIVATE * 60])
    )
    assert result["retrieval_queries_count"] == 2
    assert {item["field"] for item in result["validation_errors"]} == {"retrieval_queries.item"}
    assert {item["code"] for item in result["validation_errors"]} == {
        "string_type",
        "string_too_long",
    }
    assert_private(result, PRIVATE)


def test_unrecognized_validation_codes_locations_messages_inputs_and_context_are_not_exported(
    monkeypatch,
):
    class PrivateValidationError(Exception):
        def errors(self, **options):
            assert options == {
                "include_url": False,
                "include_context": False,
                "include_input": False,
            }
            return [
                {
                    "type": PRIVATE,
                    "loc": (PRIVATE,),
                    "msg": PRIVATE,
                    "input": {PRIVATE: PRIVATE},
                    "ctx": {PRIVATE: PRIVATE},
                    "url": PRIVATE,
                }
            ]

    def rejected(_raw):
        raise PrivateValidationError(PRIVATE)

    monkeypatch.setattr(plan_observation, "ValidationError", PrivateValidationError)
    monkeypatch.setattr(GroundedPlan, "model_validate_json", rejected)
    result = observe_plan_output(raw_plan())
    assert result["validation_errors"] == [
        {"field": "unrecognized_field", "code": "unclassified_error", "count": 1}
    ]
    assert_private(result, PRIVATE)


def test_observer_metadata_failure_is_sanitized_and_does_not_change_model_validation(monkeypatch):
    class BrokenValidationError(Exception):
        def errors(self, **options):
            raise RuntimeError(PRIVATE)

    def rejected(_raw):
        raise BrokenValidationError(PRIVATE)

    monkeypatch.setattr(plan_observation, "ValidationError", BrokenValidationError)
    monkeypatch.setattr(GroundedPlan, "model_validate_json", rejected)
    result = observe_plan_output(raw_plan())
    assert result["diagnostic"] == "GroundedPlanObservationUnavailable"
    assert not result["syntactic_valid"]
    assert_private(result, PRIVATE)


def test_output_is_deterministic_and_caller_owned_data_is_not_mutated():
    raw = raw_plan(decision="answer", sources=[{PRIVATE: PRIVATE}])
    assert observe_plan_output(raw) == observe_plan_output(raw)
    assert raw == raw_plan(decision="answer", sources=[{PRIVATE: PRIVATE}])
