"""Frozen input plumbing with mandatory mock provider and disposable accounting."""

import gzip
import json
import sqlite3
import sys
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal

import httpx
import pytest

from agent_app.orchestration.ports import ReasoningStopped
from agent_app.testing import controlled_model_baseline as baseline
from agent_app.testing.controlled_decision_inputs import load_conditions, registration_inputs
from agent_app.testing.http_pilot_runtime import offline_network


@pytest.fixture
def prepared():
    with offline_network():
        return baseline.prepare()


@pytest.fixture
def ledger(tmp_path):
    ledger = baseline._mock_ledger(tmp_path / "mock-budget.sqlite3")
    return ledger


def response(
    request, *, plan=None, malformed=False, model="gpt-4o-mini-2024-07-18", tokens=(125, 75)
):
    original = baseline._mock_response(request)
    body = original.json()
    body["model"] = model
    body["usage"] = {
        "prompt_tokens": tokens[0],
        "completion_tokens": tokens[1],
        "total_tokens": sum(tokens),
    }
    if plan is not None:
        body["choices"][0]["message"]["content"] = json.dumps(plan)
    if malformed:
        body["choices"][0]["message"]["content"] = "{malformed-private-response"
    return httpx.Response(200, json=body)


def request_data(request):
    return json.loads(json.loads(request.content)["messages"][1]["content"])


def execute(prepared, ledger, respond=baseline._mock_response, **extra):
    with offline_network():
        return baseline.execute(
            prepared,
            ledger_path=ledger._path,
            config=baseline._config("public-synthetic-controlled-test-key"),
            before=baseline.ledger_observation(ledger._path),
            underlying=httpx.MockTransport(respond),
            **extra,
        )


def test_all_first_repair_and_refinement_prompts_fit_without_fixture_gold(prepared):
    assert len(prepared) == 6
    assert [item["condition"].condition_id for item in prepared] == [
        item.condition_id for item in load_conditions()
    ]
    assert sum(len(item["prompts"]) for item in prepared) == 18
    assert all(
        frame["prompt_bytes_plus_margin"] <= baseline.INPUT_RESERVE
        for item in prepared
        for frame in item["prompts"]
    )
    for item in prepared:
        for request in item["requests"]:
            assert set(request.model_dump()) == {
                "case",
                "user_message",
                "evidence",
                "gaps",
                "conflict_groups",
                "context_sha256",
            }
            assert request.case == item["condition"].case
            assert request.user_message == item["condition"].user_message


def test_full_six_case_mock_wires_exact_inputs_questions_sources_and_accounting(prepared, ledger):
    seen = []

    def respond(request):
        body, data = json.loads(request.content), request_data(request)
        assert body["model"] == baseline.MODEL and body["max_tokens"] == baseline.OUTPUT_LIMIT
        assert set(data["request"]) == {
            "case",
            "user_message",
            "evidence",
            "gaps",
            "conflict_groups",
            "context_sha256",
        }
        seen.append(data)
        return response(request)

    before = baseline.ledger_observation(ledger._path)
    receipt = execute(prepared, ledger, respond)
    assert len(seen) == receipt["actual_sends"] == 6
    assert receipt["complete"] and receipt["accepted_operations"]
    assert (
        receipt["registered_conditions"]
        == receipt["attempted_conditions"]
        == receipt["final_proposals"]
        == 6
    )
    assert receipt["skipped_conditions"] == []
    assert receipt["evidence_scope"] == "all" and receipt["top_k"] == 5
    assert all(
        request["top_k"] == 5
        for result in receipt["condition_results"]
        for request in result["retrieval_requests"]
    )
    assert receipt["unfunded_condition_count"] == 0
    assert all(receipt["checks"].values())
    assert Decimal(receipt["new_cost_estimated_usd"]) == Decimal("0.000420750")
    assert receipt["new_reserved_usd"] == receipt["new_uncertain_usd"] == "0"
    assert receipt["new_request_accounting_complete"]
    assert (
        receipt["ledger_after"]["original_quarantine_sha256"]
        == before["original_quarantine_sha256"]
    )
    assert receipt["ledger_after"]["halted"] and receipt["ledger_after"]["uncertain_usd"] == "0.02"
    assert receipt["tracker_actions"] == 0 and not receipt["tracker_staging"]
    assert not receipt["proposal_auto_approved"] and not receipt["quality_claim"]
    assert receipt["actual_account_charge_usd"] is None
    assert receipt["real_provider_requests"] == 0
    assert receipt["intercepted_mock_sends"] == 6
    assert receipt["paid_api_cost_usd"] == "0"
    assert receipt["cost_kind"] == "synthetic_usage_estimate"
    assert receipt["accounting_scope"] == "disposable_mock_ledger"
    for item, sent, result in zip(prepared, seen, receipt["condition_results"], strict=True):
        assert sent["request"] == item["requests"][0].model_dump(mode="json")
        handoff = result["canonical_handoff"]
        assert handoff["case"] == item["condition"].case.model_dump(mode="json")
        assert handoff["grounded_request"] == sent["request"]
        assert handoff["analysis"]["decision"] == "ask"
        chosen = handoff["analysis"]["missing_info"][0]
        assert handoff["analysis"]["next_question"] == next(
            gap.question for gap in item["condition"].gaps if gap.name == chosen
        )
    assert all(
        record["verified_returned_model"] == "gpt-4o-mini-2024-07-18"
        and record["reservation"]["status"] == "settled"
        for record in receipt["provider_observations"]
    )
    text = json.dumps(receipt)
    assert "public-synthetic-controlled-test-key" not in text and "Authorization" not in text


