# Compiled proposal constraints follow-up — 2026-10-07

The compiled-schema follow-up produced usable structured proposals but **did not
demonstrate better semantic quality**. All 27 proposals passed core validation
on their first attempts; blinded review rated A/B/C acceptable on **8/5/6 of nine**.
The unchanged shorter shape policy was strongest in this run. Keep
`compiled_rules` experimental and use the shorter `structured_rules` option for
the first integrated development pilot, with whole-proposal human review.
Production defaults remain unchanged; this is not a held-out quality ranking.

## What was registered

The [V4 comparison](decision-quality-v4.md) found that hard checks could reject
an unsuitable question without recovering a proposal within two attempts. V5
adds explicit name/question pair constraints and source-bound citation IDs to
the model-visible schema and decision metadata. An empty catalog disables `ask`
in this supplied catalog; it does not prove complete user context. Empty evidence
disables `answer`. The gateway still sends ordinary prompted text, with runtime
validation authoritative; native provider schema support is not assumed.

The [V5 protocol](../experiments/decision_quality/protocol-guards-v5.json),
[review procedure](../experiments/decision_quality/review-guards-v5.json) and
execution code were committed at **`5932f89` before outputs**. Receipts pin the
code hash. The same nine **already exposed synthetic development probes**,
manual catalogs, source pools, model, input/output allowances, limits and rotated
order are reused. A's model messages are unchanged from V4. B/C have identical
first-request messages and distinct request identities; only checking differs.
No final held-out case or real retrieval measurement was used.

`compiled_rules` is separate from the measured `grounded_rules` candidate. All
six earlier policy messages remain byte-identical and selectable. Fixed runner
designs reject mixed policies or altered checking flags. Offline schema tests
cover omitted fields, cross-paired questions, unknown citations, empty inputs,
untrusted instructions and unchanged public contracts. These tests verify the
local compilation, not model obedience or source entailment.

## Results and interpretation

| Variant | Policy / checking | Accepted | Expected decision | Blinded acceptable | Needs revision | Unusable | HTTP requests | Estimated USD |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A | `structured_rules` repeat control | 9/9 | 9/9 | 8/9 | 1/9 | 0/9 | 9 | 0.007341840 |
| B | Manual catalog + `compiled_rules` | 9/9 | 7/9 | 5/9 | 3/9 | 1/9 | 9 | 0.008036160 |
| C | B's inputs + hard proposal checks | 9/9 | 8/9 | 6/9 | 2/9 | 1/9 | 9 | 0.008141100 |

All **27 actual HTTP requests** settled with known usage. There was no repair,
retrieval refinement, new uncertainty, authority error or deterministic finding.
Schema acceptance does not establish correctness: B/C supplied fundamentally
unsupported explanations for the reproduced frontend/backend mismatch.
The [public aggregate](../experiments/decision_quality/results-guards-v5.json)
preserves per-case counts and ratings without raw proposals.

Three new assistants reviewed randomized aliases without variant, policy,
attempt, cost, timing, expected-decision or previous-result information. Each
proposal received one rating: **19 acceptable, six needing revision, two unusable**.
Reviewers saw the same source/context/catalog for all variants of a case and
judged questions by usefulness rather than exact wording. These are preserved
source-based assistant judgments, not human gold labels.

| Run | A acceptable | B acceptable | C acceptable | Total accepted |
| --- | --- | --- | --- | --- |
| V4: shape / grounded / grounded with checks | 5/9 | 8/9 | 4/9 | 23/27 |
| V5: same shape / compiled / compiled with checks | 8/9 | 5/9 | 6/9 | 27/27 |

A improved despite unchanged messages. B regressed after compilation. C improved
its observed acceptance and ratings, but no guard was triggered. Therefore the
changes cannot all be attributed to compilation or checking. This is a targeted
follow-up adapted after seeing V4, with one draw per condition and related cases.
It does not establish causal superiority, general accuracy or test-set gains.
The two 8/9 counts belong to different runs and do not prove those policies tie.

## Remaining technical failures

- B asked about a value-access preference even though the complete stale-value
  example and source already supported an answer. Its supplied compiled schema
  forbids `ask` for that empty catalog, but plain prompted text did not guarantee
  compliance. B intentionally had no deterministic catalog enforcement.
- C endorsed the correct key/read-inside design but said the key argument was
  unnecessary without rewriting the one-argument handler. Advice in prose can
  break callback arity even when no invalid Python fence is present.
- B/C answered the fully specified **Lima/Oslo** mismatch by blaming callback
  access already implemented correctly. B's rationale and citation claim reversed
  the supplied order: Session State is updated **before** callback execution.
  C called the mismatch known behavior without source support. Both were rated
  unusable; A preserved the report and escalated.
- Display-lifetime drafts confused redrawn page content with widget state or
  added an unreported persistence expectation. B's unknown-version rationale
  changed “not checked” into “unable to check.” Accurate user drafts alone do
  not establish accurate summaries or rationale.
- C's deliberate old-value answer was substantively correct but attributed its
  timing claim to the callback API excerpt rather than the supplied timing
  excerpt. A known chunk ID is insufficient evidence for a specific claim.

Keep the optional AST guards for their documented, tested scope and retain the
private enforcement-copy fix. No live API/timing finding occurred in either
guard run, so their live benefit is unmeasured. Do not enable catalog restrictions
without trusted curation and revision updates, or present them as an extractor.
No extra production reasoning/judge agent is justified by these results.

The useful next integration work is the real RAG source handoff and tracker's
authoritative state: exact signatures, spans/version applicability, known facts,
reported checks and genuinely missing targets. Maintain the distinction between
source presence and claim support, key arguments and captured values, and working
versus failing reproductions. Then measure on an agreed development set before
touching the formal held-out split; add repeated draws before ranking policies.

## Accounting and verification

Fresh V5 settled estimate: **USD 0.023519100**, from 108,628 input and 8,478 output
tokens. V4 and V5 together made **57 HTTP requests across 54 observations** at
USD 0.048125550. The original ledger now records USD 0.096712770 settled, zero
pending, USD 0.02 retained uncertainty and USD 4.383287230 available. The same
audited continuation has USD 0.031960270 remaining. No grant or receipt was reset;
global halt and the old serving-ID incident remain. Account deductions remain
unverified; available ledger amount is not a provider balance. Earlier reports
retain their historical accounting snapshots.

Verified **875 passing offline tests**, Ruff lint/format, locked dependencies,
seven registered protocol validations and installed demos. CI validates both
guard protocols without a key or paid request. All changes remain in draft PR #2
on `feat/agent-core-integration`; main retains the shared foundation.
