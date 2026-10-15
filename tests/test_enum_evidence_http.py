"""Fixed source availability through the actual HTTP/gateway/approval path."""

import hashlib
import json
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from test_budget_quarantine_scope import multiple_holds as multiple_holds

from agent_app.llm.config import MetisConfig
from agent_app.llm.pricing import get_price
from agent_app.reasoning.catalog import load_user_gap_vocabulary
from agent_app.testing.dev_three_model_probe import DevProbeRejected, ledger_observation
from agent_app.testing.enum_evidence import (
    PACKET_PATH,
    fixture_retriever_factory,
    load_source_packet,
)
from agent_app.testing.http_pilot_runtime import offline_network
from agent_app.testing.quality_probe import quality_slots, run_quality_batch
from agent_app.testing.stability_probe import VOCABULARY, fixtures_for

ROOT = Path(__file__).resolve().parents[1]


def prepared(multiple_holds, case_id):
    ledger = multiple_holds[0]
    fixtures = fixtures_for(ROOT, {"protocol_id": "core-stability-v1"})
    protocol = {"experiment_id": "synthetic-enum-evidence-wire"}
    batch = {
        "batch_id": "synthetic-enum-pair",
        "kind": "controlled_evidence",
        "scope_id": "synthetic-enum-evidence-scope",
        "jobs": [
            {
                "job_id": f"{case_id}:{arm}",
                "case_id": case_id,
                "arm": arm,
                "round": 1,
                "max_output_tokens": 1024,
                "input_token_reserve": 32768,
                "grounded_json_object": True,
                "compact_plan": True,
                "source_capacity": True,
                "source_selection_reminder": True,
                "concise_user_draft": True,
                "ask_source_background": True,
            }
            for arm in ("fixed_baseline", "fixed_guide_added")
        ],
    }
    observed = asdict(ledger.quarantine_observation())
    ledger.authorize_quarantine_scope(
        authorization_id=batch["scope_id"],
        authorization_ref="synthetic-enum-test",
        expected_unknown_ids=observed["unknown_ids"],
        expected_unknown_fingerprints=observed["unknown_fingerprints"],
        expected_meta_sha256=observed["meta_sha256"],
        expected_authorization_history_sha256=observed["authorization_history_sha256"],
        protocol_sha256=hashlib.sha256(b"synthetic-enum-evidence-wire-v1").hexdigest(),
        request_slots=quality_slots(protocol, batch, fixtures),
        additional_cap_usd=Decimal("0.06"),
        allow_full_context=True,
    )
    config = MetisConfig(
        api_key="public-synthetic-enum-key",
        live_enabled=True,
        response_mode="grounded_plan",
        continuation_id=batch["scope_id"],
        grounded_decision_contracts=True,
        grounded_source_gap_handoff=True,
        grounded_source_gap_investigation=True,
        input_token_reserve=32768,
        max_output_tokens=1024,
        max_request_usd=get_price("gpt-4o-mini").cost(32768, 1024),
    )
    return ledger, protocol, batch, fixtures, config


@pytest.mark.parametrize("case_id", ["dev-case-a", "dev-case-b", "dev-case-c"])
def test_controlled_source_condition_survives_current_turn_http_gateway_and_correction(
    multiple_holds, case_id
):
    ledger, protocol, batch, fixtures, config = prepared(multiple_holds, case_id)
    packet = load_source_packet(ROOT / PACKET_PATH)
    before = ledger_observation(ledger._path)
    old_uncertain = ledger.snapshot().uncertain_usd
    requests, retrievals = [], []

    def respond(request):
        wire = json.loads(request.content)
        assert wire["response_format"] == {"type": "json_object"}
        payload = json.loads(wire["messages"][1]["content"])
        supplied = payload["request"]
        assert set(supplied) == {
            "case",
            "user_message",
            "evidence",
            "gaps",
            "conflict_groups",
            "context_sha256",
        }
        requests.append(supplied)
        user_gaps = [gap for gap in supplied["gaps"] if gap["kind"] == "user"]
        selected_decision = "ask" if user_gaps else "answer"
        bound = payload["decision_contracts"]["rules"][selected_decision]["sources"]["maxItems"]
        plan = {
            "context_sha256": supplied["context_sha256"],
            "decision": selected_decision,
            "sources": list(range(len(supplied["evidence"]["hits"])))[-bound:],
        }
        if user_gaps:
            plan["question_name"] = user_gaps[0]["name"]
        return httpx.Response(
            200,
            json={
                "model": "gpt-4o-mini-2024-07-18",
                "usage": {"prompt_tokens": 100, "completion_tokens": 70, "total_tokens": 170},
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": json.dumps(plan)},
                    }
                ],
            },
        )

    with offline_network():
        result = run_quality_batch(
            protocol,
            batch,
            fixtures,
            load_user_gap_vocabulary(str(ROOT / VOCABULARY)),
            ledger,
            config,
            before,
            underlying=httpx.MockTransport(respond),
            retriever_factory=fixture_retriever_factory(packet, fixtures, retrievals),
        )
    assert result["actual_sends"] == len(requests) == 4
    assert result["completed_routes"] == 2 and result["visited_jobs"] == 2
    assert result["accounting"]["accounting_complete"]
    assert all(row["wire_response_format"] == "json_object" for row in result["provider_sends"])
    assert len(retrievals) == 4 and all(not row.get("actual_search", False) for row in retrievals)
    assert requests[0]["case"] == requests[2]["case"]
    if case_id == "dev-case-c":
        assert len(requests[0]["evidence"]["hits"]) == 1
        assert len(requests[2]["evidence"]["hits"]) == 3
        assert requests[0]["evidence"]["hits"] == requests[2]["evidence"]["hits"][:1]
        for request in (requests[1], requests[3]):
            active = {
                fact["name"]: fact["value"]
                for fact in request["case"]["facts"]
                if fact["status"] == "active" and fact["provenance_kind"] == "user"
            }
            assert active["streamlit_version"] == "1.31.1"
        for job in result["jobs"]:
            checks = [
                check
                for check in job["checks"]
                if check["step"] == "correction"
                and check["check"] == "stale approval rejected without mutation or new model send"
            ]
            assert len(checks) == 1 and checks[0]["passed"] and checks[0]["detail"] == 409
    else:
        assert requests[0]["evidence"] == requests[2]["evidence"]
        assert requests[1]["evidence"] == requests[3]["evidence"]
    assert ledger.snapshot().halted and ledger.snapshot().uncertain_usd == old_uncertain
    assert ledger.close_quarantine_scope(batch["scope_id"]).block_reason == "ExperimentClosed"


@pytest.mark.parametrize("kind", ["stability", "adversarial", "unknown"])
def test_full_reserve_does_not_leak_to_unregistered_fixed_kinds(kind):
    fixtures = fixtures_for(ROOT, {"protocol_id": "core-stability-v1"})
    batch = {
        "kind": kind,
        "jobs": [
            {
                "job_id": "unsafe-profile",
                "case_id": "dev-case-c",
                "arm": "fixed_baseline",
                "round": 1,
                "input_token_reserve": 32768,
                "max_output_tokens": 1024,
            }
        ],
    }
    with pytest.raises(DevProbeRejected):
        quality_slots({"experiment_id": "no-dispatch"}, batch, fixtures)
