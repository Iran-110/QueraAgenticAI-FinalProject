# Evaluation cases

The additive [offline review workbench](../../docs/evaluation-workbench.fa.md)
now prepares actual C4g/C4h turn contexts, full sources and blank SemanticReview
sidecars. It preserves stopped, stale and unvisited rows beside fresh proposals,
and binds original receipt/method/protocol/fixture/rubric bytes before scoring.
It creates no human labels, final cases or frozen rubric and never makes a model
call. Fixed-evidence oracle strata are displayed separately from actual native
retrieval conditions. This is Sasan's temporary E2 preparation help while
MohammadHasan is unavailable; E1–E5 completion remains open.

The separately registered [three-dev packet](dev-three-v1/split-manifest.json)
now prepares #12782, #9770 and #8129 with opaque runtime IDs, conditional routes,
whole-family exclusions and assistant-reviewed known/missing inventories.
It remains draft, exposed development data with zero test; the historical
one-case manifest and PR35 pins below are preserved. Use
`uv run python -m agent_app.evaluation.runner data/evaluation/dev-three-v1/cases --conditional-routes`
for its scripted replay. Fixed-evidence model conditions and the actual14-doc
index are separate; [guide](../../docs/dev-three-baseline.fa.md).

Draft layout for E1/E2. The schema still needs agreement before the full 30
cases are written; `dev/pilot-12782.json` is the first case in this format.
The manifest currently selects **one dev case and zero test cases**. It is not
a frozen split. The [core-owner rubric review](../../docs/evaluation-rubric.md)
is a recommendation for E2; [rubric v1](../../docs/evaluation-rubric-v1.md)
(`e2-rubric-v1`) adopts it with Sasan's 2026-10-15 additions for new fixtures
and reviews. The additive semantic-review helper below records
caller judgments; rubric adoption, team approval and E2 completion remain open.
Registered fixtures and historical receipts are preserved unchanged.

`split-e1-v1/test/` holds **held-out test** fixtures and gold. Core developers must not open them or tune prompts, retrieval or model choice on them before the final test run.

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

## Candidate reservations and final artifact gate

`candidates/reservations-v1.json` reserves **15 dev / 15 test metadata-only
candidate components**, not finalized cases. It contains public IDs, links,
counts, query scopes and review tasks, never held-out questions or answers.
Reproduce it into a fresh output file:
`uv run python scripts/propose_evaluation_families.py --output /tmp/candidate-reservations-replay.json`.
Known development exposure is excluded from test. Link components still need
true duplicate-family review, prior exposure across all teammates, initial-text
chronology, strata, source coverage and meaningful conditional turns. Reuse the
existing pilot for candidate-12782; do not count it twice. The partial exclusion
list is not a reviewed final corpus denylist.

The additive `agent_app.evaluation.preflight` module checks a **new**
`frozen_final_v1` packet without upgrading historical fixtures or receipts:

```bash
uv run python -m agent_app.evaluation.preflight --manifest FINAL_PACKET.json --corpus-manifest CORPUS.json data/evaluation/dev data/evaluation/test
```

Its schema and synthetic integrity examples are in
[`preflight.py`](../../src/agent_app/evaluation/preflight.py) and
[`test_evaluation_preflight.py`](../../tests/test_evaluation_preflight.py).
It requires pinned fixture/rubric/exposure/corpus JSON, canonical origin URLs
within reviewed families, whole-family/exposure exclusion, 15/15 minimums and
reviewed route metadata for at least ten multi-turn cases (five test). Output
contains counts, hashes and allowlisted diagnostics only. Human declarations
do not authenticate the reviewer or prove semantic quality. Corpus declarations
do not verify actual indexed content, model/prompt/code freeze or runtime binding.

Runner flags `--final-manifest` and `--final-corpus-manifest` opt into this
gate. `--final-bundle` supplies all pinned dev/test fixture paths while the
positional paths may execute a subset, such as dev alone. It additionally
validates **every** fixture with the existing loader and rejects escaping or
non-JSON evidence paths before importing/constructing the live factory. The
receipt retains `final_artifact_preflight`; `quality_claim` remains false.
Ordinary development commands remain available for draft fixtures. This gate
does not authorize spending; the separate
budget halt and live adapter requirements still apply. Complete final
evaluation remains E1–E5 work.

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

The proposed `rubric_id` and per-turn strata/gaps/evidence conditions are
documented in the rubric review and still need owner adoption and freeze.
Registered conditional routes are now opt-in with `--conditional-routes`, and
mandatory for live `--final-manifest` runs. Exact `expect` fields test the scripted
trajectory in offline mode; live mode skips them and retains the decision-label
check, without judging source support or question necessity. A live evaluation
must register alternative questions and responses before execution. The new
route selector handles exact registered current questions without revealing
later inputs early; an unmatched valid paraphrase stops with a fixture coverage
gap rather than inventing a user reply. See
[route/live integration guide](../../docs/evaluation-live-routes.fa.md).

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
The optional final-packet gate above enforces these declared artifact conditions
over the whole bundle; ordinary draft runs do not. Neither proves actual final
index exclusion or held-out quality.

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
review schema still needs owner adoption; older receipts remain in their original format.

`agent_app.evaluation.semantic_review` now provides typed `ReviewScope` and
`SemanticReview` sidecars plus `score_review` / `aggregate_reviews`. Exact claim
spans, source quotes and active user-fact references are checked against the
bound handoff; semantic judgments are supplied by the reviewer. One unsupported
material claim fails support; incomplete/insufficient review is unassessed,
complete zero-claim support is N/A. Aggregates retain denominators and separate
strata, configurations, rubrics, declared human/assistant and original/edited
responses. They count cases separately from proposals. This helper does not
discover claims, prove entailment, authenticate humans, grade usefulness by
itself, freeze E2 or authorize an action. Usefulness remains a human judgment.

- `offline` (default) uses the scripted `agent_script` outputs. Cost is zero and
  `quality_claim` is false: it shows operational behaviour, not decision quality.
- `live` needs `--adapters module:factory`, returning an object with
  `for_case(case_id) -> RunAdapters`, `ledger` and `config`. The factory only
  ever sees case IDs; scripted outputs and gold are not supplied to it.
  `agent_app.evaluation.live:factory` now supplies verified docs-pilot Chroma +
  GroundedPlan gateway ports with case-bound cleanup. It needs explicit index,
  manifest/snapshot pins and private environment settings; it uses the existing
  designated ledger and refuses the current C5 halt. A `BudgetLedger` is mandatory; preflight rejects a halted
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
