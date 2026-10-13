"""Caller-owned question vocabulary, independent of fixtures and model outputs."""

from collections.abc import Iterable

from agent_app.contracts import CaseState, EvidenceBundle, GroundedGap, GroundedRequest
from agent_app.orchestration.intake import STREAMLIT_VERSION_QUESTION
from agent_app.reasoning.grounding import (
    UNRESOLVED_SOURCE_CONFLICT,
    make_grounded_request,
    source_scope,
)


def runtime_catalog(case: CaseState, message: str, evidence: EvidenceBundle) -> GroundedRequest:
    """Register only a user-supplied version gap and a documentary coverage gap.

    The latest authoritative facts and actual bundle are the complete input.
    No fixture expectations, inferred cause, gold labels or future turns are used.
    This small catalog does not claim to discover every necessary question.
    """
    known = {
        fact.name.casefold()
        for fact in case.facts
        if fact.status == "active" and fact.provenance_kind == "user" and fact.value
    }
    gaps = []
    if "streamlit_version" not in known:
        gaps.append(
            GroundedGap(
                name=STREAMLIT_VERSION_QUESTION.name,
                kind="user",
                description="The affected application's Streamlit version is unknown.",
                necessity="The user can report the installed release to check source applicability.",
                question=STREAMLIT_VERSION_QUESTION.question,
            )
        )
    if not any(source_scope(case, hit) == "exact_metadata_match" for hit in evidence.hits):
        gaps.append(
            GroundedGap(
                name="exact_version_documentation",
                kind="source",
                description="No supplied record has exact metadata for the confirmed version.",
                necessity="Further documentation retrieval or maintainer review may be needed.",
            )
        )
    return make_grounded_request(case, message, evidence, gaps=tuple(gaps))


def validate_user_gaps(definitions: Iterable[GroundedGap]) -> tuple[GroundedGap, ...]:
    """Strict vocabulary only; source gaps and existing questions cannot be overridden."""
    try:
        gaps = tuple(
            GroundedGap.model_validate(
                item.model_dump(warnings=False) if isinstance(item, GroundedGap) else item
            )
            for item in definitions
        )
        names = {gap.name.casefold() for gap in gaps}
        if (
            len(gaps) > 6
            or len(names) != len(gaps)
            or names
            & {
                "streamlit_version",
                "exact_version_documentation",
                UNRESOLVED_SOURCE_CONFLICT.name,
            }
            or any(gap.kind != "user" for gap in gaps)
        ):
            raise ValueError
        return gaps
    except Exception:
        raise ValueError("UserGapVocabularyInvalid") from None


def caller_catalog(
    case: CaseState,
    message: str,
    evidence: EvidenceBundle,
    *,
    definitions: tuple[GroundedGap, ...] = (),
) -> GroundedRequest:
    """Match vocabulary to current explicit unknowns, never infer gaps from prose."""
    registered = runtime_catalog(case, message, evidence)
    known = {
        fact.name.casefold()
        for fact in case.facts
        if fact.status == "active" and fact.provenance_kind == "user" and fact.value
    }
    unknowns = {name.casefold() for name in case.unknowns}
    selected = tuple(
        gap
        for gap in validate_user_gaps(definitions)
        if gap.name.casefold() in unknowns and gap.name.casefold() not in known
    )
    return make_grounded_request(
        case,
        message,
        evidence,
        gaps=registered.gaps + selected,
        conflict_groups=registered.conflict_groups,
    )
