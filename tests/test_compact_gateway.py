"""Offline compact-wire conversion keeps the existing gateway and engine limits."""

import hashlib
import json
from decimal import Decimal

import httpx
import pytest
from fastapi.testclient import TestClient
from test_budget_quarantine_scope import multiple_holds as multiple_holds
from test_evaluation_live import CountedMock
from test_evaluation_live import index as index
from test_grounded_configuration_flags import configuration
from test_grounded_gateway import (
    CASE,
    EVIDENCE,
    GAP,
    MESSAGE,
    SYNTHETIC_KEY,
    context,
    grounded_request,
    observed_cost,
    reservations,
    response_body,
)
from test_grounded_gateway import gateway_factory as gateway_factory
from test_quality_probe import ROOT, prepare
from test_quality_probe import response as canonical_response

from agent_app import live_backend
from agent_app.contracts import GroundedPlan, ProposalHandoff
from agent_app.evaluation import live
from agent_app.llm.config import MetisConfig
from agent_app.llm.metis import configured_grounded_messages, request_id_for
from agent_app.orchestration import SupportEngine
from agent_app.reasoning.catalog import load_user_gap_vocabulary
from agent_app.reasoning.grounding import (
    GroundedReasoner,
    GroundingRejected,
    build_grounded_messages,
    make_grounded_request,
    render_grounded_plan,
    source_content_sha256,
)
from agent_app.testing.dev_three_model_probe import ledger_observation
from agent_app.testing.fakes import FakeRetriever
from agent_app.testing.http_pilot_runtime import offline_network
from agent_app.testing.quality_probe import run_quality_batch
from agent_app.testing.stability_probe import VOCABULARY

COMPACT = {"grounded_decision_contracts": True, "grounded_compact_plan": True}
OBSERVATION_FIELDS = {
    "schema_version",
    "wire_format",
    "request_id",
    "raw_output_sha256",
    "raw_utf8_bytes",
    "json_shape",
    "decision",
    "sources_count",
    "selected_indexes",
    "wire_schema_valid",
    "canonical_binding_valid",
    "rejection_code",
    "unexpected_field_count",
}


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def compact_output(request, decision="ask", **changes):
    output = {"context_sha256": request.context_sha256, "decision": decision}
    if decision == "retrieve_more":
        output["retrieval_queries"] = ["Search the current Streamlit documentation"]
    else:
        output["sources"] = [0] if decision == "answer" else []
        if decision == "ask":
            output["question_name"] = GAP.name
    return json.dumps(output | changes, ensure_ascii=False, indent=2)


def engine_run(gateway, observations=None):
    contexts = []

    class CapturePlanner:
        def plan(self, request, *, context):
            contexts.append(context.model_copy(deep=True))
            try:
                return gateway.plan(request, context=context)
            finally:
                if observations is not None:
                    observations.append(gateway.latest_wire_observation(context))

    def factory(case, message, evidence):
        return make_grounded_request(case, message, evidence, gaps=(GAP,))

    retriever = FakeRetriever([EVIDENCE])
    result = SupportEngine(
        retriever,
        GroundedReasoner(CapturePlanner(), request_factory=factory),
        snapshot_id=EVIDENCE.snapshot_id,
    ).run(CASE, MESSAGE, run_id=context().run_id)
    return result, contexts, retriever


