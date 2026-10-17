"""Pure review-candidate configuration binding; never runtime or quality attestation.

Inputs, including code/index/file pins and caller composition, are supplied by the
caller. This module checks their shape, compatibility and equality. It does not
read files, environment, credentials, a ledger, an index or a running application.
Existing adapter metadata, receipts, factories and defaults are unchanged.
"""

import hashlib
import json
import re
from collections.abc import Mapping
from decimal import Context, Decimal, localcontext
from typing import Annotated, Literal

from pydantic import SecretStr, TypeAdapter

from agent_app.contracts import GroundedGap, Identifier, RunLimits
from agent_app.llm.config import METIS_CHAT_URL, MetisConfig
from agent_app.llm.pricing import get_price
from agent_app.orchestration.retrieval_profile import (
    retrieval_profile_options,
    validate_retrieval_profile,
)
from agent_app.orchestration.validation import detached_contract
from agent_app.reasoning.catalog import validate_user_gaps

_PUBLIC_METIS_FIELDS = (
    "live_enabled",
    "model",
    "phase",
    "prompt_policy",
    "response_mode",
    "grounded_decision_contracts",
    "grounded_source_gap_handoff",
    "grounded_source_gap_investigation",
    "grounded_source_selection_reminder",
    "grounded_complementary_sources",
    "grounded_resource_guidance",
    "grounded_source_capacity",
    "grounded_compact_plan",
    "grounded_json_object",
    "continuation_id",
    "max_output_tokens",
    "input_token_reserve",
    "max_request_usd",
)
_CATEGORIES = ("metis", "retrieval", "core", "display", "vocabulary", "pins")
_LIMITS = {
    "scope": "supplied_configuration_compatibility_and_equality_only",
    "runtime_verified": False,
    "live_authorization": False,
    "quality_claim": False,
}
_ERROR = "CandidateConfigurationInvalid"
_DECIMAL_BOUND = 1024
# Cache schemas at import; constructing Pydantic schemas during an exported pure
# call can consult Pydantic's environment settings even for primitive fields.
_PUBLIC_ADAPTERS = {
    name: TypeAdapter(
        Annotated[field.annotation, *field.metadata] if field.metadata else field.annotation
    )
    for name in _PUBLIC_METIS_FIELDS
    for field in (MetisConfig.model_fields[name],)
}
_IDENTIFIER_ADAPTER = TypeAdapter(Identifier)


def _need(condition):
    if not condition:
        raise ValueError(_ERROR)


