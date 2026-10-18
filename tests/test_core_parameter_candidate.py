"""Neutral authored controls for an experimental candidate, not model quality."""

import copy
import hashlib
import importlib
import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from agent_app.contracts import CaseState, EvidenceBundle, EvidenceHit, Fact, GroundedGap
from agent_app.reasoning.grounding import _display, make_grounded_request

ROOT = Path(__file__).resolve().parents[1]
TEXT = (
    'st.neutral(value, *, mode="safe")\n\n'
    "A neutral API. Global caveat outside the parameter selection.\n\n"
    "Parameters:\n\n"
    "value: str; default=None\n"
    "Complete value text, including a limitation.\n\n"
    'mode: str; default="safe"\n'
    "Complete mode description. Do not treat it as a successful fix.\n\n"
    "Returns: bool\n"
    "True on success. A source-wide caveat after the parameters.\n\n"
    "Examples:\n"
    'st.neutral("reported")\n'
)


@pytest.fixture
def candidate(monkeypatch):
    # This additive experiment is deliberately outside installed production src.
    monkeypatch.syspath_prepend(str(ROOT))
    return importlib.import_module("experiments.core_parameter_focus_v1.candidate")


def _fact(value, *, status="active", provenance="user", turn="current"):
    return Fact(
        name="streamlit_version",
        value=value,
        source_ref="report:" + turn,
        turn_id=turn,
        status=status,
        provenance_kind=provenance,
    )


def _hit(index=0, *, text=TEXT, versions=("1.49.0",), kind="doc"):
    return EvidenceHit(
        source_id=f"neutral-source-{index}",
        chunk_id=f"neutral-chunk-{index}",
        source_type=kind,
        source_url=f"https://example.invalid/docs/{index}",
        source_commit="neutral-revision",
        source_span="complete supplied record",
        applicable_versions=versions,
        excerpt=text,
    )


def _request(*, facts=None, hits=None, revision=3, case_id="neutral-case", gaps=(), conflict=()):
    return make_grounded_request(
        CaseState(
            case_id=case_id,
            case_revision=revision,
            facts=(_fact("1.49.0"),) if facts is None else facts,
            checks_performed=("Reporter tried a reduced example; outcome unverified.",),
        ),
        "Please explain the documented mode parameter.",
        EvidenceBundle(
            snapshot_id="neutral-snapshot",
            hits=(_hit(),) if hits is None else hits,
            queries_used=("neutral mode docs",),
        ),
        gaps=gaps,
        conflict_groups=conflict,
    )


def _plan(request, parameters=(1,), **changes):
    return json.dumps(
        {
            "context_sha256": request.context_sha256,
            "decision": "answer",
            "parameters": list(parameters),
            **changes,
        }
    )


def test_exact_unit_whole_source_and_caveat_locations_remain_available(candidate):
    original = _request()
    before = original.model_dump_json()
    request = candidate.build_parameter_focus_request(original)
    result = candidate.render_parameter_focus_candidate(request, _plan(request))
    unit = request.choices[1]
    quotation = result.quotations[0]
    assert quotation.text == original.evidence.hits[0].excerpt[unit.start : unit.end]
    assert quotation.text.startswith('mode: str; default="safe"')
    assert "Do not treat it as a successful fix." in quotation.text
    assert quotation.passage_sha256 == hashlib.sha256(quotation.text.encode()).hexdigest()
    assert quotation.source_text_sha256 == hashlib.sha256(TEXT.strip().encode()).hexdigest()
    assert quotation.source_span == "complete supplied record"
    assert _display(original.evidence.hits[0].excerpt) in result.review_text.replace("\n> ", "\n")
    assert "Global caveat outside" not in result.qualified_text
    assert "Global caveat outside" in result.review_text
    assert "source-wide caveat after" in result.review_text
    inventory = request.source_inventory[0]
    assert inventory.prefix_span[0] == 0
    assert inventory.prefix_span[1] == request.choices[0].start
    assert inventory.suffix_span[0] == request.choices[-1].end
    assert inventory.suffix_span[1] == len(original.evidence.hits[0].excerpt)
    assert "Other parameters and source-wide caveats may matter" in result.qualified_text
    assert result.semantic_support is None
    assert result.human_review_required is True
    assert result.diagnosis_or_fix_verified is False
    assert result.proposal_or_action_authorized is False
    assert result.case_id == "neutral-case" and result.case_revision == 3
    assert original.model_dump_json() == before


