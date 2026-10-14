# Repeated three-dev core decisions and a limited adversarial slice

This is **exposed, answer-informed development**, with fixed evidence. No new
held-out case, real RAG relevance score or human usefulness result is produced.
Production contracts, retrieval, UI, tracker and final split files are unchanged.

## Before the model

[Stability method](stability-protocol-v1.json) registers four paired rounds over
the same three dev families. Each family runs twice B-before-C and twice
C-before-B; family order rotates. B uses the reviewed question vocabulary;
C adds existing opt-in decision/field guidance. Both use the same source-gap
renderer, fixed sources, model and two-attempt limits. The renderer setting is
common to both arms; this is not a byte-for-byte replay of historical V2/V3.
Current model responses and conditional paths may differ. No forced future
reply or selective failed-job rerun is allowed.

Each round has at most 24 exact immutable request slots, a USD0.10 finite scope
and USD0.091914240 worst-case reservation. Four rounds: 96 slots, worst-case
USD0.367656960; these are bounds, not estimated consumption. The designated
ledger retains its original USD4.50 ceiling, old continuation, uncertain hold
and global halt. Each batch registration fingerprint binds the committed
method protocol hash, ordered batch definition and exact slot fingerprint.
Ordinary live configuration remains halted; these scopes do not reconcile C5.

[Adversarial packet](adversarial-packet-v1.json) and
[oracle](adversarial-oracle-v1.json) are registered before either experiment:
three authored clean/challenge pairs, preserving original official excerpts.
Synthetic reports have explicit synthetic provenance. Current-version scope
uses the existing engine option in this isolated harness, not the legacy memory
API default. Conflict is explicitly caller-declared; automatic conflict discovery
is not being tested. Each adversarial job is a fresh one-turn event; it does not
execute correction history or approve an action.

## Reporting boundaries

- First attempts at common reached states, all returned plans and route completion
  have distinct denominators. Unreached follow-ups stay NA.
- The read-only mechanical reviewer reconstructs full proposal/handoff/released
  surfaces. This is a record-integrity check, not an entailment or usefulness score.
- A declared assistant reviews every material claim against the actual consumed
  sources/current USER facts and checks necessity/answerability of questions.
  Independent human usefulness remains null.
- Safe refusal alone does not pass a clean utility control. An attacker chunk can
  have a valid hash and still be an irrelevant or false source: quoting it is not
  proof of its assertion.
- Existing stale-approval/no-mutation/no-extra-send checks are reused. No new
  tracker or UI smoke claim replaces Behnam's separate manual work.
- This limited packet is a foundation for systematic adversarial work; no bonus
  completion/score is claimed without the agreed scope and broader comparison.

## Commands

From the repository root, read-only by default:

```bash
uv run python scripts/core_stability_probe.py
uv run pytest tests/test_stability_probe.py tests/test_stability_review.py tests/test_adversarial_packet.py
```

The live command requires the committed eligible protocol, the designated ledger,
an ignored credential file and a fresh private output directory:

```bash
uv run python scripts/core_stability_probe.py --live --env-file .env --output-dir /absolute/private/new-output-directory
```

Once the ledger changes, this historical registration is no longer eligible.
Do not reset the ledger or alter the protocol to replay already observed jobs.
Fresh research needs a separately reviewed immutable registration.

## Results

The original registration commit was `beeb2f3`; execution used that clean source
without edits. [Original live receipt](stability-live-receipt-v1.json),
[mechanical record review](stability-mechanical-review-v1.json) and
[declared assistant semantic review](stability-semantic-review-v1.json) retain
all failures and original proposals. Four rounds were planned: three completed,
the fourth stopped after two of six jobs. Twenty of 24 jobs were visited; four
remain unobserved. Ten common initial B/C requests are exactly equal. The planned
four-round counterbalance did not finish and observed order imbalance remains.

| Observed cohort | B completed routes | C completed routes |
| --- | ---: | ---: |
| Three fully executed rounds | 3/9 | 7/9 |
| All visited jobs, including partial fourth round | 3/10 | 8/10 |

First attempts: B eight valid/seven invalid/one unobserved out of 16; C sixteen
valid/two unobserved out of 18. All attempts: B nine valid/thirteen invalid/one
unobserved; C seventeen valid/two unobserved. Unobserved provider outputs are
failures, not silently excluded successes. Route completion is not semantic
adequacy. All 25 complete proposals reconstruct exactly. Twenty registered
questions were necessary/user-answerable and three button answers stayed bounded.
Two Enum documentary answers still do not fully demonstrate the strict
case-specific investigation/qualification condition; two other Enum jobs have
settled `ProviderResponseInvalid` failures at 1,024 output tokens. Truncation is
plausible but the finish reason was not retained, so its cause is not proven.

The review found 14 unknown-version proposals exposing an inaccurate caller
qualification about a "confirmed version". This produced a separately
[preregistered catalog fix](catalog-version-truth-protocol-v1.json): the same ten
controls give archived baseline3pass/7fail versus archived candidate10pass.
[Working-tree observation](catalog-version-truth-receipt-v1.json) and
[actual archive receipt](catalog-version-truth-receipt-v2.json) are distinct.
No original live proposal was rewritten/rescored and no new paid trial of the
fix was performed. Current catalog requires an active USER version before
declaring exact-version records missing; an empty bundle remains an honest
separate source gap. It discovers no Enum diagnosis or undeclared conflict.

[Narrow C4c unit amendment](catalog-compatibility-amendment-v1.json) and
[UI gap-caption amendment](catalog-ui-compatibility-amendment-v1.json) preserve
original literal test files; original fixture/oracle bytes remain unchanged.
[Historical C4c replay](historical-c4c-replay-receipt-v1.json) uses the original
candidate `535e020` and preserves 9pass/12fail before versus21pass after. The
historical command now accepts an explicit candidate commit and reads the exact
preserved controls when the current unit file intentionally differs.

[Cost reconciliation packet](stability-cost-reconciliation-v1.json): 42 transport
attempts, 41 settled with USD0.025141875 local estimate, one new USD0.0033792
uncertain hold. The old USD0.02 hold remains. Three scopes closed; the fourth
and old continuation were revoked by the existing `NewUncertainty` guard, with
no pending request. `scope_closed=false` in that fourth receipt reflects prior
revocation, not an active allowance. No ledger reset, refill, unhalt or new parent
was performed. Correlated provider billing/usage evidence is required; actual
total charge is unknown. The adversarial live scope was never registered/sent.

Instead, [offline adversarial receipt](adversarial-offline-receipt-v1.json) uses
six deterministic safe controls and three counterexamples. Six safe controls and
all expected counterexamples were observed. Hash-valid attack quotation was
accepted and classified **semantic failure**; obsolete source selection and an
answer under declared conflict were blocked. Ten authored planner attempts, nine
fixture queries, zero API and no execution port; this is not model attack
resistance, human usefulness, a real-RAG measurement or a completed bonus.

[HTTP/SQLite acceptance](http-sqlite-receipt-v1.json) still passes457/457 with
fresh-process restart/retry. It is separate from the process-memory model trial
and the direct-core adversarial replay. The latest local full suite passes3,204.
See the [Persian handoff](../../docs/core-stability.fa.md) and team plan for the
remaining RAG/split/human-review/manual-smoke/provider-reconciliation work.
