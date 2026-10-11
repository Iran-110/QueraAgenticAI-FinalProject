"""Production core coordinator with real SQLite and offline authored ports."""

from dataclasses import asdict

import pytest

from agent_app.contracts import AnalysisResult, ReportedFact, UserTurn
from agent_app.demo import SNAPSHOT_ID, _answer, _evidence
from agent_app.orchestration.handoff import (
    HandoffRejected,
    ReasoningFrame,
    build_handoff,
    edit_handoff,
    validate_handoff,
)
from agent_app.orchestration.intake import STREAMLIT_VERSION_QUESTION
from agent_app.orchestration.service import CoreAdapters, CoreTurnService
from agent_app.testing.fakes import FakeReasoner, FakeRetriever
from agent_app.tracker.sqlite_tracker import SQLiteCaseTracker

CASE = "service-fixture"
MESSAGE = "A multiselect inside a fragment loses its saved default after the parent changes."
TOKEN = "offline-service-review-token"


def tracker(path):
    return SQLiteCaseTracker(path, reviewer_tokens={"fixture-maintainer": TOKEN})


def event(revision=0, event_id="initial", message=MESSAGE, version=None):
    return UserTurn(
        case_id=CASE,
        expected_revision=revision,
        turn_id=event_id,
        source_ref=f"user:{event_id}",
        message=message,
        reported_facts=(ReportedFact(name="streamlit_version", value=version),) if version else (),
    )


def ports(analysis=None, *, retrieval=None, reasoning=None):
    retriever = retrieval or FakeRetriever(
        [_evidence("service-source", "Authored offline source.")]
    )
    reasoner = reasoning or FakeReasoner([analysis or _answer("service-source")])
    calls = []

    def factory(case, message, run_id):
        calls.append((case.model_copy(deep=True), message, run_id))
        return CoreAdapters(retriever, reasoner, SNAPSHOT_ID)

    return factory, calls, retriever, reasoner


def review(t, handoff, decision="approve", review_id="review", **kwargs):
    return t.review(
        CASE,
        review_id=review_id,
        proposal_id=handoff.proposal_id,
        expected_revision=handoff.case.case_revision,
        expected_handoff_sha256=handoff.handoff_sha256,
        decision=decision,
        reviewer_id="fixture-maintainer",
        reviewer_token=TOKEN,
        **kwargs,
    )


class Proxy:
    def __init__(self, delegate):
        self.delegate = delegate

    def apply_turn(self, *args, **kwargs):
        return self.delegate.apply_turn(*args, **kwargs)

    def read_case(self, *args, **kwargs):
        return self.delegate.read_case(*args, **kwargs)

    def stage_proposal(self, *args, **kwargs):
        return self.delegate.stage_proposal(*args, **kwargs)


def test_fresh_turn_stages_exact_complete_handoff_and_never_approves(tmp_path):
    t = tracker(tmp_path / "fresh.db")
    factory, calls, retriever, reasoner = ports()
    outcome = CoreTurnService(t, factory).submit(event(version="1.50.0"), run_id="trusted-run")
    assert outcome.status == "proposal_staged"
    assert outcome.receipt.committed_revision == outcome.handoff.case.case_revision == 1
    assert outcome.handoff.user_message == MESSAGE
    assert outcome.handoff.reasoning_context.run_id == "trusted-run"
    assert outcome.stage_receipt.proposal_id == outcome.handoff.proposal_id
    assert not outcome.recovered_ack
    assert len(calls) == len(reasoner.inputs) == len(retriever.requests) == 1
    assert t.read_case(CASE)["pending_handoff"] == outcome.handoff.model_dump(mode="json")
    assert t.comments(CASE) == []


def test_correction_between_commit_and_read_stops_before_lazy_factory(tmp_path):
    t = tracker(tmp_path / "receipt-race.db")

    class CorrectAfterCommit(Proxy):
        def apply_turn(self, *args, **kwargs):
            receipt = super().apply_turn(*args, **kwargs)
            t.apply_turn(event(1, "correction", "Correction: version is 1.49.1.", "1.49.1"))
            return receipt

    factory, calls, retriever, reasoner = ports()
    outcome = CoreTurnService(CorrectAfterCommit(t), factory).submit(event(version="1.50.0"))
    assert outcome.status == "superseded_before_run"
    assert outcome.receipt.committed_revision == 1
    assert outcome.snapshot.state.case_revision == 2
    assert outcome.error_code == "StaleRevision"
    assert outcome.run_result is outcome.handoff is None
    assert calls == retriever.requests == reasoner.inputs == []
    assert t.read_case(CASE)["pending_handoff"] is None


