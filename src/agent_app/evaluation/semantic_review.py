"""Content-bound caller judgments, not entailment, authentication or authority.

Sidecars contain exact private output/source annotations. Scores export only
identities, hashes, counts and declared judgments. No model or tool is invoked.
Origins, strata, completeness and reviewer kinds remain caller declarations.
"""

import hashlib
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Annotated, Literal, get_args

from pydantic import ConfigDict, Field, ValidationError, model_validator

from agent_app.contracts import (
    Contract,
    Identifier,
    NonnegativeInt,
    ProposalHandoff,
    ReviewClaimBinding,
    Sha256,
    ShortText,
)
from agent_app.orchestration.handoff import validate_handoff
from agent_app.orchestration.validation import detached_contract
from agent_app.reasoning.review import _surface_texts, review_user_fact_sha256

type Stratum = Literal["answerable", "ambiguous", "needs_escalation"]
type Annotation = Literal["yes", "no", "unassessed", "not_applicable"]
type GateStatus = Literal["pass", "fail", "unassessed", "not_applicable"]
type DecisionJudgment = Literal["acceptable", "unacceptable", "unassessed"]
type ReviewerKind = Literal["human", "assistant"]
type Origin = Literal["model", "maintainer_edit"]
type ReviewCode = Literal[
    "InvalidSemanticReviewInput",
    "ReviewScopeMismatch",
    "UnregisteredStratum",
    "ReviewHandoffMismatch",
    "EditedOriginMismatch",
    "UnknownReviewSurface",
    "OutputSpanMismatch",
    "UnknownReviewSource",
    "SourceQuoteMismatch",
    "InactiveUserFactReference",
    "OverlappingClaimBindings",
    "ClaimCountMismatch",
    "QuestionApplicabilityMismatch",
    "DuplicateProposalReview",
]
Bool = Annotated[bool, Field(strict=True)]
Usefulness = Annotated[int, Field(strict=True, ge=0, le=2)]
Gate = Annotated[int, Field(strict=True, ge=0, le=1)]
Fraction = Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]


class SemanticReviewRejected(ValueError):
    def __init__(self, code: ReviewCode):
        if code not in get_args(ReviewCode.__value__):
            raise ValueError("InvalidSemanticReviewCode")
        self.code = code
        super().__init__(code)


def _need(condition, code: ReviewCode):
    if not condition:
        raise SemanticReviewRejected(code)


class ReviewContract(Contract):
    model_config = ConfigDict(
        extra="forbid", frozen=True, validate_default=True, hide_input_in_errors=True
    )


class ReviewScope(ReviewContract):
    """Expected identity supplied separately by the runner/reviewer caller."""

    run_id: Identifier
    config_id: Identifier
    config_sha256: Sha256
    rubric_id: Identifier
    rubric_sha256: Sha256
    stratum: Stratum
    stratum_registration_sha256: Sha256
    stratum_registered_before_run: Bool


class QuestionJudgment(ReviewContract):
    applies: Bool
    necessary: Annotation
    answerable: Annotation
    not_repeating_known: Annotation
    reason: ShortText = Field(repr=False)

    @model_validator(mode="after")
    def consistent_applicability(self):
        values = (self.necessary, self.answerable, self.not_repeating_known)
        _need(
            all(value != "not_applicable" for value in values)
            if self.applies
            else all(value == "not_applicable" for value in values),
            "QuestionApplicabilityMismatch",
        )
        return self


class SemanticReview(ReviewContract):
    schema_version: Literal[1] = 1
    review_id: Identifier
    scope: ReviewScope
    handoff_sha256: Sha256
    original_handoff_sha256: Sha256 | None = None
    reviewer_id: Identifier
    reviewer_kind: ReviewerKind
    response_origin: Origin
    declared_material_claim_count: Annotated[int, Field(strict=True, ge=0, le=10_000)]
    claim_inventory_complete: Bool
    reviewed_surfaces: tuple[Identifier, ...] = Field(max_length=310)
    claim_bindings: tuple[ReviewClaimBinding, ...] = Field(max_length=310, repr=False)
    decision_judgment: DecisionJudgment
    decision_reason: ShortText = Field(repr=False)
    question: QuestionJudgment
    usefulness_score: Usefulness | None
    usefulness_reason: ShortText = Field(repr=False)

    @model_validator(mode="after")
    def unambiguous_annotations(self):
        _need(
            len(set(self.reviewed_surfaces)) == len(self.reviewed_surfaces), "UnknownReviewSurface"
        )
        _need(self.declared_material_claim_count >= len(self.claim_bindings), "ClaimCountMismatch")
        return self


