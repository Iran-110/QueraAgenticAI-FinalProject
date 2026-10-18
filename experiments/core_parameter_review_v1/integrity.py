"""Pure, additive observations about supplied parameter records.

This compares a deliberately small literal grammar in a documentation header
with the supplied signature. It never executes Python, interprets body prose,
repairs a source, establishes actual runtime defaults or authorizes a response.
Every span is local to the exact supplied excerpt, in Unicode code points.
"""

import ast
import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass, fields, is_dataclass

from experiments.core_parameter_focus_v1.candidate import (
    FocusQuotation,
    ParameterFocusCandidate,
    render_parameter_focus_candidate,
    validate_parameter_focus_request,
)
from experiments.core_parameter_focus_v1.parameters import parse_parameter_record

_ERROR = "ParameterIntegrityUnavailable"
_DEFAULT = re.compile(r";[ \t]*default[ \t]*=")
_SPAN = re.compile(r"chars:(0|[1-9][0-9]{0,19}):(0|[1-9][0-9]{0,19});unit:unicode_codepoint")
_DEF_PREFIX = "def _parameter_focus"


@dataclass(frozen=True, slots=True)
class SourceIntegrityBinding:
    source_index: int
    source_content_sha256: str
    source_text_sha256: str
    eligibility: str
    selected: bool
    raw_source_span: str | None
    coordinate_frame: str
    excerpt_length: int
    declared_span_start: int | None
    declared_span_end: int | None
    declared_span_length_matches_excerpt: bool | None
    source_span_status: str
    span_warning: bool
    original_file_offset_mapping_verified: bool = False


@dataclass(frozen=True, slots=True)
class ParameterIntegrityObservation:
    source_index: int
    parameter_id: int
    parameter_name: str
    selected: bool
    unit_span: tuple[int, int]
    header_span: tuple[int, int]
    header_default_span: tuple[int, int] | None
    header_default_text: str | None
    header_default_state: str
    signature_default_span: tuple[int, int] | None
    signature_default_text: str | None
    signature_default_state: str
    comparison: str
    warning: bool
    semantic_support: None = None
    human_review_required: bool = True


@dataclass(frozen=True, slots=True)
class ParameterIntegrityReport:
    schema_id: str
    context_sha256: str
    candidate_sha256: str
    source_bindings: tuple[SourceIntegrityBinding, ...]
    observations: tuple[ParameterIntegrityObservation, ...]
    selected_unit_has_integrity_warning: bool
    peer_unit_has_integrity_warning: bool
    selected_source_has_span_warning: bool
    peer_source_has_span_warning: bool
    semantic_support: None = None
    human_review_required: bool = True
    actual_runtime_defaults_verified: bool = False
    original_file_offset_mapping_verified: bool = False
    proposal_or_action_authorized: bool = False


def _digest(value):
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    ).hexdigest()


def _same_typed(expected, actual):
    if type(expected) is not type(actual):
        return False
    if is_dataclass(expected):
        return all(
            _same_typed(getattr(expected, field.name), getattr(actual, field.name))
            for field in fields(expected)
        )
    if type(expected) is tuple:
        return len(expected) == len(actual) and all(
            _same_typed(left, right) for left, right in zip(expected, actual, strict=True)
        )
    return expected == actual


def _literal(node):
    """Return a typed literal description, never evaluate names or calls."""
    if isinstance(node, ast.Constant):
        kind = type(node.value)
        if kind in {str, int, bool, type(None)} or (kind is float and math.isfinite(node.value)):
            return (kind.__name__, node.value)
    elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.UAdd | ast.USub):
        if isinstance(node.operand, ast.Constant) and type(node.operand.value) in {int, float}:
            value = node.operand.value * (-1 if isinstance(node.op, ast.USub) else 1)
            if type(value) is int or math.isfinite(value):
                return (type(value).__name__, value)
    elif isinstance(node, ast.List | ast.Tuple):
        values = tuple(_literal(child) for child in node.elts)
        if all(value is not None for value in values):
            return ("list" if isinstance(node, ast.List) else "tuple", values)
    return None


