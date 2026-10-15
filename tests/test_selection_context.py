"""Bound lexical hints: authored controls, never semantic or model-quality scores."""

import hashlib
import json
import re
from dataclasses import FrozenInstanceError, asdict
from pathlib import Path

import pytest

from agent_app.contracts import (
    CaseState,
    ConversationEntry,
    EvidenceBundle,
    EvidenceHit,
    Fact,
    GroundedRequest,
    ReasoningContext,
    TurnConversation,
)
from agent_app.orchestration.conversation import build_reasoning_message
from agent_app.orchestration.retrieval_context import build_current_query
from agent_app.reasoning.claim_plan import build_claim_messages, build_claim_request
from agent_app.reasoning.evidence_selection import (
    inspect_claim_selection,
    rank_evidence_units,
    suggest_evidence_units,
)
from agent_app.reasoning.grounding import make_grounded_request
from agent_app.reasoning.selection_context import (
    build_evidence_query_context,
    validate_evidence_query_context,
)

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / "experiments/core_selection_context_v1"
SCENARIOS = json.loads((PACKET / "scenarios-v1.json").read_bytes())["scenarios"]
BASELINE = json.loads((PACKET / "legacy-baseline-v1.json").read_bytes())
SNAPSHOTS = json.loads((ROOT / "experiments/core_broader_dev_v1/snapshots-v1.json").read_bytes())[
    "snapshots"
]


def digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def scenario(name):
    row = next(item for item in SCENARIOS if item["id"] == name)
    case = CaseState.model_validate(row["case"])
    conversation = TurnConversation.model_validate(row["conversation"])
    request = build_claim_request(
        make_grounded_request(
            case,
            build_reasoning_message(conversation),
            EvidenceBundle.model_validate(row["evidence"]),
        ),
        block_mode="sections",
    )
    return request, case, conversation


def rebuild(request, *, case=None, conversation=None, evidence=None, mode=None):
    grounded = request.grounded
    return build_claim_request(
        make_grounded_request(
            case if case is not None else grounded.case,
            build_reasoning_message(conversation)
            if conversation is not None
            else grounded.user_message,
            evidence if evidence is not None else grounded.evidence,
            gaps=grounded.gaps,
            conflict_groups=grounded.conflict_groups,
        ),
        block_mode=mode or request.block_mode,
    )


def authored_plan(request):
    return {
        "context_sha256": request.context_sha256,
        "decision": "escalate",
        "passages": [],
        "user_facts": [],
        "question_name": None,
        "retrieval_queries": [],
    }


def scores(request, context=None):
    return {
        hint.source_index: hint.overlap
        for hint in rank_evidence_units(request, query_context=context)
    }


def safe_rejection(operation):
    with pytest.raises(ValueError) as caught:
        operation()
    assert str(caught.value) == "grounded_context_mismatch"


LEGACY_ROWS = [
    *(("neutral", row) for row in BASELINE["authored_neutral_results"]),
    *(("prior", row) for row in BASELINE["prior_default_results"]),
]


@pytest.mark.parametrize("kind,row", LEGACY_ROWS, ids=[row["id"] for _, row in LEGACY_ROWS])
def test_all_twenty_four_preregistered_legacy_outputs_keep_exact_digests(kind, row):
    if kind == "neutral":
        request, _, _ = scenario(row["id"])
    else:
        frozen = next(item for item in SNAPSHOTS if item["id"] == row["id"])
        request = build_claim_request(GroundedRequest.model_validate(frozen["catalog_request"]))
    assert request.context_sha256 == row["request_context_sha256"]
    assert (
        digest([asdict(hint) for hint in rank_evidence_units(request)])
        == row["ranked_units_sha256"]
    )
    assert digest(asdict(suggest_evidence_units(request))) == row["shortlist_sha256"]
    assert (
        digest(inspect_claim_selection(request, row["authored_inspection_plan"]))
        == row["inspection_sha256"]
    )
    assert rank_evidence_units(request, query_context=None) == rank_evidence_units(request)
    assert suggest_evidence_units(request, query_context=None) == suggest_evidence_units(request)
    assert inspect_claim_selection(
        request, row["authored_inspection_plan"], query_context=None
    ) == inspect_claim_selection(request, row["authored_inspection_plan"])


