# Evaluation cases

Draft layout for E1/E2. The schema still needs agreement with the core owner
before the full 30 cases are written; `dev/pilot-12782.json` is the first case
in this format.

- `split-manifest.json` lists selected cases and whole issue families per split,
  the issue IDs already exposed during development, and open blockers. Hassan's
  index exclusion (R2) reads it. It is a draft until `status` says frozen.
- `scenarios/` holds synthetic operational scenarios the brief requires
  (tool failure, switching between two cases). They use synthetic evidence from
  `evidence/` and do not count toward the 30 evaluation cases.
- `dev/` and `test/` hold one JSON fixture per case. A fixture is committed
  before its first run; later edits get a new `fixture_id`.

## Case fixture fields

| Field | Who reads it |
| --- | --- |
| `case` (ID, split, issue family, source URL, snapshot date, test eligibility, exposure) | runner, reviewer |
| `turns[].visible` (message and explicit facts, unknowns, checks, context change, or a reply to the approved question) | sent to the API in order |
| `turns[].conversation_source` (real issue text, paraphrase, or developer-authored follow-up) | reviewer |
| `turns[].evidence_bundle` + `evidence_source` | offline retriever only |
| `turns[].agent_script` | offline stand-in for the model; absent in real-model runs |
| `turns[].maintainer` (approve, reject, edit then approve, or none) | runner |
| `turns[].faults` (`retrieval: true`, or `reasoning_errors: N` before the scripted output; offline only) | runner |
| `turns[].case_id` and `case.extra_case_ids` (several cases in one fixture) | runner |
| `turns[].gold` (acceptable decisions, gaps, unacceptable claims) | reviewer/scorer only, never model input or index |
| `turns[].expect` and `probes` (operational checks on stored state) | runner |

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
effects. Before running it refuses duplicate case
IDs, a changed evidence hash, a test case marked ineligible, and any issue
family that appears in both dev and test.

Each turn records latency, model attempts, retrieval rounds, steps, cost and
tokens. The receipt also records the git commit, fixture SHA-256s, config and
evidence snapshots.

- `offline` (default) uses the scripted `agent_script` outputs. Cost is zero and
  `quality_claim` is false: it shows operational behaviour, not decision quality.
- `live` needs `--adapters module:factory`, returning an object with
  `for_case(case_id) -> RunAdapters`, `ledger` and `config`. The factory only
  ever sees case IDs; scripted outputs and gold are not used. Cost comes from
  the ledger's spend before and after each turn; tokens from the ledger entries
  of the proposal's attempts. Live runs spend the shared budget and follow its
  rules. No live adapter exists yet (U3).

Receipts must be written under a directory named after the mode
(`receipts/offline/`, `receipts/live/`) and are never overwritten.
`python -m agent_app.evaluation.pilot` is kept for the P1 command;
`receipts/pilot-12782-v1.json` is that run's single-case receipt.
