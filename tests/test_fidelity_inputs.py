"""Frozen caller/source encoding controls, not model-fidelity quality scores."""

import hashlib
import json
from pathlib import Path

import pytest

from agent_app.contracts import AnalysisResult, ReasoningContext
from agent_app.reasoning.fidelity_experiments import validate_fidelity_inputs
from agent_app.reasoning.probes import ProbeExpectations, load_suite, run_probe
from agent_app.reasoning.prompts import build_messages

FIXTURES = Path(__file__).resolve().parents[1] / "experiments" / "decision_quality"
INPUT_PATH = FIXTURES / "cases-fidelity-v7.json"
SOURCE_PATH = FIXTURES / "cases-guards-v4.json"
INPUT_SHA256 = "8c64f5659cb401a434d696c217ee386ea99d1850a6ac7bfe9c11aafac9f5aff3"
SOURCE_SHA256 = "14cef1e4633d59dbc26d77cd60a175a4abcbe35b62a476823b7ed9a9e20001a1"
SOURCE_CASES = {
    "fresh-corrected-version-submit-api": "synthetic-form-submit-exact-parameter",
    "fresh-working-fragment-failing-options-path": (
        "synthetic-corrected-version-working-reduction"
    ),
    "fresh-key-read-reported-three-way-mismatch": "synthetic-reproduced-front-back-mismatch",
    "fresh-intent-correction-deliberate-old-new-pair": (
        "synthetic-previous-value-snapshot-control"
    ),
    "fresh-known-historical-signature-uncovered": "synthetic-form-submit-exact-parameter",
    "fresh-display-observation-claim-span-control": (
        "synthetic-known-environment-callback-display"
    ),
}
CANONICAL_IDS = tuple(SOURCE_CASES)
POLICIES = ("structured_rules", "fidelity_rules")
PRIVATE_MARKERS = (
    "FROZEN_DESCRIPTION_REVIEW_ONLY",
    "FROZEN_EXPECTED_LABEL_REVIEW_ONLY",
    "FROZEN_FORBIDDEN_LABEL_REVIEW_ONLY",
    "FROZEN_MISSING_TARGET_REVIEW_ONLY",
    "FROZEN_QUESTION_REVIEW_ONLY",
)


@pytest.fixture(scope="module")
def suite():
    return load_suite(INPUT_PATH)


@pytest.fixture(scope="module")
def source_suite():
    return load_suite(SOURCE_PATH)


def probe_by_id(suite, probe_id):
    return next(probe for probe in suite.cases if probe.id == probe_id)


def active_facts(probe):
    return {fact.name: fact for fact in probe.case_state.facts if fact.status == "active"}


def test_frozen_input_and_original_source_bytes_remain_unchanged():
    assert hashlib.sha256(INPUT_PATH.read_bytes()).hexdigest() == INPUT_SHA256
    assert hashlib.sha256(SOURCE_PATH.read_bytes()).hexdigest() == SOURCE_SHA256


def test_six_unique_canonical_cases_keep_original_source_and_exclusion_metadata(
    suite, source_suite
):
    assert len(suite.cases) == 6
    assert tuple(probe.id for probe in suite.cases) == CANONICAL_IDS
    assert len({probe.case_state.case_id for probe in suite.cases}) == 6
    assert suite.schema_version == 1
    assert suite.snapshot_id == source_suite.snapshot_id == "core-quality-guards-v4"
    assert (
        suite.docs_commit
        == source_suite.docs_commit
        == ("695e6ce2fb1b23afc6df66b40420ab0013ad72fd")
    )
    assert suite.source_snapshot_date == source_suite.source_snapshot_date == "2026-10-06"
    assert (
        suite.reserved_issue_ids
        == source_suite.reserved_issue_ids
        == (
            8061,
            8901,
            12782,
            16914,
        )
    )
    assert suite.family_quarantine_candidates == source_suite.family_quarantine_candidates
    assert suite.family_quarantine_candidates


@pytest.mark.parametrize("probe_id", CANONICAL_IDS)
def test_each_case_copies_exact_v4_records_into_two_deterministic_pools(
    suite, source_suite, probe_id
):
    probe = probe_by_id(suite, probe_id)
    source = probe_by_id(source_suite, SOURCE_CASES[probe_id])
    assert probe.kind == "synthetic"
    assert (probe.origin_url, probe.origin_issue_id, probe.origin_created_at) == (None, None, None)
    assert probe.case_state.case_id == f"case-{probe.id}"
    assert len(probe.bundles) == 2
    assert probe.bundles[0].hits == probe.bundles[1].hits
    for number, (bundle, original) in enumerate(zip(probe.bundles, source.bundles, strict=True), 1):
        assert bundle.retrieval_round == number
        assert bundle.model_dump(mode="json") == original.model_dump(mode="json")
        assert bundle.queries_used == ()
        assert bundle.warnings == ()
    assert probe.expectations.required_terms == probe.expectations.forbidden_terms == ()
    assert probe.case_state.pending_proposal_id is None
    for fact in probe.case_state.facts:
        assert fact.provenance_kind == "user"
        assert fact.source_ref == f"user/synthetic-fidelity-v7/{probe_id}/{fact.turn_id}"
        assert fact.turn_id.startswith("synthetic-v7-")
    names = [fact.name for fact in probe.case_state.facts if fact.status == "active"]
    assert len(names) == len(set(names))


