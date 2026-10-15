"""Optional caller-bound context for advisory lexical inspection only.

The caller must load the case and conversation from the same authoritative case
view. Exact content binding is not authentication and cannot prove the origin of
otherwise identical histories. This context never changes reasoning messages,
retrieval, facts, source evidence, model decisions or tracker authority.
"""

import hashlib
import json
from typing import Annotated

from pydantic import StringConstraints

from agent_app.contracts import CaseState, Contract, Sha256, TurnConversation
from agent_app.orchestration.conversation import build_reasoning_message
from agent_app.orchestration.retrieval_context import build_current_query
from agent_app.orchestration.validation import detached_contract
from agent_app.reasoning.claim_plan import ClaimRequest, validate_claim_request
from agent_app.reasoning.grounding import GroundingRejected


class EvidenceQueryContext(Contract):
    request_context_sha256: Sha256
    case: CaseState
    conversation: TurnConversation
    # Keep the helper's exact bounded projection, including a possible boundary
    # space. The shared Query alias trims whitespace and would change its bytes.
    current_query: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=500)]
    context_sha256: Sha256


def _digest(payload):
    raw = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(b"evidence-query-context-v1:" + raw).hexdigest()


def _conversation_tuple(conversation):
    # Preserve build_reasoning_message's explicit raw tuple boundary before
    # generic Pydantic detachment could normalize a bypassed list into a tuple.
    if not isinstance(conversation, TurnConversation) or type(conversation.entries) is not tuple:
        raise ValueError


def build_evidence_query_context(
    request: ClaimRequest, case: CaseState, conversation: TurnConversation
) -> EvidenceQueryContext:
    """Bind a typed current projection to the full actual request and history.

    Recursive detachment precedes every dump: nested extra attributes reject,
    and declared Python values are revalidated before JSON serialization. The existing projection
    validates ordering/latest-turn/question/revision and preserves A→B→A topic
    reuse. Nothing parses factual authority out of history headers or prose.
    """
    try:
        request = validate_claim_request(detached_contract(ClaimRequest, request))
        case = detached_contract(CaseState, case)
        _conversation_tuple(conversation)
        conversation = detached_contract(TurnConversation, conversation)
        if (
            case != request.grounded.case
            or case.case_revision != conversation.committed_revision
            or build_reasoning_message(conversation).strip() != request.grounded.user_message
        ):
            raise ValueError
        current_query = build_current_query(case, conversation)
        payload = {
            "request_context_sha256": request.context_sha256,
            "case": case.model_dump(mode="json"),
            "conversation": conversation.model_dump(mode="json"),
            "current_query": current_query,
        }
        return EvidenceQueryContext(**payload, context_sha256=_digest(payload))
    except Exception:
        raise GroundingRejected("grounded_context_mismatch") from None


def validate_evidence_query_context(
    request: ClaimRequest, context: EvidenceQueryContext
) -> EvidenceQueryContext:
    """Rebuild all bindings; a provided invalid context never falls back."""
    try:
        if not isinstance(context, EvidenceQueryContext):
            raise ValueError
        _conversation_tuple(context.conversation)
        context = detached_contract(EvidenceQueryContext, context)
        rebuilt = build_evidence_query_context(request, context.case, context.conversation)
        if context != rebuilt:
            raise ValueError
        return context
    except Exception:
        raise GroundingRejected("grounded_context_mismatch") from None
