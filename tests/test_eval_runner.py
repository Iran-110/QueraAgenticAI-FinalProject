import json
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from agent_app import api
from agent_app.contracts import AnalysisResult, EvidenceBundle
from agent_app.evaluation import pilot, runner
from agent_app.llm.budget import BudgetLedger
from agent_app.llm.config import MetisConfig
from agent_app.llm.metis import MetisReasoner, request_id_for
from agent_app.testing.fakes import FakeReasoner, FakeRetriever

DEV = Path(__file__).resolve().parent.parent / "data/evaluation/dev"
FIXTURE = DEV / "pilot-12782.json"


def failed(receipt):
    return [
        (check["step"], check["check"])
        for case in receipt["cases"]
        for check in case["checks"]
        if not check["passed"]
    ]


def fixture_data():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def write(tmp_path, data, name="fixture.json"):
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def without_latency(receipt):
    return [
        {**step, "usage": {**step["usage"], "latency_ms": None}}
        for case in receipt["cases"]
        for step in case["steps"]
    ]


def test_dev_split_passes_offline():
    receipt = runner.run([DEV])
    assert failed(receipt) == []
    assert receipt["mode"] == "offline"
    assert receipt["quality_claim"] is False
    assert receipt["summary"]["cost_usd_total"] == "0"
    assert receipt["summary"]["decisions"] == {"ask": 2, "answer": 1, "escalate": 1}
    step = receipt["cases"][0]["steps"][1]
    assert step["usage"]["model_attempts"] == 1
    assert step["usage"]["input_tokens"] == 0


def test_every_accepted_event_replays_without_side_effects():
    checks = runner.run([FIXTURE])["cases"][0]["checks"]
    replays = [check for check in checks if check["check"].startswith("replay ")]
    assert len(replays) == 8
    assert all(check["passed"] for check in replays)


def test_receipt_is_deterministic_apart_from_latency():
    assert without_latency(runner.run([FIXTURE])) == without_latency(runner.run([FIXTURE]))


def test_wrong_expectation_is_reported(tmp_path):
    data = fixture_data()
    data["turns"][2]["expect"]["active_facts"]["streamlit_version"] = "1.50.0"
    assert ("p1-turn-3", "active fact streamlit_version") in failed(
        runner.run([write(tmp_path, data)])
    )


def test_rejected_question_leaves_reply_unbound(tmp_path):
    data = fixture_data()
    data["turns"][0]["maintainer"]["decision"] = "reject"
    checks = failed(runner.run([write(tmp_path, data)]))
    assert ("p1-turn-1", "released drafts") in checks
    assert ("p1-turn-2", "intake preparation") in checks


def test_changed_evidence_source_is_refused(tmp_path):
    data = fixture_data()
    data["evidence_source"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="SHA-256"):
        runner.run([write(tmp_path, data)])


def test_duplicate_case_is_refused(tmp_path):
    data = fixture_data()
    with pytest.raises(ValueError, match="Duplicate"):
        runner.collect([write(tmp_path, data, "a.json"), write(tmp_path, data, "b.json")])


def test_family_in_both_splits_is_refused(tmp_path):
    dev = fixture_data()
    test = fixture_data()
    test["case"].update(case_id="test-copy", split="test", test_eligible=True)
    with pytest.raises(ValueError, match="both dev and test"):
        runner.collect([write(tmp_path, dev, "dev.json"), write(tmp_path, test, "test.json")])


def test_exposed_case_cannot_be_test(tmp_path):
    data = fixture_data()
    data["case"]["split"] = "test"
    with pytest.raises(ValueError, match="not eligible"):
        runner.collect([write(tmp_path, data)])


