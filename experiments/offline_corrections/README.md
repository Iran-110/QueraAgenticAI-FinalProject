# C2h: current user facts in the offline SQLite pilot

Delivery and final Linux/Windows publication checks:
[PR #42](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/42).

The no-index scripted backend reused a fixed version/widget question after the
user supplied a version. The core correctly rejected that output with
`KnownFactMarkedMissing`: correction was persisted, but the next run stopped.
The manual [PR #40 report](../../docs/two-case-ui-sqlite-smoke-2026-10-13.md)
is historical and remains unchanged.

Only the no-index `offline_backend` scripted `ask/ask_version` policy changes:

| Script / current active user facts | Authored proposal |
| --- | --- |
| `ask`, version unknown | Existing canonical version question |
| `ask`, version known, widget unknown | Widget key/code question only |
| `ask`, both known | Escalate: synthetic source support is insufficient |
| `ask_version`, version known | Escalate without adding a widget gap |
| Required fact withdrawn | Ask for that user information again |

Evidence/prose and superseded facts never confirm the user's environment.
The core guard, contracts, legacy scripts, other explicit scenarios and
indexed/grounded/live adapters remain compatible. This is authored operational
routing, not general gap discovery, model decision quality or issue resolution.

## Preserved registration and corrected test predicate

Nineteen controls were frozen before production at `a6ec28d`. The
[V1 protocol](protocol-v1.json) and [original baseline](baseline-v1.json) record
**5 pass / 14 fail** on unchanged `ab6ed04` source. The
[first candidate](candidate-v1.json) records **18 pass / 1 fail**: an AppTest
assertion required an existing disabled Approve button after committed ACK loss.
The page correctly omitted it because no pending proposal remained.

The [separate V2 amendment](amendment-v2.json) changes only that mechanical
predicate to **no enabled Approve**, accepting either omission or disablement.
Questions, routes, operation identity, action counts, stale approval, cases,
revisions and retry assertions are unchanged. The byte-exact
[original V1 UI test](frozen-v1/test_offline_scripted_ui.py.txt), registration
and both V1 results remain inspectable; V1 never becomes nineteen passes.

## Actual same-test comparison

The [byte-exact V2 receipt](comparison-v2.json) runs identical amended nineteen
test bytes on actual archived `a6ec28d` source (verified identical to `ab6ed04`)
and committed `090c1e5` source. Child/worker imports are bound to each snapshot,
including namespace packages entirely inside it. Process environment excludes
provider credentials/selectors; only numeric loopback is allowed.

| Same V2 controls | Before | After |
| --- | --- | --- |
| All nineteen outcomes | 5 pass / 14 fail | 19 pass / 0 fail |
| Three sample HTTP turns: known version, correction, widget fact | Three `KnownFactMarkedMissing` stops, no pending proposal | Widget question, widget question, escalation; revisions 1/2/3 |
| Automatic actions in those three sample views | 0 | 0 |

Tests cover the actual Streamlit page, approved canonical reply, current facts,
provenance, withdrawal, case isolation, stale approval with 409, historical
failed-event replay, ACK loss, exact retry, SQLite recreation and **three fresh
TCP processes**. Expected synthetic local approvals create actions in tests;
zero sample actions is not zero actions in the entire suite. Exact review retry
adds no action. Old failed events keep their recorded outcome; continuation uses
a fresh turn ID, never reinterpretation or reset.

[Verification](verification-v2.json) records **2860 full pytest passes**, Ruff,
locked dependencies, three offline demos and **457/457** existing HTTP/SQLite
checks including fresh-process restart. It identifies actual runtime epochs and
source/test hashes, with no whole-Git-clean claim for full-suite/HTTP invocations.
[Independent assistant review](review-v2.json) is source/output review; human
usefulness scoring is null. Final Linux/Windows publication checks belong to the PR.

Real provider calls, paid cost, index/embedding and production ledger writes are
**zero**. This adds zero independent final cases and measures no model/RAG
quality. PR #40's original operator cases were not rerun. Final corpus/exclusion,
independent dev/test/rubric, C4/C5 and broader T4/U3/E5 remain open.

## Reproduce and hand off

From the root, without model keys:

```bash
uv sync --locked --group dev
uv run pytest tests/test_offline_scripted_corrections.py tests/test_offline_correction_upgrade.py tests/test_offline_scripted_ui.py
uv run python scripts/offline_correction_comparison.py --output /tmp/offline-corrections-new.json
```

Choose an unused receipt path; overwriting is rejected. Git must contain the
preregistration commit and committed source matching the worktree. Pins are
checked before, between and after arms. See the
[Persian operator guide](../../docs/offline-scripted-corrections.fa.md).
