# Connect your module to the core

The foundation can be shared without changing `app.py`. Retrieval, tracker and UI
owners can develop against the same contracts while the existing UI remains a
placeholder. No API key is needed for this example or the automated checks.

## A runnable offline adapter example

Run `uv sync --locked --group dev` from the repository root, then copy this block
into a terminal. The source and answer are synthetic fixtures, not retrieval or
model-quality results.

```bash
uv run python - <<'PY'
from agent_app.contracts import (
    AnalysisResult, CaseState, EvidenceBundle, EvidenceHit, EvidenceLink,
    RetrievalRequest,
)
from agent_app.orchestration import SupportEngine
from agent_app.testing.fakes import FakeReasoner

SNAPSHOT = "synthetic-interface-v1"


class ExampleRetriever:
    def search(self, request: RetrievalRequest) -> EvidenceBundle:
        if request.snapshot_id != SNAPSHOT:
            raise ValueError("This adapter only serves its frozen snapshot")
        hit = EvidenceHit(
            chunk_id="fixture:counter:chunk-1",
            source_id="fixture:counter",
            excerpt="Synthetic fixture: Session State retains this demo counter across reruns.",
            source_url="https://example.org/synthetic-reference",
            source_type="doc",
            source_span="Synthetic counter example, paragraph 1",
        )
        return EvidenceBundle(
            snapshot_id=SNAPSHOT,
            hits=(hit,)[:request.top_k],
            queries_used=request.queries,
            warnings=("Synthetic fixture; replace with actual indexed sources.",),
        )


reasoner = FakeReasoner([AnalysisResult(
    decision="answer",
    user_draft="This scripted example suggests keeping the counter in Session State.",
    maintainer_summary="A synthetic source accompanies the scripted counter proposal.",
    rationale="The fixture supports this demonstration only.",
    evidence_links=(EvidenceLink(
        claim="Synthetic counter persistence", chunk_id="fixture:counter:chunk-1",
    ),),
)])
engine = SupportEngine(ExampleRetriever(), reasoner, snapshot_id=SNAPSHOT)
result = engine.run(CaseState(case_id="example-case"), "How can I retain a counter?")
assert result.status == "awaiting_approval"
print(result.model_dump_json(indent=2))
PY
```

Replace only your adapter with its real implementation. Keep the other side
scripted until your module's behavior is verified. The public ports live in
`src/agent_app/orchestration/ports.py`; models live in `src/agent_app/contracts.py`.

## Retrieval handoff

`search(RetrievalRequest)` returns an `EvidenceBundle` from exactly the requested
`snapshot_id`, with at most `top_k` hits total across its queries. Preserve stable,
unique chunk IDs and source IDs plus inspectable URLs and source sections. Carry
commit/version metadata when available; do not invent missing metadata. Keep
held-out cases and their discussions/outcomes out of the index.

After refinement, reasoning receives only the latest bundle. If earlier hits
remain relevant, the retriever must include them in the new bundle within the
same `top_k` limit. The engine records the actual retrieval round. A valid locator
establishes source presence, not whether a claim faithfully follows the source.

Only active user-provenance facts establish the installed environment. Evidence
facts cannot replace a conflicting confirmed user value. The initial query packs
whole confirmed facts and prioritizes versions over long descriptive fields.

## Reasoning policy and output checks

The engine supplies `ReasoningContext` with remaining attempts, retrieval rounds,
`can_refine` and `query_limit`. These defaulted fields preserve existing callers;
workflow hints and output feedback never change a ledger request's identity.

`MetisConfig(prompt_policy="structured_rules", ...)` opts in to the development
candidate with explicit conditional output requirements. `METIS_PROMPT_POLICY`
can select it through environment configuration. The default remains `baseline`;
see the [measured comparison and limitations](decision-quality.md). Do not treat
validation as semantic correctness or add another model call outside the shared
attempt allowance.

Explicitly labeled Python fences in proposed drafts receive bounded syntax
checking through parsing and static compilation without executing code objects.
This also rejects duplicate parameters and invalid module-level control flow.
An invalid snippet may use the remaining output
repair attempt; evidence/authority violations remain terminal. Syntax validity
does not verify APIs, callback arity or correct diagnosis. Explicit development
proposal checks cover a small source-grounded subset separately; see
[their applicability and limits](proposal-checks.md).

## Tracker and UI handoff

The tracker owns authoritative state. For user updates, deduplicate the event
first, prepare `propose_user_turn`, then atomically commit using the expected
revision and invalidate old approval. Read the committed state before invoking
the engine; its `current_revision` callback should use the same tracker. See the
[user-turn guide](user-turns.md) for replay and compare-and-swap requirements.

UI renders `RunResult.analysis` only when `status == "awaiting_approval"`. This is
a pending proposal, not an executed action or a solved case. Show drafts,
evidence, unknowns and next question; display stopped/error status separately.
Approval must bind to the exact case, revision and proposal. The current core
does not save a case or enforce execution approval.

## Shared development and spending

Use separate feature branches and coordinate shared contract changes. Before a
PR, run `uv run pytest`, `uv run ruff check .` and
`uv run ruff format --check .`; GitHub CI runs offline as well.

Keep routine work offline. The full team's budget is USD 5, including embeddings
and evaluation. Live calls go through the gateway on one designated runner with
one authoritative ledger; separate laptop ledgers cannot enforce a combined
limit. Never reset that ledger or share keys in Git. The gateway's estimates must
be reconciled with provider billing. See the [gateway guide](model-gateway.md).
