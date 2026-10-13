"""Actual local query retrieval; temporary budgets and mandatory mocked provider."""

import gzip
import json
import sqlite3
import sys
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from test_evaluation_live import index as index
from test_evaluation_live import provider_response

from agent_app.contracts import CaseState, ConversationEntry, Fact, TurnConversation
from agent_app.llm.budget import BudgetLedger
from agent_app.llm.config import MetisConfig
from agent_app.orchestration.ports import ReasoningStopped
from agent_app.testing import retrieval_context_live_probe as probe
from agent_app.testing.http_pilot_runtime import offline_network

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def ledger(tmp_path):
    root = tmp_path / "root"
    (root / "runtime").mkdir(parents=True)
    path = root / "runtime/budget.sqlite3"
    ledger = BudgetLedger.create(path, limit_usd=Decimal("4.5"), opening_spend_usd=Decimal("0"))
    ledger.reserve(
        request_id="call:old-quarantine",
        run_id="run:old",
        case_id="case:old",
        case_revision=1,
        attempt=1,
        model="gpt-4.1-mini",
        phase="development",
        amount_usd=Decimal("0.008"),
    )
    ledger.mark_uncertain("call:old-quarantine", error_code="ProviderModelMismatch")
    ledger.halt()
    ledger.authorize_continuation(
        authorization_id=probe.GRANT,
        authorization_ref="test:explicit-online-query-comparison",
        expected_request_id="call:old-quarantine",
        held_usd=Decimal("0.02"),
        additional_cap_usd=Decimal("0.1"),
    )
    return path, ledger


def fixture():
    old = "Streamlit 1.50.0 and Python 3.12.9. My multiselect in @st.fragment loses its saved default after the parent selector resets Session State. A working reduction does not reproduce this failure."
    current = "Correction: Streamlit is 1.49.0. The environment changed; Python is unknown. The parent callback is still missing."
    facts = tuple(
        Fact(name=name, value=value, source_ref="user:first", turn_id="first", status="superseded")
        for name, value in (("streamlit_version", "1.50.0"), ("python_version", "3.12.9"))
    ) + (
        Fact(
            name="streamlit_version", value="1.49.0", source_ref="user:current", turn_id="current"
        ),
    )
    case = CaseState(
        case_id="query-exposed-development",
        case_revision=2,
        facts=facts,
        unknowns=("python_version", "parent_callback_code", "minimal_failing_reproduction"),
    )
    conversation = TurnConversation(
        entries=(
            ConversationEntry(actor="user", reference_id="first", revision=1, text=old),
            ConversationEntry(actor="user", reference_id="current", revision=2, text=current),
        ),
        latest_turn_id="current",
        committed_revision=2,
        latest_message=current,
    )
    return {
        "case": case.model_dump(mode="json"),
        "conversation": conversation.model_dump(mode="json"),
    }


def protocol(index, ledger):
    before = probe.ledger_observation(ledger[0])
    gaps = json.loads(
        (ROOT / "experiments/grounded_http_acceptance/connected-live-protocol-v1.json").read_bytes()
    )["policy_registered_before_provider"]["development_user_gap_definitions"]
    return {
        "protocol_id": "retrieval-context-live-comparison-v1",
        "experiment_id": "test-query-context-comparison",
        "continuation_id": probe.GRANT,
        "fixture": {
            "path": "experiments/retrieval_context/case-v1.json",
            "sha256": probe._sha(json.dumps(fixture()).encode()),
        },
        "ledger": {
            "path": "runtime/budget.sqlite3",
            "sha256_before": before["fingerprints"]["db"],
            "unknown_records_sha256": before["unknown_records_sha256"],
        },
        "index": {
            "path": str(index[0]),
            "snapshot_id": index[1],
            "manifest_sha256": index[2],
            "top_k": 1,
        },
        "gateway": {
            "model": probe.MODEL,
            "phase": "development",
            "input_token_reserve": probe.INPUT_RESERVE,
            "max_output_tokens": probe.OUTPUT_LIMIT,
            "max_request_usd": str(probe.REQUEST_BOUND),
            "batch_max_reserved_usd": str(probe.BATCH_BOUND),
            "max_actual_sends_including_repair": probe.MAX_SENDS,
        },
        "user_gap_definitions": gaps,
    }