def test_event_replay_after_restart_and_correction_has_no_new_ports(tmp_path):
    path = tmp_path / "replay.db"
    t = tracker(path)
    factory, calls, retriever, reasoner = ports()
    original = event(version="1.50.0")
    first = CoreTurnService(t, factory).submit(original, event_context={"scenario": "answer"})
    t.apply_turn(event(1, "correction", "Actually 1.49.1.", "1.49.1"))
    replay = CoreTurnService(tracker(path), factory).submit(
        original, event_context={"scenario": "answer"}
    )
    assert replay.status == "replay_only"
    assert replay.receipt.replayed and replay.receipt.ingress_hash == first.receipt.ingress_hash
    assert replay.receipt.committed_revision == 1
    assert replay.snapshot.state.case_revision == 2
    assert replay.handoff is replay.run_result is None
    assert len(calls) == len(retriever.requests) == len(reasoner.inputs) == 1
    conflict = CoreTurnService(t, factory).submit(original, event_context={"scenario": "ask"})
    assert conflict.status == "ingress_rejected" and conflict.error_code == "EventConflict"
    assert len(calls) == 1


def test_short_bound_reply_retains_original_problem_and_current_user_version(tmp_path):
    path = tmp_path / "reply.db"
    t = tracker(path)
    question = STREAMLIT_VERSION_QUESTION.question
    ask = AnalysisResult(
        decision="ask",
        user_draft=question,
        next_question=question,
        missing_info=("streamlit_version",),
        maintainer_summary="Version is unknown.",
        rationale="The version distinguishes documentation.",
    )
    first_factory, *_ = ports(ask)
    first = CoreTurnService(t, first_factory).submit(event())
    assert review(t, first.handoff)["status"] == "awaiting_user"
    factory, calls, retriever, reasoner = ports()
    incoming = event(1, "version-reply", "1.50.0")
    outcome = CoreTurnService(tracker(path), factory).submit(
        incoming, reply_to_proposal_id=first.handoff.proposal_id
    )
    assert outcome.status == "proposal_staged"
    assert outcome.receipt.preparation == "canonical_version_reply"
    assert MESSAGE in retriever.requests[0].queries[0]
    assert MESSAGE in reasoner.inputs[0][1]
    assert question in outcome.handoff.user_message
    assert outcome.handoff.user_message.endswith("1.50.0")
    version = outcome.handoff.case.facts[0]
    assert (version.value, version.turn_id, version.provenance_kind) == (
        "1.50.0",
        "version-reply",
        "user",
    )
    assert t.read_case(CASE)["history"][-1]["text"] == incoming.message
    replay = CoreTurnService(t, factory).submit(
        incoming, reply_to_proposal_id=first.handoff.proposal_id
    )
    assert replay.status == "replay_only" and len(calls) == 1


def test_factory_mutation_does_not_change_authoritative_reasoning_input(tmp_path):
    t = tracker(tmp_path / "factory-mutation.db")
    retriever = FakeRetriever([_evidence("service-source", "Authored source.")])
    reasoner = FakeReasoner([_answer("service-source")])

    def factory(case, message, run_id):
        object.__setattr__(case.facts[0], "value", "invalid-factory-version")
        return CoreAdapters(retriever, reasoner, SNAPSHOT_ID)

    outcome = CoreTurnService(t, factory).submit(event(version="1.50.0"))
    assert outcome.status == "proposal_staged"
    assert reasoner.inputs[0][0].facts[0].value == "1.50.0"
    assert outcome.handoff.case.facts[0].value == "1.50.0"


