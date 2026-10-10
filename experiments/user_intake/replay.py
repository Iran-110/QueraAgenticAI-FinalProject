"""Replay one registered development conversation through offline HTTP/core ports.

No index, model, paid request, durable tracker or source code execution is used.
Passing this authored conversation verifies software boundaries, not model quality.
"""

import argparse
import copy
import hashlib
import json
import sys
from importlib.metadata import version as metadata_version
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import NAMESPACE_URL, uuid5

from fastapi.testclient import TestClient

from agent_app import api
from agent_app.contracts import AnalysisResult, CaseState, EvidenceBundle, Fact, UserTurn
from agent_app.orchestration import engine as engine_module
from agent_app.testing.fakes import FakeReasoner, FakeRetriever
from agent_app.tracker.dummy_tracker import DummyTracker

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = Path(__file__).with_name("case-widget-version-correction.json")
FIXTURE_SHA256 = "aabeffe7c400cc5d8a0c6fa3ddc333464ee486866cad319190915a570aa7aa4a"
REGISTRATION_COMMIT = "a3d5eeb"

# Fingerprint the executed boundary, including the fixture injector itself.
# Git HEAD alone would misidentify a replay with uncommitted source changes.
CODE_PATHS = (
    "experiments/user_intake/replay.py",
    "src/agent_app/api.py",
    "src/agent_app/contracts.py",
    "src/agent_app/demo.py",
    "src/agent_app/orchestration/engine.py",
    "src/agent_app/orchestration/intake.py",
    "src/agent_app/orchestration/turns.py",
    "src/agent_app/orchestration/ports.py",
    "src/agent_app/reasoning/output.py",
    "src/agent_app/reasoning/code_checks.py",
    "src/agent_app/reasoning/proposal_checks.py",
    "src/agent_app/testing/fakes.py",
    "src/agent_app/tracker/dummy_tracker.py",
    "uv.lock",
)


def code_manifest() -> dict[str, str]:
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in CODE_PATHS}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def load_fixture(path: Path = FIXTURE_PATH) -> dict[str, Any]:
    """Require the exact predeclared source/input/expectation pack before execution."""
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != FIXTURE_SHA256:
        raise ValueError("Registered user-intake fixture hash mismatch")
    fixture = json.loads(payload)
    provenance = fixture["provenance"]
    source = ROOT / provenance["source_fixture"]
    if hashlib.sha256(source.read_bytes()).hexdigest() != provenance["source_fixture_sha256"]:
        raise ValueError("Registered source fixture hash mismatch")
    source_pack = json.loads(source.read_bytes())
    source_case = next(
        case for case in source_pack["cases"] if case["id"] == provenance["source_scenario_id"]
    )
    assert fixture["evidence_bundles"]["official-mixed-v8"] == source_case["bundles"][0]
    assert fixture["execution_boundary"]["offline_only"]
    assert fixture["execution_boundary"]["paid_calls"] == 0
    assert not fixture["execution_boundary"]["model_RAG_or_final_test_quality_claim"]
    assert len(fixture["turns"]) == 7
    CaseState.model_validate(fixture["initial_case"])
    for bundle in fixture["evidence_bundles"].values():
        EvidenceBundle.model_validate(bundle)
    for turn in fixture["turns"]:
        UserTurn.model_validate(turn["user_turn"])
        AnalysisResult.model_validate(turn["port_fixture"]["authored_analysis"])
        for field in (
            "known_information_after_user_input",
            "user_clarifiable_gaps",
            "documentation_or_evidence_gaps",
            "acceptable_decisions",
            "claim_acceptance",
            "question_acceptance",
        ):
            assert turn["inventory"][field]
    return fixture


def _normalise(value: Any, proposal_names: dict[str, str]) -> Any:
    if isinstance(value, str):
        return proposal_names.get(value, value)
    if isinstance(value, list):
        return [_normalise(item, proposal_names) for item in value]
    if isinstance(value, dict):
        return {key: _normalise(item, proposal_names) for key, item in value.items()}
    return value


