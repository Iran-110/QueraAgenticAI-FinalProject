"""Explicit opt-in configuration; credentials never appear in representations."""

import os
from collections.abc import Mapping
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    StringConstraints,
    field_validator,
    model_validator,
)

from agent_app.reasoning.prompts import PromptPolicy

METIS_CHAT_URL = "https://api.metisai.ir/openai/v1/chat/completions"


class MetisConfig(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, validate_default=True, hide_input_in_errors=True
    )

    api_key: SecretStr = Field(repr=False)
    live_enabled: Annotated[bool, Field(strict=True)] = False
    model: str = "gpt-4o-mini"
    phase: Literal["development", "evaluation", "demo"] = "development"
    prompt_policy: PromptPolicy = "baseline"
    # Caller-owned accounting authorization, never selected by model output.
    continuation_id: (
        Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")] | None
    ) = None
    max_output_tokens: Annotated[int, Field(strict=True, ge=128, le=2048)] = 1024
    input_token_reserve: Annotated[int, Field(strict=True, ge=4096, le=32768)] = 32768
    max_request_usd: Decimal = Decimal("0.02")

    @model_validator(mode="before")
    @classmethod
    def wrap_credentials_before_validation(cls, values: object) -> object:
        if isinstance(values, Mapping) and "api_key" in values:
            values = dict(values)
            raw = values["api_key"]
            if not isinstance(raw, SecretStr):
                # ValidationError JSON retains field inputs. Wrap before field checks
                # so invalid raw credentials are masked there as well as in repr.
                values["api_key"] = SecretStr(raw if isinstance(raw, str) else "")
        return values

    @field_validator("api_key")
    @classmethod
    def validate_key(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        if not raw or len(raw) > 2048 or not raw.isascii() or any(char.isspace() for char in raw):
            raise ValueError("A nonempty ASCII credential is required")
        if any(ord(char) < 33 or ord(char) > 126 for char in raw):
            raise ValueError("Invalid credential format")
        return value

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: str) -> str:
        if not value or len(value) > 100 or any(char.isspace() for char in value):
            raise ValueError("Invalid model identifier")
        return value

    @field_validator("max_request_usd", mode="before")
    @classmethod
    def validate_request_cap(cls, value: object) -> Decimal:
        if (
            not isinstance(value, Decimal)
            or not value.is_finite()
            or not 0 < value <= Decimal("0.05")
        ):
            raise ValueError("Request cap must be an explicit Decimal between 0 and 0.05 USD")
        return value

    @classmethod
    def from_env(cls) -> "MetisConfig":
        key = os.environ.get("METIS_API_KEY", "")
        if not key:
            raise ValueError("METIS_API_KEY is required")
        return cls(
            api_key=SecretStr(key),
            live_enabled=os.environ.get("METIS_LIVE_ENABLED") == "true",
            model=os.environ.get("METIS_MODEL", "gpt-4o-mini"),
            prompt_policy=os.environ.get("METIS_PROMPT_POLICY", "baseline"),
        )
