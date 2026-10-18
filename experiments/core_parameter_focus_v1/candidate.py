"""Experimental exact parameter quotations, never a replacement approval draft.

The full original grounded request remains available for review. Flat selections
refer only to this current catalog; integrity and exact version metadata do not
prove topical relevance, semantic completeness, applicability or a successful fix.
No factory, gateway, tracker or existing presentation composition imports this.
"""

import hashlib
import json
from dataclasses import asdict, dataclass, fields

from experiments.core_parameter_focus_v1.parameters import parse_parameter_record

from agent_app.contracts import GroundedRequest
from agent_app.reasoning.grounding import (
    _display,
    _prior_conflict,
    _user_version,
    source_content_sha256,
    source_scope,
    validate_grounded_request,
)

_ERROR = "ParameterFocusUnavailable"
_SCHEMA = "parameter-focus-candidate-v1"
_DISPLAY_NORMALIZATION = "crlf_to_lf_only"
_MAX_UNITS = 512
_MAX_SELECTION = 3


def _digest(value):
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    ).hexdigest()


def _text_digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ParameterChoice:
    parameter_id: int
    source_index: int
    parameter_name: str
    api_name: str
    signature: str
    start: int
    end: int
    source_content_sha256: str
    source_text_sha256: str
    passage_sha256: str


@dataclass(frozen=True, slots=True)
class SourceReview:
    source_index: int
    chunk_id: str
    eligibility: str
    source_content_sha256: str
    prefix_span: tuple[int, int] | None
    suffix_span: tuple[int, int] | None


@dataclass(frozen=True, slots=True)
class ParameterFocusRequest:
    grounded: GroundedRequest
    choices: tuple[ParameterChoice, ...]
    source_inventory: tuple[SourceReview, ...]
    context_sha256: str


@dataclass(frozen=True, slots=True)
class FocusQuotation:
    parameter_id: int
    parameter_name: str
    api_name: str
    signature: str
    source_index: int
    source_id: str
    chunk_id: str
    source_url: str
    source_span: str | None
    start: int
    end: int
    source_content_sha256: str
    source_text_sha256: str
    passage_sha256: str
    text: str
    exact_metadata_match: bool = True
    semantic_support: None = None
    human_review_required: bool = True


@dataclass(frozen=True, slots=True)
class ParameterFocusCandidate:
    schema_id: str
    context_sha256: str
    case_id: str
    case_revision: int
    user_reported_version: str
    decision: str
    quotations: tuple[FocusQuotation, ...]
    qualified_text: str
    review_text: str
    display_normalization: str = _DISPLAY_NORMALIZATION
    semantic_support: None = None
    human_review_required: bool = True
    diagnosis_or_fix_verified: bool = False
    proposal_or_action_authorized: bool = False


def build_parameter_focus_request(grounded):
    """Bind complete current input and a narrow exact-version parameter catalog.

    Unparseable, non-document and nonexact-version records stay in the unchanged
    grounded request and review inventory. They never become selectable units.
    A source gap is retained as a caller declaration, not resolved by this helper.
    """
    try:
        grounded = validate_grounded_request(grounded)
        if (
            _user_version(grounded.case) is None
            or grounded.conflict_groups
            or _prior_conflict(grounded)
        ):
            raise ValueError
        choices, inventory = [], []
        for source_index, hit in enumerate(grounded.evidence.hits):
            source_digest = source_content_sha256(hit)
            eligibility = "not_an_exact_version_document"
            prefix_span = suffix_span = None
            if (
                hit.source_type == "doc"
                and source_scope(grounded.case, hit) == "exact_metadata_match"
            ):
                try:
                    record = parse_parameter_record(hit.excerpt)
                except ValueError:
                    eligibility = "parameter_structure_unavailable"
                else:
                    eligibility = "exact_version_parameter_record"
                    prefix_span, suffix_span = record.prefix_span, record.suffix_span
                    for unit in record.parameters:
                        choices.append(
                            ParameterChoice(
                                parameter_id=len(choices),
                                source_index=source_index,
                                parameter_name=unit.name,
                                api_name=record.api_name,
                                signature=record.signature,
                                start=unit.start,
                                end=unit.end,
                                source_content_sha256=source_digest,
                                source_text_sha256=record.source_sha256,
                                passage_sha256=_text_digest(hit.excerpt[unit.start : unit.end]),
                            )
                        )
            inventory.append(
                SourceReview(
                    source_index, hit.chunk_id, eligibility, source_digest, prefix_span, suffix_span
                )
            )
        if not 1 <= len(choices) <= _MAX_UNITS:
            raise ValueError
        material = {
            "schema_id": _SCHEMA,
            "display_normalization": _DISPLAY_NORMALIZATION,
            "grounded": grounded.model_dump(mode="json"),
            "choices": [asdict(item) for item in choices],
            "source_inventory": [asdict(item) for item in inventory],
        }
        return ParameterFocusRequest(grounded, tuple(choices), tuple(inventory), _digest(material))
    except Exception:
        raise ValueError(_ERROR) from None


