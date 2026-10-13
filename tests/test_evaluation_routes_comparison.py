"""Unit checks for comparison receipts; no registered comparison is executed."""

import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/evaluation_routes_comparison.py"
SPEC = importlib.util.spec_from_file_location("routes_comparison_receipt", SCRIPT)
comparison = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(comparison)


@pytest.fixture
def pinned_inputs(tmp_path, monkeypatch):
    registered = tmp_path / "experiments/evaluation_routes"
    registered.mkdir(parents=True)
    helper = tmp_path / "tests/test_eval_conditional_routes.py"
    helper.parent.mkdir()
    helper.write_text("# Temporary unit-test helper\n")
    script = tmp_path / "scripts/comparison.py"
    script.parent.mkdir()
    script.write_text("# Temporary unit-test comparison script\n")
    fixture = registered / "fixture-v1.json"
    fixture.write_text(json.dumps({"turns": []}))
    protocol = registered / "protocol-v2.json"
    protocol.write_text(
        json.dumps(
            {
                "protocol_id": "unit-test-only",
                "fixture_sha256": comparison.digest(fixture),
                "test_helper_sha256": comparison.digest(helper),
                "script_sha256": comparison.digest(script),
            }
        )
    )
    monkeypatch.setattr(comparison, "ROOT", tmp_path)
    monkeypatch.setattr(comparison, "REGISTERED", registered)
    monkeypatch.setattr(comparison, "SCRIPT", script)
    monkeypatch.setattr(comparison.runner, "_source_hashes", lambda: {"source.py": "initial"})
    return comparison.registration()


@pytest.mark.parametrize("changed", ["protocol", "fixture", "test_helper", "comparison_script"])
def test_registered_input_mutation_is_rejected_without_replacing_initial_pins(
    pinned_inputs, changed
):
    before = deepcopy(pinned_inputs["pins"])
    path = pinned_inputs["paths"][changed]
    path.write_bytes(path.read_bytes() + b"\nCHANGED_AFTER_REGISTRATION")
    with pytest.raises(ValueError, match="^RouteComparisonRegistrationChanged$"):
        comparison.check_registration(pinned_inputs)
    assert pinned_inputs["pins"] == before


def test_current_core_source_drift_is_rejected(pinned_inputs, monkeypatch):
    monkeypatch.setattr(comparison.runner, "_source_hashes", lambda: {"source.py": "changed"})
    with pytest.raises(ValueError, match="^RouteComparisonSourceChanged$"):
        comparison.check_registration(pinned_inputs)


def test_missing_or_wrong_comparison_script_registration_fails_before_runner(pinned_inputs):
    path = pinned_inputs["paths"]["protocol"]
    data = json.loads(path.read_bytes())
    data.pop("script_sha256")
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="^RouteComparisonRegistrationChanged$"):
        comparison.registration(path)
    data["script_sha256"] = "0" * 64
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="^RouteComparisonRegistrationChanged$"):
        comparison.registration(path)


@pytest.fixture
def wire_fixture():
    return {
        "turns": [
            {"id": "initial", "visible": {"message": "Version and callback are unknown."}},
            {"id": "callback", "visible": {"message": "FUTURE_CALLBACK_RESPONSE code"}},
            {"id": "version", "visible": {"message": "1.50.0"}},
            {
                "id": "correction",
                "visible": {"message": "FUTURE_CORRECTION_MARKER use 1.49.0"},
            },
        ]
    }


def submitted_step(fixture, identifier, revision):
    visible = next(turn["visible"] for turn in fixture["turns"] if turn["id"] == identifier)
    return {
        "turn": identifier,
        "request": {"message": visible["message"]},
        "usage": {"requests": [{"context": {"case_id": "dev-routes", "case_revision": revision}}]},
    }


def prompt(step, *, extra_case=None, extra_payload=None, evidence=None):
    payload = {
        "case": {
            "case_id": "dev-routes",
            "case_revision": step["usage"]["requests"][0]["context"]["case_revision"],
            **(extra_case or {}),
        },
        "user_message": step["request"]["message"],
        "evidence": evidence or {},
        **(extra_payload or {}),
    }
    return {"messages": [{"role": "user", "content": json.dumps(payload)}]}


@pytest.mark.parametrize(
    "marker",
    ["FUTURE_CALLBACK_RESPONSE", "FUTURE_CORRECTION_MARKER", "1.50.0"],
)
def test_future_marker_in_user_state_is_rejected_even_with_correct_selected_path(
    wire_fixture, marker
):
    step = submitted_step(wire_fixture, "initial", 1)
    wire = prompt(step, extra_case={"facts": [{"name": "leaked", "value": marker}]})
    audit = comparison.wire_audit([wire], [step], wire_fixture, ["initial"])
    assert audit["all_passed"] is False
    assert audit["checks"][0]["matches_submitted_selected_turn"] is True
    assert audit["checks"][0]["unavailable_markers_absent"] is False
    assert marker not in json.dumps(audit)  # Only stable marker names leave the audit.


