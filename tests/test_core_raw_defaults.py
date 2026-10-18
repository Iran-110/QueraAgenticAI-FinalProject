"""Neutral offline raw-document defaults controls; no provider or seed payloads."""

import copy
import dataclasses
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


def entry(signature='st.sample(label, *, mode="secondary", disabled=False)'):
    return {
        "name": "sample",
        "signature": signature,
        "description": "<p>All options and their caveats remain. default=word.</p>",
        "args": [
            {
                "name": "label",
                "type_name": "str",
                "default": None,
                "description": "Required label.",
            },
            {
                "name": "mode",
                "type_name": "str",
                "default": None,
                "description": '<p>Options include "primary", "secondary", and "tertiary".</p>',
            },
            {
                "name": "disabled",
                "type_name": "bool",
                "default": "is",
                "description": "<p>False leaves it enabled; True disables it. Do not infer timing.</p>",
            },
        ],
        "returns": [{"type_name": "bool", "description": "<p>Whether clicked.</p>"}],
        "example": "<pre>print('default=word')\n# Preserve this code</pre>",
        "examples": "Plural raw metadata survives, without silently entering the legacy projection.",
        "source": "https://example.org/official.py#L1",
        "notes": {"unknown": [False, 0, None, "None"]},
    }


def normalize(raw=None, text=None, **overrides):
    raw = entry() if raw is None else raw
    kwargs = {
        "version": "1.2.3",
        "function": "streamlit.sample",
        "expected_version": "1.2.3",
        "expected_function": "streamlit.sample",
        "docs_commit": "a" * 40,
        "raw_file_sha256": "b" * 64,
        "expected_entry_sha256": canonical_entry_sha256(raw),
    }
    kwargs.update(overrides)
    return normalize_raw_defaults(
        raw, reconstruct_legacy_text(raw) if text is None else text, **kwargs
    )


def test_real_failure_shapes_repaired_without_body_or_input_mutation():
    raw = entry()
    old = copy.deepcopy(raw)
    report = normalize(raw)
    assert raw == old
    assert 'mode: str; default="secondary"' in report.derived_text
    assert "disabled: bool; default=False" in report.derived_text
    assert "label: str\nRequired label." in report.derived_text
    assert report.original_text == reconstruct_legacy_text(raw)
    restored = report.original_text
    for observation in reversed(report.observations):
        start, end = observation.old_span
        assert restored[start:end] == observation.old_text
        restored = restored[:start] + observation.replacement + restored[end:]
    assert restored == report.derived_text
    assert report.original_text_sha256 != report.derived_text_sha256
    assert report.raw_membership_authenticated is False
    assert report.derived_text_is_complete_raw_documentation is False
    assert report.actual_runtime_defaults_verified is False
    assert report.proposal_or_action_authorized is False
    assert validate_raw_default_normalization(report) == report


def test_raw_unknown_fields_plural_examples_deprecation_remain_lossless():
    raw = entry()
    raw["args"][1]["deprecated"] = {"deprecated": True, "deprecatedText": "Full original warning."}
    report = normalize(raw)
    assert json.loads(report.canonical_raw_entry) == raw
    assert "Plural raw" not in report.derived_text
    assert report.observations[1].raw_default_state == "null_ambiguous"
    assert report.observations[2].raw_default_json == '"is"'


@pytest.mark.parametrize(
    "signature,states",
    [
        ("st.sample(label, *, mode=None, disabled=False)", ["required", "literal", "literal"]),
        (
            "st.sample(label=None, *, mode=DEFAULT, disabled=False)",
            ["literal", "unresolved_expression", "literal"],
        ),
        ("st.sample(label, /, mode='x', *, disabled)", ["required", "literal", "required"]),
        (
            "st.sample(label, *mode, **disabled)",
            ["required", "variadic_without_default", "variadic_without_default"],
        ),
    ],
)
def test_missing_literal_required_and_variadic_are_distinct(signature, states):
    report = normalize(entry(signature))
    assert [item.signature_state for item in report.observations] == states
    if "DEFAULT" in signature:
        assert report.observations[1].action == "preserve_unresolved"
        assert "mode: str; default=None" in report.derived_text
    assert report.observations[0].raw_default_state == "null_ambiguous"


@pytest.mark.parametrize(
    "token", ["False", "0", "None", '"None"', "-2", "1.25", "[False, 0]", "(None, 'None')"]
)
def test_signature_tokens_are_exact_typed_declarations(token):
    raw = entry(f"st.sample(label, *, mode={token}, disabled=False)")
    report = normalize(raw)
    assert report.observations[1].replacement == token
    assert "mode: str; default=" + token in report.derived_text


def test_unicode_quoted_delimiters_ast_offsets_and_crlf_preserved():
    raw = entry('st.sample(label="سلام,)", *, mode="é🙂", disabled=False)')
    lf = reconstruct_legacy_text(raw)
    report = normalize(raw, lf.replace("\n", "\r\n"))
    assert report.observations[1].signature_token == '"é🙂"'
    for item in report.observations:
        if item.signature_span:
            start, end = item.signature_span
            assert raw["signature"][start:end] == item.signature_token
        start, end = item.old_span
        assert report.original_text[start:end] == item.old_text
    assert "\n" not in report.derived_text.replace("\r\n", "")
    assert report.derived_text.replace("\r\n", "\n") == normalize(raw).derived_text


