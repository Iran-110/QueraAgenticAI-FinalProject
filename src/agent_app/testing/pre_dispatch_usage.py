"""Narrow future measurement for a trusted pre-reservation context guard.

An absent ledger row alone never establishes a free request. Only the owning
real gateway's typed ContextLimitExceeded with captured ledger/transport absence
before and after is eligible. Serialized attestations are caller declarations,
not cryptographic authentication. Historical receipts are never amended here.
"""

import hashlib
import json
from collections.abc import Sequence

from agent_app.contracts import ReasoningContext
from agent_app.evaluation.runner import Usage
from agent_app.llm.grounded import MetisGroundedPlanner
from agent_app.llm.metis import MetisReasoner, request_id_for
from agent_app.orchestration.ports import ReasoningStopped

_KEYS = {
    "schema_version",
    "request_id",
    "context_sha256",
    "stop_code",
    "gateway_kind",
    "ledger_absent_before",
    "ledger_absent_after",
    "transport_absent_before",
    "transport_absent_after",
}


def _context_hash(context):
    return hashlib.sha256(
        json.dumps(context.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def transport_absent(records, request_id):
    """Even a pre-send marker with http_send_started=False blocks zero cost."""
    return all(
        type(record) is dict
        and type(record.get("request_id")) is str
        and bool(record["request_id"])
        and record["request_id"] != request_id
        for record in records
    )


def attest_pre_dispatch_stop(
    gateway,
    counted,
    context,
    error,
    *,
    ledger_absent_before,
    transport_absent_before,
):
    """Called only around gateway.plan by its trusted owned planner wrapper."""
    request_id = request_id_for(context)
    if not (
        type(gateway) is MetisGroundedPlanner
        and type(gateway.reasoner) is MetisReasoner
        and gateway.reasoner.ledger is counted.ledger
        and type(error) is ReasoningStopped
        and error.code == "ContextLimitExceeded"
        and ledger_absent_before is True
        and transport_absent_before is True
        and counted.ledger.get(request_id) is None
        and transport_absent(counted.records, request_id)
    ):
        return None
    return {
        "schema_version": 1,
        "request_id": request_id,
        "context_sha256": _context_hash(context),
        "stop_code": "ContextLimitExceeded",
        "gateway_kind": "MetisGroundedPlanner",
        "ledger_absent_before": True,
        "ledger_absent_after": True,
        "transport_absent_before": True,
        "transport_absent_after": True,
    }


def _eligible(ledger, context, attempts, transport_records):
    request_id = request_id_for(context)
    try:
        observed = [
            attempt
            for attempt in attempts
            if request_id_for(ReasoningContext.model_validate(attempt.get("context"))) == request_id
        ]
    except (ValueError, TypeError, AttributeError):
        return False
    if len(observed) != 1:
        return False
    attempt = observed[0]
    if attempt.get("context") != context.model_dump(mode="json"):
        return False
    attestation = attempt.get("pre_dispatch_stop")
    return (
        type(attestation) is dict
        and set(attestation) == _KEYS
        and type(attestation["schema_version"]) is int
        and attestation["schema_version"] == 1
        and attestation["request_id"] == request_id
        and attestation["context_sha256"] == _context_hash(context)
        and attestation["gateway_kind"] == "MetisGroundedPlanner"
        and attempt.get("error_code") == attestation["stop_code"] == "ContextLimitExceeded"
        and all(
            attestation[name] is True
            for name in (
                "ledger_absent_before",
                "ledger_absent_after",
                "transport_absent_before",
                "transport_absent_after",
            )
        )
        and ledger.get(request_id) is None
        and transport_absent(transport_records, request_id)
    )


class PreDispatchUsage:
    """Scope-controlled driver accounting; the ordinary runner remains unchanged.

    ledger=None preserves ScopedUsage's existing bespoke-scope preflight. All
    amounts/statuses for reserved, uncertain, sent or unattested requests still
    come from Usage and the actual ledger. Normal outputs are byte-equivalent.
    """

    ledger = None

    def __init__(self, ledger, attempts, transport_records):
        self.actual = Usage(ledger)
        self.attempts = attempts
        self.transport_records = transport_records

    def measure(self, contexts: Sequence[ReasoningContext]):
        contexts = list(contexts)
        ordinary = self.actual.measure(contexts)
        eligible = {
            request_id_for(context): context
            for context in contexts
            if _eligible(self.actual.ledger, context, self.attempts, self.transport_records)
        }
        eligible = {
            record["request_id"]: eligible[record["request_id"]]
            for record in ordinary["requests"]
            if record["request_id"] in eligible and record["status"] == "unrecorded"
        }
        if not eligible:
            return ordinary
        retained = self.actual.measure(
            [context for context in contexts if request_id_for(context) not in eligible]
        )
        records = []
        retained_records = {record["request_id"]: record for record in retained["requests"]}
        for record in ordinary["requests"]:
            request_id = record["request_id"]
            if request_id in eligible and record["status"] == "unrecorded":
                records.append(
                    {
                        "request_id": request_id,
                        "context": eligible[request_id].model_dump(mode="json"),
                        "status": "skipped_before_reservation",
                        "cost_usd": "0",
                        "reserved_amount_usd": "0",
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "error_code": "ContextLimitExceeded",
                    }
                )
            else:
                records.append(retained_records.get(request_id, record))
        return {**retained, "requests": records}
