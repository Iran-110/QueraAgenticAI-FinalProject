"""Prepare user-turn state updates without storage, model calls, or tool effects."""

import hashlib
import json
from typing import Literal

from pydantic import ValidationError

from agent_app.contracts import CaseState, CaseTransition, Fact, UserTurn
from agent_app.orchestration.validation import detached_contract


class UserTurnRejected(Exception):
    """A stable rejection code without user content in its message."""

    def __init__(
        self, code: Literal["CaseMismatch", "StaleRevision", "StateLimitExceeded"]
    ) -> None:
        if code not in {"CaseMismatch", "StaleRevision", "StateLimitExceeded"}:
            raise ValueError("Unknown user-turn rejection code")
        self.code = code
        super().__init__(code)


def _check_key(value: str) -> str:
    return " ".join(value.split()).casefold()


def _distinct(values: list[str], *, checks: bool = False) -> tuple[str, ...]:
    seen: set[str] = set()
    result = []
    for value in values:
        key = _check_key(value) if checks else value.casefold()
        if key not in seen:
            seen.add(key)
            result.append(value)
    return tuple(result)


def propose_user_turn(case: CaseState, turn: UserTurn) -> CaseTransition:
    """Transform an authoritative snapshot into a detached, uncommitted candidate.

    The tracker must deduplicate durable user events before calling this helper,
    then atomically compare revisions, save the event/state, and revoke approval.
    Free-text parsing and applying model-suggested facts are outside this boundary.
    """
    case = detached_contract(CaseState, case)
    turn = detached_contract(UserTurn, turn)
    if turn.case_id != case.case_id:
        raise UserTurnRejected("CaseMismatch")
    if turn.expected_revision != case.case_revision:
        raise UserTurnRejected("StaleRevision")

    facts = list(case.facts)
    active = {fact.name.casefold(): i for i, fact in enumerate(facts) if fact.status == "active"}
    changed: list[str] = []
    unknowns = list(case.unknowns) + list(turn.unknowns)
    context_changed = turn.context_changed
    prior_check_keys = {_check_key(check) for check in case.checks_performed}
    # A new check/result can contradict an existing inference without changing
    # any environment fact. Restating a normalized check adds no new knowledge.
    evidence_invalidated = turn.context_changed or any(
        _check_key(check) not in prior_check_keys for check in turn.checks_performed
    )
    reported_known = {
        fact.name.casefold() for fact in turn.reported_facts if fact.value is not None
    }

    for reported in turn.reported_facts:
        index = active.get(reported.name.casefold())
        previous = facts[index] if index is not None else None
        if previous is None and reported.value is None:
            unknowns.append(reported.name)
            continue  # An already absent value cannot invalidate another inference.
        if (
            previous is not None
            and previous.value == reported.value
            and previous.provenance_kind == "user"
            and not turn.context_changed
        ):
            continue  # A restatement preserves the original user attribution.
        if previous is not None:
            facts[index] = previous.model_copy(update={"status": "superseded"})
            if reported.value is None or previous.value != reported.value:
                context_changed = True
        # Even newly supplied information can disprove an old inference. With
        # no dependency graph, conservatively retire prior evidence conclusions.
        evidence_invalidated = True
        changed.append(previous.name if previous is not None else reported.name)
        if reported.value is None:
            unknowns.append(reported.name)
        else:
            facts.append(
                Fact(
                    name=reported.name,
                    value=reported.value,
                    source_ref=turn.source_ref,
                    turn_id=turn.turn_id,
                    provenance_kind="user",
                )
            )

    # On an explicit environment switch, unconfirmed user facts belong to the
    # previous environment. An ordinary correction keeps other user facts.
    for index, fact in enumerate(facts):
        if fact.status != "active":
            continue
        clear_user = (
            turn.context_changed
            and fact.provenance_kind == "user"
            and fact.name.casefold() not in reported_known
        )
        clear_evidence = evidence_invalidated and fact.provenance_kind == "evidence"
        if clear_user or clear_evidence:
            facts[index] = fact.model_copy(update={"status": "superseded"})
            changed.append(fact.name)
            unknowns.append(fact.name)

    known_names = {fact.name.casefold() for fact in facts if fact.status == "active"}
    unknowns = [name for name in unknowns if name.casefold() not in known_names]
    prior_checks = [] if context_changed else list(case.checks_performed)
    try:
        candidate = CaseState(
            case_id=case.case_id,
            case_revision=case.case_revision + 1,
            facts=tuple(facts),
            unknowns=_distinct(unknowns),
            checks_performed=_distinct(prior_checks + list(turn.checks_performed), checks=True),
            evidence_refs=() if evidence_invalidated else case.evidence_refs,
            pending_proposal_id=None,
        )
    except ValidationError:
        # Never silently discard attribution history to make a bounded state fit.
        raise UserTurnRejected("StateLimitExceeded") from None

    canonical = json.dumps(
        turn.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return CaseTransition(
        expected_revision=case.case_revision,
        turn_id=turn.turn_id,
        source_ref=turn.source_ref,
        event_hash=hashlib.sha256(canonical).hexdigest(),
        candidate=candidate,
        changed_fact_names=_distinct(changed),
        context_changed=context_changed,
        invalidated_checks=case.checks_performed if context_changed else (),
    )
