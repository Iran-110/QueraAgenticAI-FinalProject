"""Durable HTTP boundary checks with actual SQLite and authored offline ports.

Recreating an application here is not an interpreter restart. The separately
registered HTTP pilot uses fresh worker processes to prove that boundary.
"""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from agent_app import api
from agent_app.persistent_api import create_app
from agent_app.testing.http_pilot_runtime import Observations
from agent_app.tracker.sqlite_tracker import SQLiteCaseTracker, TrackerRejected

TOKEN = "persistent-http-synthetic-review-token"
REVIEWERS = {"fixture-maintainer": TOKEN}
AUTH = {"Authorization": f"Bearer {TOKEN}"}
CASE = "durable-http-case"


def event(turn_id="event-1", revision=0, **extra):
    return {
        "message": "The multiselect loses its selection after a parent rerun.",
        "scenario": "answer",
        "turn_id": turn_id,
        "expected_revision": revision,
        **extra,
    }


def review(proposal, review_id="review-1", decision="approve", **extra):
    return {
        "proposal_id": proposal["proposal_id"],
        "case_revision": proposal["case_revision"],
        "decision": decision,
        "review_id": review_id,
        "expected_handoff_sha256": proposal["review_handoff"]["handoff_sha256"],
        **extra,
    }


def get(client, case_id=CASE):
    response = client.get(f"/cases/{case_id}")
    assert response.status_code == 200
    return response.json()


def send(client, payload=None, case_id=CASE):
    response = client.post(f"/cases/{case_id}/messages", json=payload or event())
    assert response.status_code == 200
    return response.json()


def decide(client, payload, case_id=CASE, headers=None):
    return client.post(
        f"/cases/{case_id}/decision", json=payload, headers=AUTH if headers is None else headers
    )


@pytest.fixture
def runtime(tmp_path):
    path = tmp_path / "durable-api.sqlite3"
    observations = Observations()

    def adapters(scenario):
        return observations.wrap(api._adapters(scenario))

    def fresh(*, factory=adapters, reviewers=REVIEWERS):
        tracker = SQLiteCaseTracker(path, reviewer_tokens=REVIEWERS)
        return tracker, create_app(tracker, reviewer_tokens=reviewers, adapters=factory)

    return fresh, observations


def test_read_new_case_does_not_create_sqlite_record_or_use_memory_fallback(runtime, monkeypatch):
    fresh, observations = runtime
    tracker, app = fresh()
    monkeypatch.setattr(
        api,
        "_cases",
        {CASE: api._Case(state=api.CaseState(case_id=CASE, case_revision=99))},
    )
    with TestClient(app) as client:
        view = get(client)
        assert view["case_revision"] == 0 and view["status"] == "new"
        assert view["pending"] is None and view["intake"] is None
        assert view["log"] == view["actions"] == view["decisions"] == []
        assert view["review"] is None
        assert view["tracker_backend"] != "process_memory_dummy_tracker"
        assert observations.snapshot() == {
            "factory_calls": 0,
            "retrieval_calls": 0,
            "reasoning_calls": 0,
        }
    with tracker._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM cases").fetchone()[0] == 0


@pytest.mark.parametrize(
    "payload",
    [
        {"message": "Widget reset", "scenario": "answer"},
        {"message": "Widget reset", "turn_id": "missing-revision"},
        {"message": "Widget reset", "expected_revision": 0},
        event(expected_revision=True),
        event(reviewer_id="fixture-maintainer"),
        event(approved=True),
    ],
)
def test_invalid_durable_ingress_is_rejected_before_adapter_or_storage(runtime, payload):
    fresh, observations = runtime
    tracker, app = fresh()
    with TestClient(app) as client:
        before = get(client)
        counts = observations.snapshot()
        response = client.post(f"/cases/{CASE}/messages", json=payload)
        assert response.status_code == 422
        assert response.json() == {"detail": "RequestInvalid"}
        assert get(client) == before
        assert observations.snapshot() == counts
    assert tracker.read_case(CASE)["history"] == []


