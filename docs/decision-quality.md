# Decision-quality development experiments

This report records the earlier policy and incomplete model comparisons. The
[later paired source/state experiment](decision-quality-v3.md) documents 32 new
requests under an explicit capped continuation for the verified 4o route. The
global halt and unresolved 4.1 reservation remain; historical accounting below
is preserved at its recorded point.

The explicit decision-shape policy improved output reliability in this small run. It did **not** establish a semantic winner. Keep `baseline` as the default; `structured_rules` is an opt-in candidate for the next reviewed pilot. Adding another judge agent is not justified by these measurements yet.

The core now also rejects evidence facts that contradict confirmed user facts, prioritizes whole environment facts in retrieval queries, exposes trusted remaining capacity, and checks labeled Python proposals for syntax without executing them. These are tested behavioral improvements, separate from model-quality claims.

## Registered comparisons

Inputs and expectations were fixed before the first comparison. Eight development probes contain three real first-report anchors, three correlated variants and two synthetic stresses. Evidence pools are fixed, with inspectable versions, source spans and the frozen docs commit. This is neither the formal 15-dev / 15-test split nor a measurement of retrieval relevance.

All prompt comparisons use `gpt-4o-mini`, 16,384 reserved input tokens, a maximum of 768 output tokens, and the same two-attempt/two-retrieval allowance. Order rotates across cases. Provider sampling defaults are unchanged; one pass per case/configuration is stochastic. The baseline includes the common fact-authority fixes, so this is not an unchanged-main A/B.

The first protocol was committed at `850fa8f` before paid outputs. The shape follow-up was registered at `2b9c5ae` after observing repeated `final_drafts_required` errors. It reused unchanged development inputs and labels; this is explicit post-hoc development, not held-out evaluation.

| First comparison: 8 cases per policy | Accepted proposals | Allowed final decision | First-pass schema valid | HTTP attempts | Estimated USD | Mean seconds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `baseline` | 7/8 | 6/8 | 7/8 | 9 | 0.004021215 | 4.775 |
| `decision_rubric` | 5/8 | 4/8 | 3/8 | 13 | 0.006071505 | 5.548 |
| `bounded_rubric` | 7/8 | 6/8 | 5/8 | 11 | 0.005382300 | 4.772 |

| Shape follow-up: 8 cases per policy | Accepted proposals | Allowed final decision | First-pass schema valid | HTTP attempts | Estimated USD | Mean seconds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Fresh `baseline` | 7/8 | 6/8 | 6/8 | 10 | 0.004480905 | 4.554 |
| `structured_rules` | 8/8 | 7/8 | 8/8 | 8 | 0.004557465 | 5.100 |

An accepted proposal means `awaiting_approval`, never an applied change or solved case. Allowed-decision agreement uses preregistered final choices; some real cases allow several choices. Neither measure checks whether an explanation, question or code snippet is useful and correct. All first-comparison retrieval counts were one per case; those results do not measure refinement quality.

The new shape matrix makes conditional fields explicit: even `ask` needs both nonempty drafts plus its separate question. It carries the validated query limit and refinement availability. This candidate removed observed draft-format failures in the follow-up, Its estimated cost and observed latency were slightly higher in this run. Eight successes do not establish a general improvement.

## Review against sources and reported facts

An independent assistant reviewed shuffled aliases separately for each case, without policy names, costs, request order or attempt counts. It inspected accepted proposals against supplied facts and evidence. A second source audit checked material callback/API and observation errors against the frozen catalog. This is assisted qualitative review, **not human expert gold labels**.

| Run / policy | Acceptable | Needs revision | Unusable |
| --- | ---: | ---: | ---: |
| First / baseline | 2 | 5 | 1 |
| First / decision rubric | 1 | 3 | 4 |
| First / bounded rubric | 3 | 4 | 1 |
| Shape follow-up / baseline | 2 | 4 | 2 |
| Shape follow-up / structured rules | 2 | 6 | 0 |

These categories are review judgments, not calibrated quality scores. An unusable result can be a rejected response rather than incorrect accepted content. Question usefulness and severity remain partly subjective; their concrete reasons matter more than the counts.

Material findings:

- Some questions repeated loop/callback facts already in the report. Requesting the missing body of a delegated callback can be reasonable, but the question must say which diagnostic branch that body would resolve.
- A valid citation to callback arguments accompanied code with an extra parenthesis, incompatible lambda arguments, or a value captured before the callback. Source presence does not verify generated code.
- Form answers resisted injected approval/execution claims but recommended `on_change` on the submit button. The frozen `/1.64.0/streamlit.form_submit_button` signature uses `on_click`. The supplied form constraint alone did not establish a parameter name.
- One case summary denied reported checks; another reversed frontend B / printed state A. An empty structured checks list does not prove the user performed no checks. Preserve and attribute observations from the message.
- Matching source versions and an installed version are different facts. The corrected user version is 1.49.1; supplied 1.50.0 docs cannot establish a fix on that installation. Unversioned concept snapshots need an applicability caveat for historical reports.

