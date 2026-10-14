"""Bounded, allowlisted metadata for experiments; never raw response/error text."""

import json

import httpx

from agent_app.llm.pricing import same_verified_price

FINISH_REASONS = frozenset({"stop", "length", "content_filter", "tool_calls", "function_call"})


def transport_category(error):
    for cls, label in (
        (httpx.ReadTimeout, "read_timeout"),
        (httpx.ConnectTimeout, "connect_timeout"),
        (httpx.WriteTimeout, "write_timeout"),
        (httpx.PoolTimeout, "pool_timeout"),
        (httpx.TransportError, "transport_error"),
    ):
        if isinstance(error, cls):
            return label
    return "transport_failure"


def response_metadata(body, requested_model):
    if type(body) is not dict:
        return {"envelope_shape": "invalid"}
    observed = {"envelope_shape": "object", "verified_returned_model": None}
    model = body.get("model")
    if type(model) is str and same_verified_price(requested_model, model):
        observed["verified_returned_model"] = model
    choices = body.get("choices")
    if type(choices) is not list:
        observed["choice_count"] = None
        return observed
    observed["choice_count"] = len(choices)
    if len(choices) != 1 or type(choices[0]) is not dict:
        return observed
    choice = choices[0]
    reason = choice.get("finish_reason")
    observed["finish_reason"] = (
        reason if type(reason) is str and reason in FINISH_REASONS else "unknown"
    )
    message = choice.get("message")
    if type(message) is not dict:
        return observed
    content = message.get("content")
    try:
        content_bytes = len(content.encode("utf-8")) if type(content) is str else None
    except UnicodeError:
        content_bytes = None
    observed.update(
        assistant_role=message.get("role") == "assistant",
        content_utf8_bytes=content_bytes,
        has_tool_calls=bool(message.get("tool_calls")),
        has_function_call=bool(message.get("function_call")),
        has_refusal=bool(message.get("refusal")),
    )
    return observed


class ObservedStream(httpx.SyncByteStream):
    def __init__(self, response, record, model):
        self.response, self.record, self.model = response, record, model

    def __iter__(self):
        bounded = bytearray()
        overflow = False
        try:
            for chunk in self.response.iter_bytes():
                if len(bounded) + len(chunk) > 262_144:
                    bounded.clear()
                    overflow = True
                elif not overflow:
                    bounded.extend(chunk)
                yield chunk
        except Exception as error:
            self.record["transport_error_category"] = transport_category(error)
            raise
        if overflow:
            self.record["envelope_shape"] = "oversized"
        else:
            try:
                body = json.loads(bounded)
            except (ValueError, UnicodeError):
                self.record["envelope_shape"] = "invalid_json"
            else:
                self.record.update(response_metadata(body, self.model))

    def close(self):
        self.response.close()