@pytest.mark.parametrize("phase", ["factory", "retrieval", "reasoning", "before_stage"])
def test_correction_at_each_run_boundary_never_exposes_staged_old_candidate(tmp_path, phase):
    t = tracker(tmp_path / "boundary.db")

    def correct():
        t.apply_turn(event(1, "correction", "Actually 1.49.1.", "1.49.1"))

    class CorrectingRetriever(FakeRetriever):
        def search(self, request):
            response = super().search(request)
            if phase == "retrieval":
                correct()
            return response

    class CorrectingReasoner(FakeReasoner):
        def analyze(self, *args, **kwargs):
            response = super().analyze(*args, **kwargs)
            if phase == "reasoning":
                correct()
            return response

    class CorrectingStage(Proxy):
        def stage_proposal(self, handoff):
            if phase == "before_stage":
                correct()
            return super().stage_proposal(handoff)

    retriever = CorrectingRetriever([_evidence("service-source", "Authored source.")])
    reasoner = CorrectingReasoner([_answer("service-source")])

    def factory(case, message, run_id):
        if phase == "factory":
            correct()
        return CoreAdapters(retriever, reasoner, SNAPSHOT_ID)

    outcome = CoreTurnService(CorrectingStage(t), factory).submit(event(version="1.50.0"))
    assert outcome.status != "proposal_staged" and outcome.handoff is None
    assert t.read_case(CASE)["state"]["case_revision"] == 2
    assert t.read_case(CASE)["pending_handoff"] is None
    assert t.comments(CASE) == []
    assert len(reasoner.inputs) == (1 if phase in {"reasoning", "before_stage"} else 0)
    assert len(retriever.requests) == (0 if phase == "factory" else 1)


def test_lost_stage_ack_recovers_exact_pending_without_retry(tmp_path):
    t = tracker(tmp_path / "ack.db")

    class LoseAck(Proxy):
        def stage_proposal(self, handoff):
            super().stage_proposal(handoff)
            raise ConnectionError("private adapter error must not escape")

    factory, calls, retriever, reasoner = ports()
    service = CoreTurnService(LoseAck(t), factory)
    outcome = service.submit(event())
    assert outcome.status == "proposal_staged" and outcome.recovered_ack
    assert outcome.stage_receipt is None
    assert service.recover_exact_pending(outcome.handoff) == outcome.handoff
    assert len(calls) == len(retriever.requests) == len(reasoner.inputs) == 1
    assert len([r for r in t.audit_trace(CASE) if r["event"] == "proposal_staged"]) == 1
    assert t.comments(CASE) == []
    assert "private adapter" not in str(asdict(outcome))


def test_uncommitted_or_unreadable_stage_is_not_reported_as_approval_candidate(tmp_path):
    t = tracker(tmp_path / "unknown-stage.db")

    class NoAck(Proxy):
        def stage_proposal(self, handoff):
            raise ConnectionError("private exception")

    factory, calls, retriever, reasoner = ports()
    service = CoreTurnService(NoAck(t), factory)
    original = event()
    outcome = service.submit(original)
    assert outcome.status == "staging_unknown" and outcome.handoff is None
    assert outcome.candidate_handoff is not None
    assert outcome.run_result.model_attempts == 1
    with pytest.raises(HandoffRejected, match="PendingProposalMismatch"):
        service.recover_exact_pending(outcome.candidate_handoff)
    # An ingress retry means only the event is recorded; it cannot restart a run.
    assert service.submit(original).status == "replay_only"
    assert len(calls) == len(retriever.requests) == len(reasoner.inputs) == 1
    t.stage_proposal(outcome.candidate_handoff)
    assert service.recover_exact_pending(outcome.candidate_handoff) == outcome.candidate_handoff


@pytest.mark.parametrize("change", ["edit", "approve", "correction"])
def test_staged_then_changed_before_ack_is_not_returned_for_review(tmp_path, change):
    t = tracker(tmp_path / "changed-after-stage.db")

    class ChangeAfterStage(Proxy):
        def stage_proposal(self, handoff):
            receipt = super().stage_proposal(handoff)
            if change == "edit":
                review(t, handoff, "edit", edited_draft="Edited by the maintainer.")
            elif change == "approve":
                review(t, handoff)
            else:
                t.apply_turn(event(1, "correction", "Actually 1.49.1.", "1.49.1"))
            return receipt

    factory, calls, *_ = ports()
    outcome = CoreTurnService(ChangeAfterStage(t), factory).submit(event())
    assert outcome.status == "proposal_not_pending" and outcome.handoff is None
    assert len(calls) == 1
    assert outcome.run_result.model_attempts == 1


