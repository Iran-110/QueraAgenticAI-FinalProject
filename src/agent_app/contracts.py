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
    "RunLimits",
    "ReasoningContext",
    "OutputIssue",
    "OutputFeedback",
    "RunResult",
    "TraceEvent",
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


class RunLimits(Contract):
    max_model_attempts: Annotated[int, Field(strict=True, ge=1, le=2)] = 2
    max_retrieval_rounds: Annotated[int, Field(strict=True, ge=1, le=2)] = 2
    max_queries_per_round: Annotated[int, Field(strict=True, ge=1, le=2)] = 2
    max_steps: Annotated[int, Field(strict=True, ge=1, le=8)] = 8


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
        "retrieve_more_queries_required",
        "retrieve_more_final_payload_forbidden",
        "final_drafts_required",
        "final_queries_forbidden",
        "ask_question_required",
        "question_forbidden",
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
