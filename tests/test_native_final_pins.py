"""Native final declarations use synthetic packets, never curated split contents."""

import hashlib
import json
from copy import deepcopy

import pytest
from test_eval_runner_final_preflight import (
    cli,
    forbid_factory,
)
from test_eval_runner_final_preflight import (
    runnable_bundle as runnable_bundle,
)
from test_evaluation_preflight import bundle as bundle
from test_evaluation_preflight import change_fixture, rejected, run, save

from agent_app.evaluation import runner
from agent_app.testing.http_pilot_runtime import offline_network

BINDING_FIELDS = (
    "build",
    "index_snapshot",
    "corpus_manifest_sha256",
    "allowlist_sha256",
    "exclusion_manifest_sha256",
)


def scope(bundle):
    return {
        "evidence_condition": "native_index",
        "build": "synthetic-native-build-v1",
        "index_snapshot": "synthetic-native-snapshot-v1",
        "corpus_manifest_sha256": bundle["manifest"]["corpus"]["sha256"],
        "allowlist_sha256": "a" * 64,
        "exclusion_manifest_sha256": "b" * 64,
    }


def native(bundle, indexes=(0,)):
    declared = scope(bundle)
    for index in indexes:

        def apply(fixture):
            fixture["native_scope"] = deepcopy(declared)
            for turn in fixture["turns"]:
                turn["gold"]["evidence_condition"] = "native_index"

        change_fixture(bundle, index, apply)
    return declared


def change_scope(bundle, key, value, *, index=0, remove=False):
    def change(fixture):
        if remove:
            fixture["native_scope"].pop(key)
        else:
            fixture["native_scope"][key] = value

    change_fixture(bundle, index, change)


