"""Fresh review scopes keep original fixed criteria and all planned turns."""

import importlib.util
import json
from pathlib import Path

import pytest
from test_relevance_workbench import dump, synthetic_inputs, update_method

from agent_app.evaluation.review_workbench import (
    WorkbenchRejected,
    build_workbench,
    load_workbench,
    prepare_workbench,
)

ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = "core-ask-background-model-v1"
PACKET = "experiments/core_ask_background_v1"


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    inputs, root = synthetic_inputs(tmp_path, monkeypatch, campaign=CAMPAIGN, packet=PACKET)

    def single_arm(method):
        for batch in method["batches"]:
            job = batch["jobs"][0]
            job.update(arm="candidate_profile", ask_source_background=True)
            batch["jobs"] = [job]

    update_method(inputs, single_arm)
    receipt = json.loads(inputs[0].read_bytes())
    receipt.update(
        renderer_ask_source_background=True,
        single_paid_model_condition=True,
        no_model_prompt_treatment=True,
    )
    dump(inputs[0], receipt)
    return inputs, root


def test_single_paid_condition_retains_twelve_turns_and_prospective_review(inputs, tmp_path):
    sources, _ = inputs
    result = prepare_workbench(*sources, tmp_path / "review")
    assert result["kind"] == "c4h6-offline-review-workbench-v1"
    assert result["summary"]["planned_jobs"] == 6
    assert result["summary"]["planned_turns"] == result["summary"]["unvisited"] == 12
    assert result["human_usefulness"] is None and not result["quality_claim"]
    for row in result["rows"]:
        assert row["renderer_condition"] == "ask_source_background_on"
        assert "no second model call" in row["comparison_condition"]
        assert row["review_template"] is None
        assert row["topical_guidance_criteria"]
        assert row["actual_index_preregistered_criteria"]["case"] == row["case_id"]
        assert not row["oracle_evidence_condition_matches_actual"]
    assert load_workbench(tmp_path / "review/workbench.json") == result


@pytest.mark.parametrize(
    "field,value",
    [
        ("renderer_ask_source_background", False),
        ("renderer_ask_source_background", "true"),
        ("single_paid_model_condition", False),
        ("no_model_prompt_treatment", False),
    ],
)
def test_mislabelled_actual_renderer_condition_rejected(inputs, field, value):
    sources, _ = inputs
    receipt = json.loads(sources[0].read_bytes())
    receipt[field] = value
    dump(sources[0], receipt)
    with pytest.raises(WorkbenchRejected, match="WorkbenchReceiptMismatch"):
        build_workbench(*sources)


@pytest.mark.parametrize("change", ["renderer", "arm"])
def test_pinned_job_cannot_disagree_with_display_label(inputs, change):
    sources, _ = inputs

    def alter(method):
        job = method["batches"][0]["jobs"][0]
        job["ask_source_background" if change == "renderer" else "arm"] = (
            False if change == "renderer" else "some_other_condition"
        )

    update_method(sources, alter)
    with pytest.raises(WorkbenchRejected, match="WorkbenchReceiptMismatch"):
        build_workbench(*sources)


def replay_module():
    spec = importlib.util.spec_from_file_location(
        "ask_background_readonly_replay", ROOT / "scripts/ask_background_render_replay.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_same_actual_plans_isolate_renderer_and_preserve_every_failure():
    result = replay_module().build_report(
        ROOT / "experiments/retrieval_relevance_v1/model-live-receipt-v1.json"
    )
    assert result["planned_turns"] == 24
    assert result["turn_statuses"] == {
        "fresh_proposal": 22,
        "no_fresh_proposal": 1,
        "unvisited": 1,
    }
    assert result["fresh_background_additions"] == 3
    assert result["background_additions_by_case"] == {"dev-case-a": 3}
    assert result["new_provider_calls"] == 0 and not result["model_quality_claim"]
    assert result["human_usefulness"] is None
    assert len(result["actual_attempts_including_unparsed"]) == 27
    for row in result["turns"]:
        if row["status"] == "fresh_proposal":
            assert row["actual_analysis_reconstructed"] and row["non_draft_fields_equal"]


def test_replay_rejects_changed_original_receipt(tmp_path):
    source = ROOT / "experiments/retrieval_relevance_v1/model-live-receipt-v1.json"
    altered = tmp_path / "altered.json"
    receipt = json.loads(source.read_bytes())
    receipt["method"]["batches"].pop()
    dump(altered, receipt)
    with pytest.raises(AssertionError):
        replay_module().build_report(altered)