@pytest.mark.parametrize("decision", ["answer", "ask", "escalate", "retrieve_more"])
def test_compact_http_output_expands_only_current_references_and_attests_raw_bytes(
    gateway_factory, decision
):
    request, attribution = grounded_request(), context()
    raw = compact_output(request, decision)
    gateway, ledger, calls, path = gateway_factory(
        config_changes=COMPACT, responses=[response_body(raw)]
    )
    with offline_network():
        canonical = gateway.plan(request, context=attribution)
    plan = GroundedPlan.model_validate_json(canonical)
    assert plan.context_sha256 == request.context_sha256 and plan.decision == decision
    assert plan.question_name == (GAP.name if decision == "ask" else None)
    assert plan.retrieval_queries == (
        ("Search the current Streamlit documentation",) if decision == "retrieve_more" else ()
    )
    assert [reference.model_dump() for reference in plan.sources] == (
        [
            {
                "chunk_id": EVIDENCE.hits[0].chunk_id,
                "content_sha256": source_content_sha256(EVIDENCE.hits[0]),
            }
        ]
        if decision == "answer"
        else []
    )
    observation = gateway.latest_wire_observation(attribution)
    assert set(observation) == OBSERVATION_FIELDS
    assert observation["schema_version"] == 1
    assert observation["wire_format"] == "grounded-indexed-plan-v1"
    assert observation["request_id"] == request_id_for(attribution)
    assert observation["raw_output_sha256"] == digest(raw) != digest(canonical)
    assert observation["raw_utf8_bytes"] == len(raw.encode())
    assert observation["json_shape"] == "object" and observation["decision"] == decision
    assert observation["wire_schema_valid"] and observation["canonical_binding_valid"]
    assert observation["rejection_code"] is None and observation["unexpected_field_count"] == 0
    assert observation["selected_indexes"] == (
        [0] if decision == "answer" else None if decision == "retrieve_more" else []
    )
    assert observation["sources_count"] == (
        1 if decision == "answer" else None if decision == "retrieve_more" else 0
    )
    observation["raw_output_sha256"] = "caller mutation"
    assert gateway.latest_wire_observation(attribution)["raw_output_sha256"] == digest(raw)
    assert gateway.latest_wire_observation(context(run_id="run:different")) is None
    assert len(calls) == len(reservations(path)) == 1
    assert reservations(path)[0]["status"] == "settled"
    assert ledger.snapshot().settled_usd == observed_cost()
    assert ledger.snapshot().reserved_usd == ledger.snapshot().uncertain_usd == 0
    assert json.loads(calls[0].content)["messages"] == list(
        configured_grounded_messages(gateway.config, request, attribution)
    )


@pytest.mark.parametrize("explicit_false", [False, True])
def test_disabled_compact_mode_preserves_canonical_output_bytes_and_wire(
    gateway_factory, explicit_false
):
    request, attribution = grounded_request(), context()
    raw = (
        " \n"
        + json.dumps(
            GroundedPlan(
                context_sha256=request.context_sha256, decision="ask", question_name=GAP.name
            ).model_dump(mode="json"),
            indent=3,
        )
        + "\n "
    )
    changes = {"grounded_decision_contracts": True}
    if explicit_false:
        changes["grounded_compact_plan"] = False
    gateway, ledger, calls, path = gateway_factory(
        config_changes=changes, responses=[response_body(raw)]
    )
    assert gateway.config.grounded_compact_plan is False
    with offline_network():
        assert gateway.plan(request, context=attribution) == raw
    assert gateway.latest_wire_observation(attribution) is None
    wire = json.loads(calls[0].content)
    assert wire["messages"] == list(
        build_grounded_messages(request, attribution, decision_contracts=True)
    )
    assert json.loads(wire["messages"][1]["content"])["response_schema"]["title"] == (
        "GroundedPlan"
    )
    assert len(calls) == len(reservations(path)) == 1
    assert ledger.snapshot().settled_usd == observed_cost()


def test_compact_index_uses_current_revision_source_and_never_cached_reference(gateway_factory):
    first = grounded_request()
    corrected_hit = EVIDENCE.hits[0].model_copy(
        update={
            "chunk_id": "chunk:corrected-current-source",
            "excerpt": "A different complete synthetic source supplied with the correction.",
        }
    )
    corrected = grounded_request(
        case=CASE.model_copy(update={"case_revision": 3}),
        evidence=EVIDENCE.model_copy(update={"hits": (corrected_hit,)}),
    )
    first_context = context()
    corrected_context = context(case_revision=3, run_id="run:compact-correction")
    first_raw, corrected_raw = [compact_output(item, "answer") for item in (first, corrected)]
    gateway, ledger, calls, path = gateway_factory(
        config_changes=COMPACT,
        responses=[response_body(first_raw), response_body(corrected_raw)],
    )
    with offline_network():
        original = GroundedPlan.model_validate_json(gateway.plan(first, context=first_context))
        current = GroundedPlan.model_validate_json(
            gateway.plan(corrected, context=corrected_context)
        )
    assert original.sources[0].chunk_id == EVIDENCE.hits[0].chunk_id
    assert current.context_sha256 == corrected.context_sha256 != original.context_sha256
    assert current.sources[0].chunk_id == corrected_hit.chunk_id
    assert current.sources[0].content_sha256 == source_content_sha256(corrected_hit)
    assert current.sources != original.sources
    assert gateway.latest_wire_observation(first_context) is None
    assert gateway.latest_wire_observation(corrected_context)["raw_output_sha256"] == digest(
        corrected_raw
    )
    assert len(calls) == len(reservations(path)) == 2
    assert ledger.snapshot().settled_usd == observed_cost() * 2
    assert all(row["status"] == "settled" for row in reservations(path))