class FakeLive:
    """Synthetic adapters with an actual temporary ledger, not real model quality."""

    def __init__(self, tmp_path, data=None, *, metered=True):
        self.ledger = BudgetLedger.create(
            tmp_path / "synthetic.sqlite", limit_usd=Decimal("5"), opening_spend_usd=Decimal("0")
        )
        self.config = {"model": "fake-model", "snapshot_id": "fake-snapshot"}
        self.case_ids = []
        self.contexts = []
        self.metered = metered
        data = data or fixture_data()
        source = json.loads((runner.ROOT / data["evidence_source"]["path"]).read_text())
        self.bundles = [
            EvidenceBundle.model_validate(source["evidence_bundles"][turn["evidence_bundle"]])
            for turn in data["turns"]
        ]
        self.scripts = [AnalysisResult.model_validate(t["agent_script"]) for t in data["turns"]]

    def for_case(self, case_id):
        self.case_ids.append(case_id)
        bundle = self.bundles.pop(0)
        delegate = FakeReasoner([self.scripts.pop(0)])
        owner = self

        class Metered:
            def analyze(self, case, user_message, evidence, *, context):
                owner.contexts.append(context.model_copy(deep=True))
                if owner.metered:
                    request_id = request_id_for(context)
                    owner.ledger.reserve(
                        request_id=request_id,
                        run_id=context.run_id,
                        case_id=case.case_id,
                        case_revision=case.case_revision,
                        attempt=context.attempt_index,
                        model="fake-model",
                        phase="evaluation",
                        amount_usd=Decimal("0.001"),
                    )
                    owner.ledger.settle(
                        request_id, cost_usd=Decimal("0.001"), input_tokens=100, output_tokens=20
                    )
                return delegate.analyze(case, user_message, evidence, context=context)

        return api.RunAdapters(
            FakeRetriever([bundle]),
            Metered(),
            snapshot_id=bundle.snapshot_id,
        )


def test_live_mode_records_cost_tokens_and_config(tmp_path):
    live = FakeLive(tmp_path)
    receipt = runner.run([FIXTURE], mode="live", live=live)
    assert live.case_ids == ["dev-pilot-12782"] * 4
    assert receipt["mode"] == "live"
    assert receipt["config"]["model"] == "fake-model"
    assert receipt["snapshots"] == [
        receipt["cases"][0]["steps"][0]["proposal"]["review_handoff"]["evidence"]["snapshot_id"]
    ]
    assert receipt["config"]["snapshot_id"] == "fake-snapshot"
    assert receipt["summary"]["cost_usd_total"] == "0.004"
    assert receipt["cases"][0]["steps"][0]["usage"]["input_tokens"] == 100


def test_mode_and_adapters_must_agree(tmp_path):
    with pytest.raises(ValueError):
        runner.run([FIXTURE], mode="live")
    with pytest.raises(ValueError):
        runner.run([FIXTURE], live=FakeLive(tmp_path))


def test_cli_keeps_modes_apart_and_never_overwrites(tmp_path):
    with pytest.raises(SystemExit):
        runner.main([str(FIXTURE), "--output", str(tmp_path / "receipt.json")])
    with pytest.raises(SystemExit):
        runner.main([str(FIXTURE), "--mode", "live"])
    output = tmp_path / "offline" / "receipt.json"
    assert runner.main([str(FIXTURE), "--output", str(output)]) == 0
    assert json.loads(output.read_text())["mode"] == "offline"
    with pytest.raises(SystemExit):
        runner.main([str(FIXTURE), "--output", str(output)])


def test_pilot_command_still_runs():
    assert pilot.main([str(FIXTURE)]) == 0


SCENARIOS = DEV.parent / "scenarios"


def scenario_data(name):
    return json.loads((SCENARIOS / f"{name}.json").read_text(encoding="utf-8"))


def test_registered_scenarios_pass():
    receipt = runner.run([SCENARIOS])
    assert failed(receipt) == []
    assert receipt["summary"]["decisions"]["stopped"] == 2


def test_failed_tool_stops_without_proposal_and_retry_stays_within_limit():
    case = next(c for c in runner.run([SCENARIOS])["cases"] if c["case_id"] == "syn-tool-failure")
    steps = {step["turn"]: step for step in case["steps"]}
    assert steps["tool-1"]["proposal"]["proposal_id"] is None
    assert steps["tool-2"]["usage"]["model_attempts"] == 2
    assert steps["tool-3"]["proposal"]["proposal_id"] is None

    def assistant(step):
        return [e for e in steps[step]["view_after"]["log"] if e["role"] == "assistant"]

    assert assistant("tool-3") == assistant("tool-2")  # The stopped run released nothing.


