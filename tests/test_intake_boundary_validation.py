"""Offline C2j: typed version-reply boundaries reject bypassed object state."""

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

import pytest
from pydantic import BaseModel

from agent_app.contracts import (
    AnalysisResult,
    ApprovedReplyQuestion,
    CaseState,
    EvidenceLink,
    Fact,
    ReportedFact,
    UserTurn,
)
from agent_app.orchestration import intake
from agent_app.orchestration.turns import propose_user_turn

_PRIVATE_MARKER = "untrusted-boundary-marker"
_BASELINE_PATH = (
    Path(__file__).resolve().parents[1] / "experiments/intake_validation_v1/valid-baseline-v1.json"
)
_BASELINE_SHA256 = "fdd9e418fa37ebe6900fc1b8b55d3d213bea4b4938aa331694ad7f1c618aa399"


def _baseline_rows():
    payload = _BASELINE_PATH.read_bytes()
    assert hashlib.sha256(payload).hexdigest() == _BASELINE_SHA256
    baseline = json.loads(payload)
    assert baseline["row_count"] == len(baseline["rows"]) == 16
    return baseline["rows"]


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _inputs(mode):
    fact = Fact(
        name="python_version",
        value="3.13.0",
        source_ref="user:previous",
        turn_id="turn:previous",
    )
    state = CaseState(
        case_id="case:boundary",
        case_revision=4,
        pending_proposal_id="proposal:version" if mode == "pending" else None,
        facts=(fact,),
        unknowns=("streamlit_version",),
    )
    event = UserTurn(
        case_id=state.case_id,
        expected_revision=4,
        turn_id="turn:reply",
        source_ref="user:reply",
        message="1.42.0",
    )
    question = AnalysisResult(
        decision="ask",
        user_draft=intake.STREAMLIT_VERSION_QUESTION.question,
        next_question=intake.STREAMLIT_VERSION_QUESTION.question,
        missing_info=("streamlit_version",),
        maintainer_summary="The installed Streamlit version remains unknown.",
        rationale="The installed version selects applicable documentation.",
        facts_delta=(fact.model_copy(),),
        evidence_links=(EvidenceLink(claim="Version-scoped documentation.", chunk_id="doc:1"),),
    )
    record = (
        question
        if mode == "pending"
        else ApprovedReplyQuestion(
            case_id=state.case_id,
            case_revision=4,
            proposal_id="proposal:version",
            question=question,
        )
    )
    return state, event, record


def _question(mode, record):
    return record if mode == "pending" else record.question


def _prepare(mode, state, event, record):
    if mode == "pending":
        return intake.prepare_version_reply(
            state, event, proposal_id="proposal:version", question=record
        )
    return intake.prepare_approved_version_reply(
        state, event, proposal_id="proposal:version", reply=record
    )


def _snapshot(value):
    """Include bypassed state without serializing, mutating or recursing forever."""
    seen = set()

    def visit(item):
        if isinstance(item, (BaseModel, Mapping, list, tuple)):
            if id(item) in seen:
                return ("reference", id(item))
            seen.add(id(item))
        if isinstance(item, BaseModel):
            return (
                type(item).__name__,
                visit(item.__dict__),
                visit(item.__pydantic_extra__),
                visit(item.__pydantic_private__),
            )
        if isinstance(item, Mapping):
            return (type(item).__name__, tuple((visit(k), visit(v)) for k, v in item.items()))
        if isinstance(item, (list, tuple)):
            return (type(item).__name__, tuple(visit(child) for child in item))
        return (type(item).__name__, repr(item))

    return visit(value)


def _rejects_without_extraction_or_mutation(monkeypatch, mode, inputs):
    before = _snapshot(inputs)
    calls = []
    original = intake._prepare_canonical_version_reply

    def observed_extraction(*args):
        calls.append(True)
        return original(*args)

    monkeypatch.setattr(intake, "_prepare_canonical_version_reply", observed_extraction)
    with pytest.raises(intake.IntakeRejected) as caught:
        _prepare(mode, *inputs)
    assert caught.value.code == str(caught.value) == "InvalidInput"
    assert caught.value.args == ("InvalidInput",)
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__ is True
    assert _PRIVATE_MARKER not in str(caught.value)
    assert calls == []
    assert _snapshot(inputs) == before


def _target(mode, inputs, name):
    state, event, record = inputs
    question = _question(mode, record)
    targets = {
        "case": state,
        "turn": event,
        "question": question,
        "case_fact": state.facts[0],
        "question_fact": question.facts_delta[0],
        "question_link": question.evidence_links[0],
        "reply": record,
    }
    if name == "reported_fact":
        reported = ReportedFact(name="python_version", value="3.13.0")
        object.__setattr__(event, "reported_facts", (reported,))
        return reported
    return targets[name]


