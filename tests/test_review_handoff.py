"""Offline review integration checks content/freshness, never semantic truth."""

import pytest

from agent_app.contracts import (
    AnalysisResult,
    CaseState,
    EvidenceBundle,
    EvidenceHit,
    EvidenceLink,
    Fact,
    GroundedGap,
    ProposalHandoff,
    ReasoningContext,
    RunResult,
)
from agent_app.orchestration import SupportEngine
from agent_app.orchestration.handoff import (
    HandoffRejected,
    ReasoningCapture,
    ReasoningFrame,
    build_handoff,
    edit_handoff,
    ensure_handoff_current,
    validate_handoff,
)
from agent_app.reasoning.grounding import make_grounded_request, source_content_sha256
from agent_app.testing.fakes import FakeReasoner, FakeRetriever


@pytest.fixture
def inputs():
    case = CaseState(
        case_id="handoff-case",
        case_revision=2,
        facts=(
            Fact(name="streamlit_version", value="1.50.0", source_ref="user:2", turn_id="2"),
            Fact(
                name="streamlit_version",
                value="1.49.1",
                source_ref="user:1",
                turn_id="1",
                status="superseded",
            ),
        ),
        unknowns=("callback_code",),
        checks_performed=("The isolated reduction works.",),
        evidence_refs=("prior:background",),
    )
    evidence = EvidenceBundle(
        snapshot_id="handoff-snapshot",
        hits=tuple(
            EvidenceHit(
                chunk_id=name,
                source_id=f"source:{name}",
                excerpt=f"Supplied text for {name}; applicability remains to be reviewed.",
                source_url=f"https://example.org/authored-handoff/{name}",
                source_type="release_note",
                source_commit="fixture-commit",
                applicable_versions=versions,
                source_span="paragraph 1",
            )
            for name, versions in (
                ("current", ("1.50.0",)),
                ("historical", ("1.49.1",)),
                ("unconfirmed", ()),
            )
        ),
        warnings=("Authored fixture; not real retrieval quality.",),
    )
    analysis = AnalysisResult(
        decision="answer",
        user_draft="The supplied current note has relevant text; this does not establish a fix.",
        maintainer_summary="Reporter says the isolated reduction works.",
        rationale="The full application cause is unknown.",
        evidence_links=(EvidenceLink(claim="Supplied note contains text.", chunk_id="current"),),
        facts_delta=(
            Fact(
                name="documented_observation",
                value="A note was supplied.",
                source_ref="source:current",
                turn_id="proposed:2",
                provenance_kind="evidence",
            ),
        ),
        checks_suggested=("Inspect the parent callback.",),
    )
    return case, evidence, analysis


def run(inputs, *, responses=None, bundles=None):
    case, evidence, analysis = inputs
    capture = ReasoningCapture(FakeReasoner(responses or (analysis,)))
    retriever = FakeRetriever(bundles or (evidence,))
    result = SupportEngine(retriever, capture, snapshot_id=evidence.snapshot_id).run(
        case, "The full application fails.", run_id="run:handoff"
    )
    assert result.status == "awaiting_approval"
    return result, capture, retriever


def handoff(inputs):
    result, capture, _ = run(inputs)
    return build_handoff(result, capture.last)


def rejects(code, fn, *args, **kwargs):
    with pytest.raises(HandoffRejected) as caught:
        fn(*args, **kwargs)
    assert caught.value.code == code
    assert str(caught.value) == code


def test_complete_review_inputs_preserve_uncited_hits_and_all_output_surfaces(inputs):
    before = [value.model_dump() for value in inputs]
    bound = handoff(inputs)
    assert bound.case == inputs[0]
    assert bound.evidence == inputs[1]
    assert bound.analysis == inputs[2]
    assert [hit.chunk_id for hit in bound.evidence.hits] == ["current", "historical", "unconfirmed"]
    surfaces = {surface.surface_id for surface in bound.packet.surfaces}
    assert {"facts_delta.0", "checks_suggested.0", "maintainer_summary", "rationale"} <= surfaces
    assert validate_handoff(bound) == bound
    assert before == [value.model_dump() for value in inputs]
    assert not {"approved", "reviewer_id", "execute", "action"} & set(bound.model_dump())


