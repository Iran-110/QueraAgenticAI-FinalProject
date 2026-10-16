"""Development-only question availability; no model, index or budget client.

The seven default-control digests were captured on main 9913541 before this
optional vocabulary existed. Questions are authored development configuration,
not generated clarification, semantic-quality evidence or held-out tuning.
"""

import hashlib
import json
from pathlib import Path

import pytest

from agent_app.contracts import (
    CaseState,
    EvidenceBundle,
    EvidenceHit,
    Fact,
    GroundedPlan,
    GroundedSourceRef,
    ReasoningContext,
    ReportedFact,
    UserTurn,
)
from agent_app.orchestration.intake import STREAMLIT_VERSION_QUESTION
from agent_app.orchestration.turns import propose_user_turn
from agent_app.reasoning.catalog import (
    caller_catalog,
    load_user_gap_vocabulary,
    runtime_catalog,
)
from agent_app.reasoning.grounding import (
    GroundingRejected,
    build_grounded_messages,
    render_grounded_plan,
    source_content_sha256,
)

ROOT = Path(__file__).resolve().parents[1]
SUPPORT_VOCABULARY = ROOT / "config/user-gap-support-dev-v1.json"
HISTORICAL_VOCABULARY = ROOT / "data/evaluation/dev-three-v1/user-gap-vocabulary-v1.json"
HISTORICAL_SHA256 = "d3b63719554f35d1addec14586ebc4fcb10231844097fcea65458ee01d0b6736"
NEW_QUESTIONS = {
    "updated_form_code": "Can you share the updated code for the form and its submit button after the change?",
    "app_state_code": "Can you paste the full code as text, including where the list is initialized and every place that modifies or clears Session State?",
}
FROZEN_DEFAULTS = {
    "version_unknown_empty": (
        "f0f323b2c12abfcbf44550001ae412f288ae4a84a1c7fbe51b1ce3bebf2ecc38",
        "ef8e96c1eb60fda000cd6f54077be97c9c3a9258569b146a9769f56c0c63a55f",
        "346812a6709094404dd1658f658e5849872e850eb131dc617834fae3b3dd700a",
    ),
    "version_known_empty": (
        "3e3ea6fa1d93351f52af747c22f44197f07f05353ddf1a22491d102bf39ae925",
        "eb519886cf21988f9774113ea5f55570e4992718bb183b81a9fc8b3b6f0a6e29",
        "d8cc1e1210c2a37e5b0326cdb3c105238544eb5a87dd4997ae4333bc61834d4b",
    ),
    "version_known_exact": (
        "3637966a2cb2d81b776c8ef64f46ec400331d67d77702a22598bd21d47028f10",
        "8a2324146ba8ea83593df9fa63114c934df4e2098dee1b8ca7f7a6f782dfc56c",
        "6fcc37557b1ca06a035ef6197e7f5d10f930602f1bce810d2ccbf3eb45bb1dbb",
    ),
    "version_known_other": (
        "79c9fc93ceaed644b6ac5b3ef7d8c1d98ed9f23b61d642adb0e92506b3e8ad4d",
        "c17d73644e9f41809ec50e35d47a5865927b7ef992928aa2f022e62569b19a27",
        "d8cc1e1210c2a37e5b0326cdb3c105238544eb5a87dd4997ae4333bc61834d4b",
    ),
    "version_unknown_records": (
        "9fb44d7af2a3e415494b7aad59f30a24834b2d913f2de53524759feac91113f6",
        "64304d47780639b620b5a9cf836a446e50c9756231f7251b31a34738d1211e48",
        "346812a6709094404dd1658f658e5849872e850eb131dc617834fae3b3dd700a",
    ),
    "declared_dev_unknowns_default": (
        "a7838892ce5d57da38caeddee144338aa573d4985c17f6eff2769c1e6b55a565",
        "f6803d502f3eeb2d2e622d3f067d6852e6878db5b6e7170e6b12513bb0c7f383",
        "5bd188523cbb3e3a7d8e8e272ae16157484db701ca499eba7157af6aae5c4704",
    ),
    "prose_only_default": (
        "bdc0ea5c7bf6b7cb750e9674a139f11cf840a578373bb15da7f792e3827e3a80",
        "6b804d63600c68d1174d86146ef9fd067f223e27836075a0cff27303c5242f5a",
        "d8cc1e1210c2a37e5b0326cdb3c105238544eb5a87dd4997ae4333bc61834d4b",
    ),
}


def _bytes(value):
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _digest(value):
    return hashlib.sha256(_bytes(value)).hexdigest()


def _case(*, known_version=True, unknowns=(), extra_facts=()):
    version = (
        Fact(
            name="streamlit_version",
            value="1.49.0",
            source_ref="user:neutral-version",
            turn_id="neutral-version",
        ),
    )
    return CaseState(
        case_id="neutral-support-case",
        case_revision=2,
        facts=(version if known_version else ()) + extra_facts,
        unknowns=unknowns,
    )