def test_full_pending_projection_is_durable_without_process_cache(runtime, monkeypatch):
    fresh, observations = runtime
    tracker, app = fresh()
    with TestClient(app) as client:
        first = send(client)
        pending = first["pending"]
        assert pending["review_handoff"] == tracker.read_case(CASE)["pending_handoff"]
        assert pending["case_revision"] == first["case_revision"] == 1
        assert pending["model_attempts"] == pending["retrieval_rounds"] == 1
        assert pending["steps"] > 0
        assert pending["synthetic"] and not pending["stale"]
        assert pending["analysis"] == pending["review_handoff"]["analysis"]
        assert pending["evidence"][0]["content_sha256"]
        assert first["run_outcome"] is not None and first["actions"] == []
    counts = observations.snapshot()
    monkeypatch.setattr(api, "_cases", {})
    _reopened, recreated_app = fresh()
    with TestClient(recreated_app) as client:
        assert get(client) == first
    assert observations.snapshot() == counts


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong-synthetic-token"}])
@pytest.mark.parametrize("decision", ["approve", "reject", "edit"])
def test_missing_or_wrong_reviewer_cannot_mutate_or_run_ports(runtime, headers, decision):
    fresh, observations = runtime
    tracker, app = fresh()
    with TestClient(app) as client:
        before = send(client)
        payload = review(before["pending"], decision=decision)
        if decision == "edit":
            payload["edited_draft"] = "Authored edit that requires fresh approval."
        counts = observations.snapshot()
        response = decide(client, payload, headers=headers)
        assert response.status_code == 401
        assert response.json() == {"detail": "ReviewerUnauthorized"}
        assert get(client) == before
        assert observations.snapshot() == counts
    assert tracker.comments(CASE) == []


@pytest.mark.parametrize(
    "authority",
    [
        {"reviewer_id": "fixture-maintainer"},
        {"reviewer_token": TOKEN},
        {"approved": True},
        {"review_result": {"approved": True}},
    ],
)
def test_request_body_cannot_supply_review_authority(runtime, authority):
    fresh, observations = runtime
    tracker, app = fresh()
    with TestClient(app) as client:
        before = send(client)
        counts = observations.snapshot()
        response = decide(client, review(before["pending"], **authority))
        assert response.status_code == 422
        assert response.json() == {"detail": "RequestInvalid"}
        assert get(client) == before
        assert observations.snapshot() == counts
    assert tracker.comments(CASE) == []


@pytest.mark.parametrize("missing", ["review_id", "expected_handoff_sha256"])
def test_review_requires_caller_owned_id_and_exact_handoff_digest(runtime, missing):
    fresh, observations = runtime
    _tracker, app = fresh()
    with TestClient(app) as client:
        before = send(client)
        payload = review(before["pending"])
        del payload[missing]
        counts = observations.snapshot()
        response = decide(client, payload)
        assert response.status_code == 422
        assert get(client) == before
        assert observations.snapshot() == counts


def test_correct_ids_with_wrong_hash_are_refused_without_visible_action(runtime):
    fresh, observations = runtime
    tracker, app = fresh()
    with TestClient(app) as client:
        before = send(client)
        counts = observations.snapshot()
        response = decide(client, review(before["pending"], expected_handoff_sha256="0" * 64))
        assert response.status_code == 409
        assert response.json() == {"detail": "HandoffDigestMismatch"}
        assert get(client) == before
        assert observations.snapshot() == counts
    assert tracker.comments(CASE) == []


