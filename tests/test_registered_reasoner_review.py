"""Independent neutral probes of the explicit construction gate."""

import builtins
import json
import os
import socket
import sqlite3
from copy import deepcopy
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr
from test_registered_reasoner import (
    INVALID,
    MISMATCH,
    UNAVAILABLE,
    Planner,
    arguments,
    descriptor,
    gap,
    rehash,
)

from agent_app.contracts import CaseState, EvidenceBundle, Fact
from agent_app.llm.config import MetisConfig
from agent_app.orchestration import SupportEngine
from agent_app.orchestration.ports import ReasoningStopped
from agent_app.orchestration.registered_reasoner import (
    build_registered_grounded_reasoner,
    compare_registered_grounded_configuration,
    describe_registered_grounded_configuration,
)
from agent_app.testing.fakes import FakeRetriever


def _current_case():
    return CaseState(
        case_id="independent-registered-neutral",
        facts=(Fact(name="streamlit_version", value="2.5.0", source_ref="user:1", turn_id="1"),),
        unknowns=("neutral_reproduction",),
    )


@pytest.mark.parametrize("policy", ("legacy_v1", "review_brief_v1"))
def test_callback_cannot_replace_snapshotted_flags_catalog_or_receipt(policy):
    settings = arguments()["config"].model_copy(
        update={"grounded_source_gap_handoff": True, "grounded_source_gap_investigation": True}
    )
    expected = descriptor(
        policy,
        config=settings,
        ask_source_background=True,
        concise_user_draft=True,
        user_gaps=(gap(),),
    )
    observed = deepcopy(expected)
    saved_digest = expected["descriptor_sha256"]
    planner = Planner()
    calls = []

    def factory():
        calls.append(1)
        expected["candidate"]["vocabulary"]["definitions"][0]["question"] = "PRIVATE_MUTATION"
        expected.clear()
        observed.clear()
        return planner

    reasoner, receipt = build_registered_grounded_reasoner(
        expected, observed, planner_factory=factory
    )
    assert calls == [1]
    assert reasoner.review_brief is (policy == "review_brief_v1")
    assert reasoner.source_gap_handoff and reasoner.source_gap_investigation
    assert reasoner.ask_source_background and reasoner.concise_user_draft
    assert receipt["descriptor_sha256"] == saved_digest
    bundle = EvidenceBundle(snapshot_id="independent-registered-neutral")
    result = SupportEngine(FakeRetriever([bundle]), reasoner, snapshot_id=bundle.snapshot_id).run(
        _current_case(), "The current report.", run_id="independent-registered-run"
    )
    assert result.status == "awaiting_approval"
    assert result.analysis.decision == "ask"
    assert result.analysis.next_question == result.analysis.user_draft == gap().question
    assert "PRIVATE_MUTATION" not in result.analysis.model_dump_json()


def test_mutating_exported_request_and_receipt_cannot_change_bound_catalog():
    value = descriptor("review_brief_v1", user_gaps=(gap(),))
    reasoner, receipt = build_registered_grounded_reasoner(value, value, planner_factory=Planner)
    bundle = EvidenceBundle(snapshot_id="independent-registered-neutral")
    request = reasoner.request_factory(_current_case(), "The current report.", bundle)
    selected = next(item for item in request.gaps if item.name == gap().name)
    object.__setattr__(selected, "question", "PRIVATE_MUTATION")
    receipt.clear()
    value["candidate"]["vocabulary"]["definitions"].clear()
    again = reasoner.request_factory(_current_case(), "The current report.", bundle)
    assert next(item for item in again.gaps if item.name == gap().name).question == gap().question


@pytest.mark.parametrize("category", ("metis", "vocabulary", "pins"))
def test_valid_nonrenderer_mismatch_never_invokes_planner_factory(category):
    expected = descriptor()
    if category == "metis":
        changed = descriptor(
            config=arguments()["config"].model_copy(update={"max_output_tokens": 2048})
        )
    elif category == "vocabulary":
        changed = descriptor(user_gaps=(gap(),))
    else:
        changed = descriptor(code_commit="e" * 40)
    assert compare_registered_grounded_configuration(expected, changed)["differences"] == [category]
    calls = []
    with pytest.raises(ValueError, match="^" + MISMATCH + "$"):
        build_registered_grounded_reasoner(
            expected, changed, planner_factory=lambda: calls.append(1)
        )
    assert not calls


