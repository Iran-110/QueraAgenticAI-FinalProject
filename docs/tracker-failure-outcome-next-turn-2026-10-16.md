# T4: Failure outcome and next-turn behavior

## Scope

This report documents local, synthetic-offline acceptance tests for failure persistence, safe continuation, and the observed next-turn decision after different prior failures.

The tests exercise the persistent FastAPI application and SQLite tracker. They do not evaluate live retrieval, model quality, or held-out evaluation data.

## Source and environment

- Base commit: `21906290ce1be14342aa56c736ab9a4d85750aab`.
- Working branch: `test/mohammadbehnam-failure-outcome-next-turn`.
- Platform: Windows, PowerShell, Python 3.13.12.
- Test file: `tests/test_failure_outcome_next_turn.py`.
- Storage: temporary, isolated SQLite databases.
- Reasoning and retrieval: synthetic offline fixtures.

## Test 1: Retrieval failure and safe continuation

Test: `test_retrieval_failure_then_next_turn`

An initial message reports the Streamlit version as `1.49.1` and uses the scripted `error` scenario.

Observed and asserted behavior:

- Revision 1 records `RetrievalUnavailable`.
- No pending proposal or action is created.
- Replaying the original event is recognized as a replay.
- The replay preserves the original run outcome.
- A new message advances the same case to revision 2.
- The active Streamlit version remains `1.49.1`.
- The next decision requests `widget_definition`.
- The original failure remains stored in SQLite.

## Test 2: Controlled comparison of prior failures

Test: `test_different_prior_failures_same_next_decision`

Two independent cases receive the same initial message and the same reported Streamlit version.

Case A experiences the scripted `RetrievalUnavailable` failure.

Case B uses a test-only monkeypatch to raise an exception during the first Core run. The service records `CoreRunFailed`.

Both cases have revision 1, no pending proposal, no actions, and matching reported facts and unknowns.

The same follow-up message is then submitted to both cases using the scripted `ask` scenario.

Both produce:

- Decision: `ask`.
- Missing information: `widget_definition`.
- No actions.
- Revision 2 with no new run error.

The tested decision fields are identical.

## Interpretation

The previous failure type did not change the observed next-turn decision in this controlled scripted scenario.

Code inspection also found no direct prior `run_outcome` field in `TrackerCaseView`, `TurnConversation`, or `CaseState`, as passed through the inspected CoreTurnService path.

The outcome is persisted separately by the tracker.

These observations do not prove that historical outcomes are unused by every possible integration or that all future decisions are independent of prior failures.

Identical scripted decisions must not be represented as proof of model-level failure awareness or adaptive recovery.

## Verification

Commands:

`uv run pytest -v tests/test_failure_outcome_next_turn.py`

`uv run ruff check tests/test_failure_outcome_next_turn.py`

`uv run ruff format --check tests/test_failure_outcome_next_turn.py`

Results:

- Pytest: 2 passed in 1.36 seconds.
- Ruff check: all checks passed.
- Ruff format: file already formatted.

## Limitations and follow-up

- The comparison uses synthetic scripted adapters.
- The Core failure is deliberately injected by the test.
- The comparison demonstrates observed output equality, not complete causal independence.
- No production architecture or agent decision logic was changed.
- No held-out evaluation data was accessed.
- Any requirement for outcome-aware future decisions needs separate architectural review and an explicit acceptance contract.

This report provides operational evidence for T4 but does not close all remaining T4 acceptance requirements.
