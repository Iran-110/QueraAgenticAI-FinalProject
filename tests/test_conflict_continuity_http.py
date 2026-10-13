"""Authored conflict-continuity controls through HTTP, mock gateway and SQLite.

The source pair is an exposed V9 control, including explicitly synthetic false
text. These tests establish policy and handoff behavior, not model/RAG quality.
No provider, production ledger, environment key or real network is used.
"""

import json
from decimal import Decimal

import httpx
import pytest
from fastapi.testclient import TestClient
from test_conflict_continuity import (
    OFFICIAL,
    SYNTHETIC,
    CurrentPoolFactory,
    ScriptedPlanner,
    latest_pool,
)

from agent_app.contracts import GroundedRequest, ProposalHandoff
from agent_app.llm.budget import BudgetLedger
from agent_app.llm.config import MetisConfig
from agent_app.orchestration.handoff import validate_handoff
from agent_app.persistent_api import create_app
from agent_app.testing.controlled_decision_inputs import load_conditions
from agent_app.testing.fakes import FakeRetriever
from agent_app.testing.grounded_http_binding import GroundedHttpBinding
from agent_app.testing.http_pilot_runtime import offline_network
from agent_app.tracker.sqlite_tracker import SQLiteCaseTracker

CASE = "conflict-continuity-http"
MARKER = "unresolved_prior_source_conflict"
TOKEN = "synthetic-conflict-review-token"
REVIEWERS = {"fixture-maintainer": TOKEN}
AUTH = {"Authorization": "Bearer " + TOKEN}


@pytest.fixture
def condition():
    return next(
        item
        for item in load_conditions()
        if item.condition_id == "controlled-v8-same-version-synthetic-conflict"
    )


