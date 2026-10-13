"""Registered adaptive branches through HTTP; every provider send is mocked."""

import hashlib
import json
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from test_eval_runner import FakeLive
from test_eval_runner_final_preflight import runnable_bundle as runnable_bundle
from test_evaluation_live import adapters as real_adapters
from test_evaluation_live import index as index
from test_evaluation_live import ledger as ledger
from test_evaluation_live import provider_response
from test_evaluation_preflight import bundle as bundle

from agent_app import api
from agent_app.contracts import EvidenceBundle, ReasoningContext
from agent_app.evaluation import runner
from agent_app.evaluation.routes import MAX_ROUTE_NODES, RouteGraph
from agent_app.llm.budget import BudgetLedger
from agent_app.llm.config import MetisConfig
from agent_app.llm.metis import MetisReasoner
from agent_app.orchestration.intake import STREAMLIT_VERSION_QUESTION
from agent_app.testing.http_pilot_runtime import offline_network

SOURCE = Path("data/evaluation/evidence/synthetic-v1.json")
CALLBACK_QUESTION = "Can you share the parent callback?"
FUTURE_CALLBACK = "FUTURE_CALLBACK_RESPONSE def callback(): return 42"
FUTURE_VERSION = "1.50.0"
FUTURE_CORRECTION = "FUTURE_CORRECTION_MARKER: correction to version 1.49.0."
PRIVATE_GOLD = "GOLD_NOT_A_MODEL_INPUT"


def ask(target):
    question = (
        STREAMLIT_VERSION_QUESTION.question if target == "streamlit_version" else CALLBACK_QUESTION
    )
    return {
        "decision": "ask",
        "user_draft": question,
        "next_question": question,
        "missing_info": [target],
        "maintainer_summary": "Synthetic question for a missing user fact.",
        "rationale": "The user can clarify this current unknown.",
    }


def escalation():
    return {
        "decision": "escalate",
        "user_draft": "Please have a maintainer review the synthetic case.",
        "maintainer_summary": "Synthetic fixture only.",
        "rationale": "No verified fix is established.",
    }


def fixture(target="streamlit_version"):
    source = runner.ROOT / SOURCE
    turns = []
    for identifier, message, bundle_name, revision in (
        (
            "initial",
            "A widget changes after rerun; the version and parent callback are unknown.",
            "counter",
            1,
        ),
        ("callback", FUTURE_CALLBACK, "counter", 2),
        ("version", FUTURE_VERSION, "counter", 2),
        ("correction", FUTURE_CORRECTION, "uploader", 3),
    ):
        turns.append(
            {
                "id": identifier,
                "visible": {"message": message},
                "conversation_source": "developer_authored_synthetic",
                "evidence_bundle": bundle_name,
                "agent_script": ask(target) if identifier == "initial" else escalation(),
                "maintainer": {"decision": "approve" if identifier == "initial" else "none"},
                "gold": {
                    "acceptable_decisions": ["ask", "escalate"]
                    if identifier == "initial"
                    else ["escalate"],
                    "note": PRIVATE_GOLD,
                },
                "expect": {
                    "revision": revision,
                    "pending_decision": "ask" if identifier == "initial" else "escalate",
                },
            }
        )
    turns[0]["visible"]["unknowns"] = ["streamlit_version", "parent_callback_code"]
    turns[0]["visible"]["reported_facts"] = [{"name": "python_version", "value": "3.12.9"}]
    turns[0]["gold"]["gaps"] = [
        {
            "name": "streamlit_version",
            "kind": "user",
            "question": STREAMLIT_VERSION_QUESTION.question,
            "necessity": "Check applicable versions.",
        },
        {
            "name": "parent_callback_code",
            "kind": "user",
            "question": CALLBACK_QUESTION,
            "necessity": "Inspect user-supplied callback code.",
        },
    ]
    turns[1]["visible"]["reported_facts"] = [
        {"name": "parent_callback_code", "value": FUTURE_CALLBACK}
    ]
    turns[2]["visible"]["reply_to_approved_question"] = True
    turns[3]["visible"]["reported_facts"] = [{"name": "streamlit_version", "value": "1.49.0"}]
    turns[3]["expect"].update(
        active_facts={"streamlit_version": "1.49.0", "python_version": "3.12.9"},
        superseded_values={"streamlit_version": ["1.50.0"]},
        excluded_chunks=["syn-counter-doc"],
    )
    return {
        "fixture_id": "synthetic-registered-routes-v1",
        "registered_before_first_run": True,
        "case": {
            "case_id": "dev-routes",
            "split": "dev",
            "family_issue_ids": [12782, 12629],
            "test_eligible": False,
        },
        "evidence_source": {
            "path": str(SOURCE),
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "bundles_used": ["counter", "uploader"],
        },
        "turns": turns,
        "evaluation": {
            "coverage": {
                "turn_ids": [turn["id"] for turn in turns],
                "routes": [
                    {
                        "from_turn": "initial",
                        "to_turn": "callback",
                        "guard": {"decision": "ask", "question_target": "parent_callback_code"},
                    },
                    {
                        "from_turn": "initial",
                        "to_turn": "version",
                        "guard": {"decision": "ask", "question_target": "streamlit_version"},
                    },
                    {"from_turn": "initial", "to_turn": None, "guard": {"decision": "escalate"}},
                    {"from_turn": "callback", "to_turn": None, "guard": {"decision": "escalate"}},
                    {
                        "from_turn": "version",
                        "to_turn": "correction",
                        "guard": {"decision": "escalate"},
                    },
                    {"from_turn": "correction", "to_turn": None, "guard": {"decision": "escalate"}},
                ],
            }
        },
    }