def test_server_resolves_reviewer_identity_and_does_not_export_credentials(runtime):
    fresh, _observations = runtime
    tracker, app = fresh()
    with TestClient(app) as client:
        pending = send(client)["pending"]
        response = decide(
            client,
            review(pending),
            headers={**AUTH, "X-Reviewer-ID": "untrusted-header-identity"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["review"]["reviewer_id"] == "fixture-maintainer"
        assert body["actions"][0]["reviewer_id"] == "fixture-maintainer"
        assert TOKEN not in response.text
        assert TOKEN not in str(get(client))
        assert TOKEN not in str(tracker.audit_trace(CASE))


def test_same_review_payload_after_application_recreation_returns_original_receipt_once(runtime):
    fresh, observations = runtime
    tracker, app = fresh()
    with TestClient(app) as client:
        pending = send(client)["pending"]
        payload = review(pending)
        response = decide(client, payload)
        assert response.status_code == 200
        approved = response.json()
        receipt = deepcopy(approved["review"])
        assert receipt["replayed"] is False
        assert receipt["action_id"]
        assert len(approved["actions"]) == 1
        assert len([row for row in approved["log"] if row["role"] == "assistant"]) == 1
    counts = observations.snapshot()
    reopened, recreated_app = fresh()
    with TestClient(recreated_app) as client:
        before = get(client)
        assert before == approved
        repeated = decide(client, payload)
        assert repeated.status_code == 200
        assert repeated.json()["review"] == {**receipt, "replayed": True}
        assert {key: value for key, value in repeated.json().items() if key != "review"} == {
            key: value for key, value in before.items() if key != "review"
        }
        assert get(client) == before
        assert observations.snapshot() == counts
        second_identity = decide(client, {**payload, "review_id": "different-review"})
        assert second_identity.status_code == 409
        assert get(client) == before
    assert len(tracker.comments(CASE)) == len(reopened.comments(CASE)) == 1


@pytest.mark.parametrize("change", [{"decision": "reject"}, {"expected_handoff_sha256": "0" * 64}])
def test_same_review_id_with_different_payload_is_a_conflict(runtime, change):
    fresh, observations = runtime
    tracker, app = fresh()
    with TestClient(app) as client:
        payload = review(send(client)["pending"])
        assert decide(client, payload).status_code == 200
        before = get(client)
        counts = observations.snapshot()
        response = decide(client, {**payload, **change})
        assert response.status_code == 409
        assert response.json() == {"detail": "ReviewConflict"}
        assert get(client) == before
        assert observations.snapshot() == counts
    assert len(tracker.comments(CASE)) == 1


def test_edit_hash_identity_and_original_review_replay_survive_recreation(runtime):
    fresh, observations = runtime
    tracker, app = fresh()
    with TestClient(app) as client:
        original = send(client)["pending"]
        edit = review(
            original,
            "edit-1",
            "edit",
            edited_draft="An authored maintainer revision of the draft.",
        )
        response = decide(client, edit)
        assert response.status_code == 200
        before = response.json()
        replacement = before["pending"]
        assert replacement["edited"] and replacement["edited_from"] == original["proposal_id"]
        assert replacement["proposal_id"] != original["proposal_id"]
        assert (
            replacement["review_handoff"]["handoff_sha256"]
            != original["review_handoff"]["handoff_sha256"]
        )
        assert before["actions"] == []
    counts = observations.snapshot()
    _reopened, recreated_app = fresh()
    with TestClient(recreated_app) as client:
        assert get(client) == before
        replay = decide(client, edit)
        assert replay.status_code == 200
        assert replay.json()["review"] == {**before["review"], "replayed": True}
        assert get(client) == before
        old_id = decide(client, review(original, "approve-old"))
        assert old_id.status_code == 409
        old_hash = decide(
            client,
            review(
                replacement,
                "approve-wrong-hash",
                expected_handoff_sha256=original["review_handoff"]["handoff_sha256"],
            ),
        )
        assert old_hash.status_code == 409
        assert get(client) == before
        approved = decide(client, review(replacement, "approve-edited"))
        assert approved.status_code == 200
        assert approved.json()["log"][-1]["text"] == replacement["user_draft"]
        assert observations.snapshot() == counts
    assert len(tracker.comments(CASE)) == 1


def test_correction_invalidates_old_approval_and_old_ingress_never_rewinds_state(runtime):
    fresh, observations = runtime
    tracker, app = fresh()
    initial = event(
        reported_facts=[{"name": "streamlit_version", "value": "1.50.0"}],
        checks_performed=["Minimal example reproduced on 1.50.0."],
    )
    with TestClient(app) as client:
        first = send(client, initial)
        correction = event(
            "correction-2",
            1,
            message="Correction: the deployed version is 1.49.1.",
            reported_facts=[{"name": "streamlit_version", "value": "1.49.1"}],
        )
        current = send(client, correction)
        assert current["case_revision"] == 2
        assert current["checks_performed"] == current["evidence_refs"] == []
        versions = [row for row in current["facts"] if row["name"] == "streamlit_version"]
        assert [(row["value"], row["status"]) for row in versions] == [
            ("1.50.0", "superseded"),
            ("1.49.1", "active"),
        ]
        counts = observations.snapshot()
        stale = decide(client, review(first["pending"], "old-approval"))
        assert stale.status_code == 409 and get(client) == current
        replay = client.post(f"/cases/{CASE}/messages", json=initial)
        assert replay.status_code == 200
        assert replay.json()["intake"] == {**first["intake"], "replayed": True}
        assert replay.json()["case_revision"] == 2
        assert get(client) == current
        assert observations.snapshot() == counts
    assert tracker.comments(CASE) == []


@pytest.mark.parametrize(
    "change", [{"message": "Different issue under the same event ID."}, {"scenario": "refine"}]
)
def test_original_event_identity_rejects_changed_content_or_adapter_context(runtime, change):
    fresh, observations = runtime
    _tracker, app = fresh()
    original = event()
    with TestClient(app) as client:
        before = send(client, original)
        counts = observations.snapshot()
        response = client.post(f"/cases/{CASE}/messages", json={**original, **change})
        assert response.status_code == 409
        assert response.json() == {"detail": "EventConflict"}
        assert get(client) == before
        assert observations.snapshot() == counts


def test_original_approved_review_replay_after_correction_returns_current_view(runtime):
    fresh, observations = runtime
    tracker, app = fresh()
    with TestClient(app) as client:
        initial = send(
            client,
            event(reported_facts=[{"name": "streamlit_version", "value": "1.50.0"}]),
        )
        payload = review(initial["pending"])
        approved = decide(client, payload)
        assert approved.status_code == 200
        original_receipt = approved.json()["review"]
        corrected = send(
            client,
            event(
                "correction-2",
                1,
                message="Correction: the deployed version is 1.49.1.",
                reported_facts=[{"name": "streamlit_version", "value": "1.49.1"}],
            ),
        )
    counts = observations.snapshot()
    _reopened, recreated_app = fresh()
    with TestClient(recreated_app) as client:
        assert get(client) == corrected
        replay = decide(client, payload)
        assert replay.status_code == 200
        assert replay.json()["review"] == {**original_receipt, "replayed": True}
        assert replay.json()["case_revision"] == 2
        assert replay.json()["pending"] == corrected["pending"]
        assert get(client) == corrected
        assert observations.snapshot() == counts
    assert len(tracker.comments(CASE)) == 1


def test_foreign_proposal_cannot_approve_current_case(runtime):
    fresh, observations = runtime
    tracker, app = fresh()
    with TestClient(app) as client:
        one = send(client)
        other = send(client, case_id="other-durable-case")
        before = get(client)
        counts = observations.snapshot()
        response = decide(client, review(other["pending"]))
        assert response.status_code == 409
        assert get(client) == before == one
        assert get(client, "other-durable-case") == other
        assert observations.snapshot() == counts
    assert tracker.comments(CASE) == tracker.comments("other-durable-case") == []


def test_approved_canonical_question_binding_survives_application_recreation(runtime):
    fresh, observations = runtime
    _tracker, app = fresh()
    initial = event(scenario="ask_version")
    with TestClient(app) as client:
        pending = send(client, initial)["pending"]
        approved = decide(client, review(pending)).json()
        assert approved["status"] == "awaiting_user"
    _reopened, recreated_app = fresh()
    with TestClient(recreated_app) as client:
        assert get(client) == approved
        replied = send(
            client,
            event(
                "version-reply",
                1,
                message="1.50.0",
                reply_to_proposal_id=pending["proposal_id"],
            ),
        )
        assert replied["intake"]["preparation"] == "canonical_version_reply"
        assert replied["facts"][-1]["value"] == "1.50.0"
        assert initial["message"] in observations.observed_inputs[-1]["user_message"]
        assert "1.50.0" in observations.observed_inputs[-1]["user_message"]


def test_setup_stop_and_original_event_replay_are_durable_without_rerunning_ports(runtime):
    fresh, observations = runtime

    def stopped(_scenario):
        observations.factory_calls += 1
        raise RuntimeError("private-http-setup-marker")

    tracker, app = fresh(factory=stopped)
    with TestClient(app) as client:
        before = send(client)
        assert before["case_revision"] == 1 and before["pending"] is None
        assert before["run_outcome"] is not None
        assert "private-http-setup-marker" not in str(before)
        assert observations.snapshot() == {
            "factory_calls": 1,
            "retrieval_calls": 0,
            "reasoning_calls": 0,
        }
    _reopened, recreated_app = fresh(factory=stopped)
    with TestClient(recreated_app) as client:
        assert get(client) == before
        repeated = send(client)
        assert repeated["intake"] == {**before["intake"], "replayed": True}
        assert get(client) == before
        assert observations.snapshot() == {
            "factory_calls": 1,
            "retrieval_calls": 0,
            "reasoning_calls": 0,
        }
    assert tracker.comments(CASE) == []


def test_concurrent_identical_events_across_independent_apps_construct_one_run(runtime):
    fresh, observations = runtime
    tracker, app_one = fresh()
    _other_tracker, app_two = fresh()
    with TestClient(app_one) as one, TestClient(app_two) as two:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(
                pool.map(
                    lambda client: client.post(f"/cases/{CASE}/messages", json=event()), [one, two]
                )
            )
        assert [response.status_code for response in results] == [200, 200]
        assert sorted(response.json()["intake"]["replayed"] for response in results) == [
            False,
            True,
        ]
        assert get(one) == get(two)
        assert observations.snapshot() == {
            "factory_calls": 1,
            "retrieval_calls": 1,
            "reasoning_calls": 1,
        }
    assert len(tracker.read_case(CASE)["history"]) == 1


def test_concurrent_same_review_across_independent_apps_writes_one_action(runtime):
    fresh, observations = runtime
    tracker, app_one = fresh()
    _other_tracker, app_two = fresh()
    with TestClient(app_one) as one, TestClient(app_two) as two:
        payload = review(send(one)["pending"])
        counts = observations.snapshot()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda client: decide(client, payload), [one, two]))
        assert [response.status_code for response in results] == [200, 200]
        receipts = [response.json()["review"] for response in results]
        assert sorted(receipt["replayed"] for receipt in receipts) == [False, True]
        assert receipts[0]["action_id"] == receipts[1]["action_id"]
        assert get(one) == get(two)
        assert len(get(one)["actions"]) == 1
        assert observations.snapshot() == counts
    assert len(tracker.comments(CASE)) == 1


