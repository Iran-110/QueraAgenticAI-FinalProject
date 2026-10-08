# Fresh synthetic whole-proposal fidelity development inputs v7

`cases-fidelity-v7.json` contains six canonical, newly authored synthetic support
inputs. It reuses exposed official source families from V4 and targets semantic
failures discussed in the public V5/V6 reports. These are development probes,
not held-out cases, independently sampled user reports, or a test-set accuracy
estimate. The authored user reports and supplied code have not been executed by
the author. Their reported checks are attributed synthetic user statements.

The inputs are authored before new HTTP requests or model proposals for this
study. The runner must freeze the final input-file SHA-256 in its protocol and
receipts before making requests. No previous private model proposal, runtime
output, real report body, final evaluation case, comment or maintainer resolution
was read to author this pack. This file describes the registered study plan; it
does not report execution, model results, costs or a selected production policy.

## Canonical caller data

Each case has one `CaseState` and one user message. Authoritative facts, genuine
unknowns and reported performed checks are supplied before generation. The two
correction cases preserve both the superseded fact and its active replacement,
with distinct synthetic turn IDs and revision 1. Other cases use revision 0.
Facts use fresh `user/synthetic-fidelity-v7/<probe-id>/<turn-id>` source refs and
`provenance_kind="user"`. No source fact becomes a user-reported environment fact.

All six cases are `kind="synthetic"`; every origin field is null. Environment
details are supplied for every case. The historical case has a known 1.27.2
installation and a source-coverage gap, not an unknown installed version. The
missing-integration case supplies a working reduction but explicitly omits the
helper implementations and a failing reduction of that path.

No `ProposalRequirements`, freshness flag, question catalog or exact canonical
question is supplied. Intended behavior lives in the authoritative user facts
and message. The missing implementation and historical coverage cases permit
useful natural clarification. An empty curated catalog must not be used to
disable asking or to imply complete user context.

Only `CaseState`, the user message, current evidence bundle and ordinary
caller-owned reasoning context belong in model input. Descriptions,
`expectations` and `reviewer_notes` are development/review metadata and must remain
outside it. `required_terms` and `forbidden_terms` are empty in every case.
Acceptable decisions and named missing-info aids are not answer keyword scoring,
question-text constraints or proof of semantic quality.

## Registered scenarios and controls

| Canonical probe | Plausible final decisions | Distinction for source-based review |
| --- | --- | --- |
| `fresh-corrected-version-submit-api` | Answer | Active 1.64.0 supersedes 1.27.2; exact submit-button evidence supports callback-parameter advice for an unexecuted draft. |
| `fresh-working-fragment-failing-options-path` | Ask | The fixed-options reduction works; the missing helper-dependent integration still fails in the user report. |
| `fresh-key-read-reported-three-way-mismatch` | Escalate | Reported frontend Bergen differs from backend Quito and callback Quito despite supplied key/read-inside code; the sources establish no cause. |
| `fresh-intent-correction-deliberate-old-new-pair` | Answer | Corrected intent deliberately retains the construction-time old value and separately reads the fresh keyed value. |
| `fresh-known-historical-signature-uncovered` | Answer, ask or escalate with limited scope | Exact historical parameter presence is not established by 1.64.0 records; installed version is already known. |
| `fresh-display-observation-claim-span-control` | Answer | Callback placement/lifetime claims need their supporting span; a saved-value observation does not establish universal persistence. |

The old/new-pair case is a positive intent control. The display case is a positive
answer and claim-attribution control. The working-reduction case controls for a
genuine information gap despite complete environment facts. The historical case
is an uncertainty control: more than one final decision can be useful, but none
may assert unsupported exact historical coverage. The mismatch case distinguishes
a reported inconsistency from documented ordinary callback timing. These related
source families and mechanisms are not statistically independent.

Review the complete proposal: user draft, maintainer summary, rationale,
evidence-link claims, missing info, next question, facts delta and suggested
checks. A correct user draft cannot compensate for a false rationale or reversed
maintainer summary. A valid citation ID cannot compensate for a claim unsupported
by its excerpt. A plausible decision cannot compensate for fabricated checks,
incorrect callback binding, discarded intent or superseded-version confusion.

Scenario-specific `reviewer_notes` are semantic questions, not required answer
phrases. Reviewers should accept useful equivalent question wording and coherent
alternative code. Bounded retrieval refinement remains permissible before a
final answer, question or escalation.

