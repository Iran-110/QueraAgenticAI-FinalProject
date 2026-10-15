"""Optional plan port using the existing single-send provider and ledger gateway."""

from copy import deepcopy
from threading import RLock

import httpx

from agent_app.contracts import GroundedRequest, ReasoningContext
from agent_app.llm.budget import BudgetLedger
from agent_app.llm.config import MetisConfig
from agent_app.llm.metis import MetisReasoner, request_id_for
from agent_app.orchestration.ports import ReasoningStopped
from agent_app.reasoning.compact_plan import expand_compact_plan, observe_compact_plan
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
        self._wire_lock = RLock()
        self._wire_observation = None
        self.reasoner = MetisReasoner(self.config, ledger, transport=transport)

    def close(self) -> None:
        self.reasoner.close()

    def __enter__(self) -> "MetisGroundedPlanner":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def latest_wire_observation(self, context):
        """Bounded allowlisted diagnostics for only this exact attempted request."""
        request_id = request_id_for(context)
        with self._wire_lock:
            observed = self._wire_observation
            return deepcopy(observed) if observed and observed["request_id"] == request_id else None

    def plan(self, request: GroundedRequest, *, context: ReasoningContext) -> str:
        with self._wire_lock:
            self._wire_observation = None
        try:
            request = validate_grounded_request(request)
        except (AttributeError, TypeError, ValueError):
            raise ValueError("Invalid grounded request") from None
        raw = self.reasoner.analyze(
            request.case,
            request.user_message,
            request.evidence,
            context=context,
            grounded_request=request,
        )

        if not self.config.grounded_compact_plan:
            return raw
        # Preserve the existing private credential-echo stop before diagnostics;
        # no provider text or unknown field names are retained in the observation.
        if self.config.api_key.get_secret_value() in raw:
            raise ReasoningStopped("ProviderResponseInvalid")
        observed = {"request_id": request_id_for(context), **observe_compact_plan(raw, request)}
        with self._wire_lock:
            self._wire_observation = observed
        return expand_compact_plan(raw, request).model_dump_json()
