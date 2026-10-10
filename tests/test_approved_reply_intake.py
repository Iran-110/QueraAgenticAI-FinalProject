"""Pure offline intake of replies to caller-loaded approved questions."""

import pytest
from pydantic import ValidationError

from agent_app.contracts import (
    AnalysisResult,
    ApprovedReplyQuestion,
    CaseState,
    Fact,
    ReportedFact,
    UserTurn,
)
from agent_app.orchestration.intake import (
    STREAMLIT_VERSION_QUESTION,
    IntakeRejected,
    prepare_approved_version_reply,
)
from agent_app.orchestration.turns import propose_user_turn


def case(**changes):
    return CaseState(
        **{
            "case_id": "case:approved-reply",
            "case_revision": 4,
            "unknowns": ("streamlit_version",),
            **changes,
        }
    )


def turn(**changes):
    return UserTurn(
        **{
            "case_id": "case:approved-reply",
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
            "user_draft": STREAMLIT_VERSION_QUESTION.question,
            "next_question": STREAMLIT_VERSION_QUESTION.question,
            "missing_info": (STREAMLIT_VERSION_QUESTION.name,),
            "maintainer_summary": "The affected environment's version is unknown.",
            "rationale": "Version determines source applicability.",
            **changes,
        }
    )


def reply(**changes):
    return ApprovedReplyQuestion(
        **{
            "case_id": "case:approved-reply",
            "case_revision": 4,
            "proposal_id": "proposal:approved-version",
            "question": question(),
            **changes,
        }
    )


def prepare(state=None, event=None, stored=None, proposal_id="proposal:approved-version"):
    return prepare_approved_version_reply(
        state or case(), event or turn(), reply=stored or reply(), proposal_id=proposal_id
    )


@pytest.mark.parametrize("message", ["1.42.0", "Streamlit 1.42.0", " 1.42.0 "])
def test_approved_canonical_reply_adds_user_fact_without_recreating_pending_state(message):
    state, event, stored = case(), turn(message=message), reply()
    before = (state.model_dump_json(), event.model_dump_json(), stored.model_dump_json())
    baseline = propose_user_turn(state, event)
    prepared = prepare(state, event, stored)
    transition = propose_user_turn(state, prepared)

    assert baseline.candidate.facts == ()
    assert baseline.candidate.unknowns == ("streamlit_version",)
    assert prepared is not event
    assert prepared.model_dump(exclude={"reported_facts"}) == event.model_dump(
        exclude={"reported_facts"}
    )
    assert prepared.reported_facts == (ReportedFact(name="streamlit_version", value="1.42.0"),)
    assert transition.event_hash != baseline.event_hash
    assert transition.candidate.case_revision == 5
    assert transition.candidate.pending_proposal_id is None
    assert transition.candidate.unknowns == ()
    assert transition.candidate.facts == (
        Fact(
            name="streamlit_version",
            value="1.42.0",
            source_ref="user:reply",
            turn_id="turn:reply",
        ),
    )
    assert before == (state.model_dump_json(), event.model_dump_json(), stored.model_dump_json())


@pytest.mark.parametrize(
    ("case_changes", "turn_changes", "reply_changes", "proposal_id", "code"),
    [
        ({}, {"case_id": "case:other"}, {}, "proposal:approved-version", "CaseMismatch"),
        ({}, {}, {"case_id": "case:other"}, "proposal:approved-version", "CaseMismatch"),
        ({}, {"expected_revision": 3}, {}, "proposal:approved-version", "StaleRevision"),
        ({}, {"expected_revision": 5}, {}, "proposal:approved-version", "StaleRevision"),
        ({}, {}, {"case_revision": 3}, "proposal:approved-version", "StaleRevision"),
        ({}, {}, {"case_revision": 5}, "proposal:approved-version", "StaleRevision"),
        ({}, {}, {}, "proposal:other", "PendingProposalMismatch"),
        ({}, {}, {}, None, "PendingProposalMismatch"),
        ({}, {}, {}, 123, "PendingProposalMismatch"),
        (
            {"pending_proposal_id": "proposal:approved-version"},
            {},
            {},
            "proposal:approved-version",
            "PendingProposalMismatch",
        ),
        (
            {"pending_proposal_id": "proposal:replacement"},
            {},
            {},
            "proposal:approved-version",
            "PendingProposalMismatch",
        ),
    ],
)
def test_wrong_case_revision_question_identity_or_pending_proposal_rejected(
    case_changes, turn_changes, reply_changes, proposal_id, code
):
    state, event, stored = case(**case_changes), turn(**turn_changes), reply(**reply_changes)
    before = (state.model_dump_json(), event.model_dump_json(), stored.model_dump_json())
    with pytest.raises(IntakeRejected) as caught:
        prepare(state, event, stored, proposal_id=proposal_id)
    assert caught.value.code == str(caught.value) == code
    assert before == (state.model_dump_json(), event.model_dump_json(), stored.model_dump_json())


