"""Registered V9 software-boundary replay, with limits and unclassified controls."""

import copy
import hashlib
import json

import httpx
import pytest

from agent_app.reasoning import grounding_experiments as experiments


@pytest.fixture(scope="module")
def replay():
    return experiments.replay_grounding_pack(experiments.load_grounding_pack())


def test_registered_inputs_keep_v8_material_and_disclose_manual_extra_metadata():
    pack = experiments.load_grounding_pack()
    summary = experiments.validate_grounding_pack(pack)
    assert summary["cases"] == 6
    assert summary["legacy_replays"] == 14
    assert summary["positive_mappings"] == 7
    assert summary["structured_probes"] == 31
    assert summary["scenario_execution"] is False
    assert pack.suite["manual_metadata_boundary"]["conflict_detection_automatic"] is False
    assert pack.suite["provenance"]["original_reported_workaround_inspected"] is True
    assert pack.suite["provenance"]["same_issue_answer_used_as_evidence"] is False
    assert pack.suite["reserved_issue_ids"] == [8061, 8901, 12629, 12782, 16914]


def test_offline_replay_preserves_useful_controls_and_separates_representation(monkeypatch):
    def no_http(*args, **kwargs):
        pytest.fail("V9 replay must not use HTTP")

    monkeypatch.setattr(httpx.Client, "send", no_http)
    monkeypatch.setattr(httpx.AsyncClient, "send", no_http)
    result = experiments.replay_grounding_pack(experiments.load_grounding_pack())
    assert result["all_registered_expectations_matched"] is True
    assert result["real_api_calls"] == result["tracker_actions_executed"] == 0
    assert result["live_model_quality_measured"] is False
    assert result["RAG_quality_measured"] is False
    assert result["semantic_entailment_measured"] is False
    assert result["automatic_conflict_detection"] is False
    baseline = result["summary"]["legacy_baseline"]
    assert baseline["negative_accepted"] == 6
    assert baseline["positive_retained"] == 7
    assert baseline["registered_outcomes_matched"] == 14
    assert result["summary"]["mapped_positive_intents"] == {"retained": 7, "registered": 7}
    representation = result["summary"]["raw_legacy_representation"]
    assert representation["rejected"] == representation["registered"] == 14
    assert representation["includes_valid_legacy_positives"] is True
    assert representation["semantic_detection_score"] is None
    assert sum(row["control"] == "positive" for row in result["raw_conformance_observations"]) == 7


def test_report_is_repeatable_without_timestamps_or_random_run_identifiers():
    pack = experiments.load_grounding_pack()
    current = experiments.replay_grounding_pack(pack)
    assert current == experiments.replay_grounding_pack(pack)
    receipt = experiments._FIXTURES / "results-grounding-v9.json"
    # Preserve the historical receipt and its original code identity. Additive
    # contracts change the current fingerprint without changing these outcomes.
    assert hashlib.sha256(receipt.read_bytes()).hexdigest() == (
        "9340efb8dcf24b39adb7d1b41b099cf02c794d264753c3a7ee5ce0a850db1ad3"
    )
    saved = json.loads(receipt.read_text())
    assert current["code_sha256"] == experiments._code_fingerprint()
    assert {**saved, "code_sha256": current["code_sha256"]} == current


def test_current_default_replay_is_labeled_and_matches_separate_git_receipt(replay):
    assert replay["legacy_replay_role"] == "current_default_replay_of_frozen_v8_baseline"
    historical = replay["historical_baseline_reference"]
    assert historical["this_runner_executes_historical_code"] is False
    assert historical["baseline_git_commit"] == "e90f2d939248e58858e652bc644821f6682bf8f2"
    assert historical["all_current_default_outcomes_and_source_pools_match"] is True
    assert len(replay["historical_baseline_comparison_observations"]) == 14
    assert all(row["matched"] for row in replay["historical_baseline_comparison_observations"])


