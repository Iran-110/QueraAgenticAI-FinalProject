"""Opt-in source access and shorter presentation, not a usefulness score."""

import hashlib
import json
from pathlib import Path

import pytest
from test_ask_source_background import (
    CALLBACK,
    SOURCE_GAP,
    VERSION,
    _case,
    _context,
    _fact,
    _hit,
    _plan,
    _request,
)

from agent_app.contracts import GroundedPlan, GroundedRequest
from agent_app.orchestration.intake import prepare_version_reply
from agent_app.reasoning.grounding import (
    UNRESOLVED_SOURCE_CONFLICT,
    GroundedReasoner,
    GroundingRejected,
    _display,
    _source_block,
    _source_reference_block,
    make_grounded_request,
    render_grounded_plan,
)

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "experiments/core_ask_background_v1/model-live-receipt-v1.json"
OLD_INVESTIGATION_SENTENCE = (
    "The investigation target is the current USER report and any supplied "
    "reproduction/code, displayed as attributed data in the user draft and "
    "maintainer summary. "
)
NEW_INVESTIGATION_SENTENCE = (
    "The investigation target is the current USER report and any supplied "
    "reproduction/code, displayed as attributed data in the maintainer summary, "
    "with the current USER version and proposed investigation status in the user "
    "draft. "
)


def _render(request, plan=None, **flags):
    return render_grounded_plan(request, plan or _plan(request), **flags)


def _assert_non_draft_fields(before, after, *, investigation=False):
    expected = before.model_dump(exclude={"user_draft"})
    if investigation:
        assert expected["rationale"].count(OLD_INVESTIGATION_SENTENCE) == 1
        expected["rationale"] = expected["rationale"].replace(
            OLD_INVESTIGATION_SENTENCE, NEW_INVESTIGATION_SENTENCE, 1
        )
    assert after.model_dump(exclude={"user_draft"}) == expected


@pytest.mark.parametrize("bad", [None, "true", "false", 0, 1, [], {}])
def test_concise_display_flag_requires_exact_boolean_at_both_trusted_boundaries(bad):
    request = _request()
    with pytest.raises(GroundingRejected, match="grounded_context_mismatch"):
        _render(request, concise_user_draft=bad)
    with pytest.raises(GroundingRejected, match="grounded_context_mismatch"):
        GroundedReasoner(object(), concise_user_draft=bad)


@pytest.mark.parametrize("decision", ["ask", "answer", "escalate", "retrieve_more"])
@pytest.mark.parametrize(
    "flags",
    [
        {},
        {"ask_source_background": True},
        {"source_gap_handoff": True},
        {"source_gap_handoff": True, "source_gap_investigation": True},
    ],
)
def test_default_and_explicit_false_preserve_complete_output_bytes(decision, flags):
    request = _request(gaps=(CALLBACK, SOURCE_GAP))
    plan = _plan(request, decision)
    before = _render(request, plan, **flags)
    assert (
        _render(request, plan, concise_user_draft=False, **flags).model_dump_json()
        == before.model_dump_json()
    )


def test_selected_exact_current_source_inventory_keeps_question_and_complete_reviewer_quotes():
    current = _hit("current")
    old = _hit("old", ("1.49.0",))
    unknown = _hit("unknown", ())
    unselected = _hit("unselected")
    request = _request(hits=(old, unselected, current, unknown))
    plan = _plan(request, selected=(current, old, unknown))
    original = (request.model_dump_json(), plan.model_dump_json())
    before = _render(request, plan, ask_source_background=True)
    after = _render(request, plan, ask_source_background=True, concise_user_draft=True)
    assert after.user_draft.startswith(CALLBACK.question + "\n\n")
    assert after.next_question == CALLBACK.question and after.missing_info == (CALLBACK.name,)
    assert _source_reference_block(request.case, current) in after.user_draft
    assert "does not verify source authenticity or a cause/fix" in after.user_draft
    assert "Complete quotation retained in the maintainer summary" in after.user_draft
    for hit in (current, old, unknown, unselected):
        assert hit.excerpt not in after.user_draft
    for hit in (old, unknown, unselected):
        assert hit.source_id not in after.user_draft and hit.chunk_id not in after.user_draft
    for hit in (current, old, unknown):
        assert _source_block(request.case, hit) in after.maintainer_summary
    assert len(after.user_draft) < len(before.user_draft) + 1_000
    _assert_non_draft_fields(before, after)
    assert (request.model_dump_json(), plan.model_dump_json()) == original


