"""Offline freshness regressions against real SQLite state and scripted ports.

Full CaseState checks stop observable drift; they do not implement a run journal,
atomic staging token, or protection against a lifecycle ABA between observations.
"""

import sqlite3

import pytest

from agent_app.contracts import AnalysisResult, CaseState, Fact, ReportedFact, UserTurn
from agent_app.demo import SNAPSHOT_ID, _answer, _evidence
from agent_app.orchestration import SupportEngine
from agent_app.orchestration.handoff import HandoffRejected, ReasoningCapture, build_handoff
from agent_app.orchestration.ports import ReasoningStopped
from agent_app.testing.fakes import FakeReasoner, FakeRetriever
from agent_app.tracker.sqlite_tracker import SQLiteCaseTracker

CASE_ID = "engine-freshness-case"
MESSAGE = "An authored fixture widget loses its value after rerun."


def new_case(path):
    tracker = SQLiteCaseTracker(path)
    tracker.apply_turn(
        UserTurn(
            case_id=CASE_ID,
            expected_revision=0,
            turn_id="initial",
            source_ref="user:initial",
            message=MESSAGE,
            reported_facts=(ReportedFact(name="streamlit_version", value="1.50.0"),),
        )
    )
    return tracker, read_case(tracker)


def read_case(tracker):
    return CaseState.model_validate(tracker.read_case(CASE_ID)["state"])


def rival_handoff(state):
    capture = ReasoningCapture(FakeReasoner([_answer("freshness-source")]))
    result = SupportEngine(
        FakeRetriever([_evidence("freshness-source", "Authored offline evidence.")]),
        capture,
        snapshot_id=SNAPSHOT_ID,
    ).run(state, MESSAGE, run_id="rival-run")
    return build_handoff(result, capture.last)


def drift_content_at_same_revision(path, state):
    """Inject a valid storage fault; ordinary user corrections increment revision."""
    changed = state.model_copy(update={"unknowns": ("changed-at-same-revision",)})
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE cases SET state_json=? WHERE case_id=?",
            (changed.model_dump_json(), CASE_ID),
        )


@pytest.mark.parametrize("capture_input", [False, True])
def test_already_pending_sqlite_case_stops_before_any_ports(tmp_path, capture_input):
    tracker, state = new_case(tmp_path / "pending.db")
    pending = rival_handoff(state)
    tracker.stage_proposal(pending)
    before = tracker.read_case(CASE_ID)
    retriever = FakeRetriever([_evidence("freshness-source", "Unused authored evidence.")])
    reasoner = FakeReasoner([_answer("freshness-source")])
    engine = SupportEngine(
        retriever,
        ReasoningCapture(reasoner) if capture_input else reasoner,
        snapshot_id=SNAPSHOT_ID,
    )

    result = engine.run(read_case(tracker), MESSAGE, run_id="blocked-run")

    assert result.status == "stale"
    assert result.error_code == "PendingProposalMismatch"
    assert result.analysis is None
    assert result.model_attempts == result.retrieval_rounds == result.steps == 0
    assert retriever.requests == reasoner.inputs == []
    assert tracker.read_case(CASE_ID) == before
    assert tracker.comments(CASE_ID) == []


def test_nested_extra_in_initial_snapshot_rejects_before_any_ports(tmp_path):
    tracker, state = new_case(tmp_path / "nested-input.db")
    broken = state.model_copy(
        update={"facts": (state.facts[0].model_copy(update={"private_extra": "never-export"}),)}
    )
    retriever = FakeRetriever([_evidence("freshness-source", "Unused evidence.")])
    reasoner = FakeReasoner([_answer("freshness-source")])
    with pytest.raises(ValueError, match="Invalid boundary contract"):
        SupportEngine(retriever, reasoner, snapshot_id=SNAPSHOT_ID).run(broken, MESSAGE)
    assert retriever.requests == reasoner.inputs == []


def test_nested_extra_in_current_case_fails_closed_before_ports(tmp_path):
    tracker, state = new_case(tmp_path / "nested-read.db")
    broken = state.model_copy(
        update={
            "facts": (state.facts[0].model_copy(update={"private_extra": "must-not-be-scrubbed"}),)
        }
    )
    retriever = FakeRetriever([_evidence("freshness-source", "Unused evidence.")])
    reasoner = FakeReasoner([_answer("freshness-source")])
    result = SupportEngine(
        retriever, reasoner, snapshot_id=SNAPSHOT_ID, current_case=lambda _: broken
    ).run(state, MESSAGE)
    assert result.error_code == "CaseReadFailed" and result.analysis is None
    assert result.model_attempts == result.retrieval_rounds == 0
    assert retriever.requests == reasoner.inputs == []


