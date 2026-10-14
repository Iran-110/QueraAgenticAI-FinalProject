# Three exposed dev families: controlled core trials

This is an additive development packet, not a final test or RAG quality result.
The first message is a developer paraphrase of a cached issue body; comments and
outcomes were read during preparation. Authored version/correction replies are
conditional fixtures. Chronology, external duplicates and human review remain
open. The original pilot manifest, PR35 protocol and historical receipts retain
their bytes. The active experiment uses the separate [draft manifest](../../data/evaluation/dev-three-v1/split-manifest.json).

- [Known/unknown inventories and conditional oracle, frozen before calls](../../data/evaluation/dev-three-v1/scenario-review-v1.json)
- [Exposure and family review](../../data/evaluation/dev-three-v1/exposure-review-v1.json)
- [Integration and remaining team work](../../docs/dev-three-baseline.fa.md)

## Actual index acceptance

[Index protocol](index-protocol-v1.json) was registered before the formal build.
The first [receipt](index-receipt-v1.json) rejected a setup with no index; it is
retained. Two fresh native Chroma builds then produced the same snapshot:
`docs-pilot-10e7fc4bf04652d5a8ab5052fe14ef6508d4295b3a6f0d6aa1796ffc77a095aa`.
[Accepted receipt](index-receipt-v2.json): **73/73 checks, 40 native collection
queries**, clean source `0a64a79`, 14 docs/30 chunks, actual three pinned fixtures
through HTTP with a scripted planner. Exclusion covers all issues/comments and
outcomes. These are local lexical vectors, not paid semantic embeddings.
The fixed model bundle's button1.39/multiselect/fragment sources are absent from
this index. Adding cases did not add source coverage or measure retrieval quality.

## Actual model observations

All calls used the existing gateway and designated ledger. Context/slot IDs,
input sources, conditional routes and oracle were committed before each trial.
[Comparison](model-comparison-v1.json) derives its numbers from pinned receipts.

| Arm | Provider outputs | Syntactically valid plans | Complete conditional routes |
| --- | ---: | ---: | ---: |
| A: runtime catalog, V1 plus remaining V2 jobs | 8 | 2 | 0/3 |
| B: reviewed user vocabulary, V2 | 7 | 3 | 1/3 |
| C: B plus current decision/field guidance, V3 | 8 | 8 | 3/3 |

- [V1 protocol](model-protocol-v1.json), [actual receipt](model-live-receipt-v1.json),
  [assistant semantic review](semantic-review-v1.json): three sends; only A/pilot
  attempted. Its initial canonical version question was appropriate; two later
  outputs failed shape validation. Exact malformed fields were not retained.
- [V2 protocol](model-protocol-v2.json), [actual receipt](model-live-receipt-v2.json),
  [assistant semantic review](semantic-review-v2.json): only five previously
  unobserved jobs, twelve sends. Failed jobs are retained. Sanitized diagnostics
  identify invalid question_name shapes after the icon version was known and
  source references inside Enum's query-only retrieve_more branch. Its earlier
  setup failure at `b12fdc3` occurred before authorization/send; the selected
  protocol journal identity was fixed at `b86b97b`, without replaying a paid job.
- [V3 protocol](model-protocol-v3.json), [actual receipt](model-live-receipt-v3.json):
  one preregistered prompt treatment on the same three exposed families; eight
  sends, six reached turns, clean source `dbf7dc4`. Five shared first-attempt
  request hashes are exactly equal to B. Later repair/refinement payloads differ
  and Enum's correction is newly reached. No validator/parser relaxation,
  source trimming, extra attempts or new agent/framework was introduced.

**Shape validity and route completion are not semantic adequacy.** In V3 the
Enum answers quote the generic Session State guide safely but do not explicitly
hand off the caller's source gap to maintainer investigation, as the frozen
conditional oracle requires. Preserve this limitation; do not reinterpret these
answers as solved or fully adequate. A deterministic renderer follow-up is
recorded separately, without rewriting the original V3 proposals or model score.

These are single sequential runs, without randomization/repetition, on three
answer-informed dev families and fixed bundles. They do not estimate general
accuracy, causal improvement, final-test performance or live RAG quality.
Human review is false and usefulness remains null.

## Funding and failure boundaries

A newly authorized finite experiment scope is separate from the historical
continuation. The original scope controls were frozen at `80b5bf3`; a mechanical
V2 audit-rollback amendment gives 69 failed controls on archived old code versus
69 passed on candidate. Eight input-tier controls give 3pass/5fail before and
8pass after. These are accounting tests, not model quality.

