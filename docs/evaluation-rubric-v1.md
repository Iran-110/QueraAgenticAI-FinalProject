# E2 rubric v1

Rubric ID: `e2-rubric-v1`. Owner: MohammadHasan (E2). Dated 2026-10-15.

This version adopts Sasan's [core-owner draft](evaluation-rubric.md)
(`e2-core-review-draft-v1`) as its base. It adds the four changes below:

- three requested by Sasan on 2026-10-15;
- one from the [dev-three case review](../data/evaluation/dev-three-v1/case-review-v1.json).

Everything in the draft still applies unless a section below replaces it.

The draft file stays byte-identical. The review workbench binds it by hash, and
the registered dev-three fixtures name its rubric ID. Registered fixtures and
receipts are not rewritten. New fixture and review scopes name `e2-rubric-v1`.
Sidecars for registered historical workbenches, including reviews completed
now, retain their registered draft rubric ID/hash and criteria. Register a
separate v1 scope before a future run; do not relabel or retrospectively regrade
historical results.

This is a review rubric, not a scorer. The existing `SemanticReview`,
`ReviewClaimBinding` and `score_review` validate bindings and score declared
support, decision, question and usefulness judgments. They do not implement
every report dimension below; remaining manual reporting is listed under
"Reporting". This version is not frozen. It freezes on dev before any test run
(draft, "Review provenance, calibration and freeze").

## 1. Every material claim is checked against source text and version

This replaces the draft's citation-optional wording with a stricter rule.

- **Find every claim.** List every material claim in every output surface:
  - user draft;
  - maintainer summary;
  - rationale;
  - next question;
  - missing information;
  - suggested checks;
  - fact updates.

  This includes claims with no `evidence_links` entry and claims that cite the
  wrong chunk. A citation ID is never evidence by itself.
- **Find the supporting text.** For each product or API claim, the reviewer
  finds the exact supporting text in the consumed sources. The search covers
  uncited sources in the same bundle.
- **Record the binding.** Record the claim as a `ReviewClaimBinding` with a
  `ReviewSourceQuote`, giving the chunk ID, Unicode codepoint span and exact
  quote.
- **No quote means no support.** A claim without a quote is `unsupported`, or
  `insufficient` while still being adjudicated. The reviewer cannot judge it
  `supported` from memory or from outside documentation.
- **Check the version.** Read the source's version metadata, such as the
  docstring release or the release-notes section. Judge applicability against
  the user's **active** version at this revision:
  - **`current`:** the source version matches or is shown to cover the user's
    version.
  - **`historical`:** a correctly attributed statement about another release.
    It is acceptable only if worded as history, not as advice for the user's
    environment.
  - **`unknown`:** the user's version is unknown, or the source has no version.
    A document never establishes the user's version.
- **Check user-report claims.** A claim about what the user reported binds to
  the active user fact (`user_fact_sha256`), not to a document. After a
  correction or withdrawal, a claim built on the superseded value is
  `unsupported`.
- **Gate.** The strict support gate stays as in the draft: one unsupported
  material claim sets it to 0. `claim_inventory_complete` is true only after
  every surface has been read. Reviewer-found uncited claims count in
  `declared_material_claim_count`.

## 2. The model draft and the released text are scored separately

- **Separate records.** The model original and maintainer edit each get their
  own `SemanticReview`:
  - **Model original:** `response_origin: "model"`, its own `handoff_sha256`.
  - **Maintainer edit:** `response_origin: "maintainer_edit"`, with
    `original_handoff_sha256` pointing to the model original.
  - **Released text:** preserve the exact text/hash and tracker outcome beside
    the review of its original or edited handoff. Separate released-stage
    semantic reporting remains manual; `SemanticReview` has no released origin.
    Approval or release is not proof of support or that an action ran.
- **Edits never improve the model's score.** Report the model's score on its
  original output. `aggregate_reviews` already keeps origins apart and never
  blends edits.
- **Report edits separately.** Report the edit rate per stratum, and how many
  edits fixed an unsupported claim, a wrong decision or an unnecessary question.
  These are reviewer workload measurements, not model quality.
- **Rejections.** A rejected draft has no released text. Score its model review
  as usual and record the rejection as an operational outcome.

## 3. User gaps, source gaps and the follow-up for each question type

The draft's `GroundedGap` vocabulary still applies. A **user gap** can be closed
by something the user knows or can do. A **source gap** cannot. A source gap
gets no user question; it calls for bounded retrieval or escalation.

Register each acceptable question as a route (`guard.question_target`) with a
reply branch. The table says what makes each question type necessary, how its
reply is given, and what the next turn must do with the reply.

