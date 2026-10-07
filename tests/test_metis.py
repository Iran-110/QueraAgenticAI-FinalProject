"""Exercise the real provider port with intercepted HTTP and a real local ledger."""

import json
import sqlite3
from copy import deepcopy
from decimal import Decimal

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from agent_app.contracts import (
    AnalysisResult,
    CaseState,
    EvidenceBundle,
    EvidenceHit,
    EvidenceLink,
    Fact,
    ReasoningContext,
)
from agent_app.llm.budget import BudgetLedger
from agent_app.llm.config import METIS_CHAT_URL, MetisConfig
from agent_app.llm.metis import MetisReasoner
from agent_app.orchestration import SupportEngine
from agent_app.orchestration.ports import ReasoningStopped
from agent_app.testing.fakes import FakeRetriever

SYNTHETIC_KEY = "offline-test-credential-marker"
SNAPSHOT = "provider-fixture"
MESSAGE = "How should I investigate a counter reset?"
CASE = CaseState(case_id="case:provider", case_revision=4)
EVIDENCE = EvidenceBundle(
    snapshot_id=SNAPSHOT,
    hits=(
        EvidenceHit(
            chunk_id="docs:fixture",
            source_id="source:fixture",
            excerpt="A synthetic source for testing response orchestration.",
            source_url="https://example.org/synthetic-fixture",
            source_type="doc",
            source_span="fixture paragraph",
        ),
    ),
)
ANSWER = AnalysisResult(
    decision="answer",
    user_draft="A synthetic draft to review before any action.",
    maintainer_summary="This test checks provider and accounting behavior only.",
    rationale="The fixture provides a source for the proposed claim.",
    evidence_links=(EvidenceLink(claim="Synthetic claim", chunk_id="docs:fixture"),),
)


def context(**changes):
    data = {
        "run_id": "run:provider",
        "case_id": CASE.case_id,
        "case_revision": CASE.case_revision,
        "attempt_index": 1,
    }
    return ReasoningContext(**(data | changes))


def response_body(**changes):
    data = {
        "model": "gpt-4o-mini",
        "usage": {"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": 130},
        "choices": [
            {
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": ANSWER.model_dump_json()},
            }
        ],
    }
    return deepcopy(data | changes)


def reservations(path):
    """Inspect actual persisted outcomes rather than infer them from reply text."""
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        return connection.execute("SELECT * FROM reservations ORDER BY rowid").fetchall()


@pytest.fixture
def provider_factory(tmp_path):
    ports = []

    def create(
        responses=None,
        *,
        handler=None,
        limit=Decimal("1"),
        opening=Decimal("0"),
        config_changes=None,
    ):
        path = tmp_path / f"budget-{len(ports)}.sqlite3"
        ledger = BudgetLedger.create(path, limit_usd=limit, opening_spend_usd=opening)
        config = MetisConfig(
            **({"api_key": SecretStr(SYNTHETIC_KEY), "live_enabled": True} | (config_changes or {}))
        )
        calls = []
        scripted = list(responses if responses is not None else [response_body()])

        def intercepted(request):
            calls.append(request)
            if handler is not None:
                return handler(request)
            item = scripted.pop(0)
            if isinstance(item, Exception):
                raise item
            if isinstance(item, httpx.Response):
                return item
            return httpx.Response(200, json=item)

        port = MetisReasoner(config, ledger, transport=httpx.MockTransport(intercepted))
        ports.append(port)
        return port, ledger, calls, path

    yield create
    for port in ports:
        port.close()


def engine_result(port):
    engine = SupportEngine(FakeRetriever([EVIDENCE]), port, snapshot_id=SNAPSHOT)
    return engine.run(CASE, MESSAGE, run_id="run:provider")


def observed_cost(input_tokens=100, output_tokens=30):
    # Independently use the verified 2026-10-07 list rates, not the port's calculator.
    return input_tokens * Decimal("0.000000165") + output_tokens * Decimal("0.000000660")