def _gate(values, *, applies=True):
    if not applies:
        return None, "not_applicable"
    if "no" in values:
        return 0, "fail"
    if all(value == "yes" for value in values):
        return 1, "pass"
    return None, "unassessed"


class ClaimMetrics(ReviewContract):
    total: NonnegativeInt
    reviewed: NonnegativeInt
    supported: NonnegativeInt
    unsupported: NonnegativeInt
    insufficient: NonnegativeInt
    unreviewed: NonnegativeInt
    review_coverage: Fraction | None
    supported_fraction: Fraction | None

    @model_validator(mode="after")
    def consistent_counts(self):
        _need(
            self.reviewed == self.supported + self.unsupported + self.insufficient
            and self.total == self.reviewed + self.unreviewed,
            "InvalidSemanticReviewInput",
        )
        expected = (
            (self.reviewed / self.total, self.supported / self.total)
            if self.total
            else (None, None)
        )
        _need(
            (self.review_coverage, self.supported_fraction) == expected,
            "InvalidSemanticReviewInput",
        )
        return self


def _support(claims, complete):
    if claims.unsupported:
        return 0, "fail"
    if not complete or claims.insufficient or claims.unreviewed:
        return None, "unassessed"
    if not claims.total:
        return None, "not_applicable"
    return 1, "pass"


class ReviewScore(ReviewContract):
    """Derived counters only; declared human/assistant groups never authenticate."""

    review_id: Identifier
    scope: ReviewScope
    review_sha256: Sha256
    proposal_id: Identifier
    case_id: Identifier
    case_revision: NonnegativeInt
    handoff_sha256: Sha256
    original_handoff_sha256: Sha256 | None
    reviewer_kind: ReviewerKind
    response_origin: Origin
    actual_decision: Literal["answer", "ask", "escalate"]
    decision_judgment: DecisionJudgment
    claims: ClaimMetrics
    surface_count: Annotated[int, Field(strict=True, ge=1, le=310)]
    reviewed_surface_count: NonnegativeInt
    complete_review: Bool
    support_gate: Gate | None
    support_status: GateStatus
    question_applies: Bool
    question_annotations: tuple[Annotation, Annotation, Annotation]
    question_gate: Gate | None
    question_status: GateStatus
    usefulness_score: Usefulness | None
    quality_claim: Literal[False] = False
    authorizes_action: Literal[False] = False

    @model_validator(mode="after")
    def consistent_derived_gates(self):
        _need(self.scope.stratum_registered_before_run, "InvalidSemanticReviewInput")
        _need(
            all(value != "not_applicable" for value in self.question_annotations)
            if self.question_applies
            else all(value == "not_applicable" for value in self.question_annotations),
            "InvalidSemanticReviewInput",
        )
        _need(self.actual_decision != "ask" or self.question_applies, "InvalidSemanticReviewInput")
        _need(self.reviewed_surface_count <= self.surface_count, "InvalidSemanticReviewInput")
        _need(
            not self.complete_review or self.reviewed_surface_count == self.surface_count,
            "InvalidSemanticReviewInput",
        )
        _need(
            (self.support_gate, self.support_status) == _support(self.claims, self.complete_review),
            "InvalidSemanticReviewInput",
        )
        _need(
            (self.question_gate, self.question_status)
            == _gate(self.question_annotations, applies=self.question_applies),
            "InvalidSemanticReviewInput",
        )
        _need(
            (self.response_origin == "maintainer_edit")
            == (self.original_handoff_sha256 is not None),
            "InvalidSemanticReviewInput",
        )
        return self


def _parse(model, value):
    parsed = value if isinstance(value, model) else model.model_validate(value)
    return detached_contract(model, parsed)


