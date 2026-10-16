"""Neutral configuration/construction controls; no evaluation data or live I/O."""

import hashlib
import json
from copy import deepcopy

import pytest

from agent_app.contracts import CaseState, EvidenceBundle, Fact, GroundedGap
from agent_app.llm.config import MetisConfig
from agent_app.orchestration import SupportEngine
from agent_app.orchestration.configuration_freeze import (
    compare_candidate_configuration,
    describe_candidate_configuration,
)
from agent_app.orchestration.handoff import ReasoningCapture, build_handoff, validate_handoff
from agent_app.orchestration.registered_reasoner import (
    build_registered_grounded_reasoner,
    compare_registered_grounded_configuration,
    describe_registered_grounded_configuration,
)
from agent_app.reasoning.grounding import source_content_sha256
from agent_app.testing.fakes import FakeRetriever

INVALID = "RegisteredGroundedConfigurationInvalid"
MISMATCH = "RegisteredGroundedConfigurationMismatch"
UNAVAILABLE = "RegisteredGroundedCompositionUnavailable"


def gap():
    return GroundedGap(
        name="neutral_reproduction",
        kind="user",
        description="The caller declared a missing reproduction.",
        necessity="The user can supply a reproduction.",
        question="Please supply a minimal reproduction.",
    )


def arguments(**updates):
    from agent_app.contracts import RunLimits

    return {
        "config": MetisConfig(
            api_key="synthetic-placeholder",
            response_mode="grounded_plan",
            live_enabled=True,
        ),
        "retrieval_profile": "candidate_relevance_v1",
        "adapter_top_k": 5,
        "caller": "memory_api",
        "caller_evidence_scope": "all",
        "engine_top_k": 5,
        "run_limits": RunLimits(),
        "proposal_checks": False,
        "ask_source_background": False,
        "concise_user_draft": False,
        "user_gaps": (),
        "snapshot_id": "docs-pilot-" + "a" * 64,
        "index_manifest_sha256": "b" * 64,
        "code_commit": "c" * 40,
        "source_sha256": {"src/agent_app/orchestration/engine.py": "d" * 64},
    } | updates


def descriptor(policy="legacy_v1", **changes):
    return describe_registered_grounded_configuration(
        renderer_policy=policy, **arguments(**changes)
    )


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def rehash(value):
    value["descriptor_sha256"] = hashlib.sha256(
        canonical({key: item for key, item in value.items() if key != "descriptor_sha256"}).encode()
    ).hexdigest()


def test_legacy_descriptor_is_embedded_byte_exact_and_v1_stays_separate():
    legacy = describe_candidate_configuration(**arguments())
    registered = descriptor()
    assert canonical(registered["candidate"]) == canonical(legacy)
    assert compare_candidate_configuration(legacy, legacy)["accepted"]
    assert not compare_candidate_configuration(legacy, registered)["accepted"]
    assert not compare_registered_grounded_configuration(legacy, registered)["accepted"]
    assert not compare_registered_grounded_configuration(registered, legacy)["accepted"]


def test_renderer_policy_changes_the_actual_registered_identity():
    one, two = descriptor(), descriptor("review_brief_v1")
    assert one["candidate"] == two["candidate"]
    assert one["descriptor_sha256"] != two["descriptor_sha256"]
    report = compare_registered_grounded_configuration(one, two)
    assert not report["accepted"] and report["differences"] == ["renderer"]


@pytest.mark.parametrize("policy", ("legacy_v1", "review_brief_v1"))
def test_valid_matching_registration_has_no_runtime_quality_or_budget_authority(policy):
    value = descriptor(policy)
    report = compare_registered_grounded_configuration(value, deepcopy(value))
    assert report["accepted"]
    for obj in (value, report):
        assert obj["runtime_verified"] is False
        assert obj["live_authorization"] is False
        assert obj["quality_claim"] is False


@pytest.mark.parametrize("policy", (None, True, False, 1, [], {}, "", "brief", "review_brief_v2"))
def test_invalid_policy_rejected_before_any_composition(policy):
    with pytest.raises(ValueError, match="^" + INVALID + "$"):
        descriptor(policy)


