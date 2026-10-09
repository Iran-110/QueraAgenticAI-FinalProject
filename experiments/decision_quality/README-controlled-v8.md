# Controlled real-Issue core checks — V8

This pack freezes six correlated scenarios from real Streamlit Issue
[#12782](https://github.com/streamlit/streamlit/issues/12782) before any replay.
It compares the existing `evidence_scope="all"` boundary with an opt-in
`evidence_scope="exact_user_version"` filter, and compares a bare user turn with
`prepare_version_reply` for a stored installed-version question. All proposals
and sequences are explicitly developer-authored. They are **not model outputs**;
counts measure deterministic core acceptance, retention and routing, not live
reasoning quality, RAG relevance or final-test success.

## Why this Issue and what “full” means

The report says Streamlit 1.50.0 shows empty multiselect defaults in a failing
full app after a parent selector changes. Its small reduced example works. The
reporter says the prior 1.49.1 full-app logic worked. The missing parent callback
and state-update path prevent a proven full-app diagnosis even when all
registered official source excerpts are present.

The 1.49.0 and 1.50.0 generated multiselect signatures and default/key descriptions
are alike. The actual release-sensitive evidence is the 1.50.0 release note,
which lists `st.multiselect` in the supplied-key identity transition. Thus “full”
means the relevant official release-mechanism excerpt is present. It does not
mean all app facts are known or that the Issue has an established root cause.

## Provenance and answer-informed selection

Official evidence remains pinned to docs commit
`695e6ce2fb1b23afc6df66b40420ab0013ad72fd`, snapshot 2026-10-06. Every hit includes
a URL, span and explicit version metadata. The pack records local source hashes.
The release note is copied exactly from
`content/develop/quick-references/release-notes/2025.md`, lines 123–147. Its scope
is the 1.50.0 release event, not a guarantee about every later release or a
particular full app. The original `multiselect-150-default` and
`fragment-150-rerun` records are reused. New 1.49.0 signature/default records
retain exact patch scope; there is no generated 1.49.1 record. The concept
rollout-history excerpt is an unversioned October 2026 snapshot and keeps empty
`applicable_versions`.

The author inspected the original body’s code and user-reported workaround,
and the comments on #12782, while choosing the key-identity mechanism and
checking duplicate families. The original body includes an assignment to the
widget’s Session State key and calls it a solution; that user-reported workaround
and its code were deliberately omitted from the controlled visible report.
“Full” means the registered mechanism evidence is present, not the complete
original Issue body or an independently verified fix. That **informed scenario/source
selection**. No Issue answer, workaround, closure status or comment excerpt is
supplied in any primary evidence bundle. `same_issue_answer_used_as_evidence`
is false, while `issue_comments_inspected_for_scenario_or_mechanism_selection`
is true. This disclosed development selection is not independent discovery.
The synthetic contradictory hit uses `example.org`, a synthetic source ID and
an explicit synthetic warning; it is never official provenance.

The complete #12782 family, including explicit duplicate #12629, must stay out
of real RAG and final held-outs. The existing #8061/#16914 reservations and
provisional linked #8901 quarantine are retained. Comment `3409555339` explicitly
closes #12782 as duplicate of #12629. The new reservation records this evidence;
**actual corpus exclusion remains the RAG/evaluation owners’ dependency**, not
functionality implemented or measured by these fixtures.

## Predeclared scenarios

| Scenario | Known / missing distinction | Defensible behavior |
| --- | --- | --- |
| Full official mechanism evidence | 1.50.0 and working reduction known; failing parent callback/path absent | Limited cited release explanation or a targeted callback/state-update question; no confirmed cause/fix |
| Key evidence removed | Same user facts; release-mechanism source absent in both pools | Bounded retrieval, then answerable app-code question or useful escalation; do not ask the user to find docs |
| Unknown version, mixed records | Installation missing; exact 1.49.0 and 1.50.0 plus unversioned history returned | Ask the installed version; never adopt source metadata as user facts |
| User correction 1.50.0 → 1.49.1 | Active user correction supersedes old version and evidence conclusions | Use corrected state, invalidate pending approval/old conclusions, seek missing code/coverage; a clearly limited historical comparison is also semantically safe |
| Same-version synthetic conflict | Official and explicitly synthetic 1.50.0 claims disagree | Preserve provenance and uncertainty; synthetic text cannot establish the diagnosis; filtering alone does not resolve conflict |
| Retired refinement source | Release note exists only in round one | Latest bundle owns citation authority; neither scope may reuse the retired hit |

Each scenario separately freezes known user information, user-clarifiable gaps,
documentation gaps, acceptable initial/final decisions, specific answerable
questions and whole-proposal claim checks. These reviewer expectations stay
outside reasoner messages. The correction also registers a pure transition input
and manually authored expected candidate state. It does not claim tracker
storage, event deduplication or action enforcement.

## What the two candidates can establish

The scope filter retains unscoped hits and exact matches to the active
user-provenance `streamlit_version`. It drops explicit versioned mismatches and
all explicit versioned hits when that user version is unknown. It neither
infers patch equivalence nor proves semantic support. Same-version false claims,
unscoped invented environment facts and causal overclaims deliberately remain
negative coverage controls. Their acceptance must be reported, not hidden.

A safe positive control describes the 1.50.0 release boundary while explicitly
stating that the active deployment is 1.49.1 and declining applicability. The
`all` engine should retain it; strict filtering should reject its citation. This
predeclared loss prevents reporting the guard as a free quality improvement.
The underlying historical comparison is safe even though the strict boundary
chooses to restrict source availability.

`prepare_version_reply(case, turn, proposal_id=stored_id, question=stored_analysis)`
creates only a detached structured `UserTurn`. The tracker must supply the
authenticated stored proposal ID/question and authoritative case. Conversion
is limited to a whole standalone `x.y.z` or `Streamlit x.y.z` reply to an `ask`
whose sole missing target is `streamlit_version`, with empty structured payload. The stored `next_question` and displayed `user_draft` must
both equal the canonical sentence “Which Streamlit version is installed in the
affected environment?” Misleading target wording or display is rejected.
Two positive replies and fourteen negatives cover uncertainty, quotation, other
environment, multiline context, an unperformed check, wrong package, stale
revision/proposal, conflicting structured facts, wrong target and wrong case.
Only `propose_user_turn` then proposes a next revision; no save or action occurs.
The baseline bare turn intentionally does not infer facts from free text.

## Replay and reporting boundary

[The fixture](cases-controlled-v8.json) and
[the protocol](protocol-controlled-v8.json) must be committed before scenario
execution. Schema/source/hash inspection is allowed before that registration;
no preregistered proposal may be executed beforehand. Do not retune expectations
after seeing results. A changed suite needs a new identified registration.

The later offline runner must replay identical authored sequences in both
conditions, with at most two reasoning attempts, two retrieval rounds, two queries
per round and eight steps. It must keep the latest bundle, capture passed-source
IDs, verify correction/intake state metadata, and never execute embedded code.
No model, gateway, key, ledger or paid request is needed or authorized here.
The baseline code commit is `dad3202db11cff8331718c6a5d58df834c49c79c`; prior
progress documents record 1,149 offline tests. That historical test count is
context, not a new verification run or a baseline model-quality score.

Report separately: authored negative acceptance; positive retention and the
historical-comparison loss; exact registered status/decision agreement; useful
positive final decisions; and narrow intake conversion/state assertions. A
negative rejected for an unknown citation is a safety-boundary pass, not a
successful answer or semantic-quality score. Labels are developer expectations,
not independent human gold. Passing all replay assertions still leaves real
model decisions, actual RAG, durable tracker approval/restart/deduplication and
final held-out evaluation unmeasured. No framework or additional agent is added.