def write(tmp_path, data):
    path = tmp_path / "routes.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def failed(receipt):
    return [check for case in receipt["cases"] for check in case["checks"] if not check["passed"]]


class MockLive:
    def __init__(self, tmp_path, target="streamlit_version", *, malformed_first=False):
        self.ledger = BudgetLedger.create(
            tmp_path / "temporary-ledger.sqlite3",
            limit_usd=Decimal("5"),
            opening_spend_usd=Decimal("0"),
        )
        self.config = {"model": "gpt-4o-mini", "snapshot_id": "synthetic-eval-v1"}
        self.target, self.wire, self.ports, self.case_ids = target, [], [], []
        self.malformed_first = malformed_first
        self.closed = []
        self.bundles = {
            name: EvidenceBundle.model_validate(bundle)
            for name, bundle in json.loads((runner.ROOT / SOURCE).read_bytes())[
                "evidence_bundles"
            ].items()
        }

    def for_case(self, case_id):
        self.case_ids.append(case_id)
        owner = self

        class Retriever:
            def search(self, request):
                return owner.bundles[
                    "uploader"
                    if any("1.49.0" in query.casefold() for query in request.queries)
                    else "counter"
                ]

        def respond(request):
            wire = json.loads(request.content)
            self.wire.append(wire)
            data = json.loads(wire["messages"][-1]["content"])
            if data["case"]["case_revision"] == 1:
                analysis = escalation() if self.target == "escalate" else ask(self.target)
                if self.target == "ambiguous":
                    analysis.update(
                        user_draft="Which version and callback?",
                        next_question="Which version and callback?",
                        missing_info=["streamlit_version", "parent_callback_code"],
                    )
            else:
                analysis = escalation()
            return httpx.Response(
                200,
                json={
                    "model": "gpt-4o-mini-2024-07-18",
                    "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {
                                "role": "assistant",
                                "content": "{broken"
                                if self.malformed_first and len(self.wire) == 1
                                else json.dumps(analysis),
                            },
                        }
                    ],
                },
            )

        port = MetisReasoner(
            MetisConfig(
                api_key="public-synthetic-routes-key", live_enabled=True, phase="evaluation"
            ),
            self.ledger,
            transport=httpx.MockTransport(respond),
        )
        self.ports.append(port)

        def cleanup():
            self.closed.append(port)
            port.close()

        return api.RunAdapters(
            Retriever(), port, snapshot_id=self.config["snapshot_id"], cleanup=cleanup
        )


