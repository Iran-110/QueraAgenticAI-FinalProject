"""Historical rubric scope controls using exposed dev receipts; no clients."""

import hashlib
import json
from pathlib import Path

import pytest

from agent_app.evaluation.review_workbench import (
    WorkbenchRejected,
    build_workbench,
    prepare_workbench,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = sorted((ROOT / "data/evaluation/dev-three-v1/cases").glob("*.json"))
SCENARIO = ROOT / "data/evaluation/dev-three-v1/scenario-review-v1.json"
RUBRIC = ROOT / "docs/evaluation-rubric.md"
RUBRIC_ID = "e2-core-review-draft-v1"
RUBRIC_SHA256 = "b68526f6d6aadac50b5eaa670948e4acfdcae801fe271e91ccf111fa2c03f5c8"
CAMPAIGN_FOLDERS = (
    "dev_rag_coverage_v1",
    "core_repeat_repair_v1",
    "core_source_capacity_v1",
    "core_compact_plan_v1",
    "retrieval_relevance_v1",
    "core_ask_background_v1",
    "core_resource_guidance_v1",
)
GOLD_POSITIONS = [(path.name, position) for path in FIXTURES for position in range(2)]


def receipt(folder="dev_rag_coverage_v1"):
    return ROOT / "experiments" / folder / "model-live-receipt-v1.json"


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def assert_rejected_before_output(
    tmp_path, *, packet=None, fixtures=None, scenario=None, rubric=None
):
    output = tmp_path / "review-output"
    with pytest.raises(WorkbenchRejected, match="^WorkbenchScopeMismatch$") as error:
        prepare_workbench(
            packet or receipt(),
            fixtures or FIXTURES,
            scenario or SCENARIO,
            rubric or RUBRIC,
            output,
        )
    assert error.value.code == "WorkbenchScopeMismatch"
    assert not output.exists()


@pytest.mark.parametrize("folder", CAMPAIGN_FOLDERS)
def test_registered_campaign_retains_the_original_rubric_scope(folder):
    result = build_workbench(receipt(folder), FIXTURES, SCENARIO, RUBRIC)
    assert result["inputs"]["rubric"]["sha256"] == RUBRIC_SHA256
    assert result["rows"]
    for row in result["rows"]:
        assert row["scope"]["rubric_id"] == RUBRIC_ID
        assert row["scope"]["rubric_sha256"] == RUBRIC_SHA256
        if row["review_template"] is not None:
            assert row["review_template"]["scope"] == row["scope"]


@pytest.mark.parametrize("folder", CAMPAIGN_FOLDERS)
def test_same_registered_rubric_bytes_at_another_path_are_accepted(tmp_path, folder):
    copied = tmp_path / "same-rubric.md"
    copied.write_bytes(RUBRIC.read_bytes())
    result = build_workbench(receipt(folder), FIXTURES, SCENARIO, copied)
    assert result["inputs"]["rubric"] == {
        "path": str(copied.resolve()),
        "sha256": RUBRIC_SHA256,
    }
    assert all(row["scope"]["rubric_id"] == RUBRIC_ID for row in result["rows"])


@pytest.mark.parametrize("folder", CAMPAIGN_FOLDERS)
@pytest.mark.parametrize("replacement", ["v1", "same_id_changed_bytes", "malformed_bytes"])
def test_other_rubric_bytes_cannot_relabel_historical_campaigns(tmp_path, folder, replacement):
    supplied = tmp_path / "supplied-rubric.md"
    if replacement == "v1":
        supplied.write_bytes((ROOT / "docs/evaluation-rubric-v1.md").read_bytes())
    elif replacement == "same_id_changed_bytes":
        supplied.write_bytes(RUBRIC.read_bytes() + b"\n")
    else:
        supplied.write_bytes(b"\xff\x00PRIVATE_UNREGISTERED_RUBRIC")
    assert hashlib.sha256(supplied.read_bytes()).hexdigest() != RUBRIC_SHA256
    assert_rejected_before_output(tmp_path, packet=receipt(folder), rubric=supplied)


@pytest.mark.parametrize("rubric_id", [None, "e2-rubric-v1", "PRIVATE_UNREGISTERED_RUBRIC"])
def test_scenario_cannot_change_or_omit_the_registered_rubric_id(tmp_path, rubric_id):
    scenario = json.loads(SCENARIO.read_text(encoding="utf-8"))
    if rubric_id is None:
        scenario.pop("rubric_id")
    else:
        scenario["rubric_id"] = rubric_id
    supplied = write(tmp_path / "changed-scenario.json", scenario)
    assert_rejected_before_output(tmp_path, scenario=supplied)


@pytest.mark.parametrize("source", ["fixture", "scenario"])
@pytest.mark.parametrize("fixture_name,turn_position", GOLD_POSITIONS)
@pytest.mark.parametrize("missing", [False, True])
def test_every_registered_turn_requires_the_original_gold_rubric_id(
    tmp_path, source, fixture_name, turn_position, missing
):
    path = next(path for path in FIXTURES if path.name == fixture_name)
    fixture = json.loads(path.read_text(encoding="utf-8"))
    scenario = json.loads(SCENARIO.read_text(encoding="utf-8"))
    if source == "fixture":
        gold = fixture["turns"][turn_position]["gold"]
    else:
        case = next(
            case for case in scenario["case_reviews"] if case["fixture_id"] == fixture["fixture_id"]
        )
        gold = case["turns"][turn_position]["gold"]
    if missing:
        gold.pop("rubric_id")
    else:
        gold["rubric_id"] = "PRIVATE_UNREGISTERED_RUBRIC"
    if source == "fixture":
        supplied = write(tmp_path / fixture_name, fixture)
        fixtures = [supplied if current == path else current for current in FIXTURES]
        assert_rejected_before_output(tmp_path, fixtures=fixtures)
    else:
        supplied = write(tmp_path / "changed-scenario.json", scenario)
        assert_rejected_before_output(tmp_path, scenario=supplied)