def test_case_switching_checks_isolation_and_cross_case_refusal():
    case = next(c for c in runner.run([SCENARIOS])["cases"] if c["case_id"] == "syn-switch-a")
    names = {(check["step"], check["check"]) for check in case["checks"]}
    assert ("switch-2", "case syn-switch-a untouched") in names
    assert ("switch-3", "case syn-switch-b untouched") in names
    assert ("switch-2", "other case's proposal refused here") in names


def test_wrong_stop_code_is_reported(tmp_path):
    data = scenario_data("tool-failure")
    data["turns"][0]["expect"]["stop_code"] = "SomethingElse"
    assert ("tool-1", "stop reason logged") in failed(runner.run([write(tmp_path, data)]))


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda d: d["turns"][0].update(faults={"network": True}), "unknown fault"),
        (lambda d: d["turns"][0].update(faults={}), "agent_script is required"),
        (lambda d: d["turns"][0].update(case_id="undeclared"), "not declared"),
    ],
)
def test_invalid_scenario_fixtures_are_refused(tmp_path, change, message):
    data = scenario_data("tool-failure")
    change(data)
    with pytest.raises(ValueError, match=message):
        runner.collect([write(tmp_path, data)])


def test_extra_case_ids_must_be_unique_across_fixtures(tmp_path):
    first = scenario_data("case-switching")
    second = scenario_data("tool-failure")
    second["case"]["case_id"] = "syn-switch-b"
    for turn in second["turns"]:
        turn.pop("case_id", None)
    with pytest.raises(ValueError, match="Duplicate case_id syn-switch-b"):
        runner.collect([write(tmp_path, first, "a.json"), write(tmp_path, second, "b.json")])


def test_live_routes_each_actual_case_without_passing_turn_data(tmp_path):
    data = scenario_data("case-switching")
    live = FakeLive(tmp_path, data)
    receipt = runner.run([SCENARIOS / "case-switching.json"], mode="live", live=live)
    assert live.case_ids == ["syn-switch-a", "syn-switch-b", "syn-switch-a"]
    assert failed(receipt) == []


def test_live_requires_a_real_ledger_and_a_valid_mode(tmp_path):
    live = FakeLive(tmp_path)
    live.ledger = None
    with pytest.raises(ValueError, match="LiveLedgerRequired"):
        runner.run([FIXTURE], mode="live", live=live)
    with pytest.raises(ValueError, match="Invalid evaluation mode"):
        runner.run([FIXTURE], mode="not-offline")
    assert live.case_ids == []


@pytest.mark.parametrize("stop", ["halted", "exhausted"])
def test_live_budget_gate_precedes_adapter_and_user_state(tmp_path, stop):
    live = FakeLive(tmp_path)
    if stop == "halted":
        live.ledger.halt()
    else:
        live.ledger.reserve(
            request_id="prior-request",
            run_id="prior-run",
            case_id="prior-case",
            case_revision=1,
            attempt=1,
            model="fake-model",
            phase="evaluation",
            amount_usd=Decimal("5"),
        )
    before = live.ledger.snapshot()
    existing = dict(api._cases)
    with pytest.raises(ValueError, match="LiveLedgerHalted|LiveBudgetUnavailable"):
        runner.run([FIXTURE], mode="live", live=live)
    assert live.case_ids == []
    assert api._cases == existing
    assert live.ledger.snapshot() == before


def test_live_does_not_convert_script_checks_into_semantic_quality(tmp_path):
    data = fixture_data()
    data["turns"][1]["agent_script"]["user_draft"] += " The full-app root cause is proved."
    live = FakeLive(tmp_path, data)
    receipt = runner.run([write(tmp_path, data)], mode="live", live=live)
    assert failed(receipt) == []  # Operational behaviour passed; the claim was not scored.
    assert receipt["quality_claim"] is False
    assert receipt["scoring"]["claim_grounding"] == "unmeasured"
    assert (
        "The full-app root cause is proved."
        in receipt["cases"][0]["steps"][1]["proposal"]["analysis"]["user_draft"]
    )


