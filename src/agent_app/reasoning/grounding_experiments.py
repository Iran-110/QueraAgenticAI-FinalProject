"""Replay frozen V9 extractive-boundary controls without API or tracker actions.

Authored plans, curated catalogs and expected checks test software containment and
integrity. Their results never establish source truth, entailment or model quality.
"""

import argparse
import copy
import hashlib
import html
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, get_args

from pydantic import ValidationError

from agent_app.contracts import (
    AnalysisResult,
    CaseState,
    EvidenceBundle,
    EvidenceHit,
    GroundedGap,
    GroundedRequest,
    ReasoningContext,
    RetrievalRequest,
    RunLimits,
    RunResult,
)
from agent_app.orchestration.engine import SupportEngine
from agent_app.reasoning.grounding import (
    GroundedReasoner,
    GroundingRejected,
    make_grounded_request,
    render_grounded_plan,
    source_content_sha256,
    source_scope,
)

_ROOT = Path(__file__).resolve().parents[3]
_FIXTURES = _ROOT / "experiments" / "decision_quality"
_SUITE_SHA256 = "66e132abb1be158ab162fa2a7551f67d2000e44d65627fe8b4e5c9e7b3442d70"
_PROTOCOL_SHA256 = "1038621f87eb3646bde8ed1cab350ab43ac8df884bbb58257b9748b953a87cef"
REGISTRATION_COMMIT = "56ec12a"

type ExperimentCode = Literal[
    "RegistrationMismatch",
    "FixtureInvalid",
    "UnknownRegisteredOperation",
    "ReplayUnavailable",
    "OutputExists",
    "OutputWriteFailed",
]


class ExperimentRejected(ValueError):
    """Allowlisted runner diagnostics; arbitrary errors and input never escape."""

    def __init__(self, code: ExperimentCode) -> None:
        if code not in get_args(ExperimentCode.__value__):
            raise ValueError("Unsupported experiment code.")
        self.code = code
        super().__init__(code)


