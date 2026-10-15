"""Offline advisory evidence controls; passing is not semantic/model quality.

All constructed documents are authored neutral development data. The retained
Enum inventory is a traceability control, never a production case/source rule.
"""

import copy
import hashlib
import json
import math
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from agent_app.contracts import CaseState, EvidenceBundle, EvidenceHit, Fact, GroundedGap
from agent_app.reasoning.claim_plan import build_claim_request, render_claim_plan
from agent_app.reasoning.evidence_selection import (
    inspect_claim_selection,
    rank_evidence_units,
    suggest_evidence_units,
)
from agent_app.reasoning.grounding import GroundingRejected, make_grounded_request

ROOT = Path(__file__).resolve().parents[1]


def _fact(name, value, *, status="active", provenance="user", turn="current"):
    return Fact(
        name=name,
        value=value,
        source_ref=f"{provenance}:{turn}",
        turn_id=turn,
        status=status,
        provenance_kind=provenance,
    )


def _hit(index, text, *, versions=(), source_id=None, **changes):
    return EvidenceHit(
        **{
            "chunk_id": f"neutral-chunk-{index}",
            "source_id": source_id or f"neutral-document-{index}",
            "source_url": f"https://example.invalid/document/{index}",
            "source_type": "doc",
            "applicable_versions": versions,
            "excerpt": text,
            **changes,
        }
    )


def _request(
    hits,
    *,
    message="Widget persistence",
    facts=(),
    gaps=(),
    unknowns=(),
    revision=3,
    mode="sections",
):
    case = CaseState(
        case_id="neutral-selection-case",
        case_revision=revision,
        facts=tuple(facts),
        unknowns=tuple(unknowns),
    )
    bundle = EvidenceBundle(snapshot_id="neutral-selection-snapshot", hits=tuple(hits))
    return build_claim_request(
        make_grounded_request(case, message, bundle, gaps=tuple(gaps)), block_mode=mode
    )


def _plan(request, **changes):
    return {
        "context_sha256": request.context_sha256,
        "decision": "answer",
        "passages": [[0, 0]],
        "user_facts": [],
        "question_name": None,
        "retrieval_queries": [],
        **changes,
    }


def _observed_pairs(request):
    return [(h.source_index, h.block_index) for h in rank_evidence_units(request)]


def test_concrete_component_text_beats_unrelated_true_document_without_claiming_entailment():
    req = _request(
        [
            _hit(0, "# Glaciers\n\nIce shelves retreat during warm weather."),
            _hit(1, "# Widget persistence\n\nWidget persistence retains a selected value."),
        ]
    )
    hints = rank_evidence_units(req)
    assert hints[0].source_index == 1 and hints[0].overlap > hints[1].overlap
    shortlist = suggest_evidence_units(req)
    assert shortlist.passages == ((1, 0),)
    assert shortlist.semantic_support is None and shortlist.human_review_required is True


def test_only_active_USER_fact_values_contribute_from_the_fact_table():
    req = _request(
        [
            _hit(0, "# Quartz\n\nQuartz minerals form crystals."),
            _hit(1, "# Otters\n\nOtters swim beside riverbanks."),
            _hit(2, "# Tundra\n\nTundra temperatures remain low."),
        ],
        message="Please investigate.",
        facts=[
            _fact("component", "quartz", status="superseded", turn="old"),
            _fact("component", "otters"),
            _fact("model_inference", "tundra", provenance="evidence"),
        ],
    )
    scores = {h.source_index: h.overlap for h in rank_evidence_units(req)}
    assert scores[1] > 0 and scores[0] == scores[2] == 0
    assert suggest_evidence_units(req).passages == ((1, 0),)


def test_fact_names_source_references_and_unknown_names_are_not_query_content():
    req = _request(
        [_hit(0, "Quartz mineral deposits.")],
        message="Investigate.",
        unknowns=("quartz",),
        facts=[
            Fact(
                name="quartz",
                value="otter",
                source_ref="user:quartz",
                turn_id="quartz",
            )
        ],
    )
    assert rank_evidence_units(req)[0].overlap == 0


