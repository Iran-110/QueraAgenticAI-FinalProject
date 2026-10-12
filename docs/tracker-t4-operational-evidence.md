# T4 — Tracker operational evidence (Windows, offline)

**Status:** Backend evidence collected; T4 remains open pending U3/evaluation integration.
**Observed environment:** Windows PowerShell, Python 3.13 via `uv`, 12 October 2026.
**Related change:** [PR #31](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/31), commit `a550bf1` (Windows-only offline test harness compatibility).

This report records local test results supplied by the tracker owner. It is not a new tracker or API implementation. The authoritative backend is the existing [`SQLiteCaseTracker`](../src/agent_app/tracker/sqlite_tracker.py) connected through opt-in [`persistent_api.py`](../src/agent_app/persistent_api.py). The default `agent_app.api:app` demo still uses in-memory state. All runs below use synthetic, offline ports; they do not exercise a real model, production search index, external tool, or shared budget ledger.

The reported Windows counts and durations below belong to the PR31 source
`a550bf169b274647783fb9c3c7ab5898df1c6504`, subsequently published on main as
`877601c83b3f8eeb4ad032fd23d54f0e1cb1a0bf`. They are owner-reported execution
results, not a receipt produced by the documentation commit. This documentation
branch has been synchronized with that released main, including the two new
Windows runtime regressions. The independent [main CI](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38314737701)+is a separate Linux run and does not establish Windows acceptance.

## Commands and observed results

Run from the repository root:

| Verification | Command | Observed Windows result |
| --- | --- | --- |
| Tracker state, correction, idempotency and core failure boundaries | `uv run pytest -q tests/test_sqlite_tracker.py tests/test_core_tracker_failure_boundaries.py` | **27 passed** (4.67 s) |
| Runtime transactions, authenticated persistent HTTP API, process crash and lost ACK | `uv run pytest -q tests/test_sqlite_runtime.py tests/test_persistent_api.py tests/test_persistent_http_crash.py` | **77 passed** (14.56 s) |
| HTTP test runtime, including Windows `socketpair()` and Unicode output | `uv run pytest -q tests/test_http_pilot_runtime.py` | **33 passed** (11.21 s) |
| End-to-end *offline* HTTP/SQLite acceptance with fresh processes | Command below | **457/457 checks**, `accepted=true`, `same_process_accepted=true`, `restart_accepted=true`, `error_code=null` |

```powershell
$receipt = "$env:USERPROFILE\Downloads\tracker-t4-$(Get-Date -Format 'yyyyMMdd-HHmmss').json"
uv run python scripts/http_pilot_acceptance.py --factory agent_app.testing.sqlite_http_binding:sqlite_factory --protocol experiments/http_pilot_acceptance/protocol-v2.json --output $receipt
```

The acceptance receipt was directed to the **local Downloads directory**, outside this repository. Its exact filename and complete contents must be retained or independently checked before treating the receipt itself as an archived artifact; the console summary above is verified from the reported run. The repository also contains the independently recorded [SQLite C2d receipt](../experiments/http_pilot_acceptance/results-sqlite-b7107c0.json) and [acceptance contract](persistent-http.fa.md). These are **separate runs**, not a claim that the local Windows receipt is identical.

**33 + 27 + 77 = 137 pytest passes**, while **457 are acceptance checks** rather than additional pytest tests or distinct cases. Some tests cover overlapping behaviors. `quality_claim=false` is expected.

## Behaviors covered and boundaries

- **Restart / state persistence:** the acceptance protocol reopens the same SQLite database across fresh Python processes; case history, pending proposal and original review receipt survive. Merely creating another `TestClient` would not establish this.
- **Idempotency / stale proposals:** original event and review retries retain their IDs and payload identity; reviews are bound to the displayed `proposal_id`, `case_revision` and `review_handoff.handoff_sha256`. Correction invalidates stale approval. Replaying a successful review does not create a second local comment.
- **Authenticated approval:** the reviewer is resolved from trusted server-side bearer-token configuration, not the request body. Missing/incorrect credentials fail closed. Reject and edit follow separate state transitions; edit requires a new proposal and approval.
- **Rollback and crash recovery:** the dedicated tests simulate a local comment write that fails before commit, subprocess termination after ingress/staging commits, and a lost staging acknowledgement. The expected transaction rollback or original stored receipt is checked without creating extra model-port invocations or local actions.
- **Tool result / subsequent decision:** the HTTP path persists measured `RunResult` and exposes `run_outcome` with the current view. **Consumption by the next decision in the actual UI/evaluation pipeline is not yet established.** No external or GitHub-side action is tested; the tool writes a local SQLite comment only.

## Configuration and safe development reset

Create the persistent HTTP application with an explicit durable database path and a trusted mapping of reviewer credentials, as described in [C2d](persistent-http.fa.md). Keep bearer tokens in local ignored configuration; never put them in commits, test receipts, messages, or logs. Bind the development server to loopback. The acceptance binding uses a **synthetic** credential and a temporary database, and must not be mistaken for production configuration.

The tracker exposes `SQLiteCaseTracker.reset_all(confirmation="RESET LOCAL TRACKER")`. This is an **explicit, destructive development-only operation**: it deletes all case, event, proposal, review, local action, conversation, run-outcome and audit rows. It is never performed by the constructor or by a restart. An incorrect confirmation raises `ResetConfirmationRequired` (see [`test_reset_requires_explicit_confirmation`](../tests/test_sqlite_tracker.py)).

For an intentionally disposable test database **only**, after verifying the path and ensuring no server is using it:

```powershell
# Destructive: change this path only to a disposable, isolated test database.
uv run python -c "from pathlib import Path; from agent_app.tracker.sqlite_tracker import SQLiteCaseTracker; p = Path('runtime/t4-disposable.sqlite3'); assert p.is_file(), 'Disposable test DB not found'; SQLiteCaseTracker(p).reset_all(confirmation='RESET LOCAL TRACKER')"
```

**Do not run this command on the team's persistent database.** Do not reset any live state or budget ledger to force a green test. For routine verification prefer the HTTP acceptance harness's separate temporary SQLite storage; it requires **no reset**. Back up any development database that needs to be retained before an intentional reset.

## Quality checks and remaining handoff

For the three files in PR #31, local `ruff check` and `ruff format --check` passed, and `git diff --check` found no whitespace errors. The PR's GitHub Actions checks were green when reviewed; the PR was submitted to Sasan for review, **not merged by this evidence**.

The bounded UI binding, private credential configuration, stable original
`review_id`/handoff hash, uncertain-ACK retry and case switching are implemented
and tested separately in [PR #32](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/32).
That PR's status is authoritative for publication; it is not part of the
owner-reported Windows backend run above.

**Still open (T4/U3/E5):** product configuration, real-browser smoke,
authentication for browser users and recovery after complete UI-session loss.
The team must verify consumption of persisted tool outcome in the next actual
decision/evaluation, and hand the scoped backend receipts to evaluation. The
dev fixture is exposed and scripted; these passes are not held-out retrieval or
model-quality results. Keep T4 unchecked until its remaining conditions are
demonstrated.
