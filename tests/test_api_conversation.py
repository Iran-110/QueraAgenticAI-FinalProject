"""HTTP must retain user context without promoting history to fact or authority."""

from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from agent_app import api
from agent_app.orchestration.intake import STREAMLIT_VERSION_QUESTION
from agent_app.reasoning.grounding import make_grounded_request
from agent_app.testing.http_pilot_runtime import Observations, memory_factory, offline_network


@pytest.fixture
def session(tmp_path, monkeypatch):
    observations = Observations()
    original = api._adapters
    monkeypatch.setattr(api, "_adapters", lambda scenario: observations.wrap(original(scenario)))
    with offline_network(), memory_factory(tmp_path), TestClient(api.app) as client:
        yield client, observations


def send(client, number, message, *, cid="context-case", **extra):
    return client.post(
        f"/cases/{cid}/messages",
        json={
            "turn_id": f"turn-{number}",
            "expected_revision": number - 1,
            "message": message,
            "scenario": "ask_version",
            **extra,
        },
    )


def review(client, proposal, decision, **extra):
    return client.post(
        f"/cases/{proposal['case_id']}/decision",
        json={
            "proposal_id": proposal["proposal_id"],
            "case_revision": proposal["case_revision"],
            "decision": decision,
            **extra,
        },
    )


def test_canonical_short_reply_keeps_original_problem_and_exact_first_input(session):
    client, obs = session
    problem = "Fragment multiselect resets on parent rerun.\nkey='selection'"
    first = send(client, 1, problem).json()
    proposal = first["pending"]
    assert obs.observed_inputs[0]["user_message"] == problem
    assert review(client, proposal, "approve").status_code == 200
    second = send(
        client, 2, "1.50.0", reply_to_proposal_id=proposal["proposal_id"], scenario="answer"
    ).json()
    observed = obs.observed_inputs[-1]
    assert problem in observed["user_message"]
    assert STREAMLIT_VERSION_QUESTION.question in observed["user_message"]
    assert observed["user_message"].endswith("Latest user message (exact committed input):\n1.50.0")
    assert second["log"][-1] == {"role": "user", "text": "1.50.0"}
    assert second["intake"]["preparation"] == "canonical_version_reply"
    assert second["pending"]["review_handoff"]["user_message"] == observed["user_message"]


def test_intermediate_code_retained_but_corrected_state_is_authoritative(session):
    client, obs = session
    problem = "Widget resets; I reported Streamlit1.50.0."
    send(client, 1, problem, reported_facts=[{"name": "streamlit_version", "value": "1.50.0"}])
    code = (
        "Minimal reproduction:\nwith st.container():\n    st.multiselect('values', ['a'], key='k')"
    )
    send(client, 2, code)
    correction = "Correction: version is1.49.1, not1.50.0."
    third = send(
        client,
        3,
        correction,
        context_changed=True,
        reported_facts=[{"name": "streamlit_version", "value": "1.49.1"}],
    ).json()
    observed = obs.observed_inputs[-1]
    assert all(text in observed["user_message"] for text in (problem, code, correction))
    assert "Historical context may contain superseded values" in observed["user_message"]
    versions = [f for f in observed["case"]["facts"] if f["name"] == "streamlit_version"]
    assert [(f["value"], f["status"]) for f in versions] == [
        ("1.50.0", "superseded"),
        ("1.49.1", "active"),
    ]
    assert third["case_revision"] == 3
    assert not third["checks_performed"] and not third["evidence_refs"]


def test_unapproved_edits_and_unbound_assistant_output_never_become_context(session):
    client, obs = session
    first = send(client, 1, "Widget resets.").json()["pending"]
    edited = review(client, first, "edit", edited_draft="UNAPPROVED_DRAFT").json()["pending"]
    assert review(client, first, "approve").status_code == 409
    assert review(client, edited, "reject").status_code == 200
    second = send(client, 2, "Here is more detail.").json()["pending"]
    edited = review(client, second, "edit", edited_draft="APPROVED_UNBOUND_QUESTION").json()[
        "pending"
    ]
    assert review(client, edited, "approve").status_code == 200
    send(client, 3, "More code.")
    actual = obs.observed_inputs[-1]["user_message"]
    assert "UNAPPROVED_DRAFT" not in actual
    assert "APPROVED_UNBOUND_QUESTION" not in actual
    assert STREAMLIT_VERSION_QUESTION.question not in actual
    assert [entry.actor for entry in api._cases["context-case"].history] == [
        "user",
        "user",
        "assistant",
        "user",
    ]


