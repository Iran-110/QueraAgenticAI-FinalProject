"""Opt-in JSON provider formatting uses intercepted HTTP and disposable ledgers."""

import json
from decimal import Decimal

import httpx
import pytest
from test_compact_gateway import COMPACT, compact_output, engine_run
from test_grounded_gateway import (
    GAP,
    SYNTHETIC_KEY,
    context,
    grounded_request,
    observed_cost,
    reservations,
    response_body,
)
from test_grounded_gateway import gateway_factory as gateway_factory

from agent_app.contracts import GroundedPlan
from agent_app.llm.budget import BudgetLedger
from agent_app.llm.config import METIS_CHAT_URL, MetisConfig
from agent_app.llm.grounded import MetisGroundedPlanner
from agent_app.llm.metis import configured_grounded_messages, request_id_for
from agent_app.orchestration.ports import ReasoningStopped
from agent_app.testing.http_pilot_runtime import offline_network

JSON_MODE = {**COMPACT, "grounded_json_object": True}


def ask_plan(request, compact):
    if compact:
        return compact_output(request)
    return GroundedPlan(
        context_sha256=request.context_sha256, decision="ask", question_name=GAP.name
    ).model_dump_json()


@pytest.mark.parametrize("compact", [False, True])
@pytest.mark.parametrize("flag", [None, False, True])
def test_json_mode_changes_only_exact_provider_parameter_and_never_prompt(
    gateway_factory, compact, flag
):
    request, attribution = grounded_request(), context()
    changes = COMPACT if compact else {}
    if flag is not None:
        changes = {**changes, "grounded_json_object": flag}
    raw = ask_plan(request, compact)
    gateway, ledger, calls, path = gateway_factory(
        config_changes=changes, responses=[response_body(raw)]
    )
    with offline_network():
        output = gateway.plan(request, context=attribution)
    if compact:
        assert GroundedPlan.model_validate_json(output).question_name == GAP.name
    else:
        assert output == raw
    baseline_config = gateway.config.model_copy(update={"grounded_json_object": False})
    expected = {
        "model": gateway.config.model,
        "messages": list(configured_grounded_messages(baseline_config, request, attribution)),
        "max_tokens": gateway.config.max_output_tokens,
        "stream": False,
    }
    if flag is True:
        expected["response_format"] = {"type": "json_object"}
    assert json.loads(calls[0].content) == expected
    assert calls[0].content == httpx.Request("POST", METIS_CHAT_URL, json=expected).content
    assert "JSON" in expected["messages"][0]["content"]
    assert "grounded_json_object" not in json.dumps(expected)
    assert gateway.config.grounded_json_object is (flag is True)
    assert len(calls) == len(reservations(path)) == 1
    assert reservations(path)[0]["request_id"] == request_id_for(attribution)
    assert reservations(path)[0]["status"] == "settled"
    assert ledger.snapshot().settled_usd == observed_cost()
    assert ledger.snapshot().reserved_usd == ledger.snapshot().uncertain_usd == 0


@pytest.mark.parametrize("bad", ["true", "false", 0, 1, None, [], {}])
def test_json_mode_configuration_requires_explicit_boolean(bad):
    with pytest.raises(ValueError):
        MetisConfig(api_key=SYNTHETIC_KEY, response_mode="grounded_plan", grounded_json_object=bad)


def test_json_mode_requires_grounded_mode_and_does_not_turn_live_on():
    with pytest.raises(ValueError, match="JSON object mode requires grounded plan mode"):
        MetisConfig(api_key=SYNTHETIC_KEY, grounded_json_object=True)
    config = MetisConfig(
        api_key=SYNTHETIC_KEY, response_mode="grounded_plan", grounded_json_object=True
    )
    assert config.live_enabled is False


