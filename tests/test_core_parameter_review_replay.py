"""Custody of the exposed three-candidate review, never a model-quality test."""

import copy
import importlib
import json
from pathlib import Path

import pytest

from agent_app.contracts import CaseState, EvidenceBundle, EvidenceHit, Fact
from agent_app.reasoning.grounding import make_grounded_request

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def replay(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT))
    return importlib.import_module("experiments.core_parameter_review_v1.replay")


def test_all_three_sources_are_inspectable_without_claiming_semantic_success(replay):
    result = replay.run_review_replay()
    assert result["all_eight_old_attempts_and_seven_final_turns_retained"]
    assert result["all_old_candidates_exactly_preserved"]
    assert result["all_review_surface_controls_pass"]
    assert result["provider_calls"] == result["ledger_writes"] == 0
    assert result["human_usefulness"] is result["semantic_support"] is None
    assert not result["runtime_adoption"]
    assert not result["model_quality_improvement_established"]
    assert [(row["turn"], row["parameter"]) for row in result["rows"]] == [
        ("B2", "icon"),
        ("C1", "type"),
        ("C2", "disabled"),
    ]
    assert [row["selected_unit_has_integrity_warning"] for row in result["rows"]] == [
        False,
        True,
        True,
    ]
    for row in result["rows"]:
        assert row["selected_source_has_span_warning"]
        assert all(row["controls"].values())
        assert row["review"]["pending_semantic_review"] == (
            "current_question_relevance",
            "necessary_caveats_outside_selected_unit",
            "user_usefulness",
        )


def test_legacy_inputs_and_outputs_remain_byte_exact_and_sidecar_is_not_input(replay, monkeypatch):
    paths = sorted(replay.ORIGINAL.glob("*.json"))
    original = {path: path.read_bytes() for path in paths}
    read = replay._read
    observed = []

    def inspect(path):
        observed.append(path.name)
        assert path.name != "ai-review-v1.json"
        return read(path)

    monkeypatch.setattr(replay, "_read", inspect)
    assert (
        replay.run_review_replay()["ai_qualitative_sidecar_used_as_driver_or_model_input"] is False
    )
    assert {path: path.read_bytes() for path in paths} == original
    assert set(observed) == {"protocol-v1.json", "replay-fixture-v1.json", "replay-result-v2.json"}


@pytest.mark.parametrize("value", [True, 0.0, "0", 1])
def test_no_coerced_or_nonzero_provider_permission(replay, monkeypatch, value):
    read = replay._read

    def mutate(path):
        raw, item = read(path)
        if path.parent == replay.PACKAGE:
            item["provider_calls_planned"] = value
        return raw, item

    monkeypatch.setattr(replay, "_read", mutate)
    with pytest.raises(ValueError, match="^ParameterInspectionReplayRejected$"):
        replay.run_review_replay()


@pytest.mark.parametrize(
    "name", ["protocol-v1.json", "replay-fixture-v1.json", "replay-result-v2.json"]
)
def test_changed_historical_input_rejected_before_projection(replay, monkeypatch, name):
    read = replay._read

    def mutate(path):
        raw, item = read(path)
        if path.parent == replay.ORIGINAL and path.name == name:
            raw += b" "
        return raw, item

    monkeypatch.setattr(replay, "_read", mutate)
    with pytest.raises(ValueError, match="^ParameterInspectionReplayRejected$"):
        replay.run_review_replay()


def test_unrelated_old_failed_turn_cannot_be_dropped_for_better_review_report(replay, monkeypatch):
    original = replay.run_original_replay

    def omit_failure():
        result = copy.deepcopy(original())
        result["rows"] = [row for row in result["rows"] if row["turn"] != "A3"]
        return result

    monkeypatch.setattr(replay, "run_original_replay", omit_failure)
    with pytest.raises(ValueError, match="^ParameterInspectionReplayRejected$"):
        replay.run_review_replay()


def test_duplicate_json_and_nonfinite_numbers_are_not_custody_evidence(replay, tmp_path):
    for index, value in enumerate((b'{"x":1,"x":2}', b'{"x":NaN}')):
        path = tmp_path / f"bad-{index}.json"
        path.write_bytes(value)
        with pytest.raises(ValueError):
            replay._read(path)


def test_symlinked_protocol_is_not_read_as_a_new_regular_artifact(replay, tmp_path):
    target = tmp_path / "target.json"
    target.write_text(json.dumps({"x": 1}))
    link = tmp_path / "protocol.json"
    link.symlink_to(target)
    with pytest.raises(ValueError):
        replay._read(link)


@pytest.mark.parametrize("prefix,suffix", [("", "\n\n"), ("\n", ""), (" \n", "\r\n ")])
def test_boundary_whitespace_can_explain_span_difference_without_proving_corruption(
    replay, prefix, suffix
):
    normalized = (
        "neutral.widget(mode=False)\n\nNeutral API.\n\nParameters:\n\n"
        "mode: bool; default=False\nComplete definition.\n\nReturns: bool\nA value."
    )
    raw = prefix + normalized + suffix
    supplied_span = f"chars:731:{731 + len(raw)};unit:unicode_codepoint"
    hit = EvidenceHit(
        source_id="neutral-normalization",
        chunk_id="neutral-normalization-chunk",
        source_type="doc",
        source_url="https://example.invalid/neutral",
        source_span=supplied_span,
        applicable_versions=("1.49.0",),
        excerpt=raw,
    )
    # This is the existing public boundary behavior, not a new source repair.
    assert hit.excerpt == normalized and len(raw) > len(hit.excerpt)
    request = make_grounded_request(
        CaseState(
            case_id="neutral-normalization-case",
            facts=(
                Fact(
                    name="streamlit_version",
                    value="1.49.0",
                    source_ref="user:now",
                    turn_id="now",
                ),
            ),
        ),
        "Explain the documented mode parameter.",
        EvidenceBundle(snapshot_id="neutral-snapshot", hits=(hit,)),
    )
    focus = replay.build_parameter_focus_request(request)
    candidate = replay.render_parameter_focus_candidate(
        focus,
        json.dumps(
            {"context_sha256": focus.context_sha256, "decision": "answer", "parameters": [0]}
        ),
    )
    review = replay.build_parameter_review(focus, candidate)
    binding = review.integrity.source_bindings[0]
    assert binding.raw_source_span == supplied_span
    assert binding.excerpt_length == len(normalized)
    assert binding.declared_span_length_matches_excerpt is False
    assert binding.original_file_offset_mapping_verified is False
    assert review.integrity.selected_unit_has_integrity_warning is False
    assert candidate.quotations[0].text in normalized
    assert review.semantic_support is None