def _active_user(state: CaseState, name: str) -> Fact | None:
    return next(
        (
            fact
            for fact in state.facts
            if fact.name == name and fact.provenance_kind == "user" and fact.status == "active"
        ),
        None,
    )


def _seed_checkpoint(case: api._Case, checkpoint: dict[str, Any]) -> dict[str, Any]:
    """Apply an explicit fixture precondition; never persist a model's facts_delta."""
    assert case.state.case_revision == checkpoint["seed_at_revision"]
    seeds = [Fact.model_validate(fact) for fact in checkpoint["seed_active_evidence_facts"]]
    names = {fact.name for fact in seeds}
    prior = [
        fact.model_copy(update={"status": "superseded"})
        if fact.name in names and fact.status == "active"
        else fact
        for fact in case.state.facts
    ]
    case.state = CaseState.model_validate(
        {
            **case.state.model_dump(mode="json"),
            "facts": [fact.model_dump(mode="json") for fact in prior + seeds],
            "unknowns": [name for name in case.state.unknowns if name not in names],
            "evidence_refs": checkpoint["seed_evidence_refs"],
        }
    )
    return {
        "before_turn": checkpoint["before_turn"],
        "seed_at_revision": checkpoint["seed_at_revision"],
        "fixture_only_not_model_persistence": True,
        "seed_facts": [fact.model_dump(mode="json") for fact in seeds],
        "seed_evidence_refs": list(case.state.evidence_refs),
    }


def _assert_turn(
    fixture: dict[str, Any],
    turn: dict[str, Any],
    view: dict[str, Any],
    state: CaseState,
    reasoning_case: CaseState,
    checkpoint: dict[str, Any] | None,
) -> None:
    expected = turn["expected"]
    assert view["case_revision"] == state.case_revision == expected["case_revision"]
    assert reasoning_case.case_revision == state.case_revision
    assert reasoning_case.facts == state.facts and reasoning_case.unknowns == state.unknowns
    assert reasoning_case.evidence_refs == state.evidence_refs
    assert reasoning_case.pending_proposal_id is None, "Prior proposal reached the reasoner"
    assert view["intake"]["context_changed"] == expected["transition_context_changed"]
    assert list(state.checks_performed) == expected["checks_performed"]
    assert state.checks_performed == reasoning_case.checks_performed
    assert view["awaiting_reply"] is None
    for name, expected_name in (
        ("streamlit_version", "active_user_version"),
        ("python_version", "active_user_python"),
    ):
        fact = _active_user(state, name)
        wanted = expected[expected_name]
        assert (fact.value if fact else None) == wanted, f"Incorrect active {name}"
        assert (name in state.unknowns) == (wanted is None)
        assert _active_user(reasoning_case, name) == fact
        if fact is not None:
            source_turn = (
                "intake-1"
                if name == "python_version" and state.case_revision < 5
                else (
                    f"intake-{state.case_revision}"
                    if name == "streamlit_version" and state.case_revision in (2, 3)
                    else "intake-5"
                )
            )
            assert fact.turn_id == source_turn and fact.source_ref == f"user:{source_turn}", (
                "User fact attribution was replaced by evidence or another turn"
            )
    if state.case_revision >= 3:
        assert all(
            fact.status == "superseded"
            for fact in state.facts
            if fact.name == "streamlit_version" and fact.turn_id == "intake-2"
        )
    if expected.get("old_environment_user_facts_are_superseded"):
        assert all(
            fact.status == "superseded"
            for fact in state.facts
            if fact.provenance_kind == "user" and fact.turn_id == "intake-1"
        )
        assert {
            fact.name
            for fact in state.facts
            if fact.status == "active" and fact.provenance_kind == "user"
        } == {"streamlit_version", "python_version"}
    proposal = view["pending"]
    assert proposal is not None and not proposal["stale"]
    assert proposal["case_revision"] == state.case_revision
    assert proposal["decision"] == expected["proposal_decision"]
    assert proposal["decision"] in turn["inventory"]["acceptable_decisions"]
    authored = turn["port_fixture"]["authored_analysis"]
    for field in ("user_draft", "maintainer_summary", "rationale", "missing_info", "next_question"):
        assert proposal[field] == authored[field], f"Proposal field differs: {field}"
    active_names = {
        fact.name
        for fact in state.facts
        if fact.status == "active" and fact.provenance_kind == "user"
    }
    assert not active_names.intersection(proposal["missing_info"])
    for field, limit in (
        ("model_attempts", "max_model_attempts"),
        ("retrieval_rounds", "max_retrieval_rounds"),
        ("steps", "max_steps"),
    ):
        assert 0 < proposal[field] <= fixture["limits"][limit]
    if proposal["decision"] == "answer":
        bundle = fixture["evidence_bundles"][turn["port_fixture"]["bundle"]]
        hits = {hit["chunk_id"]: hit for hit in bundle["hits"]}
        assert [link["chunk_id"] for link in proposal["evidence"]] == expected["cited_chunks"]
        for citation in proposal["evidence"]:
            hit = hits[citation["chunk_id"]]
            assert citation["claim"] == citation["excerpt"] == hit["excerpt"], (
                "Answer must quote the complete registered excerpt"
            )
            assert hit["excerpt"] in proposal["user_draft"]
            assert citation["source_url"] == hit["source_url"]
            assert citation["source_span"] == hit["source_span"]
            assert "does not establish a cause or a verified fix" in proposal["user_draft"]
    if state.case_revision == 3:
        assert proposal["evidence"] == [], "1.50.0 source reused as corrected 1.49.1 advice"
    if checkpoint:
        wanted = checkpoint["expected_after_transition"]
        name = checkpoint["seed_active_evidence_facts"][0]["name"]
        inference = [fact for fact in state.facts if fact.name == name][-1]
        assert inference.status == wanted["evidence_fact_status"], "Stale inference retained"
        assert list(state.evidence_refs) == wanted["evidence_refs"], "Stale reference retained"
        assert (name in state.unknowns) == wanted["retired_inference_becomes_unknown"]
        assert view["intake"]["context_changed"] == wanted["context_changed"]
        assert reasoning_case.evidence_refs == state.evidence_refs
        assert reasoning_case.facts == state.facts


