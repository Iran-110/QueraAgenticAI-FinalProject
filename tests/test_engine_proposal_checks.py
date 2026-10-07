"""Optional caller constraints use existing repair limits and never authorize actions."""

from pathlib import Path

import pytest

from agent_app.contracts import (
    AnalysisResult,
    CaseState,
    EvidenceBundle,
    EvidenceHit,
    EvidenceLink,
    Fact,
    ProposalRequirements,
    QuestionTarget,
)
from agent_app.orchestration import SupportEngine
from agent_app.orchestration import engine as engine_module
from agent_app.reasoning.probes import load_suite
from agent_app.testing.fakes import FakeReasoner, FakeRetriever

SNAPSHOT = "proposal-flow-fixture"
QUESTION = "Can you share the complete callback helper body?"


def case(**changes):
    return CaseState(case_id="case:proposal-flow", case_revision=2, **changes)


def requirements(**changes):
    return ProposalRequirements(
        **(
            {
                "case_id": "case:proposal-flow",
                "case_revision": 2,
                "question_targets": (QuestionTarget(name="helper_body", question=QUESTION),),
            }
            | changes
        )
    )


def ask(**changes):
    return AnalysisResult(
        **(
            {
                "decision": "ask",
                "user_draft": "The small example works; the full helper is still missing. "
                + QUESTION,
                "maintainer_summary": "The full implementation is not supplied.",
                "rationale": "The helper body distinguishes two implementation branches.",
                "missing_info": ("helper_body",),
                "next_question": QUESTION,
            }
            | changes
        )
    )


def bundle():
    return EvidenceBundle(
        snapshot_id=SNAPSHOT,
        hits=(
            EvidenceHit(
                chunk_id="synthetic:source",
                source_id="synthetic:source",
                source_type="doc",
                source_url="https://example.org/proposal-fixture",
                excerpt="Synthetic source text, not an API contract.",
            ),
        ),
    )


def engine(responses, *, checks=True, retrieval=None):
    retriever = FakeRetriever(retrieval or (bundle(),))
    reasoner = FakeReasoner(responses)
    return (
        SupportEngine(retriever, reasoner, snapshot_id=SNAPSHOT, proposal_checks=checks),
        retriever,
        reasoner,
    )


@pytest.mark.parametrize("checks", [False, True])
def test_absent_catalog_does_not_guess_missing_user_details(checks):
    core, _, _ = engine((ask(missing_info=()),), checks=checks)
    result = core.run(case(), "My reduced example works.")
    assert result.status == "awaiting_approval"
    assert result.output_issues == ()


def test_catalog_can_be_exposed_without_enforcing_it_for_prompt_only_comparison():
    core, _, reasoner = engine((ask(missing_info=()),), checks=False)
    result = core.run(case(), "My reduced example works.", proposal_requirements=requirements())
    assert result.status == "awaiting_approval"
    assert reasoner.contexts[0].proposal_requirements == requirements()


@pytest.mark.parametrize(
    ("bad", "code", "field"),
    [
        (ask(missing_info=()), "ask_target_required", "missing_info"),
        (ask(missing_info=("helper_body", "another")), "ask_target_required", "missing_info"),
        (
            ask(missing_info=("unregistered_secret_field",)),
            "ask_unregistered_target",
            "missing_info",
        ),
        (ask(next_question="Which version was it?"), "ask_question_mismatch", "next_question"),
    ],
)
def test_invalid_declared_question_uses_one_repair_without_exporting_its_values(bad, code, field):
    core, retriever, reasoner = engine((bad, ask()))
    result = core.run(case(), "My reduced example works.", proposal_requirements=requirements())
    assert result.status == "awaiting_approval"
    assert (result.model_attempts, result.retrieval_rounds) == (2, 1)
    assert len(retriever.requests) == 1
    assert [(issue.code, issue.field) for issue in result.output_issues] == [(code, field)]
    assert reasoner.contexts[1].output_feedback.issues == result.output_issues
    assert reasoner.contexts[1].proposal_requirements == requirements()
    assert "unregistered_secret_field" not in result.model_dump_json()