def test_two_attempt_repair_consumes_two_sends_and_never_exceeds_global_six(prepared, ledger):
    calls = []

    def respond(request):
        calls.append(request_data(request))
        return response(request, malformed=len(calls) == 1)

    receipt = execute(prepared, ledger, respond)
    assert receipt["actual_sends"] == len(calls) == 6
    assert receipt["accepted_operations"] and not receipt["complete"]
    first = receipt["condition_results"][0]
    assert first["result"]["model_attempts"] == 2 and first["result"]["retrieval_rounds"] == 1
    assert first["canonical_handoff"] is not None
    assert first["reasoning_outputs"][0]["status"] == "invalid_analysis"
    assert first["reasoning_outputs"][0]["analysis"] is None
    assert first["reasoning_outputs"][0]["issue_codes"] == ["invalid_grounded_plan"]
    assert first["reasoning_outputs"][1]["status"] == "valid_rendered_analysis"
    assert first["reasoning_attempts"][0]["model_selection"] == {
        "status": "invalid_plan_shape",
        "issue_codes": ["invalid_grounded_plan"],
    }
    assert calls[1]["repair_issue_codes"] == ["invalid_grounded_plan"]
    assert first["grounded_requests"][0] == first["grounded_requests"][1]
    assert len(first["reasoning_attempts"]) == 2
    assert receipt["skipped_conditions"][0]["guard_stop_reason"] == "SendLimitReached"
    assert receipt["unfunded_condition_count"] == 0
    assert "malformed-private-response" not in json.dumps(receipt)


def test_refinement_uses_second_frozen_bundle_and_drops_stale_reference(prepared, ledger):
    # Isolate the final preregistered condition only in a mocked unit run.
    chosen, calls, stale_reference = prepared[-1:], [], None

    def respond(request):
        nonlocal stale_reference
        data = request_data(request)
        calls.append(data)
        if len(calls) == 1:
            stale_reference = next(
                reference
                for reference in data["source_references"]
                if reference["chunk_id"] == "release-150-multiselect-key-identity-v8"
            )
            plan = {
                "context_sha256": data["request"]["context_sha256"],
                "decision": "retrieve_more",
                "retrieval_queries": ["Inspect the missing current callback path"],
            }
        else:
            plan = {
                "context_sha256": data["request"]["context_sha256"],
                "decision": "answer",
                "sources": [stale_reference],
            }
        return response(request, plan=plan)

    receipt = execute(chosen, ledger, respond)
    assert len(calls) == receipt["actual_sends"] == 2
    result = receipt["condition_results"][0]
    assert result["canonical_handoff"] is None
    assert result["result"]["error_code"] == "GroundedSourceMismatch"
    assert result["result"]["model_attempts"] == result["result"]["retrieval_rounds"] == 2
    assert calls[0]["capacity"]["can_refine"] is True
    assert calls[1]["capacity"]["can_refine"] is False
    assert "release-150-multiselect-key-identity-v8" not in {
        source["chunk_id"] for source in calls[1]["request"]["evidence"]["hits"]
    }
    assert result["returned_evidence"][-1] == chosen[0]["requests"][1].evidence.model_dump(
        mode="json"
    )
    assert len(result["retrieval_requests"]) == 2
    assert result["reasoning_outputs"][0]["analysis"]["decision"] == "retrieve_more"
    assert result["reasoning_outputs"][1]["status"] == "invalid_analysis"
    assert result["reasoning_outputs"][1]["issue_codes"] == ["grounded_source_mismatch"]
    assert result["reasoning_attempts"][1]["model_selection"]["unknown_source_count"] == 1
    assert result["reasoning_attempts"][1]["model_selection"]["known_selected_sources"] == []


