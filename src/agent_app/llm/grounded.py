"""Optional plan port using the existing single-send provider and ledger gateway."""

import httpx

from agent_app.contracts import GroundedRequest, ReasoningContext
from agent_app.llm.budget import BudgetLedger
from agent_app.llm.config import MetisConfig
from agent_app.llm.metis import MetisReasoner
from agent_app.reasoning.grounding import validate_grounded_request


class MetisGroundedPlanner:
    """Return raw plan output; parsing, rendering and repair remain caller-owned."""

    def __init__(
        self,
        config: MetisConfig,
        ledger: BudgetLedger,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.config = MetisConfig.model_validate(config.model_dump(warnings=False))
        if self.config.response_mode != "grounded_plan":
            raise ValueError("Grounded planner requires grounded plan mode")
        self.reasoner = MetisReasoner(self.config, ledger, transport=transport)

    def close(self) -> None:
        self.reasoner.close()

    def __enter__(self) -> "MetisGroundedPlanner":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def plan(self, request: GroundedRequest, *, context: ReasoningContext) -> str:
        try:
            request = validate_grounded_request(request)
        except (AttributeError, TypeError, ValueError):
            raise ValueError("Invalid grounded request") from None
        return self.reasoner.analyze(
            request.case,
            request.user_message,
            request.evidence,
            context=context,
            grounded_request=request,
        )
