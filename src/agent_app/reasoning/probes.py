"""Development-only fixed-source probes, separate from the final evaluation set."""

import time
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from agent_app.contracts import (
    CaseState,
    Contract,
    EvidenceBundle,
    Identifier,
    ReasoningContext,
    ShortText,
    Text,
)
from agent_app.orchestration import SupportEngine
from agent_app.orchestration.ports import Reasoner, ReasoningStopped
from agent_app.reasoning.output import InvalidAnalysis, parse_analysis
from agent_app.testing.fakes import FakeRetriever


class ProbeExpectations(Contract):
    acceptable_decisions: tuple[Literal["answer", "ask", "escalate"], ...] = Field(
        min_length=1, max_length=3
    )
    allowed_missing_info: tuple[ShortText, ...] = ()
    required_terms: tuple[ShortText, ...] = ()
    forbidden_terms: tuple[ShortText, ...] = ()
    require_evidence: bool
    require_uncertainty: bool
    forbid_repeated_checks: bool


class DecisionProbe(Contract):
    id: Identifier
    kind: Literal["real_report", "controlled_variant", "synthetic"]
    origin_url: str | None
    origin_issue_id: int | None
    origin_created_at: str | None
    description: Text
    case_state: CaseState
    user_message: Text
    bundles: tuple[EvidenceBundle, ...] = Field(min_length=2, max_length=2)
    expectations: ProbeExpectations
    reviewer_notes: tuple[Text, ...]


class ProbeSuite(Contract):
    schema_version: Literal[1]
    snapshot_id: Identifier
    purpose: Text
    docs_commit: Identifier
    source_snapshot_date: ShortText
    reserved_issue_ids: tuple[int, ...]
    cases: tuple[DecisionProbe, ...] = Field(min_length=1, max_length=20)
    family_quarantine_candidates: tuple[dict, ...] = ()

    @model_validator(mode="after")
    def verify_boundaries(self):
        if len({case.id for case in self.cases}) != len(self.cases):
            raise ValueError("Probe IDs must be unique")
        reserved = set(self.reserved_issue_ids)
        for probe in self.cases:
            if probe.origin_issue_id is not None and probe.origin_issue_id not in reserved:
                raise ValueError("A report family must be reserved before model development")
            for bundle in probe.bundles:
                if bundle.snapshot_id != self.snapshot_id or len(bundle.hits) > 5:
                    raise ValueError("Probe evidence must use the fixed snapshot and top_k")
                for hit in bundle.hits:
                    if any(f"/issues/{number}" in hit.source_url for number in reserved):
                        raise ValueError("Reserved report threads cannot be retrieved evidence")
        return self


def load_suite(path: Path) -> ProbeSuite:
    return ProbeSuite.model_validate_json(path.read_text())


class ObservedReasoner:
    """Keep schema/attempt metadata; do not retain invalid raw responses."""

    def __init__(self, delegate: Reasoner):
        self.delegate = delegate
        self.attempts: list[dict] = []
        self.contexts: list[ReasoningContext] = []

    def analyze(self, case, message, evidence, *, context):
        self.contexts.append(context.model_copy(deep=True))
        observation = {"attempt_index": context.attempt_index, "can_refine": context.can_refine}
        self.attempts.append(observation)
        try:
            raw = self.delegate.analyze(case, message, evidence, context=context)
        except ReasoningStopped as error:
            observation.update(schema_valid=False, stop_code=error.code)
            raise
        except Exception:
            observation.update(schema_valid=False, stop_code="ReasoningUnavailable")
            raise
        try:
            analysis = parse_analysis(raw)
            observation.update(schema_valid=True, proposed_decision=analysis.decision)
        except InvalidAnalysis as error:
            observation.update(
                schema_valid=False, output_issues=[issue.model_dump() for issue in error.issues]
            )
        return raw


def run_probe(probe: DecisionProbe, reasoner: Reasoner, *, snapshot_id: str, run_id: str) -> dict:
    probe = DecisionProbe.model_validate(probe.model_dump(warnings=False))
    observed = ObservedReasoner(reasoner)
    retriever = FakeRetriever(probe.bundles)
    started = time.monotonic()
    result = SupportEngine(retriever, observed, snapshot_id=snapshot_id).run(
        probe.case_state, probe.user_message, run_id=run_id
    )
    accepted = result.status == "awaiting_approval"
    decision = result.analysis.decision if result.analysis else None
    return {
        "case_id": probe.id,
        "kind": probe.kind,
        "origin_issue_id": probe.origin_issue_id,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "automatic": {
            "accepted": accepted,
            "first_pass_schema_valid": bool(
                observed.attempts and observed.attempts[0].get("schema_valid")
            ),
            "allowed_final_decision": accepted
            and decision in probe.expectations.acceptable_decisions,
            "model_attempts": result.model_attempts,
            "retrieval_rounds": result.retrieval_rounds,
        },
        "attempts": observed.attempts,
        "contexts": [context.model_dump(mode="json") for context in observed.contexts],
        "queries": [request.queries for request in retriever.requests],
        "result": result.model_dump(mode="json"),
        "semantic_review": None,
    }


def summarize(observations: list[dict]) -> dict:
    """Keep decision agreement distinct from semantic quality and model ranking."""
    groups = {}
    for observation in observations:
        policy = observation["policy"]
        group = groups.setdefault(
            policy,
            {
                "cases": 0,
                "accepted": 0,
                "allowed_final_decisions": 0,
                "first_pass_schema_valid": 0,
                "model_attempts": 0,
                "retrieval_rounds": 0,
            },
        )
        group["cases"] += 1
        values = observation["automatic"]
        group["accepted"] += int(values["accepted"])
        group["allowed_final_decisions"] += int(values["allowed_final_decision"])
        group["first_pass_schema_valid"] += int(values["first_pass_schema_valid"])
        group["model_attempts"] += values["model_attempts"]
        group["retrieval_rounds"] += values["retrieval_rounds"]
    return {
        "automatic_results": groups,
        "semantic_quality": "Requires source-backed review",
        "scope": "Exploratory development probes; not final-test or RAG quality",
    }