The initial reviewer treated the form parameter wording as a minor precision issue because no explicit function call was shown. The source audit and core owner consider it material implementation advice needing correction. The public table preserves the original blinded verdicts instead of silently relabeling them. Similarly, a callback question can legitimately seek a missing function body even when the lambda is already given; review must distinguish that from asking the same question again.

## Syntax guard added after these comparisons

`reasoning/code_checks.py` parses explicitly labeled `python`, `py` and `python3` fences in both drafts with `ast.parse`. It never imports or executes snippets. It bounds block size/count and total parsed bytes, and returns only a boolean. The engine emits `invalid_python_syntax` without code or parser messages and may use the remaining attempt for repair. Source/authority violations are checked first and remain terminal.

The guard catches the observed extra-parenthesis class of failure. It does not check callback arity, parameter names, types, runtime behavior or claim entailment. Inline, unlabeled, quoted and other-language code remains outside coverage; incomplete Python fragments can fail. The first two comparison tables were recorded **before** this guard and are not rescored retrospectively.

## Focused model probe and accounting stop

Three previously used hard cases were selected for a focused model check, registered at `f06cdcc`: one controlled callback case plus two synthetic stresses. Both models were to use `structured_rules` and the same current syntax guard. The blocks ran sequentially, leaving time/order effects; this was not a new independent test set.

The `gpt-4o-mini` block completed three proposals in four requests, including one actual refinement then escalation. It had 2/3 allowed final decisions. Blinded review found one acceptable escalation and two proposals needing revision. Estimated block cost was USD 0.002186085.

The first `gpt-4.1-mini` request returned HTTP 200 but failed `ProviderModelMismatch`. No response was accepted, no second request was sent, and its USD 0.008560640 reservation remains uncertain. The response did not pass model-identity validation; the returned value was not retained. The diagnostic alone cannot distinguish an absent/invalid field from an unverified serving alias. **This incomplete comparison cannot rank model quality.** Do not infer an alias's price or repeat the request to diagnose it.

The ledger is now halted. Resume of paid work requires provider usage/billing evidence for that request and verification of the returned model identity/pricing. Keep the existing ledger and held cost; there is no automatic unhalt or refund. Offline development and CI continue normally.

Across this work: **44 observations, 56 HTTP attempts, 55 settled requests**, estimated settled comparison cost **USD 0.026699475**, plus **USD 0.008560640 held uncertain**. Together they occupy USD 0.035260115, below the originally stated USD 0.16 cap. Including six earlier compatibility calls, the ledger records USD 0.028673040 settled, USD 0.008560640 uncertain, and USD 4.462766320 available under its USD 4.50 operational ceiling. USD 0.50 remains outside that ceiling.

Amounts are usage/list-price estimates, **not reconciled account deductions or a fetched wallet balance**. The [public Metis price card](https://api.metisai.ir/api/v1/meta/providers/pricing) was checked on 2026-10-07. No paid judge calls or API calls for unit tests were made.

## Next work and teammate feedback

- Core: retain the baseline default, try the explicit shape policy only with review, preserve observations in summaries, and improve decision quality on separately registered development cases once accounting is reconciled. Another agent should earn its cost by reducing a measured recurring error.
- Data/RAG: retrieve version-specific API signatures and parameter descriptions alongside concepts, especially callbacks and submit buttons. Include relevant widget-state/callback ordering context. Preserve missing or mismatched version metadata.
- Tracker/UI: pass confirmed facts and performed checks into the case state while preserving the user report. Distinguish unknown/unrecorded checks from confirmed absence; display the next question and inspectable pending summary for approval.
- Evaluation: create the formal split independently. Quarantine report families #8061, #12782, #16914 and provisional linked #8901, including comments/outcomes and reviewed duplicates, from retrieval and final test. These probes are already development material; the declaration itself does not enforce corpus exclusion.

No change has been merged from this branch to main. Contracts remain backward compatible through defaults. Current verification: **565 offline tests**, locked dependencies, Ruff lint/format, registered-protocol validation and offline demos. Sources, protocols and aggregate results live in [the experiment directory](../experiments/decision_quality/README.md); keys, ledger, accepted proposals and blinded review files remain ignored private runtime data.
