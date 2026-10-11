# SQLite case tracker

The tracker persists case state and review actions in a local SQLite database. It uses the existing `CaseState`, `UserTurn`, and `ProposalHandoff` contracts without changing the core decision logic.

**Status:** The tracker is implemented and tested as an offline module. FastAPI and Streamlit still use their existing in-memory state; this module is not yet connected to that path.

## Implementation

Source: [`sqlite_tracker.py`](../src/agent_app/tracker/sqlite_tracker.py)

| Operation | Behavior |
| --- | --- |
| `read_case(case_id)` | Reads current state, history, pending proposal, and approved question without creating a record. |
| `apply_turn(turn, ...)` | Commits structured user updates and corrections with a revision check. Repeated events return their stored receipt. |
| `stage_proposal(handoff)` | Stores the full core handoff only if its case content and revision still match. |
| `review(case_id, ...)` | Authenticates the reviewer and checks the exact case, revision, proposal, and handoff hash before approve, reject, or edit. |
| `comments(case_id)` / `audit_trace(case_id)` | Returns local action records and a bounded operational trace. |
| `reset_all(confirmation=...)` | Clears local tracker tables only with an explicit confirmation string. |

Case updates, proposal invalidation, review receipts, and local comment writes use SQLite transactions. Reusing an event or review ID with different content is rejected. A correction invalidates the pending proposal; editing creates a new proposal that requires another approval. Rejected proposals do not write comments.

Reviewer credentials must come from trusted application configuration. Retrieved text and model output cannot authorize an action. Approved comments are written only to the local tracker, not to GitHub or real users.

## Checks

Run from the repository root with Python 3.13:

```bash
uv sync --locked --group dev
uv run pytest -q tests/test_sqlite_tracker.py
uv run python scripts/tracker_pilot.py
uv run ruff check src/agent_app/tracker/sqlite_tracker.py tests/test_sqlite_tracker.py scripts/tracker_pilot.py
```

The [tests](../tests/test_sqlite_tracker.py) cover restart, event replay, correction, stale approval, reject/edit, reviewer authentication, concurrent review, rollback on tool failure, case isolation, and explicit reset.

The [pilot](../scripts/tracker_pilot.py) runs an offline multi-turn case with fake retrieval and reasoning. It asks for a version, receives a correction, rejects the old approval, and records the approved result once. The database is temporary unless `--db` is supplied:

```bash
uv run python scripts/tracker_pilot.py --db runtime/tracker-pilot.sqlite3
```

Use a fresh database for each pilot run; the script intentionally refuses to overwrite an existing pilot case. Runtime databases and credentials must not be committed.

At the time of this handoff, all 14 tracker tests and the offline pilot passed on the supplied repository snapshot. These checks do not measure retrieval or model-answer quality.

### Core contract review — 2026-10-11

`read_case` now holds a deferred read transaction across state, proposal, reply
and conversation queries. Without it, a correction committed by another
connection could mix revision-1 state with revision-2 history. The deterministic
WAL regression fails against PR #19's original `faedfc14` and passes with the
snapshot fix; write CAS and review authentication are unchanged.

The existing answer-informed `data/evaluation/dev/pilot-12782.json` is also
composed with `SupportEngine` and actual SQLite storage in a test. It covers the
approved canonical reply, correction from 1.50.0 to 1.49.1, two retrieval rounds
with the old source removed from the final handoff, stale approval, edit/new
approval, restart/review replay, withdrawal and rejection. Gold and expectations
are not passed to the core ports; the reasoner and evidence remain scripted.
All 16 tracker tests and the original pilot pass locally. This is core/tracker
contract evidence, not API/UI integration or model/RAG quality.

## Integration work

- Replace FastAPI's in-memory `_cases` and dummy tracking path with authoritative reads and writes through `SQLiteCaseTracker`.
- Supply validated `UserTurn` events and full `ProposalHandoff` objects from the existing core. Do not build handoffs from arbitrary client input.
- Bind reviewer identity and credentials at the server boundary. The UI must submit stable event/review IDs and show the exact proposal being approved.
- Run the shared multi-turn fixture through API and UI, including restart, correction, reject/edit, retries, and tool failure. Store receipts for the evaluation owner.

The integration above remains open; the standalone tests do not establish completion of P3. Task status and ownership are tracked in the [team plan](../plan/plan.md).