def test_inventory_uses_supplied_active_user_version_not_old_or_inferred_version(inputs):
    bound = handoff(inputs)
    assert [entry.version_scope for entry in bound.source_inventory] == [
        "exact_metadata_match",
        "historical_or_other_version",
        "unconfirmed",
    ]
    assert [entry.content_sha256 for entry in bound.source_inventory] == [
        source_content_sha256(hit) for hit in bound.evidence.hits
    ]
    old_case = inputs[0].model_copy(
        update={
            "facts": tuple(
                fact.model_copy(update={"status": "superseded"}) for fact in inputs[0].facts
            )
        }
    )
    unknown = handoff((old_case, inputs[1], inputs[2]))
    assert all(entry.version_scope == "unconfirmed" for entry in unknown.source_inventory)


def test_capture_detaches_before_mutating_delegate_and_forwards_exact_context(inputs):
    case, evidence, analysis = inputs
    context = ReasoningContext(
        run_id="run:1", case_id=case.case_id, case_revision=2, attempt_index=1
    )

    class MutatingReasoner:
        calls = 0

        def analyze(self, given_case, message, given_evidence, *, context):
            self.calls += 1
            assert context is original_context
            object.__setattr__(given_case.facts[0], "value", "9.99.0")
            object.__setattr__(given_evidence.hits[0], "excerpt", "Changed after capture")
            object.__setattr__(context, "run_id", "delegate:changed")
            return analysis

    original_context = context
    delegate = MutatingReasoner()
    capture = ReasoningCapture(delegate)
    returned = capture.analyze(case, "  Preserve whitespace.  ", evidence, context=context)
    assert returned is analysis
    assert delegate.calls == 1
    assert capture.last.user_message == "  Preserve whitespace.  "
    assert capture.last.case.facts[0].value == "1.50.0"
    assert capture.last.evidence.hits[0].excerpt.startswith("Supplied text")
    assert capture.last.context.run_id == "run:1"


def test_engine_refinement_handoff_uses_last_consumed_normalized_bundle(inputs):
    more = AnalysisResult(
        decision="retrieve_more",
        user_draft="",
        maintainer_summary="",
        rationale="Need the current release note.",
        retrieval_queries=("current release note",),
    )
    initial = inputs[1].model_copy(update={"hits": (), "retrieval_round": 99})
    final = inputs[1].model_copy(update={"retrieval_round": 88})
    unused = final.model_copy(update={"warnings": ("Unused warning",)})
    result, capture, retriever = run(
        inputs, responses=(more, inputs[2]), bundles=(initial, final, unused)
    )
    bound = build_handoff(result, capture.last)
    assert result.retrieval_rounds == 2
    assert bound.evidence.retrieval_round == 2
    assert bound.reasoning_context.attempt_index == 2
    assert "Unused warning" not in bound.evidence.warnings
    assert retriever.responses == [unused]
    assert bound.evidence.hits == final.hits


def test_repair_capture_binds_last_attempt_without_buying_an_extra_attempt(inputs):
    result, capture, retriever = run(inputs, responses=("invalid JSON", inputs[2]))
    bound = build_handoff(result, capture.last)
    assert result.model_attempts == 2
    assert bound.reasoning_context.attempt_index == 2
    assert bound.reasoning_context.output_feedback is not None
    assert len(retriever.requests) == 1
    assert len(capture.reasoner.inputs) == 2


@pytest.mark.parametrize(
    "changed",
    [
        {"run_id": "another-run"},
        {"case_id": "another-case"},
        {"case_revision": 3},
        {"model_attempts": 2},
        {"retrieval_rounds": 2},
    ],
)
def test_result_and_capture_must_match_before_handoff(inputs, changed):
    result, capture, _ = run(inputs)
    rejects(
        "ReasoningContextMismatch", build_handoff, result.model_copy(update=changed), capture.last
    )


def test_stopped_run_or_absent_capture_cannot_make_a_handoff(inputs):
    result, capture, _ = run(inputs)
    stopped = RunResult(
        run_id=result.run_id, case_id=result.case_id, case_revision=2, status="error"
    )
    rejects("FinalProposalRequired", build_handoff, stopped, capture.last)
    rejects("InvalidHandoffInput", build_handoff, result, None)


