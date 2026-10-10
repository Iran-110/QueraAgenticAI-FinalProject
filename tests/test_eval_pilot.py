import json
from pathlib import Path

import pytest

from agent_app.evaluation import pilot

FIXTURE = Path(__file__).resolve().parent.parent / "data/evaluation/dev/pilot-12782.json"


def failed(receipt):
    return [(c["step"], c["check"]) for c in receipt["checks"] if not c["passed"]]


def write(tmp_path, fixture):
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")
    return path


def test_registered_pilot_passes_every_check():
    receipt = pilot.run(FIXTURE)
    assert failed(receipt) == []
    assert receipt["summary"]["checks"] >= 40
    assert receipt["real_model_calls"] == 0
    assert receipt["quality_claim"] is False


def test_pilot_receipt_is_deterministic():
    assert pilot.run(FIXTURE)["steps"] == pilot.run(FIXTURE)["steps"]


def test_wrong_expectation_is_reported(tmp_path):
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    fixture["turns"][2]["expect"]["active_facts"]["streamlit_version"] = "1.50.0"
    assert ("p1-turn-3", "active fact streamlit_version") in failed(
        pilot.run(write(tmp_path, fixture))
    )


def test_rejected_question_leaves_reply_unbound(tmp_path):
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    fixture["turns"][0]["maintainer"]["decision"] = "reject"
    checks = failed(pilot.run(write(tmp_path, fixture)))
    assert ("p1-turn-1", "released drafts") in checks
    assert ("p1-turn-2", "intake preparation") in checks


def test_changed_evidence_source_is_refused(tmp_path):
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    fixture["evidence_source"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="SHA-256"):
        pilot.run(write(tmp_path, fixture))


def test_main_refuses_to_overwrite_receipt(tmp_path):
    output = tmp_path / "receipt.json"
    assert pilot.main([str(FIXTURE), "--output", str(output)]) == 0
    with pytest.raises(SystemExit):
        pilot.main([str(FIXTURE), "--output", str(output)])
