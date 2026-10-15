"""Prospective R4c review binding using synthetic unopened receipt rows only."""

import hashlib
import html
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
CAMPAIGN = "retrieval-relevance-model-v1"
PACKET = "experiments/retrieval_relevance_v1"
PROTOCOL = f"{PACKET}/protocol-v1.json"
PREPARATION = f"{PACKET}/semantic-review-preparation-v1.json"
CRITERIA = "experiments/dev_rag_coverage_v1/protocol-v1.json"
EVIDENCE_REVIEW = "docs/pr55-evidence-review.fa.md"
FIXTURES = ROOT / "data/evaluation/dev-three-v1/cases"
SCENARIO = ROOT / "data/evaluation/dev-three-v1/scenario-review-v1.json"
RUBRIC = ROOT / "docs/evaluation-rubric.md"


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def synthetic_inputs(tmp_path, monkeypatch, campaign=CAMPAIGN, packet=PACKET):
    """No past outputs are relabelled or live request identities registered."""
    root = tmp_path / "synthetic-source"
    names = (
        f"{packet}/protocol-v1.json",
        f"{packet}/semantic-review-preparation-v1.json",
        CRITERIA,
        EVIDENCE_REVIEW,
    )
    for name in names:
        destination = root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
    monkeypatch.setattr(review_workbench, "_ROOT", root)
    monkeypatch.setitem(review_workbench._NATIVE_CRITERIA, campaign, root / CRITERIA)
    fixture_paths = sorted(FIXTURES.glob("*.json"))
    pins = {name: digest(root / name) for name in names}
    pins.update({str(path.relative_to(ROOT)): digest(path) for path in fixture_paths})
    pins[str(SCENARIO.relative_to(ROOT))] = digest(SCENARIO)
    arms = (
        ("native_top5", "candidate_relevance")
        if campaign == CAMPAIGN
        else ("canonical_wire", "compact_wire")
    )
    method = {
        "protocol_id": campaign,
        "experiment_id": "synthetic-unopened-workbench",
        "input_pins": pins,
        "batches": [
            {
                "batch_id": f"synthetic-r{round_number}-{case_id}",
                "jobs": [
                    {
                        "job_id": f"synthetic-r{round_number}:{case_id}:{arm}",
                        "case_id": case_id,
                        "arm": arm,
                        "round": round_number,
                    }
                    for arm in arms
                ],
            }
            for round_number in (1, 2)
            for case_id in ("dev-case-a", "dev-case-b", "dev-case-c")
        ],
    }
    source = root / packet
    dump(source / "live-method-v1.json", method)
    receipt = {
        "protocol_id": campaign,
        "method": method,
        "registration": {"method_sha256": digest(source / "live-method-v1.json")},
        "batches": [],
        "real_index_retrieval": True,
        "held_out_test": False,
        "human_reviewed": False,
        "human_usefulness": None,
        "embedding": "lexical_hash_v1",
    }
    receipt_path = source / "synthetic-unopened-receipt.json"
    dump(receipt_path, receipt)
    return (receipt_path, fixture_paths, SCENARIO, RUBRIC), root


@pytest.fixture
def relevance_inputs(tmp_path, monkeypatch):
    return synthetic_inputs(tmp_path, monkeypatch)


def update_method(inputs, mutate):
    receipt_path = inputs[0]
    value = json.loads(receipt_path.read_bytes())
    mutate(value["method"])
    method_path = receipt_path.parent / "live-method-v1.json"
    dump(method_path, value["method"])
    value["registration"]["method_sha256"] = digest(method_path)
    dump(receipt_path, value)


def update_preparation(inputs, root, mutate):
    path = root / PREPARATION
    value = json.loads(path.read_bytes())
    mutate(value)
    dump(path, value)
    update_method(inputs, lambda method: method["input_pins"].update({PREPARATION: digest(path)}))


