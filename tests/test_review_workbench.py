"""Actual dev receipt controls; no provider, ledger, corpus or human labels."""

import hashlib
import importlib.util
import json
import shutil
from copy import deepcopy
from pathlib import Path

import pytest

from agent_app.contracts import ProposalHandoff
from agent_app.evaluation.review_workbench import (
    WorkbenchRejected,
    _html_index,
    build_workbench,
    load_workbench,
    prepare_workbench,
    score_workbench,
    write_score,
)
from agent_app.evaluation.semantic_review import ReviewScope, score_review

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / "experiments/dev_rag_coverage_v1"
FIXTURES = ROOT / "data/evaluation/dev-three-v1/cases"
SCENARIO = ROOT / "data/evaluation/dev-three-v1/scenario-review-v1.json"
RUBRIC = ROOT / "docs/evaluation-rubric.md"


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@pytest.fixture
def inputs(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    for name in ("model-live-receipt-v1.json", "live-method-v1.json", "protocol-v1.json"):
        shutil.copyfile(PACKET / name, source / name)
    fixture_paths = []
    for path in sorted(FIXTURES.glob("*.json")):
        copy = source / path.name
        shutil.copyfile(path, copy)
        fixture_paths.append(copy)
    scenario = source / "scenario.json"
    rubric = source / "rubric.md"
    shutil.copyfile(SCENARIO, scenario)
    shutil.copyfile(RUBRIC, rubric)
    return source / "model-live-receipt-v1.json", fixture_paths, scenario, rubric


@pytest.fixture
def prepared(inputs, tmp_path):
    output = tmp_path / "private"
    workbench = prepare_workbench(*inputs, output)
    return output, workbench


def envelope(output, workbench, *, row=None, reviewer="human-one", kind="human"):
    row = row or next(row for row in workbench["rows"] if row["status"] == "fresh_proposal")
    payload = json.loads((output / f"pending-{row['item_id']}.json").read_text())
    payload["review"]["reviewer_id"] = reviewer
    payload["review"]["reviewer_kind"] = kind
    payload["review"]["review_id"] = "declared-review-" + reviewer
    return payload


def reviewed_path(output, payload, name="reviewed.json"):
    path = output / name
    dump(path, payload)
    return path


def test_actual_route_denominators_and_no_stale_double_count(inputs):
    result = build_workbench(*inputs)
    assert result["summary"] == {
        "planned_jobs": 12,
        "planned_turns": 24,
        "visited_turns": 23,
        "no_fresh_response_turns": 6,
        "fresh_proposal": 17,
        "stale_observation": 2,
        "no_fresh_proposal": 4,
        "unvisited": 1,
    }
    assert sum(len(row["actual_model_attempts"]) for row in result["rows"]) == 29
    assert sum(len(row["native_retrievals"]) for row in result["rows"]) == 26
    stale = [row for row in result["rows"] if row["status"] == "stale_observation"]
    assert len(stale) == 2
    assert all(row["review_template"] is None for row in stale)
    assert all(row["original_proposal"]["handoff"]["case"]["case_revision"] == 1 for row in stale)
    assert all(row["consumed_input"]["expected_revision"] == 1 for row in stale)
    unvisited = next(row for row in result["rows"] if row["status"] == "unvisited")
    assert unvisited["turn_id"] == "correction"
    assert unvisited["consumed_input"] is None
    assert unvisited["original_proposal"] is None
    assert unvisited["actual_model_attempts"] == []


@pytest.fixture
def resource_inputs(tmp_path):
    source = tmp_path / "resource"
    source.mkdir()
    packet = ROOT / "experiments/core_resource_guidance_v1"
    for name in ("model-live-receipt-v1.json", "live-method-v2.json", "protocol-v1.json"):
        shutil.copyfile(packet / name, source / name)
    return source / "model-live-receipt-v1.json", sorted(FIXTURES.glob("*.json")), SCENARIO, RUBRIC


def test_stopped_resource_campaign_retains_unopened_pairs_and_pre_provider_attempt(resource_inputs):
    result = build_workbench(*resource_inputs)
    assert result["summary"] == {
        "planned_jobs": 12,
        "planned_turns": 24,
        "visited_turns": 16,
        "no_fresh_response_turns": 6,
        "fresh_proposal": 10,
        "stale_observation": 4,
        "no_fresh_proposal": 2,
        "unvisited": 8,
    }
    assert sum(len(row["actual_model_attempts"]) for row in result["rows"]) == 22
    assert {row["arm"] for row in result["rows"]} == {
        "resource_guidance_off",
        "resource_guidance_on",
    }
    guard = next(
        attempt
        for row in result["rows"]
        for attempt in row["actual_model_attempts"]
        if attempt["error_code"] == "ContextLimitExceeded"
    )
    assert guard["context"]["attempt_index"] == 2
    assert "pre_dispatch_stop" not in guard  # Original observation is never retrofitted.
    assert result["kind"] == "c4h-offline-review-workbench-v1"
    assert result["human_usefulness"] is None and not result["quality_claim"]


def test_resource_workbench_binds_active_v2_not_initial_registration_preview(resource_inputs):
    receipt, fixtures, scenario, rubric = resource_inputs
    folder = receipt.parent
    shutil.copyfile(
        ROOT / "experiments/core_resource_guidance_v1/live-method-v1.json",
        folder / "live-method-v2.json",
    )
    with pytest.raises(WorkbenchRejected, match="^WorkbenchReceiptMismatch$"):
        build_workbench(receipt, fixtures, scenario, rubric)


def test_unknown_campaign_is_rejected_before_loading_an_arbitrary_method(inputs):
    receipt, *rest = inputs
    value = json.loads(receipt.read_bytes())
    value["protocol_id"] = "unregistered-campaign"
    dump(receipt, value)
    with pytest.raises(WorkbenchRejected, match="^WorkbenchReceiptMismatch$"):
        build_workbench(receipt, *rest)


def test_fixed_oracle_is_preserved_but_native_conditions_are_explicit(inputs):
    result = build_workbench(*inputs)
    row = next(
        row
        for row in result["rows"]
        if row["case_id"] == "dev-case-b" and row["turn_id"] == "version"
    )
    assert row["registered_stratum"] == "answerable"
    assert row["oracle_evidence_condition"] == "controlled_fixed_evidence"
    assert row["oracle_evidence_condition_matches_actual"] is False
    assert "if retrieved" in row["actual_index_preregistered_criteria"]["acceptable"]
    assert result["human_reviewed"] is False
    assert result["human_usefulness"] is None
    assert result["held_out_test"] is result["quality_claim"] is False
    assert result["rubric_status"] == "draft_recommendation_not_team_frozen"


def test_templates_are_unassigned_and_incomplete_not_auto_approved(inputs):
    result = build_workbench(*inputs)
    for row in result["rows"]:
        template = row["review_template"]
        if template is None:
            continue
        assert template["reviewer_id"] == "unassigned"
        assert template["reviewer_kind"] == "assistant"
        assert template["claim_inventory_complete"] is False
        assert template["reviewed_surfaces"] == template["claim_bindings"] == []
        assert template["decision_judgment"] == "unassessed"
        assert template["usefulness_score"] is None
        handoff = ProposalHandoff.model_validate(row["original_proposal"]["handoff"])
        score = score_review(handoff, template, scope=ReviewScope.model_validate(row["scope"]))
        assert score.support_gate is None and score.support_status == "unassessed"
        assert score.complete_review is False


def test_current_reply_enriched_model_context_and_original_release_are_separate(inputs):
    result = build_workbench(*inputs)
    row = next(
        row
        for row in result["rows"]
        if row["case_id"] == "dev-case-a" and row["turn_id"] == "version"
    )
    assert row["consumed_input"]["message"] == "1.50.0"
    handoff = row["original_proposal"]["handoff"]
    assert handoff["user_message"] != "1.50.0"
    assert "Original user problem" in handoff["user_message"]
    assert row["edited_proposal"] is None
    assert row["released_outputs"]
    assert row["maintainer_behavior"] == "fixture_scripted_not_human_approval"
    assert row["original_proposal"]["surfaces"]["user_draft"] == handoff["analysis"]["user_draft"]
    assert any(
        fact["fact"]["name"] == "streamlit_version"
        for fact in row["original_proposal"]["active_user_facts"]
    )


def test_prepare_fresh_directory_no_rewrite_and_byte_inputs_unchanged(inputs, tmp_path):
    paths = [inputs[0], *inputs[1], inputs[2], inputs[3]]
    before = {str(path): path.read_bytes() for path in paths}
    output = tmp_path / "packet"
    result = prepare_workbench(*inputs, output)
    assert len(list(output.glob("pending-*.json"))) == 17
    assert len(list(output.glob("context-*.json"))) == 24
    assert load_workbench(output / "workbench.json") == result
    with pytest.raises(WorkbenchRejected, match="^WorkbenchOutputExists$"):
        prepare_workbench(*inputs, output)
    assert before == {str(path): path.read_bytes() for path in paths}


def test_local_html_reader_escapes_untrusted_output_and_never_executes_sources(inputs):
    workbench = build_workbench(*inputs)
    fresh = next(row for row in workbench["rows"] if row["status"] == "fresh_proposal")
    fresh["original_proposal"]["surfaces"]["user_draft"] = "<script>alert('attack')</script>"
    text = _html_index(workbench)
    assert "<script>" not in text
    assert "&lt;script&gt;" in text
    assert "<iframe" not in text
    assert "An unvisited turn has no model response" in text


@pytest.mark.parametrize("surface", ["context", "html"])
def test_changed_review_context_or_reader_is_rejected(prepared, surface):
    output, workbench = prepared
    if surface == "html":
        (output / "review-index.html").write_text("FORGED READER", encoding="utf-8")
    else:
        row = next(row for row in workbench["rows"] if row["status"] == "fresh_proposal")
        path = output / f"context-{row['item_id']}.json"
        data = json.loads(path.read_text())
        data["original_proposal"]["handoff"]["analysis"]["user_draft"] = "FORGED OUTPUT"
        dump(path, data)
    with pytest.raises(WorkbenchRejected):
        load_workbench(output / "workbench.json")


@pytest.mark.parametrize("kind", ["receipt", "scenario", "rubric", "fixture", "method", "protocol"])
def test_changed_original_inputs_block_scoring(prepared, kind):
    output, result = prepared
    pin = result["inputs"]["fixtures"][0] if kind == "fixture" else result["inputs"][kind]
    path = Path(pin["path"])
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(WorkbenchRejected, match="^WorkbenchInputChanged$"):
        score_workbench(output / "workbench.json", [])


def test_rehashed_mutated_workbench_cannot_replace_receipt_handoff(prepared):
    output, result = prepared
    changed = deepcopy(result)
    row = next(row for row in changed["rows"] if row["status"] == "fresh_proposal")
    row["original_proposal"]["handoff"]["analysis"]["user_draft"] = "FORGED OUTPUT"
    # Even a caller recomputing the workbench's self hash cannot change inputs.
    changed.pop("workbench_sha256")
    changed["workbench_sha256"] = hashlib.sha256(
        json.dumps(changed, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    dump(output / "workbench.json", changed)
    with pytest.raises(WorkbenchRejected, match="^WorkbenchReceiptMismatch$"):
        load_workbench(output / "workbench.json")


@pytest.mark.parametrize("mutation", ["display_draft", "current_input", "run_ids"])
def test_new_preparation_rejects_receipt_content_inconsistent_with_registered_run(inputs, mutation):
    receipt, _, _, _ = inputs
    value = json.loads(receipt.read_text())
    job = value["batches"][0]["jobs"][0]
    if mutation == "display_draft":
        job["steps"][0]["proposal"]["user_draft"] = "SECRET-FORGED-OUTPUT"
    elif mutation == "current_input":
        job["steps"][0]["request"]["message"] = "SECRET-FORGED-INPUT"
    else:
        job["run_ids"] = ["forged-run"]
    dump(receipt, value)
    with pytest.raises(WorkbenchRejected) as caught:
        build_workbench(*inputs)
    assert "SECRET" not in str(caught.value)


def test_pending_sidecar_not_mistaken_for_completed_human_review(prepared):
    output, result = prepared
    path = next(output.glob("pending-*.json"))
    with pytest.raises(WorkbenchRejected, match="^WorkbenchReviewUnassigned$"):
        score_workbench(output / "workbench.json", [path])


def test_partial_caller_judgment_keeps_unreviewed_and_missed_denominators(prepared):
    output, result = prepared
    payload = envelope(output, result)
    report = score_workbench(output / "workbench.json", [reviewed_path(output, payload)])
    assert report["summary"]["planned_turns"] == 24
    assert sum(arm["reviewed_fresh_proposals"] for arm in report["by_arm"].values()) == 1
    assert sum(arm["unreviewed_fresh_proposals"] for arm in report["by_arm"].values()) == 16
    assert (
        sum(
            arm["no_fresh_proposal"] + arm["stale_observations"]
            for arm in report["by_arm"].values()
        )
        == 6
    )
    assert sum(arm["unvisited"] for arm in report["by_arm"].values()) == 1
    assert report["scores"][0]["support_status"] == "unassessed"
    assert report["scores"][0]["question_status"] == "unassessed"
    assert report["human_review_authenticated"] is False
    assert report["quality_claim"] is False


@pytest.mark.parametrize("mutation", ["item", "scope", "binding", "handoff", "unknown_field"])
def test_wrong_sidecar_binding_or_scope_is_rejected(prepared, mutation):
    output, result = prepared
    payload = envelope(output, result)
    if mutation == "item":
        payload["item_id"] = "unknown"
    elif mutation == "scope":
        payload["review"]["scope"]["config_id"] = "wrong-arm"
    elif mutation == "binding":
        payload["item_binding_sha256"] = "0" * 64
    elif mutation == "handoff":
        payload["review"]["handoff_sha256"] = "0" * 64
    else:
        payload["SECRET-UNKNOWN-FIELD"] = "SECRET-VALUE"
    with pytest.raises(WorkbenchRejected) as caught:
        score_workbench(output / "workbench.json", [reviewed_path(output, payload)])
    assert "SECRET" not in str(caught.value)


def test_duplicate_reviews_not_counted_twice_even_with_new_review_id(prepared):
    output, result = prepared
    payload = envelope(output, result)
    first = reviewed_path(output, payload, "first.json")
    payload["review"]["review_id"] = "another-id"
    second = reviewed_path(output, payload, "second.json")
    with pytest.raises(WorkbenchRejected, match="^WorkbenchDuplicateReview$"):
        score_workbench(output / "workbench.json", [first, second])


def test_different_reviewer_and_assistant_scores_use_separate_panels(prepared):
    output, result = prepared
    paths = [
        reviewed_path(
            output, envelope(output, result, reviewer="human-one", kind="human"), "human.json"
        ),
        reviewed_path(
            output,
            envelope(output, result, reviewer="assistant-one", kind="assistant"),
            "assistant.json",
        ),
    ]
    report = score_workbench(output / "workbench.json", paths)
    assert len(report["reviewer_panels"]) == 2
    assert {panel["reviewer_kind"] for panel in report["reviewer_panels"]} == {"human", "assistant"}
    assert sum(arm["reviewed_fresh_proposals"] for arm in report["by_arm"].values()) == 1


@pytest.mark.parametrize("status", ["stale_observation", "no_fresh_proposal", "unvisited"])
def test_missed_or_stale_turns_cannot_receive_fresh_proposal_scores(prepared, status):
    output, result = prepared
    payload = envelope(output, result)
    row = next(row for row in result["rows"] if row["status"] == status)
    payload["item_id"] = row["item_id"]
    payload["item_binding_sha256"] = row["item_binding_sha256"]
    with pytest.raises(WorkbenchRejected, match="^WorkbenchReviewNotEligible$"):
        score_workbench(output / "workbench.json", [reviewed_path(output, payload)])


def test_bad_claim_quote_cannot_pass_support(prepared):
    output, result = prepared
    payload = envelope(output, result)
    row = next(row for row in result["rows"] if row["item_id"] == payload["item_id"])
    quote = row["original_proposal"]["handoff"]["evidence"]["hits"][0]
    draft = row["original_proposal"]["surfaces"]["user_draft"]
    payload["review"]["reviewed_surfaces"] = ["user_draft"]
    payload["review"]["declared_material_claim_count"] = 1
    payload["review"]["claim_bindings"] = [
        {
            "output": {"surface_id": "user_draft", "start": 0, "end": len(draft), "text": draft},
            "judgment": "supported",
            "applicability": "unknown",
            "source_quote": {
                "chunk_id": quote["chunk_id"],
                "start": 0,
                "end": 6,
                "quote": "FORGED",
            },
        }
    ]
    with pytest.raises(WorkbenchRejected, match="^WorkbenchScopeMismatch$"):
        score_workbench(output / "workbench.json", [reviewed_path(output, payload)])


def test_fresh_score_file_is_not_overwritten(prepared):
    output, _ = prepared
    path = output / "scores.json"
    write_score(path, {"quality_claim": False})
    with pytest.raises(WorkbenchRejected, match="^WorkbenchOutputExists$"):
        write_score(path, {"quality_claim": True})
    assert json.loads(path.read_text())["quality_claim"] is False


def test_cli_allows_prepare_but_never_turns_pending_into_scores(inputs, tmp_path, capsys):
    spec = importlib.util.spec_from_file_location(
        "prepare_semantic_review_cli", ROOT / "scripts/prepare_semantic_review.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output = tmp_path / "cli-private"
    receipt, fixtures, scenario, rubric = inputs
    assert (
        module.main(
            [
                "prepare",
                "--receipt",
                str(receipt),
                "--fixtures",
                *map(str, fixtures),
                "--scenario",
                str(scenario),
                "--rubric",
                str(rubric),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    summary = json.loads(capsys.readouterr().out)
    assert summary["summary"]["fresh_proposal"] == 17
    assert (
        module.main(
            [
                "score",
                "--workbench",
                str(output / "workbench.json"),
                "--reviews",
                str(next(output.glob("pending-*.json"))),
                "--output",
                str(output / "scores.json"),
            ]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().out)["code"] == "WorkbenchReviewUnassigned"
    assert not (output / "scores.json").exists()


@pytest.mark.parametrize(
    "folder,kind,expected",
    [
        ("core_repeat_repair_v1", "c4h2-offline-review-workbench-v1", (16, 1, 5, 2)),
        ("core_source_capacity_v1", "c4h3-offline-review-workbench-v1", (16, 0, 4, 4)),
    ],
)
def test_new_core_campaigns_use_bound_native_criteria_and_keep_every_planned_turn(
    tmp_path, folder, kind, expected
):
    packet = ROOT / "experiments" / folder
    output = tmp_path / "workbench"
    result = prepare_workbench(
        packet / "model-live-receipt-v1.json",
        sorted(FIXTURES.glob("*.json")),
        SCENARIO,
        RUBRIC,
        output,
    )
    assert result["kind"] == kind
    assert result["summary"]["planned_turns"] == 24
    counts = tuple(
        result["summary"][key]
        for key in ("fresh_proposal", "stale_observation", "no_fresh_proposal", "unvisited")
    )
    if expected is not None:
        assert counts == expected
    assert sum(counts) == 24
    assert load_workbench(output / "workbench.json") == result
    assert (
        result["inputs"]["native_criteria"]["sha256"]
        == hashlib.sha256((PACKET / "protocol-v1.json").read_bytes()).hexdigest()
    )
    assert all(not row["oracle_evidence_condition_matches_actual"] for row in result["rows"])
    assert all(
        row["review_template"] is None or row["review_template"]["usefulness_score"] is None
        for row in result["rows"]
    )


def test_core_review_rejects_changed_native_criteria_before_preparing(tmp_path, monkeypatch):
    from agent_app.evaluation import review_workbench

    changed = tmp_path / "criteria.json"
    value = json.loads((PACKET / "protocol-v1.json").read_bytes())
    value["pre_model_scenarios"][0]["acceptable"] = "Unregistered replacement criterion."
    dump(changed, value)
    monkeypatch.setitem(review_workbench._NATIVE_CRITERIA, "core-source-capacity-model-v1", changed)
    with pytest.raises(WorkbenchRejected, match="WorkbenchReceiptMismatch"):
        build_workbench(
            ROOT / "experiments/core_source_capacity_v1/model-live-receipt-v1.json",
            sorted(FIXTURES.glob("*.json")),
            SCENARIO,
            RUBRIC,
        )
