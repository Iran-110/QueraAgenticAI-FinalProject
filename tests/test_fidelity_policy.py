"""Exact context indexing and prompt compatibility, not semantic-quality scores."""

import hashlib
import json

import pytest
from pydantic import ValidationError

from agent_app.contracts import (
    AnalysisResult,
    CaseState,
    EvidenceBundle,
    EvidenceHit,
    Fact,
    OutputFeedback,
    OutputIssue,
    ProposalRequirements,
    QuestionTarget,
    ReasoningContext,
)
from agent_app.llm.config import MetisConfig
from agent_app.llm.metis import request_id_for
from agent_app.reasoning.prompts import FIDELITY_RULES, build_messages


def case():
    return CaseState(
        case_id="case:fidelity",
        case_revision=3,
        facts=(
            Fact(
                name="streamlit_version",
                value="1.63.0",
                source_ref="user:old-report",
                turn_id="turn:1",
                status="superseded",
            ),
            Fact(
                name="docs_version",
                value="1.65.0",
                source_ref="source:new-docs",
                turn_id="turn:2",
                provenance_kind="evidence",
            ),
            Fact(
                name="streamlit_version",
                value="1.64.0",
                source_ref="user:correction",
                turn_id="turn:3",
            ),
            Fact(
                name="reported_reduction",
                value='The isolated test with default=["Pear"] works',
                source_ref="user:correction",
                turn_id="turn:3",
            ),
            Fact(
                name="docs_version",
                value="1.62.0",
                source_ref="source:old-docs",
                turn_id="turn:1",
                provenance_kind="evidence",
                status="superseded",
            ),
        ),
        unknowns=("minimal_failing_reproduction", "options_builder_implementation"),
        checks_performed=(
            'User reports the isolated test with default=["Pear"] works',
            "User reports repeating only that test in a new tab",
        ),
    )


def bundle():
    return EvidenceBundle(
        snapshot_id="fidelity-fixture",
        hits=(
            EvidenceHit(
                chunk_id="chunk:timing",
                source_id="source:timing",
                excerpt="UNTRUSTED_SOURCE_MARKER: callback arguments are established at construction.",
                source_url="https://example.org/timing",
                source_type="doc",
                source_span="Unversioned snapshot, lines 104-114",
            ),
            EvidenceHit(
                chunk_id="chunk:signature",
                source_id="source:signature",
                excerpt="st.selectbox(label, options, key=None, on_change=None, args=None)",
                source_url="https://example.org/api",
                source_type="doc",
                source_commit="a" * 40,
                source_span="JSON pointer /1.64.0/streamlit.selectbox",
                applicable_versions=("1.64.0",),
            ),
        ),
    )


def context(**changes):
    return ReasoningContext(
        **{
            "run_id": "run:fidelity",
            "case_id": case().case_id,
            "case_revision": case().case_revision,
            "attempt_index": 1,
            "remaining_model_attempts": 1,
            "remaining_retrieval_rounds": 1,
            "can_refine": True,
            "query_limit": 1,
            "proposal_requirements": ProposalRequirements(
                case_id=case().case_id,
                case_revision=case().case_revision,
                question_targets=(
                    QuestionTarget(
                        name="options_builder_implementation",
                        question="Could you share the options helper from the failing full app?",
                    ),
                ),
            ),
            **changes,
        }
    )


def messages(**changes):
    return build_messages(
        case(),
        "UNTRUSTED_USER_MARKER: my reduced test works but the full app fails.",
        bundle(),
        **{"policy": "fidelity_rules", "context": context(), **changes},
    )


