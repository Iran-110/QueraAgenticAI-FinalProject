"""Offline candidate selection checks do not measure model or retrieval quality."""

from copy import deepcopy

import pytest
from test_chroma_retrieval_adapter import RawReadBackend, request, result, row
from test_evidence_scope import proposal, state

from agent_app.contracts import (
    AnalysisResult,
    CaseState,
    EvidenceBundle,
    EvidenceHit,
    ReportedFact,
    UserTurn,
)
from agent_app.orchestration import SupportEngine
from agent_app.orchestration.turns import propose_user_turn
from agent_app.retrieval.adapter import ChromaRetrieverAdapter
from agent_app.retrieval.relevance import rank_candidates
from agent_app.testing.fakes import FakeReasoner, FakeRetriever

SNAPSHOT = "offline-adapter-snapshot"


def adapter(backend, **changes):
    return ChromaRetrieverAdapter(
        "unused-offline-path", snapshot_id=SNAPSHOT, core_retriever=backend, **changes
    )


def hit(chunk, *, source=None, api=None, versions=(), excerpt="Synthetic complete source."):
    return EvidenceHit(
        chunk_id=chunk,
        source_id=source or (f"docstring:1.50.0:streamlit.{api}" if api else f"source:{chunk}"),
        excerpt=excerpt,
        source_url="https://example.org/pinned-source",
        source_type="doc",
        source_commit="a" * 40,
        source_span=f"synthetic:{chunk}",
        applicable_versions=versions,
    )


def positions(hits):
    return {item.chunk_id: [(0, "docs", index)] for index, item in enumerate(hits, 1)}


def scoped_run(case, candidates, *, top_k=1, query="Current documentation", **changes):
    retriever = FakeRetriever([EvidenceBundle(snapshot_id=SNAPSHOT, hits=tuple(candidates))])
    reasoner = FakeReasoner([proposal()])
    engine = SupportEngine(
        retriever,
        reasoner,
        snapshot_id=SNAPSHOT,
        top_k=top_k,
        evidence_scope="exact_user_version",
        retrieval_candidate_multiplier=5,
        **changes,
    )
    outcome = engine.run(case, "Synthetic reported problem.", initial_query=query)
    return outcome, retriever, reasoner


@pytest.mark.parametrize(
    "query,api",
    [
        ("How does st.download_button handle a payload?", "download_button"),
        ("streamlit.radio option selection", "radio"),
        ("text_area initial value", "text_area"),
    ],
)
def test_explicit_and_bare_api_identity_generalize_beyond_development_cases(query, api):
    cross_reference = hit(
        "cross-reference",
        api="checkbox",
        excerpt=(f"st.{api} streamlit.{api} {api} initial option selection payload " * 20),
    )
    primary = hit("primary", api=api, excerpt="A complete parameter reference.")
    supplied = (cross_reference, primary)
    saved = [item.model_dump(mode="json") for item in supplied]
    ranked = rank_candidates(supplied, (query,), positions(supplied))
    assert ranked[0] == primary
    assert len(ranked) == len(supplied) and set(item.chunk_id for item in ranked) == {
        item.chunk_id for item in supplied
    }
    assert [item.model_dump(mode="json") for item in supplied] == saved


def test_primary_api_identity_can_come_from_markdown_locator():
    unrelated = hit("cross", api="checkbox", excerpt="st.file_uploader upload file " * 30)
    primary = hit("upload", source="docs:content/widgets/file-uploader.md")
    ranked = rank_candidates(
        (unrelated, primary), ("st.file_uploader upload file",), positions((unrelated, primary))
    )
    assert ranked[0] == primary


def test_source_diversity_retains_distinct_versions_before_supplementary_chunks():
    current = hit("current-first", api="radio", versions=("1.50.0",), excerpt="radio choice")
    extra = hit(
        "current-extra", source=current.source_id, versions=("1.50.0",), excerpt="radio choice"
    )
    historical = hit(
        "historical",
        source="docstring:1.49.0:streamlit.radio",
        versions=("1.49.0",),
        excerpt="radio choice",
    )
    independent = hit("other", api="checkbox", excerpt="A separate complete source.")
    supplied = (current, extra, historical, independent)
    ranked = rank_candidates(supplied, ("st.radio choice",), positions(supplied))
    assert ranked[0] == current
    assert {item.source_id for item in ranked[:3]} == {
        current.source_id,
        historical.source_id,
        independent.source_id,
    }
    assert ranked[-1] == extra and len(ranked) == 4


