# Agent-core progress

This is a factual milestone log, not a daily activity schedule. Update it after a verified change; keep real dates and real limitations.

## 2026-10-06 — first foundation

Branch: `feat/agent-core-foundation`. Scope: the owner's contracts and orchestration, with deterministic offline adapters.

- Shared validated contracts separate case facts, evidence, decisions, run results, and limits.
- The core proposes answer, question, or escalation and allows bounded retrieval refinement.
- Case revision checks, retrieved references, and adapter failures are handled in code.
- Offline CLI scenarios cover asking, answering, escalating, refinement, and retrieval failure without API spending.
- README, architecture, development rules, and shared Codex/Claude project instructions describe the handoff boundaries for a four-person team.

Verified locally with Python 3.13: `uv sync --locked --group dev`, 140 passing tests, Ruff lint and formatting checks, and the offline refinement CLI. No paid requests were made. The tests cover contract validation, bounded retries/refinement, source references, stale revisions, invented facts, adapter failures, and all five demo scenarios.

The recorded milestone concerns local behavior with synthetic fixtures. Passing unit tests and demos do not establish real model quality, retrieval relevance, approval enforcement in storage, restart recovery, or duplicate-safe tool execution.

## 2026-10-07 — model gateway and cost accounting

- Implemented a single-send Metis adapter using the documented nonstreaming chat endpoint. Native JSON-schema support is not assumed; the core validates the returned decision.
- Added caller-owned run/case/revision/attempt context and terminal error handling without another paid retry.
- Added an atomic SQLite cost ledger: explicit initialization, reservations, known-usage settlement, held uncertain costs, duplicate request rejection, and persistent halting on accounting anomalies.
- Added offline gateway scenarios for success, format repair, timeout, and denied budget, plus ledger initialization/status commands.
- Verified locked dependencies, 295 passing tests, Ruff lint/format, and the installed gateway repair demo. All HTTP in these tests is simulated; paid API spending remains zero.

The user confirmed the full USD 5 was untouched. The local ignored runner ledger was initialized with a USD 4.50 ceiling and zero opening spend, leaving USD 0.50 outside the operational limit. At this milestone the API key was not yet configured and the live pilot was pending. Public rates and token reservations are operational estimates until account deductions are checked. There is no team-wide enforcement across independent laptop databases.

## 2026-10-07 — explicit user turns and first live pilot

- Added `ReportedFact`, `UserTurn`, and `CaseTransition`, plus a pure proposal helper for new facts, withdrawals and corrections. The candidate advances one revision and clears the old pending proposal without saving or executing anything.
- Preserved superseded fact attribution. New knowledge invalidates old evidence conclusions; actual corrections invalidate unscoped performed checks. Explicit environment switches also retire unconfirmed user facts from the old environment.
- Added a three-turn offline CLI demo and a tracker handoff guide: durable event deduplication before stale-revision checks, atomic compare-and-swap and approval invalidation, then an authoritative read before reasoning. These remain tracker requirements rather than implemented persistence.
- Verified locked dependencies, **354 passing tests**, Ruff lint/format and the installed turn demo. CI now also runs that demo. All automated tests remain offline.
- After the user saved the local key and authorized its use, ran exactly one bounded live Metis request on a synthetic case. HTTP 200 and usage reporting worked: 1,229 input and 174 output tokens, settled at a public-rate estimate of **USD 0.000317625**. No pending or uncertain reservation remained; available runner credit was USD 4.499682375.
- The live response failed core validation with `ModelOutputInvalid`; no retry was sent. Raw output was not retained, so the specific failed rule is unknown. Clarified the prompt's JSON-instance and decision-field instructions offline; this revision has not been retested live.

Connection and usage settlement are verified for that one request. Valid live decisions, retrieval/model quality and account billing reconciliation are still pending. The key, ledger and sanitized pilot receipt remain ignored local files. The original UI and `main` were not changed.

## 2026-10-07 — diagnosed response failure and shareable foundation

- Reproduced the original prompt's failure with sanitized diagnostics: valid JSON selected `ask` without the required `next_question`. The first discarded response's exact rule remains unknown; the controlled reproduction establishes this failure mode.
- Added strict output parsing, stable decision-rule error codes and allowlisted diagnostics. Duplicate keys, Markdown/prose, nonstandard constants and oversized responses fail closed; untrusted values and field paths are not logged.
- Added targeted feedback for the second attempt without changing the shared allowance. Model evidence/authority violations remain terminal. Ledger identity excludes feedback and preserves records from before this change.
- Verified live question and source-referenced answer outputs on synthetic cases. An injected malformed first decision was repaired by one live second attempt with diagnostic feedback. These checks are compatibility evidence, not real-model quality evaluation.
- Verified **430 passing offline tests**, Ruff lint/format and the installed demos. Independent review found no new response-handling blocker. Warmed Streamlit AppTest ran the unchanged original UI with zero exceptions; no UI backend integration is claimed.
- Added a runnable teammate integration guide and updated the development instructions. The shared foundation provides contracts, ports, mock adapters, bounded reasoning, correction handling and budget accounting; data/RAG, durable tracker and UI/evaluation remain their owners' work.

The local ledger records six settled live requests in total, with 7,673 input and 1,072 output tokens and a public-rate estimate of **USD 0.001973565**. It has no reserved/uncertain funds and is not halted. Account deductions are still unverified. Keys and receipts remain local and ignored.

## 2026-10-07 — decision guards and comparison candidates

Working branch: `feat/agent-core-integration`, after sharing the tested foundation on main through PR #1.

