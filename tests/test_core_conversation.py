"""Input-preservation checks; authored ports do not establish model quality."""

import json
from pathlib import Path

import pytest

from agent_app.contracts import (
    CaseState,
    ConversationEntry,
    ReportedFact,
    TurnConversation,
    UserTurn,
)
from agent_app.demo import SNAPSHOT_ID, _answer, _evidence
from agent_app.orchestration import SupportEngine
from agent_app.orchestration.conversation import ConversationRejected, build_reasoning_message
from agent_app.orchestration.engine import build_initial_query
from agent_app.orchestration.handoff import ReasoningCapture, build_handoff
from agent_app.orchestration.intake import STREAMLIT_VERSION_QUESTION
from agent_app.testing.fakes import FakeReasoner, FakeRetriever
from agent_app.tracker.sqlite_tracker import SQLiteCaseTracker

FIXTURE = Path(__file__).resolve().parents[1] / "data/evaluation/dev/pilot-12782.json"
PROBLEM = json.loads(FIXTURE.read_text())["turns"][0]["visible"]["message"]
QUESTION = STREAMLIT_VERSION_QUESTION.question


def entry(actor, reference_id, revision, text):
    return ConversationEntry(actor=actor, reference_id=reference_id, revision=revision, text=text)


def conversation(*entries, latest_message=None, binding=None):
    latest = entries[-1]
    return TurnConversation(
        entries=entries,
        latest_turn_id=latest.reference_id,
        committed_revision=latest.revision,
        latest_message=latest.text if latest_message is None else latest_message,
        reply_to_proposal_id=binding,
    )


def version_reply():
    return conversation(
        entry("user", "initial", 1, PROBLEM),
        entry("assistant", "approved-question", 1, QUESTION),
        entry("user", "reply", 2, "1.50.0"),
        binding="approved-question",
    )


def run(case, message):
    retriever = FakeRetriever([_evidence("source", "Authored offline evidence.")])
    capture = ReasoningCapture(FakeReasoner([_answer("source")]))
    result = SupportEngine(retriever, capture, snapshot_id=SNAPSHOT_ID).run(
        case, message, run_id="conversation-fixture-run"
    )
    return result, capture, retriever


def test_initial_input_preserves_exact_normalized_user_text():
    text = "My widget loses its value.\n\n```python\nx =  1\n```"
    assert build_reasoning_message(conversation(entry("user", "initial", 1, text))) == text


def test_short_approved_version_reply_preserves_real_dev_complaint_in_query_and_handoff():
    message = build_reasoning_message(version_reply())
    case = CaseState(case_id="fixture", case_revision=2)
    query = build_initial_query(case, message)
    for term in ("multiselect", "saved default", "parent selector"):
        assert term in query
    assert PROBLEM in message
    assert QUESTION in message
    assert message.endswith("1.50.0")
    result, capture, retriever = run(case, message)
    assert result.status == "awaiting_approval"
    assert retriever.requests[0].queries == (query,)
    assert capture.last.user_message == message
    handoff = build_handoff(result, capture.last)
    assert handoff.user_message == message
    assert len(capture.reasoner.inputs) == 1


def test_old_answers_are_excluded_and_prior_versions_remain_historical_user_context():
    history = conversation(
        entry("user", "initial", 1, PROBLEM),
        entry("assistant", "old-answer", 1, "UNTRUSTED OLD EVIDENCE: use obsolete workaround"),
        entry("user", "old-reply", 2, "1.50.0"),
        entry("assistant", "latest-question", 2, QUESTION),
        entry("user", "new-reply", 3, "1.49.1"),
        binding="latest-question",
    )
    message = build_reasoning_message(history)
    assert "UNTRUSTED OLD EVIDENCE" not in message
    assert "obsolete workaround" not in message
    assert "1.50.0" in message
    assert "Prior user message (historical context; not current facts; event=old-reply" in message
    assert message.count(QUESTION) == 1
    assert PROBLEM in message
    assert message.endswith("1.49.1")


def test_intermediate_widget_code_survives_short_version_reply_in_reasoning_and_handoff():
    code = (
        "The widget definition is:\n```python\n"
        "selected = st.multiselect('City', ['A', 'B'], key='city')\n```"
    )
    history = conversation(
        entry("user", "initial", 1, PROBLEM),
        entry("assistant", "old-answer", 1, "OLD ANSWER CLAIM: an obsolete fix is established."),
        entry("user", "widget-code", 2, code),
        entry("assistant", "version-question", 2, QUESTION),
        entry("user", "reply", 3, "1.50.0"),
        binding="version-question",
    )
    message = build_reasoning_message(history)
    assert PROBLEM in message
    assert code in message
    assert QUESTION in message
    assert message.endswith("1.50.0")
    assert "OLD ANSWER CLAIM" not in message
    assert message.index(PROBLEM) < message.index(code) < message.index(QUESTION)
    case = CaseState(case_id="fixture", case_revision=3)
    result, capture, retriever = run(case, message)
    assert result.status == "awaiting_approval"
    assert "multiselect" in retriever.requests[0].queries[0]
    assert code in capture.last.user_message
    handoff = build_handoff(result, capture.last)
    assert code in handoff.user_message
    assert handoff.case.facts == ()


def test_all_prior_user_messages_count_toward_combined_input_limit():
    history = conversation(
        entry("user", "initial", 1, "A widget loses its saved default."),
        entry("user", "code", 2, "x" * 10_000),
        entry("assistant", "old-answer", 2, "Excluded assistant text."),
        entry("user", "detail", 3, "y" * 10_000),
        entry("user", "latest", 4, "Additional information."),
    )
    with pytest.raises(ConversationRejected, match="ConversationTooLong"):
        build_reasoning_message(history)


