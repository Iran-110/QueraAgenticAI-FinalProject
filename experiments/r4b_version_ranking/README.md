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
uv run python scripts/r4b_version_ranking_receipt.py --index runtime/r4b-coverage-18 --pr50-ref 1a18749 --output runtime/r4b-version-ranking-replay.json
```

The script refuses an index whose manifest differs from the registered
18-source/36-chunk build (`24815c44…`). It hashes every original file, copies
the complete tree to a temporary directory, checks copy equality, and opens
native clients only on that disposable copy. It closes the native client and
removes the copy on success or failure; any added, removed or changed original
file fails the replay and reports the differing hashes. Fresh receipts retain
the before/after original file hashes, including the manifest and native files.
Use a fresh output path; the archived receipts are retained unchanged.

The script replays the **8 unique state/query/round triples** among the 24
archived real requests of `core_repeat_repair_v1`, the same set the PR50
review used. Repeated requests are collapsed; these are eight unique query
strings, not 24 independent cases.

The historical `receipt-v1.json` field `index.unchanged` established logical
verification and unchanged manifest bytes only. It did not hash all physical
index files or establish their custody. A fresh copy-only replay establishes
preservation of its current input file hashes; it does not restore historical
physical bytes or retroactively establish their preservation in the old run.

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

The original 16 cases cover ranking and version scope; five additional neutral
controls cover disposable native reads, full-file mutation detection, client
cleanup on construction/final-verification failure, and byte packing versus
the count cap. All 21 pass locally using synthetic native-like files and an
injected client. The original report recorded 123 passed on Windows 11 with
the existing relevance, adapter and evidence-scope suites.

## Coverage, relevance and exclusion review

```bash
uv run python scripts/r4b_coverage_relevance_review.py --receipt experiments/r4b_version_ranking/receipt-v1.json --labels experiments/r4b_version_ranking/relevance-labels-v1.json --exclusion-manifest data/evaluation/split-e1-v1/split-manifest.json --output experiments/r4b_version_ranking/review-v1.json
```

[Labels](relevance-labels-v1.json) were drafted by the assistant and confirmed by Hassan
(`human_confirmed: true`, not an independent review), from chunk text and the human
case review; they are applied after retrieval and never select evidence.
Required evidence: case A multiselect and fragment at the USER release plus
the widget-behavior.md key-identity chunk (`0:4000`); case B button at the
USER release; case C none in corpus (answer-linked guide excluded).

| arm | required reached | final hits | direct | background | off_topic |
|---|---|---|---|---|---|
| PR50 head | 1/5 | 30 | 1 | 21 | 8 |
| main native | 1/5 | 30 | 1 | 21 | 8 |
| R4b path | 3/5 | 25 | 4 | 16 | 5 |

- Still missing in **every** arm: the widget-behavior.md chunk stating that
  key-based identity was introduced from v1.50 to v1.55. The case review says
  this exact text must reach the model; index membership is not enough.
  Native/PR50 never fetch it (outside top 5). The R4b path fetches it as
  candidate **23/25** (initial) and **16/25** (version turn). The corresponding
  final bundles contain **2 and 4 hits**, below the cap of 5, so that cap
  cannot explain this omission. The unversioned chunk is eligible; its omission
  is consistent with ordered whole-record packing under the 12000-byte budget.
  The old receipt does not contain stepwise packing diagnostics. Fresh receipts
  add a candidate projection checked against the actual final hits, reporting
  pre-scope rank, eligible rank, attempted serialized bytes and byte-budget or
  count-cap decisions separately. This is diagnostic replay, not additional
  engine telemetry. Packing/order remains a dev follow-up; the 1.50 release
  note is outside this profile.
- Exclusion holds: 0 indexed Issues/comments, only `doc` sources, no
  custom-classes guide or release note indexed, no final-bundle violation.
  Checked against the final `split-e1-v1` manifest's `index_exclusion` as
  well (count and hash in the review output): every listed Issue is absent
  from this docs-only build. No `split-e1-v1/test` case or query was used.

## Limits

Availability only, not semantic support, answer quality, human usefulness or
held-out evaluation. Exposed dev families; lexical-hash embedding. Family
labels report outcomes and never select evidence. The full suite on Windows
shows 8 failed / 21 errors outside the adapter/engine scope path (POSIX
permission modes, Windows 32767-char environment limit, path separators, and
two pilot-corpus/seed byte checks; the actual index build above still matched
the registered manifest). GitHub Actions remains blocked by billing.