def _header_default(text, start):
    header = text.splitlines(keepends=True)[0].removesuffix("\n").removesuffix("\r")
    matches = list(_DEFAULT.finditer(header))
    if not matches:
        return ("absent", None, None, None)
    if len(matches) != 1:
        return ("ambiguous_header_default", None, None, None)
    value_start, value_end = matches[0].end(), len(header.rstrip(" \t"))
    while value_start < value_end and header[value_start] in " \t":
        value_start += 1
    token = header[value_start:value_end]
    span = (start + value_start, start + value_end)
    try:
        node = ast.parse(token, mode="eval").body
    except (SyntaxError, ValueError, TypeError, RecursionError):
        return ("unsupported_literal", span, token, None)
    literal = _literal(node)
    if literal is not None:
        return ("literal", span, token, literal)
    return ("unresolved_expression", span, token, None)


def _signature_defaults(record):
    args = record.signature[len(record.api_name) :]
    function = ast.parse(_DEF_PREFIX + args + ":\n    pass\n").body[0]
    arguments = function.args
    named = [*arguments.posonlyargs, *arguments.args]
    default_nodes = [None] * (len(named) - len(arguments.defaults)) + arguments.defaults
    result = {}
    for argument, node in zip(named, default_nodes, strict=True):
        result[argument.arg] = ("required" if node is None else "default", node)
    if arguments.vararg is not None:
        result[arguments.vararg.arg] = ("variadic_without_default", None)
    for argument, node in zip(arguments.kwonlyargs, arguments.kw_defaults, strict=True):
        result[argument.arg] = ("required" if node is None else "default", node)
    if arguments.kwarg is not None:
        result[arguments.kwarg.arg] = ("variadic_without_default", None)
    observed = {}
    for name, (kind, node) in result.items():
        if node is None:
            observed[name] = (kind, None, None, None)
            continue
        # AST columns are UTF-8 byte offsets, whereas the report uses Unicode
        # code points. The single-line signature has already passed v1 parsing.
        offset = len(_DEF_PREFIX.encode("utf-8"))
        start = len(record.api_name) + len(
            args.encode("utf-8")[: node.col_offset - offset].decode("utf-8")
        )
        end = len(record.api_name) + len(
            args.encode("utf-8")[: node.end_col_offset - offset].decode("utf-8")
        )
        token = record.signature[start:end]
        literal = _literal(node)
        observed[name] = (
            "literal" if literal is not None else "unresolved_expression",
            (start, end),
            token,
            literal,
        )
    return observed


def _comparison(header, signature):
    h_state, _h_span, _h_text, h_literal = header
    s_state, _s_span, _s_text, s_literal = signature
    if s_state in {"required", "variadic_without_default"}:
        if h_state == "absent":
            return "no_default_declared", False
        return (
            "header_default_for_required_parameter"
            if s_state == "required"
            else "header_default_for_variadic_parameter",
            True,
        )
    if h_state == "absent":
        return "header_default_absent", True
    if h_state != "literal" or s_state != "literal":
        return "default_comparison_unavailable", True
    # Literal tags preserve bool/int, None/str and list/tuple distinctions.
    if h_literal == s_literal:
        return "supported_literal_matches", False
    return "supported_literal_differs", True


