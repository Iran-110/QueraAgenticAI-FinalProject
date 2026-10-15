"""Trusted JSON/display flags across actual native retrieval, HTTP and SQLite."""

import json
from copy import deepcopy

import httpx
import pytest
import test_candidate_live_profile as persistent_controls
from test_ask_background_quality_profile import prepared
from test_budget_quarantine_scope import multiple_holds as multiple_holds
from test_evaluation_live import index as index
from test_evaluation_live import ledger as ledger
from test_real_index_probe import ARMS, ROOT
from test_real_index_probe import native_indexes as native_indexes

from agent_app.evaluation.routes import ConditionalRoutesRejected, RouteGraph
from agent_app.reasoning.catalog import load_user_gap_vocabulary
from agent_app.testing.dev_three_model_probe import DevProbeRejected, ledger_observation
from agent_app.testing.http_pilot_runtime import offline_network
from agent_app.testing.real_index_probe import run_real_index_batch
from agent_app.testing.stability_probe import VOCABULARY


def test_both_flags_keep_persistent_correction_stale_approval_restart_retry(
    tmp_path, native_indexes, ledger, monkeypatch
):
    original_config = persistent_controls.config
    original_factory = persistent_controls.candidate_factory
    original_response = persistent_controls.ask_response
    sends = []

    def response(request, seen):
        assert json.loads(request.content)["response_format"] == {"type": "json_object"}
        sends.append(request)
        return original_response(request, seen)

    monkeypatch.setattr(
        persistent_controls, "config", lambda: original_config(grounded_json_object=True)
    )
    monkeypatch.setattr(
        persistent_controls,
        "candidate_factory",
        lambda *args, **kwargs: original_factory(*args, **kwargs, concise_user_draft=True),
    )
    monkeypatch.setattr(persistent_controls, "ask_response", response)
    persistent_controls.test_candidate_persistent_http_correction_restart_and_retry_bind_current_text(
        tmp_path, native_indexes, ledger, monkeypatch
    )
    assert len(sends) == 2


@pytest.mark.parametrize("json_mode", [False, True])
def test_quality_http_transmits_mode_and_binds_exact_concise_display(
    multiple_holds, native_indexes, json_mode
):
    ledger, protocol, batch, fixtures, config = prepared(multiple_holds)
    batch["jobs"][0].update(grounded_json_object=json_mode, concise_user_draft=True)
    before = ledger_observation(ledger._path)
    bodies = []

    def respond(request):
        body = json.loads(request.content)
        bodies.append(body)
        assert (body.get("response_format") == {"type": "json_object"}) is json_mode
        payload = json.loads(body["messages"][1]["content"])
        current = payload["request"]
        assert "concise_user_draft" not in payload and "grounded_json_object" not in payload
        known = any(
            fact["name"] == "streamlit_version" and fact["status"] == "active"
            for fact in current["case"]["facts"]
        )
        selected = (
            [
                i
                for i, hit in enumerate(current["evidence"]["hits"])
                if "1.50.0" in hit["applicable_versions"]
            ][:1]
            if known
            else []
        )
        plan = dict(
            context_sha256=current["context_sha256"],
            decision="ask",
            question_name="parent_callback_code" if known else "streamlit_version",
            sources=selected,
        )
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
        result = run_real_index_batch(
            protocol,
            batch,
            fixtures,
            load_user_gap_vocabulary(str(ROOT / VOCABULARY)),
            ledger,
            config,
            before,
            {"candidate_profile": native_indexes[ARMS[1]]},
            underlying=httpx.MockTransport(respond),
        )
    assert result["actual_sends"] == len(bodies) == 2
    assert result["completed_routes"] == 1
    assert {row["wire_response_format"] for row in result["provider_sends"]} == {
        "json_object" if json_mode else "absent"
    }
    step = result["jobs"][0]["steps"][-1]
    proposal = step["proposal"]
    view = {
        "case_id": proposal["case_id"],
        "case_revision": proposal["case_revision"],
        "pending": proposal,
    }
    graph = RouteGraph.from_fixture(
        fixtures["dev-case-a"].data, allow_source_background=True, concise_user_draft=True
    )
    assert graph.select("version", step, view) is not None
    assert (
        RouteGraph.from_fixture(fixtures["dev-case-a"].data, allow_source_background=True).select(
            "version", step, view
        )
        is None
    )
    tampered = deepcopy(step)
    tampered["proposal"]["review_handoff"]["handoff_sha256"] = "0" * 64
    assert graph.select("version", tampered, view) is None


