# C4a: actual decisions on fixed development evidence

Six V8/V9 variations share one exposed, answer-informed Issue family
(#12782/#12629). They add zero independent evaluation cases. Current model
material excludes reviewer labels, authored proposals and future bundles.
Gaps/questions/conflicts are manually curated extra inputs. Fixed retrieval
does not search an index or measure real RAG quality.

## Registered baseline and observed prefix

The immutable [protocol](protocol-v1.json), [review inventory](scenario-review-v1.json)
and runtime were pushed at `8b16f2c009d984dfbb224efcff34bf18156ec22d` before the
actual run; [Linux/Windows CI](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38439583863)
passed. [Registration](baseline-live-registration-v1.json) and
[actual receipt](baseline-live-receipt-v1.json) are byte-exact originals.

| Condition | Actual observation |
| --- | --- |
| Full evidence | Final `ask`: parent callback code; three current sources |
| Key evidence removed | Final `ask`: parent callback code; two current sources |
| Unknown version, mixed sources | `ProviderResponseInvalid`; no parsed choice or proposal |
| Version correction | Not reached after terminal provider error |
| Declared synthetic conflict | Not reached after terminal provider error |
| Refinement/stale source | Not reached after terminal provider error |

**3 actual sends, 2 reviewable proposals, 1 incomplete condition and 3 terminal
skips out of 6 conditions**. The two questions fit the preregistered admissible
route and necessary/answerable gap; whole rendered outputs, quotes and version
scopes have a separate [assistant review](baseline-review-v1.json). Both selected
the same question: no decision-quality gain or sensitivity to the omitted source
is demonstrated. Callback names are curated inputs, not model discoveries.
Faithful quotes do not establish the cause of this app failure, source truth or
optimal readability. Human usefulness remains null.

The estimated new cost is **USD0.002005245** from three settled usages; actual
provider account charge is unknown. No new pending/uncertain cost remains. The
original USD0.02 uncertainty, quarantine and halt are preserved; C5 stays open.
The third output used384tokens at the cap. Its finish reason was not captured;
truncation is possible, not confirmed. Missing output and skips are not successes.

The [original mock receipt](baseline-mock-receipt-v1.json) covers all six plumbing
paths with intercepted requests and a disposable ledger; real sends/cost are
zero. Its `registered_source_unchanged` check used no source guard and does not
prove a pinned Git run. New receipts explicitly record `source_guard_installed`.

## Single-send output-cap follow-up

A new [protocol](output-cap-followup-v1.json) and
[design](../../docs/controlled-output-cap-followup.fa.md) register only the failed
unknown-version condition, after preserving the baseline. Initial prompt/material/
model are identical; output cap512, conservative input reserve15360 and request
reserveUSD0.002872320 fit the same continuation's USD0.002909545 remaining.
There is only one actual send including repair/refinement. If the model requests
another attempt, the result stays incomplete. Logical core limits remain2/2/2/8.
No production prompt/rule change or new grant is included. Its execution/result
will be recorded separately.

The separate core import fix permits `GroundedReasoner` to be imported first in
a fresh interpreter without cyclic initialization. Public exports/classes stay
the same. This issue did not cause the provider response failure.

## Reproduction and team use

From the root, without keys:

```bash
uv run pytest tests/test_controlled_decision_inputs.py tests/test_controlled_model_baseline.py tests/test_public_core_imports.py
uv run python scripts/controlled_model_baseline.py --mock
uv run python scripts/controlled_model_baseline.py --output-cap-followup --mock
```

Consumed ledger fingerprints prevent repeating actual runs. Each historical
registration identifies its clean source epoch; later source is not evidence
about an earlier run. Keep raw receipts and reviewer unchanged. C4 on independent
connected cases, R4, E1/E2/E4/E5 and C5 remain open. The [team handoff](../../docs/team-handoff-c4.fa.md)
defines ownership/adoption. This packet, answers and duplicates stay outside
real RAG and held-out test data.
