"""Authored challenges test static scope, never live semantic quality."""

import json
import sys

import httpx
import pytest
from pydantic import ValidationError

from agent_app.llm.budget import BudgetLedger
from agent_app.reasoning import semantic_regressions as replay


def replace_scenario(pack, index, **changes):
    scenarios = list(pack.scenarios)
    scenarios[index] = scenarios[index].model_copy(update=changes)
    return pack.model_copy(update={"scenarios": tuple(scenarios)})


def test_full_proposals_retain_registered_source_and_caller_boundaries():
    pack = replay.load_semantic_pack()
    assert len(pack.scenarios) == 8
    assert sum(len(s.variants) for s in pack.scenarios) == 16
    assert sum(s.role == "paired" for s in pack.scenarios) == 6
    assert sum(s.synthetic_supplement is not None for s in pack.scenarios) == 2
    for scenario in pack.scenarios:
        assert scenario.origin_url is scenario.origin_issue_id is scenario.origin_created_at is None
        assert (
            scenario.proposal_requirements.case_id,
            scenario.proposal_requirements.case_revision,
        ) == (scenario.case_state.case_id, scenario.case_state.case_revision)


def test_replay_separates_static_scope_from_authored_semantic_labels():
    result = replay.replay_semantic_pack(replay.load_semantic_pack())
    assert result["real_api_calls"] == 0
    assert result["semantic_quality_measured"] is False
    assert result["synthetic_author_labels_only"] is True
    assert result["scripted_repetition_is_not_model_repair"] is True
    assert result["detector_expectations_matched"] == result["proposals"] == 16
    positives = [r for r in result["observations"] if r["control"] == "positive"]
    negatives = [r for r in result["observations"] if r["control"] == "negative"]
    assert len(positives) == 7 and len(negatives) == 9
    assert all(r["checks_on"]["accepted"] for r in positives)
    assert all(r["checks_off"]["accepted"] for r in result["observations"])
    rejected = [r for r in negatives if not r["checks_on"]["accepted"]]
    assert len(rejected) == 1
    assert rejected[0]["expected_check_codes"] == ["callback_arity_mismatch"]
    assert rejected[0]["checks_on"]["scripted_attempts"] == 2
    assert rejected[0]["checks_on"]["error_code"] == "ModelOutputInvalid"
    # Out-of-scope semantic defects remain visible, including the larger app fence.
    assert sum(r["checks_on"]["accepted"] for r in negatives) == 8


def test_author_semantic_label_has_no_effect_on_runtime_judgment():
    pack = replay.load_semantic_pack()
    variants = list(pack.scenarios[0].variants)
    index = next(i for i, v in enumerate(variants) if v.control == "negative")
    variant = variants[index]
    variants[index] = variant.model_copy(
        update={
            "semantic_expectation": variant.semantic_expectation.model_copy(
                update={"label": "needs_revision"}
            )
        }
    )
    original = replay.replay_semantic_pack(pack)["observations"]
    updated = replay.replay_semantic_pack(replace_scenario(pack, 0, variants=tuple(variants)))[
        "observations"
    ]
    for before, after in zip(original, updated, strict=True):
        assert before["checks_on"] == after["checks_on"]
        assert before["checks_off"] == after["checks_off"]
        assert before["detector_expectation_matched"] == after["detector_expectation_matched"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("sha256", "0" * 64),
        ("requirements_sha256", "0" * 64),
        ("docs_commit", "changed-commit"),
        ("snapshot_id", "changed-snapshot"),
        ("source_snapshot_date", "1900-01-01"),
    ],
)
def test_frozen_hash_or_metadata_mismatch_stops_before_ports(field, value, monkeypatch):
    pack = replay.load_semantic_pack()
    changed = pack.model_copy(
        update={"frozen_input": pack.frozen_input.model_copy(update={field: value})}
    )
    monkeypatch.setattr(
        replay, "SupportEngine", lambda *args, **kwargs: pytest.fail("No port before validation")
    )
    with pytest.raises(ValueError):
        replay.replay_semantic_pack(changed)


@pytest.mark.parametrize(
    "field", ["case_state", "evidence_bundle", "proposal_requirements", "user_message"]
)
def test_undeclared_context_or_catalog_change_is_rejected(field):
    pack = replay.load_semantic_pack()
    scenario = pack.scenarios[0]
    if field == "case_state":
        value = scenario.case_state.model_copy(update={"case_revision": 99})
    elif field == "evidence_bundle":
        hit = scenario.evidence_bundle.hits[0].model_copy(
            update={"excerpt": "Changed source text."}
        )
        value = scenario.evidence_bundle.model_copy(
            update={"hits": (hit, *scenario.evidence_bundle.hits[1:])}
        )
    elif field == "proposal_requirements":
        value = scenario.proposal_requirements.model_copy(
            update={"require_fresh_widget_value": False}
        )
    else:
        value = scenario.user_message + " Undeclared extra report."
    with pytest.raises(ValueError):
        replay.validate_semantic_pack(replace_scenario(pack, 0, **{field: value}))