@pytest.mark.parametrize(
    "change",
    [
        lambda r: r["args"].pop(),
        lambda r: r["args"].append(copy.deepcopy(r["args"][0])),
        lambda r: r["args"].reverse(),
        lambda r: r["args"][1].update(name="other"),
        lambda r: r.update(name="other"),
        lambda r: r.update(signature="st.other(label, *, mode=None, disabled=False)"),
        lambda r: r["args"][1].update(type_name="str; default=OTHER"),
        lambda r: r.update(args=None),
        lambda r: r.update(description=42),
    ],
)
def test_ambiguous_or_mismatching_raw_entry_rejects(change):
    raw = entry()
    change(raw)
    with pytest.raises(ValueError, match="^RawDefaultNormalizationUnavailable$"):
        normalize(raw)


@pytest.mark.parametrize(
    "override",
    [
        {"expected_version": "1.2.4"},
        {"expected_function": "streamlit.other"},
        {"expected_entry_sha256": "c" * 64},
        {"raw_file_sha256": "bad"},
        {"docs_commit": "c" * 39},
        {"version": "bad"},
        {"function": "st.sample"},
        {"expected_version": True},
    ],
)
def test_provenance_declaration_mismatch_rejects(override):
    with pytest.raises(ValueError, match="^RawDefaultNormalizationUnavailable$"):
        normalize(**override)


@pytest.mark.parametrize("token", ["do_not_execute()", "obj.default", "{'x': 1}", "lambda: 1"])
def test_unsafe_default_grammar_rejects_without_execution(token):
    with pytest.raises(ValueError, match="^RawDefaultNormalizationUnavailable$"):
        normalize(entry(f"st.sample(label, *, mode={token}, disabled=False)"))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda s: s.replace("Required label.", "Swapped body"),
        lambda s: s.replace("Do not infer timing.", "Timing invented."),
        lambda s: s.replace("print('default=word')", "print('other')"),
        lambda s: s.replace("default=is", "default=False"),
        lambda s: s + "\n",
        lambda s: s.replace("\n", "\r"),
    ],
)
def test_historical_text_not_matching_full_raw_projection_rejects(mutate):
    with pytest.raises(ValueError, match="^RawDefaultNormalizationUnavailable$"):
        normalize(text=mutate(reconstruct_legacy_text(entry())))


def test_missing_metadata_default_is_not_none_or_required_authority():
    raw = entry()
    del raw["args"][1]["default"]
    report = normalize(raw)
    assert report.observations[1].raw_default_state == "missing"
    assert report.observations[1].raw_default_json is None
    assert report.observations[1].replacement == '"secondary"'


def test_descriptions_fenced_examples_and_default_word_remain_exact():
    raw = entry()
    raw["args"][1]["description"] = (
        "<p>Complete caveat.</p><pre>```python\npeer: not a header\n```</pre>"
    )
    report = normalize(raw)
    old = parse_parts(report.original_text)
    new = parse_parts(report.derived_text)
    assert old == new


def parse_parts(text):
    return [
        line
        for line in text.splitlines()
        if not line.startswith(("label: ", "mode: ", "disabled: "))
    ]


@pytest.mark.parametrize(
    "field,value",
    [
        ("derived_text", "changed"),
        ("version", "1.2.4"),
        ("raw_file_sha256", "c" * 64),
        ("context_sha256", "c" * 64),
        ("runtime_adoption", True),
        ("actual_runtime_defaults_verified", True),
        ("raw_membership_authenticated", True),
        ("human_review_required", 1),
        ("proposal_or_action_authorized", 0),
    ],
)
def test_full_report_strict_typed_recomputation_rejects_drift(field, value):
    report = dataclasses.replace(normalize(), **{field: value})
    with pytest.raises(ValueError, match="^RawDefaultNormalizationUnavailable$"):
        validate_raw_default_normalization(report)


@pytest.mark.parametrize(
    "value", [float("nan"), float("inf"), {1: "bad"}, (1, 2), object(), "\ud800"]
)
def test_non_json_or_non_utf8_raw_values_reject(value):
    raw = entry()
    raw["extras"] = value
    with pytest.raises(ValueError, match="^RawDefaultNormalizationUnavailable$"):
        canonical_entry_sha256(raw)


def test_function_long_name_and_generic_streamlit_alias_work():
    raw = entry("streamlit.sample(label, *, mode='x', disabled=False)")
    assert normalize(raw).observations[1].replacement == "'x'"


def test_identical_text_under_another_declared_version_does_not_alias_identity():
    before = normalize()
    after = normalize(version="1.2.4", expected_version="1.2.4")
    assert before.derived_text == after.derived_text
    assert before.derived_identity != after.derived_identity
    assert before.context_sha256 != after.context_sha256


@pytest.mark.parametrize("kwargs", [{"docs_commit": "c" * 40}, {"raw_file_sha256": "c" * 64}])
def test_identical_text_under_other_provenance_does_not_alias_identity(kwargs):
    before, after = normalize(), normalize(**kwargs)
    assert before.derived_text == after.derived_text
    assert before.original_text == after.original_text
    assert before.derived_identity != after.derived_identity


def test_raw_description_crlf_kept_and_full_legacy_crlf_derivation_supported():
    raw = entry()
    raw["args"][1]["description"] = "<pre>First line.\r\nFull caveat.</pre>"
    original = reconstruct_legacy_text(raw).replace("\r\n", "\n").replace("\n", "\r\n")
    report = normalize(raw, original)
    assert json.loads(report.canonical_raw_entry) == raw
    assert "First line.\r\nFull caveat." in report.derived_text
    assert report.original_text == original


def test_nested_observation_bool_index_cannot_impersonate_integer_span():
    report = normalize()
    first = dataclasses.replace(
        report.observations[0], old_span=(True, report.observations[0].old_span[1])
    )
    forged = dataclasses.replace(report, observations=(first, *report.observations[1:]))
    with pytest.raises(ValueError, match="^RawDefaultNormalizationUnavailable$"):
        validate_raw_default_normalization(forged)