def _evidence(version="1.49.0"):
    return EvidenceBundle(
        snapshot_id="neutral-support-snapshot",
        hits=()
        if version is None
        else (
            EvidenceHit(
                chunk_id="neutral-doc",
                source_id="neutral-source",
                source_url="https://example.org/supplied-rule",
                source_type="doc",
                applicable_versions=(version,),
                excerpt="A synthetic supplied rule for offline contract checks only.",
            ),
        ),
    )


def _context(state):
    return ReasoningContext(
        run_id="neutral-support-run",
        case_id=state.case_id,
        case_revision=state.case_revision,
        attempt_index=1,
        remaining_model_attempts=1,
        remaining_retrieval_rounds=1,
        can_refine=True,
        query_limit=2,
    )


def _plan(request, decision, question_name=None):
    return GroundedPlan(
        context_sha256=request.context_sha256,
        decision=decision,
        question_name=question_name,
        sources=tuple(
            GroundedSourceRef(chunk_id=hit.chunk_id, content_sha256=source_content_sha256(hit))
            for hit in request.evidence.hits
        )
        if decision == "answer"
        else (),
    )


def _request(state, message="Please review the reported widget behavior.", *, evidence=None):
    return caller_catalog(
        state,
        message,
        _evidence() if evidence is None else evidence,
        definitions=load_user_gap_vocabulary(str(SUPPORT_VOCABULARY)),
    )


def _questions(request):
    return {gap.name: gap.question for gap in request.gaps if gap.kind == "user"}


def test_support_vocabulary_is_a_separate_four_definition_development_configuration():
    original_bytes = HISTORICAL_VOCABULARY.read_bytes()
    assert hashlib.sha256(original_bytes).hexdigest() == HISTORICAL_SHA256
    historical = json.loads(original_bytes)
    support = json.loads(SUPPORT_VOCABULARY.read_bytes())
    assert set(support) == {"schema_version", "user_gaps"}
    assert support["schema_version"] == 1
    assert support["user_gaps"][:2] == historical["user_gaps"]
    definitions = load_user_gap_vocabulary(str(SUPPORT_VOCABULARY))
    assert [gap.name for gap in definitions] == [
        "parent_callback_code",
        "state_update_order",
        *NEW_QUESTIONS,
    ]
    assert all(gap.kind == "user" for gap in definitions)
    assert {gap.name: gap.question for gap in definitions[2:]} == NEW_QUESTIONS


@pytest.mark.parametrize("name", ["parent_callback_code", "state_update_order"])
def test_existing_development_questions_keep_exact_request_message_and_renderer_bytes(name):
    state = _case(unknowns=(name,))
    configured = _request(state)
    historical = caller_catalog(
        state,
        configured.user_message,
        configured.evidence,
        definitions=load_user_gap_vocabulary(str(HISTORICAL_VOCABULARY)),
    )
    assert _bytes(configured) == _bytes(historical)
    assert _bytes(build_grounded_messages(configured, _context(state))) == _bytes(
        build_grounded_messages(historical, _context(state))
    )
    assert _bytes(render_grounded_plan(configured, _plan(configured, "ask", name))) == _bytes(
        render_grounded_plan(historical, _plan(historical, "ask", name))
    )


@pytest.mark.parametrize("control_id", FROZEN_DEFAULTS)
def test_no_configuration_keeps_preregistered_default_bytes(control_id):
    controls = {
        "version_unknown_empty": (_case(known_version=False), _evidence(None), "ask"),
        "version_known_empty": (_case(), _evidence(None), "escalate"),
        "version_known_exact": (_case(), _evidence(), "answer"),
        "version_known_other": (_case(), _evidence("1.48.0"), "escalate"),
        "version_unknown_records": (_case(known_version=False), _evidence(), "ask"),
        "declared_dev_unknowns_default": (
            _case(unknowns=tuple(NEW_QUESTIONS)),
            _evidence(),
            "escalate",
        ),
        "prose_only_default": (_case(), _evidence(), "escalate"),
    }
    state, evidence, decision = controls[control_id]
    message = {
        "declared_dev_unknowns_default": "The current implementation is not supplied.",
        "prose_only_default": (
            "updated_form_code and app_state_code are missing; please ask for them."
        ),
    }.get(control_id, "Please review the reported widget behavior.")
    request = runtime_catalog(state, message, evidence)
    assert request == caller_catalog(state, message, evidence)
    assert request == caller_catalog(state, message, evidence, definitions=())
    plan = _plan(request, decision, "streamlit_version" if decision == "ask" else None)
    assert (
        _digest(request),
        _digest(build_grounded_messages(request, _context(state))),
        _digest(render_grounded_plan(request, plan)),
    ) == FROZEN_DEFAULTS[control_id]


