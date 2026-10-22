"""Execute the actual Streamlit page against persistent HTTP and actual Chroma."""

import json
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
TOKEN = "synthetic-indexed-streamlit-private-review-credential"


def test_page_reads_index_then_approves_question_and_corrects_version(tmp_path, monkeypatch):
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
                "AGENT_TRACKER_DB": str(tmp_path / "page.sqlite3"),
                "AGENT_REVIEWER_TOKEN": TOKEN,
                "AGENT_PILOT_INDEX": str(tmp_path / "index"),
                "AGENT_PILOT_SNAPSHOT": snapshot,
            }
            with TestClient(configured_app(config)) as backend:
                monkeypatch.setattr(
                    ui_client,
                    "make_client",
                    lambda: ui_client.BackendClient(backend, reviewer_token=TOKEN),
                )
                # The real index verifies source hashes on each retrieval. AppTest's
                # three-second default is too tight on a busy Windows runner; this
                # bounds test completion, not application latency or HTTP timeouts.
                at = AppTest.from_file(
                    str(ROOT / "app_pages/assistant.py"), default_timeout=15
                ).run()
                assert not at.exception
                assert "scenario" not in [item.key for item in at.sidebar.selectbox]
                fixture = json.loads((ROOT / "data/evaluation/dev/pilot-12782.json").read_text())
                at.chat_input[0].set_value(fixture["turns"][0]["visible"]["message"]).run()
                assert not at.exception
                case_id = at.session_state.case_id
                current = backend.get(f"/cases/{case_id}").json()
                assert current["pending"]["decision"] == "ask"
                hits = current["pending"]["review_handoff"]["evidence"]["hits"]
                captions = " ".join(item.value for item in at.caption)
                assert hits and all(f"Excerpt: {hit['excerpt']}" in captions for hit in hits)
                at.button(key="approve").click().run()
                assert not at.exception
                at.chat_input[0].set_value("1.50.0").run()
                assert not at.exception
                known = backend.get(f"/cases/{case_id}").json()
                assert known["case_revision"] == 2
                assert known["pending"]["decision"] == "escalate"
                generation = at.session_state.form_gen
                at.text_area(key=f"update_message_{generation}").set_value("Correction: 1.49.0.")
                at.text_input(key=f"fact_name_0_{generation}").set_value("streamlit_version")
                at.text_input(key=f"fact_value_0_{generation}").set_value("1.49.0")
                next(item for item in at.button if item.label == "Send update").click().run()
                assert not at.exception
                corrected = backend.get(f"/cases/{case_id}").json()
                assert corrected["case_revision"] == 3
                assert corrected["pending"]["proposal_id"] != known["pending"]["proposal_id"]
                assert len(corrected["actions"]) == 1
                assert any(
                    f["name"] == "streamlit_version"
                    and f["value"] == "1.49.0"
                    and f["status"] == "active"
                    for f in corrected["facts"]
                )
                assert TOKEN not in repr(at.session_state)
    finally:
        st.cache_resource.clear()