@pytest.mark.parametrize(
    "fault", ["wrong_case", "wrong_hash", "wrong_prepared_hash", "wrong_history", "read_failure"]
)
def test_invalid_tracker_data_stops_before_adapter_setup(tmp_path, fault):
    t = tracker(tmp_path / "invalid-data.db")

    class InvalidData(Proxy):
        def apply_turn(self, *args, **kwargs):
            receipt = super().apply_turn(*args, **kwargs)
            if fault == "wrong_hash":
                receipt["ingress_hash"] = "0" * 64
            if fault == "wrong_prepared_hash":
                receipt["prepared_hash"] = "0" * 64
            return receipt

        def read_case(self, case_id):
            if fault == "read_failure":
                raise RuntimeError("sensitive storage error")
            view = super().read_case(case_id)
            if fault == "wrong_case":
                view["state"]["case_id"] = "another-case"
            if fault == "wrong_history":
                view["history"][-1]["text"] = "A different message."
            return view

    factory, calls, retriever, reasoner = ports()
    outcome = CoreTurnService(InvalidData(t), factory).submit(event())
    assert outcome.status in {"core_stopped", "ingress_unknown"}
    assert outcome.handoff is outcome.run_result is None
    assert calls == retriever.requests == reasoner.inputs == []
    assert "sensitive storage" not in str(outcome)


def test_ingress_lost_ack_only_allows_event_replay_not_automatic_reasoning(tmp_path):
    t = tracker(tmp_path / "ingress-ack.db")

    class LoseIngressAck(Proxy):
        def apply_turn(self, *args, **kwargs):
            super().apply_turn(*args, **kwargs)
            raise ConnectionError("private ingress error")

    factory, calls, *_ = ports()
    original = event()
    first = CoreTurnService(LoseIngressAck(t), factory).submit(original)
    assert first.status == "ingress_unknown" and first.receipt is None
    replay = CoreTurnService(t, factory).submit(original)
    assert replay.status == "replay_only" and replay.receipt.replayed
    assert calls == [] and t.comments(CASE) == []


def test_setup_failure_and_model_stop_preserve_ingress_without_paid_resume(tmp_path):
    t = tracker(tmp_path / "setup.db")
    setups = []

    def unavailable(*args):
        setups.append(True)
        raise RuntimeError("private credential-shaped setup data")

    service = CoreTurnService(t, unavailable)
    first = service.submit(event())
    assert first.status == "core_stopped" and first.error_code == "AdapterSetupFailed"
    assert first.receipt.committed_revision == 1
    assert service.submit(event()).status == "replay_only"
    assert len(setups) == 1
    assert "credential-shaped" not in str(first)
    factory, _, _, reasoner = ports(retrieval=FakeRetriever([RuntimeError("private retrieval")]))
    second = CoreTurnService(t, factory).submit(event(1, "next", "Please continue."))
    assert second.status == "core_stopped" and second.error_code == "RetrievalUnavailable"
    assert second.run_result.model_attempts == 0
    assert reasoner.inputs == []


def test_recovery_rejects_other_identity_and_content_without_ports(tmp_path):
    t = tracker(tmp_path / "recover.db")
    factory, calls, *_ = ports()
    service = CoreTurnService(t, factory)
    outcome = service.submit(event())
    analysis = outcome.handoff.analysis.model_copy(update={"user_draft": "Different draft."})
    altered = edit_handoff(outcome.handoff, "other-id", analysis)
    with pytest.raises(HandoffRejected, match="PendingProposalMismatch"):
        service.recover_exact_pending(altered)
    changed = build_handoff(
        outcome.run_result.model_copy(update={"analysis": analysis}),
        ReasoningFrame(
            outcome.handoff.case,
            outcome.handoff.user_message,
            outcome.handoff.evidence,
            outcome.handoff.reasoning_context,
        ),
    )
    with pytest.raises(HandoffRejected, match="HandoffMismatch"):
        service.recover_exact_pending(changed)
    assert len(calls) == 1