def config():
    return MetisConfig(
        api_key="public-synthetic-query-probe-key",
        live_enabled=True,
        model=probe.MODEL,
        phase="development",
        response_mode="grounded_plan",
        continuation_id=probe.GRANT,
        input_token_reserve=probe.INPUT_RESERVE,
        max_output_tokens=probe.OUTPUT_LIMIT,
        max_request_usd=probe.REQUEST_BOUND,
    )


def execute(index, ledger, respond):
    registration = protocol(index, ledger)
    with offline_network():
        prepared = probe.prepare_inputs(registration, fixture())
        receipt = probe.execute(
            registration,
            prepared,
            ledger_path=ledger[0],
            config=config(),
            before=probe.ledger_observation(ledger[0]),
            underlying=httpx.MockTransport(respond),
        )
    return receipt, prepared


def test_read_only_prepare_uses_two_real_queries_same_authoritative_inputs_before_provider(
    index, ledger
):
    before = ledger[0].read_bytes()
    data = fixture()
    with offline_network():
        prepared = probe.prepare_inputs(protocol(index, ledger), data)
    assert ledger[0].read_bytes() == before
    legacy, current = prepared["arms"]["legacy"], prepared["arms"]["current"]
    assert "1.50.0" in legacy["query"] and "3.12.9" in legacy["query"]
    assert "streamlit_version=1.49.0" in current["query"]
    assert "1.50.0" not in current["query"] and "3.12.9" not in current["query"]
    assert legacy["query"] != current["query"]
    assert legacy["request"].case == current["request"].case
    assert legacy["request"].user_message == current["request"].user_message
    assert "1.50.0" in prepared["message"] and "3.12.9" in prepared["message"]
    assert all(
        arm["prompt_bytes_plus_margin"] <= probe.INPUT_RESERVE for arm in prepared["arms"].values()
    )
    assert all(
        arm["evidence"].queries_used == (arm["query"],) and arm["evidence"].hits
        for arm in prepared["arms"].values()
    )
    assert data == fixture()


def test_two_send_live_shape_is_bounded_and_proposals_remain_unstaged(index, ledger):
    seen = []

    def respond(request):
        body = json.loads(request.content)
        assert body["max_tokens"] == 384 and body["model"] == "gpt-4o-mini"
        seen.append(json.loads(body["messages"][1]["content"])["request"])
        return provider_response(request)

    receipt, prepared = execute(index, ledger, respond)
    assert receipt["actual_sends"] == len(seen) == 2
    assert receipt["accepted_operations"] is True and receipt["comparison_complete"] is True
    assert all(receipt["checks"].values())
    assert receipt["tracker_actions"] == 0 and receipt["tracker_staging"] is False
    assert receipt["proposal_auto_approved"] is False
    assert seen[0]["case"] == seen[1]["case"]
    assert seen[0]["user_message"] == seen[1]["user_message"] == prepared["message"]
    assert [arm["result"]["model_attempts"] for arm in receipt["arms"]] == [1, 1]
    assert [arm["result"]["retrieval_rounds"] for arm in receipt["arms"]] == [1, 1]
    assert len({item["run_id"] for item in receipt["provider_observations"]}) == 2
    assert all(
        item["verified_returned_model"] == "gpt-4o-mini-2024-07-18"
        and item["reservation"]["status"] == "settled"
        for item in receipt["provider_observations"]
    )
    assert Decimal(receipt["new_cost_estimated_usd"]) == Decimal("0.000140250")
    assert receipt["ledger_after"]["halted"] and receipt["ledger_after"]["uncertain_usd"] == "0.02"
    assert receipt["actual_account_charge_usd"] is None and receipt["quality_claim"] is False
    serialized = json.dumps(receipt)
    assert (
        "public-synthetic-query-probe-key" not in serialized and "Authorization" not in serialized
    )
    assert "provider_payload" not in serialized


