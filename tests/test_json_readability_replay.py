"""Historical failures and exact presentation boundaries remain auditable."""

import json
from pathlib import Path

import pytest

from agent_app.contracts import GroundedRequest

ROOT = Path(__file__).resolve().parents[1]


def module(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    import json_readability_render_replay

    return json_readability_render_replay


def test_replay_preserves_all_historical_turns_and_unparsed_output(monkeypatch):
    replay = module(monkeypatch)
    result = replay.build_report(
        ROOT / "experiments/core_ask_background_v1/model-live-receipt-v1.json"
    )
    assert result["planned_turns"] == 12
    assert result["turn_statuses"] == {"fresh_proposal": 11, "stale_observation": 1}
    assert len(result["actual_attempts_including_unparsed"]) == 14
    assert (
        sum(
            not row["canonical_plan_observed"]
            for row in result["actual_attempts_including_unparsed"]
        )
        == 1
    )
    assert result["new_provider_calls"] == 0 and result["human_usefulness"] is None


def test_actual_plan_replay_rejects_any_extra_rationale_claim(monkeypatch):
    replay = module(monkeypatch)
    receipt = json.loads(
        (ROOT / "experiments/core_ask_background_v1/model-live-receipt-v1.json").read_bytes()
    )
    attempt = next(
        attempt
        for batch in receipt["batches"]
        for attempt in batch["attempts"]
        if attempt["context"]["case_id"] == "dev-case-c"
        and attempt.get("plan", {}).get("decision") == "answer"
    )
    original = replay.render_grounded_plan

    def tamper(*args, **kwargs):
        result = original(*args, **kwargs)
        if kwargs.get("concise_user_draft"):
            result = result.model_copy(update={"rationale": result.rationale + " Extra claim."})
        return result

    monkeypatch.setattr(replay, "render_grounded_plan", tamper)
    with pytest.raises(AssertionError):
        replay.pair(GroundedRequest.model_validate(attempt["request"]), attempt["plan"])
