"""Versioned declarations and a gate for an injected GroundedReasoner only.

The v1 candidate remains unchanged. V2 explicitly registers renderer policy and
can bind local reasoner flags/catalog construction after an exact comparison.
The caller still owns budget guards, planner/model configuration, engine/ports,
physical source/build verification and recording this binding in a NEW receipt.
Neither declared engine composition (memory API or persistent service) is
inspected or applied by this helper. ClaimReasoner is outside this composition.
"""

import hashlib
from collections.abc import Callable, Mapping
from typing import Literal, get_args

from agent_app.contracts import GroundedGap
from agent_app.orchestration.configuration_freeze import (
    _CATEGORIES,
    _canonical,
    _checked_descriptor,
    _hash,
    describe_candidate_configuration,
)
from agent_app.orchestration.ports import ReasoningStopCode, ReasoningStopped
from agent_app.reasoning.catalog import caller_catalog, validate_user_gaps
from agent_app.reasoning.grounding import GroundedReasoner

_INVALID = "RegisteredGroundedConfigurationInvalid"
_MISMATCH = "RegisteredGroundedConfigurationMismatch"
_UNAVAILABLE = "RegisteredGroundedCompositionUnavailable"
_COMPOSITION = "injected_grounded_reasoner_v1"
_LIMITS = {
    "runtime_verified": False,
    "live_authorization": False,
    "quality_claim": False,
}
_BINDING_LIMITS = {
    "planner_configuration_verified": False,
    "engine_settings_applied": False,
    "physical_pins_verified": False,
    "endpoint_model_verified": False,
    "budget_guards_run": False,
}
_SCOPE = "supplied_registered_grounded_configuration_equality_only"


def _need(condition, code=_INVALID):
    if not condition:
        raise ValueError(code)


def _plain_json(value):
    """Reject exotic/cyclic/oversized input before invoking the v1 rebuilder.

    These generous bounds contain every valid v1 descriptor, whose bounded
    source pins and six bounded question definitions dominate its size.
    """
    nodes, characters = 0, 0

    def visit(item, depth):
        nonlocal nodes, characters
        nodes += 1
        _need(nodes <= 10_000 and depth <= 12)
        if type(item) is dict:
            for key, child in item.items():
                _need(type(key) is str)
                visit(key, depth + 1)
                visit(child, depth + 1)
        elif type(item) is list:
            for child in item:
                visit(child, depth + 1)
        elif type(item) is str:
            characters += len(item)
            _need(len(item) <= 22_000 and characters <= 1_000_000)
        else:
            _need(item is None or type(item) in {bool, int})
            if type(item) is int:
                _need(abs(item) <= 1_000_000)

    visit(value, 0)


def _envelope(candidate, renderer_policy):
    _need(type(renderer_policy) is str and renderer_policy in {"legacy_v1", "review_brief_v1"})
    material = {
        "schema_version": 2,
        "composition": _COMPOSITION,
        "candidate": candidate,
        "renderer_policy": renderer_policy,
        "scope": _SCOPE,
        **_LIMITS,
        "binding_limits": dict(_BINDING_LIMITS),
    }
    return {**material, "descriptor_sha256": hashlib.sha256(_canonical(material)).hexdigest()}


def describe_registered_grounded_configuration(
    *, renderer_policy: Literal["legacy_v1", "review_brief_v1"], **legacy_arguments
) -> dict:
    """Create a detached hash-bound v2 envelope; never upgrade a stored v1.

    This pure declaration reads no files, environment configuration, credential
    values or planner objects and constructs no runtime clients or reasoners.
    Its dictionaries remain editable Python exports; edits must pass complete
    rebuilding/checks and constitute a new declaration, never an old receipt.
    """
    try:
        candidate = describe_candidate_configuration(**legacy_arguments)
        _plain_json(candidate)
        return _envelope(candidate, renderer_policy)
    except Exception:
        raise ValueError(_INVALID) from None


