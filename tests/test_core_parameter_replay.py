"""Recorded exposed evidence replay; no provider, ledger or held-out fixture."""

import hashlib
import importlib
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def replay(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT))
    return importlib.import_module("experiments.core_parameter_focus_v1.replay")


@pytest.fixture
def mutable(replay, tmp_path, monkeypatch):
    source = replay.PACKAGE
    destination = tmp_path / "inputs"
    destination.mkdir()
    for name in (
        "input-manifest-v1.json",
        "replay-fixture-v1.json",
        "protocol-v1.json",
        "protocol-amendment-v1.json",
    ):
        shutil.copyfile(source / name, destination / name)
    monkeypatch.setattr(replay, "PACKAGE", destination)
    return destination


def _update(directory, name, edit, *, rebind=True):
    path = directory / name
    data = json.loads(path.read_text())
    edit(data)
    path.write_text(json.dumps(data, ensure_ascii=False))
    if rebind and name == "replay-fixture-v1.json":
        manifest = directory / "input-manifest-v1.json"
        body = json.loads(manifest.read_text())
        body["fixture_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest.write_text(json.dumps(body))


def test_all_recorded_routes_retained_and_only_three_authored_projections(replay):
    report = replay.run_replay()
    assert report["attempt_rows"] == 8 and report["final_turns_retained"] == 7
    assert report["provider_calls"] == report["ledger_writes"] == 0
    assert report["all_baselines_exactly_reproduced"]
    assert report["all_primary_structural_controls_pass"]
    assert report["model_quality_improvement_established"] is False
    assert report["enum_fix_verified"] is False
    assert report["human_usefulness"] is None
    projected = [row for row in report["rows"] if "candidate" in row["projection"]]
    assert [row["turn"] for row in projected] == ["B2", "C1", "C2"]
    for row in projected:
        observation = row["projection"]
        assert all(observation["controls"].values())
        assert observation["candidate_chars"] < observation["original_chars"]
        assert all(observation["registered_clause_checks"].values())
        assert observation["candidate"]["semantic_support"] is None
        assert observation["candidate"]["proposal_or_action_authorized"] is False
        assert observation["source_only_diagnostic"]["full_source_quotation_retained"]
        assert observation["source_only_diagnostic"]["focus_shorter_than_source_only"]


def test_relevance_failures_and_retrieval_attempt_are_not_hidden(replay):
    rows = replay.run_replay()["rows"]
    by_turn = {row["turn"]: row for row in rows}
    assert by_turn["A1"]["original_decision"] == "ask"
    assert by_turn["A3"]["original_decision"] == "answer"
    assert "candidate" not in by_turn["A3"]["projection"]
    assert by_turn["B1"]["original_decision"] == "escalate"
    assert [row["original_decision"] for row in rows if row["turn"] == "B1"] == [
        "retrieve_more",
        "escalate",
    ]


def test_single_source_control_discloses_reduction_without_source_removal(replay):
    rows = replay.run_replay()["rows"]
    final = next(row for row in rows if row["turn"] == "C2")
    observation = final["projection"]
    assert observation["source_only_diagnostic"]["draft_chars"] == observation["original_chars"]
    assert observation["candidate_chars"] < observation["source_only_diagnostic"]["draft_chars"]
    assert observation["source_only_diagnostic"]["kind"].startswith("post_hoc_authored")
    assert observation["source_only_diagnostic"][
        "lengths_also_include_renderer_qualification_differences"
    ]


@pytest.mark.parametrize("fault", ["source", "revision", "draft", "duplicate", "missing"])
def test_tampered_custody_or_history_rejected_even_if_fixture_manifest_rebound(
    replay, mutable, fault
):
    def edit(data):
        if fault == "source":
            data["rows"][-1]["grounded_request"]["evidence"]["hits"][0]["excerpt"] += "Changed"
        elif fault == "revision":
            data["rows"][-1]["grounded_request"]["case"]["case_revision"] += 1
        elif fault == "draft":
            data["rows"][-1]["analysis"]["user_draft"] = "Edited after original model execution"
        elif fault == "duplicate":
            data["rows"].append(data["rows"][0])
        else:
            data["rows"].pop()

    _update(mutable, "replay-fixture-v1.json", edit)
    with pytest.raises(ValueError, match="^ParameterReplayRejected$"):
        replay.run_replay()


def test_fixture_drift_rejected_before_reconstruction(replay, mutable):
    path = mutable / "replay-fixture-v1.json"
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="^ParameterReplayRejected$"):
        replay.run_replay()


@pytest.mark.parametrize("value", [True, 1.0, "1", None])
def test_attempt_identity_not_coerced(replay, mutable, value):
    _update(mutable, "replay-fixture-v1.json", lambda data: data["rows"][0].update(attempt=value))
    with pytest.raises(ValueError, match="^ParameterReplayRejected$"):
        replay.run_replay()


@pytest.mark.parametrize("value", [True, 8.0, "8"])
def test_manifest_counts_are_actual_integer_counts(replay, mutable, value):
    _update(mutable, "input-manifest-v1.json", lambda data: data.update(attempt_rows=value))
    with pytest.raises(ValueError, match="^ParameterReplayRejected$"):
        replay.run_replay()


def test_authored_target_cannot_silently_change_away_from_registered_protocol(replay, mutable):
    _update(
        mutable,
        "replay-fixture-v1.json",
        lambda data: data["authored_focus_selection"][0].update(parameter="disabled"),
    )
    with pytest.raises(ValueError, match="^ParameterReplayRejected$"):
        replay.run_replay()


def test_replay_never_puts_authored_selection_in_candidate_payload(replay, monkeypatch):
    original = replay.parameter_focus_payload

    def inspect(request):
        payload = original(request)
        assert "authored_focus_selection" not in payload
        assert "required_full_clauses" not in payload
        assert "baseline" not in payload
        assert payload["grounded_request"] == request.grounded.model_dump(mode="json")
        return payload

    monkeypatch.setattr(replay, "parameter_focus_payload", inspect)
    assert replay.run_replay()["all_primary_structural_controls_pass"]


def test_report_is_new_only_and_never_overwrites(replay, tmp_path):
    destination = tmp_path / "new.json"
    replay.write_new_report(destination, {"provider_calls": 0})
    raw = destination.read_bytes()
    with pytest.raises(FileExistsError):
        replay.write_new_report(destination, {"provider_calls": 1})
    assert destination.read_bytes() == raw


def test_report_rejects_symlink_without_changing_target(replay, tmp_path):
    target = tmp_path / "existing.json"
    target.write_text("original")
    alias = tmp_path / "alias.json"
    alias.symlink_to(target)
    with pytest.raises(FileExistsError):
        replay.write_new_report(alias, {})
    assert target.read_text() == "original"


@pytest.mark.parametrize("folder", ["data", "runtime", "src", "app_pages", ".git"])
def test_report_cannot_write_into_runtime_source_or_evaluation(replay, folder):
    with pytest.raises(ValueError, match="^ParameterReplayRejected$"):
        replay.write_new_report(ROOT / folder / "parameter-do-not-write.json", {})
