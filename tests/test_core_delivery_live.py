"""Selected delivery integration with stub index, intercepted HTTP and temp ledger."""

import json
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest

from agent_app.contracts import CaseState, EvidenceBundle, ReasoningContext
from agent_app.evaluation import live
from agent_app.llm.budget import BudgetLedger
from agent_app.llm.config import MetisConfig
from agent_app.orchestration.core_delivery import DELIVERY_PROFILE_ID, delivery_recipe
from agent_app.orchestration.ports import ReasoningStopped
from agent_app.reasoning.catalog import load_user_gap_vocabulary

KEY = "synthetic-core-delivery-key"


def selected_config(**updates):
    public = dict(delivery_recipe()["metis"])
    public["max_request_usd"] = Decimal(public["max_request_usd"])
    return MetisConfig(api_key=KEY, phase="development", **(public | updates))


def vocabulary():
    return load_user_gap_vocabulary(str(live.ROOT / "config/user-gap-support-dev-v1.json"))


@pytest.fixture
def setup(tmp_path, monkeypatch):
    ledger = BudgetLedger.create(
        tmp_path / "ledger.sqlite3", limit_usd=Decimal("1"), opening_spend_usd=Decimal("0")
    )
    client = SimpleNamespace(verifications=0)

    def verify():
        client.verifications += 1

    client.verify = verify
    monkeypatch.setattr(live, "_verified_index", lambda *args: client)
    monkeypatch.setattr(live, "StreamlitRetriever", lambda *args, **kwargs: object())
    monkeypatch.setattr(live, "ChromaRetrieverAdapter", lambda *args, **kwargs: object())
    sends = []

    def response(request):
        sends.append(request)
        payload = json.loads(json.loads(request.content)["messages"][1]["content"])
        plan = {
            "context_sha256": payload["request"]["context_sha256"],
            "decision": "ask",
            "question_name": "streamlit_version",
            "sources": [],
        }
        return httpx.Response(
            200,
            json={
                "model": "gpt-4o-mini-2024-07-18",
                "usage": {"prompt_tokens": 125, "completion_tokens": 75, "total_tokens": 200},
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": json.dumps(plan)},
                    }
                ],
            },
        )

    def factory(**updates):
        arguments = dict(
            index_path=tmp_path / "stub-index",
            snapshot_id="docs-pilot-" + "a" * 64,
            manifest_sha256="b" * 64,
            ledger=ledger,
            config=selected_config(),
            top_k=5,
            retrieval_profile="candidate_relevance_v1",
            user_gaps=vocabulary(),
            core_profile=DELIVERY_PROFILE_ID,
            transport_factory=lambda: httpx.MockTransport(response),
        )
        return live.LiveEvaluationAdapters(**(arguments | updates))

    return factory, ledger, client, sends


def context():
    return ReasoningContext(
        run_id="neutral-run", case_id="neutral-case", case_revision=0, attempt_index=1
    )


def test_selected_binding_is_detached_and_only_selected_observations_include_it(setup):
    factory, ledger, client, sends = setup
    owner = factory()
    binding = owner.core_binding
    binding["renderer_policy"] = "changed-export"
    assert owner.core_binding["renderer_policy"] == "legacy_v1"
    assert "core_binding" not in owner.config
    ports = owner.for_case("neutral-case")
    assert ports.reasoner.review_brief is False
    value = ports.reasoner.analyze(
        CaseState(case_id="neutral-case"),
        "Neutral report.",
        EvidenceBundle(snapshot_id="neutral"),
        context=context(),
    )
    assert value.decision == "ask" and len(sends) == 1
    (row,) = owner.observations_for_contexts((context(),))
    assert row["core_binding"] == owner.core_binding
    assert KEY not in json.dumps(row)
    row["core_binding"]["renderer_policy"] = "changed-observation-export"
    assert owner.core_binding["renderer_policy"] == "legacy_v1"
    ports.cleanup()
    owner.close()


def test_omitted_profile_preserves_legacy_metadata_and_observation_shape(setup):
    factory, ledger, client, sends = setup
    owner = factory(core_profile=None)
    assert owner.core_binding is None
    assert set(owner.config) == {
        "model",
        "snapshot_id",
        "prompt_policy",
        "response_mode",
        "phase",
        "adapter_id",
        "retriever_id",
    }
    ports = owner.for_case("neutral-case")
    ports.reasoner.analyze(
        CaseState(case_id="neutral-case"),
        "Neutral report.",
        EvidenceBundle(snapshot_id="neutral"),
        context=context(),
    )
    assert "core_binding" not in owner.observations_for_contexts((context(),))[0]
    ports.cleanup()
    owner.close()


