# C4h4: strict compact wire, exposed development comparison

The [protocol](protocol-v1.json) preceded implementation. The
[method](live-method-v1.json) pinned inputs, source, both unknown holds and the
full14-table ledger journal before any fresh authorization. The unchanged
18-source/36-chunk lexical native index and main ranking were used for both arms.
No fixture, gold, corpus, exclusion or held-out case was changed. The prospective
case-A amendment was [registered before model calls](semantic-review-preparation-v1.json).

This compound treatment replaces model-echoed long references with current-request
integer indices and uses decision-specific wire fields. It retains the complete
request digest and expands selections locally to the public GroundedPlan. The
model no longer independently echoes each source digest. Default is **off**;
schema/binding success does not authenticate a source or prove semantic support.
[Behavior and failure rules](../../docs/compact-plan-wire.fa.md).

## Original run and observations

[Original receipt](model-live-receipt-v1.json), SHA256
`3aef0c1c19961df987af752a449376359523772aae94bc1520e86b9b2ce49e52`.
Paid source was `96f7c38`; source/index stayed unchanged through all six pairs.
Each family ran twice, with balanced arm ordering. Same gpt-4o-mini,1024 output
tokens,32768 input guard, two attempts and common renderer/repair settings.

| Observation | Canonical wire | Compact wire |
| --- | ---: | ---: |
| Planned jobs / turns | 6 / 12 | 6 / 12 |
| Complete selected routes | 4 / 6 | 5 / 6 |
| Fresh proposals | 10 | 10 |
| Ask / escalate / answer labels | 6 / 3 / 1 | 6 / 2 / 2 |
| Received provider responses | 18 | 14 |
| Valid plan shape observations | 15 / 18 | 14 / 14 |
| Schema-invalid complete outputs | 3 | 0 |
| Provider length stops | 0 | 0 |
| Input guard before reservation/send | 0 | 1 |
| Renderer quote-size rejection | 1 | 0 |
| Empty / stale / unvisited turns | 1 / 1 / 0 | 1 / 0 / 1 |
| Median output tokens | 161.5 | 66.5 |
| Estimated cost USD | 0.020278005 | 0.014556300 |

All24 planned turns remain:20fresh,1stale,2empty,1unvisited. Canonical observations
describe original canonical outputs; compact shape observations are recorded on
the original short wire before local expansion. Raw provider content is not
retained, so independent schema reparsing from these hashes is unavailable.
The cost audit independently checks all14 compact expansions and canonical hashes.
Six paired initial requests are identical; subsequent requests/paths can differ.
Token medians therefore are descriptive, not a same-answer efficiency estimate.

One new Enum refinement hit the input guard: compact33601/32768 bytes including
the fixed margin. Canonical projection of that **same** request is34667 bytes;
neither fits. It is not evidence of treatment-induced prompt-size growth on that
request. The original428-check preflight covered107 archived requests and their
repair contexts, not all possible future retrieval results. No evidence is
truncated and the unvisited correction remains in the denominator.

This small run shows fewer observed shape errors and one more complete route;
it does not establish broad reliability or solve the original length failures.
Neither arm had a length stop this time. Three `answer` labels are qualified
background/investigation handoffs; they do not establish the requested Enum
cause/fix or version-specific button-logo capability. Supported topical technical
answers remain zero. Human usefulness is unscored; no flag is promoted.
One schema-valid canonical correction also exceeds the renderer's full-quotation
limit; its old proposal stays stale and its approval is rejected. It is not a
fresh answer. Shape validity alone does not establish a renderable response.

## Accounting and review

[Independent read-only cost/provenance audit](cost-review-v1.json):1671/1671 checks,
32settled sends,USD0.034834305 estimated; cumulative settledUSD0.364857075 plus
unchanged old holdsUSD0.0233792. All420 prior reservations and all14 tables are
preserved; global halt,USD4.50 ceiling and prior revocations remain. Six scopes
closed;16unused slots permanently claimed. A typed pre-dispatch ContextLimitExceeded
has no reservation or send. No closed identity can resume. These are local list-price
estimates, not a provider invoice or reconciliation of the old uncertain calls.

[Structural review](structural-review-v1.json) reproduces20 complete original
analyses, keeps all turn statuses and separates wire shape from canonical output.
[Disclosed assistant semantic review](semantic-review-v1.json) inspects actual
sources and current USER facts:12 necessary answerable questions,23 exact selected
references, two fresh Enum corrections on1.31.1. The third visited correction
retains a stale old proposal and409 approval. None is a human usefulness score.
Usefulness/support need separate review of all output surfaces and actual excerpts;
an `answer` label or successful renderer is insufficient. Human-review sidecars
remain blank. This is exposed, answer-informed dev data; not held-out/final E2,
production RAG quality or browser/SQLite live acceptance. The model study uses
TestClient/DummyTracker and scripted approval. Separate fixture HTTP/SQLite
acceptance tests persistence/retry, not model quality.

[Local verification](verification-v1.json):4006pytest, Ruff289files, all three
required demos, HTTP/SQLite457/457 and145 plan links pass. Production Python was
unchanged after the full suite; subsequent changes are registered method,
ancestry sync, receipts, the read-only report script and documentation. GitHub
Actions remains blocked by the owner-reported exhausted allowance.

To regenerate an offline private review packet and structural report:

```bash
uv run python scripts/prepare_semantic_review.py prepare \
  --receipt experiments/core_compact_plan_v1/model-live-receipt-v1.json \
  --output /absolute/private/new-review-folder
uv run python scripts/review_compact_plan_run.py \
  --workbench /absolute/private/new-review-folder/workbench.json \
  --cost-review experiments/core_compact_plan_v1/cost-review-v1.json \
  --output /absolute/private/new-structural-review.json
```

The paid method is closed. Its CLI preflight correctly refuses reused identities;
these offline commands do not authorize another call.
