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