@pytest.fixture(autouse=True)
def forbid_live_configuration(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Only temporary ledger and mandatory MockTransport are allowed")

    monkeypatch.setattr(MetisConfig, "from_env", forbidden)
    monkeypatch.setattr(httpx.HTTPTransport, "__init__", forbidden)


def message(condition):
    return {
        "message": condition.user_message,
        "turn_id": "initial-current-input",
        "expected_revision": 0,
        "scenario": "answer",
        "reported_facts": [
            {"name": fact.name, "value": fact.value} for fact in condition.case.facts
        ],
        "unknowns": list(condition.case.unknowns),
        "checks_performed": list(condition.case.checks_performed),
    }


def review(pending, **changes):
    return {
        "proposal_id": pending["proposal_id"],
        "case_revision": pending["case_revision"],
        "expected_handoff_sha256": pending["review_handoff"]["handoff_sha256"],
        "review_id": "one-human-review",
        "decision": "approve",
        **changes,
    }


def runtime(tmp_path, condition, mode, final_decision):
    ledger = BudgetLedger.create(
        tmp_path / "mock-cost.sqlite3", limit_usd=Decimal("1"), opening_spend_usd=Decimal("0")
    )
    factory = CurrentPoolFactory(condition)
    stages = []
    allocations = []
    binding = GroundedHttpBinding(
        ledger,
        snapshot_id=condition.bundles[0].snapshot_id,
        retriever_factory=lambda: FakeRetriever(
            [condition.bundles[0], latest_pool(condition, mode)]
        ),
        planner_factory=lambda: ScriptedPlanner(("retrieve_more", final_decision)),
        request_factory=factory,
    )

    class ObservedTracker(SQLiteCaseTracker):
        def stage_run_proposal(self, *args, **kwargs):
            stages.append((args, kwargs))
            return super().stage_run_proposal(*args, **kwargs)

    def ports(case, scenario):
        allocations.append((case.case_id, case.case_revision, scenario))
        assert case.case_id == CASE and case.case_revision == 1
        return binding.adapters(scenario)

    def fresh_app():
        tracker = ObservedTracker(tmp_path / "cases.sqlite3", reviewer_tokens=REVIEWERS)
        return create_app(
            tracker,
            reviewer_tokens=REVIEWERS,
            case_adapters=ports,
            reasoning_label="grounded_fake_gateway",
        )

    return fresh_app, binding, factory, stages, allocations


def sent_requests(binding):
    records = binding.records
    assert [record["context"]["attempt_index"] for record in records] == [1, 2]
    assert len({record["context"]["run_id"] for record in records}) == 1
    assert {
        (record["context"]["case_id"], record["context"]["case_revision"]) for record in records
    } == {(CASE, 1)}
    assert all(record["reservation_after_attempt"]["status"] == "settled" for record in records)
    return [
        GroundedRequest.model_validate(
            json.loads(record["provider_payload"]["messages"][1]["content"])["request"]
        )
        for record in records
    ]


@pytest.mark.parametrize("mode", ["missing_member", "changed_same_id", "warning_resolution"])
def test_later_pool_cannot_stage_answer_to_previously_declared_conflict(tmp_path, condition, mode):
    fresh, binding, factory, stages, allocations = runtime(tmp_path, condition, mode, "answer")
    payload = message(condition)
    with offline_network(), TestClient(fresh()) as client:
        response = client.post(f"/cases/{CASE}/messages", json=payload)
        assert response.status_code == 200
        view = response.json()
        assert view["pending"] is None and view["actions"] == []
        assert stages == []
        outcome = view["run_outcome"]
        assert "grounded_conflict_unresolved" in json.dumps(outcome)
        counts = binding.snapshot(), list(allocations)
        replay = client.post(f"/cases/{CASE}/messages", json=payload)
        assert replay.status_code == 200 and replay.json()["intake"]["replayed"]
        assert (binding.snapshot(), allocations) == counts
    first, second = sent_requests(binding)
    assert first.conflict_groups and not second.conflict_groups
    assert not any(gap.name == MARKER for gap in factory.requests[1].gaps)
    marker = next(gap for gap in second.gaps if gap.name == MARKER)
    assert marker.kind == "source" and marker.question is None
    assert second.context_sha256 != factory.requests[1].context_sha256
    assert len(binding.records) == 2 and binding.all_clients_closed
    assert binding.snapshot()["actual_paid_requests"] == 0
    assert binding.snapshot()["reserved_reservations"] == 0
    assert binding.snapshot()["uncertain_reservations"] == 0


@pytest.mark.parametrize("mode", ["missing_member", "changed_same_id"])
def test_safe_escalation_stores_actual_augmented_wire_and_requires_one_human_approval(
    tmp_path, condition, mode
):
    fresh, binding, factory, stages, allocations = runtime(tmp_path, condition, mode, "escalate")
    payload = message(condition)
    with offline_network(), TestClient(fresh()) as client:
        response = client.post(f"/cases/{CASE}/messages", json=payload)
        assert response.status_code == 200
        initial = response.json()
        pending = initial["pending"]
        assert pending is not None and pending["decision"] == "escalate"
        assert initial["actions"] == [] and len(stages) == 1
        assert "unresolved" in pending["maintainer_summary"].casefold()
        assert "No conflict has been declared" not in pending["maintainer_summary"]
        handoff = validate_handoff(ProposalHandoff.model_validate(pending["review_handoff"]))
        first, actual = sent_requests(binding)
        assert first.conflict_groups and not actual.conflict_groups
        assert actual == handoff.grounded_request
        assert actual.evidence == handoff.evidence
        assert actual.case.case_id == CASE and actual.case.case_revision == 1
        assert actual.context_sha256 != factory.requests[1].context_sha256
        marker = next(gap for gap in actual.gaps if gap.name == MARKER)
        assert marker.kind == "source" and marker.question is None
        assert not any(gap.name == MARKER for gap in factory.requests[1].gaps)
        assert {link.chunk_id for link in handoff.analysis.evidence_links} == {OFFICIAL}
        if mode == "missing_member":
            assert SYNTHETIC not in {hit.chunk_id for hit in handoff.evidence.hits}
        old = next(hit for hit in condition.bundles[0].hits if hit.chunk_id == SYNTHETIC)
        assert old.excerpt not in handoff.analysis.maintainer_summary
        assert old.excerpt not in handoff.analysis.user_draft
        assert binding.all_clients_closed
        counts = binding.snapshot(), list(allocations), len(stages)
        unauthorized = client.post(f"/cases/{CASE}/decision", json=review(pending))
        assert unauthorized.status_code == 401
        wrong_digest = client.post(
            f"/cases/{CASE}/decision",
            json=review(pending, expected_handoff_sha256="0" * 64),
            headers=AUTH,
        )
        assert wrong_digest.status_code == 409
        assert client.get(f"/cases/{CASE}").json()["actions"] == []
        assert (binding.snapshot(), allocations, len(stages)) == counts
        approved = client.post(f"/cases/{CASE}/decision", json=review(pending), headers=AUTH)
        assert approved.status_code == 200
        assert len(approved.json()["actions"]) == 1
        action = approved.json()["actions"][0]
        assert (binding.snapshot(), allocations, len(stages)) == counts
    with offline_network(), TestClient(fresh()) as client:
        retried = client.post(f"/cases/{CASE}/decision", json=review(pending), headers=AUTH)
        assert retried.status_code == 200 and retried.json()["review"]["replayed"]
        assert retried.json()["actions"] == [action]
        replay = client.post(f"/cases/{CASE}/messages", json=payload)
        assert replay.status_code == 200 and replay.json()["intake"]["replayed"]
        assert replay.json()["actions"] == [action]
        assert (binding.snapshot(), allocations, len(stages)) == counts
        stored = client.get(f"/cases/{CASE}").json()
    public = json.dumps({"records": binding.records, "view": stored})
    assert TOKEN not in public and "public-synthetic-persistent-grounded-key" not in public
    assert "Authorization" not in public and '"headers"' not in public
    assert len(binding.records) == 2 and len(allocations) == len(stages) == 1
    assert binding.snapshot()["actual_paid_requests"] == 0
