"""Strict caller boundaries; neutral authored inputs, never semantic gold."""

import hashlib
import json

import pytest

from agent_app.contracts import (
    CaseState,
    EvidenceBundle,
    EvidenceHit,
    Fact,
    GroundedGap,
    ReasoningContext,
)
from agent_app.reasoning.claim_plan import (
    build_claim_messages,
    build_claim_request,
    render_claim_plan,
    validate_claim_request,
)
from agent_app.reasoning.grounding import (
    GroundingRejected,
    build_grounded_messages,
    make_grounded_request,
    render_grounded_plan,
    source_content_sha256,
    validate_grounded_request,
)


def neutral_request():
    case = CaseState(
        case_id="neutral-boundary-case",
        case_revision=2,
        facts=(
            Fact(name="streamlit_version", value="2.4.0", source_ref="user:2", turn_id="turn:2"),
            Fact(
                name="reported_component",
                value="connection pool",
                source_ref="user:2",
                turn_id="turn:2",
            ),
            Fact(
                name="streamlit_version",
                value="2.3.0",
                source_ref="user:1",
                turn_id="turn:1",
                status="superseded",
            ),
        ),
        unknowns=("runtime_details",),
        checks_performed=("The user reports trying a reduced example.",),
    )
    hit = EvidenceHit(
        source_id="neutral-boundary-doc",
        chunk_id="neutral-boundary-chunk",
        source_url="https://example.org/neutral_(guide)",
        source_type="doc",
        applicable_versions=("2.4.0",),
        excerpt=(
            "# A documented pattern\r\n\r\n"
            "A limited observation, not a verified runtime fix. فارسی 🧪\r\n\r\n"
            "```python\r\nvalue = 'do not execute'\r\n\r\nprint(value)\r\n```\r\n\r\n"
            "## Qualification\r\n\r\nA later condition remains part of this section.\r\n"
        ),
    )
    gap = GroundedGap(
        name="runtime_details",
        kind="user",
        description="The runtime details are unknown.",
        necessity="The user can identify the affected runtime.",
        question="Which runtime is affected?",
    )
    return make_grounded_request(
        case,
        "The connection pool behaves differently after a restart.",
        EvidenceBundle(snapshot_id="neutral-boundary-snapshot", hits=(hit,)),
        gaps=(gap,),
    )


def valid_boundary_outputs():
    """All four routes and both claim modes, with full serialized surfaces."""
    request = neutral_request()
    context = ReasoningContext(
        run_id="neutral-boundary-run",
        case_id=request.case.case_id,
        case_revision=request.case.case_revision,
        attempt_index=1,
        remaining_model_attempts=1,
        remaining_retrieval_rounds=1,
        can_refine=True,
    )
    outputs = {
        "source_hash": source_content_sha256(request.evidence.hits[0]),
        "grounded_request": request.model_dump(mode="json"),
        "grounded_messages": build_grounded_messages(request, context),
    }
    for route in ("answer", "ask", "escalate", "retrieve_more"):
        selected = route in {"answer", "escalate"}
        plan = {
            "context_sha256": request.context_sha256,
            "decision": route,
            "sources": (
                [
                    {
                        "chunk_id": request.evidence.hits[0].chunk_id,
                        "content_sha256": source_content_sha256(request.evidence.hits[0]),
                    }
                ]
                if selected
                else []
            ),
            "question_name": "runtime_details" if route == "ask" else None,
            "retrieval_queries": ["connection pool runtime reference"]
            if route == "retrieve_more"
            else [],
        }
        outputs[f"grounded_{route}"] = render_grounded_plan(request, plan).model_dump(mode="json")
    for mode in ("paragraphs", "sections"):
        claim = build_claim_request(request, block_mode=mode)
        outputs[f"{mode}_request"] = claim.model_dump(mode="json")
        outputs[f"{mode}_messages"] = build_claim_messages(claim, context)
        for route in ("answer", "ask", "escalate", "retrieve_more"):
            selected = route in {"answer", "escalate"}
            plan = {
                "context_sha256": claim.context_sha256,
                "decision": route,
                "passages": [[0, 0 if mode == "sections" else 1]] if selected else [],
                "user_facts": [0, 1] if selected else [],
                "question_name": "runtime_details" if route == "ask" else None,
                "retrieval_queries": ["connection pool runtime reference"]
                if route == "retrieve_more"
                else [],
            }
            outputs[f"{mode}_{route}"] = render_claim_plan(claim, plan).model_dump(mode="json")
    return outputs


