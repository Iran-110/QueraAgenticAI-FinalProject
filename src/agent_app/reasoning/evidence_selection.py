"""Current-input evidence hints, never an entailment or authorization gate.

Whole-section units prevent a class of syntactic omissions. Lexical overlap is
only a cheap inspection aid: a faithful complete section can still be irrelevant,
and a zero-overlap passage can still be useful. These helpers neither modify a
model decision nor enter normal factories, model messages or retrieval ranking.
"""

import math
import re
from collections import Counter
from dataclasses import dataclass

from agent_app.orchestration.validation import detached_contract
from agent_app.reasoning.claim_plan import (
    ClaimRequest,
    claim_block_has_body,
    parse_claim_plan,
    validate_claim_request,
)
from agent_app.reasoning.grounding import GroundingRejected, source_scope
from agent_app.reasoning.selection_context import (
    EvidenceQueryContext,
    validate_evidence_query_context,
)

_WORDS = re.compile(r"[^\W_]+", re.UNICODE)
_STOP = frozenset(
    "a an and are as at be been but by can could did do does for from had has have "
    "how i if in into is it its me my of on or our please so some than that the their "
    "them then there these they this those to was we were what when where which while "
    "who why will with would you your "
    "از است این با به برای بود را در رو که من می ما یک یا و ها".split()
)


@dataclass(frozen=True)
class EvidenceUnitHint:
    source_index: int
    block_index: int
    overlap: float
    matched_terms: int
    has_body: bool
    version_scope: str
    passage_utf8_bytes: int


@dataclass(frozen=True)
class EvidenceShortlist:
    context_sha256: str
    passages: tuple[tuple[int, int], ...]
    passage_utf8_bytes: int
    oversized: tuple[tuple[int, int], ...]
    historical: tuple[tuple[int, int], ...]
    # This is deliberately not a bool score masquerading as semantic review.
    semantic_support: None = None
    human_review_required: bool = True


@dataclass(frozen=True, kw_only=True)
class ContextualEvidenceShortlist(EvidenceShortlist):
    query_context_sha256: str


def _terms(text):
    # Numeric environment strings never grant version scope through overlap.
    return Counter(
        term
        for term in _WORDS.findall(text.casefold())
        if len(term) > 1 and not term.isdecimal() and term not in _STOP
    )


def _validated_inputs(request, query_context):
    if query_context is None:
        # Preserve the historical no-context path and serialized output fields.
        return validate_claim_request(request), None
    try:
        request = validate_claim_request(detached_contract(ClaimRequest, request))
        return request, validate_evidence_query_context(request, query_context)
    except Exception:
        raise GroundingRejected("grounded_context_mismatch") from None


def rank_evidence_units(
    request: ClaimRequest, *, query_context: EvidenceQueryContext | None = None
) -> tuple[EvidenceUnitHint, ...]:
    """Rank current units by advisory IDF-cosine against current USER input.

    Only passage text contributes document terms; metadata names and identifiers
    cannot manufacture relevance. Superseded/evidence/inference fact ROWS are
    not query terms. The supplied message may still contain historical prose;
    this helper does not parse or certify its factual freshness. Full-source
    and case hashes are checked before inspection. An optional bound typed
    context uses the existing current-query projection; omitted context retains
    the complete historical-message behavior exactly.
    """
    request, query_context = _validated_inputs(request, query_context)
    grounded = request.grounded
    current_values = "\n".join(
        fact.value
        for fact in grounded.case.facts
        if fact.status == "active" and fact.provenance_kind == "user"
    )
    if query_context is None:
        query = _terms(grounded.user_message + "\n" + current_values)
    else:
        # The helper's labels and fact names are not USER-provided text. A
        # projected token must also occur in actual USER entries or active USER
        # values. Old words can still survive in latest negation/unretired hints;
        # this is a lexical provenance control, never semantic understanding.
        origin = _terms(
            "\n".join(
                entry.text for entry in query_context.conversation.entries if entry.actor == "user"
            )
            + "\n"
            + current_values
        )
        query = Counter(
            {
                term: count
                for term, count in _terms(query_context.current_query).items()
                if term in origin
            }
        )
        # Keep current code/long values even when the bounded search projection
        # cannot pack them; no source or reasoning message is shortened here.
        query.update(_terms(current_values))
    units = []
    for source, spans in enumerate(request.blocks):
        hit = grounded.evidence.hits[source]
        for block, span in enumerate(spans):
            text = hit.excerpt[span.start : span.end]
            units.append((source, block, text, _terms(text)))
    frequency = Counter(term for _, _, _, terms in units for term in terms)

    def weight(terms):
        return {
            term: (1 + math.log(count)) * (math.log((1 + len(units)) / (1 + frequency[term])) + 1)
            for term, count in terms.items()
        }

    query_vector = weight(query)
    query_norm = math.sqrt(sum(value * value for value in query_vector.values()))
    hints = []
    for source, block, text, terms in units:
        document = weight(terms)
        norm = math.sqrt(sum(value * value for value in document.values()))
        overlap = (
            sum(value * document.get(term, 0) for term, value in query_vector.items())
            / (query_norm * norm)
            if query_norm and norm
            else 0.0
        )
        hints.append(
            EvidenceUnitHint(
                source_index=source,
                block_index=block,
                overlap=min(1.0, max(0.0, overlap)),
                matched_terms=len(query.keys() & terms.keys()),
                has_body=claim_block_has_body(text),
                version_scope=source_scope(grounded.case, grounded.evidence.hits[source]),
                passage_utf8_bytes=len(text.encode("utf-8")),
            )
        )
    return tuple(sorted(hints, key=lambda h: (-h.overlap, h.source_index, h.block_index)))


