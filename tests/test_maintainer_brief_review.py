"""Independent neutral checks of validation before opt-in presentation."""

import pytest
from test_maintainer_review_brief import MODES, grounded, inputs, render

from agent_app.reasoning import review_brief
from agent_app.reasoning.grounding import (
    UNRESOLVED_SOURCE_CONFLICT,
    GroundingRejected,
    make_grounded_request,
)


def _must_not_format(monkeypatch):
    def fail(*args, **kwargs):
        pytest.fail("Rejected input reached the presentation formatter")

    monkeypatch.setattr(review_brief, "format_review_brief", fail)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("storage", ("attribute", "extra", "private"))
def test_hidden_nested_user_state_rejects_before_brief(monkeypatch, mode, storage):
    _must_not_format(monkeypatch)
    _, req, body = inputs(mode)
    current = req if mode == "grounded" else req.grounded
    fact = current.case.facts[0].model_copy(deep=True)
    if storage == "attribute":
        fact = fact.model_copy(update={"NEUTRAL_UNDECLARED": "NEUTRAL_VALUE"})
    else:
        object.__setattr__(
            fact,
            "__pydantic_extra__" if storage == "extra" else "__pydantic_private__",
            {"NEUTRAL_UNDECLARED": "NEUTRAL_VALUE"},
        )
    changed = current.model_copy(
        update={"case": current.case.model_copy(update={"facts": (fact, *current.case.facts[1:])})}
    )
    req = changed if mode == "grounded" else req.model_copy(update={"grounded": changed})
    with pytest.raises(GroundingRejected, match="^grounded_context_mismatch$"):
        render(mode, req, body, review_brief=True)


@pytest.mark.parametrize("mode", MODES)
def test_source_gap_cannot_become_a_canonical_question_in_brief(monkeypatch, mode):
    _must_not_format(monkeypatch)
    _, req, body = inputs(mode, "ask")
    body["question_name"] = "applicable_docs"
    with pytest.raises(GroundingRejected, match="^grounded_question_invalid$"):
        render(mode, req, body, review_brief=True)


@pytest.mark.parametrize("mode", MODES)
def test_invalid_current_selection_rejects_before_brief(monkeypatch, mode):
    _must_not_format(monkeypatch)
    _, req, body = inputs(mode)
    if mode == "grounded":
        body["sources"][0]["content_sha256"] = "0" * 64
    else:
        body["passages"] = [[0, len(req.blocks[0])]]
    with pytest.raises(GroundingRejected, match="^grounded_source_mismatch$"):
        render(mode, req, body, review_brief=True)


@pytest.mark.parametrize("mode", MODES)
def test_prior_conflict_still_rejects_answer_before_brief(monkeypatch, mode):
    _must_not_format(monkeypatch)
    current = grounded()
    current = make_grounded_request(
        current.case,
        current.user_message,
        current.evidence,
        gaps=(*current.gaps, UNRESOLVED_SOURCE_CONFLICT),
    )
    _, req, body = inputs(mode, "answer", req=current)
    with pytest.raises(GroundingRejected, match="^grounded_conflict_unresolved$"):
        render(mode, req, body, review_brief=True)


@pytest.mark.parametrize("mode", MODES)
def test_changed_user_report_rejects_old_plan_before_brief(monkeypatch, mode):
    _must_not_format(monkeypatch)
    current, _, body = inputs(mode)
    current = make_grounded_request(
        current.case,
        current.user_message + "\nA newly reported qualification.",
        current.evidence,
        gaps=current.gaps,
    )
    _, req, _ = inputs(mode, req=current)
    with pytest.raises(GroundingRejected, match="^grounded_context_mismatch$"):
        render(mode, req, body, review_brief=True)
