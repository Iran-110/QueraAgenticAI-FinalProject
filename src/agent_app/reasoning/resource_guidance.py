"""Optional current-query and complete-quotation costs, never output authority.

The existing renderer supplies the decision bases and escaped source blocks.
No document, conflict, selected reference, query or guard is rewritten here.
Unmeasurable bases are reported with a fixed code rather than an invented bound.
"""

import json

from agent_app.contracts import AnalysisResult, GroundedPlan
from agent_app.reasoning.grounding import (
    GroundingRejected,
    _source_block,
    render_grounded_plan,
    source_content_sha256,
    validate_grounded_request,
)

RESOURCE_GUIDANCE = (
    "Current resource rules: retrieve_more queries must differ from every "
    "request.evidence.queries_used after whitespace split/join and casefold. "
    "Use relevant current USER/API terms, not a source-gap name alone. "
    "render_resources uses [user_draft,maintainer_summary,rationale] character counts. "
    "source_chars and mandatory indexes follow request.evidence.hits order. "
    "For selected union mandatory chunks, let n be its size and q=sum(source_chars) "
    "+2*(n-1) when n>0, else 0. Add q to the answer draft base; add q+2 to every "
    "summary base when n>0. Other fields keep their bases. All fields must fit "
    "limits. A fixed error instead of a base provides no size guarantee. "
    "Keep mandatory conflict chunks. Select relevant support, not all or merely "
    "the shortest sources. Guidance grants no extra capacity or approval."
)


def _render_resources(request, *, source_gap_handoff, source_gap_investigation):
    hits = request.evidence.hits
    costs = {hit.chunk_id: len(_source_block(request.case, hit)) for hit in hits}
    mandatory = {chunk for group in request.conflict_groups for chunk in group}
    mandatory = [hit.chunk_id for hit in hits if hit.chunk_id in mandatory]
    options = [("escalate", None, ())]
    options.extend(("ask", gap.name, ()) for gap in request.gaps if gap.kind == "user")
    # Any valid singleton supplies the same source-independent answer base. Try
    # later chunks if the first complete quotation cannot itself fit the limit.
    if hits:
        options.append(("answer", None, hits))
    bases = {}
    for decision, question_name, candidates in options:
        key = f"ask:{question_name}" if question_name is not None else decision
        for hit in candidates or (None,):
            references = (
                ({"chunk_id": hit.chunk_id, "content_sha256": source_content_sha256(hit)},)
                if hit is not None
                else ()
            )
            try:
                plan = GroundedPlan(
                    context_sha256=request.context_sha256,
                    decision=decision,
                    sources=references,
                    question_name=question_name,
                )
                actual = render_grounded_plan(
                    request,
                    plan,
                    source_gap_handoff=source_gap_handoff,
                    source_gap_investigation=source_gap_investigation,
                )
            except GroundingRejected as error:
                bases[key] = error.code
                continue
            selected = set(mandatory)
            if hit is not None:
                selected.add(hit.chunk_id)
            quote_chars = (
                sum(costs[chunk] for chunk in selected) + 2 * (len(selected) - 1) if selected else 0
            )
            bases[key] = [
                len(actual.user_draft) - (quote_chars if decision == "answer" else 0),
                len(actual.maintainer_summary) - (quote_chars + 2 if selected else 0),
                len(actual.rationale),
            ]
            break
    properties = AnalysisResult.model_json_schema()["properties"]
    return {
        "limits": [
            properties[name]["maxLength"]
            for name in ("user_draft", "maintainer_summary", "rationale")
        ],
        "source_chars": list(costs.values()),
        "mandatory": [i for i, hit in enumerate(hits) if hit.chunk_id in mandatory],
        "bases": bases,
    }


def add_resource_guidance(
    messages,
    request,
    *,
    enabled=False,
    source_gap_handoff=False,
    source_gap_investigation=False,
):
    """Keep disabled bytes exact; append bounded metadata from this request only."""
    if any(
        type(flag) is not bool for flag in (enabled, source_gap_handoff, source_gap_investigation)
    ) or (source_gap_investigation and not source_gap_handoff):
        raise ValueError("ResourceGuidanceFlagInvalid")
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
        if (
            type(payload) is not dict
            or payload.get("request") != request.model_dump(mode="json")
            or "render_resources" in payload
        ):
            raise ValueError
        payload["render_resources"] = _render_resources(
            request,
            source_gap_handoff=source_gap_handoff,
            source_gap_investigation=source_gap_investigation,
        )
    except (AttributeError, TypeError, ValueError, RecursionError):
        raise ValueError("ResourceGuidanceMessagesInvalid") from None
    return (
        {"role": "system", "content": messages[0]["content"] + "\n\n" + RESOURCE_GUIDANCE},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, sort_keys=True)},
    )
