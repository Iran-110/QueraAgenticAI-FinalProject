"""The E2ac human confirmation binds the exact amendment, registration and fixture bytes."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "data/evaluation/split-e1-v1/native/"
CONFIRMATION = PREFIX + "native-dev-e2ac-human-confirmation-v1.json"
AMENDMENT = PREFIX + "native-dev-gold-amendment-v2.json"
REGISTRATION = PREFIX + "native-registration-dev-v2.json"


def _sha(name):
    return hashlib.sha256((ROOT / name).read_bytes()).hexdigest()


def _load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def test_confirmation_binds_current_amendment_registration_and_fixtures():
    confirmation, amendment = _load(CONFIRMATION), _load(AMENDMENT)
    assert confirmation["amendment"] == {"path": AMENDMENT, "sha256": _sha(AMENDMENT)}
    assert confirmation["registration"] == {"path": REGISTRATION, "sha256": _sha(REGISTRATION)}
    expected = {item["case_id"]: item["fixture_path"] for item in amendment["items"]}
    assert {f["case_id"]: f["path"] for f in confirmation["fixtures"]} == expected
    for fixture in confirmation["fixtures"]:
        assert fixture["sha256"] == _sha(fixture["path"])
    pending = set(_load(REGISTRATION)["human_confirmation_pending"])
    assert {item["case_id"] for item in confirmation["items"]} == pending


def test_confirmation_is_human_assistant_informed_and_scoped_to_escalation():
    confirmation = _load(CONFIRMATION)
    assert confirmation["reviewer_kind"] == "human"
    assert confirmation["independence"] == "assistant_informed"
    assert confirmation["pins"].startswith("pending_final_build")
    for item in confirmation["items"]:
        assert item["json_pointer"] == "/turns/0/gold/decision_conditions/escalate"
        assert item["verdict"] == "correct"
    assert confirmation["summary"] == {"correct": 2, "wrong": 0, "unsure": 0}