@pytest.mark.parametrize(
    "target,visited",
    [
        ("parent_callback_code", ["initial", "callback"]),
        ("streamlit_version", ["initial", "version", "correction"]),
        ("escalate", ["initial"]),
    ],
)
def test_live_selects_only_actual_registered_path_with_current_state_and_metered_replay(
    tmp_path, target, visited
):
    live = MockLive(tmp_path, target)
    path = write(tmp_path, fixture())
    with offline_network():
        receipt = runner.run([path], mode="live", live=live, conditional_routes=True)
    assert failed(receipt) == []
    assert receipt["summary"]["coverage_complete"] is True
    assert receipt["summary"]["planned_turns"] == receipt["summary"]["turns"] == len(visited)
    assert receipt["summary"]["registered_turns"] == 4
    assert receipt["summary"]["completed_multi_turn_paths"] == (1 if len(visited) > 1 else 0)
    assert receipt["summary"]["completed_multi_turn_test_paths"] == 0
    route = receipt["cases"][0]["conditional_routes"]
    assert route["selected_turn_ids"] == route["executed_turn_ids"] == visited
    assert set(route["unvisited_registered_turn_ids"]) == {
        "initial",
        "callback",
        "version",
        "correction",
    } - set(visited)
    assert len(live.case_ids) == len(live.wire) == len(live.closed) == len(visited)
    assert all(port.client.is_closed for port in live.ports)
    assert receipt["summary"]["accounting_complete"] is True
    assert Decimal(receipt["summary"]["cost_usd_total"]) == live.ledger.snapshot().settled_usd
    assert all(PRIVATE_GOLD not in json.dumps(wire) for wire in live.wire)
    assert all(
        not {"gold", "evaluation", "routes", "agent_script", "expect"}.intersection(
            json.loads(wire["messages"][-1]["content"])
        )
        for wire in live.wire
    )
    assert FUTURE_CALLBACK not in json.dumps(live.wire[0]) and FUTURE_CORRECTION not in json.dumps(
        live.wire[0]
    )
    if target == "parent_callback_code":
        assert FUTURE_CORRECTION not in json.dumps(live.wire)
        active = [
            fact
            for fact in receipt["cases"][0]["steps"][-1]["view_after"]["facts"]
            if fact["status"] == "active"
        ]
        assert any(
            fact["name"] == "parent_callback_code" and fact["value"] == FUTURE_CALLBACK
            for fact in active
        )
    if target == "streamlit_version":
        final = receipt["cases"][0]["steps"][-1]["proposal"]["review_handoff"]
        assert {hit["chunk_id"] for hit in final["evidence"]["hits"]} == {"syn-uploader-doc"}
        assert any(
            fact["name"] == "streamlit_version"
            and fact["value"] == "1.50.0"
            and fact["status"] == "superseded"
            for fact in final["case"]["facts"]
        )
    assert receipt["quality_claim"] is False


def test_offline_graph_uses_registered_script_only_for_selected_nodes(tmp_path):
    with offline_network():
        receipt = runner.run(
            [write(tmp_path, fixture("parent_callback_code"))], conditional_routes=True
        )
    assert failed(receipt) == []
    assert receipt["cases"][0]["conditional_routes"]["selected_turn_ids"] == ["initial", "callback"]
    assert (
        receipt["summary"]["coverage_complete"] is True
        and receipt["summary"]["cost_usd_total"] == "0"
    )


@pytest.mark.parametrize(
    "maintainer",
    [
        {"decision": "none"},
        {"decision": "reject"},
        {"decision": "edit", "edited_draft": CALLBACK_QUESTION},
        {
            "decision": "edit",
            "edited_draft": "Can you give the browser instead?",
            "then": "approve",
        },
    ],
)
def test_unreleased_rejected_or_mismatched_edited_question_never_feeds_future_reply(
    tmp_path, maintainer
):
    data = fixture("parent_callback_code")
    data["turns"][0]["maintainer"] = maintainer
    live = MockLive(tmp_path, "parent_callback_code")
    with offline_network():
        receipt = runner.run(
            [write(tmp_path, data)], mode="live", live=live, conditional_routes=True
        )
    assert failed(receipt) == []
    assert len(live.wire) == len(live.case_ids) == 1
    assert receipt["summary"]["fixture_branches_unavailable"] == 1
    assert not receipt["summary"]["coverage_complete"]
    assert FUTURE_CALLBACK not in json.dumps(live.wire)


