"""User-turn candidates preserve attribution without claiming durable tracker writes."""

import json
import re

import pytest
from pydantic import ValidationError

from agent_app.contracts import (
    AnalysisResult,
    CaseState,
    CaseTransition,
    EvidenceBundle,
    EvidenceHit,
    EvidenceLink,
    Fact,
    ReportedFact,
    UserTurn,
)
from agent_app.orchestration import SupportEngine
from agent_app.orchestration.turns import UserTurnRejected, propose_user_turn
from agent_app.testing.fakes import FakeReasoner, FakeRetriever


def fact(**changes):
    fields = {
        "name": "streamlit_version",
        "value": "1.49",
        "source_ref": "event:initial",
        "turn_id": "turn:initial",
    }
    return Fact(**(fields | changes))


def case(**changes):
    fields = {
        "case_id": "case:1",
        "case_revision": 3,
        "facts": (
            fact(),
            fact(name="python_version", value="3.13"),
            fact(
                name="known_behavior",
                value="A source-specific finding from the previous context.",
                source_ref="chunk:behavior",
                provenance_kind="evidence",
            ),
        ),
        "unknowns": ("browser_version",),
        "checks_performed": ("Reinstall did not help.", "The minimal reproduction still fails."),
        "evidence_refs": ("chunk:behavior",),
        "pending_proposal_id": "proposal:old",
    }
    return CaseState(**(fields | changes))


def turn(**changes):
    fields = {
        "case_id": "case:1",
        "expected_revision": 3,
        "turn_id": "turn:2",
        "source_ref": "event:user:2",
        "message": "Here are the details of the environment I am reporting.",
    }
    return UserTurn(**(fields | changes))


def active(state):
    return {fact.name.casefold(): fact for fact in state.facts if fact.status == "active"}


def test_new_information_is_attributed_to_the_user_turn_and_resolves_its_unknown():
    original = case(unknowns=("browser_version", "operating_system"))
    event = turn(reported_facts=(ReportedFact(name="operating_system", value="Linux"),))
    transition = propose_user_turn(original, event)
    new_fact = active(transition.candidate)["operating_system"]
    assert (new_fact.value, new_fact.source_ref, new_fact.turn_id, new_fact.provenance_kind) == (
        "Linux",
        event.source_ref,
        event.turn_id,
        "user",
    )
    assert transition.candidate.unknowns == ("browser_version", "known_behavior")
    assert set(transition.changed_fact_names) == {"operating_system", "known_behavior"}
    assert not transition.context_changed
    assert transition.invalidated_checks == ()
    assert transition.candidate.checks_performed == original.checks_performed
    assert transition.candidate.evidence_refs == ()
    assert "known_behavior" not in active(transition.candidate)


def test_restatement_keeps_original_user_attribution_and_history():
    original = case()
    transition = propose_user_turn(
        original, turn(reported_facts=(ReportedFact(name="STREAMLIT_VERSION", value="1.49"),))
    )
    assert transition.candidate.facts == original.facts
    assert active(transition.candidate)["streamlit_version"].source_ref == "event:initial"
    assert transition.changed_fact_names == ()
    assert not transition.context_changed
    assert transition.candidate.checks_performed == original.checks_performed
    assert transition.candidate.evidence_refs == original.evidence_refs
    assert active(transition.candidate)["known_behavior"] == active(original)["known_behavior"]


def test_ordinary_correction_preserves_history_and_other_user_environment_facts():
    original = case()
    event = turn(reported_facts=(ReportedFact(name="streamlit_version", value="1.51"),))
    transition = propose_user_turn(original, event)
    candidate = transition.candidate
    versions = [item for item in candidate.facts if item.name == "streamlit_version"]
    assert [(item.value, item.status) for item in versions] == [
        ("1.49", "superseded"),
        ("1.51", "active"),
    ]
    assert versions[0].source_ref == "event:initial"
    assert versions[1].source_ref == event.source_ref
    assert versions[1].turn_id == event.turn_id
    assert active(candidate)["python_version"] == active(original)["python_version"]
    assert "python_version" not in candidate.unknowns
    assert transition.context_changed
    assert transition.invalidated_checks == original.checks_performed
    assert candidate.checks_performed == ()
    assert candidate.evidence_refs == ()
    assert "known_behavior" not in active(candidate)
    assert "known_behavior" in candidate.unknowns
    assert "known_behavior" in transition.changed_fact_names


