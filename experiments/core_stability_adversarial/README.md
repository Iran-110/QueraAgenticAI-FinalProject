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

Not yet executed at this registration commit. Original baselines and golden
fixtures remain unchanged. Receipts, failures and declared semantic review will
be added separately after the registered execution.
