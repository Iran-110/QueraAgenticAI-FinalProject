from pathlib import Path

import httpx
import pytest
import streamlit as st
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from agent_app import api, ui_client
from agent_app.contracts import EvidenceLink
from agent_app.tracker.dummy_tracker import DummyTracker

PAGE = str(Path(__file__).resolve().parent.parent / "app_pages" / "assistant.py")


def released(at):
    """Conversation turns the user received; a draft waiting for approval is not one."""
    return [
        message
        for message in at.chat_message
        if not any("Waiting for approval" in md.value for md in message.markdown)
    ]


@pytest.fixture(autouse=True)
def fresh_client():
    st.cache_resource.clear()
    yield
    st.cache_resource.clear()


@pytest.fixture
def backend(monkeypatch):
    monkeypatch.setattr(api, "_cases", {})
    monkeypatch.setattr(api, "tracker", DummyTracker())
    http = TestClient(api.app, base_url="http://backend")
    monkeypatch.setattr(ui_client, "make_client", lambda: ui_client.BackendClient(http))


def test_page_explains_missing_backend(monkeypatch):
    monkeypatch.setenv("AGENT_API_URL", "http://127.0.0.1:9")
    at = AppTest.from_file(PAGE).run()
    assert not at.exception
    assert "Cannot reach the backend" in at.error[0].value


def test_message_review_and_approve(backend):
    at = AppTest.from_file(PAGE).run()
    assert not at.exception
    at.chat_input[0].set_value("My widget loses its value.").run()
    assert at.button(key="approve")
    assert len(released(at)) == 1  # The draft is not released until approval.
    assert len(at.chat_message) == 2  # It is shown as a waiting chat bubble.
    at.button(key="approve").click().run()
    assert not at.exception
    assert len(at.chat_message) == len(released(at)) == 2
    assert "Which Streamlit version" in at.chat_message[1].markdown[0].value


def test_edit_then_approve(backend):
    at = AppTest.from_file(PAGE).run()
    at.chat_input[0].set_value("My widget loses its value.").run()
    at.button(key="edit").click().run()
    at.text_area(key="edited_draft").set_value("Which version do you use?")
    at.button[[b.label for b in at.button].index("Save as new proposal")].click().run()
    assert not at.exception
    assert len(released(at)) == 1
    at.button(key="approve").click().run()
    assert at.chat_message[1].markdown[0].value == "Which version do you use?"


def select_scenario(at, scenario):
    at.selectbox(key="scenario").set_value(scenario).run()


def test_chat_messages_use_stable_event_ids(backend, monkeypatch):
    sent = []
    original = ui_client.BackendClient.send_event

    def spy(self, case_id, event):
        sent.append(event)
        return original(self, case_id, event)

    monkeypatch.setattr(ui_client.BackendClient, "send_event", spy)
    at = AppTest.from_file(PAGE).run()
    at.chat_input[0].set_value("My widget loses its value.").run()
    assert sent[0]["turn_id"].startswith("ui-")
    assert sent[0]["expected_revision"] == 0
    assert at.session_state.unsent == {}


def test_proposal_shows_all_sources_and_version_scope(backend):
    at = AppTest.from_file(PAGE).run()
    select_scenario(at, "answer")
    at.chat_input[0].set_value("How can I keep a counter?").run()
    assert not at.exception
    text = " ".join(md.value for md in at.markdown)
    assert "Cited" in text  # st.badge renders as Markdown.
    assert "Version unconfirmed" in text
    assert "1 supplied, 1 cited" in text


def test_structured_update_records_check_and_context(backend):
    at = AppTest.from_file(PAGE).run()
    at.text_area(key="update_message_0").set_value("I moved to a new server.")
    at.text_area(key="update_checks_0").set_value("Cleared the browser cache")
    at.toggle(key="update_context_0").set_value(True)
    at.button[[b.label for b in at.button].index("Send update")].click().run()
    assert not at.exception
    assert at.session_state.form_gen == 1  # Success starts a blank form.
    assert any("Cleared the browser cache" in md.value for md in at.markdown)
    assert any("Context changed: yes" in md.value for md in at.markdown)


