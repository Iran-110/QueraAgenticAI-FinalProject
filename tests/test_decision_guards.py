"""Decision guard regressions from offline adversarial review.

These test operational handling of provenance and query context. They do not
establish that an arbitrary cited technical claim follows its source.
"""

import pytest

from agent_app.contracts import (
    AnalysisResult,
    CaseState,
    EvidenceBundle,
    EvidenceHit,
    EvidenceLink,
    Fact,
)
from agent_app.orchestration import SupportEngine
from agent_app.orchestration.engine import build_initial_query
from agent_app.testing.fakes import FakeReasoner, FakeRetriever

SNAPSHOT = "decision-guard-fixture"


def fact(name="streamlit_version", value="1.50", **changes):
    return Fact(
        **(
            {
                "name": name,
                "value": value,
                "source_ref": "event:user:1",
                "turn_id": "turn:1",
            }
            | changes
        )
    )


def evidence_fact(name="streamlit_version", value="1.2", **changes):
    return fact(
        name,
        value,
        **({"source_ref": "docs:example", "provenance_kind": "evidence"} | changes),
    )


def answer(**changes):
    return AnalysisResult(
        **(
            {
                "decision": "answer",
                "user_draft": "This is a synthetic source-backed proposal.",
                "maintainer_summary": "A synthetic source accompanies the proposal.",
                "rationale": "The fixture is only for operational guard testing.",
                "evidence_links": (
                    EvidenceLink(claim="Synthetic documented example", chunk_id="docs:example"),
                ),
            }
            | changes
        )
    )


def ask_version():
    return answer(
        decision="ask",
        user_draft="Please confirm the installed Streamlit version.",
        maintainer_summary="The actual environment version needs user confirmation.",
        evidence_links=(),
        missing_info=("streamlit_version",),
        next_question="Which Streamlit version is installed in this environment?",
    )


def run(case, response):
    bundle = EvidenceBundle(
        snapshot_id=SNAPSHOT,
        hits=(
            EvidenceHit(
                chunk_id="docs:example",
                source_id="source:example",
                excerpt="Synthetic example environment; not the user's installed version.",
                source_url="https://example.org/synthetic-decision-fixture",
                source_type="doc",
            ),
        ),
    )
    reasoner = FakeReasoner([response, answer()])
    engine = SupportEngine(FakeRetriever([bundle]), reasoner, snapshot_id=SNAPSHOT)
    result = engine.run(case, "My widget state resets.")
    return result, reasoner


@pytest.mark.parametrize("delta_name", ["streamlit_version", "Streamlit_Version"])
def test_evidence_delta_cannot_replace_a_confirmed_user_value(delta_name):
    case = CaseState(case_id="case:guards", case_revision=3, facts=(fact(),))
    before = case.model_dump()
    result, reasoner = run(case, answer(facts_delta=(evidence_fact(delta_name),)))

    assert result.status == "error"
    assert result.error_code == "ConflictingEvidenceFact"
    assert result.analysis is None
    assert result.model_attempts == len(reasoner.inputs) == 1
    assert case.model_dump() == before


def test_an_evidence_observation_may_match_the_confirmed_user_value():
    case = CaseState(case_id="case:guards", facts=(fact(),))
    before = case.model_dump()
    observed = evidence_fact(value="1.50")
    result, _ = run(case, answer(facts_delta=(observed,)))

    assert result.status == "awaiting_approval"
    assert result.analysis.facts_delta == (observed,)
    assert case.model_dump() == before


def test_distinct_documented_behavior_is_not_a_user_fact_conflict():
    case = CaseState(case_id="case:guards", facts=(fact(),))
    documented = evidence_fact(name="documented_example_version", value="1.2")
    result, _ = run(case, answer(facts_delta=(documented,)))

    assert result.status == "awaiting_approval"


def test_superseded_user_value_does_not_block_an_evidence_observation():
    case = CaseState(case_id="case:guards", facts=(fact(status="superseded"),))
    result, _ = run(case, answer(facts_delta=(evidence_fact(),)))

    assert result.status == "awaiting_approval"


def test_an_evidence_example_does_not_prevent_asking_for_the_actual_environment():
    case = CaseState(case_id="case:guards", facts=(evidence_fact(),))
    result, reasoner = run(case, ask_version())

    assert result.status == "awaiting_approval"
    assert result.analysis.decision == "ask"
    assert result.analysis.missing_info == ("streamlit_version",)
    assert result.model_attempts == len(reasoner.inputs) == 1


def test_confirmed_user_environment_is_still_protected_from_repeated_questions():
    case = CaseState(case_id="case:guards", facts=(fact(name="Streamlit_Version"),))
    result, reasoner = run(case, ask_version())

    assert result.status == "error"
    assert result.error_code == "KnownFactMarkedMissing"
    assert result.analysis is None
    assert result.model_attempts == len(reasoner.inputs) == 1


def test_long_early_description_does_not_hide_the_confirmed_environment_version():
    long_description = fact("description", "z" * 500)
    case = CaseState(case_id="case:query", facts=(long_description, fact()))
    query = build_initial_query(case, "My widget state resets.")

    assert "streamlit_version=1.50" in query
    assert "description=" not in query
    assert "z" not in query
    assert len(query) <= 500


def test_query_packs_multiple_whole_environment_facts_after_a_long_message():
    message = "m" * 450
    case = CaseState(
        case_id="case:query",
        facts=(
            fact("operating_system", "Linux"),
            fact("python_version", "3.13"),
            fact(),
        ),
    )
    query = build_initial_query(case, message)

    assert query.startswith("m" * 400)
    assert "m" * 401 not in query
    assert "streamlit_version=1.50" in query
    assert "python_version=3.13" in query
    assert "operating_system=Linux" in query
    assert len(query) <= 500


def test_query_fact_order_is_stable_and_environment_facts_have_priority():
    facts = (
        fact("z_context", "z"),
        fact("widget_definition", "slider"),
        fact("python_version", "3.13"),
        fact("browser_version", "1"),
        fact("error_message", "error"),
        fact("a_context", "a"),
        fact("operating_system", "Linux"),
        fact(),
    )
    query = build_initial_query(CaseState(case_id="case:query", facts=facts), "Reset.")
    reversed_query = build_initial_query(
        CaseState(case_id="case:query", facts=tuple(reversed(facts))), "Reset."
    )
    expected = (
        "streamlit_version=1.50",
        "python_version=3.13",
        "operating_system=Linux",
        "browser_version=1",
        "error_message=error",
        "widget_definition=slider",
        "a_context=a",
        "z_context=z",
    )

    assert query == reversed_query
    positions = [query.index(item) for item in expected]
    assert positions == sorted(positions)
    assert len(query) <= 500


def test_oversized_environment_fact_is_skipped_without_cutting_its_value():
    case = CaseState(
        case_id="case:query",
        facts=(fact("error_message", "e" * 1_000), fact("widget_definition", "slider")),
    )
    query = build_initial_query(case, "Reset.")

    assert "error_message=" not in query
    assert "widget_definition=slider" in query
    assert len(query) <= 500


def test_retrieval_query_excludes_source_examples_and_superseded_environment():
    case = CaseState(
        case_id="case:query",
        facts=(
            fact(value="obsolete-version", status="superseded"),
            evidence_fact("example_environment", "source-only-version"),
            fact(value="1.50", turn_id="turn:2", source_ref="event:user:2"),
        ),
    )
    query = build_initial_query(case, "Reset.")

    assert "streamlit_version=1.50" in query
    assert "obsolete-version" not in query
    assert "example_environment" not in query
    assert "source-only-version" not in query
