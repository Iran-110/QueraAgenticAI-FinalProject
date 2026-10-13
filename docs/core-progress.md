# Agent-core progress

This is a factual milestone log, not a daily activity schedule. Update it after a verified change; keep real dates and real limitations.

## 2026-10-13 — PR35, reproducible docs-only index acceptance

PR35 initially adds one unchanged reference-fixture receipt at `e37a57a`:
132/132, not the Chroma adapter or a built index. Recorded Python hashes match
`56ff8ff`; its historical dirty flag is preserved. Two fresh builds on clean
`e37a57a` produce the registered 14-source/30-chunk manifest and identical
snapshot. Correct mapper conformance independently passes 132/132 with injected
fixed collections. [Layered evidence and commands](../experiments/retrieval_acceptance/pr35/README.md)
keep these scopes distinct.

The companion replay explicitly consumes two supplied existing indexes, checks
actual query/filter forwarding and exact returned material, and exercises the
existing GroundedPlan mock gateway, HTTP and SQLite. Eleven tests reject corrupted
URLs, substituted physical queries hidden by echoes, ignored filters, missing
indexes and reused output. Matching but unregistered rebuilt snapshots are rejected
before querying or HTTP; protocol bytes are pinned in both release identities.
Source contracts, RAG implementation and tracker
are unchanged. Another three Git tests preserve actual seed bytes across
autocrlf settings. The no-attributes control reproduces 56 converted newlines
and a checksum failure; the seed-only byte policy fixes future checkout.
The full working-tree suite passes **2,295 tests**, Ruff passes, and 129 existing
focused tests cover actual index, page and fresh-interpreter restart.

No semantic relevance/model-quality claim is made. Split remains one dev/zero
test, draft and not family-reviewed; R1 final corpus, R2/R4, E1/E2 and C5 remain
open. No provider, paid embedding, key read or production ledger change occurs.
Publication, source-pinned replay and CI are recorded in the PR35 evidence
packet; the original author's receipt remains byte-for-byte unchanged.

## 2026-10-13 — GroundedPlan through the durable pilot (C2f)

The existing restricted plan and gateway now compose explicitly with persistent
HTTP, the real Streamlit page and the existing SQLite tracker. Shared contracts,
ports and Hassan's RAG adapter are unchanged. Default routing remains scripted;
`AGENT_PILOT_REASONING=grounded_fake_gateway` opts into a mandatory mock provider
with an independent temporary ledger. The ordinary launcher rejects live mode.

Preregistration `2830ba4`, amended before execution at `c6c7573`, pins the original
HTTP and service at `3c92b12`. Same authored plans, source excerpts and four turns:
baseline **10/12**, new **12/12**. Only truthful reasoning labels and per-run client
cleanup improve these operational controls; baseline already supported injection.
Complete prior analysis/quote oracles reject fabricated prose and altered wire
messages, but are exposed assistant-authored controls, not independent human gold.

Cleanup executes after final request capture and before staging, including setup,
run, handoff and cancellation failures. A cleanup error persists the safe
`AdapterCleanupFailed` code and creates no new proposal. The legacy memory seam
also respects the callback. The runnable binding releases closed resources;
selecting one complete excerpt keeps the authored mock policy within renderer
limits. Actual AppTest and two fresh TCP interpreters verify correction, original
approval retry, old approval refusal and no duplicate action with actual Chroma.

Clean source `0b962de` passed **2,280 tests**, locked sync and Ruff. Its separate
[registered live probe](../experiments/grounded_http_acceptance/live-protocol-v1.json)
used the original immutable development continuation: **one actual API request**,
3,654 input and 72 output tokens, **$0.000650430 estimated cost**, **14/14 operational
checks**. The model selected the necessary installed-version question without
reasking known facts or claiming an established cause/fix. The proposal remains
pending; no local action was authorized. [Unmodified receipt](../experiments/grounded_http_acceptance/live-result-0b962de.json)
and [separate whole-proposal review](../experiments/grounded_http_acceptance/live-review-0b962de.json)
record both scope and limitations.

The original receipt failed to retain the exact serving model ID. An offline
compressed-envelope test reproduced the observer limitation; the existing gateway
still validated decoded identity before settlement. Do not reconstruct that ID
or retroactively upgrade the receipt. The original halt/quarantined request and
$0.02 hold are preserved; actual account charges remain unknown. One exposed
development turn with fixed excerpts does not establish RAG/model quality,
comparative decision improvement, held-out evaluation or C5 reconciliation.