@pytest.mark.parametrize("stage", ["before_run", "retrieval", "reasoning"])
def test_same_revision_rival_staging_discards_the_old_run(tmp_path, stage):
    file = tmp_path / "rival.db"
    tracker, state = new_case(file)
    rival = rival_handoff(state)
    other_connection = SQLiteCaseTracker(file)

    class StagingRetriever(FakeRetriever):
        def search(self, request):
            response = super().search(request)
            if stage == "retrieval":
                other_connection.stage_proposal(rival)
            return response

    class StagingReasoner(FakeReasoner):
        def analyze(self, case, message, evidence, *, context):
            response = super().analyze(case, message, evidence, context=context)
            if stage == "reasoning":
                other_connection.stage_proposal(rival)
            return response

    retriever = StagingRetriever([_evidence("freshness-source", "Authored offline evidence.")])
    reasoner = StagingReasoner([_answer("freshness-source")])
    capture = ReasoningCapture(reasoner)
    if stage == "before_run":
        # The caller read a fresh state, then another run won before any ports.
        other_connection.stage_proposal(rival)
    result = SupportEngine(
        retriever,
        capture,
        snapshot_id=SNAPSHOT_ID,
        current_revision=lambda _: read_case(tracker).case_revision,
        current_case=lambda _: read_case(tracker),
    ).run(state, MESSAGE, run_id="delayed-run")

    assert result.status == "stale"
    assert result.error_code == "PendingProposalMismatch"
    assert result.analysis is None
    assert len(retriever.requests) == result.retrieval_rounds == (0 if stage == "before_run" else 1)
    assert len(reasoner.inputs) == result.model_attempts == (1 if stage == "reasoning" else 0)
    with pytest.raises(HandoffRejected, match="FinalProposalRequired"):
        build_handoff(result, capture.last)
    after = tracker.read_case(CASE_ID)
    assert after["state"]["case_revision"] == state.case_revision
    assert after["pending_handoff"] == rival.model_dump(mode="json")
    assert tracker.comments(CASE_ID) == []


def test_same_revision_content_drift_after_retrieval_prevents_model_call(tmp_path):
    file = tmp_path / "content-before-model.db"
    tracker, state = new_case(file)

    class DriftingRetriever(FakeRetriever):
        def search(self, request):
            response = super().search(request)
            drift_content_at_same_revision(file, state)
            return response

    retriever = DriftingRetriever([_evidence("freshness-source", "Authored offline evidence.")])
    reasoner = FakeReasoner([_answer("freshness-source")])
    result = SupportEngine(
        retriever,
        reasoner,
        snapshot_id=SNAPSHOT_ID,
        current_case=lambda _: read_case(tracker),
    ).run(state, MESSAGE)

    assert result.status == "stale"
    assert result.error_code == "CaseContentMismatch"
    assert result.analysis is None
    assert result.retrieval_rounds == len(retriever.requests) == 1
    assert result.model_attempts == 0
    assert reasoner.inputs == []
    assert read_case(tracker).case_revision == state.case_revision
    assert read_case(tracker).unknowns == ("changed-at-same-revision",)


@pytest.mark.parametrize("response", ["final", "repair", "refinement"])
def test_drift_during_reasoning_stops_final_output_repair_and_refinement(tmp_path, response):
    file = tmp_path / "content-during-model.db"
    tracker, state = new_case(file)
    output = {
        "final": _answer("freshness-source"),
        "repair": "not JSON",
        "refinement": AnalysisResult(
            decision="retrieve_more",
            user_draft="",
            maintainer_summary="",
            rationale="Authored additional search request.",
            retrieval_queries=("authored distinct refinement query",),
        ),
    }[response]

    class DriftingReasoner(FakeReasoner):
        def analyze(self, case, message, evidence, *, context):
            result = super().analyze(case, message, evidence, context=context)
            drift_content_at_same_revision(file, state)
            return result

    retriever = FakeRetriever(
        [
            _evidence("freshness-source", "Authored offline evidence."),
            _evidence("second-source", "Unused refinement evidence."),
        ]
    )
    reasoner = DriftingReasoner([output, _answer("second-source")])
    result = SupportEngine(
        retriever,
        reasoner,
        snapshot_id=SNAPSHOT_ID,
        current_case=lambda _: read_case(tracker),
    ).run(state, MESSAGE)

    assert result.status == "stale"
    assert result.error_code == "CaseContentMismatch"
    assert result.analysis is None
    assert result.model_attempts == len(reasoner.inputs) == 1
    assert result.retrieval_rounds == len(retriever.requests) == 1
    assert len(reasoner.responses) == len(retriever.responses) == 1
    assert tracker.read_case(CASE_ID)["pending_handoff"] is None