- Evidence observations can no longer propose a conflicting replacement for a confirmed user fact. Only user-provenance facts count as confirmed environment information or known answers to a missing-fact question.
- Retrieval queries pack whole confirmed facts and prioritize version/environment fields, so a long message or descriptive fact does not cut off the installed version. Source-derived versions cannot silently become query environment facts.
- Added three explicit prompt policies: current baseline, decision rubric, and rubric with caller-owned remaining analysis/retrieval capacity and query limit. Production still defaults to baseline pending comparison results.
- Workflow hints do not alter request identity or the two-attempt allowance. The second attempt receives its true remaining capacity, including after repair, refinement and short step limits.
- Verified **485 passing offline tests** and Ruff lint/format. The additional tests cover fact conflict guards, query packing, source authority, policy selection, context bypass revalidation and capacity boundaries.

No paid comparison request has been made at this milestone. Candidates are implemented choices rather than a demonstrated quality improvement. Source presence alone still cannot establish claim entailment; the planned comparison needs independent source-based review.

## 2026-10-07 — measured decision experiments and syntax checking

Branch remains `feat/agent-core-integration`; no changes from it have been merged to main.

- Registered fixed-source inputs and expectations before paid requests. Eight development probes include three real-report anchors, three correlated variants and two synthetic stresses; no formal held-out test was used. Sources and reviewer aids are inspectable in `experiments/decision_quality/`.
- Compared baseline, decision rubric and bounded rubric, then preregistered a follow-up explicit shape matrix against a fresh baseline. `structured_rules` produced 8/8 accepted proposals on its first attempts in the follow-up versus 7/8 accepted baseline proposals across ten attempts. This is a format-reliability observation, not general semantic superiority.
- Blinded source-based review of all proposals found repeated known questions, incorrect callback/API advice and inaccurate summaries. Public aggregates preserve the independent assistant's judgments and document source-audit disagreements; they are not human gold quality scores.
- Added bounded AST syntax checks for labeled Python fences without executing them. Malformed proposed code can use the remaining shared repair attempt; authority/evidence violations still stop immediately. Wrong arity, API parameters and inline/unlabeled code remain outside this guard.
- A targeted three-case 4o block completed with one actual refinement then escalation. A planned 4.1-mini block stopped on its first request with `ProviderModelMismatch`; no semantic response was accepted and no model ranking is justified.
- Verified **565 passing offline tests**, Ruff lint/format, locked dependencies, all four protocol validations and installed offline demos. CI validates registered inputs without requiring a key or making paid calls.

This work made 56 HTTP attempts across 44 observations: 55 settled requests at an estimated **USD 0.026699475**, plus **USD 0.008560640 held uncertain** for the serving-ID mismatch. Including the six earlier compatibility calls, the runner ledger contains USD 0.028673040 settled and USD 0.008560640 uncertain, with USD 4.462766320 available under its USD 4.50 ceiling. It is **halted** pending provider usage/billing evidence and verified serving identity/pricing. The ledger and reservation are preserved; no further paid request was made. Account deductions are unverified.

Default policy remains baseline; `METIS_PROMPT_POLICY=structured_rules` is an explicit development opt-in once live accounting can safely resume. See `docs/decision-quality.md` for methods, quantitative results, failures, limitations and specific future retrieval/state integration work. Keys, ledger, validated proposals and blinded review files remain private ignored runtime data.

## 2026-10-07 — paired sources, user reports and prompt comparison

- Added an audited, explicit user continuation for the verified 4o development
  route. The original global halt and USD 4.50 ceiling stay set; the unresolved
  4.1 request remains uncertain with a monotonically raised USD 0.02 allocation.
  An immutable USD 0.10 scope attributes each request and stops on new uncertainty,
  halt or overrun. There is no automatic refund, global unhalt or billing claim.
- Preregistered four paired cells across the same eight development probes:
  original inputs; exact-source enrichment; source enrichment plus attributed
  user reports; then identical normalized inputs with an extra diagnostic prompt.
  All source/fact/label boundaries and hashes were checked before paid execution.
- Ran 32 actual HTTP requests, all accepted on the first attempt. Estimated fresh
  cost was **USD 0.019914180**. Blinded source-based assistant review rated A/B/C/D
  acceptable on 4/5/6/5 of eight cases respectively. C matched all expected decisions,
  but still generated incorrect callback code. These are correlated development
  observations, not held-out quality scores or a demonstrated general winner.
- Found no observed benefit from the longer diagnostic prompt. Source enrichment
  alone did not fix its two changed probes; B's extra acceptable rating occurred
  with unchanged sources. Explicit symptoms/checks helped the reproduced mismatch
  escalation, while citations and syntax checks still missed stale callback values.
- Verified **651 offline tests**, Ruff, locked dependencies, protocol validation
  and installed demos. The new protocol is validated in CI without API calls.

The ledger now contains USD 0.048587220 settled estimates, USD 0.02 retained
uncertainty, zero pending reservations and USD 4.431412780 available under the
original ceiling. The explicit continuation has USD 0.080085820 remaining;
ordinary paid calls are still halted. Account deductions and the 4.1 identity
incident are not reconciled. The hold increase is not observed spending or a
verified cost bound. Default remains baseline; no extra production agent or
teammate-owned RAG/tracker implementation was added. See
`docs/decision-quality-v3.md` and its public aggregate for methods, findings and
source/state handoff recommendations. Work remains on the feature branch.

## 2026-10-07 — registered callback and question checks