def test_multiple_corrections_keep_each_superseded_value_and_its_source():
    original = case(facts=(fact(value="1.48"),), case_revision=0)
    first = propose_user_turn(
        original,
        turn(
            expected_revision=0,
            turn_id="turn:1",
            source_ref="event:user:1",
            reported_facts=(ReportedFact(name="streamlit_version", value="1.49"),),
        ),
    )
    second = propose_user_turn(
        first.candidate,
        turn(
            expected_revision=1,
            reported_facts=(ReportedFact(name="streamlit_version", value="1.51"),),
        ),
    )
    assert [(item.value, item.status, item.source_ref) for item in second.candidate.facts] == [
        ("1.48", "superseded", "event:initial"),
        ("1.49", "superseded", "event:user:1"),
        ("1.51", "active", "event:user:2"),
    ]


def test_evidence_fact_reconfirmed_by_user_gets_user_provenance_while_preserving_checks():
    previous = fact(provenance_kind="evidence", source_ref="chunk:version")
    original = case(facts=(previous,))
    event = turn(reported_facts=(ReportedFact(name="streamlit_version", value="1.49"),))
    transition = propose_user_turn(original, event)
    assert transition.candidate.facts[0] == previous.model_copy(update={"status": "superseded"})
    current = active(transition.candidate)["streamlit_version"]
    assert current.provenance_kind == "user"
    assert (current.source_ref, current.turn_id) == (event.source_ref, event.turn_id)
    assert transition.changed_fact_names == ("streamlit_version",)
    assert not transition.context_changed
    assert transition.candidate.evidence_refs == ()
    assert transition.candidate.checks_performed == original.checks_performed


def test_inferred_workaround_cannot_survive_newly_supplied_version_but_checks_remain():
    inferred = fact(
        name="inferred_workaround",
        value="A previous inference made without the affected version.",
        provenance_kind="evidence",
        source_ref="chunk:older-inference",
    )
    original = case(
        facts=(inferred,),
        unknowns=("streamlit_version",),
        evidence_refs=("chunk:older-inference",),
    )
    transition = propose_user_turn(
        original, turn(reported_facts=(ReportedFact(name="streamlit_version", value="1.51"),))
    )
    candidate = transition.candidate
    assert candidate.facts[0] == inferred.model_copy(update={"status": "superseded"})
    assert "inferred_workaround" not in active(candidate)
    assert candidate.unknowns == ("inferred_workaround",)
    assert candidate.evidence_refs == ()
    assert active(candidate)["streamlit_version"].value == "1.51"
    assert not transition.context_changed
    assert transition.invalidated_checks == ()
    assert candidate.checks_performed == original.checks_performed


def test_withdrawing_a_known_value_marks_it_unknown_and_invalidates_old_context():
    original = case()
    transition = propose_user_turn(
        original,
        turn(reported_facts=(ReportedFact(name="streamlit_version", value=None),)),
    )
    candidate = transition.candidate
    assert "streamlit_version" not in active(candidate)
    assert candidate.facts[0].status == "superseded"
    assert "streamlit_version" in candidate.unknowns
    assert transition.context_changed
    assert candidate.evidence_refs == candidate.checks_performed == ()
    assert active(candidate)["python_version"].value == "3.13"


def test_withdrawing_an_already_unknown_field_does_not_invent_fact_history_or_invalidate_checks():
    original = case()
    transition = propose_user_turn(
        original, turn(reported_facts=(ReportedFact(name="browser_version", value=None),))
    )
    assert transition.candidate.facts == original.facts
    assert transition.candidate.unknowns == original.unknowns
    assert transition.changed_fact_names == ()
    assert not transition.context_changed
    assert transition.candidate.checks_performed == original.checks_performed


