"""Offline replay of authored full proposals; never a model-quality evaluator.

Author labels and detector expectations are kept separate from observed core
acceptance. Fake ports repeat the fixed proposal within the existing allowance;
there is no generated repair, HTTP, credential loading, ledger or snippet execution.
"""

import argparse
import hashlib
import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from agent_app.contracts import (
    AnalysisResult,
    CaseState,
    Contract,
    EvidenceBundle,
    Identifier,
    ProposalRequirements,
    ShortText,
    Text,
)
from agent_app.orchestration import SupportEngine
from agent_app.reasoning.probes import load_suite
from agent_app.testing.fakes import FakeReasoner, FakeRetriever

_REPO = Path(__file__).resolve().parents[3]
_DEFAULT_PACK = _REPO / "experiments/decision_quality/semantic-regressions-v6.json"
_MAX_PACK_BYTES = 2_000_000
_SYNTHETIC_PREFIX = (
    "\n\nAdditional synthetic development question (not an additional installed-version report):\n"
)
Digest = Annotated[str, StringConstraints(strict=True, pattern=r"^[a-f0-9]{64}$")]
CheckCode = Literal["invalid_api_keyword", "callback_value_captured", "callback_arity_mismatch"]


class ExecutionBoundary(Contract):
    offline_only: Literal[True]
    fixed_authored_proposals_not_model_outputs: Literal[True]
    requires_paid_calls: Literal[False]
    embedded_code_is_proposed_and_not_executed: Literal[True]
    production_semantic_judge: Literal[False]
    production_default_change: Literal[False]


class FrozenInput(Contract):
    path: Literal["experiments/decision_quality/cases-guards-v4.json"]
    sha256: Digest
    requirements_path: Literal["experiments/decision_quality/requirements-guards-v4.json"]
    requirements_sha256: Digest
    docs_commit: Identifier
    snapshot_id: Identifier
    source_snapshot_date: ShortText
    source_downloads: tuple[str, ...] = Field(max_length=0)
    private_outputs_or_final_heldout_inputs_used: Literal[False]


class FrozenCopy(Contract):
    case_state: Literal["exact_deep_copy"]
    evidence_bundle: Literal["exact_deep_copy"]
    user_message: Literal["exact_copy", "frozen_message_plus_explicit_synthetic_supplement"]
    proposal_requirements: Literal["exact_deep_copy"]


class SemanticExpectation(Contract):
    label: Literal["acceptable", "needs_revision", "unusable"]
    label_source: Literal["synthetic_developer_expectation"]
    reasons: tuple[Text, ...] = Field(min_length=1, max_length=8)
    unsupported_claims: tuple[Text, ...] = Field(max_length=8)


class StaticScopeExpectation(Contract):
    expected_abstentions: tuple[ShortText, ...] = Field(max_length=12)
    meaning: Text


class ProposalVariant(Contract):
    id: Identifier
    control: Literal["positive", "negative"]
    proposal: AnalysisResult
    expected_check_codes: tuple[CheckCode, ...] = Field(max_length=3)
    semantic_expectation: SemanticExpectation
    static_scope_expectation: StaticScopeExpectation

    @model_validator(mode="after")
    def labels_and_codes_are_distinct(self):
        if len(set(self.expected_check_codes)) != len(self.expected_check_codes):
            raise ValueError("Duplicate detector expectation")
        if (self.control == "positive") != (self.semantic_expectation.label == "acceptable"):
            raise ValueError("Inconsistent authored control label")
        if self.control == "positive" and self.expected_check_codes:
            raise ValueError("A positive control cannot expect rejection")
        if self.proposal.decision == "retrieve_more":
            raise ValueError("This pack replays final full proposals")
        return self