def test_approved_registered_edit_uses_edited_proposal_and_keeps_model_original(tmp_path):
    data = fixture("parent_callback_code")
    data["turns"][0]["maintainer"] = {
        "decision": "edit",
        "edited_draft": CALLBACK_QUESTION,
        "then": "approve",
    }
    live = MockLive(tmp_path, "parent_callback_code")
    with offline_network():
        receipt = runner.run(
            [write(tmp_path, data)], mode="live", live=live, conditional_routes=True
        )
    first = receipt["cases"][0]["steps"][0]
    assert first["route_selection"]["proposal_id"] == first["edited_proposal"]["proposal_id"]
    assert first["proposal"]["proposal_id"] != first["edited_proposal"]["proposal_id"]
    assert first["route_selection"]["edited_proposal_selected"] is True
    assert receipt["summary"]["coverage_complete"] is True


def test_unregistered_ambiguous_question_stops_as_coverage_without_second_paid_attempt(tmp_path):
    live = MockLive(tmp_path, "ambiguous")
    with offline_network():
        receipt = runner.run(
            [write(tmp_path, fixture())], mode="live", live=live, conditional_routes=True
        )
    assert failed(receipt) == []
    assert receipt["summary"]["coverage_complete"] is False
    assert len(live.wire) == 1 and receipt["summary"]["fixture_branches_unavailable"] == 1


def test_terminal_pending_ask_is_completed_path_without_auto_approval(tmp_path):
    data = fixture("parent_callback_code")
    data["turns"] = data["turns"][:1]
    data["turns"][0]["maintainer"] = {"decision": "none"}
    data["evaluation"]["coverage"] = {
        "turn_ids": ["initial"],
        "routes": [
            {
                "from_turn": "initial",
                "to_turn": None,
                "guard": {"decision": "ask", "question_target": "parent_callback_code"},
            },
            {"from_turn": "initial", "to_turn": None, "guard": {"decision": "escalate"}},
        ],
    }
    live = MockLive(tmp_path, "parent_callback_code")
    with offline_network():
        receipt = runner.run(
            [write(tmp_path, data)], mode="live", live=live, conditional_routes=True
        )
    assert receipt["summary"]["coverage_complete"] is True
    step = receipt["cases"][0]["steps"][0]
    assert step["view_after"]["pending"] and step["released_outputs"] == []
    assert step["route_selection"]["question_was_released"] is False


@pytest.mark.parametrize(
    "change",
    [
        "backward",
        "self",
        "unknown_target",
        "duplicate_guard",
        "orphan",
        "source_gap",
        "nonversion_short_reply",
        "extra_guard",
        "too_many_nodes",
    ],
)
def test_malformed_graph_rejected_before_live_factory_and_without_raw_diagnostic(
    tmp_path, monkeypatch, capsys, change
):
    data = fixture()
    routes = data["evaluation"]["coverage"]["routes"]
    if change == "backward":
        routes[-1]["to_turn"] = "initial"
    elif change == "self":
        routes[-1]["to_turn"] = "correction"
    elif change == "unknown_target":
        routes[-1]["to_turn"] = "PRIVATE_BAD_TARGET"
    elif change == "duplicate_guard":
        routes.append(deepcopy(routes[0]))
    elif change == "orphan":
        routes[0]["to_turn"] = None
    elif change == "source_gap":
        data["turns"][0]["gold"]["gaps"][1]["kind"] = "source"
    elif change == "nonversion_short_reply":
        data["turns"][1]["visible"] = {"message": "3.12.9", "reply_to_approved_question": True}
    elif change == "extra_guard":
        routes[0]["guard"]["PRIVATE_SECRET"] = "PRIVATE_VALUE"
    else:
        data["turns"] += [deepcopy(data["turns"][0])] * (MAX_ROUTE_NODES + 1)
    calls = []
    monkeypatch.setattr(runner, "_load_live", lambda spec: calls.append(spec))
    assert (
        runner.main(
            [
                str(write(tmp_path, data)),
                "--mode",
                "live",
                "--adapters",
                "private:factory",
                "--conditional-routes",
            ]
        )
        == 1
    )
    assert calls == []
    assert json.loads(capsys.readouterr().err) == {"code": "ConditionalRoutesRejected"}


