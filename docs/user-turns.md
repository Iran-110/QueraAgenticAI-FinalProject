# User turns and case corrections

This core utility proposes the next `CaseState` from an explicit structured user turn. It is a pure transformation: no database write, model call, or tool action. Durable tracker and UI integration remain the other owners' work. No API key or credit is needed for this path.

## Input and behavior

`orchestration.turns.propose_user_turn(case, turn)` returns a `CaseTransition` with an uncommitted `candidate`, `event_hash`, changed fact names, and invalidated checks. It receives the authoritative current case and a validated `UserTurn`, bound to that case and its expected revision. Facts come from explicit `ReportedFact(name, value)` entries; the helper does not parse `UserTurn.message` or guess missing values.

Use stable field names such as `streamlit_version` and `python_version`. Names are compared after trimming and casefolding; aliases such as `version` are not mapped automatically. Check descriptions are compared after collapsing whitespace and casefolding, not by semantic interpretation.

- A non-null value adds a known user fact or corrects its active value. `null` withdraws a fact instead of inventing a replacement.
- Withdrawing an already absent value only records it as unknown; it does not invalidate unrelated evidence or invent fact history.
- Superseded facts remain in provenance history. A turn that only restates active user values preserves their original sources, turns, and evidence, unless an environment switch is explicit.
- New, changed, or withdrawn reported facts and evidence-to-user promotion invalidate prior evidence-derived facts and evidence references, even if `CaseTransition.context_changed=False`. Invalidated fact names become unknown unless the turn supplies an active replacement.
- An ordinary value correction derives `CaseTransition.context_changed=True`, clears old unscoped checks, and preserves other user facts. Adding new known facts or promoting an unchanged evidence value to user provenance preserves completed checks.
- Explicit `UserTurn.context_changed=True` means a different environment: old user facts not reconfirmed in that turn also become unknown. Even an equal reconfirmed value gets attribution to the new environment's turn.
- A new accepted turn proposes one revision increment and invalidates the pending proposal. The tracker must also invalidate approval for the old revision.
- Wrong case binding or a stale expected revision is rejected. The helper does not silently merge competing updates.

The hash is SHA-256 of the validated turn's complete JSON, using `ensure_ascii=False`, `sort_keys=True`, and `separators=(",", ":")`, encoded as UTF-8. It includes `UserTurn.message`. Reusing the same event ID with a changed validated message is a conflict, even if its fact changes are identical. Do not deduplicate solely on the facts or trust a caller-supplied hash. Capacity overflow returns `UserTurnRejected("StateLimitExceeded")`; provenance history is never silently truncated.

## Two-turn offline example

Run this Python from the repository's uv environment. Both candidates stay in memory; a real integration must commit each one through the tracker before proceeding.

```python
from agent_app.contracts import CaseState, ReportedFact, UserTurn
from agent_app.orchestration.turns import propose_user_turn

initial = CaseState(case_id="case-17")
first = UserTurn(
    case_id="case-17", expected_revision=0, turn_id="turn-1", source_ref="user:turn-1",
    message="I use Streamlit 1.41.0 and Python 3.13; reinstalling did not help.",
    reported_facts=(
        ReportedFact(name="streamlit_version", value="1.41.0"),
        ReportedFact(name="python_version", value="3.13"),
    ),
    checks_performed=("Reinstalled Streamlit in this environment.",),
)
one = propose_user_turn(initial, first)
correction = UserTurn(
    case_id="case-17", expected_revision=1, turn_id="turn-2", source_ref="user:turn-2",
    message="Correction: the affected environment runs Streamlit 1.42.0.",
    reported_facts=(ReportedFact(name="streamlit_version", value="1.42.0"),),
)
two = propose_user_turn(one.candidate, correction)

print(two.candidate.case_revision)  # 2
print(two.context_changed)  # True: an ordinary correction was detected
print(two.candidate.checks_performed)  # (): cleared after the context correction
print([(fact.value, fact.status) for fact in two.candidate.facts
       if fact.name == "streamlit_version"])
# [('1.41.0', 'superseded'), ('1.42.0', 'active')]
```