class SemanticScenario(Contract):
    id: Identifier
    role: Literal["paired", "additional_control"]
    kind: Literal["synthetic"]
    origin_url: None
    origin_issue_id: None
    origin_created_at: None
    description: Text
    dimensions: tuple[ShortText, ...] = Field(min_length=1, max_length=12)
    source_case_id: Identifier
    source_bundle_index: Literal[0]
    frozen_copy: FrozenCopy
    context_adaptation: Text | None
    synthetic_supplement: Text | None
    case_state: CaseState
    user_message: Text
    evidence_bundle: EvidenceBundle
    proposal_requirements: ProposalRequirements
    variants: tuple[ProposalVariant, ...] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def controls_are_registered(self):
        if len({variant.id for variant in self.variants}) != len(self.variants):
            raise ValueError("Duplicate variant identity")
        if self.role == "paired" and {variant.control for variant in self.variants} != {
            "positive",
            "negative",
        }:
            raise ValueError("A pair requires both controls")
        if self.role == "additional_control" and len(self.variants) != 1:
            raise ValueError("Additional control must be one fixed proposal")
        return self


class SemanticRegressionPack(Contract):
    schema_version: Literal[1]
    pack_id: Identifier
    purpose: Text
    created_on: ShortText
    author_label_disclaimer: Text
    execution_boundary: ExecutionBoundary
    frozen_input: FrozenInput
    review_boundaries: tuple[Text, ...] = Field(min_length=1, max_length=12)
    semantic_labels: dict[Literal["acceptable", "needs_revision", "unusable"], Text]
    scenarios: tuple[SemanticScenario, ...] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def unique_scenarios(self):
        if len({scenario.id for scenario in self.scenarios}) != len(self.scenarios):
            raise ValueError("Duplicate scenario identity")
        if set(self.semantic_labels) != {"acceptable", "needs_revision", "unusable"}:
            raise ValueError("Missing authored label definition")
        return self


def validate_semantic_pack(
    pack: SemanticRegressionPack, *, repo_root: Path = _REPO
) -> SemanticRegressionPack:
    """Revalidate copies against the registered source files before replay."""
    pack = SemanticRegressionPack.model_validate(pack.model_dump(warnings=False))
    frozen = pack.frozen_input
    source_path = repo_root / frozen.path
    requirements_path = repo_root / frozen.requirements_path
    if hashlib.sha256(source_path.read_bytes()).hexdigest() != frozen.sha256:
        raise ValueError("Frozen source file changed")
    if hashlib.sha256(requirements_path.read_bytes()).hexdigest() != frozen.requirements_sha256:
        raise ValueError("Frozen caller requirements changed")
    suite = load_suite(source_path)
    if (suite.docs_commit, suite.snapshot_id, suite.source_snapshot_date) != (
        frozen.docs_commit,
        frozen.snapshot_id,
        frozen.source_snapshot_date,
    ):
        raise ValueError("Frozen source metadata changed")
    sources = {probe.id: probe for probe in suite.cases}
    catalog = {
        name: ProposalRequirements.model_validate(value)
        for name, value in json.loads(requirements_path.read_text()).items()
    }
    for scenario in pack.scenarios:
        probe = sources.get(scenario.source_case_id)
        if probe is None or probe.kind != "synthetic":
            raise ValueError("Source case must be a registered synthetic development input")
        if scenario.case_state != probe.case_state or scenario.evidence_bundle != probe.bundles[0]:
            raise ValueError("Scenario changed frozen case or evidence")
        if scenario.proposal_requirements != catalog.get(probe.id):
            raise ValueError("Scenario changed caller requirements")
        supplied_chunks = {hit.chunk_id for hit in scenario.evidence_bundle.hits}
        if any(
            link.chunk_id not in supplied_chunks
            for variant in scenario.variants
            for link in variant.proposal.evidence_links
        ):
            raise ValueError("Proposal cites an unavailable source")
        if scenario.frozen_copy.user_message == "exact_copy":
            if (
                scenario.user_message != probe.user_message
                or scenario.context_adaptation is not None
                or scenario.synthetic_supplement is not None
            ):
                raise ValueError("Undeclared user context change")
        elif (
            not scenario.context_adaptation
            or not scenario.synthetic_supplement
            or scenario.user_message
            != probe.user_message + _SYNTHETIC_PREFIX + scenario.synthetic_supplement
        ):
            raise ValueError("Synthetic supplement must be explicit and appended exactly")
    return pack