def test_raw_message_history_can_still_supply_words_and_is_not_semantically_parsed():
    """Exclude old fact rows, without pretending arbitrary history prose is understood."""
    req = _request(
        [_hit(0, "Quartz minerals."), _hit(1, "Otter habitats.")],
        message="Historical report mentioned quartz; current structured facts are separate.",
        facts=[
            _fact("component", "quartz", status="superseded", turn="old"),
            _fact("component", "otter"),
        ],
    )
    # A caller's historical message text still contributes lexical terms. It
    # cannot update fact authority or turn this observation into semantic truth.
    assert all(h.overlap > 0 for h in rank_evidence_units(req))
    observed = inspect_claim_selection(req, _plan(req))
    assert observed["semantic_support"] is None and observed["human_review_required"]
    assert req.grounded.case.facts[0].status == "superseded"


def test_source_identifiers_urls_spans_and_commits_cannot_manufacture_overlap():
    plain = _request([_hit(0, "Glaciers retreat slowly.")], message="Quartz widget")
    decorated = _request(
        [
            _hit(
                0,
                "Glaciers retreat slowly.",
                source_id="quartz-widget",
                chunk_id="quartz-widget",
                source_url="https://example.invalid/quartz-widget",
                source_span="Quartz widget",
                source_commit="quartz-widget",
                score=1.0,
                score_kind="Quartz widget",
            )
        ],
        message="Quartz widget",
    )
    assert plain.context_sha256 != decorated.context_sha256
    assert rank_evidence_units(plain)[0].overlap == rank_evidence_units(decorated)[0].overlap == 0
    assert suggest_evidence_units(decorated).passages == ()


@pytest.mark.parametrize("current_version", [None, "2.4", "2.4.0"])
def test_unknown_metadata_and_explicit_other_version_have_separate_current_USER_policies(
    current_version,
):
    facts = [] if current_version is None else [_fact("streamlit_version", current_version)]
    req = _request(
        [
            _hit(0, "Widget persistence.", versions=()),
            _hit(1, "Widget persistence.", versions=("2.4",)),
        ],
        facts=facts,
    )
    scopes = {h.source_index: h.version_scope for h in rank_evidence_units(req)}
    shortlist = suggest_evidence_units(req)
    assert scopes[0] == "unconfirmed"
    if current_version is None:
        assert scopes[1] == "unconfirmed" and shortlist.passages == ((0, 0), (1, 0))
    elif current_version == "2.4":
        assert scopes[1] == "exact_metadata_match" and shortlist.passages == ((0, 0), (1, 0))
    else:
        assert scopes[1] == "historical_or_other_version"
        assert shortlist.passages == ((0, 0),) and shortlist.historical == ((1, 0),)
    assert shortlist.semantic_support is None and shortlist.human_review_required
    assert len(req.grounded.evidence.hits) == 2  # Original historical source is not deleted.


def test_numeric_version_strings_cannot_supply_lexical_support_or_scope_authority():
    req = _request(
        [_hit(0, "# Release 9.7.1\n\nOrdinary document body.", versions=("9.7.1",))],
        message="9.7.1",
        facts=[_fact("streamlit_version", "2.4")],
    )
    hint = rank_evidence_units(req)[0]
    assert hint.overlap == hint.matched_terms == 0
    assert hint.version_scope == "historical_or_other_version"
    assert suggest_evidence_units(req).passages == ()


def test_budget_counts_whole_UTF8_units_including_complete_condition_and_code_fence():
    req = _request(
        [
            _hit(
                0,
                "# Widget persistence\n\nWidget persistence needs a stable key.\n\n"
                "```python\nprint('🧪 ستون')\n\nprint('keep the entire fence')\n```\n\n"
                "If the file changes, start a new session.",
            )
        ]
    )
    excerpt = req.grounded.evidence.hits[0].excerpt
    budget = len(excerpt.encode("utf-8"))
    assert budget > len(excerpt)
    accepted = suggest_evidence_units(req, passage_utf8_budget=budget)
    assert accepted.passages == ((0, 0),) and accepted.passage_utf8_bytes == budget
    rejected = suggest_evidence_units(req, passage_utf8_budget=budget - 1)
    assert rejected.passages == () and rejected.oversized == ((0, 0),)
    assert rejected.passage_utf8_bytes == 0
    assert req.grounded.evidence.hits[0].excerpt == excerpt
    assert req.blocks[0][0].end == len(excerpt)