Clean `3e4617f` reproduced the 10/12 versus 12/12 comparison, core/SQLite
49/49, HTTP/SQLite 457/457 and actual adapter 132/132. Full tests at final runtime
`89a0aec` pass **2,283/2,283**; Ruff passes. [Pinned verification and receipts](../experiments/grounded_http_acceptance/verification-89a0aec.json)
separate each source revision and test scope.

The native browser smoke found a real UI defect missed by earlier page-only
tests: changing a case status changed its formatted selectbox label. Streamlit
could deserialize the former label as a case value, reset form state and fail
approval/version reply. The widget ID itself stayed stable. Stable serialized
case IDs fix this without weakening review validation. A regression runs actual
`app.py` navigation. The repeated browser flow approves on the first click,
accepts a short version reply and correction, and ends at revision3 in the same
case with one local action. [Browser receipt and screenshot](../experiments/grounded_http_acceptance/browser-receipt-89a0aec.json)
record this assistant-operated local smoke. Complete UI-session recovery,
production authentication, final corpus/split and independent quality scoring
remain open.

## 2026-10-13 — connected offline UI/index pilot (U3a/P4a/C2e)

PR30 is published on main at `6e719e9`; PR31's exact reviewed Windows worker
fix (`a550bf1`) is published at `877601c`. Its
[main CI](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38314737701)
passed. The current integration contains both releases and preserves the
existing core contracts, RAG adapter and sole SQLite tracker.

After independent exact-head review, PR32 published this integration on main at
`2ce25ab004a8381f59cabb5b64b99a93472f768e`. Its tree equals reviewed `6a063a1`.
Both Linux and Windows jobs passed in the [branch run](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38316532488)
and [combined PR run](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38316540401).
Windows accepted 37 connected-pilot tests and the separate 457-check HTTP run.
These are operational checks, not model-quality or browser evaluation.

On clean `c14314f`, **2,218 pytest tests** pass. The preregistered UI review
comparison improves the same six operational checks from **2/6 to 6/6**:
stable authenticated approval, immutable lost-ACK retry, original receipt after
backend recreation, correction and one local action. Draft/source display is
bound to the canonical approved handoff. Backend protocol is rediscovered before
POST; an unavailable or incompatible backend cannot change the pending request.
The active business case survives Streamlit widget cleanup on failed health.

The bounded builder opens actual Chroma with explicit local lexical vectors:
**14 approved docs/API sources, 30 lossless raw chunks**, no Issues/comments or
release notes. Content, version identities, spans, source hashes and manifest
are verified, including returned query rows. The actual unchanged adapter passes
seven membership/version/limit probes. Raw index text is lossless; the existing
EvidenceHit contract trims boundary whitespace in 14 of 30 excerpts. The seed
profile validates 14 packaged file hashes and reports candidate family links;
it does not establish semantic extraction quality or final duplicate exclusions.

Actual TCP tests use two fresh server interpreters with the same database and
index; Streamlit AppTest runs the page against the connected ASGI backend. The
separate fixed-evidence HTTP protocol remains **457/457**, core/SQLite **49/49**,
and real adapter with injected collections **132/132**. All three demos pass.
[Pinned receipts](../experiments/ui_review_acceptance/verification-c14314f.json)
and [commands, scopes and limitations](offline-ui-index-pilot.fa.md) are public.
CI now includes a Windows connected-pilot job; only its actual green result can
establish that platform's acceptance.

The first PR Windows page run reached AppTest's default three-second completion
timeout, while the same branch run passed. The real-index page test now has a
bounded 15-second test-run allowance; assertions, network block, application
timeouts and all acceptance inputs are unchanged. This is not a latency result.
The next Windows PR run passed the page but reported an unconfirmed TCP delivery
during correction. That test client allowed only two seconds per request; its
read budget now matches the actual UI's ten seconds (connection remains two).
No automatic retry or weaker state/action assertion was introduced.

This is a private local maintainer console and a scripted ask/escalate pilot,
not real model/RAG quality. Browser authentication and recovery after complete
UI-session loss remain product work. E1/E2 split/rubric, R2/R4 final corpus/dev
retrieval, C4/E4/E5 model evaluation and C5 billing reconciliation remain open.
No provider, paid embedding, .env key or production ledger was used; API cost
is zero and the existing halt is preserved. No team message was sent.

