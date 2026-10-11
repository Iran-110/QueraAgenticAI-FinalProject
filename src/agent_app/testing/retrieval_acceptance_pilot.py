"""Exercise an interchangeable retrieval adapter through core and local SQLite.

This reuses the registered, answer-informed dev pilot's visible turns and
scripted decisions. Only source records and backend round IDs reach the adapter
factory. No index, model quality, held-out evaluation, HTTP or API is exercised.
"""

import hashlib
import json
from pathlib import Path

from agent_app.contracts import AnalysisResult, EvidenceBundle, ProposalHandoff, UserTurn
from agent_app.orchestration.handoff import validate_handoff
from agent_app.orchestration.service import CoreAdapters, CoreTurnService
from agent_app.reasoning.grounding import source_content_sha256, source_scope
from agent_app.testing.fakes import FakeReasoner
from agent_app.testing.retrieval_acceptance import (
    AdapterFactory,
    CapturedRetriever,
    build_probe,
)
from agent_app.tracker.sqlite_tracker import SQLiteCaseTracker, TrackerRejected

ROOT = Path(__file__).resolve().parents[3]
REVIEWER = "retrieval-pilot-maintainer"
TOKEN = "offline-retrieval-pilot-fixture-token"


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def run_pilot(factory: AdapterFactory, fixture: dict, database: Path) -> dict:
    """Test the same supplied factory on the registered four-turn dev case.

    ``database`` must be a fresh temporary path. Failures export one fixed code;
    the returned successful receipt records counts and content fingerprints,
    rather than raw adapter diagnostics or its query logging.
    """
    checks: dict[str, bool] = {}

    def check(name: str, condition: bool) -> None:
        checks[name] = bool(condition)
        if not condition:
            raise RuntimeError("RetrievalPilotRejected")

    check("fresh_database", not database.exists())
    reference = fixture["pilot_reference"]
    pilot_path = ROOT / reference["path"]
    pilot_bytes = pilot_path.read_bytes()
    check("registered_pilot_hash", hashlib.sha256(pilot_bytes).hexdigest() == reference["sha256"])
    pilot = json.loads(pilot_bytes)
    evidence_reference = {key: pilot["evidence_source"][key] for key in ("path", "sha256")}
    check(
        "registered_evidence_reference",
        evidence_reference in fixture["provenance"]["source_refs"],
    )
    source_bytes = (ROOT / evidence_reference["path"]).read_bytes()
    check(
        "registered_evidence_hash",
        hashlib.sha256(source_bytes).hexdigest() == evidence_reference["sha256"],
    )
    check(
        "exposed_dev_only",
        pilot["case"]["split"] == "dev" and pilot["case"]["test_eligible"] is False,
    )
    bundles = {
        name: EvidenceBundle.model_validate(payload)
        for name, payload in json.loads(source_bytes)["evidence_bundles"].items()
    }
    # Do not copy gold, expect or probes into runtime ports or factory inputs.
    steps = [
        {
            key: step[key]
            for key in ("id", "visible", "evidence_bundle", "agent_script", "maintainer")
        }
        for step in pilot["turns"]
    ]
    check("registered_four_turns", len(steps) == 4)
    case_id = pilot["case"]["case_id"]

    def reopen() -> SQLiteCaseTracker:
        return SQLiteCaseTracker(database, reviewer_tokens={REVIEWER: TOKEN})

    tracker = reopen()
    records = []
    envelopes = []
    ports = []
    factory_calls = []
    adapter_constructions = []
    previous = None
    approved_question = None

    def review(handoff, decision, review_id, **kwargs):
        return tracker.review(
            case_id,
            review_id=review_id,
            proposal_id=handoff.proposal_id,
            expected_revision=handoff.case.case_revision,
            expected_handoff_sha256=handoff.handoff_sha256,
            decision=decision,
            reviewer_id=REVIEWER,
            reviewer_token=TOKEN,
            **kwargs,
        )

    def reject_obsolete(handoff, review_id, code, name):
        before = tracker.read_case(case_id)
        comments = tracker.comments(case_id)
        try:
            review(handoff, "approve", review_id)
        except TrackerRejected as error:
            check(name, error.code == code)
        else:
            check(name, False)
        check(
            f"{name}_no_mutation",
            tracker.read_case(case_id) == before and tracker.comments(case_id) == comments,
        )

    for index, step in enumerate(steps):
        visible = dict(step["visible"])
        bound_reply = visible.pop("reply_to_approved_question", False)
        incoming = UserTurn(
            case_id=case_id,
            expected_revision=tracker.read_case(case_id)["state"]["case_revision"],
            turn_id=step["id"],
            source_ref=f"user:{step['id']}",
            **visible,
        )
        binding = {"reply_to_proposal_id": approved_question} if bound_reply else {}
        envelopes.append((incoming, binding))
        final_bundle = bundles[step["evidence_bundle"]]
        round_ids = (tuple(hit.chunk_id for hit in final_bundle.hits),)
        responses = [AnalysisResult.model_validate(step["agent_script"])]
        refinement_queries = ()
        if index == 2:
            round_ids = (tuple(hit.chunk_id for hit in previous.evidence.hits), *round_ids)
            refinement_queries = (
                "Streamlit 1.49.1 multiselect fragment default after parent reset",
                "Streamlit 1.49.1 multiselect key identity documentation coverage",
            )
            responses.insert(
                0,
                AnalysisResult(
                    decision="retrieve_more",
                    user_draft="",
                    maintainer_summary="",
                    rationale="Retrieve fixed official excerpts for the corrected user version.",
                    retrieval_queries=refinement_queries,
                ),
            )
        probe = build_probe(fixture, round_ids=round_ids)
        selected_ports = {}

        def adapters(
            case,
            message,
            run_id,
            probe=probe,
            responses=responses,
            turn_id=step["id"],
            selected_ports=selected_ports,
        ):
            factory_calls.append(run_id)

            def construct(selected_probe):
                adapter_constructions.append(turn_id)
                return factory(selected_probe)

            captured = CapturedRetriever(construct, probe)
            reasoner = FakeReasoner(responses)
            selected_ports.update(captured=captured, reasoner=reasoner)
            ports.append((captured, reasoner))
            return CoreAdapters(captured, reasoner, probe.snapshot_id)

        service = CoreTurnService(tracker, adapters, top_k=5)
        comments_before = tracker.comments(case_id)
        outcome = service.submit(incoming, **binding)
        check(f"{index}:proposal_staged", outcome.status == "proposal_staged")
        captured, reasoner = selected_ports["captured"], selected_ports["reasoner"]
        handoff = outcome.handoff
        check(f"{index}:proposal_is_only_a_preview", tracker.comments(case_id) == comments_before)
        check(
            f"{index}:exact_pending_after_adapter",
            service.recover_exact_pending(handoff) == handoff,
        )
        check(
            f"{index}:registered_source_content_preserved",
            handoff.evidence.snapshot_id == final_bundle.snapshot_id
            and {hit.chunk_id: hit for hit in handoff.evidence.hits}
            == {hit.chunk_id: hit for hit in final_bundle.hits},
        )
        latest = captured.outputs[-1].model_copy(update={"retrieval_round": len(captured.requests)})
        check(
            f"{index}:handoff_uses_actual_latest_output",
            handoff.evidence == latest and validate_handoff(handoff) == handoff,
        )
        check(
            f"{index}:source_inventory_matches_actual_output",
            [
                (entry.chunk_id, entry.content_sha256, entry.version_scope)
                for entry in handoff.source_inventory
            ]
            == [
                (hit.chunk_id, source_content_sha256(hit), source_scope(handoff.case, hit))
                for hit in latest.hits
            ],
        )
        if bound_reply:
            check(
                "bound_short_reply_keeps_problem_and_user_version",
                outcome.receipt.preparation == "canonical_version_reply"
                and steps[0]["visible"]["message"] in reasoner.inputs[0][1]
                and "multiselect" in captured.requests[0].queries[0]
                and "streamlit_version=1.50.0" in captured.requests[0].queries[0]
                and tracker.read_case(case_id)["history"][-1]["text"] == incoming.message,
            )
        if index == 2:
            check(
                "correction_updates_authoritative_user_version",
                [
                    (fact.value, fact.status)
                    for fact in handoff.case.facts
                    if fact.name == "streamlit_version"
                ]
                == [("1.50.0", "superseded"), ("1.49.1", "active")],
            )
            calls = captured.probe.backend.calls
            check(
                "refinement_consumes_two_queries_within_budget",
                outcome.run_result.model_attempts == outcome.run_result.retrieval_rounds == 2
                and len(captured.requests) == len(captured.outputs) == 2
                and captured.requests[-1].queries == refinement_queries
                and set(captured.outputs[-1].queries_used) == set(refinement_queries)
                and {call["query"] for call in calls[-2:]} == set(refinement_queries)
                and calls[-1]["round"] == calls[-2]["round"],
            )
            removed = {hit.chunk_id for hit in previous.evidence.hits} - {
                hit.chunk_id for hit in latest.hits
            }
            check(
                "old_release_evidence_absent_from_current_handoff",
                bool(removed)
                and not removed & {entry.chunk_id for entry in handoff.source_inventory}
                and not removed & {link.chunk_id for link in handoff.analysis.evidence_links},
            )
            reject_obsolete(
                previous,
                "retrieval-stale-version",
                "StaleRevision",
                "stale_version_approval_rejected",
            )

        action = step["maintainer"]["decision"]
        released = None
        if action == "approve":
            review_receipt = review(handoff, "approve", f"{step['id']}:approve")
            check("version_question_approved", review_receipt["status"] == "awaiting_user")
            approved_question = handoff.proposal_id
            released = handoff
        elif action == "edit":
            review(
                handoff,
                "edit",
                f"{step['id']}:edit",
                edited_draft=step["maintainer"]["edited_draft"],
            )
            edited = validate_handoff(
                ProposalHandoff.model_validate(tracker.read_case(case_id)["pending_handoff"])
            )
            check(
                "edit_preserves_current_adapter_evidence",
                edited.evidence == latest
                and edited.proposal_id != handoff.proposal_id
                and tracker.comments(case_id) == comments_before,
            )
            tracker = reopen()
            reject_obsolete(
                handoff,
                "retrieval-pre-edit",
                "PendingProposalMismatch",
                "pre_edit_approval_rejected",
            )
            review_receipt = review(edited, "approve", f"{step['id']}:approve-edited")
            tracker = reopen()
            retry = review(edited, "approve", f"{step['id']}:approve-edited")
            check(
                "review_retry_after_restart_one_action",
                retry["replayed"]
                and retry["action_id"] == review_receipt["action_id"]
                and len(tracker.comments(case_id)) == len(comments_before) + 1,
            )
            released = edited
        elif action == "reject":
            review_receipt = review(handoff, "reject", f"{step['id']}:reject")
            check(
                "withdrawal_rejection_no_action",
                review_receipt["action_id"] is None
                and tracker.comments(case_id) == comments_before,
            )
        else:
            check("registered_pending_answer", action == "none")
        records.append(
            {
                "turn_id": incoming.turn_id,
                "revision": handoff.case.case_revision,
                "preparation": outcome.receipt.preparation,
                "decision": handoff.analysis.decision,
                "handoff_sha256": handoff.handoff_sha256,
                "released_handoff_sha256": released.handoff_sha256 if released else None,
                "evidence_fingerprint": _hash(handoff.evidence.model_dump(mode="json")),
                "final_chunk_ids": [hit.chunk_id for hit in handoff.evidence.hits],
                "source_inventory": [
                    entry.model_dump(mode="json") for entry in handoff.source_inventory
                ],
                "retrieval_requests_fingerprint": _hash(
                    [request.model_dump(mode="json") for request in captured.requests]
                ),
                "query_counts": [len(request.queries) for request in captured.requests],
                "backend_query_count": len(captured.probe.backend.calls),
                "model_attempts": outcome.run_result.model_attempts,
                "retrieval_rounds": outcome.run_result.retrieval_rounds,
            }
        )
        previous = handoff
        tracker = reopen()

    before_replay = tracker.read_case(case_id)
    port_counts = [
        (
            len(captured.requests),
            len(captured.outputs),
            len(captured.probe.backend.calls),
            len(reasoner.inputs),
        )
        for captured, reasoner in ports
    ]
    calls_before = len(factory_calls)
    constructions_before = len(adapter_constructions)

    def forbidden_adapters(*args):
        raise AssertionError("ReplayMustNotConstructPorts")

    replay = CoreTurnService(tracker, forbidden_adapters).submit(envelopes[2][0], **envelopes[2][1])
    check(
        "old_event_replay_no_new_ports_or_actions",
        replay.status == "replay_only"
        and replay.receipt.replayed
        and replay.receipt.committed_revision == 3
        and replay.handoff is replay.run_result is None
        and tracker.read_case(case_id) == before_replay
        and len(factory_calls) == calls_before
        and len(adapter_constructions) == constructions_before
        and [
            (
                len(captured.requests),
                len(captured.outputs),
                len(captured.probe.backend.calls),
                len(reasoner.inputs),
            )
            for captured, reasoner in ports
        ]
        == port_counts,
    )
    check(
        "withdrawn_version_not_active",
        not any(
            fact["name"] == "streamlit_version" and fact["status"] == "active"
            for fact in before_replay["state"]["facts"]
        ),
    )
    check("four_distinct_core_runs", len(factory_calls) == len(set(factory_calls)) == 4)
    check("same_adapter_factory_once_per_turn", len(adapter_constructions) == 4)
    check("only_two_approved_local_actions", len(tracker.comments(case_id)) == 2)
    return {
        "mode": "interchangeable_adapter_fixed_backend_core_sqlite_pilot",
        "registered_dev_fixture_id": pilot["fixture_id"],
        "registered_dev_fixture_sha256": reference["sha256"],
        "registered_evidence_sha256": evidence_reference["sha256"],
        "exposure": pilot["case"]["exposure"],
        "checks": checks,
        "turns": records,
        "total_retrieval_calls": sum(len(captured.requests) for captured, _reasoner in ports),
        "adapter_constructions": len(adapter_constructions),
        "total_scripted_reasoner_calls": sum(len(reasoner.inputs) for _captured, reasoner in ports),
        "local_action_count": len(tracker.comments(case_id)),
        "final_revision": before_replay["state"]["case_revision"],
        "quality_claim": False,
        "real_retrieval_quality_claim": False,
        "model_quality_claim": False,
        "held_out_test": False,
        "api_ui_connected": False,
        "real_model_calls": 0,
        "api_cost_usd": "0",
    }