def test_malformed_baseline_is_not_repaired_and_comparison_reports_incomplete(index, ledger):
    seen = []

    def respond(request):
        seen.append(1)
        return provider_response(request, malformed=len(seen) == 1)

    receipt, _prepared = execute(index, ledger, respond)
    assert receipt["actual_sends"] == len(seen) == 2
    assert receipt["comparison_complete"] is False and receipt["accepted_operations"] is False
    assert receipt["arms"][0]["canonical_handoff"] is None
    assert receipt["arms"][1]["canonical_handoff"] is not None
    assert all(arm["result"]["model_attempts"] == 1 for arm in receipt["arms"])


@pytest.mark.parametrize("fault", ["timeout", "model_mismatch", "truncated_output"])
def test_terminal_provider_fault_stops_before_second_arm_and_keeps_old_incident(
    index, ledger, fault
):
    original = ledger[1].get("call:old-quarantine")
    seen = []

    def respond(request):
        seen.append(1)
        if fault == "timeout":
            raise httpx.ReadTimeout("private-transport-failure", request=request)
        response = provider_response(
            request,
            model="unverified-private-model"
            if fault == "model_mismatch"
            else "gpt-4o-mini-2024-07-18",
        )
        if fault == "truncated_output":
            body = response.json()
            body["choices"][0]["finish_reason"] = "length"
            return httpx.Response(200, json=body)
        return response

    receipt, _prepared = execute(index, ledger, respond)
    assert receipt["actual_sends"] == len(seen) == 1
    assert receipt["comparison_complete"] is False
    assert len(receipt["arms"]) == 1
    assert ledger[1].get("call:old-quarantine") == original
    assert receipt["checks"]["original_quarantine_preserved"] is True
    if fault in {"timeout", "model_mismatch"}:
        assert receipt["new_cost_estimated_usd"] is None
        assert receipt["new_settled_estimated_usd"] == "0"
        assert Decimal(receipt["new_uncertain_usd"]) == probe.REQUEST_BOUND
        assert receipt["new_reserved_usd"] == "0"
        assert receipt["new_request_accounting_complete"] is False
        assert receipt["unaccounted_request_ids"] == [
            receipt["provider_observations"][0]["request_id"]
        ]
        assert receipt["ledger_settled_delta_estimated_usd"] == "0"
    assert "private-transport-failure" not in json.dumps(
        receipt
    ) and "unverified-private-model" not in json.dumps(receipt)


def test_gzip_serving_model_decodes_exactly_once(index, ledger):
    def respond(request):
        data = gzip.compress(provider_response(request).content)
        return httpx.Response(
            200,
            headers={
                "Content-Encoding": "gzip",
                "Content-Length": str(len(data)),
                "private-header": "private-content",
            },
            content=data,
        )

    receipt, _prepared = execute(index, ledger, respond)
    assert receipt["accepted_operations"] is True
    assert all(
        row["verified_returned_model"] == "gpt-4o-mini-2024-07-18"
        for row in receipt["provider_observations"]
    )
    assert "private-header" not in json.dumps(receipt) and "private-content" not in json.dumps(
        receipt
    )


def test_transport_cannot_delegate_a_third_send_or_mutate_ledger(ledger):
    before = probe.ledger_observation(ledger[0])
    transport = probe._ScopedTransport(
        httpx.MockTransport(lambda _: (_ for _ in ()).throw(AssertionError("Third send"))),
        ledger[1],
        before,
    )
    transport.records = [{"request_id": "old:1"}, {"request_id": "old:2"}]
    with pytest.raises(ReasoningStopped):
        transport.guard()
    assert probe.ledger_observation(ledger[0]) == before
    transport.close()


