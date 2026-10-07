"""Dated Metis USD list prices, never a statement of account deductions."""

from dataclasses import dataclass
from decimal import Decimal

PRICE_SOURCE = "https://api.metisai.ir/api/v1/meta/providers/pricing"
PRICE_VERIFIED_ON = "2026-10-07"


@dataclass(frozen=True)
class ModelPrice:
    model: str
    input_usd_per_token: Decimal
    output_usd_per_token: Decimal

    def cost(self, input_tokens: int, output_tokens: int) -> Decimal:
        if any(type(value) is not int or value < 0 for value in (input_tokens, output_tokens)):
            raise ValueError("Token counts must be nonnegative integers")
        return input_tokens * self.input_usd_per_token + output_tokens * self.output_usd_per_token


_PRICES = {
    model: ModelPrice(model, Decimal(input_rate), Decimal(output_rate))
    for model, input_rate, output_rate in (
        ("gpt-4o-mini", "0.000000165", "0.000000660"),
        ("gpt-4o-mini-2024-07-18", "0.000000165", "0.000000660"),
        ("gpt-4.1-mini", "0.000000440", "0.000001760"),
    )
}


def get_price(model: str) -> ModelPrice | None:
    return _PRICES.get(model)


def same_verified_price(requested: str, returned: str) -> bool:
    first, second = get_price(requested), get_price(returned)
    return bool(
        first
        and second
        and first.input_usd_per_token == second.input_usd_per_token
        and first.output_usd_per_token == second.output_usd_per_token
        and requested.startswith("gpt-4o-mini")
        and returned.startswith("gpt-4o-mini")
    ) or (first is not None and requested == returned)
