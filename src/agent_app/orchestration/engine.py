"""A mock-first workflow that returns previews and never executes case changes."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal, get_args
from uuid import uuid4

from pydantic import ValidationError

from agent_app.contracts import (
    AnalysisResult,
    CaseState,
    EvidenceBundle,
    OutputFeedback,
    OutputIssue,
    ProposalRequirements,
    ReasoningContext,
    RetrievalRequest,
    RunLimits,
    RunResult,
    TraceEvent,
)
from agent_app.orchestration.ports import Reasoner, ReasoningStopCode, ReasoningStopped, Retriever
from agent_app.orchestration.validation import detached_contract
from agent_app.reasoning.code_checks import has_invalid_python_code
from agent_app.reasoning.output import InvalidAnalysis, parse_analysis
from agent_app.reasoning.proposal_checks import callback_code_issues


def _normalize(text: str) -> str:
    return " ".join(text.split()).casefold()


def build_initial_query(case: CaseState, user_message: str) -> str:
    """Pack whole confirmed facts, prioritizing environment over long descriptions."""
    priority = {
        name: index
        for index, name in enumerate(
            (
                "streamlit_version",
                "python_version",
                "operating_system",
                "browser_version",
                "error_message",
                "widget_definition",
            )
        )
    }
    facts = sorted(
        (fact for fact in case.facts if fact.status == "active" and fact.provenance_kind == "user"),
        key=lambda fact: (priority.get(fact.name.casefold(), len(priority)), fact.name.casefold()),
    )
    message = " ".join(user_message.split())[:400]
    packed = []
    remaining = 500 - len(message) - 1
    for fact in facts:
        item = f"{fact.name}={fact.value}"
        needed = len(item) + (2 if packed else 0)
        if needed <= remaining:
            packed.append(item)
            remaining -= needed
    return message + (" " + "; ".join(packed) if packed else "")


class _Stopped(Exception):
    def __init__(self, code: str, status: str = "error") -> None:
        self.code = code
        self.status = status


@dataclass
class _Progress:
    limits: RunLimits
    model_attempts: int = 0
    retrieval_rounds: int = 0
    steps: int = 0
    trace: list[TraceEvent] = field(default_factory=list)
    output_issues: list[OutputIssue] = field(default_factory=list)

    def step(self, stage: str, message: str) -> None:
        if self.steps >= self.limits.max_steps:
            raise _Stopped("StepLimitExceeded", "budget_stopped")
        self.steps += 1
        self.trace.append(TraceEvent(stage=stage, message=message))

    def note(self, stage: str, message: str) -> None:
        # Operational events only: no raw messages, exceptions, secrets or hidden reasoning.
        self.trace.append(TraceEvent(stage=stage, message=message))


class SupportEngine:
    """Bound a single invocation; a future tracker must persist progress across resumes.

    ``current_case`` checks observable full-state drift in addition to the legacy
    revision callback. These reads are not a lock or lifecycle/run journal; the
    tracker must still check the final handoff atomically when staging it.

    Valid citation IDs establish source presence, not semantic correctness. A real
    quality evaluation still needs human review and source-backed case labels.
    """

    def __init__(
        self,
        retriever: Retriever,
        reasoner: Reasoner,
        *,
        snapshot_id: str,
        limits: RunLimits | None = None,
        top_k: int = 5,
        current_revision: Callable[[str], int] | None = None,
        current_case: Callable[[str], CaseState] | None = None,
        proposal_checks: bool = False,
        evidence_scope: Literal["all", "exact_user_version"] = "all",
    ) -> None:
        self.retriever = retriever
        self.reasoner = reasoner
        self.snapshot_id = snapshot_id
        self.limits = (
            RunLimits.model_validate(limits.model_dump(warnings=False))
            if limits is not None
            else RunLimits()
        )
        self.top_k = top_k
        self.current_revision = current_revision
        self.current_case = current_case
        if type(proposal_checks) is not bool:
            raise ValueError("Proposal checks require an explicit boolean.")
        self.proposal_checks = proposal_checks
        if type(evidence_scope) is not str or evidence_scope not in {"all", "exact_user_version"}:
            raise ValueError("Unsupported evidence scope policy.")
        self.evidence_scope = evidence_scope
        # Validate configuration before a port is invoked.
        RetrievalRequest(queries=("configuration-check",), snapshot_id=snapshot_id, top_k=top_k)

    def run(
        self,
        case: CaseState,
        user_message: str,
        *,
        run_id: str | None = None,
        proposal_requirements: ProposalRequirements | None = None,
    ) -> RunResult:
        case = detached_contract(CaseState, case)
        if proposal_requirements is not None:
            try:
                proposal_requirements = detached_contract(
                    ProposalRequirements, proposal_requirements
                )
                known = {
                    fact.name.casefold()
                    for fact in case.facts
                    if fact.status == "active" and fact.provenance_kind == "user"
                }
                if (
                    proposal_requirements.case_id != case.case_id
                    or proposal_requirements.case_revision != case.case_revision
                    or any(
                        target.name.casefold() in known
                        for target in proposal_requirements.question_targets
                    )
                ):
                    raise ValueError
            except (ValidationError, ValueError, TypeError, AttributeError):
                raise ValueError("Invalid caller-owned proposal requirements.") from None
        progress = _Progress(self.limits)
        run_id = run_id if run_id is not None else str(uuid4())
        # Bad caller IDs fail validation before adapters are invoked.
        RunResult(
            run_id=run_id, case_id=case.case_id, case_revision=case.case_revision, status="error"
        )

        def result(status: str, analysis: AnalysisResult | None = None, code: str | None = None):
            return RunResult(
                run_id=run_id,
                case_id=case.case_id,
                case_revision=case.case_revision,
                status=status,
                analysis=analysis,
                model_attempts=progress.model_attempts,
                retrieval_rounds=progress.retrieval_rounds,
                steps=progress.steps,
                error_code=code,
                trace=tuple(progress.trace),
                output_issues=tuple(progress.output_issues),
            )

        try:
            if (
                not isinstance(user_message, str)
                or not user_message.strip()
                or len(user_message) > 20_000
            ):
                raise _Stopped("InvalidInput")
            self._ensure_current(case)
            progress.step("started", "Loaded the supplied case snapshot.")
            queries = (build_initial_query(case, user_message),)
            seen_queries: set[str] = set()
            while True:
                evidence = self._retrieve(case, queries, seen_queries, progress)
                analysis = self._analyze(
                    case,
                    user_message,
                    evidence,
                    progress,
                    run_id=run_id,
                    proposal_requirements=proposal_requirements,
                )
                if analysis.decision != "retrieve_more":
                    self._ensure_current(case)
                    progress.step("awaiting_approval", f"Prepared an {analysis.decision} preview.")
                    return result("awaiting_approval", analysis)
                progress.note("refinement_requested", "The reasoner requested additional evidence.")
                if progress.model_attempts >= self.limits.max_model_attempts:
                    raise _Stopped("ModelAttemptLimitExceeded", "budget_stopped")
                queries = analysis.retrieval_queries
        except _Stopped as stopped:
            progress.note("stopped", stopped.code)
            return result(stopped.status, code=stopped.code)

    def _ensure_current(self, case: CaseState) -> None:
        # Reasoning cannot replace an outstanding proposal. Check supplied state
        # even without a storage callback, before retrieval or model attempts.
        if case.pending_proposal_id is not None:
            raise _Stopped("PendingProposalMismatch", "stale")
        if self.current_revision is not None:
            try:
                revision = self.current_revision(case.case_id)
            except Exception:
                raise _Stopped("CaseReadFailed") from None
            if type(revision) is not int or revision < 0:
                raise _Stopped("CaseReadFailed")
            if revision != case.case_revision:
                raise _Stopped("StaleRevision", "stale")
        if self.current_case is None:
            return
        try:
            raw = self.current_case(case.case_id)
            current = detached_contract(CaseState, raw)
        except Exception:
            raise _Stopped("CaseReadFailed") from None
        if current.case_id != case.case_id:
            raise _Stopped("CaseReadFailed")
        if current.case_revision != case.case_revision:
            raise _Stopped("StaleRevision", "stale")
        if current.pending_proposal_id != case.pending_proposal_id:
            raise _Stopped("PendingProposalMismatch", "stale")
        if current != case:
            raise _Stopped("CaseContentMismatch", "stale")

    def _retrieve(
        self,
        case: CaseState,
        queries: tuple[str, ...],
        seen_queries: set[str],
        progress: _Progress,
    ) -> EvidenceBundle:
        self._ensure_current(case)
        if progress.retrieval_rounds >= self.limits.max_retrieval_rounds:
            raise _Stopped("RetrievalRoundLimitExceeded", "budget_stopped")
        if len(queries) > self.limits.max_queries_per_round:
            raise _Stopped("QueryLimitExceeded", "budget_stopped")
        if any(_normalize(query) in seen_queries for query in queries):
            raise _Stopped("RepeatedQuery")
        try:
            request = RetrievalRequest(
                queries=queries, snapshot_id=self.snapshot_id, top_k=self.top_k
            )
        except ValidationError:
            raise _Stopped("InvalidRetrievalQuery") from None
        seen_queries.update(_normalize(query) for query in request.queries)
        progress.step("retrieval", f"Searching {len(request.queries)} query or queries.")
        progress.retrieval_rounds += 1
        try:
            raw = self.retriever.search(request.model_copy(deep=True))
        except Exception:
            self._ensure_current(case)
            raise _Stopped("RetrievalUnavailable") from None
        self._ensure_current(case)
        try:
            # Revalidate even model_construct()/model_copy() results supplied by an adapter.
            data = raw.model_dump(warnings=False) if isinstance(raw, EvidenceBundle) else raw
            evidence = EvidenceBundle.model_validate(data)
            if evidence.snapshot_id != self.snapshot_id or len(evidence.hits) > self.top_k:
                raise ValueError("Unexpected snapshot or result count")
            evidence = EvidenceBundle.model_validate(
                {**evidence.model_dump(), "retrieval_round": progress.retrieval_rounds}
            )
        except (ValidationError, ValueError, TypeError):
            raise _Stopped("RetrievalResultInvalid") from None
        progress.note("evidence_received", f"Received {len(evidence.hits)} evidence chunks.")
        if self.evidence_scope == "exact_user_version":
            # Applicability is caller/retriever metadata, never inferred from text.
            # This opt-in policy is for advice about the current installation;
            # historical/comparison workflows must keep the default 'all' policy.
            version = next(
                (
                    fact.value
                    for fact in case.facts
                    if fact.name.casefold() == "streamlit_version"
                    and fact.status == "active"
                    and fact.provenance_kind == "user"
                ),
                None,
            )
            hits = tuple(
                hit
                for hit in evidence.hits
                if not hit.applicable_versions or version in hit.applicable_versions
            )
            excluded = len(evidence.hits) - len(hits)
            if excluded:
                progress.note(
                    "evidence_scoped", f"Excluded {excluded} chunks outside the confirmed version."
                )
                evidence = evidence.model_copy(update={"hits": hits})
        return evidence

    def _analyze(
        self,
        case: CaseState,
        user_message: str,
        evidence: EvidenceBundle,
        progress: _Progress,
        *,
        run_id: str,
        proposal_requirements: ProposalRequirements | None = None,
    ) -> AnalysisResult:
        last_error = "ModelAttemptLimitExceeded"
        feedback = None
        while progress.model_attempts < self.limits.max_model_attempts:
            self._ensure_current(case)
            progress.step("reasoning", "Requesting a structured decision.")
            progress.model_attempts += 1
            try:
                raw = self.reasoner.analyze(
                    case.model_copy(deep=True),
                    user_message,
                    evidence.model_copy(deep=True),
                    context=ReasoningContext(
                        run_id=run_id,
                        case_id=case.case_id,
                        case_revision=case.case_revision,
                        attempt_index=progress.model_attempts,
                        output_feedback=feedback.model_copy(deep=True) if feedback else None,
                        proposal_requirements=(
                            proposal_requirements.model_copy(deep=True)
                            if proposal_requirements is not None
                            else None
                        ),
                        query_limit=self.limits.max_queries_per_round,
                        remaining_model_attempts=self.limits.max_model_attempts
                        - progress.model_attempts,
                        remaining_retrieval_rounds=self.limits.max_retrieval_rounds
                        - progress.retrieval_rounds,
                        can_refine=(
                            progress.model_attempts < self.limits.max_model_attempts
                            and progress.retrieval_rounds < self.limits.max_retrieval_rounds
                            and self.limits.max_steps - progress.steps >= 3
                        ),
                    ),
                )
            except InvalidAnalysis as error:
                # A structured-plan adapter may reject before an AnalysisResult
                # exists. Its diagnostics are still untrusted port output.
                self._ensure_current(case)
                feedback = self._safe_output_feedback(error)
                progress.output_issues.extend(feedback.issues)
                last_error = "ModelOutputInvalid"
                progress.note("reasoning_failed", last_error)
                progress.note("output_validation", ", ".join(i.code for i in feedback.issues))
                # Preserve the legacy terminal evidence/identity boundary. A
                # malformed representation can be repaired; binding a plan to
                # other case/source content cannot buy another paid attempt.
                terminal_codes = {
                    "grounded_context_mismatch": "GroundedContextMismatch",
                    "grounded_source_mismatch": "GroundedSourceMismatch",
                }
                for issue in feedback.issues:
                    if issue.code in terminal_codes:
                        raise _Stopped(terminal_codes[issue.code]) from None
                continue
            except ReasoningStopped as stopped:
                self._ensure_current(case)
                try:
                    # Exception fields can change after their constructor's
                    # checks. Invalid typed stops remain terminal and must keep
                    # the consumed attempt without exporting adapter diagnostics.
                    code, status = stopped.code, stopped.status
                    if (
                        type(code) is not str
                        or code not in get_args(ReasoningStopCode.__value__)
                        or type(status) is not str
                        or status not in {"error", "budget_stopped"}
                    ):
                        raise ValueError
                except Exception:
                    raise _Stopped("ReasoningUnavailable") from None
                raise _Stopped(code, status) from None
            except Exception:
                self._ensure_current(case)
                last_error = "ReasoningUnavailable"
                progress.note("reasoning_failed", last_error)
                continue
            self._ensure_current(case)
            try:
                analysis = parse_analysis(raw)
                # Source/authority violations remain terminal, even alongside bad code.
                self._validate_analysis(case, evidence, analysis)
                if has_invalid_python_code(analysis):
                    raise InvalidAnalysis((OutputIssue(code="invalid_python_syntax"),))
                if self.proposal_checks:
                    issues = list(
                        callback_code_issues(
                            analysis,
                            case,
                            evidence,
                            require_fresh_widget_value=bool(
                                proposal_requirements
                                and proposal_requirements.require_fresh_widget_value
                            ),
                        )
                    )
                    if proposal_requirements is not None and analysis.decision == "ask":
                        targets = {
                            target.name: target for target in proposal_requirements.question_targets
                        }
                        if len(analysis.missing_info) != 1:
                            issues.append(
                                OutputIssue(code="ask_target_required", field="missing_info")
                            )
                        elif analysis.missing_info[0] not in targets:
                            issues.append(
                                OutputIssue(code="ask_unregistered_target", field="missing_info")
                            )
                        elif analysis.next_question != targets[analysis.missing_info[0]].question:
                            issues.append(
                                OutputIssue(code="ask_question_mismatch", field="next_question")
                            )
                    if issues:
                        raise InvalidAnalysis(tuple(issues[:8]))
            except InvalidAnalysis as error:
                feedback = self._safe_output_feedback(error)
                progress.output_issues.extend(feedback.issues)
                last_error = "ModelOutputInvalid"
                codes = ", ".join(issue.code for issue in feedback.issues)
                progress.note("reasoning_failed", last_error)
                progress.note("output_validation", codes)
                continue
            except (ValueError, TypeError, RecursionError):
                feedback = OutputFeedback(issues=(OutputIssue(code="invalid_shape"),))
                progress.output_issues.extend(feedback.issues)
                last_error = "ModelOutputInvalid"
                progress.note("reasoning_failed", last_error)
                progress.note("output_validation", "invalid_shape")
                continue
            return analysis
        raise _Stopped(last_error)

    @staticmethod
    def _safe_output_feedback(error: InvalidAnalysis) -> OutputFeedback:
        try:
            return OutputFeedback.model_validate(
                {"issues": [issue.model_dump(warnings=False) for issue in error.issues]}
            )
        except (ValidationError, ValueError, TypeError, AttributeError, RecursionError):
            return OutputFeedback(issues=(OutputIssue(code="invalid_shape"),))

    @staticmethod
    def _validate_analysis(
        case: CaseState, evidence: EvidenceBundle, analysis: AnalysisResult
    ) -> None:
        chunk_ids = {hit.chunk_id for hit in evidence.hits}
        source_ids = {hit.source_id for hit in evidence.hits}
        if any(link.chunk_id not in chunk_ids for link in analysis.evidence_links):
            raise _Stopped("UnknownEvidenceReference")
        if analysis.decision == "answer" and not analysis.evidence_links:
            raise _Stopped("AnswerWithoutEvidence")
        known_user_facts = {
            (fact.name, fact.value, fact.source_ref, fact.turn_id)
            for fact in case.facts
            if fact.status == "active" and fact.provenance_kind == "user"
        }
        confirmed_values = {
            fact.name.casefold(): fact.value
            for fact in case.facts
            if fact.status == "active" and fact.provenance_kind == "user"
        }
        for fact in analysis.facts_delta:
            if fact.status != "active":
                raise _Stopped("UnsupportedFactUpdate")
            if fact.provenance_kind == "user":
                if (fact.name, fact.value, fact.source_ref, fact.turn_id) not in known_user_facts:
                    raise _Stopped("UnsupportedUserFact")
            elif fact.source_ref not in chunk_ids | source_ids:
                raise _Stopped("UnknownFactSource")
            elif (
                fact.name.casefold() in confirmed_values
                and fact.value != confirmed_values[fact.name.casefold()]
            ):
                raise _Stopped("ConflictingEvidenceFact")
        active_names = {
            fact.name.casefold()
            for fact in case.facts
            if fact.status == "active" and fact.provenance_kind == "user"
        }
        if any(name.casefold() in active_names for name in analysis.missing_info):
            raise _Stopped("KnownFactMarkedMissing")
        performed = {_normalize(check) for check in case.checks_performed}
        if any(_normalize(check) in performed for check in analysis.checks_suggested):
            raise _Stopped("RepeatedCheck")