def test_unauthenticated_retry_cannot_bypass_review_authentication(runtime):
    fresh, observations = runtime
    tracker, app = fresh()
    with TestClient(app) as client:
        payload = review(send(client)["pending"])
        assert decide(client, payload).status_code == 200
        before = get(client)
        counts = observations.snapshot()
        unauthorized = decide(client, payload, headers={})
        assert unauthorized.status_code == 401
        assert get(client) == before
        assert observations.snapshot() == counts
    assert len(tracker.comments(CASE)) == 1


def test_empty_or_mismatched_server_reviewer_configuration_fails_closed(runtime):
    fresh, observations = runtime
    for configured in ({}, {"different-server-reviewer": TOKEN}):
        _tracker, app = fresh(reviewers=configured)
        with TestClient(app) as client:
            before = get(client)
            if before["pending"] is None:
                before = send(client)
            counts = observations.snapshot()
            response = decide(client, review(before["pending"]))
            assert response.status_code == 401
            assert get(client) == before
            assert observations.snapshot() == counts


def test_tool_failure_after_comment_insert_rolls_back_http_review_and_retry_commits_once(
    runtime, monkeypatch
):
    fresh, observations = runtime
    tracker, app = fresh()
    original = tracker._record_local_comment

    def fail_after_insert(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("private-post-insert-tool-marker")

    with TestClient(app) as client:
        before = send(client)
        payload = review(before["pending"])
        counts = observations.snapshot()
        monkeypatch.setattr(tracker, "_record_local_comment", fail_after_insert)
        failed = decide(client, payload)
        assert failed.status_code == 503
        assert failed.json() == {"detail": "TrackerUnavailable"}
        assert "private-post-insert-tool-marker" not in failed.text
        assert get(client) == before
        assert tracker.comments(CASE) == []
        assert observations.snapshot() == counts
    # A recreated application reads the rolled-back pending proposal and can
    # safely commit the exact original review operation once.
    reopened, recreated_app = fresh()
    with TestClient(recreated_app) as client:
        assert get(client) == before
        approved = decide(client, payload)
        assert approved.status_code == 200
        first_receipt = approved.json()["review"]
        repeated = decide(client, payload)
        assert repeated.status_code == 200
        assert repeated.json()["review"] == {**first_receipt, "replayed": True}
        assert len(get(client)["actions"]) == 1
        assert observations.snapshot() == counts
    assert len(reopened.comments(CASE)) == 1


@pytest.mark.parametrize("malformed_code", ["unknown", "nonstring", "raising_attribute"])
def test_untrusted_tracker_exception_codes_export_only_fixed_diagnostics(
    runtime, monkeypatch, malformed_code
):
    fresh, observations = runtime
    tracker, app = fresh()

    class HostileCode:
        def __eq__(self, _other):
            raise RuntimeError("private-tracker-comparison-marker")

    class RaisingAttribute(TrackerRejected):
        @property
        def code(self):
            raise RuntimeError("private-tracker-attribute-marker")

        @code.setter
        def code(self, _value):
            pass

    failure = (
        RaisingAttribute("ReviewConflict")
        if malformed_code == "raising_attribute"
        else TrackerRejected("private-tracker-unknown-code")
    )
    if malformed_code == "nonstring":
        failure.code = HostileCode()

    def faulty_review(*_args, **_kwargs):
        raise failure

    with TestClient(app) as client:
        before = send(client)
        counts = observations.snapshot()
        monkeypatch.setattr(tracker, "review", faulty_review)
        response = decide(client, review(before["pending"]))
        assert response.status_code == 503
        assert response.json() == {"detail": "TrackerUnavailable"}
        assert "private-tracker" not in response.text
        assert get(client) == before
        assert observations.snapshot() == counts