def test_current_case_detects_a_real_correction_without_revision_callback(tmp_path):
    file = tmp_path / "correction.db"
    tracker, state = new_case(file)

    class CorrectingRetriever(FakeRetriever):
        def search(self, request):
            response = super().search(request)
            SQLiteCaseTracker(file).apply_turn(
                UserTurn(
                    case_id=CASE_ID,
                    expected_revision=1,
                    turn_id="correction",
                    source_ref="user:correction",
                    message="The affected server actually uses 1.49.1.",
                    reported_facts=(ReportedFact(name="streamlit_version", value="1.49.1"),),
                )
            )
            return response

    retriever = CorrectingRetriever([_evidence("freshness-source", "Old authored evidence.")])
    reasoner = FakeReasoner([_answer("freshness-source")])
    result = SupportEngine(
        retriever,
        reasoner,
        snapshot_id=SNAPSHOT_ID,
        current_case=lambda _: read_case(tracker),
    ).run(state, MESSAGE)

    assert result.status == "stale"
    assert result.error_code == "StaleRevision"
    assert result.analysis is None
    assert reasoner.inputs == []
    assert result.retrieval_rounds == len(retriever.requests) == 1
    assert [fact.status for fact in read_case(tracker).facts] == ["superseded", "active"]


@pytest.mark.parametrize(
    "bad_state",
    [
        None,
        {"case_id": CASE_ID, "case_revision": 1},
        CaseState(case_id="wrong-case", case_revision=1),
        CaseState.model_construct(case_id=CASE_ID, case_revision=True),
        CaseState(case_id=CASE_ID, case_revision=1).model_copy(
            update={"private-extra-marker": "private-extra-value"}
        ),
        CaseState(
            case_id=CASE_ID,
            case_revision=1,
            facts=(Fact(name="version", value="1.50.0", source_ref="user:1", turn_id="1"),),
        ).model_copy(
            update={
                "facts": (
                    Fact(
                        name="version", value="1.50.0", source_ref="user:1", turn_id="1"
                    ).model_copy(update={"status": "private-invalid-status"}),
                )
            }
        ),
    ],
)
def test_invalid_current_case_fails_closed_before_ports_without_raw_details(bad_state):
    retriever = FakeRetriever([_evidence("freshness-source", "Unused authored evidence.")])
    reasoner = FakeReasoner([_answer("freshness-source")])
    result = SupportEngine(
        retriever,
        reasoner,
        snapshot_id=SNAPSHOT_ID,
        current_case=lambda _: bad_state,
    ).run(CaseState(case_id=CASE_ID, case_revision=1), MESSAGE)

    assert result.status == "error"
    assert result.error_code == "CaseReadFailed"
    assert result.analysis is None
    assert retriever.requests == reasoner.inputs == []
    assert result.model_attempts == result.retrieval_rounds == 0
    assert "private-" not in result.model_dump_json()


def test_current_case_read_exception_after_retrieval_does_not_retry_or_leak():
    state = CaseState(case_id=CASE_ID, case_revision=1)
    read_failed = False

    def current_case(_):
        if read_failed:
            raise RuntimeError("private-storage-error-marker")
        return state

    class ReadFailureRetriever(FakeRetriever):
        def search(self, request):
            nonlocal read_failed
            response = super().search(request)
            read_failed = True
            return response

    retriever = ReadFailureRetriever([_evidence("freshness-source", "Authored offline evidence.")])
    reasoner = FakeReasoner([_answer("freshness-source")])
    result = SupportEngine(
        retriever, reasoner, snapshot_id=SNAPSHOT_ID, current_case=current_case
    ).run(state, MESSAGE)

    assert result.error_code == "CaseReadFailed"
    assert result.analysis is None
    assert result.retrieval_rounds == len(retriever.requests) == 1
    assert result.model_attempts == 0
    assert reasoner.inputs == []
    assert "private-storage-error-marker" not in result.model_dump_json()


