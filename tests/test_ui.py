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
