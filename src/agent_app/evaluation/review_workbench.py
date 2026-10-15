"""Offline, content-bound review preparation; no judgment, model or action.

This adapter reads actual C4g/C4h receipts rather than renderer replays. Frozen
fixed-evidence strata are retained as registrations, never silently relabelled
for native retrieval. A caller declaring a human reviewer is not authenticated.
"""

import hashlib
import html
import json
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from agent_app.contracts import ProposalHandoff
from agent_app.evaluation.semantic_review import (
    QuestionJudgment,
    ReviewScope,
    SemanticReview,
    aggregate_reviews,
    score_review,
)
from agent_app.orchestration.handoff import validate_handoff
from agent_app.reasoning.review import _surface_texts, review_user_fact_sha256

_CODES = {
    "InvalidWorkbenchInput",
    "WorkbenchInputChanged",
    "WorkbenchReceiptMismatch",
    "WorkbenchFixtureMismatch",
    "WorkbenchHandoffMismatch",
    "WorkbenchScopeMismatch",
    "WorkbenchDuplicateReview",
    "WorkbenchReviewNotEligible",
    "WorkbenchReviewUnassigned",
    "WorkbenchOutputExists",
    "WorkbenchWriteFailed",
}
_ROOT = Path(__file__).resolve().parents[3]

_CAMPAIGNS = {
    "dev-real-index-model-v1": (
        "live-method-v1.json",
        "experiments/dev_rag_coverage_v1/protocol-v1.json",
        "c4g-offline-review-workbench-v1",
    ),
    "core-repeat-repair-model-v1": (
        "live-method-v1.json",
        "experiments/core_repeat_repair_v1/protocol-v1.json",
        "c4h2-offline-review-workbench-v1",
    ),
    "core-source-capacity-model-v1": (
        "live-method-v1.json",
        "experiments/core_source_capacity_v1/protocol-v1.json",
        "c4h3-offline-review-workbench-v1",
    ),
    "core-compact-plan-model-v1": (
        "live-method-v1.json",
        "experiments/core_compact_plan_v1/protocol-v1.json",
        "c4h4-offline-review-workbench-v1",
    ),
    "retrieval-relevance-model-v1": (
        "live-method-v1.json",
        "experiments/retrieval_relevance_v1/protocol-v1.json",
        "r4c-offline-review-workbench-v1",
    ),
    "core-ask-background-model-v1": (
        "live-method-v1.json",
        "experiments/core_ask_background_v1/protocol-v1.json",
        "c4h6-offline-review-workbench-v1",
    ),
    "core-resource-guidance-model-v1": (
        "live-method-v2.json",
        "experiments/core_resource_guidance_v1/protocol-v1.json",
        "c4h-offline-review-workbench-v1",
    ),
}


# These treatments retained C4g's native criteria instead of redefining
# source sufficiency after seeing outputs. Never infer criteria from fixtures.
_NATIVE_CRITERIA = {
    name: _ROOT / "experiments/dev_rag_coverage_v1/protocol-v1.json"
    for name in (
        "core-repeat-repair-model-v1",
        "core-source-capacity-model-v1",
        "core-compact-plan-model-v1",
        "retrieval-relevance-model-v1",
        "core-ask-background-model-v1",
    )
}

_NATIVE_AMENDMENTS = {
    "core-compact-plan-model-v1": (
        "experiments/core_compact_plan_v1/semantic-review-preparation-v1.json",
        "docs/pr55-evidence-review.fa.md",
    ),
    "retrieval-relevance-model-v1": (
        "experiments/retrieval_relevance_v1/semantic-review-preparation-v1.json",
        "docs/pr55-evidence-review.fa.md",
    ),
    "core-ask-background-model-v1": (
        "experiments/core_ask_background_v1/semantic-review-preparation-v1.json",
        "docs/pr55-evidence-review.fa.md",
    ),
}


class WorkbenchRejected(ValueError):
    def __init__(self, code="InvalidWorkbenchInput"):
        if code not in _CODES:
            code = "InvalidWorkbenchInput"
        self.code = code
        super().__init__(code)


