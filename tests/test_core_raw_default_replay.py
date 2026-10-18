"""Raw pointer/source custody and declared-default audit; no model-quality score."""

import hashlib
import importlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def replay(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT))
    return importlib.import_module("experiments.core_raw_defaults_v1.replay")


def test_raw_defaults_adjudicate_prior_sources_without_rewriting_or_authorizing(replay):
    result = replay.run_replay()
    assert result["full_raw_file_hash_and_pointer_membership_verified_in_this_run"] is False
    assert result["pinned_python_declaration_ast_verified_in_this_run"] is False
    assert result["provider_calls"] == result["ledger_writes"] == 0
    assert result["original_attempts_retained"] == 8
    assert result["original_final_turns_retained"] == 7
    assert result["runtime_adoption"] is result["old_artifacts_or_drafts_rewritten"] is False
    assert result["actual_installed_runtime_verified"] is False
    assert result["human_usefulness"] is None
    assert [
        (x["parameter"], x["signature_declared_default"])
        for x in result["historical_candidate_source_links"]
    ] == [
        ("icon", "None"),
        ("type", '"secondary"'),
        ("disabled", "False"),
    ]
    primary = next(row for row in result["rows"] if row["version"] == "1.49.0")
    report = primary["normalization"]
    assert "disabled: bool; default=False\n" in report["derived_text"]
    assert (
        'type: "primary", "secondary", or "tertiary"; default="secondary"\n'
        in report["derived_text"]
    )
    assert "label: str\n" in report["derived_text"]
    assert report["raw_membership_authenticated"] is False
    assert report["derived_text_is_complete_raw_documentation"] is False
    raw = json.loads(report["canonical_raw_entry"])
    assert raw["args"][6]["default"] is None and raw["args"][8]["default"] == "is"
    assert raw["examples"] and raw["args"][9]["deprecated"]["deprecatedText"]
    assert primary["all_legacy_parameter_bodies_and_global_context_preserved"]


def _raw_document(replay):
    entry = {"signature": "st.neutral(value=None)", "name": "neutral"}
    raw = json.dumps({"1.49.0": {"streamlit.neutral": entry}}).encode()
    snapshot = {
        "source_file_sha256": hashlib.sha256(raw).hexdigest(),
        "records": [
            {
                "version": "1.49.0",
                "function": "streamlit.neutral",
                "raw_entry_sha256": replay.canonical_entry_sha256(entry),
            }
        ],
    }
    return raw, snapshot


def test_full_raw_document_requires_both_physical_hash_and_pointer_entry(replay):
    raw, snapshot = _raw_document(replay)
    assert replay.verify_raw_document(raw, snapshot)
    with pytest.raises(ValueError):
        replay.verify_raw_document(raw + b" ", snapshot)
    snapshot["records"][0]["raw_entry_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        replay.verify_raw_document(raw, snapshot)


def test_duplicate_raw_keys_reject_even_when_physical_hash_matches(replay):
    raw, snapshot = _raw_document(replay)
    duplicated = raw.replace(b'"name": "neutral"', b'"name": "wrong", "name": "neutral"')
    snapshot["source_file_sha256"] = hashlib.sha256(duplicated).hexdigest()
    with pytest.raises(ValueError):
        replay.verify_raw_document(duplicated, snapshot)


def _implementation():
    text = (
        'raise AssertionError("This source must never execute")\n'
        "class NeutralAPI:\n"
        '    def widget(self, *, mode="safe", disabled=False):\n'
        "        return mode\n"
    )
    check = {
        "sha256": hashlib.sha256(text.encode()).hexdigest(),
        "qualified_function": "NeutralAPI.widget",
        "declared_defaults": {
            "mode": {"value": "safe", "source_token": '"safe"', "line": 3},
            "disabled": {"value": False, "source_token": "False", "line": 3},
        },
    }
    return text.encode(), check


def test_implementation_check_parses_without_import_or_execution(replay):
    raw, check = _implementation()
    assert replay.verify_implementation_source(raw, check)
    with pytest.raises(ValueError):
        replay.verify_implementation_source(raw + b"\n", check)


def test_implementation_line_coordinate_rejects_equal_float(replay):
    raw, check = _implementation()
    check["declared_defaults"]["disabled"]["line"] = 3.0
    with pytest.raises(ValueError):
        replay.verify_implementation_source(raw, check)


@pytest.mark.parametrize("value", [0, 0.0, "False", None])
def test_source_default_verification_does_not_coerce_bool_or_missing_values(replay, value):
    raw, check = _implementation()
    check["declared_defaults"]["disabled"]["value"] = value
    with pytest.raises(ValueError):
        replay.verify_implementation_source(raw, check)


@pytest.mark.parametrize("value", [True, 0.0, "0", 1])
def test_driver_cannot_acquire_coerced_provider_permission(replay, monkeypatch, value):
    read = replay._read

    def mutate(path, *args):
        raw = read(path, *args)
        if path.name == "protocol-v1.json" and path.parent == replay.PACKAGE:
            payload = json.loads(raw)
            payload["provider_calls_planned"] = value
            return json.dumps(payload).encode()
        return raw

    monkeypatch.setattr(replay, "_read", mutate)
    with pytest.raises(ValueError, match="^RawDefaultReplayRejected$"):
        replay.run_replay()


def test_snapshot_drift_rejects_before_claiming_source_correction(replay, monkeypatch):
    read = replay._read

    def mutate(path, *args):
        raw = read(path, *args)
        return raw + b" " if path.name == "raw-api-snapshot-v1.json" else raw

    monkeypatch.setattr(replay, "_read", mutate)
    with pytest.raises(ValueError, match="^RawDefaultReplayRejected$"):
        replay.run_replay()
