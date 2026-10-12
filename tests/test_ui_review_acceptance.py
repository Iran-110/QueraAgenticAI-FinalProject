from pathlib import Path

from agent_app.testing.ui_review_acceptance import run

ROOT = Path(__file__).resolve().parents[1]


def test_registered_control_rejects_previous_client(tmp_path):
    receipt = run(ROOT, tmp_path, baseline=True)
    assert receipt["passed"] == 2
    assert receipt["total"] == 6
    assert receipt["accepted"] is False
    assert receipt["quality_claim"] is False


def test_lost_ack_retries_exact_review_after_correction_and_recreation(tmp_path):
    receipt = run(ROOT, tmp_path)
    assert receipt["passed"] == receipt["total"] == 6
    assert receipt["accepted"] is True
    assert receipt["provider_calls"] == receipt["paid_cost_usd"] == 0
