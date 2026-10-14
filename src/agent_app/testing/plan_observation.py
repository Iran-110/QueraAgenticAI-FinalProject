"""Allowlisted diagnostics for an untrusted GroundedPlan output.

This observer never changes validation, prompts, decisions or accounting. Schema
validity does not establish context freshness, source support or useful questions.
Provider output, validation inputs/messages and unknown names stay private.
"""

import json
from collections import Counter

from pydantic import ValidationError

from agent_app.contracts import GroundedPlan, GroundedSourceRef

__all__ = ["observe_plan_output"]

_FIELDS = frozenset(GroundedPlan.model_fields)
_SOURCE_FIELDS = frozenset(GroundedSourceRef.model_fields)
_DECISIONS = frozenset(("answer", "ask", "escalate", "retrieve_more"))
_ERROR_CODES = frozenset(
    (
        "missing",
        "extra_forbidden",
        "literal_error",
        "string_type",
        "string_pattern_mismatch",
        "string_too_short",
        "string_too_long",
        "tuple_type",
        "list_type",
        "too_long",
        "too_short",
        "value_error",
        "model_type",
        "model_attributes_type",
        "json_invalid",
    )
)
_MAX_BYTES = 262_144
_MAX_ERROR_GROUPS = 16


def _shape(value):
    if value is None:
        return "null"
    if type(value) is bool:
        return "boolean"
    if type(value) in (int, float):
        return "number"
    if type(value) is str:
        return "string"
    if type(value) is list:
        return "array"
    if type(value) is dict:
        return "object"
    return "unrecognized"


def _known_field(location):
    if type(location) not in (tuple, list):
        return "unrecognized_field"
    if not location:
        return "plan"
    first = location[0]
    if type(first) is not str or first not in _FIELDS:
        return "unrecognized_field"
    if len(location) == 1:
        return first
    if first == "sources" and type(location[1]) is int and location[1] >= 0:
        if len(location) == 2:
            return "sources.item"
        if len(location) == 3 and type(location[2]) is str and location[2] in _SOURCE_FIELDS:
            return "sources." + location[2]
    if first == "retrieval_queries" and len(location) == 2 and type(location[1]) is int:
        return "retrieval_queries.item"
    return "unrecognized_field"


def _base():
    return {
        "schema_version": 1,
        "syntactic_valid": False,
        "diagnostic": "GroundedPlanObservationUnavailable",
        "json_shape": "unrecognized",
        "decision": None,
        "known_field_shapes": {field: "missing" for field in sorted(_FIELDS)},
        "missing_known_fields": [],
        "unexpected_field_count": 0,
        "sources_count": None,
        "retrieval_queries_count": None,
        "validation_error_count": 0,
        "validation_errors": [],
        "unreported_error_count": 0,
    }


def observe_plan_output(raw: str) -> dict:
    """Describe schema failure with fixed codes, known fields and aggregate counts.

    No provider text or unknown field/enum value is returned. `syntactic_valid`
    means GroundedPlan validation succeeded; semantic grounding is checked by
    the existing core and separately reviewed against the current request.
    """
    observation = _base()
    if type(raw) is not str:
        observation["diagnostic"] = "GroundedPlanOutputTypeInvalid"
        return observation
    try:
        if len(raw.encode("utf-8")) > _MAX_BYTES:
            observation["diagnostic"] = "GroundedPlanOutputTooLarge"
            return observation
        parsed = json.loads(raw)
    except (UnicodeError, ValueError, RecursionError):
        observation["diagnostic"] = "GroundedPlanJsonInvalid"
        observation["json_shape"] = "invalid"
        return observation
    observation["json_shape"] = _shape(parsed)
    if type(parsed) is dict:
        for field in _FIELDS:
            if field in parsed:
                observation["known_field_shapes"][field] = _shape(parsed[field])
        decision = parsed.get("decision")
        if type(decision) is str and decision in _DECISIONS:
            observation["decision"] = decision
        unexpected = sum(key not in _FIELDS for key in parsed)
        sources = parsed.get("sources")
        if type(sources) is list:
            observation["sources_count"] = len(sources)
            unexpected += sum(
                sum(key not in _SOURCE_FIELDS for key in item)
                for item in sources
                if type(item) is dict
            )
        queries = parsed.get("retrieval_queries")
        if type(queries) is list:
            observation["retrieval_queries_count"] = len(queries)
        observation["unexpected_field_count"] = unexpected
    try:
        GroundedPlan.model_validate_json(raw)
    except ValidationError as failure:
        try:
            errors = failure.errors(include_url=False, include_context=False, include_input=False)
            groups = Counter()
            missing = set()
            for error in errors:
                code = error.get("type")
                code = code if type(code) is str and code in _ERROR_CODES else "unclassified_error"
                field = _known_field(error.get("loc"))
                groups[(field, code)] += 1
                if code == "missing" and field not in ("plan", "unrecognized_field"):
                    missing.add(field)
            selected = sorted(groups.items())[:_MAX_ERROR_GROUPS]
            observation["validation_errors"] = [
                {"field": field, "code": code, "count": count} for (field, code), count in selected
            ]
            observation["missing_known_fields"] = sorted(missing)
            observation["validation_error_count"] = len(errors)
            observation["unreported_error_count"] = len(errors) - sum(
                count for _, count in selected
            )
            observation["diagnostic"] = "GroundedPlanSchemaInvalid"
        except Exception:
            # Observer failure never exports raw validation metadata or retries.
            observation["diagnostic"] = "GroundedPlanObservationUnavailable"
        return observation
    except Exception:
        return observation
    observation["syntactic_valid"] = True
    observation["diagnostic"] = "GroundedPlanValid"
    return observation
