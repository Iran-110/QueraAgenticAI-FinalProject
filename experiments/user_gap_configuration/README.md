# C4c: caller vocabulary on the ordinary configured factory

This delivery connects existing `caller_catalog` behavior to explicit operator
configuration. It does not discover missing information or measure better
real-model selection. Only `reasoning/catalog.py` and `evaluation/live.py` change
in production; shared contracts and the RAG/UI/tracker modules remain unchanged.

## Registration and actual code comparison

The [protocol](protocol-v1.json), [runtime inputs](inputs-v1.json),
[reviewer-only inventory](scenario-review-v1.json) and 21 controls were committed
at `999a9d6` before production changed; its source is identical to `43ee9fb`.
Three neutral V9 question definitions and four state/message/bundle variations
come from the exposed, answer-informed #12782/#12629 family. No same-Issue answer
is a supplied source and no independent case is added. Cases, answers,
duplicates and reviewer files stay outside real RAG/final test.

Both arms keep case, message, evidence and runtime source gaps equal. Candidate
adds caller vocabulary selected only by explicit current unknowns and active
USER facts. Complete catalog/request/prompt hashes intentionally differ.
Reviewer labels, authored answers and future bundles do not enter planner
requests; the old manually curated source catalog is not substituted.

| Same frozen controls | Original `43ee9fb` | Candidate `f0145c9` |
| --- | --- | --- |
| Passed | 9 | 21 |
| Failed | 12 | 0 |
| Error / skipped / not run | 0 | 0 |

[Original baseline](baseline-v1.json) ran on clean pre-change `999a9d6`.
[First candidate](candidate-v1.json) ran with the production diff uncommitted
and makes no whole-Git-clean claim. The [final Git-archive comparison](comparison-v1.json)
imports actual source from both stated commits with identical frozen bytes and
node IDs. It validates isolated import origins, archived source/seed/helper
pins, pytest exits/outcomes and unchanged source/production-ledger fingerprints.

The twelve repaired controls concern configuration validation/adoption and the
configured HTTP path; they are **not twelve real model decisions**. Nine
controls, including direct Python `caller_catalog` injection, already worked.
The authored first-eligible planner exposes available questions. Three
known-version states permit the callback question; unknown-version preserves
the canonical version question. This measures capability, not model judgment.

The HTTP control uses the actual configured factory, offline Chroma and SQLite,
with four intercepted provider requests. It verifies two-case isolation,
correction, stale unexecuted approval rejection, supplied callback suppression
and exact committed review retry after backend recreation. Retry adds zero
action/provider wire. It is not a manual browser run or model-quality evidence.

## Verification and method review

[Verification](verification-v1.json) binds **2,881 pytest tests** in112.603s on
clean `3a166d1`, Ruff/format210 files, locked sync and three demos. Separate
fresh-process HTTP/SQLite **457/457** including restart passed on clean `f0145c9`.
Runtime/test bytes match the comparison. Publication docs/CI and the final main
merge are separate epochs; final CI is linked by the delivery PR.

An initial comparison on `3a166d1` remains locally as diagnostic. Before the
published receipt the harness was strengthened to reject internal pytest
errors, isolate child imports and verify all fixture bytes. Frozen controls,
oracle and product source stayed unchanged. The independent [assistant review](review-v1.json)
records five rejected fault injections and two accepted positive controls;
these seven fake-child probes are not additional product/model tests. Human
usefulness remains null.

## Adoption and remaining work

The [Persian guide](../../docs/user-gap-configuration.fa.md) explains
`AGENT_USER_GAP_CATALOG`: caller-reviewed UTF-8 JSON, exact `schema_version` and
`user_gaps` keys, at most32768 bytes and six user definitions. No default
vocabulary is added. Existing budget/index gates remain first; invalid vocabulary
fails before key/client setup. Definitions load once; changes require a new factory.

UI/API callers must register applicable names in `unknowns` and replies in
`reported_facts`. Active USER facts override stale unknowns. Prose/sources cannot
select a file or create a question; schema does not prove question necessity.

API spend is **USD0**. Original ledger, hold/halt and immutable grant remain.
USD0.00206953 remaining cannot fully reserve a pair at USD0.001689600 per request.
No partial paid pair, refill/reset or unhalt was done; ordinary C5 startup stays
blocked. Independent dev/test, corpus/exclusion, human review, model quality and
T4/U3/E5 remain open. The engineering completion estimate is unchanged.

From the repository root, without keys:

```bash
uv run pytest tests/test_configured_user_gap_catalog.py tests/test_user_gap_configuration_http.py
uv run python scripts/user_gap_configuration_comparison.py --output /tmp/user-gap-comparison.json
```

Use a fresh output path. Preserve original protocol/reviewer/receipts. Any actual
model comparison needs separate pre-registration and funded authorization;
incomplete outputs and human/assistant reviews must remain separate.

## Portable publication follow-up

First publication CI at `95c7d98` passed Linux and all21 native Windows controls,
then the comparison harness rejected a Git path containing Windows backslashes.
No archived Windows receipt was emitted; the failure is not a core/model result.
The original [comparison](comparison-v1.json), verification and failed CI remain
preserved. Repo-relative Git/receipt paths now use POSIX separators on all hosts.

The new [portable comparison](comparison-portable-v1.json) on `2c8b44a` still gives
9pass/12fail versus21pass/0fail with identical frozen controls. [Portable verification](verification-portable-v1.json)
records the original CI failure and actual Git-blob check for a normalized
Windows-style path. Product/test/oracle bytes stay unchanged; only the harness
paths change. Full pytest/HTTP/demos from the prior source epochs still apply.
Final publication CI must pass the matching head in [PR #44](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/44).