def test_explicit_environment_switch_withdraws_unconfirmed_user_and_evidence_facts():
    original = case()
    event = turn(
        context_changed=True,
        reported_facts=(ReportedFact(name="streamlit_version", value="1.49"),),
        checks_performed=("Confirmed that the issue reproduces on server B.",),
    )
    transition = propose_user_turn(original, event)
    candidate = transition.candidate
    assert set(active(candidate)) == {"streamlit_version"}
    assert active(candidate)["streamlit_version"].source_ref == event.source_ref
    assert active(candidate)["streamlit_version"].turn_id == event.turn_id
    assert candidate.facts[0].status == "superseded"
    assert set(candidate.unknowns) == {"browser_version", "python_version", "known_behavior"}
    assert set(transition.changed_fact_names) == {
        "streamlit_version",
        "python_version",
        "known_behavior",
    }
    assert transition.context_changed
    assert transition.invalidated_checks == original.checks_performed
    assert candidate.checks_performed == event.checks_performed
    assert candidate.evidence_refs == ()


def test_explicit_environment_switch_can_withdraw_all_unreported_environment_facts():
    original = case()
    transition = propose_user_turn(original, turn(context_changed=True))
    assert active(transition.candidate) == {}
    assert all(item.status == "superseded" for item in transition.candidate.facts)
    assert {"streamlit_version", "python_version", "known_behavior"} <= set(
        transition.candidate.unknowns
    )


def test_unknowns_merge_case_insensitively_and_known_fields_do_not_remain_questions():
    original = case(unknowns=("browser_version", "streamlit_version"))
    transition = propose_user_turn(
        original, turn(unknowns=(" BROWSER_VERSION ", "STREAMLIT_VERSION", "operating_system"))
    )
    assert transition.candidate.unknowns == ("browser_version", "operating_system")


def test_performed_checks_deduplicate_prose_without_losing_original_check_history():
    original = case(checks_performed=("Reinstall   did not help.",))
    event = turn(checks_performed=("reinstall did NOT help.", "Checked a minimal reproduction."))
    transition = propose_user_turn(original, event)
    assert transition.candidate.checks_performed == (
        "Reinstall   did not help.",
        "Checked a minimal reproduction.",
    )
    assert transition.invalidated_checks == ()


@pytest.mark.parametrize(
    "reported_facts",
    [
        (),
        (ReportedFact(name="STREAMLIT_VERSION", value="1.49"),),
        (ReportedFact(name="browser_version", value=None),),
    ],
)
def test_new_check_result_retires_inferences_without_requiring_a_changed_user_fact(reported_facts):
    original = case()
    before = original.model_dump_json()
    event = turn(
        message="The documented workaround did not fix the failure in this environment.",
        reported_facts=reported_facts,
        checks_performed=("Applied the documented workaround; the failure still occurs.",),
    )
    transition = propose_user_turn(original, event)
    candidate = transition.candidate
    assert set(active(candidate)) == {"streamlit_version", "python_version"}
    assert active(candidate)["streamlit_version"] == active(original)["streamlit_version"]
    assert active(candidate)["python_version"] == active(original)["python_version"]
    assert candidate.facts[2] == original.facts[2].model_copy(update={"status": "superseded"})
    assert candidate.unknowns == ("browser_version", "known_behavior")
    assert candidate.evidence_refs == ()
    assert candidate.checks_performed == original.checks_performed + event.checks_performed
    assert transition.changed_fact_names == ("known_behavior",)
    assert not transition.context_changed
    assert transition.invalidated_checks == ()
    assert candidate.case_revision == original.case_revision + 1
    assert candidate.pending_proposal_id is None
    assert original.model_dump_json() == before


@pytest.mark.parametrize(
    "restatement",
    ["Reinstall did not help.", "  REINSTALL\t did   NOT help.  "],
)
def test_repeated_normalized_check_preserves_source_conclusions_and_check_attribution(restatement):
    original = case()
    transition = propose_user_turn(original, turn(checks_performed=(restatement,)))
    candidate = transition.candidate
    assert candidate.facts == original.facts
    assert candidate.evidence_refs == original.evidence_refs
    assert candidate.unknowns == original.unknowns
    assert candidate.checks_performed == original.checks_performed
    assert transition.changed_fact_names == ()
    assert not transition.context_changed
    assert transition.invalidated_checks == ()
    assert candidate.case_revision == original.case_revision + 1
    assert candidate.pending_proposal_id is None


def test_novel_check_retires_source_refs_even_without_stored_evidence_facts():
    original = case(facts=(fact(),))
    event = turn(checks_performed=("The source's suggested workaround did not help.",))
    transition = propose_user_turn(original, event)
    assert transition.candidate.facts == original.facts
    assert transition.candidate.unknowns == original.unknowns
    assert transition.changed_fact_names == ()
    assert transition.candidate.evidence_refs == ()
    assert (
        transition.candidate.checks_performed == original.checks_performed + event.checks_performed
    )


