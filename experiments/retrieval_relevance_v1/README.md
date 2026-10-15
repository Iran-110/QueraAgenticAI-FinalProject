# R4c/C4h5 — bounded candidate relevance on three exposed dev cases

The [protocol](protocol-v1.json) preceded implementation at`7eb76ac`.
Hassan PR50 was unchanged at`1a18749` before implementation and before the paid
run; its branch was not edited or merged. This branch preserves the same
18-source/36-chunk lexical native index, fixtures, exclusions and original gold.
No new source, case/source-ID retrieval filter, future reply or gold entered
the model evidence. This is exposed, answer-informed development work.

## What changed and why

Native top5 missed button1.39 and multiselect1.50 that existed below the cutoff.
The adapter also favored first-query/docs-first insertion order. Existing USER
version scope ran after that early cap and could not backfill.

The optional package requests25 candidates for final5, merges all query/collection
hits using generic API identity/lexical relevance/native reciprocal rank and source
diversity, then applies confirmed active USER-version scope before final selection.
Versions are not inferred from query/source text or `since_version`.
[Integration recipe and behavior](../../docs/retrieval-relevance.fa.md).

The initial [offline replay](offline-candidates-before-packing-v1.json) had
9/11 candidate states versus10/11 native states within the prompt guard. The
[whole-record budget amendment](whole-record-budget-amendment-v1.json) was then
registered at`294a01f` before its code and every paid call. It adds a12000-byte
serialized EvidenceBundle allocation, including queries/metadata/warning; it skips
whole oversized records and continues, never cutting excerpts. Existing Text
normalization remains. Final model top-k stays5 and full-prompt guard32768.
This is not a guarantee over all future messages. Empty-envelope overflow fails.

The [second actual-index replay](offline-candidate-replay-v1.json) fits all11
observed states/repair contexts under that same guard. The original failed
replay is preserved. This availability/size check is not model quality.

## Fresh model comparison

[Method](live-method-v1.json) pins all inputs, both old unknown holds, original
authorization history and the full14-table ledger journal. Paid source was
`d77704d62121f0caa21f4e6b92fd5ef5721e5908`, unchanged through six pairs.
Both arms use gpt-4o-mini,1024 output tokens,32768 input reserve and the **same**
compact-plan, decision-contract, source-selection, source-gap and repeated-query
settings. Resource guidance/source capacity stay off. Only the declared retrieval
package differs. This is not a comparison against an old model receipt.

[Original receipt](model-live-receipt-v1.json), SHA256:
`edf56d75266d97466666224738e2d5c95e2cbbc32e396188714d00c4fbdafd17`.

| Observed outcome | Native top5 | Candidate relevance package |
| --- | ---: | ---: |
| Planned jobs / turns | 6 / 12 | 6 / 12 |
| Complete selected routes | 5 / 6 | 6 / 6 |
| Fresh proposals | 10 / 12 | 12 / 12 |
| Ask / escalate / answer labels | 6 / 2 / 2 | 6 / 0 / 6 |
| Actual model sends | 15 | 12 |
| Recorded valid raw compact plans | 14 / 15 | 12 / 12 |
| Provider length / input stops / render overflow | 0 / 0 / 0 | 0 / 0 / 0 |
| Empty / stale / unvisited turns | 1 / 0 / 1 | 0 / 0 / 0 |
| Estimated cost USD | 0.015768885 | 0.010623030 |
| Observed visited-turn latency median (ms) | 5131.1 (11 turns) | 4656.75 (12 turns) |

Latency includes reached empty turns and excludes unvisited turns; no missing
duration becomes zero. Different paths/attempt counts prevent a same-answer
efficiency claim.

## Actual semantic outcome

[Disclosed assistant review](semantic-review-v1.json) inspected22 fresh proposals,
148 populated surfaces,36 selected complete excerpts and116 active USER-fact
values. All12 questions were necessary/answerable; no source gap became a request
for USER documentation research. No unsupported material causal, release,
environment or executed-action claim was found. This is unblinded assistant work
with test/workbench implementation overlap, not a calibrated human score.

- **B, button:** both treatment version turns receive, select and release the
  actual button1.39 parameter passage. It documents single-character emoji and
  rounded Material Symbols strings. Both native final bundles lack the passage
  and escalate. Observed supported topical guidance therefore improves from0/2
  to2/2 repetitions of this **one case**. This is partial button guidance;
  warning/future delivery remain unanswered and a long quote is not a human
  usefulness score.
