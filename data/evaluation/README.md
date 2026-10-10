# Evaluation cases

Draft layout for E1/E2. The schema still needs agreement with the core owner
before the full 30 cases are written; `dev/pilot-12782.json` is the first case
in this format.

- `split-manifest.json` lists selected cases and whole issue families per split,
  the issue IDs already exposed during development, and open blockers. Hassan's
  index exclusion (R2) reads it. It is a draft until `status` says frozen.
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
| `turns[].gold` (acceptable decisions, gaps, unacceptable claims) | reviewer/scorer only, never model input or index |
| `turns[].expect` and `probes` (operational checks on stored state) | runner |

## Running the pilot

```bash
uv run python -m agent_app.evaluation.pilot data/evaluation/dev/pilot-12782.json
```

It drives the same FastAPI app the UI uses, in process, with scripted
adapters, and prints a receipt. A scripted agent makes the decisions, so the
receipt shows operational behaviour (revisions, stale proposals, approval
binding, edits, rejection, replay), not decision quality.
