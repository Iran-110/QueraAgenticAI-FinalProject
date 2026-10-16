"""Current failure-context boundary, not outcome-aware reasoning or model quality.

Configured app/tracker objects restart in one interpreter between the turns.
Authored ports capture what the current core consumes; outcomes remain separate.
"""

import hashlib
import json
import sqlite3
from copy import deepcopy

from fastapi.testclient import TestClient

from agent_app import api, offline_backend
from agent_app.contracts import EvidenceBundle, EvidenceHit
from agent_app.orchestration import SupportEngine
from agent_app.testing.http_pilot_runtime import offline_network

CASE = "neutral-failure-context"
OTHER = "neutral-unrelated-case"
OTHER_CANARY = "UNRELATED_CASE_MESSAGE_ONLY"
FAILURE_CANARY = "PRIVATE_INJECTED_CORE_FAILURE"
TOKEN = "neutral-custody-reviewer-token-20261017"
FIRST = {
    "message": "My widget resets on rerun; the reported version is 1.49.1.",
    "turn_id": "initial-failure",
    "expected_revision": 0,
    "scenario": "error",
    "reported_facts": [{"name": "streamlit_version", "value": "1.49.1"}],
    "unknowns": ["widget_definition"],
}
FOLLOW_UP = {
    "message": "Continue investigating using the confirmed facts.",
    "turn_id": "after-failure",
    "expected_revision": 1,
    "scenario": "ask",
}
CORRECTION = {
    "message": "Correction: my current version is 1.50.0. Here is the widget code.",
    "turn_id": "corrected-version",
    "expected_revision": 2,
    "scenario": "ask",
    "reported_facts": [
        {"name": "streamlit_version", "value": "1.50.0"},
        {"name": "widget_definition", "value": "st.text_input('Name', key='name')"},
    ],
}


class CapturedPorts:
    """Observe real core calls without making an outcome available to a port."""

    def __init__(self, failure, original_run):
        self.failure = failure
        self.original_run = original_run
        self.allocations, self.retrievals, self.analyses, self.core, self.closed = (
            [],
            [],
            [],
            [],
            [],
        )
        self.document = None

    def counts(self):
        return tuple(
            len(value)
            for value in (self.allocations, self.retrievals, self.analyses, self.core, self.closed)
        )

    def run(self, engine, case, message, *args, **kwargs):
        self.core.append(
            {
                "case": case.model_dump(mode="json"),
                "message": message,
                "initial_query": kwargs.get("initial_query"),
            }
        )
        if self.failure == "core" and case.case_id == CASE and case.case_revision == 1:
            raise RuntimeError(FAILURE_CANARY)
        return self.original_run(engine, case, message, *args, **kwargs)

    def allocate(self, scenario):
        identity = len(self.allocations)
        self.allocations.append(scenario)
        observation = self
        failed_retriever = api._adapters("error").retriever
        delegate = offline_backend.ScriptedQuestionReasoner(include_widget=True)

        class Retriever:
            def search(self, request):
                observation.retrievals.append(request.model_dump(mode="json"))
                if scenario == "error":
                    return failed_retriever.search(request)
                name, version = observation.document
                return EvidenceBundle(
                    snapshot_id=request.snapshot_id,
                    queries_used=request.queries,
                    hits=(
                        EvidenceHit(
                            chunk_id="neutral-" + name,
                            source_id="neutral-source-" + name,
                            source_url="https://example.org/neutral/" + name,
                            source_type="doc",
                            excerpt="NEUTRAL_" + name.upper() + "_EVIDENCE",
                            applicable_versions=(version,),
                        ),
                    ),
                )

        class Reasoner:
            def analyze(self, case, message, evidence, *, context):
                observation.analyses.append(
                    {
                        "case": case.model_dump(mode="json"),
                        "message": message,
                        "evidence": evidence.model_dump(mode="json"),
                        "context": context.model_dump(mode="json"),
                    }
                )
                return delegate.analyze(case, message, evidence, context=context)

        return api.RunAdapters(
            Retriever(), Reasoner(), cleanup=lambda: self.closed.append(identity)
        )


def _post(client, event, case=CASE):
    response = client.post(f"/cases/{case}/messages", json=event)
    assert response.status_code == 200
    return response.json()