def test_live_accepts_unscripted_fixture_and_ignores_exact_script_expectations(tmp_path):
    data = fixture_data()
    live = FakeLive(tmp_path, data)
    for turn in data["turns"]:
        turn.pop("agent_script")
        turn["expect"]["pending_decision"] = "intentionally-wrong-script-label"
    path = write(tmp_path, data)
    receipt = runner.run([path], mode="live", live=live)
    assert failed(receipt) == []
    with pytest.raises(ValueError, match="agent_script is required"):
        runner.run([path])


def test_receipt_retains_full_review_and_human_edited_and_released_outputs():
    receipt = runner.run([FIXTURE])
    step = receipt["cases"][0]["steps"][2]
    original = step["proposal"]
    edited = step["edited_proposal"]
    assert original["review_handoff"]["analysis"] == original["analysis"]
    assert edited["review_handoff"]["analysis"] == edited["analysis"]
    assert original["proposal_id"] != edited["proposal_id"]
    assert step["released_outputs"][0]["text"] == edited["analysis"]["user_draft"]
    assert edited["analysis"]["user_draft"] != original["analysis"]["user_draft"]
    assert receipt["schema_version"] == 2
    assert receipt["tracker_backend"] == "process_memory_dummy_tracker"
    assert receipt["maintainer"] == "fixture_scripted"
    assert receipt["source_sha256"]["src/agent_app/evaluation/runner.py"]
    assert receipt["source_unchanged_during_run"] is True


def test_multiple_edits_have_distinct_bound_proposal_ids(tmp_path):
    data = scenario_data("case-switching")
    data["turns"][1]["maintainer"] = {
        "decision": "edit",
        "edited_draft": "Uploader example reviewed by a human.",
        "then": "approve",
    }
    data["turns"][1]["expect"]["after_decision"]["released_draft"] = "edited"
    steps = runner.run([write(tmp_path, data)])["cases"][0]["steps"]
    edits = [step["edited_proposal"] for step in steps if step["edited_proposal"]]
    assert len(edits) == 2
    assert len({edit["proposal_id"] for edit in edits}) == 2
    assert all(edit["review_handoff"]["proposal_id"] == edit["proposal_id"] for edit in edits)


def test_unrecorded_attempts_are_unknown_not_zero_cost(tmp_path):
    live = FakeLive(tmp_path, metered=False)
    receipt = runner.run([FIXTURE], mode="live", live=live)
    usage = receipt["cases"][0]["steps"][0]["usage"]
    assert usage["cost_usd"] is None
    assert usage["input_tokens"] is None
    assert usage["requests"][0]["status"] == "unrecorded"
    assert receipt["summary"]["cost_usd_total"] is None
    assert receipt["summary"]["settled_usd_total"] == "0"
    assert receipt["summary"]["unaccounted_requests"] == 4
    assert not receipt["summary"]["accounting_complete"]