def test_version_metadata_in_retrieved_evidence_is_not_a_future_user_reply(wire_fixture):
    step = submitted_step(wire_fixture, "initial", 1)
    wire = prompt(
        step, evidence={"applicable_versions": ["1.50.0"], "source_id": "docstring:1.50.0:api"}
    )
    audit = comparison.wire_audit([wire], [step], wire_fixture, ["initial"])
    assert audit["all_passed"] is True


def test_future_marker_is_permitted_only_after_its_selected_input_was_submitted(wire_fixture):
    steps = [
        submitted_step(wire_fixture, "initial", 1),
        submitted_step(wire_fixture, "version", 2),
        submitted_step(wire_fixture, "correction", 3),
    ]
    wires = [prompt(step) for step in steps]
    wires[-1] = prompt(
        steps[-1], extra_case={"facts": [{"name": "old_version", "value": "1.50.0"}]}
    )
    selected = ["initial", "version", "correction"]
    assert comparison.wire_audit(wires, steps, wire_fixture, selected)["all_passed"] is True
    wires[0] = prompt(steps[0], extra_payload={"conversation": ["1.50.0"]})
    audit = comparison.wire_audit(wires, steps, wire_fixture, selected)
    assert audit["all_passed"] is False
    assert audit["checks"][0]["unavailable_marker_names"] == ["version"]


def test_repair_repeats_same_submitted_turn_without_authorizing_future_inputs(wire_fixture):
    step = submitted_step(wire_fixture, "initial", 1)
    wire = prompt(step)
    audit = comparison.wire_audit([wire, deepcopy(wire)], [step], wire_fixture, ["initial"])
    assert audit["all_passed"] is True
    assert audit["captured_prompts"] == 2


def test_unselected_legacy_continuation_is_not_authorized_by_its_actual_submission(wire_fixture):
    steps = [
        submitted_step(wire_fixture, "initial", 1),
        submitted_step(wire_fixture, "callback", 2),
    ]
    wires = [prompt(step) for step in steps]
    audit = comparison.wire_audit(wires, steps, wire_fixture, ["initial", "version", "correction"])
    assert audit["checks"][0]["matches_submitted_selected_turn"] is True
    assert audit["checks"][1]["matches_submitted_selected_turn"] is False
    assert audit["checks"][1]["unavailable_marker_names"] == ["callback"]
    assert audit["all_passed"] is False


def test_private_gold_in_any_wire_field_and_fixture_metadata_fail_without_raw_export(wire_fixture):
    step = submitted_step(wire_fixture, "initial", 1)
    wire = prompt(step)
    wire["messages"].insert(0, {"role": "system", "content": comparison.PRIVATE_GOLD})
    audit = comparison.wire_audit([wire], [step], wire_fixture, ["initial"])
    assert audit["all_passed"] is False
    assert audit["checks"][0]["private_gold_absent"] is False
    assert comparison.PRIVATE_GOLD not in json.dumps(audit)
    wire = prompt(step, extra_payload={"gold": {"acceptable_decisions": ["ask"]}})
    audit = comparison.wire_audit([wire], [step], wire_fixture, ["initial"])
    assert audit["checks"][0]["fixture_metadata_absent"] is False
    assert audit["all_passed"] is False


def test_unattributed_or_empty_capture_is_not_a_wire_audit_pass(wire_fixture):
    step = submitted_step(wire_fixture, "initial", 1)
    wire = prompt(step, extra_case={"case_revision": 99})
    assert not comparison.wire_audit([wire], [step], wire_fixture, ["initial"])["all_passed"]
    assert not comparison.wire_audit([], [step], wire_fixture, ["initial"])["all_passed"]


def test_cli_defaults_to_v2_and_preserves_existing_output_without_comparing(tmp_path, monkeypatch):
    output = tmp_path / "result.json"
    output.write_text("existing receipt")
    monkeypatch.setattr(comparison, "compare", lambda *_: pytest.fail("No overwrite comparison"))
    with pytest.raises(ValueError, match="^RouteComparisonOutputExists$"):
        comparison.main(["--output", str(output)])
    assert output.read_text() == "existing receipt"
    output.unlink()
    selected = []

    def fake_compare(protocol):
        selected.append(protocol)
        return {
            "quality_claim": False,
            "real_api_calls": 0,
            "paid_cost_usd": "0",
            "baseline_path_passes": 0,
            "conditional_path_passes": 0,
        }

    monkeypatch.setattr(comparison, "compare", fake_compare)
    comparison.main(["--output", str(output)])
    assert selected == [comparison.REGISTERED / "protocol-v2.json"]