def test_json_mode_environment_is_default_off_and_mode_bound(monkeypatch):
    monkeypatch.setenv("METIS_API_KEY", SYNTHETIC_KEY)
    monkeypatch.delenv("METIS_GROUNDED_JSON_OBJECT", raising=False)
    monkeypatch.delenv("METIS_RESPONSE_MODE", raising=False)
    assert MetisConfig.from_env().grounded_json_object is False
    monkeypatch.setenv("METIS_GROUNDED_JSON_OBJECT", "true")
    with pytest.raises(ValueError, match="JSON object mode requires grounded plan mode"):
        MetisConfig.from_env()
    monkeypatch.setenv("METIS_RESPONSE_MODE", "grounded_plan")
    assert MetisConfig.from_env().grounded_json_object is True
    monkeypatch.setenv("METIS_GROUNDED_JSON_OBJECT", "false")
    assert MetisConfig.from_env().grounded_json_object is False


@pytest.mark.parametrize("bad", ["", "TRUE", "1", "false ", "json_object"])
def test_json_mode_rejects_ambiguous_environment_values(monkeypatch, bad):
    monkeypatch.setenv("METIS_API_KEY", SYNTHETIC_KEY)
    monkeypatch.setenv("METIS_RESPONSE_MODE", "grounded_plan")
    monkeypatch.setenv("METIS_GROUNDED_JSON_OBJECT", bad)
    with pytest.raises(ValueError, match="Grounded mode flags must be true or false"):
        MetisConfig.from_env()


@pytest.mark.parametrize("bad_then_good", [True, False])
def test_json_mode_keeps_local_schema_validation_and_existing_two_attempt_allowance(
    gateway_factory, bad_then_good
):
    request = grounded_request()
    raw = compact_output(request)
    gateway, ledger, calls, path = gateway_factory(
        config_changes=JSON_MODE,
        responses=[
            response_body("{invalid"),
            response_body(raw if bad_then_good else "{invalid"),
            response_body(raw),
        ],
    )
    with offline_network():
        result, contexts, _ = engine_run(gateway)
    assert result.model_attempts == len(calls) == len(reservations(path)) == 2
    assert [item.attempt_index for item in contexts] == [1, 2]
    assert contexts[0].run_id == contexts[1].run_id
    assert contexts[1].remaining_model_attempts == 0
    assert not contexts[1].can_refine
    assert all(
        json.loads(call.content)["response_format"] == {"type": "json_object"} for call in calls
    )
    assert ledger.snapshot().settled_usd == observed_cost() * 2
    assert ledger.snapshot().reserved_usd == ledger.snapshot().uncertain_usd == 0
    if bad_then_good:
        assert result.status == "awaiting_approval" and result.analysis.decision == "ask"
    else:
        assert result.status == "error" and result.analysis is None
    repair = json.loads(json.loads(calls[1].content)["messages"][1]["content"])
    assert repair["repair_issue_codes"] == ["invalid_grounded_plan"]
    assert "{invalid" not in json.dumps(repair)


@pytest.mark.parametrize(
    "change,terminal",
    [
        ({"sources": [99]}, "GroundedSourceMismatch"),
        ({"context_sha256": "0" * 64}, "GroundedContextMismatch"),
    ],
)
def test_json_mode_does_not_repair_terminal_binding_failure(gateway_factory, change, terminal):
    gateway, ledger, calls, path = gateway_factory(
        config_changes=JSON_MODE,
        responses=[response_body(compact_output(grounded_request(), "answer", **change))],
    )
    with offline_network():
        result, _, _ = engine_run(gateway)
    assert result.error_code == terminal and result.model_attempts == len(calls) == 1
    assert result.analysis is None and len(reservations(path)) == 1
    assert ledger.snapshot().settled_usd == observed_cost()


def test_json_mode_does_not_repair_provider_length_even_with_valid_json(gateway_factory):
    body = response_body(compact_output(grounded_request()))
    body["choices"][0]["finish_reason"] = "length"
    gateway, ledger, calls, path = gateway_factory(config_changes=JSON_MODE, responses=[body])
    with offline_network():
        result, contexts, _ = engine_run(gateway)
    assert (
        result.error_code == "ProviderResponseInvalid" and result.model_attempts == len(calls) == 1
    )
    assert result.analysis is None and gateway.latest_wire_observation(contexts[0]) is None
    assert (
        reservations(path)[0]["status"] == "settled"
        and ledger.snapshot().settled_usd == observed_cost()
    )


