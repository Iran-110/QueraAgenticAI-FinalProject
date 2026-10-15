"""Preserve the offline experiment's exact baseline and negative observations."""

import json
from pathlib import Path

import pytest

from agent_app.testing.selection_context_replay import PACKET, ROOT, run_replay


@pytest.fixture(scope="module")
def report():
    return run_replay()


def test_replay_reproduces_retained_receipt_with_every_default_and_authored_state(report):
    retained = json.loads((ROOT / PACKET / "replay-v1.json").read_bytes())
    assert json.loads(json.dumps(report)) == retained
    assert report["all_checks_passed"]
    assert report["checks_passed"] == report["checks_total"] == 81
    assert report["legacy_default_states_checked"] == 24
    assert len(report["authored_neutral_rows"]) == 8
    assert report["actual_API_calls"] == report["ledger_or_index_clients_created"] == 0
    assert report["new_model_selection_or_semantic_quality_claim"] is False
    assert report["held_out_or_RAG_quality"] is False
    assert report["human_usefulness"] is None


def test_remaining_false_positive_false_negative_and_old_source_are_not_hidden(report):
    rows = {row["scenario_id"]: row for row in report["authored_neutral_rows"]}
    correction = rows["retired-topic-correction"]
    assert correction["legacy"]["ranked_units"][0]["source_index"] == 0
    assert correction["typed_advisory"]["ranked_units"][0]["source_index"] == 1
    # The old topic can remain in other unretired history words and the shortlist.
    assert {ref[0] for ref in correction["typed_advisory"]["shortlist"]["passages"]} == {0, 1}
    negation = rows["latest-negation-counterexample"]["typed_advisory"]
    assert negation["ranked_units"][0]["source_index"] == 0
    synonym = rows["synonym-counterexample"]["typed_advisory"]
    assert synonym["shortlist"]["passages"] == ()
    for row in rows.values():
        assert row["model_proposals_created"] == 0
        assert row["typed_advisory"]["inspection"]["semantic_support"] is None
        assert row["typed_advisory"]["inspection"]["human_review_required"] is True


def test_changed_frozen_fixture_fails_before_any_request_or_ranking(tmp_path, monkeypatch):
    folder = tmp_path / PACKET
    folder.mkdir(parents=True)
    pins = json.loads((ROOT / PACKET / "input-pins-v1.json").read_bytes())
    for relative in pins["source_and_inputs"]:
        if relative.startswith("src/"):
            continue
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((ROOT / relative).read_bytes())
    (folder / "input-pins-v1.json").write_text(json.dumps(pins))
    scenario_file = folder / "scenarios-v1.json"
    scenario_file.write_bytes(scenario_file.read_bytes() + b"\n")

    def no_request(*args, **kwargs):
        pytest.fail("Altered frozen packet reached request construction")

    monkeypatch.setattr(
        "agent_app.testing.selection_context_replay.build_claim_request", no_request
    )
    with pytest.raises(ValueError, match="^FrozenContextInputMismatch$"):
        run_replay(Path(tmp_path))