def _checked_registered(value):
    _need(type(value) is dict)
    _need(
        set(value)
        == {
            "schema_version",
            "composition",
            "candidate",
            "renderer_policy",
            "scope",
            *_LIMITS,
            "binding_limits",
            "descriptor_sha256",
        }
    )
    _plain_json(value)
    _need(type(value["schema_version"]) is int and value["schema_version"] == 2)
    _need(_hash(value["descriptor_sha256"]))
    candidate = _checked_descriptor(value["candidate"])
    rebuilt = _envelope(candidate, value["renderer_policy"])
    _need(_canonical(rebuilt) == _canonical(value))
    return rebuilt


def _differences(first, second):
    result = [name for name in _CATEGORIES if first["candidate"][name] != second["candidate"][name]]
    if first["renderer_policy"] != second["renderer_policy"]:
        result.append("renderer")
    return result


def compare_registered_grounded_configuration(expected: Mapping, observed: Mapping) -> dict:
    """Compare only valid same-kind v2 declarations; no implicit v1 conversion."""
    report = {
        "scope": _SCOPE,
        **_LIMITS,
        "binding_limits": dict(_BINDING_LIMITS),
        "accepted": False,
        "descriptors_compatible": False,
        "differences": [],
        "diagnostics": [],
    }
    try:
        first, second = _checked_registered(expected), _checked_registered(observed)
        differences = _differences(first, second)
        report.update(
            accepted=not differences, descriptors_compatible=True, differences=differences
        )
    except Exception:
        report["diagnostics"] = [_INVALID]
    return report


def _clean_stop(error):
    try:
        code, status = error.code, error.status
        if (
            type(code) is str
            and code in get_args(ReasoningStopCode.__value__)
            and type(status) is str
            and status in {"error", "budget_stopped"}
        ):
            return ReasoningStopped(code, status)
    except Exception:
        pass
    return None


def build_registered_grounded_reasoner(
    expected: Mapping,
    observed: Mapping,
    *,
    planner_factory: Callable,
) -> tuple[GroundedReasoner, dict]:
    """Gate one actual local constructor; the factory is invoked only after match.

    Frozen local flags and detached vocabulary are derived before the callback;
    mutations to either caller declaration cannot change the applied settings.
    The callback receives no descriptor/credentials and owns its model config
    and all prerequisite guards. The returned planner must have callable plan.
    Typed terminal ReasoningStopped failures retain only validated code/status.
    This does not certify future mutation of the returned Python reasoner.
    """
    try:
        first, second = _checked_registered(expected), _checked_registered(observed)
    except Exception:
        raise ValueError(_INVALID) from None
    _need(not _differences(first, second), _MISMATCH)
    _need(callable(planner_factory))
    try:
        candidate = first["candidate"]
        configuration, display = candidate["metis"]["configuration"], candidate["display"]
        flags = {
            "source_gap_handoff": configuration["grounded_source_gap_handoff"],
            "source_gap_investigation": configuration["grounded_source_gap_investigation"],
            "ask_source_background": display["ask_source_background"],
            "concise_user_draft": display["concise_user_draft"],
        }
        if first["renderer_policy"] == "review_brief_v1":
            flags["review_brief"] = True
        definitions = validate_user_gaps(
            tuple(
                GroundedGap.model_validate(item) for item in candidate["vocabulary"]["definitions"]
            )
        )

        def request_factory(case, message, evidence):
            return caller_catalog(case, message, evidence, definitions=definitions)

        # All applied settings above are detached before external code runs.
        planner = planner_factory()
        _need(callable(getattr(planner, "plan", None)), _UNAVAILABLE)
        reasoner = GroundedReasoner(planner, request_factory=request_factory, **flags)
        receipt = {
            "schema_version": 1,
            "composition": _COMPOSITION,
            "scope": "constructed_grounded_reasoner_flags_and_caller_catalog_only",
            "descriptor_sha256": first["descriptor_sha256"],
            "renderer_policy": first["renderer_policy"],
            "reasoner_construction_bound": True,
            **_LIMITS,
            "binding_limits": dict(_BINDING_LIMITS),
        }
        return reasoner, receipt
    except ReasoningStopped as error:
        clean = _clean_stop(error)
        if clean is not None:
            raise clean from None
        raise ValueError(_UNAVAILABLE) from None
    except Exception:
        raise ValueError(_UNAVAILABLE) from None
