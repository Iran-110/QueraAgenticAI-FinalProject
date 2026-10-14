"""Actual HTTP runner and provider gateway, using mock wire and synthetic ledger."""

import json
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from test_budget_quarantine_scope import multiple_holds as multiple_holds

from agent_app.contracts import EvidenceHit
from agent_app.llm.config import MetisConfig
from agent_app.llm.pricing import get_price
from agent_app.reasoning.catalog import load_user_gap_vocabulary
from agent_app.reasoning.grounding import source_content_sha256
from agent_app.testing.dev_three_model_probe import ledger_observation
from agent_app.testing.http_pilot_runtime import offline_network
from agent_app.testing.quality_probe import quality_slots, run_quality_batch
from agent_app.testing.quality_review import summarize_quality
from agent_app.testing.stability_probe import VOCABULARY, fixtures_for

ROOT = Path(__file__).resolve().parents[1]


def prepare(multiple_holds, case_id="dev-case-a"):
    ledger, path, _ = multiple_holds
    fixtures = fixtures_for(ROOT, {"protocol_id": "new-fixed-evidence"})
    protocol = {"experiment_id": "synthetic-quality-paired"}
    batch = {
        "batch_id": "synthetic-cap",
        "kind": "stability",
        "scope_id": "synthetic-quality-scope",
        "jobs": [
            {
                "job_id": f"synthetic:{case_id}:{bound}",
                "case_id": case_id,
                "arm": f"cap{bound}",
                "round": 1,
                "decision_contracts": True,
                "max_output_tokens": bound,
            }
            for bound in (1024, 2048)
        ],
    }
    slots = quality_slots(protocol, batch, fixtures)
    observed = asdict(ledger.quarantine_observation())
    ledger.authorize_quarantine_scope(
        authorization_id=batch["scope_id"],
        authorization_ref="synthetic-new-user-authorization",
        expected_unknown_ids=observed["unknown_ids"],
        expected_unknown_fingerprints=observed["unknown_fingerprints"],
        expected_meta_sha256=observed["meta_sha256"],
        expected_authorization_history_sha256=observed["authorization_history_sha256"],
        protocol_sha256="d" * 64,
        request_slots=slots,
        additional_cap_usd=Decimal(".06"),
    )
    config = MetisConfig(
        api_key="synthetic-quality-key",
        live_enabled=True,
        response_mode="grounded_plan",
        continuation_id=batch["scope_id"],
        grounded_decision_contracts=True,
        grounded_source_gap_handoff=True,
        grounded_source_gap_investigation=True,
        input_token_reserve=16384,
        max_output_tokens=2048,
        max_request_usd=get_price("gpt-4o-mini").cost(16384, 2048),
    )
    return ledger, protocol, batch, fixtures, config


def response(request):
    wire = json.loads(request.content)
    supplied = json.loads(wire["messages"][1]["content"])["request"]
    user_gaps = [gap for gap in supplied["gaps"] if gap["kind"] == "user"]
    if user_gaps:
        decision = "ask"
        name = user_gaps[0]["name"]
        refs = []
    else:
        decision = "answer"
        name = None
        hit = EvidenceHit.model_validate(supplied["evidence"]["hits"][0])
        refs = [{"chunk_id": hit.chunk_id, "content_sha256": source_content_sha256(hit)}]
    content = json.dumps(
        {
            "decision": decision,
            "context_sha256": supplied["context_sha256"],
            "sources": refs,
            "question_name": name,
            "retrieval_queries": [],
        }
    )
    return httpx.Response(
        200,
        json={
            "model": "gpt-4o-mini-2024-07-18",
            "usage": {"prompt_tokens": 100, "completion_tokens": 80, "total_tokens": 180},
            "choices": [
                {"finish_reason": "stop", "message": {"role": "assistant", "content": content}}
            ],
        },
    )


@pytest.mark.parametrize("case_id", ["dev-case-a", "dev-case-b", "dev-case-c"])
def test_paired_http_uses_exact_wire_bounds_and_preserves_quarantines(multiple_holds, case_id):
    ledger, protocol, batch, fixtures, config = prepare(multiple_holds, case_id)
    before = ledger_observation(ledger._path)
    with offline_network():
        receipt = run_quality_batch(
            protocol,
            batch,
            fixtures,
            load_user_gap_vocabulary(str(ROOT / VOCABULARY)),
            ledger,
            config,
            before,
            underlying=httpx.MockTransport(response),
        )
    assert receipt["visited_jobs"] == 2 and not receipt["stopped_early"]
    assert receipt["original_accounting_preserved"]
    assert receipt["actual_sends"] >= 2
    assert {r["wire_max_output_tokens"] for r in receipt["provider_sends"]} == {1024, 2048}
    assert all(r["finish_reason"] == "stop" for r in receipt["provider_sends"])
    assert ledger.snapshot().halted and ledger.snapshot().reserved_usd == 0
    first = [
        a
        for a in receipt["attempts"]
        if a["context"]["attempt_index"] == 1 and a["context"]["case_revision"] == 1
    ]
    assert len(first) == 2 and first[0]["request"] == first[1]["request"]
    assert ledger.close_quarantine_scope(batch["scope_id"]).block_reason == "ExperimentClosed"
    summary = summarize_quality({"batches": [receipt], "renderer_source_gap_investigation": True})
    assert len(summary["common_initial_state_comparisons"]) == 1
    for job in summary["jobs"]:
        for proposal in job["proposal_reviews"]:
            if proposal["proposal_present"]:
                verification = proposal["render_verification"]
                assert verification["proposal_analysis_matches"]
                assert verification["handoff_analysis_matches"]
                assert verification["top_level_analysis_surfaces_match"]


def test_timeout_stops_whole_pair_with_unknown_hold_and_safe_metadata(multiple_holds):
    ledger, protocol, batch, fixtures, config = prepare(multiple_holds)

    def timeout(request):
        raise httpx.ReadTimeout("synthetic-private-key-not-for-diagnostics")

    with offline_network():
        receipt = run_quality_batch(
            protocol,
            batch,
            fixtures,
            load_user_gap_vocabulary(str(ROOT / VOCABULARY)),
            ledger,
            config,
            ledger_observation(ledger._path),
            underlying=httpx.MockTransport(timeout),
        )
    assert receipt["visited_jobs"] == 1 and receipt["stopped_early"]
    assert receipt["actual_sends"] == 1
    assert receipt["provider_sends"][0]["transport_error_category"] == "read_timeout"
    assert not receipt["original_accounting_preserved"]
    assert ledger.quarantine_scope_status(batch["scope_id"]).block_reason == "NewUncertainty"
    assert len(ledger.quarantine_observation().unknown_ids) == 3
    assert "synthetic-private-key" not in json.dumps(receipt)


def test_spent_scope_cannot_be_replayed_without_new_send(multiple_holds):
    ledger, protocol, batch, fixtures, config = prepare(multiple_holds)
    ledger.close_quarantine_scope(batch["scope_id"])
    sent = []

    def forbidden(request):
        sent.append(request)
        raise AssertionError("no provider call")

    with offline_network():
        receipt = run_quality_batch(
            protocol,
            batch,
            fixtures,
            load_user_gap_vocabulary(str(ROOT / VOCABULARY)),
            ledger,
            config,
            ledger_observation(ledger._path),
            underlying=httpx.MockTransport(forbidden),
        )
    assert receipt["visited_jobs"] == 0 and receipt["stopped_early"]
    assert sent == [] and receipt["actual_sends"] == 0
