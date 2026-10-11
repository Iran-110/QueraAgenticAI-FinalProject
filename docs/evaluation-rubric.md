# E2 rubric: core-owner review draft

This is Sasan's review recommendation for MohammadHasan's E2 work, dated
2026-10-11. It is not an implemented scorer, a frozen team rubric, or completion
of E2/E4. MohammadHasan owns the fixture schema, evaluation runner and report;
agree the additions below before changing that interface. Existing registered
fixtures and receipts remain historical records.

The current [split manifest](../data/evaluation/split-manifest.json) is draft:
one exposed dev case and no test cases. The two synthetic operational scenarios
do not count toward the required 15 dev, 15 test and 10 multi-turn scenarios
(at least five in test). The seed ZIP is named in the plan but is not tracked in
this repository; the manifest does not prove that a teammate received it.

## Inputs and scoring unit

Score one proposal at one case revision against the information available at
that turn. Save its exact [ProposalHandoff](integration.md#complete-proposal-handoff-c3):
case, actual last consumed evidence, full analysis, source inventory,
GroundedRequest when present, review packet and outer handoff hash. A citation
ID or valid JSON alone cannot establish answer quality.

Inspect every output surface: user draft, maintainer summary, rationale, next
question, citation claims, missing-info entries, suggested checks, fact updates
and any retrieval queries. The packet inventories these surfaces; it does not
discover claims or judge their truth. Inspect complete source text and metadata,
including uncited sources relevant to a declared conflict.

Record model proposals before maintainer review. If the maintainer edits a
proposal, preserve both original and edited handoffs with their distinct
proposal IDs and hashes, and record what was actually released. Score the model
and the edited/released response separately: a human correction must not improve
the model's original score. A rejected draft is not a user-visible response.
Approval/release is not proof of source support or an executed tracker action.

## Decision quality and conditional routes

Assign the turn's stratum before execution, independently of the decision the
model eventually chooses. Report results separately for:

- **Answerable:** the available evidence supports a useful response within a
  stated scope. A partial documented answer can be acceptable without proving
  the full-app cause or a fix.
- **Ambiguous:** a missing user fact or conflicting/incomplete evidence changes
  the defensible next step. A targeted question or bounded retrieval can help.
- **Needs escalation:** the remaining uncertainty cannot be resolved through
  the available user clarification or bounded retrieval. A useful escalation
  explains evidence, unresolved information and the next investigation.

Register acceptable decisions with their conditions, not a single preferred
label or an unconstrained list of all labels. Asking, answering or escalating
can each be valid in different conditions. Report unsupported answers and
unnecessary abstentions separately; escalating every case is not success.

`retrieve_more` is an intermediate core decision. Review its query relevance,
remaining capacity and whether the resulting latest bundle changes the
decision. Final proposals are `answer`, `ask` or `escalate`; a stopped run is a
separate operational outcome. Do not require an intermediate retrieval decision
to appear in the final pending proposal.

For multi-turn evaluation, register a response branch for each acceptable
question target or route. Reveal only the next input selected by that guard.
For example, a version reply belongs to an approved version question, while a
request for callback code needs a corresponding callback reply. If an otherwise
valid question has no registered response branch, flag fixture coverage as
insufficient rather than automatically failing the model. Offline regression
checks may retain exact scripted decisions; semantic evaluation must not use
those exact expectations to reject other registered acceptable routes.

## Claim support and version applicability

A material claim changes the user's understanding or next action: product/API
behaviour, a limitation, causal diagnosis, release applicability, a verified
fix, a reported observation, or a statement that an action happened. Review
claims even when the model omitted them from `evidence_links`.

For each material claim record its output surface and exact character span,
judgment and reference:

- Product claims need an inspectable source and the specific supporting quote
  or section. Record source/chunk ID, URL, source span, commit/version metadata
  and content hash. Presence of a source does not prove entailment.
- User reports need active, user-attributed fact/turn provenance. Keep the
  distinction between "the user reports" and an independently verified fact;
  a documentation citation cannot establish the user's installed environment.
- Action reports need actual tracker/tool outcomes. "Passed to a maintainer"
  before any such action is evidence of an operational reporting failure,
  even if an escalation draft was prepared correctly.
- An explicitly uncertain hypothesis must remain conditional. A hypothesis
  presented as an established cause or fix is an unsupported claim.

Use `supported`, `unsupported` or `insufficient`. One unsupported material
claim sets the strict proposal support gate to **0**; if all material claims
are supported and reviewed, it is **1**. If no unsupported claim has been found,
an insufficient judgment leaves the gate unassessed until adjudication; it is
not silently counted as supported. Also report claim counts, supported claims
divided by identified material claims, and reviewed claims divided by identified
material claims so the gate does not hide the extent or location of a failure.
With no material
claims, support is **N/A**, not 1. An incomplete review is an abstention with a
reason and unreviewed count, not a successful empty response. State denominators
and abstention/N/A counts when aggregating.

Review applicability separately as `current`, `historical` or `unknown`, using
the active user version at this revision. A correctly attributed statement
about the 1.50.0 release can be supported when the user has 1.49.1; applying it
as a fix for that user's environment needs additional support. Exact metadata
equality is not semantic compatibility. Missing version metadata is unknown,
and an unknown user version is not inferred from a document. Historical or
version-independent statements are not automatically failures when current
applicability is unconfirmed; assess their wording and relevance.

Reuse the existing `ReviewOutputSpan`, `ReviewSourceQuote` and
`ReviewClaimBinding` shapes when appropriate. Their integrity validation cannot
replace the reviewer judgment, establish full claim coverage, authenticate the
reviewer or authorize execution. Evaluation N/A/abstention annotations belong
to E2's review schema; do not force them into the core's Boolean
`ReviewDimension.passed` contract or change that shared contract implicitly.

## Facts, gaps, questions, conflict and uncertainty

Keep these dimensions distinct from support:

| Dimension | Passing judgment |
| --- | --- |
| `fact_fidelity` | Uses active user facts, attributes reports correctly, and does not promote source metadata or model guesses to confirmed user facts. Corrections/withdrawals/environment changes supersede the relevant prior conclusions. |
| `question_utility` | Every user request or proposed check targets a necessary, currently unresolved gap the user can answer or perform, and changes a defensible decision. Known facts and completed checks are not requested again without a stated reason. |
| `conflict_handling` | Recognizes the registered conflict, shows the relevant evidence and explains a supported preference or preserves uncertainty; does not silently choose a convenient source. |
| `uncertainty` | Distinguishes reported facts, documented behaviour and hypotheses; gives a bounded useful next step and does not claim diagnosis, fix or resolution without evidence. |

Use the existing `GroundedGap` vocabulary: `name`, `kind` (`user` or `source`),
`description`, `necessity`, and `question` for a user gap only. A user can report
their version, supply code or describe a check result; they cannot supply the
missing documentation merely by repeating their version. Source gaps call for
retrieval or escalation when clarification cannot resolve them.

Review requests in the entire draft, summary and suggested checks, not only
`next_question` or proposals labelled `ask`. Question utility is N/A only if no
user request/check is present and none is needed under the registered route.
After withdrawal or an explicit environment switch, a previously answered
question can become necessary again. Evaluate repetition against the current
state, not merely whether the wording appeared earlier in the conversation.

For a conflict case register the source IDs, conflict basis and acceptable
resolution before the run. A manually declared `GroundedRequest.conflict_groups`
control tests routing; it does not demonstrate automatic conflict discovery.
Record the actual runtime gap/conflict catalog in the handoff. Evaluator gold
and later turns must not be copied into model input. Caller-reviewed runtime
catalogs are an explicit treatment input, not proof of the model discovering
the missing information unaided.

## Human usefulness and separate measurements

Use a small human usefulness scale, with a short reason:

| Score | Anchor |
| --- | --- |
| 0 | Misleading, irrelevant or unusable; an unsupported instruction, impossible question or no meaningful next step. |
| 1 | Partly useful and understandable, but a necessary detail or actionable next step is missing, or the request is broader than needed. |
| 2 | A clear, appropriately scoped response or specific feasible next step that advances this case without unnecessary repetition. |

A justified question or escalation can score 2; closing the case is not
required. Report usefulness beside the support/fidelity gates, not as a score
that cancels an unsupported claim.

Measure retrieval relevance/labelled-source coverage, operational state and
approval/retry outcomes, and cost/latency separately. Label fixed-evidence
replays as controlled core tests. Process-memory checks do not prove persistence
or authenticated approval. Recorded or scripted replies are not live-model
quality evidence. A live-mode invocation also needs semantic review; mode alone
does not validate the decision or source support.

## Small optional fixture additions

The following is an illustrative extension to the existing fixture, not an
implemented schema or scorer. It omits the existing `visible`, evidence and
operational fields. MohammadHasan must agree and validate the field names and
implement conditional-route/scoring semantics before reporting these scores.

```json
{
  "rubric_id": "e2-core-review-draft-v1",
  "turns": [{
    "id": "example-turn-1",
    "gold": {
      "stratum": "ambiguous",
      "acceptable_decisions": ["ask", "escalate"],
      "allowed_intermediate_decisions": ["retrieve_more"],
      "gaps": [{
        "name": "streamlit_version",
        "kind": "user",
        "description": "Installed version is not confirmed.",
        "necessity": "Version changes which release record applies.",
        "question": "Which Streamlit version is installed in the affected environment?"
      }],
      "evidence_condition": {
        "kind": "unknown_user_version_mixed_sources",
        "removed_chunk_ids": [],
        "conflict_groups": []
      },
      "routes": [{
        "guard": {"decision": "ask", "question_target": "streamlit_version"},
        "next_input_ref": "example-turn-2.visible"
      }, {
        "guard": {"decision": "escalate", "unresolved_source_gap": true},
        "next_input_ref": null
      }]
    }
  }]
}
```

An empty conflict list does not mean two versioned sources contradict. A
removed-source variant must record the relevant missing IDs and gap; a source
gap has no user question. A `guard` must have explicit validator/runner semantics,
not be treated as a free-form string that automatically validates an output.
Keep rubric references and gold outside the model payload and RAG index.

## Review provenance, calibration and freeze

Each external review should identify reviewer/type (human or model), rubric
version/hash, case/turn/revision, proposal ID, handoff/packet hash, stage
(original, edited or released), timestamp, reviewed surfaces, claim annotations,
dimension scores and reasons. Disagreements and abstentions need an adjudication
record. Hashes bind artifacts; they do not make reviewers independent or honest.
The model that wrote a response must not be its sole correctness witness.

Start with human review of a dev subset covering all strata, version ambiguity,
removed evidence, correction and conflict. If a later LLM judge is used, record
its model, prompt/config and sample IDs; compare it with independently obtained
human judgments by dimension and examine disagreements. Calibrate on dev and
freeze rubric/judge settings before test. Judge calls are paid model calls and
must use the shared gateway/ledger; the unresolved live halt still applies.

Before final evaluation, freeze fixture/rubric versions, the whole-family split,
exposure exclusions, corpus allowlist/exclusion manifest and hash, code,
prompt/model/config and scorer. The current loader checks only family overlap
among fixtures loaded together; it does not enforce the draft manifest,
reserved exposure IDs, minimum counts or actual corpus exclusion. Final-run
validation of these artifacts remains E1/E2/E3 and R2 owner work. Held-out cases,
comments/outcomes, duplicates and direct-answer documents stay outside the
index; future user turns and gold are not visible before their turn.

Do not tune on test or retroactively overwrite registered fixtures/receipts.
Use a new version and disclose whether an oracle or label was added after a
first run. Compare baseline and improvements on the same case inputs and report
case/family counts as well as correlated turn/variant counts.
