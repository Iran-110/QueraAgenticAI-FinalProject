"""Optional source-selection guidance, not a model-quality or runtime-fix score."""

import hashlib
import json
import os
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from test_budget_quarantine_scope import multiple_holds as multiple_holds
from test_quality_probe import prepare, response

from agent_app.contracts import (
    GroundedRequest,
    OutputFeedback,
    OutputIssue,
    ReasoningContext,
)
from agent_app.llm.budget import BudgetLedger
from agent_app.llm.config import MetisConfig
from agent_app.llm.grounded import MetisGroundedPlanner
from agent_app.llm.metis import configured_grounded_messages, request_id_for
from agent_app.orchestration import SupportEngine
from agent_app.orchestration.ports import ReasoningStopped
from agent_app.reasoning.catalog import caller_catalog, load_user_gap_vocabulary
from agent_app.reasoning.compact_plan import add_compact_plan_messages
from agent_app.reasoning.grounding import (
    GroundedReasoner,
    build_grounded_messages,
    make_grounded_request,
)
from agent_app.reasoning.source_capacity import add_source_capacity
from agent_app.reasoning.source_selection import (
    COMPLEMENTARY_SOURCE_POLICY,
    SOURCE_SELECTION_REMINDER,
    add_complementary_source_policy,
    add_source_selection_reminder,
)
from agent_app.testing.dev_three_model_probe import DevProbeRejected, ledger_observation
from agent_app.testing.fakes import FakeRetriever
from agent_app.testing.http_pilot_runtime import offline_network
from agent_app.testing.quality_probe import run_quality_batch
from agent_app.testing.stability_probe import VOCABULARY

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "experiments/core_complementary_sources_v1/protocol-v1.json"
PARENT = ROOT / "experiments/core_enum_evidence_v1/model-live-receipt-v1.json"
PUBLIC_KEY = "public-synthetic-complementary-source-key"


def _receipt():
    return json.loads(PARENT.read_bytes())


def _attempts():
    return [attempt for batch in _receipt()["batches"] for attempt in batch["attempts"]]


def _C_requests():
    batch = next(
        batch
        for batch in _receipt()["batches"]
        if batch["batch_id"] == "enum-evidence-r1-dev-case-c"
    )
    # Only the two actual guide-present current contexts, not fixture gold.
    return [GroundedRequest.model_validate(attempt["request"]) for attempt in batch["attempts"][2:]]


def _config(**changes):
    return MetisConfig.model_validate(
        {
            "api_key": PUBLIC_KEY,
            "live_enabled": True,
            "response_mode": "grounded_plan",
            "input_token_reserve": 32768,
            "max_output_tokens": 1024,
            "grounded_decision_contracts": True,
            "grounded_source_gap_handoff": True,
            "grounded_source_gap_investigation": True,
            "grounded_source_selection_reminder": True,
            "grounded_source_capacity": True,
            "grounded_compact_plan": True,
            "grounded_json_object": True,
            **changes,
        }
    )


def _provider(content):
    return httpx.Response(
        200,
        json={
            "model": "gpt-4o-mini",
            "usage": {"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": 130},
            "choices": [
                {"finish_reason": "stop", "message": {"role": "assistant", "content": content}}
            ],
        },
    )


def _ledger(tmp_path):
    return BudgetLedger.create(
        tmp_path / "offline-cost.sqlite3", limit_usd=Decimal("1"), opening_spend_usd=Decimal("0")
    )


def test_new_text_matches_preregistration_and_old_text_remains_immutable():
    raw = PROTOCOL.read_bytes()
    assert (
        hashlib.sha256(raw).hexdigest()
        == "1c698261830ed17f79dcfb80c821746ae8cf5fb2c8bfe819db36e473174b9cea"
    )
    treatment = json.loads(raw)["treatment"]
    assert COMPLEMENTARY_SOURCE_POLICY == treatment["text"]
    assert len(COMPLEMENTARY_SOURCE_POLICY) == 1341
    assert (
        hashlib.sha256(COMPLEMENTARY_SOURCE_POLICY.encode()).hexdigest()
        == treatment["text_utf8_sha256"]
    )
    old = json.loads(
        (ROOT / "experiments/core_quality_followup/adversarial-live-protocol-v1.json").read_bytes()
    )
    assert SOURCE_SELECTION_REMINDER == old["candidate"]["candidate_text"]
    assert MetisConfig(api_key=PUBLIC_KEY).grounded_complementary_sources is False