def _need(condition, code="InvalidWorkbenchInput"):
    if not condition:
        raise WorkbenchRejected(code)


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value):
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _read(path):
    try:
        path = Path(path).resolve(strict=True)
        raw = path.read_bytes()
        value = json.loads(raw)
        _need(type(value) is dict)
        return value, {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()}
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError):
        raise WorkbenchRejected() from None


def _pin(path):
    try:
        path = Path(path).resolve(strict=True)
        return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    except (OSError, ValueError, TypeError):
        raise WorkbenchRejected() from None


def _validate_handoff(raw):
    try:
        return validate_handoff(ProposalHandoff.model_validate(raw))
    except (ValidationError, ValueError, TypeError, AttributeError, RecursionError):
        raise WorkbenchRejected("WorkbenchHandoffMismatch") from None


def _template(handoff, scope, item_id):
    applies = (
        handoff.analysis.decision == "ask"
        or handoff.analysis.next_question is not None
        or bool(handoff.analysis.checks_suggested)
    )
    annotation = "unassessed" if applies else "not_applicable"
    return SemanticReview(
        review_id=f"pending-{item_id}",
        scope=scope,
        handoff_sha256=handoff.handoff_sha256,
        reviewer_id="unassigned",
        reviewer_kind="assistant",
        response_origin="model",
        declared_material_claim_count=0,
        claim_inventory_complete=False,
        reviewed_surfaces=(),
        claim_bindings=(),
        decision_judgment="unassessed",
        decision_reason="Pending independent review.",
        question=QuestionJudgment(
            applies=applies,
            necessary=annotation,
            answerable=annotation,
            not_repeating_known=annotation,
            reason="Pending review of every request and suggested check.",
        ),
        usefulness_score=None,
        usefulness_reason="No human usefulness judgment has been supplied.",
    ).model_dump(mode="json")


def _proposal_record(raw, case_id):
    handoff = _validate_handoff(raw["review_handoff"])
    analysis = handoff.analysis.model_dump(mode="json")
    _need(
        raw["proposal_id"] == handoff.proposal_id
        and raw["case_id"] == case_id == handoff.case.case_id
        and raw["case_revision"] == handoff.case.case_revision
        and raw["analysis"] == analysis
        and all(
            raw[name] == analysis[name]
            for name in (
                "decision",
                "user_draft",
                "next_question",
                "maintainer_summary",
                "rationale",
                "missing_info",
                "facts_delta",
                "checks_suggested",
                "retrieval_queries",
            )
        ),
        "WorkbenchHandoffMismatch",
    )
    return {
        "proposal_id": handoff.proposal_id,
        "handoff_sha256": handoff.handoff_sha256,
        "proposal_sha256": _hash(raw),
        "handoff": handoff.model_dump(mode="json"),
        "surfaces": _surface_texts(handoff.analysis),
        "active_user_facts": [
            {"fact": fact.model_dump(mode="json"), "sha256": review_user_fact_sha256(fact)}
            for fact in handoff.case.facts
            if fact.status == "active" and fact.provenance_kind == "user"
        ],
    }


