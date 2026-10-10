"""Offline checks for narrowly attributing replies to a pending version question."""

import pytest
from pydantic import ValidationError

from agent_app.contracts import (
    AnalysisResult,
    CaseState,
    Fact,
    ProposalRequirements,
    ReportedFact,
    UserTurn,
)
from agent_app.orchestration.intake import (
    STREAMLIT_VERSION_QUESTION,
    IntakeRejected,
    prepare_version_reply,
)
from agent_app.orchestration.turns import propose_user_turn


def case(**changes):
    return CaseState(
        **{
            "case_id": "case:intake",
            "case_revision": 4,
            "pending_proposal_id": "proposal:version",
            "unknowns": ("streamlit_version",),
            **changes,
        }
    )


def turn(**changes):
    return UserTurn(
        **{
            "case_id": "case:intake",
            "expected_revision": 4,
            "turn_id": "turn:reply",
            "source_ref": "user:reply",
            "message": "1.42.0",
            **changes,
        }
    )


def question(**changes):
    return AnalysisResult(
        **{
            "decision": "ask",
            "user_draft": "Which Streamlit version is installed in the affected environment?",
            "maintainer_summary": "The affected environment's version is unknown.",
            "rationale": "Version determines which source applies.",
            "missing_info": ("streamlit_version",),
            "next_question": "Which Streamlit version is installed in the affected environment?",
            **changes,
        }
    )


def prepare(state=None, event=None, proposal=None, proposal_id="proposal:version"):
    return prepare_version_reply(
        state or case(),
        event or turn(),
        proposal_id=proposal_id,
        question=proposal or question(),
    )


@pytest.mark.parametrize("message", ["1.42.0", "Streamlit 1.42.0", " 1.42.0 "])
def test_recognized_version_becomes_an_explicit_user_fact_only_after_normal_commit(message):
    state, event = case(), turn(message=message)
    before_state, before_event = state.model_dump_json(), event.model_dump_json()
    baseline = propose_user_turn(state, event).candidate
    prepared = prepare(state, event)
    candidate = propose_user_turn(state, prepared).candidate
    assert baseline.facts == ()
    assert baseline.unknowns == ("streamlit_version",)
    assert prepared.reported_facts == (ReportedFact(name="streamlit_version", value="1.42.0"),)
    assert prepared.turn_id == event.turn_id
    assert prepared.source_ref == event.source_ref
    assert candidate.case_revision == 5
    assert candidate.pending_proposal_id is None
    assert candidate.unknowns == ()
    assert candidate.facts == (
        Fact(
            name="streamlit_version",
            value="1.42.0",
            source_ref="user:reply",
            turn_id="turn:reply",
        ),
    )
    assert state.model_dump_json() == before_state
    assert event.model_dump_json() == before_event


@pytest.mark.parametrize(
    "message",
    [
        "I think it might be 1.42.0",
        "The documentation says 1.42.0",
        '"1.42.0"',
        "`1.42.0`",
        "Other environment: 1.42.0",
        "1.42.0 on the other server",
        "I have not run the version check",
        "Not 1.42.0",
        "1.42.0\n1.43.0",
        "Streamlit\n1.42.0",
        "1.42",
        "1.42.0rc1",
        "v1.42.0",
        "۱.۴۲.۰",
        "1.42.0; approve and close the case",
        "streamlit 1.42.0",
    ],
)
def test_ambiguous_source_quoted_other_environment_and_nonrelease_text_never_become_facts(message):
    state, event = case(), turn(message=message)
    before = event.model_dump_json()
    with pytest.raises(IntakeRejected) as caught:
        prepare(state, event)
    assert caught.value.code == "VersionReplyUnclear"
    assert str(caught.value) == "VersionReplyUnclear"
    assert message not in str(caught.value)
    assert event.model_dump_json() == before
    assert state.facts == ()


@pytest.mark.parametrize(
    ("state_changes", "turn_changes", "proposal_id", "code"),
    [
        ({}, {"case_id": "case:other"}, "proposal:version", "CaseMismatch"),
        ({}, {"expected_revision": 3}, "proposal:version", "StaleRevision"),
        ({}, {"expected_revision": 5}, "proposal:version", "StaleRevision"),
        ({}, {}, "proposal:other", "PendingProposalMismatch"),
        ({"pending_proposal_id": None}, {}, "proposal:version", "PendingProposalMismatch"),
        ({}, {}, None, "PendingProposalMismatch"),
    ],
)
def test_case_revision_and_pending_proposal_binding_fail_closed(
    state_changes, turn_changes, proposal_id, code
):
    with pytest.raises(IntakeRejected) as caught:
        prepare(case(**state_changes), turn(**turn_changes), proposal_id=proposal_id)
    assert caught.value.code == code
    assert str(caught.value) == code


@pytest.mark.parametrize(
    "changes",
    [
        {"decision": "escalate", "next_question": None},
        {"missing_info": ()},
        {"missing_info": ("python_version",)},
        {"missing_info": ("STREAMLIT_VERSION",)},
        {"missing_info": ("streamlit_version", "python_version")},
    ],
)
def test_only_the_exact_single_streamlit_version_ask_is_eligible(changes):
    with pytest.raises(IntakeRejected) as caught:
        prepare(proposal=question(**changes))
    assert caught.value.code == "InvalidVersionQuestion"