## 2026-10-12 — PR29 release and persistent HTTP composition (C2d)

After final exact-head review and 63 focused checks, PR29 merged to main at
`cddef782726e7d92c8f3d85eeae5933f563e4246`. Its merge tree exactly equals reviewed
`8befb3f`; [main CI](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38238938038)
passed. No external/team message was sent.

The separate `feat/http-sqlite-integration` branch now provides an opt-in
`persistent_api.create_app` using the existing SQLite tracker and CoreTurnService.
One SQLite read snapshot supplies the HTTP view. Ingress and an explicit unknown
outcome marker commit together; stage and measured RunResult commit together;
review authenticates configured bearer credentials and binds a stable client
review ID to exact proposal/revision/hash. Only the existing transaction writes
local actions. The one-root-proposal-per-revision gate closes the former final
same-revision ABA path; fresh reasoning after a closed revision needs a new turn.
No automatic resume or second storage backend was added.

Protocol v2 was registered at `6f0e8b5` before execution. Clean `b7107c0` passes
**457/457 checks** (342 same-process,115 restart), with all five fresh-interpreter
checkpoints preserving state and original event/review receipts. Actual database
comments match exported action history. Memory v1 on the same clean source still
fails persistence (**367/404**, accepted=false), reproducing the negative control.
Fixture/gold/evidence are unchanged. Different protocol denominators are not a
quality comparison. [Receipts and wiring](persistent-http.fa.md) identify the exact
envelope adaptation and expose no authentication headers.

**2,035 full tests**, locked sync and Ruff pass, including 41 HTTP,32 tracker,
4 actual crash/ACK and12 binding tests. Actual `os._exit` after ingress/stage,
post-INSERT rollback, lost staging ACK, concurrent requests, migration and
snapshot reads are covered. The three demos, 49-check core/SQLite pilot and
actual RAG adapter with fixed collections (132/132) pass again.

This closes the bounded offline HTTP/core/tracker acceptance. Legacy `api:app`
remains memory; existing UI client still needs the new configured backend,
authenticated stable review payload/retry binding. Real index/model configuration,
corpus/exclusion and evaluation remain open. API cost is zero; no .env, provider,
embedding, real index or production ledger was accessed. C5 remains halted.

## 2026-10-12 — HTTP pilot acceptance and short-reply context (C2c)

The registered existing dev pilot now has a reusable HTTP kit with actual fresh
child interpreters at five restart checkpoints. Protocol `7a8d230` precedes
baseline execution; fixture, evidence and gold are unchanged. On clean source
`89eab33` (API identical to main `4f576d6`), the sole same-process failure was
loss of the initial issue when the user replied with only a version. The API
now reuses the existing bounded conversation builder with server-owned committed
history; active CaseState remains authoritative and only a validated bound
canonical assistant question enters reasoning context.

Clean `60c0712` improves same-process checks from **301/302 to 302/302** on the
same protocol and fixture. Restart checks remain **65/102** and all five state
preservation checkpoints fail: the actual API remains process-memory. Overall
`accepted=false`; a missing state or404 approval after restart is not dedup.
Retry verifies the entire original intake receipt, whole current view and zero
factory/retrieval/reasoning calls. Read/review requests cannot hide model work.
Edited/rejected drafts never enter context; overflow stops before ports with
committed ingress and safe replay. A latest-only GroundedRequest supplier fails
handoff matching safely. See [receipts, comparison and wiring requirements](http-pilot-acceptance.fa.md).

The legacy user-intake replay now independently checks retained original/prior
messages and exact latest input; its registered fixture/gold and historical
receipts are preserved. A mutation restoring latest-only input fails that replay.
**1,946 full tests**, locked sync, Ruff lint/format, all three required demos,
the legacy seven-turn replay, the **49-check core/SQLite pilot**, and actual RAG
adapter with fixed injected collections (**132/132**) pass. The CI expected-gap
flag is a negative control that keeps persistence acceptance false.