def test_version_reply_binds_to_approved_question(backend):
    at = AppTest.from_file(PAGE).run()
    select_scenario(at, "ask_version")
    at.chat_input[0].set_value("My widget loses its value.").run()
    at.button(key="approve").click().run()
    assert "Streamlit version" in at.chat_input[0].placeholder
    at.chat_input[0].set_value("1.50.0").run()  # Same chat box answers the question.
    assert not at.exception
    facts = next(df.value for df in at.dataframe if "Status" in df.value.columns)
    assert list(facts["Name"]) == ["streamlit_version"]
    assert list(facts["Value"]) == ["1.50.0"]
    assert list(facts["Status"]) == ["active"]


def test_non_version_text_while_asked_is_a_normal_message(backend):
    at = AppTest.from_file(PAGE).run()
    select_scenario(at, "ask_version")
    at.chat_input[0].set_value("My widget loses its value.").run()
    at.button(key="approve").click().run()
    at.chat_input[0].set_value("the latest one").run()
    assert not at.exception and not at.error
    assert at.session_state.unsent == {}
    assert released(at)[-1].markdown[0].value == "the latest one"
    facts = [df.value for df in at.dataframe if "Status" in df.value.columns]
    assert not facts or "streamlit_version" not in list(facts[0]["Name"])


def test_lost_message_retries_with_identical_event(backend, monkeypatch):
    sent = []
    original = ui_client.BackendClient.send_event

    def flaky(self, case_id, event):
        sent.append(event)
        if len(sent) == 1:
            original(self, case_id, event)  # Arrives, but the response is lost.
            raise ui_client.BackendError("Cannot reach the backend.", retryable=True)
        return original(self, case_id, event)

    monkeypatch.setattr(ui_client.BackendClient, "send_event", flaky)
    at = AppTest.from_file(PAGE).run()
    at.chat_input[0].set_value("My widget loses its value.").run()
    assert at.session_state.unsent == {at.session_state.case_id: sent[0]}
    at.button[[b.label for b in at.button].index("Retry sending")].click().run()
    assert sent[1] == sent[0]
    assert at.session_state.unsent == {}
    assert "Already received" in at.info[0].value
    assert len(released(at)) == 1  # Replay did not duplicate the message.


def test_mode_switch_keeps_live_and_replay_cases_apart(backend, monkeypatch):
    monkeypatch.setenv("AGENT_REPLAY_API_URL", "http://replay")
    live = ui_client.make_client()
    replay = ui_client.BackendClient(
        TestClient(api.app, base_url="http://replay"), reviewer_token=None
    )
    monkeypatch.setattr(
        ui_client, "make_client", lambda base_url=None: replay if base_url else live
    )
    at = AppTest.from_file(PAGE).run()
    assert at.session_state.active_mode == "Live"
    at.chat_input[0].set_value("Live question.").run()
    live_case = at.session_state.case_id
    at.segmented_control(key="mode").set_value("Replay").run()
    assert not at.exception
    assert at.session_state.active_mode == "Replay"
    assert at.session_state.case_id != live_case
    assert not at.chat_message  # The replay mode starts its own empty case.
    at.chat_input[0].set_value("Replay question.").run()
    assert any("Replay · no model call" in md.value for md in at.markdown)
    at.segmented_control(key="mode").set_value("Live").run()
    assert at.session_state.case_id == live_case
    assert released(at)[0].markdown[0].value == "Live question."


def test_without_replay_backend_there_is_no_mode_switch(backend):
    at = AppTest.from_file(PAGE).run()
    assert not [w for w in at.segmented_control if w.key == "mode"]


