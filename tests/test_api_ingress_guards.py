"""Additive structured HTTP ingress guards with memory-only offline adapters."""

import json
import re

import pytest
from fastapi.testclient import TestClient

from agent_app import api
from agent_app.contracts import AnalysisResult, CaseState, Fact
from agent_app.demo import _evidence
from agent_app.orchestration.intake import STREAMLIT_VERSION_QUESTION
from agent_app.tracker.dummy_tracker import DummyTracker


@pytest.fixture
def ingress_client(monkeypatch):
    monkeypatch.setattr(api, "_cases", {})
    monkeypatch.setattr(api, "tracker", DummyTracker())
    original_script = api._script
    calls = []

    def script(scenario):
        calls.append(scenario)
        if scenario == "ask":
            return (
                [_evidence("canonical-question-context", "Synthetic version-question context.")],
                [
                    AnalysisResult(
                        decision="ask",
                        user_draft=STREAMLIT_VERSION_QUESTION.question,
                        next_question=STREAMLIT_VERSION_QUESTION.question,
                        missing_info=(STREAMLIT_VERSION_QUESTION.name,),
                        maintainer_summary="The affected Streamlit version is unknown.",
                        rationale="The version determines the relevant documentation.",
                    )
                ],
            )
        return original_script(scenario)

    monkeypatch.setattr(api, "_script", script)
    return TestClient(api.app), calls


def post(client, payload, case_id="case-intake"):
    # ASCII JSON escaping lets the server validate a lone UTF-8 surrogate;
    # httpx's ordinary json= encoder otherwise rejects it before sending.
    return client.post(
        f"/cases/{case_id}/messages",
        content=json.dumps(payload, ensure_ascii=True),
        headers={"Content-Type": "application/json"},
    )


def event(turn_id="ingress-1", revision=0, **extra):
    return {
        "message": "My widget loses its value.",
        "scenario": "ask",
        "turn_id": turn_id,
        "expected_revision": revision,
        **extra,
    }


def decision(client, pending, action="approve", case_id="case-intake", **extra):
    return client.post(
        f"/cases/{case_id}/decision",
        json={
            "proposal_id": pending["proposal_id"],
            "case_revision": pending["case_revision"],
            "decision": action,
            **extra,
        },
    )


def approved_question(client, case_id="case-intake"):
    created = post(client, event(), case_id=case_id)
    assert created.status_code == 200
    pending = created.json()["pending"]
    approved = decision(client, pending, case_id=case_id)
    assert approved.status_code == 200
    view = approved.json()
    assert view["pending"] is None
    assert view["awaiting_reply"]["proposal_id"] == pending["proposal_id"]
    assert view["awaiting_reply"]["case_revision"] == pending["case_revision"]
    return pending


def active_facts(view):
    return {fact["name"].casefold(): fact for fact in view["facts"] if fact["status"] == "active"}


def assert_safe_error(response, status, code=None):
    assert response.status_code == status
    detail = response.json()["detail"]
    assert isinstance(detail, str)
    assert re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", detail)
    if code is not None:
        assert detail == code
    assert "private-marker" not in response.text


def test_approved_question_bare_reply_is_attributed_once_and_raw_replay_survives_cleared_question(
    ingress_client,
):
    client, calls = ingress_client
    question = approved_question(client)
    payload = event(
        "reply-1",
        1,
        message="1.42.0",
        scenario="answer",
        reply_to_proposal_id=question["proposal_id"],
    )
    response = post(client, payload)
    assert response.status_code == 200
    first = response.json()
    version = active_facts(first)["streamlit_version"]
    assert version["value"] == "1.42.0"
    assert version["provenance_kind"] == "user"
    assert version["turn_id"] == "reply-1"
    assert first["case_revision"] == 2
    assert first["awaiting_reply"] is None
    receipt = first["intake"]
    assert receipt["committed_revision"] == 2
    assert receipt["replayed"] is False
    assert re.fullmatch(r"[a-f0-9]{64}", receipt["ingress_hash"])
    assert re.fullmatch(r"[a-f0-9]{64}", receipt["prepared_hash"])
    assert receipt["ingress_hash"] != receipt["prepared_hash"]
    assert receipt["preparation"] == "canonical_version_reply"
    before = (len(calls), first["log"], first["decisions"], first["pending"])

    replay = post(client, payload)
    assert replay.status_code == 200
    current = replay.json()
    assert current["case_revision"] == 2
    assert current["facts"] == first["facts"]
    assert current["intake"] == {**receipt, "replayed": True}
    assert before == (len(calls), current["log"], current["decisions"], current["pending"])