def test_supplement_requires_exact_marked_message_and_description():
    pack = replay.load_semantic_pack()
    index = next(i for i, s in enumerate(pack.scenarios) if s.synthetic_supplement)
    with pytest.raises(ValueError):
        replay.validate_semantic_pack(replace_scenario(pack, index, context_adaptation=None))
    with pytest.raises(ValueError):
        replay.validate_semantic_pack(
            replace_scenario(pack, index, synthetic_supplement="Unmarked rewrite.")
        )


def test_unavailable_citation_is_rejected_before_replay():
    pack = replay.load_semantic_pack()
    variants = list(pack.scenarios[0].variants)
    variant = variants[0]
    link = variant.proposal.evidence_links[0].model_copy(update={"chunk_id": "unknown:source"})
    variants[0] = variant.model_copy(
        update={"proposal": variant.proposal.model_copy(update={"evidence_links": (link,)})}
    )
    with pytest.raises(ValueError):
        replay.validate_semantic_pack(replace_scenario(pack, 0, variants=tuple(variants)))


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate_scenario",
        "duplicate_variant",
        "unknown_code",
        "inconsistent_label",
        "final_heldout",
        "source_path",
    ],
)
def test_strict_scope_and_label_contracts_reject_changes(mutation):
    raw = replay.load_semantic_pack().model_dump(mode="json")
    if mutation == "duplicate_scenario":
        raw["scenarios"].append(raw["scenarios"][0])
    elif mutation == "duplicate_variant":
        raw["scenarios"][0]["variants"].append(raw["scenarios"][0]["variants"][0])
    elif mutation == "unknown_code":
        raw["scenarios"][0]["variants"][1]["expected_check_codes"] = ["arbitrary_code"]
    elif mutation == "inconsistent_label":
        raw["scenarios"][0]["variants"][0]["semantic_expectation"]["label"] = "unusable"
    elif mutation == "final_heldout":
        raw["frozen_input"]["private_outputs_or_final_heldout_inputs_used"] = True
    else:
        raw["frozen_input"]["path"] = "../../outside.json"
    with pytest.raises(ValidationError):
        replay.SemanticRegressionPack.model_validate(raw)


def test_pack_size_is_bounded_before_validation(monkeypatch):
    monkeypatch.setattr(replay, "_MAX_PACK_BYTES", 10)
    with pytest.raises(ValueError):
        replay.load_semantic_pack()


def test_full_length_scenario_identity_remains_replayable():
    pack = replay.load_semantic_pack()
    changed = replace_scenario(pack, 0, id="s" * 200)
    result = replay.replay_semantic_pack(changed)
    assert result["detector_expectations_matched"] == result["proposals"] == 16


def test_canonical_identities_avoid_delimiter_collisions_and_separate_conditions():
    identities = {
        replay.semantic_run_id("pack", "a:b", "c", False),
        replay.semantic_run_id("pack", "a", "b:c", False),
        replay.semantic_run_id("pack", "a:b", "c", True),
        replay.semantic_run_id("other-pack", "a:b", "c", False),
    }
    assert len(identities) == 4
    assert all(len(value) < 200 for value in identities)
    assert replay.semantic_run_id("pack", "a:b", "c", False) in identities


def test_cli_stays_offline_in_live_environment_and_never_loads_a_ledger(monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        pytest.fail("Offline replay must never send HTTP or load a ledger")

    monkeypatch.setattr(httpx.Client, "send", forbidden)
    monkeypatch.setattr(BudgetLedger, "__init__", forbidden)
    monkeypatch.setenv("METIS_API_KEY", "PRIVATE_FAKE_REPLAY_CREDENTIAL")
    monkeypatch.setenv("METIS_LIVE_ENABLED", "true")
    monkeypatch.setattr(sys, "argv", ["semantic-regressions"])
    assert replay.main() == 0
    output = capsys.readouterr()
    assert output.err == ""
    assert "PRIVATE_FAKE_REPLAY_CREDENTIAL" not in output.out
    assert json.loads(output.out)["real_api_calls"] == 0


def test_invalid_cli_input_exports_only_allowlisted_error_code(tmp_path, monkeypatch, capsys):
    path = tmp_path / "pack.json"
    path.write_text('{"PRIVATE_UNKNOWN_PACK_FIELD": "PRIVATE_INVALID_PACK_CONTENT"}')
    monkeypatch.setattr(sys, "argv", ["semantic-regressions", "--pack", str(path)])
    assert replay.main() == 1
    output = capsys.readouterr()
    assert json.loads(output.out) == {
        "error_code": "InvalidSemanticRegressionPack",
        "real_api_calls": 0,
    }
    assert output.err == ""