def test_slow_live_run_shows_calm_still_working_state(backend, monkeypatch):
    sent = []
    original = ui_client.BackendClient.send_event

    def slow(self, case_id, event):
        sent.append(event)
        if len(sent) == 1:
            original(self, case_id, event)  # The run finishes after the UI timeout.
            raise ui_client.BackendError(
                ui_client.ERROR_TEXT["BackendStillWorking"],
                code="BackendStillWorking",
                retryable=True,
            )
        return original(self, case_id, event)

    monkeypatch.setattr(ui_client.BackendClient, "send_event", slow)
    at = AppTest.from_file(PAGE).run()
    at.chat_input[0].set_value("My widget loses its value.").run()
    assert not at.error
    assert "still working" in at.info[0].value
    labels = [b.label for b in at.button]
    assert "Retry sending" not in labels
    at.button[labels.index("Check again")].click().run()
    assert sent[1] == sent[0]
    assert at.session_state.unsent == {} and at.session_state.still_working == {}
    assert at.button(key="approve")


def test_read_timeout_is_reported_as_still_working():
    def timeout(request):
        raise httpx.ReadTimeout("slow", request=request)

    client = ui_client.BackendClient(
        httpx.Client(transport=httpx.MockTransport(timeout), base_url="http://backend")
    )
    with pytest.raises(ui_client.BackendError) as raised:
        client.get_case("case-a")
    assert raised.value.code == "BackendStillWorking" and raised.value.retryable


def send_update(at, message, facts=(), gen=0):
    at.text_area(key=f"update_message_{gen}").set_value(message)
    for index, (name, value) in enumerate(facts):
        at.text_input(key=f"fact_name_{index}_{gen}").set_value(name)
        if value is None:
            at.checkbox(key=f"fact_withdraw_{index}_{gen}").check()
        else:
            at.text_input(key=f"fact_value_{index}_{gen}").set_value(value)
    at.button[[b.label for b in at.button].index("Send update")].click().run()
    assert not at.exception


def facts_table(at):
    return next(df.value for df in at.dataframe if "Status" in df.value.columns)


def test_correction_supersedes_fact_and_stales_pending_proposal(backend):
    at = AppTest.from_file(PAGE).run()
    select_scenario(at, "answer")
    send_update(at, "The app uses Streamlit 1.50.0.", [("streamlit_version", "1.50.0")])
    assert at.button(key="approve")
    send_update(at, "Correction: it is 1.49.1.", [("streamlit_version", "1.49.1")], gen=1)
    facts = facts_table(at)
    assert list(zip(facts["Value"], facts["Status"], strict=True)) == [
        ("1.50.0", "superseded"),
        ("1.49.1", "active"),
    ]
    assert any("Changed facts: streamlit_version" in md.value for md in at.markdown)


def test_withdrawn_fact_becomes_unknown(backend):
    at = AppTest.from_file(PAGE).run()
    select_scenario(at, "error")
    send_update(at, "Version 1.50.0.", [("streamlit_version", "1.50.0")])
    send_update(at, "I am not sure of the version.", [("streamlit_version", None)], gen=1)
    assert list(facts_table(at)["Status"]) == ["superseded"]
    assert any("- streamlit_version" in md.value for md in at.markdown)


def test_rejected_update_keeps_typed_input(backend):
    at = AppTest.from_file(PAGE).run()
    send_update(at, "Two values.", [("python_version", "3.12"), ("python_version", "3.13")])
    assert at.error  # Duplicate fact names are rejected by the API.
    assert at.session_state.form_gen == 0
    assert at.text_area(key="update_message_0").value == "Two values."


def new_case(at):
    at.button[[b.label for b in at.button].index("New case")].click().run()