@pytest.mark.parametrize(
    "changes,code,terminal_code",
    [
        ({"context_sha256": "0" * 64}, "grounded_context_mismatch", "GroundedContextMismatch"),
        ({"sources": [99]}, "grounded_source_mismatch", "GroundedSourceMismatch"),
    ],
)
def test_binding_violation_is_one_settled_send_and_never_buys_engine_repair(
    gateway_factory, changes, code, terminal_code
):
    raw = compact_output(grounded_request(), "answer", **changes)
    gateway, ledger, calls, path = gateway_factory(
        config_changes=COMPACT,
        responses=[response_body(raw), response_body(compact_output(grounded_request()))],
    )
    with offline_network():
        result, contexts, retriever = engine_run(gateway)
    assert result.status == "error" and result.error_code == terminal_code
    assert result.analysis is None and result.model_attempts == len(calls) == 1
    assert result.retrieval_rounds == len(retriever.requests) == 1
    assert [issue.code for issue in result.output_issues] == [code]
    observation = gateway.latest_wire_observation(contexts[0])
    assert observation["raw_output_sha256"] == digest(raw)
    assert observation["wire_schema_valid"] and not observation["canonical_binding_valid"]
    assert observation["rejection_code"] == code
    assert len(reservations(path)) == 1 and reservations(path)[0]["status"] == "settled"
    assert ledger.snapshot().settled_usd == observed_cost()
    assert ledger.snapshot().reserved_usd == ledger.snapshot().uncertain_usd == 0
    assert not ledger.snapshot().halted


def test_direct_compact_binding_failure_keeps_the_existing_typed_boundary(gateway_factory):
    raw = compact_output(grounded_request(), "answer", sources=[99])
    gateway, _, calls, _ = gateway_factory(config_changes=COMPACT, responses=[response_body(raw)])
    with offline_network(), pytest.raises(GroundingRejected) as caught:
        gateway.plan(grounded_request(), context=context())
    assert caught.value.code == "grounded_source_mismatch" and len(calls) == 1


def test_malformed_first_compact_object_repairs_in_same_run_with_exactly_two_paid_identities(
    gateway_factory,
):
    request = grounded_request()
    marker = "private-synthetic-output-marker"
    bad = compact_output(request, private_synthetic_field=marker)
    good = compact_output(request)
    gateway, ledger, calls, path = gateway_factory(
        config_changes=COMPACT, responses=[response_body(bad), response_body(good)]
    )
    observations = []
    with offline_network():
        result, contexts, retriever = engine_run(gateway, observations)
    assert result.status == "awaiting_approval" and result.analysis.decision == "ask"
    assert result.model_attempts == len(calls) == len(reservations(path)) == 2
    assert result.retrieval_rounds == len(retriever.requests) == 1
    assert [item.attempt_index for item in contexts] == [1, 2]
    assert contexts[0].run_id == contexts[1].run_id
    assert not contexts[1].can_refine and contexts[1].remaining_model_attempts == 0
    assert [issue.code for issue in contexts[1].output_feedback.issues] == ["invalid_grounded_plan"]
    assert len({row["request_id"] for row in reservations(path)}) == 2
    assert all(row["status"] == "settled" for row in reservations(path))
    assert ledger.snapshot().settled_usd == observed_cost() * 2
    assert ledger.snapshot().reserved_usd == ledger.snapshot().uncertain_usd == 0
    second_wire = json.loads(json.loads(calls[1].content)["messages"][1]["content"])
    assert second_wire["repair_issue_codes"] == ["invalid_grounded_plan"]
    assert marker not in json.dumps(second_wire) + result.model_dump_json()
    rejected = observations[0]
    assert set(rejected) == OBSERVATION_FIELDS
    assert rejected["raw_output_sha256"] == digest(bad)
    assert not rejected["wire_schema_valid"] and not rejected["canonical_binding_valid"]
    assert rejected["rejection_code"] == "invalid_grounded_plan"
    assert rejected["unexpected_field_count"] == 1
    assert marker not in json.dumps(rejected) and "private_synthetic_field" not in json.dumps(
        rejected
    )
    assert gateway.latest_wire_observation(contexts[0]) is None
    observation = gateway.latest_wire_observation(contexts[1])
    assert observation["raw_output_sha256"] == digest(good)
    assert observation["wire_schema_valid"] and observation["canonical_binding_valid"]


