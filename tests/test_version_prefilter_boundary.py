"""An optional native filter cannot invalidate otherwise valid USER facts."""

import json

import pytest

from agent_app.contracts import AnalysisResult, CaseState, EvidenceBundle, EvidenceHit, Fact
from agent_app.orchestration import SupportEngine
from agent_app.testing.fakes import FakeReasoner, FakeRetriever

SNAPSHOT = "prefilter-boundary"


def hit(chunk, versions=()):
    return EvidenceHit(
        chunk_id=chunk,
        source_id=f"source:{chunk}",
        excerpt="Complete neutral source used only for an offline boundary control.",
        source_url="https://example.org/prefilter-boundary",
        source_type="doc",
        applicable_versions=versions,
    )


def execute(version, *, prefilter=True, query="neutral query"):
    facts = (
        (
            Fact(
                name="streamlit_version",
                value=version,
                source_ref="user:initial",
                turn_id="initial",
            ),
        )
        if version is not None
        else ()
    )
    case = CaseState(case_id="neutral-case", facts=facts)
    before = case.model_dump()
    hits = [hit("unversioned"), hit("other-version", ("different-version",))]
    if version is not None and len(version) <= 500:
        # A generic valid backend can return this exact long version, including
        # shared applicability. Falling back to unversioned-only would lose it.
        hits.extend([hit("exact", (version,)), hit("shared", ("historical", version))])
    retriever = FakeRetriever([EvidenceBundle(snapshot_id=SNAPSHOT, hits=tuple(hits))])
    reasoner = FakeReasoner(
        [
            AnalysisResult(
                decision="escalate",
                user_draft="A maintainer should review the supplied report.",
                maintainer_summary="This neutral fixture makes no source-support judgment.",
                rationale="The test observes scope and input custody only.",
            )
        ]
    )
    options = {} if prefilter is None else {"retrieval_version_prefilter": prefilter}
    engine = SupportEngine(
        retriever,
        reasoner,
        snapshot_id=SNAPSHOT,
        evidence_scope="exact_user_version",
        **options,
    )
    result = engine.run(case, "A neutral reported problem.", initial_query=query)
    assert case.model_dump() == before
    return result, retriever, reasoner


@pytest.mark.parametrize(
    "version",
    [
        "v" * 497,
        "v" * 500,
        "v" * 501,
        "v" * 20_000,
        '"' * 249,
        "\\" * 249,
        "v" + "\n" * 248 + "v",
        "\x00" * 83,
        "é" * 497,
        "\\u000d" * 83,
    ],
    ids=[
        "497-characters",
        "500-characters",
        "beyond-metadata-bound",
        "maximum-fact-bound",
        "escaped-quotes",
        "escaped-backslashes",
        "escaped-newlines",
        "escaped-control",
        "unicode-characters",
        "literal-unicode-escape",
    ],
)
def test_oversized_encoding_skips_only_prefilter_and_preserves_exact_scope(version):
    assert len(json.dumps([version], ensure_ascii=False, separators=(",", ":"))) > 500
    baseline, baseline_retriever, baseline_reasoner = execute(version, prefilter=False)
    observed, retriever, reasoner = execute(version)
    assert observed.status == baseline.status == "awaiting_approval"
    assert observed.error_code is baseline.error_code is None
    assert observed.analysis == baseline.analysis
    assert len(retriever.requests) == len(reasoner.inputs) == 1
    assert retriever.requests[0] == baseline_retriever.requests[0]
    assert retriever.requests[0].filters == {}
    assert reasoner.inputs == baseline_reasoner.inputs
    supplied_case, _, evidence = reasoner.inputs[0]
    assert supplied_case.facts[0].value == version
    assert "other-version" not in {item.chunk_id for item in evidence.hits}
    if len(version) <= 500:
        assert {item.chunk_id for item in evidence.hits} == {"unversioned", "exact", "shared"}
        assert evidence.hits[1].applicable_versions == (version,)
    else:
        assert {item.chunk_id for item in evidence.hits} == {"unversioned"}


@pytest.mark.parametrize("version", ["v" * 496, '"' * 248, "\\" * 248, "é" * 496])
def test_exact_filter_limit_still_sends_the_complete_canonical_value(version):
    encoded = json.dumps([version], ensure_ascii=False, separators=(",", ":"))
    assert len(encoded) == 500
    result, retriever, reasoner = execute(version)
    assert result.status == "awaiting_approval"
    assert retriever.requests[0].filters == {"applicable_versions": ("[]", encoded)}
    assert reasoner.inputs[0][0].facts[0].value == version


@pytest.mark.parametrize("version,expected", [("1.50.0", ("[]", '["1.50.0"]')), (None, "[]")])
def test_canonical_and_unknown_versions_keep_the_original_filter(version, expected):
    result, retriever, _ = execute(version)
    assert result.status == "awaiting_approval"
    assert retriever.requests[0].filters == {"applicable_versions": expected}


@pytest.mark.parametrize("prefilter", [None, False])
def test_omitted_and_false_prefilter_keep_the_unfiltered_request(prefilter):
    result, retriever, _ = execute("1.50.0", prefilter=prefilter)
    assert result.status == "awaiting_approval"
    assert retriever.requests[0].filters == {}


@pytest.mark.parametrize("query", ["", "   ", "q" * 501])
def test_filter_fallback_does_not_accept_an_invalid_query(query):
    result, retriever, reasoner = execute("v" * 497, query=query)
    assert result.status == "error" and result.error_code == "InvalidRetrievalQuery"
    assert retriever.requests == reasoner.inputs == []