def output_digests():
    return {
        name: hashlib.sha256(
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        for name, value in valid_boundary_outputs().items()
    }


# Captured from the unmodified validators before implementing detachment.
BASELINE_DIGESTS = {
    "source_hash": "9ba6c302d2b81629385928d60c08a70d1c3f6bc623a1a671063262450d69ef3c",
    "grounded_request": "83a9019c32d30ed48b7af7b8d5b576a0f8c391d0052fb647d04c33cbdfa4e60e",
    "grounded_messages": "a8711d203c0534eac3e3f39ad75446fba4949c3ecde9fef1e307acbab2372fed",
    "grounded_answer": "52a7cdaa7e0b04298d2d9e70a1ac9654b8178aded65df4626d741a460cee3f23",
    "grounded_ask": "53ed8d17f59da21b06439d6adb37d084ec8a46db5ac8075d06353ad90216115a",
    "grounded_escalate": "b260352eb9f369fc8680646b93e99d7e0c1450c8edad312ee72c22a2caf8e25f",
    "grounded_retrieve_more": "31d859e49a3744f0256c7a4ebb736548cccdec22037535ad1a4e2ae7ee86d92b",
    "paragraphs_request": "5132864cb579d33dafbfbc95a9c2e52916ab8928efed45794b6eaab07f653199",
    "paragraphs_messages": "ba4456f4d716e8d59d1a3059ccab22bc55b50a43f7f713ea08cc4a4564410eff",
    "paragraphs_answer": "2c23344e08adaaf30734808d46cc1181e1332b48d62d08f81168f910f1b12835",
    "paragraphs_ask": "e1b9ef49b011be695ba126c970ef33f9e07d94c621e5200e04ede0d8e96b78a9",
    "paragraphs_escalate": "1dc093b95f86e0707928fb9d0e708aae5f4a6904bd249ee1283da5f3e8368ff8",
    "paragraphs_retrieve_more": "31d859e49a3744f0256c7a4ebb736548cccdec22037535ad1a4e2ae7ee86d92b",
    "sections_request": "ffa7de321d454bcc6808ee253a1d565bf343e1886e5ffbb53e62f3599591bd32",
    "sections_messages": "c71645e76d730eaee5027ba01350d6e2af2a0a0f56adf6c4fd633d779b5e1dbd",
    "sections_answer": "00eeed0a43c2d76f2ff64058d5cfcdd933953e9dcffb23417718afb1498c8ad7",
    "sections_ask": "e1b9ef49b011be695ba126c970ef33f9e07d94c621e5200e04ede0d8e96b78a9",
    "sections_escalate": "d49a703acc78ec5320d555ae007c41db7639bbd7cc8a6300bc674df98dbdd8ba",
    "sections_retrieve_more": "31d859e49a3744f0256c7a4ebb736548cccdec22037535ad1a4e2ae7ee86d92b",
}


def test_valid_full_request_messages_and_all_render_routes_keep_original_bytes():
    assert output_digests() == BASELINE_DIGESTS


def _hidden(model, kind):
    if kind == "undeclared_attribute":
        return model.model_copy(update={"NEUTRAL_HIDDEN_NAME": "NEUTRAL_HIDDEN_VALUE"})
    changed = model.model_copy(deep=True)
    object.__setattr__(
        changed,
        "__pydantic_extra__" if kind == "extra_storage" else "__pydantic_private__",
        {"NEUTRAL_HIDDEN_NAME": "NEUTRAL_HIDDEN_VALUE"},
    )
    return changed


def _replace(request, location, change):
    if location == "request":
        return change(request)
    if location == "case":
        return request.model_copy(update={"case": change(request.case)})
    if location == "fact":
        case = request.case.model_copy(
            update={"facts": (change(request.case.facts[0]), *request.case.facts[1:])}
        )
        return request.model_copy(update={"case": case})
    if location == "bundle":
        return request.model_copy(update={"evidence": change(request.evidence)})
    if location == "hit":
        bundle = request.evidence.model_copy(update={"hits": (change(request.evidence.hits[0]),)})
        return request.model_copy(update={"evidence": bundle})
    return request.model_copy(update={"gaps": (change(request.gaps[0]),)})


def _reject(call, code="grounded_context_mismatch"):
    with pytest.raises(GroundingRejected) as caught:
        call()
    assert caught.value.code == code
    assert str(caught.value) == code
    assert "NEUTRAL_HIDDEN" not in str(caught.value)
    assert caught.value.__suppress_context__


@pytest.mark.parametrize("kind", ["undeclared_attribute", "extra_storage", "private_storage"])
@pytest.mark.parametrize("location", ["request", "case", "fact", "bundle", "hit", "gap"])
def test_grounded_validator_rejects_hidden_data_before_dump(location, kind):
    request = _replace(neutral_request(), location, lambda model: _hidden(model, kind))
    _reject(lambda: validate_grounded_request(request))


@pytest.mark.parametrize("kind", ["undeclared_attribute", "extra_storage", "private_storage"])
@pytest.mark.parametrize("location", ["case", "fact", "bundle", "hit", "gap"])
def test_grounded_builder_rejects_hidden_ingress_before_it_can_be_discarded(location, kind):
    request = _replace(neutral_request(), location, lambda model: _hidden(model, kind))
    _reject(
        lambda: make_grounded_request(
            request.case, request.user_message, request.evidence, gaps=request.gaps
        )
    )


@pytest.mark.parametrize("kind", ["undeclared_attribute", "extra_storage", "private_storage"])
def test_source_digest_refuses_hidden_data_instead_of_hashing_a_sanitized_projection(kind):
    hit = _hidden(neutral_request().evidence.hits[0], kind)
    _reject(lambda: source_content_sha256(hit), "grounded_source_mismatch")


@pytest.mark.parametrize("mode", ["paragraphs", "sections"])
@pytest.mark.parametrize("kind", ["undeclared_attribute", "extra_storage", "private_storage"])
@pytest.mark.parametrize(
    "location", ["claim", "block", "request", "case", "fact", "bundle", "hit", "gap"]
)
def test_claim_validator_rejects_hidden_data_at_every_owned_nested_boundary(mode, kind, location):
    claim = build_claim_request(neutral_request(), block_mode=mode)
    if location == "claim":
        claim = _hidden(claim, kind)
    elif location == "block":
        claim = claim.model_copy(
            update={"blocks": ((_hidden(claim.blocks[0][0], kind), *claim.blocks[0][1:]),)}
        )
    else:
        claim = claim.model_copy(
            update={
                "grounded": _replace(claim.grounded, location, lambda model: _hidden(model, kind))
            }
        )
    _reject(lambda: validate_claim_request(claim))


@pytest.mark.parametrize(
    ("location", "changes"),
    [
        ("case", {"case_revision": True}),
        ("fact", {"value": 7}),
        ("fact", {"provenance_kind": "NEUTRAL_HIDDEN_VALUE"}),
        ("bundle", {"snapshot_id": 7}),
        ("hit", {"excerpt": 7}),
        ("hit", {"source_type": "NEUTRAL_HIDDEN_VALUE"}),
        ("gap", {"question": 7}),
        ("gap", {"kind": "NEUTRAL_HIDDEN_VALUE"}),
    ],
)
def test_nested_declared_values_remain_strict_and_diagnostics_stay_constant(location, changes):
    request = _replace(neutral_request(), location, lambda model: model.model_copy(update=changes))
    _reject(lambda: validate_grounded_request(request))
    _reject(
        lambda: make_grounded_request(
            request.case, request.user_message, request.evidence, gaps=request.gaps
        )
    )
    # Preserve the malformed nested object until the claim validation boundary.
    claim = build_claim_request(neutral_request()).model_copy(update={"grounded": request})
    _reject(lambda: validate_claim_request(claim))
    if location == "hit":
        _reject(lambda: source_content_sha256(request.evidence.hits[0]), "grounded_source_mismatch")


def test_validated_snapshots_detach_nested_models_from_caller_objects():
    request = neutral_request()
    validated = validate_grounded_request(request)
    rebuilt = make_grounded_request(
        request.case, request.user_message, request.evidence, gaps=request.gaps
    )
    claim = build_claim_request(request)
    validated_claim = validate_claim_request(claim)
    before = validated.model_dump_json()
    before_claim = validated_claim.model_dump_json()
    object.__setattr__(request.case.facts[0], "value", "different caller-owned value")
    object.__setattr__(request.evidence.hits[0], "excerpt", "different caller-owned excerpt")
    assert validated.model_dump_json() == before
    assert rebuilt.model_dump_json() == before
    assert validated_claim.model_dump_json() == before_claim
