"""Caller-owned question vocabulary, independent of fixtures and model outputs."""

import json
from collections.abc import Iterable
from pathlib import Path

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


def load_user_gap_vocabulary(config_path: str) -> tuple[GroundedGap, ...]:
    """Read bounded caller configuration once; never infer questions from sources.

    This validates shape, not the relevance or neutrality of a question. The
    operator must review the vocabulary; current case unknowns still select it.
    """

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError
            result[key] = value
        return result

    def reject_constant(_value):
        raise ValueError

    try:
        if type(config_path) is not str or not config_path.strip():
            raise ValueError
        path = Path(config_path)
        if not path.is_file():
            raise ValueError
        with path.open("rb") as source:
            raw = source.read(32769)
        if len(raw) > 32768:
            raise ValueError
        payload = json.loads(
            raw.decode("utf-8"), object_pairs_hook=unique_object, parse_constant=reject_constant
        )
        if (
            type(payload) is not dict
            or set(payload) != {"schema_version", "user_gaps"}
            or type(payload["schema_version"]) is not int
            or payload["schema_version"] != 1
            or type(payload["user_gaps"]) is not list
        ):
            raise ValueError
        return validate_user_gaps(payload["user_gaps"])
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
