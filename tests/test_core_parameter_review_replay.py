"""Custody of the exposed three-candidate review, never a model-quality test."""

import copy
import importlib
import json
from pathlib import Path

import pytest

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