def test_legacy_sequential_mode_and_narrow_version_reply_guard_remain_unchanged(tmp_path):
    data = fixture("parent_callback_code")
    live = MockLive(tmp_path, "parent_callback_code")
    with offline_network():
        receipt = runner.run([write(tmp_path, data)], mode="live", live=live)
    assert "registered_turns" not in receipt["summary"]
    assert receipt["summary"]["planned_turns"] == 4
    assert "conditional_routes" not in receipt["cases"][0]
    assert receipt["summary"]["coverage_complete"] is False
    assert receipt["cases"][0]["steps"][-1]["runner_stop"] == "FixtureBranchUnavailable"
    # Linear mode visits the callback then stops before binding a short version
    # to an unrelated released question, exactly as the legacy guard requires.
    assert len(live.wire) == 2


def test_live_final_packet_implies_conditional_routes_without_explicit_flag(
    runnable_bundle, tmp_path
):
    root = runnable_bundle["root"]
    selected = runnable_bundle["paths"][0]
    data = json.loads(selected.read_text(encoding="utf-8"))
    live = FakeLive(tmp_path, data)
    with offline_network():
        receipt = runner.run(
            [selected],
            mode="live",
            live=live,
            final_manifest=root / "manifest.json",
            final_corpus_manifest=root / "corpus.json",
            final_bundle=runnable_bundle["paths"],
            trusted_root=root,
        )
    assert receipt["summary"]["selected_path_complete"] is True
    assert receipt["cases"][0]["conditional_routes"]["registered_nodes"] == len(data["turns"])
    assert "registered conditional" in receipt["scoring"]["live_conversation"]
    assert receipt["quality_claim"] is False


class ObservedMockLive(MockLive):
    def observations_for_contexts(self, contexts):
        rows = []
        for context in contexts:
            request_id = runner.request_id_for(context)
            reservation = self.ledger.get(request_id)
            rows.append(
                {
                    "request_id": request_id,
                    "run_id": context.run_id,
                    "case_id": context.case_id,
                    "case_revision": context.case_revision,
                    "attempt_index": context.attempt_index,
                    "prompt_sha256": "a" * 64,
                    "requested_model": "gpt-4o-mini",
                    "verified_returned_model": "gpt-4o-mini-2024-07-18",
                    "http_send_started": True,
                    "http_status": 200,
                    "ledger_status": reservation.status,
                    "input_tokens": reservation.input_tokens,
                    "output_tokens": reservation.output_tokens,
                    "cost_estimated_usd": str(reservation.cost_usd),
                    "held_usd": "0",
                    "error_code": None,
                }
            )
        return rows


def test_optional_provider_observations_match_context_ledger_and_verified_serving_ids(tmp_path):
    live = ObservedMockLive(tmp_path, "parent_callback_code")
    with offline_network():
        receipt = runner.run(
            [write(tmp_path, fixture())], mode="live", live=live, conditional_routes=True
        )
    assert failed(receipt) == []
    for step in receipt["cases"][0]["steps"]:
        observation = step["usage"]["provider_observations"][0]
        request = step["usage"]["requests"][0]
        assert observation["request_id"] == request["request_id"]
        assert observation["verified_returned_model"] == "gpt-4o-mini-2024-07-18"
        assert observation["cost_estimated_usd"] == request["cost_usd"]
    assert "public-synthetic-routes-key" not in json.dumps(receipt)


