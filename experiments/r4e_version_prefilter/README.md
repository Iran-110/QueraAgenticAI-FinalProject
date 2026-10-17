# R4e — version prefilter and dev availability benchmark

Owner: Hassan. Follows R4b (key-identity packing gap) on the final
`docs-api-release-final-v1` corpus. Dev only: no test fixture, question or gold
was opened; registered dev passages are used for scoring, never as input.

## Problem on the final corpus

The final corpus holds every API docstring for 43 versions. The candidate
policy fetches 25 native candidates and applies the exact USER-version scope
afterwards. On the 16 registered dev cases, 4–17 of the 25 candidates were the
same docstring text at other versions (`slider` alone took 24 slots in one
turn), so after scoping 0–3 eligible candidates often remained. With the real
archived case-A queries, the 1.50.0 `multiselect` and `fragment` docstrings that
reached the model on the 18-source build were crowded out entirely.

## Change (opt-in, default unchanged)

`SupportEngine(retrieval_version_prefilter=True)` sends the scope rule as a
native filter: `applicable_versions ∈ {"[]", '["<active USER version>"]'}`, or
`"[]"` when the version is unknown. Rules:

- Same eligibility as the existing scope (unversioned records plus the active
  USER version from USER facts only; superseded/evidence facts ignored).
- Requires `evidence_scope="exact_user_version"`; strict boolean; rejected
  before any port otherwise. The post-retrieval scope stays authoritative.
- No index rebuild: every registered corpus stores canonical single-version
  `applicable_versions`; a test proves filter ≡ scope chunk for chunk on the
  18-source and final corpora for six versions including unknown.
- Default engines send `filters={}` exactly as before; profiles, factories,
  live runner and freeze descriptor are untouched (wiring is a core decision).

## Benchmark

`scripts/r4e_dev_availability.py`: for every dev turn with registered
`answer_required` passages (19 requirements, 16 eligible under the scope rule),
first-round query from `build_initial_query`, candidate policy with and without
the prefilter, passages observed in the final bundle. Native reads use a
disposable copy; original files are hashed before/after.

```bash
uv run python scripts/r4e_dev_availability.py --index runtime/final-corpus-v2 --manifest-sha256 d5158882f0c266820425f7ab82627939b9af77ae07f70b5b967c5abdb8fd0cf4 --output experiments/r4e_version_prefilter/dev-availability-v1.json
```

Stand-in result through the real engine/adapter/retriever code (exact-L2 Chroma
replica, recorded before the Windows run): eligible requirements in the 25
candidates **5 → 10**, reaching the model **2 → 4** of 16.
[Real-Chroma receipt](dev-availability-v1.json).

## Levers measured and rejected (offline exploration, same 16 dev turns)

| lever | effect with prefilter |
|---|---|
| structure-aware markdown segmentation (1000/2000/3000 chars) | none or worse |
| larger lexical embedding (4096 dims) | none |
| BM25 first stage / BM25 re-rank of native top-100 | recall@25 10 / 9 |
| ranking variants (no markdown-name identity, no source diversity, lexical first) | 4/16 each |
| API-name backfill of docstrings named in the query | 4/16 |
| larger byte budget (core setting) 16k / 20k / 28k | 4 / 5 / 5 |
| release-note segmentation at version/bullet lines (250–1500 chars) | 3–4/16; release notes 0/5 |
| IDF-weighted lexical vectors (256/2048 dims), with or without that segmentation | 4–5/16; release notes 0/5 |

**Release notes.** Five of the 16 eligible requirements are single release-note
lines (2024–2026 pages). None enters the 25 candidates in the first round under
any variant above, with or without the prefilter: the user describes a symptom
("the page goes blank"), the note describes the fix in other words, and their
native rank stays between 100 and 1,575 of about 2,200 chunks. Reaching them
needs a model-authored refinement query (second round) or semantic retrieval;
first-round lexical changes to the corpus do not.

The remaining gap is first-stage lexical relevance for conceptual passages
(mostly `widget-behavior.md` and release-note lines) under a 5-hit cap. Model-
authored refinement queries (second retrieval round) are not modelled here and
may recover part of it. Case A's registered native requirement is the 1.50.0
`multiselect` key passage; the R4b key-identity chunk is not in the official
dev gold.

## Limits

Availability only: not semantic support, answer quality, human usefulness or
held-out evaluation. Approximated first-round queries, identical across arms.
Lexical-hash embedding. Ranking, packing and the final count cap are unchanged.