@pytest.mark.parametrize(
    "surface", ["user_draft", "maintainer_summary", "rationale", "checks_suggested", "facts_delta"]
)
def test_changed_output_invalidates_whole_handoff(inputs, surface):
    bound = handoff(inputs)
    replacements = {
        "user_draft": "Unsupported edited draft.",
        "maintainer_summary": "An altered summary.",
        "rationale": "An altered rationale.",
        "checks_suggested": ("A different proposed check.",),
        "facts_delta": (),
    }
    altered = bound.model_copy(
        update={"analysis": bound.analysis.model_copy(update={surface: replacements[surface]})}
    )
    rejects("HandoffMismatch", validate_handoff, altered)


@pytest.mark.parametrize(
    "field,value",
    [
        ("excerpt", "Different bytes under the same chunk ID."),
        ("source_commit", "changed-commit"),
        ("source_id", "another-source"),
        ("applicable_versions", ("1.49.1",)),
        ("source_span", "paragraph 2"),
    ],
)
def test_changed_source_bytes_or_metadata_invalidates_handoff(inputs, field, value):
    bound = handoff(inputs)
    changed = bound.evidence.hits[0].model_copy(update={field: value})
    evidence = bound.evidence.model_copy(update={"hits": (changed, *bound.evidence.hits[1:])})
    rejects("HandoffMismatch", validate_handoff, bound.model_copy(update={"evidence": evidence}))


def test_missing_uncited_source_or_changed_message_invalidates_handoff(inputs):
    bound = handoff(inputs)
    for changes in (
        {"evidence": bound.evidence.model_copy(update={"hits": bound.evidence.hits[:1]})},
        {"user_message": "An entirely different problem."},
        {"source_inventory": bound.source_inventory[:1]},
        {"packet": bound.packet.model_copy(update={"analysis_sha256": "f" * 64})},
    ):
        rejects("HandoffMismatch", validate_handoff, bound.model_copy(update=changes))


def test_grounded_request_and_gap_catalog_are_inspectable_and_bound(inputs):
    result, capture, _ = run(inputs)
    request = make_grounded_request(
        capture.last.case,
        capture.last.user_message,
        capture.last.evidence,
        gaps=(
            GroundedGap(
                name="callback_code",
                kind="user",
                description="Missing parent callback.",
                necessity="Inspect state updates.",
                question="Can you share the callback?",
            ),
        ),
        conflict_groups=(("current", "historical"),),
    )
    bound = build_handoff(result, capture.last, grounded_request=request)
    assert bound.grounded_request.gaps[0].question == "Can you share the callback?"
    assert bound.grounded_request.conflict_groups == (("current", "historical"),)
    changed_request = make_grounded_request(
        request.case,
        request.user_message,
        request.evidence,
        gaps=(request.gaps[0].model_copy(update={"necessity": "Changed necessity."}),),
        conflict_groups=request.conflict_groups,
    )
    rejects(
        "HandoffMismatch",
        validate_handoff,
        bound.model_copy(update={"grounded_request": changed_request}),
    )
    bad_hash = request.model_copy(update={"context_sha256": "f" * 64})
    rejects(
        "GroundedContextMismatch", build_handoff, result, capture.last, grounded_request=bad_hash
    )
    mismatched = make_grounded_request(request.case, "Other user message.", request.evidence)
    rejects(
        "GroundedContextMismatch", build_handoff, result, capture.last, grounded_request=mismatched
    )