def _same_typed_catalog(expected, actual):
    """Normal equality accepts True/1 and 1.0/1; a catalog never should.

    The nested GroundedRequest has already passed detached contract validation
    during reconstruction. The additional experimental dataclasses and tuples
    need their own exact-type comparison before any rebuilt value is returned.
    """
    if type(expected) is not type(actual):
        return False
    if type(expected) in {ParameterFocusRequest, ParameterChoice, SourceReview}:
        return all(
            _same_typed_catalog(getattr(expected, field.name), getattr(actual, field.name))
            for field in fields(expected)
        )
    if type(expected) is tuple:
        return len(expected) == len(actual) and all(
            _same_typed_catalog(left, right) for left, right in zip(expected, actual, strict=True)
        )
    return expected == actual


def validate_parameter_focus_request(request):
    """Reject stale/mutated catalogs instead of rebuilding a different request."""
    try:
        if type(request) is not ParameterFocusRequest:
            raise ValueError
        rebuilt = build_parameter_focus_request(request.grounded)
        if not _same_typed_catalog(rebuilt, request):
            raise ValueError
        return rebuilt
    except Exception:
        raise ValueError(_ERROR) from None


def parameter_focus_payload(request):
    """Return a detached inspection/model payload with all original source text.

    This is an experimental payload only, with no model call or financial scope.
    No quality labels, oracle, suggested choice or source-specific rule is added.
    """
    request = validate_parameter_focus_request(request)
    return {
        "schema_id": _SCHEMA,
        "display_normalization": _DISPLAY_NORMALIZATION,
        "context_sha256": request.context_sha256,
        "grounded_request": request.grounded.model_dump(mode="json"),
        "parameters": [asdict(item) for item in request.choices],
        "source_inventory": [asdict(item) for item in request.source_inventory],
        "response_schema": {
            "type": "object",
            "properties": {
                "context_sha256": {"type": "string", "const": request.context_sha256},
                "decision": {"type": "string", "const": "answer"},
                "parameters": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": _MAX_SELECTION,
                    "uniqueItems": True,
                    "items": {"type": "integer", "enum": list(range(len(request.choices)))},
                },
            },
            "required": ["context_sha256", "decision", "parameters"],
            "additionalProperties": False,
        },
        "limitations": {
            "semantic_support": None,
            "human_review_required": True,
            "complete_parameter_is_not_complete_source_or_caveat_coverage": True,
            "not_an_approved_proposal_or_runtime_configuration": True,
        },
    }


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _invalid_constant(_value):
    raise ValueError


def _selection(raw, request):
    if type(raw) is not str or len(raw.encode("utf-8")) > 16_384:
        raise ValueError
    plan = json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
    json.dumps(plan, ensure_ascii=False, allow_nan=False).encode("utf-8")
    if (
        type(plan) is not dict
        or set(plan) != {"context_sha256", "decision", "parameters"}
        or type(plan["context_sha256"]) is not str
        or plan["context_sha256"] != request.context_sha256
        or type(plan["decision"]) is not str
        or plan["decision"] != "answer"
        or type(plan["parameters"]) is not list
        or not 1 <= len(plan["parameters"]) <= _MAX_SELECTION
        or any(
            type(index) is not int or not 0 <= index < len(request.choices)
            for index in plan["parameters"]
        )
        or len(set(plan["parameters"])) != len(plan["parameters"])
    ):
        raise ValueError
    return tuple(plan["parameters"])


