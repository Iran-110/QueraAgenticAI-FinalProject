"""A separate, source-aware inspection surface; never an approval draft.

The old candidate and its model-inspection payload are unchanged. This view
does not decide relevance, completeness, usefulness or how a model should act.
It exposes exact quotations, inspectable citations and unresolved source checks.
"""

from dataclasses import asdict, dataclass, replace
from urllib.parse import quote

from experiments.core_parameter_focus_v1.candidate import (
    ParameterFocusCandidate,
    _quote,
    validate_parameter_focus_request,
)
from experiments.core_parameter_review_v1.integrity import (
    ParameterIntegrityReport,
    _digest,
    _same_typed,
    inspect_parameter_integrity,
)

from agent_app.reasoning.grounding import _display

_ERROR = "ParameterReviewUnavailable"
_PENDING = (
    "current_question_relevance",
    "necessary_caveats_outside_selected_unit",
    "user_usefulness",
)


@dataclass(frozen=True, slots=True)
class ParameterReview:
    schema_id: str
    context_sha256: str
    candidate_sha256: str
    original_candidate: ParameterFocusCandidate
    integrity: ParameterIntegrityReport
    concise_text: str
    maintainer_text: str
    source_review_required: bool
    pending_semantic_review: tuple[str, ...]
    review_binding_sha256: str
    reviewer_basis: str = "deterministic_source_observations_only"
    semantic_support: None = None
    human_usefulness: None = None
    human_review_required: bool = True
    model_selection_observed: bool = False
    original_file_offset_mapping_verified: bool = False
    approved_response_or_action: bool = False
    runtime_adoption: bool = False


def _selected_issues(integrity, source_index, parameter_id):
    """Fixed descriptions of lexical observations, not claims about defaults."""
    messages = []
    for observation in integrity.observations:
        if observation.parameter_id != parameter_id or not observation.warning:
            continue
        if observation.comparison == "supported_literal_differs":
            explanation = "Header and signature declare different literal defaults"
        else:
            explanation = "Header and signature defaults cannot be compared safely"
        header = (
            "<absent>"
            if observation.header_default_text is None
            else observation.header_default_text
        )
        signature = (
            "<absent>"
            if observation.signature_default_text is None
            else observation.signature_default_text
        )
        messages.append(
            explanation
            + "; header: "
            + _display(header)
            + "; signature: "
            + _display(signature)
            + ". These observations do not choose a corrected or actual runtime default."
        )
    binding = next(item for item in integrity.source_bindings if item.source_index == source_index)
    if binding.span_warning:
        if binding.declared_span_length_matches_excerpt is False:
            declared = binding.declared_span_end - binding.declared_span_start
            messages.append(
                "Supplied span length differs from excerpt length: "
                + str(declared)
                + " versus "
                + str(binding.excerpt_length)
                + " Unicode code points; original-file mapping is unverified."
            )
        else:
            messages.append(
                "Supplied source span is missing, opaque or invalid. Offsets below "
                "are excerpt-relative; original-file mapping is unverified."
            )
    peers = sum(
        item.source_index == source_index and not item.selected and item.warning
        for item in integrity.observations
    )
    if peers:
        messages.append(
            f"Other parameters in this same source have {peers} unresolved "
            "defaults. This does not disprove the selected quotation; details "
            "remain in the maintainer view."
        )
    return tuple(messages)


def build_parameter_review(focus_request, candidate):
    """Return a current-bound inspection view with explicit unresolved checks.

    No authored semantic findings are accepted as input, and no question,
    action, proposal or financial authorization is generated. Full original
    request, candidate, source text and old output bytes remain unmodified.
    """
    try:
        request = validate_parameter_focus_request(focus_request)
        integrity = inspect_parameter_integrity(request, candidate)
        sections, source_review_required = [], False
        for item in candidate.quotations:
            issues = _selected_issues(integrity, item.source_index, item.parameter_id)
            source_review_required |= bool(issues)
            # The detached GroundedRequest has already validated HTTP(S), no
            # credentials/whitespace and a valid port. Encoding also prevents
            # Markdown/HTML delimiters from changing the citation's structure.
            url = quote(item.source_url, safe=":/?&=.%#")
            section = (
                "### "
                + _display(item.api_name)
                + " · "
                + _display(item.parameter_name)
                + " · Streamlit "
                + _display(candidate.user_reported_version)
                + " (USER-reported)\n\n"
            )
            if issues:
                section += "Source checks requiring review:\n\n" + "\n".join(
                    "- " + message for message in issues
                )
                section += "\n\n"
            section += _quote(item.text)
            section += (
                "\n\n[Supplied documentation]("
                + url
                + f"). Quotation offsets [{item.start},{item.end}) are Unicode "
                "code points within the supplied excerpt.\n"
            )
            sections.append(section)
        concise = (
            "Experimental inspection; not an approved response.\n\n"
            + "\n".join(sections)
            + "\nRelevance, external caveats and usefulness remain unscored. "
            "Full sources and signatures: maintainer view."
        )
        observation_lines = []
        for item in integrity.observations:
            observation_lines.append(
                "- Source "
                + str(item.source_index)
                + "; parameter "
                + _display(item.parameter_name)
                + "; selected="
                + str(item.selected)
                + "; observation="
                + item.comparison
                + "; header span="
                + _display(str(item.header_default_span))
                + "; signature span="
                + _display(str(item.signature_default_span))
                + "."
            )
        maintainer = (
            concise
            + "\n\n### Supplied question context\n\n"
            + _quote(request.grounded.user_message)
            + "\n\n### Integrity observations across the supplied catalog\n\n"
            + "\n".join(observation_lines)
            + "\n\nThese checks compare supplied spellings only. They do not interpret "
            "body prose, authenticate a source or map excerpts to the original file. "
            "A source defect must not be turned into an unrelated question to the user."
            + "\n\n### Original complete candidate review\n\n"
            + candidate.review_text
        )
        review = ParameterReview(
            schema_id="parameter-inspection-review-v1",
            context_sha256=request.context_sha256,
            candidate_sha256=integrity.candidate_sha256,
            original_candidate=candidate,
            integrity=integrity,
            concise_text=concise,
            maintainer_text=maintainer,
            source_review_required=source_review_required,
            pending_semantic_review=_PENDING,
            review_binding_sha256="",
        )
        material = asdict(review)
        del material["review_binding_sha256"]
        return replace(review, review_binding_sha256=_digest(material))
    except Exception:
        raise ValueError(_ERROR) from None


def validate_parameter_review(focus_request, candidate, review):
    """Regenerate and strictly compare; an edited warning/text is a new review."""
    try:
        if type(review) is not ParameterReview:
            raise ValueError
        rebuilt = build_parameter_review(focus_request, candidate)
        if not _same_typed(rebuilt, review):
            raise ValueError
        return rebuilt
    except Exception:
        raise ValueError(_ERROR) from None