def test_bound_current_topic_retains_signal_without_rewriting_contaminated_history():
    request, case, conversation = scenario("retired-topic-correction")
    context = build_evidence_query_context(request, case, conversation)
    terms = set(re.findall(r"[^\W_]+", context.current_query.casefold()))
    assert {"document", "export"}.isdisjoint(terms)
    assert {"connection", "pooling"} <= terms
    legacy, current = scores(request), scores(request, context)
    assert legacy[0] > legacy[1]  # Original observable failure remains in the None arm.
    assert current[1] > 0
    assert "document export" in request.grounded.user_message.casefold()
    shortlist = suggest_evidence_units(request, query_context=context)
    assert shortlist.semantic_support is None and shortlist.human_review_required


def test_reactivated_A_is_not_permanently_blacklisted_and_version_reply_keeps_topic():
    request, case, conversation = scenario("topic-a-b-a")
    context = build_evidence_query_context(request, case, conversation)
    terms = set(re.findall(r"[^\W_]+", context.current_query.casefold()))
    assert {"document", "export"} <= terms
    assert {"cache", "eviction"}.isdisjoint(terms)
    current = scores(request, context)
    assert current[0] > 0
    request, case, conversation = scenario("version-only-followup")
    context = build_evidence_query_context(request, case, conversation)
    assert conversation.latest_message == "1.49.0"
    shortlist = suggest_evidence_units(request, query_context=context)
    assert (0, 0) in shortlist.passages and (2, 0) in shortlist.historical
    assert (2, 0) not in shortlist.passages


@pytest.mark.parametrize("name", ["assistant-evidence-exclusion", "fact-name-metadata-poison"])
def test_assistant_evidence_rows_and_fact_or_source_names_do_not_supply_query_authority(name):
    request, case, conversation = scenario(name)
    context = build_evidence_query_context(request, case, conversation)
    current = scores(request, context)
    assert current[0] > 0 and current[1] == 0
    assert suggest_evidence_units(request, query_context=context).passages == ((0, 0),)


def test_latest_negation_and_synonym_are_explicit_semantic_counterexamples():
    request, case, conversation = scenario("latest-negation-counterexample")
    context = build_evidence_query_context(request, case, conversation)
    assert scores(request, context)[0] > 0  # Lexical matching does not understand negation.
    inspected = inspect_claim_selection(request, authored_plan(request), query_context=context)
    assert inspected["semantic_support"] is None and inspected["human_review_required"]
    request, case, conversation = scenario("synonym-counterexample")
    context = build_evidence_query_context(request, case, conversation)
    assert all(value == 0 for value in scores(request, context).values())
    assert suggest_evidence_units(request, query_context=context).passages == ()


@pytest.mark.parametrize(
    "field,value",
    [
        ("case_id", "another-case-with-identical-message"),
        ("case_revision", 3),
        ("checks_performed", ("PRIVATE_NEW_CHECK",)),
        ("unknowns", ("PRIVATE_UNKNOWN",)),
        ("evidence_refs", ("PRIVATE_SOURCE",)),
        ("pending_proposal_id", "PRIVATE_PROPOSAL"),
    ],
)
def test_builder_binds_the_complete_caller_case_not_just_message_or_facts(field, value):
    request, case, conversation = scenario("retired-topic-correction")
    changed = case.model_copy(update={field: value})
    safe_rejection(lambda: build_evidence_query_context(request, changed, conversation))