@pytest.mark.parametrize(
    "field", ("renderer_policy", "composition", "schema_version", "descriptor_sha256", "candidate")
)
def test_missing_envelope_field_never_calls_factory(field):
    valid = descriptor()
    changed = deepcopy(valid)
    del changed[field]
    called = []
    with pytest.raises(ValueError, match="^" + INVALID + "$"):
        build_registered_grounded_reasoner(valid, changed, planner_factory=lambda: called.append(1))
    assert called == []


@pytest.mark.parametrize(
    "change",
    (
        {"schema_version": 1},
        {"schema_version": True},
        {"schema_version": 3},
        {"composition": "automatic_live_factory"},
        {"runtime_verified": True},
        {"live_authorization": True},
        {"quality_claim": True},
        {"renderer_policy": "unknown"},
        {"EXTRA_SECRET_NAME": "PRIVATE_VALUE"},
    ),
)
def test_rehashed_inconsistent_registration_rejected_without_echo(change):
    valid = descriptor()
    bad = deepcopy(valid)
    bad.update(change)
    rehash(bad)
    called = []
    report = compare_registered_grounded_configuration(valid, bad)
    assert not report["accepted"]
    assert report["diagnostics"] == [INVALID]
    assert "PRIVATE_VALUE" not in canonical(report) and "EXTRA_SECRET_NAME" not in canonical(report)
    with pytest.raises(ValueError, match="^" + INVALID + "$"):
        build_registered_grounded_reasoner(valid, bad, planner_factory=lambda: called.append(1))
    assert called == []


def test_valid_but_different_policy_rejected_before_factory():
    calls = []
    with pytest.raises(ValueError, match="^" + MISMATCH + "$"):
        build_registered_grounded_reasoner(
            descriptor(),
            descriptor("review_brief_v1"),
            planner_factory=lambda: calls.append(1),
        )
    assert calls == []


class Planner:
    def __init__(self):
        self.requests = []

    def plan(self, request, *, context):
        self.requests.append(request.model_dump(mode="json"))
        question = next((g for g in request.gaps if g.kind == "user"), None)
        return {
            "context_sha256": request.context_sha256,
            "decision": "ask" if question else "escalate",
            "sources": [
                {"chunk_id": hit.chunk_id, "content_sha256": source_content_sha256(hit)}
                for hit in request.evidence.hits
            ],
            "question_name": question.name if question else None,
            "retrieval_queries": [],
        }


@pytest.mark.parametrize("policy", ("legacy_v1", "review_brief_v1"))
@pytest.mark.parametrize("ask_background", (False, True))
@pytest.mark.parametrize("concise", (False, True))
def test_checked_policy_reaches_actual_constructor_and_bound_catalog(
    policy, ask_background, concise
):
    config = arguments()["config"].model_copy(
        update={
            "grounded_source_gap_handoff": True,
            "grounded_source_gap_investigation": True,
        }
    )
    value = descriptor(
        policy,
        config=config,
        ask_source_background=ask_background,
        concise_user_draft=concise,
        user_gaps=(gap(),),
    )
    calls = []
    planner = Planner()

    def factory():
        calls.append(1)
        return planner

    reasoner, binding = build_registered_grounded_reasoner(
        value, deepcopy(value), planner_factory=factory
    )
    assert calls == [1] and reasoner.planner is planner
    assert reasoner.review_brief is (policy == "review_brief_v1")
    assert reasoner.ask_source_background is ask_background
    assert reasoner.concise_user_draft is concise
    assert reasoner.source_gap_handoff is True and reasoner.source_gap_investigation is True
    assert binding["descriptor_sha256"] == value["descriptor_sha256"]
    assert binding["renderer_policy"] == policy
    assert binding["reasoner_construction_bound"] is True
    assert binding["live_authorization"] is False and binding["quality_claim"] is False
    case = CaseState(case_id="closeout-neutral", unknowns=("neutral_reproduction",))
    bundle = EvidenceBundle(snapshot_id="closeout-neutral")
    request = reasoner.request_factory(case, "The current report.", bundle)
    assert any(
        g.name == "neutral_reproduction" and g.question == gap().question for g in request.gaps
    )


