"""Validated v1 boundary types for the offline agent core.

These objects carry data and proposed responses. They never grant permission to
change a case. The tracker owns revisions, approvals, and durable persistence.
"""

from __future__ import annotations

from typing import Annotated, Literal, Self
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError

__all__ = [
    "Decision",
    "EvidenceHit",
    "EvidenceBundle",
    "Fact",
    "CaseState",
    "ReportedFact",
    "UserTurn",
    "CaseTransition",
    "RetrievalRequest",
    "EvidenceLink",
    "AnalysisResult",
    "ApprovedReplyQuestion",
    "RunLimits",
    "QuestionTarget",
    "ProposalRequirements",
    "ReasoningContext",
    "OutputIssue",
    "OutputFeedback",
    "RunResult",
    "TraceEvent",
    "GroundedGap",
    "GroundedSourceRef",
    "GroundedRequest",
    "GroundedPlan",
    "ReviewSurface",
    "ReviewOutputSpan",
    "ReviewSourceQuote",
    "ReviewClaimBinding",
    "ReviewDimension",
    "ProposalReviewPacket",
    "ReviewAttestation",
    "ProposalReviewResult",
    "SourceReviewEntry",
    "ProposalHandoff",
    "ConversationEntry",
    "TurnConversation",
    "TrackerTurnReceipt",
    "TrackerCaseView",
    "TrackerStageReceipt",
]


Decision = Literal["answer", "ask", "escalate", "retrieve_more"]
Identifier = Annotated[
    str,
    StringConstraints(
        strict=True,
        strip_whitespace=True,
        min_length=1,
        max_length=200,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$",
    ),
]
ShortText = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=500)
]
Text = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=20_000)
]
Query = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=500)
]
NonnegativeInt = Annotated[int, Field(strict=True, ge=0)]
PositiveInt = Annotated[int, Field(strict=True, gt=0)]


class Contract(BaseModel):
    """Reject unknown fields and preserve immutable snapshots at boundaries."""

    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


