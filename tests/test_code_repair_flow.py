"""Syntax repair shares the core's existing attempts and preserves authority checks."""

import pytest
from pydantic import ValidationError

from agent_app.contracts import (
    AnalysisResult,
    CaseState,
    EvidenceBundle,
    EvidenceHit,
    EvidenceLink,
    OutputFeedback,
    OutputIssue,
)
from agent_app.llm.config import MetisConfig
from agent_app.orchestration import SupportEngine
from agent_app.orchestration import engine as engine_module
from agent_app.testing.fakes import FakeReasoner, FakeRetriever

SNAPSHOT = "code-repair-fixture"
CASE = CaseState(case_id="case:code-repair", case_revision=3)
INVALID_SOURCE = "PRIVATE_REJECTED_CODE_MARKER = )"
VALID_SOURCE = (
    "def callback(step):\n"
    "    st.session_state.counter += step\n"
    'st.button("Run", on_click=callback, args=(1,))'
)


def fenced(source):
    return f"```python\n{source}\n```"


def answer(source=VALID_SOURCE, *, chunk_id="docs:callback", maintainer_source=None):
    return AnalysisResult(
        decision="answer",
        user_draft=fenced(source),
        maintainer_summary=(
            fenced(maintainer_source)
            if maintainer_source
            else "A pending synthetic callback draft."
        ),
        rationale="This tests syntax repair, not runtime or API correctness.",
        evidence_links=(EvidenceLink(claim="Synthetic callback example", chunk_id=chunk_id),),
    )


def run(responses):
    bundle = EvidenceBundle(
        snapshot_id=SNAPSHOT,
        hits=(
            EvidenceHit(
                chunk_id="docs:callback",
                source_id="source:callback",
                excerpt="Synthetic callback evidence for operational testing.",
                source_url="https://example.org/offline-code-repair",
                source_type="doc",
            ),
        ),
    )
    retriever = FakeRetriever([bundle])
    reasoner = FakeReasoner(responses)
    result = SupportEngine(retriever, reasoner, snapshot_id=SNAPSHOT).run(
        CASE, "How can I pass a value to the callback?", run_id="run:code-repair"
    )
    return result, retriever, reasoner


def test_valid_json_with_bad_python_gets_one_targeted_repair_within_the_same_run():
    before = CASE.model_dump()
    result, retriever, reasoner = run([answer(INVALID_SOURCE).model_dump_json(), answer()])

    assert result.status == "awaiting_approval"
    assert result.analysis == answer()
    assert result.model_attempts == len(reasoner.inputs) == 2
    assert result.retrieval_rounds == len(retriever.requests) == 1
    assert reasoner.contexts[0].output_feedback is None
    assert reasoner.contexts[1].output_feedback == OutputFeedback(
        issues=(OutputIssue(code="invalid_python_syntax"),)
    )
    assert {context.run_id for context in reasoner.contexts} == {"run:code-repair"}
    assert [context.attempt_index for context in reasoner.contexts] == [1, 2]
    assert CASE.model_dump() == before


def test_bad_python_in_the_second_maintainer_draft_stops_after_two_attempts():
    result, _, reasoner = run(
        [answer(INVALID_SOURCE), answer(maintainer_source=INVALID_SOURCE), answer()]
    )

    assert result.status == "error"
    assert result.error_code == "ModelOutputInvalid"
    assert result.analysis is None
    assert result.model_attempts == len(reasoner.inputs) == 2
    assert [issue.code for issue in result.output_issues] == [
        "invalid_python_syntax",
        "invalid_python_syntax",
    ]
    assert len(reasoner.responses) == 1


def test_earlier_json_failure_leaves_no_third_attempt_for_python_repair():
    result, _, reasoner = run(["not valid JSON", answer(INVALID_SOURCE), answer()])

    assert result.status == "error"
    assert result.analysis is None
    assert result.model_attempts == len(reasoner.inputs) == 2
    assert reasoner.contexts[1].output_feedback == OutputFeedback(
        issues=(OutputIssue(code="invalid_json"),)
    )
    assert [issue.code for issue in result.output_issues] == [
        "invalid_json",
        "invalid_python_syntax",
    ]
    assert len(reasoner.responses) == 1


def test_bad_code_cannot_convert_an_unknown_source_into_a_repairable_violation(monkeypatch):
    def forbid_syntax_check(_analysis):
        pytest.fail("Source authority must be checked before buying syntax repair")

    monkeypatch.setattr(engine_module, "has_invalid_python_code", forbid_syntax_check)
    result, _, reasoner = run([answer(INVALID_SOURCE, chunk_id="invented:source"), answer()])

    assert result.status == "error"
    assert result.error_code == "UnknownEvidenceReference"
    assert result.analysis is None
    assert result.model_attempts == len(reasoner.inputs) == 1
    assert result.output_issues == ()
    assert len(reasoner.responses) == 1


def test_rejected_source_and_parser_exception_text_are_absent_from_exported_diagnostics(capsys):
    result, _, reasoner = run([answer(INVALID_SOURCE), answer()])
    exported = result.model_dump_json() + reasoner.contexts[1].model_dump_json()
    captured = capsys.readouterr()

    assert result.status == "awaiting_approval"
    assert "invalid_python_syntax" in exported
    assert "PRIVATE_REJECTED_CODE_MARKER" not in exported
    assert "SyntaxError" not in exported
    assert "unmatched" not in exported
    assert captured.out == captured.err == ""


def test_environment_policy_selection_is_validated_and_defaults_to_baseline(monkeypatch):
    monkeypatch.setenv("METIS_API_KEY", "offline-code-repair-test-key")
    monkeypatch.delenv("METIS_PROMPT_POLICY", raising=False)
    monkeypatch.delenv("METIS_LIVE_ENABLED", raising=False)
    monkeypatch.delenv("METIS_MODEL", raising=False)

    assert MetisConfig.from_env().prompt_policy == "baseline"
    monkeypatch.setenv("METIS_PROMPT_POLICY", "structured_rules")
    selected = MetisConfig.from_env()
    assert selected.prompt_policy == "structured_rules"
    assert selected.live_enabled is False
    monkeypatch.setenv("METIS_PROMPT_POLICY", "unregistered-policy")
    with pytest.raises(ValidationError):
        MetisConfig.from_env()


def test_wrong_callback_arity_with_valid_syntax_remains_a_semantic_review_requirement():
    wrong_arity = (
        "def callback(required_argument):\n"
        "    st.session_state.counter += required_argument\n"
        'st.button("Run", on_click=callback)'
    )
    result, _, reasoner = run([answer(wrong_arity)])

    assert result.status == "awaiting_approval"
    assert result.model_attempts == len(reasoner.inputs) == 1
    assert result.output_issues == ()
    assert result.analysis.user_draft == fenced(wrong_arity)
