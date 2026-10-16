"""Bound supplied-passage observations; no gold selection or semantic judgment.

Requirements and handoffs are caller-supplied declarations. Hash equality does
not authenticate their origin, verify a physical index/build, or establish that
a provider consumed the supplied bundle. Missing means not observed in this
bundle; all requirements observed does not establish answer sufficiency.
"""

import hashlib
import json
import re
from typing import Annotated

from pydantic import ConfigDict, Field, StringConstraints, field_validator

from agent_app.contracts import (
    Contract,
    EvidenceHit,
    Identifier,
    ProposalHandoff,
    ReviewExactText,
)
from agent_app.orchestration.handoff import validate_handoff
from agent_app.orchestration.validation import detached_contract

ERROR = "EvidenceObservationRejected"


class PassageAnchor(Contract):
    """One exact passage/revision/URL alternative; None is an exact revision."""

    model_config = ConfigDict(
        extra="forbid", frozen=True, validate_default=True, hide_input_in_errors=True
    )
    source_id: Identifier
    source_commit: Identifier | None  # Required, including an explicit None.
    source_url: Annotated[str, StringConstraints(strict=True, max_length=2_000)]
    passage: ReviewExactText  # Preserve exact whitespace and Unicode.

    @field_validator("source_url")
    @classmethod
    def valid_url(cls, value):
        return EvidenceHit.source_url_is_web_link(value)

    @field_validator("passage")
    @classmethod
    def nonblank_passage(cls, value):
        if not value.strip():
            raise ValueError(ERROR)
        return value


class PassageRequirement(Contract):
    """All requirements are required; any one alternative satisfies this group."""

    model_config = ConfigDict(
        extra="forbid", frozen=True, validate_default=True, hide_input_in_errors=True
    )
    requirement_id: Identifier
    alternatives: tuple[PassageAnchor, ...] = Field(min_length=1, max_length=10)


class EvidenceObservationRejected(ValueError):
    def __init__(self):
        super().__init__(ERROR)


def _need(value):
    if not value:
        raise EvidenceObservationRejected()


def _sha(kind, value):
    material = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return hashlib.sha256(
        ("evidence-observation-v1:" + kind + ":" + material).encode("utf-8")
    ).hexdigest()


def _hash(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _requirements(requirements):
    _need(type(requirements) is tuple and 1 <= len(requirements) <= 20)
    validated = tuple(detached_contract(PassageRequirement, item) for item in requirements)
    _need(sum(len(item.alternatives) for item in validated) <= 100)
    ids, anchors = set(), set()
    for requirement in validated:
        key = requirement.requirement_id.casefold()
        _need(key not in ids)
        ids.add(key)
        for anchor in requirement.alternatives:
            digest = _sha("anchor", anchor.model_dump(mode="json"))
            _need(digest not in anchors)
            anchors.add(digest)
    return validated, _sha("requirements", [item.model_dump(mode="json") for item in validated])


def passage_requirements_sha256(requirements: tuple[PassageRequirement, ...]) -> str:
    """Hash the complete validated ordered AND/OR declaration without I/O."""
    try:
        return _requirements(requirements)[1]
    except Exception:
        raise EvidenceObservationRejected() from None


def observe_required_passages(
    handoff: ProposalHandoff,
    requirements: tuple[PassageRequirement, ...],
    *,
    expected_handoff_sha256: str,
    requirements_sha256: str,
) -> dict:
    """Observe exact passages in one content-validated supplied handoff bundle.

    Each anchor must fit wholly within one hit. All matching hits are retained;
    repeated text within a hit records its first exact Unicode-codepoint span.
    Citation is only analysis.evidence_links membership, not passage support.
    Empty evidence is observable; absent/invalid handoffs or criteria reject.
    The caller must separately bind the handoff to an actual captured attempt
    and establish preregistration; neither a hash nor this helper attests either.
    """
    try:
        _need(_hash(expected_handoff_sha256) and _hash(requirements_sha256))
        validated, digest = _requirements(requirements)
        _need(digest == requirements_sha256)
        handoff = validate_handoff(handoff)
        _need(handoff.handoff_sha256 == expected_handoff_sha256)
        inventory = {item.chunk_id: item for item in handoff.source_inventory}
        cited = {link.chunk_id for link in handoff.analysis.evidence_links}
        groups = []
        for requirement in validated:
            alternatives = []
            for anchor in requirement.alternatives:
                matches = []
                for hit in handoff.evidence.hits:
                    if (hit.source_id, hit.source_commit, hit.source_url) != (
                        anchor.source_id,
                        anchor.source_commit,
                        anchor.source_url,
                    ):
                        continue
                    start = hit.excerpt.find(anchor.passage)
                    if start >= 0:
                        item = inventory[hit.chunk_id]
                        matches.append(
                            {
                                "chunk_id": hit.chunk_id,
                                "content_sha256": item.content_sha256,
                                "start": start,
                                "end": start + len(anchor.passage),
                                "version_scope": item.version_scope,
                                "cited_by_analysis": hit.chunk_id in cited,
                            }
                        )
                alternatives.append(
                    {
                        "anchor_sha256": _sha("anchor", anchor.model_dump(mode="json")),
                        "observed": bool(matches),
                        "matches": matches,
                    }
                )
            groups.append(
                {
                    "requirement_id": requirement.requirement_id,
                    "observed": any(item["observed"] for item in alternatives),
                    "alternatives": alternatives,
                }
            )
        return {
            "schema_version": 1,
            "scope": "exact_passage_observation_in_supplied_handoff_bundle_only",
            "requirements_sha256": digest,
            "handoff_sha256": handoff.handoff_sha256,
            "case_id": handoff.case.case_id,
            "case_revision": handoff.case.case_revision,
            "proposal_id": handoff.proposal_id,
            "run_id": handoff.reasoning_context.run_id,
            "attempt_index": handoff.reasoning_context.attempt_index,
            "grounded_context_sha256": (
                handoff.grounded_request.context_sha256
                if handoff.grounded_request is not None
                else None
            ),
            "snapshot_id": handoff.evidence.snapshot_id,
            "requirements": groups,
            "all_requirements_observed": all(group["observed"] for group in groups),
            "observed_requirement_count": sum(group["observed"] for group in groups),
            "requirement_count": len(groups),
            "occurrence_scope": "first_exact_unicode_codepoint_occurrence_per_matching_hit",
            "citation_scope": "analysis_evidence_links_chunk_membership_only",
            "missing_scope": "not_observed_in_this_supplied_bundle_only",
            "claim_support": "unassessed",
            "whole_answer_sufficiency": "unassessed",
            "decision_judgment": "unassessed",
            "actual_model_consumption_verified": False,
            "physical_build_verified": False,
            "source_authenticity_verified": False,
            "preregistration_verified": False,
            "quality_claim": False,
        }
    except Exception:
        raise EvidenceObservationRejected() from None
