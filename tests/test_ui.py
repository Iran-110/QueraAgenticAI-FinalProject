from pathlib import Path

import pytest
import streamlit as st
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from agent_app import api, ui_client
from agent_app.tracker.dummy_tracker import DummyTracker

PAGE = str(Path(__file__).resolve().parent.parent / "app_pages" / "assistant.py")


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
    assert len(at.chat_message) == 1  # The draft stays hidden until approval.
    at.button(key="approve").click().run()
    assert not at.exception
    assert len(at.chat_message) == 2
    assert "Which Streamlit version" in at.chat_message[1].markdown[0].value


def test_edit_then_approve(backend):
    at = AppTest.from_file(PAGE).run()
    at.chat_input[0].set_value("My widget loses its value.").run()
    at.button(key="edit").click().run()
    at.text_area(key="edited_draft").set_value("Which version do you use?")
    at.button[[b.label for b in at.button].index("Save as new proposal")].click().run()
    assert not at.exception
    assert len(at.chat_message) == 1
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
    assert at.session_state.unsent is None


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
    at.text_input(key="version_reply").set_value("1.50.0")
    at.button[[b.label for b in at.button].index("Send reply")].click().run()
    assert not at.exception
    facts = next(df.value for df in at.dataframe if "Status" in df.value.columns)
    assert list(facts["Name"]) == ["streamlit_version"]
    assert list(facts["Value"]) == ["1.50.0"]
    assert list(facts["Status"]) == ["active"]


def test_unclear_version_reply_is_explained(backend):
    at = AppTest.from_file(PAGE).run()
    select_scenario(at, "ask_version")
    at.chat_input[0].set_value("My widget loses its value.").run()
    at.button(key="approve").click().run()
    at.text_input(key="version_reply").set_value("the latest one")
    at.button[[b.label for b in at.button].index("Send reply")].click().run()
    assert "release number only" in at.error[0].value
    assert at.session_state.unsent is None


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
    assert at.session_state.unsent == sent[0]
    at.button[[b.label for b in at.button].index("Retry sending")].click().run()
    assert sent[1] == sent[0]
    assert at.session_state.unsent is None
    assert "Already received" in at.info[0].value
    assert len(at.chat_message) == 1  # Replay did not duplicate the message.


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
