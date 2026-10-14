# C4h / E2p — current resource constraints and complete review coverage

This packet follows the three **exposed, answer-informed development families**
in C4g. It is not held-out evaluation, a new case selection, a RAG ranking
change, or a complete final rubric. The existing single-agent architecture stays.

The [protocol](protocol-v1.json) was committed at `9ab4cec` before implementing
the treatment or making new model calls. The observed baseline contains five
RepeatedQuery stops and one all-source renderer overflow. Both guards were
correct; those original receipts are unchanged.

Optional `METIS_GROUNDED_RESOURCE_GUIDANCE=true` tells the planner the current
query-repeat rule and exact complete-quotation rendering costs before choosing
a plan. Disabled/default preserves complete historical prompt bytes. The
renderer, references, facts, conflicts, approval rules and two-attempt bounds
remain authoritative. Costs are Unicode character counts for rendered fields,
not tokens or proof of semantic support. Source lengths are positional in the
unchanged current evidence order, never relevance scores.

The new paid comparison uses the identical verified 18-source/36-chunk native
lexical index in OFF/ON arms. It keeps the existing current-user-version scope,
top5 ranking, other four flags, output1024 and reserve32768. Six balanced pairs
in two rounds have 48 fresh immutable slots, up to USD0.06 per pair. Missing
documents still require source investigation; guidance cannot create evidence.

`live-method-v1.json` preserves the initial read-only registration preview.
It allocated no scope and sent no request. The active
[method V2](live-method-v2.json) additionally requires an offline full-payload
preflight in its builder: 29 archived actual requests and their repair-capacity
variants, 58 contexts/116 OFF/ON size checks. Future model-selected retrievals
remain subject to the unchanged per-call UTF-8 guard; the archived check does
not prove their sizes. V2 retains the initial preview hash and uses fresh IDs
never allocated by V1. No old scope or grant is revived.

The read-only preregistration validation used before the paid campaign was:

```bash
uv run python scripts/core_resource_model_probe.py
```

After closure this exact method intentionally refuses another run: its ledger
snapshot is spent. Inspect the immutable receipts/reviews below; do not prepare
a replacement method to resume its remaining pairs.

An actual new registered run requires explicit `--live`, the ignored `.env`, a fresh private
output directory outside Git, and the exact registered ledger. This is a finite
development exception preserving the global halt, both unknown holds and
USD4.50 cap. It does not enable ordinary live UI/API startup or reconcile C5.
The script checks source/input/method/index before credentials, between pairs
and immediately before HTTP dispatch. Any new uncertainty stops the campaign;
cleanup closes only a scope bound to our exact digest and authorization ref.
Unused slots stay permanently claimed after closure. Do not replay spent IDs.

The companion [review workbench](../../docs/evaluation-workbench.fa.md) helps
MohammadHasan's E2 work without changing Hassan's ranking/backfill or Behnam's
manual UI/SQLite smoke. On the original C4g receipt it preserves all 24 planned
turns: 23 visited, 17 fresh proposals, six visited without fresh response
(including two stale observations), and one unvisited. Blank review templates
have no human scores. Fixed-evidence strata and actual native-index criteria
are displayed separately; a source available in a fixture may be absent from
the actual bundle.

The course motivates measuring failed attempts and abstention separately
(Week03 HW03), choosing necessary evidence rather than copying everything
(Week02 HW01), bounded planning and deterministic action gates (Week04 HW03),
and testing reviewer regressions (Week04 HW01). A new reviewer agent, bandit or
conformal policy needs independent labels and a measured problem first. Three
exposed families and pending human usefulness labels do not justify those
architectural additions or a bonus-quality claim.

## Original paid observation

The [byte-exact actual receipt](model-live-receipt-v1.json) records21HTTP sends
on `f71ec1631d4830dfd0eb5cec0139f6abad58733e`; production sources/input/index were
unchanged during execution. Four of six registered pairs ran: eight jobs and
16visited turns, not a complete balanced two-round experiment. Four jobs/eight
turns were unvisited. Both OFF and ON completed **1/4 visited routes**; no
quality gain is established. The option remains experimental/default-false.

