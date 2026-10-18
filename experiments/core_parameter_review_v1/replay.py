"""Reproduce source-aware inspection of three already-authored candidates.

No new model selections, semantic labels, provider calls or runtime changes.
Qualitative AI review is a separate sidecar, never an input to this driver.
"""

import argparse
import hashlib
import json
import stat
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.core_parameter_focus_v1.candidate import (  # noqa: E402
    build_parameter_focus_request,
    render_parameter_focus_candidate,
)
from experiments.core_parameter_focus_v1.replay import (  # noqa: E402
    run_replay as run_original_replay,
)
from experiments.core_parameter_focus_v1.replay import write_new_report  # noqa: E402
from experiments.core_parameter_review_v1.display import (  # noqa: E402
    build_parameter_review,
    validate_parameter_review,
)
from experiments.core_parameter_review_v1.integrity import _digest  # noqa: E402

from agent_app.contracts import GroundedRequest  # noqa: E402

PACKAGE = Path(__file__).resolve().parent
ORIGINAL = PACKAGE.parent / "core_parameter_focus_v1"
_ERROR = "ParameterInspectionReplayRejected"


def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError
        value[key] = item
    return value


def _invalid_constant(_value):
    raise ValueError


def _read(path):
    info = path.lstat()
    if path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError
    if info.st_size > 2_000_000:
        raise ValueError
    raw = path.read_bytes()
    return raw, json.loads(raw, object_pairs_hook=_unique, parse_constant=_invalid_constant)


def run_review_replay():
    try:
        protocol_raw, protocol = _read(PACKAGE / "protocol-v1.json")
        expected_names = {"replay-fixture-v1.json", "replay-result-v2.json", "protocol-v1.json"}
        if (
            set(protocol["input_sha256"]) != expected_names
            or type(protocol["provider_calls_planned"]) is not int
            or protocol["provider_calls_planned"] != 0
            or type(protocol["ledger_writes_planned"]) is not int
            or protocol["ledger_writes_planned"] != 0
            or protocol["runtime_adoption"] is not False
        ):
            raise ValueError
        inputs = {}
        for name, digest in protocol["input_sha256"].items():
            raw, value = _read(ORIGINAL / name)
            if hashlib.sha256(raw).hexdigest() != digest:
                raise ValueError
            inputs[name] = value
        original = inputs["replay-result-v2.json"]
        if _digest(run_original_replay()) != _digest(original):
            raise ValueError
        targets = protocol["targets"]
        if (
            type(targets) is not list
            or len(targets) != 3
            or len({item["turn"] for item in targets}) != 3
        ):
            raise ValueError
        rows = []
        fixture = inputs["replay-fixture-v1.json"]
        for spec in targets:
            recorded = [
                row
                for row in original["rows"]
                if row["turn"] == spec["turn"] and "candidate" in row["projection"]
            ]
            if len(recorded) != 1:
                raise ValueError
            baseline = recorded[0]
            sources = [
                row
                for row in fixture["rows"]
                if row["turn"] == spec["turn"] and row["attempt"] == baseline["attempt"]
            ]
            if len(sources) != 1:
                raise ValueError
            request = GroundedRequest.model_validate(sources[0]["grounded_request"])
            focus = build_parameter_focus_request(request)
            candidate = render_parameter_focus_candidate(
                focus, json.dumps(baseline["projection"]["authored_plan"])
            )
            if _digest(asdict(candidate)) != _digest(baseline["projection"]["candidate"]):
                raise ValueError
            if tuple(item.parameter_name for item in candidate.quotations) != (
                spec["selected_parameter"],
            ):
                raise ValueError
            review = build_parameter_review(focus, candidate)
            validate_parameter_review(focus, candidate, review)
            exact_quote = candidate.quotations[0]
            controls = {
                "old_candidate_exactly_preserved": _digest(asdict(review.original_candidate))
                == _digest(baseline["projection"]["candidate"]),
                "complete_original_parameter_preserved": review.original_candidate.quotations
                == candidate.quotations,
                "citation_in_concise_surface": "[Supplied documentation](" in review.concise_text,
                "local_coordinate_frame_explicit": "within the supplied excerpt"
                in review.concise_text,
                "source_warning_visible": "Source checks requiring review:" in review.concise_text,
                "full_original_review_retained": candidate.review_text in review.maintainer_text,
                "no_semantic_or_human_score": review.semantic_support is None
                and review.human_usefulness is None,
                "no_model_or_release_authority": review.model_selection_observed is False
                and review.approved_response_or_action is False
                and review.runtime_adoption is False,
            }
            rows.append(
                {
                    "turn": spec["turn"],
                    "parameter": exact_quote.parameter_name,
                    "condition": "same_original_authored_selection; deterministic_review_only",
                    "old_candidate_chars": len(candidate.qualified_text),
                    "new_inspection_chars": len(review.concise_text),
                    "length_is_not_the_acceptance_target": True,
                    "selected_unit_has_integrity_warning": (
                        review.integrity.selected_unit_has_integrity_warning
                    ),
                    "selected_source_has_span_warning": (
                        review.integrity.selected_source_has_span_warning
                    ),
                    "controls": controls,
                    "review": asdict(review),
                }
            )
        return {
            "schema_version": 1,
            "experiment_id": "core_parameter_review_v1",
            "protocol_sha256": hashlib.sha256(protocol_raw).hexdigest(),
            "input_sha256": protocol["input_sha256"],
            "provider_calls": 0,
            "ledger_writes": 0,
            "runtime_adoption": False,
            "human_usefulness": None,
            "semantic_support": None,
            "model_quality_improvement_established": False,
            "all_eight_old_attempts_and_seven_final_turns_retained": True,
            "all_old_candidates_exactly_preserved": True,
            "all_review_surface_controls_pass": all(all(row["controls"].values()) for row in rows),
            "rows": rows,
            "limits": protocol["non_goals"],
            "ai_qualitative_sidecar_used_as_driver_or_model_input": False,
        }
    except Exception:
        raise ValueError(_ERROR) from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    try:
        report = run_review_replay()
        write_new_report(arguments.output, report)
        print(json.dumps({key: value for key, value in report.items() if key != "rows"}))
        return 0 if report["all_review_surface_controls_pass"] else 2
    except Exception:
        print(json.dumps({"error_code": _ERROR}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