def test_historical_comparison_is_retained_with_active_corrected_version(replay):
    row = next(
        row
        for row in replay["mapped_positive_observations"]
        if row["baseline_replay_id"] == "correction-safe-historical-comparison"
    )
    actual = row["actual"]
    assert actual["status"] == "awaiting_approval"
    assert actual["final_decision"] == "answer"
    assert actual["rendered_source_scopes"] == {
        "release-150-multiselect-key-identity-v8": "historical_or_other_version"
    }
    facts = experiments._unescape_display(actual["analysis"]["maintainer_summary"])
    assert "streamlit_version: 1.49.1" in facts
    assert "streamlit_version: 1.50.0" not in facts
    assert actual["render_checks"]["no_patch_equivalence_inferred"] is True


def test_complete_rendered_surfaces_and_exact_context_source_hashes_are_retained(replay):
    for row in replay["mapped_positive_observations"]:
        actual = row["actual"]
        analysis = actual["analysis"]
        assert {
            "user_draft",
            "maintainer_summary",
            "rationale",
            "evidence_links",
            "next_question",
            "missing_info",
            "checks_suggested",
            "facts_delta",
            "retrieval_queries",
        } <= analysis.keys()
        assert actual["analysis_sha256"] == experiments._fingerprint(analysis)
        assert actual["latest_evidence_sha256"] == experiments._fingerprint(
            actual["latest_evidence"]
        )
        assert analysis["facts_delta"] == analysis["checks_suggested"] == []
        for observation in actual["planner_observations"]:
            request = observation["request"]
            material = {key: value for key, value in request.items() if key != "context_sha256"}
            assert request["context_sha256"] == experiments._fingerprint(material)
            assert observation["request_sha256"] == request["context_sha256"]
            for hit in request["evidence"]["hits"]:
                assert observation["source_hashes"][hit["chunk_id"]] == experiments._fingerprint(
                    hit
                )
            assert "inventory" not in request
            assert "authored_replays" not in request
            assert "semantic_expectation" not in request


def test_false_source_and_undeclared_conflict_remain_explicit_unclassified_limits(replay):
    probes = {row["probe_id"]: row for row in replay["structured_probe_observations"]}
    for name in ("v9-conflict-catalog-ablation", "v9-source-authenticity-spoof-fresh-hash"):
        row = probes[name]
        assert row["actual"]["status"] == "awaiting_approval"
        assert row["actual"]["expected_matched"] is True
        assert row["actual"]["analysis"]["facts_delta"] == []
        assert row["registered_expected"].get("source_truth") == "unclassified"
    spoof = probes["v9-source-authenticity-spoof-fresh-hash"]["actual"]
    assert (
        "Controlled synthetic false rule: every keyed widget resets when default changes."
        in experiments._quoted_excerpts(spoof["analysis"]["maintainer_summary"])
    )
    assert replay["summary"]["unclassified_coverage_control_ids"] == [
        "v9-conflict-catalog-ablation",
        "v9-source-authenticity-spoof-fresh-hash",
    ]


def test_declared_conflict_blocks_answer_and_cannot_be_hidden_by_source_selection(replay):
    rows = {row["probe_id"]: row["actual"] for row in replay["structured_probe_observations"]}
    rejected = rows["v9-conflict-answer-selects-one-side"]
    assert rejected["analysis"] is None
    assert rejected["status"] == "error"
    assert any(
        issue["code"] == "grounded_conflict_unresolved" for issue in rejected["output_issues"]
    )
    escalation = rows["v9-conflict-escalation-shows-both"]
    assert escalation["analysis"]["decision"] == "escalate"
    assert {link["chunk_id"] for link in escalation["analysis"]["evidence_links"]} == {
        "release-150-multiselect-key-identity-v8",
        "synthetic-conflict-150-default-reset-v8",
    }


def test_unknown_and_documentation_questions_reject_within_existing_allowance(replay):
    rows = {row["probe_id"]: row["actual"] for row in replay["structured_probe_observations"]}
    for name in (
        "v9-documentation-gap-as-user-question",
        "v9-unregistered-user-question",
        "v9-known-fact-registered-as-gap",
        "v9-ask-without-target",
        "v9-answer-with-question-target",
    ):
        actual = rows[name]
        assert actual["analysis"] is None
        assert actual["model_attempts"] <= 2
        assert actual["retrieval_rounds"] == 1
    known = rows["v9-known-fact-registered-as-gap"]
    assert known["request_preparation_codes"]
    assert known["planner_observations"] == []