@pytest.mark.parametrize("change", ["case", "revision", "source", "mode", "message", "hash"])
def test_context_cannot_be_reused_with_a_different_valid_or_tampered_request(change):
    request, case, conversation = scenario("retired-topic-correction")
    context = build_evidence_query_context(request, case, conversation)
    if change == "case":
        changed = rebuild(request, case=case.model_copy(update={"case_id": "foreign-case"}))
    elif change == "revision":
        changed = rebuild(request, case=case.model_copy(update={"case_revision": 3}))
    elif change == "source":
        hits = request.grounded.evidence.hits
        evidence = request.grounded.evidence.model_copy(
            update={
                "hits": (hits[0].model_copy(update={"excerpt": "A changed source."}), *hits[1:])
            }
        )
        changed = rebuild(request, evidence=evidence)
    elif change == "mode":
        changed = rebuild(request, mode="paragraphs")
    elif change == "message":
        grounded = request.grounded
        changed = build_claim_request(
            make_grounded_request(case, "PRIVATE_CHANGED_INPUT", grounded.evidence),
            block_mode="sections",
        )
    else:
        changed = request.model_copy(update={"context_sha256": "0" * 64})
    for operation in (
        lambda: validate_evidence_query_context(changed, context),
        lambda: rank_evidence_units(changed, query_context=context),
        lambda: suggest_evidence_units(changed, query_context=context),
        lambda: inspect_claim_selection(changed, authored_plan(changed), query_context=context),
    ):
        safe_rejection(operation)


def test_complete_ignored_assistant_history_is_bound_even_if_reasoning_message_is_identical():
    request, case, conversation = scenario("assistant-evidence-exclusion")
    entries = conversation.entries
    changed_history = conversation.model_copy(
        update={
            "entries": (
                entries[0],
                entries[1].model_copy(update={"text": "PRIVATE_DIFFERENT_ASSISTANT_HISTORY"}),
                entries[2],
            )
        }
    )
    assert build_reasoning_message(conversation) == build_reasoning_message(changed_history)
    before = build_evidence_query_context(request, case, conversation)
    after = build_evidence_query_context(request, case, changed_history)
    assert before != after
    assert before.context_sha256 != after.context_sha256
    tampered = before.model_copy(update={"conversation": changed_history})
    safe_rejection(lambda: validate_evidence_query_context(request, tampered))


@pytest.mark.parametrize(
    "field,value",
    [
        ("current_query", "PRIVATE_REPLACEMENT_QUERY"),
        ("current_query", True),
        ("request_context_sha256", "0" * 64),
        ("context_sha256", "0" * 64),
        ("PRIVATE_EXTRA", "PRIVATE_VALUE"),
        ("case", {"case_id": "PRIVATE_UNTYPED_CASE"}),
        ("conversation", {"PRIVATE_UNTYPED_HISTORY": True}),
    ],
)
def test_each_context_field_is_revalidated_without_fallback_or_raw_error_text(field, value):
    request, case, conversation = scenario("retired-topic-correction")
    context = build_evidence_query_context(request, case, conversation)
    tampered = context.model_copy(update={field: value})
    for operation in (
        lambda: validate_evidence_query_context(request, tampered),
        lambda: rank_evidence_units(request, query_context=tampered),
        lambda: suggest_evidence_units(request, query_context=tampered),
        lambda: inspect_claim_selection(request, authored_plan(request), query_context=tampered),
    ):
        safe_rejection(operation)


@pytest.mark.parametrize("value", [False, "PRIVATE_CONTEXT", {}, object()])
def test_untyped_context_objects_are_rejected_instead_of_treated_as_absent(value):
    request, _, _ = scenario("retired-topic-correction")
    for operation in (
        lambda: validate_evidence_query_context(request, value),
        lambda: rank_evidence_units(request, query_context=value),
        lambda: suggest_evidence_units(request, query_context=value),
        lambda: inspect_claim_selection(request, authored_plan(request), query_context=value),
    ):
        safe_rejection(operation)


def test_new_context_and_typed_shortlist_are_frozen_and_detach_caller_owned_inputs():
    request, case, conversation = scenario("retired-topic-correction")
    context = build_evidence_query_context(request, case, conversation)
    snapshot = context.model_dump_json()
    with pytest.raises(ValueError):
        context.current_query = "PRIVATE_MUTATION"
    shortlist = suggest_evidence_units(request, query_context=context)
    with pytest.raises(FrozenInstanceError):
        shortlist.query_context_sha256 = "0" * 64
    # Bypass caller models' freeze deliberately; the built snapshot must be detached.
    object.__setattr__(case, "checks_performed", ("PRIVATE_LATER_CHANGE",))
    object.__setattr__(conversation.entries[0], "text", "PRIVATE_LATER_HISTORY")
    assert context.model_dump_json() == snapshot
    assert validate_evidence_query_context(request, context) == context