def test_refinement_then_final_ask_retains_both_valid_rendered_decisions(prepared, ledger):
    calls = []

    def respond(request):
        data = request_data(request)
        calls.append(data)
        if len(calls) == 1:
            plan = {
                "context_sha256": data["request"]["context_sha256"],
                "decision": "retrieve_more",
                "retrieval_queries": ["Inspect current parent callback source coverage"],
            }
            return response(request, plan=plan)
        return response(request)

    receipt = execute(prepared[-1:], ledger, respond)
    result = receipt["condition_results"][0]
    assert receipt["complete"] and receipt["actual_sends"] == 2
    assert [item["analysis"]["decision"] for item in result["reasoning_outputs"]] == [
        "retrieve_more",
        "ask",
    ]
    assert [item["retrieval_round"] for item in result["reasoning_outputs"]] == [1, 2]
    assert all(item["status"] == "valid_rendered_analysis" for item in result["reasoning_outputs"])
    assert result["reasoning_outputs"][0]["analysis"]["retrieval_queries"] == [
        "Inspect current parent callback source coverage"
    ]
    assert result["reasoning_outputs"][1]["analysis"] == result["canonical_handoff"]["analysis"]
    assert all(item["grounded_context_sha256"] for item in result["reasoning_outputs"])


def test_invalid_plan_selection_records_only_flags_not_unknown_payload(prepared, ledger):
    def respond(request):
        data = request_data(request)
        return response(
            request,
            plan={
                "context_sha256": data["request"]["context_sha256"],
                "decision": "ask",
                "question_name": "private_unknown_question",
                "sources": [{"chunk_id": "private_unknown_source", "content_sha256": "0" * 64}],
            },
        )

    receipt = execute(prepared[:1], ledger, respond)
    selection = receipt["condition_results"][0]["reasoning_attempts"][0]["model_selection"]
    assert selection["status"] == "valid_plan_shape" and selection["decision"] == "ask"
    assert selection["unknown_source_count"] == 1 and selection["unknown_question_present"]
    assert selection["known_question_name"] is None and selection["known_selected_sources"] == []
    assert "private_unknown_question" not in json.dumps(receipt)
    assert "private_unknown_source" not in json.dumps(receipt)
    assert receipt["condition_results"][0]["reasoning_outputs"][0]["analysis"] is None


@pytest.mark.parametrize("fault", ["timeout", "model_mismatch", "truncated", "usage_missing"])
def test_terminal_provider_fault_stops_rest_and_preserves_unknown_cost(prepared, ledger, fault):
    calls = []

    def respond(request):
        calls.append(1)
        if fault == "timeout":
            raise httpx.ReadTimeout("private-provider-error", request=request)
        result = response(
            request,
            model="private-unknown-model"
            if fault == "model_mismatch"
            else "gpt-4o-mini-2024-07-18",
        )
        body = result.json()
        if fault == "truncated":
            body["choices"][0]["finish_reason"] = "length"
        elif fault == "usage_missing":
            body.pop("usage")
        return httpx.Response(200, json=body)

    receipt = execute(prepared, ledger, respond)
    assert receipt["actual_sends"] == len(calls) == 1
    assert not receipt["complete"] and len(receipt["skipped_conditions"]) == 5
    assert receipt["checks"]["immutable_grant_and_global_budget_preserved"]
    if fault != "truncated":
        assert receipt["new_cost_estimated_usd"] is None
        assert not receipt["new_request_accounting_complete"]
        assert Decimal(receipt["new_uncertain_usd"]) == baseline.REQUEST_BOUND
    else:
        assert receipt["new_request_accounting_complete"]
        assert Decimal(receipt["new_cost_estimated_usd"]) > 0
    assert "private-provider-error" not in json.dumps(receipt)
    assert "private-unknown-model" not in json.dumps(receipt)


