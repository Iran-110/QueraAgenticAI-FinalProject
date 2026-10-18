"""Neutral integrity counterexamples; not source truth or model quality scores."""

import hashlib
import importlib
import json
from dataclasses import FrozenInstanceError, asdict, replace
from pathlib import Path

import pytest

from agent_app.contracts import CaseState, EvidenceBundle, EvidenceHit, Fact
from agent_app.reasoning.grounding import make_grounded_request

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def api(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT))
    return (
        importlib.import_module("experiments.core_parameter_focus_v1.candidate"),
        importlib.import_module("experiments.core_parameter_review_v1.integrity"),
    )


def source(signature='neutral.widget(value, *, mode="safe")', headers=None):
    headers = headers or ("value: object", 'mode: str; default="safe"')
    return (
        signature
        + "\n\nA complete neutral source; global caveats remain outside units.\n\nParameters:\n\n"
        + "\n\n".join(
            header + "\nThe entire parameter definition, including caveats." for header in headers
        )
        + "\n\nReturns: object\nThe complete return definition.\n\nNotes:\nA shared caveat."
    )


def prepare(api, *, text=None, selected=(1,), span="auto", revision=2, extra_hits=()):
    candidate_api, _integrity_api = api
    text = source() if text is None else text
    if span == "auto":
        span = f"chars:0:{len(text)};unit:unicode_codepoint"
    request = make_grounded_request(
        CaseState(
            case_id="neutral-integrity",
            case_revision=revision,
            facts=(
                Fact(
                    name="streamlit_version", value="1.49.0", source_ref="user:now", turn_id="now"
                ),
            ),
        ),
        "Explain the mode parameter. This question is not an integrity verdict.",
        EvidenceBundle(
            snapshot_id="neutral-integrity-snapshot",
            hits=(
                EvidenceHit(
                    source_id="neutral-source",
                    chunk_id="neutral-chunk",
                    source_type="doc",
                    source_url="https://example.invalid/neutral",
                    source_commit="neutral-source-revision",
                    source_span=span,
                    applicable_versions=("1.49.0",),
                    excerpt=text,
                ),
                *extra_hits,
            ),
        ),
    )
    focus = candidate_api.build_parameter_focus_request(request)
    candidate = candidate_api.render_parameter_focus_candidate(
        focus,
        json.dumps(
            {"context_sha256": focus.context_sha256, "decision": "answer", "parameters": selected}
        ),
    )
    return focus, candidate


def inspect(api, **kwargs):
    focus, candidate = prepare(api, **kwargs)
    return focus, candidate, api[1].inspect_parameter_integrity(focus, candidate)


def selected(report):
    return next(row for row in report.observations if row.selected)


