# Review of Hassan's RAG PR #50

Review target: [PR #50](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/50),
exact head `7581dcc9505afa4929879c65aa8de5222bdb43bd`, base
`f78c6e965e27a04b701b4d8a4df653617df42ead`. Later pushes need a new review.

[Original independent receipt](review-head-7581dcc-v1.json), SHA256
`7535c89e51d5561b05fbb09a040731a5d3ae2d1d870e8a6a8cd9b973dc60566b`,
is a synthetic offline code control, with exact Git blobs loaded in memory.
The ranking control applies the base engine's version predicate; it does not
claim a full real-index/model route. The separate 91 existing tests run the exact
candidate adapter and base engine, with remaining dependency and test pins.

The reviewed head is not merge-ready:

- Newest-version-first sorting displaces a relevant 1.39.0 record with unrelated
  1.50.0/1.51.0 records at top_k=2. Current-version scoping then retains zero
  candidate hits versus one baseline hit.
- The backend still receives `n_results=request.top_k`; the claimed 5x over-fetch
  is absent. The reported 96 query-composition checks do not test this ranking,
  index retrieval or model decision quality; its documented command omits `--index`.
- `since_version` is treated as exact applicability, including when explicit
  `version=None` was supplied. Introduction version semantics need a reviewed
  contract; the canonical index already carries `applicable_versions`.
- Both Linux checks fail on Ruff E722; Windows checks pass. All 91 existing
  selected tests pass, but do not cover the demonstrated ranking regression.

Hassan owns the correction: bounded actual candidate fetching, relevance and
explicit version policy, metadata semantics, regression controls for unknown,
older/current and corrected versions, and native-index before/after receipts.
This review edits none of his RAG files, sources, index or branch. Root's
repeat-query comparison keeps the main adapter unchanged as a separate factor.

## New head 1a18749, reviewed 2026-10-15

Hassan force-updated the branch to `1a18749159e09abd4f19d2417dc7fa1dc9146eb2`.
[New independent receipt](review-head-1a18749-v1.json) preserves the old review.
Reproduce from this repository (no credentials, paid calls or rebuild):

```bash
uv run python scripts/review_rag_pr50_head.py --output runtime/pr50-new-head-review.json
```

The exact new adapter is loaded from Git in memory. All **24 archived native
retrieval requests** replayed on the verified18-source/36-chunk index return the
same membership in both versions. Order can change; this is not a relevance
score. Every backend call still receives the requested top_k, not top_k*5.
The mixed-collection synthetic control still loses the current1.39 source in
favor of unrelated future versions. `since_version` still becomes exact
applicability; canonical index records already have `applicable_versions`.
No files on Hassan's branch or in the index were changed.

The advertised context-comparison command was independently rerun:96/96 literal
query controls, **index_queried=false, zero collection reads and zero model calls**.
It cannot establish that the ranking delivered the missing records to a model.
Local Ruff lint now passes; `ruff format --check` still fails on the adapter.
GitHub job116157085323's annotation reports account payments/spending-limit
failure **before the job started**. This infrastructure failure is separate from
both the local formatting failure and the demonstrated behavior problems.
No billing setting was changed. PR50 remains unmerged.
