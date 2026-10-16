"""Selected full-runner controls; neutral authored paths and intercepted sends.

The actual configured factory, temporary native index/ledger and memory HTTP
runner execute here. These plans are authored controls, never model-quality or
held-out evaluation. No primary ledger/index or real provider is used.
"""

import hashlib
import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from test_core_delivery_http import runtime
from test_evaluation_live import CountedMock
from test_real_index_probe import native_indexes as native_indexes

from agent_app import api
from agent_app.contracts import ProposalHandoff
from agent_app.evaluation import live, runner
from agent_app.orchestration.core_delivery import delivery_recipe
from agent_app.orchestration.handoff import validate_handoff
from agent_app.orchestration.intake import STREAMLIT_VERSION_QUESTION
from agent_app.reasoning.catalog import load_user_gap_vocabulary
from agent_app.testing.http_pilot_runtime import offline_network

ROOT = Path(__file__).resolve().parents[1]
GOLD_CANARY = "NEUTRAL_RUNNER_GOLD_ONLY"
FUTURE_CANARY = "NEUTRAL_FUTURE_CALLBACK"
FUTURE_CODE = "def NEUTRAL_FUTURE_CALLBACK():\n    pass"
SCRIPT_CANARY = "NEUTRAL_SCRIPT_ONLY"


def authored_fixture(folder, identity):
    """Register this neutral graph before constructing its mock provider."""
    folder.mkdir()
    evidence = folder / "neutral-evidence.json"
    raw = json.dumps(
        {"evidence_bundles": {"neutral": {"snapshot_id": "neutral-placeholder", "hits": []}}}
    ).encode()
    evidence.write_bytes(raw)
    definitions = load_user_gap_vocabulary(str(ROOT / "config/user-gap-support-dev-v1.json"))
    callback = next(gap for gap in definitions if gap.name == "parent_callback_code")
    questions = (
        {
            "name": "streamlit_version",
            "kind": "user",
            "question": STREAMLIT_VERSION_QUESTION.question,
            "necessity": "A neutral authored version question registration.",
        },
        callback.model_dump(mode="json"),
    )
    visible = (
        {
            "message": "A selector resets; the parent callback is unavailable.",
            "unknowns": ["parent_callback_code"],
        },
        {"message": "1.50.0", "reply_to_approved_question": True},
        {
            "message": "Here is the current callback as reported text.",
            "reported_facts": [{"name": "parent_callback_code", "value": FUTURE_CODE}],
        },
    )
    ids = ("report", "version", "callback")
    data = {
        "fixture_id": "neutral-selected-runner-" + identity,
        "registered_before_first_run": True,
        "case": {
            "case_id": "neutral-selected-" + identity,
            "split": "dev",
            "family_issue_ids": [],
            "test_eligible": False,
        },
        "evidence_source": {
            "path": evidence.name,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bundles_used": ["neutral"],
        },
        "turns": [
            {
                "id": name,
                "evidence_bundle": "neutral",
                "conversation_source": "neutral authored integration control",
                "visible": event,
                "gold": {
                    "acceptable_decisions": ["ask" if index < 2 else "escalate"],
                    "gaps": [questions[index]] if index < 2 else [],
                    "private_canary": GOLD_CANARY,
                },
                "agent_script": {"unusable_in_live_mode": SCRIPT_CANARY},
                "expect": {},
                "maintainer": {"decision": "approve"},
            }
            for index, (name, event) in enumerate(zip(ids, visible, strict=True))
        ],
        "evaluation": {
            "coverage": {
                "turn_ids": list(ids),
                "routes": [
                    {
                        "from_turn": "report",
                        "to_turn": "version",
                        "guard": {"decision": "ask", "question_target": "streamlit_version"},
                    },
                    {
                        "from_turn": "version",
                        "to_turn": "callback",
                        "guard": {"decision": "ask", "question_target": "parent_callback_code"},
                    },
                    {
                        "from_turn": "callback",
                        "to_turn": None,
                        "guard": {"decision": "escalate"},
                    },
                ],
            }
        },
    }
    path = folder / "neutral-runner.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.mark.parametrize("phase", ("development", "evaluation"))