## Exact source reuse and exclusions

The pack retains snapshot `core-quality-guards-v4`, official documentation commit
[`695e6ce2fb1b23afc6df66b40420ab0013ad72fd`](https://github.com/streamlit/docs/tree/695e6ce2fb1b23afc6df66b40420ab0013ad72fd)
and source snapshot date `2026-10-06`. Every `EvidenceHit` is copied unchanged
from `cases-guards-v4.json`: excerpt, chunk/source IDs, URL, type, commit,
version applicability and source span. There are nine unique hit records.

| New probe | Existing V4 source case | Copied chunks |
| --- | --- | --- |
| Corrected submit API | `synthetic-form-submit-exact-parameter` | `form-164-callback-v4`, `submit-button-164-signature-v4`, `submit-button-164-on-click-v4` |
| Working fragment / failing integration | `synthetic-corrected-version-working-reduction` | `multiselect-164-default-v4`, `fragment-164-rerun-v4` |
| Three-way mismatch | `synthetic-reproduced-front-back-mismatch` | `selectbox-164-callback-v4`, `selectbox-164-signature-v4`, `selectbox-164-key-access-v4`, `widget-callback-order-snapshot-v4` |
| Corrected old/new intent | `synthetic-previous-value-snapshot-control` | The same four selectbox/order chunks |
| Historical signature gap | `synthetic-form-submit-exact-parameter` | The same three form/submit chunks |
| Display and claim-span control | `synthetic-known-environment-callback-display` | The same four selectbox/order chunks |

Each case has two deterministic identical hit pools, with retrieval rounds 1
and 2. This is fixed-source handoff, not an actual retrieval ranking or discovery
measurement. No corpus, index, adapter or RAG source has changed. The generated
API records retain exact applicability to 1.64.0. The widget-order concept record
retains empty `applicable_versions` and its unversioned October 2026 snapshot
description; it is not historical 1.27.2 documentation.

Reservations #8061, #8901, #12782 and #16914 and the original family-quarantine
candidate record are retained unchanged as exclusions. No new real report family
is consumed by the synthetic suite.

## Registered comparison and review plan

`protocol-fidelity-v7.json` freezes the suite bytes, canonical content and explicit
24-entry schedule. `review-fidelity-v7.json` freezes the source-review procedure.
The comparison is two draws across two frozen policies on these six
canonical inputs: 24 observations, in replicate-major order. The runner should
record both policy identities, rotate their order within a case and preserve one
canonical input per scenario rather than duplicate cases in this artifact.
Receipts pin the registered plan, input and code hashes. Production defaults
stay `baseline` with optional proposal checks disabled. Each observation retains
the existing two-attempt and two-retrieval-round limits. Both conditions use
`gpt-4o-mini`, input reserve 32768 and output ceiling 768. The shorter control is
`structured_rules`; the candidate `fidelity_rules` adds a concise fidelity
instruction and a deterministic exact-record index together. Their individual
effects are not separated by this comparison.

The original continuation and unresolved-incident ledger govern every request.
The comparison ceiling is USD 0.030 within the existing remaining authorization;
it does not refresh that authorization. Budget refusals may leave a partial
comparison and are recorded without refilling missing observations. Public
unauthenticated provider pricing was rechecked on 2026-10-08 and matched the
gateway's pinned 2026-10-07 rates; historical protocols remain unchanged.

Use randomized proposal aliases for source-based whole-proposal review. Give
human or assistant reviewers the same authoritative case/message/evidence, and
withhold policy, draw, attempt, cost, timing, automatic decision agreement and
prior ratings. Record acceptable, needs-revision or unusable judgments with
claim-specific evidence and uncertainty. Assistant source-review judgments are
not human gold labels. Keep automatic schema/decision agreement separate from
semantic ratings, and inspect within-case draw variation before interpreting a
policy difference. Two related draws per condition cannot establish general
accuracy, causal superiority, RAG quality or held-out gains.

## Offline input validation

From the repository root:

```bash
uv run --no-sync python -m agent_app.reasoning.fidelity_experiments
```

In addition to `ProbeSuite`, `CaseState` and `EvidenceBundle` contract validation,
verify exact `EvidenceHit` equality against the mapped V4 source cases, identical
round-1/round-2 pools, unique synthetic IDs, null origins, unchanged source and
exclusion metadata, one active fact per name, and empty required/forbidden terms.
These checks execute no embedded code and make no model or network request.
