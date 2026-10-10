"""Join the real gateway and C3 HTTP/core handoff using mandatory mocked HTTP."""

import argparse
import importlib.util
import json
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import httpx

from agent_app.contracts import CaseState, EvidenceBundle, GroundedRequest, ReasoningContext
from agent_app.llm.budget import BudgetLedger
from agent_app.llm.config import MetisConfig
from agent_app.llm.grounded import MetisGroundedPlanner
from agent_app.llm.metis import request_id_for
from agent_app.orchestration import SupportEngine
from agent_app.orchestration.handoff import ReasoningCapture, build_handoff, validate_handoff
from agent_app.reasoning.grounding import GroundedReasoner
from agent_app.testing.fakes import FakeRetriever

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_PATH = Path(__file__).with_name("protocol-gateway-handoff-v1.json")
PROTOCOL_SHA256 = "440ce8b91ec33f15f360be9aebae5cf0cc2bc919e7a2d4f637f9d3c372315d98"
REGISTRATION_COMMIT = "d9c8e82"
SPEC = importlib.util.spec_from_file_location(
    "gateway_handoff_c3", ROOT / "experiments/review_handoff/replay.py"
)
assert SPEC is not None and SPEC.loader is not None
c3 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c3)
CODE_PATHS = tuple(
    sorted(
        {
            *c3.CODE_PATHS,
            "experiments/gateway_handoff/replay.py",
            "experiments/gateway_handoff/protocol-gateway-handoff-v1.json",
            *(
                f"src/agent_app/llm/{name}.py"
                for name in ("budget", "config", "grounded", "metis", "pricing")
            ),
        }
    )
)


def _plain(value):
    return json.loads(
        json.dumps(
            value, default=lambda item: str(item) if isinstance(item, Decimal) else asdict(item)
        )
    )


def load_protocol(path=PROTOCOL_PATH):
    import hashlib

    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != PROTOCOL_SHA256:
        raise ValueError("RegisteredGatewayProtocolMismatch")
    protocol = json.loads(payload)
    for name in ("inherited_fixture", "inherited_exact_output_oracle"):
        item = protocol[name]
        assert hashlib.sha256((ROOT / item["path"]).read_bytes()).hexdigest() == item["sha256"]
    assert protocol["execution_boundary"]["actual_paid_requests"] == 0
    assert protocol["inherited_exact_output_oracle"]["introduced_after_original_C3_first_replay"]
    c3.load_fixture()
    c3.load_expected_analyses()
    return protocol


def code_manifest():
    import hashlib

    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in CODE_PATHS}


class GatewayBridge:
    """Existing planner sends real wire JSON to a fixture-only HTTP transport."""

    def __init__(self, authored, ledger, protocol, attempts, mode="normal"):
        self.authored, self.ledger, self.protocol = authored, ledger, protocol
        self.attempts, self.mode, self.current = attempts, mode, None
        config = protocol["gateway_config"]
        self.gateway = MetisGroundedPlanner(
            MetisConfig(
                api_key="public-synthetic-gateway-handoff-key",
                live_enabled=True,
                max_request_usd=Decimal(config["max_request_usd"]),
                **{
                    name: config[name]
                    for name in (
                        "model",
                        "phase",
                        "response_mode",
                        "input_token_reserve",
                        "max_output_tokens",
                    )
                },
            ),
            ledger,
            transport=httpx.MockTransport(self.respond),
        )

    def respond(self, request):
        # Persist JSON bodies only. Request headers/Authorization are never read
        # or stored; the credential is an explicit public synthetic constant.
        record = self.current
        payload = json.loads(request.content)
        record["provider_payload"] = payload
        record["transport_called"] = True
        reserved = self.ledger.get(record["request_id"])
        assert reserved is not None and reserved.status == "reserved"
        record["reservation_before_response"] = _plain(reserved)
        if self.mode == "timeout":
            raise httpx.ReadTimeout("Fixture timeout", request=request)
        data = json.loads(payload["messages"][1]["content"])
        assert set(data) == {
            "capacity",
            "repair_issue_codes",
            "request",
            "response_schema",
            "source_references",
        }
        prepared = GroundedRequest.model_validate(data["request"])
        assert prepared == self.request and data["response_schema"]["title"] == "GroundedPlan"
        content = self.authored.plan(prepared, context=self.context).model_dump_json()
        if self.mode == "malformed_plan_repair" and self.context.attempt_index == 1:
            content = "{not-plan-json"
        model = (
            "gpt-4.1-mini"
            if self.mode == "model_mismatch"
            else self.protocol["gateway_config"]["returned_model"]
        )
        return httpx.Response(
            200,
            json={
                "model": model,
                "usage": self.protocol["mock_usage"],
                "choices": [
                    {"finish_reason": "stop", "message": {"role": "assistant", "content": content}}
                ],
            },
        )

    def plan(self, request, *, context):
        self.request, self.context = request, context
        record = {
            "request_id": request_id_for(context),
            "context": context.model_dump(mode="json"),
            "transport_called": False,
        }
        self.current = record
        try:
            return self.gateway.plan(request, context=context)
        finally:
            record["reservation_after_attempt"] = _plain(self.ledger.get(record["request_id"]))
            self.attempts.append(record)

    def close(self):
        self.gateway.close()


