"""Current-installation search context, separate from exact reasoning history.

Historical words are lexical topic hints, never facts or source evidence. This
projection intentionally loses numeric historical details; current raw code and
comparisons remain unmodified in the latest input and complete reasoning history.
"""

import re

from agent_app.contracts import CaseState, TurnConversation
from agent_app.orchestration.conversation import ConversationRejected, build_reasoning_message
from agent_app.orchestration.validation import detached_contract

_WORDS = re.compile(r"\w+(?:\.\w+)*", re.UNICODE)
_PRIORITY = {
    name: index
    for index, name in enumerate(
        (
            "streamlit_version",
            "python_version",
            "operating_system",
            "browser_version",
            "error_message",
            "widget_definition",
        )
    )
}


def _terms(text):
    # A standalone lexer on caller-owned historical user entries, never parsing
    # conversation headers or interpreting snippets. Digit-bearing identifiers
    # are omitted as whole terms, rather than turning 1.50 into asserted facts.
    return tuple(
        word.rstrip(".")
        for word in _WORDS.findall(text)
        if not any(char.isdigit() for char in word)
    )


def build_current_query(case: CaseState, conversation: TurnConversation) -> str:
    """Pack confirmed current parameters, latest input and bounded topic hints.

    Validates the exact same complete conversation as reasoning before deriving
    anything. This does not discover facts, sanitize source content, filter RAG
    results or constrain model-authored refinement queries.
    """
    try:
        case = detached_contract(CaseState, case)
        conversation = detached_contract(TurnConversation, conversation)
        build_reasoning_message(conversation)
        if case.case_revision != conversation.committed_revision:
            raise ValueError
        unknown = {name.casefold() for name in case.unknowns}
        active = tuple(
            fact
            for fact in case.facts
            if fact.status == "active" and fact.provenance_kind == "user"
        )
        if any(fact.name.casefold() in unknown for fact in active):
            raise ValueError
    except ConversationRejected:
        raise
    except Exception:
        raise ConversationRejected("InvalidConversationInput") from None

    facts = sorted(
        active,
        key=lambda fact: (
            _PRIORITY.get(fact.name.casefold(), len(_PRIORITY)),
            fact.name.casefold(),
        ),
    )
    packed = []
    for fact in facts:
        value = " ".join(fact.value.split())
        item = f"{fact.name}={value}"
        if len("; ".join((*packed, item))) <= 180:
            packed.append(item)
    parameters = "; ".join(packed)
    latest = " ".join(conversation.latest_message.split())
    earlier_users = tuple(entry for entry in conversation.entries[:-1] if entry.actor == "user")
    latest_limit = 400 if not earlier_users else 240
    blocks = [parameters, latest[:latest_limit]] if parameters else [latest[:latest_limit]]
    # Only topic terms are filtered. Never edit the latest event, exact code,
    # model message or historical transcript. Retired words that are current
    # again (A->B->A) remain permitted as topic hints.
    current_terms = {term.casefold() for fact in active for term in _terms(fact.value)}
    retired_terms = {
        term.casefold()
        for fact in case.facts
        if fact.status == "superseded" and fact.provenance_kind == "user"
        for term in _terms(fact.value)
    } - current_terms
    seen = set()
    hints = []
    terms = [term for entry in earlier_users for term in _terms(entry.text)]
    # Actual st.* identifiers supplied in earlier code get space alongside the
    # original complaint; this is lexical retention, not code execution/analysis.
    terms.sort(key=lambda term: not term.casefold().startswith("st."))
    for term in terms:
        folded = term.casefold()
        if not term or folded in seen or folded in retired_terms:
            continue
        seen.add(folded)
        if len(" ".join((*hints, term))) <= 120:
            hints.append(term)
    if hints:
        blocks.append("topic: " + " ".join(hints))
    query = " | ".join(blocks)
    # Whole facts are never partially packed; the latest text is only a bounded
    # search projection. Reasoning still receives its exact 20k-bound transcript.
    return query[:500]