def score_review(
    handoff: ProposalHandoff,
    sidecar: SemanticReview | Mapping,
    *,
    scope: ReviewScope,
    original_handoff: ProposalHandoff | None = None,
) -> ReviewScore:
    """Validate exact annotations; never discover claims or judge entailment."""
    try:
        handoff = validate_handoff(handoff)
        review, expected = _parse(SemanticReview, sidecar), _parse(ReviewScope, scope)
        original = validate_handoff(original_handoff) if original_handoff is not None else None
    except (ValidationError, ValueError, TypeError, AttributeError, RecursionError):
        raise SemanticReviewRejected("InvalidSemanticReviewInput") from None
    _need(review.scope == expected, "ReviewScopeMismatch")
    _need(expected.stratum_registered_before_run, "UnregisteredStratum")
    _need(review.handoff_sha256 == handoff.handoff_sha256, "ReviewHandoffMismatch")
    if review.response_origin == "maintainer_edit":
        _need(
            original is not None
            and review.original_handoff_sha256 == original.handoff_sha256
            and original.handoff_sha256 != handoff.handoff_sha256
            and original.proposal_id != handoff.proposal_id
            and original.case == handoff.case
            and original.evidence == handoff.evidence
            and original.user_message == handoff.user_message
            and original.reasoning_context == handoff.reasoning_context,
            "EditedOriginMismatch",
        )
    else:
        _need(original is None and review.original_handoff_sha256 is None, "EditedOriginMismatch")
    surfaces = _surface_texts(handoff.analysis)
    _need(set(review.reviewed_surfaces) <= set(surfaces), "UnknownReviewSurface")
    hits = {hit.chunk_id: hit for hit in handoff.evidence.hits}
    active = {
        review_user_fact_sha256(f)
        for f in handoff.case.facts
        if f.status == "active" and f.provenance_kind == "user"
    }
    intervals = {}
    for binding in review.claim_bindings:
        span = binding.output
        _need(
            span.surface_id in surfaces and span.surface_id in review.reviewed_surfaces,
            "UnknownReviewSurface",
        )
        _need(surfaces[span.surface_id][span.start : span.end] == span.text, "OutputSpanMismatch")
        for start, end in intervals.setdefault(span.surface_id, []):
            _need(span.end <= start or span.start >= end, "OverlappingClaimBindings")
        intervals[span.surface_id].append((span.start, span.end))
        if binding.source_quote is not None:
            quote = binding.source_quote
            _need(quote.chunk_id in hits, "UnknownReviewSource")
            _need(
                hits[quote.chunk_id].excerpt[quote.start : quote.end] == quote.quote,
                "SourceQuoteMismatch",
            )
        if binding.user_fact_sha256 is not None:
            _need(binding.user_fact_sha256 in active, "InactiveUserFactReference")
    requires_question = (
        handoff.analysis.decision == "ask"
        or handoff.analysis.next_question is not None
        or bool(handoff.analysis.checks_suggested)
    )
    _need(not requires_question or review.question.applies, "QuestionApplicabilityMismatch")
    count = Counter(binding.judgment for binding in review.claim_bindings)
    total, reviewed = review.declared_material_claim_count, len(review.claim_bindings)
    claims = ClaimMetrics(
        total=total,
        reviewed=reviewed,
        supported=count["supported"],
        unsupported=count["unsupported"],
        insufficient=count["insufficient"],
        unreviewed=total - reviewed,
        review_coverage=reviewed / total if total else None,
        supported_fraction=count["supported"] / total if total else None,
    )
    complete = review.claim_inventory_complete and set(review.reviewed_surfaces) == set(surfaces)
    support_gate, support_status = _support(claims, complete)
    annotations = (
        review.question.necessary,
        review.question.answerable,
        review.question.not_repeating_known,
    )
    question_gate, question_status = _gate(annotations, applies=review.question.applies)
    digest = hashlib.sha256(("semantic-review-v1:" + review.model_dump_json()).encode()).hexdigest()
    return ReviewScore(
        review_id=review.review_id,
        scope=review.scope,
        review_sha256=digest,
        proposal_id=handoff.proposal_id,
        case_id=handoff.case.case_id,
        case_revision=handoff.case.case_revision,
        handoff_sha256=handoff.handoff_sha256,
        original_handoff_sha256=review.original_handoff_sha256,
        reviewer_kind=review.reviewer_kind,
        response_origin=review.response_origin,
        actual_decision=handoff.analysis.decision,
        decision_judgment=review.decision_judgment,
        claims=claims,
        surface_count=len(surfaces),
        reviewed_surface_count=len(review.reviewed_surfaces),
        complete_review=complete,
        support_gate=support_gate,
        support_status=support_status,
        question_applies=review.question.applies,
        question_annotations=annotations,
        question_gate=question_gate,
        question_status=question_status,
        usefulness_score=review.usefulness_score,
    )


