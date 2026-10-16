"""R4b regression controls for the PR50 review findings; offline, zero API.

Covers the three reviewed defects end to end through the real adapter and
engine: newest-first displacement of the current release, missing backend
over-fetch, and `since_version` treated as exact applicability. Version
labels below are synthetic metadata; no case/source-ID filter selects evidence.
"""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from test_chroma_retrieval_adapter import RawReadBackend, result, row

from agent_app.contracts import AnalysisResult, CaseState, Fact, RetrievalRequest
from agent_app.orchestration import SupportEngine
from agent_app.retrieval.adapter import ChromaRetrieverAdapter
from agent_app.testing.fakes import FakeReasoner

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = "offline-adapter-snapshot"
QUERY = "st.multiselect st.button st.fragment default value"


def proposal():
    return AnalysisResult(
        decision="escalate",
        user_draft="The supplied sources do not establish the full application cause.",
        maintainer_summary="Version scope is tested without a generated model response.",
        rationale="A version filter does not establish source entailment.",
    )


def version_fact(value, *, status="active", turn="initial"):
    return Fact(
        name="streamlit_version",
        value=value,
        source_ref=f"user:{turn}",
        turn_id=turn,
        status=status,
    )


def case(*facts):
    return CaseState(case_id="r4b-case", facts=facts)


def versioned(chunk, source, version, excerpt):
    return row(
        chunk,
        source_id=source,
        excerpt=excerpt,
        applicable_versions=json.dumps([version]),
        version=version,
    )


# One complete record per release identity, plus one unversioned guide.
CORPUS = (
    versioned("button-139", "docstring:1.39.0:streamlit.button", "1.39.0", "st.button icon"),
    versioned(
        "multiselect-149",
        "docstring:1.49.0:streamlit.multiselect",
        "1.49.0",
        "st.multiselect default value",
    ),
    versioned(
        "multiselect-150",
        "docstring:1.50.0:streamlit.multiselect",
        "1.50.0",
        "st.multiselect default value",
    ),
    versioned("fragment-150", "docstring:1.50.0:streamlit.fragment", "1.50.0", "st.fragment"),
    versioned("text-input-164", "docstring:1.64.0:streamlit.text_input", "1.64.0", "st.text_input"),
    row("guide", source_id="docs:widget-behavior.md", excerpt="Widget default value behavior."),
)


def run(state, rows=CORPUS, *, top_k=5, multiplier=5, query=QUERY):
    backend = RawReadBackend({query: result(docs=rows)})
    adapter = ChromaRetrieverAdapter(
        "unused-offline-path",
        snapshot_id=SNAPSHOT,
        core_retriever=backend,
        selection_policy="query_relevance_v1",
    )
    reasoner = FakeReasoner([proposal()])
    engine = SupportEngine(
        adapter,
        reasoner,
        snapshot_id=SNAPSHOT,
        top_k=top_k,
        evidence_scope="exact_user_version",
        retrieval_candidate_multiplier=multiplier,
        evidence_utf8_budget_bytes=12000,
    )
    outcome = engine.run(state, "Synthetic reported problem.", initial_query=query)
    hits = reasoner.inputs[0][2].hits if reasoner.inputs else ()
    return outcome, backend, {hit.chunk_id for hit in hits}


def test_review_control_keeps_current_release_instead_of_newer_unrelated_releases():
    """The archived PR50 control: top_k=2, user 1.39.0, two later releases."""
    review = json.loads(
        (ROOT / "experiments/rag_pr50_review/review-head-7581dcc-v1.json").read_bytes()
    )["ranking_control"]
    rows = deepcopy(review["native_backend_rows"])
    query = review["request"]["queries"][0]

    class Backend:
        def __init__(self):
            self.calls = []

        def search(self, query, n_results=3, *, filters=None):
            self.calls.append((query, n_results))
            return deepcopy(rows)

    backend = Backend()
    reasoner = FakeReasoner([proposal()])
    engine = SupportEngine(
        ChromaRetrieverAdapter(
            "", snapshot_id=SNAPSHOT, core_retriever=backend, selection_policy="query_relevance_v1"
        ),
        reasoner,
        snapshot_id=SNAPSHOT,
        top_k=2,
        evidence_scope="exact_user_version",
        retrieval_candidate_multiplier=5,
    )
    engine.run(CaseState.model_validate(review["case"]), "Synthetic.", initial_query=query)
    assert backend.calls == [(query, 10)]
    assert [hit.chunk_id for hit in reasoner.inputs[0][2].hits] == ["current"]