def test_current_revision_remains_enforced_when_full_case_callback_is_also_supplied():
    state = CaseState(case_id=CASE_ID, case_revision=1)
    retriever = FakeRetriever([_evidence("freshness-source", "Unused authored evidence.")])
    reasoner = FakeReasoner([_answer("freshness-source")])
    result = SupportEngine(
        retriever,
        reasoner,
        snapshot_id=SNAPSHOT_ID,
        current_revision=lambda _: 2,
        current_case=lambda _: state,
    ).run(state, MESSAGE)

    assert result.status == "stale"
    assert result.error_code == "StaleRevision"
    assert retriever.requests == reasoner.inputs == []


def test_unchanged_sqlite_snapshot_still_produces_a_bound_proposal(tmp_path):
    tracker, state = new_case(tmp_path / "unchanged.db")
    retriever = FakeRetriever([_evidence("freshness-source", "Authored offline evidence.")])
    reasoner = FakeReasoner([_answer("freshness-source")])
    capture = ReasoningCapture(reasoner)
    result = SupportEngine(
        retriever,
        capture,
        snapshot_id=SNAPSHOT_ID,
        current_revision=lambda _: read_case(tracker).case_revision,
        current_case=lambda _: read_case(tracker),
    ).run(state, MESSAGE, run_id="fresh-run")

    assert result.status == "awaiting_approval"
    assert result.model_attempts == len(reasoner.inputs) == 1
    assert result.retrieval_rounds == len(retriever.requests) == 1
    handoff = build_handoff(result, capture.last)
    tracker.stage_proposal(handoff)
    assert tracker.read_case(CASE_ID)["pending_handoff"] == handoff.model_dump(mode="json")
    assert tracker.comments(CASE_ID) == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("code", "private-provider-code-marker"),
        ("code", {"private-provider-code-marker": "private-provider-data"}),
        ("status", "awaiting_approval"),
        ("status", "private-provider-status-marker"),
        ("status", True),
    ],
)
def test_mutated_terminal_stop_retains_one_attempt_without_retry_or_raw_details(field, value):
    stopped = ReasoningStopped("BudgetExceeded", "budget_stopped")
    setattr(stopped, field, value)
    stopped.args = ("private-provider-exception-marker",)
    retriever = FakeRetriever([_evidence("freshness-source", "Authored offline evidence.")])
    reasoner = FakeReasoner([stopped, _answer("freshness-source")])

    result = SupportEngine(retriever, reasoner, snapshot_id=SNAPSHOT_ID).run(
        CaseState(case_id=CASE_ID), MESSAGE
    )

    assert result.status == "error"
    assert result.error_code == "ReasoningUnavailable"
    assert result.analysis is None
    assert result.model_attempts == len(reasoner.inputs) == 1
    assert result.retrieval_rounds == len(retriever.requests) == 1
    assert len(reasoner.responses) == 1
    assert "private-provider" not in result.model_dump_json()


@pytest.mark.parametrize("field", ["code", "status"])
def test_unreadable_terminal_stop_fields_preserve_attempt_and_stop_safely(field):
    class UnreadableStop(ReasoningStopped):
        def __getattribute__(self, name):
            if name == field:
                raise RuntimeError("private-provider-property-marker")
            return super().__getattribute__(name)

    stopped = UnreadableStop("BudgetExceeded", "budget_stopped")
    retriever = FakeRetriever([_evidence("freshness-source", "Authored offline evidence.")])
    reasoner = FakeReasoner([stopped, _answer("freshness-source")])

    result = SupportEngine(retriever, reasoner, snapshot_id=SNAPSHOT_ID).run(
        CaseState(case_id=CASE_ID), MESSAGE
    )

    assert result.status == "error"
    assert result.error_code == "ReasoningUnavailable"
    assert result.analysis is None
    assert result.model_attempts == len(reasoner.inputs) == 1
    assert result.retrieval_rounds == len(retriever.requests) == 1
    assert len(reasoner.responses) == 1
    assert "private-provider" not in result.model_dump_json()