def _canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _hash(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _decimal_text(value):
    # Decimal.normalize() applies the ambient precision and can merge distinct
    # caps. Bound representation growth, then strip only insignificant zeroes.
    parts = value.as_tuple()
    _need(len(parts.digits) <= _DECIMAL_BOUND and abs(parts.exponent) <= _DECIMAL_BOUND)
    text = format(value, "f").rstrip("0").rstrip(".")
    _need(len(text) <= _DECIMAL_BOUND)
    return text


def _public_config(config):
    # Fail closed on future fields; neither serialization nor credential access
    # is used, even for the synthetic object passed to the dependency validator.
    _need(type(config) is MetisConfig)
    _need(set(MetisConfig.model_fields) == {*_PUBLIC_METIS_FIELDS, "api_key"})
    _need(set(vars(config)) == set(MetisConfig.model_fields))
    _need(not config.__pydantic_extra__ and not config.__pydantic_private__)
    values = {}
    for name in _PUBLIC_METIS_FIELDS:
        values[name] = _PUBLIC_ADAPTERS[name].validate_python(getattr(config, name), strict=True)
    values["model"] = MetisConfig.validate_model(values["model"])
    values["max_request_usd"] = MetisConfig.validate_request_cap(values["max_request_usd"])
    synthetic = MetisConfig.model_construct(api_key=SecretStr("public-placeholder"), **values)
    MetisConfig.require_grounded_contract_mode(synthetic)
    _need(values["response_mode"] == "grounded_plan")
    _need(values["phase"] in {"development", "evaluation"})
    _need(values["continuation_id"] is None)
    price = get_price(values["model"])
    _need(price is not None)
    # The registered rates and bounded integer token limits need fewer than 20
    # significant digits. Isolate exact arithmetic from caller precision,
    # rounding, exponent settings and traps; do not change historical pricing.
    with localcontext(Context(prec=64)):
        reserve_cost = price.cost(values["input_token_reserve"], values["max_output_tokens"])
    _need(reserve_cost <= values["max_request_usd"])
    values["max_request_usd"] = _decimal_text(values["max_request_usd"])
    return values


def _source_pins(pins):
    _need(isinstance(pins, Mapping) and 1 <= len(pins) <= 1024)
    result = {}
    for name, digest in pins.items():
        _need(type(name) is str and len(name) <= 200)
        _need(
            name in {"uv.lock", "pyproject.toml"}
            or re.fullmatch(r"src/agent_app/(?:[a-zA-Z0-9_]+/)*[a-zA-Z0-9_]+\.py", name) is not None
        )
        _need(_hash(digest))
        result[name] = digest
    return result


def describe_candidate_configuration(
    *,
    config: MetisConfig,
    retrieval_profile: str,
    adapter_top_k: int,
    caller: Literal["memory_api", "persistent_service"],
    caller_evidence_scope: Literal["all", "exact_user_version"],
    engine_top_k: int,
    run_limits: RunLimits,
    proposal_checks: bool,
    ask_source_background: bool,
    concise_user_draft: bool,
    user_gaps: tuple[GroundedGap, ...],
    snapshot_id: str,
    index_manifest_sha256: str,
    code_commit: str,
    source_sha256: Mapping[str, str],
    vocabulary_raw_sha256: str | None = None,
) -> dict:
    """Describe compatible declared settings, with no startup or freeze approval.

    ``memory_api`` has its current fixed engine defaults. ``persistent_service``
    records explicit service options; this is not inspection of live_backend.
    ``live_enabled`` is bound as supplied, including False for a disabled review
    candidate. Ledger/provider/startup eligibility is deliberately unmeasured.
    Source pins are shape-checked declarations, not verified file observations.
    """
    try:
        public = _public_config(config)
        _need(type(adapter_top_k) is int and 1 <= adapter_top_k <= 5)
        _need(type(engine_top_k) is int and 1 <= engine_top_k <= 50)
        validate_retrieval_profile(retrieval_profile, top_k=adapter_top_k)
        overrides = retrieval_profile_options(retrieval_profile, top_k=engine_top_k)
        _need(type(caller) is str and caller in {"memory_api", "persistent_service"})
        _need(
            type(caller_evidence_scope) is str
            and caller_evidence_scope in {"all", "exact_user_version"}
        )
        _need(
            all(
                type(x) is bool
                for x in (proposal_checks, ask_source_background, concise_user_draft)
            )
        )
        limits = detached_contract(RunLimits, run_limits).model_dump(mode="json")
        if caller == "memory_api":
            _need(caller_evidence_scope == "all" and engine_top_k == 5 and not proposal_checks)
            _need(limits == RunLimits().model_dump(mode="json"))
        _need(type(user_gaps) is tuple)
        gaps = validate_user_gaps(tuple(detached_contract(GroundedGap, gap) for gap in user_gaps))
        definitions = [gap.model_dump(mode="json") for gap in gaps]
        _need(type(snapshot_id) is str)
        _need(_IDENTIFIER_ADAPTER.validate_python(snapshot_id) == snapshot_id)
        _need(re.fullmatch(r"docs-pilot-[0-9a-f]{64}", snapshot_id) is not None)
        _need(_hash(index_manifest_sha256))
        _need(type(code_commit) is str and re.fullmatch(r"[0-9a-f]{40}", code_commit) is not None)
        _need(vocabulary_raw_sha256 is None or _hash(vocabulary_raw_sha256))
        engine = {
            "top_k": engine_top_k,
            "evidence_scope": caller_evidence_scope,
            "repair_repeated_queries": False,
            "retrieval_candidate_multiplier": 1,
            "evidence_utf8_budget_bytes": None,
        } | overrides
        material = {
            "schema_version": 1,
            **_LIMITS,
            "metis": {"endpoint": METIS_CHAT_URL, "configuration": public},
            "retrieval": {
                "profile": retrieval_profile,
                "adapter_top_k": adapter_top_k,
                "adapter_candidate_limit": (25 if retrieval_profile != "native" else adapter_top_k),
                "adapter_selection_policy": (
                    "query_relevance_v1" if retrieval_profile != "native" else "native"
                ),
                "caller": caller,
                "caller_evidence_scope": caller_evidence_scope,
                "profile_overrides": overrides,
                "composed_engine_policy": engine,
            },
            "core": {"run_limits": limits, "proposal_checks": proposal_checks},
            "display": {
                "ask_source_background": ask_source_background,
                "concise_user_draft": concise_user_draft,
            },
            "vocabulary": {
                "definitions": definitions,
                "semantic_sha256": _digest(definitions),
                "declared_raw_sha256": vocabulary_raw_sha256,
            },
            "pins": {
                "snapshot_id": snapshot_id,
                "index_manifest_sha256": index_manifest_sha256,
                "code_commit": code_commit,
                "source_sha256": _source_pins(source_sha256),
            },
        }
        return {**material, "descriptor_sha256": _digest(material)}
    except Exception:
        raise ValueError(_ERROR) from None


def _checked_descriptor(value):
    _need(type(value) is dict)
    _need(set(value) == {"schema_version", *_LIMITS, *_CATEGORIES, "descriptor_sha256"})
    _need(type(value["schema_version"]) is int and value["schema_version"] == 1)
    _need(_hash(value["descriptor_sha256"]))
    # Rebuilding validates both the public input fields and all derived policy,
    # hashes and static limitations; a freshly rehashed inconsistent descriptor
    # cannot claim that a different policy is compatible.
    public = value["metis"]["configuration"]
    _need(type(public) is dict and set(public) == set(_PUBLIC_METIS_FIELDS))
    public = dict(public)
    cap = public["max_request_usd"]
    _need(
        type(cap) is str and len(cap) <= _DECIMAL_BOUND and re.fullmatch(r"0\.\d+", cap) is not None
    )
    public["max_request_usd"] = Decimal(cap)
    config = MetisConfig.model_construct(api_key=SecretStr("public-placeholder"), **public)
    retrieval, core, display = value["retrieval"], value["core"], value["display"]
    vocabulary, pins = value["vocabulary"], value["pins"]
    definitions = vocabulary["definitions"]
    _need(type(definitions) is list)
    gaps = tuple(GroundedGap.model_validate(item) for item in definitions)
    rebuilt = describe_candidate_configuration(
        config=config,
        retrieval_profile=retrieval["profile"],
        adapter_top_k=retrieval["adapter_top_k"],
        caller=retrieval["caller"],
        caller_evidence_scope=retrieval["caller_evidence_scope"],
        engine_top_k=retrieval["composed_engine_policy"]["top_k"],
        run_limits=RunLimits.model_validate(core["run_limits"]),
        proposal_checks=core["proposal_checks"],
        ask_source_background=display["ask_source_background"],
        concise_user_draft=display["concise_user_draft"],
        user_gaps=gaps,
        snapshot_id=pins["snapshot_id"],
        index_manifest_sha256=pins["index_manifest_sha256"],
        code_commit=pins["code_commit"],
        source_sha256=pins["source_sha256"],
        vocabulary_raw_sha256=vocabulary["declared_raw_sha256"],
    )
    _need(_canonical(rebuilt) == _canonical(value))
    return rebuilt


def compare_candidate_configuration(expected: Mapping, observed: Mapping) -> dict:
    """Reject invalid/tampered declarations or report fixed-category differences.

    An accepted comparison means only identical compatible supplied declarations.
    It never grants live access or verifies the provenance/completeness of pins.
    Diagnostics do not echo caller values, source paths or arbitrary field names.
    """
    report = {
        **_LIMITS,
        "accepted": False,
        "descriptors_compatible": False,
        "differences": [],
        "diagnostics": [],
    }
    try:
        first, second = _checked_descriptor(expected), _checked_descriptor(observed)
        differences = [category for category in _CATEGORIES if first[category] != second[category]]
        report.update(
            accepted=not differences, descriptors_compatible=True, differences=differences
        )
    except Exception:
        report["diagnostics"] = [_ERROR]
    return report
