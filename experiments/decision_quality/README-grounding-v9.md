# Typed extractive core boundary — V9 preregistration

This pack registers an optional core response contract that lets the model select
whole supplied source records, a caller-approved question, a decision, or bounded
retrieval queries. The core renders the visible proposal deterministically. It
addresses the known free-prose claim loophole without another production agent,
framework, RAG implementation, or tracker. The registration is **offline only**;
all plans, attacks, metadata catalogs, and expected behaviors are Codex-authored.
No project model decides these proposals and no paid request is authorized.

The [suite](cases-grounding-v9.json) and
[protocol](protocol-grounding-v9.json) must be committed before the first new
baseline/candidate replay. Inspecting source copies, schemas, and hashes is
allowed beforehand. Do not retune expectations after replay; identify a new
registration or disclose an amendment if fixtures need to change.

## Material inputs and provenance

The six cases, fourteen complete authored sequences, source bundles, user facts,
known/missing inventories, and original expected outcomes are copied from
[V8](cases-controlled-v8.json). The ordinary `evidence_scope="all"` core at Git
commit `e90f2d939248e58858e652bc644821f6682bf8f2` is the baseline. Its historical
expectation is six of seven authored semantic negatives accepted and seven of
seven positives retained. Reproducing that behavior is software-boundary evidence,
not a live-model quality baseline.