def _summary(rows):
    decisions = Counter(row.decision_judgment for row in rows)
    support = Counter(row.support_status for row in rows)
    questions = Counter(row.question_status for row in rows)
    decision_denominator = decisions["acceptable"] + decisions["unacceptable"]
    support_denominator = support["pass"] + support["fail"]
    totals = {
        name: sum(getattr(row.claims, name) for row in rows)
        for name in ("total", "reviewed", "supported", "unsupported", "insufficient", "unreviewed")
    }
    question_denominator = questions["pass"] + questions["fail"]
    return {
        "proposals": len(rows),
        "cases": len({row.case_id for row in rows}),
        "decision_judgments": {
            name: decisions[name] for name in ("acceptable", "unacceptable", "unassessed")
        },
        "actual_decisions": {
            name: sum(row.actual_decision == name for row in rows)
            for name in ("answer", "ask", "escalate")
        },
        "decision_judged_denominator": decision_denominator,
        "declared_decision_acceptance_fraction": decisions["acceptable"] / decision_denominator
        if decision_denominator
        else None,
        "support_statuses": {
            name: support[name] for name in ("pass", "fail", "unassessed", "not_applicable")
        },
        "support_judged_denominator": support_denominator,
        "declared_support_pass_fraction": support["pass"] / support_denominator
        if support_denominator
        else None,
        "material_claims": sum(row.claims.total for row in rows),
        "unreviewed_claims": sum(row.claims.unreviewed for row in rows),
        "claim_counts": totals,
        "claim_review_coverage": totals["reviewed"] / totals["total"] if totals["total"] else None,
        "declared_supported_claim_fraction": totals["supported"] / totals["total"]
        if totals["total"]
        else None,
        "question_statuses": {
            name: questions[name] for name in ("pass", "fail", "unassessed", "not_applicable")
        },
        "question_judged_denominator": question_denominator,
        "declared_question_pass_fraction": questions["pass"] / question_denominator
        if question_denominator
        else None,
        "declared_usefulness_distribution": {
            str(score): sum(row.usefulness_score == score for row in rows) for score in (0, 1, 2)
        },
        "usefulness_unassessed": sum(row.usefulness_score is None for row in rows),
    }


def aggregate_reviews(scores: Sequence[ReviewScore]) -> dict:
    """Separate configurations/rubrics/reviewer kinds/origins; never blend edits."""
    try:
        rows = [_parse(ReviewScore, score) for score in scores]
    except (ValidationError, ValueError, TypeError, AttributeError, RecursionError):
        raise SemanticReviewRejected("InvalidSemanticReviewInput") from None
    groups, seen = {}, set()
    for row in rows:
        scope = row.scope
        key = (
            scope.run_id,
            scope.config_id,
            scope.config_sha256,
            scope.rubric_id,
            scope.rubric_sha256,
            row.reviewer_kind,
            row.response_origin,
        )
        duplicate = key + (row.proposal_id,)
        _need(duplicate not in seen, "DuplicateProposalReview")
        seen.add(duplicate)
        groups.setdefault(key, []).append(row)
    return {
        "quality_claim": False,
        "authorizes_action": False,
        "judgments_only": True,
        "groups": [
            {
                "run_id": key[0],
                "config_id": key[1],
                "config_sha256": key[2],
                "rubric_id": key[3],
                "rubric_sha256": key[4],
                "reviewer_kind": key[5],
                "response_origin": key[6],
                "proposal_count": len(rows),
                "by_stratum": {
                    stratum: _summary([row for row in rows if row.scope.stratum == stratum])
                    for stratum in ("answerable", "ambiguous", "needs_escalation")
                },
            }
            for key, rows in sorted(groups.items())
        ],
    }
