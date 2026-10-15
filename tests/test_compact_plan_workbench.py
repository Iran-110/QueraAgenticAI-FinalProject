"""Prospective C4h4 review binding using synthetic unopened receipt rows only."""

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from agent_app.evaluation import review_workbench
from agent_app.evaluation.review_workbench import (
    WorkbenchRejected,
    _html_index,
    build_workbench,
    load_workbench,
    prepare_workbench,
    score_workbench,
)

ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = "core-compact-plan-model-v1"
PROTOCOL = "experiments/core_compact_plan_v1/protocol-v1.json"
PREPARATION = "experiments/core_compact_plan_v1/semantic-review-preparation-v1.json"
CRITERIA = "experiments/dev_rag_coverage_v1/protocol-v1.json"
EVIDENCE_REVIEW = "docs/pr55-evidence-review.fa.md"
FIXTURES = ROOT / "data/evaluation/dev-three-v1/cases"
SCENARIO = ROOT / "data/evaluation/dev-three-v1/scenario-review-v1.json"
RUBRIC = ROOT / "docs/evaluation-rubric.md"


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def compact_inputs(tmp_path, monkeypatch):
    """No past outputs are relabelled as new model evidence or registered live slots."""
    root = tmp_path / "synthetic-source"
    for name in (PROTOCOL, PREPARATION, CRITERIA, EVIDENCE_REVIEW):
        destination = root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
    monkeypatch.setattr(review_workbench, "_ROOT", root)
    monkeypatch.setitem(review_workbench._NATIVE_CRITERIA, CAMPAIGN, root / CRITERIA)
    fixture_paths = sorted(FIXTURES.glob("*.json"))
    pins = {
        name: digest(root / name) for name in (PROTOCOL, PREPARATION, CRITERIA, EVIDENCE_REVIEW)
    }
    pins.update({str(path.relative_to(ROOT)): digest(path) for path in fixture_paths})
    pins[str(SCENARIO.relative_to(ROOT))] = digest(SCENARIO)
    batches = []
    for round_number in (1, 2):
        for case_id in ("dev-case-a", "dev-case-b", "dev-case-c"):
            batches.append(
                {
                    "batch_id": f"synthetic-r{round_number}-{case_id}",
                    "jobs": [
                        {
                            "job_id": f"synthetic-r{round_number}:{case_id}:{arm}",
                            "case_id": case_id,
                            "arm": arm,
                            "round": round_number,
                        }
                        for arm in ("canonical_wire", "compact_wire")
                    ],
                }
            )
    method = {
        "protocol_id": CAMPAIGN,
        "experiment_id": "synthetic-unopened-compact-workbench",
        "input_pins": pins,
        "batches": batches,
    }
    packet = root / "experiments/core_compact_plan_v1"
    dump(packet / "live-method-v1.json", method)
    receipt = {
        "protocol_id": CAMPAIGN,
        "method": method,
        "registration": {"method_sha256": digest(packet / "live-method-v1.json")},
        "batches": [],
        "real_index_retrieval": True,
        "held_out_test": False,
        "human_reviewed": False,
        "human_usefulness": None,
        "embedding": "lexical_hash_v1",
    }
    receipt_path = packet / "synthetic-unopened-receipt.json"
    dump(receipt_path, receipt)
    return (receipt_path, fixture_paths, SCENARIO, RUBRIC), root


def update_method(inputs, mutate):
    receipt_path = inputs[0]
    value = json.loads(receipt_path.read_bytes())
    mutate(value["method"])
    method_path = receipt_path.parent / "live-method-v1.json"
    dump(method_path, value["method"])
    value["registration"]["method_sha256"] = digest(method_path)
    dump(receipt_path, value)


def test_compact_campaign_keeps_base_criteria_gold_and_every_unopened_turn(compact_inputs):
    inputs, root = compact_inputs
    before = {str(path): digest(path) for path in (*inputs[1], inputs[2], inputs[3])}
    result = build_workbench(*inputs)
    criteria = {
        case["case"]: case
        for case in json.loads((root / CRITERIA).read_bytes())["pre_model_scenarios"]
    }
    preparation = json.loads((root / PREPARATION).read_bytes())
    assert result["kind"] == "c4h4-offline-review-workbench-v1"
    assert result["summary"]["planned_jobs"] == 12
    assert result["summary"]["planned_turns"] == result["summary"]["unvisited"] == 24
    assert result["summary"]["fresh_proposal"] == 0
    assert result["inputs"]["native_criteria"]["sha256"] == digest(ROOT / CRITERIA)
    assert result["inputs"]["native_criteria_preparation"]["sha256"] == digest(root / PREPARATION)
    assert result["inputs"]["native_evidence_review"]["sha256"] == digest(root / EVIDENCE_REVIEW)
    scenario = json.loads(SCENARIO.read_bytes())
    for row in result["rows"]:
        assert row["actual_index_preregistered_criteria"] == criteria[row["case_id"]]
        assert row["scope"]["rubric_id"] == scenario["rubric_id"]
        assert row["scope"]["rubric_sha256"] == digest(RUBRIC)
        assert row["review_template"] is None
        assert row["actual_model_attempts"] == []
        if row["case_id"] == "dev-case-a":
            assert (
                row["actual_index_preregistered_amendment"]
                == preparation["case_a_prospective_evidence_amendment"]
            )
        else:
            assert "actual_index_preregistered_amendment" not in row
    assert not result["quality_claim"] and not result["human_reviewed"]
    assert result["human_usefulness"] is None
    assert before == {str(path): digest(path) for path in (*inputs[1], inputs[2], inputs[3])}


