"""Independent neutral counterexamples for offline source-default derivations."""

import builtins
import copy
import dataclasses
import inspect
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.core_raw_defaults_v1.normalization import (  # noqa: E402
    canonical_entry_sha256,
    normalize_raw_defaults,
    reconstruct_legacy_text,
    validate_raw_default_normalization,
)


def raw_entry(signature='st.inspectable(label, *, style="secondary", disabled=False)'):
    return {
        "name": "inspectable",
        "signature": signature,
        "description": "<p>فارسی 🙂: default=None is a quote, not authority.</p>",
        "args": [
            {"name": "label", "type_name": "str", "description": "Required, no default."},
            {
                "name": "style",
                "type_name": "str",
                "default": None,
                "description": "<p>Keep all choices and this default=None prose.</p>",
            },
            {
                "name": "disabled",
                "type_name": "bool",
                "default": "is",
                "description": "<p>False enables; True disables. No automatic re-enable.</p>",
            },
        ],
        "returns": [{"type_name": "bool", "description": "Whether activated."}],
        "example": "<pre>print('disabled: bool; default=is')\n# Keep literal example</pre>",
        "examples": [{"code": "unprojected()", "deprecated": True}],
        "deprecated": {"text": "Do not discard this raw-only warning."},
        "provenance": {"caller_claim": [True, 1, 1.0, False, None, "None"]},
    }


def derive(raw=None, legacy=None, **overrides):
    raw = raw_entry() if raw is None else raw
    settings = {
        "version": "1.2.3",
        "expected_version": "1.2.3",
        "function": "streamlit.inspectable",
        "expected_function": "streamlit.inspectable",
        "docs_commit": "1" * 40,
        "raw_file_sha256": "2" * 64,
        "expected_entry_sha256": canonical_entry_sha256(raw),
    }
    settings.update(overrides)
    return normalize_raw_defaults(
        raw, reconstruct_legacy_text(raw) if legacy is None else legacy, **settings
    )


def rejected(report):
    with pytest.raises(ValueError, match="^RawDefaultNormalizationUnavailable$"):
        validate_raw_default_normalization(report)


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_exact_patch_preserves_every_non_default_byte_including_example_and_prose(newline):
    raw = raw_entry('st.inspectable(label="é🙂", *, style="a; default=b", disabled=False)')
    legacy = reconstruct_legacy_text(raw).replace("\n", newline)
    report = derive(raw, legacy)
    edits = report.observations
    cursor = 0
    pieces = []
    for edit in edits:
        start, end = edit.old_span
        assert cursor <= start <= end
        assert legacy[start:end] == edit.old_text
        pieces.extend((legacy[cursor:start], edit.replacement))
        cursor = end
    pieces.append(legacy[cursor:])
    assert "".join(pieces) == report.derived_text
    assert "default=None is a quote, not authority." in report.derived_text
    assert "this default=None prose." in report.derived_text
    assert "print('disabled: bool; default=is')" in report.derived_text
    assert 'style: str; default="a; default=b"' in report.derived_text
    assert ("\r\n" in report.derived_text) is (newline == "\r\n")
    assert validate_raw_default_normalization(report) == report


def test_complete_raw_only_metadata_is_retained_but_never_added_to_historical_projection():
    raw = raw_entry()
    report = derive(raw)
    retained = json.loads(report.canonical_raw_entry)
    assert retained == raw
    assert type(retained["provenance"]["caller_claim"][0]) is bool
    assert type(retained["provenance"]["caller_claim"][1]) is int
    assert type(retained["provenance"]["caller_claim"][2]) is float
    assert "Do not discard" not in report.original_text
    assert "unprojected()" not in report.derived_text
    raw["deprecated"]["text"] = "subsequent caller mutation"
    assert "Do not discard" in report.canonical_raw_entry
    assert validate_raw_default_normalization(report) == report


def test_provenance_syntax_is_not_physical_file_or_installed_runtime_authentication():
    first = derive()
    second = derive(raw_file_sha256="3" * 64, docs_commit="4" * 40)
    assert first.derived_text == second.derived_text
    assert first.context_sha256 != second.context_sha256
    assert second.json_pointer == "/1.2.3/streamlit.inspectable"
    assert second.raw_membership_authenticated is False
    assert second.actual_runtime_defaults_verified is False
    assert second.runtime_adoption is False


def test_literal_defaults_depend_on_supplied_signature_without_name_or_runtime_resolution(
    monkeypatch,
):
    def unexpected(*args, **kwargs):
        raise AssertionError("Runtime lookup or expression evaluation attempted")

    raw = raw_entry(
        "st.inspectable(label=None, *, style=UNRESOLVED_REVIEW_SENTINEL, disabled=-0.0)"
    )
    with monkeypatch.context() as patch:
        patch.setattr(inspect, "signature", unexpected)
        patch.setattr(builtins, "eval", unexpected)
        patch.setattr(builtins, "UNRESOLVED_REVIEW_SENTINEL", object(), raising=False)
        report = derive(raw)
        assert report.observations[0].signature_state == "literal"
        assert report.observations[0].replacement == "None"
        assert report.observations[1].signature_state == "unresolved_expression"
        assert report.observations[1].replacement == "None"
        assert report.observations[2].replacement == "-0.0"
        assert validate_raw_default_normalization(report) == report