The [assistant trace review](semantic-review-v1.json) retains22planner attempts,
20observed schemas (18valid/two invalid), three valid repeated-query plans,
five valid novel-query plans, and10fresh proposals: six necessary questions,
two qualified general SessionState backgrounds and two investigation handoffs.
Four Enum corrections have only stale prior proposals; their approval gets409.
Both visited B/version turns have no fresh proposal. Documentary background
does not establish Enum cause/fix or human usefulness. One provider output
finished `length` at1024 and stopped as ProviderResponseInvalid with settled
usage. Invalid raw outputs were not retained, and the reviewer authored the
guidance; these limitations are explicit. Human usefulness stays null.

One novel Enum correction refinement yielded five full chunks with an input
size33075 including the conservative margin. The unchanged32768 guard stopped
before reservation/HTTP. On the **same captured request**, OFF is32065: the
guide itself causes this observed regression. Archived-input preflight fits do
not cover every future retrieval result. The original fourth Usage reports
`unrecorded` and `accounting_complete=false`/`cost_usd=null`; the campaign
stopped at four pairs and will not resume. This failure is retained.

The [independent cost review V2](cost-review-v2.json) passes882/882 controls:
21settled sends atUSD0.024946020 local estimate;362settled/two old uncertain and
zero pending afterward. All343 old reservation rows, all old rows across14
tables and the full schema remain unchanged. Four scopes closed,32slots
allocated/21used/11unused permanently claimed;16planned slots were unallocated.
Both old holds totalingUSD0.0233792, halt, revocations and4.50ceiling remain.
The total settled local estimate isUSD0.264364980. These are recorded gateway
usage and local rates, not independently retained raw billing envelopes or an
account invoice. [V1](cost-review-v1.json) remains881/882 because its reviewer
initially compared the executed method digest with previewV1 instead of activeV2;
V2 corrects only that expectation, not requests or accounting.

## Future-only measurement repair and review coverage

The [separate amendment](pre-dispatch-accounting-amendment-v1.json) changes only
future scoped drivers. A real gateway's typed ContextLimitExceeded may be marked
`skipped_before_reservation` with zero local cost/tokens only if its owned
planner observed no ledger row and no transport marker before and after.
The same observations are rechecked by PreDispatchUsage. Missing/unattested,
contradictory, sent, reserved and uncertain records remain conservative; even
`http_send_started=false` after reservation is insufficient. Normal Usage bytes
are unchanged. Twenty-eight new/88focused controls pass, including actual
oversized gateway and conditionalHTTP with zero send, zero reservation and
**zero complete routes**, plus cancellation retaining a real uncertain hold.
No API call was made for this repair and no original receipt was re-scored.

The workbench now supports both original C4g and this closed C4h methodV2.
For C4h it retains24planned/16visited/10fresh/sixno-fresh (fourstale/twoempty)
and eightunvisited rows. Human labels are blank. Prepare a fresh private reader:

```bash
uv run python scripts/prepare_semantic_review.py prepare \
  --receipt experiments/core_resource_guidance_v1/model-live-receipt-v1.json \
  --output runtime/resource-review-FRESH
```

Original C4g results, fixtures, oracle, corpus pins and histories remain intact.
Hassan's relevance/version ranking and Behnam's manual persistent-UI smoke were
not changed. Final family chronology,15dev/15test and human review remain open.

[Release verification](verification-v1.json):3649pytest passed, zero failures,
errors or skips; Ruff checked268Python files; three required demos are valid;
HTTP/SQLite457/457 including restart/retry passed. All203 local documentation
links resolve. The29 changed files scanned contain no actual environment key.
These are software/receipt-integrity checks, not a quality score. CI on the
reviewed final head remains the publication gate.