- Added optional caller-owned, case/revision-bound question catalogs and explicit
  fresh-widget-value intent. Catalogs are manually curated input, not a free-text
  extractor. The new `grounded_rules` policy exposes them; five prior policy
  payloads remain unchanged when the new feedback is absent.
- Added optional bounded static checks for explicit API keywords and own-widget
  construction-time value capture using applicable pinned source metadata. An
  intentional previous-value snapshot stays valid without fresh-value intent.
  Questions are checked against registered structured targets and wording;
  unrestricted draft prose still needs whole-proposal review.
- Kept authority checks first and the shared two-attempt allowance unchanged.
  All changes are opt-in; production defaults, action permissions and tracker
  ownership stay unchanged. No source or user snippet is executed.
- Registered nine fresh synthetic development probes, including positive controls,
  with A/B/C separating the current shape policy, caller metadata plus prompt,
  and identical inputs with deterministic enforcement. Input/catalog hashes,
  rotated condition order and blinded-review procedure are frozen before outputs.
  These are related development scenarios, not formal held-out evaluation.
- Verified **820 passing offline tests**, Ruff lint/format, locked dependencies,
  six protocol validations and installed demos. CI validates the new protocol
  offline. All mock HTTP and test ledgers remain separate from the original runner.

No paid call was made for this implementation milestone. The planned comparison
has a USD 0.055 batch ceiling within the existing user-authorized continuation;
it cannot create a new grant, reset receipts or release the unresolved model
hold. The original ledger and previous accounting state are preserved. See
`docs/proposal-checks.md` for applicability, interface and coverage limits.

## 2026-10-07 — isolate proposal constraints at the reasoner boundary

Independent integration review reproduced an adapter-mutation bypass: the port
context shared the engine's enforcement catalog. Each attempt now receives deep
copies of proposal requirements and repair feedback. Replacing targets, mutating
a nested question, disabling fresh-value intent or changing feedback issues
cannot alter the private enforcement copy or retained diagnostics. Four new
offline regressions cover these paths. **824 tests** and Ruff pass; no paid
request was made before this correction.

## 2026-10-07 — fresh guard comparison results

Completed all 27 registered observations with 30 actual HTTP requests. Independent
blinded assistant review rated A/B/C acceptable on **5/8/4 of nine** respectively.
B's manual catalog plus prompt helped, while hard checking in C rejected questions
in two observations but failed to recover usable proposals. Citation omissions
also caused terminal failures. No live callback/API AST finding occurred, so this
run does not establish those guards' live benefit. Intentional old-value snapshots
and component-specific mismatch reports were preserved by all variants.

Fresh settled estimate was USD 0.024606450. The original ledger now records
USD 0.073193670 settled, USD 0.02 retained uncertainty, zero pending and
USD 4.406806330 available. The same continuation has USD 0.055479370 remaining;
global halt and unresolved accounting remain. No production default changed.
See `docs/decision-quality-v4.md` and the public aggregate for exact outcomes,
ratings, source-audit reservations and manual-catalog limitations. The next
focused hypothesis is to compile the same constraints into model-visible schema
and metadata, then separately register a repeat on exposed development inputs.

## 2026-10-07 — registered compiled-schema follow-up

Added a separate `compiled_rules` candidate that binds ask name/question pairs
and supplied answer citation IDs in model-visible JSON Schema and decision
metadata. All six earlier policies, including measured `grounded_rules`, remain
byte-identical and selectable. The gateway still sends prompted text and runtime
validation stays authoritative; native provider schema enforcement is not assumed.
Whole-draft consistency, source entailment and runtime correctness remain outside
these shape guarantees.

Registered V5 before outputs on the same **already exposed** nine synthetic
development probes. The unchanged A policy is a repeat control; B/C use compiled
schema with the same catalog, differing only in deterministic enforcement. Fixed
designs reject hybrid policies/flags. The USD 0.04 batch ceiling uses the existing
continuation and original ledger. A/B/C differences and V4/V5 changes remain
exploratory, not independent causal or held-out measurements. A separate blinded
procedure preserves ratings and source-audit reservations.

Verified **875 offline tests**, Ruff lint/format, seven registered protocol
validations and installed demos. No paid V5 request preceded this registration.
Frozen V4 inputs/protocol and gateway/ledger implementation remain unchanged.

## 2026-10-07 — compiled-schema repeat results

Completed all 27 V5 observations with one HTTP request each, no repair/refinement
or new accounting anomaly. All passed core validation, while independent blinded
review rated A/B/C acceptable on **8/5/6 of nine**. The unchanged A control improved
from V4, so improvements cannot all be attributed to new compilation. B/C still
invented a callback diagnosis for the fully specified frontend/backend mismatch;
both were rated unusable there. Known citation IDs and valid JSON did not prove
claim support. No live deterministic finding occurred in this repeat.

Keep the shorter `structured_rules` option for the first integrated development
pilot with human review, retain measured `grounded_rules` for curated-catalog
trials, and leave `compiled_rules` experimental. Production defaults remain
unchanged; no extra production agent was added or justified. RAG, tracker and
UI/evaluation continue under their own module boundaries.

V5 fresh estimate: USD 0.023519100; V4/V5 combined: 57 HTTP requests across
54 observations, USD 0.048125550. The original ledger now has USD 0.096712770
settled, zero pending, USD 0.02 retained uncertainty and USD 4.383287230 available.
The original continuation has USD 0.031960270 remaining, with global halt and
the unresolved incident preserved. Historical report snapshots stay unchanged.
**875 offline tests**, Ruff, seven protocol validations and installed demos pass.
See `docs/decision-quality-v5.md` and its aggregate for exact results and limits.

