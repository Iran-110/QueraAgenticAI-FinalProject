# Current retrieval context — exposed development comparison

Preregistered and pushed source: `0b3f1cc05f83913eaad41a03d6e454d95b1928c1`;
[Linux/Windows CI](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38419633473).
The comparison imports only the original query builder from main `109f59e`,
keeping current case/contracts/core fixed. It does not compare two whole releases.
The protocols, fixture and original receipts remain unchanged.

## What improved

The previous correction query began with historical reasoning text. Retired
Streamlit 1.50.0 and Python 3.12.9 displaced the latest correction; the current
1.49.0 parameter appeared at the end. The new query separates current user facts,
latest raw input and bounded historical topic hints from the unchanged full
reasoning history. Whole current code/comparisons remain in reasoning.

The ten variations are authored development controls from exposed #12782/#12629,
not independent issues or held-out cases. Familiarity with those issues informed
their construction; their answers were not supplied as retrieval evidence.
Fixtures, answers, outcomes and issue families must stay outside the real corpus.

| Query variant | Literal controls passing | All controls per scenario | Latest coverage | Topic coverage |
| --- | --- | --- | --- | --- |
| Original history prefix | 72/96 | 2/10 | 4/10 | 9/10 |
| Latest input only | 74/96 | 2/10 | 10/10 | 2/10 |
| Current state and topic | 96/96 | 10/10 | 10/10 | 10/10 |

[Offline result](offline-result-0b3f1cc.json) records literal expectations fixed
before the run. [Existing-index result](index-result-0b3f1cc.json) adds 60 actual
collection reads with query/ID/distance/version/text hashes, on the same verified
14-source/30-chunk docs-only lexical Chroma index. These are query controls and
retrieval observations, not 60 cases or semantic accuracy scores. Current queries
returned six unscoped and four 1.64.0 top hits across the ten variations; no known
user version had a matching versioned top hit. Query cleanup does not establish
better retrieval ranking. The local index path is retained as original provenance.

## Actual paid pair

[Registration](live-registration-0b3f1cc.json), [unaltered receipt](live-result-0b3f1cc.json)
and [separate assistant source review](review-0b3f1cc.json) preserve the full output.
There is no human rubric score. Before both sends, the same state, complete
reasoning history, gap catalog, index, bounded prompts and acceptable decisions
were registered. The explicit environment change leaves Python unknown; ordinary
correction preserving Python is a separate offline control.

Both arms made exactly one send/attempt and asked:

> Can you share the parent selector callback that resets Session State?

The callback is missing user-supplied app code, which the user can provide.
Documentation cannot establish this app's state-update order. The model selected
a caller-curated question; it did not independently discover or solve the cause.
Both user drafts avoided an unsupported fix and reasking the known version.
Maintainer summaries attributed facts and quotes, retained unknowns, and did not
claim execution or resolution. No tracker staging, approval or action occurred.

The legacy arm returned an **unversioned Session State** excerpt mostly about
serialization/caveats. The current arm returned **1.64.0 text_input** documentation
for a user on **1.49.0**, about validation/live/query parameters. The renderer
explicitly marked it historical/other-version, not proof of applicability.
Neither source establishes the multiselect/fragment root cause. The paid pair
shows the same acceptable question, **no demonstrated RAG or decision-quality
gain**, and a concrete version/relevance gap for R4.

| Arm | Serving model | Input/output tokens | Settled estimate USD |
| --- | --- | --- | --- |
| Legacy | gpt-4o-mini-2024-07-18 | 2678/169 | 0.000553410 |
| Current | gpt-4o-mini-2024-07-18 | 2710/174 | 0.000561990 |

Total new estimated cost: **USD 0.001115400**, actual account charge unknown.
No new pending/uncertain reservation remains. The original USD 0.02 uncertain
record, global halt and existing continuation cap remain intact. Ledger settled
estimate is USD 0.12375825 across 180 records; the same grant has USD 0.00491479
remaining. This does not reconcile C5 or authorize general live startup.
The paid protocol is one-shot: its original ledger fingerprint has been consumed.
Do not rerun it, reset its ledger or rewrite pins to repeat the paid pair.

## Subsequent offline protection

After this paid observation, the persistent HTTP factory exposes the existing
`evidence_scope` policy. Default `all` preserves comparison workflows;
`live_backend.configured_app` chooses `exact_user_version` for advice about the
current installation. Versioned mismatches and unknown-user/versioned hits are
excluded before reasoning; unversioned hits stay explicitly unconfirmed.
The policy does not rerank/backfill RAG, infer versions from prose, or guarantee
semantic relevance. It can leave no source, so an appropriate ask/escalation
remains possible. This additional binding is verified offline; it was **not**
present in either paid arm and cannot be credited as a live improvement.

Reproduce only offline controls with fresh output paths:

```bash
uv run python scripts/retrieval_context_comparison.py --validate-only
uv run python scripts/retrieval_context_comparison.py --output /tmp/query-context-fresh.json
uv run pytest tests/test_current_retrieval_context.py tests/test_persistent_version_scope.py
```

Final independent dev/test fixtures, version-aware retrieval/source coverage,
human rubric review, frozen corpus/exclusion and C5 reconciliation remain open.

[Local verification](verification-v1.json): 2714 pytest, locked dependency sync,
Ruff and all three required offline demos pass on production code `a06925f`,
with publication artifacts/documents still uncommitted. Actual HTTP/SQLite
fresh-process acceptance passed457/457; its original dirty working-tree release
identity is preserved and every recorded source hash matches `a06925f`. Clean
release CI remains separate. The 21 new HTTP scope tests and existing actual-page
mocked-provider tests exercise exclusions, correction, refinement, restart and
immutable review retry without using the production ledger or key.