def _quote(text):
    # Display only: Windows line ends should not turn into visible control
    # markers. Exact raw source/parameter bytes, offsets and digests remain in
    # the request and FocusQuotation; bare CR and literal escapes are not erased.
    return "\n".join("> " + line for line in _display(text.replace("\r\n", "\n")).split("\n"))


def render_parameter_focus_candidate(request, raw):
    """Render qualified exact selected units plus a lossless source review view.

    No claim of caveat completeness is made. Full selected records, including
    their prefix/suffix and other parameters, remain in review_text with only
    display CRLF-to-LF normalization; request/quotation text and source hashes
    retain their exact original form. The existing API and approved drafts do
    not consume this result.
    """
    try:
        request = validate_parameter_focus_request(request)
        selected = _selection(raw, request)
        quotations = []
        for parameter_id in selected:
            unit = request.choices[parameter_id]
            hit = request.grounded.evidence.hits[unit.source_index]
            quotations.append(
                FocusQuotation(
                    parameter_id=unit.parameter_id,
                    parameter_name=unit.parameter_name,
                    api_name=unit.api_name,
                    signature=unit.signature,
                    source_index=unit.source_index,
                    source_id=hit.source_id,
                    chunk_id=hit.chunk_id,
                    source_url=hit.source_url,
                    source_span=hit.source_span,
                    start=unit.start,
                    end=unit.end,
                    source_content_sha256=unit.source_content_sha256,
                    source_text_sha256=unit.source_text_sha256,
                    passage_sha256=unit.passage_sha256,
                    text=hit.excerpt[unit.start : unit.end],
                )
            )
        version = _user_version(request.grounded.case)
        qualification = (
            "Selected exact parameter quotations from supplied documentation. "
            "The source version metadata matches the current USER-reported Streamlit "
            "version "
            + _display(version)
            + "; this does not verify relevance, applicability, a diagnosis or a fix. "
            "Other parameters and source-wide caveats may matter; complete original "
            "records remain in the review view. Human review is required."
        )
        focused = "\n\n".join(
            "API: "
            + _display(item.api_name)
            + "; parameter: "
            + _display(item.parameter_name)
            + "; chunk: "
            + _display(item.chunk_id)
            + f"; excerpt characters [{item.start},{item.end}).\n"
            + "Signature supplied by the source (other parameters are not selected):\n"
            + _quote(item.signature)
            + "\n\n"
            + _quote(item.text)
            for item in quotations
        )
        qualified_text = qualification + "\n\n" + focused
        # This is still not an AnalysisResult. Keep its candidate answer within
        # the current draft character ceiling without shortening any quotation.
        if len(qualified_text) > 20_000:
            raise ValueError
        selected_sources = sorted({item.source_index for item in quotations})
        review = (
            qualification
            + "\n\nComplete selected source records:\n\n"
            + "\n\n".join(
                "Chunk: "
                + _display(request.grounded.evidence.hits[index].chunk_id)
                + "; URL as supplied: "
                + _display(request.grounded.evidence.hits[index].source_url)
                + "\n"
                + _quote(request.grounded.evidence.hits[index].excerpt)
                for index in selected_sources
            )
        )
        return ParameterFocusCandidate(
            schema_id=_SCHEMA,
            context_sha256=request.context_sha256,
            case_id=request.grounded.case.case_id,
            case_revision=request.grounded.case.case_revision,
            user_reported_version=version,
            decision="answer",
            quotations=tuple(quotations),
            qualified_text=qualified_text,
            review_text=review,
        )
    except Exception:
        raise ValueError(_ERROR) from None
