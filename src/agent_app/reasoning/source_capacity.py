"""Compact optional renderer-capacity guidance, never source selection authority.

Only existing count bounds change on the wire. Full current source records stay
available, and the unchanged renderer validates the actual plan. The conservative
common count can exclude feasible smaller-source combinations; it says nothing
about their relevance, support, authenticity or usefulness.
"""

import json

from agent_app.reasoning.grounding import _prior_conflict, validate_grounded_request
from agent_app.reasoning.resource_guidance import _render_resources


def source_capacity(request, *, source_gap_handoff=False, source_gap_investigation=False):
    """Return a positive common bound, or None when this method cannot advise.

    Conflicts are deliberately outside this method: their mandatory union must
    never be hidden by a source-count rule. Likewise, an unrenderable singleton
    or decision base does not justify excluding every source from the model.
    """
    if any(type(flag) is not bool for flag in (source_gap_handoff, source_gap_investigation)) or (
        source_gap_investigation and not source_gap_handoff
    ):
        raise ValueError("SourceCapacityFlagsInvalid")
    request = validate_grounded_request(request)
    if not request.evidence.hits or request.conflict_groups or _prior_conflict(request):
        return None
    resources = _render_resources(
        request,
        source_gap_handoff=source_gap_handoff,
        source_gap_investigation=source_gap_investigation,
    )
    bases, limits = resources["bases"], resources["limits"]
    if any(type(base) is not list for base in bases.values()):
        return None
    costs = sorted(resources["source_chars"], reverse=True)
    accepted, total = 0, 0
    for count, cost in enumerate(costs[:8], 1):
        total += cost
        quotes = total + 2 * (count - 1)
        if any(
            base[0] + (quotes if decision == "answer" else 0) > limits[0]
            or base[1] + quotes + 2 > limits[1]
            or base[2] > limits[2]
            for decision, base in bases.items()
        ):
            break
        accepted = count
    if not accepted:
        return None
    # If the whole available pool fits, the existing schema needs no tightening.
    return 8 if accepted == min(len(costs), 8) else accepted


def add_source_capacity(
    messages,
    request,
    *,
    enabled=False,
    source_gap_handoff=False,
    source_gap_investigation=False,
):
    """Recompute from this request; no cache, extra prompt, mutation or clipping."""
    if any(
        type(flag) is not bool for flag in (enabled, source_gap_handoff, source_gap_investigation)
    ) or (source_gap_investigation and not source_gap_handoff):
        raise ValueError("SourceCapacityFlagsInvalid")
    if not enabled:
        return messages
    try:
        request = validate_grounded_request(request)
        if (
            type(messages) is not tuple
            or len(messages) != 2
            or any(
                type(message) is not dict
                or set(message) != {"role", "content"}
                or type(message["content"]) is not str
                or not message["content"]
                for message in messages
            )
            or messages[0]["role"] != "system"
            or messages[1]["role"] != "user"
        ):
            raise ValueError
        payload = json.loads(messages[1]["content"])
        if payload["request"] != request.model_dump(mode="json"):
            raise ValueError
        contracts = payload["decision_contracts"]
        schema_sources = payload["response_schema"]["properties"]["sources"]
        if contracts["schema_id"] != "grounded-decision-fields-v1":
            raise ValueError
        bound = source_capacity(
            request,
            source_gap_handoff=source_gap_handoff,
            source_gap_investigation=source_gap_investigation,
        )
        if bound is None or bound >= schema_sources["maxItems"]:
            return messages
        schema_sources["maxItems"] = bound
        for rule in contracts["rules"].values():
            rule["sources"]["maxItems"] = min(rule["sources"]["maxItems"], bound)
    except (AttributeError, KeyError, TypeError, ValueError, RecursionError):
        raise ValueError("SourceCapacityMessagesInvalid") from None
    return (
        dict(messages[0]),
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, sort_keys=True)},
    )