def test_equal_relevance_uses_native_rank_without_automatic_newest_version_preference():
    historical = hit(
        "old",
        source="docstring:1.39.0:streamlit.radio",
        versions=("1.39.0",),
        excerpt="radio option choice",
    )
    newer = hit(
        "new",
        source="docstring:1.64.0:streamlit.radio",
        versions=("1.64.0",),
        excerpt="radio option choice",
    )
    supplied = (newer, historical)
    native = {historical.chunk_id: [(0, "docs", 1)], newer.chunk_id: [(0, "docs", 4)]}
    assert rank_candidates(supplied, ("st.radio option choice",), native)[0] == historical


def test_ties_are_deterministic_and_full_excerpt_identity_is_preserved():
    excerpt = "Complete فارسی source\n<code>&_*`\n" + "x" * 19000
    first = hit("a", source="source:a", excerpt=excerpt)
    second = hit("b", source="source:b", excerpt=excerpt)
    native = {item.chunk_id: [(0, "docs", 1)] for item in (first, second)}
    forward = rank_candidates((first, second), ("unrelated query",), native)
    reversed_input = rank_candidates((second, first), ("unrelated query",), native)
    assert forward == reversed_input
    assert {item.chunk_id: item.model_dump_json() for item in forward} == {
        item.chunk_id: item.model_dump_json() for item in (first, second)
    }


def test_adapter_combines_queries_and_collections_before_relevance_selection():
    unrelated = row("unrelated", source_id="doc:unrelated", excerpt="A weather report.")
    second_doc = row(
        "api",
        source_id="docstring:1.50.0:streamlit.download_button",
        excerpt="download_button click payload data",
    )
    second_issue = row(
        "issue:payload",
        source_id="issue:payload",
        source_type="issue",
        source_url="https://github.com/streamlit/streamlit/issues/42",
        excerpt="download_button click payload data",
    )
    backend = RawReadBackend(
        {
            "configuration storage": result(docs=(unrelated,)),
            "st.download_button click payload data": result(
                docs=(second_doc,), issues=(second_issue,)
            ),
        }
    )
    supplied = request("configuration storage", "st.download_button click payload data", top_k=2)
    saved = supplied.model_dump()
    output = adapter(backend, selection_policy="query_relevance_v1").search(supplied)
    assert {item.chunk_id for item in output.hits} == {"api", "issue:payload"}
    assert output.queries_used == supplied.queries and supplied.model_dump() == saved
    assert backend.calls == [
        ("configuration storage", 2, {}),
        ("st.download_button click payload data", 2, {}),
    ]


def test_engine_requests_actual_larger_backend_candidate_count_then_caps_model_evidence():
    class CandidateBackend:
        def __init__(self):
            self.calls = []

        def search(self, query, n_results, *, filters):
            self.calls.append((query, n_results, deepcopy(filters)))
            return result(
                docs=tuple(
                    row(f"chunk:{i}", source_id=f"source:{i}", excerpt="radio option choice")
                    for i in range(n_results)
                )
            )

    backend = CandidateBackend()
    reasoner = FakeReasoner([proposal()])
    outcome = SupportEngine(
        adapter(backend, selection_policy="query_relevance_v1"),
        reasoner,
        snapshot_id=SNAPSHOT,
        top_k=5,
        retrieval_candidate_multiplier=5,
    ).run(CaseState(case_id="candidate-case"), "radio option choice", initial_query="radio choice")
    assert outcome.status == "awaiting_approval"
    assert backend.calls == [("radio choice", 25, {})]
    assert len(reasoner.inputs[0][2].hits) == 5
    assert outcome.model_attempts == outcome.retrieval_rounds == 1


@pytest.mark.parametrize("top_k,candidate_count", [(1, 5), (5, 25), (11, 50), (50, 50)])
def test_candidate_request_is_bounded_by_fifty(top_k, candidate_count):
    candidates = tuple(hit(f"candidate:{i}") for i in range(candidate_count))
    outcome, retriever, reasoner = scoped_run(
        CaseState(case_id="cap-case"), candidates, top_k=top_k
    )
    assert outcome.status == "awaiting_approval"
    assert retriever.requests[0].top_k == candidate_count
    assert len(reasoner.inputs[0][2].hits) == top_k


def test_confirmed_user_version_is_filtered_before_final_cap_and_backfills_current_hits():
    future = tuple(hit(f"future:{i}", versions=("1.64.0",)) for i in range(10))
    current = tuple(hit(f"current:{i}", versions=("1.39.0",)) for i in range(7))
    sources = future + current
    snapshots = [item.model_dump_json() for item in sources]
    outcome, retriever, reasoner = scoped_run(state("1.39.0"), sources, top_k=5)
    assert outcome.status == "awaiting_approval" and retriever.requests[0].top_k == 25
    assert reasoner.inputs[0][2].hits == current[:5]
    assert [item.model_dump_json() for item in sources] == snapshots