def test_relevance_keeps_all_turns_base_gold_draft_scope_and_case_guidance(relevance_inputs):
    inputs, root = relevance_inputs
    before = {str(path): digest(path) for path in (*inputs[1], inputs[2], inputs[3])}
    result = build_workbench(*inputs)
    preparation = json.loads((root / PREPARATION).read_bytes())
    criteria = {
        case["case"]: case
        for case in json.loads((root / CRITERIA).read_bytes())["pre_model_scenarios"]
    }
    scenario = json.loads(SCENARIO.read_bytes())
    assert result["kind"] == "r4c-offline-review-workbench-v1"
    assert result["summary"]["planned_jobs"] == 12
    assert result["summary"]["planned_turns"] == result["summary"]["unvisited"] == 24
    assert result["summary"]["fresh_proposal"] == 0
    for name, source in (
        ("native_criteria", CRITERIA),
        ("native_criteria_preparation", PREPARATION),
        ("native_evidence_review", EVIDENCE_REVIEW),
    ):
        assert result["inputs"][name]["sha256"] == digest(root / source)
    for row in result["rows"]:
        case_id = row["case_id"]
        assert row["actual_index_preregistered_criteria"] == criteria[case_id]
        assert row["supported_topical_guidance"] == preparation["supported_topical_guidance"]
        assert row["topical_guidance_criteria"] == preparation["topical_guidance_criteria"][case_id]
        assert row["scope"]["rubric_id"] == scenario["rubric_id"]
        assert row["scope"]["rubric_sha256"] == digest(RUBRIC)
        assert row["review_template"] is None
        assert row["actual_model_attempts"] == []
        if case_id == "dev-case-a":
            assert (
                row["actual_index_preregistered_amendment"]
                == preparation["case_a_prospective_evidence_amendment"]
            )
        else:
            assert "actual_index_preregistered_amendment" not in row
    assert not result["quality_claim"] and not result["human_reviewed"]
    assert result["human_usefulness"] is None
    assert before == {str(path): digest(path) for path in (*inputs[1], inputs[2], inputs[3])}


def test_relevance_displays_every_case_and_preserves_unvisited_denominators(
    relevance_inputs, tmp_path
):
    inputs, root = relevance_inputs
    output = tmp_path / "review"
    workbench = prepare_workbench(*inputs, output)
    assert load_workbench(output / "workbench.json") == workbench
    text = (output / "review-index.html").read_text()
    preparation = json.loads((root / PREPARATION).read_bytes())
    assert text.count("Preregistered topical guidance criteria for this case") == 24
    for criterion in preparation["topical_guidance_criteria"].values():
        assert text.count(html.escape(criterion)) == 8
    assert "Prospective case-A evidence amendment for this campaign" in text
    report = score_workbench(output / "workbench.json", [])
    assert len(list(output.glob("context-*.json"))) == 24
    assert not list(output.glob("pending-*.json"))
    assert report["summary"] == workbench["summary"]
    assert sum(arm["unvisited"] for arm in report["by_arm"].values()) == 24
    assert report["scores"] == []
    assert not report["quality_claim"] and not report["human_review_authenticated"]


def test_relevance_guidance_is_escaped_in_every_case(relevance_inputs):
    inputs, root = relevance_inputs
    attack = "<script>untrusted & private</script>"
    update_preparation(
        inputs,
        root,
        lambda value: value.update(
            supported_topical_guidance=attack,
            topical_guidance_criteria={case: attack for case in value["topical_guidance_criteria"]},
        ),
    )
    text = _html_index(build_workbench(*inputs))
    assert attack not in text
    assert text.count(html.escape(attack)) == 48


