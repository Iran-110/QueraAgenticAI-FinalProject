"""Current-installation source filtering, not semantic entailment verification."""

import pytest

from agent_app.contracts import (
    AnalysisResult,
    CaseState,
    EvidenceBundle,
    EvidenceHit,
    EvidenceLink,
    Fact,
    ReportedFact,
    UserTurn,
)
from agent_app.orchestration import SupportEngine
from agent_app.orchestration.turns import propose_user_turn
from agent_app.testing.fakes import FakeReasoner, FakeRetriever

SNAPSHOT = "scope-fixture"


def hit(chunk_id, versions=()):
    return EvidenceHit(
        chunk_id=chunk_id,
        source_id=f"doc:{chunk_id}",
        excerpt="Authored fixture for source-scope behavior only.",
        source_url="https://example.org/source-scope-fixture",
        source_type="doc",
        applicable_versions=versions,
    )


def state(value="1.50.0", **changes):
    return CaseState(
        case_id="scope-case",
        facts=(
            Fact(
                name="streamlit_version",
                value=value,
                source_ref="user:initial",
                turn_id="initial",
                **changes,
            ),
        ),
    )


def proposal(decision="escalate", **changes):
    return AnalysisResult(
        decision=decision,
        user_draft="The supplied sources do not establish the full application cause.",
        maintainer_summary="Source scope is tested without a generated model response.",
        rationale="A source-scope filter does not establish source entailment.",
        **changes,
    )


def run(case, hits, responses, scope="exact_user_version"):
    retriever = FakeRetriever([EvidenceBundle(snapshot_id=SNAPSHOT, hits=tuple(hits))])
    reasoner = FakeReasoner(responses)
    engine = SupportEngine(retriever, reasoner, snapshot_id=SNAPSHOT, evidence_scope=scope)
    return engine.run(case, "My widget state is unexpected."), reasoner


@pytest.mark.parametrize(
    "case,expected",
    [
        (state(), {"current", "shared", "unscoped"}),
        (state("1.49.0"), {"old", "shared", "unscoped"}),
        (state("1.49.1"), {"unscoped"}),
        (CaseState(case_id="scope-case"), {"unscoped"}),
        (state(provenance_kind="evidence"), {"unscoped"}),
        (state(status="superseded"), {"unscoped"}),
    ],
)
def test_only_active_user_version_establishes_exact_scope(case, expected):
    hits = (
        hit("current", ("1.50.0",)),
        hit("old", ("1.49.0",)),
        hit("shared", ("1.49.0", "1.50.0")),
        hit("unscoped"),
    )
    before = case.model_dump()
    result, reasoner = run(case, hits, [proposal()])
    assert result.status == "awaiting_approval"
    assert {item.chunk_id for item in reasoner.inputs[0][2].hits} == expected
    assert any(event.stage == "evidence_scoped" for event in result.trace)
    assert case.model_dump() == before
    assert len(hits) == 4


def test_default_preserves_mixed_sources_and_historical_comparisons():
    sources = (hit("current", ("1.50.0",)), hit("old", ("1.49.0",)))
    answer = proposal(
        "answer",
        evidence_links=(EvidenceLink(claim="A historical comparison only.", chunk_id="old"),),
    )
    result, reasoner = run(state(), sources, [answer], scope="all")
    assert result.status == "awaiting_approval"
    assert reasoner.inputs[0][2].hits == sources
    assert not any(event.stage == "evidence_scoped" for event in result.trace)


def test_correction_then_returned_old_chunk_cannot_be_cited_under_exact_scope():
    original = state("1.49.0")
    corrected = propose_user_turn(
        original,
        UserTurn(
            case_id=original.case_id,
            expected_revision=0,
            turn_id="correction",
            source_ref="user:correction",
            message="Correction: this environment uses 1.50.0.",
            reported_facts=(ReportedFact(name="streamlit_version", value="1.50.0"),),
        ),
    ).candidate
    answer = proposal(
        "answer",
        evidence_links=(EvidenceLink(claim="Applies to the installation.", chunk_id="old"),),
    )
    baseline, _ = run(corrected, [hit("old", ("1.49.0",))], [answer], scope="all")
    candidate, reasoner = run(corrected, [hit("old", ("1.49.0",))], [answer, answer])
    assert baseline.status == "awaiting_approval"
    assert candidate.error_code == "UnknownEvidenceReference"
    assert candidate.model_attempts == 1
    assert reasoner.inputs[0][2].hits == ()


def test_refinement_scopes_each_latest_bundle_without_resurrecting_prior_hits():
    bundles = [
        EvidenceBundle(snapshot_id=SNAPSHOT, hits=(hit("current", ("1.50.0",)),)),
        EvidenceBundle(snapshot_id=SNAPSHOT, hits=(hit("old", ("1.49.0",)),)),
    ]
    reasoner = FakeReasoner(
        [
            AnalysisResult(
                decision="retrieve_more",
                user_draft="",
                maintainer_summary="",
                rationale="Seek applicable documentation.",
                retrieval_queries=("exact current-version documentation",),
            ),
            proposal(),
        ]
    )
    result = SupportEngine(
        FakeRetriever(bundles),
        reasoner,
        snapshot_id=SNAPSHOT,
        evidence_scope="exact_user_version",
    ).run(state(), "My widget state is unexpected.")
    assert result.status == "awaiting_approval"
    assert result.model_attempts == result.retrieval_rounds == 2
    assert reasoner.inputs[0][2].hits[0].chunk_id == "current"
    assert reasoner.inputs[1][2].hits == ()
    assert [context.can_refine for context in reasoner.contexts] == [True, False]


def test_scope_cannot_hide_an_invalid_oversized_retrieval_result():
    reasoner = FakeReasoner([proposal()])
    result = SupportEngine(
        FakeRetriever([EvidenceBundle(snapshot_id=SNAPSHOT, hits=(hit("old1"), hit("old2")))]),
        reasoner,
        snapshot_id=SNAPSHOT,
        top_k=1,
        evidence_scope="exact_user_version",
    ).run(state(), "Problem.")
    assert result.error_code == "RetrievalResultInvalid"
    assert reasoner.inputs == []


def test_same_version_conflict_and_unscoped_sources_require_semantic_review():
    sources = (hit("claim-a", ("1.50.0",)), hit("claim-b", ("1.50.0",)), hit("unknown"))
    result, reasoner = run(state(), sources, [proposal()])
    assert result.status == "awaiting_approval"
    assert reasoner.inputs[0][2].hits == sources


@pytest.mark.parametrize("scope", ["auto", "", None, True, [], {}])
def test_bad_scope_configuration_stops_before_adapters(scope):
    reasoner = FakeReasoner([proposal()])
    retriever = FakeRetriever([])
    with pytest.raises(ValueError, match="Unsupported evidence scope policy"):
        SupportEngine(retriever, reasoner, snapshot_id=SNAPSHOT, evidence_scope=scope)
    assert retriever.requests == reasoner.inputs == []