def _snapshot(ledger, attempts):
    rows = [item["reservation_after_attempt"] for item in attempts]
    assert all(row is not None for row in rows)
    for item, row in zip(attempts, rows, strict=True):
        context = ReasoningContext.model_validate(item["context"])
        assert item["request_id"] == row["request_id"] == request_id_for(context)
        assert (row["run_id"], row["case_id"], row["case_revision"], row["attempt"]) == (
            context.run_id,
            context.case_id,
            context.case_revision,
            context.attempt_index,
        )
    return {
        "transport_calls": sum(item["transport_called"] for item in attempts),
        "settled_reservations": sum(row["status"] == "settled" for row in rows),
        "reserved_reservations": sum(row["status"] == "reserved" for row in rows),
        "uncertain_reservations": sum(row["status"] == "uncertain" for row in rows),
        "ledger": _plain(ledger.snapshot()),
    }


def _control(control, protocol, directory, first_case):
    ledger = BudgetLedger.create(
        directory / (control["id"] + ".sqlite3"),
        limit_usd=Decimal("1"),
        opening_spend_usd=Decimal("0"),
    )
    attempts, prepared = [], []
    fixture = c3.load_fixture()
    case = first_case.model_copy(update={"case_id": "gateway-control:" + control["id"]})
    source = c3.AuthoredPlanner([{"decision": "ask", "question_name": "streamlit_version"}] * 2)
    bridge = GatewayBridge(source, ledger, protocol, attempts, control["id"])

    def factory(current, message, evidence):
        request = c3.catalog(fixture, current, message, evidence)
        prepared.append(request)
        return request

    capture = ReasoningCapture(GroundedReasoner(bridge, request_factory=factory))
    bundle = EvidenceBundle.model_validate(fixture["evidence_bundles"]["official-mixed"])
    try:
        result = SupportEngine(
            FakeRetriever([bundle]), capture, snapshot_id=bundle.snapshot_id
        ).run(
            case,
            fixture["turns"][0]["wire_request"]["message"],
            run_id="gateway-control:" + control["id"],
        )
    finally:
        bridge.close()
    assert bridge.gateway.reasoner.client.is_closed
    assert (
        result.status == control["expected_status"]
        and result.error_code == control["expected_error"]
    )
    assert result.model_attempts == control["expected_model_attempts"]
    accounting = _snapshot(ledger, attempts)
    assert accounting["transport_calls"] == control["expected_transport_calls"]
    assert accounting["settled_reservations"] == control["expected_settled"]
    assert accounting["uncertain_reservations"] == control["expected_uncertain"]
    assert accounting["reserved_reservations"] == 0
    assert accounting["ledger"]["halted"] == control["expected_halted"]
    assert Decimal(accounting["ledger"]["settled_usd"]) == Decimal(
        control["expected_simulated_settled_USD"]
    )
    handoff = None
    if result.analysis is not None:
        assert result.analysis == c3.load_expected_analyses()["handoff-1"]
        handoff = build_handoff(result, capture.last, grounded_request=prepared[-1])
        validate_handoff(handoff)
        assert json.loads(attempts[1]["provider_payload"]["messages"][1]["content"])[
            "repair_issue_codes"
        ] == ["invalid_grounded_plan"]
    return {
        "control_id": control["id"],
        "result": result.model_dump(mode="json"),
        "provider_attempts": attempts,
        "simulated_accounting": accounting,
        "handoff": handoff.model_dump(mode="json") if handoff else None,
        "client_closed": True,
    }


