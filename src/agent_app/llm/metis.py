"""A single-send, non-streaming Metis reasoning port with durable accounting."""

import hashlib
import json

import httpx
from pydantic import ValidationError

from agent_app.contracts import CaseState, EvidenceBundle, GroundedRequest, ReasoningContext
from agent_app.llm.budget import BudgetDenied, BudgetLedger, LedgerConflict, LedgerUnavailable
from agent_app.llm.config import METIS_CHAT_URL, MetisConfig
from agent_app.llm.pricing import get_price, same_verified_price
from agent_app.orchestration.ports import ReasoningStopped
from agent_app.reasoning.grounding import build_grounded_messages, validate_grounded_request
from agent_app.reasoning.prompts import build_messages


def request_id_for(context: ReasoningContext) -> str:
    """Feedback and workflow hints never create another billable attempt identity."""
    context = ReasoningContext.model_validate(context.model_dump(warnings=False))
    identity = context.model_dump_json(
        include={"run_id", "case_id", "case_revision", "attempt_index"}
    )
    return "call:" + hashlib.sha256(identity.encode()).hexdigest()


class MetisReasoner:
    def __init__(
        self,
        config: MetisConfig,
        ledger: BudgetLedger,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.config = MetisConfig.model_validate(config.model_dump(warnings=False))
        self.ledger = ledger
        self.client = httpx.Client(
            transport=transport or httpx.HTTPTransport(retries=0),
            timeout=httpx.Timeout(30, connect=5, write=10, pool=5),
            follow_redirects=False,
            trust_env=False,
        )

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "MetisReasoner":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def analyze(
        self,
        case: CaseState,
        user_message: str,
        evidence: EvidenceBundle,
        *,
        context: ReasoningContext,
        grounded_request: GroundedRequest | None = None,
    ) -> str:
        if self.config.response_mode == "analysis" and grounded_request is not None:
            raise ValueError("Grounded request requires grounded plan mode")
        if self.config.response_mode == "grounded_plan" and grounded_request is None:
            raise ValueError("Grounded plan mode requires a grounded request")
        try:
            case = CaseState.model_validate(case.model_dump(warnings=False))
            evidence = EvidenceBundle.model_validate(evidence.model_dump(warnings=False))
            context = ReasoningContext.model_validate(context.model_dump(warnings=False))
        except (AttributeError, TypeError, ValidationError):
            if self.config.response_mode == "grounded_plan":
                raise ValueError("Invalid grounded input") from None
            raise
        if context.case_id != case.case_id or context.case_revision != case.case_revision:
            raise ValueError("Reasoning context does not match case")
        if (
            not isinstance(user_message, str)
            or not user_message.strip()
            or len(user_message) > 20_000
        ):
            raise ValueError("Invalid user input")
        if self.config.response_mode == "grounded_plan":
            try:
                request = validate_grounded_request(grounded_request)
                if (
                    request.case != case
                    or request.user_message != user_message
                    or request.evidence != evidence
                ):
                    raise ValueError("Grounded request does not match reasoning inputs")
                messages = build_grounded_messages(request, context)
            except (AttributeError, TypeError, ValueError):
                raise ValueError("Invalid grounded request or context") from None
        if not self.config.live_enabled:
            raise ReasoningStopped("LiveCallsDisabled")
        price = get_price(self.config.model)
        if price is None:
            raise ReasoningStopped("UnknownPricing", "budget_stopped")
        if self.config.response_mode == "analysis":
            messages = build_messages(
                case,
                user_message,
                evidence,
                feedback=context.output_feedback,
                policy=self.config.prompt_policy,
                context=context,
            )
        # UTF-8 byte count plus framing margin is a conservative operational guard,
        # not a provider billing guarantee. The live pilot must verify this assumption.
        message_bytes = len(json.dumps(messages, ensure_ascii=False).encode("utf-8"))
        if message_bytes + 1024 > self.config.input_token_reserve:
            raise ReasoningStopped("ContextLimitExceeded")
        reserve = price.cost(self.config.input_token_reserve, self.config.max_output_tokens)
        if reserve > self.config.max_request_usd:
            raise ReasoningStopped("CostBoundExceeded", "budget_stopped")
        # Feedback changes the prompt, never the identity of an already used
        # attempt. Excluding it also preserves pre-feedback ledger request IDs.
        request_id = request_id_for(context)
        try:
            self.ledger.reserve(
                request_id=request_id,
                run_id=context.run_id,
                case_id=case.case_id,
                case_revision=case.case_revision,
                attempt=context.attempt_index,
                model=self.config.model,
                phase=self.config.phase,
                amount_usd=reserve,
                continuation_id=self.config.continuation_id,
            )
        except BudgetDenied:
            raise ReasoningStopped("BudgetExceeded", "budget_stopped") from None
        except LedgerConflict:
            raise ReasoningStopped("DuplicateModelRequest") from None
        except LedgerUnavailable:
            raise ReasoningStopped("LedgerUnavailable") from None
        except ValueError:
            raise ReasoningStopped("ProviderRequestFailed") from None
        payload = {
            "model": self.config.model,
            "messages": list(messages),
            "max_tokens": self.config.max_output_tokens,
            "stream": False,
        }
        try:
            with self.client.stream(
                "POST",
                METIS_CHAT_URL,
                json=payload,
                headers={"Authorization": "Bearer " + self.config.api_key.get_secret_value()},
            ) as response:
                if response.status_code != 200:
                    raise ValueError("Non-success provider status")
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > 262_144:
                        raise ValueError("Provider response too large")
                body = json.loads(data)
        except Exception:
            self._uncertain(request_id, "ProviderRequestFailed")
            raise ReasoningStopped("ProviderRequestFailed") from None
        if not isinstance(body, dict):
            self._uncertain(request_id, "ProviderResponseInvalid")
            raise ReasoningStopped("ProviderResponseInvalid")
        returned_model = body.get("model")
        if not isinstance(returned_model, str) or not same_verified_price(
            self.config.model, returned_model
        ):
            self._uncertain(request_id, "ProviderModelMismatch", halt=True)
            raise ReasoningStopped("ProviderModelMismatch")
        usage = body.get("usage")
        if not isinstance(usage, dict):
            self._uncertain(request_id, "ProviderUsageUnknown", halt=True)
            raise ReasoningStopped("ProviderUsageUnknown")
        input_tokens, output_tokens = usage.get("prompt_tokens"), usage.get("completion_tokens")
        total_tokens = usage.get("total_tokens")
        if any(type(value) is not int or value < 0 for value in (input_tokens, output_tokens)) or (
            total_tokens is not None
            and (type(total_tokens) is not int or total_tokens != input_tokens + output_tokens)
        ):
            self._uncertain(request_id, "ProviderUsageUnknown", halt=True)
            raise ReasoningStopped("ProviderUsageUnknown")
        cost = price.cost(input_tokens, output_tokens)
        try:
            self.ledger.settle(
                request_id, cost_usd=cost, input_tokens=input_tokens, output_tokens=output_tokens
            )
        except ValueError:
            self._uncertain(request_id, "ProviderUsageUnknown", halt=True)
            raise ReasoningStopped("ProviderUsageUnknown") from None
        except (LedgerUnavailable, LedgerConflict):
            # The pre-send reservation remains durable when settlement cannot complete.
            raise ReasoningStopped("LedgerUnavailable") from None
        if cost > reserve:
            raise ReasoningStopped("CostBoundExceeded", "budget_stopped")
        if (
            input_tokens > self.config.input_token_reserve
            or output_tokens > self.config.max_output_tokens
        ):
            self._halt()
            raise ReasoningStopped("ProviderResponseInvalid")
        choices = body.get("choices")
        if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
            raise ReasoningStopped("ProviderResponseInvalid")
        choice = choices[0]
        message = choice.get("message")
        if (
            choice.get("finish_reason") != "stop"
            or not isinstance(message, dict)
            or message.get("role") != "assistant"
            or message.get("tool_calls")
            or message.get("function_call")
            or message.get("refusal")
            or not isinstance(message.get("content"), str)
            or not message["content"].strip()
        ):
            raise ReasoningStopped("ProviderResponseInvalid")
        # The caller owns output validation/rendering and the bounded repair allowance.
        return message["content"]

    def _halt(self) -> None:
        try:
            self.ledger.halt()
        except LedgerUnavailable:
            raise ReasoningStopped("LedgerUnavailable") from None

    def _uncertain(self, request_id: str, code: str, *, halt: bool = False) -> None:
        try:
            self.ledger.mark_uncertain(request_id, error_code=code)
            if halt:
                self.ledger.halt()
        except (LedgerUnavailable, LedgerConflict):
            raise ReasoningStopped("LedgerUnavailable") from None
