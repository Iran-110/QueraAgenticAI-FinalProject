"""Mocked GroundedPlan gateway and real local TCP across fresh interpreters."""

from pathlib import Path

import pytest
from test_persistent_tcp import server

from agent_app import ui_client
from agent_app.contracts import ProposalHandoff
from agent_app.orchestration.handoff import validate_handoff
from agent_app.orchestration.intake import STREAMLIT_VERSION_QUESTION
from agent_app.retrieval.offline_index import build_index
from agent_app.retrieval.pilot_corpus import build_pilot_corpus
from agent_app.testing.http_pilot_runtime import offline_network
from agent_app.tracker.sqlite_tracker import SQLiteCaseTracker

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "synthetic-grounded-loopback-review-credential-for-tests"


def test_indexed_grounded_http_exact_review_retry_after_fresh_interpreter_restart(tmp_path):
    with offline_network():
        corpus = build_pilot_corpus(
            ROOT / "streamlit-data-for-dev-test",
            ROOT / "data/evaluation/split-manifest.json",
            ROOT / "experiments/corpus/pilot-allowlist.json",
        )
        snapshot = build_index(corpus, tmp_path / "index")
    config = {
        "AGENT_TRACKER_DB": str(tmp_path / "tcp.sqlite3"),
        "AGENT_REVIEWER_TOKEN": TOKEN,
        "AGENT_PILOT_INDEX": str(tmp_path / "index"),
        "AGENT_PILOT_SNAPSHOT": snapshot,
        "AGENT_PILOT_REASONING": "grounded_fake_gateway",
    }
    case_id = "grounded-tcp-pilot"
    first_event = {
        "message": "My widget resets on rerun; the installed version is unknown.",
        "turn_id": "grounded-tcp-original",
        "expected_revision": 0,
        "scenario": "answer",
    }
    with server(tmp_path / "ready-first.json", config) as http:
        client = ui_client.BackendClient(http, reviewer_token=TOKEN)
        capabilities = client.discover_capabilities()
        assert capabilities.retrieval_label == "local_chroma_hash"
        assert capabilities.reasoning_label == "grounded_fake_gateway"
        initial = client.send_event(case_id, first_event)
        first = validate_handoff(
            ProposalHandoff.model_validate(initial["pending"]["review_handoff"])
        )
        assert first.grounded_request is not None and first.evidence.hits
        assert first.analysis.next_question == STREAMLIT_VERSION_QUESTION.question
        assert initial["actions"] == [] and initial["quality_claim"] is False
        question = client.prepare_review(case_id, initial["pending"], "approve")
        approved = client.send_review(question)
        assert len(approved["actions"]) == 1
        reply_event = {
            "message": "1.50.0",
            "turn_id": "grounded-tcp-version",
            "expected_revision": 1,
            "reply_to_proposal_id": first.proposal_id,
            "scenario": "answer",
        }
        known = client.send_event(case_id, reply_event)
        known_handoff = validate_handoff(
            ProposalHandoff.model_validate(known["pending"]["review_handoff"])
        )
        assert known_handoff.grounded_request is not None
        assert first_event["message"] in known_handoff.user_message
        assert known_handoff.user_message.endswith("1.50.0")
        assert known_handoff.analysis.decision == "escalate"
        assert known_handoff.analysis.evidence_links
        operation = client.prepare_review(case_id, known["pending"], "approve")
        stale_operation = client.prepare_review(case_id, known["pending"], "approve")
        committed = client.send_review(operation)
        assert len(committed["actions"]) == 2
        original_body = operation.body_json
    with server(tmp_path / "ready-restart.json", config) as fresh:
        client = ui_client.BackendClient(fresh, reviewer_token=TOKEN)
        corrected = client.send_event(
            case_id,
            {
                "message": "Correction: the installed version is 1.49.0.",
                "turn_id": "grounded-tcp-correction",
                "expected_revision": 2,
                "reported_facts": [{"name": "streamlit_version", "value": "1.49.0"}],
                "context_changed": True,
                "scenario": "answer",
            },
        )
        assert corrected["pending"] is not None, corrected["run_outcome"]
        current = validate_handoff(
            ProposalHandoff.model_validate(corrected["pending"]["review_handoff"])
        )
        assert corrected["case_revision"] == 3 and current.analysis.decision == "escalate"
        assert current.grounded_request is not None
        assert current.proposal_id != known_handoff.proposal_id
        assert any(
            fact.name == "streamlit_version" and fact.value == "1.49.0" and fact.status == "active"
            for fact in current.case.facts
        )
        with pytest.raises(ui_client.BackendError) as rejected:
            client.send_review(stale_operation)
        assert rejected.value.code in {"StaleRevision", "PendingProposalMismatch"}
        replay = client.send_review(operation)
        assert operation.body_json == original_body
        assert replay["review"] == {**committed["review"], "replayed": True}
        assert replay["pending"] == corrected["pending"]
        assert replay["case_revision"] == 3 and len(replay["actions"]) == 2
        # Original ingress replay also cannot create another proposal or action.
        for event in (first_event, reply_event):
            duplicate = client.send_event(case_id, event)
            assert duplicate["intake"]["replayed"] is True
            assert duplicate["pending"] == corrected["pending"]
            assert len(duplicate["actions"]) == 2
        assert TOKEN not in str(replay)
    assert len(SQLiteCaseTracker(config["AGENT_TRACKER_DB"]).comments(case_id)) == 2
