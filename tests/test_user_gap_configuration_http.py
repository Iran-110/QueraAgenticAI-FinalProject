"""Frozen configured-HTTP control with real local ports and authored mock plans.

The temporary catalog is caller configuration, never a user/source instruction.
The actual configured factory, offline Chroma index and SQLite backend are used;
every provider request is intercepted. This measures integration and freshness,
not model-choice quality, source relevance or a successful application fix.
"""

import json
from decimal import Decimal

import httpx
from fastapi.testclient import TestClient
from test_evaluation_live import KEY, CountedMock, provider_response
from test_evaluation_live import index as index

from agent_app import live_backend
from agent_app.contracts import GroundedGap, ProposalHandoff
from agent_app.evaluation import live
from agent_app.llm.budget import BudgetLedger
from agent_app.orchestration.handoff import validate_handoff
from agent_app.testing.http_pilot_runtime import offline_network

TOKEN = "synthetic-user-gap-configuration-review-token"
CALLBACK = GroundedGap(
    name="parent_callback_code",
    kind="user",
    description="The application's parent selector callback is not supplied.",
    necessity=(
        "The user can supply the callback and nearby state updates to inspect the "
        "unseen application path; documentation cannot establish its cause."
    ),
    question="Can you share the parent selector callback and its relevant state updates?",
)


def _message(turn_id, revision, **changes):
    return {
        "message": "The multiselect loses its selection; the parent callback is not supplied.",
        "turn_id": turn_id,
        "expected_revision": revision,
        "reported_facts": [{"name": "streamlit_version", "value": "1.50.0"}],
        "unknowns": [CALLBACK.name],
        **changes,
    }


def _review(pending, review_id):
    return {
        "proposal_id": pending["proposal_id"],
        "case_revision": pending["case_revision"],
        "expected_handoff_sha256": pending["review_handoff"]["handoff_sha256"],
        "review_id": review_id,
        "decision": "approve",
    }


def _callback_question(view):
    pending = view["pending"]
    assert pending is not None and pending["decision"] == "ask"
    assert pending["missing_info"] == [CALLBACK.name]
    assert pending["next_question"] == pending["user_draft"] == CALLBACK.question
    assert pending["facts_delta"] == [] and pending["checks_suggested"] == []
    handoff = validate_handoff(ProposalHandoff.model_validate(pending["review_handoff"]))
    assert handoff.case.case_id == view["case_id"]
    assert handoff.case.case_revision == view["case_revision"]
    assert [gap for gap in handoff.grounded_request.gaps if gap.kind == "user"] == [CALLBACK]
    return pending