C2c's kit/execution is complete; its acceptance checkbox, U3/T4/C2 remain open
until real persistent HTTP wiring, authenticated review, lifecycle CAS and
interrupted-run journal are verified. Transport is ASGI, not an external TCP
server or browser test. The exposed answer-informed scripted dev family provides
no model, semantic claim support, real RAG or held-out evaluation result.
API cost is zero; no provider, embedding, index, .env or production ledger was
used. C5 halt stays unchanged.

## 2026-10-12 — R3 release to main and clean-main replay

Final review found no release blocker in the bounded offline port. With Sasan's
authorization, [PR #27](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/27)
merged into Hassan's `feat/rag-module` at `4162079d9b8fd809f6c600626719358a6d5763d2`;
then [PR #23](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/23)
merged into main at `ec1a1f05d28c59e5aee271bcad48c41fb22cf2f6`.
Both updated-head PR checks passed before the main merge. Both merge trees
exactly match the reviewed `65addbb` tree; no unreviewed runtime change entered.

On clean main, the actual adapter/backend with injected native collections
again passed **14 cases / 132 checks**. All runtime fingerprints and the fixed
fixture match the clean `326480d` receipt; source stayed unchanged during the
run. **95 targeted tests**, the adapter smoke and the independent **49-check**
core/SQLite pilot passed again. [Exact-main CI](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38225492349)
passed **1,891 tests**, Ruff and all registered offline replays.
See the [clean-main receipt](../experiments/retrieval_acceptance/results-main-ec1a1f0.json),
[release verification](../experiments/retrieval_acceptance/release-main-ec1a1f0.json)
and [R3 scope](rag-adapter-acceptance.fa.md). Seed catalogs and metadata are now
on main under `streamlit-data-for-dev-test/`; E1 can start from those files.

R3 port acceptance is published. Real index/exclusion/segmentation and retrieval
quality remain R1/R2/R4/P4; HTTP/UI persistent lifecycle, authentication and
journal/CAS remain U3/T4/C2. Split/rubric and real decision evaluation remain
E1–E5/C4. C5's halt is preserved. No real index, embedding, model, credentials
or production ledger was used; API cost was zero.

## 2026-10-12 — reusable RAG/core acceptance kit (C2b)

- Registered fixed evidence in `db9c2c0` before first execution. Five exact C3
  source hits and P1 are hash-bound; the #12782/#12629 family is exposed dev,
  answer-informed, with authored follow-ups. Labels/gold stay outside ports.
- The same reviewed factory can inject a fixed read backend into an actual
  adapter, preserving its production search/mapping. The default is explicitly
  the reference fixture adapter, with no index, embedding or provider request.
- The complete protocol passes **132/132 checks across 14 cases**. Four turns
  run through CoreTurnService and actual temporary SQLite, using five retrieval
  rounds and five scripted reasoning calls. Correction/refinement clears old
  evidence, stale approval fails, edit has a fresh approval, retry after restart
  returns one action, and old-event replay constructs no new adapters.
- Negative controls reject metadata/quote/query/cap/snapshot defects, silent
  oversize clipping, swallowed retrieval errors and stale refinement output.
  Alternative hit/query ordering remains accepted. Review of the kit itself
  fixed a false acceptance of forged synthetic-boundary metadata and a raw
  inspection error for factories without a real source file. A later review
  added source membership checks: returned hits must come from actual backend
  reads, not another query or an unread cached inventory.
- CLI receipts are exclusive, bind source hashes and commit/dirty status, and
  use safe error codes. Static candidate preflight never imports Chroma and
  rejects an empty entrypoint. CI also runs the fixture kit; its default success
  does not mean a production RAG adapter was accepted.

Verified locally: locked sync, **1828 passing tests** (32 new acceptance/CLI
tests), Ruff lint/format and the complete offline acceptance run. The first
110/110, ten-case receipt is preserved; the final protocol activates additional
already-registered version, URL and response-snapshot probes. More checks are
coverage, not measured model/retrieval quality improvement. API cost is zero.

At this pre-push milestone, PR #23 was pinned to `bdb7c53`: existing CI was green
but all four Python RAG files were zero bytes. Actual adapter acceptance R3/P4
was still pending. The release and clean-main replay above supersede that status.
Nonempty request filters, HTTP/UI, CAS/journal
lifecycle, actual index/ingestion, corpus exclusion and held-out quality remain
outside this kit. [Protocol and handoff](rag-core-acceptance.fa.md).

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
Runner/UI changes and the updated plan are published in
[PR #21](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/21).
The initial review above made no merge; release status is recorded separately
below rather than changing that historical baseline.
E2 scoring/conditional branches, frozen split/corpus checks, tracker/API recovery,
real RAG and C5 remain open. Reasoner-only usage attribution excludes retrieval,
embedding and adapter setup; provider billing is not reconciled by these tests.
No paid requests, real key/ledger access or team messages occurred.

## 2026-10-11 — standalone tracker release and recovery handoff

With the user's authorization, [PR #20](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/20)
merged into Behnam's branch at `662875839ce86c3db288e5b767be42ad0685f167`;
then [PR #19](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/19)
merged into main at `464e55e5855665029d5b730607f3875baf82320c`.
[Tracker branch CI](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38150131745)
and [fix review CI](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38150134843)
passed at `6628758`; these are not main-release checks at `464e55e`.
[Main release CI](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38150252419)
also passed at `464e55e`.
The standalone tracker has 16 passing tests; its synced branch suite had 1,690.
T1–T3 are accepted for the standalone SQLite module, with source, tests and pilot
linked in the plan. API/UI still use memory state; this does not close P3/U3/T4.

The [persistent-core handoff](persistent-core-handoff.md) specifies one
authoritative tracker state, replay before adapters, stale reasoning/staging,
exact stored-handoff reads after an ambiguous stage acknowledgement, and an
interrupted event with no automatic new model run. It is an integration policy,
not a production HTTP coordinator or durable reasoning journal. C2/P3/U3/T4,
real retrieval and semantic evaluation remain open. Follow the task table in the
team plan for the next small offline pilot; no new live use is authorized by
this release and C5 remains unresolved.

Added 11 authored offline core/SQLite failure-boundary cases: a receipt
superseded before the authoritative read, correction during reasoning or before
staging, interruption before reasoning and after reasoning/before staging,
exact lost-ack recovery, rollback after a comment INSERT, and concurrent
identical events/reviews. Recovery helpers live only in the test harness.
All 27 targeted tests (11 new plus 16 tracker tests) pass; the current branch
synced with released main passes **1,721 tests**, Ruff and locked dependencies.
All 19 offline workflow commands pass. No production core or API recovery
implementation, paid call, real key read or ledger change was added.

## 2026-10-11 — reusable receipt-bound core composition (C2a)

The prior shared release includes #19 at `464e55e` and #21 at `94b60e1`;
main CI `38151154794` passed all 1,721 tests. New baselines use `94b60e1`.

- Added `CoreTurnService` over the existing tracker ingress/read/stage port.
  A fresh receipt must match the original event and post-commit revision before
  constructing adapters. Replay never resumes reasoning. Complete pending
  content is read and compared after staging, including ambiguous ACK recovery.
- Preserved original and intermediate user messages when a short version reply
  arrives. Historical text cannot set active facts or supply retrieved evidence;
  old assistant answers are excluded. Canonical approved-question binding and
  total context limits remain explicit. The original event remains unchanged.
- Added full `current_case` freshness and an initial pending guard, alongside
  the compatible revision callback. Mutable typed terminal errors are revalidated
  at consumption; invalid codes cannot escape or buy a second model attempt.
  Constructed nested extra attributes fail before serialization can scrub them.
- Actual pre-change SQLite composition reproduced old-message/new-revision
  staging, missing complaint after a short reply, and same-revision pending
  drift. Same-input tests now prevent those observable failures; this measures
  input preservation and operational guards, not real model/RAG quality.
- **75 new focused cases pass; 1,796 full tests pass**, with one upstream
  Starlette/httpx deprecation warning. Locked dependencies, Ruff (107 files),
  20 offline CI workflow commands and the existing standalone tracker pilot pass.
  The new registered dev pilot records **4 turns / 49 operational checks** with
  actual temporary SQLite, complete original/edited/released handoffs, distinct
  run IDs and restart/replay. It is scripted, answer-informed and not held-out.
- Prepared a read-only C5 reconciliation packet; source fingerprints and primary
  ledger DB/WAL/SHM are preserved. Halt remains true and the USD 0.02 uncertain
  request remains unresolved. No key read, provider call or real cost was added.

See [service and baseline results](core-turn-service.fa.md) and
[C5 evidence needed](live-reconciliation-2026-10-11.fa.md). API still uses memory;
HTTP/auth integration, durable outcome/resumption and atomic lifecycle staging
are U3/T4 dependencies. Full reads cannot close the final same-revision ABA
between the last observation and the write. R3/E1/E2/C4/C5 remain open.

## 2026-10-11 — bounded readiness review and first RAG handoff

Released core `37ce74a` remains green: exact-head main CI `38157117534`
passed the existing 1,796 tests and registered four-turn / 49-check scripted
SQLite pilot. A bounded independent review found no new reproducible defect
in the core-owned C2a scope; no new runtime guard or architecture was added.

RAG owner pushed `c0d450a` and opened PR #23. Its first Chroma backend does
not yet implement `RetrievalRequest -> EvidenceBundle`. A probe using the
actual candidate search method with injected collections, without importing
Chroma or creating an index, reproduced `RetrievalResultInvalid` and zero
model calls. The pinned-head CI stops at Ruff with 31 findings. Seed review
also identifies missing preserved commit/location metadata and five Markdown
chunks above the core excerpt limit. These are R3 integration requirements,
not a measured regression in core or real retrieval quality.

See the [pinned review and owner acceptance checklist](rag-handoff-review-2026-10-11.fa.md).
R1/R2/R3/P4, API lifecycle/journal integration, evaluation split/rubric and C5
remain open. No embedding, model download, paid request, key read or ledger
change was performed. Continue with a small offline RAG adapter and the
existing service/pilot; no additional framework is justified by this review.

## 2026-10-12 — R3 connection repair over the restored candidate

PR #23 head `b571080` restored all four files, but fixed-backend acceptance
reproduced incompatible contract namespaces, lost provenance, clipped valid
quotes and unchecked request snapshots. With Sasan's explicit authorization,
`fix/rag-core-acceptance` preserves that branch and merges released main before
repairing the existing adapter/backend. No shared contract changed.

The actual adapter now uses canonical imports, preserves supplied source
metadata and 20,000-character text, rejects malformed/oversized data, checks
configured snapshots, and forwards explicit filters. Existing collections are
read through freshly checked snapshot metadata; same-ID mutable contents still
require a frozen corpus/index. Unsafe prototype index construction is blocked.
`chroma_binding` injects native fixed collections into both real constructors;
search and mapper remain production code. On clean source commit `326480d`,
the registered four-turn SQLite/scripted-reasoner pilot passes 132/132 checks.
[Pinned baseline replay and final receipt](rag-adapter-acceptance.fa.md) use the
same fixed inputs and corrected observation code: literal `b571080` fails at
10/28 executed checks; namespace-only diagnostic fails at 74/85. Early exits
change denominators; no quality percentages are inferred. **1,891 full tests**,
95 targeted tests, locked sync, Ruff, the three required demos and standalone
49-check core/tracker regression pass. Production source fingerprints remain
unchanged across the clean receipt run. That pre-release receipt came from the
separate repair branch; publication and the clean-main receipt are recorded
in the release milestone above.

The harness's `calls[-2:]` assumed one physical read per query despite the
existing multi-collection allowance. Observation now selects the current round;
independent controls accept repeated reads but reject omitted refinement queries,
including a false `queries_used` echo or a read only in a previous round. No
fixture, gold, decision criteria or logical resource limit changed.

No real index, embedding, provider, credentials or production ledger was used.
R1/R2/R4, actual index-backed P4, HTTP/persistent API and C5 remain open.

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
| Product configuration and real-browser acceptance | Tracker/tools + UI | Bounded SQLite/API/UI binding is published in PR32; still need browser authentication/configuration, browser smoke and full-session recovery |
| Evaluation cases and labelled real-model runs | UI/evaluation | Frozen 15 dev + 15 test families, rubric and operational outcome consumed in evaluation; connected offline runs are separate from model quality |
| Baseline versus final measurements | Whole team | Same cases, quality/cost/latency results, and failure analysis |
| Systematic Adversarial Testing | Proposed core bonus, mentor agreement | Defined challenge set plus measured before/after improvement |

The tracker's operations and explicit reset boundary are documented in
[SQLite tracker](sqlite-tracker.md). The opt-in
[connected offline backend](offline-ui-index-pilot.fa.md) uses that same tracker.
The legacy memory API/core demo does not use its database; restarting the memory
demo is not a persistence/recovery test.