def replay_pilot(fixture_path: Path = FIXTURE_PATH) -> dict[str, Any]:
    if not __debug__:
        raise RuntimeError("AssertionChecksDisabled")
    code_at_start = code_manifest()
    fixture = load_fixture(fixture_path)
    case_id = fixture["initial_case"]["case_id"]
    scripted: list[str] = []
    retrievers: list[FakeRetriever] = []
    reasoners: list[FakeReasoner] = []
    retrieval_revisions: list[int] = []
    current_turn: list[dict[str, Any]] = []
    proposal_names: dict[str, str] = {}
    checks: list[dict[str, Any]] = []

    class RecordingRetriever(FakeRetriever):
        def __init__(self, responses):
            super().__init__(responses)
            retrievers.append(self)

        def search(self, request):
            retrieval_revisions.append(api._cases[case_id].state.case_revision)
            return super().search(request)

    class RecordingReasoner(FakeReasoner):
        def __init__(self, responses):
            super().__init__(responses)
            reasoners.append(self)

    def script(scenario):
        turn = current_turn[0]
        assert scenario == turn["wire_request_template"]["scenario"]
        scripted.append(turn["id"])
        spec = turn["port_fixture"]
        # Never pass scenario inventory, expectations or seed metadata into a port.
        return (
            [EvidenceBundle.model_validate(fixture["evidence_bundles"][spec["bundle"]])],
            [AnalysisResult.model_validate(spec["authored_analysis"])],
        )

    def fixed_uuid():
        return uuid5(NAMESPACE_URL, f"{fixture['fixture_id']}:{current_turn[0]['id']}:proposal")

    def assert_no_mutation(client, before):
        assert client.get(f"/cases/{case_id}").json() == before

    with (
        patch.object(api, "_cases", {}),
        patch.object(api, "tracker", DummyTracker()),
        patch.object(
            api, "SNAPSHOT_ID", fixture["evidence_bundles"]["official-mixed-v8"]["snapshot_id"]
        ),
        patch.object(api, "_script", script),
        patch.object(api, "FakeRetriever", RecordingRetriever),
        patch.object(api, "FakeReasoner", RecordingReasoner),
        patch.object(engine_module, "uuid4", fixed_uuid),
        TestClient(api.app) as client,
    ):
        previous_proposal = None
        approved_question_id = None
        observations = []
        for turn in fixture["turns"]:
            current_turn[:] = [turn]
            checkpoint = next(
                (
                    item
                    for item in fixture["controlled_transition_checkpoints"]
                    if item["before_turn"] == turn["id"]
                ),
                None,
            )
            seed_receipt = _seed_checkpoint(api._cases[case_id], checkpoint) if checkpoint else None
            request = copy.deepcopy(turn["wire_request_template"])
            if request.get("reply_to_proposal_id") == "$approved_proposal_id":
                assert approved_question_id is not None
                request["reply_to_proposal_id"] = approved_question_id
            prior = client.get(f"/cases/{case_id}").json()
            assistants_before = sum(entry["role"] == "assistant" for entry in prior["log"])
            response = client.post(f"/cases/{case_id}/messages", json=request)
            assert response.status_code == 200, f"{turn['id']} failed: {response.json()}"
            view = response.json()
            proposal = view["pending"]
            assert proposal is not None, f"{turn['id']} produced no proposal"
            proposal_names[proposal["proposal_id"]] = f"proposal:{turn['id']}"
            assert len(scripted) == len(reasoners) == len(retrievers) == view["case_revision"]
            reasoner, retriever = reasoners[-1], retrievers[-1]
            assert len(reasoner.inputs) == len(reasoner.contexts) == len(retriever.requests) == 1
            reasoning_case, message, evidence = reasoner.inputs[0]
            state = api._cases[case_id].state
            _assert_turn(fixture, turn, view, state, reasoning_case, checkpoint)
            assert sum(entry["role"] == "assistant" for entry in view["log"]) == assistants_before
            assert message == turn["user_turn"]["message"]
            assert evidence == EvidenceBundle.model_validate(
                fixture["evidence_bundles"][turn["port_fixture"]["bundle"]]
            )
            context = reasoner.contexts[0]
            assert context.case_id == case_id and context.case_revision == state.case_revision
            assert (
                context.attempt_index == 1
                and context.query_limit <= fixture["limits"]["max_queries_per_round"]
            )
            assert context.proposal_requirements is None and context.output_feedback is None
            retrieval = retriever.requests[0]
            assert (
                retrieval.snapshot_id == evidence.snapshot_id
                and retrieval_revisions[-1] == state.case_revision
            )
            assert 1 <= len(retrieval.queries) <= fixture["limits"]["max_queries_per_round"]
            assert retrieval.top_k == len(evidence.hits) == 5
            queries = " ".join(retrieval.queries)
            version = turn["expected"]["active_user_version"]
            if version is not None:
                assert f"streamlit_version={version}" in queries
            else:
                assert "streamlit_version=" not in queries
            if turn["id"] == "intake-3":
                # The user's correction mentions the old value in prose. Only
                # the packed confirmed-fact token must use the new version.
                assert "streamlit_version=1.50.0" not in queries
            if state.case_revision >= 5:
                assert "python_version=3.12.9" not in queries
                assert "python_version=3.13" in queries
            assert "prior_evidence_observation=" not in queries

            raw_turn = api.MessageRequest.model_validate(request).user_turn(
                case_id, prior["case_revision"]
            )
            ingress_hash = _digest(
                {
                    "turn": raw_turn.model_dump(mode="json"),
                    "scenario": request["scenario"],
                    "reply_to_proposal_id": request.get("reply_to_proposal_id"),
                }
            )
            prepared = raw_turn
            if turn["input_mode"] == "approved_version_reply":
                prepared = UserTurn.model_validate(
                    {
                        **raw_turn.model_dump(mode="json"),
                        "reported_facts": [{"name": "streamlit_version", "value": "1.50.0"}],
                    }
                )
                assert view["intake"]["preparation"] == "canonical_version_reply"
            assert view["intake"]["ingress_hash"] == ingress_hash
            assert view["intake"]["prepared_hash"] == _digest(prepared.model_dump(mode="json"))

            if previous_proposal:
                before = client.get(f"/cases/{case_id}").json()
                rejected = client.post(
                    f"/cases/{case_id}/decision",
                    json={
                        "proposal_id": previous_proposal["proposal_id"],
                        "case_revision": previous_proposal["case_revision"],
                        "decision": "approve",
                    },
                )
                assert rejected.status_code == 409
                assert_no_mutation(client, before)
                checks.append(
                    {
                        "at_turn": turn["id"],
                        "probe": "previous_proposal_approval",
                        "status_code": 409,
                    }
                )

            before = client.get(f"/cases/{case_id}").json()
            replayed = client.post(f"/cases/{case_id}/messages", json=request)
            assert replayed.status_code == 200 and replayed.json()["intake"]["replayed"]
            assert replayed.json()["intake"]["committed_revision"] == view["case_revision"]
            assert len(scripted) == len(reasoners) == len(retrievers) == view["case_revision"]
            assert_no_mutation(client, before)
            changed = {**request, "message": request["message"] + " Changed event content."}
            conflict = client.post(f"/cases/{case_id}/messages", json=changed)
            assert conflict.status_code == 409 and conflict.json()["detail"] == "EventConflict"
            assert_no_mutation(client, before)
            checks.append(
                {
                    "at_turn": turn["id"],
                    "probe": "identical_replay_and_changed_event_conflict",
                    "replay_status": 200,
                    "conflict_status": 409,
                    "extra_port_calls": 0,
                }
            )

            if turn["id"] == "intake-1":
                assert [entry["role"] for entry in view["log"]] == ["user"]
                premature = copy.deepcopy(fixture["turns"][1]["wire_request_template"])
                premature["reply_to_proposal_id"] = proposal["proposal_id"]
                rejected = client.post(f"/cases/{case_id}/messages", json=premature)
                assert (
                    rejected.status_code == 409
                    and rejected.json()["detail"] == "PendingReplyMissing"
                )
                assert_no_mutation(client, before)
                checks.append(
                    {
                        "at_turn": turn["id"],
                        "probe": "reply_before_question_approval",
                        "status_code": 409,
                    }
                )

            if turn["id"] == "intake-3":
                stale = {**request, "turn_id": "stale-correction", "expected_revision": 0}
                rejected = client.post(f"/cases/{case_id}/messages", json=stale)
                assert rejected.status_code == 409 and rejected.json()["detail"] == "StaleRevision"
                assert_no_mutation(client, before)
                checks.append(
                    {"at_turn": turn["id"], "probe": "stale_new_user_event", "status_code": 409}
                )

            if turn["human_review_fixture"]["approve"]:
                decision = {
                    "proposal_id": proposal["proposal_id"],
                    "case_revision": proposal["case_revision"],
                    "decision": "approve",
                }
                approved = client.post(f"/cases/{case_id}/decision", json=decision)
                assert approved.status_code == 200
                after_approval = approved.json()
                assert after_approval["pending"] is None
                assert (
                    sum(entry["role"] == "assistant" for entry in after_approval["log"])
                    == assistants_before + 1
                )
                assert after_approval["log"][-1]["text"] == proposal["user_draft"]
                if proposal["decision"] == "ask":
                    approved_question_id = proposal["proposal_id"]
                    assert after_approval["awaiting_reply"]["proposal_id"] == approved_question_id
                again = client.post(f"/cases/{case_id}/decision", json=decision)
                assert again.status_code == 409
                assert_no_mutation(client, after_approval)
                checks.append(
                    {
                        "at_turn": turn["id"],
                        "probe": "approved_once_repeated_approval_rejected",
                        "status_code": 409,
                    }
                )
            after = client.get(f"/cases/{case_id}").json()
            observations.append(
                {
                    "turn_id": turn["id"],
                    "expected_inventory_sha256": _digest(turn["inventory"]),
                    "seed_precondition": seed_receipt,
                    "wire_request": request,
                    "intake_receipt": view["intake"],
                    "hash_verification": {
                        "original_ingress_verified": True,
                        "prepared_turn_verified": True,
                    },
                    "reasoner_input_case": reasoning_case.model_dump(mode="json"),
                    "reasoner_context": context.model_dump(mode="json"),
                    "received_evidence_chunk_ids": [hit.chunk_id for hit in evidence.hits],
                    "retrieval_request": retrieval.model_dump(mode="json"),
                    "retrieval_authoritative_revision": retrieval_revisions[-1],
                    "proposal": proposal,
                    "state_after_review": after,
                }
            )
            previous_proposal = proposal
        final_view = client.get(f"/cases/{case_id}").json()
        assert final_view["status"] == "escalated" and final_view["case_revision"] == 7
        assert len(final_view["decisions"]) == 3
        assert [entry["decision"] for entry in final_view["decisions"]] == ["approve"] * 3
        assert len(scripted) == len(reasoners) == len(retrievers) == 7
        receipt = {
            "receipt_version": 1,
            "executed_code_sha256": code_at_start,
            "code_sha256": _digest(code_at_start),
            "runtime": {
                "python": sys.version.split()[0],
                "packages": {
                    name: metadata_version(name)
                    for name in ("fastapi", "starlette", "pydantic", "httpx")
                },
            },
            "fixture_id": fixture["fixture_id"],
            "fixture_registration_commit": REGISTRATION_COMMIT,
            "fixture_sha256": FIXTURE_SHA256,
            "source_fixture_sha256": fixture["provenance"]["source_fixture_sha256"],
            "identity_strategy": {
                "proposal_ids": "Semantic labels in exported views; exact offline UUIDs are deterministically UUIDv5(NAMESPACE_URL, fixture_id + ':' + turn_id + ':proposal').",
                "ingress_hash": "Actual validated ingress hash, including its deterministic offline proposal binding. No production UUID generator is changed outside the isolated replay.",
            },
            "result": "passed_registered_software_assertions",
            "turns": observations,
            "ingress_and_review_probes": checks,
            "final_view": final_view,
            "summary": {
                "accepted_primary_turns": 7,
                "reasoner_calls": 7,
                "retrieval_calls": 7,
                "fixture_seed_checkpoints": 3,
                "whole_registered_source_quotes_checked": 2,
                "approved_releases": 3,
                "paid_requests": 0,
                "API_cost_USD": "0",
                "real_model_calls": 0,
                "real_RAG_queries": 0,
            },
            "reporting_boundary": fixture["reporting_boundary"],
            "unmeasured": "Real model decisions, retrieval quality, durable tracker/restart behavior, a verified app fix and final held-out test quality.",
        }
    if code_manifest() != code_at_start:
        raise RuntimeError("CodeChangedDuringReplay")
    receipt = _normalise(receipt, proposal_names)
    receipt["receipt_sha256"] = _digest(receipt)
    return receipt


def write_receipt(path: Path, receipt: dict[str, Any]) -> None:
    """Keep an existing audit receipt intact; reruns need a new explicit destination."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, help="New receipt path; existing files are never replaced."
    )
    args = parser.parse_args()
    try:
        receipt = replay_pilot()
        if args.output:
            write_receipt(args.output, receipt)
    except RuntimeError as error:
        code = str(error)
        if code not in {"AssertionChecksDisabled", "CodeChangedDuringReplay"}:
            code = "PilotUnavailable"
        print(json.dumps({"error_code": code}))
        return 2
    except FileExistsError:
        print(json.dumps({"error_code": "OutputExists"}))
        return 2
    except AssertionError:
        print(json.dumps({"error_code": "PilotExpectationMismatch"}))
        return 2
    except Exception:
        print(json.dumps({"error_code": "PilotUnavailable"}))
        return 2
    print(
        json.dumps(
            {
                "result": receipt["result"],
                "summary": receipt["summary"],
                "receipt_sha256": receipt["receipt_sha256"],
                "output": str(args.output) if args.output else None,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