def test_provider_length_is_settled_terminal_and_has_no_compact_expansion_or_repair(
    gateway_factory,
):
    body = response_body("{" * 4000)
    body["choices"][0]["finish_reason"] = "length"
    body["usage"] = {"prompt_tokens": 100, "completion_tokens": 1024, "total_tokens": 1124}
    gateway, ledger, calls, path = gateway_factory(
        config_changes=COMPACT,
        responses=[body, response_body(compact_output(grounded_request()))],
    )
    with offline_network():
        result, contexts, retriever = engine_run(gateway)
    assert result.status == "error" and result.error_code == "ProviderResponseInvalid"
    assert result.analysis is None and result.model_attempts == len(calls) == 1
    assert result.retrieval_rounds == len(retriever.requests) == 1
    assert gateway.latest_wire_observation(contexts[0]) is None
    row = reservations(path)[0]
    assert len(reservations(path)) == 1 and row["status"] == "settled"
    assert (row["input_tokens"], row["output_tokens"]) == (100, 1024)
    assert ledger.snapshot().settled_usd == (
        Decimal("100") * Decimal("0.000000165") + Decimal("1024") * Decimal("0.000000660")
    )
    assert ledger.snapshot().reserved_usd == ledger.snapshot().uncertain_usd == 0
    assert not ledger.snapshot().halted


@pytest.mark.parametrize("bad", ["true", 1, None])
def test_compact_flag_is_strict_bool(bad):
    with pytest.raises(ValueError):
        MetisConfig(
            api_key=SYNTHETIC_KEY,
            response_mode="grounded_plan",
            grounded_decision_contracts=True,
            grounded_compact_plan=bad,
        )


def test_compact_environment_is_default_false_and_requires_decision_contracts(monkeypatch):
    monkeypatch.setenv("METIS_API_KEY", SYNTHETIC_KEY)
    monkeypatch.setenv("METIS_RESPONSE_MODE", "grounded_plan")
    monkeypatch.delenv("METIS_GROUNDED_COMPACT_PLAN", raising=False)
    monkeypatch.delenv("METIS_GROUNDED_DECISION_CONTRACTS", raising=False)
    assert MetisConfig.from_env().grounded_compact_plan is False
    monkeypatch.setenv("METIS_GROUNDED_COMPACT_PLAN", "true")
    with pytest.raises(ValueError):
        MetisConfig.from_env()
    monkeypatch.setenv("METIS_GROUNDED_DECISION_CONTRACTS", "true")
    config = MetisConfig.from_env()
    assert config.grounded_compact_plan and not config.live_enabled
    monkeypatch.setenv("METIS_GROUNDED_COMPACT_PLAN", "TRUE")
    with pytest.raises(ValueError):
        MetisConfig.from_env()


def test_quality_job_compact_flag_reaches_actual_wire_and_preserves_canonical_attempts(
    multiple_holds,
):
    ledger, protocol, batch, fixtures, config = prepare(multiple_holds)
    batch["jobs"][0]["compact_plan"] = False
    batch["jobs"][1]["compact_plan"] = True
    wires, raw_outputs = [], []

    def respond(request):
        wire = json.loads(request.content)
        wires.append(wire)
        if wire["max_tokens"] == 1024:
            response = canonical_response(request)
            raw_outputs.append(response.json()["choices"][0]["message"]["content"])
            return response
        supplied = json.loads(wire["messages"][1]["content"])["request"]
        user_gaps = [gap for gap in supplied["gaps"] if gap["kind"] == "user"]
        content = {
            "context_sha256": supplied["context_sha256"],
            "decision": "ask" if user_gaps else "escalate",
            "sources": [],
        }
        if user_gaps:
            content["question_name"] = user_gaps[0]["name"]
        raw_outputs.append(json.dumps(content))
        return httpx.Response(200, json=response_body(raw_outputs[-1]))

    with offline_network():
        receipt = run_quality_batch(
            protocol,
            batch,
            fixtures,
            load_user_gap_vocabulary(str(ROOT / VOCABULARY)),
            ledger,
            config,
            ledger_observation(ledger._path),
            underlying=httpx.MockTransport(respond),
        )
    assert receipt["visited_jobs"] == 2 and not receipt["stopped_early"]
    assert receipt["original_accounting_preserved"] and receipt["actual_sends"] == len(wires)
    assert all(job["coverage_complete"] for job in receipt["jobs"])
    assert all(attempt["plan"] for attempt in receipt["attempts"])
    assert all(
        set(attempt["plan"]) == set(GroundedPlan.model_fields) for attempt in receipt["attempts"]
    )
    assert {wire["max_tokens"] for wire in wires} == {1024, 2048}
    for attempt, wire, raw in zip(receipt["attempts"], wires, raw_outputs, strict=True):
        if wire["max_tokens"] == 1024:
            assert "wire_output" not in attempt and attempt["output_sha256"] == digest(raw)
        else:
            observed = attempt["wire_output"]
            assert observed["request_id"] == request_id_for(context(**attempt["context"]))
            assert observed["raw_output_sha256"] == digest(raw) != attempt["output_sha256"]
            assert observed["wire_schema_valid"] and observed["canonical_binding_valid"]
    assert ledger.snapshot().halted and ledger.snapshot().reserved_usd == 0
    assert len(ledger.quarantine_observation().unknown_ids) == 2


