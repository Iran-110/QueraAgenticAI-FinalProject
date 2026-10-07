"""Synthetic, offline vertical slices, never an answer-quality benchmark."""

from agent_app.contracts import AnalysisResult, CaseState, EvidenceBundle, EvidenceHit, EvidenceLink
from agent_app.orchestration import SupportEngine
from agent_app.testing.fakes import FakeReasoner, FakeRetriever

SNAPSHOT_ID = "synthetic-demo-v1"


def _evidence(chunk_id: str, excerpt: str) -> EvidenceBundle:
    return EvidenceBundle(
        snapshot_id=SNAPSHOT_ID,
        hits=(
            EvidenceHit(
                chunk_id=chunk_id,
                source_id=f"synthetic:{chunk_id}",
                excerpt=excerpt,
                source_url="https://example.org/synthetic-demo",
                source_type="doc",
                source_span="synthetic demonstration; not a real retrieved source",
            ),
        ),
        warnings=("Synthetic evidence: not a real retrieval or quality evaluation.",),
    )


def _ask() -> AnalysisResult:
    question = "Which Streamlit version are you using, and can you share the widget's key and code?"
    return AnalysisResult(
        decision="ask",
        user_draft=question,
        maintainer_summary="Widget state loss is reported; version and widget definition are unknown.",
        rationale="The missing version and widget definition distinguish possible explanations.",
        missing_info=("streamlit_version", "widget_definition"),
        next_question=question,
    )


def _answer(chunk_id: str) -> AnalysisResult:
    return AnalysisResult(
        decision="answer",
        user_draft="This scripted demo suggests storing the counter in Session State.",
        maintainer_summary="A synthetic evidence reference accompanies this scripted example.",
        rationale="The mock source supports the scripted counter example.",
        evidence_links=(EvidenceLink(claim="Demo counter persistence", chunk_id=chunk_id),),
    )


def run_demo(scenario: str) -> dict:
    case = CaseState(
        case_id="demo-case",
        case_revision=1,
        unknowns=("streamlit_version", "widget_definition"),
    )
    first = _evidence("demo-initial", "Synthetic background about a Streamlit user session.")
    retrieval: list = [first]
    reasoning: list = [_ask()]
    user_message = "My widget loses its value. What should I check?"
    if scenario == "answer":
        user_message = "How can I retain a counter between reruns?"
        reasoning = [_answer("demo-initial")]
    elif scenario == "escalate":
        reasoning = [
            AnalysisResult(
                decision="escalate",
                user_draft="This demo has insufficient evidence; a maintainer should review the case.",
                maintainer_summary="The synthetic evidence does not establish a safe next fix.",
                rationale="Further product investigation is required.",
            )
        ]
    elif scenario == "refine":
        second = _evidence("demo-refined", "Synthetic evidence returned by the second search.")
        retrieval.append(second)
        reasoning = [
            AnalysisResult(
                decision="retrieve_more",
                user_draft="",
                maintainer_summary="",
                rationale="A more specific query could supply the missing evidence.",
                retrieval_queries=("Streamlit widget key Session State rerun",),
            ),
            _answer("demo-refined"),
        ]
    elif scenario == "error":
        retrieval = [RuntimeError("Synthetic retrieval failure")]
        reasoning = []
    elif scenario != "ask":
        raise ValueError("Unknown demonstration scenario")
    retriever = FakeRetriever(retrieval)
    reasoner = FakeReasoner(reasoning)
    engine = SupportEngine(retriever, reasoner, snapshot_id=SNAPSHOT_ID)
    result = engine.run(case, user_message)
    return {
        "mode": "synthetic_mock",
        "scenario": scenario,
        "real_api_calls": 0,
        "paid_cost_usd": 0,
        "case_mutations": 0,
        "result": result.model_dump(mode="json"),
    }