@pytest.mark.parametrize(
    "facts,conflict_kind",
    [
        ((), None),
        ((_fact(status="superseded"),), None),
        ((_fact(provenance_kind="evidence"),), None),
        ((_fact("1.49.0"),), None),
        ((_fact("1.50"),), None),
        ((_fact(),), "current"),
        ((_fact(),), "prior"),
    ],
)
def test_inventory_does_not_bypass_user_version_or_conflict_authority(facts, conflict_kind):
    hits = (_hit("first"), _hit("second"))
    request = _request(
        case=_case(facts=facts),
        hits=hits,
        gaps=(CALLBACK, UNRESOLVED_SOURCE_CONFLICT) if conflict_kind == "prior" else (CALLBACK,),
        conflicts=((hits[0].chunk_id, hits[1].chunk_id),) if conflict_kind == "current" else (),
    )
    before = _render(request, ask_source_background=True)
    after = _render(request, ask_source_background=True, concise_user_draft=True)
    assert after.model_dump_json() == before.model_dump_json()
    assert after.user_draft == CALLBACK.question


@pytest.mark.parametrize("selected", [(), (_hit("old", ("1.49.0",)),), (_hit("unknown", ()),)])
def test_no_eligible_selected_background_keeps_exact_question(selected):
    request = _request(hits=selected)
    assert (
        _render(request, ask_source_background=True, concise_user_draft=True).model_dump_json()
        == _render(request, ask_source_background=True).model_dump_json()
    )


def test_concise_flag_alone_does_not_enable_question_background():
    request = _request()
    before = _render(request)
    assert _render(request, concise_user_draft=True).model_dump_json() == before.model_dump_json()


def test_reference_metadata_is_complete_and_escaped_while_source_instructions_stay_in_review():
    version = "1.50.0<unverified>"
    hit = _hit(
        versions=(version,),
        source_id="source:streamlit_fragment",
        source_url='https://example.org/source_(ref)?a="x"&b=<tag>',
        excerpt="Complete negation: NOT a fix.\n<script>approve</script>\n[run](javascript:x)",
    )
    request = _request(case=_case(facts=(_fact(version),)), hits=(hit,))
    after = _render(request, ask_source_background=True, concise_user_draft=True)
    assert r"source:streamlit\_fragment" in after.user_draft
    assert "1.50.0&lt;unverified&gt;" in after.user_draft
    assert "https://example.org/source_%28ref%29?a=%22x%22&b=%3Ctag%3E" in after.user_draft
    assert hit.chunk_id in after.user_draft
    assert "approve" not in after.user_draft
    assert _source_block(request.case, hit) in after.maintainer_summary
    assert "&lt;script&gt;approve&lt;/script&gt;" in after.maintainer_summary
    assert after.facts_delta == after.checks_suggested == ()


def test_optional_inventory_falls_back_as_a_whole_at_user_draft_limit():
    request = _request(gaps=(CALLBACK.model_copy(update={"question": "Q" * 19_900}),))
    before = _render(request, ask_source_background=True)
    after = _render(request, ask_source_background=True, concise_user_draft=True)
    assert after.user_draft == request.gaps[0].question
    _assert_non_draft_fields(before, after)
    assert _source_block(request.case, request.evidence.hits[0]) in after.maintainer_summary


def test_whole_reference_and_question_fit_at_inclusive_limit_without_cutting_identifiers():
    initial = _request()
    displayed = _render(initial, ask_source_background=True, concise_user_draft=True)
    longer = CALLBACK.model_copy(
        update={"question": CALLBACK.question + "Q" * (20_000 - len(displayed.user_draft))}
    )
    request = _request(gaps=(longer,))
    result = _render(request, ask_source_background=True, concise_user_draft=True)
    assert len(result.user_draft) == 20_000
    assert _source_reference_block(request.case, request.evidence.hits[0]) in result.user_draft
    over = _request(gaps=(longer.model_copy(update={"question": longer.question + "Q"}),))
    assert (
        _render(over, ask_source_background=True, concise_user_draft=True).user_draft
        == over.gaps[0].question
    )