@pytest.mark.parametrize("top_k,expected", [(1, 5), (5, 25), (10, 50), (20, 50)])
def test_backend_actually_receives_bounded_overfetch(top_k, expected):
    _, backend, _ = run(case(version_fact("1.50.0")), top_k=top_k)
    assert [call[1] for call in backend.calls] == [expected]


def test_multiplier_one_keeps_legacy_backend_count():
    _, backend, _ = run(case(version_fact("1.50.0")), multiplier=1)
    assert [call[1] for call in backend.calls] == [5]


@pytest.mark.parametrize(
    "state,expected",
    [
        # Unknown version: no versioned record is presented as applicable.
        (case(), {"guide"}),
        # Older installation: newer releases are excluded, not ranked first.
        (case(version_fact("1.39.0")), {"button-139", "guide"}),
        (case(version_fact("1.49.0")), {"multiselect-149", "guide"}),
        (case(version_fact("1.50.0")), {"multiselect-150", "fragment-150", "guide"}),
        # A version with no indexed release keeps only unversioned material.
        (case(version_fact("1.31.1")), {"guide"}),
    ],
)
def test_final_evidence_matches_the_active_user_version(state, expected):
    outcome, _, final = run(state)
    assert outcome.status == "awaiting_approval"
    assert final == expected


def test_correction_replaces_scope_without_reusing_the_superseded_version():
    corrected = case(
        version_fact("1.50.0", status="superseded"),
        version_fact("1.49.0", turn="correction"),
    )
    _, _, final = run(corrected)
    assert final == {"multiselect-149", "guide"}


def test_relevant_current_release_survives_more_than_top_k_newer_records():
    """Five newer same-API releases cannot crowd out the user's 1.39.0 record."""
    newer = tuple(
        versioned(
            f"button-1{minor}",
            f"docstring:1.{minor}.0:streamlit.button",
            f"1.{minor}.0",
            "st.button icon",
        )
        for minor in range(50, 56)
    )
    rows = (*newer, CORPUS[0])
    outcome, backend, final = run(case(version_fact("1.39.0")), rows=rows, query="st.button icon")
    assert backend.calls[0][1] == 25
    assert final == {"button-139"}


@pytest.mark.parametrize(
    "metadata",
    [
        {"since_version": "1.39.0"},
        {"since_version": "1.39.0", "version": None},
        {"since_version": "1.39.0", "applicable_versions": "[]"},
    ],
)
def test_since_version_is_introduction_metadata_not_exact_applicability(metadata):
    since = row("since", source_id="docs:since.md", excerpt="st.multiselect", **metadata)
    # A 1.39.0 user must not receive it as an exact 1.39.0 record, and a
    # 1.50.0 user must not lose it as a mismatched exact record either.
    for version in ("1.39.0", "1.50.0"):
        _, _, final = run(case(version_fact(version)), rows=(since,), query="st.multiselect")
        assert final == {"since"}
    backend = RawReadBackend({"st.multiselect": result(docs=(since,))})
    bundle = ChromaRetrieverAdapter(
        "", snapshot_id=SNAPSHOT, core_retriever=backend, selection_policy="query_relevance_v1"
    ).search(RetrievalRequest(queries=("st.multiselect",), snapshot_id=SNAPSHOT))
    assert bundle.hits[0].applicable_versions == ()
