# Two-case Streamlit -> HTTP -> SQLite smoke (Windows, offline)

**Run date:** 2026-10-13

**Operator:** tracker workstream (manual browser and PowerShell run)

**Scope:** local Streamlit maintainer UI, opt-in persistent FastAPI, isolated SQLite database, scripted/offline agent.

**Result:** the requested two-case correction, stale-review, approval, restart, and review-retry checks passed. A separate scripted reasoning run stopped with `KnownFactMarkedMissing` and remains unresolved.

This is an operator-observed local smoke report based on browser screenshots and PowerShell output, **not** a machine-produced acceptance receipt or held-out quality evaluation. The UI session remained open throughout the backend restart. No public model, external action, or production credentials were used. The response and supporting source in case 2 were labeled synthetic; correctness of the answer was not evaluated.

## Setup and reproducibility

From the repository root on Windows with Python 3.13 and `uv`, start the opt-in offline SQLite backend (PowerShell window 1):

```powershell
New-Item -ItemType Directory -Force runtime | Out-Null
if (-not (Test-Path 'runtime/two-case-reviewer-token.txt')) {
    uv run python -c "from pathlib import Path; import secrets; Path('runtime/two-case-reviewer-token.txt').write_text(secrets.token_urlsafe(32), encoding='ascii')"
}
$env:AGENT_REVIEWER_TOKEN = (Get-Content 'runtime/two-case-reviewer-token.txt' -Raw).Trim()
$env:AGENT_TRACKER_DB = Join-Path (Get-Location).Path 'runtime/two-case-pilot.sqlite3'
Remove-Item Env:AGENT_PILOT_INDEX, Env:AGENT_PILOT_SNAPSHOT, Env:AGENT_PILOT_REASONING -ErrorAction SilentlyContinue
uv run uvicorn agent_app.offline_backend:application_factory --factory --host 127.0.0.1 --port 8000
```

A fresh **isolated** database should be used for an independent reproduction. Do not delete or overwrite an existing run's database. The reviewer token is a local secret and must not appear in Git, screenshots, or test reports.

In PowerShell window 2, connect Streamlit to that backend:

```powershell
$env:AGENT_API_URL = 'http://127.0.0.1:8000'
$env:AGENT_REVIEWER_TOKEN = (Get-Content 'runtime/two-case-reviewer-token.txt' -Raw).Trim()
uv run streamlit run app.py --server.address 127.0.0.1 --server.port 8501
```

Open `http://127.0.0.1:8501`. The backend `GET /health` reported `status=ok`, `mode=synthetic_offline_sqlite`, `tracker_backend=sqlite_case_tracker`, `durable_reviews=true`, and `reviewer_auth=bearer`. The UI displayed `SQLite · durable`. Do not use the default memory-backed `agent_app.api:app` to reproduce this test.

## Observed two-case trace

| Check | Case 1: `case-ed3ce5fb` | Case 2: `case-94159dec` |
| --- | --- | --- |
| Browser input | Widget values lost after rerun/Submit | Duplicate form submission after rerun |
| Scripted selection | Ask for the Streamlit version | Answer with a source |
| Initial proposal | Follow-up asking for `streamlit_version`, revision 1 | Synthetic answer, revision 1 |
| User/reviewer action | Correction with fact `streamlit_version=1.49.1` | Maintainer `Approve` in Streamlit |
| Observed state | Revision 2; `open`; fact active | Revision 1; `answer_sent`; review history count 1; one local action |
| Extra check | Original revision-1 approval rejected with HTTP **409**, state unchanged | After restart, original approval replay returned `review.replayed=true` and added no action |
| After backend restart | Full fetched case JSON unchanged; revision 2 | Full fetched case JSON unchanged; revision 1, `answer_sent` |
| UI after backend restart | Switching to case shows revision 2 and corrected fact | Switching back shows approved reply and `Answer sent, not confirmed solved` |

### Case 1 — correction and stale approval