def test_whole_oversize_unit_is_skipped_without_suppressing_smaller_useful_unit():
    req = _request(
        [
            _hit(0, "# Widget persistence\n\n" + "Widget persistence " * 60),
            _hit(1, "Widget persistence remains qualified."),
        ]
    )
    small_size = len(req.grounded.evidence.hits[1].excerpt.encode())
    shortlist = suggest_evidence_units(req, passage_utf8_budget=small_size)
    assert shortlist.passages == ((1, 0),) and (0, 0) in shortlist.oversized
    assert shortlist.passage_utf8_bytes == small_size


@pytest.mark.parametrize("limit", [True, False, 0, -1, 7, 1.0, "2", None])
def test_max_units_has_strict_one_to_six_bounds(limit):
    with pytest.raises(ValueError, match="InvalidEvidenceShortlistLimit"):
        suggest_evidence_units(_request([_hit(0, "Widget persistence.")]), max_units=limit)


@pytest.mark.parametrize("budget", [True, False, 0, -1, 6000.0, "6000", None])
def test_raw_byte_budget_requires_positive_integer(budget):
    with pytest.raises(ValueError, match="InvalidEvidenceShortlistBudget"):
        suggest_evidence_units(
            _request([_hit(0, "Widget persistence.")]), passage_utf8_budget=budget
        )


def test_default_shortlist_is_not_quote_all_and_six_unit_ceiling_is_real():
    req = _request([_hit(i, "Widget persistence needs a stable key.") for i in range(9)])
    assert suggest_evidence_units(req).passages == ((0, 0), (1, 0))
    assert suggest_evidence_units(req, max_units=6).passages == tuple((i, 0) for i in range(6))
    assert len(req.grounded.evidence.hits) == 9


def test_complementary_chunks_from_same_source_are_not_dropped_for_source_diversity():
    req = _request(
        [
            _hit(
                0,
                "# Widget persistence\n\nWidget persistence needs a stable key.",
                source_id="one-guide",
            ),
            _hit(
                1,
                "# Widget persistence caveat\n\nWidget persistence changes after editing.",
                source_id="one-guide",
            ),
            _hit(2, "# Glaciers\n\nIce melts in warm weather."),
        ]
    )
    shortlist = suggest_evidence_units(req)
    assert set(shortlist.passages) == {(0, 0), (1, 0)}
    assert req.grounded.evidence.hits[0].source_id == req.grounded.evidence.hits[1].source_id


def test_heading_only_match_does_not_displace_substantive_match_or_earn_an_answer():
    req = _request(
        [
            _hit(0, "# Widget persistence\n\n## Stable widget persistence"),
            _hit(1, "# Widget persistence\n\nA stable key is required for widget persistence."),
        ]
    )
    hints = {h.source_index: h for h in rank_evidence_units(req)}
    assert not hints[0].has_body and hints[1].has_body
    assert suggest_evidence_units(req).passages == ((1, 0),)
    observed = inspect_claim_selection(req, _plan(req))
    assert "heading_or_separator_only" in observed["warnings"]
    assert observed["semantic_support"] is None
    with pytest.raises(GroundingRejected, match="invalid_grounded_plan"):
        render_claim_plan(req, _plan(req))


@pytest.mark.parametrize(
    "changed", ["revision", "case", "message", "source_text", "source_metadata"]
)
def test_old_plan_is_not_rebound_to_new_revision_source_or_message(changed):
    old = _request([_hit(0, "Widget persistence.")], facts=[_fact("streamlit_version", "2.4")])
    grounded = old.grounded
    case, message, hits = grounded.case, grounded.user_message, grounded.evidence.hits
    if changed == "revision":
        case = case.model_copy(update={"case_revision": case.case_revision + 1})
    elif changed == "case":
        case = case.model_copy(update={"case_id": "different-case"})
    elif changed == "message":
        message = "An explicitly corrected widget report."
    elif changed == "source_text":
        hits = (hits[0].model_copy(update={"excerpt": "New source body under same identifier."}),)
    else:
        hits = (hits[0].model_copy(update={"applicable_versions": ("2.4",)}),)
    fresh = build_claim_request(
        make_grounded_request(case, message, grounded.evidence.model_copy(update={"hits": hits})),
        block_mode="sections",
    )
    with pytest.raises(GroundingRejected, match="grounded_context_mismatch"):
        inspect_claim_selection(fresh, _plan(old))


