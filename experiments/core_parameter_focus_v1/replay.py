"""Replay exposed recorded plans with authored parameter selections; no provider.

This script never indexes its fixture, opens a ledger, or updates a proposal.
Its reduction/containment controls are not a model or human-quality score.
"""

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.core_parameter_focus_v1.candidate import (  # noqa: E402
    build_parameter_focus_request,
    parameter_focus_payload,
    render_parameter_focus_candidate,
)

from agent_app.contracts import AnalysisResult, GroundedRequest  # noqa: E402
from agent_app.reasoning.grounding import _display, render_grounded_plan  # noqa: E402

PACKAGE = Path(__file__).resolve().parent
_ERROR = "ParameterReplayRejected"
_BASELINE_ORIGINS = frozenset(
    {
        "deterministically_reconstructed_from_original_recorded_plan",
        "matched_original_staged_analysis_exactly",
    }
)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(_ERROR)
        value[key] = item
    return value


def _bad_constant(_):
    raise ValueError(_ERROR)


def _read(name):
    path = PACKAGE / name
    info = path.lstat()
    if (
        path.is_symlink()
        or not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or info.st_size > 1_000_000
    ):
        raise ValueError(_ERROR)
    raw = path.read_bytes()
    return raw, json.loads(raw, object_pairs_hook=_unique, parse_constant=_bad_constant)


def _inputs():
    _, manifest = _read("input-manifest-v1.json")
    fixture_raw, fixture = _read("replay-fixture-v1.json")
    protocol_raw, protocol = _read("protocol-v1.json")
    amendment_raw, amendment = _read("protocol-amendment-v1.json")
    if (
        type(manifest["schema_version"]) is not int
        or manifest["schema_version"] != 1
        or manifest["fixture_sha256"] != _sha(fixture_raw)
        or manifest["protocol_sha256"] != _sha(protocol_raw)
        or manifest["amendment_sha256"] != _sha(amendment_raw)
        or amendment["protocol_sha256"] != _sha(protocol_raw)
        or type(fixture["schema_version"]) is not int
        or fixture["schema_version"] != 1
        or type(fixture["new_model_calls"]) is not int
        or fixture["new_model_calls"] != 0
        or type(protocol["provider_calls_planned"]) is not int
        or protocol["provider_calls_planned"] != 0
        or protocol["runtime_adoption"] is not False
        or any(
            type(manifest[name]) is not int or manifest[name] <= 0
            for name in ("attempt_rows", "final_turns", "primary_turns")
        )
    ):
        raise ValueError(_ERROR)
    expected = [
        {key: item[key] for key in ("turn", "api_name", "parameter")}
        for item in protocol["primary_authored_projections"]
    ]
    if fixture["authored_focus_selection"] != expected:
        raise ValueError(_ERROR)
    return manifest, fixture, protocol


def _projection(request, original_plan, baseline, spec):
    focus = build_parameter_focus_request(request)
    selected_chunks = {item["chunk_id"] for item in original_plan["sources"]}
    choices = [
        choice
        for choice in focus.choices
        if choice.api_name == spec["api_name"]
        and choice.parameter_name == spec["parameter"]
        and request.evidence.hits[choice.source_index].chunk_id in selected_chunks
    ]
    if len(choices) != 1:
        raise ValueError(_ERROR)
    choice = choices[0]
    plan = {
        "context_sha256": focus.context_sha256,
        "decision": "answer",
        "parameters": [choice.parameter_id],
    }
    result = render_parameter_focus_candidate(focus, json.dumps(plan))
    quotation = result.quotations[0]
    hit = request.evidence.hits[choice.source_index]
    # Post-hoc deterministic display diagnostic: separate dropping unrelated
    # selected sources from choosing a smaller complete parameter unit. This
    # remains authored and uses the old renderer, never a new model selection.
    source_only_plan = {
        **original_plan,
        "sources": [item for item in original_plan["sources"] if item["chunk_id"] == hit.chunk_id],
    }
    source_only = render_grounded_plan(
        request, source_only_plan, source_gap_handoff=True, source_gap_investigation=True
    )
    payload = parameter_focus_payload(focus)
    clauses = {
        clause: clause.casefold() in quotation.text.casefold()
        for clause in spec["required_full_clauses"]
    }
    controls = {
        "same_original_answer_decision": baseline.decision == result.decision == "answer",
        "only_original_selected_source": quotation.chunk_id in selected_chunks,
        "complete_parameter_text_exact": quotation.text == hit.excerpt[choice.start : choice.end],
        "raw_source_hash_exact": _sha(hit.excerpt.encode()) == quotation.source_text_sha256,
        "raw_parameter_hash_exact": _sha(quotation.text.encode()) == quotation.passage_sha256,
        "full_source_retained": focus.grounded.evidence.hits[choice.source_index] == hit,
        "registered_clauses_retained": all(clauses.values()),
        "candidate_shorter": len(result.qualified_text) < len(baseline.user_draft),
        "semantic_support_not_claimed": result.semantic_support is None,
        "human_review_still_required": result.human_review_required is True,
        "no_action_authorized": result.proposal_or_action_authorized is False,
        "diagnosis_or_fix_not_verified": result.diagnosis_or_fix_verified is False,
    }
    return {
        "status": "authored_projection_not_new_model_choice",
        "controls": controls,
        "registered_clause_checks": clauses,
        "original_chars": len(baseline.user_draft),
        "candidate_chars": len(result.qualified_text),
        "character_reduction_fraction": round(
            1 - len(result.qualified_text) / len(baseline.user_draft), 6
        ),
        "parameter_chars": len(quotation.text),
        "complete_source_chars": len(hit.excerpt),
        "source_only_diagnostic": {
            "kind": "post_hoc_authored_display_control_not_model_selection",
            "draft_chars": len(source_only.user_draft),
            "full_source_quotation_retained": _display(hit.excerpt)
            in source_only.user_draft.replace("\n> ", "\n"),
            "draft_sha256": _sha(source_only.user_draft.encode()),
            "focus_shorter_than_source_only": len(result.qualified_text)
            < len(source_only.user_draft),
            "lengths_also_include_renderer_qualification_differences": True,
        },
        "inspection_payload_utf8_bytes": len(
            json.dumps(payload, ensure_ascii=False).encode("utf-8")
        ),
        "payload_is_not_a_complete_paid_gateway_request": True,
        "candidate": asdict(result),
        "authored_plan": plan,
    }


