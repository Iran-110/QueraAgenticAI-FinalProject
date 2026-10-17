"""Re-render a pinned exposed archive; no new model choices or quality scores."""

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import quote

from agent_app.contracts import GroundedRequest, ProposalHandoff
from agent_app.orchestration.handoff import validate_handoff
from agent_app.reasoning.grounding import _display, render_grounded_plan

ARCHIVE = "experiments/dev_rag_coverage_v1/model-live-receipt-v1.json"
ARCHIVE_SHA256 = "409fe34076fa6772e6442b881332874fe8e66d1f09e80a759e2ab8207d71f901"


def run(root: Path) -> dict:
    """Use all recorded fresh proposals, without deduplicating favorable rows."""
    raw = (root / ARCHIVE).read_bytes()
    if hashlib.sha256(raw).hexdigest() != ARCHIVE_SHA256:
        raise ValueError("MaintainerBriefArchiveMismatch")
    archive = json.loads(raw)
    rows = []
    nonfresh_states = []
    for bi, batch in enumerate(archive["batches"]):
        for ji, job in enumerate(batch["jobs"]):
            for si, step in enumerate(job["steps"]):
                proposal = step.get("proposal")
                if not proposal or not proposal.get("review_handoff") or proposal.get("stale"):
                    nonfresh_states.append(
                        {
                            "archive_pointer": f"/batches/{bi}/jobs/{ji}/steps/{si}",
                            "state": (
                                "stale_previous_proposal"
                                if proposal and proposal.get("stale")
                                else "proposal_without_bound_fresh_handoff"
                                if proposal
                                else "no_proposal"
                            ),
                            "compared_as_fresh_model_output": False,
                        }
                    )
                    continue
                handoff = validate_handoff(
                    ProposalHandoff.model_validate(proposal["review_handoff"])
                )
                request = GroundedRequest.model_validate(handoff.grounded_request)
                matching = [
                    attempt
                    for attempt in batch["attempts"]
                    if attempt["context"]["run_id"] == handoff.reasoning_context.run_id
                    and attempt.get("plan") is not None
                    and attempt["request"] == request.model_dump(mode="json")
                ]
                if len(matching) != 1:
                    raise ValueError("MaintainerBriefAttemptBindingMismatch")
                plan = matching[0]["plan"]
                options = {"source_gap_handoff": True, "source_gap_investigation": True}
                legacy = render_grounded_plan(request, plan, **options)
                candidate = render_grounded_plan(request, plan, review_brief=True, **options)
                quoted = {
                    hit.chunk_id: "\n".join(
                        "> " + line for line in _display(hit.excerpt).split("\n")
                    )
                    for hit in request.evidence.hits
                    if hit.chunk_id in {link.chunk_id for link in legacy.evidence_links}
                }
                source_inventory = all(
                    quote(hit.source_url, safe=":/?&=.%#") in candidate.maintainer_summary
                    for hit in request.evidence.hits
                )
                record = {
                    "archive_pointer": f"/batches/{bi}/jobs/{ji}/steps/{si}/proposal",
                    "case_id": request.case.case_id,
                    "case_revision": request.case.case_revision,
                    "decision": legacy.decision,
                    "original_handoff_sha256": handoff.handoff_sha256,
                    "recorded_request_and_plan_bound": True,
                    "legacy_reconstruction_exact": legacy == handoff.analysis,
                    "same_decision": candidate.decision == legacy.decision,
                    "same_evidence_links": candidate.evidence_links == legacy.evidence_links,
                    "same_missing_info_and_question": (
                        candidate.missing_info == legacy.missing_info
                        and candidate.next_question == legacy.next_question
                    ),
                    "canonical_ask_unchanged": legacy.decision != "ask"
                    or candidate.user_draft == legacy.user_draft,
                    "all_selected_complete_source_quotes_in_summary": all(
                        text in candidate.maintainer_summary for text in quoted.values()
                    ),
                    "all_supplied_source_urls_in_inventory": source_inventory,
                    "proposed_next_step_visible": "Proposed next step"
                    in candidate.maintainer_summary,
                    "legacy_lengths": {
                        key: len(getattr(legacy, key))
                        for key in ("user_draft", "maintainer_summary", "rationale")
                    },
                    "candidate_lengths": {
                        key: len(getattr(candidate, key))
                        for key in ("user_draft", "maintainer_summary", "rationale")
                    },
                    "legacy_visible_cr_markers_in_summary": legacy.maintainer_summary.count(
                        "\\\\u000d"
                    ),
                    "candidate_visible_cr_markers_in_summary": candidate.maintainer_summary.count(
                        "\\\\u000d"
                    ),
                    "candidate_analysis_sha256": hashlib.sha256(
                        candidate.model_dump_json().encode()
                    ).hexdigest(),
                    "quality_claim": False,
                }
                rows.append(record)
    checks = (
        "recorded_request_and_plan_bound",
        "legacy_reconstruction_exact",
        "same_decision",
        "same_evidence_links",
        "same_missing_info_and_question",
        "canonical_ask_unchanged",
        "all_selected_complete_source_quotes_in_summary",
        "all_supplied_source_urls_in_inventory",
        "proposed_next_step_visible",
    )
    return {
        "schema_version": 1,
        "task_id": "C4p",
        "kind": "offline deterministic re-render of existing exposed paid-model plans",
        "archive_path": ARCHIVE,
        "archive_sha256": ARCHIVE_SHA256,
        "original_archive_bytes_preserved": True,
        "all_recorded_step_entries_accounted_for": True,
        "recorded_step_entries": len(rows) + len(nonfresh_states),
        "recorded_nonfresh_entries": len(nonfresh_states),
        "nonfresh_states": nonfresh_states,
        "fresh_proposals_compared": len(rows),
        "rows": rows,
        "checks_passed": sum(bool(row[key]) for row in rows for key in checks),
        "checks_total": len(rows) * len(checks),
        "comparison_limits": [
            "Recorded decisions and selected references are replayed, not new model choices.",
            "Lengths, quote retention and section presence do not establish answer usefulness or support.",
            "Candidate AnalysisResult surfaces require a fresh bound handoff and maintainer approval before any delivery.",
            "No held-out cases, retrieval, model API, credentials, index or ledger client is used.",
            "Historical human scores remain attached to original outputs; no score is transferred.",
            "This projection enumerates recorded step entries, including repeated/stale/failure records, not unique visited or all planned turns. Original unvisited states remain in the unchanged campaign registration; no campaign completion rate is computed here.",
        ],
        "provider_calls": 0,
        "human_usefulness": None,
        "claim_support": "unassessed",
        "quality_claim": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(Path(__file__).resolve().parents[1])
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "fresh_proposals_compared",
                    "recorded_nonfresh_entries",
                    "checks_passed",
                    "checks_total",
                    "provider_calls",
                    "quality_claim",
                )
            }
        )
    )
    if result["checks_passed"] != result["checks_total"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
