# Evaluation cases

Draft layout for E1/E2. The schema still needs agreement before the full 30
cases are written; `dev/pilot-12782.json` is the first case in this format.
The manifest currently selects **one dev case and zero test cases**. It is not
a frozen split. The [core-owner rubric review](../../docs/evaluation-rubric.md)
is a recommendation for E2, not an implemented scorer, team approval or an E2
completion claim. Registered fixtures and receipts are preserved unchanged.

- `split-manifest.json` lists selected cases and whole issue families per split,
  the issue IDs already exposed during development, and open blockers. Hassan's
  index exclusion (R2) reads it. It is a draft until `status` says frozen.
- `scenarios/` holds synthetic operational scenarios the brief requires
  (tool failure, switching between two cases). They use synthetic evidence from
  `evidence/` and do not count toward the 30 evaluation cases.
- `dev/` and `test/` hold one JSON fixture per case. A fixture is committed
  before its first run; later edits get a new `fixture_id`.

The seed pool is tracked under `streamlit-data-for-dev-test/`: 240 Issues,
1178 comments, 56 Markdown documents and 1172 versioned API records. Its packaged
checksums can be verified with `uv run python data_scripts/seed_profile.py`.
Presence in Git does not freeze the split or approve a RAG corpus. Family
selection, linkage review and final corpus exclusion remain E1/R1/R2 work.
The complete project targets remain 15 dev,
15 test and at least 10 multi-turn scenarios, at least five of them in test.

## Case fixture fields

| Field | Who reads it |
| --- | --- |
| `case` (ID, split, issue family, source URL, snapshot date, test eligibility, exposure) | runner, reviewer |
| `turns[].visible` (message and explicit facts, unknowns, checks, context change, or a reply to the approved question) | sent to the API in order |
| `turns[].conversation_source` (real issue text, paraphrase, or developer-authored follow-up) | reviewer |
| `turns[].evidence_bundle` + `evidence_source` | offline retriever only |
| `turns[].agent_script` | offline stand-in for the model; never supplied to live adapters |
| `turns[].maintainer` (approve, reject, edit then approve, or none) | runner |
| `turns[].faults` (`retrieval: true`, or `reasoning_errors: N` before the scripted output; offline only) | runner |
| `turns[].case_id` and `case.extra_case_ids` (several cases in one fixture) | runner |
| `turns[].gold` (acceptable decisions, gaps, unacceptable claims) | reviewer/scorer only, never model input or index |
| `turns[].expect` and `probes` (operational checks on stored state) | runner |

The proposed `rubric_id`, per-turn strata/gaps/evidence conditions and conditional
routes are documented in the rubric review. They require schema and runner
implementation by the evaluation owner. Exact `expect` fields test the scripted
trajectory in offline mode; live mode skips them and retains the decision-label
check, without judging source support or question necessity. A live evaluation
must handle registered alternative questions and responses without revealing
later inputs early; adaptive branch selection remains unimplemented.

## Running the evaluation

```bash
uv run python -m agent_app.evaluation.runner data/evaluation/dev
uv run python -m agent_app.evaluation.runner data/evaluation/dev --output data/evaluation/receipts/offline/dev-<date>.json
```

The runner drives the FastAPI app the UI uses, in process. Each turn sends only
that turn's `visible` input, so later turns, gold and expectations never reach
the agent early. Checks read stored state: revisions, fact history, the bound
reply, cited sources and version scope, stale and pre-edit approvals refused,
double approval refused, rejection releasing nothing, stop reasons after
injected failures, proposals refused through another case, every other case
unchanged on each turn, and replay of every accepted event without side
effects. Before running it refuses duplicate case IDs, a changed evidence hash,
a test case marked ineligible, and a family shared across splits **among the
files loaded in that invocation**. It does not yet enforce the split manifest,
its frozen status, exposure reservations, minimum counts or R2 corpus exclusion.
Those checks must be implemented before claiming final held-out evaluation.

