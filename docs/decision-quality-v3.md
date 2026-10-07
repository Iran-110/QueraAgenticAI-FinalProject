# Source, user-state and prompt comparison — 2026-10-07

The strongest candidate in this development run was **enriched sources plus
explicit user reports**, using the shorter `structured_rules` prompt. It received
6/8 acceptable blinded reviews and 8/8 expected final decisions. The longer
`diagnostic_rules` prompt received 5/8 acceptable reviews. This supports investing
in source and state handoff before adding another production agent. It does not
establish a general winner: the strongest candidate still proposed incorrect
callback code, and the inputs are eight correlated development probes.

## Design and results

The [registered protocol](../experiments/decision_quality/protocol-ablation-v3.json)
was committed at `388f5cb` before model outputs. All conditions used the verified
`gpt-4o-mini` route, identical 32,768-token input reservations, 768-token output
allowances and existing two-attempt/two-retrieval limits. Condition order rotated
across cases. Inputs, source additions and normalization attribution were frozen
and audited; [the fixture notes](../experiments/decision_quality/README-enrichment-v3.md)
explain the exact differences. No final held-out evaluation case was used.

| Cell | Inputs and prompt | Accepted / first attempt | Expected decision | Blinded acceptable | Needs revision | Estimated USD | Mean seconds |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A | Original + structured rules | 8/8 | 6/8 | 4/8 | 4/8 | 0.004529745 | 4.089 |
| B | Added sources + structured rules | 8/8 | 6/8 | 5/8 | 3/8 | 0.004712895 | 3.944 |
| C | Added sources and user reports + structured rules | 8/8 | 8/8 | 6/8 | 2/8 | 0.005270760 | 4.640 |
| D | C's identical inputs + diagnostic rules | 8/8 | 6/8 | 5/8 | 3/8 | 0.005400780 | 4.686 |

All **32 observations made exactly one HTTP request**. There were no repair
attempts, retrieval refinements, unaccepted proposals or new accounting failures.
Expected-decision agreement is an automatic check against the frozen broad
expectations; it does not grade answer content. Latency is one sequential run's
observed elapsed time, without statistical inference.

Three independent assistants reviewed randomized proposal aliases with the
original message, condition-specific state and used sources. They did not see
condition names, prompt choice, cost, timing or attempt identity. All 32 received
one rating: 20 acceptable, 12 needing revision, zero unusable. These are
source-based assistant judgments, **not human gold scores**. The root source
audit preserves their ratings and documents disagreements separately. Raw
proposals and alias mappings remain private; the [public aggregate](../experiments/decision_quality/results-ablation-v3.json)
contains inspectable counts, categories and accounting metadata.

## What improved and what failed

| Probe | A | B | C | D |
| --- | --- | --- | --- | --- |
| Historical loop callback | Revise | Accept | Revise | Revise |
| Current loop callback | Revise | Revise | Revise | Revise |
| Fragment with working reduced example | Accept | Accept | Accept | Accept |
| Fragment with unknown versions | Accept | Accept | Accept | Accept |
| Fragment after version correction | Accept | Accept | Accept | Accept |
| Dataframe/session reconnection | Accept | Accept | Accept | Accept |
| Form callback with injected source instructions | Revise | Revise | Accept | Accept |
| Reproduced frontend/backend mismatch | Revise | Revise | Accept | Revise |

- C escalated the reproduced mismatch and preserved frontend **B**, backend **A**
  and the reported checks. Other cells asked code-resolved questions or suggested
  unsupported cache/version remedies. D's user draft again reversed the symptom.
- C and D gave the correct form callback placement. A recommended `on_change`
  for the submit button; B's user draft was correct but its rationale made the
  same parameter error despite an `on_click` signature. Reviewing only the user
  draft would miss this defect.
- C and D's current callback examples passed syntax validation but captured the
  widget's value in `args` during construction. The supplied source explicitly
  requires looking up that value inside the callback. This also risks reading a
  key before the widget creates it. **A valid citation and valid Python syntax
  did not establish correct callback behavior.** No source snippet was executed.
- Questions for the unknown-version fragment and absent full-app reproduction
  were useful. Reviewers distinguished a working reduction from a failing
  reproduction; none inferred a deployment version from retrieved docs.
- B's historical callback explanation was independently rated acceptable. Its
  offer of more instructions is nevertheless a questionable use of the `ask`
  workflow because it obtains no diagnostic fact. That rating remains published
  without a silent root reclassification.

The A/B evidence change affects only two probes, and neither became acceptable
under B. B's one extra acceptable rating came from an **unchanged-source** probe.
Therefore this run does not demonstrate that enrichment alone caused improvement.
Normalization is a useful hypothesis for the C changes, but each cell has only
one sample per case. C/D shows no observed benefit from the extra 200-word prompt.

## Concrete integration direction

The data/RAG handoff should include the exact callable signature, relevant
parameter descriptions, source commit/span and version applicability alongside
conceptual excerpts. Callback timing and runtime advice need source-based review,
including whether an example contradicts the very source it cites. The frozen
catalog lacks exact 1.27.2 and 1.49.1 records; nearby versions were not relabelled.

The tracker/UI handoff should preserve explicitly reported symptoms and checks
with user-turn attribution. Store component-specific values separately and keep
a working reduction distinct from a failing reproduction. An empty durable
check list cannot prove that the user tried nothing. The normalization here is
caller-assigned fixture state, not a production free-text extractor or persistent
tracker implementation.

Keep `diagnostic_rules` experimental and the production default at `baseline`.
The shorter shape policy remains a useful opt-in for integration trials, with
human review of technical content. Another reasoning/judge agent is not justified
by this run. The next focused core experiment should address callback correctness
and genuinely missing-information questions, then use fresh development cases;
the final test split remains untouched.

## Accounting and verification

Fresh settled public-rate estimate: **USD 0.019914180**, from 89,636 input and
7,764 output tokens. Total ledger settled estimate is USD 0.048587220. The earlier
unknown `gpt-4.1-mini` request remains uncertain; its held allocation increased
from USD 0.008560640 to **USD 0.02** under the user's explicit continuation request.
That increase is an allocation, not fresh spending, a verified cost bound or
reconciliation. The USD 4.50 global ceiling and global halt remain unchanged.
Available local ledger amount is USD 4.431412780; this is not a provider balance.

Only the verified 4o development route can use the audited USD 0.10 continuation
scope. It has USD 0.080085820 remaining after this batch. Ordinary calls remain
blocked; any new uncertainty/halt revokes the exception. Account deductions and
the earlier serving identity remain unresolved. No further 4.1 request was sent.
See [the gateway controls](model-gateway.md) for scope and recovery limitations.

Verified: **651 passing offline tests**, Ruff lint/format, locked dependencies,
registered protocol validation and installed refinement/gateway-repair/user-turn
demos. CI also validates the four-cell protocol without a key or paid network
request. Changes remain on `feat/agent-core-integration` in draft PR #2; main
retains the previously shared foundation.
