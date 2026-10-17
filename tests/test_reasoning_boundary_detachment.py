"""Untrusted typed port results must not be sanitized into valid contracts."""

import hashlib
import json
from collections.abc import Mapping

import pytest

from agent_app.contracts import AnalysisResult, CaseState, EvidenceBundle, EvidenceHit
from agent_app.orchestration.engine import SupportEngine
from agent_app.reasoning.output import InvalidAnalysis, parse_analysis
from agent_app.testing.fakes import FakeReasoner

MARKER = "untrusted-port-extra-marker"


def _digest(model):
    return hashlib.sha256(
        json.dumps(model.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _analysis(decision="escalate"):
    payload = {
        "decision": decision,
        "user_draft": "A maintainer should review the supplied documents.",
        "maintainer_summary": "The supplied documents need review.",
        "rationale": "The available evidence does not establish a diagnosis.",
        "evidence_links": [{"claim": "Supplied document.", "chunk_id": "doc:1"}],
        "facts_delta": [
            {"name": "platform", "value": "local", "source_ref": "user:1", "turn_id": "turn:1"}
        ],
    }
    if decision == "ask":
        payload.update(next_question="Which version is installed?", missing_info=["version"])
    if decision == "retrieve_more":
        payload.update(user_draft="", maintainer_summary="", retrieval_queries=["widget lifecycle"])
    return AnalysisResult.model_validate(payload)


def _bundle():
    return EvidenceBundle(
        snapshot_id="boundary:docs",
        hits=(
            EvidenceHit(
                chunk_id="doc:1",
                source_id="source:1",
                excerpt="A neutral document.",
                source_url="https://example.org/docs",
                source_type="doc",
            ),
        ),
    )


def _inject(value, kind):
    if kind == "attribute":
        return value.model_copy(update={MARKER: MARKER})
    result = value.model_copy(deep=True)
    object.__setattr__(result, "__pydantic_" + kind + "__", {MARKER: MARKER})
    return result


class _Retriever:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def search(self, request):
        self.calls += 1
        return self.response


def _run(raw):
    reasoner = FakeReasoner([_analysis().model_copy(update={"facts_delta": ()})])
    retriever = _Retriever(raw)
    result = SupportEngine(retriever, reasoner, snapshot_id="boundary:docs").run(
        CaseState(case_id="boundary:case"), "Explain this document.", run_id="boundary:run"
    )
    return result, reasoner, retriever


@pytest.mark.parametrize("kind", ["attribute", "private", "extra"])
@pytest.mark.parametrize(
    "representation,target", [("model", "bundle"), ("model", "hit"), ("nested_mapping", "hit")]
)
def test_malformed_retrieval_stops_before_reasoning(kind, target, representation):
    bundle = _bundle()
    if target == "hit":
        bundle = bundle.model_copy(update={"hits": (_inject(bundle.hits[0], kind),)})
    else:
        bundle = _inject(bundle, kind)
    raw = (
        {"snapshot_id": bundle.snapshot_id, "hits": bundle.hits}
        if representation == "nested_mapping"
        else bundle
    )
    result, reasoner, retriever = _run(raw)
    assert result.status == "error" and result.error_code == "RetrievalResultInvalid"
    assert result.model_attempts == 0 and result.retrieval_rounds == 1
    assert retriever.calls == 1 and reasoner.inputs == []
    assert MARKER not in result.model_dump_json()
    invalid = bundle if target == "bundle" else bundle.hits[0]
    metadata = (
        invalid.__dict__ if kind == "attribute" else getattr(invalid, "__pydantic_" + kind + "__")
    )
    assert metadata[MARKER] == MARKER


@pytest.mark.parametrize(
    "field,value",
    [("source_url", "javascript:invalid"), ("excerpt", None), ("source_type", "unregistered")],
)
def test_mapping_does_not_trust_nested_typed_hit_fields(field, value):
    bundle = _bundle()
    hit = bundle.hits[0].model_copy(update={field: value})
    result, reasoner, _ = _run({"snapshot_id": bundle.snapshot_id, "hits": (hit,)})
    assert result.error_code == "RetrievalResultInvalid" and reasoner.inputs == []
    assert result.model_attempts == 0


@pytest.mark.parametrize("kind", ["attribute", "private", "extra"])
@pytest.mark.parametrize("target", ["analysis", "evidence_links", "facts_delta"])
def test_typed_output_rejects_hidden_contract_state(kind, target):
    analysis = _analysis()
    raw = (
        _inject(analysis, kind)
        if target == "analysis"
        else analysis.model_copy(update={target: (_inject(getattr(analysis, target)[0], kind),)})
    )
    with pytest.raises(InvalidAnalysis) as caught:
        parse_analysis(raw)
    assert [(issue.code, issue.field) for issue in caught.value.issues] == [("invalid_shape", None)]
    assert MARKER not in str(caught.value) + repr(caught.value.issues)
    assert raw is not analysis


@pytest.mark.parametrize("kind", ["attribute", "private", "extra"])
@pytest.mark.parametrize("target", ["evidence_links", "facts_delta"])
def test_mapping_output_rejects_hidden_nested_contract_state(kind, target):
    analysis = _analysis()
    raw = analysis.model_dump()
    raw[target] = (_inject(getattr(analysis, target)[0], kind),)
    with pytest.raises(InvalidAnalysis) as caught:
        parse_analysis(raw)
    assert [(issue.code, issue.field) for issue in caught.value.issues] == [("invalid_shape", None)]
    assert MARKER not in str(caught.value) + repr(caught.value.issues)


@pytest.mark.parametrize(
    "target,field,value",
    [("evidence_links", "chunk_id", "bad identifier"), ("facts_delta", "provenance_kind", "model")],
)
def test_mapping_output_revalidates_bypassed_nested_declared_fields(target, field, value):
    analysis = _analysis()
    raw = analysis.model_dump()
    raw[target] = (getattr(analysis, target)[0].model_copy(update={field: value}),)
    with pytest.raises(InvalidAnalysis) as caught:
        parse_analysis(raw)
    assert [(issue.code, issue.field) for issue in caught.value.issues] == [
        ("invalid_field", target)
    ]


class _BrokenMapping(Mapping):
    def __iter__(self):
        raise ValueError(MARKER)

    def __getitem__(self, key):
        raise ValueError(MARKER)

    def __len__(self):
        return 1


def test_malformed_mapping_conversion_has_only_allowlisted_diagnostics():
    with pytest.raises(InvalidAnalysis) as caught:
        parse_analysis(_BrokenMapping())
    assert str(caught.value) == "ModelOutputInvalid"
    assert [(i.code, i.field) for i in caught.value.issues] == [("invalid_shape", None)]


# Captured on 35c1ed0 before modifying either parser or engine.
VALID_ANALYSIS_DIGESTS = {
    "answer": "09bcb5dac6d6cc7c97ac473923e70fc1abe34d46e4f0793f75b91f22dd7ed20f",
    "ask": "8b75756091f4978f5bc3662a62036700fa2197cf655c36d23ca7873381edb718",
    "escalate": "7500fee8242eb3ccfb966a1c0c4d99578c39d19d0fcab870e076ccec460ce78a",
    "retrieve_more": "4ddfdcb8360159980959e6203597b05bdebc295bd84a8befb23162f6fca769b1",
}
VALID_RUN_DIGEST = "151914f764e250aad1930e94e6cd2dbdc4e15b1592d5bf1fce197c4b74b05240"


@pytest.mark.parametrize("decision", ["answer", "ask", "escalate", "retrieve_more"])
@pytest.mark.parametrize("representation", ["model", "mapping", "nested_mapping", "json"])
def test_valid_analysis_bytes_remain_exact(decision, representation):
    expected = _analysis(decision)
    raw = expected
    if representation == "mapping":
        raw = expected.model_dump()
    if representation == "nested_mapping":
        raw = expected.model_dump() | {
            "evidence_links": expected.evidence_links,
            "facts_delta": expected.facts_delta,
        }
    if representation == "json":
        raw = expected.model_dump_json()
    actual = parse_analysis(raw)
    assert actual == expected and actual is not expected
    assert _digest(actual) == VALID_ANALYSIS_DIGESTS[decision]


@pytest.mark.parametrize("representation", ["model", "mapping", "nested_mapping"])
def test_valid_retrieval_run_bytes_and_input_remain_exact(representation):
    expected = _bundle()
    raw = expected if representation == "model" else expected.model_dump()
    if representation == "nested_mapping":
        raw["hits"] = expected.hits
    result, reasoner, _ = _run(raw)
    assert result.status == "awaiting_approval"
    assert _digest(result) == VALID_RUN_DIGEST
    assert reasoner.inputs[0][2] == expected and reasoner.inputs[0][2] is not expected
    assert _bundle() == expected


def test_invalid_model_output_uses_existing_two_attempt_repair_allowance():
    malformed = _inject(_analysis(), "private")
    reasoner = FakeReasoner([malformed, _analysis().model_copy(update={"facts_delta": ()})])
    result = SupportEngine(_Retriever(_bundle()), reasoner, snapshot_id="boundary:docs").run(
        CaseState(case_id="boundary:case"), "Explain this document.", run_id="boundary:repair"
    )
    assert result.status == "awaiting_approval" and result.model_attempts == 2
    assert len(reasoner.inputs) == 2 and reasoner.contexts[1].output_feedback is not None
    assert reasoner.contexts[1].output_feedback.issues[0].code == "invalid_shape"
    assert MARKER not in result.model_dump_json()


def test_two_invalid_model_outputs_cannot_obtain_a_third_attempt():
    reasoner = FakeReasoner([_inject(_analysis(), "extra")] * 3)
    result = SupportEngine(_Retriever(_bundle()), reasoner, snapshot_id="boundary:docs").run(
        CaseState(case_id="boundary:case"), "Explain this document.", run_id="boundary:stop"
    )
    assert result.status == "error" and result.error_code == "ModelOutputInvalid"
    assert result.model_attempts == len(reasoner.inputs) == 2
    assert len(reasoner.responses) == 1 and result.retrieval_rounds == 1
    assert MARKER not in result.model_dump_json()