def _get(client):
    response = client.get(f"/cases/{CASE}")
    assert response.status_code == 200
    return response.json()


def _active_version(case):
    return [
        fact["value"]
        for fact in case["facts"]
        if fact["name"] == "streamlit_version"
        and fact["status"] == "active"
        and fact["provenance_kind"] == "user"
    ]


def _projection(call):
    # Only fresh random run identity is removed. Every consumed case/message/
    # source/context field otherwise participates in the cross-failure check.
    result = deepcopy(call)
    result["context"].pop("run_id")
    return result


def _exercise(tmp_path, monkeypatch, failure, original_run):
    database = tmp_path / (failure + ".sqlite3")
    config = {"AGENT_TRACKER_DB": str(database), "AGENT_REVIEWER_TOKEN": TOKEN}
    captured = CapturedPorts(failure, original_run)
    monkeypatch.setattr(offline_backend, "_scripted_adapters", captured.allocate)

    def run(engine, case, message, *args, **kwargs):
        return captured.run(engine, case, message, *args, **kwargs)

    monkeypatch.setattr(SupportEngine, "run", run)
    expected_error = "CoreRunFailed" if failure == "core" else "RetrievalUnavailable"
    with TestClient(offline_backend.configured_app(config)) as client:
        first = _post(client, FIRST)
        assert first["case_revision"] == 1
        assert first["run_outcome"]["error_code"] == expected_error
        assert first["pending"] is None and first["actions"] == []
        assert FAILURE_CANARY not in json.dumps(first)
        assert captured.analyses == []
        assert len(captured.allocations) == len(captured.closed) == 1
    original_outcome = first["run_outcome"]

    # This is an actual new configured application, tracker and SQLite connection.
    with TestClient(offline_backend.configured_app(config)) as client:
        assert _get(client)["run_outcome"] == original_outcome
        before = captured.counts()
        replay = _post(client, FIRST)
        assert replay["intake"]["replayed"] is True
        assert replay["run_outcome"] == original_outcome
        assert replay["case_revision"] == 1 and replay["pending"] is None
        assert captured.counts() == before

        # Another case is persisted before continuing the failed one. Neither
        # its text, facts, evidence nor proposal may become this case's context.
        captured.document = ("unrelated", "2.2.2")
        other = _post(
            client,
            {
                "message": OTHER_CANARY,
                "turn_id": "other-case-turn",
                "expected_revision": 0,
                "scenario": "ask",
                "reported_facts": [{"name": "streamlit_version", "value": "2.2.2"}],
            },
            OTHER,
        )
        assert other["case_revision"] == 1 and other["pending"] is not None
        other_proposal = other["pending"]["proposal_id"]
        other_saved = client.get(f"/cases/{OTHER}").json()

        captured.document = ("after_failure", "1.49.1")
        continued = _post(client, FOLLOW_UP)
        next_input = captured.analyses[-1]
        assert next_input["case"]["case_id"] == CASE
        assert next_input["case"]["case_revision"] == 2
        assert _active_version(next_input["case"]) == ["1.49.1"]
        assert continued["run_outcome"]["error_code"] is None
        assert continued["pending"]["missing_info"] == ["widget_definition"]
        assert continued["actions"] == []
        assert next_input["message"].endswith(FOLLOW_UP["message"])
        assert FIRST["message"] in next_input["message"]
        assert next_input["context"]["case_revision"] == 2
        # Negative current-behavior observation: durable failure metadata is
        # not a field or injected prose in this actual reasoner/core input.
        encoded = json.dumps(next_input)
        for absent in (
            "run_outcome",
            "RetrievalUnavailable",
            "CoreRunFailed",
            FAILURE_CANARY,
            OTHER_CANARY,
            other_proposal,
            "NEUTRAL_UNRELATED_EVIDENCE",
            "2.2.2",
        ):
            assert absent not in encoded
        next_retrieval = deepcopy(captured.retrievals[-1])
        assert len(next_retrieval["queries"]) == 1
        assert "streamlit_version=1.49.1" in next_retrieval["queries"][0]
        assert OTHER_CANARY not in json.dumps(next_retrieval)
        assert captured.core[-1] == {
            "case": next_input["case"],
            "message": next_input["message"],
            "initial_query": next_retrieval["queries"][0],
        }
        old_proposal = continued["pending"]["proposal_id"]
        old_handoff = continued["pending"]["review_handoff"]["handoff_sha256"]
        assert next_input["evidence"]["hits"][0]["chunk_id"] == "neutral-after_failure"

        captured.document = ("corrected", "1.50.0")
        corrected = _post(client, CORRECTION)
        current = captured.analyses[-1]
        assert corrected["case_revision"] == current["case"]["case_revision"] == 3
        assert _active_version(current["case"]) == ["1.50.0"]
        assert current["case"]["pending_proposal_id"] is None
        assert current["case"]["evidence_refs"] == []
        assert current["case"]["unknowns"] == []
        assert current["message"].endswith(CORRECTION["message"])
        # Old USER text remains explicitly historical; source evidence and
        # unreleased proposal content do not become current authority.
        assert "historical context; not current facts" in current["message"]
        assert FIRST["message"] in current["message"]
        assert continued["pending"]["user_draft"] not in current["message"]
        assert [hit["chunk_id"] for hit in current["evidence"]["hits"]] == ["neutral-corrected"]
        current_retrieval = deepcopy(captured.retrievals[-1])
        assert len(current_retrieval["queries"]) == 1
        assert "streamlit_version=1.50.0" in current_retrieval["queries"][0]
        for absent in ("1.49.1", "2.2.2", OTHER_CANARY, old_proposal):
            assert absent not in json.dumps(current_retrieval)
        assert captured.core[-1] == {
            "case": current["case"],
            "message": current["message"],
            "initial_query": current_retrieval["queries"][0],
        }
        for absent in (old_proposal, old_handoff, "NEUTRAL_AFTER_FAILURE_EVIDENCE", OTHER_CANARY):
            assert absent not in json.dumps(current)
        assert corrected["pending"]["proposal_id"] != old_proposal
        assert corrected["pending"]["decision"] == "escalate"
        assert corrected["run_outcome"]["error_code"] is None
        assert corrected["actions"] == []
        other_after = client.get(f"/cases/{OTHER}").json()
        assert other_after == other_saved

        # Even after correction, the original event's intake is replay-only.
        # HTTP returns current run_outcome here, not the historical event's one.
        before = captured.counts()
        replay = _post(client, FIRST)
        assert replay["intake"]["replayed"] is True
        assert replay["intake"]["committed_revision"] == 1
        assert replay["case_revision"] == 3
        assert replay["run_outcome"] == corrected["run_outcome"]
        assert captured.counts() == before
    assert captured.closed == list(range(len(captured.allocations)))
    with sqlite3.connect(database) as db:
        original = db.execute(
            "SELECT revision,error_code FROM run_outcomes WHERE case_id=? AND turn_id=?",
            (CASE, FIRST["turn_id"]),
        ).fetchone()
        count = db.execute("SELECT COUNT(*) FROM run_outcomes WHERE case_id=?", (CASE,)).fetchone()
    assert original == (1, expected_error) and count == (3,)
    return _projection(next_input), next_retrieval, _projection(current), current_retrieval


def test_durable_failure_is_not_current_reasoning_context_across_restart_and_correction(
    tmp_path, monkeypatch, record_testsuite_property
):
    original_run = SupportEngine.run
    with offline_network():
        retrieval = _exercise(tmp_path, monkeypatch, "retrieval", original_run)
        core = _exercise(tmp_path, monkeypatch, "core", original_run)
    # Actual consumed inputs agree for these two authored histories despite
    # distinct durable errors. No adaptive/model-level independence is claimed.
    assert retrieval == core
    record_testsuite_property(
        "failure_context_custody",
        json.dumps(
            {
                "failure_modes": ["RetrievalUnavailable", "CoreRunFailed"],
                "application_tracker_reconstruction_in_one_interpreter": True,
                "replay_new_port_calls": 0,
                "negative_current_behavior": "prior outcome persisted separately from reasoner inputs",
                "same_inputs_after_removing_only_run_id": True,
                "consumed_input_sha256": hashlib.sha256(
                    json.dumps(retrieval, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest(),
                "quality_claim": False,
            },
            sort_keys=True,
        ),
    )
