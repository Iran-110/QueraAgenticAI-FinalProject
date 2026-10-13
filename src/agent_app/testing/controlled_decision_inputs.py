"""Runtime-only projection of frozen V9 material, without labels or scripted plans.

The catalogs/conflicts are manually curated, answer-informed development inputs.
This helper neither authorizes paid work nor proves source truth or RAG quality.
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from agent_app.contracts import (
    CaseState,
    EvidenceBundle,
    GroundedGap,
    GroundedRequest,
    RetrievalRequest,
)
from agent_app.orchestration.validation import detached_contract
from agent_app.reasoning.grounding import make_grounded_request
from agent_app.reasoning.grounding_experiments import load_grounding_pack

ROOT = Path(__file__).resolve().parents[3]
SUITE_PATH = "experiments/decision_quality/cases-grounding-v9.json"
PROTOCOL_PATH = "experiments/decision_quality/protocol-grounding-v9.json"
_RELEASE_MECHANISM = "release-150-multiselect-key-identity-v8"


class ControlledInputsRejected(ValueError):
    def __init__(self):
        super().__init__("ControlledDecisionInputsRejected")


class FixedEvidenceUnavailable(ValueError):
    def __init__(self):
        super().__init__("FixedEvidenceUnavailable")


@dataclass(frozen=True, slots=True)
class ControlledCondition:
    condition_id: str
    case: CaseState
    user_message: str
    bundles: tuple[EvidenceBundle, ...]
    gaps: tuple[GroundedGap, ...]
    conflict_groups: tuple[tuple[str, ...], ...]


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _hash(value) -> str:
    return _sha(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    )


def _current_catalog(pack, original, evidence):
    """Registered manual projection using only the currently supplied source pool.

    Original fixture annotations stay untouched. The stale-source annotation
    described a later removal before it occurred; it cannot be a model input.
    """
    gaps = tuple(GroundedGap.model_validate(gap) for gap in original["grounding_catalog"]["gaps"])
    user_gaps = tuple(gap for gap in gaps if gap.kind == "user")
    source_gaps = tuple(gap for gap in gaps if gap.kind == "source")
    present = {hit.chunk_id for hit in evidence.hits}
    if original["id"] == "controlled-v8-refinement-stale-source":
        if _RELEASE_MECHANISM in present:
            full = next(case for case in pack.suite["cases"] if case["id"] == "controlled-v8-full")
            source_gaps = tuple(
                GroundedGap.model_validate(gap)
                for gap in full["grounding_catalog"]["gaps"]
                if gap["kind"] == "source"
            )
        else:
            source_gaps = tuple(
                gap.model_copy(
                    update={
                        "description": "The currently supplied evidence lacks the key-identity release-mechanism excerpt."
                    }
                )
                if gap.name == "documentation_gap_1"
                else gap
                for gap in source_gaps
            )
    elif original["id"] == "controlled-v8-key-evidence-removed":
        if _RELEASE_MECHANISM in present:
            raise ControlledInputsRejected()
        source_gaps = tuple(
            gap.model_copy(
                update={
                    "description": "The currently supplied evidence lacks the key-identity release-mechanism excerpt."
                }
            )
            if gap.name == "documentation_gap_1"
            else gap
            for gap in source_gaps
        )
    groups = tuple(tuple(group) for group in original["grounding_catalog"]["conflict_groups"])
    return user_gaps + source_gaps, groups


def load_conditions() -> tuple[ControlledCondition, ...]:
    """Preserve original material except disclosed IDs/current-catalog normalization."""
    try:
        pack = load_grounding_pack()
        conditions = []
        for index, original in enumerate(pack.suite["cases"], start=1):
            bundles = tuple(EvidenceBundle.model_validate(bundle) for bundle in original["bundles"])
            gaps, groups = _current_catalog(pack, original, bundles[0])
            conditions.append(
                ControlledCondition(
                    condition_id=original["id"],
                    case=CaseState.model_validate(original["case_state"]).model_copy(
                        update={"case_id": f"c4-condition-{index:02d}"}
                    ),
                    user_message=original["user_message"],
                    bundles=bundles,
                    gaps=gaps,
                    conflict_groups=groups,
                )
            )
        return tuple(conditions)
    except Exception:
        raise ControlledInputsRejected() from None


def _material(condition: ControlledCondition) -> dict:
    if (
        type(condition) is not ControlledCondition
        or type(condition.condition_id) is not str
        or type(condition.user_message) is not str
        or type(condition.bundles) is not tuple
        or type(condition.gaps) is not tuple
        or type(condition.conflict_groups) is not tuple
        or any(type(group) is not tuple for group in condition.conflict_groups)
    ):
        raise ControlledInputsRejected()
    return {
        "condition_id": condition.condition_id,
        "case": detached_contract(CaseState, condition.case).model_dump(mode="json"),
        "user_message": condition.user_message,
        "bundles": [
            detached_contract(EvidenceBundle, bundle).model_dump(mode="json")
            for bundle in condition.bundles
        ],
        "gaps": [
            detached_contract(GroundedGap, gap).model_dump(mode="json") for gap in condition.gaps
        ],
        "conflict_groups": [list(group) for group in condition.conflict_groups],
    }


def grounded_request(
    condition: ControlledCondition,
    case: CaseState,
    message: str,
    evidence: EvidenceBundle,
) -> GroundedRequest:
    """Bind the actual case/message and exact supplied registered round only.

    Equality includes the round and complete source content/version metadata;
    identical source IDs or a newly calculated hash do not authorize mutations.
    Future registered bundles are never inserted into the current request.
    """
    try:
        material = _material(condition)
        registered = next(
            item for item in load_conditions() if item.condition_id == condition.condition_id
        )
        if material != _material(registered):
            raise ValueError
        actual_case = detached_contract(CaseState, case)
        actual_evidence = detached_contract(EvidenceBundle, evidence)
        if (
            type(message) is not str
            or actual_case != registered.case
            or message != registered.user_message
        ):
            raise ValueError
        index = actual_evidence.retrieval_round - 1
        if not 0 <= index < len(registered.bundles):
            raise ValueError
        expected = registered.bundles[index].model_copy(update={"retrieval_round": index + 1})
        if actual_evidence != expected:
            raise ValueError
        pack = load_grounding_pack()
        original = next(
            item for item in pack.suite["cases"] if item["id"] == condition.condition_id
        )
        gaps, groups = _current_catalog(pack, original, actual_evidence)
        return make_grounded_request(
            actual_case,
            message,
            actual_evidence,
            gaps=gaps,
            conflict_groups=groups,
        )
    except Exception:
        raise ControlledInputsRejected() from None


class FixedRetriever:
    """Serve registered rounds sequentially; record queries, never execute snippets."""

    def __init__(self, bundles: tuple[EvidenceBundle, ...]):
        try:
            if type(bundles) is not tuple or not 1 <= len(bundles) <= 2:
                raise ValueError
            detached = tuple(detached_contract(EvidenceBundle, bundle) for bundle in bundles)
            if len({bundle.snapshot_id for bundle in detached}) != 1:
                raise ValueError
            self._bytes = tuple(bundle.model_dump_json().encode() for bundle in detached)
            self._snapshot = detached[0].snapshot_id
        except Exception:
            raise FixedEvidenceUnavailable() from None
        self.requests: list[RetrievalRequest] = []
        self.returned: list[EvidenceBundle] = []
        self._index = 0

    def search(self, request: RetrievalRequest) -> EvidenceBundle:
        try:
            request = detached_contract(RetrievalRequest, request)
            self.requests.append(request.model_copy(deep=True))
            if request.snapshot_id != self._snapshot or self._index >= len(self._bytes):
                raise ValueError
            bundle = EvidenceBundle.model_validate_json(self._bytes[self._index])
            if len(bundle.hits) > request.top_k:
                raise ValueError
            bundle = bundle.model_copy(update={"retrieval_round": self._index + 1})
            self._index += 1
            self.returned.append(bundle.model_copy(deep=True))
            return bundle
        except Exception:
            raise FixedEvidenceUnavailable() from None


def registration_inputs() -> dict:
    """Pins/disclosures for a NEW protocol, never old offline permission or gold.

    Source-file hashes below are the registered original blob pins. This helper
    preserves their frozen excerpts; it does not freshly authenticate those blobs.
    """
    try:
        pack = load_grounding_pack()
        conditions = load_conditions()
        round_catalogs = {
            condition.condition_id: {
                str(bundle.retrieval_round): {
                    "gaps": [
                        gap.model_dump(mode="json")
                        for gap in _current_catalog(pack, original, bundle)[0]
                    ],
                    "conflict_groups": [
                        list(group) for group in _current_catalog(pack, original, bundle)[1]
                    ],
                }
                for bundle in condition.bundles
            }
            for condition, original in zip(conditions, pack.suite["cases"], strict=True)
        }
        return {
            "suite_path": SUITE_PATH,
            "suite_sha256": _sha((ROOT / SUITE_PATH).read_bytes()),
            "protocol_path": PROTOCOL_PATH,
            "protocol_sha256": _sha((ROOT / PROTOCOL_PATH).read_bytes()),
            "material_sha256_by_condition": {
                condition.condition_id: _hash(
                    {
                        "condition": _material(condition),
                        "current_round_catalogs": round_catalogs[condition.condition_id],
                    }
                )
                for condition in conditions
            },
            "runtime_case_aliases": {
                original["case_state"]["case_id"]: condition.case.case_id
                for condition, original in zip(conditions, pack.suite["cases"], strict=True)
            },
            "current_catalog_sha256_by_condition": {
                name: {round_id: _hash(catalog) for round_id, catalog in catalogs.items()}
                for name, catalogs in round_catalogs.items()
            },
            "docs_commit": pack.suite["docs_commit"],
            "source_snapshot_date": pack.suite["source_snapshot_date"],
            "source_files": [dict(source) for source in pack.suite["provenance"]["source_files"]],
            "source_files_are_registered_pins": True,
            "provenance_sha256": _hash(pack.suite["provenance"]),
            "manual_metadata_sha256": _hash(pack.suite["manual_metadata_boundary"]),
            "reserved_issue_ids": list(pack.suite["reserved_issue_ids"]),
            "retained_label_bearing_fact_attributions": [
                {
                    "condition_id": condition.condition_id,
                    "fact_index": index,
                    "source_ref": fact.source_ref,
                    "turn_id": fact.turn_id,
                    "reason": "Existing attribution describes an explicit past/current correction; preserved, not future outcome metadata.",
                }
                for condition in conditions
                for index, fact in enumerate(condition.case.facts)
                if "controlled-v8" in fact.source_ref or "controlled-v8" in fact.turn_id
            ],
            "disclosures": {
                "answer_informed_development_selection": True,
                "same_issue_answer_used_as_evidence": False,
                "manually_curated_gaps_and_conflicts": True,
                "opaque_runtime_case_ids": True,
                "source_catalog_normalized_per_current_round": True,
                "original_catalog_retained_exactly": False,
                "normalization_is_prepaid_baseline_amendment": True,
                "automatic_gap_or_conflict_detection": False,
                "exposed_development_only": True,
                "independent_issue_families": 1,
                "final_evaluation_case_count": 0,
                "original_protocol_authorizes_paid_work": False,
                "quarantine_applied_to_real_RAG_claim": False,
                "quality_claim": False,
            },
        }
    except Exception:
        raise ControlledInputsRejected() from None