def test_valid_json_answer_uses_verified_endpoint_and_settles_observed_usage(provider_factory):
    port, ledger, calls, path = provider_factory()
    result = engine_result(port)
    assert result.status == "awaiting_approval"
    assert result.analysis == ANSWER
    assert result.model_attempts == len(calls) == 1
    request = calls[0]
    assert request.method == "POST"
    assert str(request.url) == METIS_CHAT_URL
    assert request.headers["Authorization"] == "Bearer " + SYNTHETIC_KEY
    payload = json.loads(request.content)
    assert payload["model"] == "gpt-4o-mini"
    assert payload["stream"] is False
    assert payload["max_tokens"] == port.config.max_output_tokens
    assert [message["role"] for message in payload["messages"]] == ["system", "user"]
    assert json.loads(payload["messages"][1]["content"])["user_message"] == MESSAGE
    snapshot = ledger.snapshot()
    assert snapshot.settled_usd == observed_cost()
    assert snapshot.reserved_usd == snapshot.uncertain_usd == 0
    assert snapshot.available_usd == Decimal("1") - observed_cost()
    rows = reservations(path)
    assert len(rows) == 1
    assert rows[0]["status"] == "settled"
    assert rows[0]["input_tokens"] == 100
    assert rows[0]["output_tokens"] == 30
    assert rows[0]["run_id"] == result.run_id
    assert rows[0]["case_id"] == CASE.case_id
    assert rows[0]["case_revision"] == CASE.case_revision
    assert rows[0]["attempt"] == 1
    assert rows[0]["phase"] == "development"


@pytest.mark.parametrize("repair_succeeds", [True, False])
def test_invalid_analysis_content_is_charged_and_only_engine_can_spend_one_repair(
    provider_factory, repair_succeeds
):
    invalid = response_body()
    invalid["choices"][0]["message"]["content"] = "not AnalysisResult JSON"
    second = response_body() if repair_succeeds else invalid
    port, ledger, calls, path = provider_factory([invalid, second, response_body()])
    result = engine_result(port)
    assert result.status == ("awaiting_approval" if repair_succeeds else "error")
    assert result.error_code == (None if repair_succeeds else "ModelOutputInvalid")
    assert result.model_attempts == len(calls) == 2
    assert result.retrieval_rounds == 1
    assert ledger.snapshot().settled_usd == 2 * observed_cost()
    rows = reservations(path)
    assert len(rows) == 2
    assert [row["attempt"] for row in rows] == [1, 2]
    assert all(row["status"] == "settled" for row in rows)


def test_timeout_preserves_unknown_cost_and_stops_without_a_second_send(provider_factory):
    def timeout(request):
        raise httpx.ReadTimeout("Private transport detail: " + SYNTHETIC_KEY, request=request)

    port, ledger, calls, path = provider_factory(handler=timeout, limit=Decimal("0.01"))
    result = engine_result(port)
    assert result.status == "error"
    assert result.error_code == "ProviderRequestFailed"
    assert result.model_attempts == len(calls) == 1
    assert result.analysis is None
    snapshot = ledger.snapshot()
    assert snapshot.settled_usd == snapshot.reserved_usd == 0
    assert snapshot.uncertain_usd > 0
    assert snapshot.available_usd == snapshot.limit_usd - snapshot.uncertain_usd
    row = reservations(path)[0]
    assert row["status"] == "uncertain"
    assert row["cost_nanos"] is row["input_tokens"] is row["output_tokens"] is None
    assert SYNTHETIC_KEY not in result.model_dump_json()
    assert SYNTHETIC_KEY.encode() not in path.read_bytes()
    # A fresh run cannot spend money already held for an ambiguous previous send.
    with pytest.raises(ReasoningStopped) as stopped:
        port.analyze(CASE, MESSAGE, EVIDENCE, context=context(run_id="run:after-timeout"))
    assert stopped.value.code == "BudgetExceeded"
    assert len(calls) == 1
    assert ledger.snapshot().uncertain_usd == snapshot.uncertain_usd


@pytest.mark.parametrize(
    "usage",
    [
        None,
        [],
        {},
        {"prompt_tokens": 100},
        {"completion_tokens": 30},
        {"prompt_tokens": True, "completion_tokens": 30},
        {"prompt_tokens": -1, "completion_tokens": 30},
        {"prompt_tokens": 100, "completion_tokens": -1},
        {"prompt_tokens": "100", "completion_tokens": 30},
        {"prompt_tokens": 100, "completion_tokens": "30"},
        {"prompt_tokens": 2**100, "completion_tokens": 30},
        {"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": True},
        {"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": 129},
    ],
)
def test_unusable_usage_never_becomes_zero_cost_or_a_retry(provider_factory, usage):
    port, ledger, calls, path = provider_factory([response_body(usage=usage)])
    result = engine_result(port)
    assert result.error_code == "ProviderUsageUnknown"
    assert result.analysis is None
    assert result.model_attempts == len(calls) == 1
    snapshot = ledger.snapshot()
    assert snapshot.settled_usd == 0
    assert snapshot.uncertain_usd > 0
    assert snapshot.halted
    row = reservations(path)[0]
    assert row["status"] == "uncertain"
    assert row["cost_nanos"] is None


