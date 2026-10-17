# Native-index gold for split-e1-v1

Fixtures here hold gold for runs where the agent takes evidence from the real
index (`evidence_condition: native_index`). Each fixture is a separate version
of a registered fixed-evidence fixture (`native_of` gives its path and hash):
same case, family and visible turns, new `fixture_id`, new gold and routes. The
fixed fixtures and their receipts are unchanged. Never run a native fixture and
its fixed version in one invocation.

Rules, agreed with Sasan in [native evidence review](../../../../docs/native-evidence-review.fa.md):

- **answer** needs the registered passages in that turn's supplied bundle *and*
  support for the claim, API scope and active USER version. Presence alone is not
  support.
- **escalate** is acceptable when the passages were not supplied or do not cover
  the case, but it must name the missing documentation and a concrete next step.
  A missing passage does not make every escalation right.
- `native_passages` uses the `agent_app.evaluation.evidence_observation` format
  (AND requirements, OR alternatives of `source_id`, `source_commit`,
  `source_url`, exact `passage`). Every anchor is checked against seed text.
  Observation is necessary, not sufficient; support stays a human judgment.
- Gold and passage requirements never enter the prompt or retriever. The runner
  checks only decision membership and routes.
- Final frozen packets also validate explicit native condition labels and declared
  complete/consistent build pins before constructing a live factory. Their
  `corpus_manifest_sha256` is the raw **evaluation corpus JSON** hash, separate
  from the physical index manifest pin. This gate does not score passages or
  verify storage. [Final-pin contract and remaining gates](../../../../docs/native-freeze-readiness.fa.md).
- Pins (`native_scope`) are `pending_final_build` until Hassan's final build,
  allowlist and exclusion exist. The gold is not valid for a run before then.

Current dev selection: [registration v2](native-registration-dev-v2.json), with
14 unchanged v1 fixtures and two additive fixtures in `dev-v2/`. Only the initial
escalation conditions for fragment-rerun and tabs-blank change: an actual material
documentation/applicability gap and a concrete next step are required; reporting
a 1.38.0 remedy without supplied support is not required or permitted. A missing
observer match alone is not a semantic gap. The known USER version is not asked
again. Answer conditions, tabs follow-up, visible inputs, scripts, routes and
passage requirements/hashes are unchanged. The scripted offline path still
supplies its original fixture evidence; it is plumbing, not native model quality.

The [amendment record](native-dev-gold-amendment-v2.json) binds both new hashes
and their exact predecessors. It is **assistant review**; historical human verdicts are not
transferred to the new bytes. Human confirmation of the two changed clauses is
recorded separately in [the E2ac confirmation](native-dev-e2ac-human-confirmation-v1.json)
(mhg, 2026-10-17: both correct; assistant-informed, since each card showed the
assistant's recommendation). It binds the amendment, registration and fixture
hashes; their registered `pending`/`human_reviewed` fields are not rewritten. Build pins remain `pending_final_build`. Select
exactly the 16 paths in v2; do not recursively collect old and new versions.
See [E2ac verification and command](../../../../docs/native-dev-gold-amendment.fa.md).

Historical dev v1: [registration](native-registration-dev-v1.json) of 16 fixtures and the
[human review](native-dev-gold-review-v1.json) (mhg, 2026-10-16: 14 correct and
2 unsure, both amended and then correct; one label fix after review). Five cases
(d, f, h, i, m) need release notes, which the current 18-source index lacks.

test (**held-out; do not open during core/RAG development**): [registration](native-registration-test-v1.json)
of 15 fixtures in `test/` and the human review `native-test-gold-review-v1.json` (mhg,
2026-10-16: 14 correct and 1 unsure, amended and then correct). Written without any
retrieval or model run on test. No pytest reads them; the evaluation owner verifies
them with the runner and the registration hashes.