def load_semantic_pack(path: Path = _DEFAULT_PACK, *, repo_root: Path = _REPO):
    with path.open("rb") as source:
        content = source.read(_MAX_PACK_BYTES + 1)
    if len(content) > _MAX_PACK_BYTES:
        raise ValueError("Oversized semantic regression pack")
    return validate_semantic_pack(
        SemanticRegressionPack.model_validate_json(content), repo_root=repo_root
    )


def semantic_run_id(pack_id: str, scenario_id: str, variant_id: str, checks: bool) -> str:
    identity = json.dumps([pack_id, scenario_id, variant_id, checks], separators=(",", ":"))
    return "semantic:" + hashlib.sha256(identity.encode()).hexdigest()


def replay_semantic_pack(pack: SemanticRegressionPack, *, repo_root: Path = _REPO) -> dict:
    pack = validate_semantic_pack(pack, repo_root=repo_root)
    observations = []
    for scenario in pack.scenarios:
        for variant in scenario.variants:
            conditions = {}
            for checks in (False, True):
                result = SupportEngine(
                    FakeRetriever((scenario.evidence_bundle,)),
                    FakeReasoner((variant.proposal, variant.proposal)),
                    snapshot_id=scenario.evidence_bundle.snapshot_id,
                    proposal_checks=checks,
                ).run(
                    scenario.case_state,
                    scenario.user_message,
                    run_id=semantic_run_id(pack.pack_id, scenario.id, variant.id, checks),
                    proposal_requirements=scenario.proposal_requirements,
                )
                conditions["checks_on" if checks else "checks_off"] = {
                    "accepted": result.status == "awaiting_approval",
                    "status": result.status,
                    "error_code": result.error_code,
                    "scripted_attempts": result.model_attempts,
                    "issue_codes": sorted({issue.code for issue in result.output_issues}),
                }
            observed = conditions["checks_on"]["issue_codes"]
            expected = sorted(variant.expected_check_codes)
            scope_matched = (
                observed == expected
                and conditions["checks_off"]["accepted"]
                and conditions["checks_on"]["accepted"] == (not expected)
                and conditions["checks_on"]["error_code"]
                == ("ModelOutputInvalid" if expected else None)
            )
            observations.append(
                {
                    "scenario_id": scenario.id,
                    "variant_id": variant.id,
                    "control": variant.control,
                    "author_semantic_label": variant.semantic_expectation.label,
                    "expected_check_codes": expected,
                    "detector_expectation_matched": scope_matched,
                    **conditions,
                }
            )
    return {
        "pack_id": pack.pack_id,
        "scenarios": len(pack.scenarios),
        "proposals": len(observations),
        "real_api_calls": 0,
        "semantic_quality_measured": False,
        "synthetic_author_labels_only": True,
        "scripted_repetition_is_not_model_repair": True,
        "detector_expectations_matched": sum(
            row["detector_expectation_matched"] for row in observations
        ),
        "observations": observations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", type=Path, default=_DEFAULT_PACK)
    args = parser.parse_args()
    try:
        result = replay_semantic_pack(load_semantic_pack(args.pack))
    except (OSError, ValueError, TypeError, RecursionError, MemoryError):
        print(json.dumps({"error_code": "InvalidSemanticRegressionPack", "real_api_calls": 0}))
        return 1
    print(json.dumps(result, indent=2))
    return int(result["detector_expectations_matched"] != result["proposals"])


if __name__ == "__main__":
    raise SystemExit(main())