def test_replay_returns_current_case_with_old_immutable_receipt_before_stale_revision_check(
    ingress_client,
):
    client, calls = ingress_client
    original = event(
        scenario="answer",
        reported_facts=[{"name": "streamlit_version", "value": "1.41.0"}],
    )
    one = post(client, original).json()
    two = post(
        client,
        event(
            "correction-2",
            1,
            message="Correction: the affected version is 1.42.0.",
            scenario="answer",
            reported_facts=[{"name": "streamlit_version", "value": "1.42.0"}],
        ),
    ).json()
    calls_before = len(calls)
    replay = post(client, original)
    assert replay.status_code == 200
    view = replay.json()
    assert view["case_revision"] == two["case_revision"] == 2
    assert active_facts(view)["streamlit_version"]["value"] == "1.42.0"
    assert view["intake"] == {**one["intake"], "replayed": True}
    assert view["intake"]["committed_revision"] == 1
    assert view["pending"] == two["pending"]
    assert view["log"] == two["log"]
    assert len(calls) == calls_before
    assert client.get("/cases/case-intake").json()["intake"] == two["intake"]


@pytest.mark.parametrize(
    "change",
    [
        {"message": "private-marker changed text"},
        {"scenario": "escalate"},
        {"reply_to_proposal_id": "proposal:changed-binding"},
        {"reported_facts": [{"name": "streamlit_version", "value": "1.43.0"}]},
    ],
)
def test_event_id_conflict_includes_message_scenario_reply_binding_and_structured_content(
    ingress_client, change
):
    client, calls = ingress_client
    original = event(scenario="answer")
    assert post(client, original).status_code == 200
    before = client.get("/cases/case-intake").json()
    calls_before = len(calls)
    response = post(client, {**original, **change})
    assert_safe_error(response, 409, "EventConflict")
    assert client.get("/cases/case-intake").json() == before
    assert len(calls) == calls_before


def test_revision_string_cannot_be_coerced_into_approval_authority(ingress_client):
    client, calls = ingress_client
    view = post(client, event()).json()
    pending = view["pending"]
    response = client.post(
        "/cases/case-intake/decision",
        content=json.dumps(
            {
                "proposal_id": pending["proposal_id"],
                "case_revision": str(pending["case_revision"]),
                "decision": "approve",
            },
            ensure_ascii=True,
        ),
        headers={"Content-Type": "application/json"},
    )
    assert_safe_error(response, 422, "RequestInvalid")
    assert client.get("/cases/case-intake").json() == view
    assert len(calls) == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"message": "private-marker", "unknown_field": "private-marker"},
        {"message": " \n\t "},
        event(expected_revision=True),
        event(message="\ud800private-marker"),
        event(reported_facts=[{"name": "private-marker", "value": "\ud800"}]),
        event(checks_performed=["\ud800private-marker"]),
        event(context_changed="private-marker"),
        event(unknowns=["streamlit_version", "STREAMLIT_VERSION"]),
        event(
            reported_facts=[
                {"name": "streamlit_version", "value": "1.41.0"},
                {"name": "STREAMLIT_VERSION", "value": "1.42.0"},
            ]
        ),
        {"message": "private-marker", "turn_id": "id-only"},
        {"message": "private-marker", "expected_revision": 0},
        {
            "message": "private-marker",
            "reported_facts": [{"name": "streamlit_version", "value": "1.42.0"}],
        },
        {"message": "private-marker", "checks_performed": ["A new check."]},
        {"message": "private-marker", "context_changed": True},
        {"message": "private-marker", "reply_to_proposal_id": "proposal:unknown"},
    ],
)
def test_invalid_ingress_returns_safe_422_before_case_creation_or_adapter_call(
    ingress_client, payload
):
    client, calls = ingress_client
    before = client.get("/cases/case-intake").json()
    assert "case-intake" not in api._cases
    response = post(client, payload)
    assert_safe_error(response, 422, "RequestInvalid")
    assert "case-intake" not in api._cases
    assert client.get("/cases/case-intake").json() == before
    assert calls == []