class InterceptedLive:
    """Real gateway and ledger, mandatory intercepted HTTP, zero real spend."""

    def __init__(self, tmp_path, data, *, ledger=None, failure=None):
        self.ledger = ledger or BudgetLedger.create(
            tmp_path / "intercepted.sqlite", limit_usd=Decimal("5"), opening_spend_usd=Decimal("0")
        )
        self.config = {"model": "gpt-4o-mini", "snapshot_id": "intercepted-snapshot"}
        self.data = data
        source = json.loads((runner.ROOT / data["evidence_source"]["path"]).read_text())
        self.bundle = EvidenceBundle.model_validate(
            source["evidence_bundles"][data["turns"][0]["evidence_bundle"]]
        )
        self.failure = failure
        self.clients = []
        self.wire = []
        self.case_ids = []

    def for_case(self, case_id):
        self.case_ids.append(case_id)

        def respond(request):
            self.wire.append(json.loads(request.content))
            if self.failure == "timeout":
                raise httpx.ReadTimeout("synthetic timeout")
            content = (
                "{invalid"
                if self.failure == "malformed"
                else json.dumps(self.data["turns"][0]["agent_script"])
            )
            return httpx.Response(
                200,
                json={
                    "model": "gpt-4o-mini",
                    "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"role": "assistant", "content": content},
                        }
                    ],
                },
            )

        port = MetisReasoner(
            MetisConfig(api_key="synthetic-offline-audit", live_enabled=True, phase="evaluation"),
            self.ledger,
            transport=httpx.MockTransport(respond),
        )
        self.clients.append(port)
        return api.RunAdapters(
            FakeRetriever([self.bundle]), port, snapshot_id=self.bundle.snapshot_id
        )

    def close(self):
        for port in self.clients:
            port.close()


def one_turn():
    data = fixture_data()
    data["turns"] = data["turns"][:1]
    return data


def test_new_live_evaluations_have_unique_billable_ids_but_event_replay_is_stable(tmp_path):
    data = one_turn()
    path = write(tmp_path, data)
    first = InterceptedLive(tmp_path, data)
    second = InterceptedLive(tmp_path, data, ledger=first.ledger)
    try:
        a = runner.run([path], mode="live", live=first)
        b = runner.run([path], mode="live", live=second)
        assert failed(a) == failed(b) == []
        assert len(first.wire) == len(second.wire) == 1
        assert a["evaluation_run_id"] != b["evaluation_run_id"]
        aid = a["cases"][0]["steps"][0]["usage"]["requests"][0]["request_id"]
        bid = b["cases"][0]["steps"][0]["usage"]["requests"][0]["request_id"]
        assert aid != bid
        payload = json.loads(first.wire[0]["messages"][-1]["content"])
        assert payload["user_message"] == data["turns"][0]["visible"]["message"]
        assert not any(fact["name"] == "streamlit_version" for fact in payload["case"]["facts"])
        assert "gold" not in payload and "agent_script" not in payload and "expect" not in payload
        assert "unacceptable_claims" not in json.dumps(first.wire[0])
        for receipt in (a, b):
            usage = receipt["cases"][0]["steps"][0]["usage"]
            assert usage["requests"][0]["status"] == "settled"
            assert usage["requests"][0]["request_id"] == request_id_for(
                runner.ReasoningContext.model_validate(usage["requests"][0]["context"])
            )
    finally:
        first.close()
        second.close()


@pytest.mark.parametrize("failure,attempts", [("malformed", 2), ("timeout", 1)])
def test_stopped_gateway_attempts_keep_cost_identity_and_unknown_reservations(
    tmp_path, failure, attempts
):
    data = one_turn()
    live = InterceptedLive(tmp_path, data, failure=failure)
    try:
        receipt = runner.run([write(tmp_path, data)], mode="live", live=live)
        usage = receipt["cases"][0]["steps"][0]["usage"]
        assert len(live.wire) == usage["model_attempts"] == attempts
        assert len(usage["requests"]) == attempts
        assert receipt["cases"][0]["steps"][0]["proposal"]["proposal_id"] is None
        if failure == "timeout":
            assert usage["cost_usd"] is None and usage["input_tokens"] is None
            assert usage["settled_usd"] == "0"
            assert Decimal(usage["uncertain_usd"]) == live.ledger.snapshot().uncertain_usd > 0
            assert usage["requests"][0]["status"] == "uncertain"
        else:
            assert usage["input_tokens"] == 200
            assert Decimal(usage["cost_usd"]) == live.ledger.snapshot().settled_usd > 0
            assert all(entry["status"] == "settled" for entry in usage["requests"])
    finally:
        live.close()