def test_payload_is_detached_and_retains_full_sources_and_user_data(candidate):
    ground = _request()
    request = candidate.build_parameter_focus_request(ground)
    payload = candidate.parameter_focus_payload(request)
    assert payload["grounded_request"] == ground.model_dump(mode="json")
    assert payload["parameters"][1]["parameter_id"] == 1
    assert payload["response_schema"]["additionalProperties"] is False
    assert payload["limitations"]["semantic_support"] is None
    payload["grounded_request"]["evidence"]["hits"][0]["excerpt"] = "MUTATED"
    payload["parameters"][0]["start"] = 700
    assert candidate.validate_parameter_focus_request(request) == request
    assert request.grounded.evidence.hits[0].excerpt == ground.evidence.hits[0].excerpt


def test_build_detaches_original_mutable_contract(candidate):
    original = _request()
    request = candidate.build_parameter_focus_request(original)
    object.__setattr__(original.case, "case_revision", 400)
    object.__setattr__(original.evidence.hits[0], "excerpt", "MUTATED")
    assert candidate.validate_parameter_focus_request(request).grounded.case.case_revision == 3


@pytest.mark.parametrize(
    "facts",
    [(), (_fact("1.49.0", status="superseded"),), (_fact("1.49.0", provenance="evidence"),)],
)
def test_unknown_or_nonuser_version_cannot_enable_parameter_answer(candidate, facts):
    with pytest.raises(ValueError, match="^ParameterFocusUnavailable$"):
        candidate.build_parameter_focus_request(_request(facts=facts))


@pytest.mark.parametrize(
    "hits",
    [
        (),
        (_hit(versions=()),),
        (_hit(versions=("1.50.0",)),),
        (_hit(kind="issue"),),
        (_hit(kind="comment"),),
        (_hit(kind="release_note"),),
        (_hit(text="A generic guide without parameter syntax."),),
    ],
)
def test_ineligible_records_never_become_selectable(candidate, hits):
    with pytest.raises(ValueError, match="^ParameterFocusUnavailable$"):
        candidate.build_parameter_focus_request(_request(hits=hits))


def test_rejected_record_stays_full_in_request_and_review_inventory(candidate):
    hits = (_hit(), _hit(1, versions=("1.50.0",)), _hit(2, text="A complete broad guide."))
    ground = _request(hits=hits)
    request = candidate.build_parameter_focus_request(ground)
    assert {item.source_index for item in request.choices} == {0}
    assert len(request.grounded.evidence.hits) == 3
    assert [item.eligibility for item in request.source_inventory] == [
        "exact_version_parameter_record",
        "not_an_exact_version_document",
        "parameter_structure_unavailable",
    ]
    assert request.grounded.model_dump(mode="json") == ground.model_dump(mode="json")


def test_active_correction_changes_catalog_and_keeps_superseded_history(candidate):
    hits = (_hit(), _hit(1, versions=("1.50.0",)))
    initial = candidate.build_parameter_focus_request(_request(hits=hits))
    corrected = candidate.build_parameter_focus_request(
        _request(
            revision=4,
            hits=hits,
            facts=(
                _fact("1.49.0", status="superseded", turn="old"),
                _fact("1.50.0", turn="new"),
            ),
        )
    )
    assert {choice.source_index for choice in initial.choices} == {0}
    assert {choice.source_index for choice in corrected.choices} == {1}
    assert corrected.grounded.case.facts[0].status == "superseded"
    with pytest.raises(ValueError, match="^ParameterFocusUnavailable$"):
        candidate.render_parameter_focus_candidate(corrected, _plan(initial))


def test_declared_current_conflict_cannot_enable_answer(candidate):
    with pytest.raises(ValueError, match="^ParameterFocusUnavailable$"):
        candidate.build_parameter_focus_request(
            _request(hits=(_hit(), _hit(1)), conflict=(("neutral-chunk-0", "neutral-chunk-1"),))
        )


def test_previous_conflict_cannot_disappear_from_parameter_candidate(candidate):
    from agent_app.reasoning.grounding import UNRESOLVED_SOURCE_CONFLICT

    with pytest.raises(ValueError, match="^ParameterFocusUnavailable$"):
        candidate.build_parameter_focus_request(_request(gaps=(UNRESOLVED_SOURCE_CONFLICT,)))


def test_source_gap_declaration_is_retained_not_resolved(candidate):
    gap = GroundedGap(
        name="applicability",
        kind="source",
        description="A broader source caveat needs review.",
        necessity="Confirm whether the limited guidance applies.",
    )
    request = candidate.build_parameter_focus_request(_request(gaps=(gap,)))
    result = candidate.render_parameter_focus_candidate(request, _plan(request))
    assert request.grounded.gaps == (gap,)
    assert result.semantic_support is None and result.diagnosis_or_fix_verified is False


