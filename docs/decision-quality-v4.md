# Fresh callback and question guard comparison — 2026-10-07

The manually curated question catalog plus `grounded_rules` prompt produced the
most acceptable proposals in this run: **8/9**, compared with **5/9** for the
shape policy and **4/9** when the same catalog/prompt also had hard checks.
Hard checks correctly refused unregistered questions, but two attempts did not
always recover a usable proposal. This is evidence to improve how constraints
are presented before enabling strict enforcement by default; it is not evidence
that validation should accept incorrect output.

## Registered design and observed results

Nine newly authored [synthetic development scenarios](../experiments/decision_quality/README-guards-v4.md)
and their caller catalogs were frozen at `9a1427d` before responses. Integration
review then reproduced an adapter-mutation bypass; `857aabb` isolated the private
enforcement catalog and retained feedback before live execution. No request was
sent with the bypass present. The [comparison protocol](../experiments/decision_quality/protocol-guards-v4.json)
and [blinded review procedure](../experiments/decision_quality/review-guards-v4.json)
were registered before outputs. Private receipts pin the exact execution code.

All conditions use `gpt-4o-mini`, identical user messages/state/source pools,
32,768-token input reservations, 768-token output allowances, rotated order and
the existing two-attempt/two-retrieval limits. B/C first-request messages were
verified byte-identical; their request IDs differ, and only enforcement differs.
All scenarios are post hoc development probes with related mechanisms. No
formal held-out case, report outcome or real retrieval adapter was used.

| Variant | Inputs / checking | Accepted | Expected decision | Blinded acceptable | Needs revision | Unusable | HTTP requests | Estimated USD |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A | `structured_rules` | 8/9 | 7/9 | 5/9 | 3/9 | 1/9 | 9 | 0.007253400 |
| B | Manual catalog + `grounded_rules` | 9/9 | 8/9 | 8/9 | 1/9 | 0/9 | 10 | 0.008289765 |
| C | B's inputs + hard proposal checks | 6/9 | 6/9 | 4/9 | 2/9 | 3/9 | 11 | 0.009063285 |

The **27 observations made 30 actual HTTP requests**, all settled with known
usage. First responses were schema-valid in 26/27 observations, which differs
from core acceptance and semantic quality. B refined retrieval once; C used two
repair attempts. Neither C repair recovered an accepted proposal. A and C each
had one terminal `AnswerWithoutEvidence`; authority rules were not weakened to
buy another attempt. The [public aggregate](../experiments/decision_quality/results-guards-v4.json)
contains per-case counts and error codes without raw proposals.

Three assistants independently reviewed randomized aliases without variant,
prompt, attempt, timing, cost or expected-decision labels. Each observation has
one preserved rating: 17 acceptable, six requiring revision and four unusable.
Null proposals were rated unusable. Reviewers judged useful questions by meaning,
not exact catalog wording. These are source-based assistant judgments rather
than human gold labels or statistically independent measurements.

## Useful distinctions

- A/B corrected the stale callback by removing captured arguments and reading
  the current keyed value inside the callback. B/C corrected the form callback
  parameter to `on_click`. C's stale-value response and A's form response failed
  because they omitted evidence links, not because their code was diagnosed.
- All variants mishandled the already correct pass-key design check. A/B asked
  for information explicit in the message or introduced a failure the user had
  disclaimed. C refused an unregistered question, then failed to recover one.
- B/C asked for the genuinely absent helper implementation. A's question blurred
  the already supplied helper call with the hidden widget arguments. Questions
  need to target information that is both missing and obtainable.
- C's installed-version question was useful, but its maintainer summary falsely
  said `bind` was absent from the supplied 1.64.0 signature. A expanded a reported
  `bind` error into an unverified claim about `persist_state`. Structured question
  conformance did not validate the rest of the proposal.
- C accurately explained callback display timing but suggested storing a value
  already stored by the keyed widget, blurring value storage with rendered-output
  lifetime. The answer needs to distinguish those two concerns.
- All three preserved frontend **Lima** versus backend/callback **Oslo** and
  escalated the fully specified mismatch without inventing a proven cause. All
  accepted the intentional previous-value snapshot. Construction-time argument
  capture is not universally wrong. Root audit flags B's warning about subsequent
  interactions as potentially too broad: arguments are established again on
  each later widget-command call. Its independent acceptable rating is preserved,
  and the supplied first North-to-South comparison remains supported.
- A's extra question about whether generated options were populated before a
  change was independently judged useful even though it was outside the manual
  catalog. The catalog constrains choices; it is not a completeness oracle.

No live `invalid_api_keyword` or `callback_value_captured` finding occurred in
this run. Their narrow behavior is verified by offline regressions, including
actual frozen source metadata and positive controls; this run cannot establish
their live benefit. C rejected questions in two observations, preventing unsuitable proposals
but reduced availability. A/B/C results also vary across independent draws, so
differences cannot all be attributed to checks.

## Follow-up direction and limits

Compile the same caller question pairs and answer citation requirements into the
model-visible output schema and decision metadata. The current prose requests
these constraints, yet the model still omitted targets/citations or asked with
an empty catalog. This is a focused hypothesis for a registered follow-up on the
already exposed development inputs; any follow-up must record its separate code,
protocol and outcomes. Native provider structured-output support is not assumed.

Keep production defaults unchanged and both guards experimental. Caller curation
needs a case/revision binding and independent port copies; it does not implement
a production fact extractor, durable tracker or action approval. The AST checks
cover labeled Python and specific applicable signatures/timing only. Free-text
claims, callback arity and runtime behavior still need whole-proposal review.
No extra production agent is justified by this comparison.

## Accounting and verification at this milestone

Fresh settled public-rate estimate: **USD 0.024606450**, from 113,734 input and
8,849 output tokens. The original ledger has USD 0.073193670 settled, zero pending,
USD 0.02 retained uncertainty and USD 4.406806330 available. The same audited
continuation has USD 0.055479370 remaining. The global halt and unresolved 4.1
request remain; no hold was released or grant refreshed. Account deductions
remain unverified. This is a local ledger snapshot, not a provider wallet balance.

Verified **824 passing offline tests**, Ruff lint/format, locked dependencies,
six registered protocol validations and installed demos. CI validates the new
protocol without a key or paid request. Work remains in draft PR #2 on
`feat/agent-core-integration`; main retains the shared foundation.
