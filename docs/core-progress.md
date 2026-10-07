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

## Next integration work

| Work | Owner | Completion evidence |
| --- | --- | --- |
| Real retrieval adapter and frozen corpus | Data/RAG | Inspectable sources, metadata, and dev retrieval measurements |
| Live billing reconciliation and real-case evaluation | Agent core + evaluation | Synthetic question/answer/repair compatibility now verified; still need account deduction comparison and held-out quality/cost measurements |
| Durable tracker and safe execution | Tracker/tools | Persisted state, restart, reject/edit/stale approval, and retry tests |
| Backend connection and evaluation cases | UI/evaluation | Live local flow and 15 dev + 15 test with required multi-turn cases |
| Baseline versus final measurements | Whole team | Same cases, quality/cost/latency results, and failure analysis |
| Systematic Adversarial Testing | Proposed core bonus, mentor agreement | Defined challenge set plus measured before/after improvement |

Local tracker reset instructions will be added with its actual implementation. There is no persistent tracker to reset in the current core demo.
