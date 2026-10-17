"""Bounded optional provider diagnostics, never arbitrary observer/model content."""

import re

from agent_app.orchestration.core_delivery import validated_delivery_binding


def _need(condition):
    if not condition:
        raise ValueError("ProviderObservationsUnavailable")


def _count(value, maximum):
    return type(value) is int and 0 <= value <= maximum


def _hash(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def optional_provider_metadata(row, *, request_id):
    """Validate optional allowlisted fields; caller validates the base identity.

    Copy only known primitive values. A caller-supplied receipt remains a
    declaration, not authentication of runtime, source/build or model quality.
    """
    output = {}
    if "core_binding" in row:
        output["core_binding"] = validated_delivery_binding(row["core_binding"])
        _need(output["core_binding"]["observed_metis"]["model"] == row["requested_model"])
    if "wire_output" not in row:
        return output
    wire = row["wire_output"]
    if wire is None:
        output["wire_output"] = None
        return output
    fields = {
        "request_id",
        "schema_version",
        "wire_format",
        "raw_output_sha256",
        "raw_utf8_bytes",
        "json_shape",
        "decision",
        "sources_count",
        "selected_indexes",
        "wire_schema_valid",
        "canonical_binding_valid",
        "rejection_code",
        "unexpected_field_count",
    }
    _need(type(wire) is dict and set(wire) == fields)
    _need(type(wire["request_id"]) is str and wire["request_id"] == request_id)
    _need(type(wire["schema_version"]) is int and wire["schema_version"] == 1)
    _need(type(wire["wire_format"]) is str and wire["wire_format"] == "grounded-indexed-plan-v1")
    _need(wire["raw_output_sha256"] is None or _hash(wire["raw_output_sha256"]))
    _need(wire["raw_utf8_bytes"] is None or _count(wire["raw_utf8_bytes"], 262144))
    _need(type(wire["json_shape"]) is str and wire["json_shape"] in {"invalid", "object", "other"})
    _need(
        wire["decision"] is None
        or (
            type(wire["decision"]) is str
            and wire["decision"] in {"answer", "ask", "escalate", "retrieve_more"}
        )
    )
    _need(wire["sources_count"] is None or _count(wire["sources_count"], 262144))
    indexes = wire["selected_indexes"]
    _need(
        indexes is None
        or (type(indexes) is list and len(indexes) <= 8 and all(_count(x, 99) for x in indexes))
    )
    _need(type(wire["wire_schema_valid"]) is bool and type(wire["canonical_binding_valid"]) is bool)
    _need(not wire["canonical_binding_valid"] or wire["wire_schema_valid"])
    _need(
        wire["rejection_code"] is None
        or (
            type(wire["rejection_code"]) is str
            and wire["rejection_code"]
            in {"invalid_grounded_plan", "grounded_context_mismatch", "grounded_source_mismatch"}
        )
    )
    _need((wire["rejection_code"] is None) == wire["canonical_binding_valid"])
    _need(_count(wire["unexpected_field_count"], 262144))
    if wire["wire_schema_valid"]:
        _need(
            wire["json_shape"] == "object"
            and wire["decision"] is not None
            and _hash(wire["raw_output_sha256"])
            and type(wire["raw_utf8_bytes"]) is int
            and wire["raw_utf8_bytes"] > 0
            and wire["unexpected_field_count"] == 0
        )
    if wire["canonical_binding_valid"]:
        if wire["decision"] == "retrieve_more":
            _need(wire["sources_count"] is None and indexes is None)
        else:
            _need(indexes is not None and wire["sources_count"] == len(indexes))
            _need(len(indexes) == len(set(indexes)))
            _need(wire["decision"] != "answer" or len(indexes) >= 1)
    output["wire_output"] = {
        key: list(value) if type(value) is list else value for key, value in wire.items()
    }
    return output
