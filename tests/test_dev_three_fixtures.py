"""Integrity and operational routes for the exposed three-case draft packet.

These checks do not grade the model, entailment, human usefulness or final E1.
"""

import hashlib
import json
from pathlib import Path

import pytest

from agent_app.evaluation import runner
from agent_app.evaluation.routes import ConditionalRoutesRejected, RouteGraph

ROOT = Path(__file__).resolve().parent.parent
PACKET = ROOT / "data/evaluation/dev-three-v1"
CASES = PACKET / "cases"
CASE_FILES = ("pilot-12782-v1.json", "icon-9770-v1.json", "enum-8129-v1.json")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("filename", CASE_FILES)
def test_fixture_loads_and_has_a_bounded_conditional_graph(filename):
    fixture = runner.load_fixture(CASES / filename)
    graph = RouteGraph.from_fixture(fixture.data)
    assert len(graph.node_ids) == 2
    assert fixture.data["boundaries"]["max_reached_turns"] == 2
    assert fixture.case["split"] == "dev"
    assert fixture.case["test_eligible"] is False
    assert fixture.data["initial_report_provenance"]["original_initial_text_verified"] is False
    assert all(turn["gold"]["human_reviewed"] is False for turn in fixture.data["turns"])
    assert all(turn["gold"]["usefulness_score"] is None for turn in fixture.data["turns"])


def test_historical_split_fixture_and_metadata_reservations_are_preserved():
    expected = {
        "data/evaluation/split-manifest.json": "78e630cbef86937f2838795a2329ee56e16ea0beef7900db5c63d5fede6404ff",
        "data/evaluation/dev/pilot-12782.json": "f4b9cef54c98dd875ff0e55f41aebcde19a9b02717b7cb8c5525eba9575f2855",
        "data/evaluation/candidates/reservations-v1.json": "e1bcded192d7bf5c82a8883a3e6234d5df38b01f6d30b7b2d6dd706e7d21031b",
    }
    assert {path: digest(ROOT / path) for path in expected} == expected


def test_selected_families_are_dev_candidates_with_conservative_related_closure():
    reservations = read(ROOT / "data/evaluation/candidates/reservations-v1.json")
    dev_ids = {
        issue
        for case in reservations["candidates"]
        if case["proposed_split"] == "dev"
        for issue in case["issue_ids"]
    }
    test_ids = {
        issue
        for case in reservations["candidates"]
        if case["proposed_split"] == "test"
        for issue in case["issue_ids"]
    }
    fixtures = runner.collect([CASES])
    origins = {int(fixture.case["origin_url"].rsplit("/", 1)[1]) for fixture in fixtures}
    families = [set(fixture.case["family_issue_ids"]) for fixture in fixtures]
    assert origins == {12782, 9770, 8129}
    assert origins <= dev_ids
    assert set.union(*families).isdisjoint(test_ids)
    assert all(a.isdisjoint(b) for i, a in enumerate(families) for b in families[i + 1 :])
    assert read(CASES / "enum-8129-v1.json")["case"]["family_issue_ids"] == [2379, 8129, 8180]


def test_fixed_docs_excerpts_have_real_seed_hashes_and_exact_complete_spans():
    evidence = read(PACKET / "evidence-v1.json")
    hits = {
        hit["chunk_id"]: hit
        for bundle in evidence["evidence_bundles"].values()
        for hit in bundle["hits"]
    }
    assert set(hits) == {source["chunk_id"] for source in evidence["source_records"]}
    for name, expected in evidence["source_pins"].items():
        assert digest(ROOT / name) == expected
    for source in evidence["source_records"]:
        records = [
            json.loads(line) for line in (ROOT / source["seed_path"]).read_text().splitlines()
        ]
        matches = [record for record in records if record["source_id"] == source["source_id"]]
        assert len(matches) == 1
        record = matches[0]
        text = record["text"]
        span = source["span"]
        assert span["unit"] == "unicode_codepoint"
        assert 0 <= span["start"] < span["end"] <= len(text)
        assert hashlib.sha256(text.encode()).hexdigest() == source["source_record_text_sha256"]
        hit = hits[source["chunk_id"]]
        assert hit["excerpt"] == text[span["start"] : span["end"]]
        assert hashlib.sha256(hit["excerpt"].encode()).hexdigest() == source["excerpt_sha256"]
        assert hit["source_type"] == "doc"
        assert hit["source_commit"] == record["docs_commit"]
        assert hit["source_url"] == record["source_url"]
        assert hit["applicable_versions"] == ([record["version"]] if "version" in record else [])
        if source["selection_unit"] == "whole_record":
            assert (span["start"], span["end"]) == (0, len(text))
        else:
            assert hit["excerpt"].startswith("default:")
            assert text[span["end"] :].startswith("help:")


