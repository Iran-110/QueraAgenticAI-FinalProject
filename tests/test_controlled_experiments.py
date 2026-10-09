"""Registered V8 replays exercise narrow boundaries, never model/RAG quality."""

import copy
import json

import httpx
import pytest

from agent_app.reasoning import controlled_experiments as controlled


def test_registered_shapes_sources_and_scope_disclosures_are_frozen():
    pack = controlled.load_controlled_pack()
    summary = controlled.validate_controlled_pack(pack)
    assert summary["cases"] == 6
    assert summary["replays_per_scope"] == 14
    assert summary["intake_probes"] == 16
    assert summary["scenario_execution"] is False
    assert pack.suite["reserved_issue_ids"] == [8061, 8901, 12629, 12782, 16914]
    assert pack.suite["provenance"]["original_reported_workaround_inspected"] is True
    assert pack.suite["provenance"]["same_issue_answer_used_as_evidence"] is False
    assert pack.suite["provenance"]["issue_comments_inspected_for_scenario_or_mechanism_selection"]


def test_exact_scope_rejects_two_more_unsafe_controls_and_loses_safe_comparison(monkeypatch):
    def no_network(*args, **kwargs):
        pytest.fail("Controlled replay must not use HTTP")

    monkeypatch.setattr(httpx.Client, "send", no_network)
    monkeypatch.setattr(httpx.AsyncClient, "send", no_network)
    result = controlled.replay_controlled_pack(controlled.load_controlled_pack())
    assert result["all_registered_expectations_matched"] is True
    assert result["real_api_calls"] == result["tracker_actions_executed"] == 0
    assert result["semantic_quality_measured"] is result["RAG_quality_measured"] is False
    assert result["summary"]["all"]["unsafe_accepted"] == 6
    assert result["summary"]["exact_user_version"]["unsafe_accepted"] == 4
    assert result["summary"]["all"]["positive_retained"] == 7
    assert result["summary"]["exact_user_version"]["positive_retained"] == 6
    historical = next(
        r
        for r in result["observations"]
        if r["replay_id"] == "correction-safe-historical-comparison"
    )
    assert historical["authored_semantic_label"] == "acceptable"
    assert historical["all"]["status"] == "awaiting_approval"
    assert historical["exact_user_version"]["error_code"] == "UnknownEvidenceReference"


def test_retained_unscoped_and_same_version_sources_do_not_prove_claim_support():
    result = controlled.replay_controlled_pack(controlled.load_controlled_pack())
    observations = {r["replay_id"]: r for r in result["observations"]}
    for replay_id in (
        "full-unsupported-causal-guarantee",
        "removed-default-doc-causal-invention",
        "unknown-version-adopted-from-unscoped-history",
        "conflict-synthetic-rule-overrides-official",
    ):
        assert observations[replay_id]["authored_semantic_label"] == "unusable"
        for scope in ("all", "exact_user_version"):
            assert observations[replay_id][scope]["status"] == "awaiting_approval"
    unknown = observations["unknown-focused-installed-version-question"]["exact_user_version"]
    assert unknown["received_chunk_ids"] == [["widget-key-identity-history-snapshot-v8"]]


def test_latest_bundle_retirement_remains_enforced_in_both_scopes():
    result = controlled.replay_controlled_pack(controlled.load_controlled_pack())
    stale = next(
        r
        for r in result["observations"]
        if r["replay_id"] == "refinement-do-not-reuse-retired-citation"
    )
    for scope in ("all", "exact_user_version"):
        actual = stale[scope]
        assert actual["model_attempts"] == actual["retrieval_rounds"] == 2
        assert actual["error_code"] == "UnknownEvidenceReference"
        assert "release-150-multiselect-key-identity-v8" in actual["received_chunk_ids"][0]
        assert "release-150-multiselect-key-identity-v8" not in actual["received_chunk_ids"][1]


def test_intake_conversion_preserves_attribution_and_rejects_ambiguous_or_stale_replies():
    result = controlled.replay_controlled_pack(controlled.load_controlled_pack())
    assert result["intake_conditions_matched"] == 32
    assert result["intake_conversions"] == {"bare_turn": 0, "prepare_version_reply": 2}
    for observation in result["intake_observations"]:
        candidate = observation["prepare_version_reply"]
        if observation["control"] == "positive":
            assert candidate["active_version"] == "1.50.0"
            assert candidate["case_revision"] == 1
            assert candidate["pending_proposal_id"] is None
            assert candidate["user_attribution_preserved"] is True
        else:
            assert candidate["converted"] is False
            assert candidate["transition_allowed"] is False
    drift = [r for r in result["intake_observations"] if r["probe_id"].startswith("misleading-")]
    assert len(drift) == 3
    assert all(r["prepare_version_reply"]["error_code"] == "InvalidVersionQuestion" for r in drift)
    correction = result["transition_observations"][0]
    assert correction["expected_matched"] is True
    assert correction["pending_proposal_id"] is None
    assert correction["evidence_refs"] == []
    assert correction["invalidated_check_count"] == 1
    assert correction["changed_fact_names"] == ["streamlit_version", "prior_evidence_observation"]