@pytest.mark.parametrize("phase", ["unapproved", "rejected", "replaced", "wrong_case"])
def test_reply_requires_current_stored_approved_question(ingress_client, phase):
    client, calls = ingress_client
    first = post(client, event()).json()
    question = first["pending"]
    case_id = "case-intake"
    revision = 1
    if phase == "rejected":
        assert decision(client, question, "reject").status_code == 200
    elif phase == "replaced":
        assert decision(client, question).status_code == 200
        replaced = post(client, event("other-turn", 1, message="Here is more context.")).json()
        revision = replaced["case_revision"]
    elif phase == "wrong_case":
        assert decision(client, question).status_code == 200
        case_id = "case-other"
        revision = 0
    before = client.get(f"/cases/{case_id}").json()
    calls_before = len(calls)
    response = post(
        client,
        event(
            "reply-1",
            revision,
            message="1.42.0",
            scenario="answer",
            reply_to_proposal_id=question["proposal_id"],
        ),
        case_id=case_id,
    )
    assert_safe_error(response, 409, "PendingReplyMissing")
    assert client.get(f"/cases/{case_id}").json() == before
    assert len(calls) == calls_before


@pytest.mark.parametrize(
    "extra",
    [
        {"message": "Maybe 1.42.0; private-marker"},
        {"reported_facts": [{"name": "streamlit_version", "value": "1.42.0"}]},
        {"unknowns": ["python_version"]},
        {"checks_performed": ["Version command was run."]},
        {"context_changed": True},
    ],
)
def test_ambiguous_or_mixed_reply_does_not_consume_question_or_mutate_state(ingress_client, extra):
    client, calls = ingress_client
    question = approved_question(client)
    before = client.get("/cases/case-intake").json()
    calls_before = len(calls)
    response = post(
        client,
        {
            **event(
                "reply-1",
                1,
                message="1.42.0",
                scenario="answer",
                reply_to_proposal_id=question["proposal_id"],
            ),
            **extra,
        },
    )
    code = "VersionReplyUnclear" if "message" in extra else "RequestInvalid"
    assert_safe_error(response, 422, code)
    assert client.get("/cases/case-intake").json() == before
    assert len(calls) == calls_before
    # Rejected ingress did not reserve the event ID or consume the question.
    valid = post(
        client,
        event(
            "reply-1",
            1,
            message="1.42.0",
            scenario="answer",
            reply_to_proposal_id=question["proposal_id"],
        ),
    )
    assert valid.status_code == 200
    assert active_facts(valid.json())["streamlit_version"]["value"] == "1.42.0"


def test_edited_approved_question_is_displayed_but_not_used_for_version_extraction(ingress_client):
    client, calls = ingress_client
    question = post(client, event()).json()["pending"]
    edited = decision(client, question, "edit", edited_draft="Which Python version is installed?")
    assert edited.status_code == 200
    revised = edited.json()["pending"]
    assert revised["proposal_id"] != question["proposal_id"]
    assert decision(client, question).status_code == 409
    assert decision(client, revised).status_code == 200
    before = client.get("/cases/case-intake").json()
    calls_before = len(calls)
    response = post(
        client,
        event(
            "reply-1",
            1,
            message="3.13.0",
            scenario="answer",
            reply_to_proposal_id=revised["proposal_id"],
        ),
    )
    assert_safe_error(response, 422, "InvalidVersionQuestion")
    assert client.get("/cases/case-intake").json() == before
    assert len(calls) == calls_before


def test_old_approved_question_identity_and_stale_revision_cannot_be_rebound(ingress_client):
    client, calls = ingress_client
    question = approved_question(client)
    before = client.get("/cases/case-intake").json()
    for extra in [
        {"reply_to_proposal_id": "proposal:wrong"},
        {"expected_revision": 0},
    ]:
        response = post(
            client,
            {
                **event(
                    "reply-1",
                    1,
                    message="1.42.0",
                    scenario="answer",
                    reply_to_proposal_id=question["proposal_id"],
                ),
                **extra,
            },
        )
        code = "StaleRevision" if "expected_revision" in extra else "PendingProposalMismatch"
        assert_safe_error(response, 409, code)
        assert client.get("/cases/case-intake").json() == before
    assert len(calls) == 1


def test_bare_version_without_reply_binding_stays_unstructured(ingress_client):
    client, _ = ingress_client
    approved_question(client)
    response = post(client, event("reply-1", 1, message="1.42.0", scenario="answer"))
    assert response.status_code == 200
    assert active_facts(response.json()) == {}
    assert response.json()["awaiting_reply"] is None


def test_question_binding_cannot_borrow_approval_from_another_existing_case(ingress_client):
    client, calls = ingress_client
    approved_question(client)
    other = approved_question(client, case_id="case-other")
    before = client.get("/cases/case-intake").json()
    other_before = client.get("/cases/case-other").json()
    calls_before = len(calls)
    response = post(
        client,
        event(
            "reply-1",
            1,
            message="1.42.0",
            scenario="answer",
            reply_to_proposal_id=other["proposal_id"],
        ),
    )
    assert_safe_error(response, 409, "PendingProposalMismatch")
    assert client.get("/cases/case-intake").json() == before
    assert client.get("/cases/case-other").json() == other_before
    assert len(calls) == calls_before


