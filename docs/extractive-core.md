# Optional extractive reasoning and whole-proposal review

This core path addresses the unrestricted claim channel observed in the V8
controlled proposals. The model chooses a `GroundedPlan`: decision, complete
source references, a registered question target, or bounded retrieval queries.
It cannot supply final prose, citation claims, fact updates, suggested checks,
code, or a selectively shortened quote. `GroundedReasoner` renders an ordinary
`AnalysisResult` for the existing `SupportEngine` and UI contract. The production
default remains the existing `analysis` response mode.

The renderer quotes complete selected excerpts, escapes source markup, shows
active user facts/checks as reports, and states that application cause, verified
fix and resolution are unestablished. Unknown version metadata remains unknown;
only exact active-user-version membership receives an exact-metadata label.
Other versions remain available as historical comparisons. These labels describe
supplied metadata and do not verify source authenticity or runtime applicability.
An oversized whole proposal is rejected; no tail is silently removed.

## Caller inputs and ports

`GroundedPlanner.plan(request, *, context)` returns a `GroundedPlan`, bare JSON
mapping, or JSON string. Run/case/revision/attempt identity remains in the existing
caller-owned `ReasoningContext`; plans cannot choose it. A plan binds to the SHA-256
of the entire case, message, latest bundle and catalogs. Each source selection
also binds the entire supplied source record, including excerpt and metadata.
Changing bytes under the same chunk ID or facts under the same revision invalidates
that binding. Hashes are integrity checks, not signatures or semantic judgments.

The application supplies a `request_factory(case, message, evidence)` to
`GroundedReasoner`. It calls `make_grounded_request` with reviewed metadata:

- `GroundedGap(kind="user")` names missing user-observable information and includes
  an exact question plus its necessity. An already-active user fact cannot be a
  gap. Use the exported `STREAMLIT_VERSION_QUESTION` for the narrow version intake.
- `GroundedGap(kind="source")` describes missing documentation and forbids a user
  question. The planner may request retrieval within the shared limits.
- `conflict_groups` identify at least two distinct chunk IDs in the **latest**
  bundle. `answer` is forbidden while any declared group exists. Every member is
  rendered on a final ask/escalation, even if the plan selects one side only.

Catalogs are trusted application preparation, never unvalidated model/source
fields. They are manual in V9. No catalog means no registered question/conflict;
it does not prove complete context or source consistency. There is no automatic
semantic conflict detector or general free-text user-fact extractor.

Malformed plans and invalid question/conflict choices may use the remaining
model attempt. Source/context binding failures are terminal
`GroundedSourceMismatch`/`GroundedContextMismatch`. Provider terminal errors also
remain terminal. Retrieval, repair and refinement share the original two attempts,
two rounds, two queries per round and eight steps. There is no additional agent,
framework, retry allowance or tool execution.

## Runnable offline example

Run from the repository root. This is a synthetic interface demonstration with
an authored planner; it is not a model or RAG evaluation.

```bash
uv run python - <<'PY'
from agent_app.contracts import CaseState, EvidenceBundle, GroundedGap, GroundedPlan
from agent_app.orchestration import SupportEngine
from agent_app.orchestration.intake import STREAMLIT_VERSION_QUESTION
from agent_app.reasoning.grounding import GroundedReasoner, make_grounded_request
from agent_app.reasoning.review import build_proposal_review_packet
from agent_app.testing.fakes import FakeRetriever

question = STREAMLIT_VERSION_QUESTION
prepared = []  # per-run fixture capture; do not share this across concurrent runs

def request_factory(case, message, evidence):
    request = make_grounded_request(case, message, evidence, gaps=(GroundedGap(
        name=question.name, kind="user", question=question.question,
        description="Installed Streamlit version is unknown.",
        necessity="Choose documentation for the affected environment.",
    ),))
    prepared.append(request)
    return request

class AuthoredPlanner:
    def plan(self, request, *, context):
        return GroundedPlan(context_sha256=request.context_sha256,
                            decision="ask", question_name=question.name)

engine = SupportEngine(
    FakeRetriever([EvidenceBundle(snapshot_id="synthetic-extractive")]),
    GroundedReasoner(AuthoredPlanner(), request_factory=request_factory),
    snapshot_id="synthetic-extractive",
)
result = engine.run(CaseState(case_id="example:extractive"), "My full app fails.")
assert result.status == "awaiting_approval"
assert result.analysis.user_draft == question.question
packet = build_proposal_review_packet(
    prepared[-1].case, prepared[-1].evidence, result.analysis,
)
print(result.model_dump_json(indent=2))
print(packet.model_dump_json(indent=2))
PY
```

## Gateway connection

`MetisConfig(response_mode="grounded_plan", ...)` and `MetisGroundedPlanner`
connect the new plan port to the **same** `MetisReasoner` HTTP/ledger accounting
path. `METIS_RESPONSE_MODE` selects the mode through environment configuration;
the default is `analysis`. Wrap the planner with `GroundedReasoner` and the trusted
catalog factory above. Existing eight `prompt_policy` values remain unchanged
for `analysis`; the extractive mode uses its separate typed-plan instructions.

The gateway verifies request/case/message/evidence/context binding before reserving
or sending. It returns raw content; parsing and repair remain in the core. Ledger
identity excludes response mode and feedback, so changing them cannot resend a
used run/case/revision/attempt. This is not permission to use live mode or to bypass
the existing halted ledger. No paid request was used to test this connection.

## Whole-proposal review record

`build_proposal_review_packet(case, latest_evidence, analysis)` hashes the entire
case, latest bundle and final `AnalysisResult`, including all drafts, rationale,
citation claims, questions, missing inputs, fact updates and checks. It inventories
every nonempty output surface. Store the actual final prepared request and proposal
per run; reconstructing an earlier bundle is insufficient. The pure helper cannot
know which bundle an external caller most recently retrieved.

`validate_proposal_review(packet, attestation, case, evidence, analysis,
authenticated_reviewer_id=...)` verifies those bindings, complete surface coverage,
six explicit review dimensions, and any exact source/output spans or active-user
fact references recorded by the reviewer. Offsets count Python Unicode code points,
not UTF-8 bytes or browser UTF-16 units. UI must convert offsets before recording
spans. A current-version source judgment needs exact active-user-version metadata.

The reviewer must inspect claim support, applicability, fidelity of reported facts,
question utility, conflicts and uncertainty across the whole output. Optional
`claim_bindings` record identified material claims; the helper does not discover
all claims or prove that the reviewer recorded all of them. An authenticated
reviewer can make an incorrect judgment and mechanically pass. Tests explicitly
retain that limitation. A `pass` means the review record is complete and matches
the supplied content; it is not automatic entailment, reviewer authentication,
tracker approval or execution authority.

The tracker must authenticate the reviewer, persist the packet/attestation with
the exact proposal, and separately enforce human action approval, revision checks,
atomic persistence and original-event deduplication/replay. Editing any proposal,
source or case invalidates the old review. The UI must display the whole final
proposal, including the maintainer summary and all source records, before review.

## Remaining integration evidence

RAG must supply inspectable current bundles and trustworthy version/provenance
metadata, carry forward relevant hits on refinement, and actually enforce the
declared evaluation-family quarantine. Tracker/UI must test stale/edited review,
reject/retry/restart and duplicate-event behavior with their real storage and
authentication. Evaluation must measure real-model plan selection, useful question
choice and source relevance on unexposed cases. None of these are established by
the controlled V9 adapter replay.