@pytest.mark.parametrize("policy", ("legacy_v1", "review_brief_v1"))
def test_registered_reasoner_runs_through_engine_and_fresh_handoff(policy):
    value = descriptor(policy, user_gaps=(gap(),))
    reasoner, binding = build_registered_grounded_reasoner(value, value, planner_factory=Planner)
    case = CaseState(
        case_id="closeout-neutral",
        unknowns=("neutral_reproduction",),
        facts=(Fact(name="streamlit_version", value="2.6.0", source_ref="user:1", turn_id="1"),),
    )
    bundle = EvidenceBundle(snapshot_id="closeout-neutral")
    capture = ReasoningCapture(reasoner)
    result = SupportEngine(FakeRetriever([bundle]), capture, snapshot_id=bundle.snapshot_id).run(
        case,
        "The current report.",
        run_id="closeout-neutral-run",
    )
    assert result.status == "awaiting_approval" and result.analysis.decision == "ask"
    assert result.analysis.next_question == gap().question
    handoff = build_handoff(result, capture.last)
    assert validate_handoff(handoff) == handoff
    assert "approved" not in handoff.model_dump()
    assert binding["descriptor_sha256"] == value["descriptor_sha256"]


@pytest.mark.parametrize("result", (None, object(), {"plan": "not_callable"}))
def test_invalid_factory_result_is_not_reported_as_bound(result):
    value = descriptor()
    called = []

    def factory():
        called.append(1)
        return result

    with pytest.raises(ValueError, match="^" + UNAVAILABLE + "$"):
        build_registered_grounded_reasoner(value, value, planner_factory=factory)
    assert called == [1]


def test_callback_failure_does_not_echo_private_values():
    value = descriptor()

    def factory():
        raise RuntimeError("PRIVATE_CALLBACK_VALUE")

    with pytest.raises(ValueError) as error:
        build_registered_grounded_reasoner(value, value, planner_factory=factory)
    assert str(error.value) == UNAVAILABLE


def test_noncallable_factory_fails_before_use():
    value = descriptor()
    with pytest.raises(ValueError, match="^" + INVALID + "$"):
        build_registered_grounded_reasoner(value, value, planner_factory=None)


def test_known_active_user_fact_suppresses_bound_question():
    value = descriptor("review_brief_v1", user_gaps=(gap(),))
    reasoner, _ = build_registered_grounded_reasoner(value, value, planner_factory=Planner)
    fact = Fact(
        name="neutral_reproduction", value="already supplied", source_ref="user:2", turn_id="2"
    )
    case = CaseState(case_id="closeout-neutral", facts=(fact,))
    request = reasoner.request_factory(
        case, "The user already supplied it.", EvidenceBundle(snapshot_id="neutral")
    )
    assert not any(g.name == fact.name for g in request.gaps)


def test_exported_gate_and_constructor_do_not_load_credentials_or_resources(monkeypatch):
    import builtins
    import os
    import socket
    import sqlite3
    from pathlib import Path

    import httpx
    from pydantic import SecretStr

    settings = arguments(user_gaps=(gap(),))
    expected = describe_registered_grounded_configuration(
        renderer_policy="review_brief_v1", **settings
    )

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Unexpected environment, credential or resource access")

    class NoEnvironment(dict):
        __getitem__ = get = __iter__ = __contains__ = forbidden

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(os, "getenv", forbidden)
    monkeypatch.setattr(os, "environ", NoEnvironment())
    monkeypatch.setattr(SecretStr, "get_secret_value", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    monkeypatch.setattr(httpx, "Client", forbidden)
    observed = describe_registered_grounded_configuration(
        renderer_policy="review_brief_v1", **settings
    )
    assert compare_registered_grounded_configuration(expected, observed)["accepted"]
    reasoner, binding = build_registered_grounded_reasoner(
        expected, observed, planner_factory=Planner
    )
    assert reasoner.review_brief is True and binding["reasoner_construction_bound"] is True