def test_current_check_normalizes_only_the_expected_pending_id(inputs):
    bound = handoff(inputs)
    current = bound.case.model_copy(update={"pending_proposal_id": bound.proposal_id})
    assert ensure_handoff_current(bound, current, bound.proposal_id) is None
    for changes, code in (
        ({"case_id": "other-case"}, "CaseMismatch"),
        ({"case_revision": 3}, "StaleRevision"),
        ({"pending_proposal_id": None}, "PendingProposalMismatch"),
        ({"pending_proposal_id": "replaced-proposal"}, "PendingProposalMismatch"),
        ({"unknowns": ("changed-unknown",)}, "CaseContentMismatch"),
        ({"checks_performed": ("Changed check.",)}, "CaseContentMismatch"),
        ({"evidence_refs": ()}, "CaseContentMismatch"),
    ):
        rejects(
            code,
            ensure_handoff_current,
            bound,
            current.model_copy(update=changes),
            bound.proposal_id,
        )
    changed_fact = current.facts[0].model_copy(update={"value": "1.49.1"})
    changed = current.model_copy(update={"facts": (changed_fact, *current.facts[1:])})
    rejects("CaseContentMismatch", ensure_handoff_current, bound, changed, bound.proposal_id)
    rejects("PendingProposalMismatch", ensure_handoff_current, bound, current, "other-proposal")


def test_edit_rebuilds_packet_and_preserves_origin_without_old_approval(inputs):
    bound = handoff(inputs)
    edited_analysis = bound.analysis.model_copy(update={"user_draft": "Edited human proposal."})
    edited = edit_handoff(bound, "proposal:edited", edited_analysis)
    assert validate_handoff(edited) == edited
    assert edited.reasoning_context == bound.reasoning_context
    assert edited.case == bound.case and edited.evidence == bound.evidence
    assert edited.packet.packet_sha256 != bound.packet.packet_sha256
    assert edited.handoff_sha256 != bound.handoff_sha256
    new_state = bound.case.model_copy(update={"pending_proposal_id": edited.proposal_id})
    ensure_handoff_current(edited, new_state, edited.proposal_id)
    rejects("PendingProposalMismatch", ensure_handoff_current, bound, new_state, bound.proposal_id)


def test_identical_text_edit_still_changes_identity_binding(inputs):
    bound = handoff(inputs)
    edited = edit_handoff(bound, "proposal:same-text-edit", bound.analysis)
    assert edited.packet.packet_sha256 == bound.packet.packet_sha256
    assert edited.handoff_sha256 != bound.handoff_sha256
    rejects("PendingProposalMismatch", edit_handoff, bound, bound.proposal_id, bound.analysis)


def test_revalidation_detaches_nested_content_and_rejects_bypassed_models(inputs):
    bound = handoff(inputs)
    clone = validate_handoff(bound)
    object.__setattr__(bound.evidence.hits[0], "excerpt", "Mutated source")
    assert clone.evidence.hits[0].excerpt.startswith("Supplied text")
    invalid = clone.model_copy(update={"unexpected_authority": "execute now"})
    rejects("InvalidHandoffInput", validate_handoff, invalid)
    rejects("InvalidHandoffInput", validate_handoff, {"execute": True})
    with pytest.raises(ValueError):
        HandoffRejected("unknown-diagnostic")


def test_capture_rejects_invalid_input_without_retaining_an_earlier_frame(inputs):
    case, evidence, analysis = inputs
    context = ReasoningContext(
        run_id="run:1", case_id=case.case_id, case_revision=2, attempt_index=1
    )
    delegate = FakeReasoner((analysis,))
    capture = ReasoningCapture(delegate)
    capture.analyze(case, "Message.", evidence, context=context)
    rejects("InvalidHandoffInput", capture.analyze, case, "\ud800", evidence, context=context)
    assert capture.last is None
    assert len(delegate.inputs) == 1
    bad_context = context.model_copy(update={"case_revision": 99})
    rejects(
        "ReasoningContextMismatch", capture.analyze, case, "Message.", evidence, context=bad_context
    )


def test_wire_round_trip_reconstructs_a_complete_validated_handoff(inputs):
    original = handoff(inputs)
    restored = ProposalHandoff.model_validate_json(original.model_dump_json())
    assert validate_handoff(restored) == original
    assert restored.case.pending_proposal_id is None


def test_build_preserves_exact_nonblank_user_message_bytes(inputs):
    result, capture, _ = run(inputs)
    frame = ReasoningFrame(
        capture.last.case, "  Original message.  ", capture.last.evidence, capture.last.context
    )
    bound = build_handoff(result, frame)
    assert bound.user_message == "  Original message.  "
    assert validate_handoff(bound) == bound