## 2026-10-07 — callback binding and full-proposal regression scope

- Added static compilation after bounded Python parsing. Duplicate parameters
  and invalid module-level control flow now use the existing syntax repair code,
  without executing code objects or exporting source-bearing compiler warnings.
- Extended optional proposal checks with `callback_arity_mismatch`, requiring
  pinned exact-version signatures and explicit callback argument documentation.
  Static binding preserves valid keys/defaults/variadics and abstains on ambiguous
  bindings, mutation or evaluation effects. Independent audit's 2,560 combinations
  agreed with Python's signature binder; no proposed snippet was executed.
- Added eight offline synthetic scenarios with 16 authored full proposals, exact
  frozen source/catalog copies, marked supplements and separate developer labels.
  All 16 detector scope expectations matched; seven positive controls passed,
  one isolated arity defect was rejected and eight deliberately negative proposals
  remained accepted. The original larger callback fence and prose-only failure
  are retained as explicit coverage limits. No live semantic gain is claimed.
- CI now replays this pack through fake ports. Canonical hashed identities,
  input hashes, copy validation and allowlisted diagnostics preserve boundaries.
  No key, original ledger, paid request, teammate adapter or prompt default was
  changed. See `docs/decision-quality-v6.md` for the reproducible result and limits.

Verified locked dependencies, **1,027 offline tests**, Ruff lint/format, all seven
existing protocol validations, the new authored-proposal replay and three
installed demos. Existing policy message digests and request identities pass;
all HTTP/ledgers in tests are simulated or temporary. No paid request was made.

## 2026-10-08 — registered whole-proposal fidelity comparison

Added an optional `fidelity_rules` candidate over the unchanged shorter
`structured_rules` policy. It combines a concise instruction with an exact index
of current/superseded user facts, evidence observations, reported checks, unknowns
and source scopes. The index infers no facts, claim support or action authority.
All seven previous policies remain byte-identical, including repair feedback;
production defaults and optional-check settings remain unchanged.

Registered six fresh synthetic caller inputs over unchanged exposed V4 sources,
two draws per policy and an explicit rotating 24-observation schedule. Both arms
use the same model, sources, limits and uncatalogued user intent. Frozen suite,
content and schedule hashes plus a blinded full-proposal review procedure precede
HTTP requests. This evaluates the bundled candidate on related development
inputs; it cannot separate the index/instruction effects or establish held-out
accuracy, real RAG quality or a general winner.

The new runner preserves the original ledger, unresolved USD 0.02 hold and
unchanged continuation. Its USD 0.030 comparison ceiling is within the remaining
authorization; conservative request reservations may stop the batch early.
Before the new trial, settled estimates remain USD 0.096712770, pending zero,
and continuation remaining USD 0.031960270. Partial comparisons are recorded
without replenishing authorization or replacing receipts. No paid request
preceded this registration. See the V7 input README, protocol and review plan in
`experiments/decision_quality/`.

Verified locked dependencies, **1,149 offline tests**, Ruff lint/format, all
eight protocol validations, unchanged authored semantic replay and installed
refinement, gateway-repair and turn demos. Candidate compatibility/provenance and
runner accounting tests use fake ports, intercepted HTTP and temporary ledgers.
An independent review also confirmed exact source copies and 63 unchanged-policy
message comparisons. These are encoding/compatibility checks, not live fidelity
results.

## 2026-10-08 — whole-proposal fidelity results

The registered V7 batch recorded 21 of 24 planned observations and 25 settled
HTTP requests, yielding 19 accepted finals. The USD 0.030 trial cap denied the
historical candidate's second call; three scheduled repeats never started.
The first draw covered all six families and four families completed both draws.
One control answer was terminally rejected for missing evidence; one candidate
JSON repair succeeded within the existing allowance. Partial draws were not
refilled and the original uncertainty, halt and authorization remain unchanged.

Three fresh blinded assistant reviewers rated the nine pairs with both finals
acceptable on **3/9 control versus 5/9 candidate**. Across the four fully repeated
families this narrows to **3/8 versus 4/8**. Citation-support passes tie at 6/9;
both pass check attribution on 9/9. The candidate helps the corrected form API
case but still produces summary drift, unsupported release recency, a redundant
callback question and one misattributed timing claim. Original ratings remain
preserved; unblinded root source audit made no category changes.

Keep the new bundled instruction/index experimental, the shorter policy for the
first integrated pilot, and production defaults unchanged. No general winner,
held-out gain, real RAG measurement or extra production agent is established.
The fresh estimated cost is USD 0.024175635; original settled estimates are now
USD 0.120888405 with zero pending and the old USD 0.02 uncertainty retained.
Continuation remaining is USD 0.007784635; provider deductions are unreconciled.
The 1,149-test preregistration build passed GitHub CI at `1ef5c35`, run
`37746599205`. See `docs/decision-quality-v7.md` and the sanitized V7 aggregate.

## 2026-10-09 — controlled real-Issue source scope and reply intake

Continued on the clean `feat/agent-core-integration` checkout at `dad3202` after
reading the repository rules, original brief and mentor roadmap. The original
**1,149 offline tests** passed before changes. No existing work was replaced and
no merge/push to main was performed.

- Registered six correlated development projections of real Issue #12782,
  including complete mechanism evidence, ablation, unknown/mixed versions,
  correction, synthetic same-version conflict and retired refinement citations.
  Frozen inputs, inventories, answerable user gaps versus document gaps, full
  authored proposals, source spans, labels and hashes were committed at
  `8814fbb` before scenario execution. Body-workaround/comment-informed selection
  is disclosed; no answer/outcome text enters primary evidence. Added confirmed
  duplicate #12629 to the quarantine declaration; actual RAG index enforcement
  remains a data/evaluation integration requirement.
