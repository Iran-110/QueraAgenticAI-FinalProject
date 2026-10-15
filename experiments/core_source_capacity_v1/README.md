# C4h3: compact source-capacity experiment

**No live route or answer-quality improvement demonstrated. Default remains off.**
This is an exposed, answer-informed three-dev experiment, not held-out/final
validation and not a RAG quality score. No new framework or agent was added.

- [Protocol before implementation](protocol-v1.json), commit`3f98c27`.
- [Frozen finite method](live-method-v1.json),48 exact slots in6 finite scopes.
- [Semantic criteria before calls](semantic-review-preparation-v1.json).
- [Original live receipt](model-live-receipt-v1.json), paid source`05be694`.
- [Read-only cost/provenance review](cost-review-v1.json),1225/1225 checks.
- [Assistant semantic inspection](semantic-review-v1.json),44 mechanical
  checks, all24 planned turns,6 distinct selected excerpts. Reviewer implemented
  the treatment and knew arm identities; **not independent human review**.

Both arms use native18-source/36-chunk Chroma, lexical_hash_v1, existing main
ranking, top5 before version scoping. No source-ID/gold filter, corpus build,
quote truncation or extra model/retrieval capacity. Both arms enable the existing
repeated-query repair, source reminder and gap handoff/investigation; only compact
source capacity varies. The original verbose resource guidance stays off.

| Observation | OFF | ON |
|---|---:|---:|
| Full exposed-dev routes |4/6|4/6|
| Fresh proposals |8|8|
| Necessary USER questions |5|5|
| Qualified SOURCE escalations |3|3|
| Technical answers |0|0|
| Calls with changed source-count bound |0|2|
| Renderer overflows observed |0|0|

The bound changed only the two ON calls on one Enum correction,8→3. All6 paired
initial requests and their wire messages were identical; initial differences are
stochastic, not an effect of this treatment. No live overflow reduction can be
inferred because neither arm encountered that failure. Archived offline replay
separately verifies that the historical four-source overflow has a safe bound3;
that authored-subset control is not new model quality.

All24 planned turns remain:16 fresh,4 visited empty and4 conditionally unvisited,
zero stale proposals. There were26 provider `stop` and2 `length` responses.
Malformed extra fields, invalid retrieve_more/source combinations and one
source-reference mismatch remain. No output was silently repaired or truncated.
Ten fresh questions ask missing version or missing parent callback/code; they do
not ask for absent documentation. Six qualified escalations preserve USER facts
and lack a proven cause/fix. This is not a solved-case rate. Correction1.31.1,
old approval rejection and exact retry checks are in the original trace.
Approval is fixture-scripted through TestClient/DummyTracker; this is not a new
browser/SQLite smoke report. The separate fixture HTTP/SQLite acceptance passed457/457.

28 sends all settled, local configured-price estimate **USD0.032721150**; cumulative
settled estimateUSD0.330022770. Both old uncertain holdsUSD0.0233792, global halt,
USD4.50 ceiling and all old authorizations/revocations remain. All392 prior
reservations and14 tables/schema match the private backup;6 new scopes closed
and20 unused slots permanently claimed. This is not a provider invoice.

The closed paid command is intentionally not resumable. Never replace its method,
ledger snapshot or identities to continue. The default CLI now rejects spent
identities. For offline review with no credentials:

```bash
uv run python scripts/prepare_semantic_review.py prepare \
  --receipt experiments/core_source_capacity_v1/model-live-receipt-v1.json \
  --output runtime/capacity-review-FRESH
uv run python scripts/review_source_capacity_run.py \
  --workbench runtime/capacity-review-FRESH/workbench.json \
  --output runtime/capacity-inspection-FRESH.json
uv run pytest tests/test_source_capacity.py tests/test_source_capacity_model_cli.py tests/test_review_workbench.py
```

Current-source tests cover default bytes, every admitted source subset, escaping,
unequal costs, oversize singletons/bases, conflict fallback, correction, actual
HTTP payloads and the unchanged two-attempt rejection.79 archived requests and
158 original/repair contexts passed no-growth input preflight, max32082/32768.
The current method is conservative: a common count bound can exclude feasible
small-source subsets. It is prompt guidance, not semantic support or permission.

Next core measurement should target observed malformed output/reference copying
and1024-token `length` failures with a separately registered comparison. RAG
ranking remains Hassan's separate factor; [PR50 review](../rag_pr50_review/README.md)
shows its newest head still lacks advertised over-fetching. Do not combine that
unmerged change with this baseline. Human rubric/split/test remain open.
