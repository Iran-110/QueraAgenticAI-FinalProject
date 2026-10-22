"""Reusable live adapter controls use real local Chroma and mock provider wires."""

import gzip
import hashlib
import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from agent_app.contracts import CaseState, EvidenceBundle, Fact, GroundedGap
from agent_app.evaluation import live, runner
from agent_app.llm.budget import BudgetLedger
from agent_app.llm.config import MetisConfig
from agent_app.orchestration import SupportEngine
from agent_app.orchestration.handoff import ReasoningCapture, build_handoff
from agent_app.orchestration.ports import ReasoningStopped
from agent_app.reasoning.catalog import caller_catalog, runtime_catalog, validate_user_gaps
from agent_app.retrieval.offline_index import OfflineIndexRejected, build_index
from agent_app.retrieval.pilot_corpus import MANIFEST_NAME, build_pilot_corpus
from agent_app.testing.grounded_http_binding import runtime_catalog as prior_catalog
from agent_app.testing.http_pilot_runtime import offline_network

ROOT = Path(__file__).resolve().parents[1]
KEY = "public-synthetic-live-evaluation-key"
CALLBACK = GroundedGap(
    name="parent_callback_code",
    kind="user",
    description="The parent callback was not supplied.",
    necessity="The user can supply the callback to inspect the state-update order; documentation cannot establish this app's cause.",
    question="Can you share the parent selector callback that resets Session State?",
)


@pytest.fixture(scope="module")
def index(tmp_path_factory):
    directory = tmp_path_factory.mktemp("live-evaluation-index") / "index"
    with offline_network():
        corpus = build_pilot_corpus(
            ROOT / "streamlit-data-for-dev-test",
            ROOT / "data/evaluation/split-manifest.json",
            ROOT / "experiments/corpus/pilot-allowlist.json",
        )
        snapshot = build_index(corpus, directory)
    return directory, snapshot, hashlib.sha256((directory / MANIFEST_NAME).read_bytes()).hexdigest()


@pytest.fixture
def ledger(tmp_path):
    return BudgetLedger.create(
        tmp_path / "mock-ledger.sqlite3", limit_usd=Decimal("1"), opening_spend_usd=Decimal("0")
    )


def config(**changes):
    return MetisConfig(
        **(
            {
                "api_key": KEY,
                "live_enabled": True,
                "model": "gpt-4o-mini",
                "phase": "development",
                "response_mode": "grounded_plan",
                "input_token_reserve": 32768,
                "max_output_tokens": 768,
                "max_request_usd": Decimal("0.02"),
            }
            | changes
        )
    )


def provider_response(request, *, malformed=False, model="gpt-4o-mini-2024-07-18", question=None):
    payload = json.loads(request.content)
    data = json.loads(payload["messages"][1]["content"])
    gaps = [gap for gap in data["request"]["gaps"] if gap["kind"] == "user"]
    if question is None:
        question = gaps[0]["name"] if gaps else None
    plan = {
        "context_sha256": data["request"]["context_sha256"],
        "decision": "ask" if question else "escalate",
    }
    if question:
        plan["question_name"] = question
    else:
        plan["sources"] = data["source_references"][:1]
    return httpx.Response(
        200,
        json={
            "model": model,
            "usage": {"prompt_tokens": 125, "completion_tokens": 75, "total_tokens": 200},
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": "{broken" if malformed else json.dumps(plan),
                    },
                }
            ],
        },
    )


class CountedMock(httpx.MockTransport):
    def __init__(self, respond):
        super().__init__(respond)
        self.close_calls = 0

    def close(self):
        self.close_calls += 1
        super().close()


def adapters(index, ledger, respond=provider_response, **changes):
    transports = []

    def allocate():
        transport = CountedMock(respond)
        transports.append(transport)
        return transport

    factory = live.LiveEvaluationAdapters(
        index_path=index[0],
        snapshot_id=index[1],
        manifest_sha256=index[2],
        ledger=ledger,
        config=config(),
        transport_factory=allocate,
        **changes,
    )
    return factory, transports


def run(factory, case, message):
    ports = factory.for_case(case.case_id)
    capture = ReasoningCapture(ports.reasoner)
    result = SupportEngine(ports.retriever, capture, snapshot_id=ports.snapshot_id).run(
        case, message
    )
    request = ports.grounded_request_supplier()
    handoff = (
        build_handoff(result, capture.last, grounded_request=request)
        if result.analysis is not None
        else None
    )
    ports.cleanup()
    return result, handoff, ports, capture.last