def test_forged_unit_spans_fail_before_ranking_or_shortlisting():
    req = _request([_hit(0, "Widget persistence.")])
    span = req.blocks[0][0].model_copy(update={"end": req.blocks[0][0].end - 1})
    forged = req.model_copy(update={"blocks": ((span,),)})
    for operation in (rank_evidence_units, suggest_evidence_units):
        with pytest.raises(GroundingRejected, match="grounded_context_mismatch"):
            operation(forged)


@pytest.mark.parametrize("selection", [[[1, 0]], [[0, 999]]])
def test_out_of_current_source_bounds_are_still_terminal_binding_failures(selection):
    req = _request([_hit(0, "Widget persistence.")])
    with pytest.raises(GroundingRejected, match="grounded_source_mismatch"):
        inspect_claim_selection(req, _plan(req, passages=selection))


def test_only_current_active_USER_fact_indexes_are_inspectable():
    req = _request(
        [_hit(0, "Widget persistence.")],
        facts=[
            _fact("component", "retired", status="superseded", turn="old"),
            _fact("component", "widget"),
            _fact("theory", "inference", provenance="evidence"),
        ],
    )
    assert inspect_claim_selection(req, _plan(req, user_facts=[0]))["human_review_required"]
    with pytest.raises(GroundingRejected, match="grounded_context_mismatch"):
        inspect_claim_selection(req, _plan(req, user_facts=[1]))


def test_canonical_ask_survives_inspection_even_with_unrelated_review_background():
    question = "Which runtime module is loaded by that command?"
    gap = GroundedGap(
        name="runtime_details",
        kind="user",
        description="Runtime identity was not supplied.",
        necessity="The answer changes the next investigation.",
        question=question,
    )
    req = _request([_hit(0, "Glaciers retreat slowly.")], gaps=[gap])
    raw = _plan(req, decision="ask", question_name=gap.name)
    before = copy.deepcopy(raw)
    observed = inspect_claim_selection(req, raw)
    rendered = render_claim_plan(req, raw)
    assert raw == before and observed["decision_unchanged"] == "ask"
    assert rendered.user_draft == rendered.next_question == question
    assert rendered.missing_info == (gap.name,)
    assert observed["semantic_support"] is None and observed["human_review_required"]
    assert "no_lexical_signal_not_proof_of_irrelevance" in observed["warnings"]


def test_high_overlap_false_positive_is_not_mislabeled_supported_or_useful():
    req = _request(
        [
            _hit(
                0,
                "# Widget persistence\n\nWidget persistence widget persistence: this is a fictional poem, not technical guidance.",
            )
        ]
    )
    assert suggest_evidence_units(req).passages == ((0, 0),)
    observed = inspect_claim_selection(req, _plan(req))
    assert observed["semantic_support"] is None and observed["human_review_required"]
    assert "supported" not in observed and "relevant" not in observed


def test_synonym_false_negative_remains_reviewable_not_proven_irrelevant():
    # Authored semantic counterexample: superficially different terms can refer
    # to the same symptom. No automated quality label is inferred here.
    req = _request(
        [_hit(0, "Unresponsive programs may wait indefinitely.")], message="Application freezes"
    )
    hint = rank_evidence_units(req)[0]
    assert hint.overlap == 0 and suggest_evidence_units(req).passages == ()
    observed = inspect_claim_selection(req, _plan(req))
    assert observed["decision_unchanged"] == "answer"
    assert observed["semantic_support"] is None and observed["human_review_required"]
    assert observed["warnings"] == ["no_lexical_signal_not_proof_of_irrelevance"]


