# C4x — complete API parameter focus, offline candidate

This is an **experimental answer representation**, outside installed runtime
source. No current factory, UI, funded scope or approved draft selects it.
It is not a new model-quality result or a verified Enum fix.

The old renderer faithfully quotes whole selected chunks. In the exposed C4v
rehearsal, a narrow button parameter question received a 4.5–9.5k-character draft.
Markdown section parsing also treats these plain API docstrings as one section;
paragraph selection can omit continued options or qualifications.

`parameters.py` recognizes one conservative source-signature/`Parameters:`
grammar, keeps complete definitions and retains the entire original record.
`candidate.py` binds flat unit IDs to the complete current `GroundedRequest`,
active USER version and exact source/span hashes. No free technical prose,
diagnosis, fact correction, proposal or action can be supplied in its plan.
`semantic_support=None` and human review remain explicit.

## Observed deterministic comparison

Selections below are **authored after observing exposed failures**, not new model
choices. Only already-selected original API sources may supply the focus. All
eight original attempt rows/seven final turns remain in the replay; A3 relevance
failure, B1 retrieval miss and the other unchanged observations are retained.

| Turn | Focus | Original draft | Source-only display control | Parameter candidate |
| --- | --- | ---: | ---: | ---: |
| B2 | button `icon` | 9,551 | 3,434 | 1,357 |
| C1 | button `type` | 9,190 | 4,552 | 1,193 |
| C2 | button `disabled` | 4,552 | 4,552 | 860 |

Candidate lengths are 81–87% below original drafts. The complete focus spans are
597/428/111 characters; icon format/emoji restrictions, all three type options
and disabled True/default False text remain. This establishes structural
containment and shorter displayed candidates, **not usefulness or model success**.

The source-only column is a post-hoc, authored display diagnostic, declared in
`source-only-diagnostic-v1.json`. It separates removal of unrelated selected
sources from parameter focus. Renderer qualifications also differ, so this is
not a one-factor model experiment. C2 already had one selected source.

`protocol-v1.json` and its review/display amendment are retained. The fixture was
derived from eight recorded calls whose hashes matched C4v's existing receipt.
Five final analyses also matched separately staged views exactly. A1/A2 final
analyses and B1's retrieval-only attempt are reconstructed from their saved plan
and unchanged renderer. `input-counts-clarification-v1.json` distinguishes two
reconstructed final turns from three reconstructed attempt rows; original input
metadata is not silently rewritten. A portable replay validates supplied pins
and reconstructs outputs; it does not reopen/authenticate private provider calls.

## Usage and boundaries

```python
from experiments.core_parameter_focus_v1.candidate import (
    build_parameter_focus_request, parameter_focus_payload,
    render_parameter_focus_candidate,
)

focus = build_parameter_focus_request(current_grounded_request)
inspection_payload = parameter_focus_payload(focus)
# An explicitly authored offline plan selects IDs from THIS request.
candidate = render_parameter_focus_candidate(focus, reviewed_plan_json)
```

Candidate output is deliberately not `AnalysisResult`/`ProposalHandoff`.
Source-wide caveats and other parameters may still matter; the full source and
context remain available for review. Missing version, conflict, ambiguous or
truncated grammar, malformed selection and stale/mutated context reject.
Actual CRLF is normalized to LF only in display; raw text, offsets and hashes
remain exact. Literal `\u000d`, Markdown and HTML remain safely attributed.

The saved source itself has suspicious header defaults (`type ... default=None`
versus signature/body secondary, and `disabled ... default=is` versus False).
These bytes are preserved, not repaired or certified. Review the pinned source
and extraction before treating a default as authoritative. A complete structural
unit is not a clean, independent or semantically sufficient proposition.

No provider, index, corpus, exclusion, case/gold or ledger is opened or changed
by replay. Fixtures/outputs live under experiments and must never be indexed as
RAG sources. The current 21 funded files and separate 117-file presentation watch
remain exact. Global halt, three holds and unspent meeting capacity are preserved.

## Reproduce

From repository root, choose a **new** output path:

```bash
uv run pytest -q tests/test_core_parameter_focus.py \
  tests/test_core_parameter_candidate.py tests/test_core_parameter_review.py \
  tests/test_core_parameter_replay.py
uv run python experiments/core_parameter_focus_v1/replay.py \
  --output /tmp/parameter-focus-fresh.json
```

The writer refuses overwrite, symlinks and evaluation/runtime/source destinations.
It is not a race-proof sandbox. `replay-result-v1.json` retains the first reviewed
projection; `replay-result-v2.json` adds the source-only diagnostic. For a readable
comparison, see `comparison.fa.md`; code/test evidence is in `verification-v1.json`.

Promotion needs separate human relevance/usefulness review, a reviewed delivery
contract/config and, if paid testing is authorized later, a **fresh preregistered
comparison**. Never recapture the current meeting watch or reuse closed scope IDs
to activate this candidate.
