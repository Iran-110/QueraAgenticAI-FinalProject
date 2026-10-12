# Core ↔ SQLite: interrupted runs and safe retries

The standalone `SQLiteCaseTracker` is available after PR #19, including PR #20's
consistent read snapshot. The default FastAPI demo still uses process memory.
The opt-in [C2d HTTP factory](persistent-http.fa.md) now composes this tracker
with [CoreTurnService](core-turn-service.fa.md), stores explicit outcomes and
passes authenticated review envelopes. UI binding remains U3; automatic
run resumption is not implemented. The policies below also apply to that path.

## One authoritative state

Call `apply_turn` with the original validated `UserTurn`, its original reply
binding, and the same trusted adapter context on retries. Require a stable event
ID and explicit expected revision at the HTTP boundary. The tracker deduplicates
the original event before reply preparation or stale-revision checks.

For a **fresh** event, read state from that tracker after the commit. Its revision
must equal the receipt's `committed_revision`; otherwise a newer turn has already
won and this old message must not be run against the newer facts. Give the same
tracker to `SupportEngine.current_case` for full state freshness; the older
`current_revision` callback checks only its number. Keep model/retrieval work outside
SQLite write transactions, then use `stage_proposal` to check the full case and
revision atomically. Every new accepted turn needs its own caller-owned run ID;
the test fixture's constant run ID is only for its isolated single-run database.
Do not mirror authoritative state in FastAPI's `_cases`.

Keep the original ingress receipt separate from the current view. Replaying an
old event does not rewind facts, history, pending proposals or approved replies.
It must return before constructing retrieval/model adapters. An input event's
receipt proves that input was committed, not that reasoning completed.

## Failure policy for the API owner

| Interruption or race | Safe result | Recovery boundary |
| --- | --- | --- |
| Ingress committed; process stops before reasoning or staging | Input remains committed; no proposal is available | Identical event replay performs no new model/retrieval work. Show interrupted/unavailable outcome rather than inventing completion. |
| Correction commits during reasoning | Core reports `stale / StaleRevision`; no final analysis is released | Preserve the newer facts; any already consumed model request keeps its ledger record. |
| Correction commits after core returns, before staging | `stage_proposal` rejects `StaleRevision` | Discard the old handoff; do not retry it against the newer revision. |
| Proposal commit succeeds, but its acknowledgement is lost | A fresh consistent read contains the exact pending handoff | Validate the stored handoff and its current case binding; require the original proposal ID and full handoff equality before treating that staging as recovered. No new reasoning. |
| Staging result is ambiguous and exact stored handoff is absent/different | No claim that staging succeeded | Do not approve a different/current proposal using the old request. Journal-based resume remains T4 work. |
| Review writes a local comment then fails before commit | The whole transaction rolls back | Retry the identical authenticated review ID and payload; one committed action at most. |
| Same event arrives concurrently | One fresh receipt; other equal requests replay it | Only the caller receiving the fresh receipt may initiate reasoning. A conflicting payload is rejected. |

`stage_proposal` itself is not idempotent: while a successfully staged proposal
remains pending, calling it again returns `PendingProposalMismatch`. After
approval or correction, other conflict/stale codes can apply. Resolve an ambiguous acknowledgement by
reading and comparing the original handoff, not by assuming that rejection means
the prior write failed. For comparison, use `validate_handoff` on both objects,
`ensure_handoff_current` on the stored object and current state, and compare their
complete contents. Hash validity establishes integrity, not semantic correctness
or reviewer permission. A human edit produces a different proposal and hash.

An interrupted event with no stored proposal must not automatically be rerun
after restart. An explicit resume feature needs a durable run/outcome journal
and caller-owned request identity, plus ledger reconciliation. Merely generating
a new run ID is not recovery. Live calls remain halted until C5 is resolved;
neither retries nor integration tests may clear uncertainty or reset the budget.

## What the core supplies and what is still needed

Core supplies `CoreTurnService` with receipt-bound lazy adapters, historical user
context, read-only exact pending recovery, the pure user transition,
approved-question reply preparation, bounded engine, full-current-case callback,
complete `ProposalHandoff`, and stale
handoff checks. The existing #12782 dev fixture tests canonical follow-up,
correction, refinement/final evidence, authenticated edit/approval, restart and
withdrawal against actual SQLite. It remains answer-informed, scripted and dev
only; it is not a RAG or model-quality evaluation.

The [failure-boundary tests](../tests/test_core_tracker_failure_boundaries.py)
exercise the races and interruption policy above with actual SQLite and scripted
ports. Their small coordinator is a test harness, not a production API adapter.
They do not persist a reasoning outcome or prove HTTP/UI restart behavior.
The newer [service tests](../tests/test_core_turn_service.py) invoke the actual
core coordinator rather than those historical harness helpers. Full snapshot
reads alone stop only observed lifecycle changes. C2d now additionally checks
open status and the absence of any previous root proposal at the same revision
inside the stage transaction; measured staging transitions its persisted event
outcome once. This conservatively closes the final same-revision ABA route.
All 11 failure-boundary cases and the 16 tracker tests pass together. They
include a fresh event superseded before the post-commit read, interruption both
before reasoning and after reasoning/before staging, exact lost-ack recovery,
correction races, rollback after a comment INSERT and concurrent identical
event/review requests. No provider request or production ledger was used.

The C2d HTTP path now uses this single state source, explicit run/outcome status,
stable review IDs, expected revision, exact proposal ID and handoff hash.
Reviewer credentials come from trusted server configuration, not model/source/user
content. Only the tracker transaction releases a local action. U3 still needs
the current UI/client to supply the new stable review envelope and authenticate
the maintainer; index/model configuration and evaluation remain separate work.

The registered dev HTTP fixture now passes on actual SQLite, including restart,
correction, edit/reject and original event/review retries; actual process crashes
at both commit boundaries and local tool rollback are tested separately.
Backend-labelled receipts remain separate from memory receipts. UI integration,
meaningful model/source support scoring and conditional branches remain U3/E2.

```bash
uv run pytest -q tests/test_sqlite_tracker.py tests/test_core_tracker_failure_boundaries.py
uv run python scripts/tracker_pilot.py
uv run python scripts/core_tracker_pilot.py --output /tmp/core-tracker-pilot-new.json
```
