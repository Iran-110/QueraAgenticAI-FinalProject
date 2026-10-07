# Offline whole-proposal regression checks

The next core milestone fixes two concrete static-validation gaps and keeps the
remaining semantic gaps inspectable. It does **not** add another model, change a
prompt policy/default, or claim a new live quality improvement.

## Changes and verification

The syntax checker now statically compiles each bounded parsed Python module.
Python can parse duplicate function parameters and invalid module-level
`return`, `break` or `await` without accepting them for compilation. Those cases
now receive the existing `invalid_python_syntax` repair diagnostic. Code objects
are discarded; no imports, functions, annotations or snippets are executed.
Source-bearing parser/compiler warnings and raw exceptions stay unexported.
Valid scoped counterparts and the no-execution boundary have regression tests.

Optional proposal checks now detect a narrow callback parameter-binding mismatch
using an exact-version pinned callable signature and explicit callback argument
documentation. They preserve a correctly supplied stable key, defaults,
positional-only/keyword-only parameters, variadics and intentional old-value
arguments. Ambiguous binding or evaluation effects cause abstention. Independent
static audit compared **2,560 binding combinations** against
`inspect.Signature.bind`, without executing a proposed function, and found no
disagreement. These comparisons are distinct from the pytest test count.

See [applicability and limits](proposal-checks.md). In particular, other top-level
calls, including an extra `st.write(...)`, put the fence outside this conservative
arity subset. Prose-only argument-removal advice is also outside coverage.

## Full-proposal replay

The [authored challenge pack](../experiments/decision_quality/README-semantic-v6.md)
contains **8 synthetic scenarios and 16 complete proposals**. It reuses exposed
V4 inputs with unchanged case/evidence/catalog copies and registered source
hashes. Two explicitly marked hypothetical supplements are recorded separately.
The proposals, semantic labels and detector expectations are developer-authored;
they are not fresh model responses, independent judgments, held-out cases or gold
quality labels. No answer-keyword scoring is used.

The local replay uses fake ports with checks off/on. It repeats a rejected fixed
proposal within the existing two-attempt allowance; it does not generate a
repair. Labels do not enter the engine or determine core acceptance. The
[public replay result](../experiments/decision_quality/results-semantic-v6.json)
records component/fixture hashes and reports:

| Observation | Result |
| --- | --- |
| Replay invocations / scripted reasoning attempts | 32 / 33 |
| Accepted with optional checks off | 16/16 |
| Accepted with optional checks on | 15/16 |
| Isolated, explicit arity mismatch | Rejected within two scripted attempts |
| Developer-positive controls accepted with checks | 7/7 |
| Developer-negative proposals still accepted with checks | 8/9 |
| Detector scope expectations matched | 16/16 |
| Paid requests / estimated fresh paid cost | 0 / USD 0 |

The 16/16 result is agreement with the authored **detector scope** expectations,
not semantic accuracy. The retained negative proposals include reversed update
order, discarded user intent, stale/corrected-fact confusion, unsupported
historical certainty, a wrong claim-to-chunk link, fabricated checked version and
prose-only broken advice. The larger callback example with its output call also
remains accepted. Its original proposal was preserved; a separately labeled
isolated registration demonstrates the smaller proof subset. That authoring
refinement is documented rather than silently changing the original case.

## Reproduce and next decision

From the repository root:

```bash
uv run python -m agent_app.reasoning.semantic_regressions
uv run pytest tests/test_semantic_regressions.py tests/test_callback_arity_checks.py
```

The replay has no live mode, credential loading or ledger access; CI runs it
offline. Hash/context mismatches fail before ports run, and diagnostics do not
export invalid input or exception text. Run IDs hash canonical identity tuples
so long IDs and delimiter ambiguities cannot break the replay.

Keep the shorter measured development policy and human whole-proposal review.
The next semantic work should preserve active user facts, working/failing test
distinctions and claim-specific source support across **all** proposal fields.
These authored regressions expose those requirements; they do not implement a
production fact extractor or entailment judge. A new live prompt/agent comparison
requires its own frozen inputs and source-based review before selecting a policy.
Actual RAG, persisted tracker approval and UI integration remain their owners'
work. The original ledger, retained uncertainty and production defaults stay as
recorded in V5.