@pytest.mark.parametrize(
    "mutation",
    [
        "UPDATE ledger_meta SET limit_nanos=5000000000",
        "UPDATE ledger_meta SET opening_nanos=1",
        "UPDATE ledger_continuations SET authorization_ref='test:changed'",
        "UPDATE ledger_continuations SET cap_nanos=101000000",
        "UPDATE ledger_continuations SET held_nanos=30000000",
    ],
)
def test_scope_guard_rejects_immutable_budget_or_grant_drift_without_send(ledger, mutation):
    before = probe.ledger_observation(ledger[0])
    with sqlite3.connect(ledger[0]) as connection:
        connection.execute(mutation)
    mutated = probe.ledger_observation(ledger[0])
    transport = probe._ScopedTransport(
        httpx.MockTransport(lambda _: (_ for _ in ()).throw(AssertionError("No send"))),
        ledger[1],
        before,
    )
    with pytest.raises(ReasoningStopped):
        transport.guard()
    assert transport.records == []
    assert probe.ledger_observation(ledger[0]) == mutated
    transport.close()


def test_transport_rechecks_immutable_scope_after_reservation_before_send(ledger):
    before = probe.ledger_observation(ledger[0])
    ledger[1].reserve(
        request_id="call:prepared-before-drift",
        run_id="run:prepared",
        case_id="case:prepared",
        case_revision=2,
        attempt=1,
        model=probe.MODEL,
        phase="development",
        amount_usd=probe.REQUEST_BOUND,
        continuation_id=probe.GRANT,
    )
    with sqlite3.connect(ledger[0]) as connection:
        connection.execute("UPDATE ledger_continuations SET cap_nanos=101000000")
    mutated = probe.ledger_observation(ledger[0])
    transport = probe._ScopedTransport(
        httpx.MockTransport(lambda _: (_ for _ in ()).throw(AssertionError("No send"))),
        ledger[1],
        before,
    )
    transport.current = {"request_id": "call:prepared-before-drift"}
    with pytest.raises(ReasoningStopped):
        transport.handle_request(httpx.Request("POST", probe.METIS_CHAT_URL))
    assert transport.records == []
    assert probe.ledger_observation(ledger[0]) == mutated
    transport.close()


def test_unsent_attempt_hold_is_accounted_when_scope_drifts_after_reservation(
    index, ledger, monkeypatch
):
    handle = probe._ScopedTransport.handle_request

    def drift_then_guard(transport, request):
        with sqlite3.connect(ledger[0]) as connection:
            connection.execute("UPDATE ledger_continuations SET cap_nanos=101000000")
        return handle(transport, request)

    monkeypatch.setattr(probe._ScopedTransport, "handle_request", drift_then_guard)
    receipt, _prepared = execute(
        index, ledger, lambda _: (_ for _ in ()).throw(AssertionError("No provider send"))
    )
    assert receipt["actual_sends"] == 0
    assert receipt["accepted_operations"] is False
    assert len(receipt["model_request_observations"]) == 1
    attempt = receipt["model_request_observations"][0]
    assert attempt["http_send_started"] is False
    assert attempt["reservation"]["status"] == "uncertain"
    assert receipt["new_cost_estimated_usd"] is None
    assert Decimal(receipt["new_uncertain_usd"]) == probe.REQUEST_BOUND
    assert receipt["unaccounted_request_ids"] == [attempt["request_id"]]


def test_full_raw_prompt_must_fit_before_model_or_credentials(index, ledger):
    data = fixture()
    text = data["conversation"]["latest_message"] + " callback " * 1700
    data["conversation"]["latest_message"] = text
    data["conversation"]["entries"][-1]["text"] = text
    before = ledger[0].read_bytes()
    with offline_network(), pytest.raises(probe.ProbeRejected):
        probe.prepare_inputs(protocol(index, ledger), data)
    assert ledger[0].read_bytes() == before


