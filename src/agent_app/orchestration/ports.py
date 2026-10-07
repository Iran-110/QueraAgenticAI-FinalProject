"""Adapters implemented independently by the retrieval and model owners."""

from collections.abc import Mapping
from typing import Literal, Protocol, get_args

from agent_app.contracts import (
    AnalysisResult,
    CaseState,
    EvidenceBundle,
    ReasoningContext,
    RetrievalRequest,
)

type ReasoningOutput = AnalysisResult | Mapping[str, object] | str

type ReasoningStopCode = Literal[
    "ProviderRequestFailed",
    "ProviderResponseInvalid",
    "ProviderUsageUnknown",
    "ProviderModelMismatch",
    "ContextLimitExceeded",
    "DuplicateModelRequest",
    "LedgerUnavailable",
    "LiveCallsDisabled",
    "UnknownPricing",
    "BudgetExceeded",
    "CostBoundExceeded",
]


class ReasoningStopped(Exception):
    """A terminal adapter failure that must not trigger another paid attempt."""

    def __init__(
        self, code: ReasoningStopCode, status: Literal["error", "budget_stopped"] = "error"
    ) -> None:
        if code not in get_args(ReasoningStopCode.__value__):
            raise ValueError("Unsupported reasoning stop code")
        if status not in {"error", "budget_stopped"}:
            raise ValueError("Unsupported reasoning stop status")
        self.code = code
        self.status = status
        super().__init__(code)


class Retriever(Protocol):
    def search(self, request: RetrievalRequest) -> EvidenceBundle:
        """Return evidence from the requested frozen snapshot; perform no case writes."""
        ...


class Reasoner(Protocol):
    def analyze(
        self,
        case: CaseState,
        user_message: str,
        evidence: EvidenceBundle,
        *,
        context: ReasoningContext,
    ) -> ReasoningOutput:
        """Return a structured decision; permission to mutate a case is never model output."""
        ...