@pytest.mark.parametrize(
    "case,expected",
    [
        (state("1.39.0"), "current"),
        (state("1.64.0"), "newer"),
        (state("1.38.0"), "older"),
        (CaseState(case_id="scope-case"), "unscoped"),
        (state("1.64.0", provenance_kind="evidence"), "unscoped"),
        (state("1.64.0", status="superseded"), "unscoped"),
    ],
)
def test_only_current_active_user_facts_authorize_version_scope(case, expected):
    sources = (
        hit("newer", versions=("1.64.0",), excerpt="st.radio since 1.64.0"),
        hit("current", versions=("1.39.0",)),
        hit("older", versions=("1.38.0",)),
        hit("unscoped"),
    )
    before = case.model_dump_json()
    outcome, _, reasoner = scoped_run(case, sources, query="st.radio version 1.64.0")
    assert outcome.status == "awaiting_approval"
    assert [item.chunk_id for item in reasoner.inputs[0][2].hits] == [expected]
    assert case.model_dump_json() == before


def test_real_user_correction_changes_scope_without_reusing_prior_version_authority():
    original = state("1.39.0")
    corrected = propose_user_turn(
        original,
        UserTurn(
            case_id=original.case_id,
            expected_revision=original.case_revision,
            turn_id="corrected",
            source_ref="user:corrected",
            message="Correction: the installed Streamlit version is 1.38.0.",
            reported_facts=(ReportedFact(name="streamlit_version", value="1.38.0"),),
        ),
    ).candidate
    sources = (hit("old-current", versions=("1.39.0",)), hit("corrected", versions=("1.38.0",)))
    first, _, first_reasoner = scoped_run(original, sources)
    second, _, second_reasoner = scoped_run(corrected, sources, query="st.radio version 1.64.0")
    assert first.status == second.status == "awaiting_approval"
    assert first_reasoner.inputs[0][2].hits == sources[:1]
    assert second_reasoner.inputs[0][2].hits == sources[1:]
    assert original.facts[0].status == "active" and original.facts[0].value == "1.39.0"


def test_since_version_does_not_become_exact_applicability_or_override_explicit_versions():
    records = (
        row("since-only", source_id="doc:since", since_version="1.0.0"),
        row("legacy-exact", source_id="doc:legacy", version="1.39.0", since_version="1.0.0"),
        row(
            "explicit-unknown",
            source_id="doc:unknown",
            applicable_versions="[]",
            version="1.64.0",
            since_version="1.0.0",
        ),
    )
    backend = RawReadBackend({"st.radio": result(docs=records)})
    bundle = adapter(backend, selection_policy="query_relevance_v1").search(request("st.radio"))
    by_id = {item.chunk_id: item for item in bundle.hits}
    assert by_id["since-only"].applicable_versions == ()
    assert by_id["explicit-unknown"].applicable_versions == ()
    assert by_id["legacy-exact"].applicable_versions == ("1.39.0",)
    outcome, _, reasoner = scoped_run(state("1.50.0"), bundle.hits, top_k=5)
    assert outcome.status == "awaiting_approval"
    assert {item.chunk_id for item in reasoner.inputs[0][2].hits} == {
        "since-only",
        "explicit-unknown",
    }


@pytest.mark.parametrize("bad", [True, False, "5", 5.0, 0, 2, 50, None, []])
def test_candidate_multiplier_is_strict_and_rejected_before_any_port(bad):
    retriever, reasoner = FakeRetriever([]), FakeReasoner([])
    with pytest.raises(ValueError):
        SupportEngine(retriever, reasoner, snapshot_id=SNAPSHOT, retrieval_candidate_multiplier=bad)
    assert retriever.requests == reasoner.inputs == []


@pytest.mark.parametrize("bad", [None, True, 1, "relevance", "query_relevance_v2", [], {}])
def test_adapter_policy_is_explicit_and_rejected_before_backend_read(bad):
    backend = RawReadBackend({})
    with pytest.raises(ValueError):
        adapter(backend, selection_policy=bad)
    assert backend.calls == []


def test_backend_over_return_is_rejected_in_opt_in_instead_of_discarding_unvalidated_rows():
    records = tuple(row(f"chunk:{i}", source_id=f"source:{i}") for i in range(3))
    backend = RawReadBackend({"query": result(docs=records)})
    with pytest.raises(ValueError):
        adapter(backend, selection_policy="query_relevance_v1").search(request("query", top_k=2))