@pytest.mark.parametrize(
    "scenario", ("valid", "malformed_then_valid", "malformed_twice", "transport_failure")
)
def test_selected_configuration_reaches_complete_runner_receipt(
    tmp_path, native_indexes, monkeypatch, record_testsuite_property, phase, scenario
):
    ledger, values = runtime(tmp_path, native_indexes, monkeypatch)
    values["AGENT_EVAL_PHASE"] = phase
    fixture_root = tmp_path / "authored"
    path = authored_fixture(fixture_root, phase + "-" + scenario)
    original_collect = runner.collect

    def collect_authored(paths, *, mode="offline"):
        # The real loader retains its containment/hash checks inside this
        # temporary fixture namespace. Runtime/source hashing keeps real ROOT.
        with patch.object(runner, "ROOT", fixture_root):
            return original_collect(paths, mode=mode)

    monkeypatch.setattr(runner, "collect", collect_authored)
    wires, transports, engines, index_checks = [], [], [], []
    known_attempts = 0

    def respond(request):
        nonlocal known_attempts
        body = json.loads(request.content)
        current = json.loads(body["messages"][1]["content"])["request"]
        wires.append({"body": body, "request": current})
        known = any(
            fact["name"] == "streamlit_version" and fact["status"] == "active"
            for fact in current["case"]["facts"]
        )
        if known:
            known_attempts += 1
        if known and scenario == "transport_failure":
            raise httpx.ReadTimeout("neutral authored mock timeout", request=request)
        gap = next((item for item in current["gaps"] if item["kind"] == "user"), None)
        plan = {
            "context_sha256": current["context_sha256"],
            "decision": "ask" if gap else "escalate",
            "sources": [],
        }
        if gap:
            plan["question_name"] = gap["name"]
        malformed = known and (
            scenario == "malformed_twice"
            or (scenario == "malformed_then_valid" and known_attempts == 1)
        )
        content = "{not-json" if malformed else json.dumps(plan)
        return httpx.Response(
            200,
            json={
                "model": "gpt-4o-mini-2024-07-18",
                "usage": {"prompt_tokens": 100, "completion_tokens": 40, "total_tokens": 140},
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": content},
                    }
                ],
            },
        )

    def allocate(*args, **kwargs):
        transport = CountedMock(respond)
        transports.append(transport)
        return transport

    original_engine = api.SupportEngine

    def observe_engine(*args, **kwargs):
        actual = original_engine(*args, **kwargs)
        engines.append(
            {
                name: getattr(actual, name)
                for name in (
                    "top_k",
                    "evidence_scope",
                    "retrieval_candidate_multiplier",
                    "evidence_utf8_budget_bytes",
                    "repair_repeated_queries",
                )
            }
        )
        return actual

    monkeypatch.setattr(httpx, "HTTPTransport", allocate)
    monkeypatch.setattr(api, "SupportEngine", observe_engine)
    original_verified_index = live._verified_index

    def observe_index(*args, **kwargs):
        index_checks.append("new_verified_client")
        return original_verified_index(*args, **kwargs)

    monkeypatch.setattr(live, "_verified_index", observe_index)
    with offline_network():
        factory = live.configured_factory(values)
        original_verify = factory._client.verify

        def observe_verify():
            index_checks.append("existing_client_verify")
            return original_verify()

        monkeypatch.setattr(factory._client, "verify", observe_verify)
        try:
            receipt = runner.run([path], mode="live", live=factory, conditional_routes=True)
            assert factory.active_clients == 0
            if scenario == "transport_failure":
                before = ledger.snapshot()
                counts = (
                    len(wires),
                    len(transports),
                    len(values.key_reads),
                    len(factory._observations),
                    len(index_checks),
                )
                with pytest.raises(ValueError, match="^LiveAccountingUnresolved$"):
                    factory.for_case("neutral-after-uncertain")
                with pytest.raises(ValueError, match="^LiveAccountingUnresolved$"):
                    live.configured_factory(values)
                assert counts == (
                    len(wires),
                    len(transports),
                    len(values.key_reads),
                    len(factory._observations),
                    len(index_checks),
                )
                assert ledger.snapshot() == before
        finally:
            factory.close()
    assert all(transport.close_calls == 1 for transport in transports)
    packet = json.loads(json.dumps(receipt))
    assert packet == receipt and packet["quality_claim"] is False
    assert packet["tracker_backend"] == "process_memory_dummy_tracker"
    assert packet["source_unchanged_during_run"] is True
    assert (
        packet["source_sha256"]["src/agent_app/evaluation/runner.py"]
        == hashlib.sha256((ROOT / "src/agent_app/evaluation/runner.py").read_bytes()).hexdigest()
    )
    assert packet["config"] == factory.config and len(packet["config"]) == 7
    case = packet["cases"][0]
    steps = [step for step in case["steps"] if "usage" in step]
    observations = [row for step in steps for row in step["usage"]["provider_observations"]]
    assert all(step["usage"]["provider_observations_error"] is None for step in steps)
    assert len(observations) == len(wires)
    assert all(row["core_binding"] == factory.core_binding for row in observations)
    assert all(row["core_binding"]["observed_metis"]["phase"] == phase for row in observations)
    for row in observations:
        reservation = ledger.get(row["request_id"])
        assert reservation is not None and reservation.phase == phase
        assert reservation.run_id == row["run_id"] and reservation.attempt == row["attempt_index"]
        assert reservation.status == row["ledger_status"]
    expected_engine = {"top_k": 5, **delivery_recipe()["engine_policy"]}
    assert engines and all(engine == expected_engine for engine in engines)
    assert all(GOLD_CANARY not in json.dumps(wire) for wire in wires)
    assert all(SCRIPT_CANARY not in json.dumps(wire) for wire in wires)
    successful = scenario in {"valid", "malformed_then_valid"}
    early_wires = wires[:-1] if successful else wires
    assert all(FUTURE_CANARY not in json.dumps(wire) for wire in early_wires)
    for step in steps:
        if step["proposal"].get("review_handoff"):
            validate_handoff(ProposalHandoff.model_validate(step["proposal"]["review_handoff"]))
    failed_checks = {check["check"] for check in case["checks"] if not check["passed"]}
    if successful:
        assert packet["summary"]["coverage_complete"] and not failed_checks
        assert case["conditional_routes"]["executed_turn_ids"] == ["report", "version", "callback"]
        assert case["conditional_routes"]["unvisited_registered_turn_ids"] == []
        assert [step["proposal"]["decision"] for step in steps] == ["ask", "ask", "escalate"]
        assert len(wires) == (3 if scenario == "valid" else 4) and len(transports) == 3
        assert FUTURE_CANARY in json.dumps(wires[-1])
        if scenario == "valid":
            assert all(row["wire_output"]["canonical_binding_valid"] for row in observations)
        else:
            assert steps[1]["usage"]["model_attempts"] == 2
            assert [row["wire_output"]["canonical_binding_valid"] for row in observations] == [
                True,
                False,
                True,
                True,
            ]
        assert all(row["ledger_status"] == "settled" for row in observations)
        assert Decimal(packet["summary"]["cost_usd_total"]) > 0
        assert ledger.snapshot().uncertain_usd == 0
    else:
        assert not packet["summary"]["coverage_complete"]
        assert case["conditional_routes"]["executed_turn_ids"] == ["report", "version"]
        assert case["conditional_routes"]["unvisited_registered_turn_ids"] == ["callback"]
        assert case["steps"][-1]["runner_stop"] == "FixtureBranchUnavailable"
        assert steps[-1]["proposal"]["proposal_id"] is None and not steps[-1]["released_outputs"]
        assert len(transports) == 2
        if scenario == "malformed_twice":
            assert len(wires) == 3 and steps[-1]["usage"]["model_attempts"] == 2
            assert all(row["ledger_status"] == "settled" for row in observations)
            assert all(not row["wire_output"]["wire_schema_valid"] for row in observations[1:])
            assert Decimal(packet["summary"]["cost_usd_total"]) > 0
            assert ledger.snapshot().uncertain_usd == 0
            assert failed_checks == {"decision is acceptable (gold)", "approve: proposal available"}
        else:
            assert len(wires) == 2 and steps[-1]["usage"]["model_attempts"] == 1
            assert observations[-1]["wire_output"] is None
            assert observations[-1]["ledger_status"] == "uncertain"
            assert packet["summary"]["cost_usd_total"] is None
            assert ledger.snapshot().uncertain_usd > 0
            # A fresh disposable ledger preserves the uncertain hold without
            # auto-flipping its separate halt flag. No next route is selected.
            assert ledger.snapshot().halted is False
            assert failed_checks == {
                "decision is acceptable (gold)",
                "approve: proposal available",
                "model attempt accounting is complete",
            }
    assert ledger.snapshot().reserved_usd == 0
    snapshot = ledger.snapshot()
    assert Decimal(packet["summary"]["settled_usd_total"]) == snapshot.settled_usd
    assert Decimal(packet["summary"]["reserved_usd_total"]) == snapshot.reserved_usd
    assert Decimal(packet["summary"]["uncertain_usd_total"]) == snapshot.uncertain_usd
    if successful or scenario == "malformed_twice":
        assert Decimal(packet["summary"]["cost_usd_total"]) == snapshot.settled_usd
    record_testsuite_property(
        "selected_runner_" + phase + "_" + scenario,
        json.dumps(
            {
                "recipe_sha256": factory.core_binding["recipe_sha256"],
                "binding_sha256": factory.core_binding["binding_sha256"],
                "phase": phase,
                "scenario": scenario,
                "actual_mock_sends": len(wires),
                "projected_provider_rows": len(observations),
                "effective_engine": engines[0],
                "coverage_complete": packet["summary"]["coverage_complete"],
                "cost_usd_total": packet["summary"]["cost_usd_total"],
                "uncertain_usd": str(ledger.snapshot().uncertain_usd),
                "temporary_ledger_halted": ledger.snapshot().halted,
                "next_allocation_and_factory_accounting_block_checked": scenario
                == "transport_failure",
                "script_or_gold_leaked": False,
            },
            sort_keys=True,
        ),
    )
