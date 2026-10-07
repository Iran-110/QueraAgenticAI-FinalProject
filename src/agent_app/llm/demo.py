"""Exercise the real gateway with synthetic HTTP responses and a temporary ledger."""

from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
from pydantic import SecretStr

from agent_app.contracts import CaseState
from agent_app.demo import SNAPSHOT_ID, _ask, _evidence
from agent_app.llm.budget import BudgetLedger
from agent_app.llm.config import MetisConfig
from agent_app.llm.metis import MetisReasoner
from agent_app.orchestration import SupportEngine
from agent_app.testing.fakes import FakeRetriever


def run_gateway_demo(scenario: str) -> dict:
    if scenario not in {"success", "repair", "timeout", "budget"}:
        raise ValueError("Unknown gateway demonstration scenario")
    sends = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal sends
        sends += 1
        if scenario == "timeout":
            raise httpx.ReadTimeout("Synthetic provider timeout", request=request)
        content = (
            "invalid JSON" if scenario == "repair" and sends == 1 else _ask().model_dump_json()
        )
        return httpx.Response(
            200,
            json={
                "model": "gpt-4o-mini-2024-07-18",
                "usage": {"prompt_tokens": 500, "completion_tokens": 100, "total_tokens": 600},
                "choices": [
                    {"finish_reason": "stop", "message": {"role": "assistant", "content": content}}
                ],
            },
        )

    with TemporaryDirectory(prefix="agent-gateway-demo-") as directory:
        opening = Decimal("4.999") if scenario == "budget" else Decimal("0")
        ledger = BudgetLedger.create(
            Path(directory) / "synthetic.sqlite3", limit_usd=Decimal("5"), opening_spend_usd=opening
        )
        config = MetisConfig(api_key=SecretStr("synthetic-unused-key"), live_enabled=True)
        with MetisReasoner(config, ledger, transport=httpx.MockTransport(respond)) as reasoner:
            retriever = FakeRetriever([_evidence("demo-initial", "Synthetic session evidence.")])
            result = SupportEngine(retriever, reasoner, snapshot_id=SNAPSHOT_ID).run(
                CaseState(case_id="synthetic-gateway-case", case_revision=1),
                "My widget loses its value. What should I check?",
                run_id=f"synthetic-gateway-{scenario}",
            )
        snapshot = ledger.snapshot()
        return {
            "mode": "synthetic_http",
            "scenario": scenario,
            "real_api_calls": 0,
            "paid_cost_usd": 0,
            "mock_http_requests": sends,
            "simulated_usage_cost_usd": str(snapshot.settled_usd),
            "simulated_ledger": {
                key: str(value) if isinstance(value, Decimal) else value
                for key, value in asdict(snapshot).items()
            },
            "result": result.model_dump(mode="json"),
        }