Python 3.13 remains an active user fact from `turn-1`. To represent a different environment where Python is not yet confirmed, set `context_changed=True` explicitly in the correction; Python then becomes unknown. Use `ReportedFact(name="python_version", value=None)` to withdraw that value directly.

## Tracker handoff

1. Validate the incoming turn and compute its canonical hash. Look up the immutable `(case_id, turn_id)` event and stored hash **before** checking whether a replay's expected revision is stale.
2. If the event already committed with the same hash, return its recorded outcome; do not apply it again. If the ID was reused with different content, reject it.
3. For a new event, read the authoritative case and call the proposal helper. Its case and expected revision must match that snapshot.
4. Store the candidate case, event, and hash in one transaction using compare-and-swap against the expected revision. Advance once and invalidate the old approval atomically. A failed comparison requires re-reading; it must not run the engine on an uncommitted candidate.
5. After commit, read the authoritative state and then invoke the engine with the current message. The engine's revision callback should read that same tracker.

The pure helper cannot recognize an event that committed before a restart. Replays with an old revision therefore depend on the tracker's event lookup; replay handling, compare-and-swap, and approval invalidation are integration requirements, not implemented storage claims.

## A narrow reply adapter for the pending version question

`prepare_version_reply` handles one explicit input gap without another model or
agent. `UserTurn.message` remains unparsed by the ordinary turn helper. When the
tracker supplies the exact stored pending question with the single
`streamlit_version` target, this adapter recognizes a whole final-release reply
(`1.50.0` or `Streamlit 1.50.0`) and adds a `ReportedFact` to a detached turn.
The message, event ID and source attribution remain unchanged. Uncertain text,
quoted documentation, another environment, multiline answers, prereleases and
mixed structured updates are rejected with a safe `IntakeRejected.code`.
They need an explicit structured input or clarification, not an invented fact.

The adapter checks the incoming case/revision, pending ID, question target and
whether a user version is already known. Both `next_question` and the displayed
`user_draft` must be exactly the exported core-owned
`STREAMLIT_VERSION_QUESTION.question`: "Which Streamlit version is installed in
the affected environment?" Use that `QuestionTarget` in the caller-owned question
catalog. A model may pair the correct missing field with a question about Python
or another environment; exact display binding prevents that attribution error.
Other question wording uses the existing explicit structured-input path.
Matching an ID cannot authenticate a
caller-supplied question; the tracker must load both from its authoritative
proposal record. For corrections or an environment switch, submit explicit
`ReportedFact`/`context_changed` through the existing path instead.

```python
from agent_app.orchestration.intake import prepare_version_reply

# All three records come from the tracker/UI ingress, not retrieved documents.
prepared = prepare_version_reply(
    authoritative_case,
    incoming_user_turn,
    proposal_id=stored_pending_proposal_id,
    question=stored_pending_analysis,
)
transition = propose_user_turn(authoritative_case, prepared)
# Commit with compare-and-swap, revoke old approval, then re-read before reasoning.
```

Preparation adds a field, so the canonical hash of the prepared turn differs
from the original incoming turn's hash. A tracker that prepares on ingress must
look up `(case_id, turn_id)` using the **original validated ingress hash before
checking pending proposal or revision**. Persist that original event/hash, the
prepared turn/hash, and the committed transition in the same transaction.
An identical raw replay returns the stored outcome without re-running intake;
after the first commit its question is no longer pending. A changed raw event
with the same ID is a conflict. `CaseTransition.event_hash` remains the canonical
hash of the prepared turn; do not compare it against a raw replay hash.

Alternatively, an upstream adapter can prepare once and submit/retry the exact
same prepared immutable `UserTurn` through the normal tracker event contract.
Do not mix raw and prepared envelopes on that endpoint. Neither durable ingress
deduplication nor proposal authentication is implemented by this core helper.
