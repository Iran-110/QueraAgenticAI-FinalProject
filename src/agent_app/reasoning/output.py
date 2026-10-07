"""Strict decision parsing and bounded diagnostics without response content."""

import json
from collections.abc import Mapping

from pydantic import ValidationError

from agent_app.contracts import AnalysisResult, OutputIssue

_DECISION_FIELDS = {
    "retrieve_more_queries_required": "retrieval_queries",
    "retrieve_more_final_payload_forbidden": None,
    "final_drafts_required": None,
    "final_queries_forbidden": "retrieval_queries",
    "ask_question_required": "next_question",
    "question_forbidden": "next_question",
}


class InvalidAnalysis(Exception):
    def __init__(self, issues: tuple[OutputIssue, ...]) -> None:
        self.issues = issues
        super().__init__("ModelOutputInvalid")


class _DuplicateField(ValueError):
    pass


def _object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateField()
        result[key] = value
    return result


def _reject_constant(_: str) -> None:
    raise ValueError()


def _issues(error: ValidationError) -> tuple[OutputIssue, ...]:
    issues: list[OutputIssue] = []
    for item in error.errors(include_input=False, include_context=False, include_url=False):
        location = item["loc"]
        # Extra keys, nested paths, messages and inputs can contain model text.
        # Export only a known top-level field and a code we define ourselves.
        field = location[0] if location and location[0] in AnalysisResult.model_fields else None
        code = {"missing": "missing_field", "extra_forbidden": "unknown_field"}.get(
            item["type"], "invalid_field"
        )
        if not location and item["type"] in _DECISION_FIELDS:
            code = item["type"]
            field = _DECISION_FIELDS[code]
        issue = OutputIssue(code=code, field=field)
        if issue not in issues:
            issues.append(issue)
        if len(issues) == 8:
            break
    return tuple(issues) or (OutputIssue(code="invalid_field"),)


def parse_analysis(raw: object) -> AnalysisResult:
    """Accept one bare JSON object or a port model/mapping; never extract prose."""
    if isinstance(raw, str):
        try:
            if len(raw.encode("utf-8")) > 262_144:
                raise InvalidAnalysis((OutputIssue(code="output_too_large"),))
            raw = json.loads(raw, object_pairs_hook=_object, parse_constant=_reject_constant)
        except _DuplicateField:
            raise InvalidAnalysis((OutputIssue(code="duplicate_field"),)) from None
        except (ValueError, UnicodeError, RecursionError):
            raise InvalidAnalysis((OutputIssue(code="invalid_json"),)) from None
    elif isinstance(raw, AnalysisResult):
        raw = raw.model_dump(warnings=False)
    elif isinstance(raw, Mapping):
        raw = dict(raw)
    if not isinstance(raw, dict):
        raise InvalidAnalysis((OutputIssue(code="invalid_shape"),))
    try:
        return AnalysisResult.model_validate(raw)
    except ValidationError as error:
        raise InvalidAnalysis(_issues(error)) from None