@pytest.mark.parametrize("changed", ["case_state", "authored_label", "expected_outcome"])
def test_postregistration_mutation_stops_before_ports(changed, monkeypatch):
    pack = controlled.load_controlled_pack()
    suite = copy.deepcopy(pack.suite)
    if changed == "case_state":
        suite["cases"][0]["case_state"]["case_revision"] = 99
    elif changed == "authored_label":
        suite["cases"][0]["authored_replays"][0]["semantic_expectation"]["label"] = "unusable"
    else:
        suite["cases"][0]["authored_replays"][0]["expected_by_scope"]["all"]["status"] = "error"
    monkeypatch.setattr(
        controlled,
        "SupportEngine",
        lambda *args, **kwargs: pytest.fail("No port before validation"),
    )
    with pytest.raises(ValueError, match="content changed"):
        controlled.replay_controlled_pack(controlled.ControlledPack(suite, pack.protocol))


@pytest.mark.parametrize("change_protocol", [False, True])
def test_unregistered_file_hash_cannot_be_reauthorized_by_local_protocol(tmp_path, change_protocol):
    pack = controlled.load_controlled_pack()
    suite = copy.deepcopy(pack.suite)
    suite["created_on"] = "2000-01-01"
    protocol = copy.deepcopy(pack.protocol)
    if change_protocol:
        protocol["suite_sha256"] = controlled._hash(suite)
    suite_path, protocol_path = tmp_path / "cases.json", tmp_path / "protocol.json"
    suite_path.write_bytes(controlled._encoded(suite))
    protocol_path.write_bytes(controlled._encoded(protocol))
    with pytest.raises(ValueError, match="hash mismatch"):
        controlled.load_controlled_pack(suite_path, protocol_path)


def test_validate_only_cli_does_not_execute_ports_or_transitions(monkeypatch, capsys):
    def no_execution(*args, **kwargs):
        pytest.fail("Validate-only must not execute scenarios")

    monkeypatch.setattr(controlled, "SupportEngine", no_execution)
    monkeypatch.setattr(controlled, "propose_user_turn", no_execution)
    assert controlled.main(["--validate-only"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["scenario_execution"] is False


def test_saved_report_is_exclusive_and_stdout_has_only_aggregates(tmp_path, capsys):
    report = tmp_path / "report.json"
    assert controlled.main(["--output", str(report)]) == 0
    saved = json.loads(report.read_text())
    aggregate = json.loads(capsys.readouterr().out)
    assert saved["observations"]
    assert "observations" not in aggregate
    assert "intake_observations" not in aggregate
    assert aggregate["all_registered_expectations_matched"] is True
    original = report.read_bytes()
    with pytest.raises(FileExistsError):
        controlled.main(["--output", str(report)])
    assert report.read_bytes() == original


def test_replay_reports_changed_runtime_outcome_without_retuning_labels(monkeypatch):
    original = controlled._replay_engine

    def changed_runtime(case, replay, scope, pack):
        actual = original(case, replay, scope, pack)
        if replay["id"] == "full-limited-supported-answer" and scope == "all":
            actual.update(status="error", final_decision=None, expected_matched=False)
        return actual

    monkeypatch.setattr(controlled, "_replay_engine", changed_runtime)
    result = controlled.replay_controlled_pack(controlled.load_controlled_pack())
    assert result["all_registered_expectations_matched"] is False
    assert result["failures"] == ["engine/full-limited-supported-answer/all"]
    assert result["summary"]["all"]["positive_retained"] == 6


def test_positive_retention_does_not_count_an_accepted_wrong_final_decision(monkeypatch):
    original = controlled._replay_engine

    def wrong_final_decision(case, replay, scope, pack):
        actual = original(case, replay, scope, pack)
        if replay["id"] == "full-limited-supported-answer" and scope == "all":
            actual.update(final_decision="ask", expected_matched=False)
        return actual

    monkeypatch.setattr(controlled, "_replay_engine", wrong_final_decision)
    result = controlled.replay_controlled_pack(controlled.load_controlled_pack())
    altered = next(
        r for r in result["observations"] if r["replay_id"] == "full-limited-supported-answer"
    )
    assert altered["all"]["status"] == "awaiting_approval"
    assert altered["registered_positive_final_decision"] == "answer"
    assert result["summary"]["all"]["positive_retained"] == 6
    assert result["failures"] == ["engine/full-limited-supported-answer/all"]


def test_intake_regression_with_no_new_fact_is_reported_without_crashing(monkeypatch):
    monkeypatch.setattr(controlled, "prepare_version_reply", lambda case, turn, **kwargs: turn)
    result = controlled.replay_controlled_pack(controlled.load_controlled_pack())
    positives = [r for r in result["intake_observations"] if r["control"] == "positive"]
    assert len(positives) == 2
    assert result["all_registered_expectations_matched"] is False
    for observation in positives:
        candidate = observation["prepare_version_reply"]
        assert candidate["active_version"] is None
        assert candidate["converted"] is False
        assert candidate["user_attribution_preserved"] is False
        assert candidate["expected_matched"] is False
        assert f"intake/{observation['probe_id']}/prepare_version_reply" in result["failures"]