def _unique_text(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    if len({value.casefold() for value in values}) != len(values):
        raise ValueError(f"{field_name} must not contain duplicates")
    return values


class EvidenceHit(Contract):
    chunk_id: Identifier
    source_id: Identifier
    excerpt: Text
    source_url: Annotated[str, StringConstraints(strict=True, max_length=2_000)]
    source_type: Literal["issue", "comment", "doc", "release_note"]
    source_commit: Identifier | None = None
    applicable_versions: tuple[ShortText, ...] = ()
    source_span: ShortText | None = None
    score: Annotated[float, Field(strict=True, allow_inf_nan=False)] | None = None
    score_kind: ShortText | None = None

    @field_validator("source_url")
    @classmethod
    def source_url_is_web_link(cls, value: str) -> str:
        try:
            parsed = urlsplit(value)
            valid = parsed.scheme in {"http", "https"} and bool(parsed.hostname)
            valid = valid and parsed.username is None and parsed.password is None
            # Accessing port also rejects malformed port strings.
            _ = parsed.port
        except ValueError:
            valid = False
        if not valid or any(character.isspace() for character in value):
            raise ValueError("source_url must be an absolute HTTP(S) URL")
        return value

    @field_validator("applicable_versions")
    @classmethod
    def unique_versions(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _unique_text(values, "applicable_versions")


class EvidenceBundle(Contract):
    snapshot_id: Identifier
    hits: tuple[EvidenceHit, ...] = Field(default=(), max_length=100)
    queries_used: tuple[Query, ...] = Field(default=(), max_length=20)
    retrieval_round: PositiveInt = 1
    warnings: tuple[ShortText, ...] = Field(default=(), max_length=50)

    @field_validator("hits")
    @classmethod
    def unique_chunks(cls, hits: tuple[EvidenceHit, ...]) -> tuple[EvidenceHit, ...]:
        if len({hit.chunk_id for hit in hits}) != len(hits):
            raise ValueError("hits must have unique chunk_id values")
        return hits


class Fact(Contract):
    name: ShortText
    value: Text
    source_ref: Identifier
    turn_id: Identifier
    provenance_kind: Literal["user", "evidence"] = "user"
    status: Literal["active", "superseded"] = "active"


def _unique_active_facts(facts: tuple[Fact, ...]) -> tuple[Fact, ...]:
    active_names = [fact.name.casefold() for fact in facts if fact.status == "active"]
    if len(set(active_names)) != len(active_names):
        raise ValueError("only one active fact is allowed per name")
    return facts


class CaseState(Contract):
    case_id: Identifier
    case_revision: NonnegativeInt = 0
    facts: tuple[Fact, ...] = Field(default=(), max_length=200)
    unknowns: tuple[ShortText, ...] = Field(default=(), max_length=100)
    checks_performed: tuple[Text, ...] = Field(default=(), max_length=100)
    evidence_refs: tuple[Identifier, ...] = Field(default=(), max_length=200)
    pending_proposal_id: Identifier | None = None

    @field_validator("facts")
    @classmethod
    def unique_active_facts(cls, facts: tuple[Fact, ...]) -> tuple[Fact, ...]:
        return _unique_active_facts(facts)

    @field_validator("unknowns")
    @classmethod
    def unique_items(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _unique_text(values, "unknowns")

    @field_validator("evidence_refs")
    @classmethod
    def unique_evidence_refs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(values)) != len(values):
            raise ValueError("evidence_refs must not contain duplicates")
        return values


class ReportedFact(Contract):
    """A caller-attributed user statement; None explicitly withdraws a fact."""

    name: ShortText
    value: Text | None


class UserTurn(Contract):
    """Structured input from the user, never inferred from a model's response."""

    case_id: Identifier
    expected_revision: NonnegativeInt
    turn_id: Identifier
    source_ref: Identifier
    message: Text
    reported_facts: tuple[ReportedFact, ...] = Field(default=(), max_length=50)
    unknowns: tuple[ShortText, ...] = Field(default=(), max_length=100)
    checks_performed: tuple[Text, ...] = Field(default=(), max_length=100)
    context_changed: Annotated[bool, Field(strict=True)] = False

    @field_validator("reported_facts")
    @classmethod
    def unique_fact_names(cls, values: tuple[ReportedFact, ...]) -> tuple[ReportedFact, ...]:
        if len({value.name.casefold() for value in values}) != len(values):
            raise ValueError("reported_facts must have unique names")
        return values

    @field_validator("unknowns")
    @classmethod
    def unique_unknowns(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _unique_text(values, "unknowns")

    @field_validator("checks_performed")
    @classmethod
    def unique_checks(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len({" ".join(value.split()).casefold() for value in values}) != len(values):
            raise ValueError("checks_performed must not contain equivalent checks")
        return values


class CaseTransition(Contract):
    """An uncommitted candidate; only the tracker can accept and persist it."""

    expected_revision: NonnegativeInt
    turn_id: Identifier
    source_ref: Identifier
    event_hash: Annotated[str, StringConstraints(strict=True, pattern=r"^[a-f0-9]{64}$")]
    candidate: CaseState
    changed_fact_names: tuple[ShortText, ...] = Field(default=(), max_length=250)
    context_changed: Annotated[bool, Field(strict=True)]
    invalidated_checks: tuple[Text, ...] = Field(default=(), max_length=100)

    @field_validator("changed_fact_names")
    @classmethod
    def unique_changed_names(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _unique_text(values, "changed_fact_names")

    @model_validator(mode="after")
    def candidate_is_unapproved_next_revision(self) -> Self:
        if self.candidate.case_revision != self.expected_revision + 1:
            raise ValueError("candidate must advance exactly one revision")
        if self.candidate.pending_proposal_id is not None:
            raise ValueError("a new user turn must invalidate the pending proposal")
        return self


class RetrievalRequest(Contract):
    queries: tuple[Query, ...] = Field(min_length=1, max_length=2)
    snapshot_id: Identifier
    top_k: Annotated[int, Field(strict=True, ge=1, le=50)] = 5
    filters: dict[ShortText, ShortText | tuple[ShortText, ...]] = Field(default_factory=dict)

    @field_validator("queries")
    @classmethod
    def unique_queries(cls, queries: tuple[str, ...]) -> tuple[str, ...]:
        return _unique_text(queries, "queries")


class EvidenceLink(Contract):
    claim: Text
    chunk_id: Identifier


class AnalysisResult(Contract):
    decision: Decision
    user_draft: Annotated[
        str, StringConstraints(strict=True, strip_whitespace=True, max_length=20_000)
    ]
    maintainer_summary: Annotated[
        str, StringConstraints(strict=True, strip_whitespace=True, max_length=20_000)
    ]
    rationale: Annotated[
        str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=2_000)
    ]
    evidence_links: tuple[EvidenceLink, ...] = Field(default=(), max_length=100)
    missing_info: tuple[ShortText, ...] = Field(default=(), max_length=50)
    next_question: Text | None = None
    retrieval_queries: tuple[Query, ...] = Field(default=(), max_length=2)
    facts_delta: tuple[Fact, ...] = Field(default=(), max_length=100)
    checks_suggested: tuple[Text, ...] = Field(default=(), max_length=50)

    @field_validator("evidence_links")
    @classmethod
    def unique_links(cls, links: tuple[EvidenceLink, ...]) -> tuple[EvidenceLink, ...]:
        if len({(link.claim, link.chunk_id) for link in links}) != len(links):
            raise ValueError("evidence_links must not contain duplicate claim/chunk pairs")
        return links

    @field_validator("retrieval_queries", "missing_info", "checks_suggested")
    @classmethod
    def unique_items(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _unique_text(values, "analysis fields")

    @field_validator("facts_delta")
    @classmethod
    def unique_active_facts(cls, facts: tuple[Fact, ...]) -> tuple[Fact, ...]:
        return _unique_active_facts(facts)

    @model_validator(mode="after")
    def decision_has_required_payload(self) -> Self:
        if self.decision == "retrieve_more":
            if not self.retrieval_queries:
                raise PydanticCustomError(
                    "retrieve_more_queries_required", "retrieve_more requires retrieval_queries"
                )
            if self.user_draft or self.maintainer_summary or self.next_question is not None:
                raise PydanticCustomError(
                    "retrieve_more_final_payload_forbidden",
                    "retrieve_more must not contain a final draft or next_question",
                )
        else:
            if not self.user_draft or not self.maintainer_summary:
                raise PydanticCustomError(
                    "final_drafts_required",
                    "a final decision requires user_draft and maintainer_summary",
                )
            if self.retrieval_queries:
                raise PydanticCustomError(
                    "final_queries_forbidden", "only retrieve_more may request retrieval_queries"
                )

        if self.decision == "ask" and self.next_question is None:
            raise PydanticCustomError("ask_question_required", "ask requires next_question")
        if self.decision != "ask" and self.next_question is not None:
            raise PydanticCustomError("question_forbidden", "only ask may contain next_question")
        return self


class ApprovedReplyQuestion(Contract):
    """Caller-loaded approved question, bound to one exact case revision.

    This immutable payload is not proof of approval or authentication. The
    tracker must supply its authoritative approved record and invalidate it
    when a new turn or proposal replaces the question.
    """

    case_id: Identifier
    case_revision: NonnegativeInt
    proposal_id: Identifier
    question: AnalysisResult


class RunLimits(Contract):
    max_model_attempts: Annotated[int, Field(strict=True, ge=1, le=2)] = 2
    max_retrieval_rounds: Annotated[int, Field(strict=True, ge=1, le=2)] = 2
    max_queries_per_round: Annotated[int, Field(strict=True, ge=1, le=2)] = 2
    max_steps: Annotated[int, Field(strict=True, ge=1, le=8)] = 8


class QuestionTarget(Contract):
    """A caller-approved clarification, never inferred from a source instruction."""

    name: ShortText
    question: Text


class ProposalRequirements(Contract):
    """Optional caller intent bound to one immutable case revision.

    An empty question catalog registers no clarification; it does not prove that
    all user information is known. These constraints grant no action authority.
    """

    case_id: Identifier
    case_revision: NonnegativeInt
    question_targets: tuple[QuestionTarget, ...] = Field(default=(), max_length=8)
    require_fresh_widget_value: Annotated[bool, Field(strict=True)] = False

    @field_validator("question_targets")
    @classmethod
    def unique_questions(cls, targets: tuple[QuestionTarget, ...]) -> tuple[QuestionTarget, ...]:
        targets = tuple(
            QuestionTarget.model_validate(target.model_dump(warnings=False)) for target in targets
        )
        if len({target.name.casefold() for target in targets}) != len(targets):
            raise ValueError("question_targets must have unique names")
        if len({" ".join(target.question.split()).casefold() for target in targets}) != len(
            targets
        ):
            raise ValueError("question_targets must have distinct questions")
        return targets


class OutputIssue(Contract):
    """Allowlisted validation metadata; no model values or arbitrary field paths."""

    code: Literal[
        "invalid_json",
        "duplicate_field",
        "invalid_shape",
        "output_too_large",
        "missing_field",
        "unknown_field",
        "invalid_field",
        "invalid_python_syntax",
        "ask_target_required",
        "ask_unregistered_target",
        "ask_question_mismatch",
        "invalid_api_keyword",
        "callback_value_captured",
        "callback_arity_mismatch",
        "retrieve_more_queries_required",
        "retrieve_more_final_payload_forbidden",
        "final_drafts_required",
        "final_queries_forbidden",
        "ask_question_required",
        "question_forbidden",
        "invalid_grounded_plan",
        "grounded_context_mismatch",
        "grounded_source_mismatch",
        "grounded_question_invalid",
        "grounded_conflict_unresolved",
        "grounded_render_too_large",
    ]
    field: (
        Literal[
            "decision",
            "user_draft",
            "maintainer_summary",
            "rationale",
            "evidence_links",
            "missing_info",
            "next_question",
            "retrieval_queries",
            "facts_delta",
            "checks_suggested",
        ]
        | None
    ) = None


class OutputFeedback(Contract):
    issues: tuple[OutputIssue, ...] = Field(min_length=1, max_length=8)


class ReasoningContext(Contract):
    """Caller-owned attribution for one attempt, never supplied by model output."""

    run_id: Identifier
    case_id: Identifier
    case_revision: NonnegativeInt
    attempt_index: Annotated[int, Field(strict=True, ge=1, le=2)]
    output_feedback: OutputFeedback | None = None
    remaining_model_attempts: Annotated[int, Field(strict=True, ge=0, le=1)] = 0
    remaining_retrieval_rounds: Annotated[int, Field(strict=True, ge=0, le=1)] = 0
    can_refine: Annotated[bool, Field(strict=True)] = False
    query_limit: Annotated[int, Field(strict=True, ge=1, le=2)] = 2
    proposal_requirements: ProposalRequirements | None = None

    @model_validator(mode="after")
    def feedback_is_only_for_repair(self) -> Self:
        if self.output_feedback is not None and self.attempt_index != 2:
            raise ValueError("output feedback belongs only to the second attempt")
        if self.remaining_model_attempts > 2 - self.attempt_index:
            raise ValueError("remaining model attempts exceed the hard allowance")
        if self.can_refine and not (
            self.remaining_model_attempts and self.remaining_retrieval_rounds
        ):
            raise ValueError("refinement requires remaining analysis and retrieval capacity")
        if self.proposal_requirements is not None:
            requirements = ProposalRequirements.model_validate(
                self.proposal_requirements.model_dump(warnings=False)
            )
            if (
                requirements.case_id != self.case_id
                or requirements.case_revision != self.case_revision
            ):
                raise ValueError("proposal requirements do not match the reasoning context")
        return self


class TraceEvent(Contract):
    """A short operational event; hidden model reasoning is not part of the API."""

    stage: ShortText
    message: Annotated[
        str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=2_000)
    ]


class RunResult(Contract):
    run_id: Identifier
    case_id: Identifier
    case_revision: NonnegativeInt
    status: Literal["awaiting_approval", "error", "stale", "budget_stopped"]
    analysis: AnalysisResult | None = None
    model_attempts: NonnegativeInt = 0
    retrieval_rounds: NonnegativeInt = 0
    steps: NonnegativeInt = 0
    error_code: Identifier | None = None
    trace: tuple[TraceEvent, ...] = Field(default=(), max_length=200)
    output_issues: tuple[OutputIssue, ...] = Field(default=(), max_length=16)

    @model_validator(mode="after")
    def status_matches_payload(self) -> Self:
        if self.status == "awaiting_approval":
            if self.analysis is None or self.analysis.decision == "retrieve_more":
                raise ValueError("awaiting_approval requires a final analysis")
            if self.error_code is not None:
                raise ValueError("awaiting_approval must not contain error_code")
        elif self.analysis is not None:
            raise ValueError("a stopped or failed run must not expose a final analysis")
        return self


Sha256 = Annotated[
    str, StringConstraints(strict=True, pattern=r"^[a-f0-9]{64}$", min_length=64, max_length=64)
]


class GroundedGap(Contract):
    """Caller-described missing input; it never authorizes an action."""

    name: Identifier
    kind: Literal["user", "source"]
    description: ShortText
    necessity: ShortText
    question: Text | None = None

    @model_validator(mode="after")
    def question_matches_kind(self) -> Self:
        if self.kind == "user" and self.question is None:
            raise ValueError("a user gap requires a question")
        if self.kind == "source" and self.question is not None:
            raise ValueError("a source gap cannot contain a user question")
        return self


class GroundedSourceRef(Contract):
    chunk_id: Identifier
    content_sha256: Sha256


class GroundedRequest(Contract):
    """Bounded extractive input; cross-object freshness belongs to its helper."""

    case: CaseState
    user_message: Text
    evidence: EvidenceBundle
    gaps: tuple[GroundedGap, ...] = Field(default=(), max_length=8)
    conflict_groups: tuple[tuple[Identifier, ...], ...] = Field(default=(), max_length=8)
    context_sha256: Sha256

    @field_validator("gaps")
    @classmethod
    def unique_gaps(cls, gaps: tuple[GroundedGap, ...]) -> tuple[GroundedGap, ...]:
        if len({gap.name.casefold() for gap in gaps}) != len(gaps):
            raise ValueError("gap names must be unique")
        return gaps

    @field_validator("conflict_groups")
    @classmethod
    def valid_conflict_groups(
        cls, groups: tuple[tuple[str, ...], ...]
    ) -> tuple[tuple[str, ...], ...]:
        if any(len(group) < 2 or len(set(group)) != len(group) for group in groups):
            raise ValueError("conflict groups require at least two distinct chunk IDs")
        if len({frozenset(group) for group in groups}) != len(groups):
            raise ValueError("conflict groups must be distinct")
        return groups


class GroundedPlan(Contract):
    """A restricted decision plan, without generated technical prose."""

    context_sha256: Sha256
    decision: Decision
    sources: tuple[GroundedSourceRef, ...] = Field(default=(), max_length=8)
    question_name: Identifier | None = None
    retrieval_queries: tuple[Query, ...] = Field(default=(), max_length=2)

    @field_validator("sources")
    @classmethod
    def unique_source_refs(
        cls, sources: tuple[GroundedSourceRef, ...]
    ) -> tuple[GroundedSourceRef, ...]:
        if len({source.chunk_id for source in sources}) != len(sources):
            raise ValueError("grounded source IDs must be unique")
        return sources

    @field_validator("retrieval_queries")
    @classmethod
    def unique_queries(cls, queries: tuple[str, ...]) -> tuple[str, ...]:
        return _unique_text(queries, "retrieval_queries")

    @model_validator(mode="after")
    def decision_matches_plan(self) -> Self:
        if self.decision == "retrieve_more":
            if not self.retrieval_queries or self.question_name is not None or self.sources:
                raise ValueError("retrieve_more requires only queries")
        else:
            if self.retrieval_queries:
                raise ValueError("only retrieve_more can contain queries")
            if self.decision == "ask":
                if self.question_name is None:
                    raise ValueError("ask requires a question name")
            elif self.question_name is not None:
                raise ValueError("only ask can contain a question name")
            if self.decision == "answer" and not self.sources:
                raise ValueError("answer requires a source")
        return self


ReviewExactText = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=22_000)]
ReviewDimensionName = Literal[
    "claim_support",
    "version_applicability",
    "fact_fidelity",
    "question_utility",
    "conflict_handling",
    "uncertainty",
]


class ReviewSurface(Contract):
    """Inventory of a complete output surface; text remains in its original object."""

    surface_id: Identifier
    text_sha256: Sha256
    # A valid 20k Fact.value plus 500-char name can expand sixfold in
    # canonical JSON. This inventories content; it does not retain that text.
    length: Annotated[int, Field(strict=True, ge=1, le=125_000)]


class ReviewOutputSpan(Contract):
    surface_id: Identifier
    start: NonnegativeInt
    end: PositiveInt
    text: ReviewExactText

    @model_validator(mode="after")
    def span_matches_text_length(self) -> Self:
        if self.end <= self.start or self.end - self.start != len(self.text):
            raise ValueError("output span must match its exact text length")
        return self


class ReviewSourceQuote(Contract):
    chunk_id: Identifier
    start: NonnegativeInt
    end: PositiveInt
    quote: ReviewExactText

    @model_validator(mode="after")
    def span_matches_quote_length(self) -> Self:
        if self.end <= self.start or self.end - self.start != len(self.quote):
            raise ValueError("source span must match its exact quote length")
        return self


class ReviewClaimBinding(Contract):
    """A reviewer's judgment, not machine proof of semantic entailment."""

    output: ReviewOutputSpan
    judgment: Literal["supported", "unsupported", "insufficient"]
    applicability: Literal["current", "historical", "unknown"]
    source_quote: ReviewSourceQuote | None = None
    user_fact_sha256: Sha256 | None = None

    @model_validator(mode="after")
    def binding_has_one_reference(self) -> Self:
        if self.source_quote is not None and self.user_fact_sha256 is not None:
            raise ValueError("a claim binding selects at most one reference")
        if (
            self.judgment == "supported"
            and self.source_quote is None
            and self.user_fact_sha256 is None
        ):
            raise ValueError("a supported claim binding requires a reference")
        return self


class ReviewDimension(Contract):
    name: ReviewDimensionName
    passed: Annotated[bool, Field(strict=True)]


class ProposalReviewPacket(Contract):
    """Content binding only; this packet never grants approval or execution authority."""

    schema_version: Literal[1] = 1
    case_id: Identifier
    case_revision: NonnegativeInt
    case_sha256: Sha256
    evidence_sha256: Sha256
    analysis_sha256: Sha256
    surfaces: tuple[ReviewSurface, ...] = Field(min_length=1, max_length=310)
    packet_sha256: Sha256

    @field_validator("surfaces")
    @classmethod
    def unique_surfaces(cls, surfaces: tuple[ReviewSurface, ...]) -> tuple[ReviewSurface, ...]:
        if len({surface.surface_id for surface in surfaces}) != len(surfaces):
            raise ValueError("review surfaces must be unique")
        return surfaces


class ReviewAttestation(Contract):
    """Caller-provided review record; the caller must authenticate reviewer provenance."""

    reviewer_id: Identifier
    packet_sha256: Sha256
    disposition: Literal["approved", "needs_revision"]
    reviewed_surfaces: tuple[Identifier, ...] = Field(default=(), max_length=310)
    dimensions: tuple[ReviewDimension, ...] = Field(default=(), max_length=6)
    claim_bindings: tuple[ReviewClaimBinding, ...] = Field(default=(), max_length=310)

    @field_validator("reviewed_surfaces")
    @classmethod
    def unique_reviewed_surfaces(cls, surfaces: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(surfaces)) != len(surfaces):
            raise ValueError("reviewed surfaces must be unique")
        return surfaces

    @field_validator("dimensions")
    @classmethod
    def unique_dimensions(
        cls, dimensions: tuple[ReviewDimension, ...]
    ) -> tuple[ReviewDimension, ...]:
        if len({dimension.name for dimension in dimensions}) != len(dimensions):
            raise ValueError("review dimensions must be unique")
        return dimensions


class ProposalReviewResult(Contract):
    """Review usability only; passing does not execute or approve a tracker action."""

    status: Literal["pass", "needs_review"]
    codes: tuple[
        Literal[
            "InvalidReviewInput",
            "FinalProposalRequired",
            "ReviewPacketMismatch",
            "UnauthenticatedReviewer",
            "ReviewerMismatch",
            "AttestationPacketMismatch",
            "IncompleteSurfaceReview",
            "UnknownReviewSurface",
            "IncompleteDimensionReview",
            "ReviewDimensionFailed",
            "ReviewNeedsRevision",
            "OutputSpanMismatch",
            "UnknownReviewSource",
            "SourceQuoteMismatch",
            "InactiveUserFactReference",
            "CurrentVersionApplicabilityUnconfirmed",
            "ClaimNeedsRevision",
        ],
        ...,
    ] = Field(default=(), max_length=18)

    @model_validator(mode="after")
    def status_matches_codes(self) -> Self:
        if (self.status == "pass") != (not self.codes):
            raise ValueError("a pass requires no review failure codes")
        if len(set(self.codes)) != len(self.codes):
            raise ValueError("review failure codes must be unique")
        return self


class SourceReviewEntry(Contract):
    """Inventory of supplied source bytes and version metadata, never source truth."""

    chunk_id: Identifier
    content_sha256: Sha256
    version_scope: Literal["unconfirmed", "exact_metadata_match", "historical_or_other_version"]


class ProposalHandoff(Contract):
    """Complete content for review; integrity grants no action or approval authority."""

    schema_version: Literal[1] = 1
    proposal_id: Identifier
    case: CaseState
    user_message: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=20_000)]
    evidence: EvidenceBundle
    analysis: AnalysisResult
    reasoning_context: ReasoningContext
    grounded_request: GroundedRequest | None = None
    source_inventory: tuple[SourceReviewEntry, ...] = Field(default=(), max_length=100)
    packet: ProposalReviewPacket
    handoff_sha256: Sha256

    @field_validator("user_message")
    @classmethod
    def user_message_is_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("user message must be nonblank")
        return value

    @field_validator("source_inventory")
    @classmethod
    def unique_sources(
        cls, entries: tuple[SourceReviewEntry, ...]
    ) -> tuple[SourceReviewEntry, ...]:
        if len({entry.chunk_id for entry in entries}) != len(entries):
            raise ValueError("source inventory must have unique chunk IDs")
        return entries