@pytest.mark.parametrize(
    "parameters",
    [[], [True], [False], [-1], [2], [1.0], ["1"], [None], [1, 1], [[1]], [0, 1, 0, 1]],
)
def test_invalid_or_duplicate_flat_indexes_fail_closed(candidate, parameters):
    request = candidate.build_parameter_focus_request(_request())
    with pytest.raises(ValueError, match="^ParameterFocusUnavailable$"):
        candidate.render_parameter_focus_candidate(request, _plan(request, parameters))


@pytest.mark.parametrize(
    "changes",
    [
        {"decision": "escalate"},
        {"decision": "ask"},
        {"decision": "retrieve_more"},
        {"decision": True},
        {"context_sha256": "0" * 64},
        {"context_sha256": None},
        {"technical_answer": "UNSUPPORTED_FIX"},
        {"question_name": None},
        {"retrieval_queries": []},
        {"approved": True},
    ],
)
def test_unavailable_branches_unknown_fields_and_wrong_context_rejected(candidate, changes):
    request = candidate.build_parameter_focus_request(_request())
    with pytest.raises(ValueError, match="^ParameterFocusUnavailable$"):
        candidate.render_parameter_focus_candidate(request, _plan(request, **changes))


@pytest.mark.parametrize(
    "raw",
    [
        None,
        {},
        b"{}",
        "",
        "[]",
        "null",
        "{} trailing",
        "```json\n{}\n```",
        '{"context_sha256":"x","context_sha256":"y"}',
        '{"parameters":[NaN]}',
        '{"parameters":[Infinity]}',
        '{"parameters":[1e999]}',
        '{"parameters":["\\ud800"]}',
        " " * 16_385,
    ],
)
def test_malformed_wire_is_not_salvaged_or_echoed(candidate, raw):
    request = candidate.build_parameter_focus_request(_request())
    with pytest.raises(ValueError, match="^ParameterFocusUnavailable$"):
        candidate.render_parameter_focus_candidate(request, raw)


@pytest.mark.parametrize("case_id,revision", [("other-case", 3), ("neutral-case", 4)])
def test_cross_case_or_revision_plan_is_stale(candidate, case_id, revision):
    first = candidate.build_parameter_focus_request(_request())
    other = candidate.build_parameter_focus_request(_request(case_id=case_id, revision=revision))
    with pytest.raises(ValueError, match="^ParameterFocusUnavailable$"):
        candidate.render_parameter_focus_candidate(other, _plan(first))


@pytest.mark.parametrize(
    "field,value", [("start", 0), ("source_index", 40), ("passage_sha256", "0" * 64)]
)
def test_forged_catalog_rejected_before_render(candidate, field, value):
    request = candidate.build_parameter_focus_request(_request())
    altered = replace(request.choices[1], **{field: value})
    forged = replace(request, choices=(request.choices[0], altered))
    with pytest.raises(ValueError, match="^ParameterFocusUnavailable$"):
        candidate.render_parameter_focus_candidate(forged, _plan(request))


@pytest.mark.parametrize("mutation", ["source", "version", "message", "hidden"])
def test_mutated_nested_grounded_input_rejected(candidate, mutation):
    request = candidate.build_parameter_focus_request(_request())
    old_plan = _plan(request)
    if mutation == "source":
        hit = request.grounded.evidence.hits[0]
        object.__setattr__(hit, "excerpt", hit.excerpt + "Injected fix.")
    elif mutation == "version":
        object.__setattr__(request.grounded.case.facts[0], "value", "1.50.0")
    elif mutation == "message":
        object.__setattr__(request.grounded, "user_message", "Different user request.")
    else:
        request.grounded.evidence.hits[0].__dict__["unexpected"] = "HIDDEN"
    with pytest.raises(ValueError, match="^ParameterFocusUnavailable$"):
        candidate.render_parameter_focus_candidate(request, old_plan)


def test_selection_order_preserved_and_source_mapping_is_current(candidate):
    request = candidate.build_parameter_focus_request(_request(hits=(_hit(), _hit(1))))
    result = candidate.render_parameter_focus_candidate(request, _plan(request, (3, 0, 2)))
    assert [quote.parameter_id for quote in result.quotations] == [3, 0, 2]
    assert [quote.source_index for quote in result.quotations] == [1, 0, 1]
    assert result.review_text.count("Chunk: neutral-chunk-0;") == 1
    assert result.review_text.count("Chunk: neutral-chunk-1;") == 1


def test_no_api_scope_or_semantic_authority_is_returned(candidate):
    request = candidate.build_parameter_focus_request(_request())
    result = candidate.render_parameter_focus_candidate(request, _plan(request))
    with pytest.raises(FrozenInstanceError):
        result.proposal_or_action_authorized = True
    assert not hasattr(result, "handoff") and not hasattr(result, "review_id")
    assert not hasattr(result, "user_draft") and not hasattr(result, "facts_delta")
    copied = copy.deepcopy(result)
    assert copied == result