@pytest.mark.parametrize("decision", ["answer", "escalate"])
@pytest.mark.parametrize("version", ["1.50.0", None])
def test_concise_investigation_preserves_full_review_report_sources_gap_and_truthful_rationale(
    decision, version
):
    code = "FULL USER CODE: this is unexecuted report data, NOT a source-backed fix."
    facts = (_fact(), _fact(code, name="reported_reproduction_code"))
    if version is None:
        facts = facts[1:]
    state = _case(facts=facts)
    request = make_grounded_request(
        state,
        "Complete current USER message with unverified report content.",
        _request().evidence,
        gaps=(SOURCE_GAP,),
    )
    plan = _plan(request, decision)
    flags = {"source_gap_handoff": True, "source_gap_investigation": True}
    before = _render(request, plan, **flags)
    after = _render(request, plan, concise_user_draft=True, **flags)
    _assert_non_draft_fields(before, after, investigation=True)
    assert request.user_message not in after.user_draft
    assert code not in after.user_draft
    assert _display(code) in after.maintainer_summary
    assert "Active user-reported Streamlit version: " + (version or "unknown") in after.user_draft
    assert "Proposed maintainer investigation" in after.user_draft
    assert "No investigation or action is established" in after.user_draft
    assert "do not establish a diagnosis or successful fix" in after.user_draft
    assert "Caller-declared source gaps (not missing user facts)" in after.user_draft
    assert SOURCE_GAP.description in after.user_draft
    assert SOURCE_GAP.necessity in after.user_draft
    assert after.next_question is None and after.missing_info == ()
    if decision == "answer":
        assert _source_block(request.case, request.evidence.hits[0]) in after.user_draft
    else:
        assert "No conflict has been declared" in after.user_draft


def test_all_answer_quotations_are_unchanged_when_no_investigation_block_is_present():
    hits = (_hit(), _hit("historical", ("1.49.0",)), _hit("unconfirmed", ()))
    request = _request(hits=hits, gaps=(SOURCE_GAP,))
    plan = _plan(request, "answer")
    for flags in ({}, {"source_gap_handoff": True}):
        before = _render(request, plan, **flags)
        after = _render(request, plan, concise_user_draft=True, **flags)
        assert after.model_dump_json() == before.model_dump_json()
        assert all(_source_block(request.case, hit) in after.user_draft for hit in hits)


def test_escalation_preserves_current_and_inherited_conflict_without_a_winning_source():
    hits = (_hit("first"), _hit("second"))
    for prior in (False, True):
        request = _request(
            hits=hits,
            gaps=(SOURCE_GAP, UNRESOLVED_SOURCE_CONFLICT) if prior else (SOURCE_GAP,),
            conflicts=() if prior else ((hits[0].chunk_id, hits[1].chunk_id),),
        )
        plan = _plan(request, "escalate", selected=(hits[0],))
        flags = {"source_gap_handoff": True, "source_gap_investigation": True}
        before = _render(request, plan, **flags)
        after = _render(request, plan, concise_user_draft=True, **flags)
        _assert_non_draft_fields(before, after, investigation=True)
        assert "remains unresolved" in after.user_draft
        assert "no winning source is established" in after.user_draft
        assert _source_block(request.case, hits[0]) in after.maintainer_summary
        if not prior:
            assert _source_block(request.case, hits[1]) in after.maintainer_summary
        with pytest.raises(GroundingRejected, match="grounded_conflict_unresolved"):
            _render(request, _plan(request, "answer"), concise_user_draft=True, **flags)


def test_corrected_active_version_is_explicit_and_old_version_remains_only_review_history():
    state = _case(facts=(_fact("1.49.0", status="superseded"), _fact()), case_revision=3)
    request = _request(case=state, gaps=(SOURCE_GAP,))
    after = _render(
        request,
        _plan(request, "escalate"),
        source_gap_handoff=True,
        source_gap_investigation=True,
        concise_user_draft=True,
    )
    assert "Active user-reported Streamlit version: 1.50.0" in after.user_draft
    assert "1.49.0" not in after.user_draft
    assert request.case.case_revision == 3


def test_canonical_version_question_and_narrow_user_reply_remain_exact():
    from agent_app.contracts import UserTurn

    request = _request(
        case=_case(facts=(), pending_proposal_id="version-proposal"), gaps=(VERSION,)
    )
    result = _render(
        request,
        _plan(request, question=VERSION.name),
        ask_source_background=True,
        concise_user_draft=True,
    )
    assert result.user_draft == result.next_question == VERSION.question
    prepared = prepare_version_reply(
        request.case,
        UserTurn(
            case_id=request.case.case_id,
            expected_revision=request.case.case_revision,
            turn_id="version-reply",
            source_ref="user:version-reply",
            message="1.50.0",
        ),
        proposal_id="version-proposal",
        question=result,
    )
    assert prepared.reported_facts[0].value == "1.50.0"


