"""Actual Chroma to core/SQLite/client integration; scripted routing, no model."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_app import ui_client
from agent_app.offline_backend import configured_app
from agent_app.retrieval.offline_index import build_index, open_verified_index
from agent_app.retrieval.pilot_corpus import build_pilot_corpus
from agent_app.testing.http_pilot_runtime import offline_network
from agent_app.tracker.sqlite_tracker import SQLiteCaseTracker

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "synthetic-indexed-pilot-private-review-credential"


@pytest.fixture(scope="module")
def index(tmp_path_factory):
    destination = tmp_path_factory.mktemp("actual-docs-pilot") / "index"
    with offline_network():
        corpus = build_pilot_corpus(
            ROOT / "streamlit-data-for-dev-test",
            ROOT / "data/evaluation/split-manifest.json",
            ROOT / "experiments/corpus/pilot-allowlist.json",
        )
        build_index(corpus, destination)
    return destination


def test_actual_index_correction_approval_and_backend_recreation(index, tmp_path):
    config = {
        "AGENT_TRACKER_DB": str(tmp_path / "cases.sqlite3"),
        "AGENT_REVIEWER_TOKEN": TOKEN,
        "AGENT_PILOT_INDEX": str(index),
        "AGENT_PILOT_SNAPSHOT": open_verified_index(index)[1],
    }
    fixture = json.loads((ROOT / "data/evaluation/dev/pilot-12782.json").read_text())
    case_id = "indexed-dev-12782"
    with offline_network(), TestClient(configured_app(config)) as http:
        client = ui_client.BackendClient(http, reviewer_token=TOKEN)
        capabilities = client.discover_capabilities()
        assert capabilities.retrieval_label == "local_chroma_hash"
        assert capabilities.durable_reviews is True
        original = client.send_event(
            case_id,
            {
                **fixture["turns"][0]["visible"],
                "turn_id": "indexed-original",
                "expected_revision": 0,
                "scenario": "answer",
            },
        )
        # Scenario controls cannot make this conservative scripted router answer.
        assert original["pending"]["decision"] == "ask"
        handoff = original["pending"]["review_handoff"]
        verified, snapshot = open_verified_index(index)
        chunks = {c["chunk_id"]: c for c in verified.manifest["corpus"]["chunks"]}
        assert handoff["evidence"]["snapshot_id"] == snapshot
        assert handoff["evidence"]["hits"]
        for hit in handoff["evidence"]["hits"]:
            chunk = chunks[hit["chunk_id"]]
            assert hit["excerpt"] == chunk["document"].strip()
            assert hit["source_span"] == chunk["metadata"]["source_span"]
            assert hit["source_type"] == "doc"
            assert hit["source_commit"] == "695e6ce2fb1b23afc6df66b40420ab0013ad72fd"
        question = client.prepare_review(case_id, original["pending"], "approve")
        approved = client.send_review(question)
        assert approved["status"] == "awaiting_user"
        known = client.send_event(
            case_id,
            {
                "message": "1.50.0",
                "turn_id": "indexed-version",
                "expected_revision": 1,
                "scenario": "answer",
                "reply_to_proposal_id": original["pending"]["proposal_id"],
            },
        )
        assert known["pending"]["decision"] == "escalate"
        old_review = client.prepare_review(case_id, known["pending"], "approve")
        corrected = client.send_event(
            case_id,
            {
                "message": "Correction: the installed version is 1.49.0.",
                "turn_id": "indexed-correction",
                "expected_revision": 2,
                "scenario": "answer",
                "context_changed": True,
                "reported_facts": [{"name": "streamlit_version", "value": "1.49.0"}],
            },
        )
        assert corrected["case_revision"] == 3
        assert corrected["pending"]["proposal_id"] != known["pending"]["proposal_id"]
        assert corrected["pending"]["review_handoff"]["case"]["checks_performed"] == []
        active = [f for f in corrected["facts"] if f["status"] == "active"]
        assert any(f["name"] == "streamlit_version" and f["value"] == "1.49.0" for f in active)
        with pytest.raises(ui_client.BackendError) as rejected:
            client.send_review(old_review)
        assert rejected.value.code in {"StaleRevision", "PendingProposalMismatch"}
        assert len(corrected["actions"]) == 1
        operation = client.prepare_review(case_id, corrected["pending"], "approve")
        sent = client.send_review(operation)
        assert len(sent["actions"]) == 2
        original_receipt = sent["review"]
    with offline_network(), TestClient(configured_app(config)) as fresh:
        client = ui_client.BackendClient(fresh, reviewer_token=TOKEN)
        replay = client.send_review(operation)
        assert replay["review"] == {**original_receipt, "replayed": True}
        assert len(replay["actions"]) == 2
        assert replay["case_revision"] == 3
        assert TOKEN not in json.dumps(replay)
        withdrawal = client.send_event(
            case_id,
            {
                "message": "I cannot confirm the installed version now.",
                "turn_id": "indexed-withdrawal",
                "expected_revision": 3,
                "scenario": "answer",
                "reported_facts": [{"name": "streamlit_version", "value": None}],
                "unknowns": ["streamlit_version"],
                "context_changed": True,
            },
        )
        assert withdrawal["pending"]["decision"] == "ask"
        assert not any(
            f["name"] == "streamlit_version" and f["status"] == "active"
            for f in withdrawal["facts"]
        )
    tracker = SQLiteCaseTracker(config["AGENT_TRACKER_DB"])
    assert len(tracker.comments(case_id)) == 2


def test_indexed_launcher_does_not_use_default_embedding_function(index, tmp_path, monkeypatch):
    from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

    def forbidden(self, input):
        raise AssertionError("A model must not be downloaded or used")

    monkeypatch.setattr(DefaultEmbeddingFunction, "__call__", forbidden)
    with (
        offline_network(),
        TestClient(
            configured_app(
                {
                    "AGENT_TRACKER_DB": str(tmp_path / "no-model.sqlite3"),
                    "AGENT_REVIEWER_TOKEN": TOKEN,
                    "AGENT_PILOT_INDEX": str(index),
                    "AGENT_PILOT_SNAPSHOT": open_verified_index(index)[1],
                }
            )
        ) as http,
    ):
        response = http.post(
            "/cases/no-model/messages",
            json={
                "message": "Session State widget rerun",
                "turn_id": "first",
                "expected_revision": 0,
            },
        )
        assert response.status_code == 200
        assert response.json()["pending"]["decision"] == "ask"
