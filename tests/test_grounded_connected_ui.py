"""Actual Streamlit page/index/persistent HTTP with an explicitly mocked gateway."""

import copy
from pathlib import Path
from types import SimpleNamespace

import httpx
import streamlit as st
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from agent_app import ui_client
from agent_app.contracts import ProposalHandoff
from agent_app.offline_backend import configured_app
from agent_app.orchestration.handoff import validate_handoff
from agent_app.orchestration.intake import STREAMLIT_VERSION_QUESTION
from agent_app.retrieval.offline_index import build_index
from agent_app.retrieval.pilot_corpus import build_pilot_corpus
from agent_app.testing.http_pilot_runtime import offline_network
from agent_app.tracker.sqlite_tracker import SQLiteCaseTracker

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "synthetic-connected-grounded-page-review-credential"


def _button(at, label):
    return next(button for button in at.button if button.label == label)


def _correction(at, version):
    generation = at.session_state.form_gen
    at.text_area(key=f"update_message_{generation}").set_value(f"Correction: {version}.")
    at.text_input(key=f"fact_name_0_{generation}").set_value("streamlit_version")
    at.text_input(key=f"fact_value_0_{generation}").set_value(version)
    _button(at, "Send update").click().run()
    assert not at.exception


def _handoff(view):
    handoff = validate_handoff(ProposalHandoff.model_validate(view["pending"]["review_handoff"]))
    assert handoff.grounded_request is not None
    assert handoff.grounded_request.case == handoff.case
    assert handoff.grounded_request.evidence == handoff.evidence
    assert handoff.grounded_request.user_message == handoff.user_message
    return handoff


def test_indexed_grounded_page_correction_and_original_review_retry_after_backend_recreation(
    tmp_path, monkeypatch
):
    st.cache_resource.clear()
    state = SimpleNamespace(backend=None, loss=False, reviews=[])
    try:
        with offline_network():
            corpus = build_pilot_corpus(
                ROOT / "streamlit-data-for-dev-test",
                ROOT / "data/evaluation/split-manifest.json",
                ROOT / "experiments/corpus/pilot-allowlist.json",
            )
            snapshot = build_index(corpus, tmp_path / "index")
            config = {
                "AGENT_TRACKER_DB": str(tmp_path / "page.sqlite3"),
                "AGENT_REVIEWER_TOKEN": TOKEN,
                "AGENT_PILOT_INDEX": str(tmp_path / "index"),
                "AGENT_PILOT_SNAPSHOT": snapshot,
                "AGENT_PILOT_REASONING": "grounded_fake_gateway",
            }

            class Transport:
                def request(self, method, path, **arguments):
                    response = state.backend.request(method, path, **arguments)
                    if method == "POST" and path.endswith("/decision"):
                        state.reviews.append(copy.deepcopy(arguments["json"]))
                        if state.loss and response.status_code == 200:
                            state.loss = False
                            raise httpx.ReadTimeout(
                                "Synthetic committed review acknowledgment lost"
                            )
                    return response

            monkeypatch.setattr(
                ui_client,
                "make_client",
                lambda: ui_client.BackendClient(Transport(), reviewer_token=TOKEN),
            )
            state.backend = TestClient(configured_app(config)).__enter__()
            at = AppTest.from_file(str(ROOT / "app_pages/assistant.py"), default_timeout=15).run()
            assert not at.exception
            assert "scenario" not in [item.key for item in at.sidebar.selectbox]
            captions = " ".join(item.value for item in at.caption)
            assert "mocked provider" in captions and "no model quality result" in captions
            assert "local indexed docs" in captions and "scripted ask-then-escalate" not in captions
            original_message = "My text input resets on rerun. The installed version is unknown."
            at.chat_input[0].set_value(original_message).run()
            assert not at.exception
            case_id = at.session_state.case_id
            initial = state.backend.get(f"/cases/{case_id}").json()
            request = _handoff(initial).grounded_request
            assert initial["reasoning_label"] == "grounded_fake_gateway"
            assert initial["quality_claim"] is False and initial["actions"] == []
            assert initial["pending"]["next_question"] == STREAMLIT_VERSION_QUESTION.question
            assert {gap.kind for gap in request.gaps} == {"user", "source"}
            page_text = " ".join(item.value for item in at.markdown)
            assert "User information: streamlit_version" in page_text
            assert "Source coverage: exact_version_documentation" in page_text
            captions = " ".join(item.value for item in at.caption)
            assert request.evidence.hits
            assert all(f"Excerpt: {hit.excerpt}" in captions for hit in request.evidence.hits)
            at.button(key="approve").click().run()
            assert not at.exception
            at.text_input(key="version_reply").set_value("1.50.0")
            _button(at, "Send reply").click().run()
            assert not at.exception
            known = state.backend.get(f"/cases/{case_id}").json()
            known_handoff = _handoff(known)
            assert known["case_revision"] == 2 and known["pending"]["decision"] == "escalate"
            assert original_message in known_handoff.user_message
            assert known_handoff.user_message.endswith("1.50.0")
            assert not any(gap.kind == "user" for gap in known_handoff.grounded_request.gaps)
            assert known_handoff.analysis.evidence_links
            assert len(known["actions"]) == 1
            state.loss = True
            at.button(key="approve").click().run()
            assert not at.exception
            operation = at.session_state.unsent_reviews[case_id]
            original_payload = operation.payload()
            committed = state.backend.get(f"/cases/{case_id}").json()
            original_receipt = committed["review"]
            assert len(committed["actions"]) == 2
            _correction(at, "1.49.0")
            corrected = state.backend.get(f"/cases/{case_id}").json()
            corrected_handoff = _handoff(corrected)
            assert corrected["case_revision"] == 3
            assert corrected["pending"]["proposal_id"] != known["pending"]["proposal_id"]
            assert any(
                fact.name == "streamlit_version"
                and fact.value == "1.49.0"
                and fact.status == "active"
                for fact in corrected_handoff.case.facts
            )
            assert at.session_state.unsent_reviews[case_id].payload() == original_payload
            assert at.button(key="approve").disabled
            state.backend.__exit__(None, None, None)
            state.backend = TestClient(configured_app(config)).__enter__()
            _button(at, "Retry review").click().run()
            assert not at.exception
            assert at.session_state.unsent_reviews == {}
            assert state.reviews[-1] == original_payload
            retried = state.backend.get(f"/cases/{case_id}").json()
            # GET retains the original immutable receipt; the successful POST
            # response separately marks it replayed for this exact operation.
            assert retried["review"] == original_receipt
            assert retried["pending"] == corrected["pending"]
            assert len(retried["actions"]) == 2 and retried["case_revision"] == 3
            assert not at.button(key="approve").disabled
            assert TOKEN not in repr(at.session_state)
            assert len(SQLiteCaseTracker(config["AGENT_TRACKER_DB"]).comments(case_id)) == 2
    finally:
        if state.backend is not None:
            state.backend.__exit__(None, None, None)
        st.cache_resource.clear()
