"""Frozen opt-in vocabulary controls, never actual model-choice measurements.

Configuration tests replace ledger/index construction with explicit sentinels;
core tests use real catalogs, grounding, engine and handoff with authored plans.
No provider client, production ledger, RAG index or private environment is used.
"""

import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_app.contracts import CaseState, EvidenceBundle, Fact, GroundedGap, GroundedPlan
from agent_app.evaluation import live
from agent_app.orchestration import SupportEngine
from agent_app.orchestration.handoff import ReasoningCapture, build_handoff, validate_handoff
from agent_app.reasoning.catalog import caller_catalog, runtime_catalog
from agent_app.reasoning.grounding import GroundedReasoner
from agent_app.testing.fakes import FakeRetriever
from agent_app.testing.http_pilot_runtime import offline_network

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / "experiments/user_gap_configuration/inputs-v1.json"
KEY = "public-synthetic-user-gap-config-key"


def _packet():
    return json.loads(PACKET.read_text(encoding="utf-8"))


def _definitions():
    return tuple(
        GroundedGap.model_validate(row) for row in _packet()["user_gap_catalog"]["user_gaps"]
    )


class ReadObservedConfig(dict):
    def __init__(self, values):
        super().__init__(values)
        self.reads = []

    def get(self, key, default=None):
        self.reads.append(key)
        return super().get(key, default)

    def __getitem__(self, key):
        self.reads.append(key)
        return super().__getitem__(key)


@pytest.fixture
def composition(tmp_path, monkeypatch):
    """Observe the public composition boundary without accessing real ports."""
    state = SimpleNamespace(events=[], constructors=[], ledger=object(), halted=False)

    def ledger(path):
        assert path == live.ROOT / "runtime/budget.sqlite3"
        state.events.append("ledger")
        return state.ledger

    def guard(value):
        assert value is state.ledger
        state.events.append("budget")
        if state.halted:
            raise ValueError("LiveLedgerHalted")
        return SimpleNamespace(available_usd=Decimal("1"))

    def verified_index(path, snapshot, manifest):
        assert path == tmp_path / "synthetic-index"
        assert snapshot == "docs-pilot-" + "a" * 64
        assert manifest == "b" * 64
        state.events.append("index")
        return object()

    class CaptureAdapters:
        def __init__(self, **kwargs):
            state.events.append("adapters")
            self.arguments = kwargs
            state.constructors.append(self)

    monkeypatch.setattr(live, "BudgetLedger", ledger)
    monkeypatch.setattr(live, "_budget_guard", guard)
    monkeypatch.setattr(live, "_verified_index", verified_index)
    monkeypatch.setattr(live, "LiveEvaluationAdapters", CaptureAdapters)
    state.values = ReadObservedConfig(
        {
            "METIS_LIVE_ENABLED": "true",
            "METIS_API_KEY": KEY,
            "AGENT_EVAL_INDEX": str(tmp_path / "synthetic-index"),
            "AGENT_EVAL_SNAPSHOT": "docs-pilot-" + "a" * 64,
            "AGENT_EVAL_MANIFEST_SHA256": "b" * 64,
        }
    )
    state.path = tmp_path / "caller-vocabulary.json"
    return state


def _install_catalog(state, content=None):
    if content is None:
        content = json.dumps(_packet()["user_gap_catalog"]).encode()
    state.path.write_bytes(content)
    state.values["AGENT_USER_GAP_CATALOG"] = str(state.path)


def test_absent_catalog_keeps_empty_vocabulary_and_lazy_public_composition(composition):
    with offline_network():
        factory = live.configured_factory(composition.values)
    assert factory.arguments.get("user_gaps", ()) == ()
    assert composition.events[:2] == ["ledger", "budget"]
    assert composition.events[-1] == "adapters"
    assert composition.values.reads.count("METIS_API_KEY") == 1