def test_setup_is_lazy_and_every_cleanup_closes_client_exactly_once(index, ledger):
    with offline_network():
        factory, transports = adapters(index, ledger)
        assert factory.index_path == index[0].resolve()
        with pytest.raises(AttributeError):
            factory.index_path = Path("caller-cannot-rebind-index")
        assert transports == [] and factory.active_clients == 0
        ports = factory.for_case("case:lazy")
        assert len(transports) == factory.active_clients == 1
        ports.cleanup()
        ports.cleanup()
        factory.close()
        assert factory.active_clients == 0 and transports[0].close_calls == 1
    assert ledger.snapshot().settled_usd == 0
    assert KEY not in repr(factory) and KEY not in json.dumps(factory.config)
    original = factory.config
    original["model"] = "caller-mutated"
    assert factory.config["model"] == "gpt-4o-mini"
    with pytest.raises(ValueError, match="LiveEvaluationFactoryClosed"):
        factory.for_case("case:late")


def test_actual_index_version_question_handoff_and_context_matched_observations(index, ledger):
    with offline_network():
        factory, transports = adapters(index, ledger)
        result, handoff, ports, frame = run(
            factory,
            CaseState(case_id="case:version"),
            "The widget loses its default and the Streamlit version is unknown.",
        )
    assert result.analysis.decision == "ask" and result.model_attempts == 1
    assert handoff.analysis.missing_info == ("streamlit_version",)
    assert handoff.grounded_request == ports.grounded_request_supplier()
    assert len(handoff.evidence.hits) == 1 and handoff.evidence.snapshot_id == index[1]
    rows = factory.observations_for_contexts((frame.context,))
    assert len(rows) == 1
    row = rows[0]
    assert row["verified_returned_model"] == "gpt-4o-mini-2024-07-18"
    assert (
        row["ledger_status"] == "settled"
        and row["input_tokens"] == 125
        and row["output_tokens"] == 75
    )
    assert Decimal(row["cost_estimated_usd"]) == Decimal("0.000070125")
    assert row["held_usd"] is None and len(row["prompt_sha256"]) == 64
    assert transports[0].close_calls == 1 and factory.active_clients == 0
    wrong = frame.context.model_copy(update={"run_id": "run:other"})
    assert factory.observations_for_contexts((wrong,)) == []
    exported = json.dumps(rows)
    assert KEY not in exported and "Authorization" not in exported and "messages" not in exported
    row["verified_returned_model"] = "caller-mutated"
    assert (
        factory.observations_for_contexts((frame.context,))[0]["verified_returned_model"]
        == "gpt-4o-mini-2024-07-18"
    )
    before = ledger.snapshot()
    with pytest.raises(ReasoningStopped) as stopped:
        ports.reasoner.analyze(
            handoff.case, handoff.user_message, handoff.evidence, context=frame.context
        )
    assert stopped.value.code == "LiveCallsDisabled" and ledger.snapshot() == before


def test_current_explicit_callback_question_excludes_known_version_and_python(index, ledger):
    seen = []

    def respond(request):
        data = json.loads(json.loads(request.content)["messages"][1]["content"])["request"]
        seen.append(data)
        return provider_response(request, question="parent_callback_code")

    known = tuple(
        Fact(name=name, value=value, source_ref="user:known", turn_id="turn:known")
        for name, value in (("streamlit_version", "1.50.0"), ("python_version", "3.12.9"))
    )
    case = CaseState(
        case_id="case:callback", case_revision=1, facts=known, unknowns=("parent_callback_code",)
    )
    with offline_network():
        factory, _transports = adapters(index, ledger, respond, user_gaps=(CALLBACK,))
        result, handoff, _ports, _frame = run(
            factory,
            case,
            "The reduction works; the missing parent selector callback resets Session State.",
        )
    assert result.analysis.next_question == CALLBACK.question
    assert result.analysis.missing_info == ("parent_callback_code",)
    assert result.analysis.evidence_links == ()
    assert all(
        gap["name"] not in {"python_version", "streamlit_version"} for gap in seen[0]["gaps"]
    )
    assert handoff.grounded_request.case == case


def test_malformed_output_repair_keeps_one_run_and_two_distinct_attempts(index, ledger):
    seen = []

    def respond(request):
        seen.append(1)
        return provider_response(request, malformed=len(seen) == 1)

    with offline_network():
        factory, transports = adapters(index, ledger, respond)
        result, handoff, _ports, frame = run(
            factory, CaseState(case_id="case:repair"), "The installed version is unknown."
        )
    assert result.model_attempts == len(seen) == 2 and handoff is not None
    rows = factory.observations_for_contexts((frame.context,))
    assert len(rows) == 1 and rows[0]["attempt_index"] == 2
    assert ledger.snapshot().settled_usd == Decimal("0.000140250")
    assert transports[0].close_calls == 1