@pytest.mark.parametrize("fault", ["too_many", "bad_url", "blank_excerpt"])
def test_invalid_candidates_cannot_be_hidden_by_scope_or_final_cap(fault):
    candidates = (hit("keep"), hit("late-rejected", versions=("1.64.0",)))
    if fault == "too_many":
        candidates = tuple(hit(f"late:{i}", versions=("1.64.0",)) for i in range(6))
    else:
        field, value = ("source_url", "invalid") if fault == "bad_url" else ("excerpt", "   ")
        candidates = (candidates[0], candidates[1].model_copy(update={field: value}))
    bundle = EvidenceBundle.model_construct(snapshot_id=SNAPSHOT, hits=candidates)
    reasoner = FakeReasoner([proposal()])
    outcome = SupportEngine(
        FakeRetriever([bundle]),
        reasoner,
        snapshot_id=SNAPSHOT,
        top_k=1,
        retrieval_candidate_multiplier=5,
        evidence_scope="exact_user_version",
    ).run(state("1.39.0"), "Synthetic problem.")
    assert outcome.error_code == "RetrievalResultInvalid" and reasoner.inputs == []
    assert outcome.model_attempts == 0 and outcome.retrieval_rounds == 1


def test_conflicting_duplicate_after_first_query_is_not_hidden_by_relevance_cap():
    first = row("shared", excerpt="The complete original source.")
    changed = row("shared", excerpt="Different bytes under the same identity.")
    backend = RawReadBackend({"first": result(docs=(first,)), "second": result(issues=(changed,))})
    with pytest.raises(ValueError):
        adapter(backend, selection_policy="query_relevance_v1").search(
            request("first", "second", top_k=1)
        )


@pytest.mark.parametrize("continue_retrieving", [False, True])
def test_candidate_expansion_preserves_two_query_two_round_and_two_attempt_limits(
    continue_retrieving,
):
    refinement = AnalysisResult(
        decision="retrieve_more",
        user_draft="",
        maintainer_summary="",
        rationale="Seek a bounded missing source.",
        retrieval_queries=("first source gap", "second source gap"),
    )
    backend = RawReadBackend(
        {
            query: result(docs=(row("same-current-record"),))
            for query in ("initial lookup", *refinement.retrieval_queries)
        }
    )
    reasoner = FakeReasoner([refinement, refinement if continue_retrieving else proposal()])
    outcome = SupportEngine(
        adapter(backend, selection_policy="query_relevance_v1"),
        reasoner,
        snapshot_id=SNAPSHOT,
        top_k=5,
        retrieval_candidate_multiplier=5,
    ).run(
        CaseState(case_id="query-budget-case"), "Synthetic problem.", initial_query="initial lookup"
    )
    assert backend.calls == [
        (query, 25, {}) for query in ("initial lookup", *refinement.retrieval_queries)
    ]
    assert outcome.model_attempts == outcome.retrieval_rounds == len(reasoner.inputs) == 2
    assert reasoner.contexts[1].query_limit == 2 and not reasoner.contexts[1].can_refine
    assert reasoner.inputs[1][2].queries_used == refinement.retrieval_queries
    if continue_retrieving:
        assert outcome.error_code == "ModelAttemptLimitExceeded"
    else:
        assert outcome.status == "awaiting_approval"


def test_default_and_explicit_native_adapter_keep_identical_legacy_bytes_and_calls():
    records = tuple(row(f"chunk:{i}", source_id=f"source:{i}") for i in range(3))
    scripted = {"first": result(docs=records), "second": result(issues=(row("issue:1"),))}
    backends = (RawReadBackend(scripted), RawReadBackend(scripted))
    supplied = request("first", "second", top_k=2, source_type=("doc", "issue"))
    default = adapter(backends[0]).search(supplied)
    native = adapter(backends[1], selection_policy="native").search(supplied)
    assert default.model_dump_json() == native.model_dump_json()
    assert backends[0].calls == backends[1].calls
    assert [item.chunk_id for item in default.hits] == ["chunk:0", "chunk:1"]


def test_default_and_explicit_multiplier_one_keep_existing_result_and_trace_bytes():
    bundle = EvidenceBundle(snapshot_id=SNAPSHOT, hits=(hit("original"),))
    outputs, requests, observed = [], [], []
    for options in ({}, {"retrieval_candidate_multiplier": 1}):
        retriever, reasoner = FakeRetriever([bundle]), FakeReasoner([proposal()])
        outcome = SupportEngine(retriever, reasoner, snapshot_id=SNAPSHOT, **options).run(
            CaseState(case_id="native-equivalence"), "Synthetic problem.", run_id="same-native-run"
        )
        outputs.append(outcome.model_dump_json())
        requests.append([item.model_dump_json() for item in retriever.requests])
        observed.append(reasoner.inputs[0][2].model_dump_json())
    assert outputs[0] == outputs[1] and requests[0] == requests[1] and observed[0] == observed[1]
