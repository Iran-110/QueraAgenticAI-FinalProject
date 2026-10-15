"""Authored offline lexical-freshness controls, never model/RAG quality.

Read tracked neutral fixtures and old exposed default baselines only. No gateway,
tracker, native index or budget client is constructed. Reviewer expectations are
used only after helpers return, never as query inputs or source filters.
"""

import argparse
import hashlib
import json
import re
from dataclasses import asdict
from pathlib import Path

from agent_app.contracts import CaseState, EvidenceBundle, GroundedRequest, TurnConversation
from agent_app.orchestration.conversation import build_reasoning_message
from agent_app.reasoning.claim_plan import build_claim_request
from agent_app.reasoning.evidence_selection import (
    inspect_claim_selection,
    rank_evidence_units,
    suggest_evidence_units,
)
from agent_app.reasoning.grounding import make_grounded_request
from agent_app.reasoning.selection_context import build_evidence_query_context

ROOT = Path(__file__).resolve().parents[3]
PACKET = "experiments/core_selection_context_v1"


def _encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _legacy_digest(observed):
    # Frozen pre-code recipe uses these exact historical keys.
    return _sha(
        _encoded(
            {
                "rank": observed["ranked_units"],
                "suggest": observed["shortlist"],
                "inspect": observed["inspection"],
            }
        )
    )


def _observation(request, *, query_context=None):
    ranked = [asdict(hint) for hint in rank_evidence_units(request, query_context=query_context)]
    shortlist = suggest_evidence_units(request, query_context=query_context)
    plan = {
        "context_sha256": request.context_sha256,
        "decision": "answer" if shortlist.passages else "escalate",
        "passages": shortlist.passages,
        "user_facts": [],
        "question_name": None,
        "retrieval_queries": [],
    }
    # Authored projection of a suggestion for inspection; not model output.
    inspected = inspect_claim_selection(request, plan, query_context=query_context)
    return {"ranked_units": ranked, "shortlist": asdict(shortlist), "inspection": inspected}


