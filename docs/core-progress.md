# Agent-core progress

This is a factual milestone log, not a daily activity schedule. Update it after a verified change; keep real dates and real limitations.

## 2026-10-06 — first foundation

Branch: `feat/agent-core-foundation`. Scope: the owner's contracts and orchestration, with deterministic offline adapters.

- Shared validated contracts separate case facts, evidence, decisions, run results, and limits.
- The core proposes answer, question, or escalation and allows bounded retrieval refinement.
- Case revision checks, retrieved references, and adapter failures are handled in code.
- Offline CLI scenarios cover asking, answering, escalating, refinement, and retrieval failure without API spending.
- README, architecture, development rules, and shared Codex/Claude project instructions describe the handoff boundaries for a four-person team.

Verified locally with Python 3.13: `uv sync --locked --group dev`, 140 passing tests, Ruff lint and formatting checks, and the offline refinement CLI. No paid requests were made. The tests cover contract validation, bounded retries/refinement, source references, stale revisions, invented facts, adapter failures, and all five demo scenarios.

The recorded milestone concerns local behavior with synthetic fixtures. Passing unit tests and demos do not establish real model quality, retrieval relevance, approval enforcement in storage, restart recovery, or duplicate-safe tool execution.

## 2026-10-07 — model gateway and cost accounting

- Implemented a single-send Metis adapter using the documented nonstreaming chat endpoint. Native JSON-schema support is not assumed; the core validates the returned decision.
- Added caller-owned run/case/revision/attempt context and terminal error handling without another paid retry.
- Added an atomic SQLite cost ledger: explicit initialization, reservations, known-usage settlement, held uncertain costs, duplicate request rejection, and persistent halting on accounting anomalies.
- Added offline gateway scenarios for success, format repair, timeout, and denied budget, plus ledger initialization/status commands.
- Verified locked dependencies, 295 passing tests, Ruff lint/format, and the installed gateway repair demo. All HTTP in these tests is simulated; paid API spending remains zero.

The user confirmed the full USD 5 was untouched. The local ignored runner ledger was initialized with a USD 4.50 ceiling and zero opening spend, leaving USD 0.50 outside the operational limit. At this milestone the API key was not yet configured and the live pilot was pending. Public rates and token reservations are operational estimates until account deductions are checked. There is no team-wide enforcement across independent laptop databases.

## 2026-10-07 — explicit user turns and first live pilot

- Added `ReportedFact`, `UserTurn`, and `CaseTransition`, plus a pure proposal helper for new facts, withdrawals and corrections. The candidate advances one revision and clears the old pending proposal without saving or executing anything.
- Preserved superseded fact attribution. New knowledge invalidates old evidence conclusions; actual corrections invalidate unscoped performed checks. Explicit environment switches also retire unconfirmed user facts from the old environment.
- Added a three-turn offline CLI demo and a tracker handoff guide: durable event deduplication before stale-revision checks, atomic compare-and-swap and approval invalidation, then an authoritative read before reasoning. These remain tracker requirements rather than implemented persistence.
- Verified locked dependencies, **354 passing tests**, Ruff lint/format and the installed turn demo. CI now also runs that demo. All automated tests remain offline.
- After the user saved the local key and authorized its use, ran exactly one bounded live Metis request on a synthetic case. HTTP 200 and usage reporting worked: 1,229 input and 174 output tokens, settled at a public-rate estimate of **USD 0.000317625**. No pending or uncertain reservation remained; available runner credit was USD 4.499682375.
- The live response failed core validation with `ModelOutputInvalid`; no retry was sent. Raw output was not retained, so the specific failed rule is unknown. Clarified the prompt's JSON-instance and decision-field instructions offline; this revision has not been retested live.

Connection and usage settlement are verified for that one request. Valid live decisions, retrieval/model quality and account billing reconciliation are still pending. The key, ledger and sanitized pilot receipt remain ignored local files. The original UI and `main` were not changed.

## Next integration work

| Work | Owner | Completion evidence |
| --- | --- | --- |
| Real retrieval adapter and frozen corpus | Data/RAG | Inspectable sources, metadata, and dev retrieval measurements |
| Live Metis response compatibility and billing reconciliation | Agent core | First request verified access and usage; still need a valid decision, sanitized validation diagnostics and account deduction comparison |
| Durable tracker and safe execution | Tracker/tools | Persisted state, restart, reject/edit/stale approval, and retry tests |
| Backend connection and evaluation cases | UI/evaluation | Live local flow and 15 dev + 15 test with required multi-turn cases |
| Baseline versus final measurements | Whole team | Same cases, quality/cost/latency results, and failure analysis |
| Systematic Adversarial Testing | Proposed core bonus, mentor agreement | Defined challenge set plus measured before/after improvement |

Local tracker reset instructions will be added with its actual implementation. There is no persistent tracker to reset in the current core demo.
