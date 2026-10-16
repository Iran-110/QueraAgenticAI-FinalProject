# Tracker operational acceptance evidence

## Scope

Manual Windows/PowerShell acceptance observations for the Streamlit UI, persistent FastAPI backend, and SQLite tracker.

Both runs used synthetic offline behavior. They do not establish retrieval quality or model-answer quality.

## 1. Tested source baselines

### Two-case smoke test

- Documented source commit: `f8b3106`.
- Original report: `docs/two-case-ui-sqlite-smoke-2026-10-14.md`.
- Original evidence: PR #52.
- Sanitized receipt: `docs/receipts/two-case-smoke-2026-10-14-sanitized.json`.

The original report records that HEAD and origin/main were checked before the test.

### Approval response-loss and UI retry

- Test branch baseline: `b32b861f4aad61a82df2aa88e4378e44c6a71ce1`.
- Receipt commit: `0d21450`.
- Evidence merged in PR #66.
- Sanitized receipt: `docs/receipts/approval-ack-drop-ui-retry-sanitized.json`.

Git reflog confirms that the receipt branch was created from `b32b861` on 2026-10-15. The diff from `b32b861` to `0d21450` contains only the two receipt files.

Limitation: a separate HEAD capture at the exact moment of the manual fault-injection run was not preserved. The branch baseline is therefore documented, but the runtime checkout is not independently attested.

## 2. Execution environment

- Platform: Windows / PowerShell.
- Backend: `http://127.0.0.1:8000`.
- Streamlit UI: `http://127.0.0.1:8501`.
- Fault proxy: `http://127.0.0.1:8001`.
- Storage: local SQLite database under `runtime/`.
- Reasoning: scripted synthetic offline adapter.
- No external model or retrieval requests.

Backend command:

`uv run uvicorn agent_app.offline_backend:application_factory --factory --host 127.0.0.1 --port 8000`

Streamlit command:

`uv run streamlit run app.py --server.address 127.0.0.1 --server.port 8501`

The backend and UI required the same locally configured reviewer authorization. The UI used `AGENT_API_URL=http://127.0.0.1:8001` during fault injection.

Fault proxy command:

`uv run python "$env:USERPROFILE\Downloads\review_ack_drop_proxy.py"`

Fault proxy SHA-256:

`038B59FC048F283A76D44B04FA2B64F2A7CFD0F707335155A0D884BDF8CF5933`

The proxy script was a local test utility and was not committed. Its hash identifies the observed file but does not, by itself, make the test fully reproducible.

## 3. Operational acceptance results

### Correction and stale review

- A correction advanced Case 1 from revision 1 to revision 2.
- The corrected Streamlit version remained an active fact.
- A replacement proposal was created.
- Approval of the obsolete proposal returned HTTP 409.
- The rejected stale request did not change the case or create an action.

### Maintainer edit and approval

- Edit created a replacement proposal with a new proposal ID.
- The edited text was preserved.
- Approval released the edited response.
- Case 1 reached `awaiting_user`, revision 2, with one action.

### Rejection and case isolation

- Reject returned Case 2 to `open` at revision 1.
- Its pending proposal was cleared.
- No action was created.
- Case 1 remained unchanged.

### Backend restart

Both cases were read again after restarting the backend against the same SQLite database.

- Case 1: `awaiting_user`, revision 2, one action.
- Case 2: `open`, revision 1, zero actions.
- Full case snapshots matched their pre-restart versions.

### Approval retry after restart

Replaying the same accepted review returned `review.replayed=true`. The case remained unchanged, with one action.

## 4. Approval response-loss experiment

A local proxy dropped the response to a successfully committed approval request.

| Observation | Revision | Status | Actions |
| --- | ---: | --- | ---: |
| Before approval | 1 | awaiting_review | 0 |
| After response loss | 1 | answer_sent | 1 |
| After Retry review in UI | 1 | answer_sent | 1 |
| After browser reopen | 1 | answer_sent | 1 |

The UI displayed an unconfirmed-review warning and retained a Retry review operation. Retrying confirmed the original review without creating a second action.

The API case state remained identical after the browser was closed and reopened.

## 5. Limitations

- These results cover operational behavior with synthetic offline adapters.
- The new browser session created a new UI case.
- Automatic recovery of an unconfirmed review operation across a completely new browser session has not been demonstrated.
- The fault proxy source is not versioned in the repository.
- Failure/outcome effects on subsequent agent decisions require separate acceptance tests.

## 6. References

- PR #52: two-case SQLite smoke test.
- PR #66: sanitized operational receipts.
- `docs/two-case-ui-sqlite-smoke-2026-10-14.md`.
- `docs/receipts/two-case-smoke-2026-10-14-sanitized.json`.
- `docs/receipts/approval-ack-drop-ui-retry-sanitized.json`.