def build_workbench(
    receipt_path: Path,
    fixture_paths: Sequence[Path],
    scenario_path: Path,
    rubric_path: Path,
) -> dict:
    """Read exposed development artifacts; keep all planned/failed turn rows."""
    try:
        receipt, receipt_pin = _read(receipt_path)
        _need(receipt.get("protocol_id") in _CAMPAIGNS, "WorkbenchReceiptMismatch")
        method_name, protocol_name, kind = _CAMPAIGNS[receipt["protocol_id"]]
        method_file, method_pin = _read(Path(receipt_path).parent / method_name)
        protocol, protocol_pin = _read(Path(receipt_path).parent / "protocol-v1.json")
        scenario, scenario_pin = _read(scenario_path)
        rubric_pin = _pin(rubric_path)
        fixtures, fixture_pins = {}, []
        for path in fixture_paths:
            fixture, pin = _read(path)
            case = fixture["case"]
            case_id = case["case_id"]
            _need(case_id not in fixtures, "WorkbenchFixtureMismatch")
            _need(
                case["split"] == "dev"
                and case["test_eligible"] is False
                and fixture["registered_before_first_run"] is True,
                "WorkbenchFixtureMismatch",
            )
            fixtures[case_id] = (fixture, pin)
            fixture_pins.append(pin)
        method = receipt["method"]
        if receipt["protocol_id"] == "core-ask-background-model-v1":
            _need(
                receipt.get("renderer_ask_source_background") is True
                and receipt.get("no_model_prompt_treatment") is True
                and receipt.get("single_paid_model_condition") is True
                and all(
                    job.get("ask_source_background") is True and job["arm"] == "candidate_profile"
                    for batch in method["batches"]
                    for job in batch["jobs"]
                ),
                "WorkbenchReceiptMismatch",
            )
        _need(
            receipt["real_index_retrieval"] is True
            and receipt["held_out_test"] is False
            and receipt["human_reviewed"] is False
            and receipt["human_usefulness"] is None
            and method["protocol_id"] == receipt["protocol_id"]
            and method_file == method
            and receipt["registration"]["method_sha256"] == method_pin["sha256"]
            and method["input_pins"][protocol_name] == protocol_pin["sha256"],
            "WorkbenchReceiptMismatch",
        )
        _need(
            scenario["registered_before_first_run"] is True and scenario["human_reviewed"] is False,
            "WorkbenchFixtureMismatch",
        )
        scenario_cases = {case["case_id"]: case for case in scenario["case_reviews"]}
        _need(len(scenario_cases) == len(scenario["case_reviews"]))
        criteria_protocol, criteria_pin = protocol, None
        if receipt["protocol_id"] in _NATIVE_CRITERIA:
            criteria_protocol, criteria_pin = _read(_NATIVE_CRITERIA[receipt["protocol_id"]])
            _need(
                method["input_pins"]["experiments/dev_rag_coverage_v1/protocol-v1.json"]
                == criteria_pin["sha256"],
                "WorkbenchReceiptMismatch",
            )
        criteria = {case["case"]: case for case in criteria_protocol["pre_model_scenarios"]}
        _need(len(criteria) == len(criteria_protocol["pre_model_scenarios"]))
        inputs = {
            "receipt": receipt_pin,
            "fixtures": sorted(fixture_pins, key=lambda pin: pin["path"]),
            "scenario": scenario_pin,
            "rubric": rubric_pin,
            "method": method_pin,
            "protocol": protocol_pin,
        }
        if criteria_pin is not None:
            inputs["native_criteria"] = criteria_pin
        amendment = None
        topical_guidance, supported_topical_guidance = None, None
        if receipt["protocol_id"] in _NATIVE_AMENDMENTS:
            preparation_name, evidence_review_name = _NATIVE_AMENDMENTS[receipt["protocol_id"]]
            preparation, preparation_pin = _read(_ROOT / preparation_name)
            evidence_review_pin = _pin(_ROOT / evidence_review_name)
            amendment = preparation["case_a_prospective_evidence_amendment"]
            _need(
                preparation["registered_before_model"] is True
                and preparation["native_criteria_path"]
                == "experiments/dev_rag_coverage_v1/protocol-v1.json"
                and preparation["native_criteria_sha256"] == criteria_pin["sha256"]
                and method["input_pins"][preparation_name] == preparation_pin["sha256"]
                and amendment["review_path"] == evidence_review_name
                and amendment["review_sha256"] == evidence_review_pin["sha256"]
                and method["input_pins"][evidence_review_name] == evidence_review_pin["sha256"],
                "WorkbenchReceiptMismatch",
            )
            inputs["native_criteria_preparation"] = preparation_pin
            inputs["native_evidence_review"] = evidence_review_pin
            if receipt["protocol_id"] in {
                "retrieval-relevance-model-v1",
                "core-ask-background-model-v1",
            }:
                topical_guidance = preparation.get("topical_guidance_criteria")
                supported_topical_guidance = preparation.get("supported_topical_guidance")
                _need(
                    type(topical_guidance) is dict
                    and set(topical_guidance) == set(criteria)
                    and all(
                        type(value) is str and value.strip() for value in topical_guidance.values()
                    )
                    and type(supported_topical_guidance) is str
                    and supported_topical_guidance.strip(),
                    "WorkbenchReceiptMismatch",
                )
        # The source registration already binds fixture/scenario byte hashes.
        registered = set(method["input_pins"].values())
        _need(
            {pin["sha256"] for pin in fixture_pins} | {scenario_pin["sha256"]} <= registered,
            "WorkbenchFixtureMismatch",
        )
        packet_id = _hash({"kind": kind, "inputs": inputs})
        planned = {
            batch["batch_id"]: {job["job_id"]: job for job in batch["jobs"]}
            for batch in method["batches"]
        }
        _need(len(planned) == len(method["batches"]))
        batches = {batch["batch_id"]: batch for batch in receipt["batches"]}
        _need(len(batches) == len(receipt["batches"]) and set(batches) <= set(planned))
        rows, seen_jobs = [], set()
        for batch_plan in method["batches"]:
            batch_id = batch_plan["batch_id"]
            batch = batches.get(batch_id)
            jobs = {job["job_id"]: job for job in batch["jobs"]} if batch else {}
            _need(not batch or len(jobs) == len(batch["jobs"]))
            _need(set(jobs) <= set(planned[batch_id]), "WorkbenchReceiptMismatch")
            for job_plan in batch_plan["jobs"]:
                job_id, case_id = job_plan["job_id"], job_plan["case_id"]
                _need(job_id not in seen_jobs, "WorkbenchReceiptMismatch")
                seen_jobs.add(job_id)
                fixture, fixture_pin = fixtures[case_id]
                job = jobs.get(job_id)
                _need(
                    not job
                    or (
                        job["fixture_id"] == fixture["fixture_id"]
                        and job["fixture_sha256"] == fixture_pin["sha256"]
                        and all(job[key] == job_plan[key] for key in job_plan)
                    ),
                    "WorkbenchFixtureMismatch",
                )
                case_scenario = scenario_cases[case_id]
                _need(case_scenario["fixture_id"] == fixture["fixture_id"])
                scenarios = {turn["turn_id"]: turn for turn in case_scenario["turns"]}
                _need(len(scenarios) == len(case_scenario["turns"]))
                steps = job["steps"] if job else []
                consumed = {step["turn"]: step for step in steps if "request" in step}
                _need(len(consumed) == sum("request" in step for step in steps))
                known_turns = {turn["id"] for turn in fixture["turns"]}
                _need(set(consumed) <= known_turns, "WorkbenchFixtureMismatch")
                for turn in fixture["turns"]:
                    turn_id = turn["id"]
                    registered_turn = scenarios[turn_id]
                    _need(registered_turn["gold"] == turn["gold"], "WorkbenchFixtureMismatch")
                    step = consumed.get(turn_id)
                    if step:
                        _need(
                            all(
                                step["request"][name] == value
                                for name, value in turn["visible"].items()
                                if name
                                in {
                                    "message",
                                    "scenario",
                                    "reported_facts",
                                    "unknowns",
                                    "checks_performed",
                                    "context_changed",
                                }
                            ),
                            "WorkbenchFixtureMismatch",
                        )
                    raw = step.get("proposal") if step else None
                    observed = (
                        _proposal_record(raw, case_id)
                        if raw and raw.get("review_handoff")
                        else None
                    )
                    status = "unvisited"
                    if step:
                        status = "no_fresh_proposal"
                        if observed:
                            expected_revision = step["request"]["expected_revision"] + 1
                            status = (
                                "fresh_proposal"
                                if raw.get("stale") is False
                                and raw["case_revision"] == expected_revision
                                else "stale_observation"
                            )
                            if status == "fresh_proposal":
                                _need(
                                    observed["handoff"]["reasoning_context"]["run_id"]
                                    in job["run_ids"]
                                    and sum(
                                        attempt["context"]
                                        == observed["handoff"]["reasoning_context"]
                                        and attempt["request"]
                                        == observed["handoff"]["grounded_request"]
                                        for attempt in batch["attempts"]
                                    )
                                    == 1,
                                    "WorkbenchHandoffMismatch",
                                )
                    item_id = _hash({"job_id": job_id, "turn_id": turn_id})[:24]
                    scope = ReviewScope(
                        run_id=method["experiment_id"],
                        config_id=job_plan["arm"],
                        config_sha256=_hash(
                            {
                                "method": receipt["registration"]["method_sha256"],
                                "arm": job_plan["arm"],
                            }
                        ),
                        rubric_id=scenario["rubric_id"],
                        rubric_sha256=rubric_pin["sha256"],
                        stratum=turn["gold"]["stratum"],
                        stratum_registration_sha256=scenario_pin["sha256"],
                        stratum_registered_before_run=True,
                    )
                    edited = step.get("edited_proposal") if step else None
                    row = {
                        "item_id": item_id,
                        "job_id": job_id,
                        "arm": job_plan["arm"],
                        "round": job_plan["round"],
                        "case_id": case_id,
                        "turn_id": turn_id,
                        "fixture_id": fixture["fixture_id"],
                        "fixture_sha256": fixture_pin["sha256"],
                        "status": status,
                        "selected_route_complete": bool(job and job["coverage_complete"]),
                        "original_proposal": observed,
                        "edited_proposal": _proposal_record(edited, case_id) if edited else None,
                        "released_outputs": step.get("released_outputs", []) if step else [],
                        "maintainer_behavior": "fixture_scripted_not_human_approval",
                        "consumed_input": step["request"] if step else None,
                        "consumed_input_sha256": _hash(step["request"]) if step else None,
                        "operational_usage": step.get("usage") if step else None,
                        "actual_model_attempts": [
                            attempt
                            for attempt in batch.get("attempts", [])
                            if step
                            and attempt["context"]["run_id"] in job["run_ids"]
                            and attempt["context"]["case_revision"]
                            == step["request"]["expected_revision"] + 1
                        ]
                        if batch and job
                        else [],
                        "native_retrievals": [
                            result
                            for result in batch.get("actual_retrievals", [])
                            if result["job_id"] == job_id and result["turn_id"] == turn_id
                        ]
                        if batch
                        else [],
                        "registered_stratum": scope.stratum,
                        "registered_decision_conditions": turn["gold"].get(
                            "decision_conditions", {}
                        ),
                        "registered_acceptable_decisions": turn["gold"]["acceptable_decisions"],
                        "actual_index_preregistered_criteria": criteria[case_id],
                        "oracle_evidence_condition": scenario["evidence_condition"],
                        "actual_evidence_condition": receipt["embedding"]
                        + "_native_top5_post_ranking_version_scope",
                        "oracle_evidence_condition_matches_actual": False,
                        "scope": scope.model_dump(mode="json"),
                        "runner_diagnostics": [
                            diagnostic
                            for diagnostic in steps
                            if diagnostic.get("turn") == turn_id and "runner_stop" in diagnostic
                        ],
                        "operational_checks": [
                            check for check in job.get("checks", []) if check.get("step") == turn_id
                        ]
                        if job
                        else [],
                    }
                    if amendment is not None and case_id == "dev-case-a":
                        row["actual_index_preregistered_amendment"] = amendment
                    if topical_guidance is not None:
                        row["supported_topical_guidance"] = supported_topical_guidance
                        row["topical_guidance_criteria"] = topical_guidance[case_id]
                    if receipt["protocol_id"] == "core-ask-background-model-v1":
                        row["renderer_condition"] = "ask_source_background_on"
                        row["comparison_condition"] = (
                            "OFF renderer on the identical actual request/plan; no second model call"
                        )
                    row["item_binding_sha256"] = _hash(row)
                    row["review_template"] = (
                        _template(_validate_handoff(observed["handoff"]), scope, item_id)
                        if status == "fresh_proposal"
                        else None
                    )
                    rows.append(row)
        counts = Counter(row["status"] for row in rows)
        result = {
            "schema_version": 1,
            "kind": kind,
            "packet_id": packet_id,
            "inputs": inputs,
            "quality_claim": False,
            "authorizes_action": False,
            "held_out_test": False,
            "human_reviewed": False,
            "human_usefulness": None,
            "rubric_status": "draft_recommendation_not_team_frozen",
            "strata_scope": "preregistered_fixed_evidence_strata_retained_for_native_evidence_review",
            "summary": {
                "planned_jobs": len(seen_jobs),
                "planned_turns": len(rows),
                "visited_turns": len(rows) - counts["unvisited"],
                "no_fresh_response_turns": counts["no_fresh_proposal"]
                + counts["stale_observation"],
                **{
                    status: counts[status]
                    for status in (
                        "fresh_proposal",
                        "stale_observation",
                        "no_fresh_proposal",
                        "unvisited",
                    )
                },
            },
            "rows": rows,
        }
        result["workbench_sha256"] = _hash(result)
        return result
    except WorkbenchRejected:
        raise
    except (KeyError, ValueError, TypeError, AttributeError, RecursionError):
        raise WorkbenchRejected() from None


