"""Replay registered authored controls without a model, corpus, or tracker store.

This is a software-boundary comparison. Developer-authored semantic labels are
never passed to the reasoner and never inferred from proposal wording.
"""

import argparse
import copy
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_app.contracts import (
    AnalysisResult,
    CaseState,
    EvidenceBundle,
    ReasoningContext,
    RetrievalRequest,
    RunLimits,
    UserTurn,
)
from agent_app.orchestration.engine import SupportEngine
from agent_app.orchestration.intake import IntakeRejected, prepare_version_reply
from agent_app.orchestration.turns import UserTurnRejected, propose_user_turn

_ROOT = Path(__file__).resolve().parents[3]
_FIXTURES = _ROOT / "experiments" / "decision_quality"
_SUITE_SHA256 = "00bd1765a3296b039e56097296b1bd792aa4ccb736dac4bd54af28d6521226a3"
_PROTOCOL_SHA256 = "4b101229a810ae5e2d38edb9e534ebe65fa43e534f71660e358fb26fd0edc139"
REGISTRATION_COMMIT = "8814fbb"


def _encoded(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _hash(value: Any) -> str:
    return hashlib.sha256(_encoded(value)).hexdigest()


@dataclass(frozen=True)
class ControlledPack:
    suite: dict[str, Any]
    protocol: dict[str, Any]


def load_controlled_pack(
    suite_path: Path | None = None, protocol_path: Path | None = None
) -> ControlledPack:
    """Read only the exact registered fixtures, including when copied for tests."""
    suite_path = suite_path or _FIXTURES / "cases-controlled-v8.json"
    protocol_path = protocol_path or _FIXTURES / "protocol-controlled-v8.json"
    suite_bytes = suite_path.read_bytes()
    protocol_bytes = protocol_path.read_bytes()
    if (
        hashlib.sha256(suite_bytes).hexdigest() != _SUITE_SHA256
        or hashlib.sha256(protocol_bytes).hexdigest() != _PROTOCOL_SHA256
    ):
        raise ValueError("Registered controlled fixture hash mismatch.")
    pack = ControlledPack(json.loads(suite_bytes), json.loads(protocol_bytes))
    validate_controlled_pack(pack)
    return pack


def validate_controlled_pack(pack: ControlledPack) -> dict[str, Any]:
    """Validate shapes and registration only; no engine or turn execution."""
    suite, protocol = pack.suite, pack.protocol
    if _hash(suite) != _SUITE_SHA256 or _hash(protocol) != _PROTOCOL_SHA256:
        raise ValueError("Registered controlled fixture content changed.")
    if (
        protocol["suite_sha256"] != _SUITE_SHA256
        or suite["docs_commit"] != protocol["docs_commit"]
        or suite["reserved_issue_ids"] != [8061, 8901, 12629, 12782, 16914]
        or not suite["execution_boundary"]["offline_only"]
        or not suite["execution_boundary"]["authored_proposals_not_model_outputs"]
        or protocol["paid_calls_authorized"]
        or protocol["model"] is not None
    ):
        raise ValueError("Invalid controlled registration boundary.")
    RunLimits.model_validate(protocol["limits"])
    seen_cases: set[str] = set()
    seen_replays: set[str] = set()
    sources: dict[str, dict[str, Any]] = {}
    for case in suite["cases"]:
        if case["id"] in seen_cases or case["origin_issue_id"] != 12782:
            raise ValueError("Invalid controlled development family.")
        seen_cases.add(case["id"])
        CaseState.model_validate(case["case_state"])
        inventory = case["inventory"]
        if not all(
            inventory[name]
            for name in (
                "visible_known_information",
                "user_clarifiable_gaps",
                "documentation_or_evidence_gaps",
                "acceptable_initial_decisions",
                "acceptable_final_decisions",
                "targeted_answerable_questions",
                "claim_support_checklist",
            )
        ):
            raise ValueError("Missing controlled scenario inventory.")
        for bundle in case["bundles"]:
            evidence = EvidenceBundle.model_validate(bundle)
            if (
                evidence.snapshot_id != suite["snapshot_id"]
                or len(evidence.hits) > protocol["top_k"]
            ):
                raise ValueError("Invalid controlled source pool.")
            for hit in bundle["hits"]:
                previous = sources.setdefault(hit["chunk_id"], hit)
                if previous != hit or not hit["source_span"]:
                    raise ValueError("Controlled source copy changed.")
                if hit["source_id"] not in suite["provenance"]["synthetic_source_ids"]:
                    if hit["source_commit"] != suite["docs_commit"]:
                        raise ValueError("Unpinned controlled official source.")
        for replay in case["authored_replays"]:
            if replay["id"] in seen_replays or not 1 <= len(replay["sequence"]) <= 2:
                raise ValueError("Invalid controlled replay sequence.")
            seen_replays.add(replay["id"])
            for proposal in replay["sequence"]:
                AnalysisResult.model_validate(proposal)
        if "transition_input" in case:
            transition = case["transition_input"]
            CaseState.model_validate(transition["prior_case_state"])
            UserTurn.model_validate(transition["user_turn"])
            CaseState.model_validate(transition["expected_candidate_case_state"])
    # Reused original generated records remain exact copies, not retuned evidence.
    original = json.loads((_FIXTURES / "cases-normalized-v3.json").read_text())
    anchor = next(c for c in original["cases"] if c["id"] == "real-fragment-default-partial-repro")
    for hit in anchor["bundles"][0]["hits"]:
        if sources[hit["chunk_id"]] != hit:
            raise ValueError("Original official source record changed.")
    intake_ids: set[str] = set()
    for probe in suite["intake_probes"]:
        if probe["id"] in intake_ids:
            raise ValueError("Duplicate controlled intake probe.")
        intake_ids.add(probe["id"])
        CaseState.model_validate(probe["case_state"])
        AnalysisResult.model_validate(probe["stored_question"])
        UserTurn.model_validate(probe["user_turn"])
    if (
        len(seen_cases) != protocol["scenario_count"]
        or len(seen_replays) != protocol["engine_replay_count_per_scope"]
        or len(intake_ids) != protocol["intake_probe_count"]
    ):
        raise ValueError("Controlled registration count mismatch.")
    return {
        "registration_commit": REGISTRATION_COMMIT,
        "suite_sha256": _SUITE_SHA256,
        "cases": len(seen_cases),
        "replays_per_scope": len(seen_replays),
        "intake_probes": len(intake_ids),
        "unique_source_records": len(sources),
        "scenario_execution": False,
        "real_api_calls": 0,
    }


class _FixedRetriever:
    def __init__(self, bundles: list[dict[str, Any]]) -> None:
        self.bundles = bundles
        self.requests: list[RetrievalRequest] = []

    def search(self, request: RetrievalRequest) -> EvidenceBundle:
        index = len(self.requests)
        self.requests.append(request.model_copy(deep=True))
        return EvidenceBundle.model_validate(copy.deepcopy(self.bundles[index]))


class _AuthoredReasoner:
    def __init__(self, sequence: list[dict[str, Any]]) -> None:
        self.sequence = sequence
        self.received_chunk_ids: list[list[str]] = []

    def analyze(
        self,
        case: CaseState,
        user_message: str,
        evidence: EvidenceBundle,
        *,
        context: ReasoningContext,
    ) -> str:
        index = len(self.received_chunk_ids)
        self.received_chunk_ids.append([hit.chunk_id for hit in evidence.hits])
        # No inventory, labels, reviewer aid, expected results or intake probe is
        # sent through the port. The authored sequence does not adapt its output.
        return json.dumps(self.sequence[index], ensure_ascii=False)


def _matches(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    return all(actual.get(key) == value for key, value in expected.items())


def _replay_engine(case: dict[str, Any], replay: dict[str, Any], scope: str, pack: ControlledPack):
    state = CaseState.model_validate(case["case_state"])
    retriever = _FixedRetriever(case["bundles"])
    reasoner = _AuthoredReasoner(replay["sequence"])
    result = SupportEngine(
        retriever,
        reasoner,
        snapshot_id=pack.suite["snapshot_id"],
        limits=RunLimits.model_validate(pack.protocol["limits"]),
        top_k=pack.protocol["top_k"],
        current_revision=lambda _: state.case_revision,
        evidence_scope=scope,
    ).run(state, case["user_message"], run_id=f"v8-{scope}-{replay['id']}")
    actual = {
        "status": result.status,
        "final_decision": result.analysis.decision if result.analysis else None,
        "error_code": result.error_code,
        "model_attempts": result.model_attempts,
        "retrieval_rounds": result.retrieval_rounds,
    }
    return {
        **actual,
        "expected_matched": _matches(actual, replay["expected_by_scope"][scope]),
        "received_chunk_ids": reasoner.received_chunk_ids,
        "trace": [event.model_dump(mode="json") for event in result.trace],
        "steps": result.steps,
    }


def _active_version(state: CaseState) -> str | None:
    return next(
        (
            fact.value
            for fact in state.facts
            if fact.name == "streamlit_version"
            and fact.status == "active"
            and fact.provenance_kind == "user"
        ),
        None,
    )


def _replay_intake(probe: dict[str, Any], prepare: bool) -> dict[str, Any]:
    state = CaseState.model_validate(probe["case_state"])
    turn = UserTurn.model_validate(probe["user_turn"])
    expected = probe["expected"]["prepare_version_reply" if prepare else "bare_turn"]
    try:
        prepared = (
            prepare_version_reply(
                state,
                turn,
                proposal_id=probe["proposal_id"],
                question=AnalysisResult.model_validate(probe["stored_question"]),
            )
            if prepare
            else turn
        )
        transition = propose_user_turn(state, prepared)
    except (IntakeRejected, UserTurnRejected) as error:
        matches = (
            not expected["conversion_allowed"]
            and error.code == expected.get("expected_rejection_code", error.code)
            if prepare
            else not expected["transition_allowed"]
        )
        return {
            "converted": False,
            "transition_allowed": False,
            "error_code": error.code,
            "active_version": _active_version(state),
            "expected_matched": matches,
        }
    candidate = transition.candidate
    converted = prepared.reported_facts != turn.reported_facts
    actual = {
        "converted": converted,
        "transition_allowed": True,
        "error_code": None,
        "active_version": _active_version(candidate),
        "case_revision": candidate.case_revision,
        "pending_proposal_id": candidate.pending_proposal_id,
        "evidence_refs": list(candidate.evidence_refs),
        "event_hash": transition.event_hash,
    }
    if prepare:
        new_fact = next(
            (
                fact
                for fact in candidate.facts
                if fact.name == "streamlit_version"
                and fact.status == "active"
                and fact.provenance_kind == "user"
            ),
            None,
        )
        actual["user_attribution_preserved"] = (
            new_fact is not None
            and new_fact.provenance_kind == expected["new_fact_provenance"]
            and new_fact.source_ref == turn.source_ref
            and new_fact.turn_id == turn.turn_id
        )
        matches = (
            converted == expected["conversion_allowed"]
            and actual["active_version"] == expected["active_version_after_transition"]
            and actual["case_revision"] == expected["next_revision"]
            and actual["pending_proposal_id"] == expected["pending_proposal_id_after_transition"]
            and actual["evidence_refs"] == expected["evidence_refs_after_conversion"]
            and actual["user_attribution_preserved"]
        )
    else:
        matches = (
            not converted
            and actual["active_version"] == expected["active_version"]
            and actual["pending_proposal_id"] is None
            and candidate.case_revision == state.case_revision + 1
        )
    return {**actual, "expected_matched": matches}


def replay_controlled_pack(pack: ControlledPack) -> dict[str, Any]:
    validation = validate_controlled_pack(pack)
    observations = []
    transitions = []
    for case in pack.suite["cases"]:
        for replay in case["authored_replays"]:
            observations.append(
                {
                    "scenario_id": case["id"],
                    "replay_id": replay["id"],
                    "control": replay["control"],
                    "authored_semantic_label": replay["semantic_expectation"]["label"],
                    "registered_positive_final_decision": replay["expected_by_scope"]["all"][
                        "final_decision"
                    ],
                    **{
                        scope: _replay_engine(case, replay, scope, pack)
                        for scope in ("all", "exact_user_version")
                    },
                }
            )
        if "transition_input" in case:
            given = case["transition_input"]
            transition = propose_user_turn(
                CaseState.model_validate(given["prior_case_state"]),
                UserTurn.model_validate(given["user_turn"]),
            )
            matches = (
                transition.candidate.model_dump(mode="json")
                == given["expected_candidate_case_state"]
                and list(transition.invalidated_checks) == given["expected_invalidated_checks"]
                and list(transition.changed_fact_names) == given["expected_changed_fact_names"]
                and transition.context_changed == given["expected_context_changed"]
            )
            transitions.append(
                {
                    "scenario_id": case["id"],
                    "expected_matched": matches,
                    "case_revision": transition.candidate.case_revision,
                    "pending_proposal_id": transition.candidate.pending_proposal_id,
                    "evidence_refs": list(transition.candidate.evidence_refs),
                    "changed_fact_names": list(transition.changed_fact_names),
                    "invalidated_check_count": len(transition.invalidated_checks),
                    "event_hash": transition.event_hash,
                }
            )
    intake = [
        {
            "probe_id": probe["id"],
            "control": probe["control"],
            "bare_turn": _replay_intake(probe, False),
            "prepare_version_reply": _replay_intake(probe, True),
        }
        for probe in pack.suite["intake_probes"]
    ]
    summary = {}
    for scope in ("all", "exact_user_version"):
        positives = [r for r in observations if r["control"] == "positive"]
        negatives = [r for r in observations if r["control"] == "negative"]
        summary[scope] = {
            "unsafe_accepted": sum(r[scope]["status"] == "awaiting_approval" for r in negatives),
            "negative_controls": len(negatives),
            "positive_retained": sum(
                r[scope]["status"] == "awaiting_approval"
                and r[scope]["final_decision"] == r["registered_positive_final_decision"]
                for r in positives
            ),
            "positive_controls": len(positives),
            "registered_outcomes_matched": sum(r[scope]["expected_matched"] for r in observations),
            "replays": len(observations),
        }
    failures = [
        f"engine/{r['replay_id']}/{scope}"
        for r in observations
        for scope in ("all", "exact_user_version")
        if not r[scope]["expected_matched"]
    ]
    failures += [
        f"intake/{r['probe_id']}/{condition}"
        for r in intake
        for condition in ("bare_turn", "prepare_version_reply")
        if not r[condition]["expected_matched"]
    ]
    failures += [f"transition/{r['scenario_id']}" for r in transitions if not r["expected_matched"]]
    return {
        **validation,
        "scenario_execution": True,
        "authored_proposals_not_model_outputs": True,
        "authorship": "Proposals and labels authored by Codex during implementation; another "
        "assistant independently audited sources before replay. These are not paid Metis "
        "reasoner outputs or human gold labels.",
        "semantic_quality_measured": False,
        "RAG_quality_measured": False,
        "tracker_actions_executed": 0,
        "summary": summary,
        "intake_conversions": {
            condition: sum(r[condition]["converted"] for r in intake)
            for condition in ("bare_turn", "prepare_version_reply")
        },
        "intake_conditions_matched": sum(
            r[condition]["expected_matched"]
            for r in intake
            for condition in ("bare_turn", "prepare_version_reply")
        ),
        "transition_conditions_matched": sum(r["expected_matched"] for r in transitions),
        "all_registered_expectations_matched": not failures,
        "failures": failures,
        "observations": observations,
        "intake_observations": intake,
        "transition_observations": transitions,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    pack = load_controlled_pack()
    result = validate_controlled_pack(pack) if args.validate_only else replay_controlled_pack(pack)
    if args.output is not None:
        # Exclusive creation preserves a previously saved report.
        with args.output.open("x", encoding="utf-8") as output:
            output.write(_encoded(result).decode("utf-8"))
    aggregate = {key: value for key, value in result.items() if not key.endswith("observations")}
    print(json.dumps(aggregate, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("all_registered_expectations_matched", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