def test_invalid_input_does_not_create_a_tracker_event(tmp_path):
    t = tracker(tmp_path / "bad-caller.db")
    factory, calls, *_ = ports()
    with pytest.raises(ValueError, match="Invalid core turn input"):
        CoreTurnService(t, factory).submit(event(), event_context={"scenario": object()})
    with pytest.raises(ValueError, match="Invalid core turn input"):
        CoreTurnService(t, factory).submit(event(), run_id="bad run id")
    assert t.read_case(CASE)["state"]["case_revision"] == 0
    assert calls == []
    with pytest.raises(ValueError, match="Invalid core service configuration"):
        CoreTurnService(t, None)
    assert t.read_case(CASE)["state"]["case_revision"] == 0


def test_nested_bypassed_input_extras_reject_before_tracker_commit(tmp_path):
    t = tracker(tmp_path / "nested-extra.db")
    incoming = event(version="1.50.0")
    broken = incoming.model_copy(
        update={
            "reported_facts": (
                incoming.reported_facts[0].model_copy(update={"private_extra": "never-export"}),
            )
        }
    )
    factory, calls, *_ = ports()
    with pytest.raises(ValueError, match="Invalid core turn input"):
        CoreTurnService(t, factory).submit(broken)
    assert t.read_case(CASE)["state"]["case_revision"] == 0 and calls == []


def test_nested_handoff_attributes_are_not_silently_scrubbed_on_recovery(tmp_path):
    t = tracker(tmp_path / "nested-handoff.db")
    factory, calls, *_ = ports()
    service = CoreTurnService(t, factory)
    outcome = service.submit(event(version="1.50.0"))
    broken_case = outcome.handoff.case.model_copy(
        update={
            "facts": (
                outcome.handoff.case.facts[0].model_copy(update={"private_extra": "never-export"}),
            )
        }
    )
    broken = outcome.handoff.model_copy(update={"case": broken_case})
    with pytest.raises(HandoffRejected, match="InvalidHandoffInput"):
        validate_handoff(broken)
    with pytest.raises(HandoffRejected, match="InvalidHandoffInput"):
        service.recover_exact_pending(broken)
    assert len(calls) == 1


def test_grounded_supplier_diagnostics_are_allowlisted_and_attempts_retained(tmp_path):
    t = tracker(tmp_path / "supplier-error.db")
    factory, calls, retriever, reasoner = ports()

    def broken_supplier():
        error = HandoffRejected("HandoffMismatch")
        error.code = "private-supplier-error-marker"
        raise error

    def supplier_factory(case, message, run_id):
        factory(case, message, run_id)
        return CoreAdapters(retriever, reasoner, SNAPSHOT_ID, broken_supplier)

    outcome = CoreTurnService(t, supplier_factory).submit(event())
    assert outcome.status == "core_stopped" and outcome.error_code == "InvalidHandoffInput"
    assert outcome.run_result.model_attempts == outcome.run_result.retrieval_rounds == 1
    assert "private-supplier-error-marker" not in str(asdict(outcome))
    assert outcome.handoff is None and t.read_case(CASE)["pending_handoff"] is None
    assert len(calls) == 1


def test_unreadable_post_stage_confirmation_preserves_only_recovery_candidate(tmp_path):
    t = tracker(tmp_path / "unreadable-ack.db")

    class UnreadableAfterStage(Proxy):
        staged = False

        def stage_proposal(self, handoff):
            receipt = super().stage_proposal(handoff)
            self.staged = True
            return receipt

        def read_case(self, case_id):
            if self.staged:
                raise ConnectionError("private read error")
            return super().read_case(case_id)

    factory, calls, *_ = ports()
    outcome = CoreTurnService(UnreadableAfterStage(t), factory).submit(event())
    assert outcome.status == "staging_unknown" and outcome.error_code == "CaseReadFailed"
    assert outcome.handoff is None and outcome.candidate_handoff is not None
    assert (
        CoreTurnService(t, factory).recover_exact_pending(outcome.candidate_handoff)
        == outcome.candidate_handoff
    )
    assert len(calls) == 1 and t.comments(CASE) == []
