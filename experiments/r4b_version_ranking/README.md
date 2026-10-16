# R4b — version-aware candidate ranking: before/after receipt

Owner: Hassan. Responds to the [PR50 review](../rag_pr50_review/README.md).
PR50's adapter (`1a18749`) is superseded, not patched: the already-merged
R4c path on main (`query_relevance_v1`, engine `retrieval_candidate_multiplier=5`,
`evidence_scope="exact_user_version"`, 12000-byte whole-record packing) fixes
all three reviewed defects. This task adds regression tests and a native-index
receipt proving that; no adapter, engine, corpus, index or default changed.

## Reproduce (zero API, no credentials)

```bash
uv run pytest tests/test_r4b_version_ranking.py
uv run python scripts/build_pilot_index.py --destination runtime/r4b-coverage-18 --allowlist experiments/dev_rag_coverage_v1/allowlist.json --split-manifest experiments/dev_rag_coverage_v1/split-manifest.json
uv run python scripts/r4b_version_ranking_receipt.py --index runtime/r4b-coverage-18 --pr50-ref 1a18749 --output experiments/r4b_version_ranking/receipt-v1.json
```

The script refuses an index whose manifest differs from the registered
18-source/36-chunk build (`24815c44…`) and verifies the index is unchanged
after the replay. Queries are the 24 archived real requests of
`core_repeat_repair_v1` (8 unique states), the same set the PR50 review used.

## Result ([receipt](receipt-v1.json))

Pre-scope rank of the needed release record / whether it reached the model
at the active USER version:

| case | turn | USER version | record | PR50 head | main native | R4b path |
|---|---|---|---|---|---|---|
| a | initial | unknown | multiselect | – / no | – / no | 2,3 / no |
| a | initial | unknown | fragment | – / no | – / no | 1 / no |
| a | version | 1.50.0 | multiselect 1.50 | – / no | – / no | 2,3 / **yes** |
| a | version | 1.50.0 | fragment 1.50 | 1 / yes | 3 / yes | 1 / **yes** |
| b | initial | unknown | button | – / no | – / no | 1–4 / no |
| b | version | 1.39.0 | button 1.39 | – / no | – / no | 1 / **yes** |

- Over-fetch is real: backend `n_results` is 5 in PR50/native and 25 in R4b.
- Newest-first displacement is gone: for the 1.39.0 user, the 1.49/1.50/1.64
  button records rank 2–4 and are removed by scope; 1.39.0 reaches the model.
- Unknown version (initial turns): no versioned record reaches the model in
  any arm; this is the intended conservative policy (ask the version first).
- `version_unsafe = none` across all 8 states × 3 arms; enum case C stays on
  unversioned guides in every arm.
- `since_version` stays introduction metadata (tests): never exact
  applicability, also with explicit `version=None` or `applicable_versions=[]`.

Tests: `test_r4b_version_ranking.py` 16 cases; with the existing relevance,
adapter and evidence-scope suites, 123 passed on Windows 11.

## Limits

Availability only, not semantic support, answer quality, human usefulness or
held-out evaluation. Exposed dev families; lexical-hash embedding. Family
labels report outcomes and never select evidence. The full suite on Windows
shows 8 failed / 21 errors outside the adapter/engine scope path (POSIX
permission modes, Windows 32767-char environment limit, path separators, and
two pilot-corpus/seed byte checks; the actual index build above still matched
the registered manifest). GitHub Actions remains blocked by billing.