@pytest.mark.parametrize("token", ["[UNKNOWN, None]", "(False, UNKNOWN)"])
def test_partially_unknown_composite_is_not_promoted_to_a_literal_default(token):
    report = derive(raw_entry(f"st.inspectable(label, *, style={token}, disabled=False)"))
    observation = report.observations[1]
    assert observation.signature_state == "unresolved_expression"
    assert observation.action == "preserve_unresolved"
    assert observation.replacement == "None"
    assert token in report.derived_text.splitlines()[0]
    assert "style: str; default=None" in report.derived_text


@pytest.mark.parametrize("field", ["description", "example", "examples", "deprecated"])
def test_raw_digest_detects_changes_outside_parameter_fields(field):
    raw = raw_entry()
    old_hash = canonical_entry_sha256(raw)
    raw[field] = "different source content"
    with pytest.raises(ValueError, match="^RawDefaultNormalizationUnavailable$"):
        derive(raw, expected_entry_sha256=old_hash)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda s: s.replace("No automatic re-enable.", "Automatic re-enable is guaranteed."),
        lambda s: s.replace("Required, no default.", "Optional."),
        lambda s: s.replace("Keep literal example", "tampered example"),
        lambda s: s.replace("فارسی", "Persian"),
        lambda s: s.replace("Whether activated.", "New return contract."),
    ],
)
def test_expected_entry_hash_does_not_authorize_substituted_legacy_body(mutation):
    raw = raw_entry()
    with pytest.raises(ValueError, match="^RawDefaultNormalizationUnavailable$"):
        derive(raw, mutation(reconstruct_legacy_text(raw)))


@pytest.mark.parametrize(
    "field,value",
    [
        ("raw_membership_authenticated", 0),
        ("actual_runtime_defaults_verified", 0.0),
        ("runtime_adoption", 0),
        ("human_review_required", 1.0),
        ("proposal_or_action_authorized", 0.0),
        ("semantic_support", False),
        ("basis", "installed_runtime"),
        ("expected_function", "streamlit.other"),
        ("expected_version", "1.2.4"),
        ("json_pointer", "/other/streamlit.inspectable"),
        ("derived_identity", "api-signature-defaults-v1:" + "0" * 64),
        ("schema_id", "raw-default-normalization-v2"),
        ("observations", []),
    ],
)
def test_report_flags_metadata_and_collection_types_are_strictly_revalidated(field, value):
    rejected(dataclasses.replace(derive(), **{field: value}))


@pytest.mark.parametrize(
    "field,value",
    [
        ("signature_state", "required"),
        ("signature_token", "False"),
        ("signature_span", [0, 1]),
        ("raw_default_state", "missing"),
        ("raw_default_json", "false"),
        ("action", "remove_spurious_default"),
        ("old_span", (True, 2)),
        ("old_span", (1.0, 2.0)),
        ("old_text", "forged"),
        ("replacement", "False"),
    ],
)
def test_nested_observation_fields_cannot_be_reconstructed_as_authority(field, value):
    report = derive()
    changed = dataclasses.replace(report.observations[1], **{field: value})
    rejected(
        dataclasses.replace(
            report, observations=(report.observations[0], changed, report.observations[2])
        )
    )


@pytest.mark.parametrize("field", ["old_span", "signature_span"])
def test_equal_valued_float_coordinates_reject_instead_of_passing_python_tuple_equality(field):
    report = derive()
    observation = report.observations[1]
    original_span = getattr(observation, field)
    alias_span = tuple(float(value) for value in original_span)
    assert alias_span == original_span  # Equality alone would miss this wire-type drift.
    changed = dataclasses.replace(observation, **{field: alias_span})
    rejected(
        dataclasses.replace(
            report,
            observations=(report.observations[0], changed, report.observations[2]),
        )
    )


def test_canonical_raw_string_type_changes_and_extra_fields_invalidate_old_report_binding():
    report = derive()
    changed = json.loads(report.canonical_raw_entry)
    changed["provenance"]["caller_claim"][0] = 1
    serialized = json.dumps(changed, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    rejected(dataclasses.replace(report, canonical_raw_entry=serialized))
    changed["extra"] = "must be bound"
    serialized = json.dumps(changed, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    rejected(dataclasses.replace(report, canonical_raw_entry=serialized))


def test_derived_text_is_not_accepted_as_original_legacy_text_for_same_raw_entry():
    report = derive()
    assert report.derived_text != report.original_text
    with pytest.raises(ValueError, match="^RawDefaultNormalizationUnavailable$"):
        derive(legacy=report.derived_text)


def test_distinct_raw_none_string_false_and_zero_do_not_establish_signature_defaults():
    raw = raw_entry()
    raw["args"][0]["default"] = "None"
    raw["args"][1]["default"] = False
    raw["args"][2]["default"] = 0
    report = derive(raw)
    assert [o.raw_default_json for o in report.observations] == ['"None"', "false", "0"]
    assert [o.action for o in report.observations] == [
        "remove_spurious_default",
        "signature_literal",
        "signature_literal",
    ]
    assert "label: str\nRequired, no default." in report.derived_text
    assert 'style: str; default="secondary"' in report.derived_text
    assert "disabled: bool; default=False" in report.derived_text


def test_input_copy_mutation_is_not_hidden_by_report_dataclass_freezing():
    raw = raw_entry()
    report = derive(raw)
    copied = copy.deepcopy(raw)
    copied["args"][1]["description"] = "Replacement body"
    with pytest.raises(ValueError, match="^RawDefaultNormalizationUnavailable$"):
        derive(copied, report.original_text)