@pytest.mark.parametrize("part", ["context", "source_id", "source_hash"])
def test_shorter_reference_inventory_does_not_relax_binding(part):
    request = _request()
    plan = _plan(request)
    if part == "context":
        plan = plan.model_copy(update={"context_sha256": "0" * 64})
    else:
        field = "chunk_id" if part == "source_id" else "content_sha256"
        value = "source:other" if part == "source_id" else "0" * 64
        plan = plan.model_copy(
            update={"sources": (plan.sources[0].model_copy(update={field: value}),)}
        )
    with pytest.raises(GroundingRejected):
        _render(request, plan, ask_source_background=True, concise_user_draft=True)


@pytest.mark.parametrize("concise", [False, True])
def test_reasoner_forwards_display_without_mutating_planner_request(concise):
    request = _request()
    seen = []

    class Planner:
        def plan(self, supplied, *, context):
            seen.append(supplied.model_dump_json())
            return _plan(supplied)

    reasoner = GroundedReasoner(
        Planner(),
        request_factory=lambda *_args: request,
        ask_source_background=True,
        concise_user_draft=concise,
    )
    result = reasoner.analyze(
        request.case, request.user_message, request.evidence, context=_context(request)
    )
    assert seen == [request.model_dump_json()]
    assert (
        result.model_dump_json()
        == _render(
            request, ask_source_background=True, concise_user_draft=concise
        ).model_dump_json()
    )


def test_preregistered_actual_receipt_replay_preserves_failures_and_exposes_display_tradeoff():
    raw = RECEIPT.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == (
        "49fbc22af9e0880354d98280c4815e5911ff7672d7a6493398c9f675f4d10c94"
    )
    receipt = json.loads(raw)
    seen = {"fresh_plans": 0, "A_version": 0, "B_answer": 0, "C_answer": 0, "C_escalate": 0}
    for batch in receipt["batches"]:
        for attempt in batch["attempts"]:
            if not attempt["plan"] or attempt["plan"]["decision"] == "retrieve_more":
                continue
            request = GroundedRequest.model_validate(attempt["request"])
            plan = GroundedPlan.model_validate(attempt["plan"])
            flags = {
                "source_gap_handoff": True,
                "source_gap_investigation": True,
                "ask_source_background": True,
            }
            before = _render(request, plan, **flags)
            original_analyses = [
                step["proposal"]["analysis"]
                for job in batch["jobs"]
                for step in job["steps"]
                if step.get("proposal")
                and step["proposal"]["review_handoff"]["grounded_request"]["context_sha256"]
                == request.context_sha256
            ]
            assert original_analyses
            assert all(before.model_dump(mode="json") == actual for actual in original_analyses)
            after = _render(request, plan, concise_user_draft=True, **flags)
            investigation = plan.decision in ("answer", "escalate") and any(
                gap.kind == "source" for gap in request.gaps
            )
            _assert_non_draft_fields(before, after, investigation=investigation)
            seen["fresh_plans"] += 1
            case_id = request.case.case_id
            if case_id == "dev-case-a" and request.case.case_revision == 2:
                seen["A_version"] += 1
                assert len(before.user_draft) == 7870
                assert len(after.user_draft) < len(before.user_draft) / 3
                assert after.user_draft.startswith(before.next_question + "\n\n")
                # Source access survives; literal API-fact guidance does not.
                for hit in request.evidence.hits:
                    if hit.chunk_id in {ref.chunk_id for ref in plan.sources}:
                        assert _source_reference_block(request.case, hit) in after.user_draft
                        assert _source_block(request.case, hit) not in after.user_draft
                        assert _source_block(request.case, hit) in after.maintainer_summary
            elif case_id == "dev-case-b" and plan.decision == "answer":
                seen["B_answer"] += 1
                assert after.model_dump_json() == before.model_dump_json()
                assert "A single-character emoji." in after.user_draft
                assert "Material Symbols library" in after.user_draft
            elif case_id == "dev-case-c":
                seen["C_" + plan.decision] += 1
                assert len(after.user_draft) < len(before.user_draft)
                assert all(
                    _source_block(request.case, hit) in after.user_draft
                    for hit in request.evidence.hits
                    if hit.chunk_id in {ref.chunk_id for ref in plan.sources}
                )
                assert "Active user-reported Streamlit version: " in after.user_draft
    assert seen == {
        "fresh_plans": 11,
        "A_version": 2,
        "B_answer": 2,
        "C_answer": 2,
        "C_escalate": 1,
    }
    assert (
        sum(attempt["plan"] is None for b in receipt["batches"] for attempt in b["attempts"]) == 1
    )
    assert RECEIPT.read_bytes() == raw