def test_gzip_serving_identity_is_decoded_once_without_header_leak(prepared, ledger):
    def respond(request):
        compressed = gzip.compress(response(request).content)
        return httpx.Response(
            200,
            headers={"Content-Encoding": "gzip", "private-header": "private-value"},
            content=compressed,
        )

    receipt = execute(prepared, ledger, respond)
    assert receipt["complete"] and receipt["accepted_operations"]
    assert all(
        row["verified_returned_model"] == "gpt-4o-mini-2024-07-18"
        for row in receipt["provider_observations"]
    )
    assert "private-header" not in json.dumps(receipt)


@pytest.mark.parametrize("bound", ["batch", "grant", "global"])
def test_unfunded_cases_are_skipped_without_a_fresh_client_send(prepared, ledger, bound):
    if bound == "grant":
        with sqlite3.connect(ledger._path) as connection:
            connection.execute("UPDATE ledger_continuations SET cap_nanos=4914790")
    elif bound == "global":
        with sqlite3.connect(ledger._path) as connection:
            connection.execute("UPDATE ledger_meta SET opening_nanos=4479000000")
    calls = []

    def respond(request):
        calls.append(1)
        return response(request, tokens=(14000, 384))

    receipt = execute(prepared, ledger, respond)
    wanted = 0 if bound == "global" else 1
    assert len(calls) == receipt["actual_sends"] == wanted
    assert receipt["accepted_operations"] and not receipt["complete"]
    assert receipt["unfunded_condition_count"] == 6 - wanted
    reason = {
        "batch": "BatchCostCapInsufficient",
        "grant": "RemainingAuthorizationInsufficient",
        "global": "GlobalBudgetInsufficient",
    }[bound]
    assert receipt["skipped_conditions"][0]["guard_stop_reason"] == reason
    assert receipt["ledger_after"]["halted"]
    assert receipt["new_request_accounting_complete"]


def test_pre_send_scope_race_keeps_unsent_uncertainty_in_accounting(prepared, ledger, monkeypatch):
    original = baseline._ScopedTransport.handle_request

    def mutate_then_guard(transport, request):
        with sqlite3.connect(ledger._path) as connection:
            connection.execute("UPDATE ledger_continuations SET cap_nanos=101000000")
        return original(transport, request)

    monkeypatch.setattr(baseline._ScopedTransport, "handle_request", mutate_then_guard)
    receipt = execute(prepared, ledger, lambda _: (_ for _ in ()).throw(AssertionError("No send")))
    assert receipt["actual_sends"] == 0
    assert len(receipt["model_request_observations"]) == 1
    assert receipt["new_cost_estimated_usd"] is None
    assert Decimal(receipt["new_uncertain_usd"]) == baseline.REQUEST_BOUND
    assert not receipt["model_request_observations"][0]["http_send_started"]
    assert not receipt["accepted_operations"]


def test_source_drift_stops_before_condition_without_ledger_mutation(prepared, ledger):
    before = baseline.ledger_observation(ledger._path)

    def stopped():
        raise baseline.BaselineRejected()

    receipt = execute(prepared, ledger, source_guard=stopped)
    assert receipt["actual_sends"] == receipt["attempted_conditions"] == 0
    assert not receipt["accepted_operations"]
    assert receipt["ledger_after"] == before
    assert len(receipt["skipped_conditions"]) == 6


