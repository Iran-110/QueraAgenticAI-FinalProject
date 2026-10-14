import json

import httpx
import pytest

from agent_app.testing.provider_observation import (
    ObservedStream,
    response_metadata,
    transport_category,
)


@pytest.mark.parametrize(
    "reason", ["stop", "length", "content_filter", "tool_calls", "function_call"]
)
def test_allowlisted_finish_reason_is_observed_without_content(reason):
    secret = "synthetic-private-response"
    body = {
        "model": "gpt-4o-mini-2024-07-18",
        "choices": [
            {
                "finish_reason": reason,
                "message": {
                    "role": "assistant",
                    "content": secret,
                    "tool_calls": [{"arguments": secret}],
                },
            }
        ],
    }
    record = response_metadata(body, "gpt-4o-mini")
    assert record["finish_reason"] == reason
    assert record["verified_returned_model"] == body["model"]
    assert record["content_utf8_bytes"] == len(secret.encode())
    assert record["has_tool_calls"]
    assert secret not in json.dumps(record)


def test_unknown_fields_and_model_are_not_exported():
    body = {
        "model": "credential-echo",
        "choices": [
            {
                "finish_reason": "credential-echo",
                "message": {
                    "role": "credential-echo",
                    "refusal": "credential-echo",
                    "unknown-name": "credential-echo",
                    "content": "فارسی",
                },
            }
        ],
    }
    record = response_metadata(body, "gpt-4o-mini")
    assert record["finish_reason"] == "unknown"
    assert record["verified_returned_model"] is None
    assert record["content_utf8_bytes"] == len("فارسی".encode())
    assert "credential-echo" not in json.dumps(record)
    assert "unknown-name" not in json.dumps(record)


@pytest.mark.parametrize("body", [None, [], "private", {"choices": "private"}, {"choices": [None]}])
def test_malformed_envelopes_remain_shape_only(body):
    assert "private" not in json.dumps(response_metadata(body, "gpt-4o-mini"))


def test_observer_passes_exact_bytes_and_records_finish_reason():
    raw = json.dumps(
        {
            "model": "gpt-4o-mini",
            "choices": [
                {
                    "finish_reason": "length",
                    "message": {"role": "assistant", "content": "unfinished"},
                }
            ],
        }
    ).encode()
    response = httpx.Response(200, content=raw)
    record = {}
    observed = ObservedStream(response, record, "gpt-4o-mini")
    assert b"".join(observed) == raw
    assert record["finish_reason"] == "length"
    assert "unfinished" not in json.dumps(record)


def test_transport_error_message_is_never_exported():
    assert transport_category(httpx.ReadTimeout("private-key")) == "read_timeout"
    assert transport_category(RuntimeError("private-key")) == "transport_failure"


def test_oversized_response_is_not_parsed_or_logged():
    raw = b"x" * 262_145
    record = {}
    assert b"".join(ObservedStream(httpx.Response(200, content=raw), record, "gpt-4o-mini")) == raw
    assert record == {"envelope_shape": "oversized"}