@pytest.mark.parametrize(
    "change",
    [
        "unknown_field",
        "wrong_context",
        "wrong_revision",
        "wrong_attempt",
        "wrong_requested_model",
        "unsent_response",
        "unsent_status_only",
        "verified_without_status",
        "verified_failed_http",
        "wrong_serving_id",
        "duplicate",
        "bad_cost",
        "tokens",
        "exception",
    ],
)
def test_bad_provider_observation_cannot_export_unknown_payload_or_misattribute_cost(
    tmp_path, change
):
    live = ObservedMockLive(tmp_path, "parent_callback_code")
    original = live.observations_for_contexts

    def invalid(contexts):
        rows = original(contexts)
        if change == "unknown_field":
            rows[0]["PRIVATE_API_KEY"] = "PRIVATE_OBSERVATION_SECRET"
        elif change == "wrong_context":
            rows[0]["case_id"] = "PRIVATE_OTHER_CASE"
        elif change == "wrong_revision":
            rows[0]["case_revision"] += 1
        elif change == "wrong_attempt":
            rows[0]["attempt_index"] += 1
        elif change == "wrong_requested_model":
            rows[0]["requested_model"] = "gpt-4.1-mini"
        elif change == "unsent_response":
            rows[0]["http_send_started"] = False
        elif change == "unsent_status_only":
            rows[0]["http_send_started"] = False
            rows[0]["verified_returned_model"] = None
        elif change == "verified_without_status":
            rows[0]["http_status"] = None
        elif change == "verified_failed_http":
            rows[0]["http_status"] = 500
        elif change == "wrong_serving_id":
            rows[0]["verified_returned_model"] = "PRIVATE_UNVERIFIED_MODEL"
        elif change == "duplicate":
            rows.append(deepcopy(rows[0]))
        elif change == "bad_cost":
            rows[0]["cost_estimated_usd"] = "NaN"
        elif change == "tokens":
            rows[0]["input_tokens"] += 1
        else:
            raise RuntimeError("PRIVATE_CALLBACK_ERROR")
        return rows

    live.observations_for_contexts = invalid
    with offline_network():
        receipt = runner.run(
            [write(tmp_path, fixture())], mode="live", live=live, conditional_routes=True
        )
    assert "PRIVATE" not in json.dumps(receipt)
    assert receipt["summary"]["accounting_complete"] is True
    assert Decimal(receipt["summary"]["cost_usd_total"]) == live.ledger.snapshot().settled_usd
    assert len(live.wire) == 2
    assert all(
        step["usage"]["provider_observations_error"] == "ProviderObservationsUnavailable"
        for step in receipt["cases"][0]["steps"]
    )
    assert all(
        step["usage"]["provider_observations"] == [] for step in receipt["cases"][0]["steps"]
    )


def test_repair_shares_each_turn_two_attempt_limit_and_replay_adds_no_attempt(tmp_path):
    live = MockLive(tmp_path, "parent_callback_code", malformed_first=True)
    with offline_network():
        receipt = runner.run(
            [write(tmp_path, fixture())], mode="live", live=live, conditional_routes=True
        )
    assert failed(receipt) == [] and receipt["summary"]["coverage_complete"] is True
    steps = receipt["cases"][0]["steps"]
    assert [step["usage"]["model_attempts"] for step in steps] == [2, 1]
    assert len(live.case_ids) == 2 and len(live.wire) == 3 and len(live.closed) == 2
    first = steps[0]["usage"]["requests"]
    assert [request["context"]["attempt_index"] for request in first] == [1, 2]
    assert len({request["request_id"] for request in first}) == 2
    assert all(request["status"] == "settled" for request in first)


@pytest.mark.parametrize(
    "mutation", ["revision", "case", "approved_id", "approved_question", "release"]
)
def test_route_selector_refuses_stale_foreign_or_unreleased_authority(tmp_path, mutation):
    live = MockLive(tmp_path, "parent_callback_code")
    data = fixture()
    with offline_network():
        receipt = runner.run(
            [write(tmp_path, data)], mode="live", live=live, conditional_routes=True
        )
    graph = RouteGraph.from_fixture(data)
    step = deepcopy(receipt["cases"][0]["steps"][0])
    view = deepcopy(step["view_after"])
    assert graph.select("initial", step, view).target == "callback"
    if mutation == "revision":
        view["case_revision"] += 1
    elif mutation == "case":
        view["case_id"] = "foreign-case"
    elif mutation == "approved_id":
        view["awaiting_reply"]["proposal_id"] = "different-proposal"
    elif mutation == "approved_question":
        view["awaiting_reply"]["question"]["user_draft"] = "A different question."
    else:
        step["released_outputs"] = []
    assert graph.select("initial", step, view) is None


