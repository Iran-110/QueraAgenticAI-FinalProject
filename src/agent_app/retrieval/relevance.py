"""Pure candidate ordering; relevance signals never establish evidence authority.

Only supplied queries, current complete candidate records and native positions
contribute. There is no case vocabulary, version inference, source allowlist or
cached corpus. The engine separately enforces confirmed USER version scope.
"""

import math
import re
from collections import Counter
from urllib.parse import unquote, urlsplit

from agent_app.contracts import EvidenceHit

_WORDS = re.compile(r"\w+", re.UNICODE)
_API = re.compile(r"(?<![\w.])(?:st|streamlit)\.([a-z_]\w*)", re.IGNORECASE)


def _tokens(text):
    return Counter(_WORDS.findall(text.casefold()))


def _identities(hit):
    """Primary metadata names, never APIs merely mentioned inside an excerpt."""
    identities = set(_API.findall(hit.source_id.casefold()))
    path = unquote(urlsplit(hit.source_url).path).casefold()
    identities.update(_API.findall(path))
    for value in (hit.source_id.casefold(), path):
        basename = value.rsplit("/", 1)[-1]
        if basename.endswith((".md", ".html")):
            name = basename.rsplit(".", 1)[0].replace("-", "_")
            if re.fullmatch(r"[a-z_]\w*", name):
                identities.add(name)
    return identities


def _reciprocal_rank(positions):
    # Repeated rows from the same read do not manufacture extra rank votes.
    best = {}
    for query_index, collection, rank in positions:
        key = (query_index, collection)
        best[key] = min(rank, best.get(key, rank))
    return sum(1 / (60 + best[key]) for key in sorted(best))


def rank_candidates(hits, queries, positions) -> tuple[EvidenceHit, ...]:
    """Order validated complete hits, preferring source diversity before extras.

    Explicit query API identities precede bare API names, then the best lexical
    cosine across queries and native reciprocal rank. All remaining ties use
    stable IDs. Numeric query words have no version-filtering authority.
    """
    hits, queries = tuple(hits), tuple(queries)
    if not hits:
        return ()
    document_terms = {hit.chunk_id: _tokens(hit.excerpt) for hit in hits}
    query_terms = tuple(_tokens(query) for query in queries)
    explicit_apis = {name for query in queries for name in _API.findall(query.casefold())}
    bare_terms = {term for terms in query_terms for term in terms}
    frequencies = Counter(term for terms in document_terms.values() for term in terms)
    count = len(hits)

    def idf(term):
        return math.log((1 + count) / (1 + frequencies[term])) + 1

    def weighted(terms):
        return {term: (1 + math.log(amount)) * idf(term) for term, amount in terms.items()}

    query_vectors = tuple(weighted(terms) for terms in query_terms)
    query_norms = tuple(
        math.sqrt(sum(value * value for value in vector.values())) for vector in query_vectors
    )

    def key(hit):
        identities = _identities(hit)
        document = weighted(document_terms[hit.chunk_id])
        norm = math.sqrt(sum(value * value for value in document.values()))
        lexical = max(
            (
                sum(value * document.get(term, 0) for term, value in query.items())
                / (query_norm * norm)
                if query_norm and norm
                else 0
                for query, query_norm in zip(query_vectors, query_norms, strict=True)
            ),
            default=0,
        )
        return (
            -len(identities & explicit_apis),
            -len(identities & bare_terms),
            -lexical,
            -_reciprocal_rank(positions.get(hit.chunk_id, ())),
            hit.source_id,
            hit.chunk_id,
        )

    first, supplementary, seen_sources = [], [], set()
    for hit in sorted(hits, key=key):
        if hit.source_id in seen_sources:
            supplementary.append(hit)
        else:
            seen_sources.add(hit.source_id)
            first.append(hit)
    return tuple((*first, *supplementary))