def suggest_evidence_units(
    request: ClaimRequest,
    *,
    max_units: int = 2,
    passage_utf8_budget: int = 6_000,
    query_context: EvidenceQueryContext | None = None,
) -> EvidenceShortlist:
    """Return bounded whole-unit inspection suggestions, never a model answer.

    The byte budget counts raw passages only, NOT a total prompt/render/token
    allowance. Original evidence stays intact. Unknown-version docs may be
    considered, but exact version metadata still does not verify applicability.
    No extra model calls, retrieval queries, question selection or gap discovery
    occur. Lexical false positives/negatives must be reviewed.
    """
    if type(max_units) is not int or not 1 <= max_units <= 6:
        raise ValueError("InvalidEvidenceShortlistLimit")
    if type(passage_utf8_budget) is not int or passage_utf8_budget <= 0:
        raise ValueError("InvalidEvidenceShortlistBudget")
    request, query_context = _validated_inputs(request, query_context)
    ranked = rank_evidence_units(request, query_context=query_context)
    selected, oversized, historical = [], [], []
    used = 0
    for hint in ranked:
        ref = (hint.source_index, hint.block_index)
        if hint.version_scope == "historical_or_other_version":
            historical.append(ref)
            continue
        if not hint.has_body or hint.overlap <= 0:
            continue
        if used + hint.passage_utf8_bytes > passage_utf8_budget:
            oversized.append(ref)
            continue
        if len(selected) < max_units:
            selected.append(ref)
            used += hint.passage_utf8_bytes
    result = dict(
        context_sha256=request.context_sha256,
        passages=tuple(selected),
        passage_utf8_bytes=used,
        oversized=tuple(oversized),
        historical=tuple(historical),
    )
    return (
        EvidenceShortlist(**result)
        if query_context is None
        else ContextualEvidenceShortlist(
            **result, query_context_sha256=query_context.context_sha256
        )
    )


def inspect_claim_selection(
    request: ClaimRequest, raw, *, query_context: EvidenceQueryContext | None = None
) -> dict:
    """Report bounded lexical/structural observations of an EXISTING plan.

    A high overlap is never reported as supported or relevant. These observations
    do not reject a legitimate question or replace semantic/human evaluation.
    Old context/source/fact selections still fail instead of being silently
    rebound to the new case. No content or arbitrary field names enter warnings.
    """
    request, query_context = _validated_inputs(request, query_context)
    plan = parse_claim_plan(raw)
    if plan.context_sha256 != request.context_sha256:
        raise GroundingRejected("grounded_context_mismatch")
    active = tuple(
        f
        for f in request.grounded.case.facts
        if f.status == "active" and f.provenance_kind == "user"
    )
    if any(index >= len(active) for index in plan.user_facts):
        raise GroundingRejected("grounded_context_mismatch")
    ranked = rank_evidence_units(request, query_context=query_context)
    hints = {(h.source_index, h.block_index): h for h in ranked}
    if any(ref not in hints for ref in plan.passages):
        raise GroundingRejected("grounded_source_mismatch")
    warnings = []
    if any(not hints[ref].has_body for ref in plan.passages):
        warnings.append("heading_or_separator_only")
    if any(hints[ref].overlap <= 0 for ref in plan.passages):
        warnings.append("no_lexical_signal_not_proof_of_irrelevance")
    if any(hints[ref].version_scope == "historical_or_other_version" for ref in plan.passages):
        warnings.append("different_reported_version_not_runtime_verification")
    observation = {
        "schema_version": 1,
        "context_sha256": request.context_sha256,
        "decision_unchanged": plan.decision,
        "selected_units": len(plan.passages),
        "selected_raw_utf8_bytes": sum(hints[ref].passage_utf8_bytes for ref in plan.passages),
        "warnings": warnings,
        "semantic_support": None,
        "human_review_required": True,
    }
    if query_context is not None:
        observation.update(
            query_context_sha256=query_context.context_sha256,
            query_input_kind="bound_current_user_projection",
        )
    return observation