def test_compressed_response_observes_exact_verified_id_without_exporting_headers(index, ledger):
    def respond(request):
        body = gzip.compress(provider_response(request).content)
        return httpx.Response(
            200,
            headers={
                "content-encoding": "gzip",
                "content-length": str(len(body)),
                "private-header": "private-value",
            },
            content=body,
        )

    with offline_network():
        factory, _transports = adapters(index, ledger, respond)
        _result, _handoff, _ports, frame = run(
            factory, CaseState(case_id="case:gzip"), "The version is unknown."
        )
    row = factory.observations_for_contexts((frame.context,))[0]
    assert row["verified_returned_model"] == "gpt-4o-mini-2024-07-18"
    assert "private-header" not in json.dumps(row) and "private-value" not in json.dumps(row)


def test_case_binding_refuses_before_reservation_or_send(index, ledger):
    with offline_network():
        factory, transports = adapters(index, ledger)
        ports = factory.for_case("case:allocated")
        capture = ReasoningCapture(ports.reasoner)
        result = SupportEngine(ports.retriever, capture, snapshot_id=ports.snapshot_id).run(
            CaseState(case_id="case:other"), "The version is unknown."
        )
        ports.cleanup()
    assert result.error_code == "ProviderRequestFailed" and ledger.snapshot().settled_usd == 0
    assert ledger.snapshot().reserved_usd == 0 and transports[0].close_calls == 1


@pytest.mark.parametrize("failure", ["timeout", "model_mismatch"])
def test_terminal_uncertainty_stops_new_ports_and_preserves_hold(index, ledger, failure):
    seen = []

    def respond(request):
        seen.append(1)
        if failure == "timeout":
            raise httpx.ReadTimeout("private-provider-failure", request=request)
        return provider_response(request, model="private-unverified-model")

    with offline_network():
        factory, transports = adapters(index, ledger, respond)
        result, handoff, _ports, _frame = run(
            factory, CaseState(case_id="case:terminal"), "The version is unknown."
        )
        with pytest.raises(ValueError, match="LiveLedgerHalted|LiveAccountingUnresolved"):
            factory.for_case("case:later")
    assert len(seen) == 1 and result.model_attempts == 1 and handoff is None
    assert ledger.snapshot().uncertain_usd > 0 and transports[0].close_calls == 1


def test_index_manifest_mutation_stops_new_ports_before_provider_allocation(index, ledger):
    path = index[0] / MANIFEST_NAME
    original = path.read_bytes()
    with offline_network():
        factory, transports = adapters(index, ledger)
        try:
            path.write_bytes(original + b" ")
            with pytest.raises(OfflineIndexRejected, match="PilotIndexChanged"):
                factory.for_case("case:index-changed")
            assert transports == []
        finally:
            path.write_bytes(original)


def test_factory_close_attempts_all_owned_clients_even_when_one_close_fails(index, ledger):
    transports = []

    class ClosingTransport(CountedMock):
        def close(self):
            super().close()
            if self is transports[0]:
                raise RuntimeError("private-close-failure-detail")

    def allocate():
        value = ClosingTransport(provider_response)
        transports.append(value)
        return value

    with offline_network():
        factory = live.LiveEvaluationAdapters(
            index_path=index[0],
            snapshot_id=index[1],
            manifest_sha256=index[2],
            ledger=ledger,
            config=config(),
            transport_factory=allocate,
        )
        factory.for_case("case:close-first")
        factory.for_case("case:close-second")
        with pytest.raises(ValueError, match="^LiveEvaluationCleanupFailed$"):
            factory.close()
        factory.close()
    assert [transport.close_calls for transport in transports] == [1, 1]
    assert factory.active_clients == 0


def test_invalid_transport_stops_setup_without_false_uncertain_charge(index, ledger):
    before = ledger.snapshot()
    with offline_network():
        factory = live.LiveEvaluationAdapters(
            index_path=index[0],
            snapshot_id=index[1],
            manifest_sha256=index[2],
            ledger=ledger,
            config=config(),
            transport_factory=lambda: object(),
        )
        with pytest.raises(ValueError, match="^LiveEvaluationAdapterUnavailable$"):
            factory.for_case("case:invalid-transport")
    assert ledger.snapshot() == before and factory.active_clients == 0


