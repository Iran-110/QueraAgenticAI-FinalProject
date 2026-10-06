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

## Next integration work

| Work | Owner | Completion evidence |
| --- | --- | --- |
| Real retrieval adapter and frozen corpus | Data/RAG | Inspectable sources, metadata, and dev retrieval measurements |
| Real Metis gateway and shared budget accounting | Agent core | Small paid pilot with recorded model, tokens, price basis, and actual cost |
| Durable tracker and safe execution | Tracker/tools | Persisted state, restart, reject/edit/stale approval, and retry tests |
| Backend connection and evaluation cases | UI/evaluation | Live local flow and 15 dev + 15 test with required multi-turn cases |
| Baseline versus final measurements | Whole team | Same cases, quality/cost/latency results, and failure analysis |
| Systematic Adversarial Testing | Proposed core bonus, mentor agreement | Defined challenge set plus measured before/after improvement |

Local tracker reset instructions will be added with its actual implementation. There is no persistent tracker to reset in the current core demo.