def test_question_is_not_inferred_without_the_tracker_validated_reply_binding():
    history = version_reply().model_copy(update={"reply_to_proposal_id": None})
    message = build_reasoning_message(history)
    assert QUESTION not in message
    assert PROBLEM in message
    assert message.endswith("1.50.0")


@pytest.mark.parametrize(
    "change",
    [
        {"latest_turn_id": "other-event"},
        {"committed_revision": 3},
        {"latest_message": "1.49.1"},
        {"reply_to_proposal_id": "other-question"},
    ],
)
def test_latest_receipt_or_question_binding_mismatch_is_rejected(change):
    with pytest.raises(ConversationRejected, match="ConversationMismatch"):
        build_reasoning_message(version_reply().model_copy(update=change))


@pytest.mark.parametrize(
    "entries,binding",
    [
        (
            (entry("assistant", "question", 1, QUESTION), entry("user", "reply", 2, "1.50.0")),
            "question",
        ),
        ((entry("user", "initial", 2, PROBLEM), entry("user", "reply", 1, "1.50.0")), None),
        ((entry("user", "initial", 1, PROBLEM), entry("user", "initial", 2, "1.50.0")), None),
        ((entry("user", "initial", 1, PROBLEM), entry("user", "reply", 1, "1.50.0")), None),
        (
            (
                entry("user", "initial", 1, PROBLEM),
                entry("assistant", "question", 1, "Could you try this workaround?"),
                entry("user", "reply", 2, "1.50.0"),
            ),
            "question",
        ),
        (
            (
                entry("user", "initial", 1, PROBLEM),
                entry("assistant", "question", 1, QUESTION),
                entry("user", "intervening", 2, "some other context"),
                entry("user", "reply", 3, "1.50.0"),
            ),
            "question",
        ),
    ],
)
def test_invalid_order_or_unbound_historical_question_is_rejected(entries, binding):
    with pytest.raises(ConversationRejected, match="ConversationMismatch"):
        build_reasoning_message(conversation(*entries, binding=binding))


def test_oversized_combined_context_is_rejected_without_truncating_either_message():
    original = "Original complaint. " + "x" * 11_000
    latest = "Latest user detail. " + "y" * 11_000
    history = conversation(
        entry("user", "initial", 1, original), entry("user", "latest", 2, latest)
    )
    with pytest.raises(ConversationRejected, match="ConversationTooLong"):
        build_reasoning_message(history)
    assert history.entries[0].text == original
    assert history.latest_message == latest


def test_bypass_constructed_input_is_revalidated_without_leaking_text():
    secret = "untrusted-value-must-not-appear"
    tampered = version_reply().model_copy(update={secret: secret})
    with pytest.raises(ConversationRejected) as error:
        build_reasoning_message(tampered)
    assert error.value.code == "InvalidConversationInput"
    assert secret not in str(error.value)


def test_nested_extra_storage_cannot_disappear_during_conversation_validation():
    history = version_reply()
    nested = history.entries[0].model_copy(deep=True)
    object.__setattr__(nested, "__pydantic_extra__", {"private-extra": "private-value"})
    history = history.model_copy(update={"entries": (nested, *history.entries[1:])})
    with pytest.raises(ConversationRejected) as error:
        build_reasoning_message(history)
    assert error.value.code == "InvalidConversationInput"
    assert "private-" not in str(error.value)


def test_historical_version_never_restores_superseded_fact_or_changes_ingress(tmp_path):
    tracker = SQLiteCaseTracker(tmp_path / "conversation.db", reviewer_tokens={})
    original_text = "My multiselect loses its saved default after rerun. I am using 1.50.0."
    original = UserTurn(
        case_id="correction",
        turn_id="initial",
        expected_revision=0,
        source_ref="user:initial",
        message=original_text,
        reported_facts=(ReportedFact(name="streamlit_version", value="1.50.0"),),
    )
    tracker.apply_turn(original)
    correction = UserTurn(
        case_id=original.case_id,
        turn_id="correction",
        expected_revision=1,
        source_ref="user:correction",
        message="Correction: the affected environment is 1.49.1.",
        reported_facts=(ReportedFact(name="streamlit_version", value="1.49.1"),),
    )
    receipt = tracker.apply_turn(correction)
    before = tracker.read_case(original.case_id)
    raw_event = correction.model_dump(mode="json")
    history = TurnConversation(
        entries=tuple(ConversationEntry.model_validate(item) for item in before["history"]),
        latest_turn_id=receipt["turn_id"],
        committed_revision=receipt["committed_revision"],
        latest_message=correction.message,
    )
    message = build_reasoning_message(history)
    assert original_text in message
    assert "historical context; not current facts" in message
    assert "superseded values" in message
    assert message.endswith(correction.message)
    case = CaseState.model_validate(before["state"])
    result, capture, _retriever = run(case, message)
    assert result.status == "awaiting_approval"
    assert [(fact.value, fact.status) for fact in capture.last.case.facts] == [
        ("1.50.0", "superseded"),
        ("1.49.1", "active"),
    ]
    assert tracker.read_case(original.case_id) == before
    assert correction.model_dump(mode="json") == raw_event
    assert message != correction.message
    assert tracker.apply_turn(correction) == {**receipt, "replayed": True}
