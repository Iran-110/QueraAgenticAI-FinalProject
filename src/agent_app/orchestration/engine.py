"""A mock-first workflow that returns previews and never executes case changes."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from uuid import uuid4

from pydantic import ValidationError

from agent_app.contracts import (
    AnalysisResult,
    CaseState,
    EvidenceBundle,
    RetrievalRequest,
    RunLimits,
    RunResult,
    TraceEvent,
)
from agent_app.orchestration.ports import Reasoner, Retriever


def _normalize(text: str) -> str:
    return " ".join(text.split()).casefold()


def build_initial_query(case: CaseState, user_message: str) -> str:
    """Use the current message and active facts, never superseded environment values."""
    facts = "; ".join(f"{fact.name}={fact.value}" for fact in case.facts if fact.status == "active")
    message = " ".join(user_message.split())[:400]
    return (message + (f" {facts[:99]}" if facts else ""))[:500]


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
        # Validate configuration before a port is invoked.
        RetrievalRequest(queries=("configuration-check",), snapshot_id=snapshot_id, top_k=top_k)

    def run(self, case: CaseState, user_message: str, *, run_id: str | None = None) -> RunResult:
        case = CaseState.model_validate(case.model_dump(warnings=False))
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
                analysis = self._analyze(case, user_message, evidence, progress)
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
        if self.current_revision is None:
            return
        try:
            revision = self.current_revision(case.case_id)
        except Exception:
            raise _Stopped("CaseReadFailed") from None
        if type(revision) is not int or revision < 0:
            raise _Stopped("CaseReadFailed")
        if revision != case.case_revision:
            raise _Stopped("StaleRevision", "stale")

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
        return evidence

    def _analyze(
        self, case: CaseState, user_message: str, evidence: EvidenceBundle, progress: _Progress
    ) -> AnalysisResult:
        last_error = "ModelAttemptLimitExceeded"
        while progress.model_attempts < self.limits.max_model_attempts:
            self._ensure_current(case)
            progress.step("reasoning", "Requesting a structured decision.")
            progress.model_attempts += 1
            try:
                raw = self.reasoner.analyze(
                    case.model_copy(deep=True), user_message, evidence.model_copy(deep=True)
                )
            except Exception:
                self._ensure_current(case)
                last_error = "ReasoningUnavailable"
                progress.note("reasoning_failed", last_error)
                continue
            self._ensure_current(case)
            try:
                if isinstance(raw, str):
                    analysis = AnalysisResult.model_validate_json(raw)
                elif isinstance(raw, AnalysisResult):
                    analysis = AnalysisResult.model_validate(raw.model_dump(warnings=False))
                elif isinstance(raw, Mapping):
                    analysis = AnalysisResult.model_validate(dict(raw))
                else:
                    raise ValueError("Unsupported output type")
            except (ValidationError, ValueError, TypeError):
                last_error = "ModelOutputInvalid"
                progress.note("reasoning_failed", last_error)
                continue
            # Invalid evidence/unsupported facts fail closed rather than buying another attempt.
            self._validate_analysis(case, evidence, analysis)
            return analysis
        raise _Stopped(last_error)

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
        for fact in analysis.facts_delta:
            if fact.status != "active":
                raise _Stopped("UnsupportedFactUpdate")
            if fact.provenance_kind == "user":
                if (fact.name, fact.value, fact.source_ref, fact.turn_id) not in known_user_facts:
                    raise _Stopped("UnsupportedUserFact")
            elif fact.source_ref not in chunk_ids | source_ids:
                raise _Stopped("UnknownFactSource")
        active_names = {fact.name.casefold() for fact in case.facts if fact.status == "active"}
        if any(name.casefold() in active_names for name in analysis.missing_info):
            raise _Stopped("KnownFactMarkedMissing")
        performed = {_normalize(check) for check in case.checks_performed}
        if any(_normalize(check) in performed for check in analysis.checks_suggested):
            raise _Stopped("RepeatedCheck")
