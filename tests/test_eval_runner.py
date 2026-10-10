import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_app import api
from agent_app.contracts import AnalysisResult, EvidenceBundle
from agent_app.evaluation import pilot, runner
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


class FakeLedger:
    """Charges a fixed amount per run; records tokens under the real request IDs."""

    def __init__(self):
        self.spent = Decimal(0)

    def charge(self, amount):
        self.spent += amount

    def snapshot(self):
        return SimpleNamespace(
            settled_usd=self.spent, reserved_usd=Decimal(0), uncertain_usd=Decimal(0)
        )

    def get(self, _request_id):
        return SimpleNamespace(input_tokens=100, output_tokens=20)


class FakeLive:
    """Stands in for real adapters; it only ever sees case IDs."""

    def __init__(self):
        self.ledger = FakeLedger()
        self.config = {"model": "fake-model", "snapshot_id": "fake-snapshot"}
        self.case_ids = []
        data = fixture_data()
        source = json.loads((runner.ROOT / data["evidence_source"]["path"]).read_text())
        self.bundles = [
            EvidenceBundle.model_validate(source["evidence_bundles"][turn["evidence_bundle"]])
            for turn in data["turns"]
        ]
        self.scripts = [AnalysisResult.model_validate(t["agent_script"]) for t in data["turns"]]

    def for_case(self, case_id):
        self.case_ids.append(case_id)
        self.ledger.charge(Decimal("0.001"))
        bundle = self.bundles.pop(0)
        return api.RunAdapters(
            FakeRetriever([bundle]),
            FakeReasoner([self.scripts.pop(0)]),
            snapshot_id=bundle.snapshot_id,
        )


def test_live_mode_records_cost_tokens_and_config():
    live = FakeLive()
    receipt = runner.run([FIXTURE], mode="live", live=live)
    assert live.case_ids == ["dev-pilot-12782"] * 4
    assert receipt["mode"] == "live"
    assert receipt["config"]["model"] == "fake-model"
    assert receipt["snapshots"] == ["fake-snapshot"]
    assert receipt["summary"]["cost_usd_total"] == "0.004"
    assert receipt["cases"][0]["steps"][0]["usage"]["input_tokens"] == 100


def test_mode_and_adapters_must_agree():
    with pytest.raises(ValueError):
        runner.run([FIXTURE], mode="live")
    with pytest.raises(ValueError):
        runner.run([FIXTURE], live=FakeLive())


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