@pytest.mark.parametrize("bad", [None, 0, 1, "true", "false", [], {}, b"true"])
def test_strict_config_and_helper_reject_non_boolean_before_message_access(bad):
    with pytest.raises(ValueError):
        _config(grounded_complementary_sources=bad)

    class Unreadable:
        def __len__(self):
            pytest.fail("Invalid operator configuration must fail before reading source data")

    with pytest.raises(ValueError, match="^ComplementarySourcesFlagInvalid$"):
        add_complementary_source_policy(Unreadable(), bad)


def test_mode_prerequisite_and_config_copy_preserve_operator_setting():
    with pytest.raises(ValueError):
        _config(grounded_complementary_sources=True, grounded_source_selection_reminder=False)
    with pytest.raises(ValueError):
        _config(grounded_complementary_sources=True, response_mode="analysis")
    config = _config(grounded_complementary_sources=True)
    assert MetisConfig.model_validate(config.model_dump()).grounded_complementary_sources is True
    assert PUBLIC_KEY not in repr(config)


@pytest.mark.parametrize("value", ["TRUE", "True", "1", "0", " true", "false ", "", "yes"])
def test_from_env_rejects_noncanonical_values(monkeypatch, value):
    for name in list(os.environ):
        if name.startswith("METIS_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("METIS_API_KEY", PUBLIC_KEY)
    monkeypatch.setenv("METIS_GROUNDED_COMPLEMENTARY_SOURCES", value)
    with pytest.raises(ValueError, match="Grounded mode flags"):
        MetisConfig.from_env()


def test_from_env_requires_reminder_and_preserves_false_default(monkeypatch):
    for name in list(os.environ):
        if name.startswith("METIS_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("METIS_API_KEY", PUBLIC_KEY)
    assert MetisConfig.from_env().grounded_complementary_sources is False
    monkeypatch.setenv("METIS_GROUNDED_COMPLEMENTARY_SOURCES", "true")
    with pytest.raises(ValueError):
        MetisConfig.from_env()
    monkeypatch.setenv("METIS_RESPONSE_MODE", "grounded_plan")
    monkeypatch.setenv("METIS_GROUNDED_SOURCE_SELECTION_REMINDER", "true")
    assert MetisConfig.from_env().grounded_complementary_sources is True
    monkeypatch.setenv("METIS_GROUNDED_COMPLEMENTARY_SOURCES", "false")
    assert MetisConfig.from_env().grounded_complementary_sources is False


@pytest.mark.parametrize(
    "malformed",
    [
        (),
        [],
        None,
        ({"role": "user", "content": "x"}, {"role": "user", "content": "y"}),
        ({"role": "system", "content": "x", "extra": "z"}, {"role": "user", "content": "y"}),
    ],
)
def test_enabled_helper_rejects_ambiguous_policy_placement(malformed):
    with pytest.raises(ValueError, match="^ComplementarySourcesMessagesInvalid$"):
        add_complementary_source_policy(malformed, True)


@pytest.mark.parametrize("compact", [False, True])
@pytest.mark.parametrize("repair", [False, True])
def test_all_24_historical_requests_keep_disabled_bytes_and_only_add_SYSTEM(compact, repair):
    receipt = _receipt()
    assert (
        hashlib.sha256(PARENT.read_bytes()).hexdigest()
        == "bf4ba6855c56591ea2875bde060c917363f3507e2cf7e1885fe3b4488b7fabda"
    )
    actual_wires = {
        send["request_id"]: send["wire_messages_sha256"]
        for batch in receipt["batches"]
        for send in batch["provider_sends"]
    }
    for attempt in _attempts():
        request = GroundedRequest.model_validate(attempt["request"])
        context = ReasoningContext.model_validate(attempt["context"])
        if repair:
            context = context.model_copy(
                update={
                    "attempt_index": 2,
                    "remaining_model_attempts": 0,
                    "can_refine": False,
                    "output_feedback": OutputFeedback(
                        issues=(OutputIssue(code="invalid_grounded_plan"),)
                    ),
                }
            )
        config = _config(grounded_compact_plan=compact)
        original = build_grounded_messages(request, context, decision_contracts=True)
        original = add_source_selection_reminder(original, True)
        original = add_source_capacity(
            original, request, enabled=True, source_gap_handoff=True, source_gap_investigation=True
        )
        original = add_compact_plan_messages(original, request, context, enabled=compact)
        disabled = configured_grounded_messages(config, request, context)
        explicit_false = configured_grounded_messages(
            config.model_copy(update={"grounded_complementary_sources": False}), request, context
        )
        assert disabled == explicit_false == original
        if compact and not repair:
            assert (
                hashlib.sha256(
                    json.dumps(disabled, ensure_ascii=False, sort_keys=True).encode()
                ).hexdigest()
                == actual_wires[request_id_for(context)]
            )
        before = deepcopy(disabled)
        assert add_complementary_source_policy(disabled) is disabled
        assert add_complementary_source_policy(disabled, False) is disabled
        enabled = configured_grounded_messages(
            config.model_copy(update={"grounded_complementary_sources": True}), request, context
        )
        assert (
            enabled[0]["content"] == disabled[0]["content"] + "\n\n" + COMPLEMENTARY_SOURCE_POLICY
        )
        assert enabled[1] == disabled[1]
        assert disabled == before
        assert json.loads(enabled[1]["content"])["request"] == request.model_dump(mode="json")
        assert len(json.dumps(enabled, ensure_ascii=False).encode()) + 1024 <= 32768


def test_quality_job_flag_is_applied_per_job_to_actual_mock_transport(multiple_holds):
    ledger, protocol, batch, fixtures, config = prepare(multiple_holds, "dev-case-b")
    for index, job in enumerate(batch["jobs"]):
        job.update(source_selection_reminder=True, complementary_sources=bool(index))
    before = ledger_observation(ledger._path)
    observed = []

    def respond(request):
        body = json.loads(request.content)
        observed.append(COMPLEMENTARY_SOURCE_POLICY in body["messages"][0]["content"])
        return response(request)

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
        )
    assert result["completed_routes"] == 2 and result["actual_sends"] == 4
    assert observed == [False, False, True, True]
    assert result["original_accounting_preserved"]


@pytest.mark.parametrize("value", [None, 0, 1, "true", [], {}, True])
def test_invalid_job_or_missing_reminder_stops_before_transport_or_reservation(
    multiple_holds, value
):
    ledger, protocol, batch, fixtures, config = prepare(multiple_holds)
    batch["jobs"][0]["complementary_sources"] = value
    before = ledger_observation(ledger._path)
    with offline_network(), pytest.raises(DevProbeRejected):
        run_quality_batch(
            protocol,
            batch,
            fixtures,
            (),
            ledger,
            config,
            before,
            underlying=httpx.MockTransport(lambda _: pytest.fail("Must not reach transport")),
        )
    assert ledger_observation(ledger._path) == before


def test_actual_gateway_repairs_current_selection_and_keeps_revision_identity(tmp_path):
    ledger = _ledger(tmp_path)
    sends = []
    contexts = []

    def respond(request):
        body = json.loads(request.content)
        sends.append(body)
        assert COMPLEMENTARY_SOURCE_POLICY in body["messages"][0]["content"]
        wire = json.loads(body["messages"][1]["content"])
        current = wire["request"]
        assert len(current["evidence"]["hits"]) == 3
        return _provider(
            "{}"
            if len(sends) % 2
            else json.dumps(
                {
                    "context_sha256": current["context_sha256"],
                    "decision": "answer",
                    "sources": [1, 2],
                }
            )
        )

    for request in _C_requests():
        gateway = MetisGroundedPlanner(
            _config(grounded_complementary_sources=True),
            ledger,
            transport=httpx.MockTransport(respond),
        )

        class Planner:
            def __init__(self, gateway):
                self.gateway = gateway

            def plan(self, request, *, context):
                contexts.append(context.model_copy(deep=True))
                return self.gateway.plan(request, context=context)

        try:
            engine = SupportEngine(
                FakeRetriever([request.evidence]),
                GroundedReasoner(
                    Planner(gateway),
                    request_factory=caller_catalog,
                    source_gap_handoff=True,
                    source_gap_investigation=True,
                    concise_user_draft=True,
                ),
                snapshot_id=request.evidence.snapshot_id,
                evidence_scope="exact_user_version",
            )
            with offline_network():
                result = engine.run(
                    request.case, request.user_message, run_id="offline-complementary-identity"
                )
            assert result.status == "awaiting_approval" and result.model_attempts == 2
            assert (
                len(result.analysis.evidence_links) == 2 and result.analysis.next_question is None
            )
            assert "enumCoercion" in result.analysis.user_draft
            assert "restart your Streamlit server" in result.analysis.user_draft
            assert request.evidence.hits[0].chunk_id not in {
                link.chunk_id for link in result.analysis.evidence_links
            }
        finally:
            gateway.close()
    assert len(sends) == 4
    assert [c.case_revision for c in contexts] == [1, 1, 2, 2]
    assert [c.attempt_index for c in contexts] == [1, 2, 1, 2]
    assert all(c.output_feedback and c.remaining_model_attempts == 0 for c in contexts[1::2])
    assert len({request_id_for(c) for c in contexts}) == 4
    assert all(ledger.get(request_id_for(c)).status == "settled" for c in contexts)
    replay = contexts[1].model_copy(
        update={"output_feedback": OutputFeedback(issues=(OutputIssue(code="invalid_shape"),))}
    )
    assert request_id_for(replay) == request_id_for(contexts[1])
    with (
        offline_network(),
        MetisGroundedPlanner(
            _config(),
            ledger,
            transport=httpx.MockTransport(
                lambda _: pytest.fail("A flag/feedback change cannot replay a spent identity")
            ),
        ) as gateway,
    ):
        with pytest.raises(ReasoningStopped) as error:
            gateway.plan(_C_requests()[0], context=replay)
    assert error.value.code == "DuplicateModelRequest"


@pytest.mark.parametrize("failure", ["context", "source"])
def test_terminal_binding_mismatch_cannot_use_prompt_as_an_extra_attempt(tmp_path, failure):
    ledger = _ledger(tmp_path)
    request = _C_requests()[0]
    sends = []

    def respond(wire):
        body = json.loads(wire.content)
        sends.append(body)
        current = json.loads(body["messages"][1]["content"])["request"]
        return _provider(
            json.dumps(
                {
                    "context_sha256": "0" * 64
                    if failure == "context"
                    else current["context_sha256"],
                    "decision": "answer",
                    "sources": [999] if failure == "source" else [1, 2],
                }
            )
        )

    with (
        offline_network(),
        MetisGroundedPlanner(
            _config(grounded_complementary_sources=True),
            ledger,
            transport=httpx.MockTransport(respond),
        ) as gateway,
    ):
        engine = SupportEngine(
            FakeRetriever([request.evidence]),
            GroundedReasoner(gateway, request_factory=caller_catalog),
            snapshot_id=request.evidence.snapshot_id,
        )
        result = engine.run(request.case, request.user_message)
    assert len(sends) == result.model_attempts == 1
    assert result.status == "error" and result.analysis is None


def test_added_prompt_bytes_still_stop_before_reservation_and_transport(tmp_path):
    ledger = _ledger(tmp_path)
    original = _C_requests()[0]
    context = ReasoningContext(
        run_id="offline-complementary-limit",
        case_id=original.case.case_id,
        case_revision=original.case.case_revision,
        attempt_index=1,
    )
    size = (
        len(
            json.dumps(
                configured_grounded_messages(_config(), original, context), ensure_ascii=False
            ).encode()
        )
        + 1024
    )
    request = make_grounded_request(
        original.case,
        original.user_message + "x" * (32768 - size - 300),
        original.evidence,
        gaps=original.gaps,
    )
    assert (
        len(
            json.dumps(
                configured_grounded_messages(_config(), request, context), ensure_ascii=False
            ).encode()
        )
        + 1024
        <= 32768
    )
    assert (
        len(
            json.dumps(
                configured_grounded_messages(
                    _config(grounded_complementary_sources=True), request, context
                ),
                ensure_ascii=False,
            ).encode()
        )
        + 1024
        > 32768
    )
    with (
        offline_network(),
        MetisGroundedPlanner(
            _config(grounded_complementary_sources=True),
            ledger,
            transport=httpx.MockTransport(
                lambda _: pytest.fail("Input stop must precede transport")
            ),
        ) as gateway,
    ):
        with pytest.raises(ReasoningStopped) as error:
            gateway.plan(request, context=context)
    assert error.value.code == "ContextLimitExceeded"
    assert ledger.get(request_id_for(context)) is None
