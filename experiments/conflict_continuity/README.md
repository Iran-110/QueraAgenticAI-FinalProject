# C4b: keep a declared conflict through refinement

Delivery and final Linux/Windows publication checks:
[PR #41](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/41).

A current-pool omission is not a resolution of a conflict already declared by
the caller. On actual baseline `03225e2`, an authored `retrieve_more` followed by
an answer could lose that status when one conflict member disappeared or changed
content. The answer had current citations, but incorrectly told the maintainer
that no conflict had been declared.

The [protocol](protocol-v1.json) and fourteen frozen controls were committed at
`c9f15b8` before the production fix. Their test SHA remains
`51ea7362e9a3f2fd3a87df824d939ef7018472305fe46113698b93d39c46a236`.
The [byte-exact comparison receipt](comparison-v1.json) executes archived old
source and clean candidate `8cc41bf`, with identical tests, four historical V8/V9
fixture pins and authored planner choices. Snapshot-bound imports and disabled
network prevent mixed installed code or provider calls. The receipt includes
all fourteen outcomes and complete requests/results/handoffs for seven target
controls; the baseline is executed, not inferred from expected failures.

| Registered software control | Baseline | Candidate |
| --- | --- | --- |
| All fourteen unchanged controls | 7 pass / 7 fail | 14 pass / 0 fail |
| Unsafe answers after omission, same-ID content change or warning-only resolution | 3 reach approval | 0 reach approval; 3 `grounded_conflict_unresolved` failures |
| Four safe ask/escalate targets, with explicit unresolved status and current-only sources | 0 meet every control | 4 meet every control |
| Remaining seven controls, including fresh scope and clean refinement | 7 pass | 7 pass |

The four safe decisions were accepted by both versions. The change is the
missing unresolved-status disclosure, not four newly successful decisions.
`ask` keeps the exact caller-registered user question; disclosure appears in
the maintainer summary/rationale. Escalation also discloses it in the user draft.

These are **authored software controls**, derived in memory from one exposed,
answer-informed #12782/#12629 V9 family with an explicitly synthetic conflicting
source. No model selected either round's plans. Original fixtures, prior paid
receipts and reviewer criteria are unchanged. This adds **zero independent
evaluation cases**, measures neither real RAG nor model quality, and supplies no
human usefulness score. Keep the family and its case/comment/answer/outcome/
duplicates outside the real RAG corpus and independent test set.

## Boundary and connected verification

[Verification](verification-v1.json) records **2841 full pytest passes**, Ruff,
locked dependencies and three offline demos. The fourteen controls plus 25
lifecycle/boundary and 5 HTTP tests are **44 new regressions**, not 44 independent
Issues. The [separate existing HTTP/SQLite receipt](http-sqlite-v1.json) passes
457/457 checks, including fresh-process restart, on clean `8cc41bf`.

The five new FastAPI/SQLite checks use intercepted `MockTransport` and a
temporary ledger: unsafe outputs do not stage a proposal; safe escalation has
an actual enriched planner request bound into its canonical handoff; exact human
approval, retry and SQLite application restart leave one action. This is an
in-process API test, not a manual browser run or a real provider experiment.
[Independent assistant audit](review-v1.json) reviews the original receipt and
source separately; human quality scoring remains null.

**Real provider requests and paid cost for this delivery: zero.** The designated
ledger, existing uncertainty, quarantine, halt and continuation are preserved.
The earlier incomplete C4a paid baseline remains incomplete; C4/E1/E2/R4/E4/E5/C5
remain open. Existing one dev case and zero held-out cases are unchanged.

## Reproduce offline

From the repository root, without keys:

```bash
uv sync --locked --group dev
uv run pytest tests/test_conflict_continuity.py tests/test_conflict_continuity_boundaries.py tests/test_conflict_continuity_http.py
uv run python scripts/conflict_continuity_comparison.py --output /tmp/conflict-continuity-new.json > /tmp/conflict-continuity-console.json
```

Choose unused output paths; the runner refuses to replace an existing receipt.
`--arm baseline` executes only the actual historical source. The copied frozen
test bytes are the same in both arms. Current receipt commits/source hashes identify
the runtime epoch; later publication-only docs/CI commits do not rewrite it.
CI repeats this code comparison on Linux and Windows alongside the frozen tests.

See the [Persian integration guide](../../docs/conflict-continuity.fa.md) for the
scope, source-gap marker, actual-request capture and unresolved limitations.
