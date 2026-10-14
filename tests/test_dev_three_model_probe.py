"""Registered model trial wiring with fake provider and disposable accounting."""

import importlib.util
import json
import sys
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from agent_app.contracts import ReasoningContext
from agent_app.evaluation.runner import collect
from agent_app.llm.budget import BudgetLedger
from agent_app.llm.config import MetisConfig
from agent_app.llm.pricing import get_price
from agent_app.reasoning.catalog import load_user_gap_vocabulary
from agent_app.testing.dev_three_model_probe import (
    CAP,
    INPUT_RESERVE,
    MODEL,
    OUTPUT_LIMIT,
    ScopedPlanner,
    ledger_observation,
    request_slots,
    run_trial,
)
from agent_app.testing.http_pilot_runtime import offline_network

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / "data/evaluation/dev-three-v1"


def preparation(tmp_path):
    ledger = BudgetLedger.create(
        tmp_path / "budget.sqlite3", limit_usd=Decimal("4.5"), opening_spend_usd=Decimal("0")
    )
    ledger.reserve(
        request_id="quarantined",
        run_id="old-run",
        case_id="old-case",
        case_revision=0,
        attempt=1,
        model="gpt-4.1-mini",
        phase="development",
        amount_usd=Decimal("0.02"),
    )
    ledger.mark_uncertain("quarantined", error_code="ProviderModelMismatch")
    ledger.halt()
    ledger.authorize_continuation(
        authorization_id="old-grant",
        authorization_ref="old-user-authorization",
        expected_request_id="quarantined",
        held_usd=Decimal("0.02"),
        additional_cap_usd=Decimal("0.01"),
    )
    protocol = {
        "experiment_id": "synthetic-dev-three-v1",
        "scope_id": "synthetic-scope",
        "protocol_id": "dev-three-controlled-model-v1",
    }
    paths = [
        PACKET / "cases" / name
        for name in ("pilot-12782-v1.json", "icon-9770-v1.json", "enum-8129-v1.json")
    ]
    fixtures = collect(paths, mode="live")
    definitions = load_user_gap_vocabulary(str(PACKET / "user-gap-vocabulary-v1.json"))
    before = ledger_observation(ledger._path)
    slots = request_slots(protocol, fixtures)
    ledger.authorize_experiment_scope(
        authorization_id=protocol["scope_id"],
        authorization_ref="synthetic-user-authorization",
        parent_authorization_id="old-grant",
        protocol_sha256="a" * 64,
        request_slots=slots,
        additional_cap_usd=CAP,
    )
    config = MetisConfig(
        api_key="synthetic-noncredential",
        live_enabled=True,
        model=MODEL,
        phase="development",
        response_mode="grounded_plan",
        continuation_id=protocol["scope_id"],
        input_token_reserve=INPUT_RESERVE,
        max_output_tokens=OUTPUT_LIMIT,
        max_request_usd=get_price(MODEL).cost(INPUT_RESERVE, OUTPUT_LIMIT),
    )
    return protocol, fixtures, definitions, ledger, config, before