@pytest.mark.parametrize("field", ["grounded_json_object", "concise_user_draft"])
@pytest.mark.parametrize("value", [1, 0, "true", None, [], {}])
def test_research_flags_reject_before_transport_or_reservation(
    multiple_holds, native_indexes, field, value
):
    ledger, protocol, batch, fixtures, config = prepared(multiple_holds)
    batch["jobs"][0][field] = value
    before = ledger_observation(ledger._path)
    with offline_network(), pytest.raises(DevProbeRejected):
        run_real_index_batch(
            protocol,
            batch,
            fixtures,
            load_user_gap_vocabulary(str(ROOT / VOCABULARY)),
            ledger,
            config,
            before,
            {"candidate_profile": native_indexes[ARMS[1]]},
            underlying=httpx.MockTransport(lambda _: pytest.fail("must not send")),
        )
    assert ledger_observation(ledger._path) == before


@pytest.mark.parametrize("value", [1, "true", None])
def test_route_display_policy_is_strict_local_configuration(value):
    with pytest.raises(ConditionalRoutesRejected):
        RouteGraph.from_fixture({}, concise_user_draft=value)


def test_configured_flags_remain_trusted_lazy_and_distinct(tmp_path, index, monkeypatch):
    from decimal import Decimal

    from agent_app.evaluation import live
    from agent_app.llm.budget import BudgetLedger

    runtime = tmp_path / "runtime"
    runtime.mkdir()
    BudgetLedger.create(
        runtime / "budget.sqlite3", limit_usd=Decimal("1"), opening_spend_usd=Decimal("0")
    )
    monkeypatch.setattr(live, "ROOT", tmp_path)
    monkeypatch.setattr(httpx, "HTTPTransport", lambda **_: pytest.fail("startup sent"))
    values = {
        "METIS_LIVE_ENABLED": "true",
        "METIS_API_KEY": "public-synthetic-key",
        "AGENT_EVAL_INDEX": str(index[0]),
        "AGENT_EVAL_SNAPSHOT": index[1],
        "AGENT_EVAL_MANIFEST_SHA256": index[2],
        "AGENT_EVAL_TOP_K": "5",
        "AGENT_RETRIEVAL_PROFILE": "candidate_relevance_v1",
        "AGENT_GROUNDED_ASK_SOURCE_BACKGROUND": "true",
        "AGENT_GROUNDED_CONCISE_USER_DRAFT": "true",
        "METIS_GROUNDED_JSON_OBJECT": "true",
    }
    with offline_network():
        factory = live.configured_factory(values)
        assert factory._config.grounded_json_object is True
        assert factory.concise_user_draft is True and factory.active_clients == 0
        assert factory.config["adapter_id"].endswith("_json_object_v1_concise_draft_v1")
        factory.close()
        for field in ("METIS_GROUNDED_JSON_OBJECT", "AGENT_GROUNDED_CONCISE_USER_DRAFT"):
            with pytest.raises(ValueError, match="^LiveEvaluationConfigurationInvalid$"):
                live.configured_factory({**values, field: "True"})


def test_invalid_display_flag_fails_before_ledger(monkeypatch):
    from agent_app.evaluation import live

    monkeypatch.setattr(live, "_budget_guard", lambda _: pytest.fail("reached ledger"))
    with pytest.raises(ValueError, match="^LiveEvaluationConfigurationInvalid$"):
        live.LiveEvaluationAdapters(
            index_path="unused",
            snapshot_id="unused",
            manifest_sha256="unused",
            ledger=None,
            config=None,
            concise_user_draft="true",
        )