def run_replay():
    try:
        manifest, fixture, protocol = _inputs()
        rows, calls, final_turns, attempts = [], set(), set(), {}
        specs = {item["turn"]: item for item in protocol["primary_authored_projections"]}
        for recorded in fixture["rows"]:
            if (
                type(recorded["turn"]) is not str
                or type(recorded["attempt"]) is not int
                or not 1 <= recorded["attempt"] <= 2
                or type(recorded["original_call_sha256"]) is not str
                or re.fullmatch(r"[0-9a-f]{64}", recorded["original_call_sha256"]) is None
                or type(recorded["baseline_origin"]) is not str
                or recorded["baseline_origin"] not in _BASELINE_ORIGINS
                or recorded["turn"] in final_turns
                or recorded["attempt"] != attempts.get(recorded["turn"], 0) + 1
            ):
                raise ValueError(_ERROR)
            request = GroundedRequest.model_validate(recorded["grounded_request"])
            plan = recorded["canonical_plan"]
            baseline = render_grounded_plan(
                request, plan, source_gap_handoff=True, source_gap_investigation=True
            )
            if baseline != AnalysisResult.model_validate(recorded["analysis"]):
                raise ValueError(_ERROR)
            identity = (recorded["turn"], recorded["attempt"])
            if identity in calls:
                raise ValueError(_ERROR)
            calls.add(identity)
            attempts[recorded["turn"]] = recorded["attempt"]
            row = {
                "turn": recorded["turn"],
                "attempt": recorded["attempt"],
                "original_call_sha256": recorded["original_call_sha256"],
                "original_analysis_origin": recorded["baseline_origin"],
                "original_decision": baseline.decision,
                "original_draft_chars": len(baseline.user_draft),
                "original_draft_sha256": _sha(baseline.user_draft.encode()),
                "baseline_exactly_reproduced": True,
            }
            if baseline.decision != "retrieve_more":
                if recorded["turn"] in final_turns:
                    raise ValueError(_ERROR)
                final_turns.add(recorded["turn"])
            if recorded["turn"] in specs and baseline.decision == "answer":
                try:
                    row["projection"] = _projection(request, plan, baseline, specs[row["turn"]])
                except Exception:
                    row["projection"] = {"status": "unavailable", "error_code": _ERROR}
            else:
                row["projection"] = {"status": "unchanged_not_a_registered_parameter_answer"}
            rows.append(row)
        primary = [row["projection"] for row in rows if row["turn"] in specs]
        if (
            len(rows) != manifest["attempt_rows"]
            or len(final_turns) != manifest["final_turns"]
            or set(attempts) != final_turns
            or len(primary) != manifest["primary_turns"]
            or not set(specs).issubset(final_turns)
        ):
            raise ValueError(_ERROR)
        return {
            "schema_version": 1,
            "experiment_id": "core_parameter_focus_v1",
            "protocol_sha256": manifest["protocol_sha256"],
            "fixture_sha256": manifest["fixture_sha256"],
            "provider_calls": 0,
            "ledger_writes": 0,
            "runtime_adoption": False,
            "human_usefulness": None,
            "model_quality_improvement_established": False,
            "enum_fix_verified": False,
            "attempt_rows": len(rows),
            "final_turns_retained": len(final_turns),
            "all_baselines_exactly_reproduced": True,
            "original_call_digest_provenance": (
                "supplied_pinned_historical_digest; original call files are not "
                "reopened or authenticated by this replay"
            ),
            "all_primary_structural_controls_pass": all(
                item.get("controls") and all(item["controls"].values()) for item in primary
            ),
            "rows": rows,
            "unresolved_observations": protocol["retained_unresolved_observations"],
            "limits": protocol["invalid_claims"],
        }
    except Exception:
        raise ValueError(_ERROR) from None


def write_new_report(destination, report):
    destination = Path(destination)
    resolved = destination.resolve()
    if destination.suffix != ".json" or any(
        resolved.is_relative_to(ROOT / name)
        for name in ("data", "runtime", "src", "app_pages", ".git")
    ):
        raise ValueError(_ERROR)
    raw = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False).encode() + b"\n"
    descriptor = os.open(
        destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600
    )
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(raw)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    try:
        report = run_replay()
        write_new_report(arguments.output, report)
        print(json.dumps({key: value for key, value in report.items() if key not in {"rows"}}))
        return 0 if report["all_primary_structural_controls_pass"] else 2
    except Exception:
        print(json.dumps({"error_code": _ERROR}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