def _write_text_new(path, value):
    try:
        with path.open("x", encoding="utf-8") as stream:
            path.chmod(0o600)
            stream.write(value)
    except FileExistsError:
        raise WorkbenchRejected("WorkbenchOutputExists") from None
    except OSError:
        raise WorkbenchRejected("WorkbenchWriteFailed") from None


def _write_new(path, value):
    _write_text_new(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def _html_index(workbench):
    """Escaped local reader only; retrieved text never becomes HTML or script."""

    def pre(value):
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
        return "<pre>" + html.escape(text) + "</pre>"

    parts = [
        "<!doctype html><html lang='en'><meta charset='utf-8'>",
        "<title>Exposed dev semantic review</title>",
        "<style>body{max-width:1000px;margin:2rem auto;font:16px system-ui;padding:1rem}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f4f4;padding:1rem}section{border-top:1px solid #aaa;margin-top:2rem}summary{cursor:pointer}a{color:#125899}</style>",
        "<h1>Exposed dev semantic review — pending</h1>",
        "<p>No human usefulness scores or quality claims. Approval was scripted. Fixed-evidence oracle strata are reference registrations; actual native evidence differs. Use the preregistered native criteria and actual sources. An unvisited turn has no model response to score.</p>",
        pre(workbench["summary"]),
        "<p>Edit copies of pending sidecars; set a distinct review ID and your reviewer identity/kind. Review every output surface. Count and bind material claims with exact Unicode character spans. Unassessed/incomplete is never a support pass.</p>",
    ]
    for row in workbench["rows"]:
        item_id = row["item_id"]
        label = f"{row['job_id']} / {row['turn_id']} — {row['status']}"
        parts.append(f"<section id='{item_id}'><h2>{html.escape(label)}</h2>")
        parts.append(f"<a href='context-{item_id}.json'>Complete bound context JSON</a>")
        if row["review_template"] is not None:
            parts.append(f" · <a href='pending-{item_id}.json'>Blank review sidecar</a>")
        elif row["status"] == "stale_observation":
            parts.append(
                "<p>Old proposal only. This is not a fresh response to the correction and is excluded from proposal scores.</p>"
            )
        parts.append(
            "<details><summary>Current consumed input</summary>"
            + pre(row["consumed_input"])
            + "</details>"
        )
        parts.append(
            "<details><summary>Preregistered native-index criteria</summary>"
            + pre(row["actual_index_preregistered_criteria"])
            + "</details>"
        )
        if "actual_index_preregistered_amendment" in row:
            parts.append(
                "<details><summary>Prospective case-A evidence amendment for this campaign</summary>"
                + pre(row["actual_index_preregistered_amendment"])
                + "</details>"
            )
        if "supported_topical_guidance" in row:
            parts.append(
                "<details><summary>Preregistered topical guidance criteria for this case</summary>"
                + pre(
                    {
                        "supported_topical_guidance": row["supported_topical_guidance"],
                        "topical_guidance_criteria": row["topical_guidance_criteria"],
                    }
                )
                + "</details>"
            )
        parts.append(
            "<details><summary>Reference fixed-evidence conditions (different evidence)</summary>"
            + pre(
                {
                    "stratum": row["registered_stratum"],
                    "decision_conditions": row["registered_decision_conditions"],
                    "evidence_condition_matches_actual": False,
                }
            )
            + "</details>"
        )
        observed = row["original_proposal"]
        if observed:
            parts.append("<details><summary>Complete original observed output surfaces</summary>")
            for name, text in observed["surfaces"].items():
                parts.append("<h3>" + html.escape(name) + "</h3>" + pre(text))
            parts.append(
                "</details><details><summary>Actual supplied evidence and active user facts</summary>"
            )
            parts.append(
                pre(
                    {
                        "active_user_facts": observed["active_user_facts"],
                        "source_inventory": observed["handoff"]["source_inventory"],
                        "evidence": observed["handoff"]["evidence"],
                    }
                )
                + "</details>"
            )
        parts.append(
            "<details><summary>Edited/released output and runner diagnostics</summary>"
            + pre(
                {
                    "edited_proposal": row["edited_proposal"],
                    "released_outputs": row["released_outputs"],
                    "diagnostics": row["runner_diagnostics"],
                    "checks": row["operational_checks"],
                }
            )
            + "</details></section>"
        )
    parts.append("</html>")
    return "\n".join(parts)


def prepare_workbench(receipt_path, fixture_paths, scenario_path, rubric_path, output_dir):
    """Write a fresh private directory; pending templates contain no judgments."""
    workbench = build_workbench(receipt_path, fixture_paths, scenario_path, rubric_path)
    output = Path(output_dir)
    try:
        output.mkdir(parents=True, mode=0o700, exist_ok=False)
    except FileExistsError:
        raise WorkbenchRejected("WorkbenchOutputExists") from None
    except OSError:
        raise WorkbenchRejected("WorkbenchWriteFailed") from None
    _write_new(output / "workbench.json", workbench)
    _write_text_new(output / "review-index.html", _html_index(workbench))
    for row in workbench["rows"]:
        _write_new(output / f"context-{row['item_id']}.json", row)
        if row["review_template"] is not None:
            _write_new(
                output / f"pending-{row['item_id']}.json",
                {
                    "schema_version": 1,
                    "packet_id": workbench["packet_id"],
                    "item_id": row["item_id"],
                    "item_binding_sha256": row["item_binding_sha256"],
                    "review": row["review_template"],
                },
            )
    return workbench


def load_workbench(path):
    workbench, _ = _read(path)
    try:
        inputs = workbench["inputs"]
        for pin in [
            inputs["receipt"],
            inputs["scenario"],
            inputs["rubric"],
            inputs["method"],
            inputs["protocol"],
            *inputs["fixtures"],
            *([inputs["native_criteria"]] if "native_criteria" in inputs else []),
            *(
                [inputs["native_criteria_preparation"]]
                if "native_criteria_preparation" in inputs
                else []
            ),
            *([inputs["native_evidence_review"]] if "native_evidence_review" in inputs else []),
        ]:
            _need(_pin(pin["path"]) == pin, "WorkbenchInputChanged")
        expected = build_workbench(
            inputs["receipt"]["path"],
            [pin["path"] for pin in inputs["fixtures"]],
            inputs["scenario"]["path"],
            inputs["rubric"]["path"],
        )
        _need(expected == workbench, "WorkbenchReceiptMismatch")
        directory = Path(path).parent
        try:
            _need(
                (directory / "review-index.html").read_text(encoding="utf-8")
                == _html_index(expected),
                "WorkbenchReceiptMismatch",
            )
            for row in expected["rows"]:
                context, _ = _read(directory / f"context-{row['item_id']}.json")
                _need(context == row, "WorkbenchHandoffMismatch")
        except OSError:
            raise WorkbenchRejected("WorkbenchReceiptMismatch") from None
        return workbench
    except WorkbenchRejected:
        raise
    except (KeyError, ValueError, TypeError, AttributeError, RecursionError):
        raise WorkbenchRejected() from None


def score_workbench(workbench_path, review_paths):
    """Validate declared sidecars separately; never discard missed-turn rows."""
    workbench = load_workbench(workbench_path)
    rows = {row["item_id"]: row for row in workbench["rows"]}
    scores, seen = [], set()
    try:
        for path in review_paths:
            envelope, _ = _read(path)
            _need(
                set(envelope)
                == {"schema_version", "packet_id", "item_id", "item_binding_sha256", "review"}
            )
            _need(envelope["schema_version"] == 1)
            item_id = envelope["item_id"]
            _need(item_id in rows, "WorkbenchScopeMismatch")
            row = rows[item_id]
            _need(row["status"] == "fresh_proposal", "WorkbenchReviewNotEligible")
            _need(
                envelope["packet_id"] == workbench["packet_id"]
                and envelope["item_binding_sha256"] == row["item_binding_sha256"],
                "WorkbenchScopeMismatch",
            )
            review = SemanticReview.model_validate(envelope["review"])
            _need(
                review.reviewer_id != "unassigned" and not review.review_id.startswith("pending-"),
                "WorkbenchReviewUnassigned",
            )
            # Several independent reviewers may annotate one item, but never
            # overwrite/recount the same reviewer record under another ID.
            identity = (item_id, review.reviewer_kind, review.reviewer_id, review.response_origin)
            _need(identity not in seen, "WorkbenchDuplicateReview")
            seen.add(identity)
            _need(review.response_origin == "model", "WorkbenchReviewNotEligible")
            score = score_review(
                _validate_handoff(row["original_proposal"]["handoff"]),
                review,
                scope=ReviewScope.model_validate(row["scope"]),
            )
            scores.append((row, review, score))
        # Existing aggregation intentionally rejects duplicated proposal votes.
        # Keep independent reviewers in distinct panels rather than vote pooling.
        panels = {}
        for _row, review, score in scores:
            panels.setdefault((review.reviewer_kind, review.reviewer_id), []).append(score)
        reviewed_ids = {row["item_id"] for row, _, _ in scores}
        arms = {}
        for arm in sorted({row["arm"] for row in rows.values()}):
            selected = [row for row in rows.values() if row["arm"] == arm]
            arms[arm] = {
                "planned_turns": len(selected),
                "fresh_proposals": sum(row["status"] == "fresh_proposal" for row in selected),
                "reviewed_fresh_proposals": sum(row["item_id"] in reviewed_ids for row in selected),
                "stale_observations": sum(row["status"] == "stale_observation" for row in selected),
                "no_fresh_proposal": sum(row["status"] == "no_fresh_proposal" for row in selected),
                "unvisited": sum(row["status"] == "unvisited" for row in selected),
                "unreviewed_fresh_proposals": sum(
                    row["status"] == "fresh_proposal" and row["item_id"] not in reviewed_ids
                    for row in selected
                ),
            }
        return {
            "schema_version": 1,
            "packet_id": workbench["packet_id"],
            "workbench_sha256": workbench["workbench_sha256"],
            "quality_claim": False,
            "authorizes_action": False,
            "human_review_authenticated": False,
            "reviewer_kinds_are_caller_declarations": True,
            "rubric_status": workbench["rubric_status"],
            "strata_scope": workbench["strata_scope"],
            "oracle_evidence_condition_matches_actual": False,
            "summary": workbench["summary"],
            "by_arm": arms,
            "reviewer_panels": [
                {
                    "reviewer_kind": key[0],
                    "reviewer_id": key[1],
                    "scores": aggregate_reviews(values),
                }
                for key, values in sorted(panels.items())
            ],
            "scores": [score.model_dump(mode="json") for _, _, score in scores],
        }
    except WorkbenchRejected:
        raise
    except (ValidationError, KeyError, ValueError, TypeError, AttributeError, RecursionError):
        raise WorkbenchRejected("WorkbenchScopeMismatch") from None


def write_score(path, result):
    _write_new(Path(path), result)