@pytest.mark.parametrize("name", [CRITERIA, PREPARATION, EVIDENCE_REVIEW])
def test_relevance_requires_each_registered_criteria_input_pin(relevance_inputs, name):
    inputs, _ = relevance_inputs
    update_method(inputs, lambda method: method["input_pins"].pop(name))
    with pytest.raises(WorkbenchRejected):
        build_workbench(*inputs)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.update(registered_before_model=False),
        lambda value: value.update(native_criteria_sha256="0" * 64),
        lambda value: value["case_a_prospective_evidence_amendment"].update(review_sha256="0" * 64),
        lambda value: value.pop("supported_topical_guidance"),
        lambda value: value.update(supported_topical_guidance=" "),
        lambda value: value.update(supported_topical_guidance={"not": "text"}),
        lambda value: value.pop("topical_guidance_criteria"),
        lambda value: value["topical_guidance_criteria"].pop("dev-case-b"),
        lambda value: value["topical_guidance_criteria"].update({"unregistered-case": "extra"}),
        lambda value: value["topical_guidance_criteria"].update({"dev-case-c": ""}),
        lambda value: value["topical_guidance_criteria"].update({"dev-case-a": None}),
    ],
    ids=[
        "not_prospective",
        "native_hash",
        "review_hash",
        "missing_definition",
        "empty_definition",
        "invalid_definition",
        "missing_case_criteria",
        "missing_case",
        "unregistered_case",
        "empty_case_criterion",
        "invalid_case_criterion",
    ],
)
def test_relevance_rejects_invalid_preparation_even_when_repinned(relevance_inputs, mutation):
    inputs, root = relevance_inputs
    update_preparation(inputs, root, mutation)
    with pytest.raises(WorkbenchRejected, match="^WorkbenchReceiptMismatch$"):
        build_workbench(*inputs)


@pytest.mark.parametrize("field", ["supported_topical_guidance", "topical_guidance_criteria"])
def test_relevance_guidance_changes_invalidate_preparation_hash_before_scoring(
    relevance_inputs, tmp_path, field
):
    inputs, root = relevance_inputs
    output = tmp_path / "review"
    prepare_workbench(*inputs, output)
    path = root / PREPARATION
    preparation = json.loads(path.read_bytes())
    if field == "supported_topical_guidance":
        preparation[field] += " Changed."
    else:
        preparation[field]["dev-case-b"] += " Changed."
    dump(path, preparation)
    with pytest.raises(WorkbenchRejected, match="^WorkbenchInputChanged$"):
        score_workbench(output / "workbench.json", [])


def test_relevance_exported_guidance_cannot_replace_registered_preparation(
    relevance_inputs, tmp_path
):
    inputs, _ = relevance_inputs
    output = tmp_path / "review"
    workbench = prepare_workbench(*inputs, output)
    workbench["rows"][0]["topical_guidance_criteria"] = "Unregistered replacement."
    dump(output / "workbench.json", workbench)
    with pytest.raises(WorkbenchRejected, match="^WorkbenchReceiptMismatch$"):
        load_workbench(output / "workbench.json")


def test_compact_campaign_never_acquires_relevance_fields_or_html(tmp_path, monkeypatch):
    inputs, root = synthetic_inputs(
        tmp_path,
        monkeypatch,
        campaign="core-compact-plan-model-v1",
        packet="experiments/core_compact_plan_v1",
    )
    result = build_workbench(*inputs)
    scenario = json.loads(SCENARIO.read_bytes())
    assert result["kind"] == "c4h4-offline-review-workbench-v1"
    assert result["summary"]["unvisited"] == 24
    assert "Preregistered topical guidance criteria" not in _html_index(result)
    for row in result["rows"]:
        assert "supported_topical_guidance" not in row
        assert "topical_guidance_criteria" not in row
        assert row["scope"]["rubric_id"] == scenario["rubric_id"]
        assert row["scope"]["rubric_sha256"] == digest(RUBRIC)
    preparation = json.loads(
        (root / "experiments/core_compact_plan_v1/semantic-review-preparation-v1.json").read_bytes()
    )
    assert (
        next(
            row["actual_index_preregistered_amendment"]
            for row in result["rows"]
            if row["case_id"] == "dev-case-a"
        )
        == preparation["case_a_prospective_evidence_amendment"]
    )