def test_unrelated_ledger_activity_is_not_charged_to_the_current_turn(tmp_path):
    data = one_turn()
    live = InterceptedLive(tmp_path, data)
    original = live.for_case

    def unrelated(case_id):
        live.ledger.reserve(
            request_id="unrelated",
            run_id="unrelated",
            case_id="other-case",
            case_revision=1,
            attempt=1,
            model="fake-model",
            phase="evaluation",
            amount_usd=Decimal("0.01"),
        )
        live.ledger.settle(
            "unrelated", cost_usd=Decimal("0.01"), input_tokens=1000, output_tokens=500
        )
        return original(case_id)

    live.for_case = unrelated
    try:
        receipt = runner.run([write(tmp_path, data)], mode="live", live=live)
        usage = receipt["cases"][0]["steps"][0]["usage"]
        assert Decimal(usage["cost_usd"]) == live.ledger.snapshot().settled_usd - Decimal("0.01")
        assert usage["input_tokens"] == 100
        assert "retrieval" in receipt["usage_scope"]
    finally:
        live.close()


@pytest.mark.parametrize("question", ["parent callback", "escalate"])
def test_live_fixed_follow_up_branch_stops_as_coverage_before_incompatible_reply(
    tmp_path, question
):
    data = fixture_data()
    if question == "escalate":
        data["turns"][0]["agent_script"] = {
            "decision": "escalate",
            "user_draft": "Please have a maintainer inspect the missing callback.",
            "maintainer_summary": "Root cause unconfirmed.",
            "rationale": "The full app cannot be diagnosed from these inputs.",
        }
    else:
        script = data["turns"][0]["agent_script"]
        script.update(
            user_draft="Can you share the parent callback?",
            next_question="Can you share the parent callback?",
            missing_info=["parent_callback_code"],
        )
    live = FakeLive(tmp_path, data)
    receipt = runner.run([write(tmp_path, data)], mode="live", live=live)
    assert failed(receipt) == []  # Both routes are allowed by this turn's gold.
    assert len(live.case_ids) == 1
    assert receipt["summary"]["fixture_branches_unavailable"] == 1
    assert not receipt["summary"]["coverage_complete"]
    assert receipt["summary"]["cases_all_passed"] == 0
    assert not receipt["cases"][0]["summary"]["coverage_complete"]
    assert receipt["cases"][0]["steps"][1]["runner_stop"] == "FixtureBranchUnavailable"
    assert receipt["quality_claim"] is False


def test_live_config_cannot_write_credentials_into_a_receipt(tmp_path):
    live = FakeLive(tmp_path)
    live.config["api_key"] = "synthetic-credential-that-must-not-be-exported"
    with pytest.raises(ValueError, match="^LiveConfigInvalid$"):
        runner.run([FIXTURE], mode="live", live=live)
    assert live.case_ids == []


def test_incomplete_live_fixture_branch_has_a_distinct_cli_exit(tmp_path, monkeypatch):
    data = fixture_data()
    script = data["turns"][0]["agent_script"]
    script.update(
        user_draft="Can you share the parent callback?",
        next_question="Can you share the parent callback?",
        missing_info=["parent_callback_code"],
    )
    live = FakeLive(tmp_path, data)
    monkeypatch.setattr(runner, "_load_live", lambda _spec: live)
    output = tmp_path / "live" / "receipt.json"
    assert (
        runner.main(
            [
                str(write(tmp_path, data)),
                "--mode",
                "live",
                "--adapters",
                "synthetic:only",
                "--output",
                str(output),
            ]
        )
        == 2
    )
    receipt = json.loads(output.read_text())
    assert receipt["summary"]["failed"] == 0
    assert receipt["summary"]["coverage_complete"] is False


def test_exclusive_receipt_write_preserves_a_file_created_during_execution(tmp_path, monkeypatch):
    output = tmp_path / "offline" / "receipt.json"
    original = runner.run

    def race(paths, **kwargs):
        receipt = original(paths, **kwargs)
        output.parent.mkdir()
        output.write_text("existing receipt remains intact\n")
        return receipt

    monkeypatch.setattr(runner, "run", race)
    with pytest.raises(FileExistsError):
        runner.main([str(FIXTURE), "--output", str(output)])
    assert output.read_text() == "existing receipt remains intact\n"
