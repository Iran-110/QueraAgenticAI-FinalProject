"""Archived plans are deterministic controls, never retrospectively new quality."""

from pathlib import Path

import pytest

from agent_app.testing.repeat_query_replay import RECEIPT, observed_repeat_plans, replay

ROOT = Path(__file__).resolve().parents[1]


def test_actual_archived_repeat_plans_repair_without_new_retrieval_or_user_gap():
    receipt = replay(ROOT)
    assert receipt["accepted"]
    assert receipt["checks_total"] == receipt["checks_passed"] == 42
    assert receipt["real_model_calls"] == 0
    assert not receipt["quality_claim"]
    assert receipt["authored_escalation_fallback"]
    for row in receipt["observations"]:
        assert row["arms"]["off"]["result"]["analysis"] is None
        fallback = row["arms"]["on"]["result"]["analysis"]
        assert not fallback["missing_info"]
        assert "investigat" in fallback["maintainer_summary"].casefold()


def test_original_receipt_changed_cannot_be_reinterpreted_as_new_controls(tmp_path):
    target = tmp_path / RECEIPT
    target.parent.mkdir(parents=True)
    target.write_bytes((ROOT / RECEIPT).read_bytes() + b"\n")
    with pytest.raises(ValueError, match="^RepeatReplayArchiveChanged$"):
        observed_repeat_plans(tmp_path)