@pytest.mark.parametrize(
    "fault,rejection",
    [
        ("context", "grounded_context_mismatch"),
        ("index", "grounded_source_mismatch"),
        ("length", None),
    ],
)
def test_quality_receipt_captures_rejected_compact_wire_without_expansion_or_second_send(
    multiple_holds, fault, rejection
):
    ledger, protocol, batch, fixtures, config = prepare(multiple_holds)
    batch["jobs"] = batch["jobs"][:1]
    batch["jobs"][0]["compact_plan"] = True
    raw_outputs = []

    def respond(request):
        supplied = json.loads(json.loads(request.content)["messages"][1]["content"])["request"]
        if fault == "length":
            raw_outputs.append("{" * 4000)
            body = response_body(raw_outputs[-1])
            body["choices"][0]["finish_reason"] = "length"
        else:
            output = {
                "context_sha256": "0" * 64 if fault == "context" else supplied["context_sha256"],
                "decision": "answer",
                "sources": [0] if fault == "context" else [99],
            }
            raw_outputs.append(json.dumps(output))
            body = response_body(raw_outputs[-1])
        return httpx.Response(200, json=body)

    with offline_network():
        receipt = run_quality_batch(
            protocol,
            batch,
            fixtures,
            load_user_gap_vocabulary(str(ROOT / VOCABULARY)),
            ledger,
            config,
            ledger_observation(ledger._path),
            underlying=httpx.MockTransport(respond),
        )
    assert receipt["visited_jobs"] == receipt["actual_sends"] == len(raw_outputs) == 1
    assert receipt["original_accounting_preserved"] and not receipt["stopped_early"]
    assert not receipt["jobs"][0]["coverage_complete"]
    assert len(receipt["attempts"]) == 1
    attempt = receipt["attempts"][0]
    assert attempt["plan"] is None and "output_sha256" not in attempt
    if fault == "length":
        assert attempt["wire_output"] is None and attempt["error_code"] == "ProviderResponseInvalid"
    else:
        observed = attempt["wire_output"]
        assert observed["raw_output_sha256"] == digest(raw_outputs[0])
        assert observed["wire_schema_valid"] and not observed["canonical_binding_valid"]
        assert observed["rejection_code"] == rejection
    assert ledger.snapshot().halted and ledger.snapshot().reserved_usd == 0
    assert len(ledger.quarantine_observation().unknown_ids) == 2