def binding_sha256(declared):
    encoded = json.dumps(
        {key: declared[key] for key in BINDING_FIELDS},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def test_coherent_native_declarations_add_only_a_bounded_nonquality_observation(bundle):
    declared = native(bundle, range(30))
    report = run(bundle)
    assert report["accepted"] is True and report["quality_claim"] is False
    assert report["native_index_declarations"] == {
        "scope": "declared_final_packet_pins_only",
        "fixture_count": 30,
        "binding_sha256": binding_sha256(declared),
        "physical_index_verified": False,
        "semantic_support_assessed": False,
    }
    assert declared["build"] not in json.dumps(report)
    assert declared["index_snapshot"] not in json.dumps(report)


def test_fixed_packet_retains_the_exact_legacy_report_shape(bundle):
    report = run(bundle)
    assert report["accepted"] is True
    assert set(report) == {
        "accepted",
        "quality_claim",
        "eligibility_scope",
        "diagnostics",
        "hashes",
        "counts",
    }
    assert report["quality_claim"] is False
    assert report["eligibility_scope"] == "mechanical_frozen_artifact_eligibility_only"
    assert report["diagnostics"] == []


def test_native_and_fixed_fixtures_can_coexist_without_promoting_fixed_metadata(bundle):
    declared = native(bundle, (3, 17))
    report = run(bundle)
    assert report["accepted"] is True
    assert report["native_index_declarations"]["fixture_count"] == 2
    assert report["native_index_declarations"]["binding_sha256"] == binding_sha256(declared)
    assert report["counts"]["dev"] == report["counts"]["test"] == 15


@pytest.mark.parametrize("key", BINDING_FIELDS)
@pytest.mark.parametrize("mode", ["missing", "null", "blank"])
def test_missing_or_empty_native_binding_fields_cannot_pass_a_frozen_label(bundle, key, mode):
    native(bundle)
    change_scope(bundle, key, None if mode != "blank" else " ", remove=mode == "missing")
    rejected(run(bundle), "NativeIndexPinsRequired")


@pytest.mark.parametrize(
    "value",
    ["pending_final_build", " pending_final_build ", "PENDING_FINAL_BUILD", "Pending_Final_Build"],
)
def test_pending_build_is_rejected_even_with_other_well_formed_hashes(bundle, value):
    native(bundle)
    change_scope(bundle, "build", value)
    rejected(run(bundle), "NativeIndexPinsRequired")


@pytest.mark.parametrize("key", ["build", "index_snapshot"])
@pytest.mark.parametrize("value", [True, 1, "two words", "line\nbreak", "x" * 2001])
def test_native_identifiers_are_bounded_ids_without_coercion(bundle, key, value):
    native(bundle)
    change_scope(bundle, key, value)
    rejected(run(bundle), "NativeIndexPinsRequired")


@pytest.mark.parametrize("key,maximum", [("build", 128), ("index_snapshot", 160)])
def test_native_identifier_limits_accept_the_boundary_and_reject_one_more(bundle, key, maximum):
    native(bundle)
    change_scope(bundle, key, "x" * maximum)
    assert run(bundle)["accepted"] is True
    change_scope(bundle, key, "x" * (maximum + 1))
    rejected(run(bundle), "NativeIndexPinsRequired")


@pytest.mark.parametrize(
    "key", ["corpus_manifest_sha256", "allowlist_sha256", "exclusion_manifest_sha256"]
)
@pytest.mark.parametrize("value", [True, 3, "a" * 63, "A" * 64, "g" * 64])
def test_each_native_sha_is_a_full_lowercase_digest(bundle, key, value):
    native(bundle)
    change_scope(bundle, key, value)
    rejected(run(bundle), "NativeIndexPinsRequired")


@pytest.mark.parametrize("value", [None, [], "private-untrusted-value"])
def test_native_gold_without_a_scope_object_fails_with_safe_diagnostic(bundle, value):
    native(bundle)
    change_fixture(bundle, 0, lambda fixture: fixture.update(native_scope=value))
    report = run(bundle)
    rejected(report, "NativeIndexPinsRequired")
    assert "private-untrusted-value" not in json.dumps(report)


def test_missing_native_scope_cannot_hide_behind_native_gold_labels(bundle):
    native(bundle)
    change_fixture(bundle, 0, lambda fixture: fixture.pop("native_scope"))
    rejected(run(bundle), "NativeIndexPinsRequired")


@pytest.mark.parametrize("label", [None, "controlled_fixed_evidence", "native-index", True])
def test_scope_label_must_agree_with_all_native_turns(bundle, label):
    native(bundle)
    change_scope(bundle, "evidence_condition", label)
    rejected(run(bundle), "NativeEvidenceConditionRejected")


@pytest.mark.parametrize("mode", ["missing", "fixed", "wrong_type"])
def test_mixed_turn_labels_cannot_launder_native_pin_checks(bundle, mode):
    native(bundle)

    def change(fixture):
        gold = fixture["turns"][1]["gold"]
        if mode == "missing":
            gold.pop("evidence_condition")
        else:
            gold["evidence_condition"] = "controlled_fixed_evidence" if mode == "fixed" else True

    change_fixture(bundle, 0, change)
    rejected(run(bundle), "NativeEvidenceConditionRejected")


def test_native_scope_alone_triggers_condition_validation_before_missing_pins(bundle):
    change_fixture(bundle, 0, lambda fixture: fixture.update(native_scope={}))
    rejected(run(bundle), "NativeEvidenceConditionRejected")


def test_native_corpus_pin_must_match_the_already_verified_corpus_file(bundle):
    native(bundle)
    change_scope(bundle, "corpus_manifest_sha256", "c" * 64)
    rejected(run(bundle), "NativeCorpusHashMismatch")


def test_corpus_hash_is_raw_file_identity_not_canonical_json_equivalence(bundle):
    native(bundle)
    corpus_path = bundle["root"] / "corpus.json"
    corpus_path.write_bytes(corpus_path.read_bytes() + b"\n")
    bundle["manifest"]["corpus"]["sha256"] = hashlib.sha256(corpus_path.read_bytes()).hexdigest()
    save(bundle)
    rejected(run(bundle), "NativeCorpusHashMismatch")


@pytest.mark.parametrize(
    "key", ["build", "index_snapshot", "allowlist_sha256", "exclusion_manifest_sha256"]
)
def test_native_fixtures_must_declare_one_consistent_binding_across_the_packet(bundle, key):
    native(bundle, (0, 29))
    value = "c" * 64 if key.endswith("sha256") else "other-valid-synthetic-id"
    change_scope(bundle, key, value, index=29)
    rejected(run(bundle), "NativeIndexBindingMismatch")


def test_notes_are_neither_binding_authority_nor_exported_content(bundle):
    declared = native(bundle, (0, 29))
    change_scope(bundle, "note", "PRIVATE-ANNOTATION-ONE")
    change_scope(bundle, "note", "PRIVATE-ANNOTATION-TWO", index=29)
    report = run(bundle)
    assert report["accepted"] is True
    assert report["native_index_declarations"]["binding_sha256"] == binding_sha256(declared)
    assert "PRIVATE-ANNOTATION" not in json.dumps(report)


def test_invalid_native_final_packet_stops_before_any_live_factory(
    runnable_bundle, monkeypatch, capsys
):
    native(runnable_bundle)
    change_scope(runnable_bundle, "build", "pending_final_build")
    calls = forbid_factory(monkeypatch)
    assert runner.main(cli(runnable_bundle)) == 1
    assert calls == []
    assert json.loads(capsys.readouterr().err) == {"code": "FinalEvaluationPreflightRejected"}


def test_ordinary_offline_development_does_not_gain_a_final_freeze_gate(runnable_bundle):
    native(runnable_bundle, (10,))
    change_scope(runnable_bundle, "build", "pending_final_build", index=10)
    with offline_network():
        receipt = runner.run([runnable_bundle["paths"][10]], mode="offline")
    assert receipt["summary"]["failed"] == 0
    assert receipt["quality_claim"] is False
    assert receipt["final_artifact_preflight"] is None
