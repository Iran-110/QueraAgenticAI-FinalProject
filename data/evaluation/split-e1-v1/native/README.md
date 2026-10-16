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
- Pins (`native_scope`) are `pending_final_build` until Hassan's final build,
  allowlist and exclusion exist. The gold is not valid for a run before then.

dev: [registration](native-registration-dev-v1.json) of 16 fixtures and the
[human review](native-dev-gold-review-v1.json) (mhg, 2026-10-16: 14 correct and
2 unsure, both amended and then correct; one label fix after review). Five cases
(d, f, h, i, m) need release notes, which the current 18-source index lacks.

test: registered separately by the evaluation owner before the final run.