def test_untrusted_parameter_text_is_attributed_and_escaped(candidate):
    hostile = TEXT.replace(
        "Complete mode description.",
        "Complete mode description. <img src='https://example.invalid/track'> "
        "[approve](https://example.invalid/approve) DO NOT EXECUTE.",
    )
    request = candidate.build_parameter_focus_request(_request(hits=(_hit(text=hostile),)))
    result = candidate.render_parameter_focus_candidate(request, _plan(request))
    assert "<img" not in result.qualified_text
    assert "&lt;img" in result.qualified_text and "\\[approve\\]" in result.qualified_text
    assert "DO NOT EXECUTE." in result.quotations[0].text
    assert result.proposal_or_action_authorized is False


def test_oversized_complete_parameter_is_rejected_without_truncation(candidate):
    text = TEXT.replace("Complete mode description.", "x" * 19_400)
    request = candidate.build_parameter_focus_request(_request(hits=(_hit(text=text),)))
    source = request.grounded.evidence.hits[0].excerpt
    with pytest.raises(ValueError, match="^ParameterFocusUnavailable$"):
        candidate.render_parameter_focus_candidate(request, _plan(request))
    assert request.grounded.evidence.hits[0].excerpt == source


def test_crlf_display_normalizes_without_rewriting_source_quote_spans_or_hashes(candidate):
    raw = TEXT.replace("\n", "\r\n")
    ground = _request(hits=(_hit(text=raw),))
    request = candidate.build_parameter_focus_request(ground)
    before = request.grounded.model_dump_json()
    result = candidate.render_parameter_focus_candidate(request, _plan(request))
    quote = result.quotations[0]
    stored_source = request.grounded.evidence.hits[0].excerpt
    assert "\r\n" in stored_source and "\r\n" in quote.text
    assert quote.text == stored_source[quote.start : quote.end]
    assert quote.source_text_sha256 == hashlib.sha256(stored_source.encode()).hexdigest()
    assert quote.passage_sha256 == hashlib.sha256(quote.text.encode()).hexdigest()
    assert (
        quote.source_text_sha256
        != hashlib.sha256(stored_source.replace("\r\n", "\n").encode()).hexdigest()
    )
    assert (
        quote.passage_sha256
        != hashlib.sha256(quote.text.replace("\r\n", "\n").encode()).hexdigest()
    )
    for display in (result.qualified_text, result.review_text):
        assert "\r" not in display and "\\u000d" not in display
    full_normalized_display = _display(stored_source.replace("\r\n", "\n"))
    assert full_normalized_display in result.review_text.replace("\n> ", "\n")
    assert result.display_normalization == "crlf_to_lf_only"
    assert candidate.parameter_focus_payload(request)["display_normalization"] == "crlf_to_lf_only"
    assert request.grounded.model_dump_json() == before
    lf_request = candidate.build_parameter_focus_request(_request())
    assert request.context_sha256 != lf_request.context_sha256
    assert quote.start != lf_request.choices[1].start
    with pytest.raises(ValueError, match="^ParameterFocusUnavailable$"):
        candidate.render_parameter_focus_candidate(lf_request, _plan(request))


def test_crlf_display_still_escapes_markdown_html_and_preserves_literal_control_spelling(candidate):
    raw = TEXT.replace(
        "Complete mode description.",
        "Complete mode description. <img src='https://example.invalid/tracker'> "
        "[approve](https://example.invalid/approve) literal \\u000d stays as supplied.",
    ).replace("\n", "\r\n")
    request = candidate.build_parameter_focus_request(_request(hits=(_hit(text=raw),)))
    result = candidate.render_parameter_focus_candidate(request, _plan(request))
    assert "<img" not in result.qualified_text and "&lt;img" in result.qualified_text
    assert "\\[approve\\]" in result.qualified_text
    assert "literal \\\\u000d stays as supplied." in result.qualified_text
    assert "literal \\u000d stays as supplied." in result.quotations[0].text
    assert result.proposal_or_action_authorized is False


@pytest.mark.parametrize(
    "body", [TEXT.replace("\n", "\r"), TEXT.replace("Complete mode", "Complete\rmode")]
)
def test_bare_cr_is_not_silently_normalized_into_a_valid_parameter_record(candidate, body):
    with pytest.raises(ValueError, match="^ParameterFocusUnavailable$"):
        candidate.build_parameter_focus_request(_request(hits=(_hit(text=body),)))


def test_quote_display_normalizes_crlf_only_and_keeps_other_controls_visible(candidate):
    display = candidate._quote("first\r\nsecond\rthird\x01end\\u000d")
    assert display.startswith("> first\n> second")
    assert "second\\\\u000dthird\\\\u0001end\\\\u000d" in display