def response(request, payloads):
    wire = json.loads(request.content)
    payload = json.loads(wire["messages"][1]["content"])
    payloads.append(payload)
    actual = payload["request"]
    user_gaps = [gap for gap in actual["gaps"] if gap["kind"] == "user"]
    refs = payload["source_references"]
    if user_gaps:
        question = next(
            (gap for gap in user_gaps if gap["name"] == "streamlit_version"), user_gaps[0]
        )
        plan = {
            "context_sha256": actual["context_sha256"],
            "decision": "ask",
            "question_name": question["name"],
        }
    elif actual["case"]["case_id"] == "dev-case-b":
        plan = {"context_sha256": actual["context_sha256"], "decision": "answer", "sources": refs}
    else:
        plan = {"context_sha256": actual["context_sha256"], "decision": "escalate", "sources": refs}
    return httpx.Response(
        200,
        json={
            "model": "gpt-4o-mini-2024-07-18",
            "choices": [
                {
                    "message": {"role": "assistant", "content": json.dumps(plan)},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 1000, "completion_tokens": 180, "total_tokens": 1180},
        },
    )


def test_registered_trial_consumes_exact_slots_and_keeps_real_cost_and_old_halt(tmp_path):
    protocol, fixtures, definitions, ledger, config, before = preparation(tmp_path)
    payloads = []
    with offline_network():
        receipt = run_trial(
            protocol,
            fixtures,
            definitions,
            ledger,
            config,
            before,
            underlying=httpx.MockTransport(lambda request: response(request, payloads)),
        )
    assert receipt["actual_sends"] == 12
    assert receipt["completed_case_arm_runs"] == 6 and not receipt["stopped_early"]
    assert all(check["passed"] for case in receipt["cases"] for check in case["checks"])
    assert receipt["accounting"]["accounting_complete"] is True
    assert Decimal(receipt["accounting"]["cost_usd"]) > 0
    assert len(receipt["accounting"]["requests"]) == 12
    assert receipt["original_accounting_preserved"] is True
    assert ledger.snapshot().halted and ledger.snapshot().uncertain_usd == Decimal("0.02")
    assert ledger.continuation_status("old-grant").used_usd == 0
    assert ledger.experiment_scope_status(protocol["scope_id"]).consumed_requests == 12
    assert receipt["quality_claim"] is False and receipt["actual_rag_quality"] is False
    assert receipt["human_usefulness"] is None
    enum = [case for case in receipt["cases"] if case["case_id"] == "dev-case-c"]
    assert all(
        any(
            check["check"] == "live stale unexecuted approval rejected" and check["passed"]
            for check in case["checks"]
        )
        for case in enum
    )
    assert all(
        record["verified_returned_model"] == "gpt-4o-mini-2024-07-18"
        for record in receipt["provider_sends"]
    )
    # Evidence and exposed current facts are equal; only the registered vocabulary differs.
    a, b = payloads[1]["request"], payloads[7]["request"]
    assert a["case"] == b["case"] and a["evidence"] == b["evidence"]
    assert not any(gap["kind"] == "user" for gap in a["gaps"])
    assert any(gap["name"] == "parent_callback_code" for gap in b["gaps"])
    assert "1.31.1" not in json.dumps(payloads[4]["request"]["case"]["facts"])
    for payload in payloads:
        assert set(payload["request"]) == {
            "case",
            "user_message",
            "evidence",
            "gaps",
            "conflict_groups",
            "context_sha256",
        }
        assert "gold" not in payload and "agent_script" not in payload
    ledger.close_experiment_scope(protocol["scope_id"])
    assert ledger.experiment_scope_status(protocol["scope_id"]).block_reason == "ExperimentClosed"


def test_oversized_context_is_recorded_as_zero_wire_unfunded_attempt(tmp_path):
    protocol, fixtures, definitions, ledger, config, before = preparation(tmp_path)
    from agent_app.contracts import CaseState, EvidenceBundle
    from agent_app.llm.grounded import MetisGroundedPlanner
    from agent_app.orchestration.ports import ReasoningStopped
    from agent_app.reasoning.grounding import make_grounded_request
    from agent_app.testing.dev_three_model_probe import ScopeTransport, SharedTransport

    counted = ScopeTransport(
        httpx.MockTransport(lambda request: pytest.fail("No send permitted")),
        ledger,
        protocol["scope_id"],
        before,
    )
    gateway = MetisGroundedPlanner(config, ledger, transport=SharedTransport(counted))
    records = []
    planner = ScopedPlanner(gateway, counted, records)
    request = make_grounded_request(
        CaseState(case_id="dev-case-a"), "x" * 18000, EvidenceBundle(snapshot_id="synthetic")
    )
    context = ReasoningContext(
        run_id="unlisted-run", case_id="dev-case-a", case_revision=0, attempt_index=1
    )
    with pytest.raises(ReasoningStopped) as failed:
        planner.plan(request, context=context)
    assert failed.value.code == "ContextLimitExceeded"
    assert len(records) == 1 and records[0]["error_code"] == "ContextLimitExceeded"
    assert records[0]["context"] == context.model_dump(mode="json")
    assert (
        counted.records == []
        and ledger.experiment_scope_status(protocol["scope_id"]).consumed_requests == 0
    )
    gateway.close()
    counted.close()


def test_provider_echo_of_escaped_credential_is_terminal_and_never_recorded(tmp_path):
    protocol, fixtures, definitions, ledger, config, before = preparation(tmp_path)
    secret = 'synthetic-key"\\private-credential-echo'
    config = MetisConfig.model_validate({**config.model_dump(), "api_key": secret})

    def malicious(request):
        payload = json.loads(json.loads(request.content)["messages"][1]["content"])
        plan = {
            "context_sha256": payload["request"]["context_sha256"],
            "decision": "ask",
            "question_name": secret,
        }
        return httpx.Response(
            200,
            json={
                "model": "gpt-4o-mini-2024-07-18",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": json.dumps(plan)},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1000, "completion_tokens": 180, "total_tokens": 1180},
            },
        )

    receipt = run_trial(
        protocol,
        fixtures,
        definitions,
        ledger,
        config,
        before,
        underlying=httpx.MockTransport(malicious),
    )
    assert receipt["actual_sends"] == 1 and receipt["stopped_early"]
    assert receipt["attempts"][0]["credential_echo_rejected"] is True
    assert receipt["attempts"][0]["plan"] is None
    assert secret not in json.dumps(receipt)
    assert json.dumps(secret)[1:-1] not in json.dumps(receipt)
    assert receipt["accounting"]["accounting_complete"] is True


def cli_module():
    spec = importlib.util.spec_from_file_location(
        "dev_three_cli_unit", ROOT / "scripts/dev_three_model_probe.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("surface", ["key", "value", "list"])
def test_private_writer_rejects_raw_and_json_escaped_credentials_before_creation(tmp_path, surface):
    module = cli_module()
    secret = 'synthetic-secret"\\writer-token'
    values = {
        "key": {secret: "x"},
        "value": {"text": "prefix:" + secret},
        "list": {"items": [secret]},
    }
    path = tmp_path / "never-created.json"
    with pytest.raises(ValueError):
        module.write_new(path, values[surface], secret=secret)
    assert not path.exists()


def test_authorization_journal_failure_closes_scope_and_never_exports_exception(
    tmp_path, monkeypatch, capsys
):
    protocol, fixtures, definitions, ledger, config, _before = preparation(tmp_path)
    protocol = {
        **protocol,
        "authorization_ref": "synthetic-user-authorization",
        "parent_authorization_id": "old-grant",
    }
    source = {"source_commit": "synthetic-source", "source_clean": True, "source_hashes": {}}
    registration = {
        **source,
        "protocol_sha256": "a" * 64,
        "request_slots_sha256": "b" * 64,
        "ledger_before": ledger_observation(ledger._path),
    }
    module = cli_module()
    monkeypatch.setattr(
        module,
        "preflight",
        lambda *args: (
            protocol,
            fixtures,
            definitions,
            request_slots(protocol, fixtures),
            registration,
        ),
    )
    monkeypatch.setattr(module, "source_observation", lambda root: source)
    monkeypatch.setattr(module, "credential", lambda path: config.api_key.get_secret_value())
    original_write = module.write_new

    def fail_authorization(path, value, **kwargs):
        if path.name == "authorization.json":
            raise OSError("synthetic-private-io-marker")
        return original_write(path, value, **kwargs)

    monkeypatch.setattr(module, "write_new", fail_authorization)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "dev-three",
            "--live",
            "--ledger",
            str(ledger._path),
            "--env-file",
            str(tmp_path / "unused.env"),
            "--output-dir",
            str(tmp_path / "live"),
        ],
    )
    assert module.main() == 1
    assert ledger.experiment_scope_status(protocol["scope_id"]).block_reason == "ExperimentClosed"
    assert "synthetic-private-io-marker" not in capsys.readouterr().out
    assert (tmp_path / "live/scope-closed.json").is_file()