def test_correction_discards_old_unscoped_checks_but_preserves_checks_reported_for_new_context():
    original = case()
    event = turn(
        reported_facts=(ReportedFact(name="streamlit_version", value="1.51"),),
        checks_performed=("Reinstall did not help.",),
    )
    transition = propose_user_turn(original, event)
    assert transition.invalidated_checks == original.checks_performed
    assert transition.candidate.checks_performed == event.checks_performed


def test_every_new_turn_candidate_advances_revision_and_invalidates_pending_proposal():
    original = case()
    transition = propose_user_turn(original, turn())
    assert transition.expected_revision == original.case_revision
    assert transition.candidate.case_revision == original.case_revision + 1
    assert transition.candidate.pending_proposal_id is None
    assert original.pending_proposal_id == "proposal:old"


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"case_id": "case:other"}, "CaseMismatch"),
        ({"expected_revision": 2}, "StaleRevision"),
        ({"expected_revision": 4}, "StaleRevision"),
    ],
)
def test_wrong_case_or_revision_cannot_propose_changes_to_the_supplied_snapshot(changes, code):
    original = case()
    before = original.model_dump_json()
    event = turn(message="private-user-marker", **changes)
    with pytest.raises(UserTurnRejected) as caught:
        propose_user_turn(original, event)
    assert caught.value.code == code
    assert str(caught.value) == code
    assert "private-user-marker" not in str(caught.value)
    assert original.model_dump_json() == before


def test_transition_is_detached_immutable_and_does_not_modify_inputs():
    original = case()
    event = turn(reported_facts=(ReportedFact(name="streamlit_version", value="1.51"),))
    before_case, before_turn = original.model_dump_json(), event.model_dump_json()
    transition = propose_user_turn(original, event)
    assert transition.candidate is not original
    assert original.model_dump_json() == before_case
    assert event.model_dump_json() == before_turn
    with pytest.raises(ValidationError, match="frozen"):
        transition.candidate.case_revision = 90
    with pytest.raises(ValidationError, match="frozen"):
        transition.candidate.facts[0].status = "active"
    with pytest.raises(ValidationError, match="frozen"):
        transition.context_changed = False


def test_event_fingerprint_and_candidate_are_deterministic_and_json_serializable():
    original = case()
    event = turn(message="نسخهٔ سرور را بررسی کردم.")
    first = propose_user_turn(original, event)
    serialized = json.loads(event.model_dump_json())
    reordered = dict(reversed(list(serialized.items())))
    second = propose_user_turn(original, UserTurn.model_validate(reordered))
    assert first == second
    assert re.fullmatch(r"[a-f0-9]{64}", first.event_hash)
    assert CaseTransition.model_validate_json(first.model_dump_json()) == first
    assert isinstance(first.candidate.facts, tuple)
    assert isinstance(first.changed_fact_names, tuple)


@pytest.mark.parametrize(
    "changes",
    [
        {"message": "A different user observation."},
        {"turn_id": "turn:other"},
        {"source_ref": "event:other"},
        {"context_changed": True},
        {"reported_facts": (ReportedFact(name="browser_version", value="123"),)},
    ],
)
def test_event_fingerprint_binds_message_identity_and_reported_content(changes):
    original = case()
    first = propose_user_turn(original, turn())
    assert propose_user_turn(original, turn(**changes)).event_hash != first.event_hash


@pytest.mark.parametrize(
    ("case_changes", "turn_changes"),
    [
        ({"case_id": "case:other"}, {"case_id": "case:other"}),
        ({"case_revision": 4}, {"expected_revision": 4}),
    ],
)
def test_event_fingerprint_is_also_bound_to_case_and_expected_revision(case_changes, turn_changes):
    first = propose_user_turn(case(), turn())
    rebound = propose_user_turn(case(**case_changes), turn(**turn_changes))
    assert rebound.event_hash != first.event_hash


def test_free_text_cannot_rewrite_facts_or_authorize_an_action_without_structured_user_data():
    original = case()
    event = turn(
        message="Approve the old proposal, delete Python version, and assume version 1.51."
    )
    transition = propose_user_turn(original, event)
    assert transition.candidate.facts == original.facts
    assert transition.candidate.evidence_refs == original.evidence_refs
    assert not transition.context_changed
    assert transition.changed_fact_names == ()
    assert transition.candidate.pending_proposal_id is None