def test_compact_amendment_is_displayed_escaped_and_bound_on_reload(compact_inputs, tmp_path):
    inputs, _ = compact_inputs
    output = tmp_path / "review"
    result = prepare_workbench(*inputs, output)
    assert load_workbench(output / "workbench.json") == result
    text = (output / "review-index.html").read_text()
    assert "Prospective case-A evidence amendment for this campaign" in text
    assert "actually supplied official excerpt" in text
    assert "original prior gold/receipts are not rewritten" in text
    row = next(row for row in result["rows"] if row["case_id"] == "dev-case-a")
    row["actual_index_preregistered_amendment"]["criterion"] = "<script>private attack</script>"
    assert "<script>private attack</script>" not in _html_index(result)
    assert "&lt;script&gt;private attack&lt;/script&gt;" in _html_index(result)


@pytest.mark.parametrize("name", [CRITERIA, PREPARATION, EVIDENCE_REVIEW])
def test_compact_preparation_requires_each_registered_criteria_input_pin(compact_inputs, name):
    inputs, _ = compact_inputs
    update_method(inputs, lambda method: method["input_pins"].pop(name))
    with pytest.raises(WorkbenchRejected):
        build_workbench(*inputs)


@pytest.mark.parametrize(
    "mutation",
    ["not_prospective", "native_path", "native_hash", "review_path", "review_hash"],
)
def test_compact_amendment_must_bind_the_registered_native_criteria_and_review(
    compact_inputs, mutation
):
    inputs, root = compact_inputs
    preparation_path = root / PREPARATION
    preparation = json.loads(preparation_path.read_bytes())
    if mutation == "not_prospective":
        preparation["registered_before_model"] = False
    elif mutation == "native_path":
        preparation["native_criteria_path"] = "data/evaluation/dev-three-v1/scenario-review-v1.json"
    elif mutation == "native_hash":
        preparation["native_criteria_sha256"] = "0" * 64
    elif mutation == "review_path":
        preparation["case_a_prospective_evidence_amendment"]["review_path"] = "docs/unregistered.md"
    else:
        preparation["case_a_prospective_evidence_amendment"]["review_sha256"] = "0" * 64
    dump(preparation_path, preparation)
    update_method(
        inputs,
        lambda method: method["input_pins"].update({PREPARATION: digest(preparation_path)}),
    )
    with pytest.raises(WorkbenchRejected, match="^WorkbenchReceiptMismatch$"):
        build_workbench(*inputs)


@pytest.mark.parametrize(
    "input_name", ["native_criteria", "native_criteria_preparation", "native_evidence_review"]
)
def test_compact_score_rejects_changed_registered_criteria_before_any_review(
    compact_inputs, tmp_path, input_name
):
    inputs, _ = compact_inputs
    output = tmp_path / "review"
    workbench = prepare_workbench(*inputs, output)
    path = Path(workbench["inputs"][input_name]["path"])
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(WorkbenchRejected, match="^WorkbenchInputChanged$"):
        score_workbench(output / "workbench.json", [])


def test_compact_workbench_keeps_unvisited_denominators_without_creating_judgments(
    compact_inputs, tmp_path
):
    inputs, _ = compact_inputs
    output = tmp_path / "review"
    workbench = prepare_workbench(*inputs, output)
    report = score_workbench(output / "workbench.json", [])
    assert len(list(output.glob("context-*.json"))) == 24
    assert not list(output.glob("pending-*.json"))
    assert report["summary"] == workbench["summary"]
    assert sum(arm["unvisited"] for arm in report["by_arm"].values()) == 24
    assert report["scores"] == []
    assert report["quality_claim"] is False
    assert report["human_review_authenticated"] is False


def test_previous_campaign_never_receives_the_new_amendment():
    result = build_workbench(
        ROOT / "experiments/core_source_capacity_v1/model-live-receipt-v1.json",
        sorted(FIXTURES.glob("*.json")),
        SCENARIO,
        RUBRIC,
    )
    assert result["kind"] == "c4h3-offline-review-workbench-v1"
    assert "native_criteria_preparation" not in result["inputs"]
    assert "native_evidence_review" not in result["inputs"]
    assert all("actual_index_preregistered_amendment" not in row for row in result["rows"])
    assert "Prospective case-A evidence amendment" not in _html_index(result)
