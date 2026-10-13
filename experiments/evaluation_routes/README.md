# Controlled runner-route comparison

Registration was committed at `65f1c31` **before this comparison**. The fixture
reuses exposed, developer-authored synthetic test material already exercised in
unit tests; it is not a newly registered independent Issue or held-out case.
Neither its inputs, gold, nor receipts belong in the real RAG corpus.

[Result on clean source 65f1c31](results-65f1c31.json): the old runner follows
turns in file order and does not complete any of the three registered paths;
the conditional runner completes **3/3**. Both use exactly the same current
core, ports, synthetic evidence, fixture and mandatory mocked provider helper.
Only the archived runner module from `a0877705abdb54882f7d478f8801931f28d2ccca`
is replaced in the baseline. This is not a full historical-release comparison.

| Fixed mock choice | Old runner visits | Conditional runner visits |
| --- | --- | --- |
| parent callback question | initial, callback; then stops before incompatible version reply | initial, callback; registered terminal reached |
| version question | initial, callback; then stops before incompatible version reply | initial, version, correction; registered terminal reached |
| escalation | initial, callback; then stops before incompatible version reply | initial; registered terminal reached |

The baseline has **zero failed mechanical checks**, but incomplete path coverage.
Do not report its result as wrong model decisions, failed pytest, or 0% answer
quality. The new result shows proper continuation/termination selection and no
irrelevant future user reply, not improved semantic quality. All allocated mock
SDK clients close in both variants. Trace data is projected to counts, IDs and
hashes; no provider payload, credential or source/output text is published here.

Real API sends and paid cost are **zero**. Receipt `simulated_settled_usd` is
usage attributed to intercepted mock requests on separate temporary ledgers,
not team expenditure. The designated production ledger and C5 halt are untouched.
Maintainer approval is fixture-scripted and tracker storage is process memory.
Persistent SQLite behavior is tested independently; these paths add **zero**
cases to the final 15/15 evaluation set.

Reproduce without overwriting the original receipt:

```bash
uv run python scripts/evaluation_routes_comparison.py --output /tmp/routes-comparison-new.json
```

Git history must contain the pinned baseline commit. Protocol, fixture and
shared test-helper bytes are verified before execution; changing any requires
new preregistration. The result pins current Python source hashes and verifies
they stay unchanged during the run. Core-source changes legitimately require
a new comparison rather than rewriting this historical result.

This fixed control complements the broader tests for unreleased/rejected/edited
questions, source gaps, unmatched paraphrases, graph eligibility and final gating:

```bash
uv run pytest tests/test_eval_conditional_routes.py
```