@pytest.mark.parametrize(
    "target",
    ["owner", "gateway", "sender", "transport", "renderer", "gaps", "top_k", "profile_none"],
)
def test_selected_drift_stops_before_latest_observation_reservation_or_send(setup, target):
    factory, ledger, client, sends = setup
    owner = factory()
    ports = owner.for_case("neutral-case")
    run = ports.reasoner.planner
    changed = selected_config(grounded_json_object=True)
    if target == "owner":
        owner._config = changed
    elif target == "gateway":
        run.gateway.config = changed
    elif target == "sender":
        run.gateway.reasoner.config = changed
    elif target == "transport":
        run.transport.config = changed
    elif target == "renderer":
        ports.reasoner.review_brief = True
    elif target == "gaps":
        owner._gaps = ()
    elif target == "top_k":
        owner._top_k = 1
    else:
        owner._core_profile = None
    before = ledger._path.read_bytes()
    request = ports.reasoner.request_factory(
        CaseState(case_id="neutral-case"), "Neutral report.", EvidenceBundle(snapshot_id="neutral")
    )
    with pytest.raises(ReasoningStopped) as error:
        run.plan(request, context=context())
    assert error.value.code == "ProviderRequestFailed"
    assert run.latest is None and owner._observations == [] and sends == []
    assert ledger._path.read_bytes() == before
    ports.cleanup()
    owner.close()


def test_allocation_rechecks_before_index_verify_and_transport(setup):
    factory, ledger, client, sends = setup
    owner = factory()
    owner._ask_source_background = True
    with pytest.raises(ValueError, match="^CoreDeliveryConfigurationMismatch$"):
        owner.for_case("neutral-case")
    assert client.verifications == 0 and sends == [] and owner.active_clients == 0
    owner.close()


@pytest.mark.parametrize("target", ["unknown_profile", "config", "gap_extra", "gap_private"])
def test_selected_raw_constructor_rejects_before_budget_index_or_serialization(
    setup, monkeypatch, target
):
    factory, ledger, client, sends = setup
    changes = {}
    if target == "unknown_profile":
        changes["core_profile"] = "unknown-sensitive-profile"
    elif target == "config":
        value = selected_config()
        object.__setattr__(value, "sensitive_hidden", "sensitive-value")
        changes["config"] = value
    else:
        gaps = vocabulary()
        if target == "gap_extra":
            object.__setattr__(gaps[0], "sensitive_hidden", "sensitive-value")
        else:
            object.__setattr__(gaps[0], "__pydantic_private__", {"sensitive": "value"})
        changes["user_gaps"] = gaps
    calls = []

    def forbidden(*args, **kwargs):
        calls.append("forbidden")
        raise AssertionError("Must reject before I/O")

    monkeypatch.setattr(live, "_budget_guard", forbidden)
    monkeypatch.setattr(live, "_verified_index", forbidden)
    with pytest.raises(ValueError, match="^CoreDeliveryConfigurationMismatch$"):
        factory(**changes)
    assert calls == []


def test_configured_selection_checks_halt_before_key_or_index(tmp_path, monkeypatch):
    monkeypatch.setattr(live, "ROOT", tmp_path)
    (tmp_path / "runtime").mkdir()
    ledger = BudgetLedger.create(
        tmp_path / "runtime/budget.sqlite3", limit_usd=Decimal("1"), opening_spend_usd=Decimal("0")
    )
    ledger.halt()

    class Values(dict):
        def get(self, key, default=None):
            assert key != "METIS_API_KEY"
            return super().get(key, default)

    calls = []
    monkeypatch.setattr(live, "_verified_index", lambda *args: calls.append("index"))
    with pytest.raises(ValueError, match="^LiveLedgerHalted$"):
        live.configured_factory(
            Values(AGENT_CORE_PROFILE=DELIVERY_PROFILE_ID, METIS_LIVE_ENABLED="true")
        )
    assert calls == []


def test_configured_selection_validates_semantic_vocabulary_before_key(tmp_path, monkeypatch):
    monkeypatch.setattr(live, "ROOT", tmp_path)
    (tmp_path / "runtime").mkdir()
    BudgetLedger.create(
        tmp_path / "runtime/budget.sqlite3", limit_usd=Decimal("1"), opening_spend_usd=Decimal("0")
    )
    monkeypatch.setattr(live, "_verified_index", lambda *args: object())
    monkeypatch.setattr(live, "load_user_gap_vocabulary", lambda _path: ())
    keys = []

    class Values(dict):
        def get(self, key, default=None):
            if key == "METIS_API_KEY":
                keys.append(key)
                raise AssertionError("No credential read on mismatch")
            return super().get(key, default)

    values = Values(
        AGENT_CORE_PROFILE=DELIVERY_PROFILE_ID,
        METIS_LIVE_ENABLED="true",
        AGENT_EVAL_INDEX="stub",
        AGENT_EVAL_SNAPSHOT="docs-pilot-" + "a" * 64,
        AGENT_EVAL_MANIFEST_SHA256="b" * 64,
    )
    with pytest.raises(ValueError, match="^CoreDeliveryConfigurationMismatch$"):
        live.configured_factory(values)
    assert keys == []