def test_two_failed_questions_cannot_receive_a_third_attempt():
    bad = ask(missing_info=())
    core, _, reasoner = engine((bad, bad, ask()))
    result = core.run(case(), "A helper is missing.", proposal_requirements=requirements())
    assert (result.status, result.error_code, result.model_attempts) == (
        "error",
        "ModelOutputInvalid",
        2,
    )
    assert len(reasoner.responses) == 1


def test_refinement_leaves_no_additional_question_repair():
    refine = AnalysisResult(
        decision="retrieve_more",
        user_draft="",
        maintainer_summary="",
        rationale="A specific source is missing.",
        retrieval_queries=("specific helper source",),
    )
    core, _, reasoner = engine(
        (refine, ask(missing_info=()), ask()), retrieval=(bundle(), bundle())
    )
    result = core.run(case(), "A helper is missing.", proposal_requirements=requirements())
    assert result.status == "error"
    assert (result.model_attempts, result.retrieval_rounds) == (2, 2)
    assert len(reasoner.responses) == 1


def test_empty_catalog_does_not_allow_an_unregistered_question():
    core, _, _ = engine((ask(), ask()))
    result = core.run(
        case(),
        "An observed mismatch remains.",
        proposal_requirements=requirements(question_targets=()),
    )
    assert result.analysis is None
    assert [issue.code for issue in result.output_issues] == ["ask_unregistered_target"] * 2


@pytest.mark.parametrize("changes", [{"case_id": "case:other"}, {"case_revision": 1}])
def test_stale_or_unrelated_catalog_fails_before_any_adapter(changes):
    core, retriever, reasoner = engine((ask(),))
    with pytest.raises(ValueError, match="Invalid caller-owned"):
        core.run(case(), "A helper is missing.", proposal_requirements=requirements(**changes))
    assert retriever.requests == reasoner.inputs == []


def test_corrected_active_user_fact_cannot_be_registered_as_missing():
    facts = (
        Fact(
            name="streamlit_version",
            value="1.63.0",
            source_ref="user:old",
            turn_id="old",
            status="superseded",
        ),
        Fact(name="streamlit_version", value="1.64.0", source_ref="user:new", turn_id="new"),
    )
    targets = (QuestionTarget(name="streamlit_version", question="Which version?"),)
    core, retriever, reasoner = engine((ask(),))
    with pytest.raises(ValueError, match="Invalid caller-owned"):
        core.run(
            case(facts=facts),
            "The version was corrected.",
            proposal_requirements=requirements(question_targets=targets),
        )
    assert retriever.requests == reasoner.inputs == []


def test_source_version_does_not_make_a_user_version_known():
    fact = Fact(
        name="streamlit_version",
        value="1.64.0",
        source_ref="synthetic:source",
        turn_id="source-turn",
        provenance_kind="evidence",
    )
    targets = (QuestionTarget(name="streamlit_version", question="Which version is installed?"),)
    core, _, _ = engine(
        (ask(missing_info=("streamlit_version",), next_question=targets[0].question),)
    )
    result = core.run(
        case(facts=(fact,)),
        "Installed version is unknown.",
        proposal_requirements=requirements(question_targets=targets),
    )
    assert result.status == "awaiting_approval"