def digest(messages):
    return hashlib.sha256(
        json.dumps(messages, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


# Captured from the seven existing policies before adding fidelity_rules. These
# rich inputs cover corrections, provenance, source scopes and caller catalogs.
PRIOR_DIGESTS = {
    "baseline": {
        "none": "0f92dbef9eff8ce7c3585d140449922490823b85e6e4d41dad0a70a9b8284d26",
        "invalid_python_syntax": "1a58ac149b3f609746e4420b169a9fee804e561aa98b1ba12d963bbee387dbca",
        "callback_arity_mismatch": "cfbbcf919aea1ec09f298be45065f75d6e1dee13e76f636289bd3e7b04ed79cc",
    },
    "decision_rubric": {
        "none": "ecf67ab0b7f2879aaccfc9937498ad797f963b6f2d3002f4da7a5c6f29145eee",
        "invalid_python_syntax": "43f1641a5139002eba9fbc7efbf43f3e0d40f2f1e9954c8dc35990099dc61723",
        "callback_arity_mismatch": "260bf6c13198af66811b7d67966dde1e6d655e3d5a4d95d8a5eddc95f91a51bc",
    },
    "bounded_rubric": {
        "none": "6ced00872116a6d70dfe0228964245bd27039b9f84b9fd2a4622db3cf437f7a8",
        "invalid_python_syntax": "db3e06685ef3125fade116de65a060542a0bdf6d4c179b7d24dac5ca99c7eb57",
        "callback_arity_mismatch": "b676cde6f445cee83c935d25f2a4c23d643ae4c46249aebe94726899f7eac6e2",
    },
    "structured_rules": {
        "none": "ecea1b92777649129c1f48d83b7fcddd8049a1667b5d956324468fc83d037017",
        "invalid_python_syntax": "08b99ddd22c3798ad22548e4d9daf7cecedd7c25f8cf578e3c2d50052d679079",
        "callback_arity_mismatch": "6715e454fc24a823daa1e39b80e7c89c289806dd53904d7608b09a2ebde4da95",
    },
    "diagnostic_rules": {
        "none": "9f14d5d143e4115e1b6a3c9f2ad221be3a6efb9ca4b95097ab4b307499c59efd",
        "invalid_python_syntax": "c7b3161179fea28d1d19f0d969df7df0280466cbb15e9b1ec76e3d412df69070",
        "callback_arity_mismatch": "828a7fe7aaaaa79b8e99cc6a4a652bf21d5c6769a2ff6d6fb112f2b8c053c9f0",
    },
    "grounded_rules": {
        "none": "014b478a35bf33aec72d824e7a5a4134f00712ffe9d330bb1bd4370d5252c982",
        "invalid_python_syntax": "0e74601290fffa77425bba4988cc24be774a6ecdca6232ae552cd2bde39801a3",
        "callback_arity_mismatch": "f725503a3a97c38b9457e63a8c3a20554af4deb542c37e5bd4180b0b4a21a225",
    },
    "compiled_rules": {
        "none": "bb8cd06565db67426754116ac332862b9fa8772cb55367b78074f958af2397d1",
        "invalid_python_syntax": "2f7ac876187c3e15727c96ffef10c499507ce6eb40e152861dc6774d28a79489",
        "callback_arity_mismatch": "5801c19daf09e240c50417c26ba854fdf4276e3508b8613f5cc02020d493892b",
    },
}


@pytest.mark.parametrize(
    "feedback_kind", (None, "invalid_python_syntax", "callback_arity_mismatch")
)
@pytest.mark.parametrize(
    "policy",
    (
        "baseline",
        "decision_rubric",
        "bounded_rubric",
        "structured_rules",
        "diagnostic_rules",
        "grounded_rules",
        "compiled_rules",
    ),
)
def test_previous_seven_policy_messages_remain_byte_identical(policy, feedback_kind):
    feedback = OutputFeedback(issues=(OutputIssue(code=feedback_kind),)) if feedback_kind else None
    built = messages(policy=policy, feedback=feedback)
    assert digest(built) == PRIOR_DIGESTS[policy][feedback_kind or "none"]
    assert "fidelity_view" not in json.loads(built[1]["content"])


def test_candidate_adds_only_the_fidelity_instruction_and_index_to_shape_policy():
    prior = messages(policy="structured_rules")
    candidate = messages()
    assert candidate[0]["content"] == prior[0]["content"] + FIDELITY_RULES
    prior_payload = json.loads(prior[1]["content"])
    candidate_payload = json.loads(candidate[1]["content"])
    assert set(candidate_payload) == set(prior_payload) | {"fidelity_view"}
    del candidate_payload["fidelity_view"]
    assert candidate_payload == prior_payload
    assert candidate_payload["response_schema"] == AnalysisResult.model_json_schema()
    assert "proposal_requirements" not in candidate_payload


def test_index_preserves_corrections_attribution_and_evidence_status_in_supplied_order():
    supplied = case()
    view = json.loads(messages()[1]["content"])["fidelity_view"]
    assert (view["case_id"], view["case_revision"]) == (
        supplied.case_id,
        supplied.case_revision,
    )
    assert view["active_user_facts"] == [
        supplied.facts[index].model_dump(mode="json") for index in (2, 3)
    ]
    assert view["superseded_user_facts"] == [supplied.facts[0].model_dump(mode="json")]
    assert view["evidence_observations"] == [
        supplied.facts[index].model_dump(mode="json") for index in (1, 4)
    ]
    assert view["recorded_checks"] == list(supplied.checks_performed)
    assert view["unknowns"] == list(supplied.unknowns)


def test_source_index_copies_scopes_without_claim_support_or_applicability_inference():
    view = json.loads(messages()[1]["content"])["fidelity_view"]
    assert view["source_scopes"] == [
        {
            "chunk_id": hit.chunk_id,
            "applicable_versions": list(hit.applicable_versions),
            "source_span": hit.source_span,
            "source_commit": hit.source_commit,
        }
        for hit in bundle().hits
    ]
    assert view["source_scopes"][0]["applicable_versions"] == []
    assert view["source_scopes"][0]["source_commit"] is None
    assert all(
        set(scope) == {"chunk_id", "applicable_versions", "source_span", "source_commit"}
        for scope in view["source_scopes"]
    )


def test_empty_records_stay_empty_without_inventing_checks_facts_or_source_labels():
    empty_case = CaseState(case_id="case:fidelity", case_revision=3)
    built = build_messages(
        empty_case,
        "A supplied symptom with unrecorded checks.",
        EvidenceBundle(snapshot_id="empty"),
        policy="fidelity_rules",
        context=context(proposal_requirements=None),
    )
    view = json.loads(built[1]["content"])["fidelity_view"]
    assert set(view) == {
        "case_id",
        "case_revision",
        "active_user_facts",
        "superseded_user_facts",
        "evidence_observations",
        "recorded_checks",
        "unknowns",
        "source_scopes",
    }
    assert all(
        value == [] for key, value in view.items() if key not in {"case_id", "case_revision"}
    )
    assert "checks are unrecorded, not that none were performed" in built[0]["content"]


def test_untrusted_values_remain_data_and_cannot_supply_index_instruction_or_labels():
    built = messages()
    assert "UNTRUSTED_USER_MARKER" not in built[0]["content"]
    assert "UNTRUSTED_SOURCE_MARKER" not in built[0]["content"]
    payload = json.loads(built[1]["content"])
    assert payload["user_message"].startswith("UNTRUSTED_USER_MARKER")
    assert payload["evidence"]["hits"][0]["excerpt"].startswith("UNTRUSTED_SOURCE_MARKER")
    assert set(payload) == {
        "case",
        "user_message",
        "evidence",
        "response_schema",
        "workflow",
        "decision_requirements",
        "fidelity_view",
    }


def test_index_and_payload_are_fresh_copies_without_mutating_or_caching_inputs():
    supplied_case, supplied_bundle, supplied_context = case(), bundle(), context()
    originals = (
        supplied_case.model_dump_json(),
        supplied_bundle.model_dump_json(),
        supplied_context.model_dump_json(),
        AnalysisResult.model_json_schema(),
    )
    first = build_messages(
        supplied_case,
        "A supplied symptom.",
        supplied_bundle,
        policy="fidelity_rules",
        context=supplied_context,
    )
    modified_payload = json.loads(first[1]["content"])
    modified_payload["fidelity_view"]["active_user_facts"][0]["value"] = "CHANGED"
    modified_payload["fidelity_view"]["recorded_checks"].clear()
    second = build_messages(
        supplied_case,
        "A supplied symptom.",
        supplied_bundle,
        policy="fidelity_rules",
        context=supplied_context,
    )
    assert first == second
    assert originals == (
        supplied_case.model_dump_json(),
        supplied_bundle.model_dump_json(),
        supplied_context.model_dump_json(),
        AnalysisResult.model_json_schema(),
    )
    other_case = CaseState(case_id="case:fidelity", case_revision=3)
    later = build_messages(
        other_case,
        "Another supplied symptom.",
        EvidenceBundle(snapshot_id="different"),
        policy="fidelity_rules",
        context=supplied_context,
    )
    assert json.loads(later[1]["content"])["fidelity_view"]["active_user_facts"] == []


@pytest.mark.parametrize(
    "workflow",
    [
        None,
        context(case_id="case:other", proposal_requirements=None),
        context(case_revision=2, proposal_requirements=None),
    ],
)
def test_candidate_requires_context_bound_to_the_same_case_revision(workflow):
    with pytest.raises(ValueError):
        messages(context=workflow)


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "invented"},
        {"provenance_kind": "assistant"},
        {"turn_id": "bad turn"},
        {"value": None},
    ],
)
def test_candidate_revalidates_nested_fact_bypass_before_indexing(changes):
    malformed_fact = case().facts[0].model_copy(update=changes)
    malformed_case = case().model_copy(update={"facts": (malformed_fact,)})
    with pytest.raises(ValidationError):
        build_messages(
            malformed_case,
            "A supplied symptom.",
            bundle(),
            policy="fidelity_rules",
            context=context(),
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"applicable_versions": ("1.64.0", "1.64.0")},
        {"source_url": "not-a-url"},
        {"chunk_id": "bad chunk"},
    ],
)
def test_candidate_revalidates_nested_source_bypass_before_indexing(changes):
    malformed_hit = bundle().hits[0].model_copy(update=changes)
    malformed_bundle = bundle().model_copy(update={"hits": (malformed_hit,)})
    with pytest.raises(ValidationError):
        build_messages(
            case(),
            "A supplied symptom.",
            malformed_bundle,
            policy="fidelity_rules",
            context=context(),
        )