def test_toggling_json_mode_cannot_buy_a_second_send_for_same_request_identity(gateway_factory):
    request, attribution = grounded_request(), context()
    gateway, ledger, calls, path = gateway_factory(
        responses=[response_body(ask_plan(request, False))]
    )
    with offline_network():
        gateway.plan(request, context=attribution)
        before = ledger.snapshot()
        config = gateway.config.model_copy(update={"grounded_json_object": True})
        with MetisGroundedPlanner(
            config,
            ledger,
            transport=httpx.MockTransport(lambda _: pytest.fail("identity replay sent HTTP")),
        ) as toggled:
            with pytest.raises(ReasoningStopped) as caught:
                toggled.plan(request, context=attribution)
        assert caught.value.code == "DuplicateModelRequest"
    assert len(calls) == len(reservations(path)) == 1 and ledger.snapshot() == before


def test_unsupported_parameter_status_preserves_uncertain_hold_and_never_falls_back(tmp_path):
    path = tmp_path / "unsupported-json.sqlite3"
    ledger = BudgetLedger.create(path, limit_usd=Decimal("1"), opening_spend_usd=Decimal("0"))
    config = MetisConfig(
        api_key=SYNTHETIC_KEY, live_enabled=True, response_mode="grounded_plan", **JSON_MODE
    )
    calls = []

    def unsupported(request):
        calls.append(request)
        assert json.loads(request.content)["response_format"] == {"type": "json_object"}
        return httpx.Response(
            400, json={"error": {"message": "Synthetic unsupported response_format"}}
        )

    with (
        offline_network(),
        MetisGroundedPlanner(config, ledger, transport=httpx.MockTransport(unsupported)) as gateway,
    ):
        result, _, _ = engine_run(gateway)
    assert result.error_code == "ProviderRequestFailed" and result.model_attempts == len(calls) == 1
    assert result.analysis is None
    rows = reservations(path)
    assert len(rows) == 1 and rows[0]["status"] == "uncertain"
    assert ledger.snapshot().uncertain_usd > 0
    assert ledger.snapshot().settled_usd == ledger.snapshot().reserved_usd == 0


def test_json_mode_preserves_pre_dispatch_halt_no_reservation_or_transport(gateway_factory):
    gateway, ledger, calls, path = gateway_factory(config_changes=JSON_MODE)
    ledger.halt()
    with offline_network():
        result, _, _ = engine_run(gateway)
    assert result.error_code == "BudgetExceeded" and calls == []
    assert reservations(path) == [] and ledger.snapshot().halted


def test_json_mode_keeps_full_utf8_input_guard_before_reservation(gateway_factory):
    request = grounded_request()
    evidence = request.evidence.model_copy(
        update={"hits": (request.evidence.hits[0].model_copy(update={"excerpt": "ی" * 19000}),)}
    )
    oversized = grounded_request(evidence=evidence)
    gateway, ledger, calls, path = gateway_factory(config_changes=JSON_MODE)
    with offline_network(), pytest.raises(ReasoningStopped) as caught:
        gateway.plan(oversized, context=context())
    assert caught.value.code == "ContextLimitExceeded"
    assert calls == [] and reservations(path) == []
    assert ledger.snapshot().settled_usd == ledger.snapshot().uncertain_usd == 0


def test_json_mode_cannot_increase_per_request_cost_bound(gateway_factory):
    gateway, ledger, calls, path = gateway_factory(
        config_changes={**JSON_MODE, "max_request_usd": Decimal("0.0001")}
    )
    with offline_network(), pytest.raises(ReasoningStopped) as caught:
        gateway.plan(grounded_request(), context=context())
    assert caught.value.code == "CostBoundExceeded"
    assert calls == [] and reservations(path) == []
    assert ledger.snapshot().settled_usd == ledger.snapshot().uncertain_usd == 0
