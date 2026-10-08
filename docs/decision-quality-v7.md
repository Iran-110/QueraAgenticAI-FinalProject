# Whole-proposal fidelity comparison — 2026-10-08

The new fidelity candidate showed a **limited development advantage, with
remaining factual and citation errors**. In nine pairs where both policies
produced final proposals, blinded reviewers rated **5/9** `fidelity_rules`
responses acceptable versus **3/9** for `structured_rules`. Across the four
families with two completed draws per policy, that difference narrowed to
**4/8 versus 3/8**. Citation-support passes were **6/9 for both** in the paired
final subset. Keep the candidate experimental and retain human review; these
results do not select a general winner or justify another production agent.

## Registered change and inputs

The [V6 offline challenges](decision-quality-v6.md) exposed failures that static
checks cannot establish: reported-fact fidelity, check attribution, source
entailment and preservation of already-correct designs. The new optional
`fidelity_rules` policy adds a short instruction and an exact-record index over
unchanged `structured_rules`. It groups active and superseded user facts,
evidence observations, recorded checks, unknowns and source scopes. The index
copies their provenance and status; it infers no facts, cause, claim support,
source applicability or action permission. The original inputs remain present.

The instruction requires these distinctions throughout drafts, summaries,
rationale and citation claims. It addresses working versus failing reductions,
unexecuted drafts, checks reported by the user, deliberate old/new comparisons
and historical coverage. Instruction and index change together; this design
cannot separate their effects. All seven earlier policy messages, including
repair feedback, remain unchanged. Production defaults stay `baseline` and
`proposal_checks=False`.

The [protocol](../experiments/decision_quality/protocol-fidelity-v7.json),
[fresh input pack](../experiments/decision_quality/cases-fidelity-v7.json),
[input guide](../experiments/decision_quality/README-fidelity-v7.md) and
[review procedure](../experiments/decision_quality/review-fidelity-v7.json)
were committed at **`1ef5c35` before the first HTTP request**. The candidate was
separately committed at `39efc16`. Six new synthetic caller reports reuse nine
exact official source records from the exposed V4 families. Sources, exclusions
and source metadata remain unchanged. The author used the public V5/V6 failure
descriptions without inspecting previous private proposal files or formal
held-out cases. The probes deliberately target already-known development gaps.

Each case has one authoritative state and user message, with two identical
fixed hit pools. Both policies receive the same complete caller-authored facts
and genuine unknowns. There is no question catalog, `ProposalRequirements`,
freshness flag or optional proposal checking. Expectations and reviewer notes
stay outside model messages. The suite contains no required/forbidden answer
keywords. Fixed-source handoff does not measure retrieval or automatic fact
extraction.

Both policies use `gpt-4o-mini`, output ceiling 768, input reserve 32768 and the
existing two-attempt/two-retrieval-round allowance. The explicit 24-observation
schedule completes one paired draw across all cases before repeating, reverses
each case's policy order on its second draw, and pins input/content/schedule
hashes. The original continuation and ledger govern the USD 0.030 trial ceiling.

## Completion and missing data

The trial recorded **21 attempted observations, 25 HTTP requests and 19 accepted
final proposals**. Ten case/draw pairs have both recorded engine invocations;
nine have two accepted finals. The first draw covered all six cases. The second
draw completed four families before budget headroom stopped the historical case.

| Policy | Attempted observations | Accepted finals | HTTP requests | Blinded acceptable / present finals | Needs revision | Absent final |
| --- | --- | --- | --- | --- | --- | --- |
| `structured_rules` | 10 | 9 | 12 | 3/9 | 6 | 1: terminal `AnswerWithoutEvidence` |
| `fidelity_rules` | 11 | 10 | 13 | 6/10 | 4 | 1: `BudgetExceeded` after a refinement request |

The final candidate historical observation made one settled call requesting
more retrieval. Its second call was refused before HTTP because the trial's
remaining ceiling could not cover another conservative request reservation.
The control's second historical draw and both second display draws never began.
There was no refilling, authorization extension, receipt overwrite or imputation.
The original account still has substantial ledger availability; this is a
**registered trial-cap stop**, not a claim that the shared USD 5 credit is gone.

The control's first display response proposed an answer without an evidence
link. Core validation rejected it terminally. Its raw invalid proposal is not
retained or reconstructed. One candidate mismatch response used its remaining
attempt to repair invalid JSON. Three other accepted observations used bounded
retrieval refinement. Engine attempt counts also include the historical call
denied before HTTP; they are not paid-call counts.

## Whole-proposal review

Three fresh assistant reviewers each assessed two whole case families. They saw
the same exact reported state, user message, source excerpts and full final
proposals under shuffled random aliases. Policy, replicate, prompt/index,
attempts, cost, latency, expected decisions, reviewer aids and earlier reviews
were withheld. One original rating and four dimension judgments were preserved
per observation. The unblinded root audit inspected all 19 accepted proposals
and agreed with the original categories without changing ratings.

The two absent finals received availability labels of unusable and semantic
dimensions of not-assessable. Neither is included as a substantive reasoning
defect in the present-final comparison. Three never-started observations have no
review label. Assistant judgments are source-based development assessments,
not human gold; there is no inter-rater reliability estimate.

| Review subset | Control acceptable | Candidate acceptable |
| --- | --- | --- |
| Nine pairs with both final proposals | 3/9 | 5/9 |
| Four fully repeated families, eight finals per policy | 3/8 | 4/8 |