- Added opt-in exact active-user-version filtering after retrieval validation.
  Unknown versions drop explicitly scoped chunks, while unscoped metadata stays
  unknown and available. No patch/range equivalence is inferred. Default `all`
  and all model prompt policies/ports/shared contracts are unchanged.
- Added pure canonical-question reply intake. Whole release-number replies gain
  user attribution only for the correct case/revision/authenticated pending
  question and exact registered question/display text. Independent review found
  and closed target/wording drift that could otherwise turn a Python answer into
  a Streamlit fact. Ambiguous or mixed input needs explicit structured facts.
  Tracker replay guidance now distinguishes original and prepared event hashes.
- Replayed the same 14 authored sequences under both scopes: negative acceptance
  **6/7 → 4/7**, positive retention **7/7 → 6/7**. The strict candidate deliberately
  loses a safe historical comparison. Four unsupported semantic proposals remain
  accepted. All registered outcomes match; this includes registered failures and
  is not a semantic accuracy score. The actual old Git code was separately
  extracted/imported without changing the checkout; all 14 baseline results and
  reasoner source-ID pools match the current default exactly.
- Two canonical version replies convert versus zero with bare turns. All **32
  intake condition checks** and the version-correction transition match the
  frozen expectations. The helper/traces perform no tracker actions. Novel
  check-only turns do not retire every inference; results must be represented as
  explicit facts/corrections. This is the historical V8 limitation, superseded by
  the check-result invalidation milestone below. Source/whole-proposal review
  remains necessary.

Codex authored the fixture proposals/labels and an independent assistant audited
them against sources. No project model decided these proposals; no human gold,
real RAG quality, solved Issue or held-out success is claimed. The two capability
commits are `bb947db` and `de4d2ca`. The deterministic runner, original-code replay
script and inspectable JSON receipts are checked in; CI adds the new offline
validation/replay commands. The single-agent foundation remains sufficient for
these changes; no framework or extra production agent is justified.

Verified locked dependencies, **1,245 offline tests**, Ruff lint/format, all eight
prior registered protocol validations, the existing semantic replay, new
controlled validation/replay, original-code baseline reproduction and installed
refinement/gateway-repair/turn demos. New source/intake/runner regressions cover
current versus superseded provenance, latest bundles, code bypass revalidation,
question/display binding, attribution, stale events and scorer failure handling.
GitHub CI for these new local commits has not been run; no remote result is
claimed.

Fresh API cost is **USD 0**; the key/environment file was not loaded or printed.
The existing ledger was read without changing it: USD 4.50 operational limit,
USD 0.120888405 settled estimates, zero pending, USD 0.02 uncertainty,
USD 4.359111595 available, and `halted=true`. The uncertainty is one unresolved
`ProviderModelMismatch`; the existing continuation has USD 0.007784635 left.
Provider identity/usage/billing evidence is still missing, so no paid run,
unhalt, refund or new continuation was attempted. See the
[Persian controlled-core report](controlled-core-v8.fa.md) for results, limits,
reproduction and exact RAG/tracker/UI handoff requirements.

## 2026-10-09 — retire prior inferences after new reported checks

Reproduced the check-only gap before changing the helper: a newly reported failed
cache workaround retained an active evidence diagnosis and its source reference.
Four targeted negative regressions failed while two normalized-restatement
positive controls passed. After the change, all six pass and the same cache
report retires the diagnosis, marks it unknown and clears prior evidence refs.
Active user facts and old/new check history remain; superseded inference
attribution, revision advancement and pending-proposal invalidation are preserved.

Novelty uses the existing whitespace-collapse/casefold normalization. Repeating
an equivalent check preserves conclusions. Because there is no dependency graph,
any new check description conservatively retires all active evidence-derived
facts and refs, including potentially unrelated conclusions; this is not semantic
check matching or verification that a reported result is true. Free-text-only
observations still require explicit structured checks/facts. The tracker remains
responsible for immutable event deduplication, atomic commit and approval removal.

Verified **64 focused turn tests**, scoped Ruff lint/format and the installed
offline turn demo. The prior V8 controlled-case measurements remain unchanged;
these regressions demonstrate state invalidation behavior, not model quality,
real RAG performance or held-out success. No paid request, key access or tracker
write was made for this change. See [user turns](user-turns.md) for the current
input rules and handoff behavior.

## 2026-10-09 — source-bound plans and complete review records

Continued from `e90f2d9` on `feat/agent-core-integration`, preserving the earlier
controlled work. Preregistered V9 at `56ec12a` before replay: six identical V8
material cases, fourteen original proposals, seven positive plan mappings and 31
structured probes. Extra caller-curated user/source gaps and declared conflicts
are explicit candidate inputs, not model-discovered labels. The production
single-agent structure/defaults remain unchanged.

Added optional `GroundedPlanner`/`GroundedReasoner` with complete context/source
hash binding and deterministic whole-quote rendering. It removes unrestricted
model prose, citation claims, fact updates, check suggestions and quote-substring
selection from this path. Active reports remain attributed; version scopes remain
exact metadata/historical/unconfirmed. Source/context integrity failures stop
terminally; malformed plans use only the existing remaining attempt. The new
`MetisGroundedPlanner` reuses the same single-send gateway, ledger and duplicate
request identity; all eight prior analysis prompt policies stay unchanged.