@pytest.mark.parametrize(
    "state,code",
    [
        ({"limit_usd": Decimal("6")}, "LiveLedgerLimitInvalid"),
        ({"available_usd": Decimal("0")}, "LiveBudgetUnavailable"),
        ({"reserved_usd": Decimal("0.01")}, "LiveAccountingUnresolved"),
        ({"uncertain_usd": Decimal("0.01")}, "LiveAccountingUnresolved"),
    ],
)
def test_budget_policy_blocks_index_and_provider_setup(index, ledger, monkeypatch, state, code):
    snapshot = ledger.snapshot()
    monkeypatch.setattr(ledger, "snapshot", lambda: replace(snapshot, **state))

    def forbidden(*_args):
        raise AssertionError("Invalid accounting must precede index/provider allocation")

    monkeypatch.setattr(live, "_verified_index", forbidden)
    with pytest.raises(ValueError, match=code):
        live.LiveEvaluationAdapters(
            index_path=index[0],
            snapshot_id=index[1],
            manifest_sha256=index[2],
            ledger=ledger,
            config=config(),
            transport_factory=forbidden,
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"continuation_id": "forbidden-old-grant"},
        {"response_mode": "analysis"},
        {"live_enabled": False},
        {"model": "unpriced-model"},
    ],
)
def test_configuration_scope_rejected_without_model_transport(index, ledger, changes):
    with offline_network(), pytest.raises(ValueError, match="LiveEvaluationConfigurationInvalid"):
        live.LiveEvaluationAdapters(
            index_path=index[0],
            snapshot_id=index[1],
            manifest_sha256=index[2],
            ledger=ledger,
            config=config(**changes),
            transport_factory=lambda: (_ for _ in ()).throw(AssertionError("Provider allocated")),
        )


def test_no_argument_configuration_checks_halt_before_key(index, tmp_path, monkeypatch):
    monkeypatch.setattr(live, "ROOT", tmp_path)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    ledger = BudgetLedger.create(
        runtime / "budget.sqlite3", limit_usd=Decimal("4.5"), opening_spend_usd=Decimal("0")
    )
    ledger.halt()

    class KeyGuard(dict):
        def get(self, name, default=None):
            if name == "METIS_API_KEY":
                raise AssertionError("Halted ledger must precede credential lookup")
            return super().get(name, default)

    values = KeyGuard(
        METIS_LIVE_ENABLED="true",
        AGENT_EVAL_INDEX=str(index[0]),
        AGENT_EVAL_SNAPSHOT=index[1],
        AGENT_EVAL_MANIFEST_SHA256=index[2],
    )
    before = (runtime / "budget.sqlite3").read_bytes()
    with pytest.raises(ValueError, match="LiveLedgerHalted"):
        live.configured_factory(values)
    assert (runtime / "budget.sqlite3").read_bytes() == before


def test_configuration_checks_index_before_key_and_rejects_different_ledger(
    index, tmp_path, monkeypatch
):
    monkeypatch.setattr(live, "ROOT", tmp_path)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    BudgetLedger.create(
        runtime / "budget.sqlite3", limit_usd=Decimal("4.5"), opening_spend_usd=Decimal("0")
    )

    class KeyGuard(dict):
        def get(self, name, default=None):
            if name == "METIS_API_KEY":
                raise AssertionError("Invalid index must precede credential lookup")
            return super().get(name, default)

    values = KeyGuard(
        METIS_LIVE_ENABLED="true",
        AGENT_EVAL_INDEX=str(index[0]),
        AGENT_EVAL_SNAPSHOT=index[1],
        AGENT_EVAL_MANIFEST_SHA256="0" * 64,
    )
    with pytest.raises(ValueError, match="LiveIndexRejected"):
        live.configured_factory(values)
    values["AGENT_EVAL_LEDGER"] = str(tmp_path / "fresh-budget.sqlite3")
    with pytest.raises(ValueError, match="LiveLedgerPathRejected"):
        live.configured_factory(values)
    assert not (tmp_path / "fresh-budget.sqlite3").exists()


@pytest.mark.parametrize("status", ["reserved", "uncertain"])
def test_zero_amount_unresolved_row_still_blocks_and_preserves_ledger_bytes(index, ledger, status):
    ledger.reserve(
        request_id="call:unresolved-zero",
        run_id="run:unresolved-zero",
        case_id="case:unresolved-zero",
        case_revision=0,
        attempt=1,
        model="gpt-4o-mini",
        phase="development",
        amount_usd=Decimal("0"),
    )
    if status == "uncertain":
        ledger.mark_uncertain("call:unresolved-zero", error_code="ProviderRequestFailed")
    before = ledger._path.read_bytes()
    assert ledger.snapshot().reserved_usd == ledger.snapshot().uncertain_usd == 0
    with pytest.raises(ValueError, match="LiveAccountingUnresolved"):
        live.LiveEvaluationAdapters(
            index_path=index[0],
            snapshot_id=index[1],
            manifest_sha256=index[2],
            ledger=ledger,
            config=config(),
        )
    assert ledger._path.read_bytes() == before
    assert ledger.get("call:unresolved-zero").status == status