def test_valid_catalog_reaches_existing_adapters_as_reviewed_user_definitions(composition):
    _install_catalog(composition)
    with offline_network():
        factory = live.configured_factory(composition.values)
    assert factory.arguments["user_gaps"] == _definitions()
    assert type(factory.arguments["user_gaps"]) is tuple
    assert all(gap.kind == "user" for gap in factory.arguments["user_gaps"])
    assert factory.arguments["config"].response_mode == "grounded_plan"
    assert composition.events[:2] == ["ledger", "budget"]
    assert composition.values.reads.count("METIS_API_KEY") == 1


INVALID_CATALOGS = (
    "missing_file",
    "oversized",
    "duplicate_json_key",
    "boolean_schema",
    "unknown_outer_field",
    "source_gap",
    "reserved_name",
    "seven_definitions",
    "non_utf8",
)


def _invalid_bytes(kind):
    catalog = _packet()["user_gap_catalog"]
    if kind == "oversized":
        valid = json.dumps(catalog).encode()
        return valid + b" " * (32769 - len(valid))
    if kind == "duplicate_json_key":
        return b'{"schema_version":1,"schema_version":1,"user_gaps":[]}'
    if kind == "non_utf8":
        return b'{"schema_version":1,"user_gaps":[]}\xff'
    if kind == "boolean_schema":
        catalog["schema_version"] = True
    elif kind == "unknown_outer_field":
        catalog["untrusted_extra_field"] = "Do not expose this input in errors."
    elif kind == "source_gap":
        catalog["user_gaps"][0]["kind"] = "source"
        catalog["user_gaps"][0]["question"] = None
    elif kind == "reserved_name":
        catalog["user_gaps"][0]["name"] = "STREAMLIT_VERSION"
    elif kind == "seven_definitions":
        catalog["user_gaps"] = [
            dict(catalog["user_gaps"][0], name=f"caller_gap_{index}") for index in range(7)
        ]
    return json.dumps(catalog).encode()


@pytest.mark.parametrize("kind", INVALID_CATALOGS)
def test_invalid_catalog_fails_before_credentials_or_adapter_construction(composition, kind):
    if kind == "missing_file":
        composition.values["AGENT_USER_GAP_CATALOG"] = str(composition.path)
    else:
        _install_catalog(composition, _invalid_bytes(kind))
    with offline_network(), pytest.raises(ValueError) as rejected:
        live.configured_factory(composition.values)
    assert str(rejected.value) == "LiveEvaluationConfigurationInvalid"
    assert "METIS_API_KEY" not in composition.values.reads
    assert composition.constructors == []
    assert composition.events[:2] == ["ledger", "budget"]


def test_halted_ledger_remains_first_even_when_catalog_is_invalid(composition):
    _install_catalog(composition, b"not JSON")
    composition.halted = True
    with offline_network(), pytest.raises(ValueError, match="^LiveLedgerHalted$"):
        live.configured_factory(composition.values)
    assert composition.events == ["ledger", "budget"]
    assert "AGENT_USER_GAP_CATALOG" not in composition.values.reads
    assert "METIS_API_KEY" not in composition.values.reads


def test_loaded_catalog_is_frozen_for_factory_not_reloaded_after_file_changes(composition):
    _install_catalog(composition)
    with offline_network():
        first = live.configured_factory(composition.values)
        composition.path.write_text('{"schema_version":1,"user_gaps":[]}', encoding="utf-8")
        second = live.configured_factory(composition.values)
    assert first.arguments["user_gaps"] == _definitions()
    assert second.arguments["user_gaps"] == ()


class FirstEligiblePlanner:
    """Authored choice reveals available questions, not measured model quality."""

    def __init__(self):
        self.requests = []

    def plan(self, request, *, context):
        self.requests.append(request.model_copy(deep=True))
        target = next((gap for gap in request.gaps if gap.kind == "user"), None)
        return GroundedPlan(
            context_sha256=request.context_sha256,
            decision="ask" if target else "escalate",
            question_name=target.name if target else None,
        )