def test_authority_error_precedes_semantic_repair(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Semantic checks must not run after authority violation")

    monkeypatch.setattr(engine_module, "callback_code_issues", forbidden)
    bad = ask(
        missing_info=(),
        evidence_links=(EvidenceLink(claim="Unsupported", chunk_id="not-retrieved"),),
    )
    core, _, reasoner = engine((bad, ask()))
    result = core.run(case(), "A helper is missing.", proposal_requirements=requirements())
    assert result.error_code == "UnknownEvidenceReference"
    assert result.model_attempts == 1
    assert len(reasoner.responses) == 1


def test_canonical_next_question_does_not_claim_to_validate_free_text_draft():
    core, _, _ = engine((ask(user_draft="Which version are you using?"),))
    result = core.run(case(), "A helper is missing.", proposal_requirements=requirements())
    assert result.status == "awaiting_approval"
    assert result.analysis.next_question == QUESTION
    # This deliberate boundary needs semantic review and appropriate UI rendering.
    assert result.analysis.user_draft != QUESTION


@pytest.mark.parametrize("value", [1, "true", None])
def test_quality_flag_is_trusted_strict_configuration(value):
    with pytest.raises(ValueError, match="explicit boolean"):
        engine((), checks=value)


@pytest.mark.parametrize(
    ("probe_id", "bad_code", "fixed_code", "issue_code", "fresh"),
    [
        (
            "synthetic-own-widget-stale-args",
            "import streamlit as st\n"
            'def changed(value):\n    st.session_state["received"] = value\n'
            'st.selectbox("Region", ["Oslo", "Lima"], key="region", '
            'on_change=changed, args=(st.session_state["region"],))',
            "import streamlit as st\n"
            'def changed(key):\n    st.session_state["received"] = st.session_state[key]\n'
            'st.selectbox("Region", ["Oslo", "Lima"], key="region", '
            'on_change=changed, args=("region",))',
            "callback_value_captured",
            True,
        ),
        (
            "synthetic-form-submit-exact-parameter",
            "import streamlit as st\ndef submitted():\n    pass\n"
            'st.form_submit_button("Submit", on_change=submitted)',
            "import streamlit as st\ndef submitted():\n    pass\n"
            'st.form_submit_button("Submit", on_click=submitted)',
            "invalid_api_keyword",
            False,
        ),
        (
            "synthetic-own-widget-pass-key-control",
            "import streamlit as st\ndef changed(key):\n"
            '    st.session_state["received"] = st.session_state[key]\n'
            'st.selectbox("Region", ["Oslo", "Lima"], key="region", on_change=changed)',
            "import streamlit as st\ndef changed(key):\n"
            '    st.session_state["received"] = st.session_state[key]\n'
            'st.selectbox("Region", ["Oslo", "Lima"], key="region", '
            'on_change=changed, args=("region",))',
            "callback_arity_mismatch",
            True,
        ),
    ],
)
def test_source_grounded_callback_finding_uses_existing_one_repair(
    probe_id, bad_code, fixed_code, issue_code, fresh
):
    suite = load_suite(
        Path(__file__).parents[1] / "experiments/decision_quality/cases-guards-v4.json"
    )
    probe = next(probe for probe in suite.cases if probe.id == probe_id)
    evidence = probe.bundles[0]

    def proposal(code):
        return AnalysisResult(
            decision="answer",
            user_draft=f"```python\n{code}\n```",
            maintainer_summary="Proposed code only; not executed.",
            rationale="Synthetic integration test using frozen source metadata.",
            evidence_links=(
                EvidenceLink(
                    claim="Applicable callable signature", chunk_id=evidence.hits[0].chunk_id
                ),
            ),
        )

    trusted = ProposalRequirements(
        case_id=probe.case_state.case_id,
        case_revision=probe.case_state.case_revision,
        require_fresh_widget_value=fresh,
    )
    retriever = FakeRetriever((evidence,))
    reasoner = FakeReasoner((proposal(bad_code), proposal(fixed_code)))
    result = SupportEngine(
        retriever, reasoner, snapshot_id=suite.snapshot_id, proposal_checks=True
    ).run(probe.case_state, probe.user_message, proposal_requirements=trusted)
    assert result.status == "awaiting_approval"
    assert result.analysis.user_draft == proposal(fixed_code).user_draft
    assert (result.model_attempts, result.retrieval_rounds) == (2, 1)
    assert [issue.code for issue in result.output_issues] == [issue_code]
    assert reasoner.contexts[1].output_feedback.issues == result.output_issues
    assert reasoner.contexts[1].proposal_requirements == trusted

    # The same syntactically valid candidate remains accepted by the production default.
    default = SupportEngine(
        FakeRetriever((evidence,)),
        FakeReasoner((proposal(bad_code),)),
        snapshot_id=suite.snapshot_id,
    ).run(probe.case_state, probe.user_message)
    assert default.status == "awaiting_approval"
    assert default.model_attempts == 1


def test_intentional_previous_value_snapshot_survives_opt_in_checks():
    suite = load_suite(
        Path(__file__).parents[1] / "experiments/decision_quality/cases-guards-v4.json"
    )
    probe = next(
        probe for probe in suite.cases if probe.id == "synthetic-previous-value-snapshot-control"
    )
    code = (
        "import streamlit as st\n"
        'st.session_state.setdefault("region", "Oslo")\n'
        "def changed(previous):\n"
        '    st.session_state["transition"] = (previous, st.session_state["region"])\n'
        'st.selectbox("Region", ["Oslo", "Lima"], key="region", '
        'on_change=changed, args=(st.session_state["region"],))'
    )
    proposal = AnalysisResult(
        decision="answer",
        user_draft=f"```python\n{code}\n```",
        maintainer_summary="Preserves the explicitly intended old-value snapshot.",
        rationale="The user needs both the previous and current values.",
        evidence_links=(
            EvidenceLink(claim="Callback timing", chunk_id=probe.bundles[0].hits[0].chunk_id),
        ),
    )
    result = SupportEngine(
        FakeRetriever((probe.bundles[0],)),
        FakeReasoner((proposal,)),
        snapshot_id=suite.snapshot_id,
        proposal_checks=True,
    ).run(
        probe.case_state,
        probe.user_message,
        proposal_requirements=ProposalRequirements(
            case_id=probe.case_state.case_id,
            case_revision=probe.case_state.case_revision,
            require_fresh_widget_value=False,
        ),
    )
    assert result.status == "awaiting_approval"
    assert result.model_attempts == 1
    assert result.output_issues == ()


@pytest.mark.parametrize(
    ("mutation", "bad", "expected_issue"),
    [
        (
            "replace_catalog",
            ask(missing_info=("unregistered_target",), next_question="An unapproved question?"),
            "ask_unregistered_target",
        ),
        (
            "change_nested_question",
            ask(next_question="An unapproved question?"),
            "ask_question_mismatch",
        ),
    ],
)
def test_adapter_cannot_mutate_the_catalog_used_for_enforcement(mutation, bad, expected_issue):
    trusted = requirements()

    class MutatingReasoner(FakeReasoner):
        def __init__(self):
            super().__init__((bad, ask()))
            self.received_requirements = []

        def analyze(self, case, user_message, evidence, *, context):
            self.received_requirements.append(context.proposal_requirements.model_copy(deep=True))
            if not self.inputs:
                if mutation == "replace_catalog":
                    object.__setattr__(
                        context.proposal_requirements,
                        "question_targets",
                        (
                            QuestionTarget(
                                name="unregistered_target", question="An unapproved question?"
                            ),
                        ),
                    )
                else:
                    object.__setattr__(
                        context.proposal_requirements.question_targets[0],
                        "question",
                        "An unapproved question?",
                    )
            return super().analyze(case, user_message, evidence, context=context)

    reasoner = MutatingReasoner()
    result = SupportEngine(
        FakeRetriever((bundle(),)), reasoner, snapshot_id=SNAPSHOT, proposal_checks=True
    ).run(
        case(),
        "The reduced example works but the full helper is missing.",
        proposal_requirements=trusted,
    )
    assert result.status == "awaiting_approval"
    assert result.model_attempts == 2
    assert result.analysis.next_question == QUESTION
    assert [issue.code for issue in result.output_issues] == [expected_issue]
    assert reasoner.received_requirements == [trusted, trusted]
    assert trusted == requirements()
    assert reasoner.contexts[0].proposal_requirements.question_targets[0].question == (
        "An unapproved question?"
    )


def test_adapter_cannot_disable_the_private_fresh_value_requirement_across_repair():
    suite = load_suite(
        Path(__file__).parents[1] / "experiments/decision_quality/cases-guards-v4.json"
    )
    probe = next(probe for probe in suite.cases if probe.id == "synthetic-own-widget-stale-args")
    trusted = ProposalRequirements(
        case_id=probe.case_state.case_id,
        case_revision=probe.case_state.case_revision,
        require_fresh_widget_value=True,
    )
    bad_code = (
        "import streamlit as st\n"
        "def changed(value):\n    pass\n"
        'st.selectbox("Region", ["Oslo", "Lima"], key="region", '
        'on_change=changed, args=(st.session_state["region"],))'
    )
    fixed_code = (
        "import streamlit as st\n"
        'def changed(key):\n    st.session_state["received"] = st.session_state[key]\n'
        'st.selectbox("Region", ["Oslo", "Lima"], key="region", '
        'on_change=changed, args=("region",))'
    )

    def proposal(code):
        return AnalysisResult(
            decision="answer",
            user_draft=f"```python\n{code}\n```",
            maintainer_summary="Proposed callback code, not executed.",
            rationale="Frozen applicable source metadata permits a bounded static check.",
            evidence_links=(
                EvidenceLink(claim="Callback timing", chunk_id=probe.bundles[0].hits[0].chunk_id),
            ),
        )

    class MutatingReasoner(FakeReasoner):
        def __init__(self):
            super().__init__((proposal(bad_code), proposal(fixed_code)))
            self.received_fresh_flags = []

        def analyze(self, case, user_message, evidence, *, context):
            self.received_fresh_flags.append(
                context.proposal_requirements.require_fresh_widget_value
            )
            if not self.inputs:
                object.__setattr__(
                    context.proposal_requirements, "require_fresh_widget_value", False
                )
            return super().analyze(case, user_message, evidence, context=context)

    reasoner = MutatingReasoner()
    result = SupportEngine(
        FakeRetriever((probe.bundles[0],)),
        reasoner,
        snapshot_id=suite.snapshot_id,
        proposal_checks=True,
    ).run(probe.case_state, probe.user_message, proposal_requirements=trusted)
    assert result.status == "awaiting_approval"
    assert (result.model_attempts, result.retrieval_rounds) == (2, 1)
    assert result.analysis.user_draft == proposal(fixed_code).user_draft
    assert [issue.code for issue in result.output_issues] == ["callback_value_captured"]
    assert reasoner.received_fresh_flags == [True, True]
    assert reasoner.contexts[0].proposal_requirements.require_fresh_widget_value is False
    assert trusted.require_fresh_widget_value is True


def test_adapter_cannot_rewrite_retained_diagnostics_through_second_attempt_feedback():
    class MutatingReasoner(FakeReasoner):
        def analyze(self, case, user_message, evidence, *, context):
            if context.output_feedback is not None:
                issue = context.output_feedback.issues[0]
                assert (issue.code, issue.field) == ("ask_target_required", "missing_info")
                object.__setattr__(issue, "code", "invalid_api_keyword")
                object.__setattr__(issue, "field", None)
            return super().analyze(case, user_message, evidence, context=context)

    reasoner = MutatingReasoner((ask(missing_info=()), ask()))
    result = SupportEngine(
        FakeRetriever((bundle(),)), reasoner, snapshot_id=SNAPSHOT, proposal_checks=True
    ).run(case(), "The full helper is missing.", proposal_requirements=requirements())
    assert result.status == "awaiting_approval"
    assert result.model_attempts == 2
    assert [(issue.code, issue.field) for issue in result.output_issues] == [
        ("ask_target_required", "missing_info")
    ]
    assert reasoner.contexts[1].output_feedback.issues[0].code == "invalid_api_keyword"
    assert reasoner.contexts[1].output_feedback.issues[0].field is None