class ConversationEntry(Contract):
    """One caller-loaded persisted message; its text is untrusted context."""

    actor: Literal["user", "assistant"]
    reference_id: Identifier
    revision: NonnegativeInt
    text: Text


class TurnConversation(Contract):
    """Bind a committed user message to its authoritative conversation snapshot."""

    entries: tuple[ConversationEntry, ...] = Field(min_length=1, max_length=1000)
    latest_turn_id: Identifier
    committed_revision: PositiveInt
    latest_message: Text
    reply_to_proposal_id: Identifier | None = None


class TrackerTurnReceipt(Contract):
    """Existing tracker ingress acknowledgement, never proof of completed reasoning."""

    case_id: Identifier
    turn_id: Identifier
    ingress_hash: Sha256
    prepared_hash: Sha256
    committed_revision: PositiveInt
    changed_fact_names: tuple[ShortText, ...] = Field(default=(), max_length=250)
    context_changed: Annotated[bool, Field(strict=True)]
    invalidated_checks: tuple[Text, ...] = Field(default=(), max_length=100)
    preparation: Literal["structured", "unstructured", "canonical_version_reply"]
    replayed: Annotated[bool, Field(strict=True)]


class TrackerCaseView(Contract):
    """One consistent tracker read, including same-revision proposal lifecycle."""

    state: CaseState
    history: tuple[ConversationEntry, ...] = Field(default=(), max_length=1000)
    status: Literal["new", "open", "awaiting_review", "awaiting_user", "answer_sent", "escalated"]
    pending_handoff: ProposalHandoff | None = None
    awaiting_reply: ApprovedReplyQuestion | None = None

    @model_validator(mode="after")
    def consistent_view(self) -> Self:
        if (self.state.pending_proposal_id is not None) != (self.pending_handoff is not None):
            raise ValueError("pending state and content must agree")
        if (self.status == "awaiting_review") != (self.pending_handoff is not None):
            raise ValueError("pending lifecycle must agree")
        if (self.status == "awaiting_user") != (self.awaiting_reply is not None):
            raise ValueError("reply lifecycle must agree")
        if self.awaiting_reply is not None and (
            self.awaiting_reply.case_id != self.state.case_id
            or self.awaiting_reply.case_revision != self.state.case_revision
        ):
            raise ValueError("reply must refer to the current case revision")
        previous = 0
        for entry in self.history:
            if entry.revision < previous or entry.revision > self.state.case_revision:
                raise ValueError("history must be ordered within the current revision")
            previous = entry.revision
        return self


class TrackerStageReceipt(Contract):
    case_id: Identifier
    proposal_id: Identifier
    revision: NonnegativeInt