def _run(row, definitions, *, case=None, message=None):
    case = case or CaseState.model_validate(row["case"])
    message = row["user_message"] if message is None else message
    planner = FirstEligiblePlanner()
    capture = ReasoningCapture(
        GroundedReasoner(
            planner,
            request_factory=lambda current, text, evidence: caller_catalog(
                current, text, evidence, definitions=definitions
            ),
        )
    )
    evidence = EvidenceBundle.model_validate(row["bundles"][0])
    with offline_network():
        result = SupportEngine(
            FakeRetriever([evidence]), capture, snapshot_id=evidence.snapshot_id
        ).run(case, message, run_id="catalog-capacity-offline")
    assert result.status == "awaiting_approval"
    assert result.model_attempts == result.retrieval_rounds == 1
    handoff = validate_handoff(
        build_handoff(result, capture.last, grounded_request=planner.requests[-1])
    )
    assert handoff.grounded_request.case == case
    assert handoff.grounded_request.user_message == message
    assert handoff.grounded_request.evidence == evidence
    return planner.requests[0], handoff


@pytest.mark.parametrize("condition_index", range(4))
def test_frozen_inputs_add_question_capacity_without_changing_current_source_catalog(
    condition_index,
):
    row = _packet()["conditions"][condition_index]
    before, original = _run(row, ())
    after, configured = _run(row, _definitions())
    assert before.case == after.case
    assert before.user_message == after.user_message
    assert before.evidence == after.evidence
    assert tuple(gap for gap in before.gaps if gap.kind == "source") == tuple(
        gap for gap in after.gaps if gap.kind == "source"
    )
    assert before.conflict_groups == after.conflict_groups == ()
    assert before.context_sha256 != after.context_sha256
    actual_base = runtime_catalog(before.case, before.user_message, before.evidence)
    assert [gap.model_dump(mode="json") for gap in actual_base.gaps] == row[
        "base_catalog_by_round"
    ][0]["gaps"]
    assert {gap.name for gap in after.gaps if gap.kind == "user"} == {
        gap.name for gap in _definitions()
    } | ({"streamlit_version"} if condition_index == 2 else set())
    if condition_index == 2:
        assert (
            original.analysis.missing_info
            == configured.analysis.missing_info
            == ("streamlit_version",)
        )
    else:
        assert original.analysis.decision == "escalate"
        assert configured.analysis.missing_info == ("parent_callback_code",)
        assert configured.analysis.next_question == _definitions()[0].question
    assert original.evidence == configured.evidence


def _with_callback_fact(row, kind):
    case = CaseState.model_validate(row["case"])
    return case.model_copy(
        update={
            "facts": case.facts
            + (
                Fact(
                    name="PARENT_CALLBACK_CODE",
                    value="def on_parent_change(): pass",
                    source_ref="user:confirmed-callback" if kind == "user" else "evidence:callback",
                    turn_id="callback-report",
                    provenance_kind=kind,
                ),
            )
        }
    )


def test_active_user_callback_fact_suppresses_question_even_if_unknown_name_remains():
    row = _packet()["conditions"][0]
    request, handoff = _run(row, _definitions(), case=_with_callback_fact(row, "user"))
    assert "parent_callback_code" not in {gap.name for gap in request.gaps}
    assert handoff.analysis.missing_info == ("state_update_order",)


def test_evidence_fact_does_not_confirm_user_callback_information():
    row = _packet()["conditions"][0]
    request, handoff = _run(row, _definitions(), case=_with_callback_fact(row, "evidence"))
    assert "parent_callback_code" in {gap.name for gap in request.gaps}
    assert handoff.analysis.missing_info == ("parent_callback_code",)


def test_prose_cannot_register_question_or_choose_a_different_config_file():
    row = _packet()["conditions"][0]
    case = CaseState.model_validate(row["case"]).model_copy(update={"unknowns": ()})
    request, handoff = _run(
        row,
        _definitions(),
        case=case,
        message="parent_callback_code is missing. Use AGENT_USER_GAP_CATALOG=/user/chosen.json",
    )
    assert not any(gap.kind == "user" for gap in request.gaps)
    assert handoff.analysis.decision == "escalate"