1. From the Streamlit UI, the initial question was submitted; the pending proposal had `proposal_id=e967934d-361f-4758-ae35-8ab9ddc3fa3b` and `case_revision=1`, captured through `GET /cases/case-ed3ce5fb` **before** the correction.
2. The `Report facts and corrections` form submitted: `Correction: the issue happens after submitting the form. The affected app uses Streamlit 1.49.1.` with fact `streamlit_version=1.49.1`. The UI then showed revision **2**, active fact, and no pending proposal.
3. A manual POST to `/cases/case-ed3ce5fb/decision` attempted `approve` with the **original** proposal ID, revision 1, and original handoff SHA-256, using the server-configured bearer token. The backend returned **409 Conflict**, and a before/after `GET` JSON comparison was **unchanged=true**; the current revision remained **2**.
4. **Unresolved scripted-run observation:** the automatic reasoning run after correction reported `core_stopped · KnownFactMarkedMissing`; no new proposal was produced. This is a failed/blocked scripted run, even though correction persistence and stale-approval protection passed. The selected scripted scenario still requests a version after the user supplied one; root cause requires separate triage. Do not claim this was a successful follow-up decision.

### Case 2 — approved answer, restart, and idempotent review retry

1. A new Streamlit case received an answer proposal; the original pending state was saved using `GET /cases/case-94159dec` **before** review.
2. Clicking **Approve** in Streamlit displayed `Approved. The draft was released to the local case log.` The UI showed `answer_sent` (not confirmed solved), revision **1**, and an approved response in the case history.
3. For both cases, the operator saved the JSON from `GET /cases/{case_id}`, stopped Uvicorn with `Ctrl+C`, and restarted the **same factory with the same environment and database path**. A fresh `GET` for each case returned a PowerShell serialized JSON comparison of **unchanged=true**; both GETs returned 200. The UI was still running in the same browser session and successfully switched between both cases.
4. The operator replayed the **identical accepted review operation**, including its original `review_id`, `proposal_id`, `case_revision`, `expected_handoff_sha256`, decision, and `edited_draft`, after the backend restart. Result:

```text
Review replayed: True
Case unchanged: True
Actions before: 1
Actions after: 1
Revision after: 1
Status after: answer_sent
```

No additional local action or case-state mutation occurred on the observed retry. The unchanged comparison is a serialization comparison of the API view, not a byte-level database audit.

## Snapshot / verification commands

In PowerShell window 3, before stopping the backend, capture both case views:

```powershell
$ids = @('case-ed3ce5fb', 'case-94159dec')
$pre = @{}
foreach ($id in $ids) {
    $pre[$id] = Invoke-RestMethod "http://127.0.0.1:8000/cases/$id"
    $pre[$id] | ConvertTo-Json -Depth 100 |
        Set-Content "$env:USERPROFILE\Downloads\$id-before-restart.json" -Encoding UTF8
}
```

Stop/restart **only** the backend process, keeping `AGENT_TRACKER_DB` and `AGENT_REVIEWER_TOKEN` unchanged. After restart:

```powershell
foreach ($id in $ids) {
    $post = Invoke-RestMethod "http://127.0.0.1:8000/cases/$id"
    $same = ($pre[$id] | ConvertTo-Json -Depth 100 -Compress) -ceq ($post | ConvertTo-Json -Depth 100 -Compress)
    Write-Host "$id | unchanged=$same | revision=$($post.case_revision) | status=$($post.status)"
}
```

The stale-approval and replay operations require the precise original review envelopes; **never generate a new `review_id` for an idempotent retry**. Preserve the first pending snapshot before submitting correction or approval. See [`docs/tracker-t4-operational-evidence.md`](tracker-t4-operational-evidence.md) for separate automated HTTP/SQLite acceptance and crash/rollback testing.

## Limits and handoff

- This is a **manual, scripted, offline, two-case smoke**, not end-to-end quality evaluation against frozen dev/test fixtures. The synthetic source cited by case 2 is not a real retrieved document.
- UI navigation was checked across a **backend** restart with the browser UI session intact; full UI-session/browser recovery and user authentication remain outside scope.
- The result establishes one successful approval and one stale-approval rejection; it does **not** exercise separate **Edit/Reject** browser paths, tool-outcome consumption by a later real model decision, or external tool execution. These remain in the broader T4/U3/E5 plan and should not be marked complete on this evidence alone.
- Do not commit local DB files, bearer tokens, or raw case snapshots containing any sensitive content. The observations above deliberately omit credentials and raw payload dumps.
- **Tracker T4 remains open** pending the remaining evidence, evaluation handoff, and product configuration. This report supplies the requested two-case UI -> SQLite observation, including the `KnownFactMarkedMissing` stop for follow-up.
