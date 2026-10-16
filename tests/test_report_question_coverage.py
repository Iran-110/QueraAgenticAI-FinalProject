import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "report_question_coverage", ROOT / "scripts/report_question_coverage.py"
)
coverage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(coverage)
VOCABULARY = {"app_state_code", "updated_form_code"}


def _turn(turn_id, acceptable, **visible):
    return {
        "id": turn_id,
        "visible": visible,
        "gold": {"acceptable_decisions": acceptable, "gaps": []},
    }


def _fixture(turns, routes):
    return {
        "case": {"case_id": "case-x"},
        "turns": turns,
        "evaluation": {"coverage": {"routes": routes}},
    }


def _ask(from_turn, to_turn, target):
    return {
        "from_turn": from_turn,
        "to_turn": to_turn,
        "guard": {"decision": "ask", "question_target": target},
    }


def test_unknowns_carry_over_and_a_reply_makes_the_target_known():
    fixture = _fixture(
        [
            _turn("initial", ["ask"], unknowns=["streamlit_version", "app_state_code"]),
            _turn("version", ["ask"]),
            _turn("code", ["answer"], reported_facts=[{"name": "app_state_code", "value": "x"}]),
        ],
        [
            _ask("initial", "version", "streamlit_version"),
            _ask("version", "code", "app_state_code"),
            {"from_turn": "code", "to_turn": None, "guard": {"decision": "answer"}},
        ],
    )

    rows = coverage.branch_rows(fixture, VOCABULARY)

    assert [(r["turn_id"], r["question_source"], r["available_on_turn"]) for r in rows] == [
        ("initial", "built_in_version", True),
        ("version", "vocabulary", True),
    ]
    assert coverage.unneeded_offers(fixture, VOCABULARY) == []


def test_missing_vocabulary_entry_is_a_limitation_and_extra_offers_are_listed():
    fixture = _fixture(
        [_turn("initial", ["ask"], unknowns=["entry_page"]), _turn("next", ["answer"])],
        [_ask("initial", "next", "entry_page")],
    )

    (row,) = coverage.branch_rows(fixture, VOCABULARY)

    assert row["question_source"] == "not_in_vocabulary"
    assert not row["available_on_turn"]
    # No version fact yet, so the built-in version question is on offer where ask is not accepted.
    assert coverage.unneeded_offers(fixture, VOCABULARY) == [
        {"case_id": "case-x", "turn_id": "next", "offered": ["streamlit_version"]}
    ]


def test_committed_dev_section_matches_a_rebuild():
    committed = json.loads(
        (ROOT / "data/evaluation/split-e1-v1/question-coverage-v1.json").read_text(encoding="utf-8")
    )
    rebuilt, _ = coverage.build(splits=("dev",))

    assert rebuilt["splits"]["dev"] == committed["splits"]["dev"]
    assert set(committed["splits"]["test"]) == {"fixtures_checked", "summary"}