def test_unknown_or_mismatched_new_request_accounting_cannot_report_zero_paid_cost():
    record = {
        "request_id": "call:sent",
        "run_id": "run:sent",
        "case_id": "case:sent",
        "case_revision": 2,
        "attempt_index": 1,
        "reservation": None,
    }
    summary = probe._new_request_accounting([record])
    assert summary["new_cost_estimated_usd"] is None
    assert summary["new_request_accounting_complete"] is False
    assert summary["unaccounted_request_ids"] == ["call:sent"]
    record["reservation"] = {
        "request_id": "call:different",
        "run_id": "run:sent",
        "case_id": "case:sent",
        "case_revision": 2,
        "attempt": 1,
        "model": probe.MODEL,
        "phase": "development",
        "status": "settled",
        "cost_usd": "0",
    }
    assert probe._new_request_accounting([record])["new_cost_estimated_usd"] is None


@pytest.mark.parametrize("field", ["case_revision", "raw_message", "hidden_gold", "expected_query"])
def test_preflight_rejects_inconsistent_or_hidden_input_before_model(index, ledger, field):
    data, registered = fixture(), protocol(index, ledger)
    if field == "case_revision":
        data["case"]["case_revision"] = 3
    elif field == "raw_message":
        data["user_message"] = "golden answer must enter provider"
    elif field == "hidden_gold":
        data["gold"] = {"decision": "answer"}
    else:
        registered["expected_queries"] = {"legacy": "wrong", "current": "wrong"}
    before = ledger[0].read_bytes()
    with offline_network(), pytest.raises(probe.ProbeRejected):
        probe.prepare_inputs(registered, data)
    assert ledger[0].read_bytes() == before


def test_default_cli_dryruns_both_arms_without_key_or_transport(index, ledger, monkeypatch, capsys):
    registered, data = protocol(index, ledger), fixture()
    before = probe.ledger_observation(ledger[0])
    monkeypatch.setattr(
        probe, "load_registration", lambda *_args: (registered, data, {"ledger_before": before})
    )
    monkeypatch.setattr(
        sys, "argv", ["query-probe", "--ledger", str(ledger[0]), "--env-file", "never-read.env"]
    )
    monkeypatch.setattr(
        probe, "_credential", lambda *_: (_ for _ in ()).throw(AssertionError("No key"))
    )
    monkeypatch.setattr(
        httpx.HTTPTransport,
        "__init__",
        lambda *_args, **_kw: (_ for _ in ()).throw(AssertionError("No provider")),
    )
    with offline_network():
        probe.main()
    assert json.loads(capsys.readouterr().out)["both_prompts_fit"] is True
    assert probe.ledger_observation(ledger[0]) == before


def test_registration_requires_immutable_current_ledger_and_pushed_source(
    index, ledger, monkeypatch
):
    root = ledger[0].parents[1]
    registered = protocol(index, ledger)
    destination = root / probe.PROTOCOL
    destination.parent.mkdir(parents=True)
    fixture_path = root / registered["fixture"]["path"]
    fixture_path.write_text(json.dumps(fixture()), encoding="utf-8")
    destination.write_text(json.dumps(registered), encoding="utf-8")
    source = {
        "source_commit": "pushed",
        "upstream_commit": "pushed",
        "source_clean": True,
        "source_pushed": True,
        "source_hashes": {},
    }
    monkeypatch.setattr(probe, "source_observation", lambda *_args: source)
    _protocol, _fixture, registration = probe.load_registration(root, ledger[0])
    assert (
        registration["ledger_before"]["fingerprints"]["db"] == registered["ledger"]["sha256_before"]
    )
    source["source_pushed"] = False
    with pytest.raises(probe.ProbeRejected):
        probe.load_registration(root, ledger[0])
    source["source_pushed"] = True
    changed = deepcopy(registered)
    changed["ledger"]["sha256_before"] = "0" * 64
    destination.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(probe.ProbeRejected):
        probe.load_registration(root, ledger[0])