def test_latest_bundle_integrity_probe_does_not_accumulate_retired_evidence(replay):
    row = next(
        row
        for row in replay["structured_probe_observations"]
        if row["probe_id"] == "v9-retired-source-after-refinement"
    )
    actual = row["actual"]
    assert actual["analysis"] is None
    assert actual["model_attempts"] == actual["retrieval_rounds"] == 2
    calls = actual["planner_observations"]
    chunk = "release-150-multiselect-key-identity-v8"
    assert chunk in calls[0]["source_hashes"]
    assert chunk not in calls[1]["source_hashes"]
    assert any(issue["code"] == "grounded_source_mismatch" for issue in actual["output_issues"])


@pytest.mark.parametrize("field", ["state", "catalog", "expectation", "positive_mapping"])
def test_postregistration_mutation_fails_before_ports(field, monkeypatch):
    pack = experiments.load_grounding_pack()
    suite = copy.deepcopy(pack.suite)
    if field == "state":
        suite["cases"][0]["case_state"]["case_revision"] = 50
    elif field == "catalog":
        suite["cases"][0]["grounding_catalog"]["gaps"][0]["question"] = "Different question?"
    elif field == "expectation":
        suite["structured_probes"][0]["expected"]["boundary"] = "reject"
    else:
        suite["positive_plan_mappings"][0]["plan_templates"][0]["decision"] = "escalate"

    def no_port(*args, **kwargs):
        pytest.fail("Unregistered input must fail before adapters")

    monkeypatch.setattr(experiments, "SupportEngine", no_port)
    with pytest.raises(experiments.ExperimentRejected, match="RegistrationMismatch"):
        experiments.replay_grounding_pack(experiments.GroundingPack(suite, pack.protocol))


def test_local_protocol_cannot_reauthorize_mutated_input_file(tmp_path):
    pack = experiments.load_grounding_pack()
    suite = copy.deepcopy(pack.suite)
    suite["created_on"] = "2000-01-01"
    protocol = copy.deepcopy(pack.protocol)
    protocol["suite_sha256"] = hashlib.sha256(experiments._encoded(suite)).hexdigest()
    suite_path, protocol_path = tmp_path / "suite.json", tmp_path / "protocol.json"
    suite_path.write_bytes(experiments._encoded(suite))
    protocol_path.write_bytes(experiments._encoded(protocol))
    with pytest.raises(experiments.ExperimentRejected, match="RegistrationMismatch"):
        experiments.load_grounding_pack(suite_path, protocol_path)