def test_configured_http_callback_gap_correction_supply_and_sqlite_review_replay(
    tmp_path, monkeypatch, index
):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    ledger = BudgetLedger.create(
        runtime / "budget.sqlite3", limit_usd=Decimal("1"), opening_spend_usd=Decimal("0")
    )
    monkeypatch.setattr(live, "ROOT", tmp_path)
    catalog = tmp_path / "reviewed-user-gaps.json"
    catalog.write_text(
        json.dumps({"schema_version": 1, "user_gaps": [CALLBACK.model_dump(mode="json")]}),
        encoding="utf-8",
    )
    values = {
        "METIS_LIVE_ENABLED": "true",
        "METIS_API_KEY": KEY,
        "AGENT_EVAL_INDEX": str(index[0]),
        "AGENT_EVAL_SNAPSHOT": index[1],
        "AGENT_EVAL_MANIFEST_SHA256": index[2],
        "AGENT_TRACKER_DB": str(tmp_path / "configured-http.sqlite3"),
        "AGENT_REVIEWER_TOKEN": TOKEN,
        "AGENT_REVIEWER_ID": "fixture-maintainer",
        "AGENT_USER_GAP_CATALOG": str(catalog),
    }
    transports, requests, factories = [], [], []

    def respond(request):
        actual = json.loads(json.loads(request.content)["messages"][1]["content"])["request"]
        requests.append(actual)
        # The authored provider chooses from the actual current catalog, so the
        # unchanged baseline without this configuration bridge escalates.
        return provider_response(request)

    def transport(*_args, **_kwargs):
        intercepted = CountedMock(respond)
        transports.append(intercepted)
        return intercepted

    monkeypatch.setattr(httpx, "HTTPTransport", transport)

    def configured_factory(configuration):
        actual = live.configured_factory(configuration)
        assert isinstance(actual, live.LiveEvaluationAdapters)
        factories.append(actual)
        return actual

    def backend():
        return live_backend.configured_app(values, adapters_factory=configured_factory)

    headers = {"Authorization": "Bearer " + TOKEN}
    with offline_network():
        with TestClient(backend()) as client:
            assert transports == [] and requests == []
            first_response = client.post("/cases/gap-case-a/messages", json=_message("gap-a-1", 0))
            assert first_response.status_code == 200
            first = first_response.json()
            old = _callback_question(first)
            assert first["case_revision"] == 1 and first["actions"] == []

            second_response = client.post("/cases/gap-case-b/messages", json=_message("gap-b-1", 0))
            assert second_response.status_code == 200
            second = second_response.json()
            _callback_question(second)

            correction_response = client.post(
                "/cases/gap-case-a/messages",
                json=_message(
                    "gap-a-2",
                    1,
                    message="Correction: Streamlit is 1.49.1 in the same environment.",
                    reported_facts=[{"name": "streamlit_version", "value": "1.49.1"}],
                ),
            )
            assert correction_response.status_code == 200
            corrected = correction_response.json()
            current = _callback_question(corrected)
            assert corrected["case_revision"] == 2
            assert current["proposal_id"] != old["proposal_id"]
            assert [
                fact["value"]
                for fact in requests[-1]["case"]["facts"]
                if fact["name"] == "streamlit_version" and fact["status"] == "active"
            ] == ["1.49.1"]
            before_stale = len(requests), len(transports)
            stale = client.post(
                "/cases/gap-case-a/decision", json=_review(old, "gap-stale-review"), headers=headers
            )
            assert stale.status_code == 409
            assert (len(requests), len(transports)) == before_stale
            assert client.get("/cases/gap-case-b").json() == second
            assert client.get("/cases/gap-case-a").json()["actions"] == []

            supplied_response = client.post(
                "/cases/gap-case-a/messages",
                json=_message(
                    "gap-a-3",
                    2,
                    message="Here is the parent callback; its effect is not independently verified.",
                    reported_facts=[
                        {"name": CALLBACK.name, "value": "def on_parent_change():\n    pass"}
                    ],
                ),
            )
            assert supplied_response.status_code == 200
            supplied = supplied_response.json()
            pending = supplied["pending"]
            assert supplied["case_revision"] == 3 and supplied["actions"] == []
            assert CALLBACK.name not in supplied["unknowns"]
            assert pending is not None and pending["decision"] == "escalate"
            assert pending["missing_info"] == [] and pending["next_question"] is None
            assert pending["facts_delta"] == [] and pending["checks_suggested"] == []
            handoff = validate_handoff(ProposalHandoff.model_validate(pending["review_handoff"]))
            assert not any(gap.kind == "user" for gap in handoff.grounded_request.gaps)
            assert not any(gap["kind"] == "user" for gap in requests[-1]["gaps"])
            assert client.get("/cases/gap-case-b").json() == second
            operation = _review(pending, "gap-current-review")
            approved_response = client.post(
                "/cases/gap-case-a/decision", json=operation, headers=headers
            )
            assert approved_response.status_code == 200
            approved = approved_response.json()
            assert len(approved["actions"]) == 1 and approved["pending"] is None
            assert approved["quality_claim"] is False
            counted = len(transports), len(requests)
            accounting = ledger.snapshot()

        assert all(factory.active_clients == 0 for factory in factories)
        with TestClient(backend()) as client:
            assert client.get("/cases/gap-case-a").json() == approved
            assert client.get("/cases/gap-case-b").json() == second
            retried = client.post("/cases/gap-case-a/decision", json=operation, headers=headers)
            assert retried.status_code == 200
            replayed = retried.json()
            assert replayed["review"]["replayed"] is True
            assert replayed["actions"] == approved["actions"] and replayed["pending"] is None
            assert replayed["case_revision"] == 3
            assert (len(transports), len(requests)) == counted and ledger.snapshot() == accounting

    assert len(factories) == 2 and len(requests) == len(transports) == 4
    assert all(factory.active_clients == 0 for factory in factories)
    assert all(intercepted.close_calls == 1 for intercepted in transports)
    assert KEY not in json.dumps(replayed) and TOKEN not in json.dumps(replayed)
