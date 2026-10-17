# Final corpus build — `docs-api-release-final-v1` (R1/R2, E2ad build gate)

Owner: Hassan. Adds a third closed protocol to the existing loader so a wider,
connectable index exists for the native freeze. The two historical profiles
(14 and 18 sources) keep their own code path; their snapshots from current
inputs are unchanged and checked by tests and the build receipt.

## Source policy

| kind | sources | chunks | version provenance |
|---|---:|---:|---|
| product docs (`docs_markdown`) | 47 | 74 | none; snapshot of pinned docs commit |
| release notes (`release_note`) | 9 | 104 | none; never inferred from text |
| API docstrings (`docs_generated`) | 1,172 | 1,649 | exact docstring version (43 versions, 1.22.0–1.64.0) |
| **total** | **1,228** | **1,827** | |

- Selection is closed: [allowlist](allowlist.json) lists every source ID; the
  loader also pins the count and a hash of the sorted ID set, so a manifest
  with any other selection is rejected.
- Everything comes from the hash-pinned seed package at docs commit `695e6ce`;
  text, span, URL and hashes are kept losslessly (4,000-character chunks).
- Denied: `content/develop/concepts/app-design/custom-classes.md` (answer-linked
  Enum guide), in code and in the allowlist. It is not in the seed scope anyway.
- Release notes, `widget-behavior.md` and versioned docstrings stay in, per
  `index_exclusion.keep_in_corpus_note` of the split manifest.

## Exclusion

[`exclusion-v1.json`](exclusion-v1.json) is extracted from
`data/evaluation/split-e1-v1/split-manifest.json` (`index_exclusion`): 90 Issue
IDs with all comments/outcomes, plus the direct-answer documents. The builder
requires it to contain every development-exposed Issue and the 46 historical
reservations. No Issue or comment is indexed (`indexed_issue_count = 0`). Only
the split manifest's exclusion metadata was read; no test fixture, gold or
review file was opened.

After the evaluation freeze, refresh the exclusion and rebuild into new names.
`build-receipt-v1.json` (before the verification session) and
`build-receipt-v2.json` (current pins) and `runtime/final-corpus-v2` stay as
they are; both scripts also refuse an existing output.

```bash
uv run python scripts/prepare_final_corpus_inputs.py --split-manifest data/evaluation/split-e1-v1/freeze/split-manifest-frozen-v1.json --exclusion-out experiments/final_corpus_v1/exclusion-v2.json
uv run python scripts/build_final_index.py --exclusion experiments/final_corpus_v1/exclusion-v2.json --destination runtime/final-corpus-v3 --receipt experiments/final_corpus_v1/build-receipt-v3.json
```

The native gold pins then come from `build-receipt-v3.json`.

## Build (offline, zero API)

```bash
uv run pytest tests/test_final_corpus.py tests/test_pilot_corpus.py tests/test_offline_index.py -q
# Windows: tests/test_pilot_corpus.py now reads seed/split files as UTF-8 explicitly;
# with the default cp1256 locale two of its checks failed before this change.
uv run python scripts/build_final_index.py --destination runtime/final-corpus-v1 --receipt experiments/final_corpus_v1/build-receipt-v1.json
```

The receipt carries the native pins: `build`, `index_snapshot`,
`index_manifest_sha256` (physical `pilot-manifest.json`), `allowlist_sha256`
and `exclusion_manifest_sha256`. `corpus_manifest_sha256` stays null: it is the
evaluation packet's corpus JSON, owned by evaluation, not the physical index
manifest. The receipt also records a deterministic in-memory rebuild, both
historical snapshots, source/chunk counts and an adapter smoke on two generic
API queries with timing.

## Loader changes

- `pilot_corpus.py`: `FINAL_PROTOCOL`, `build_final_corpus` and a separate
  validator. `release_note` is accepted only under this protocol; old protocols
  still accept `doc` only and reject the final allowlist (and vice versa).
- `offline_index.py`: expected vectors are computed once when the index is
  opened instead of on every verification (same comparison, same strictness),
  and writes go in batches of 500 (historical profiles fit in one batch).

## Connection blocker: per-search verification (resolved here)

`VerifiedChromaClient` re-reads and compares **every stored row** on each
access. One `StreamlitRetriever.search` triggered **22** full verifications
(get_collection/metadata/query, before and after, both collections). With
36 chunks this was invisible; with 1,827 chunks one search took **1.8 s on an
in-memory stand-in** and **4.2 s / 5.1 s with real Chroma on Windows 11**
([before-fix receipt](build-receipt-v1.json), `adapter_smoke`). An engine run can
issue up to four searches, so a turn could spend 10–20 s in verification alone.

Decision (Hassan, to save time with the deadline close): **verify full storage
once before and once after each search** via `VerifiedChromaClient.read_session()`,
which `StreamlitRetriever.search` opens when its client offers it.

- Every returned row is still checked against the frozen corpus (`_verify_result`).
- Storage changed during a search is rejected at the closing check
  (`PilotIndexChanged`) and by every later read.
- The lock is held for the whole search; access outside a session (direct facade
  use, construction, `open_verified_index`) keeps per-access verification.
- A file-timestamp fingerprint was rejected: Windows can report stale mtimes for
  files SQLite holds open, which could hide a write.

Result: 2 full verifications per search. Real Chroma on Windows 11:
**4.2 s / 5.1 s → 0.49 s / 0.47 s** per search
([build-receipt-v2.json](build-receipt-v2.json)); same snapshot and pins as v1.
150 related tests pass on Windows 11, including every storage-mutation check in
`tests/test_offline_index.py` against real Chroma.
[`tests/test_offline_index_session.py`](../../tests/test_offline_index_session.py)
covers the count, nested sessions, mutation during a search, changed returned
rows and recovery after a failure, without chromadb, plus a real-Chroma variant.

Ranking/packing of the key-identity evidence is unchanged and stays a separate
dev-only task.

## Limits

Lexical-hash embedding; no semantic retrieval-quality or answer-quality claim.
Built before the evaluation freeze. Membership in this index is not evidence
reaching the model.