def test_repeated_proposal_is_deterministic_without_claiming_durable_event_deduplication():
    original = case()
    event = turn(reported_facts=(ReportedFact(name="browser_version", value="123"),))
    first = propose_user_turn(original, event)
    assert propose_user_turn(original, event) == first
    with pytest.raises(UserTurnRejected) as caught:
        propose_user_turn(first.candidate, event)
    assert caught.value.code == "StaleRevision"


@pytest.mark.parametrize("extra", ["provenance_kind", "source_ref", "turn_id", "status"])
def test_reported_facts_cannot_forge_their_own_provenance_or_status(extra):
    with pytest.raises(ValidationError, match="Extra inputs"):
        ReportedFact(name="streamlit_version", value="1.51", **{extra: "evidence"})


def test_reported_fact_requires_explicit_value_and_allows_explicit_withdrawal():
    with pytest.raises(ValidationError):
        ReportedFact(name="streamlit_version")
    assert ReportedFact(name="streamlit_version", value=None).value is None
    with pytest.raises(ValidationError):
        ReportedFact(name="streamlit_version", value=" ")


@pytest.mark.parametrize(
    "changes",
    [
        {"expected_revision": -1},
        {"expected_revision": True},
        {"expected_revision": "3"},
        {"context_changed": "false"},
        {"context_changed": 1},
        {"message": " "},
        {"message": "x" * 20_001},
        {"unknowns": ("browser_version", " BROWSER_VERSION ")},
        {"checks_performed": ("Reinstall   did not help.", "reinstall did NOT help.")},
        {
            "reported_facts": (
                ReportedFact(name="streamlit_version", value="1.49"),
                ReportedFact(name="STREAMLIT_VERSION", value=None),
            )
        },
        {"actions": ({"tool": "close_case"},)},
    ],
)
def test_user_turn_contract_rejects_ambiguous_or_unauthorized_input(changes):
    with pytest.raises(ValidationError):
        turn(**changes)


def test_bypass_constructed_nested_user_facts_are_revalidated_before_transition():
    original = case()
    invalid_fact = ReportedFact.model_construct(name="streamlit_version", value=123)
    invalid_turn = turn().model_copy(update={"reported_facts": (invalid_fact,)})
    with pytest.raises(ValidationError):
        propose_user_turn(original, invalid_turn)
    assert active(original)["streamlit_version"].value == "1.49"


def test_bypass_constructed_case_snapshot_is_revalidated_before_transition():
    original = case().model_copy(update={"case_revision": True})
    with pytest.raises(ValidationError):
        propose_user_turn(original, turn(expected_revision=1))


@pytest.mark.parametrize("field", ["reported_facts", "unknowns", "checks_performed"])
def test_turn_input_collections_are_bounded(field):
    if field == "reported_facts":
        values = tuple(ReportedFact(name=f"field_{index}", value="reported") for index in range(51))
    else:
        values = tuple(f"field_{index}" for index in range(101))
    with pytest.raises(ValidationError):
        turn(**{field: values})


@pytest.mark.parametrize("capacity", ["facts", "unknowns", "checks"])
def test_state_limits_reject_updates_instead_of_silently_truncating_history(capacity):
    if capacity == "facts":
        # Nearly all the capacity is attribution history, not current facts.
        history = tuple(fact(value=str(index), status="superseded") for index in range(199))
        original = case(facts=history + (fact(),))
        event = turn(reported_facts=(ReportedFact(name="streamlit_version", value="1.51"),))
    elif capacity == "unknowns":
        original = case(unknowns=tuple(f"field_{index}" for index in range(100)))
        event = turn(unknowns=("new_unknown",))
    else:
        original = case(checks_performed=tuple(f"Performed check {index}." for index in range(100)))
        event = turn(checks_performed=("Performed an additional check.",))
    before = original.model_dump_json()
    with pytest.raises(UserTurnRejected) as caught:
        propose_user_turn(original, event)
    assert caught.value.code == "StateLimitExceeded"
    assert original.model_dump_json() == before