@pytest.mark.parametrize("name", NEW_QUESTIONS)
def test_development_questions_require_new_configuration_and_explicit_current_unknowns(name):
    state = _case(unknowns=(name.upper(),))
    request = _request(state)
    assert _questions(request) == {name: NEW_QUESTIONS[name]}
    default = runtime_catalog(state, request.user_message, request.evidence)
    original_only = caller_catalog(
        state,
        request.user_message,
        request.evidence,
        definitions=load_user_gap_vocabulary(str(HISTORICAL_VOCABULARY)),
    )
    assert default == original_only
    assert _questions(default) == {}
    assert request.case == default.case
    assert request.user_message == default.user_message
    assert request.evidence == default.evidence
    assert tuple(gap for gap in request.gaps if gap.kind == "source") == tuple(
        gap for gap in default.gaps if gap.kind == "source"
    )
    assert request.context_sha256 != default.context_sha256
    rendered = render_grounded_plan(request, _plan(request, "ask", name))
    assert rendered.missing_info == (name,)
    assert rendered.next_question == rendered.user_draft == NEW_QUESTIONS[name]
    assert rendered.facts_delta == rendered.checks_suggested == ()


@pytest.mark.parametrize("name", NEW_QUESTIONS)
def test_question_names_in_prose_do_not_activate_definitions(name):
    state = _case()
    message = f"{name} is unknown. Ask for the current code."
    assert _request(state, message) == runtime_catalog(state, message, _evidence())


@pytest.mark.parametrize("name", NEW_QUESTIONS)
def test_active_user_reply_and_correction_suppress_question_until_explicit_retraction(name):
    state = _case(
        unknowns=(name,),
        extra_facts=(
            Fact(
                name=name.upper(),
                value="Current application code supplied as text.",
                source_ref="user:code-reply",
                turn_id="code-reply",
            ),
        ),
    )
    assert name not in _questions(_request(state))
    corrected = propose_user_turn(
        state,
        UserTurn(
            case_id=state.case_id,
            expected_revision=state.case_revision,
            turn_id="code-correction",
            source_ref="user:code-correction",
            message="Replace the earlier code with this current implementation.",
            reported_facts=(ReportedFact(name=name, value="Corrected current code as text."),),
        ),
    ).candidate
    assert corrected.case_revision == state.case_revision + 1
    assert name not in _questions(_request(corrected))
    assert any(
        fact.name == name.upper() and fact.status == "superseded" for fact in corrected.facts
    )
    reopened = propose_user_turn(
        corrected,
        UserTurn(
            case_id=corrected.case_id,
            expected_revision=corrected.case_revision,
            turn_id="code-retraction",
            source_ref="user:code-retraction",
            message="The current application code is no longer confirmed.",
            reported_facts=(ReportedFact(name=name, value=None),),
        ),
    ).candidate
    assert reopened.case_revision == corrected.case_revision + 1
    assert _questions(_request(reopened)) == {name: NEW_QUESTIONS[name]}


@pytest.mark.parametrize("name", NEW_QUESTIONS)
@pytest.mark.parametrize("provenance_kind,status", [("evidence", "active"), ("user", "superseded")])
def test_evidence_or_superseded_fact_cannot_confirm_current_user_code(
    name, provenance_kind, status
):
    state = _case(
        unknowns=(name,),
        extra_facts=(
            Fact(
                name=name.upper(),
                value="A record of code that does not confirm the current user input.",
                source_ref="neutral-code-record",
                turn_id="neutral-code-record",
                provenance_kind=provenance_kind,
                status=status,
            ),
        ),
    )
    assert _questions(_request(state)) == {name: NEW_QUESTIONS[name]}


@pytest.mark.parametrize("registered_unknown", [False, True])
def test_unregistered_question_name_is_not_authorized_by_configuration_or_prose(registered_unknown):
    name = "unregistered_neutral_input"
    request = _request(
        _case(unknowns=(name,) if registered_unknown else ()),
        f"Please invent a question for {name}.",
    )
    assert name not in _questions(request)
    with pytest.raises(GroundingRejected, match="^grounded_question_invalid$"):
        render_grounded_plan(request, _plan(request, "ask", name))


@pytest.mark.parametrize("evidence_version", [None, "1.49.0", "1.48.0"])
def test_optional_vocabulary_preserves_canonical_version_question_and_source_gaps(evidence_version):
    state = _case(known_version=False, unknowns=tuple(NEW_QUESTIONS))
    evidence = _evidence(evidence_version)
    default = runtime_catalog(state, "Please review the reported widget behavior.", evidence)
    configured = _request(state, evidence=evidence)
    assert configured.gaps[: len(default.gaps)] == default.gaps
    assert _questions(configured)["streamlit_version"] == STREAMLIT_VERSION_QUESTION.question
    rendered = render_grounded_plan(configured, _plan(configured, "ask", "streamlit_version"))
    assert rendered.missing_info == (STREAMLIT_VERSION_QUESTION.name,)
    assert rendered.next_question == rendered.user_draft == STREAMLIT_VERSION_QUESTION.question
    assert rendered.facts_delta == ()