def run_replay(root: Path = ROOT):
    folder = root / PACKET
    pins = json.loads((folder / "input-pins-v1.json").read_bytes())
    checks = []

    def check(name, value):
        checks.append({"name": name, "passed": bool(value)})

    frozen = {
        name: sha for name, sha in pins["source_and_inputs"].items() if not name.startswith("src/")
    }
    before = {name: _sha((root / name).read_bytes()) for name in frozen}
    for name, sha in frozen.items():
        if before[name] != sha:
            raise ValueError("FrozenContextInputMismatch")
        check("frozen_input:" + name, True)
    packet = json.loads((folder / "scenarios-v1.json").read_bytes())
    baseline = json.loads((folder / "legacy-baseline-v1.json").read_bytes())
    neutral_baseline = {row["id"]: row for row in baseline["authored_neutral_results"]}
    rows = []
    for scenario in packet["scenarios"]:
        case = CaseState.model_validate(scenario["case"])
        conversation = TurnConversation.model_validate(scenario["conversation"])
        evidence = EvidenceBundle.model_validate(scenario["evidence"])
        message = build_reasoning_message(conversation)
        check("exact_stored_reasoning:" + scenario["id"], message == scenario["reasoning_message"])
        request = build_claim_request(
            make_grounded_request(case, message, evidence), block_mode="sections"
        )
        input_before = _encoded(
            {
                "case": case.model_dump(mode="json"),
                "conversation": conversation.model_dump(mode="json"),
                "request": request.model_dump(mode="json"),
            }
        )
        legacy = _observation(request)
        check(
            "legacy_neutral_byte_parity:" + scenario["id"],
            _legacy_digest(legacy) == neutral_baseline[scenario["id"]]["combined_advisory_sha256"],
        )
        context = build_evidence_query_context(request, case, conversation)
        current = _observation(request, query_context=context)
        check(
            "typed_output_digest_custody:" + scenario["id"],
            current["shortlist"]["query_context_sha256"] == context.context_sha256
            and current["inspection"]["query_context_sha256"] == context.context_sha256,
        )
        check(
            "not_semantic_support:" + scenario["id"],
            current["shortlist"]["semantic_support"] is None
            and current["inspection"]["semantic_support"] is None
            and current["inspection"]["human_review_required"] is True,
        )
        check("bounded_query:" + scenario["id"], len(context.current_query) <= 500)
        # Pre-code authored expectations are inspected AFTER helper output;
        # they NEVER enter its selection/query input.
        expected = scenario["authored_review_expectations"]
        projected_terms = set(context.current_query.casefold().replace("_", " ").split())
        if expected.get("retired_topic_terms"):
            check(
                "known_retired_topic_not_in_projection:" + scenario["id"],
                not set(expected["retired_topic_terms"]) & projected_terms,
            )
        if expected.get("current_topic_terms"):
            check(
                "current_topic_kept:" + scenario["id"],
                all(
                    term in context.current_query.casefold()
                    for term in expected["current_topic_terms"]
                ),
            )
        forbidden = set(expected.get("forbidden_query_only_terms", ()))
        if forbidden:
            poison_only_hints = []
            for hint in current["ranked_units"]:
                source, block = hint["source_index"], hint["block_index"]
                span = request.blocks[source][block]
                text = request.grounded.evidence.hits[source].excerpt[span.start : span.end]
                terms = set(re.findall(r"[^\W_]+", text.casefold()))
                if forbidden <= terms:
                    poison_only_hints.append(hint)
            check(
                "metadata_or_nonUSER_poison_terms_not_matched:" + scenario["id"],
                bool(poison_only_hints) and all(h["matched_terms"] == 0 for h in poison_only_hints),
            )
        # Ranking is observed, not a structural pass requirement. Unretired
        # historical details can still outweigh the corrected topic.
        topical_preference = (
            current["ranked_units"][0]["source_index"] in expected["current_source_indexes"]
            if expected.get("current_source_indexes") and current["ranked_units"]
            else None
        )
        input_after = _encoded(
            {
                "case": case.model_dump(mode="json"),
                "conversation": conversation.model_dump(mode="json"),
                "request": request.model_dump(mode="json"),
            }
        )
        check("full_inputs_unchanged:" + scenario["id"], input_before == input_after)
        rows.append(
            {
                "scenario_id": scenario["id"],
                "kind": scenario["fixture_kind"],
                "full_reasoning_message_sha256": _sha(message.encode()),
                "claim_request_sha256_unchanged": request.context_sha256,
                "bound_context_sha256": context.context_sha256,
                "bounded_current_query": context.current_query,
                "legacy": legacy,
                "typed_advisory": current,
                "authored_current_source_is_top_observation_not_quality": topical_preference,
                "model_proposals_created": 0,
                "human_usefulness": None,
                "reviewer_expectations_only": expected,
            }
        )
    previous = json.loads((root / baseline["prior_snapshot_file"]).read_bytes())["snapshots"]
    prior_baselines = {row["id"]: row for row in baseline["prior_default_results"]}
    for snapshot in previous:
        request = build_claim_request(GroundedRequest.model_validate(snapshot["catalog_request"]))
        observed = _observation(request)
        check(
            "legacy_exposed_snapshot_byte_parity:" + snapshot["id"],
            _legacy_digest(observed) == prior_baselines[snapshot["id"]]["combined_advisory_sha256"],
        )
    check("eight_authored_and16old_default_states", len(rows) == 8 and len(previous) == 16)
    after = {name: _sha((root / name).read_bytes()) for name in frozen}
    check("all_frozen_packet_bytes_unchanged", before == after)
    return {
        "schema_version": 1,
        "task": "C4l/E2y",
        "kind": "authored_offline_lexical_freshness_and_legacy_parity",
        "source_input_pins": before,
        "authored_neutral_rows": rows,
        "legacy_default_states_checked": len(rows) + len(previous),
        "checks": checks,
        "checks_passed": sum(row["passed"] for row in checks),
        "checks_total": len(checks),
        "all_checks_passed": all(row["passed"] for row in checks),
        "actual_API_calls": 0,
        "ledger_or_index_clients_created": 0,
        "model_messages_sources_or_default_ranking_changed": False,
        "new_model_selection_or_semantic_quality_claim": False,
        "human_usefulness": None,
        "held_out_or_RAG_quality": False,
        "remaining_limits": [
            "TurnConversation has no case_id. Caller must load authoritative same-case history; content binding is not authentication.",
            "Latest-message negation still has literal topic words; lexical scoring does not understand intent or prove relevance.",
            "Unstructured historical details not represented by retired facts can still survive bounded topic hints.",
            "Synonyms can have zero overlap. Shortlist absence is not proof of missing or irrelevant evidence.",
            "All fixtures are authored neutral development controls, not model conversations or final evaluation cases.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run_replay()
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(
        json.dumps(
            {
                "checks_passed": report["checks_passed"],
                "checks_total": report["checks_total"],
                "actual_API_calls": 0,
                "semantic_quality_claim": False,
            }
        )
    )
    return 0 if report["all_checks_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