def test_replay_and_refused_reply_do_not_append_or_recompose_history(session, monkeypatch):
    client, obs = session
    first = send(client, 1, "Widget resets.").json()["pending"]
    review(client, first, "approve")
    send(client, 2, "1.50.0", reply_to_proposal_id=first["proposal_id"], scenario="answer")
    state = client.get("/cases/context-case").json()
    history = deepcopy(api._cases["context-case"].history)
    counts = obs.snapshot()
    monkeypatch.setattr(api, "build_reasoning_message", lambda _: pytest.fail("Replay recomposed"))
    retried = send(
        client, 2, "1.50.0", reply_to_proposal_id=first["proposal_id"], scenario="answer"
    )
    assert retried.status_code == 200 and retried.json()["intake"]["replayed"]
    refused = send(client, 3, "1.49.1", reply_to_proposal_id=first["proposal_id"])
    assert refused.status_code == 409
    assert client.get("/cases/context-case").json() == state
    assert api._cases["context-case"].history == history
    assert obs.snapshot() == counts


def test_oversized_history_stops_before_ports_and_retry_cannot_resume(session):
    client, obs = session
    for number in range(1, 5):
        response = send(client, number, str(number) * 4000, scenario="error")
        assert response.status_code == 200
    counts = obs.snapshot()
    stopped = send(client, 5, "5" * 4000, scenario="error").json()
    assert stopped["case_revision"] == 5 and stopped["pending"] is None
    assert stopped["log"][-1]["text"] == (
        "The run stopped (error: ConversationTooLong). Nothing was proposed."
    )
    assert obs.snapshot() == counts
    history = deepcopy(api._cases["context-case"].history)
    retried = send(client, 5, "5" * 4000, scenario="error").json()
    assert retried["intake"]["replayed"]
    assert client.get("/cases/context-case").json() == stopped
    assert api._cases["context-case"].history == history and obs.snapshot() == counts
    # A separate case retains its own exact first input, with no leaked history.
    send(client, 1, "Independent issue.", cid="other-case")
    assert obs.observed_inputs[-1]["user_message"] == "Independent issue."


def test_inconsistent_server_history_is_a_safe_terminal_failure(session):
    client, obs = session
    prior = send(client, 1, "Widget resets.").json()["pending"]
    case = api._cases["context-case"]
    case.history[0] = case.history[0].model_copy(update={"revision": 50})
    counts = obs.snapshot()
    stopped = send(client, 2, "More details.").json()
    assert stopped["case_revision"] == 2 and stopped["pending"]["stale"]
    assert case.state.pending_proposal_id is None and case.pending_handoff is None
    assert stopped["log"][-1]["text"] == (
        "The run stopped (error: ConversationMismatch). Nothing was proposed."
    )
    assert obs.snapshot() == counts
    assert review(client, prior, "approve").status_code == 409
    assert client.get("/cases/context-case").json() == stopped
    assert send(client, 2, "More details.").json()["intake"]["replayed"]
    assert obs.snapshot() == counts


@pytest.mark.parametrize("capture_actual", [True, False])
def test_grounded_supplier_must_capture_actual_composed_input(session, monkeypatch, capture_actual):
    client, obs = session
    first = send(client, 1, "Multiselect resets on a parent rerun.").json()["pending"]
    review(client, first, "approve")
    original = api._adapters
    captured = None

    def adapters(scenario):
        ports = original(scenario)

        class Capture:
            def analyze(self, case, user_message, evidence, *, context):
                nonlocal captured
                captured = make_grounded_request(
                    case, user_message if capture_actual else "1.50.0", evidence
                )
                return ports.reasoner.analyze(case, user_message, evidence, context=context)

        return api.RunAdapters(
            ports.retriever,
            Capture(),
            snapshot_id=ports.snapshot_id,
            grounded_request_supplier=lambda: captured,
        )

    monkeypatch.setattr(api, "_adapters", adapters)
    second = send(
        client, 2, "1.50.0", reply_to_proposal_id=first["proposal_id"], scenario="answer"
    ).json()
    assert captured is not None
    if capture_actual:
        handoff = second["pending"]["review_handoff"]
        assert handoff["grounded_request"]["user_message"] == handoff["user_message"]
    else:
        assert api._cases["context-case"].pending_handoff is None
        assert second["log"][-1]["text"] == "Review handoff stopped (GroundedContextMismatch)."
    counts = obs.snapshot()
    assert send(
        client, 2, "1.50.0", reply_to_proposal_id=first["proposal_id"], scenario="answer"
    ).json()["intake"]["replayed"]
    assert obs.snapshot() == counts
