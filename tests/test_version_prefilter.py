"""R4e: opt-in version prefilter applies the scope rule before the native top-k cut.

Default engines send no filter. With the option, the request carries the same
eligibility rule as the post-retrieval scope (unversioned records plus the
active USER version), which stays authoritative for anything returned.
"""

import json
from pathlib import Path

import pytest

from agent_app.contracts import AnalysisResult, CaseState, EvidenceBundle, EvidenceHit, Fact
from agent_app.orchestration import SupportEngine
from agent_app.retrieval.pilot_corpus import build_final_corpus, build_pilot_corpus
from agent_app.retrieval.retriever import StreamlitRetriever
from agent_app.testing.fakes import FakeReasoner, FakeRetriever

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "streamlit-data-for-dev-test"
SNAPSHOT = "prefilter-snapshot"


def proposal():
    return AnalysisResult(
        decision="escalate",
        user_draft="The supplied sources do not establish the cause.",
        maintainer_summary="Version prefilter is tested without a generated model response.",
        rationale="A version filter does not establish source entailment.",
    )


def fact(value, *, status="active", kind="user", turn="initial"):
    return Fact(
        name="streamlit_version",
        value=value,
        source_ref=f"user:{turn}",
        turn_id=turn,
        status=status,
        provenance_kind=kind,
    )


def hit(chunk, versions=()):
    return EvidenceHit(
        chunk_id=chunk,
        source_id=f"source:{chunk}",
        excerpt="Synthetic complete source.",
        source_url="https://example.org/pinned",
        source_type="doc",
        applicable_versions=versions,
    )


def run(case, *, prefilter, hits=()):
    retriever = FakeRetriever([EvidenceBundle(snapshot_id=SNAPSHOT, hits=tuple(hits))])
    reasoner = FakeReasoner([proposal()])
    engine = SupportEngine(
        retriever,
        reasoner,
        snapshot_id=SNAPSHOT,
        evidence_scope="exact_user_version",
        retrieval_candidate_multiplier=5,
        evidence_utf8_budget_bytes=12000,
        retrieval_version_prefilter=prefilter,
    )
    engine.run(case, "Synthetic reported problem.", initial_query="widget state reset")
    return retriever.requests[0], reasoner


def test_default_engine_sends_no_filter():
    request, _ = run(CaseState(case_id="c", facts=(fact("1.50.0"),)), prefilter=False)
    assert request.filters == {}


@pytest.mark.parametrize(
    "facts,expected",
    [
        ((fact("1.50.0"),), ("[]", '["1.50.0"]')),
        ((), "[]"),
        ((fact("1.50.0", status="superseded"), fact("1.49.0", turn="fix")), ("[]", '["1.49.0"]')),
        ((fact("1.50.0", kind="evidence"),), "[]"),
    ],
    ids=["known", "unknown", "corrected", "non-user-fact"],
)
def test_prefilter_carries_the_active_user_version_only(facts, expected):
    request, _ = run(CaseState(case_id="c", facts=facts), prefilter=True)
    assert request.filters == {"applicable_versions": expected}
    assert request.top_k == 25


def test_post_retrieval_scope_still_rejects_hits_a_backend_should_have_filtered():
    returned = (hit("current", ("1.50.0",)), hit("other", ("1.64.0",)), hit("unversioned"))
    _, reasoner = run(
        CaseState(case_id="c", facts=(fact("1.50.0"),)), prefilter=True, hits=returned
    )
    assert {h.chunk_id for h in reasoner.inputs[0][2].hits} == {"current", "unversioned"}


@pytest.mark.parametrize(
    "options",
    [
        {"retrieval_version_prefilter": "yes"},
        {"retrieval_version_prefilter": 1},
        {"retrieval_version_prefilter": True, "evidence_scope": "all"},
    ],
)
def test_invalid_configuration_is_rejected_before_any_port(options):
    retriever, reasoner = FakeRetriever([]), FakeReasoner([])
    with pytest.raises(ValueError):
        SupportEngine(retriever, reasoner, snapshot_id=SNAPSHOT, **options)
    assert retriever.requests == reasoner.inputs == []


def test_native_filter_is_a_plain_membership_clause():
    where = StreamlitRetriever._where({"applicable_versions": ("[]", '["1.50.0"]')})
    assert where == {"applicable_versions": {"$in": ["[]", '["1.50.0"]']}}
    assert StreamlitRetriever._where({"applicable_versions": "[]"}) == {"applicable_versions": "[]"}


@pytest.fixture(scope="module")
def registered_corpora():
    return [
        build_pilot_corpus(
            SEED,
            ROOT / "experiments/dev_rag_coverage_v1/split-manifest.json",
            ROOT / "experiments/dev_rag_coverage_v1/allowlist.json",
        ),
        build_final_corpus(
            SEED,
            ROOT / "experiments/final_corpus_v1/allowlist.json",
            ROOT / "experiments/final_corpus_v1/exclusion-v1.json",
        ),
    ]


@pytest.mark.parametrize("version", [None, "1.22.0", "1.39.0", "1.50.0", "1.64.0", "9.9.9"])
def test_prefilter_selects_exactly_the_scope_eligible_chunks(registered_corpora, version):
    """On every registered corpus the filter and the scope rule agree chunk for chunk."""
    allowed = {"[]"} | ({json.dumps([version], separators=(",", ":"))} if version else set())
    for corpus in registered_corpora:
        chunks = corpus.manifest["corpus"]["chunks"]
        by_filter = {
            c["chunk_id"] for c in chunks if c["metadata"]["applicable_versions"] in allowed
        }
        by_scope = {
            c["chunk_id"]
            for c in chunks
            if not json.loads(c["metadata"]["applicable_versions"])
            or version in json.loads(c["metadata"]["applicable_versions"])
        }
        assert by_filter == by_scope


def test_real_chroma_prefilter_returns_only_eligible_candidates(tmp_path, registered_corpora):
    pytest.importorskip("chromadb")
    from agent_app.retrieval.adapter import ChromaRetrieverAdapter
    from agent_app.retrieval.offline_index import build_index, open_verified_index

    corpus = registered_corpora[1]
    snapshot = build_index(corpus, tmp_path / "index")
    client, _ = open_verified_index(tmp_path / "index")
    adapter = ChromaRetrieverAdapter(
        "",
        snapshot_id=snapshot,
        core_retriever=StreamlitRetriever("", snapshot_id=snapshot, client=client),
        selection_policy="query_relevance_v1",
    )
    retriever = _Recording(adapter)
    engine = SupportEngine(
        retriever,
        FakeReasoner([proposal()]),
        snapshot_id=snapshot,
        evidence_scope="exact_user_version",
        retrieval_candidate_multiplier=5,
        evidence_utf8_budget_bytes=12000,
        retrieval_version_prefilter=True,
    )
    case = CaseState(case_id="c", facts=(fact("1.50.0"),))
    engine.run(case, "multiselect default value reset", initial_query="st.multiselect default")
    candidates = retriever.bundles[0].hits
    assert len(candidates) == 25
    assert all(
        not h.applicable_versions or h.applicable_versions == ("1.50.0",) for h in candidates
    )


class _Recording:
    def __init__(self, adapter):
        self.adapter, self.bundles = adapter, []

    def search(self, request):
        bundle = self.adapter.search(request)
        self.bundles.append(bundle)
        return bundle
