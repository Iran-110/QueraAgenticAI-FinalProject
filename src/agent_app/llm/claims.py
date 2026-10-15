"""Explicit internal claim planner using the unchanged single-send budget path.

No environment flag or normal API factory selects this planner. Its private
message projection can change representation, never caller identity, limits,
accounting, provider checks, tracker authority or the two-attempt allowance.
"""

import json
from threading import RLock

from agent_app.contracts import ReasoningContext
from agent_app.llm.metis import MetisReasoner
from agent_app.orchestration.ports import ReasoningStopped
from agent_app.reasoning.claim_plan import build_claim_messages, validate_claim_request


class _ClaimGateway(MetisReasoner):
    def __init__(self, config, ledger, *, transport=None):
        super().__init__(config, ledger, transport=transport)
        self._claim_binding = None

    def _analysis_messages(self, case, user_message, evidence, context):
        binding = self._claim_binding
        if binding is None:
            raise ValueError("ClaimGatewayBindingRequired")
        request, expected_context = binding
        if (
            expected_context != context
            or request.grounded.case != case
            or request.grounded.user_message != user_message.strip()
            or request.grounded.evidence != evidence
        ):
            raise ValueError("ClaimGatewayBindingMismatch")
        return build_claim_messages(request, context)


class MetisClaimPlanner:
    """Return only an untrusted private plan; the core validates and renders it."""

    def __init__(self, config, ledger, *, transport=None):
        if config.response_mode != "analysis" or any(
            getattr(config, name)
            for name in type(config).model_fields
            if name.startswith("grounded_")
        ):
            raise ValueError("ClaimPlannerRequiresPlainAnalysisGateway")
        self._lock = RLock()
        self.reasoner = _ClaimGateway(config, ledger, transport=transport)
        self.config = self.reasoner.config

    def close(self):
        self.reasoner.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def plan(self, request, *, context):
        request = validate_claim_request(request)
        context = ReasoningContext.model_validate(context.model_dump(warnings=False))
        # Pure validation/projection precedes the gateway's credential transport
        # and reserve. The exact projection is recomputed inside the send path.
        build_claim_messages(request, context)
        with self._lock:
            self.reasoner._claim_binding = (request, context)
            try:
                raw = self.reasoner.analyze(
                    request.grounded.case,
                    request.grounded.user_message,
                    request.grounded.evidence,
                    context=context,
                )
                key = self.config.api_key.get_secret_value()
                decoded = raw
                try:
                    decoded = json.dumps(json.loads(raw), ensure_ascii=False)
                except (ValueError, RecursionError):
                    pass
                if key in raw or key in decoded:
                    raise ReasoningStopped("ProviderResponseInvalid")
                return raw
            finally:
                # No previous source, USER snapshot or repair context survives
                # a completed or failed planner call.
                self.reasoner._claim_binding = None
