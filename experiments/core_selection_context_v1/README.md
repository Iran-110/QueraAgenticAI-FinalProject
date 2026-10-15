# C4l/E2y — optional bound current-query context (offline)

Registered before implementation on merged PR65/main `efaf02a`. This packet
tests advisory lexical freshness and exact legacy output compatibility. It
contains no new model run, model choice, RAG-quality score or held-out result.

- [Protocol](protocol-v1.json), [pre-code input pins](input-pins-v1.json).
- [Eight authored neutral scenarios](scenarios-v1.json),
  [24 frozen legacy rank/shortlist/inspection baselines](legacy-baseline-v1.json).
- [Replay receipt](replay-v1.json): 81/81 controls, all24 default digests exact.
- [Integration and explicit limitations](../../docs/selection-context.fa.md),
  [runner](../../src/agent_app/testing/selection_context_replay.py).

The optional context binds the full request/case/conversation, current projection
and its digest. All active USER values are retained beyond query packing; helper
labels/fact names alone do not become query terms. Same-case history provenance
is caller-owned, not authenticated by content binding. Stale/tampered contexts
reject; the omitted/None path retains exact fields and values.

In the authored correction control the current source moves from second to
first, but the old source can remain in the default shortlist. Latest-message
negation remains a lexical false positive, and synonyms can be false negatives.
These counterexamples remain in the receipt, not discarded or counted as model
success. Structural checks do not require the authored topical source to win.
All results retain semantic_support=null and human_review_required=true.

No API, ledger mutation, native index read, corpus/exclusion/gold change,
shared contract, teammate module, default prompt, model message or action/review
authority changes. Global halt, all three uncertain holds and all closed
experiment identities remain unchanged. Hosted CI is not represented as passing.
