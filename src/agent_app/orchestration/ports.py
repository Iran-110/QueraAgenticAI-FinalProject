"""Adapters implemented independently by the retrieval and model owners."""

from collections.abc import Mapping
from typing import Protocol

from agent_app.contracts import AnalysisResult, CaseState, EvidenceBundle, RetrievalRequest

type ReasoningOutput = AnalysisResult | Mapping[str, object] | str


class Retriever(Protocol):
    def search(self, request: RetrievalRequest) -> EvidenceBundle:
        """Return evidence from the requested frozen snapshot; perform no case writes."""
        ...


class Reasoner(Protocol):
    def analyze(
        self, case: CaseState, user_message: str, evidence: EvidenceBundle
    ) -> ReasoningOutput:
        """Return a structured decision; permission to mutate a case is never model output."""
        ...