def test_exact_five_hundred_character_query_retains_cut_boundary_trailing_space():
    latest = "x" * 390 + " " + "y" * 50
    conversation = TurnConversation(
        entries=(ConversationEntry(actor="user", reference_id="current", revision=1, text=latest),),
        latest_turn_id="current",
        committed_revision=1,
        latest_message=latest,
    )
    case = CaseState(
        case_id="neutral-query-boundary",
        case_revision=1,
        facts=(
            Fact(
                name="component",
                value="p" * 96,
                source_ref="user:current",
                turn_id="current",
            ),
        ),
    )
    request = build_claim_request(
        make_grounded_request(
            case,
            build_reasoning_message(conversation),
            EvidenceBundle(snapshot_id="neutral-boundary", hits=()),
        ),
        block_mode="sections",
    )
    expected = build_current_query(case, conversation)
    assert len(expected) == 500 and expected.endswith(" ")
    context = build_evidence_query_context(request, case, conversation)
    assert context.current_query == expected
    assert validate_evidence_query_context(request, context) == context


def test_bypassed_history_list_is_rejected_before_detachment_can_normalize_it():
    request, case, conversation = scenario("retired-topic-correction")
    bypassed = conversation.model_copy(update={"entries": list(conversation.entries)})
    safe_rejection(lambda: build_evidence_query_context(request, case, bypassed))
    context = build_evidence_query_context(request, case, conversation)
    tampered = context.model_copy(update={"conversation": bypassed})
    safe_rejection(lambda: validate_evidence_query_context(request, tampered))
    safe_rejection(lambda: rank_evidence_units(request, query_context=tampered))
    safe_rejection(lambda: suggest_evidence_units(request, query_context=tampered))
    safe_rejection(
        lambda: inspect_claim_selection(request, authored_plan(request), query_context=tampered)
    )
    normalized = TurnConversation.model_validate(conversation.model_dump(mode="json"))
    assert type(normalized.entries) is tuple
    assert build_evidence_query_context(request, case, normalized) == context


@pytest.mark.parametrize(
    "change",
    [
        "case_extra",
        "nested_fact_extra",
        "fact_value_type",
        "revision_bool",
        "request_extra",
        "source_extra",
        "conversation_extra",
        "entry_extra",
        "entry_text_type",
        "entry_revision_bool",
        "latest_mismatch",
        "invalid_utf8",
    ],
)
def test_bypassed_nested_extras_types_and_unicode_fail_with_one_content_free_error(change):
    request, case, conversation = scenario("retired-topic-correction")
    if change == "case_extra":
        case = case.model_copy(update={"PRIVATE_EXTRA": "PRIVATE_VALUE"})
    elif change in {"nested_fact_extra", "fact_value_type"}:
        update = {"PRIVATE_EXTRA": "PRIVATE_VALUE"} if change.endswith("extra") else {"value": 123}
        case = case.model_copy(
            update={"facts": (case.facts[0].model_copy(update=update), *case.facts[1:])}
        )
    elif change == "revision_bool":
        case = case.model_copy(update={"case_revision": True})
    elif change == "request_extra":
        request = request.model_copy(update={"PRIVATE_EXTRA": "PRIVATE_VALUE"})
    elif change == "source_extra":
        hits = request.grounded.evidence.hits
        bundle = request.grounded.evidence.model_copy(
            update={
                "hits": (hits[0].model_copy(update={"PRIVATE_EXTRA": "PRIVATE_VALUE"}), *hits[1:])
            }
        )
        request = request.model_copy(
            update={"grounded": request.grounded.model_copy(update={"evidence": bundle})}
        )
    elif change == "conversation_extra":
        conversation = conversation.model_copy(update={"PRIVATE_EXTRA": "PRIVATE_VALUE"})
    elif change in {"entry_extra", "entry_text_type", "entry_revision_bool"}:
        update = {
            "entry_extra": {"PRIVATE_EXTRA": "PRIVATE_VALUE"},
            "entry_text_type": {"text": 123},
            "entry_revision_bool": {"revision": True},
        }[change]
        conversation = conversation.model_copy(
            update={
                "entries": (
                    conversation.entries[0].model_copy(update=update),
                    conversation.entries[1],
                )
            }
        )
    elif change == "latest_mismatch":
        conversation = conversation.model_copy(update={"latest_message": "PRIVATE_MISMATCH"})
    else:
        conversation = conversation.model_copy(
            update={
                "entries": (
                    conversation.entries[0].model_copy(update={"text": "PRIVATE_INVALID_\ud800"}),
                    conversation.entries[1],
                )
            }
        )
    safe_rejection(lambda: build_evidence_query_context(request, case, conversation))