@pytest.mark.parametrize("complete", [True, False])
def test_conditional_cli_distinguishes_completed_path_and_unavailable_branch(
    tmp_path, monkeypatch, complete
):
    data = fixture()
    if not complete:
        data["turns"][0]["maintainer"] = {"decision": "none"}
    live = MockLive(tmp_path, "parent_callback_code")
    monkeypatch.setattr(runner, "_load_live", lambda _spec: live)
    output = tmp_path / "live" / "receipt.json"
    with offline_network():
        code = runner.main(
            [
                str(write(tmp_path, data)),
                "--mode",
                "live",
                "--adapters",
                "synthetic:factory",
                "--conditional-routes",
                "--output",
                str(output),
            ]
        )
    assert code == (0 if complete else 2)
    receipt = json.loads(output.read_text(encoding="utf-8"))
    assert receipt["summary"]["coverage_complete"] is complete
    assert receipt["summary"]["failed"] == 0
    assert receipt["summary"]["cases_all_passed"] == (1 if complete else 0)


@pytest.mark.parametrize("compressed", [False, True])
def test_actual_live_factory_retains_verified_serving_ids_in_runner_receipt(
    tmp_path, index, ledger, compressed
):
    def respond(request):
        response = provider_response(request)
        if compressed:
            import gzip

            return httpx.Response(
                200, headers={"content-encoding": "gzip"}, content=gzip.compress(response.content)
            )
        return response

    with offline_network():
        live, transports = real_adapters(index, ledger, respond)
        try:
            receipt = runner.run(
                [write(tmp_path, fixture())], mode="live", live=live, conditional_routes=True
            )
        finally:
            live.close()
    assert failed(receipt) == []
    assert receipt["summary"]["coverage_complete"] is True
    assert len(transports) == 3 and all(transport.close_calls == 1 for transport in transports)
    assert receipt["snapshots"] == [index[1]]
    for step in receipt["cases"][0]["steps"]:
        observation = step["usage"]["provider_observations"][0]
        reservation = step["usage"]["requests"][0]
        assert step["usage"]["provider_observations_error"] is None
        assert observation["verified_returned_model"] == "gpt-4o-mini-2024-07-18"
        assert observation["held_usd"] is None and observation["ledger_status"] == "settled"
        assert observation["request_id"] == reservation["request_id"]
        assert observation["cost_estimated_usd"] == reservation["cost_usd"]
        assert step["proposal"]["review_handoff"]["evidence"]["snapshot_id"] == index[1]
    assert receipt["quality_claim"] is False


def observation_row(ledger, context):
    request_id = runner.request_id_for(context)
    reservation = ledger.get(request_id)
    return {
        "request_id": request_id,
        "run_id": context.run_id,
        "case_id": context.case_id,
        "case_revision": context.case_revision,
        "attempt_index": context.attempt_index,
        "prompt_sha256": "b" * 64,
        "requested_model": "gpt-4o-mini",
        "verified_returned_model": None,
        "http_send_started": False,
        "http_status": None,
        "ledger_status": reservation.status,
        "input_tokens": reservation.input_tokens,
        "output_tokens": reservation.output_tokens,
        "cost_estimated_usd": str(reservation.cost_usd)
        if reservation.cost_usd is not None
        else None,
        "held_usd": str(reservation.amount_usd)
        if reservation.status in {"reserved", "uncertain"}
        else None,
        "error_code": reservation.error_code,
    }


@pytest.mark.parametrize("status", ["reserved", "uncertain", "settled", "released"])
def test_observation_nohold_and_active_hold_are_distinguished_by_authoritative_ledger(
    tmp_path, status
):
    ledger = BudgetLedger.create(
        tmp_path / "hold-check.sqlite3", limit_usd=Decimal("1"), opening_spend_usd=Decimal("0")
    )
    context = ReasoningContext(
        run_id="hold-run", case_id="hold-case", case_revision=1, attempt_index=1
    )
    identifier = runner.request_id_for(context)
    ledger.reserve(
        request_id=identifier,
        run_id=context.run_id,
        case_id=context.case_id,
        case_revision=1,
        attempt=1,
        model="gpt-4o-mini",
        phase="evaluation",
        amount_usd=Decimal("0.001"),
    )
    if status == "uncertain":
        ledger.mark_uncertain(identifier, error_code="ProviderRequestFailed")
    elif status == "settled":
        ledger.settle(identifier, cost_usd=Decimal("0.0001"), input_tokens=100, output_tokens=20)
    elif status == "released":
        ledger.release_unsent(identifier, error_code="ProviderRequestFailed")
    row = observation_row(ledger, context)
    before = ledger.snapshot()
    allowed = [None, "0"] if status in {"settled", "released"} else ["0.001"]
    for held in allowed:
        valid = row | {"held_usd": held}
        projected, error = runner._provider_observations(
            lambda _contexts, value=valid: [value], [context], ledger
        )
        assert projected == [valid] and error is None
    forbidden = ["0.001"] if status in {"settled", "released"} else [None, "0", "0.002"]
    for held in forbidden:
        projected, error = runner._provider_observations(
            lambda _contexts, amount=held: [row | {"held_usd": amount}], [context], ledger
        )
        assert projected == [] and error == "ProviderObservationsUnavailable"
    assert ledger.snapshot() == before