Added pure whole-proposal review packets/attestations. Complete output surfaces,
case and latest bundle are bound, with six required review dimensions and optional
exact source/output spans or active-user-fact references. Authentication and
action approval remain tracker-owned. Tests deliberately show that an incorrect
authenticated semantic judgment can mechanically pass. Hashes/record completeness
do not prove truth, entailment, claim coverage or reviewer authentication.

The current-default V9 replay reproduces **6/7 negative acceptance, 7/7 positives**;
the new representation retains **all seven mapped positive intents**, including
the safe historical comparison lost by strict V8 filtering. All **31 registered
probe expectations** match, including accepted unclassified false-source and
undeclared-conflict controls. Fourteen old payloads are all rejected as schema
mismatches, including valid positives; this is not semantic detection. The actual
`e90f2d9` code was separately archived/imported in a temporary directory; all
fourteen outcomes/source pools match, without checkout changes. Original V8 Git
baseline reproduction remains byte-identical.

Independent scorer review reproduced a false positive when removing the key
release source and its citation while retaining another source. Corrected scoring
derives mandatory sources from the final plan plus conflict groups, checks exact
citation sets and complete quotations in both answer and summary, and binds all
rendered fields. Unexpected adapter crashes no longer count as successful guard
rejections. Those checks are output integrity, not a semantic judge. Initial
receipts are preserved under ignored runtime paths; the final checked-in receipt
exactly reproduces source fingerprint
`1004f837a9b5dae02bc23cfd8688ea9037ffd937e394e2b07d9ce169a44094da`.
Public hashing/packet helpers now sanitize encoding/constructed-input failures;
review inventories retain valid long escaped fact records without truncation.

Verified locked dependencies, **1,414 offline tests** (169 more than V8), Ruff
lint/format, eight earlier protocol validations, semantic and V8 replays, V9
validation/replay, both actual Git baselines, saved-receipt equality, all three
required demos, runnable integration example and local documentation links.
CI includes V9 offline commands; no remote run is claimed. New project API cost
is **USD 0**, with no environment-key read, tracker writes or ledger mutation.
Original ledger remains halted with USD 0.02 unresolved model mismatch and
USD 0.120888405 settled estimates; billing/identity reconciliation is still absent.

See [Persian upgrade rationale/results](controlled-core-v9.fa.md) and
[extractive contracts and handoffs](extractive-core.md). Actual RAG provenance and
family exclusion, authenticated tracker review/approval/replay, complete UI
display and unexposed real-model evaluation remain integration work. No new
production agent/framework, merge to main or push was performed.

## 2026-10-10 — shared core integration release

With Sasan's explicit authorization, PR #7 was merged normally into main as
`85b6027254bfa3f02a720101673626265817a560`. All fourteen V8/V9 feature commits
remain reachable, with the authored receipts and original Git baseline histories
preserved. Release review found additive contracts compatible with the current
UI/API; GroundedPlan, evidence scope and proposal checks remain opt-in/default
unchanged.

Exact feature-head CI passed 1,414 tests at `8cf56d8` (run `38033908496`);
the PR merge CI passed 1,428 tests including existing UI/API tests (run
`38033931700`). Both also passed style checks, registered offline replays and
demos. These are compatibility and controlled development evidence, not real
retrieval or held-out quality measurements.

The UI/API still uses scripted retrieval/reasoning and memory case storage.
Structured user-fact intake, durable tracker approval/replay/restart, real
retrieval and real-model evaluation remain the named owners' integration work.
No paid request, environment-key read, ledger reset or uncertainty release was
performed for this release. The ordinary live halt remains unresolved.

## 2026-10-10 — structured HTTP ingress and approved-question pilot (C2 / P2)

Branch: `feat/user-intake-pilot`, starting from shared `main` at `5af98e6`.

- Recorded four HTTP ingress regressions before implementation at `cf2281e`.
  They all failed on the baseline, which silently ignored fact/revision/event
  fields. A separate isolated Git-archive recheck also failed the same four
  regressions; the new adapter passes all four. The replay assertion adjustment
  is disclosed in `experiments/user_intake/baseline-recheck.json`.
- Registered a seven-turn exposed development fixture at `a3d5eeb` before replay.
  Its #12782 anchor is answer-informed; continuations/reasoner decisions are
  authored, with five unchanged official V8 source hits. #12782/#12629 remain
  excluded from independent test/RAG usage; this runner does not modify an index.
- API ingress now maps explicit facts/checks/unknowns/environment changes into
  the existing pure transition. Stable client IDs and strict expected revisions
  are required for structured updates. Original envelope hashes include the
  reply binding/scenario and are looked up before stale/preparation checks.
  Replay returns current state plus the original receipt without another run.
- Added `ApprovedReplyQuestion` and a pure helper for a canonical version reply
  after local question approval clears the pending ID. No fabricated pending
  state, client approval flag or arbitrary question wording can authorize it.
  Edited/noncanonical/ambiguous/stale/other-case replies are guarded. All legacy
  event IDs are UUIDs and reserved against later reuse; review input is strict
  and validation diagnostics never echo raw values.
- The actual HTTP replay captured current CaseState and exact source bundle at
  each port: seven accepted turns, seven reasoning/retrieval calls, three explicit
  evidence-history seeds, two whole-source quote checks and three separately
  approved releases. Correction, withdrawal, environment changes, novel/repeated
  checks, stale approval and event/action retries matched registered assertions.
  Mutation tests detect retained stale inference and unsupported claims even
  when the citation ID exists. Agreement is not a semantic model quality score.
