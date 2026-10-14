# Two-case UI → API → SQLite smoke test (2026-10-14)

## Scope

Manual, local Windows smoke test of the **Streamlit UI → persistent FastAPI backend → SQLite case tracker** on the updated `main` baseline (`f8b3106`). The run used the **synthetic offline** backend: scripted behavior and synthetic evidence, without external retrieval or model requests.

This is a follow-up to the earlier smoke-test report in PR #40. It does not replace that report or reimplement the existing automated tests. It checks the updated correction/follow-up flow together with stale-review protection, maintainer edit, valid approval, rejection, per-case isolation, restart durability, and approval retry/idempotency.

## Environment and run commands

- Platform: Windows / PowerShell.
- Git baseline: `f8b3106` (`HEAD` and `origin/main` checked before testing).
- Work branch: `test/mohammadbehnam-latest-two-case-smoke`.
- Backend: `http://127.0.0.1:8000`.
- UI: `http://127.0.0.1:8501`.
- Persistence: dedicated SQLite file under `runtime/` (not committed).
- Review authorization: local bearer token under `runtime/` (not committed).

In a PowerShell terminal at the repository root, prepare an isolated database and the reviewer token (keep these local):

```powershell
New-Item -ItemType Directory -Force runtime | Out-Null
$db = "runtime/two-case-clean-$(Get-Date -Format 'yyyyMMdd-HHmmss').sqlite3"
$env:AGENT_TRACKER_DB = Join-Path (Get-Location).Path $db
$env:AGENT_REVIEWER_TOKEN = (Get-Content "runtime/two-case-20261014-token.txt" -Raw).Trim()
Remove-Item Env:AGENT_PILOT_INDEX, Env:AGENT_PILOT_SNAPSHOT -ErrorAction SilentlyContinue
$env:AGENT_PILOT_REASONING = "scripted"
uv run uvicorn agent_app.offline_backend:application_factory --factory --host 127.0.0.1 --port 8000
```

The token file name above refers to the locally prepared token used for this run; for a new run, create a new secret token and configure the backend with it. **Do not commit tokens or databases.** Preserve `AGENT_TRACKER_DB` when restarting the backend to test durability.

In a second PowerShell terminal (same repository root), run the UI:

```powershell
$env:AGENT_API_URL = "http://127.0.0.1:8000"
$env:AGENT_REVIEWER_TOKEN = (Get-Content "runtime/two-case-20261014-token.txt" -Raw).Trim()
uv run streamlit run app.py --server.address 127.0.0.1 --server.port 8501
```

Confirm `GET http://127.0.0.1:8000/health` reports `status=ok`, `mode=synthetic_offline_sqlite`, and `tracker_backend=sqlite_case_tracker` before using the UI. API inspection and response snapshots used `Invoke-RestMethod` and `ConvertTo-Json -Depth 100` from a third PowerShell terminal.

## Case 1 — correction, stale approval, edit, valid approval

**Case:** `case-7772175f`.

1. Submitted a Streamlit form/widget-value-loss report via the UI, producing a draft for maintainer review at **revision 1**.
2. Submitted a correction explicitly recording `streamlit_version = 1.49.1`. The case advanced to **revision 2**, and a **new** proposal replaced the previous proposal. The updated scripted flow asked for the widget definition/key and relevant code rather than asking again for the already-known Streamlit version.
3. Attempted to approve the **revision 1** proposal after the correction, using its original proposal information. The API rejected this stale approval with **HTTP 409**; a before/after case comparison returned **unchanged = true**, and there were **zero actions** at that point.
4. Used the maintainer **Edit** action on the current proposal. The resulting proposal had a new ID, and the replacement draft text was verified in the case returned by the API.
5. Approved the edited, current proposal in the UI. The edited follow-up was displayed as sent after maintainer approval. The API state was **`awaiting_user`**, **revision 2**, with no pending proposal and the active fact `streamlit_version = 1.49.1`.

## Case 2 — reject and case isolation

**Case:** `case-fc94ef5d`.

1. Opened an independent second case and submitted: “My Streamlit app processes the same form submission twice after a rerun. How can I prevent duplicate processing?”
2. Selected the scripted **Answer with a source** scenario. Before review, the API showed **`awaiting_review`**, **revision 1**, a pending proposal, and **zero actions**.
3. Clicked **Reject** in the UI. The UI displayed **“Rejected. Nothing was sent.”** and recorded **one** review-history entry.
4. The API subsequently showed **`open`**, **revision 1**, **no pending proposal**, and **zero actions**.
5. Compared the entire API case document for Case 1 against its snapshot before Case 2 rejection: **unchanged = true**. Case 1 remained **`awaiting_user`**, **revision 2**, without a pending proposal.

## Backend restart — durable recovery

Stopped Uvicorn gracefully with `Ctrl+C` and restarted the backend from the **same PowerShell session** (preserving the configured SQLite database path and reviewer environment). After restart, fetched both cases again through the API.

| Case | Full API state unchanged | Status after restart | Revision after restart | Actions observed |
|---|---|---|---:|---:|
| `case-7772175f` | `true` | `awaiting_user` | 2 | 1 |
| `case-fc94ef5d` | `true` | `open` | 1 | 0 |

These observations support persistence of both case records across a backend process restart with the same SQLite database, and isolation between the two cases.

## Approval retry — idempotency

Replayed the *same already-accepted approval request* for Case 1, including the existing `review_id`, proposal/revision identity, and handoff digest, against `POST /cases/{case_id}/decision` after restart.

| Check | Observed |
|---|---|
| `review.replayed` | `true` |
| Full case state unchanged | `true` |
| Actions before replay | 1 |
| Actions after replay | 1 |
| Revision after replay | 2 |
| Status after replay | `awaiting_user` |

The replay did not create another action or mutate the case. Locally generated receipt: `case1-f8b3106-retry-receipt.json` (not committed).

## Evidence and acceptance summary

| Acceptance check | Result |
|---|---|
| UI → API → SQLite, two independent cases | Pass |
| Correction changes revision and replaces proposal | Pass |
| Known Streamlit version is retained; revised follow-up asks for missing code | Pass |
| Stale approval blocked without mutation (HTTP 409) | Pass |
| Maintainer Edit creates a new pending proposal with edited text | Pass |
| Valid approval releases the edited follow-up | Pass |
| Reject sends nothing and records a decision | Pass |
| Reject creates no action; does not alter the other case | Pass |
| Both cases survive backend restart without change | Pass |
| Repeated approval is replayed without an extra action | Pass |

The smoke test used synthetic scripted responses and synthetic evidence only. It does **not** validate live retrieval, model answer quality, or the evaluation corpus. The local JSON snapshots and terminal/UI screenshots were used to verify the observations; no local runtime database or bearer token is included in this PR.