@pytest.mark.parametrize("returned_model", [None, True, "unknown-model", "gpt-4.1-mini"])
def test_unverified_model_identity_keeps_unknown_cost_and_halts(provider_factory, returned_model):
    port, ledger, calls, path = provider_factory([response_body(model=returned_model)])
    result = engine_result(port)
    assert result.error_code == "ProviderModelMismatch"
    assert result.model_attempts == len(calls) == 1
    assert result.analysis is None
    assert ledger.snapshot().uncertain_usd > 0
    assert ledger.snapshot().halted
    assert reservations(path)[0]["cost_nanos"] is None


def test_exact_snapshot_of_mini_with_same_verified_rate_is_accepted(provider_factory):
    port, ledger, calls, _ = provider_factory([response_body(model="gpt-4o-mini-2024-07-18")])
    result = engine_result(port)
    assert result.status == "awaiting_approval"
    assert len(calls) == 1
    assert ledger.snapshot().settled_usd == observed_cost()
    assert not ledger.snapshot().halted


@pytest.mark.parametrize(
    ("scenario", "config_changes", "limit", "error_code", "status"),
    [
        ("denied-budget", {}, Decimal("0.001"), "BudgetExceeded", "budget_stopped"),
        ("disabled", {"live_enabled": False}, Decimal("1"), "LiveCallsDisabled", "error"),
        (
            "unknown-price",
            {"model": "unpriced-model"},
            Decimal("1"),
            "UnknownPricing",
            "budget_stopped",
        ),
        (
            "request-cap",
            {"max_request_usd": Decimal("0.0001")},
            Decimal("1"),
            "CostBoundExceeded",
            "budget_stopped",
        ),
        ("large-context", {}, Decimal("1"), "ContextLimitExceeded", "error"),
    ],
)
def test_preflight_rejection_makes_zero_http_calls_and_creates_no_reservation(
    provider_factory, scenario, config_changes, limit, error_code, status
):
    port, ledger, calls, path = provider_factory(config_changes=config_changes, limit=limit)
    message = "x" * 20_000 if scenario == "large-context" else MESSAGE
    bundle = EVIDENCE
    if scenario == "large-context":
        hit = EVIDENCE.hits[0].model_copy(update={"excerpt": "x" * 20_000})
        bundle = EVIDENCE.model_copy(update={"hits": (hit,)})
    engine = SupportEngine(FakeRetriever([bundle]), port, snapshot_id=SNAPSHOT)
    result = engine.run(CASE, message)
    assert result.status == status
    assert result.error_code == error_code
    assert result.analysis is None
    assert result.model_attempts == 1
    assert calls == []
    assert reservations(path) == []
    snapshot = ledger.snapshot()
    assert snapshot.settled_usd == snapshot.reserved_usd == snapshot.uncertain_usd == 0
    assert snapshot.available_usd == limit


@pytest.mark.parametrize(
    "malformation",
    [
        "length",
        "no_choices",
        "many_choices",
        "bad_choice",
        "tools",
        "function",
        "refusal",
        "role",
        "no_content",
    ],
)
def test_invalid_provider_outputs_settle_valid_usage_before_the_terminal_error(
    provider_factory, malformation
):
    body = response_body()
    choice = body["choices"][0]
    if malformation == "length":
        choice["finish_reason"] = "length"
    elif malformation == "no_choices":
        body["choices"] = []
    elif malformation == "many_choices":
        body["choices"].append(deepcopy(choice))
    elif malformation == "bad_choice":
        body["choices"] = [None]
    elif malformation == "tools":
        choice["message"]["tool_calls"] = [{"name": "execute_case"}]
    elif malformation == "function":
        choice["message"]["function_call"] = {"name": "execute_case"}
    elif malformation == "refusal":
        choice["message"]["refusal"] = "This request cannot be answered."
    elif malformation == "role":
        choice["message"]["role"] = "system"
    else:
        choice["message"]["content"] = None
    port, ledger, calls, path = provider_factory([body, response_body()])
    result = engine_result(port)
    assert result.status == "error"
    assert result.error_code == "ProviderResponseInvalid"
    assert result.analysis is None
    assert result.model_attempts == len(calls) == 1
    snapshot = ledger.snapshot()
    assert snapshot.settled_usd == observed_cost()
    assert snapshot.reserved_usd == snapshot.uncertain_usd == 0
    assert reservations(path)[0]["status"] == "settled"