@pytest.mark.parametrize("terminal", [False, True])
def test_shared_transport_is_closed_once_after_normal_or_terminal_batch(prepared, ledger, terminal):
    class CountedTransport(httpx.MockTransport):
        def __init__(self):
            def respond(request):
                if terminal:
                    raise httpx.ReadTimeout("private-close-test", request=request)
                return response(request)

            super().__init__(respond)
            self.closes = 0

        def close(self):
            self.closes += 1
            super().close()

    transport = CountedTransport()
    with offline_network():
        receipt = baseline.execute(
            prepared,
            ledger_path=ledger._path,
            config=baseline._config("public-synthetic-close-test-key"),
            before=baseline.ledger_observation(ledger._path),
            underlying=transport,
        )
    assert transport.closes == 1
    assert receipt["checks"]["clients_closed"]
    assert receipt["actual_sends"] == (1 if terminal else 6)
    assert "private-close-test" not in json.dumps(receipt)


def test_handoff_failure_retains_actual_result_cost_and_fixed_error(prepared, ledger, monkeypatch):
    monkeypatch.setattr(
        baseline,
        "build_handoff",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("private-handoff-error")),
    )
    receipt = execute(prepared, ledger)
    assert receipt["actual_sends"] == 1 and not receipt["complete"]
    assert receipt["condition_results"][0]["result"]["status"] == "awaiting_approval"
    assert receipt["condition_results"][0]["handoff_error"] == "InvalidHandoffInput"
    assert receipt["condition_results"][0]["canonical_handoff"] is None
    assert len(receipt["skipped_conditions"]) == 5
    assert "private-handoff-error" not in json.dumps(receipt)


def test_preflight_malformed_or_oversized_fixed_input_stops_before_keys(ledger):
    before = baseline.ledger_observation(ledger._path)
    values = list(load_conditions())
    values[0] = replace(values[0], user_message="long raw message " * 1100)
    with offline_network(), pytest.raises(ValueError):
        baseline.prepare(values)
    assert baseline.ledger_observation(ledger._path) == before


def test_seventh_send_guard_does_not_touch_ledger(ledger):
    before = baseline.ledger_observation(ledger._path)
    scoped = baseline._ScopedTransport(
        httpx.MockTransport(lambda _: (_ for _ in ()).throw(AssertionError("No seventh send"))),
        ledger,
        before,
        lambda: None,
    )
    scoped.records = [{"request_id": str(index)} for index in range(6)]
    with pytest.raises(ReasoningStopped):
        scoped.guard()
    assert scoped.last_stop_reason == "SendLimitReached"
    assert baseline.ledger_observation(ledger._path) == before
    scoped.close()


def test_mock_cli_uses_only_temporary_ledger_and_no_credentials(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["controlled-baseline", "--mock"])
    monkeypatch.setattr(
        baseline, "_credential", lambda *_: (_ for _ in ()).throw(AssertionError("No key"))
    )
    monkeypatch.setattr(
        baseline,
        "load_registration",
        lambda *_: (_ for _ in ()).throw(AssertionError("No production ledger")),
    )
    with offline_network():
        baseline.main()
    report = json.loads(capsys.readouterr().out)
    assert report["execution_mode"] == "mocked_model_fixed_evidence"
    assert report["real_provider_requests"] == 0
    assert report["paid_api_cost_usd"] == "0" and report["intercepted_mock_sends"] == 6
    assert report["complete"] and report["actual_sends"] == 6 and not report["quality_claim"]


def test_default_cli_prepares_all_inputs_without_credential_or_transport(
    prepared, ledger, monkeypatch, capsys
):
    registration = {
        "fixture_pins": registration_inputs(),
        "review_pins": {"path": "review.json"},
        "ledger_before": baseline.ledger_observation(ledger._path),
        "source_commit": "stable",
        "source_clean": True,
    }
    monkeypatch.setattr(baseline, "load_registration", lambda *_: ({}, registration))
    monkeypatch.setattr(
        baseline, "source_observation", lambda *_: {"source_commit": "stable", "source_clean": True}
    )
    monkeypatch.setattr(
        baseline, "_credential", lambda *_: (_ for _ in ()).throw(AssertionError("No key"))
    )
    monkeypatch.setattr(
        httpx.HTTPTransport,
        "__init__",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("No provider")),
    )
    monkeypatch.setattr(sys, "argv", ["controlled-baseline", "--ledger", str(ledger._path)])
    with offline_network():
        baseline.main()
    report = json.loads(capsys.readouterr().out)
    assert report["eligible_read_only"] and report["all_prompts_fit"]
    assert report["paid_requests"] == 0 and not report["all_six_funded_claim"]