def test_configured_compact_http_wire_matches_trace_and_canonical_pending_proposal(
    tmp_path, index, monkeypatch
):
    ledger, values = configuration(tmp_path, index, monkeypatch)
    values.update(METIS_GROUNDED_COMPACT_PLAN="true", METIS_GROUNDED_DECISION_CONTRACTS="true")
    wires, raw_outputs, transports, factories = [], [], [], []

    def respond(request):
        wire = json.loads(request.content)
        wires.append(wire)
        supplied = json.loads(wire["messages"][1]["content"])
        assert supplied["wire_format"] == "grounded-indexed-plan-v1"
        raw_outputs.append(
            json.dumps(
                {
                    "context_sha256": supplied["request"]["context_sha256"],
                    "decision": "ask",
                    "sources": [],
                    "question_name": "streamlit_version",
                },
                indent=2,
            )
        )
        return httpx.Response(200, json=response_body(raw_outputs[-1]))

    def transport(*_args, **_kwargs):
        actual = CountedMock(respond)
        transports.append(actual)
        return actual

    def configured(settings):
        factory = live.configured_factory(settings)
        factories.append(factory)
        return factory

    monkeypatch.setattr(httpx, "HTTPTransport", transport)
    with (
        offline_network(),
        TestClient(live_backend.configured_app(values, adapters_factory=configured)) as client,
    ):
        response = client.post(
            "/cases/compact-configured-case/messages",
            json={
                "message": "The widget loses its default and the Streamlit version is unknown.",
                "turn_id": "compact-configured-turn",
                "expected_revision": 0,
                "reported_facts": [],
                "unknowns": ["streamlit_version"],
            },
        )
        assert response.status_code == 200
        view = response.json()
        assert view["pending"] is not None, {
            "status": view["run_outcome"].get("status"),
            "error_code": view["run_outcome"].get("error_code"),
            "provider_sends": len(wires),
            "raw_outputs": len(raw_outputs),
            "trace_errors": [record["error_code"] for record in factories[0]._observations],
        }
        assert view["actions"] == [] and view["pending"]["decision"] == "ask"
        handoff = ProposalHandoff.model_validate(view["pending"]["review_handoff"])
        request, attribution = handoff.grounded_request, handoff.reasoning_context
        expected_messages = configured_grounded_messages(factories[0]._config, request, attribution)
        assert wires[0]["messages"] == list(expected_messages)
        assert json.loads(wires[0]["messages"][1]["content"])["request"] == request.model_dump(
            mode="json"
        )
        canonical_plan = GroundedPlan(
            context_sha256=request.context_sha256,
            decision="ask",
            question_name="streamlit_version",
        )
        expected_analysis = render_grounded_plan(request, canonical_plan)
        assert view["pending"]["analysis"] == expected_analysis.model_dump(mode="json")
        assert handoff.analysis == expected_analysis
        trace = factories[0].observations_for_contexts((attribution,))
        assert len(trace) == 1
        observed = trace[0]
        assert observed["prompt_sha256"] == digest(
            json.dumps(wires[0]["messages"], ensure_ascii=False)
        )
        assert observed["prompt_sha256"] == digest(
            json.dumps(expected_messages, ensure_ascii=False)
        )
        assert observed["ledger_status"] == "settled" and observed["http_send_started"]
        assert observed["wire_output"]["request_id"] == request_id_for(attribution)
        assert observed["wire_output"]["raw_output_sha256"] == digest(raw_outputs[0])
        assert observed["wire_output"]["raw_utf8_bytes"] == len(raw_outputs[0].encode())
        assert observed["wire_output"]["selected_indexes"] == []
        assert observed["wire_output"]["wire_schema_valid"]
        assert observed["wire_output"]["canonical_binding_valid"]
        assert observed["wire_output"]["rejection_code"] is None
    assert len(wires) == len(transports) == len(factories) == 1
    assert transports[0].close_calls == 1 and factories[0].active_clients == 0
    assert ledger.snapshot().settled_usd == observed_cost()
    assert ledger.snapshot().reserved_usd == ledger.snapshot().uncertain_usd == 0


@pytest.mark.parametrize("fault", ["invalid_switch", "missing_contracts", "ordinary_halt"])
def test_configured_compact_guards_run_before_credential_or_transport(
    tmp_path, index, monkeypatch, fault
):
    ledger, values = configuration(tmp_path, index, monkeypatch)
    values.update(METIS_GROUNDED_COMPACT_PLAN="true", METIS_GROUNDED_DECISION_CONTRACTS="true")
    if fault == "invalid_switch":
        values["METIS_GROUNDED_COMPACT_PLAN"] = "TRUE"
    elif fault == "missing_contracts":
        values["METIS_GROUNDED_DECISION_CONTRACTS"] = "false"
    else:
        ledger.halt()
    before = ledger.snapshot()
    credentials, transports = [], []

    class Sensitive(dict):
        def get(self, key, *args):
            if key == "METIS_API_KEY":
                credentials.append(key)
            return super().get(key, *args)

        def __getitem__(self, key):
            if key == "METIS_API_KEY":
                credentials.append(key)
            return super().__getitem__(key)

    def forbidden_transport(*_args, **_kwargs):
        transports.append(True)
        raise AssertionError("No transport may be allocated before configuration guards")

    monkeypatch.setattr(httpx, "HTTPTransport", forbidden_transport)
    with offline_network(), pytest.raises(ValueError) as caught:
        live.configured_factory(Sensitive(values))
    if fault == "ordinary_halt":
        assert str(caught.value) == "LiveLedgerHalted"
    assert credentials == transports == [] and ledger.snapshot() == before