def test_nine_unique_source_records_preserve_version_and_span_boundaries(suite):
    hits = {hit.chunk_id: hit for probe in suite.cases for hit in probe.bundles[0].hits}
    assert len(hits) == 9
    for chunk_id, hit in hits.items():
        assert hit.source_commit == suite.docs_commit
        assert hit.source_span
        assert hit.source_type == "doc"
        if chunk_id == "widget-callback-order-snapshot-v4":
            assert hit.applicable_versions == ()
            assert "not historical 1.27.2 documentation" in hit.source_span
        else:
            assert hit.applicable_versions == ("1.64.0",)
            assert hit.source_span.startswith("JSON pointer /1.64.0/")


@pytest.mark.parametrize("probe_id", CANONICAL_IDS)
def test_all_environment_facts_are_explicit_user_reports(suite, probe_id):
    facts = active_facts(probe_by_id(suite, probe_id))
    expected = (
        ("1.27.2", "3.10.14", "Ubuntu 22.04", "Firefox 128")
        if probe_id == "fresh-known-historical-signature-uncovered"
        else ("1.64.0", "3.13.0", "Ubuntu 24.04", "Firefox 143")
    )
    names = ("streamlit_version", "python_version", "operating_system", "browser")
    assert tuple(facts[name].value for name in names) == expected
    assert all(facts[name].provenance_kind == "user" for name in names)


@pytest.mark.parametrize(
    ("probe_id", "name", "old_value", "current_value"),
    [
        ("fresh-corrected-version-submit-api", "streamlit_version", "1.27.2", "1.64.0"),
        (
            "fresh-intent-correction-deliberate-old-new-pair",
            "reported_callback_intent",
            "Record only the freshly selected value",
            "Capture the widget-construction value as the old component and read the current "
            "keyed value inside the callback for an old/new pair",
        ),
    ],
)
def test_corrections_preserve_one_active_replacement_and_superseded_history(
    suite, probe_id, name, old_value, current_value
):
    probe = probe_by_id(suite, probe_id)
    facts = [fact for fact in probe.case_state.facts if fact.name == name]
    assert probe.case_state.case_revision == 1
    assert [(fact.value, fact.status, fact.turn_id) for fact in facts] == [
        (old_value, "superseded", "synthetic-v7-prior"),
        (current_value, "active", "synthetic-v7-correction"),
    ]
    assert facts[0].source_ref != facts[1].source_ref
    assert all(fact.provenance_kind == "user" for fact in facts)
    other_revisions = [
        item.case_state.case_revision
        for item in suite.cases
        if item.id
        not in {
            "fresh-corrected-version-submit-api",
            "fresh-intent-correction-deliberate-old-new-pair",
        }
    ]
    assert other_revisions == [0, 0, 0, 0]


def test_unrun_working_failing_and_positive_controls_keep_the_authored_report_scopes(suite):
    draft = probe_by_id(suite, "fresh-corrected-version-submit-api")
    assert active_facts(draft)["reported_execution_status"].value == (
        "This form draft has not been executed"
    )
    assert len(draft.case_state.checks_performed) == 1
    assert "observing version 1.64.0" in draft.case_state.checks_performed[0]

    integration = probe_by_id(suite, "fresh-working-fragment-failing-options-path")
    facts = active_facts(integration)
    assert facts["reported_reduced_example_result"].value == (
        'The supplied isolated fixed-options fragment with default=["Bristol"] works'
    )
    assert facts["reported_full_app_transition"].value == (
        "Changing Region from West to East in the full app leaves Ports empty"
    )
    assert facts["reported_helper_logging_status"].value == (
        "The helper return values have not been logged"
    )
    assert set(integration.case_state.unknowns) == {
        "options_builder_implementation",
        "default_builder_implementation",
        "minimal_failing_integration",
    }
    assert len(integration.case_state.checks_performed) == 2

    mismatch = active_facts(probe_by_id(suite, "fresh-key-read-reported-three-way-mismatch"))
    assert mismatch["reported_frontend_value"].value == "Bergen"
    assert mismatch["reported_backend_session_state_value"].value == "Quito"
    assert mismatch["reported_callback_value"].value == "Quito"
    assert mismatch["reported_version_comparison_status"].value == (
        "Other Streamlit versions have not been tested"
    )

    old_new = probe_by_id(suite, "fresh-intent-correction-deliberate-old-new-pair")
    assert old_new.case_state.checks_performed == ()
    assert active_facts(old_new)["reported_failure_status"].value == (
        "No failure is being reported"
    )
    assert active_facts(old_new)["reported_expected_comparison"].value == (
        'Starting at Basic and selecting Pro should give ("Basic", "Pro")'
    )

    historical = probe_by_id(suite, "fresh-known-historical-signature-uncovered")
    assert "streamlit_version" not in historical.case_state.unknowns
    assert set(historical.case_state.unknowns) == {
        "historical_api_signature",
        "historical_source_coverage",
    }
    assert active_facts(historical)["reported_callable_inspection_status"].value == (
        "The installed form_submit_button callable has not been inspected"
    )

    display = active_facts(probe_by_id(suite, "fresh-display-observation-claim-span-control"))
    assert display["reported_saved_value_observation"].value == (
        "Saved announcement still shows Lime after the subsequent Show details interaction"
    )
    assert display["reported_value_status"].value == "No wrong callback value is reported"