def test_matching_literals_are_observations_not_semantic_or_release_authority(api):
    focus, candidate, report = inspect(api)
    row = selected(report)
    assert row.comparison == "supported_literal_matches"
    assert row.warning is False
    assert report.selected_unit_has_integrity_warning is False
    assert report.semantic_support is None
    assert report.actual_runtime_defaults_verified is False
    assert report.human_review_required is True
    assert report.proposal_or_action_authorized is False
    assert report.context_sha256 == focus.context_sha256
    assert (
        report.candidate_sha256
        == hashlib.sha256(
            json.dumps(
                asdict(candidate),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode()
        ).hexdigest()
    )
    with pytest.raises(FrozenInstanceError):
        row.warning = True


@pytest.mark.parametrize(
    "signature,header,comparison,header_state,signature_state",
    [
        (
            'neutral.widget(value, *, mode="secondary")',
            "mode: str; default=None",
            "supported_literal_differs",
            "literal",
            "literal",
        ),
        (
            "neutral.widget(value, *, mode=False)",
            "mode: bool; default=is",
            "default_comparison_unavailable",
            "unsupported_literal",
            "literal",
        ),
        (
            "neutral.widget(value, *, mode=False)",
            "mode: bool; default=0",
            "supported_literal_differs",
            "literal",
            "literal",
        ),
        (
            'neutral.widget(value, *, mode="None")',
            "mode: str; default=None",
            "supported_literal_differs",
            "literal",
            "literal",
        ),
        (
            "neutral.widget(value, *, mode)",
            "mode: str; default=None",
            "header_default_for_required_parameter",
            "literal",
            "required",
        ),
        (
            "neutral.widget(value, *, mode=SENTINEL)",
            "mode: object; default=SENTINEL",
            "default_comparison_unavailable",
            "unresolved_expression",
            "unresolved_expression",
        ),
        (
            'neutral.widget(value, *, mode="safe")',
            "mode: str",
            "header_default_absent",
            "absent",
            "literal",
        ),
        (
            'neutral.widget(value, *, mode="safe")',
            'mode: str; default="safe"; default=None',
            "default_comparison_unavailable",
            "ambiguous_header_default",
            "literal",
        ),
        (
            'neutral.widget(value, *, mode="safe")',
            "mode: str; default=",
            "default_comparison_unavailable",
            "unsupported_literal",
            "literal",
        ),
    ],
)
def test_default_integrity_counterexamples(
    api, signature, header, comparison, header_state, signature_state
):
    _focus, _candidate, report = inspect(api, text=source(signature, ("value: object", header)))
    row = selected(report)
    assert (row.comparison, row.header_default_state, row.signature_default_state) == (
        comparison,
        header_state,
        signature_state,
    )
    assert row.warning is True and report.selected_unit_has_integrity_warning is True
    assert report.semantic_support is None


@pytest.mark.parametrize(
    "default,header",
    [
        ("-3", "-3"),
        ("+3", "3"),
        ("[1, False, None]", "[1, False, None]"),
        ('("a", -2)', '("a", -2)'),
        ('"é🚨"', '"é🚨"'),
    ],
)
def test_literal_grammar_accepts_only_data_and_preserves_typed_containers(api, default, header):
    _focus, _candidate, report = inspect(
        api,
        text=source(
            f"neutral.widget(value, *, mode={default})",
            ("value: object", f"mode: object; default={header}"),
        ),
    )
    assert selected(report).comparison == "supported_literal_matches"


@pytest.mark.parametrize("header", ["(1, 2)", "[1, True]", "[1, 2.0]"])
def test_container_kind_and_nested_types_are_not_silently_equal(api, header):
    _focus, _candidate, report = inspect(
        api,
        text=source(
            "neutral.widget(value, *, mode=[1, 2])",
            ("value: object", f"mode: object; default={header}"),
        ),
    )
    assert selected(report).comparison == "supported_literal_differs"


def test_required_parameter_without_header_default_is_not_a_missing_default(api):
    _focus, _candidate, report = inspect(api, selected=(0,))
    assert selected(report).comparison == "no_default_declared"
    assert selected(report).signature_default_state == "required"
    assert report.selected_unit_has_integrity_warning is False


def test_variadic_without_default_is_not_described_as_required(api):
    _focus, _candidate, report = inspect(
        api,
        text=source("neutral.widget(value, *mode)", ("value: object", "mode: tuple; default=None")),
    )
    row = selected(report)
    assert row.signature_default_state == "variadic_without_default"
    assert row.comparison == "header_default_for_variadic_parameter"


def test_selected_and_peer_parameter_warnings_are_independent(api):
    text = source(headers=("value: object; default=None", 'mode: str; default="safe"'))
    _focus, _candidate, report = inspect(api, text=text)
    assert report.selected_unit_has_integrity_warning is False
    assert report.peer_unit_has_integrity_warning is True
    assert report.observations[0].comparison == "header_default_for_required_parameter"


def test_body_prose_is_never_parsed_as_default_authority(api):
    text = source().replace(
        "The entire parameter definition",
        "The default is malicious and the signature is wrong. The entire parameter definition",
    )
    _focus, _candidate, report = inspect(api, text=text)
    assert selected(report).comparison == "supported_literal_matches"
    assert report.actual_runtime_defaults_verified is False


def test_untrusted_header_expression_is_not_executed(api, tmp_path):
    marker = tmp_path / "executed"
    expr = f'__import__("pathlib").Path({str(marker)!r}).touch()'
    _focus, _candidate, report = inspect(
        api, text=source(headers=("value: object", f"mode: str; default={expr}"))
    )
    assert selected(report).comparison == "default_comparison_unavailable"
    assert not marker.exists()


def test_unicode_and_crlf_offsets_retain_exact_local_substrings(api):
    text = source(
        'neutral.widget(value="é🚨", *, mode="🚨")',
        ('value: str; default="é🚨"', 'mode: str; default="🚨"'),
    ).replace("\n", "\r\n")
    focus, candidate, report = inspect(api, text=text)
    raw = focus.grounded.evidence.hits[0].excerpt
    row = selected(report)
    assert raw[slice(*row.header_default_span)] == row.header_default_text == '"🚨"'
    assert raw[slice(*row.signature_default_span)] == row.signature_default_text == '"🚨"'
    assert raw[slice(*row.header_span)] == 'mode: str; default="🚨"'
    assert raw[slice(*row.unit_span)] == candidate.quotations[0].text
    assert report.source_bindings[0].excerpt_length == len(raw)
    assert report.source_bindings[0].coordinate_frame == "excerpt_unicode_codepoint"


@pytest.mark.parametrize("offset", [0, 300])
def test_declared_span_length_does_not_authenticate_original_file_mapping(api, offset):
    text = source()
    _focus, _candidate, report = inspect(
        api, text=text, span=f"chars:{offset}:{offset + len(text)};unit:unicode_codepoint"
    )
    binding = report.source_bindings[0]
    assert (binding.declared_span_start, binding.declared_span_end) == (offset, offset + len(text))
    assert binding.declared_span_length_matches_excerpt is True
    assert binding.span_warning is False
    assert binding.original_file_offset_mapping_verified is False
    assert report.original_file_offset_mapping_verified is False


def test_declared_span_mismatch_is_not_a_default_integrity_failure_or_silent_repair(api):
    text = source()
    raw_span = f"chars:0:{len(text) + 2};unit:unicode_codepoint"
    focus, _candidate, report = inspect(api, text=text, span=raw_span)
    binding = report.source_bindings[0]
    assert binding.raw_source_span == raw_span == focus.grounded.evidence.hits[0].source_span
    assert binding.declared_span_length_matches_excerpt is False
    assert report.selected_source_has_span_warning is True
    assert report.selected_unit_has_integrity_warning is False


@pytest.mark.parametrize(
    "span",
    [
        None,
        "opaque provenance",
        "chars:2:1;unit:unicode_codepoint",
        "chars:01:10;unit:unicode_codepoint",
        "chars:0:9;unit:bytes",
    ],
)
def test_opaque_or_invalid_global_spans_stay_unknown(api, span):
    _focus, _candidate, report = inspect(api, span=span)
    binding = report.source_bindings[0]
    assert binding.raw_source_span == span
    assert binding.declared_span_length_matches_excerpt is None
    assert binding.original_file_offset_mapping_verified is False
    assert binding.span_warning is True


def test_noneligible_source_provenance_is_still_bound_and_distinct(api):
    extra = EvidenceHit(
        source_id="opaque",
        chunk_id="opaque",
        source_type="issue",
        source_url="https://example.invalid/issue",
        excerpt="A complete issue report.",
        source_span="opaque",
    )
    _focus, _candidate, report = inspect(api, extra_hits=(extra,))
    assert len(report.source_bindings) == 2
    assert report.source_bindings[1].eligibility == "not_an_exact_version_document"
    assert report.source_bindings[1].selected is False
    assert report.peer_source_has_span_warning is True
    assert all(row.source_index == 0 for row in report.observations)


@pytest.mark.parametrize(
    "field,value",
    [
        ("case_revision", True),
        ("case_revision", 2.0),
        ("semantic_support", False),
        ("qualified_text", "Improved but unauthenticated"),
        ("proposal_or_action_authorized", True),
    ],
)
def test_candidate_reconstruction_rejects_mutated_and_equal_wrong_types(api, field, value):
    focus, candidate = prepare(api)
    with pytest.raises(ValueError, match="^ParameterIntegrityUnavailable$"):
        api[1].inspect_parameter_integrity(focus, replace(candidate, **{field: value}))


@pytest.mark.parametrize(
    "field,value",
    [
        ("parameter_id", True),
        ("parameter_id", 1.0),
        ("source_index", False),
        ("text", "Changed source"),
        ("exact_metadata_match", 1),
    ],
)
def test_quotation_mutations_cannot_create_a_bound_review(api, field, value):
    focus, candidate = prepare(api)
    changed = replace(candidate.quotations[0], **{field: value})
    with pytest.raises(ValueError, match="^ParameterIntegrityUnavailable$"):
        api[1].inspect_parameter_integrity(focus, replace(candidate, quotations=(changed,)))


def test_stale_candidate_and_forged_catalog_are_rejected(api):
    focus, candidate = prepare(api)
    newer, _ = prepare(api, revision=3)
    with pytest.raises(ValueError, match="^ParameterIntegrityUnavailable$"):
        api[1].inspect_parameter_integrity(newer, candidate)
    changed = replace(focus.choices[1], parameter_id=1.0)
    with pytest.raises(ValueError, match="^ParameterIntegrityUnavailable$"):
        api[1].inspect_parameter_integrity(
            replace(focus, choices=(focus.choices[0], changed)), candidate
        )


def test_review_leaves_input_and_candidate_bytes_unchanged(api):
    focus, candidate = prepare(api)
    original_request = focus.grounded.model_dump_json()
    original_candidate = asdict(candidate)
    first = api[1].inspect_parameter_integrity(focus, candidate)
    second = api[1].inspect_parameter_integrity(focus, candidate)
    assert asdict(first) == asdict(second)
    assert focus.grounded.model_dump_json() == original_request
    assert asdict(candidate) == original_candidate
