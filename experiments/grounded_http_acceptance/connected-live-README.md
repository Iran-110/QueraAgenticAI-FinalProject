# Connected live development pilot, 2026-10-13

This is **one exposed, answer-informed development family**, not a final quality
evaluation or held-out test. The protocol and executable source were committed
and pushed at `fbac1b4788f31d737dcb4341146cf1771225990b` before any provider send.
Shared contracts, Hassan's adapter, the tracker, seed and historical receipts
are preserved. Default UI routing remains scripted/mock; this is a separate
explicit opt-in probe, not a general live UI launcher or evaluation factory.

| Artifact | What it establishes |
| --- | --- |
| [Original protocol](connected-live-protocol-v1.json) | Current visible inputs, known/missing data, acceptable decisions and bounded budget before execution |
| [Original receipt](connected-live-result-fbac1b4.json) | Actual provider observations, complete handoffs, real retrieval, persisted facts and operational checks |
| [Separate assistant review](connected-live-review-fbac1b4.json) | Full-surface source/question review, protocol inconsistency and negative findings; no human gold or formal quality score |
| [Verification](connected-live-verification-v1.json) | Artifact hashes, baseline cleanup replay, offline checks and publication source |

The receipt is an unchanged byte copy of the original private output:
SHA-256 `7bb15da9fafcbfaf90557b6ece5d6710d9044eedf2bf67ff32d649f39228112c`.
It records **two actual sends**, exact verified serving ID
`gpt-4o-mini-2024-07-18`, 5,323 input / 342 output tokens and **$0.001104015
estimated new cost**. Actual account charge remains unknown.

The existing 14-source/30-chunk approved docs index is verified before and after
execution, with native Chroma and local lexical-hash embeddings. Both current
proposals ask for the missing parent callback; no diagnosis, fix or resolution
is asserted. The same source chunk has unknown version metadata and remains
explicitly unconfirmed. The review checks every analysis surface and binds
each handoff to its actual last retrieval and grounded request.

Operational checks pass: revisions 1/2 and fresh proposal, 1.50.0 superseded by
1.49.0, no automatic release/action, unauthenticated review refused, exact
ingress retry without new ports/sends, latest projection recovered after
same-interpreter application recreation, closed clients, original halt and
quarantine preserved, two-send and reservation bounds. This is in-process HTTP
through TestClient and real SQLite, not a live browser or fresh-process claim.

## Preserved protocol inconsistency

The second turn sets `visible.context_changed=true`, which explicitly declares
a **different environment** under [the existing contract](../../docs/user-turns.md).
Its reviewer-only `known` expectation also listed Python 3.12.9. Those conflict:
unreconfirmed Python correctly becomes superseded/unknown. The protocol and
receipt are not retroactively edited. This is a preregistration mistake, not a
core failure or successful proof that Python was preserved. Two post-execution
offline regressions exercise both meanings: ordinary partial version correction
keeps Python; an explicit environment switch retires it.

## Limits learned from the actual execution

- Source fidelity passes; targeted relevance is weak. Both queries return the
  same unversioned Session State chunk, mostly serialization/caveats. It does
  not establish a fragment/multiselect cause or an applicable fix. The indexed
  chunk starts/ends mid-section; quoting a whole chunk is not a complete paragraph.
- The correction search still contains labelled historical version text plus
  current 1.49.0. Current facts are correctly bound, but old-version ranking bias
  has not been ruled out. Query composition and relevance need controlled dev
  comparisons before choosing a final retrieval policy.
- Parent-callback and failing-interaction gaps are manually curated caller
  vocabulary. Model selection among them does not demonstrate automatic gap
  discovery. The same unanswered, unapproved question can remain appropriate
  after correction; it does not repeat an already supplied callback answer.
- `top_k=1` retains a whole excerpt inside the unchanged conservative input
  reserve. Repairs/refinement would share the two-send allowance. No final
  retrieval/model score, approved action, useful fix, held-out result or C5
  reconciliation is claimed.

## Reproduce safely

Offline, with real temporary Chroma/SQLite and mandatory mocked provider:

```bash
uv run pytest tests/test_connected_live_dev_probe.py tests/test_grounded_live_probe.py
uv run pytest tests/test_eval_runner_cleanup.py tests/test_evaluation_preflight.py tests/test_eval_runner_final_preflight.py tests/test_evaluation_family_candidates.py
uv run python scripts/propose_evaluation_families.py --output /tmp/new-reservations-replay.json
```

Before the original execution, the default `connected_live_dev_probe.py --index
<registered-index>` read only the registered ledger/source/manifest and reported
eligibility with zero requests. `--live --env-file .env --output-dir <fresh-private-dir>`
required clean committed source, actual index verification and the registered
ledger fingerprint before reading credentials. **That registration is now
spent and must not be rerun**: the ledger fingerprint has changed. A new paid
experiment requires a separately registered bounded scope, using the same
designated ledger and explicit authorization; do not edit this protocol or
reset/unhalt/refill the ledger. Remaining continuation is $0.006030190; original
$0.02 hold/global halt persist. Account charges and old model mismatch remain unresolved.
