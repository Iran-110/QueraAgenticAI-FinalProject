# User live mode

Real users can chat with the live model through the existing UI, outside the
development/evaluation experiments and the presentation scope.

`src/agent_app/user_backend.py` reuses the ordinary live backend
(`live_backend.configured_app`) and the selected core profile
`grounded_candidate_prefilter_v2` (final v3 index, exact USER-version prefilter,
top 5, reviewed question vocabulary). The difference is accounting:

- Every request is reserved on a separate ledger, `runtime/user-budget.sqlite3`,
  capped at **USD 1**. The backend refuses a ledger with a higher limit and
  never opens the team ledger `runtime/budget.sqlite3`.
- The team halt, its three holds and the presentation scopes are untouched.
- The per-request cap (USD 0.02), the two-attempt limit and the uncertain-result
  halt still apply. If the provider result is uncertain, the user ledger halts
  and further user calls stop until a person reconciles it. Never delete or
  recreate the ledger to get fresh credit.
- No file pinned by the presentation protocol was changed, so the meeting scope
  still matches its bound source hashes.

Limitation: the pinned core modules only know the `development`/`evaluation`
phase labels, so user reservations carry the `development` label. The separate
ledger file is what identifies user use. A real `user` label needs a new
versioned profile and a new presentation protocol after the meeting.

## Run

Create the ledger once (already done on the machine where this was added):

```bash
uv run agent-app budget init --path runtime/user-budget.sqlite3 --limit-usd 1 --opening-spend-usd 0
```

Backend, with private settings from your ignored `.env` (`METIS_API_KEY`,
`METIS_LIVE_ENABLED=true`, `AGENT_TRACKER_DB`, `AGENT_REVIEWER_TOKEN` of 32+
characters). The index defaults to `runtime/demo-final-corpus-v3` with its
pinned snapshot/manifest; override with `AGENT_EVAL_INDEX`,
`AGENT_EVAL_SNAPSHOT`, `AGENT_EVAL_MANIFEST_SHA256`.

```bash
set -a; . ./.env; set +a; uv run uvicorn agent_app.user_backend:app_factory --factory --host 127.0.0.1 --port 8765
```

UI, in another shell with the same reviewer token:

```bash
set -a; . ./.env; set +a; AGENT_API_URL=http://127.0.0.1:8765 uv run streamlit run app.py
```

Check remaining credit:

```bash
uv run agent-app budget status --path runtime/user-budget.sqlite3
```

Startup sends no model request. Tests (`tests/test_user_backend.py`) use a
mock provider only.
