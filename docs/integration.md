# Connect your module to the core

Owners can develop against the same contracts. The Streamlit/FastAPI prototype
uses scripted retrieval/reasoning and memory storage. Its additive HTTP ingress
now accepts explicit facts, checks, corrections and approved version replies;
UI controls and durable storage still need their owners' adapters. No API key is
needed for this example or the automated checks.

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

`SupportEngine(..., evidence_scope="exact_user_version")` is an opt-in filter for
advice about the current installation. Each returned bundle is validated first,
then explicitly versioned chunks survive only if `applicable_versions` contains
the active user `streamlit_version` value exactly. No patch compatibility,
version range or applicability is inferred from prose. Unknown/evidence-only
versions retain only unscoped chunks. The operational `evidence_scoped` trace
records an exclusion count; the reasoner does not receive the excluded records.
Refinement applies the same policy to the latest bundle within existing limits.

RAG should enumerate verified versions as canonical values such as `1.50.0`;
`1.50.x`, `>=1.50` and a user value such as `v1.50.0` will not match. An empty
version list means metadata is unknown, not universally applicable. These chunks
remain available and still need source review. Incorrect metadata and same-version
contradictions are outside this filter. Keep the default `evidence_scope="all"`
for deliberate historical comparisons or when mixed sources are needed to
explain a version difference; the strict filter can reject such useful proposals.
No retriever signature or shared contract has changed.

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

`fidelity_rules` is a separate opt-in development candidate. It combines a
whole-proposal fidelity instruction with an exact index of supplied facts,
checks and source scopes. It does not extract user facts or establish claim
support. The [fresh repeated comparison](decision-quality-v7.md) found a small
usefulness advantage with remaining summary/citation defects and tied paired
source-support scores. Keep the shorter policy for the first integrated pilot
and review the entire proposal. No additional runtime agent is required.

Explicitly labeled Python fences in proposed drafts receive bounded syntax
checking through parsing and static compilation without executing code objects.
This also rejects duplicate parameters and invalid module-level control flow.
An invalid snippet may use the remaining output
repair attempt; evidence/authority violations remain terminal. Syntax validity
does not verify APIs, callback arity or correct diagnosis. Explicit development
proposal checks cover a small source-grounded subset separately; see
[their applicability and limits](proposal-checks.md).

## Optional source-bound plans and complete review

The additive `GroundedPlanner` port can replace unrestricted final prose with a
`GroundedPlan` selecting routing, complete source references or a registered user
question. Wrap it in `GroundedReasoner`; the engine still returns `AnalysisResult`
and requires separate approval. The caller supplies reviewed user/source gap and
conflict catalogs for each latest bundle. Source/context hashes enforce content
binding; they do not detect false source text, unknown contradictions or semantic
entailment. Keep `evidence_scope="all"` when preserving historical comparisons.

`MetisGroundedPlanner` uses the existing gateway/ledger with
`MetisConfig(response_mode="grounded_plan", ...)`; default `analysis` is unchanged.
Malformed plans share the two-attempt allowance. Source/context binding failures
are terminal and never buy another attempt. There is no second production agent.

Pure proposal-review helpers bind the whole output, case and latest evidence to
an authenticated caller's review record. Their `pass` validates the record's
integrity/completeness, not semantic correctness or tracker permission. The
tracker must separately authenticate the reviewer, bind execution approval,
check revision and persist deduplicated outcomes atomically. See the
[extractive contracts, runnable example and exact handoff](extractive-core.md)
and [controlled Persian results](controlled-core-v9.fa.md).

## Tracker and UI handoff

The tracker owns authoritative state. For user updates, deduplicate the event
first, prepare `propose_user_turn`, then atomically commit using the expected
revision and invalidate old approval. Read the committed state before invoking
the engine; its `current_revision` callback should use the same tracker. See the
[user-turn guide](user-turns.md) for replay and compare-and-swap requirements.

For a standalone reply to a stored version question, use
`prepare_version_reply(case, turn, proposal_id=stored_id, question=stored_analysis)`
from `agent_app.orchestration.intake`. It recognizes only an entire `1.50.0` or
`Streamlit 1.50.0` message and returns a detached `UserTurn` with a user-attributed
`ReportedFact`. Case, revision and pending proposal must match, the exact question
target must be `streamlit_version`, and the incoming turn must otherwise contain
no structured updates. Both `next_question` and the displayed `user_draft` must
equal the core-owned `STREAMLIT_VERSION_QUESTION.question` exactly; a correct
field name with a question about Python or another environment is insufficient.
Use that exported `QuestionTarget` in a caller-owned `ProposalRequirements`
catalog and display it unchanged. Other wording uses explicit structured input.
Ambiguous text raises `IntakeRejected` with an allowlisted
code. Keep it visible for explicit user clarification; do not silently drop the
message or count a check as performed. Corrections, environment switches and
prerelease versions use the existing explicit structured `UserTurn` path.

