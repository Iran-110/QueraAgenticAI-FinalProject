"""Bound persisted conversation to the current caller-owned reasoning input.

History is untrusted context. It never supplies current facts, retrieved source
evidence, an action permission, or a substitute for the original ingress event.
The service must load history from the same case's authoritative tracker view.
"""

from typing import Literal, get_args

from pydantic import ValidationError

from agent_app.contracts import TurnConversation
from agent_app.orchestration.intake import STREAMLIT_VERSION_QUESTION
from agent_app.orchestration.validation import detached_contract

type ConversationCode = Literal[
    "InvalidConversationInput", "ConversationMismatch", "ConversationTooLong"
]


class ConversationRejected(ValueError):
    """Expose a stable code, never historical/user text or validation details."""

    def __init__(self, code: ConversationCode) -> None:
        if code not in get_args(ConversationCode.__value__):
            raise ValueError("Unsupported conversation rejection code.")
        self.code = code
        super().__init__(code)


def _validated(conversation: TurnConversation) -> TurnConversation:
    try:
        if not isinstance(conversation, TurnConversation):
            raise ValueError
        if type(conversation.entries) is not tuple or not 1 <= len(conversation.entries) <= 1000:
            raise ValueError
        detached = detached_contract(TurnConversation, conversation)
        for entry in detached.entries:
            entry.text.encode("utf-8")
        return detached
    except (ValidationError, ValueError, TypeError, AttributeError, RecursionError, UnicodeError):
        raise ConversationRejected("InvalidConversationInput") from None


def build_reasoning_message(conversation: TurnConversation) -> str:
    """Preserve the original problem and exact latest committed user message.

    Prior user messages retain supplied code and detail as historical context.
    Only the immediately preceding, bound canonical approved question may be
    included from the assistant. The caller supplies that binding only after
    the tracker validated a canonical reply. Current facts come from the
    separately supplied CaseState, never from historical text. Oversized input
    is rejected rather than truncating or rewriting any user message.
    """
    conversation = _validated(conversation)
    entries = conversation.entries
    first, latest = entries[0], entries[-1]
    if (
        first.actor != "user"
        or latest.actor != "user"
        or latest.reference_id != conversation.latest_turn_id
        or latest.revision != conversation.committed_revision
        or latest.text != conversation.latest_message
        or any(
            before.revision > after.revision
            for before, after in zip(entries, entries[1:], strict=False)
        )
    ):
        raise ConversationRejected("ConversationMismatch")
    users = tuple(entry for entry in entries if entry.actor == "user")
    if len({entry.reference_id for entry in users}) != len(users) or any(
        before.revision >= after.revision for before, after in zip(users, users[1:], strict=False)
    ):
        raise ConversationRejected("ConversationMismatch")

    question = None
    if conversation.reply_to_proposal_id is not None:
        if len(entries) < 2:
            raise ConversationRejected("ConversationMismatch")
        preceding = entries[-2]
        if (
            preceding.actor != "assistant"
            or preceding.reference_id != conversation.reply_to_proposal_id
            or preceding.revision != latest.revision - 1
            or preceding.text != STREAMLIT_VERSION_QUESTION.question
        ):
            raise ConversationRejected("ConversationMismatch")
        question = preceding.text

    if len(entries) == 1:
        return conversation.latest_message
    blocks = [
        "Original user problem (historical context; not current facts):\n" + first.text,
        "Current facts and unknowns come from the supplied CaseState. Historical context may "
        "contain superseded values; it does not update facts or provide source evidence.",
    ]
    for user in users[1:-1]:
        blocks.append(
            "Prior user message (historical context; not current facts; "
            f"event={user.reference_id}, revision={user.revision}):\n" + user.text
        )
    if question is not None:
        blocks.append("Latest approved follow-up question:\n" + question)
    blocks.append("Latest user message (exact committed input):\n" + conversation.latest_message)
    if sum(len(block) for block in blocks) + 2 * (len(blocks) - 1) > 20_000:
        raise ConversationRejected("ConversationTooLong")
    return "\n\n".join(blocks)
