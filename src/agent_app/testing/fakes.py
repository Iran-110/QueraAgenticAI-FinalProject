"""Small offline adapters usable by every module owner while real integrations are built."""

from collections.abc import Sequence
from copy import deepcopy

from agent_app.contracts import CaseState, EvidenceBundle, RetrievalRequest
from agent_app.orchestration.ports import ReasoningOutput


class FakeRetriever:
    def __init__(self, responses: Sequence[EvidenceBundle | Exception]) -> None:
        self.responses = list(responses)
        self.requests: list[RetrievalRequest] = []

    def search(self, request: RetrievalRequest) -> EvidenceBundle:
        self.requests.append(request.model_copy(deep=True))
        if not self.responses:
            raise RuntimeError("No scripted retrieval response remains")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response.model_copy(deep=True)


class FakeReasoner:
    def __init__(self, responses: Sequence[ReasoningOutput | Exception]) -> None:
        self.responses = list(responses)
        self.inputs: list[tuple[CaseState, str, EvidenceBundle]] = []

    def analyze(
        self, case: CaseState, user_message: str, evidence: EvidenceBundle
    ) -> ReasoningOutput:
        self.inputs.append(
            (case.model_copy(deep=True), user_message, evidence.model_copy(deep=True))
        )
        if not self.responses:
            raise RuntimeError("No scripted reasoning response remains")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return deepcopy(response)