def test_full_inputs_plans_and_frozen_advisory_results_are_immutable():
    req = _request([_hit(0, "Widget persistence.")])
    before = req.model_dump_json()
    raw = _plan(req)
    raw_before = copy.deepcopy(raw)
    ranked = rank_evidence_units(req)
    shortlist = suggest_evidence_units(req)
    inspect_claim_selection(req, raw)
    assert req.model_dump_json() == before and raw == raw_before
    with pytest.raises(FrozenInstanceError):
        shortlist.semantic_support = True
    with pytest.raises(FrozenInstanceError):
        ranked[0].overlap = 1.0
    assert math.isfinite(ranked[0].overlap) and 0 <= ranked[0].overlap <= 1


def test_zero_terms_and_empty_bundle_produce_no_forced_source_or_answer():
    for hits in ([], [_hit(0, "123 456")]):
        req = _request(hits, message="123 456")
        assert suggest_evidence_units(req).passages == ()
        assert all(h.overlap == 0 and math.isfinite(h.overlap) for h in rank_evidence_units(req))


def _pointer(value, pointer):
    for item in pointer.strip("/").split("/"):
        value = value[int(item)] if isinstance(value, list) else value[item]
    return value


def test_observed_Enum_failure_inventory_traces_original_selection_and_omitted_context():
    """Audit provenance of the exposed regression seed; not a model-quality test."""
    path = ROOT / "experiments/core_evidence_selection_v1/failure-inventory-v1.json"
    inventory = json.loads(path.read_text())
    assert inventory["provenance"]["all_labels_are_posthoc_authored_exposed_development_judgments"]
    assert inventory["provenance"]["held_out_test"] is False
    row = next(
        r for r in inventory["observed_inventory"] if r.get("snapshot_id") == "enum-guide:initial"
    )
    reference = row["original_receipt"]
    original_bytes = (ROOT / reference["path"]).read_bytes()
    assert hashlib.sha256(original_bytes).hexdigest() == reference["sha256"]
    original = json.loads(original_bytes)
    retained = _pointer(original, row["original_plan_json_pointer"])
    assert retained == row["original_plan"]
    assert retained["passages"] == [[2, 5], [1, 1]]
    omitted = row["available_but_omitted_review_context"]
    assert {(q["source_index"], q["block_index"]) for q in omitted} == {(1, 2), (1, 10)}
    for quote in row["selected_passages"] + omitted:
        assert quote["end"] - quote["start"] == len(quote["text"])
        assert hashlib.sha256(quote["text"].encode()).hexdigest() == quote["text_sha256"]
    assert row["authored_semantic_label"] == "heading_only_plus_missing_caveat"


def test_relevant_complete_section_does_not_expand_into_unrelated_sibling_or_whole_record():
    req = _request(
        [
            _hit(
                0,
                "## Widget persistence\n\nWidget persistence needs a stable key.\n\n"
                "### Qualification\n\nEditing the definition may require a new session.\n\n"
                "## Glacier research\n\n" + "Ice shelves and marine sediment. " * 80,
            )
        ]
    )
    shortlist = suggest_evidence_units(req)
    assert shortlist.passages == ((0, 0),)
    span = req.blocks[0][0]
    text = req.grounded.evidence.hits[0].excerpt[span.start : span.end]
    assert "Qualification" in text and "new session" in text
    assert "Glacier research" not in text and "marine sediment" not in text
    assert len(text) < len(req.grounded.evidence.hits[0].excerpt)
    assert shortlist.semantic_support is None  # Section shape is not a semantic verdict.


def test_raw_passage_budget_does_not_claim_to_bound_rendered_draft_or_prompt():
    req = _request([_hit(0, "Widget persistence.")])
    raw_size = len(req.grounded.evidence.hits[0].excerpt.encode())
    shortlist = suggest_evidence_units(req, passage_utf8_budget=raw_size)
    assert shortlist.passages == ((0, 0),)
    rendered = render_claim_plan(req, _plan(req))
    # Source links, USER scope and core attribution add content. The caller must
    # still apply the real render/input limits; raw budget is not that limit.
    assert shortlist.passage_utf8_bytes == raw_size
    assert len(rendered.user_draft.encode()) > raw_size
    assert shortlist.semantic_support is None and shortlist.human_review_required