def test_switching_cases_keeps_each_case_state(backend):
    at = AppTest.from_file(PAGE).run()
    first = at.session_state.case_id
    at.chat_input[0].set_value("My widget loses its value.").run()
    assert at.button(key="approve")  # Case 1 now has a proposal awaiting review.
    new_case(at)
    second = at.session_state.case_id
    assert second != first
    assert at.session_state.cases == [first, second]
    assert not at.chat_message  # The new case starts empty.
    assert any("1 case(s) awaiting review" in caption.value for caption in at.sidebar.caption)
    at.sidebar.selectbox(key="case_id").set_value(first).run()
    assert not at.exception
    assert at.button(key="approve")  # The pending proposal is still there.
    assert at.chat_message[0].markdown[0].value == "My widget loses its value."


def test_switcher_keeps_case_identity_while_panel_reports_status(backend):
    at = AppTest.from_file(PAGE).run()
    at.chat_input[0].set_value("My widget loses its value.").run()
    options = at.sidebar.selectbox(key="case_id").options
    assert options == [at.session_state.case_id]
    assert any("Awaiting maintainer review" in item.value for item in at.markdown)
    at.button(key="approve").click().run()
    assert not at.exception
    assert at.sidebar.selectbox(key="case_id").options == options
    assert any("Waiting for the user" in item.value for item in at.markdown)


def test_unsent_message_stays_with_its_case(backend, monkeypatch):
    def lost(self, case_id, event):
        raise ui_client.BackendError("Cannot reach the backend.", retryable=True)

    monkeypatch.setattr(ui_client.BackendClient, "send_event", lost)
    at = AppTest.from_file(PAGE).run()
    first = at.session_state.case_id
    at.chat_input[0].set_value("My widget loses its value.").run()
    assert "Retry sending" in [b.label for b in at.button]
    new_case(at)
    assert "Retry sending" not in [b.label for b in at.button]
    at.sidebar.selectbox(key="case_id").set_value(first).run()
    assert "Retry sending" in [b.label for b in at.button]
    assert list(at.session_state.unsent) == [first]


def test_rejected_correction_form_does_not_move_into_another_case(backend):
    at = AppTest.from_file(PAGE).run()
    first = at.session_state.case_id
    send_update(
        at, "Case A correction", [("streamlit_version", "1.49.1"), ("streamlit_version", "1.50.0")]
    )
    assert at.error
    assert at.text_area(key="update_message_0").value == "Case A correction"
    new_case(at)
    second = at.session_state.case_id
    assert second != first
    assert at.session_state.form_gen == 1
    assert at.text_area(key="update_message_1").value == ""
    assert at.text_input(key="fact_name_0_1").value == ""
    assert at.text_input(key="fact_value_0_1").value == ""
    send_update(at, "Case B has Python 3.12", [("python_version", "3.12")], gen=1)
    assert list(facts_table(at)["Name"]) == ["python_version"]
    assert all("Case A" not in msg.markdown[0].value for msg in at.chat_message)
    at.sidebar.selectbox(key="case_id").set_value(first).run()
    assert at.session_state.form_gen == 3  # Send and case switch each use fresh widgets.
    assert at.text_area(key="update_message_3").value == ""
    assert not at.dataframe


def test_source_review_preserves_every_declared_claim_for_the_same_chunk(backend, monkeypatch):
    bundles, outputs = api._script("answer")
    chunk_id = outputs[0].evidence_links[0].chunk_id
    outputs[0] = outputs[0].model_copy(
        update={
            "evidence_links": (
                EvidenceLink(
                    claim="First declaration to inspect against this source.", chunk_id=chunk_id
                ),
                EvidenceLink(
                    claim="Second declaration to inspect against this source.", chunk_id=chunk_id
                ),
            )
        }
    )
    monkeypatch.setattr(api, "_script", lambda _scenario: (bundles, outputs))
    at = AppTest.from_file(PAGE).run()
    select_scenario(at, "answer")
    at.chat_input[0].set_value("Review both source declarations.").run()
    assert not at.exception
    assert [caption.value for caption in at.caption if caption.value.startswith("Claim:")] == [
        "Claim: First declaration to inspect against this source.",
        "Claim: Second declaration to inspect against this source.",
    ]