@pytest.mark.parametrize("status", [302, 401, 429, 500])
def test_non_success_http_is_never_retried_or_assumed_unbilled(provider_factory, status):
    port, ledger, calls, path = provider_factory(
        [
            httpx.Response(
                status,
                json={"error": {"message": "Private provider detail: " + SYNTHETIC_KEY}},
                headers={"location": "https://example.org/other-endpoint", "retry-after": "0"},
            )
        ]
    )
    result = engine_result(port)
    assert result.error_code == "ProviderRequestFailed"
    assert result.model_attempts == len(calls) == 1
    assert ledger.snapshot().uncertain_usd > 0
    assert SYNTHETIC_KEY not in result.model_dump_json()
    assert SYNTHETIC_KEY.encode() not in path.read_bytes()


@pytest.mark.parametrize("malformation", ["invalid_json", "non_object", "oversized"])
def test_unreadable_provider_envelope_keeps_its_reservation_without_retry(
    provider_factory, malformation
):
    if malformation == "non_object":
        response = httpx.Response(200, json=[])
        expected_error = "ProviderResponseInvalid"
    else:
        text = SYNTHETIC_KEY if malformation == "invalid_json" else "x" * 262_145
        response = httpx.Response(200, text=text)
        expected_error = "ProviderRequestFailed"
    port, ledger, calls, path = provider_factory([response])
    result = engine_result(port)
    assert result.error_code == expected_error
    assert result.analysis is None
    assert result.model_attempts == len(calls) == 1
    assert ledger.snapshot().settled_usd == 0
    assert ledger.snapshot().uncertain_usd > 0
    assert reservations(path)[0]["cost_nanos"] is None
    assert SYNTHETIC_KEY not in result.model_dump_json()


def test_duplicate_context_cannot_resend_even_with_different_user_text(provider_factory):
    port, ledger, calls, path = provider_factory()
    first = port.analyze(CASE, MESSAGE, EVIDENCE, context=context())
    assert AnalysisResult.model_validate_json(first) == ANSWER
    with pytest.raises(ReasoningStopped) as stopped:
        port.analyze(
            CASE, "A different message with the same attempt ID.", EVIDENCE, context=context()
        )
    assert stopped.value.code == "DuplicateModelRequest"
    assert len(calls) == len(reservations(path)) == 1
    assert ledger.snapshot().settled_usd == observed_cost()


def test_observed_cost_overrun_is_recorded_and_blocks_further_sends(provider_factory):
    body = response_body(
        usage={"prompt_tokens": 40_000, "completion_tokens": 0, "total_tokens": 40_000}
    )
    port, ledger, calls, path = provider_factory([body, response_body()])
    result = engine_result(port)
    assert result.status == "budget_stopped"
    assert result.error_code == "CostBoundExceeded"
    assert result.analysis is None
    assert len(calls) == 1
    snapshot = ledger.snapshot()
    assert snapshot.halted
    assert snapshot.settled_usd == observed_cost(40_000, 0)
    assert snapshot.uncertain_usd == snapshot.reserved_usd == 0
    row = reservations(path)[0]
    assert row["status"] == "settled"
    assert row["input_tokens"] == 40_000
    with pytest.raises(ReasoningStopped) as stopped:
        port.analyze(CASE, MESSAGE, EVIDENCE, context=context(run_id="run:after-overrun"))
    assert stopped.value.code == "BudgetExceeded"
    assert len(calls) == 1


def test_reported_token_bound_violation_records_known_cost_and_halts(provider_factory):
    body = response_body(
        usage={"prompt_tokens": 32_769, "completion_tokens": 0, "total_tokens": 32_769}
    )
    port, ledger, calls, path = provider_factory([body])
    result = engine_result(port)
    assert result.error_code == "ProviderResponseInvalid"
    assert result.analysis is None
    assert len(calls) == result.model_attempts == 1
    assert ledger.snapshot().settled_usd == observed_cost(32_769, 0)
    assert ledger.snapshot().halted
    assert reservations(path)[0]["status"] == "settled"


def test_opening_team_spend_is_counted_before_a_provider_request(provider_factory):
    port, ledger, calls, path = provider_factory(limit=Decimal("0.01"), opening=Decimal("0.005"))
    result = engine_result(port)
    assert result.status == "budget_stopped"
    assert result.error_code == "BudgetExceeded"
    assert calls == []
    assert reservations(path) == []
    assert ledger.snapshot().opening_spend_usd == Decimal("0.005")
    assert ledger.snapshot().available_usd == Decimal("0.005")