@pytest.mark.parametrize(
    "changes",
    [{"checks_performed": (None,)}, {"unknowns": ("same", "SAME")}, {"case_revision": -1}],
)
def test_candidate_revalidates_constructed_case_fields(changes):
    malformed_case = case().model_copy(update=changes)
    with pytest.raises(ValidationError):
        build_messages(
            malformed_case,
            "A supplied symptom.",
            bundle(),
            policy="fidelity_rules",
            context=context(),
        )


def test_candidate_revalidates_constructed_workflow_context():
    with pytest.raises(ValidationError):
        messages(context=context().model_copy(update={"remaining_model_attempts": 2}))


@pytest.mark.parametrize("message", [None, 1, "", "   ", "x" * 20_001])
def test_candidate_rejects_invalid_user_input_without_extracting_it(message):
    with pytest.raises(ValueError, match="Invalid user input"):
        build_messages(case(), message, bundle(), policy="fidelity_rules", context=context())


def test_candidate_preserves_message_whitespace_instead_of_rewriting_the_report():
    text = "  An exact user report.\n"
    built = build_messages(case(), text, bundle(), policy="fidelity_rules", context=context())
    assert json.loads(built[1]["content"])["user_message"] == text


def test_fidelity_selection_preserves_default_and_configuration_secret_masking():
    secret = "FAKE_PRIVATE_FIDELITY_CREDENTIAL"
    config = MetisConfig(api_key=secret, prompt_policy="fidelity_rules")
    assert config.prompt_policy == "fidelity_rules"
    assert config.live_enabled is False
    assert secret not in repr(config)
    assert secret not in config.model_dump_json()
    assert MetisConfig(api_key=secret).prompt_policy == "baseline"
    assert build_messages(case(), "A supplied symptom.", bundle()) == build_messages(
        case(), "A supplied symptom.", bundle(), policy="baseline"
    )
    with pytest.raises(ValidationError) as error:
        MetisConfig(api_key=secret, prompt_policy="invalid-policy")
    assert secret not in error.value.json()


@pytest.mark.parametrize("code", ["invalid_python_syntax", "callback_arity_mismatch"])
def test_feedback_suffix_and_request_identity_are_unchanged_by_the_candidate(code):
    feedback = OutputFeedback(issues=(OutputIssue(code=code),))
    repaired_context = context(
        attempt_index=2,
        remaining_model_attempts=0,
        can_refine=False,
        output_feedback=feedback,
    )
    plain_context = repaired_context.model_copy(update={"output_feedback": None})
    assert request_id_for(repaired_context) == request_id_for(plain_context)
    candidate_plain = messages(context=plain_context)
    candidate_repaired = messages(context=repaired_context, feedback=feedback)
    old_plain = messages(policy="structured_rules", context=plain_context)
    old_repaired = messages(policy="structured_rules", context=repaired_context, feedback=feedback)
    prior_suffix = old_repaired[0]["content"][len(old_plain[0]["content"]) :]
    assert candidate_repaired[0]["content"] == candidate_plain[0]["content"] + prior_suffix
    assert candidate_repaired[1] == candidate_plain[1]