The tracker must authenticate the stored question payload; `AnalysisResult`
itself has no proposal ID/revision. Preparation is not approval or persistence.
See the user-turn guide for the original-versus-prepared event hashes and replay
ordering needed when this helper runs on the tracker ingress path.

After a question is approved and displayed, its pending ID is cleared. Load the
tracker-owned `ApprovedReplyQuestion` and use `prepare_approved_version_reply`;
never restore pending state to impersonate approval. The offline API creates a
memory record on local approval and accepts an explicit `reply_to_proposal_id`
with a stable event. This is not reviewer authentication. The
[HTTP examples and receipt semantics](user-turns.md#additive-offline-http-ingress)
and [C2/P2 handoff](user-intake-pilot.fa.md) specify the remaining UI/tracker work.

UI renders `RunResult.analysis` only when `status == "awaiting_approval"`. This is
a pending proposal, not an executed action or a solved case. Show drafts,
evidence, unknowns and next question; display stopped/error status separately.
Approval must bind to the exact case, revision and proposal. The pure core does
not save cases or enforce execution approval; process-local checks do not replace
the tracker's durable transaction or authenticated review.

### Complete proposal handoff (C3)

Wrap one invocation's `Reasoner` with `ReasoningCapture`, then call
`build_handoff(result, capture.last)`. It exports `ProposalHandoff`: the case
before setting its pending ID, exact user message, final consumed evidence,
complete analysis, caller-owned reasoning context, all-source inventory and
whole-output review packet. It uses the engine's final normalized/filtered bundle;
prepared or earlier retrieval responses cannot supply citations or warnings.
Every source retains `source_commit`, `source_span`, `applicable_versions` and
scores. `source_inventory.version_scope` is an exact metadata comparison, not a
semantic applicability judgment or proof that a document is correct.

With `GroundedReasoner`, capture the request returned by its caller-owned
`request_factory` in a per-invocation closure. Pass that final request to
`build_handoff(..., grounded_request=request)`. Never reconstruct a catalog from
the first bundle after refinement. `GroundedRequest` must exactly match the
captured case/evidence and the message with only outer whitespace stripped,
matching `GroundedReasoner`'s existing normalization. The handoff preserves and
hashes the exact original message separately; inner text is never normalized.
Its user/source gaps and declared conflict groups
are part of the outer handoff digest. A catalog-only change can leave final text
and the legacy review packet unchanged while changing `handoff_sha256`.

The offline HTTP adapter exports the complete object at
`pending.review_handoff`, with additive `pending.analysis` and legacy display
fields. UI U2 should show every analysis surface and all supplied sources, even
uncited sources, plus user/source gaps when present. The `RunAdapters` factory is
a trusted per-run integration seam using the existing `Retriever`/`Reasoner`
ports; it defaults to scripted adapters. A supplier failure exports only an
allowlisted error, leaves no new proposal and preserves the committed ingress
receipt. It does not automatically retry a consumed event.

Adapter construction or engine-configuration failure is recorded as
`AdapterSetupUnavailable` after the accepted event is committed. It creates no
new proposal or model attempt. A previous proposal stays stale after a new turn;
replaying the accepted event returns its receipt/error view without rerunning
adapter setup. Config/constructor exception details never reach the user.

Tracker T2/T3 must retain the exact handoff with its pending proposal and use
`ensure_handoff_current(handoff, authoritative_case, proposal_id)` inside its
approval transaction. That checks full content as well as IDs/revision, removing
only the expected pending ID before comparison. It catches same-revision case
drift. Use `edit_handoff` with a new proposal ID for any edit and rebuild the UI
projection; even an identical-text edit needs new approval. The original
`reasoning_context.run_id` remains the model invocation identity, while
`proposal_id` becomes the human edit's identity.

`validate_handoff` checks integrity. `validate_proposal_review` checks an
attestation against the exact packet and reviewer identity supplied by the caller.
Neither authenticates a reviewer, proves entailment or grants execution approval.
Human edits are not automatically grounded again; semantic review must inspect
the rebuilt packet, including any newly written claims. The API still uses
unauthenticated process-local approval and does not execute tracker tools.

Run the registered current-state/refinement/correction example offline:

```bash
uv run python experiments/review_handoff/replay.py
```

The authored planner and fixed official sources exercise the same HTTP/core
boundary without paid requests. Its receipt is software integration evidence;
see [the C3 record and remaining owner handoffs](review-handoff-pilot.fa.md).

## Shared development and spending

Use separate feature branches and coordinate shared contract changes. Before a
PR, run `uv run pytest`, `uv run ruff check .` and
`uv run ruff format --check .`; GitHub CI runs offline as well.

Keep routine work offline. The full team's budget is USD 5, including embeddings
and evaluation. Live calls go through the gateway on one designated runner with
one authoritative ledger; separate laptop ledgers cannot enforce a combined
limit. Never reset that ledger or share keys in Git. The gateway's estimates must
be reconciled with provider billing. See the [gateway guide](model-gateway.md).