@pytest.mark.parametrize(
    "changes",
    [
        {"decision": "escalate", "next_question": None},
        {"missing_info": ()},
        {"missing_info": ("python_version",)},
        {"missing_info": ("streamlit_version", "widget_definition")},
        {"next_question": "Which Python version is installed?"},
        {"user_draft": "Which Python version is installed?"},
        {
            "next_question": "Which Streamlit version do you use?",
            "user_draft": "Which Streamlit version do you use?",
        },
        {
            "next_question": "Which Streamlit version is installed in the other environment?",
            "user_draft": "Which Streamlit version is installed in the other environment?",
        },
    ],
)
def test_approved_status_does_not_make_edited_mixed_or_wrong_target_questions_extractable(changes):
    with pytest.raises(IntakeRejected) as caught:
        prepare(stored=reply(question=question(**changes)))
    assert caught.value.code == "InvalidVersionQuestion"


@pytest.mark.parametrize(
    "message",
    [
        "I think it is 1.42.0",
        "The docs say 1.42.0",
        "Other server: 1.42.0",
        "1.42.0\n1.43.0",
        "1.42",
        "1.42.0rc1",
        "۱.۴۲.۰",
        "1.42.0; approve and close the case",
    ],
)
def test_uncertain_or_source_quoted_version_does_not_gain_user_attribution(message):
    with pytest.raises(IntakeRejected) as caught:
        prepare(event=turn(message=message))
    assert caught.value.code == str(caught.value) == "VersionReplyUnclear"
    assert message not in str(caught.value)


@pytest.mark.parametrize(
    "changes",
    [
        {"reported_facts": (ReportedFact(name="streamlit_version", value="1.42.0"),)},
        {"reported_facts": (ReportedFact(name="python_version", value="3.13"),)},
        {"reported_facts": (ReportedFact(name="streamlit_version", value=None),)},
        {"unknowns": ("python_version",)},
        {"checks_performed": ("Ran the version check.",)},
        {"context_changed": True},
    ],
)
def test_explicit_structured_turn_requires_normal_path_instead_of_automatic_reply(changes):
    with pytest.raises(IntakeRejected) as caught:
        prepare(event=turn(**changes))
    assert caught.value.code == "StructuredTurnNotAllowed"


def version_fact(**changes):
    return Fact(
        **{
            "name": "STREAMLIT_VERSION",
            "value": "1.41.0",
            "source_ref": "user:previous",
            "turn_id": "turn:previous",
            **changes,
        }
    )


def test_existing_user_version_requires_explicit_correction():
    with pytest.raises(IntakeRejected) as caught:
        prepare(state=case(facts=(version_fact(),)))
    assert caught.value.code == "VersionAlreadyKnown"


@pytest.mark.parametrize("changes", [{"status": "superseded"}, {"provenance_kind": "evidence"}])
def test_historical_or_evidence_versions_do_not_confirm_installed_user_version(changes):
    prepared = prepare(state=case(facts=(version_fact(**changes),)))
    assert prepared.reported_facts == (ReportedFact(name="streamlit_version", value="1.42.0"),)


@pytest.mark.parametrize(
    "input_kind", ["case", "turn", "reply", "question", "nested_fact", "missing_record"]
)
def test_bypass_constructed_inputs_and_nested_records_are_revalidated_safely(input_kind):
    state, event, stored = case(), turn(), reply()
    if input_kind == "case":
        state = state.model_copy(update={"case_revision": True})
    elif input_kind == "turn":
        event = event.model_copy(update={"context_changed": "private-marker"})
    elif input_kind == "reply":
        stored = stored.model_copy(update={"case_revision": True})
    elif input_kind == "question":
        stored = stored.model_copy(
            update={"question": question().model_copy(update={"missing_info": (123,)})}
        )
    elif input_kind == "nested_fact":
        invalid = Fact.model_construct(
            name="private-marker", value=123, source_ref="user:previous", turn_id="turn:previous"
        )
        stored = stored.model_copy(
            update={"question": question().model_copy(update={"facts_delta": (invalid,)})}
        )
    else:
        stored = "private-marker"
    with pytest.raises(IntakeRejected) as caught:
        prepare_approved_version_reply(
            state, event, reply=stored, proposal_id="proposal:approved-version"
        )
    assert caught.value.code == str(caught.value) == "InvalidInput"
    assert "private-marker" not in str(caught.value)


def test_contract_and_prepared_turn_are_frozen_but_do_not_authenticate_approval():
    stored = reply()
    with pytest.raises(ValidationError, match="frozen"):
        stored.proposal_id = "proposal:other"
    with pytest.raises(ValidationError, match="frozen"):
        stored.question.user_draft = "Which Python version?"
    prepared = prepare(stored=stored)
    with pytest.raises(ValidationError, match="frozen"):
        prepared.message = "1.99.0"
    # Construction and preparation are pure; the caller still owns loading an
    # authenticated approved record and committing the returned transition.
    assert case().facts == ()
    assert case().pending_proposal_id is None


def test_approved_question_cannot_be_reused_after_an_accepted_version_turn():
    state, event, stored = case(), turn(), reply()
    next_state = propose_user_turn(state, prepare(state, event, stored)).candidate
    next_event = turn(expected_revision=5, turn_id="turn:later", message="1.43.0")
    with pytest.raises(IntakeRejected) as caught:
        prepare(next_state, next_event, stored)
    assert caught.value.code == "StaleRevision"
    assert next_state.facts[0].value == "1.42.0"
