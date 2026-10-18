# C4y — source-aware parameter inspection, offline only

This additive experiment reviews the three already-authored C4x candidates.
It does not change their request/payload, model choice, old drafts or runtime.
Initial qualitative review found topical local evidence in all three examples,
selected default problems in C1/C2, missing convenient citations and a supplied
span-length mismatch in every selected source. AI review is not human scoring.

`integrity.py` regenerates the exact bound candidate and compares a narrow safe
literal grammar in headers/signatures, without execution or interpreting prose.
It distinguishes selected parameters from peers, preserves every original byte,
and reports local Unicode coordinates separately from supplied upstream spans.
Matching lengths never authenticate the original-file mapping or source truth.
Sentinel names and unsupported expressions remain unknown; bool/int, None/string
and list/tuple distinctions are retained.

`display.py` offers an inspection surface with exact complete parameter quotes,
escaped supplied HTTP(S) citations and specific unresolved source warnings.
Full original sources/signatures remain available to maintainers. Its envelope
binds the whole current request, candidate, observations, text and flags; mutation
requires a freshly generated review. It is not AnalysisResult/ProposalHandoff,
has no model/factory/UI hook and cannot authorize an answer, question or action.
Semantic support/usefulness stay null and human review stays mandatory.

`replay.py` validates the pinned C4x inputs, reproduces all eight original attempt
rows/seven final turns, then applies the same original authored selections. It
does not read `ai-review-v1.json`; qualitative annotations never enter selection
payload or corpus. No case/source-ID rule is added to any runtime component.

## Artifacts

- `protocol-v1.json`: honestly registered after initial AI review/design; not a
  blind model preregistration. Only a deterministic inspection comparison.
- `ai-review-v1.json`: separate qualitative AI findings and eight exact support
  spans, bound to all three original requests/candidates/sources. No human score.
- `replay-result-v1.json`: reproducible source observations and inspection views.
- `comparison.fa.md`: readable findings and all three inspection texts.
- `boundary-normalization-observation-v1.json`: post-hoc explanation compatible
  with existing EvidenceHit whitespace stripping; a span mismatch alone is not
  index corruption. Appending two LF characters fits the supplied lengths and
  16hex chunk prefixes, without authenticating raw documents/full hashes/mapping.
- `verification-v1.json`: historical697-control state at its pinned code commit.
- `verification-v2.json`: current code/artifact hashes, checks and preserved scope.

700 focused tests include100 new controls and the prior600 controls. Ruff/format
436Python files and independent review pass. A first broad run retained two
wording assertions after warning shortening; explicit no-default-correction and
unverified-original-mapping wording was restored and the full run passed again.
The failure log/earlier private projections were retained, not silently replaced.
Three later neutral boundary-normalization controls distinguish a provenance
warning from proof of source corruption. Historical verification-v1 is retained.

The new view can be longer than C4x's short candidate: visible source defects and
citations add useful review information. Length is not this step's acceptance
criterion; actual model success and human usefulness remain unmeasured.

## Reproduce

From the repository root, use a new output path:

```bash
uv run --no-env-file pytest -q tests/test_core_parameter_integrity_review.py \
  tests/test_core_parameter_inspection.py tests/test_core_parameter_review_replay.py
uv run --no-env-file python experiments/core_parameter_review_v1/replay.py \
  --output /tmp/parameter-inspection-fresh.json
```

The reused new-only report writer refuses overwrite and runtime/source/evaluation
destinations. It is not a race-proof sandbox. Verification used a neutral working
directory and parent-interpreter input/network audit; native/subprocess activity
is outside that audit's attestation.

The21funded files, separate117-file meeting watch, financial protocols, halt/three
holds, actual UI/provider configuration, corpus/exclusion/gold remain unchanged.
No paid API, index query, ledger write or held-out payload access. Fixtures and
review sidecars must stay outside RAG. A3/B1/Enum remain unresolved.

Actual adoption still needs human review, upstream source/extraction investigation,
broader dev/model selection including non-answer decisions, and a separately
reviewed delivery/profile/approval contract. Never recapture the current meeting
watch, refill a scope or reuse closed identities to activate this prototype.