- **A, multiselect/fragment:** both treatment version bundles contain exact1.50
  multiselect and fragment. Multiselect is selected once, fragment twice, but
  only the necessary callback question reaches the USER draft. Better evidence
  availability is not counted as delivered guidance. Neither arm invents the
  disputed key-identity release claim, root cause or fix; real callback/order is
  still missing.
- **C, Enum:** the six fresh answer labels across arms are qualified generic
  background/investigation, not Enum cause/fix. All three reached fresh correction
  proposals use active1.31.1 with unchanged code/environment. The native first-round
  empty result and unvisited correction remain failures/coverage gaps.

Zero edits appear. All19 released texts equal original drafts; three initial
Enum drafts were not released. No final solved-case or general RAG quality claim
is made. Human usefulness stays null.

All24 planned turns remain:22fresh,1empty,1unvisited. One native complete response
failed raw-wire schema after the existing allowance; canonical expansion is
unobserved for it. The other26 compact expansions/hashes are independently
checked. Raw provider content is not retained, so raw schema observations cannot
be independently reparsed from hashes alone.

The six paired initial USER states/messages and initial queries match; evidence
intentionally differs. Subsequent model queries and paths may differ. More
answers or routes do not mean more solved cases, and the whole package comparison
does not identify the effect of each component.

## Integrity and cost

[Read-only recomputation](cost-review-v1.json):3912/3912 checks. The assistant
auditor also contributed tests; independence concerns recalculation, not reviewer
separation from the implementation. It reconstructs
all27 native search observations (each includes docs/issues collection reads),
adapter selection, actual USER scope and complete whole-record packing through
the exact model bundle. Actual ranks, complete native text/metadata hashes and
the frozen manifest/storage membership are checked. No Chroma or provider client
is created by the audit. Maximum treatment evidence11751/12000bytes.

27settled model sends cost an estimatedUSD0.026391915. Cumulative local estimate
USD0.391248990 plus unchanged old holdsUSD0.0233792. All452 previous reservations
and every previous row/schema in14 tables remain; global halt,USD4.50 ceiling
and prior revocations are intact. Six scopes closed,21unused slots permanently
claimed. No new hold, pending reservation or pre-dispatch skip. Local estimates
are not a provider invoice or reconciliation of old uncertain calls.

[Structural review](structural-review-v1.json) retains all denominators and
reconstructs every fresh original analysis. The
[prospective semantic criteria](semantic-review-preparation-v1.json) distinguish
passage availability, reference selection, user-facing topical guidance,
diagnosis/fix and human usefulness. Quote correctness alone is insufficient.
Human usefulness remains null; this does not close final E2, held-out testing,
production semantic RAG or browser/live SQLite acceptance.

Model runs use the existing HTTP TestClient/DummyTracker with scripted review.
Separate fixture HTTP/SQLite acceptance tests restart/retry independently.
Defaults remain native/multiplier1/budgetNone; normal UI/live configuration is
not automatically enabled by this experiment. Ordinary live startup stays halted.

[Local verification](verification-v1.json):4150pytest, Ruff297files, three required
demos and separate fixture HTTP/SQLite457/457 pass;149 local plan links resolve.
Production Python stayed unchanged after the full suite. Subsequent changes are
method/receipt/report-script/docs only. Final-head GitHub CI remains blocked by
the owner-reported allowance problem; local verification is not a passing CI run.

Offline reproduction (choose new private output paths):

```bash
uv run python scripts/retrieval_relevance_offline_probe.py \
  --output /absolute/private/new-retrieval-replay.json
uv run python scripts/prepare_semantic_review.py prepare \
  --receipt experiments/retrieval_relevance_v1/model-live-receipt-v1.json \
  --output /absolute/private/new-review-folder
uv run python scripts/review_retrieval_relevance_run.py \
  --workbench /absolute/private/new-review-folder/workbench.json \
  --cost-review experiments/retrieval_relevance_v1/cost-review-v1.json \
  --output /absolute/private/new-structural-review.json
```

The paid campaign is closed; its identities/scopes cannot resume. Historical
receipts, gold and scoring scopes remain unchanged.