@pytest.mark.parametrize("mode", ["pending", "approved"])
@pytest.mark.parametrize(
    "target_name",
    ["case", "turn", "question", "case_fact", "question_fact", "question_link", "reported_fact"],
)
def test_unknown_constructed_fields_are_rejected_at_every_nested_contract(
    monkeypatch, mode, target_name
):
    inputs = _inputs(mode)
    _target(mode, inputs, target_name).__dict__[_PRIVATE_MARKER] = _PRIVATE_MARKER
    _rejects_without_extraction_or_mutation(monkeypatch, mode, inputs)


@pytest.mark.parametrize("mode", ["pending", "approved"])
@pytest.mark.parametrize("target_name", ["case", "question", "question_link"])
@pytest.mark.parametrize("metadata", ["__pydantic_extra__", "__pydantic_private__"])
def test_hidden_pydantic_metadata_is_not_silently_discarded(
    monkeypatch, mode, target_name, metadata
):
    inputs = _inputs(mode)
    object.__setattr__(
        _target(mode, inputs, target_name), metadata, {_PRIVATE_MARKER: _PRIVATE_MARKER}
    )
    _rejects_without_extraction_or_mutation(monkeypatch, mode, inputs)


@pytest.mark.parametrize("metadata", ["__dict__", "__pydantic_extra__", "__pydantic_private__"])
def test_approved_record_itself_is_validated_before_question_extraction(monkeypatch, metadata):
    inputs = _inputs("approved")
    stored = inputs[2]
    if metadata == "__dict__":
        stored.__dict__[_PRIVATE_MARKER] = _PRIVATE_MARKER
    else:
        object.__setattr__(stored, metadata, {_PRIVATE_MARKER: _PRIVATE_MARKER})
    _rejects_without_extraction_or_mutation(monkeypatch, "approved", inputs)


@pytest.mark.parametrize("mode", ["pending", "approved"])
@pytest.mark.parametrize(
    "target_name,field,value",
    [("case", "case_revision", True), ("turn", "message", 123), ("question_link", "claim", 123)],
)
def test_existing_declared_type_rejections_keep_the_same_safe_boundary(
    monkeypatch, mode, target_name, field, value
):
    inputs = _inputs(mode)
    object.__setattr__(_target(mode, inputs, target_name), field, value)
    _rejects_without_extraction_or_mutation(monkeypatch, mode, inputs)


@pytest.mark.parametrize("mode", ["pending", "approved"])
@pytest.mark.parametrize("shape", ["cycle", "excess_depth"])
def test_recursive_constructed_values_fail_closed_without_altering_original_graph(
    monkeypatch, mode, shape
):
    inputs = _inputs(mode)
    if shape == "cycle":
        malformed = []
        malformed.append(malformed)
    else:
        malformed = _PRIVATE_MARKER
        for _ in range(70):
            malformed = (malformed,)
    object.__setattr__(inputs[0], "checks_performed", malformed)
    _rejects_without_extraction_or_mutation(monkeypatch, mode, inputs)


@pytest.mark.parametrize("row", _baseline_rows(), ids=lambda row: row["id"])
def test_valid_prepared_output_transition_and_input_bytes_match_frozen_baseline(row):
    payload = row["input_contracts"]["json"]
    state = CaseState.model_validate(payload["case"])
    event = UserTurn.model_validate(payload["turn"])
    pending = row["helper"] == "prepare_version_reply"
    record_field = "question" if pending else "reply"
    record_model = AnalysisResult if pending else ApprovedReplyQuestion
    record = record_model.model_validate(payload[record_field])
    original_objects = (state, event, record)
    before_graph = _snapshot(original_objects)

    def input_bytes():
        return _canonical(
            {
                "case": state.model_dump(mode="json"),
                "turn": event.model_dump(mode="json"),
                record_field: record.model_dump(mode="json"),
                "proposal_id": payload["proposal_id"],
            }
        )

    assert input_bytes() == row["input_contracts"]["canonical_json"]
    if pending:
        prepared = intake.prepare_version_reply(
            state, event, proposal_id=payload["proposal_id"], question=record
        )
    else:
        prepared = intake.prepare_approved_version_reply(
            state, event, proposal_id=payload["proposal_id"], reply=record
        )
    transition = propose_user_turn(state, prepared)

    for actual, expected_field in (
        (prepared, "prepared_user_turn"),
        (transition, "proposed_transition"),
    ):
        actual_json = _canonical(actual.model_dump(mode="json"))
        expected = row[expected_field]
        assert actual_json == expected["canonical_json"]
        assert hashlib.sha256(actual_json.encode()).hexdigest() == expected["canonical_sha256"]
    assert prepared is not event
    assert _snapshot(original_objects) == before_graph
    assert input_bytes() == row["input_contracts"]["canonical_json"]
    assert (
        hashlib.sha256(input_bytes().encode()).hexdigest()
        == row["input_contracts_after_call_sha256"]
    )