def test_validate_only_executes_no_scenario_ports_or_renderer(monkeypatch, capsys):
    def no_execution(*args, **kwargs):
        pytest.fail("Validation cannot execute scenarios")

    monkeypatch.setattr(experiments, "SupportEngine", no_execution)
    monkeypatch.setattr(experiments, "render_grounded_plan", no_execution)
    assert experiments.main(["--validate-only"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["scenario_execution"] is False
    assert result["real_api_calls"] == 0


def test_exclusive_report_does_not_overwrite_or_replay_existing_target(
    tmp_path, capsys, monkeypatch
):
    output = tmp_path / "report.json"
    assert experiments.main(["--output", str(output)]) == 0
    full = json.loads(output.read_text())
    aggregate = json.loads(capsys.readouterr().out)
    assert full["mapped_positive_observations"][0]["actual"]["analysis"]
    assert "mapped_positive_observations" not in aggregate
    assert "structured_probe_observations" not in aggregate
    previous = output.read_bytes()

    def no_replay(*args, **kwargs):
        pytest.fail("An existing output target must be rejected before replay")

    monkeypatch.setattr(experiments, "replay_grounding_pack", no_replay)
    assert experiments.main(["--output", str(output)]) == 2
    assert json.loads(capsys.readouterr().out) == {"error_code": "OutputExists"}
    assert output.read_bytes() == previous


def test_cli_allowlists_arbitrary_runner_error_without_echoing_private_values(monkeypatch, capsys):
    def bad_load():
        raise ValueError("sensitive-marker-v9 must not appear")

    monkeypatch.setattr(experiments, "load_grounding_pack", bad_load)
    assert experiments.main([]) == 2
    output = capsys.readouterr().out
    assert "sensitive-marker" not in output
    assert json.loads(output) == {"error_code": "ReplayUnavailable"}


def test_accepted_wrong_final_decision_does_not_count_as_useful_retention(monkeypatch):
    original = experiments._run_candidate

    def wrong_final(*args, **kwargs):
        actual = original(*args, **kwargs)
        if kwargs["replay_id"] == "full-limited-supported-answer":
            actual["final_decision"] = "ask"
        return actual

    monkeypatch.setattr(experiments, "_run_candidate", wrong_final)
    result = experiments.replay_grounding_pack(experiments.load_grounding_pack())
    assert result["summary"]["mapped_positive_intents"]["retained"] == 6
    assert result["all_registered_expectations_matched"] is False
    assert result["failures"] == ["positive-mapping/full-limited-supported-answer"]


def test_failed_registered_render_check_is_reported_without_retuning(monkeypatch):
    original = experiments._check_render

    def failed_history(name, actual):
        if name == "historical_other_version_label":
            return False
        return original(name, actual)

    monkeypatch.setattr(experiments, "_check_render", failed_history)
    result = experiments.replay_grounding_pack(experiments.load_grounding_pack())
    assert result["all_registered_expectations_matched"] is False
    assert "positive-mapping/correction-safe-historical-comparison" in result["failures"]
    assert "structured-probe/v9-positive-historical-quote" in result["failures"]
    assert result["summary"]["mapped_positive_intents"]["retained"] == 6


def test_all_probe_results_preserve_preregistered_individual_oracles(replay):
    pack = experiments.load_grounding_pack()
    frozen = {probe["id"]: probe["expected"] for probe in pack.suite["structured_probes"]}
    for row in replay["structured_probe_observations"]:
        assert row["registered_expected"] == frozen[row["probe_id"]]
        assert row["actual"]["expected_matched"] is True
    assert (
        sum(
            category["registered"]
            for category in replay["summary"]["structured_categories"].values()
        )
        == 31
    )


@pytest.mark.parametrize("surface", ["both", "maintainer_summary", "user_draft"])
def test_missing_key_source_block_or_citation_never_counts_as_whole_quote_retention(
    monkeypatch, surface
):
    original = experiments._run_candidate
    chunk = "release-150-multiselect-key-identity-v8"

    def removed_source(*args, **kwargs):
        actual = original(*args, **kwargs)
        if kwargs["replay_id"] != "full-limited-supported-answer":
            return actual
        analysis = actual["analysis"]
        fields = ("maintainer_summary", "user_draft") if surface == "both" else (surface,)
        for field in fields:
            # Keep the easy surviving default source while deleting the key
            # release mechanism to reproduce the independently found bypass.
            analysis[field] = analysis[field].split(f"Supplied source {chunk}", 1)[0].rstrip()
        if surface == "both":
            analysis["evidence_links"] = [
                link for link in analysis["evidence_links"] if link["chunk_id"] != chunk
            ]
            assert analysis["evidence_links"]
        actual["analysis_sha256"] = experiments._fingerprint(analysis)
        return actual

    monkeypatch.setattr(experiments, "_run_candidate", removed_source)
    pack = experiments.load_grounding_pack()
    mapping = pack.suite["positive_plan_mappings"][0]
    case = next(case for case in pack.suite["cases"] if case["id"] == mapping["case_id"])
    actual = experiments._run_mapping(case, mapping, pack)
    assert actual["status"] == "awaiting_approval"
    assert actual["render_checks"]["whole_selected_excerpts"] is False
    assert actual["render_checks"]["contract_final_render_bound"] is False
    if surface == "both":
        assert actual["render_checks"]["contract_selected_source_set"] is False
    else:
        assert actual["render_checks"]["contract_selected_source_set"] is True
    assert actual["expected_matched"] is False


def test_rationale_fact_invention_is_not_hidden_by_correct_summary_and_quotes(monkeypatch):
    original = experiments._run_candidate

    def changed_rationale(*args, **kwargs):
        actual = original(*args, **kwargs)
        if kwargs["replay_id"] == "correction-safe-historical-comparison":
            actual["analysis"]["rationale"] = (
                "The current installed user version is 1.50.0 and the cause is proven."
            )
            actual["analysis_sha256"] = experiments._fingerprint(actual["analysis"])
        return actual

    monkeypatch.setattr(experiments, "_run_candidate", changed_rationale)
    pack = experiments.load_grounding_pack()
    mapping = next(
        mapping
        for mapping in pack.suite["positive_plan_mappings"]
        if mapping["baseline_replay_id"] == "correction-safe-historical-comparison"
    )
    case = next(case for case in pack.suite["cases"] if case["id"] == mapping["case_id"])
    actual = experiments._run_mapping(case, mapping, pack)
    assert actual["render_checks"]["only_active_user_version_current"] is True
    assert actual["render_checks"]["whole_selected_excerpts"] is True
    assert actual["render_checks"]["contract_final_render_bound"] is False
    assert actual["expected_matched"] is False


def test_adapter_crash_does_not_count_as_any_registered_rejection_family(monkeypatch):
    def crashed_plan(*args, **kwargs):
        raise RuntimeError("private-adapter-marker-v9")

    monkeypatch.setattr(experiments._TemplatePlanner, "plan", crashed_plan)
    pack = experiments.load_grounding_pack()
    cases = {case["id"]: case for case in pack.suite["cases"]}
    probes = [
        probe
        for probe in pack.suite["structured_probes"]
        if probe["id"]
        in {
            "v9-context-hash-changed",
            "v9-source-hash-changed",
            "v9-free-user-prose",
            "v9-documentation-gap-as-user-question",
            "v9-conflict-answer-selects-one-side",
        }
    ]
    assert len(probes) == 5
    for probe in probes:
        actual = experiments._run_probe(cases[probe["case_id"]], probe, pack)
        assert actual["status"] == "error"
        assert actual["error_code"] == "ReasoningUnavailable"
        assert actual["rejection_cause_matched"] is False
        assert actual["expected_matched"] is False
        assert "private-adapter-marker" not in json.dumps(actual)


def test_wrong_guard_cause_is_reported_even_when_boundary_is_reject(monkeypatch):
    original = experiments._run_candidate

    def wrong_cause(*args, **kwargs):
        actual = original(*args, **kwargs)
        if kwargs["replay_id"] == "v9-source-hash-changed":
            actual["error_code"] = "GroundedContextMismatch"
            actual["output_issues"] = [{"code": "grounded_context_mismatch", "field": None}]
        return actual

    monkeypatch.setattr(experiments, "_run_candidate", wrong_cause)
    result = experiments.replay_grounding_pack(experiments.load_grounding_pack())
    assert result["all_registered_expectations_matched"] is False
    assert result["failures"] == ["structured-probe/v9-source-hash-changed"]


def test_historical_receipt_disagreement_is_reported_without_relabeling_baseline(monkeypatch):
    original = experiments._run_legacy

    def changed_source_pool(*args, **kwargs):
        actual = original(*args, **kwargs)
        if args[1]["id"] == "full-limited-supported-answer":
            actual["reasoner_observations"][0]["evidence"]["hits"] = []
        return actual

    monkeypatch.setattr(experiments, "_run_legacy", changed_source_pool)
    result = experiments.replay_grounding_pack(experiments.load_grounding_pack())
    assert result["summary"]["legacy_baseline"]["registered_outcomes_matched"] == 14
    assert (
        result["historical_baseline_reference"][
            "all_current_default_outcomes_and_source_pools_match"
        ]
        is False
    )
    assert result["all_registered_expectations_matched"] is False
    assert result["failures"] == ["historical-baseline/full-limited-supported-answer"]