| Question type (`question_target` examples) | Necessary when | Reply branch | Expected follow-up after the reply |
| --- | --- | --- | --- |
| Installed version (`streamlit_version`) | The version is unknown and changes which documented behaviour applies | Short reply bound to the approved canonical version question | Record the version as an active fact. Re-scope sources and claims to that version. Never ask it again unless the user withdraws it or switches environment. |
| Environment (`python_version`, `operating_system`, `browser`, `deployment`) | The behaviour is documented to differ by that environment | Structured `reported_facts` | Use the fact only where a source ties behaviour to it. An unrelated environment fact must not change the decision. |
| App code or state order (`parent_callback_code`, `state_update_order`) | The reported reduction works, or the failing path is not shown | Message with code or ordered steps | Compare the supplied code with the documented behaviour. A reproduction is still a user report, not a confirmed cause. |
| Reproduction (`minimal_failing_reproduction`) | No failing example exists and a maintainer would need one | Code, or "could not reproduce" | If the user cannot reproduce, do not ask again; escalate with what is known. |
| Check result (`checks_performed`) | A specific, safe check would separate two documented explanations | `checks_performed` entry with the result | Use the result to choose between the explanations. Do not repeat a check that is already done. |
| Error or traceback (`error_message`) | The report says "fails" but gives no observable output | Message | Match the error text against sources. Never execute a pasted snippet. |
| Source gap (`kind: "source"`) | Docs do not cover the version, cause or fix | No user reply | Retrieve once more within limits, or escalate and name the missing documentation. Asking the user to supply documentation is a wrong question. |

Only `streamlit_version`, `parent_callback_code` and `state_update_order` are
registered today: the canonical version question and the
[reviewed user-gap vocabulary](../data/evaluation/dev-three-v1/user-gap-vocabulary-v1.json).
The other names are proposals. Add them to a reviewed vocabulary with Sasan
before a fixture uses them as `question_target`.

Each question is judged with `QuestionJudgment`:

- **`necessary`:** it targets an unresolved gap that changes a decision;
- **`answerable`:** the user can know or do it;
- **`not_repeating_known`:** it does not repeat an active fact or completed
  check.

This applies to questions anywhere in the output, including requests buried in
the draft or the suggested checks.

The follow-up turn is judged on the reply it actually received:

- **Using the reply:** the reply binds to the right fact; superseded values
  stop being used; the question is not repeated.
- **Route advancement:** use the reply to take the next acceptable route. A
  decision label may stay the same: `ask(streamlit_version)` can become
  `ask(parent_callback_code)` when the version is resolved but code is still
  needed. Change the label only when the registered conditions require it.
- **Ignored reply:** a turn that ignores a decisive reply fails `fact_fidelity`,
  regardless of whether its decision label changed.

If a valid question type has no registered reply branch, mark the fixture's
coverage insufficient. It is not a model failure (draft, "Decision quality and
conditional routes").

Each case should register at least one route that ends after a reply, so
follow-up behaviour is actually exercised. The multi-turn targets come from E1:
at least 10 scenarios, at least 5 of them in test.

## 4. Gold depends on the evidence condition

Acceptable decisions and unacceptable claims hold only for the evidence the
model actually received. Record `evidence_condition` with each gold entry:

- **`controlled_fixed_evidence`:** the fixture's own bundle. This is a
  controlled core test.
- **`native_index`:** the actual supplied bundle from the real index after
  version scoping, with its evidence hash, pinned build, corpus allowlist and
  exclusion manifest hashes.

Do not apply a gold judgment from one condition to the other. Index or allowlist
membership alone is not support. A legitimate document can support a
`native_index` claim only when its supporting passage reached the model in that
turn's actual supplied evidence and supports the claim's wording and version
applicability.

Example: in dev-case-a, the 1.50.0 release notes say `st.multiselect` uses only
its key for identity when a key is provided. `widget-behavior.md`, which is
already in the allowlist, describes the broader rollout of key-based widget
identity from v1.50.0 through v1.55.0; it does not establish that every widget
changed in v1.50.0. The fixed bundle does not support the release-specific
`st.multiselect` claim. A separately preregistered native gold may allow it when
the actual consumed passage supports it. This does not establish the full-app
cause or a fix, or change historical fixed-evidence gold or results.

Direct-answer documents linked from a case's answer comments are excluded from
the index. Ordinary product documentation is not a leak and stays in the
corpus.

Not implemented: the runner and scorer read one gold per turn. Until they
accept per-condition gold, review native-index runs against a separate gold
version registered before those runs, and never by reinterpreting the
fixed-evidence labels after seeing the output. Historical workbenches keep
their registered scope and preregistered native criteria.

## Reporting

Remaining manual reporting: claim applicability is recorded in bindings but
not exported by `ReviewScore`. Question type, `fact_fidelity`, follow-up use of
replies, edit outcomes and released-stage judgments have no dedicated
`SemanticReview` fields or automatic aggregates. Record these separately with
the bound handoff identities and reasons; do not add unimplemented fields to
the existing sidecar schema.

Report each of these separately, with denominators:

- decision quality by stratum, with unsupported answers and unnecessary
  abstentions shown apart;
- strict support gate, plus supported and reviewed claim ratios;
- version applicability;
- question utility by question type;
- follow-up use of replies;
- usefulness on the 0–2 scale;
- edit outcomes;
- retrieval relevance;
- operational checks;
- cost and latency.

Keep these apart in the report:

- fixed evidence vs native index;
- dev vs test;
- human vs assistant reviewers;
- model vs maintainer edit.