def test_version_replies_follow_only_the_registered_canonical_question():
    for filename in ("pilot-12782-v1.json", "icon-9770-v1.json"):
        data = read(CASES / filename)
        graph = RouteGraph.from_fixture(data)
        matching = [route for route in graph.routes if route.target == "version"]
        assert len(matching) == 1
        assert matching[0].question_target == "streamlit_version"
        assert data["turns"][1]["visible"]["reply_to_approved_question"] is True
        assert "counterfactual" in data["turns"][1]["conversation_source"]


def test_a_version_reply_cannot_be_bound_to_the_callback_question():
    data = read(CASES / "pilot-12782-v1.json")
    data["evaluation"]["coverage"]["routes"][0]["guard"]["question_target"] = "parent_callback_code"
    with pytest.raises(ConditionalRoutesRejected):
        RouteGraph.from_fixture(data)


def test_known_enum_version_and_full_code_are_not_manufactured_user_gaps():
    data = read(CASES / "enum-8129-v1.json")
    initial, correction = data["turns"]
    facts = {fact["name"]: fact["value"] for fact in initial["visible"]["reported_facts"]}
    assert facts["streamlit_version"] == "1.31.0"
    assert "class Color(Enum):" in facts["reported_reproduction_code"]
    assert facts["reported_reproduction_code"] in initial["visible"]["message"]
    assert initial["visible"]["unknowns"] == []
    assert initial["gold"]["gaps"] == []
    assert initial["maintainer"]["decision"] == "none"
    assert correction["expect"]["previous_proposal_now_stale"] is True
    assert correction["visible"]["reported_facts"] == [
        {"name": "streamlit_version", "value": "1.31.1"}
    ]
    assert correction["visible"]["context_changed"] is False
    assert "counterfactual" in correction["conversation_source"]


def test_source_gap_conditions_do_not_authorize_an_enum_fix_or_repeat_known_facts():
    data = read(CASES / "enum-8129-v1.json")
    for turn in data["turns"]:
        assert set(turn["gold"]["acceptable_decisions"]) == {"answer", "escalate"}
        assert "strictly qualified" in turn["gold"]["decision_conditions"]["answer"]
        assert "ask" not in turn["gold"]["decision_conditions"]
        assert any("verified fix" in claim for claim in turn["gold"]["unacceptable_claims"])


def test_evidence_and_initial_inputs_do_not_contain_withheld_enum_answer():
    evidence = read(PACKET / "evidence-v1.json")
    assert all(
        "custom-classes" not in hit["source_url"]
        for bundle in evidence["evidence_bundles"].values()
        for hit in bundle["hits"]
    )
    enum = read(CASES / "enum-8129-v1.json")
    initial = enum["turns"][0]["visible"]
    assert "colors.py" not in initial["message"]
    assert "from colors import Color" not in initial["message"]
    assert "1.31.1" not in initial["message"]
    exposure = read(PACKET / "exposure-review-v1.json")
    assert exposure["human_reviewed"] is False
    assert exposure["e1_complete"] is False
    assert any(
        "custom-classes" in item["source_url"]
        for item in exposure["direct_answer_documents_excluded"]
    )


def test_fixed_vs_actual_index_source_conditions_are_not_conflated():
    review = read(PACKET / "scenario-review-v1.json")
    assert review["evidence_condition"] == "controlled_fixed_evidence"
    assert review["actual_index_condition"]["quality_claim"] is False
    assert "lacks" in review["actual_index_condition"]["note"]
    assert review["human_reviewed"] is False
    assert review["usefulness_score"] is None


def test_scripted_routes_pass_with_correction_stale_approval_and_event_replay():
    receipt = runner.run([CASES], conditional_routes=True)
    assert receipt["mode"] == "offline"
    assert receipt["quality_claim"] is False
    assert receipt["summary"]["cases"] == 3
    assert receipt["summary"]["turns"] == 6
    assert receipt["summary"]["failed"] == 0
    assert receipt["summary"]["cases_all_passed"] == 3
    assert receipt["summary"]["cost_usd_total"] == "0"
    assert receipt["summary"]["coverage_complete"] is True
    assert receipt["tracker_backend"] == "process_memory_dummy_tracker"
    enum = next(case for case in receipt["cases"] if case["case_id"] == "dev-case-c")
    assert any(
        check["check"] == "stale proposal approval refused" and check["passed"]
        for check in enum["checks"]
    )
    assert any(
        check["check"] == "stale draft never released" and check["passed"]
        for check in enum["checks"]
    )
    for case in receipt["cases"]:
        assert case["conditional_routes"]["selected_path_complete"] is True
        assert case["conditional_routes"]["executed_turn_ids"] == [
            turn["id"] for turn in read(ROOT / case["fixture_path"])["turns"]
        ]
        assert all(
            check["passed"] for check in case["checks"] if check["check"].startswith("replay ")
        )