def test_case_revision_too_large_for_durable_attribution_does_not_trigger_http_or_retry(
    provider_factory,
):
    port, _, calls, path = provider_factory()
    case = CASE.model_copy(update={"case_revision": 2**100})
    engine = SupportEngine(FakeRetriever([EVIDENCE]), port, snapshot_id=SNAPSHOT)
    result = engine.run(case, MESSAGE)
    assert result.status == "error"
    assert result.error_code == "ProviderRequestFailed"
    assert result.model_attempts == 1
    assert result.analysis is None
    assert calls == []
    assert reservations(path) == []


@pytest.mark.parametrize("mismatch", ["case_id", "case_revision"])
def test_context_must_match_the_exact_caller_case_before_reservation(provider_factory, mismatch):
    port, ledger, calls, path = provider_factory()
    changes = {mismatch: "case:other" if mismatch == "case_id" else CASE.case_revision + 1}
    with pytest.raises(ValueError, match="does not match case"):
        port.analyze(CASE, MESSAGE, EVIDENCE, context=context(**changes))
    assert calls == []
    assert reservations(path) == []
    assert ledger.snapshot().available_usd == Decimal("1")


@pytest.mark.parametrize("invalid_input", ["case", "evidence", "context"])
def test_nested_models_built_without_validation_are_revalidated_before_sending(
    provider_factory, invalid_input
):
    port, _, calls, path = provider_factory()
    case, bundle, attribution = CASE, EVIDENCE, context()
    if invalid_input == "case":
        invalid_fact = Fact.model_construct(
            name="version", value="1", source_ref="event:1", turn_id="turn:1", status="invented"
        )
        case = CASE.model_copy(update={"facts": (invalid_fact,)})
    elif invalid_input == "evidence":
        invalid_hit = EVIDENCE.hits[0].model_copy(update={"excerpt": " "})
        bundle = EVIDENCE.model_copy(update={"hits": (invalid_hit,)})
    else:
        attribution = context().model_copy(update={"attempt_index": 3})
    with pytest.raises(ValidationError):
        port.analyze(case, MESSAGE, bundle, context=attribution)
    assert calls == []
    assert reservations(path) == []


def test_configuration_representations_and_provider_failures_redact_the_credential(
    provider_factory,
):
    def fail(request):
        raise httpx.ConnectError("Connection failed with " + SYNTHETIC_KEY, request=request)

    port, ledger, _, path = provider_factory(handler=fail)
    assert SYNTHETIC_KEY not in repr(port.config)
    assert SYNTHETIC_KEY not in str(port.config)
    assert SYNTHETIC_KEY not in port.config.model_dump_json()
    with pytest.raises(ReasoningStopped) as stopped:
        port.analyze(CASE, MESSAGE, EVIDENCE, context=context())
    assert SYNTHETIC_KEY not in str(stopped.value)
    assert SYNTHETIC_KEY not in repr(stopped.value)
    assert SYNTHETIC_KEY not in repr(ledger.snapshot())
    assert SYNTHETIC_KEY.encode() not in path.read_bytes()


def test_environment_configuration_requires_explicit_live_opt_in(monkeypatch):
    monkeypatch.setenv("METIS_API_KEY", SYNTHETIC_KEY)
    monkeypatch.delenv("METIS_LIVE_ENABLED", raising=False)
    assert not MetisConfig.from_env().live_enabled
    monkeypatch.setenv("METIS_LIVE_ENABLED", "TRUE")
    assert not MetisConfig.from_env().live_enabled
    monkeypatch.setenv("METIS_LIVE_ENABLED", "true")
    assert MetisConfig.from_env().live_enabled


@pytest.mark.parametrize("wrapped", [False, True])
def test_invalid_credential_does_not_appear_in_validation_error_exports(wrapped):
    invalid_key = "offline invalid credential marker"
    with pytest.raises(ValidationError) as stopped:
        MetisConfig(api_key=SecretStr(invalid_key) if wrapped else invalid_key)
    assert invalid_key not in str(stopped.value)
    assert invalid_key not in repr(stopped.value)
    assert invalid_key not in stopped.value.json()


def test_unavailable_ledger_prevents_http_and_hides_storage_failure_detail(provider_factory):
    port, _, calls, path = provider_factory()
    path.unlink()
    result = engine_result(port)
    assert result.error_code == "LedgerUnavailable"
    assert result.model_attempts == 1
    assert result.analysis is None
    assert calls == []
    assert str(path) not in result.model_dump_json()
