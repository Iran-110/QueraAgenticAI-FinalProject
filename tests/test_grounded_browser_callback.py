"""Exercise review callback through app.py navigation, not the standalone page."""

from pathlib import Path

import streamlit as st
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from agent_app import ui_client
from agent_app.offline_backend import configured_app
from agent_app.retrieval.offline_index import build_index
from agent_app.retrieval.pilot_corpus import build_pilot_corpus
from agent_app.testing.http_pilot_runtime import offline_network

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "public-synthetic-main-navigation-review-credential"


def test_main_navigation_approve_uses_the_displayed_case_and_canonical_proposal(
    tmp_path, monkeypatch
):
    st.cache_resource.clear()
    try:
        with offline_network():
            corpus = build_pilot_corpus(
                ROOT / "streamlit-data-for-dev-test",
                ROOT / "data/evaluation/split-manifest.json",
                ROOT / "experiments/corpus/pilot-allowlist.json",
            )
            snapshot = build_index(corpus, tmp_path / "index")
            config = {
                "AGENT_TRACKER_DB": str(tmp_path / "navigation.sqlite3"),
                "AGENT_REVIEWER_TOKEN": TOKEN,
                "AGENT_PILOT_INDEX": str(tmp_path / "index"),
                "AGENT_PILOT_SNAPSHOT": snapshot,
                "AGENT_PILOT_REASONING": "grounded_fake_gateway",
            }
            with TestClient(configured_app(config)) as backend:
                shared_client = ui_client.BackendClient(backend, reviewer_token=TOKEN)
                monkeypatch.setattr(ui_client, "make_client", lambda: shared_client)
                at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=15).run()
                assert not at.exception
                selector = at.sidebar.selectbox(key="case_id")
                initial_options = list(selector.options)
                initial_widget_id = selector.proto.id
                initial_generation = at.session_state.form_gen

                def stable_case_selector():
                    current_selector = at.sidebar.selectbox(key="case_id")
                    assert current_selector.options == initial_options
                    assert current_selector.proto.id == initial_widget_id

                at.chat_input[0].set_value(
                    "My widget resets on rerun; the installed version is unknown."
                ).run()
                assert not at.exception
                stable_case_selector()
                assert at.session_state.form_gen == initial_generation
                case_id = at.session_state.case_id
                current = shared_client.get_case(case_id)
                assert current["pending"] is not None and current["actions"] == []
                # The independently read proposal is valid before the callback.
                probe = shared_client.prepare_review(case_id, current["pending"], "approve")
                assert probe.case_id == case_id
                at.button(key="approve").click().run()
                assert not at.exception
                stable_case_selector()
                assert at.session_state.form_gen == initial_generation
                latest = shared_client.get_case(case_id)
                assert latest["status"] == "awaiting_user"
                assert len(latest["actions"]) == 1
                assert at.session_state.unsent_reviews == {}
                assert at.session_state.case_id == case_id
                # Changing the case status must not impersonate a user changing
                # cases and clear the freshly submitted version_reply widget.
                at.chat_input[0].set_value("1.50.0").run()
                assert not at.exception
                stable_case_selector()
                assert at.session_state.form_gen == initial_generation
                known = shared_client.get_case(case_id)
                assert known["case_revision"] == 2
                assert any(
                    fact["name"] == "streamlit_version"
                    and fact["value"] == "1.50.0"
                    and fact["status"] == "active"
                    for fact in known["facts"]
                )
                generation = at.session_state.form_gen
                at.text_area(key=f"update_message_{generation}").set_value(
                    "Correction: the affected version is 1.49.0."
                )
                at.text_input(key=f"fact_name_0_{generation}").set_value("streamlit_version")
                at.text_input(key=f"fact_value_0_{generation}").set_value("1.49.0")
                next(item for item in at.button if item.label == "Send update").click().run()
                assert not at.exception
                stable_case_selector()
                corrected = shared_client.get_case(case_id)
                assert corrected["case_revision"] == 3
                assert len(corrected["actions"]) == 1
                assert corrected["pending"]["proposal_id"] != known["pending"]["proposal_id"]
                assert at.session_state.case_id == case_id
                assert at.session_state.form_gen == initial_generation + 1
                assert TOKEN not in repr(at.session_state)
    finally:
        st.cache_resource.clear()