def replay_gateway(path=PROTOCOL_PATH):
    if not __debug__:
        raise RuntimeError("AssertionChecksDisabled")
    protocol = load_protocol(path)
    before = code_manifest()
    attempts, bridges = [], []
    with TemporaryDirectory(prefix="offline-gateway-handoff-") as temporary:
        directory = Path(temporary)
        ledger = BudgetLedger.create(
            directory / "primary.sqlite3",
            limit_usd=Decimal(protocol["gateway_config"]["temporary_ledger_limit_usd"]),
            opening_spend_usd=Decimal("0"),
        )

        class GatewayReasoner(GroundedReasoner):
            def __init__(self, authored, *, request_factory):
                bridge = GatewayBridge(authored, ledger, protocol, attempts)
                bridges.append(bridge)
                super().__init__(bridge, request_factory=request_factory)

        try:
            with patch.object(c3, "GroundedReasoner", GatewayReasoner):
                primary = c3.replay_handoff()
        finally:
            for bridge in bridges:
                bridge.close()
        assert all(bridge.gateway.reasoner.client.is_closed for bridge in bridges)
        accounting = _snapshot(ledger, attempts)
        expected = protocol["expected_primary_accounting"]
        for name in (
            "transport_calls",
            "settled_reservations",
            "reserved_reservations",
            "uncertain_reservations",
        ):
            assert accounting[name] == expected[name]
        assert accounting["ledger"]["halted"] == expected["halted"]
        assert Decimal(accounting["ledger"]["settled_usd"]) == Decimal(
            expected["simulated_settled_USD"]
        )
        assert len({record["request_id"] for record in attempts}) == len(attempts)
        first = CaseState.model_validate(primary["turns"][0]["handoff"]["case"])
        controls = [
            _control(control, protocol, directory, first)
            for control in protocol["registered_controls"]
        ]
    if code_manifest() != before:
        raise RuntimeError("CodeChangedDuringReplay")
    receipt = {
        "receipt_version": 1,
        "result": "passed_registered_gateway_composition_assertions",
        "protocol_sha256": PROTOCOL_SHA256,
        "registration_commit": REGISTRATION_COMMIT,
        "executed_code_sha256": before,
        "code_sha256": c3._digest(before),
        "primary_C3_receipt": primary,
        "primary_provider_attempts": attempts,
        "primary_simulated_accounting": accounting,
        "controls": controls,
        "all_clients_closed": True,
        "runtime": primary["runtime"],
        "summary": {
            "primary_gateway_requests": accounting["transport_calls"],
            "control_gateway_requests": sum(
                item["simulated_accounting"]["transport_calls"] for item in controls
            ),
            "actual_paid_requests": 0,
            "actual_API_cost_USD": "0",
            "real_model_calls": 0,
            "primary_simulated_settled_USD": accounting["ledger"]["settled_usd"],
        },
        "limitations": protocol["limitations"],
    }
    receipt["receipt_sha256"] = c3._digest(receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if not __debug__:
            raise RuntimeError("AssertionChecksDisabled")
        if args.validate:
            load_protocol()
            print(
                json.dumps(
                    {
                        "protocol_sha256": PROTOCOL_SHA256,
                        "scenario_execution": False,
                        "actual_paid_requests": 0,
                    }
                )
            )
            return 0
        receipt = replay_gateway()
        if args.output:
            c3.write_receipt(args.output, receipt)
    except FileExistsError:
        print(json.dumps({"error_code": "OutputExists"}))
        return 2
    except RuntimeError as error:
        code = (
            str(error)
            if str(error) in {"AssertionChecksDisabled", "CodeChangedDuringReplay"}
            else "ReplayUnavailable"
        )
        print(json.dumps({"error_code": code}))
        return 2
    except AssertionError:
        print(json.dumps({"error_code": "RegisteredExpectationMismatch"}))
        return 2
    except Exception:
        print(json.dumps({"error_code": "ReplayUnavailable"}))
        return 2
    print(
        json.dumps(
            {
                "result": receipt["result"],
                "summary": receipt["summary"],
                "receipt_sha256": receipt["receipt_sha256"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