def _encoded(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@dataclass(frozen=True)
class GroundingPack:
    suite: dict[str, Any]
    protocol: dict[str, Any]


def load_grounding_pack(
    suite_path: Path | None = None, protocol_path: Path | None = None
) -> GroundingPack:
    try:
        suite_bytes = (suite_path or _FIXTURES / "cases-grounding-v9.json").read_bytes()
        protocol_bytes = (protocol_path or _FIXTURES / "protocol-grounding-v9.json").read_bytes()
    except OSError:
        raise ExperimentRejected("FixtureInvalid") from None
    if (
        hashlib.sha256(suite_bytes).hexdigest() != _SUITE_SHA256
        or hashlib.sha256(protocol_bytes).hexdigest() != _PROTOCOL_SHA256
    ):
        raise ExperimentRejected("RegistrationMismatch")
    try:
        pack = GroundingPack(json.loads(suite_bytes), json.loads(protocol_bytes))
    except (ValueError, UnicodeError, RecursionError):
        raise ExperimentRejected("FixtureInvalid") from None
    validate_grounding_pack(pack)
    return pack


def _catalog(case: dict[str, Any]) -> tuple[tuple[GroundedGap, ...], tuple[tuple[str, ...], ...]]:
    catalog = case["grounding_catalog"]
    return (
        tuple(GroundedGap.model_validate(gap) for gap in catalog["gaps"]),
        tuple(tuple(group) for group in catalog["conflict_groups"]),
    )


def validate_grounding_pack(pack: GroundingPack) -> dict[str, Any]:
    """Check the registration and inputs; do not run any scenario or adapter."""
    if (
        hashlib.sha256(_encoded(pack.suite)).hexdigest() != _SUITE_SHA256
        or hashlib.sha256(_encoded(pack.protocol)).hexdigest() != _PROTOCOL_SHA256
    ):
        raise ExperimentRejected("RegistrationMismatch")
    suite, protocol = pack.suite, pack.protocol
    try:
        if (
            protocol["suite_sha256"] != _SUITE_SHA256
            or protocol["paid_calls_authorized"]
            or protocol["model"] is not None
            or suite["execution_boundary"]["paid_calls_authorized"]
            or not suite["execution_boundary"]["offline_only"]
            or suite["reserved_issue_ids"] != [8061, 8901, 12629, 12782, 16914]
        ):
            raise ValueError
        RunLimits.model_validate(protocol["limits"])
        legacy_bytes = (_FIXTURES / "cases-controlled-v8.json").read_bytes()
        if hashlib.sha256(legacy_bytes).hexdigest() != suite["baseline"]["suite_sha256"]:
            raise ValueError
        legacy = json.loads(legacy_bytes)
        case_ids, replay_ids, positive_ids = set(), set(), set()
        for case, original in zip(suite["cases"], legacy["cases"], strict=True):
            old_keys = {key: value for key, value in case.items() if key in original}
            if old_keys != original or case["id"] in case_ids:
                raise ValueError
            case_ids.add(case["id"])
            CaseState.model_validate(case["case_state"])
            _catalog(case)
            for bundle in case["bundles"]:
                evidence = EvidenceBundle.model_validate(bundle)
                if evidence.snapshot_id != suite["snapshot_id"] or len(evidence.hits) > 5:
                    raise ValueError
            for replay in case["authored_replays"]:
                if replay["id"] in replay_ids:
                    raise ValueError
                replay_ids.add(replay["id"])
                if replay["control"] == "positive":
                    positive_ids.add(replay["id"])
                for result in replay["sequence"]:
                    AnalysisResult.model_validate(result)
        mapped_ids = {mapping["baseline_replay_id"] for mapping in suite["positive_plan_mappings"]}
        probes = suite["structured_probes"]
        if (
            len(case_ids) != protocol["scenario_count"]
            or len(replay_ids) != protocol["legacy_baseline_replay_count"]
            or len(suite["positive_plan_mappings"]) != protocol["positive_plan_mapping_count"]
            or mapped_ids != positive_ids
            or len(probes) != protocol["structured_probe_count"]
            or len({probe["id"] for probe in probes}) != len(probes)
            or any(probe["case_id"] not in case_ids for probe in probes)
        ):
            raise ValueError
    except (KeyError, ValueError, TypeError, OSError, ValidationError, RecursionError):
        raise ExperimentRejected("FixtureInvalid") from None
    return {
        "registration_commit": REGISTRATION_COMMIT,
        "suite_sha256": _SUITE_SHA256,
        "protocol_sha256": _PROTOCOL_SHA256,
        "cases": len(case_ids),
        "legacy_replays": len(replay_ids),
        "positive_mappings": len(mapped_ids),
        "structured_probes": len(probes),
        "scenario_execution": False,
        "real_api_calls": 0,
    }


class _FixedRetriever:
    def __init__(self, bundles: list[dict[str, Any]]) -> None:
        self.bundles = copy.deepcopy(bundles)
        self.requests: list[dict[str, Any]] = []
        self.returned: list[EvidenceBundle] = []

    def search(self, request: RetrievalRequest) -> EvidenceBundle:
        index = len(self.requests)
        self.requests.append(request.model_dump(mode="json"))
        # The core owns retrieval_round, including its exact latest-bundle hash.
        bundle = EvidenceBundle.model_validate(self.bundles[index]).model_copy(
            update={"retrieval_round": index + 1}
        )
        self.returned.append(bundle)
        return bundle


class _LegacyReasoner:
    def __init__(self, sequence: list[dict[str, Any]]) -> None:
        self.sequence = sequence
        self.calls: list[dict[str, Any]] = []

    def analyze(
        self, case: CaseState, message: str, evidence: EvidenceBundle, *, context: ReasoningContext
    ) -> dict[str, Any]:
        index = min(len(self.calls), len(self.sequence) - 1)
        self.calls.append(
            {
                "context": context.model_dump(mode="json"),
                "evidence": evidence.model_dump(mode="json"),
            }
        )
        return copy.deepcopy(self.sequence[index])


def _compile_plan(request: GroundedRequest, template: dict[str, Any]) -> dict[str, Any]:
    hits = {hit.chunk_id: hit for hit in request.evidence.hits}
    return {
        "context_sha256": request.context_sha256,
        "decision": template["decision"],
        "sources": [
            {
                "chunk_id": chunk,
                "content_sha256": source_content_sha256(hits[chunk]) if chunk in hits else "0" * 64,
            }
            for chunk in template["source_chunk_ids"]
        ],
        "question_name": template["question_name"],
        "retrieval_queries": copy.deepcopy(template["retrieval_queries"]),
    }


_MUTATIONS = {
    "none",
    "replace_plan_field",
    "replace_first_source_hash",
    "reference_absent_source",
    "change_source_after_plan_hash",
    "change_case_after_context_hash",
    "use_prior_state_context_hash",
    "second_plan_source_hash_from_first_bundle",
    "add_plan_field",
    "add_first_source_field",
    "append_catalog_gap",
    "clear_conflict_groups",
    "replace_source_before_preparation",
}


def _probe_inputs(case: dict[str, Any], mutation: dict[str, Any]) -> dict[str, Any]:
    changed = copy.deepcopy(case)
    operation = mutation["operation"]
    if operation not in _MUTATIONS:
        raise ExperimentRejected("UnknownRegisteredOperation")
    if operation == "change_case_after_context_hash":
        fact = next(
            fact
            for fact in changed["case_state"]["facts"]
            if fact["name"] == mutation["fact_name"] and fact["status"] == "active"
        )
        fact["value"] = mutation["value"]
    elif operation in {"change_source_after_plan_hash", "replace_source_before_preparation"}:
        for bundle in changed["bundles"]:
            for hit in bundle["hits"]:
                if hit["chunk_id"] != mutation["chunk_id"]:
                    continue
                if operation == "replace_source_before_preparation":
                    hit.update(copy.deepcopy(mutation["fields"]))
                elif "suffix" in mutation:
                    hit[mutation["field"]] += mutation["suffix"]
                else:
                    hit[mutation["field"]] = copy.deepcopy(mutation["value"])
    elif operation == "append_catalog_gap":
        changed["grounding_catalog"]["gaps"].append(copy.deepcopy(mutation["gap"]))
    elif operation == "clear_conflict_groups":
        changed["grounding_catalog"]["conflict_groups"] = []
    return changed


class _TemplatePlanner:
    def __init__(
        self,
        templates: list[dict[str, Any]],
        original: dict[str, Any],
        mutation: dict[str, Any],
    ) -> None:
        self.templates, self.original, self.mutation = templates, original, mutation
        self.calls: list[dict[str, Any]] = []

    def plan(self, request: GroundedRequest, *, context: ReasoningContext) -> dict[str, Any]:
        index = min(len(self.calls), len(self.templates) - 1)
        plan = _compile_plan(request, self.templates[index])
        mutation, operation = self.mutation, self.mutation["operation"]
        if operation in {"replace_plan_field", "add_plan_field"}:
            plan[mutation["field"]] = copy.deepcopy(mutation["value"])
        elif operation == "replace_first_source_hash":
            plan["sources"][0]["content_sha256"] = mutation["value"]
        elif operation == "reference_absent_source":
            plan["sources"][0]["content_sha256"] = mutation["content_sha256"]
        elif operation == "add_first_source_field":
            plan["sources"][0][mutation["field"]] = copy.deepcopy(mutation["value"])
        elif operation in {
            "change_source_after_plan_hash",
            "second_plan_source_hash_from_first_bundle",
        }:
            chunk = mutation["chunk_id"]
            hit = next(
                hit for hit in self.original["bundles"][0]["hits"] if hit["chunk_id"] == chunk
            )
            for reference in plan["sources"]:
                if reference["chunk_id"] == chunk:
                    reference["content_sha256"] = source_content_sha256(
                        EvidenceHit.model_validate(hit)
                    )
        elif operation in {"change_case_after_context_hash", "use_prior_state_context_hash"}:
            original_state = self.original["case_state"]
            if operation == "use_prior_state_context_hash":
                original_state = self.original["transition_input"]["prior_case_state"]
            prior = make_grounded_request(
                CaseState.model_validate(original_state),
                request.user_message,
                request.evidence,
                gaps=request.gaps,
                conflict_groups=request.conflict_groups,
            )
            plan["context_sha256"] = prior.context_sha256
        self.calls.append(
            {
                "context": context.model_dump(mode="json"),
                "request": request.model_dump(mode="json"),
                "request_sha256": request.context_sha256,
                "catalog_sha256": _fingerprint(
                    {
                        "gaps": [gap.model_dump(mode="json") for gap in request.gaps],
                        "conflict_groups": request.model_dump(mode="json")["conflict_groups"],
                    }
                ),
                "source_hashes": {
                    hit.chunk_id: source_content_sha256(hit) for hit in request.evidence.hits
                },
                "plan": copy.deepcopy(plan),
            }
        )
        return plan


def _result_capture(result: RunResult, retriever: _FixedRetriever) -> dict[str, Any]:
    analysis = result.analysis.model_dump(mode="json") if result.analysis else None
    latest = retriever.returned[-1].model_dump(mode="json") if retriever.returned else None
    return {
        "status": result.status,
        "final_decision": result.analysis.decision if result.analysis else None,
        "error_code": result.error_code,
        "model_attempts": result.model_attempts,
        "retrieval_rounds": result.retrieval_rounds,
        "steps": result.steps,
        "analysis": analysis,
        "analysis_sha256": _fingerprint(analysis) if analysis else None,
        "latest_evidence": latest,
        "latest_evidence_sha256": _fingerprint(latest) if latest else None,
        "retrieval_requests": retriever.requests,
        "trace": [event.model_dump(mode="json") for event in result.trace],
        "output_issues": [issue.model_dump(mode="json") for issue in result.output_issues],
    }


def _run_legacy(
    case: dict[str, Any], replay: dict[str, Any], pack: GroundingPack
) -> dict[str, Any]:
    state = CaseState.model_validate(case["case_state"])
    retriever = _FixedRetriever(case["bundles"])
    reasoner = _LegacyReasoner(replay["sequence"])
    result = SupportEngine(
        retriever,
        reasoner,
        snapshot_id=pack.suite["snapshot_id"],
        current_revision=lambda _: state.case_revision,
        limits=RunLimits.model_validate(pack.protocol["limits"]),
        top_k=pack.protocol["top_k"],
    ).run(state, case["user_message"], run_id=f"v9-baseline-{replay['id']}")
    actual = _result_capture(result, retriever)
    actual["reasoner_observations"] = reasoner.calls
    actual["expected_matched"] = all(
        actual.get(key) == value for key, value in replay["expected_by_scope"]["all"].items()
    )
    return actual


def _run_candidate(
    case: dict[str, Any],
    templates: list[dict[str, Any]],
    pack: GroundingPack,
    *,
    replay_id: str,
    mutation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    mutation = mutation or {"operation": "none"}
    changed = _probe_inputs(case, mutation)
    state = CaseState.model_validate(changed["case_state"])
    gaps, groups = _catalog(changed)
    planner = _TemplatePlanner(templates, case, mutation)
    factory_errors: list[str] = []

    def factory(case_state: CaseState, message: str, evidence: EvidenceBundle) -> GroundedRequest:
        try:
            return make_grounded_request(
                case_state, message, evidence, gaps=gaps, conflict_groups=groups
            )
        except GroundingRejected as error:
            factory_errors.append(error.code)
            raise

    retriever = _FixedRetriever(changed["bundles"])
    reasoner = GroundedReasoner(planner, request_factory=factory)
    result = SupportEngine(
        retriever,
        reasoner,
        snapshot_id=pack.suite["snapshot_id"],
        current_revision=lambda _: state.case_revision,
        limits=RunLimits.model_validate(pack.protocol["limits"]),
        top_k=pack.protocol["top_k"],
    ).run(state, changed["user_message"], run_id=f"v9-candidate-{replay_id}")
    actual = _result_capture(result, retriever)
    actual.update(
        case_sha256=_fingerprint(state.model_dump(mode="json")),
        case_state=state.model_dump(mode="json"),
        catalog=copy.deepcopy(changed["grounding_catalog"]),
        catalog_sha256=_fingerprint(changed["grounding_catalog"]),
        planner_observations=planner.calls,
        request_preparation_codes=factory_errors,
    )
    if result.analysis and planner.calls:
        latest_request = GroundedRequest.model_validate(planner.calls[-1]["request"])
        actual["rendered_source_scopes"] = {
            link.chunk_id: source_scope(
                latest_request.case,
                next(hit for hit in latest_request.evidence.hits if hit.chunk_id == link.chunk_id),
            )
            for link in result.analysis.evidence_links
        }
    return actual


def _unescape_display(text: str) -> str:
    # An independent reconstruction checks full raw fixture excerpts against
    # escaped blockquotes instead of reusing the renderer's escaping function.
    return html.unescape(re.sub(r"\\([\\`*_{}\[\]()#!|~])", r"\1", text))


def _quoted_excerpts(text: str) -> list[str]:
    excerpts, pending = [], []
    for line in text.split("\n"):
        if line.startswith("> "):
            pending.append(line[2:])
        elif pending:
            excerpts.append(_unescape_display("\n".join(pending)))
            pending = []
    if pending:
        excerpts.append(_unescape_display("\n".join(pending)))
    return excerpts


def _expected_sources(actual: dict[str, Any]) -> tuple[set[str], list[dict[str, Any]]]:
    """Use the retained plan and caller groups, never output citations as gold."""
    if not actual.get("planner_observations"):
        return set(), []
    observation = actual["planner_observations"][-1]
    request = observation["request"]
    expected_ids = {reference["chunk_id"] for reference in observation["plan"]["sources"]}
    expected_ids.update(chunk for group in request["conflict_groups"] for chunk in group)
    return expected_ids, [
        hit for hit in request["evidence"]["hits"] if hit["chunk_id"] in expected_ids
    ]


def _source_set_matches(actual: dict[str, Any]) -> bool:
    analysis = actual.get("analysis")
    if analysis is None or not actual.get("planner_observations"):
        return False
    expected_ids, available = _expected_sources(actual)
    linked = {link["chunk_id"] for link in analysis["evidence_links"]}
    return expected_ids == linked == {hit["chunk_id"] for hit in available}


def _final_render_bound(actual: dict[str, Any]) -> bool:
    """Check all retained fields against their immutable request/plan binding.

    This is a deterministic rendering integrity check, not a second semantic
    judge. The independent quote/fact/scope checks remain necessary as well.
    """
    analysis = actual.get("analysis")
    if analysis is None or not actual.get("planner_observations"):
        return False
    observation = actual["planner_observations"][-1]
    try:
        request = GroundedRequest.model_validate(observation["request"])
        expected = render_grounded_plan(request, observation["plan"]).model_dump(mode="json")
        validated = AnalysisResult.model_validate(analysis).model_dump(mode="json")
    except (GroundingRejected, ValidationError, TypeError, ValueError, RecursionError):
        return False
    return validated == expected and actual["analysis_sha256"] == _fingerprint(validated)


def _check_render(name: str, actual: dict[str, Any]) -> bool:
    bounded = (
        actual["model_attempts"] <= 2
        and actual["retrieval_rounds"] <= 2
        and actual["steps"] <= 8
        and all(len(request["queries"]) <= 2 for request in actual["retrieval_requests"])
    )
    if name in {
        "maximum_two_model_attempts",
        "maximum_two_retrieval_rounds",
        "no_unbounded_resume",
    }:
        return bounded
    if name == "bounded_two_attempt_two_round_sequence":
        return bounded and actual["model_attempts"] == actual["retrieval_rounds"] == 2
    if name in {"latest_bundle_only", "no_retired_citation"}:
        if not actual["planner_observations"]:
            return False
        final_call = actual["planner_observations"][-1]
        available = {hit["chunk_id"] for hit in final_call["request"]["evidence"]["hits"]}
        selected = {hit["chunk_id"] for hit in final_call["plan"]["sources"]}
        return actual["analysis"] is None and bool(selected - available)
    analysis = actual["analysis"]
    if analysis is None or not actual["planner_observations"]:
        return False
    request = actual["planner_observations"][-1]["request"]
    summary = _unescape_display(analysis["maintainer_summary"])
    facts_section = summary.split("User-reported active facts:\n", 1)[-1].split(
        "\n\nUser-reported checks:", 1
    )[0]
    active = [
        fact
        for fact in request["case"]["facts"]
        if fact["status"] == "active" and fact["provenance_kind"] == "user"
    ]
    version = next((fact["value"] for fact in active if fact["name"] == "streamlit_version"), None)
    linked = {link["chunk_id"] for link in analysis["evidence_links"]}
    expected_ids, selected = _expected_sources(actual)
    gaps = {gap["name"]: gap for gap in request["gaps"]}
    question = analysis["next_question"]
    if name == "all_active_user_facts_attributed":
        return "User-reported active facts:" in summary and all(
            f"{fact['name']}: {fact['value']}" in facts_section for fact in active
        )
    if name == "whole_selected_excerpts":
        quotes = _quoted_excerpts(analysis["maintainer_summary"])
        draft_quotes = (
            _quoted_excerpts(analysis["user_draft"]) if analysis["decision"] == "answer" else quotes
        )
        return (
            bool(expected_ids)
            and _source_set_matches(actual)
            and all(hit["excerpt"] in quotes and hit["excerpt"] in draft_quotes for hit in selected)
        )
    if name == "current_exact_metadata_label":
        return (
            bool(version)
            and any(version in hit["applicable_versions"] for hit in selected)
            and ("Supplied version metadata exactly matches the user-reported version" in summary)
        )
    if name == "historical_other_version_label":
        return (
            bool(version)
            and any(
                hit["applicable_versions"] and version not in hit["applicable_versions"]
                for hit in selected
            )
            and "not evidence of applicability to the current installation" in summary
        )
    if name == "unconfirmed_applicability_label":
        return any(version is None or not hit["applicable_versions"] for hit in selected) and (
            "Applicability to the installed environment is unconfirmed" in summary
        )
    if name in {"only_active_user_version_current", "superseded_version_not_rendered_as_current"}:
        retired = [
            fact
            for fact in request["case"]["facts"]
            if fact["name"] == "streamlit_version" and fact["status"] == "superseded"
        ]
        return f"streamlit_version: {version}" in facts_section and all(
            f"streamlit_version: {fact['value']}" not in facts_section for fact in retired
        )
    if name == "no_patch_equivalence_inferred":
        return (
            version == "1.49.1"
            and all("1.49.1" not in hit["applicable_versions"] for hit in selected)
            and ("not evidence of applicability to the current installation" in summary)
        )
    if name == "no_source_version_promoted_to_user_fact":
        return (
            version is None
            and "streamlit_version:" not in facts_section
            and not analysis["facts_delta"]
        )
    if name == "working_reduction_report_preserved":
        return any(
            fact["name"] == "reported_reproduction_status"
            and f"{fact['name']}: {fact['value']}" in facts_section
            for fact in active
        )
    if name == "exact_canonical_question":
        target = (
            gaps.get(analysis["missing_info"][0]) if len(analysis["missing_info"]) == 1 else None
        )
        return (
            bool(target)
            and target["kind"] == "user"
            and (question == analysis["user_draft"] == target["question"])
        )
    if name in {"user_gap_separated_from_source_gap", "source_gap_not_presented_as_user_question"}:
        return (
            len(analysis["missing_info"]) == 1
            and analysis["missing_info"][0] in gaps
            and gaps[analysis["missing_info"][0]]["kind"] == "user"
            and all(gap["question"] is None for gap in request["gaps"] if gap["kind"] == "source")
        )
    if name == "all_declared_conflict_members_rendered":
        mandatory = {chunk for group in request["conflict_groups"] for chunk in group}
        quotes = _quoted_excerpts(analysis["maintainer_summary"])
        return (
            bool(mandatory)
            and mandatory <= linked
            and all(
                hit["excerpt"] in quotes
                for hit in request["evidence"]["hits"]
                if hit["chunk_id"] in mandatory
            )
        )
    if name == "conflict_is_caller_declared":
        return bool(request["conflict_groups"]) and "caller-declared source conflict" in summary
    if name == "local_escalation_is_only_proposal":
        return analysis["decision"] == "escalate" and (
            "Further maintainer investigation is proposed" in analysis["user_draft"]
        )
    if name == "unverified_cause_and_fix_disclaimer":
        return (
            "a successful fix and a resolved case are not established by this proposal" in summary
            and not analysis["facts_delta"]
            and not analysis["checks_suggested"]
        )
    if name == "source_text_attributed_not_verified":
        return (
            bool(selected)
            and "These are attributed supplied records" in summary
            and all(
                "not a verified cause or fix" in link["claim"]
                for link in analysis["evidence_links"]
            )
        )
    raise ExperimentRejected("UnknownRegisteredOperation")


def _run_mapping(
    case: dict[str, Any], mapping: dict[str, Any], pack: GroundingPack
) -> dict[str, Any]:
    actual = _run_candidate(
        case, mapping["plan_templates"], pack, replay_id=mapping["baseline_replay_id"]
    )
    expected_decision = mapping["plan_templates"][-1]["decision"]
    checks = {name: _check_render(name, actual) for name in mapping["required_render_checks"]}
    checks.update(
        contract_selected_source_set=_source_set_matches(actual),
        contract_final_render_bound=_final_render_bound(actual),
    )
    actual.update(
        render_checks=checks,
        registered_final_decision=expected_decision,
        expected_matched=actual["status"] == "awaiting_approval"
        and actual["final_decision"] == expected_decision
        and all(checks.values()),
    )
    return actual


def _expected_rejection_cause(probe: dict[str, Any]) -> tuple[str, str | None]:
    """Require the typed reason implicit in the registered operation/shape.

    Frozen boundary labels remain untouched. Adapter crashes or unrelated
    failures are never a substitute for the specific software guard exercised.
    """
    operation = probe["mutation"]["operation"]
    if operation in {
        "replace_plan_field",
        "change_case_after_context_hash",
        "use_prior_state_context_hash",
    }:
        return "GroundedContextMismatch", "grounded_context_mismatch"
    if operation in {
        "replace_first_source_hash",
        "reference_absent_source",
        "change_source_after_plan_hash",
        "second_plan_source_hash_from_first_bundle",
    }:
        return "GroundedSourceMismatch", "grounded_source_mismatch"
    if operation in {"add_plan_field", "add_first_source_field"}:
        return "ModelOutputInvalid", "invalid_grounded_plan"
    template = probe["plan_templates"][-1]
    if (
        len(template["retrieval_queries"]) > 2
        or (template["decision"] == "ask" and template["question_name"] is None)
        or (template["decision"] != "ask" and template["question_name"] is not None)
    ):
        return "ModelOutputInvalid", "invalid_grounded_plan"
    if probe["category"] == "question_boundary":
        return "ModelOutputInvalid", "grounded_question_invalid"
    if probe["category"] == "declared_conflict" and template["decision"] == "answer":
        return "ModelOutputInvalid", "grounded_conflict_unresolved"
    if probe["expected"]["boundary"] == "stop" and template["decision"] == "retrieve_more":
        return "ModelAttemptLimitExceeded", None
    raise ExperimentRejected("UnknownRegisteredOperation")


def _rejection_cause_matches(actual: dict[str, Any], expected: tuple[str, str | None]) -> bool:
    error_code, issue_code = expected
    codes = {issue["code"] for issue in actual["output_issues"]}
    if actual["error_code"] != error_code:
        return False
    if issue_code is None:
        return not codes
    return bool(codes) and codes == {issue_code}


def _run_probe(case: dict[str, Any], probe: dict[str, Any], pack: GroundingPack) -> dict[str, Any]:
    actual = _run_candidate(
        case,
        probe["plan_templates"],
        pack,
        replay_id=probe["id"],
        mutation=probe["mutation"],
    )
    expected = probe["expected"]
    boundary = "accept" if actual["status"] == "awaiting_approval" else "reject"
    if expected["boundary"] == "stop":
        boundary_ok = actual["status"] in {"error", "budget_stopped"}
    else:
        boundary_ok = boundary == expected["boundary"]
    checks = {name: _check_render(name, actual) for name in expected.get("checks", [])}
    rejection_cause = None
    cause_matched = True
    if expected["boundary"] == "accept":
        checks.update(
            contract_selected_source_set=_source_set_matches(actual),
            contract_final_render_bound=_final_render_bound(actual),
        )
    else:
        rejection_cause = _expected_rejection_cause(probe)
        cause_matched = _rejection_cause_matches(actual, rejection_cause)
    matched = boundary_ok and cause_matched and all(checks.values())
    if "final_decision" in expected:
        matched &= actual["final_decision"] == expected["final_decision"]
    if expected.get("stage") == "request_preparation":
        matched &= bool(actual["request_preparation_codes"]) and not actual["planner_observations"]
    actual.update(
        boundary=boundary,
        render_checks=checks,
        required_rejection_cause=(
            {"error_code": rejection_cause[0], "issue_code": rejection_cause[1]}
            if rejection_cause
            else None
        ),
        rejection_cause_matched=cause_matched,
        expected_matched=bool(matched),
    )
    return actual


def _raw_legacy_conformance(case: dict[str, Any], replay: dict[str, Any]) -> dict[str, Any]:
    gaps, groups = _catalog(case)
    request = make_grounded_request(
        CaseState.model_validate(case["case_state"]),
        case["user_message"],
        EvidenceBundle.model_validate(case["bundles"][0]),
        gaps=gaps,
        conflict_groups=groups,
    )
    # Every step is checked; an otherwise valid old retrieve_more is also a
    # different representation. This does not invoke a model or engine.
    codes = []
    for raw in replay["sequence"]:
        try:
            render_grounded_plan(request, raw)
        except GroundingRejected as error:
            codes.append(error.code)
        else:
            codes.append(None)
    return {
        "replay_id": replay["id"],
        "control": replay["control"],
        "rejected": all(code == "invalid_grounded_plan" for code in codes),
        "codes": codes,
        "meaning": "representation_mismatch_not_automatic_semantic_detection",
    }


def _code_fingerprint() -> str:
    digest = hashlib.sha256()
    package = Path(__file__).resolve().parents[1]
    for relative in (
        "contracts.py",
        "orchestration/engine.py",
        "orchestration/ports.py",
        "reasoning/code_checks.py",
        "reasoning/output.py",
        "reasoning/grounding.py",
        "reasoning/grounding_experiments.py",
    ):
        digest.update(relative.encode())
        digest.update((package / relative).read_bytes())
    return digest.hexdigest()


def _historical_baseline_comparison(
    pack: GroundingPack, baseline: list[dict[str, Any]]
) -> dict[str, Any]:
    """Compare current-default replay with the separate isolated Git-code receipt.

    This runner does not import or execute historical code. The dedicated script
    owns that execution; the receipt records the observed states and source pools.
    """
    try:
        path = _FIXTURES / "baseline-git-v9.json"
        receipt_bytes = path.read_bytes()
        receipt = json.loads(receipt_bytes)
        if (
            receipt["baseline_git_commit"] != pack.protocol["baseline_git_commit"]
            or receipt["registration_git_commit"] != REGISTRATION_COMMIT
            or receipt["suite_sha256"] != pack.suite["baseline"]["suite_sha256"]
            or receipt["real_api_calls"] != 0
            or receipt["paid_cost_usd"] != "0"
            or receipt["original_default_scope"] != "all"
        ):
            raise ValueError
        original = {row["replay_id"]: row for row in receipt["observations"]}
        if len(original) != len(receipt["observations"]) or set(original) != {
            row["replay_id"] for row in baseline
        }:
            raise ValueError
        observations = []
        for row in baseline:
            recorded = original[row["replay_id"]]
            actual = row["actual"]
            source_pools = [
                [hit["chunk_id"] for hit in call["evidence"]["hits"]]
                for call in actual["reasoner_observations"]
            ]
            fields_match = all(
                actual.get(key) == value for key, value in recorded["observed"].items()
            )
            pools_match = source_pools == recorded["reasoner_chunk_ids"]
            observations.append(
                {
                    "replay_id": row["replay_id"],
                    "historical_observed": copy.deepcopy(recorded["observed"]),
                    "historical_source_pools": copy.deepcopy(recorded["reasoner_chunk_ids"]),
                    "current_source_pools": source_pools,
                    "outcomes_match": fields_match,
                    "source_pools_match": pools_match,
                    "matched": fields_match and pools_match,
                }
            )
    except (OSError, KeyError, ValueError, TypeError, UnicodeError, RecursionError):
        raise ExperimentRejected("FixtureInvalid") from None
    return {
        "receipt_path": "experiments/decision_quality/baseline-git-v9.json",
        "receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
        "baseline_git_commit": receipt["baseline_git_commit"],
        "role": "separate_receipt_from_isolated_historical_git_code_execution",
        "this_runner_executes_historical_code": False,
        "all_current_default_outcomes_and_source_pools_match": all(
            row["matched"] for row in observations
        ),
        "observations": observations,
    }


def replay_grounding_pack(pack: GroundingPack) -> dict[str, Any]:
    validation = validate_grounding_pack(pack)
    cases = {case["id"]: case for case in pack.suite["cases"]}
    baseline, conformance = [], []
    for case in cases.values():
        for replay in case["authored_replays"]:
            baseline.append(
                {
                    "case_id": case["id"],
                    "replay_id": replay["id"],
                    "control": replay["control"],
                    "authored_semantic_label": replay["semantic_expectation"]["label"],
                    "registered_final_decision": replay["sequence"][-1]["decision"],
                    "actual": _run_legacy(case, replay, pack),
                }
            )
            conformance.append(_raw_legacy_conformance(case, replay))
    historical = _historical_baseline_comparison(pack, baseline)
    mappings = [
        {
            "case_id": mapping["case_id"],
            "baseline_replay_id": mapping["baseline_replay_id"],
            "intent_preserved": mapping["intent_preserved"],
            "actual": _run_mapping(cases[mapping["case_id"]], mapping, pack),
        }
        for mapping in pack.suite["positive_plan_mappings"]
    ]
    probes = [
        {
            "probe_id": probe["id"],
            "category": probe["category"],
            "registered_expected": copy.deepcopy(probe["expected"]),
            "actual": _run_probe(cases[probe["case_id"]], probe, pack),
        }
        for probe in pack.suite["structured_probes"]
    ]
    failures = [
        f"baseline/{row['replay_id']}" for row in baseline if not row["actual"]["expected_matched"]
    ]
    failures += [
        f"raw-conformance/{row['replay_id']}" for row in conformance if not row["rejected"]
    ]
    failures += [
        f"positive-mapping/{row['baseline_replay_id']}"
        for row in mappings
        if not row["actual"]["expected_matched"]
    ]
    failures += [
        f"structured-probe/{row['probe_id']}"
        for row in probes
        if not row["actual"]["expected_matched"]
    ]
    failures += [
        f"historical-baseline/{row['replay_id']}"
        for row in historical["observations"]
        if not row["matched"]
    ]
    positive = [row for row in baseline if row["control"] == "positive"]
    negative = [row for row in baseline if row["control"] == "negative"]
    categories = {}
    for row in probes:
        category = categories.setdefault(row["category"], {"matched": 0, "registered": 0})
        category["registered"] += 1
        category["matched"] += int(row["actual"]["expected_matched"])
    unclassified = [
        row["probe_id"]
        for row in probes
        if any(value == "unclassified" for value in row["registered_expected"].values())
    ]
    return {
        **validation,
        "code_sha256": _code_fingerprint(),
        "scenario_execution": True,
        "authored_proposals_not_model_outputs": True,
        "extra_candidate_caller_metadata": True,
        "automatic_conflict_detection": False,
        "semantic_entailment_measured": False,
        "live_model_quality_measured": False,
        "RAG_quality_measured": False,
        "source_authenticity_measured": False,
        "tracker_actions_executed": 0,
        "legacy_replay_role": "current_default_replay_of_frozen_v8_baseline",
        "historical_baseline_reference": {
            key: value for key, value in historical.items() if key != "observations"
        },
        "summary": {
            "legacy_baseline": {
                "negative_accepted": sum(
                    row["actual"]["status"] == "awaiting_approval" for row in negative
                ),
                "negative_controls": len(negative),
                "positive_retained": sum(
                    row["actual"]["status"] == "awaiting_approval"
                    and row["actual"]["final_decision"] == row["registered_final_decision"]
                    for row in positive
                ),
                "positive_controls": len(positive),
                "registered_outcomes_matched": sum(
                    row["actual"]["expected_matched"] for row in baseline
                ),
            },
            "raw_legacy_representation": {
                "rejected": sum(row["rejected"] for row in conformance),
                "registered": len(conformance),
                "includes_valid_legacy_positives": True,
                "semantic_detection_score": None,
            },
            "mapped_positive_intents": {
                "retained": sum(row["actual"]["expected_matched"] for row in mappings),
                "registered": len(mappings),
            },
            "structured_categories": categories,
            "unclassified_coverage_control_ids": unclassified,
        },
        "all_registered_expectations_matched": not failures,
        "failures": failures,
        "baseline_observations": baseline,
        "historical_baseline_comparison_observations": historical["observations"],
        "raw_conformance_observations": conformance,
        "mapped_positive_observations": mappings,
        "structured_probe_observations": probes,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.output is not None and args.output.exists():
            raise ExperimentRejected("OutputExists")
        pack = load_grounding_pack()
        result = (
            validate_grounding_pack(pack) if args.validate_only else replay_grounding_pack(pack)
        )
        if args.output is not None:
            try:
                with args.output.open("x", encoding="utf-8") as output:
                    output.write(_encoded(result).decode("utf-8"))
            except FileExistsError:
                raise ExperimentRejected("OutputExists") from None
            except OSError:
                raise ExperimentRejected("OutputWriteFailed") from None
    except ExperimentRejected as error:
        print(json.dumps({"error_code": error.code}, sort_keys=True))
        return 2
    except Exception:
        # Library callers retain failures for debugging; CLI never prints an
        # arbitrary exception that may contain input values or unknown names.
        print(json.dumps({"error_code": "ReplayUnavailable"}, sort_keys=True))
        return 2
    aggregate = {key: value for key, value in result.items() if not key.endswith("observations")}
    print(json.dumps(aggregate, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("all_registered_expectations_matched", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