def test_load_registration_checks_review_pins_order_scope_and_original_ledger(
    tmp_path, ledger, monkeypatch
):
    root = tmp_path / "repository"
    (root / "runtime").mkdir(parents=True)
    destination = root / "runtime/budget.sqlite3"
    # Test only: a disposable database file, never the production budget ledger.
    destination.write_bytes(ledger._path.read_bytes())
    with sqlite3.connect(destination) as connection:
        connection.execute("UPDATE ledger_continuations SET cap_nanos=4914790")
    before = baseline.ledger_observation(destination)
    source = {
        "source_commit": "pushed",
        "upstream_commit": "pushed",
        "source_clean": True,
        "source_pushed": True,
        "source_hashes": {},
    }
    order = [item.condition_id for item in load_conditions()]
    review = root / "experiments/controlled_model_baseline/scenario-review-v1.json"
    review.parent.mkdir(parents=True)
    review.write_text(
        json.dumps({"ordered_condition_ids": order, "private_labels_never_sent": True}),
        encoding="utf-8",
    )
    protocol = {
        "protocol_id": baseline.PROTOCOL_ID,
        "experiment_id": baseline.EXPERIMENT_ID,
        "continuation_id": baseline.GRANT,
        "ledger": {
            "path": "runtime/budget.sqlite3",
            "sha256_before": before["fingerprints"]["db"],
            "unknown_records_sha256": before["unknown_records_sha256"],
        },
        "gateway": baseline._gateway_policy(),
        "limits": baseline.LIMITS,
        "evidence_scope": "all",
        "top_k": 5,
        "fixture_pins": registration_inputs(),
        "ordered_condition_ids": order,
        "review_pins": {
            "path": str(review.relative_to(root)),
            "sha256": baseline._sha(review.read_bytes()),
        },
        "source_pins": {},
    }
    path = root / baseline.PROTOCOL
    path.write_text(json.dumps(protocol), encoding="utf-8")
    monkeypatch.setattr(baseline, "source_observation", lambda *_: source)
    _, registered = baseline.load_registration(root, destination)
    assert registered["ordered_condition_ids"] == order
    assert "private_labels_never_sent" not in json.dumps(registered)
    wrong = deepcopy(protocol)
    wrong["evidence_scope"] = "exact_user_version"
    path.write_text(json.dumps(wrong), encoding="utf-8")
    with pytest.raises(baseline.BaselineRejected):
        baseline.load_registration(root, destination)
    path.write_text(json.dumps(protocol), encoding="utf-8")
    source["source_pushed"] = False
    with pytest.raises(baseline.BaselineRejected):
        baseline.load_registration(root, destination)
    source["source_pushed"] = True
    review.write_text(json.dumps({"ordered_condition_ids": order[::-1]}), encoding="utf-8")
    wrong = deepcopy(protocol)
    wrong["review_pins"]["sha256"] = baseline._sha(review.read_bytes())
    path.write_text(json.dumps(wrong), encoding="utf-8")
    with pytest.raises(baseline.BaselineRejected):
        baseline.load_registration(root, destination)


def test_non_mock_transport_cannot_use_disposable_ledger_for_paid_work(prepared, ledger):
    class NeverDelegate(httpx.BaseTransport):
        def handle_request(self, _request):
            raise AssertionError("No paid delegation")

    before = baseline.ledger_observation(ledger._path)
    with pytest.raises(baseline.BaselineRejected):
        baseline.execute(
            prepared,
            ledger_path=ledger._path,
            config=baseline._config("public-synthetic-no-paid-work"),
            before=before,
            underlying=NeverDelegate(),
            source_guard=lambda: None,
        )
    assert baseline.ledger_observation(ledger._path) == before