Each trial had an immutable USD0.10 cap, exact request slots and at most two
attempts per reached turn. Worst reservation: V1 USD0.091914240/24slots;
V2 USD0.078397440/20slots; V3 USD0.045957120/12slots. All three scopes closed.
The original global USD4.50 ceiling, halt, old grant and USD0.02 unknown hold
remain. Ordinary configured live execution still halts; C5 is not reconciled.

Actual reasoner sends across these trials: **23**, locally estimated cost
**USD0.013688565**. Returned model was verified as `gpt-4o-mini-2024-07-18` and
all new requests settled. This is not the provider invoice or total team spend.
A checkpoint failure before transport dispatch counts zero sends, retains the
conservative uncertainty and closes eligibility; it never releases/replays a
reservation. Credentials and raw malformed outputs are excluded from receipts.

Receipt slots and ledger fingerprints prevent rerunning these historical live
registrations. A future experiment requires a new reviewed protocol and scope,
with the same designated ledger. No refill/reset or automatic public-live bypass.

## Deterministic source-gap handoff replay

The [original V3 semantic review](semantic-review-v3.json) reconstructs all six
terminal proposals with the original `dbf7dc4` renderer. It verifies all source
blocks, current facts/correction and necessary questions, while retaining the
two Enum conditional-answer limitations. Its scores are not rewritten.

[Seventeen controls](source-gap-handoff-protocol-v1.json) were frozen at
`de6c27c` before the renderer changed. The same observed eight V3 plans are
[replayed separately](source-gap-replayed-proposals-v1.json) on `b5a6d92`.
The core now displays the full caller-declared source-gap description/necessity
and proposes further documentation/maintainer investigation on terminal
surfaces. ASK remains its exact canonical question; retrieve_more is unchanged.
Source content, references and active facts remain bound to the original request.
No-gap byte goldens and oversized-output fail-closed checks are preserved.

This fixes disclosure of an existing input gap; it does not diagnose Enum,
automatically discover gaps or establish human usefulness. No new model request
or paid API cost is incurred by the renderer replay. Original V3 proposals,
decisions and the frozen scenario oracle are unchanged.


## Historical-default compatibility amendment

The first renderer treatment (`b5a6d92`) passed the same17 archived controls,
but the full suite caught legacy drift: **3070passed/8failed/19errors**. Frozen
C3 complete-analysis and V9 goldens must remain reproducible; none were edited.
Original V1 controls are preserved byte-for-byte in
[source-gap-handoff-controls-v1.py](source-gap-handoff-controls-v1.py) and Git
`de6c27c`. Its [original receipt](source-gap-handoff-receipt-v1.json) remains.

[V2 registration](source-gap-handoff-protocol-v2.json) was committed before
making the handoff an explicit caller mode. Its41 controls preserve the original
17 assertions and add historical default/false bytes, strict flags, bounded
refinement and fresh question/source checks. Observed baseline20pass/21fail
becomes41pass. Seventeen separate configured-factory controls give5pass/12fail
before and17pass after: four actual intercepted HTTP switch combinations,
invalid options rejected before credential lookup and ordinary halt retained.
Initial configuration test setup failures (missing temporary directory/short
synthetic review token) were corrected before freezing the final control bytes.

`render_grounded_plan(..., source_gap_handoff=True)` or an explicit
`GroundedReasoner` caller option enables disclosure; default/false preserve the
historical output. The private factory uses `METIS_GROUNDED_SOURCE_GAP_HANDOFF`.
It is independent of `METIS_GROUNDED_DECISION_CONTRACTS`; both are strict opt-ins.
The configured factory now forwards both options, with validation before keys.
No option changes budget authority or stored approval identities.

[Explicit replay](source-gap-replayed-proposals-v2.json) reproduces exactly the
same candidate analyses as V1 using the same eight recorded plans, while default
rendering preserves original V3/legacy outputs. This is another deterministic
software check, not another real model trial or retrospective V3 score.
Historical model protocols reject the unregistered renderer mode.

[Verification](verification-v1.json) binds the separate configuration baseline/
candidate XML and the retained failed full-suite run. Final local suite:
**3139passed/0failed/0errors/0skipped**. The three required demos, locked sync,
Ruff and format checks pass. [HTTP/SQLite receipt](http-sqlite-receipt-v1.json):
**457/457**, including fresh-process restart and immutable retry. GitHub Linux/
Windows checks are required on the final publication head before merge.
[Actual archived V2 renderer comparison](source-gap-handoff-receipt-v2.json)
executes41 controls; the separate17 configuration controls are not included in
that number. Reproduce from the repo with the exact candidate commit:

```bash
uv run python scripts/source_gap_handoff_replay.py --candidate a641b52cee3ac1ddb7e9119bb21199d3948aba32 --output-dir runtime/source-gap-comparison
```