def _source_binding(index, hit, inventory, selected):
    start = end = matches = None
    status = "opaque_or_missing_span_unverified"
    if type(hit.source_span) is str and (match := _SPAN.fullmatch(hit.source_span)):
        raw_start, raw_end = int(match[1]), int(match[2])
        if raw_start <= raw_end:
            start, end = raw_start, raw_end
            matches = end - start == len(hit.excerpt)
            status = "declared_length_matches_excerpt" if matches else "declared_length_differs"
        else:
            status = "declared_span_order_invalid"
    return SourceIntegrityBinding(
        source_index=index,
        source_content_sha256=inventory.source_content_sha256,
        source_text_sha256=hashlib.sha256(hit.excerpt.encode("utf-8")).hexdigest(),
        eligibility=inventory.eligibility,
        selected=selected,
        raw_source_span=hit.source_span,
        coordinate_frame="excerpt_unicode_codepoint",
        excerpt_length=len(hit.excerpt),
        declared_span_start=start,
        declared_span_end=end,
        declared_span_length_matches_excerpt=matches,
        source_span_status=status,
        span_warning=matches is not True,
    )


def inspect_parameter_integrity(focus_request, candidate):
    """Bind and observe the supplied candidate; no semantic or release score.

    Defaults are inspected in every eligible catalog unit, with selected-unit
    and peer warnings kept separate. All source metadata also stays inspectable;
    a declared span's length can be compared, but its original-file mapping is
    never authenticated here. Unsupported/default sentinel expressions remain
    unknown, including equal-looking sentinel names.
    """
    try:
        request = validate_parameter_focus_request(focus_request)
        if (
            type(candidate) is not ParameterFocusCandidate
            or type(candidate.quotations) is not tuple
            or any(
                type(item) is not FocusQuotation or type(item.parameter_id) is not int
                for item in candidate.quotations
            )
        ):
            raise ValueError
        selected_ids = tuple(item.parameter_id for item in candidate.quotations)
        regenerated = render_parameter_focus_candidate(
            request,
            json.dumps(
                {
                    "context_sha256": request.context_sha256,
                    "decision": "answer",
                    "parameters": selected_ids,
                }
            ),
        )
        if not _same_typed(regenerated, candidate):
            raise ValueError
        selected_sources = {item.source_index for item in regenerated.quotations}
        bindings = tuple(
            _source_binding(index, hit, inventory, index in selected_sources)
            for index, (hit, inventory) in enumerate(
                zip(request.grounded.evidence.hits, request.source_inventory, strict=True)
            )
        )
        observations, records = [], {}
        for choice in request.choices:
            if choice.source_index not in records:
                record = parse_parameter_record(
                    request.grounded.evidence.hits[choice.source_index].excerpt
                )
                records[choice.source_index] = (record, _signature_defaults(record))
            record, defaults = records[choice.source_index]
            text = record.source_text[choice.start : choice.end]
            header = _header_default(text, choice.start)
            signature = defaults[choice.parameter_name]
            comparison, warning = _comparison(header, signature)
            header_text = text.splitlines(keepends=True)[0].removesuffix("\n").removesuffix("\r")
            observations.append(
                ParameterIntegrityObservation(
                    source_index=choice.source_index,
                    parameter_id=choice.parameter_id,
                    parameter_name=choice.parameter_name,
                    selected=choice.parameter_id in selected_ids,
                    unit_span=(choice.start, choice.end),
                    header_span=(choice.start, choice.start + len(header_text)),
                    header_default_span=header[1],
                    header_default_text=header[2],
                    header_default_state=header[0],
                    signature_default_span=signature[1],
                    signature_default_text=signature[2],
                    signature_default_state=signature[0],
                    comparison=comparison,
                    warning=warning,
                )
            )
        return ParameterIntegrityReport(
            schema_id="parameter-integrity-review-v1",
            context_sha256=request.context_sha256,
            candidate_sha256=_digest(asdict(regenerated)),
            source_bindings=bindings,
            observations=tuple(observations),
            selected_unit_has_integrity_warning=any(
                row.selected and row.warning for row in observations
            ),
            peer_unit_has_integrity_warning=any(
                not row.selected and row.warning for row in observations
            ),
            selected_source_has_span_warning=any(
                row.selected and row.span_warning for row in bindings
            ),
            peer_source_has_span_warning=any(
                not row.selected and row.span_warning for row in bindings
            ),
        )
    except Exception:
        raise ValueError(_ERROR) from None