def test_observer_rejects_ledger_identity_drift_even_if_context_row_and_cost_match(
    tmp_path, monkeypatch
):
    live = ObservedMockLive(tmp_path, "parent_callback_code")
    context = ReasoningContext(
        run_id="identity-run", case_id="identity-case", case_revision=1, attempt_index=1
    )
    identifier = runner.request_id_for(context)
    live.ledger.reserve(
        request_id=identifier,
        run_id=context.run_id,
        case_id=context.case_id,
        case_revision=1,
        attempt=1,
        model="gpt-4o-mini",
        phase="evaluation",
        amount_usd=Decimal("0.001"),
    )
    live.ledger.settle(identifier, cost_usd=Decimal("0.0001"), input_tokens=100, output_tokens=20)
    row = observation_row(live.ledger, context)
    reservation = live.ledger.get(identifier)
    monkeypatch.setattr(
        live.ledger, "get", lambda _identifier: replace(reservation, case_revision=2)
    )
    projected, error = runner._provider_observations(
        lambda _contexts: [row], [context], live.ledger
    )
    assert projected == [] and error == "ProviderObservationsUnavailable"


def test_duplicate_unsent_attempt_can_observe_prior_settlement_without_new_wire_claim(tmp_path):
    accounting = BudgetLedger.create(
        tmp_path / "duplicate.sqlite3", limit_usd=Decimal("1"), opening_spend_usd=Decimal("0")
    )
    context = ReasoningContext(
        run_id="duplicate-run", case_id="duplicate-case", case_revision=1, attempt_index=1
    )
    identifier = runner.request_id_for(context)
    accounting.reserve(
        request_id=identifier,
        run_id=context.run_id,
        case_id=context.case_id,
        case_revision=1,
        attempt=1,
        model="gpt-4o-mini",
        phase="evaluation",
        amount_usd=Decimal("0.001"),
    )
    accounting.settle(identifier, cost_usd=Decimal("0.0001"), input_tokens=100, output_tokens=20)
    row = observation_row(accounting, context) | {"error_code": "DuplicateModelRequest"}
    projected, error = runner._provider_observations(lambda _contexts: [row], [context], accounting)
    assert error is None and projected == [row]
    assert projected[0]["ledger_status"] == "settled"
    assert projected[0]["http_send_started"] is False
    assert projected[0]["http_status"] is projected[0]["verified_returned_model"] is None


def test_actual_factory_model_mismatch_keeps_unknown_id_private_and_retains_exact_hold(
    tmp_path, index, ledger
):
    def respond(request):
        return provider_response(request, model="PRIVATE_UNVERIFIED_PROVIDER_MODEL")

    with offline_network():
        live, transports = real_adapters(index, ledger, respond)
        try:
            receipt = runner.run(
                [write(tmp_path, fixture())], mode="live", live=live, conditional_routes=True
            )
        finally:
            live.close()
    assert len(transports) == 1 and transports[0].close_calls == 1
    first = receipt["cases"][0]["steps"][0]
    assert first["usage"]["provider_observations_error"] is None
    observation = first["usage"]["provider_observations"][0]
    assert observation["verified_returned_model"] is None
    assert (
        observation["ledger_status"] == "uncertain"
        and observation["error_code"] == "ProviderModelMismatch"
    )
    assert Decimal(observation["held_usd"]) == ledger.snapshot().uncertain_usd > 0
    assert receipt["summary"]["coverage_complete"] is False
    assert receipt["summary"]["cost_usd_total"] is None
    assert "PRIVATE_UNVERIFIED_PROVIDER_MODEL" not in json.dumps(receipt)