def test_positive_budget_smaller_than_configured_request_bound_stops_before_key(
    index, tmp_path, monkeypatch
):
    monkeypatch.setattr(live, "ROOT", tmp_path)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    ledger = BudgetLedger.create(
        runtime / "budget.sqlite3", limit_usd=Decimal("0.001"), opening_spend_usd=Decimal("0")
    )

    class KeyGuard(dict):
        def get(self, name, default=None):
            if name == "METIS_API_KEY":
                raise AssertionError("Insufficient request capacity must precede credential lookup")
            return super().get(name, default)

    values = KeyGuard(
        METIS_LIVE_ENABLED="true",
        AGENT_EVAL_INDEX=str(index[0]),
        AGENT_EVAL_SNAPSHOT=index[1],
        AGENT_EVAL_MANIFEST_SHA256=index[2],
    )
    before = ledger._path.read_bytes()
    with pytest.raises(ValueError, match="LiveBudgetUnavailable"):
        live.configured_factory(values)
    assert ledger._path.read_bytes() == before


def test_live_factory_drives_existing_runner_and_uses_actual_index_not_fixture_gold(index, ledger):
    with offline_network():
        factory, transports = adapters(index, ledger)
        receipt = runner.run(
            [ROOT / "data/evaluation/dev/pilot-12782.json"], mode="live", live=factory
        )
    assert receipt["mode"] == "live" and receipt["quality_claim"] is False
    assert receipt["summary"]["turns"] == 4 and receipt["summary"]["coverage_complete"] is True
    assert len(transports) == 4 and all(item.close_calls == 1 for item in transports)
    assert factory.active_clients == 0
    assert KEY not in json.dumps(receipt)
    for step in receipt["cases"][0]["steps"]:
        if "usage" in step:
            assert step["proposal"]["review_handoff"]["evidence"]["snapshot_id"] == index[1]


def test_production_catalog_backward_compatibility_and_current_unknown_only():
    assert runtime_catalog is prior_catalog
    fact = Fact(name="streamlit_version", value="1.50.0", source_ref="user:1", turn_id="turn:1")
    case = CaseState(case_id="case:catalog", facts=(fact,), unknowns=("parent_callback_code",))
    evidence = EvidenceBundle(snapshot_id="no-fixture-input")
    registered = caller_catalog(
        case, "The reduced example works.", evidence, definitions=(CALLBACK,)
    )
    assert [gap.name for gap in registered.gaps if gap.kind == "user"] == ["parent_callback_code"]
    supplied = Fact(
        name="parent_callback_code", value="Provided code", source_ref="user:2", turn_id="turn:2"
    )
    known = case.model_copy(update={"facts": (fact, supplied)})
    assert not any(
        gap.kind == "user"
        for gap in caller_catalog(
            known, "Callback is missing in prose.", evidence, definitions=(CALLBACK,)
        ).gaps
    )
    absent = case.model_copy(update={"unknowns": ()})
    assert not any(
        gap.kind == "user"
        for gap in caller_catalog(
            absent, "No callback in prose.", evidence, definitions=(CALLBACK,)
        ).gaps
    )


@pytest.mark.parametrize(
    "definitions",
    [
        [{**CALLBACK.model_dump(), "gold": "answer"}],
        [CALLBACK, CALLBACK],
        [{**CALLBACK.model_dump(), "kind": "source", "question": None}],
        [{**CALLBACK.model_dump(), "name": "streamlit_version"}],
    ],
)
def test_user_vocabulary_rejects_hidden_gold_source_gaps_and_overrides(definitions):
    with pytest.raises(ValueError, match="UserGapVocabularyInvalid"):
        validate_user_gaps(definitions)


def test_missing_designated_ledger_reports_unavailable_without_creating_it(
    index, tmp_path, monkeypatch
):
    monkeypatch.setattr(live, "ROOT", tmp_path)
    (tmp_path / "runtime").mkdir()
    values = {
        "METIS_LIVE_ENABLED": "true",
        "AGENT_EVAL_INDEX": str(index[0]),
        "AGENT_EVAL_SNAPSHOT": index[1],
        "AGENT_EVAL_MANIFEST_SHA256": index[2],
    }
    with pytest.raises(ValueError, match="^LiveLedgerUnavailable$"):
        live.configured_factory(values)
    assert not (tmp_path / "runtime/budget.sqlite3").exists()