- The receipt fingerprints 14 source/dependency-lock files, runtime versions,
  fixture and inputs. It refuses success if code changes during execution or
  Python disables assertions. Existing V9 receipt bytes/code identity remain
  frozen; all current behavioral observations match it, with only current code
  fingerprint differing after the additive contract.

Verified locked dependencies, **1,529 passing offline tests** (101 added), Ruff
lint/format and all 16 prior CI validation/replay/demo commands. The new pilot is
also in CI. One existing Starlette/httpx deprecation warning remains. Independent
reviews found no remaining API/helper/runner blocker.

No paid call, key read or ledger mutation occurred; cost is zero. The API still
uses process memory, scripted ports and unauthenticated local review. Durable
CAS/event outcomes, reviewer authentication, restart recovery and real UI input
controls remain T1–T3/U2. P2's offline adapter is complete; C2 remains open for
those integrations. RAG/model/final-test quality and an actual app fix are
unmeasured. See [the Persian result and precise owner handoff](user-intake-pilot.fa.md)
and [wire/reply semantics](user-turns.md).

## 2026-10-10 — complete review handoffs and current-state fixture (C3)

Branch: `feat/core-review-handoff`, from the PR #10 merge `3f22ef9`.
Published for review in [PR #11](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/11).

- Registered four HTTP review-boundary regressions before changing the API.
  An isolated import of the actual baseline source reproduced four failures;
  the same tests now pass. In particular, an unused prepared bundle could
  overwrite a consumed citation sharing its chunk ID. Review now projects only
  the engine's final consumed, normalized/filtered bundle and warnings.
- Added `ProposalHandoff`, all-source content hashes/version scope and a
  transparent per-invocation `ReasoningCapture`. The handoff retains the complete
  case, message, analysis, reasoning context, sources and optional actual final
  `GroundedRequest` catalog. Whole-case drift at the same revision, source/output
  tampering and stale proposal IDs stop local approval. Human edits rebind a new
  proposal and review packet without another model request.
- Preregistered a four-turn current-state/correction/withdrawal fixture using
  the same five pinned official V8 excerpts. Actual offline HTTP ports observe
  five reasoning/retrieval calls, two separate approved releases and four event
  replays without additional calls. The corrected 1.49.1 lacks exact metadata
  coverage; authored retrieval refinement removes the prior release record and
  ends in escalation. A separate declared-conflict control checks bounded
  routing, not an actual contradiction between the documents.
- Independent audit found that shared-renderer expected output could retain
  exact quotes while appending unsupported cause/fix prose. Preserved the v1
  receipt and its source in `2680151`; then inspected all five analyses and
  registered a fixed output oracle in `057a4d3`. Whole-output checks now catch
  both that mutation and wrong user facts from a shared rendering helper. This
  oracle is explicitly post-first-replay audit hardening, not preregistered
  semantic gold or a general entailment judge. The final v2 receipt is separate.
- Verified locked dependencies, **1,621 passing offline tests** (92 added),
  Ruff lint/format and all 18 CI validation/replay/demo commands. Re-ran the
  full suite and final replay after oracle hardening. One existing
  Starlette/httpx deprecation warning remains; independent final review found
  no remaining actionable blocker.

No paid request, key read or ledger mutation occurred. This closes the core's C3
fixture/contract task, while C2/U2 and durable authenticated T1–T3 integration,
real RAG/model quality, C4's connected baseline and C5 accounting reconciliation
remain open. No teammate-owned production adapter or extra agent framework was
implemented. See [the precise results and owner handoffs](review-handoff-pilot.fa.md)
and the [integration contract](integration.md#complete-proposal-handoff-c3).

## 2026-10-10 — readiness audit and intercepted gateway composition

Follow-up on C3 in the same [PR #11](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/11).

- Preregistered two additional regressions in `d14cfc4`: valid outer whitespace
  broke the frozen handoff; adapter construction failure returned HTTP500 after
  accepting the event. Identical initial test bytes fail twice against archived
  `254e6542` and pass twice after `68dec4f`. The handoff keeps the exact raw
  message while matching existing GroundedRequest normalization. Setup failures
  export a sanitized terminal code, retain the event receipt and cannot release
  a stale proposal after correction. A third, post-baseline test covers that
  correction/approval path. Independent review found no actionable issue.
- Preregistered the gateway composition protocol in `d9c8e82`. The existing
  MetisGroundedPlanner/MetisReasoner now joins the same C3 HTTP/core/review replay
  through mandatory MockTransport, synthetic credentials and temporary ledgers.
  Seven primary sends settle mocked usage; four event replays add none. Separate
  controls check two-attempt malformed-plan repair and single-send terminal
  mismatch/timeout with retained uncertainty. Oracle/labels/auth headers do not
  enter provider messages or recorded bodies. All clients close, state restores,
  and wire mutations/code drift/disabled assertions/receipt overwrite fail.
- Preserved C3 v1/v2 receipts and wrote v3 after the production fixes; the
  fixture and posthoc C3 oracle are unchanged. The gateway has its own v1
  receipt with full wire/context/accounting fingerprints. A first harness run
  failed on string versus Decimal config; runner conversion was corrected,
  not the protocol. This is reported, not hidden as a successful first run.
- Verified locked dependencies, **1,634 passing offline tests** (105 over main;
  13 added in this audit), Ruff lint/format and all 19 offline CI commands.
  Independent gateway review passed its 10 focused tests with no actionable
  issue. One existing Starlette/httpx warning remains.
- Updated the plan with explicit 2026-10-10 requested pilot deliveries for RAG,
  tracker and UI/evaluation, including branch/PR, runnable evidence and a
  blocker/delegation fallback. This is the coordinator's request, not a claim
  teammates agreed or completed their tasks.

Actual paid requests and spending remain zero; mocked primary settlement of
USD 0.000490875 is not provider billing. The real key/ledger were not accessed or
modified. Core is ready for the fixture handoff; this does not prove production
RAG/model quality, durable authenticated approval, connected UI or held-out
evaluation. C4 requires teammates' actual adapters; C5 still needs external
identity/usage/billing evidence, not a guessed alias or cleared uncertainty.
See [the readiness evidence and remaining handoff](core-readiness-audit.fa.md).

## 2026-10-10 — C3 shared release on main

With the user's explicit authorization, completed final production, experiment
integrity and owner-handoff review of PR #11. Fixed stale setup-error and local
UI approval guidance, and added the exact shared fixture/replay/contract links to
the plan. No remaining actionable release blocker was found.

Merged with a normal merge commit
`edea31c6b511520ffcb78b6b5c6fc565b2266265`, preserving preregistration history.
Both final-head checks passed at `c96720c`; the
[main release CI](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38045540320)
also passed at the merge commit. Final verification includes 1,634 offline tests,
Ruff, locked dependencies, all 19 CI commands and unchanged receipt/source
fingerprints. Production code did not change during the final documentation fixes.

The plan now directs teammates to sync their feature branches from origin/main
and identifies the four-turn C3 fixture for today's requested pilot deliveries.
P3/P4/U2, durable authenticated tracker behavior, real RAG/model quality, C4/C5
and held-out evaluation remain open. No team message, paid call or real key/ledger
access occurred. This is a shared fixture integration release, not a final quality
or end-to-end production success claim.

## 2026-10-11 — team adapter and evaluation review

Reviewed current main `6131091` (1,674 passing tests) and the standalone SQLite
tracker PR #19 at `faedfc14`. UI/runner PRs #13–#18 were already merged, while
retrieval/reasoning remain scripted and FastAPI still uses process memory.

The runner now selects the actual case's adapter, gives new live experiments
fresh model request identities, preserves full original/edited handoffs and
released responses, and joins observed reasoning attempts to their exact
ledger records, including stopped attempts. Settlement, reserved/uncertain
amounts and unknown usage are distinct. A mandatory ledger preflight respects
halt/availability and the USD 5 cap; public config is allowlisted. Live mode
alone no longer claims quality. Fixed-path follow-ups stop as fixture coverage
when they do not match the approved question. Rejected UI form inputs are
cleared on case switching. Existing fixtures and receipts are unchanged.

The tracker read snapshot fix is published separately in
[PR #20](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/20), targeting
the tracker branch. Its deterministic concurrency regression fails on the
original tracker and passes after the fix. The existing four-turn #12782 dev
fixture also passes when core handoffs are composed with actual SQLite across
correction, refinement, edit/approval, restart/replay and withdrawal/rejection.
All 16 tracker tests and the synced branch's 1,690-test suite pass. This does not
connect API/UI to SQLite.

On the runner/UI review branch, all 1,694 tests and Ruff pass, including 20 new
tests. Nine targeted regressions fail on actual archived main `6131091` and pass
after the fixes; the last UI fix preserves all claims linked to the same chunk.
[Review evidence and remaining boundaries](team-integration-review-2026-10-11.fa.md)
and the [E2 rubric recommendation](evaluation-rubric.md) explain the handoff.
E2 scoring/conditional branches, frozen split/corpus checks, tracker/API recovery,
real RAG and C5 remain open. Reasoner-only usage attribution excludes retrieval,
embedding and adapter setup; provider billing is not reconciled by these tests.
No paid requests, real key/ledger access or team messages occurred.

## Next integration work

### Shared release — 2026-10-07

PR #2 was reviewed and merged with a normal merge commit
`bc7f1939a9eb575d46d1f517accc80b642593ced`. The registered experiment commits
remain reachable. Main now contains the tested core, guarded user facts, bounded
query packing, source/syntax validation, optional proposal checks, continuation
accounting, frozen development evidence and integration documentation. Production
defaults remain `baseline` and `proposal_checks=False`; this does not turn on live
requests or connect teammate-owned production adapters.

Both exact-head PR checks passed; main's offline CI run `37690357252` also passed
at that merge commit. Independent release review ran 174 focused authority,
engine, schema and continuation tests successfully. Feature development continues
on `feat/agent-core-integration`; previous milestones describe their historical
branch and accounting state rather than the current release.

| Work | Owner | Completion evidence |
| --- | --- | --- |
| Real retrieval adapter and frozen corpus | Data/RAG | Inspectable sources, metadata, and dev retrieval measurements |
| Live billing reconciliation and real-case evaluation | Agent core + evaluation | Synthetic question/answer/repair compatibility now verified; still need account deduction comparison and held-out quality/cost measurements |
| Durable tracker and safe execution | Tracker/tools | Persisted state, restart, reject/edit/stale approval, and retry tests |
| Backend connection and evaluation cases | UI/evaluation | Live local flow and 15 dev + 15 test with required multi-turn cases |
| Baseline versus final measurements | Whole team | Same cases, quality/cost/latency results, and failure analysis |
| Systematic Adversarial Testing | Proposed core bonus, mentor agreement | Defined challenge set plus measured before/after improvement |

Local tracker reset instructions will be added with its actual implementation. There is no persistent tracker to reset in the current core demo.
