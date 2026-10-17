"""Pure turn input boundaries reject hidden state without changing valid transitions."""

import hashlib
import json
from collections.abc import Mapping

import pytest
from pydantic import BaseModel, ValidationError

from agent_app.contracts import CaseState, Fact, ReportedFact, UserTurn
from agent_app.orchestration.turns import propose_user_turn

_MARKER = "untrusted-turn-boundary-marker"
_VALID_TRANSITION_SHA256 = {
    "message_only": "31de5867e4df1c9b1fc421a862782a959d576c8aa85b17eb74cad0b17ac8a8ce",
    "restatement": "6974708be25b30cc716f1428415ead486f87b70d33c185f4966e27dc4c0a0f14",
    "correction": "585b4a0319ebd299dcd18f74312cf56893ff59bff2fcf9b5232b5bce4f4aa269",
    "addition": "179037a43793dff733e2e04eca59d8615c608a49111a7a6c3c8c604213db4b0a",
    "withdrawal": "aeca5916b207569b954e43e5a1d07de13c9df846957f30d5804885a4385ca38c",
    "environment_switch": "7f00d4e8fb9e7df14f28e598946a5bd796f3d24729c4a6e47751dedd1e12896e",
    "new_check": "2615ee78140a21e18e259e673e5c8738f102d920706be0c842987d09e615244d",
    "repeated_check": "f36bb0c02fd9cf5333b9ca8f9d80e6490cc81738364ce449c7819e8f66562ab4",
}


def _inputs(variant="correction"):
    state = CaseState(
        case_id="case:turn-boundary",
        case_revision=4,
        facts=(
            Fact(
                name="streamlit_version",
                value="1.49.0",
                source_ref="user:previous",
                turn_id="turn:previous",
            ),
            Fact(
                name="python_version",
                value="3.13.0",
                source_ref="user:previous",
                turn_id="turn:previous",
            ),
            Fact(
                name="prior_inference",
                value="A source-derived observation from the prior context.",
                source_ref="chunk:previous",
                turn_id="turn:previous",
                provenance_kind="evidence",
            ),
        ),
        unknowns=("browser_version",),
        checks_performed=("A minimal reproduction still fails.",),
        evidence_refs=("chunk:previous",),
        pending_proposal_id="proposal:previous",
    )
    changes = {
        "message_only": {},
        "restatement": {
            "reported_facts": (ReportedFact(name="STREAMLIT_VERSION", value="1.49.0"),)
        },
        "correction": {"reported_facts": (ReportedFact(name="streamlit_version", value="1.50.0"),)},
        "addition": {"reported_facts": (ReportedFact(name="browser_version", value="125"),)},
        "withdrawal": {"reported_facts": (ReportedFact(name="streamlit_version", value=None),)},
        "environment_switch": {
            "context_changed": True,
            "reported_facts": (ReportedFact(name="streamlit_version", value="1.49.0"),),
        },
        "new_check": {"checks_performed": ("The workaround did not help.",)},
        "repeated_check": {"checks_performed": ("A   MINIMAL reproduction still fails.",)},
    }
    event = UserTurn(
        case_id=state.case_id,
        expected_revision=4,
        turn_id=f"turn:{variant}",
        source_ref=f"user:{variant}",
        message="The affected environment needs another review. توضیح کاربر",
        **changes[variant],
    )
    return state, event


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _snapshot(value):
    """Observe hidden bypassed state as well as ordinary contract fields."""
    if isinstance(value, BaseModel):
        return (
            type(value).__name__,
            _snapshot(value.__dict__),
            _snapshot(value.__pydantic_extra__),
            _snapshot(value.__pydantic_private__),
            frozenset(value.__pydantic_fields_set__),
        )
    if isinstance(value, Mapping):
        return (type(value).__name__, tuple((_snapshot(k), _snapshot(v)) for k, v in value.items()))
    if isinstance(value, (tuple, list)):
        return (type(value).__name__, tuple(_snapshot(child) for child in value))
    return (type(value).__name__, value)


@pytest.mark.parametrize("target_name", ["case", "case_fact", "turn", "reported_fact"])
@pytest.mark.parametrize("hidden_state", ["extra_field", "extra_metadata", "private_metadata"])
def test_hidden_state_is_rejected_before_a_turn_candidate_can_be_created(target_name, hidden_state):
    state, event = _inputs()
    target = {
        "case": state,
        "case_fact": state.facts[0],
        "turn": event,
        "reported_fact": event.reported_facts[0],
    }[target_name]
    if hidden_state == "extra_field":
        target.__dict__[_MARKER] = _MARKER
    else:
        field = "__pydantic_extra__" if hidden_state == "extra_metadata" else "__pydantic_private__"
        object.__setattr__(target, field, {_MARKER: _MARKER})
    before = _snapshot((state, event))

    with pytest.raises(ValueError, match=r"^Invalid boundary contract\.$") as caught:
        propose_user_turn(state, event)

    assert _MARKER not in str(caught.value)
    assert _snapshot((state, event)) == before
    assert state.case_revision == 4
    assert state.pending_proposal_id == "proposal:previous"


@pytest.mark.parametrize(
    "target_name,field,value",
    [
        ("case", "case_revision", True),
        ("case_fact", "value", 123),
        ("turn", "context_changed", 1),
        ("reported_fact", "value", 123),
    ],
)
def test_invalid_declared_fields_keep_existing_validation_error_and_inputs(
    target_name, field, value
):
    state, event = _inputs()
    target = {
        "case": state,
        "case_fact": state.facts[0],
        "turn": event,
        "reported_fact": event.reported_facts[0],
    }[target_name]
    object.__setattr__(target, field, value)
    before = _snapshot((state, event))

    with pytest.raises(ValidationError):
        propose_user_turn(state, event)

    assert _snapshot((state, event)) == before


@pytest.mark.parametrize(
    "variant",
    [
        "message_only",
        "restatement",
        "correction",
        "addition",
        "withdrawal",
        "environment_switch",
        "new_check",
        "repeated_check",
    ],
)
def test_valid_complete_transition_bytes_keep_prechange_hash_and_inputs(variant):
    state, event = _inputs(variant)
    before = _snapshot((state, event))

    result = propose_user_turn(state, event)

    payload = _canonical(result.model_dump(mode="json")).encode("utf-8")
    assert hashlib.sha256(payload).hexdigest() == _VALID_TRANSITION_SHA256[variant]
    assert _snapshot((state, event)) == before
    assert result.candidate.case_revision == 5
    assert result.candidate.pending_proposal_id is None