def test_all_active_USER_values_survive_bounded_query_omission_and_labels_do_not_add_matches():
    conversation = TurnConversation(
        entries=(
            ConversationEntry(
                actor="user", reference_id="current", revision=1, text="Investigate."
            ),
        ),
        latest_turn_id="current",
        committed_revision=1,
        latest_message="Investigate.",
    )
    case = CaseState(
        case_id="neutral-large-current-values",
        case_revision=1,
        facts=(
            Fact(
                name="component",
                value="ordinary " * 60,
                source_ref="user:current",
                turn_id="current",
            ),
            Fact(
                name="glacier_migration",
                value="quartz",
                source_ref="user:current",
                turn_id="current",
            ),
        ),
    )
    # The large first value is omitted as a whole; a separate value still fits.
    # Put the relevant word AFTER the latest-message projection too.
    long_value = "ordinary " * 80 + "zircon"
    case = case.model_copy(
        update={
            "facts": (
                *case.facts,
                Fact(name="late", value=long_value, source_ref="user:current", turn_id="current"),
            )
        }
    )
    evidence = EvidenceBundle(
        snapshot_id="neutral-large-values",
        hits=tuple(
            EvidenceHit(
                chunk_id=f"neutral-{i}",
                source_id=f"neutral-{i}",
                source_url=f"https://example.invalid/{i}",
                source_type="doc",
                excerpt=text,
            )
            for i, text in enumerate(
                ("Zircon minerals.", "Glacier migration topic late component.")
            )
        ),
    )
    request = build_claim_request(
        make_grounded_request(case, build_reasoning_message(conversation), evidence),
        block_mode="sections",
    )
    assert "zircon" not in build_current_query(case, conversation)
    context = build_evidence_query_context(request, case, conversation)
    assert context.current_query == build_current_query(case, conversation)
    assert scores(request, context)[0] > 0
    assert scores(request, context)[1] == 0


@pytest.mark.parametrize("row", SCENARIOS, ids=[row["id"] for row in SCENARIOS])
def test_optional_inspection_never_changes_models_sources_history_or_legacy_results(row):
    request, case, conversation = scenario(row["id"])
    before = (request.model_dump_json(), case.model_dump_json(), conversation.model_dump_json())
    runtime = ReasoningContext(
        run_id="offline-selection-custody",
        case_id=case.case_id,
        case_revision=case.case_revision,
        attempt_index=1,
    )
    messages = build_claim_messages(request, runtime)
    legacy = (
        rank_evidence_units(request),
        suggest_evidence_units(request),
        inspect_claim_selection(request, authored_plan(request)),
    )
    context = build_evidence_query_context(request, case, conversation)
    rank_evidence_units(request, query_context=context)
    shortlist = suggest_evidence_units(request, query_context=context)
    inspection = inspect_claim_selection(request, authored_plan(request), query_context=context)
    assert (
        isinstance(shortlist.query_context_sha256, str)
        and len(shortlist.query_context_sha256) == 64
    )
    assert inspection["query_context_sha256"] == shortlist.query_context_sha256
    assert shortlist.query_context_sha256 == context.context_sha256
    assert inspection["query_input_kind"] == "bound_current_user_projection"
    assert "query_context_sha256" not in asdict(legacy[1])
    assert "query_input_kind" not in legacy[2]
    assert inspection["semantic_support"] is None and inspection["human_review_required"]
    assert (
        request.model_dump_json(),
        case.model_dump_json(),
        conversation.model_dump_json(),
    ) == before
    assert build_claim_messages(request, runtime) == messages
    assert (
        rank_evidence_units(request),
        suggest_evidence_units(request),
        inspect_claim_selection(request, authored_plan(request)),
    ) == legacy