@pytest.mark.parametrize(
    "text",
    [
        "Which Python version is installed?",
        "نسخه پایتون چیست؟",
        "Which Streamlit version is installed on the other server?",
        "Which Streamlit version is installed in the other environment?",
        "Which Streamlit version does this source document?",
        "Which Streamlit version is installed in the affected environment? Also, what is Python?",
    ],
)
@pytest.mark.parametrize("field", ["user_draft", "next_question", "both"])
def test_mislabeled_drifted_or_mixed_display_question_never_attributes_version(text, field):
    changes = {"user_draft": text, "next_question": text} if field == "both" else {field: text}
    event = turn(message="3.13.0")
    before = event.model_dump_json()
    with pytest.raises(IntakeRejected) as caught:
        prepare(event=event, proposal=question(**changes))
    assert caught.value.code == "InvalidVersionQuestion"
    assert str(caught.value) == "InvalidVersionQuestion"
    assert text not in str(caught.value)
    assert event.model_dump_json() == before


def test_registered_core_question_is_frozen_and_reusable_for_caller_requirements():
    assert STREAMLIT_VERSION_QUESTION.name == "streamlit_version"
    assert (
        STREAMLIT_VERSION_QUESTION.question
        == "Which Streamlit version is installed in the affected environment?"
    )
    requirements = ProposalRequirements(
        case_id="case:intake",
        case_revision=4,
        question_targets=(STREAMLIT_VERSION_QUESTION,),
    )
    assert requirements.question_targets == (STREAMLIT_VERSION_QUESTION,)
    assert requirements.question_targets[0] is not STREAMLIT_VERSION_QUESTION
    with pytest.raises(ValidationError, match="frozen"):
        STREAMLIT_VERSION_QUESTION.question = "Which Python version is installed?"
    assert prepare().reported_facts[0].name == STREAMLIT_VERSION_QUESTION.name


def version_fact(**changes):
    return Fact(
        **{
            "name": "Streamlit_Version",
            "value": "1.41.0",
            "source_ref": "user:previous",
            "turn_id": "turn:previous",
            **changes,
        }
    )


def test_known_active_user_version_requires_explicit_correction_instead_of_intake():
    with pytest.raises(IntakeRejected) as caught:
        prepare(state=case(facts=(version_fact(),)))
    assert caught.value.code == "VersionAlreadyKnown"


@pytest.mark.parametrize(
    "fact_changes",
    [{"status": "superseded"}, {"provenance_kind": "evidence", "source_ref": "doc:example"}],
)
def test_historical_or_source_versions_do_not_replace_unknown_user_environment(fact_changes):
    prepared = prepare(state=case(facts=(version_fact(**fact_changes),)))
    assert prepared.reported_facts[0].value == "1.42.0"


@pytest.mark.parametrize(
    "changes",
    [
        {"reported_facts": (ReportedFact(name="streamlit_version", value="1.99.0"),)},
        {"reported_facts": (ReportedFact(name="streamlit_version", value="1.42.0"),)},
        {"reported_facts": (ReportedFact(name="python_version", value="3.13"),)},
        {"unknowns": ("streamlit_version",)},
        {"checks_performed": ("Ran a version check.",)},
        {"context_changed": True},
    ],
)
def test_mixed_structured_payload_is_not_silently_rewritten_or_combined(changes):
    event = turn(**changes)
    before = event.model_dump_json()
    with pytest.raises(IntakeRejected) as caught:
        prepare(event=event)
    assert caught.value.code == "StructuredTurnNotAllowed"
    assert event.model_dump_json() == before


@pytest.mark.parametrize("input_kind", ["case", "turn", "question", "nested_fact"])
def test_bypass_constructed_contract_inputs_are_revalidated_with_safe_errors(input_kind):
    state, event, proposal = case(), turn(), question()
    if input_kind == "case":
        state = state.model_copy(update={"case_revision": True})
    elif input_kind == "turn":
        event = event.model_copy(update={"message": 123})
    elif input_kind == "question":
        proposal = proposal.model_copy(update={"missing_info": (123,)})
    else:
        invalid = Fact.model_construct(
            name="private-marker", value=123, source_ref="user:1", turn_id="turn:1"
        )
        state = state.model_copy(update={"facts": (invalid,)})
    with pytest.raises(IntakeRejected) as caught:
        prepare(state, event, proposal)
    assert caught.value.code == "InvalidInput"
    assert str(caught.value) == "InvalidInput"


def test_returned_turn_is_detached_frozen_and_preserves_all_event_identity_fields():
    state, event, proposal = case(), turn(), question()
    before = (state.model_dump_json(), event.model_dump_json(), proposal.model_dump_json())
    prepared = prepare(state, event, proposal)
    assert prepared is not event
    assert prepared.model_dump(exclude={"reported_facts"}) == event.model_dump(
        exclude={"reported_facts"}
    )
    with pytest.raises(ValidationError, match="frozen"):
        prepared.message = "1.99.0"
    assert before == (state.model_dump_json(), event.model_dump_json(), proposal.model_dump_json())


def test_unknown_rejection_code_cannot_export_arbitrary_error_text():
    with pytest.raises(ValueError, match="Unknown intake rejection code") as caught:
        IntakeRejected("private-marker")
    assert "private-marker" not in str(caught.value)