Each turn records latency, model attempts, retrieval rounds, steps, cost and
tokens. The receipt also records the git commit, fixture SHA-256s and config.
Its case/top-level snapshots come from evidence actually supplied to captured
reasoner attempts; `config.snapshot_id` remains the adapter's declared value.
New receipts use schema version 2 and record Python-source
hashes plus `source_unchanged_during_run`; historical receipts retain their
original schema. Metrics unavailable after a stopped run can be null.
Full review must retain the original
`pending.review_handoff`, every edited proposal and the released response, bound
to their proposal IDs and hashes. New runner receipts preserve `proposal`,
`edited_proposal` and `released_outputs`; full proposal objects contain the
analysis, final evidence, source inventory and review handoff. Storing them does
not score claim support, question utility or human usefulness. The E2
scorer/review schema remains open; older receipts remain in their original format.

- `offline` (default) uses the scripted `agent_script` outputs. Cost is zero and
  `quality_claim` is false: it shows operational behaviour, not decision quality.
- `live` needs `--adapters module:factory`, returning an object with
  `for_case(case_id) -> RunAdapters`, `ledger` and `config`. The factory only
  ever sees case IDs; scripted outputs and gold are not supplied to it. No real live adapter
  exists yet (U3). A `BudgetLedger` is mandatory; preflight rejects a halted
  ledger, a configured limit above the team's USD 5 cap or unavailable budget
  before `for_case` runs, and checks again before each turn. The factory must
  construct its local configuration and ledger without making paid requests;
  the runner cannot inspect that ledger until the factory returns it. Existing pending and
  uncertain holds remain included in availability. Inspect the designated
  runner's reservations and approved shared ceiling before actual use; the
  gateway still enforces its request reservation limits. No reset or extra
  laptop ledger can release the real project's halt.

Live accounting joins **observed reasoner attempts only** to individual gateway
request IDs, including repaired or stopped attempts. `usage_scope` explicitly
excludes retrieval, embeddings and adapter setup; this is not the total cost of
the run or team. Those costs still consume the shared budget and need separate
gateway/ledger attribution by their owners.

Per-turn `settled_usd`, `reserved_usd` and `uncertain_usd` retain the known ledger
amounts and distinct statuses. `cost_usd` and `cost_usd_total` are null if a tracked
request is unrecorded, mismatched, pending or uncertain; missing token usage is
also null, not zero. Known settlement totals remain visible even when the total
is unknown. `accounting_complete` describes attribution of these reasoner
requests, not provider billing reconciliation or full-team accounting.
Ledger-wide spend deltas do not attribute concurrent work. Each new live
invocation has a fresh `evaluation_run_id`; retry of the same accepted event
keeps its identity and creates no new send. Live config accepts only allowlisted
scalar fields; never include keys or raw request headers in config/receipts.

Before sending a registered short version reply, live mode verifies that the
approved question is the canonical version question. If another valid question
or route was selected, it stops with `FixtureBranchUnavailable` rather than
feeding that reply to the wrong question. `coverage_complete`, `planned_turns`
and `fixture_branches_unavailable` distinguish this incomplete fixture path from
a completed run. With no failed checks but incomplete coverage, the CLI exits
2; failed checks exit 1, and a complete passing run exits 0. A coverage gap is
not a semantic failure of the model. Conditional follow-up branches remain E2/E3
owner work.
Only cases with complete coverage and no failed checks count in
`cases_all_passed`; every case also records its own coverage status.

`quality_claim` remains false in both modes; neither a live adapter nor a passing
operational receipt is a quality result. External, versioned semantic reviews
can support a separate quality report; the runner does not issue such a claim.
Runner experiments still use process-local API state
and DummyTracker, including live mode: they do not demonstrate durable storage,
reviewer authentication, restart recovery or the production tracker's execution.

Receipts must be written under a directory named after the mode
(`receipts/offline/`, `receipts/live/`) and are never overwritten.
`python -m agent_app.evaluation.pilot` is kept for the P1 command;
`receipts/pilot-12782-v1.json` is that run's single-case receipt.
