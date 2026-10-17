# dev-three v2 (e2-rubric-v1, fixed evidence)

The three exposed dev cases (a: #12782 family, b: #9770 family, c: #8129
family) re-registered for `e2-rubric-v1`, as asked in
[evaluation readiness](../../../docs/evaluation-readiness.fa.md). They are the
same cases and families, not new ones. The v1 fixtures in
[`dev-three-v1/cases/`](../dev-three-v1/cases/) and every receipt built on them
stay unchanged under `e2-core-review-draft-v1`; do not put v1 and v2 results in
one denominator.

What changed from v1:

- `fixture_id` (`dev-three-*-v2`) and a `supersedes` block with the v1 path and hash;
- complete family Issue lists, matching the split manifest;
- per turn: `rubric_id: e2-rubric-v1`, `evidence_condition: controlled_fixed_evidence`
  and `required_sources` (the source an answer must point to);
- case b, version turn: one added unacceptable claim (the 1.39.0 bundle does not
  establish Markdown image labels from 1.40.0) and the reviewer's rule that an
  unsourced tip is allowed only when it says plainly it was not found in the
  supplied sources, while the documented icon options are still given.

Decisions, gaps, routes and evidence (`dev-three-v1/evidence-v1.json`) are the
same as v1. Gold here holds only for the fixed bundle; native-index gold is a
separate registration.

Human review: [`gold-review-v1.json`](gold-review-v1.json) (mhg, 2026-10-16;
initial verdicts, plain-language follow-up and final verdicts kept apart, with
the assistant's recommendations recorded separately). Recorded limitation: in
case a, the callback and state-order questions have no reply turn, so behaviour
after the user sends code is not tested.

Offline: `uv run python -m agent_app.evaluation.runner data/evaluation/dev-three-v2/cases --conditional-routes`
gives 3 cases, 6 turns, 79/79 checks, zero cost. This is plumbing, not model quality.