@pytest.mark.parametrize("new_result", [False, True])
def test_explicit_check_results_reach_core_and_only_novel_results_retire_evidence(
    ingress_client, new_result
):
    client, _ = ingress_client
    initial = CaseState(
        case_id="case-intake",
        case_revision=2,
        facts=(
            Fact(
                name="streamlit_version",
                value="1.42.0",
                source_ref="user:initial",
                turn_id="initial",
            ),
            Fact(
                name="cause",
                value="A prior evidence inference.",
                source_ref="doc:prior",
                turn_id="inference:prior",
                provenance_kind="evidence",
            ),
        ),
        checks_performed=("Reinstall failed.",),
        evidence_refs=("doc:prior",),
    )
    api._cases["case-intake"] = api._Case(state=initial)
    check = "The minimal example reproduces the problem." if new_result else "REINSTALL   failed."
    response = post(
        client,
        event(
            "check-3",
            2,
            message="Here is the explicit check result.",
            scenario="answer",
            checks_performed=[check],
        ),
    )
    assert response.status_code == 200
    view = response.json()
    assert view["case_revision"] == 3
    assert view["intake"]["context_changed"] is False
    assert view["intake"]["invalidated_checks"] == []
    assert active_facts(view)["streamlit_version"]["value"] == "1.42.0"
    if new_result:
        assert "cause" not in active_facts(view)
        assert "cause" in view["unknowns"]
        assert view["evidence_refs"] == []
        assert view["checks_performed"] == ["Reinstall failed.", check]
    else:
        assert active_facts(view)["cause"]["value"] == "A prior evidence inference."
        assert view["evidence_refs"] == ["doc:prior"]
        assert view["checks_performed"] == ["Reinstall failed."]


def test_explicit_correction_withdrawal_and_environment_switch_retire_state_and_old_approval(
    ingress_client,
):
    client, _ = ingress_client
    first = post(
        client,
        event(
            scenario="answer",
            reported_facts=[
                {"name": "streamlit_version", "value": "1.41.0"},
                {"name": "python_version", "value": "3.13"},
            ],
            checks_performed=["Reinstalled in the affected environment."],
        ),
    ).json()
    old_proposal = first["pending"]
    # Explicit fixture storage setup: production API does not adopt model
    # facts_delta. This observation represents a prior tracker-owned inference.
    current = api._cases["case-intake"].state
    api._cases["case-intake"].state = CaseState.model_validate(
        {
            **current.model_dump(),
            "facts": (
                *current.facts,
                Fact(
                    name="cause",
                    value="Old source inference.",
                    source_ref="doc:old",
                    turn_id="inference:old",
                    provenance_kind="evidence",
                ),
            ),
            "evidence_refs": ("doc:old",),
        }
    )
    corrected = post(
        client,
        event(
            "correction-2",
            1,
            message="Correction: the affected version is 1.42.0.",
            scenario="answer",
            reported_facts=[{"name": "streamlit_version", "value": "1.42.0"}],
        ),
    )
    assert corrected.status_code == 200
    state = api._cases["case-intake"].state
    known = active_facts(corrected.json())
    assert known["streamlit_version"]["value"] == "1.42.0"
    assert known["python_version"]["value"] == "3.13"
    assert "cause" not in known
    assert state.evidence_refs == ()
    assert state.checks_performed == ()
    assert any(fact.name == "cause" and fact.status == "superseded" for fact in state.facts)
    assert decision(client, old_proposal).status_code == 409

    withdrawn = post(
        client,
        event(
            "withdrawal-3",
            2,
            message="The Streamlit version is not confirmed.",
            scenario="answer",
            reported_facts=[{"name": "streamlit_version", "value": None}],
        ),
    )
    assert withdrawn.status_code == 200
    assert "streamlit_version" not in active_facts(withdrawn.json())
    assert "streamlit_version" in withdrawn.json()["unknowns"]
    switched = post(
        client,
        event(
            "environment-4",
            3,
            message="This is a different environment, version 1.50.0.",
            scenario="answer",
            context_changed=True,
            reported_facts=[{"name": "streamlit_version", "value": "1.50.0"}],
        ),
    )
    assert switched.status_code == 200
    assert set(active_facts(switched.json())) == {"streamlit_version"}
    assert "python_version" in switched.json()["unknowns"]
    assert switched.json()["case_revision"] == 4