class CapturePolicyMessages:
    """Fake reasoning records the actual caller path; it does not judge an answer."""

    def __init__(self, policy):
        self.policy = policy
        self.messages = []
        self.contexts = []

    def analyze(self, case, user_message, evidence, *, context: ReasoningContext):
        self.contexts.append(context)
        self.messages.append(
            build_messages(case, user_message, evidence, policy=self.policy, context=context)
        )
        return AnalysisResult(
            decision="escalate",
            user_draft="Offline caller-payload capture for review.",
            maintainer_summary="Only checks fixture encoding and control-plane boundaries.",
            rationale="A scripted capture verifies no model quality or technical conclusion.",
        )


@pytest.mark.parametrize("policy", POLICIES)
@pytest.mark.parametrize("probe_id", CANONICAL_IDS)
def test_actual_caller_path_excludes_private_labels_catalogs_and_review_metadata(
    suite, policy, probe_id
):
    probe = probe_by_id(suite, probe_id)
    labeled = probe.model_copy(
        update={
            "description": PRIVATE_MARKERS[0],
            "expectations": ProbeExpectations(
                acceptable_decisions=("answer",),
                required_terms=(PRIVATE_MARKERS[1],),
                forbidden_terms=(PRIVATE_MARKERS[2],),
                allowed_missing_info=(PRIVATE_MARKERS[3],),
                require_evidence=True,
                require_uncertainty=True,
                forbid_repeated_checks=True,
            ),
            "reviewer_notes": (PRIVATE_MARKERS[4],),
        }
    )
    capture = CapturePolicyMessages(policy)
    observed = run_probe(
        labeled,
        capture,
        snapshot_id=suite.snapshot_id,
        run_id=f"offline:frozen-input:{probe_id}:{policy}",
        proposal_requirements=None,
        proposal_checks=False,
    )
    assert observed["automatic"]["accepted"] is True
    assert observed["automatic"]["allowed_final_decision"] is False
    assert len(capture.messages) == len(capture.contexts) == 1
    context = capture.contexts[0]
    assert context.proposal_requirements is None
    messages = capture.messages[0]
    serialized = json.dumps(messages)
    assert all(marker not in serialized for marker in PRIVATE_MARKERS)
    assert all(question not in serialized for question in probe.reviewer_notes)
    assert all(
        name not in serialized
        for name in (
            "proposal_requirements",
            "question_targets",
            "require_fresh_widget_value",
            "acceptable_decisions",
            "required_terms",
            "forbidden_terms",
            "reviewer_notes",
        )
    )
    payload = json.loads(messages[1]["content"])
    expected_keys = {
        "case",
        "user_message",
        "evidence",
        "response_schema",
        "workflow",
        "decision_requirements",
    }
    if policy == "fidelity_rules":
        expected_keys.add("fidelity_view")
    assert set(payload) == expected_keys
    assert payload["case"] == probe.case_state.model_dump(mode="json")
    assert payload["user_message"] == probe.user_message
    assert payload["evidence"] == probe.bundles[0].model_dump(mode="json")
    assert payload["response_schema"] == AnalysisResult.model_json_schema()
    assert "available" not in payload["decision_requirements"]["ask"]
    assert payload["workflow"] == {
        "remaining_model_attempts": context.remaining_model_attempts,
        "remaining_retrieval_rounds": context.remaining_retrieval_rounds,
        "can_refine": context.can_refine,
        "query_limit": context.query_limit,
    }
    if policy == "fidelity_rules":
        view = payload["fidelity_view"]
        assert view["recorded_checks"] == list(probe.case_state.checks_performed)
        assert view["unknowns"] == list(probe.case_state.unknowns)
        assert view["evidence_observations"] == []
        assert view["active_user_facts"] == [
            fact.model_dump(mode="json")
            for fact in probe.case_state.facts
            if fact.status == "active"
        ]
        assert view["superseded_user_facts"] == [
            fact.model_dump(mode="json")
            for fact in probe.case_state.facts
            if fact.status == "superseded"
        ]


def test_registered_protocol_pins_the_same_canonical_inputs_when_present(suite):
    protocol_path = FIXTURES / "protocol-fidelity-v7.json"
    if not protocol_path.exists():
        pytest.skip("Protocol registration has not yet been authored")
    registered, plan = validate_fidelity_inputs(protocol_path)
    assert registered == suite
    assert plan.suite_sha256 == INPUT_SHA256
    assert plan.case_count == 6
    assert plan.replicates == 2
    assert plan.policies == POLICIES
    assert plan.proposal_checks is False
    assert len(plan.schedule) == 24