Among the nine paired finals, the candidate alone was acceptable in four pairs,
the control alone in two, and three had matching categories. The dimension
comparison separates overall usefulness from claim support:

| Dimension, nine paired finals per policy | Control passes | Candidate passes |
| --- | --- | --- |
| Reported-fact fidelity | 7/9 | 8/9 |
| Check attribution | 9/9 | 9/9 |
| Claim/source support | 6/9 | 6/9 |
| Technical usefulness | 6/9 | 8/9 |

These are repeated, related draws over six targeted source families. The small,
partially completed comparison establishes neither statistical superiority nor
held-out accuracy. V5 used different, exposed inputs and catalogs; its higher
control score cannot be treated as a like-for-like regression measurement here.
See the [sanitized aggregate](../experiments/decision_quality/results-fidelity-v7.json)
for per-observation ratings, dimensions, completion, component hashes and costs.

## Concrete findings

| Synthetic family | Observed comparison and remaining defect |
| --- | --- |
| Corrected version / form submit API | Both candidate draws directly replace `on_change` with source-supported `on_click` and preserve the saving handler. Both control draws ask unnecessary follow-up questions despite sufficient intent and API evidence. |
| Working reduction / failing integration | One candidate draw is acceptable; the other says missing helper implementations cause the failure. Both control summaries also distort the report. Missing review copies must not become unimplemented functions, an unobserved empty options list or a proven cause. |
| Complete keyed frontend/backend mismatch | One control escalation is acceptable. The other adds an unsupported unresolvable prognosis. The candidate alternates between a redundant callback-assignment question and an escalation that incorrectly calls the installed release the latest. Correct values alone do not make the whole proposal accurate. |
| Deliberate old/new comparison | Both control draws preserve the requested design. One candidate draw cites the argument-passing excerpt for a construction-timing claim; the other is acceptable. The candidate did not improve citation fidelity here. |
| Known historical signature gap | The completed candidate draw asks for genuinely absent historical coverage. The control extends one pinned newer signature into future-version coverage and leaves the user-facing historical limit unclear. The second pair is incomplete and adds no semantic evidence. |
| Display placement/lifetime | The candidate's completed draw uses the supporting timing/lifetime excerpt and keeps the retained saved value scoped to the supplied app. The control has no accepted final. Neither second draw began. |

The historical question preserves uncertainty but asks the reporter to supply
old documentation. Independent publication review noted that this shifts source
discovery to the user and does not establish optimal routing. Both conditions
already used bounded refinement over identical fixed pools, so this experiment
cannot show whether actual RAG could resolve the gap without asking. Preserve
the original acceptable rating with this separate reservation.

The recurring defect is often in `maintainer_summary`, `rationale` or a specific
`evidence_links.claim`, even when the user-facing next step is useful. A known
chunk ID proves source presence, not support for an arbitrary timing, release,
historical or causal claim. The current AST checks cover their documented static
scope; this trial intentionally did not enable them or measure their live gain.

## Integration decision

Keep `fidelity_rules` available for explicit development comparisons, with
whole-proposal review. Keep the shorter `structured_rules` recommendation for
the first integrated development pilot until the actual retrieval and state
handoffs can be measured. No policy default, contract, teammate adapter or
production agent count changed.

The useful team handoffs are concrete: RAG should provide the exact span needed
for each parameter/timing claim and preserve version coverage; tracker should
preserve active/superseded facts, attributed checks and genuinely absent code;
UI/evaluation should assess both drafts and distinguish absent finals from
semantically wrong finals. The next measurement should use the real adapters
and an agreed development set, retain final held-outs, and repeat complete pairs.
Adding a judge model would add spending and another fallible decision; this
experiment has not shown that it resolves the remaining failure modes.

## Accounting and verification

All 25 HTTP requests settled with known usage: **114,715 input and 7,951 output
tokens**, at estimated **USD 0.024175635**. Control and candidate estimates were
USD 0.009918315 and USD 0.014257320 respectively; their denominators and retry
counts differ, so the totals are not a matched per-response price comparison.
Within the same nine accepted-final pairs, both policies made 11 HTTP requests;
control and candidate estimates were USD 0.008902905 and USD 0.012101760. The
candidate's roughly 36% higher matched estimate accompanies its larger context
index. This is a cost/usefulness tradeoff on this small subset, not a general
price or quality ranking.
There was no new uncertain request. The original ledger records USD 0.120888405
settled, zero pending, USD 0.02 retained uncertainty and USD 4.359111595
available. The unchanged continuation retains USD 0.007784635. Global halt and
the old serving-ID incident remain preserved. Estimates are not verified
provider deductions or provider credit balance; earlier reports retain their
historical snapshots.

Verified locked dependencies, **1,149 offline tests**, Ruff lint/format, all eight
registered protocol validations, authored semantic replay and the three
installed demos. GitHub's offline CI passed at the exact preregistration commit
`1ef5c35` in run `37746599205`. CI makes no paid requests. Raw proposals, alias
maps and original review files remain private ignored runtime data.

Offline protocol validation:

```bash
uv run --no-sync python -m agent_app.reasoning.fidelity_experiments
```

The same command with explicit live opt-in would attempt the frozen trial using
the original ledger and continuation. The recorded output directory is exclusive
and cannot be silently replaced or resumed. Do not run another copy to evade a
budget stop or present a newly funded completion as the registered batch.