@pytest.mark.parametrize(
    "target", ("derived_policy", "display_type", "vocabulary_extra", "binding_limit")
)
def test_rehashed_nested_tampering_rejects_before_factory(target):
    expected = descriptor(user_gaps=(gap(),))
    changed = deepcopy(expected)
    candidate = changed["candidate"]
    if target == "derived_policy":
        candidate["retrieval"]["composed_engine_policy"]["evidence_scope"] = "all"
    elif target == "display_type":
        candidate["display"]["ask_source_background"] = 1
    elif target == "vocabulary_extra":
        candidate["vocabulary"]["definitions"][0]["PRIVATE_NAME"] = "PRIVATE_VALUE"
    else:
        changed["binding_limits"]["budget_guards_run"] = True
    rehash(candidate)
    rehash(changed)
    report = compare_registered_grounded_configuration(expected, changed)
    assert report["diagnostics"] == [INVALID] and not report["accepted"]
    assert "PRIVATE" not in json.dumps(report)
    calls = []
    with pytest.raises(ValueError, match="^" + INVALID + "$"):
        build_registered_grounded_reasoner(
            expected, changed, planner_factory=lambda: calls.append(1)
        )
    assert not calls


@pytest.mark.parametrize("kind", ("typed_hidden", "cycle", "exotic_dict"))
def test_nonplain_nested_state_rejects_without_executing_callbacks(kind):
    expected = descriptor(user_gaps=(gap(),))
    changed = deepcopy(expected)
    if kind == "typed_hidden":
        hidden = gap().model_copy(update={"PRIVATE_NAME": "PRIVATE_VALUE"})
        changed["candidate"]["vocabulary"]["definitions"] = [hidden]
    elif kind == "cycle":
        recursive = []
        recursive.append(recursive)
        changed["candidate"]["vocabulary"]["definitions"] = recursive
    else:

        class Exotic(dict):
            def items(self):
                pytest.fail("Exotic dictionary callback executed")

        changed["candidate"]["vocabulary"] = Exotic(changed["candidate"]["vocabulary"])
    calls = []
    with pytest.raises(ValueError, match="^" + INVALID + "$"):
        build_registered_grounded_reasoner(
            expected, changed, planner_factory=lambda: calls.append(1)
        )
    assert not calls


@pytest.mark.parametrize("mutation", (None, "code", "status"))
def test_factory_terminal_stop_is_sanitized_or_rejected_without_repetition(mutation):
    value = descriptor()
    stop = ReasoningStopped("BudgetExceeded", "budget_stopped")
    stop.args = ("PRIVATE_VALUE",)
    stop.PRIVATE_NAME = "PRIVATE_VALUE"
    if mutation:
        setattr(stop, mutation, "PRIVATE_VALUE")
    calls = []

    def factory():
        calls.append(1)
        raise stop

    if mutation:
        with pytest.raises(ValueError, match="^" + UNAVAILABLE + "$"):
            build_registered_grounded_reasoner(value, value, planner_factory=factory)
    else:
        with pytest.raises(ReasoningStopped) as caught:
            build_registered_grounded_reasoner(value, value, planner_factory=factory)
        assert caught.value is not stop
        assert caught.value.code == "BudgetExceeded" and caught.value.status == "budget_stopped"
        assert "PRIVATE" not in repr(caught.value) + repr(vars(caught.value))
        assert caught.value.__suppress_context__
    assert calls == [1]


@pytest.mark.parametrize("policy", ("legacy_v1", "review_brief_v1"))
def test_pure_gates_and_neutral_constructor_need_no_io_or_secret_access(monkeypatch, policy):
    values = arguments(user_gaps=(gap(),))

    def forbidden(*args, **kwargs):
        pytest.fail("External state or credential access attempted")

    with monkeypatch.context() as patch:
        patch.setattr(builtins, "open", forbidden)
        patch.setattr(Path, "open", forbidden)
        patch.setattr(Path, "read_bytes", forbidden)
        patch.setattr(Path, "read_text", forbidden)
        patch.setattr(os, "getenv", forbidden)
        patch.setattr(type(os.environ), "get", forbidden)
        patch.setattr(type(os.environ), "__getitem__", forbidden)
        patch.setattr(sqlite3, "connect", forbidden)
        patch.setattr(socket, "socket", forbidden)
        patch.setattr(httpx, "Client", forbidden)
        patch.setattr(MetisConfig, "model_dump", forbidden)
        patch.setattr(MetisConfig, "model_dump_json", forbidden)
        patch.setattr(SecretStr, "get_secret_value", forbidden)
        value = describe_registered_grounded_configuration(renderer_policy=policy, **values)
        report = compare_registered_grounded_configuration(value, value)
        reasoner, receipt = build_registered_grounded_reasoner(
            value, value, planner_factory=Planner
        )
    assert report["accepted"] and receipt["reasoner_construction_bound"]
    assert reasoner.review_brief is (policy == "review_brief_v1")