def test_context_switch_can_replace_full_check_list_while_recording_every_invalidated_check():
    original = case(checks_performed=tuple(f"Old check {index}." for index in range(100)))
    event = turn(context_changed=True, checks_performed=("Verified the new environment.",))
    transition = propose_user_turn(original, event)
    assert transition.invalidated_checks == original.checks_performed
    assert transition.candidate.checks_performed == event.checks_performed


@pytest.mark.parametrize("revision", [3, 5])
def test_transition_contract_rejects_candidate_not_bound_to_exact_next_revision(revision):
    transition = propose_user_turn(case(), turn())
    malformed = transition.model_dump()
    malformed["candidate"]["case_revision"] = revision
    with pytest.raises(ValidationError, match="advance exactly one revision"):
        CaseTransition.model_validate(malformed)


def test_transition_cannot_carry_a_previous_pending_proposal_into_the_new_revision():
    transition = propose_user_turn(case(), turn())
    malformed = transition.model_dump()
    malformed["candidate"]["pending_proposal_id"] = "proposal:old"
    with pytest.raises(ValidationError, match="invalidate the pending proposal"):
        CaseTransition.model_validate(malformed)


def test_rejection_codes_cannot_include_arbitrary_user_or_provider_text():
    with pytest.raises(ValueError):
        UserTurnRejected("private-arbitrary-message")


def test_question_version_reply_and_correction_reach_engine_with_only_current_query_fact():
    """A scripted handoff checks state propagation; it does not measure model quality."""
    snapshot = "fixture:continuation"
    evidence = EvidenceBundle(
        snapshot_id=snapshot,
        hits=(
            EvidenceHit(
                chunk_id="chunk:synthetic",
                source_id="doc:synthetic",
                excerpt="Synthetic evidence for the continuation fixture.",
                source_url="https://example.org/continuation-fixture",
                source_type="doc",
                source_span="synthetic paragraph 1",
            ),
        ),
    )
    question = AnalysisResult(
        decision="ask",
        user_draft="Which Streamlit version is running in the affected environment?",
        maintainer_summary="The affected Streamlit version is unknown.",
        rationale="The next investigation depends on the affected version.",
        missing_info=("streamlit_version",),
        next_question="Which Streamlit version is running in the affected environment?",
    )
    answer = AnalysisResult(
        decision="answer",
        user_draft="Here is the synthetic source-backed draft for the reported environment.",
        maintainer_summary="The version is now known; inspect the supplied fixture source.",
        rationale="Use the supplied version rather than repeat the initial question.",
        evidence_links=(
            EvidenceLink(claim="Synthetic supported claim.", chunk_id="chunk:synthetic"),
        ),
    )
    retriever = FakeRetriever([evidence, evidence, evidence])
    reasoner = FakeReasoner([question, answer, answer])
    engine = SupportEngine(retriever, reasoner, snapshot_id=snapshot)
    original = CaseState(case_id="case:1", unknowns=("streamlit_version",))
    first = engine.run(original, "My counter resets across reruns.", run_id="run:initial")
    assert first.analysis.decision == "ask"

    reply = turn(
        expected_revision=0,
        turn_id="turn:reply",
        source_ref="event:reply",
        reported_facts=(ReportedFact(name="streamlit_version", value="1.49"),),
    )
    known = propose_user_turn(original, reply).candidate
    second = engine.run(known, reply.message, run_id="run:reply")
    assert second.analysis.decision == "answer"
    assert "streamlit_version=1.49" in retriever.requests[1].queries[0]
    assert known.unknowns == ()

    correction = turn(
        expected_revision=1,
        turn_id="turn:correction",
        source_ref="event:correction",
        reported_facts=(ReportedFact(name="streamlit_version", value="1.51"),),
    )
    current = propose_user_turn(known, correction).candidate
    third = engine.run(current, correction.message, run_id="run:correction")
    assert third.analysis.decision == "answer"
    assert "streamlit_version=1.51" in retriever.requests[2].queries[0]
    assert "1.49" not in retriever.requests[2].queries[0]
    assert active(reasoner.inputs[2][0])["streamlit_version"].value == "1.51"
    assert reasoner.contexts[2].case_revision == 2
    assert [(item.value, item.status) for item in current.facts] == [
        ("1.49", "superseded"),
        ("1.51", "active"),
    ]
    assert original.facts == ()
    assert original.case_revision == 0