The real anchor is Streamlit Issue
[#12782](https://github.com/streamlit/streamlit/issues/12782). The complete
#12782/#12629 duplicate family and existing quarantined families remain excluded
from intended real RAG and final held-outs. Applying quarantine to the actual
index remains the RAG/evaluation owners' integration requirement.

Source excerpts remain pinned to docs commit
`695e6ce2fb1b23afc6df66b40420ab0013ad72fd`. Scenario/source selection was informed
by the Issue body, its reported workaround, and comments. The supplied controlled
input deliberately omits that workaround/code, Issue answers and closure outcome.
This is an exposed development family; it is not independent discovery or a
held-out test. “Full evidence” means the registered release-mechanism source is
present, while the full failing callback/state-update path and verified fix remain
absent. The suite retains V8's source paths/hashes and exact disclosure.

## New representation and manually prepared metadata

`GroundedPlan` contains only `context_sha256`, `decision`, source selections
`{chunk_id, content_sha256}`, an optional `question_name`, and bounded
`retrieval_queries`. It contains no final prose, citation claim, fact update,
suggested check, or model-selected quote substring. Templates in this registration
select IDs/routes. Runtime preparation computes the digest of the actual
case/message/evidence/catalog context and complete source records. The suite hash
pins those material inputs and templates before any replay.

The candidate additionally receives a **manually prepared** catalog. Codex
translated each frozen V8 inventory into user-observable versus source gaps,
recorded necessity, and canonical questions. The synthetic-conflict case also
receives one manually declared group linking the official release excerpt and
synthetic contradictory excerpt. This metadata is an extra candidate input;
it is neither a discovered model conclusion nor an entailment label inferred
from the positive/negative controls. It grants no action authority. The
`v9-conflict-catalog-ablation` probe removes it to expose the dependency.

The renderer must show all active user facts as attributed user reports, whole
escaped selected excerpts with source attribution, canonical questions, and the
unresolved cause/fix boundary. It computes applicability labels from active user
version and source metadata: exact matching metadata can be labeled current;
other explicitly scoped versions are historical; unknown user version or
unversioned source applicability remains unconfirmed. No `1.49.0` → `1.49.1`
patch equivalence is inferred. Superseded reports do not become current facts.
A declared unresolved conflict forbids `answer` and its members must remain
visible even if the plan selects one side only.

An exact quotation establishes which text was supplied. A digest establishes
which bytes/metadata were selected. Neither proves source authenticity, truth,
relevance, semantic entailment, current runtime behavior, a full-app root cause,
or a verified fix. A canonical catalog question is caller-approved wording; the
catalog does not automatically discover missing information in arbitrary chat
or code, or prove that a question is minimal. An empty catalog registers no
question; it does not establish complete user context.

## Seven positive intents to preserve

These explicit mappings avoid comparing incompatible output schemas as if they
were identical model responses. The material cases are the same, while rendered
wording is deliberately different and extra caller metadata is disclosed.

| Original authored positive | Candidate plan sequence | Required useful behavior |
| --- | --- | --- |
| `full-limited-supported-answer` | answer with release note and default excerpt | Current-release documentation summary, attributed known facts, no cause/fix certainty |
| `full-targeted-user-code-question` | ask `parent_callback_code` | One exact answerable callback/state-path question; working reduction stays reported as working |
| `removed-refine-then-answerable-question` | retrieve, then ask `parent_callback_code` | Source gap goes to bounded retrieval; missing user code goes to the user |
| `unknown-focused-installed-version-question` | ask `streamlit_version` | Ask for affected deployment version; mixed source versions never become user facts |
| `correction-respect-active-version-question` | ask `parent_callback_code` | Active corrected 1.49.1 is respected; old version is not current |
| `correction-safe-historical-comparison` | answer with 1.50.0 release note | Preserve the safe historical quotation that V8 strict filtering lost; do not apply it to 1.49.1 |
| `conflict-refine-then-bounded-escalation` | retrieve, then escalate | Both caller-declared conflicting excerpts remain visible; escalation is a proposed local next step |

All seven final decisions are preregistered retention targets. Their preservation
is a controlled capability check, not evidence that a real model will choose the
same plans or that the cases are solved.

## Registered probes and separate measurements

The suite registers 31 structured probes in addition to the seven positive
mappings and fourteen baseline sequences. They cover whole quotes and canonical
questions; wrong context/source hashes; changed same-ID excerpt/version metadata;
changed same-revision user facts; context from before a version correction; stale
round-one evidence; forbidden free text/claims/facts/checks/substrings; unknown,
known, or documentation question targets; invalid decision/question combinations;
manual conflict gating/obligatory visibility/ablation; supplied provenance
spoofing; and shared retrieval/model ceilings.

Report these measurements separately:

1. Baseline acceptance of the fourteen original proposals, with positive and
   negative controls separated.
2. New-format expressibility/containment. All fourteen old `AnalysisResult`
   payloads contain fields outside `GroundedPlan` and are representation
   mismatches, including seven valid positive drafts. Rejecting them is **not
   automatic semantic detection** of the seven negative meanings.
3. Seven mapped positive intents retained, with historical comparison and bounded
   two-round paths shown individually.
4. Source/context integrity and latest-bundle binding, independently of source
   truth or useful decision quality.
5. Canonical user-question constraints and the user-gap/source-gap distinction,
   with manual catalog preparation disclosed.
6. Declared-conflict gate versus the metadata ablation. No automatic semantic
   contradiction detection is implemented or measured.
7. Coverage controls with source truth/authenticity/usefulness **unclassified**.
   The ablated contradictory source and freshly hashed false source with spoofed
   provenance may be accepted as attributed quotations. Their acceptance must be
   shown explicitly; no entailment or authenticity success may be claimed.
8. Existing limits: at most two model attempts, two retrieval rounds, two queries
   per round and eight steps, with no implicit resumed allowance.

Do not combine these into a single “semantic accuracy” percentage. The suite's
expected baseline counts and seven-retention target are preregistered
expectations, not observed results. Failed expectations and coverage controls
must appear in the report, with complete rendered proposals and hashes retained
for whole-proposal inspection.

## Human review and integration boundaries

Deterministic rendering removes the model's unrestricted final-claim channel;
it does not remove the need to review the whole rendered content. Any human gate
must bind the exact output digest, case and revision. This registration neither
approves a proposal nor executes tracker actions. Human approval, persistence,
atomic revision checks, deduplication/restart, actual RAG corpus quarantine,
retrieval relevance, real-model selection quality, account billing and final
held-out evaluation remain unmeasured.

The experiment must not load `.env`, use the key, clear a ledger halt, release an
uncertain reservation, run snippets, modify `main`, or recreate teammates'
modules. The existing single-agent structure is sufficient for this core change.
