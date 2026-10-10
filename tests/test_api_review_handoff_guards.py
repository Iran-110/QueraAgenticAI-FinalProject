"""Adversarial offline review checks; authored sources are not a quality score."""

from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from agent_app import api
from agent_app.contracts import (
    AnalysisResult,
    CaseState,
    EvidenceBundle,
    EvidenceHit,
    EvidenceLink,
    Fact,
    ProposalHandoff,
    ReviewAttestation,
    ReviewDimension,
)
from agent_app.demo import SNAPSHOT_ID
from agent_app.orchestration.handoff import HandoffRejected
from agent_app.reasoning.grounding import make_grounded_request
from agent_app.reasoning.review import REVIEW_DIMENSIONS, validate_proposal_review
from agent_app.testing.fakes import FakeReasoner, FakeRetriever
from agent_app.tracker.dummy_tracker import DummyTracker


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(api, "_cases", {})
    monkeypatch.setattr(api, "tracker", DummyTracker())
    return TestClient(api.app)


def source(chunk="current-source", *, excerpt="Authored current-source text.", version="1.50.0"):
    return EvidenceHit(
        chunk_id=chunk,
        source_id=f"fixture:{chunk}",
        source_url="https://example.org/explicitly-authored-review-fixture",
        source_type="doc",
        source_commit="fixture-source-commit",
        source_span="Authored offline review fixture, paragraph 1",
        applicable_versions=(version,),
        excerpt=excerpt,
        score=0.8,
        score_kind="fixture_score",
    )


def bundle(*hits, retrieval_round=1, warnings=()):
    return EvidenceBundle(
        snapshot_id=SNAPSHOT_ID,
        hits=hits or (source(),),
        retrieval_round=retrieval_round,
        queries_used=("fixture source query",),
        warnings=warnings,
    )


def answer(chunk="current-source", *, rich=False):
    return AnalysisResult(
        decision="answer",
        user_draft="The authored source records this observation.",
        maintainer_summary="A fixture-only observation accompanies the proposal.",
        rationale="The selected fixture source supports the quoted observation.",
        evidence_links=(
            EvidenceLink(claim="The authored source records this observation.", chunk_id=chunk),
        ),
        facts_delta=(
            Fact(
                name="documented_observation",
                value="Authored current-source text.",
                source_ref=chunk,
                turn_id="fixture-observation",
                provenance_kind="evidence",
            ),
        )
        if rich
        else (),
        checks_suggested=("Share a minimal reproducer if the observation differs.",)
        if rich
        else (),
    )


def install(monkeypatch, retrieval, reasoning):
    monkeypatch.setattr(api, "_script", lambda _scenario: (retrieval, reasoning))


def send(client, **extra):
    response = client.post(
        "/cases/review-case/messages",
        json={"message": "Please inspect this fixture observation.", "scenario": "answer", **extra},
    )
    assert response.status_code == 200
    return response.json()


def decide(client, pending, decision="approve", **extra):
    return client.post(
        "/cases/review-case/decision",
        json={
            "proposal_id": pending["proposal_id"],
            "case_revision": pending["case_revision"],
            "decision": decision,
            **extra,
        },
    )


def current(client):
    return client.get("/cases/review-case").json()


def assert_rejected_without_release(client, pending, *, decision="approve", **extra):
    before = current(client)
    response = decide(client, pending, decision, **extra)
    assert response.status_code == 409
    assert current(client) == before
    assert all(entry["role"] != "assistant" for entry in before["log"])
    assert before["decisions"] == []
    # Diagnostic values and arbitrary source text must not escape as errors.
    assert len(response.json()["detail"]) < 200
    assert "private-source-marker" not in response.text


def test_unused_future_bundle_cannot_shadow_consumed_source_or_warnings(client, monkeypatch):
    consumed = bundle(source(excerpt="The consumed source, not a later scripted result."))
    unused = bundle(
        source(excerpt="private-source-marker from a never-consumed future result."),
        warnings=("UnusedFutureWarning",),
    )
    install(monkeypatch, [consumed, unused], [answer()])
    pending = send(client)["pending"]
    assert pending["evidence"][0]["excerpt"] == consumed.hits[0].excerpt
    assert "UnusedFutureWarning" not in pending["warnings"]
    handoff = ProposalHandoff.model_validate(pending["review_handoff"])
    assert handoff.evidence == consumed
    assert "private-source-marker" not in str(pending)


def test_refinement_exports_only_actual_final_normalized_bundle(client, monkeypatch):
    first = bundle(source("previous-source"), retrieval_round=91, warnings=("PreviousWarning",))
    final = bundle(source("final-source"), retrieval_round=92, warnings=("FinalWarning",))
    unused = bundle(source("unused-source"), warnings=("UnusedWarning",))
    retrieve_more = AnalysisResult(
        decision="retrieve_more",
        user_draft="",
        maintainer_summary="",
        rationale="An additional fixture source is needed.",
        retrieval_queries=("more specific fixture observation",),
    )
    install(monkeypatch, [first, final, unused], [retrieve_more, answer("final-source")])
    pending = send(client)["pending"]
    handoff = ProposalHandoff.model_validate(pending["review_handoff"])
    assert pending["retrieval_rounds"] == pending["model_attempts"] == 2
    assert handoff.evidence.retrieval_round == 2
    assert handoff.evidence.hits == final.hits
    assert handoff.reasoning_context.attempt_index == 2
    assert handoff.evidence.warnings == ("FinalWarning",)
    assert pending["warnings"] == ["FinalWarning"]
    assert handoff.analysis.retrieval_queries == ()
    assert [entry.chunk_id for entry in handoff.source_inventory] == ["final-source"]


def test_review_exports_post_filter_input_without_reintroducing_excluded_hits(client, monkeypatch):
    raw = bundle(
        source(),
        source("other-version", version="1.49.0"),
        source("unscoped-source").model_copy(update={"applicable_versions": ()}),
        retrieval_round=91,
    )
    install(monkeypatch, [raw], [answer()])
    engine_type = api.SupportEngine

    def exact_version_engine(*args, **kwargs):
        return engine_type(*args, **kwargs, evidence_scope="exact_user_version")

    # This deliberately exercises the existing opt-in engine policy. It does
    # not silently enable a new production filter in the HTTP demo.
    monkeypatch.setattr(api, "SupportEngine", exact_version_engine)
    pending = send(
        client,
        turn_id="known-version",
        expected_revision=0,
        reported_facts=[{"name": "streamlit_version", "value": "1.50.0"}],
    )["pending"]
    handoff = ProposalHandoff.model_validate(pending["review_handoff"])
    assert handoff.evidence.retrieval_round == 1
    assert [hit.chunk_id for hit in handoff.evidence.hits] == ["current-source", "unscoped-source"]
    assert [entry.chunk_id for entry in handoff.source_inventory] == [
        "current-source",
        "unscoped-source",
    ]
    assert "other-version" not in str(pending)


def test_full_analysis_and_uncited_source_metadata_reach_review(client, monkeypatch):
    evidence = bundle(source(), source("uncited-source", version="1.49.0"))
    analysis = answer(rich=True)
    install(monkeypatch, [evidence], [analysis])
    pending = send(
        client,
        turn_id="version-report",
        expected_revision=0,
        reported_facts=[{"name": "streamlit_version", "value": "1.50.0"}],
        checks_performed=["Verified the affected environment manually."],
    )["pending"]
    handoff = ProposalHandoff.model_validate(pending["review_handoff"])
    assert handoff.analysis == analysis
    assert pending["analysis"] == analysis.model_dump(mode="json")
    assert handoff.case.pending_proposal_id is None
    assert handoff.case.facts[0].source_ref == "user:version-report"
    assert handoff.case.checks_performed == ("Verified the affected environment manually.",)
    assert handoff.evidence == evidence
    assert len(pending["evidence"]) == 1
    assert [hit.chunk_id for hit in handoff.evidence.hits] == ["current-source", "uncited-source"]
    assert [entry.version_scope for entry in handoff.source_inventory] == [
        "exact_metadata_match",
        "historical_or_other_version",
    ]
    assert pending["evidence"][0]["source_id"] == "fixture:current-source"
    assert pending["evidence"][0]["source_commit"] == "fixture-source-commit"
    assert pending["evidence"][0]["applicable_versions"] == ["1.50.0"]
    assert pending["evidence"][0]["score"] == 0.8
    assert pending["evidence"][0]["score_kind"] == "fixture_score"
    assert pending["facts_delta"] == analysis.model_dump(mode="json")["facts_delta"]
    assert pending["checks_suggested"] == list(analysis.checks_suggested)
    assert pending["retrieval_queries"] == []
    surfaces = {surface.surface_id for surface in handoff.packet.surfaces}
    assert {"facts_delta.0", "checks_suggested.0", "evidence_links.0.claim"} <= surfaces
    assert [entry["role"] for entry in current(client)["log"]] == ["user"]
    assert current(client)["decisions"] == []


def test_delegate_mutation_cannot_rewrite_captured_review_inputs(client, monkeypatch):
    evidence = bundle(source())

    class MutatingReasoner:
        calls = 0

        def analyze(self, case, user_message, evidence, *, context):
            self.calls += 1
            object.__setattr__(case, "unknowns", ("private-source-marker",))
            object.__setattr__(evidence.hits[0], "excerpt", "private-source-marker")
            object.__setattr__(context, "run_id", "private-source-marker")
            return answer()

    reasoner = MutatingReasoner()
    retriever = FakeRetriever([evidence])
    monkeypatch.setattr(
        api,
        "_adapters",
        lambda _scenario: api.RunAdapters(retriever, reasoner, snapshot_id=SNAPSHOT_ID),
    )
    pending = send(client)["pending"]
    handoff = ProposalHandoff.model_validate(pending["review_handoff"])
    assert reasoner.calls == 1
    assert handoff.case.unknowns == ()
    assert handoff.evidence == evidence
    assert handoff.reasoning_context.run_id == pending["proposal_id"]
    assert "private-source-marker" not in str(pending)
    assert decide(client, pending).status_code == 200


def test_mechanical_review_pass_is_not_approval_authority(client, monkeypatch):
    install(monkeypatch, [bundle(source())], [answer()])
    pending = send(client)["pending"]
    handoff = ProposalHandoff.model_validate(pending["review_handoff"])
    attestation = ReviewAttestation(
        reviewer_id="fixture-only-reviewer",
        packet_sha256=handoff.packet.packet_sha256,
        disposition="approved",
        reviewed_surfaces=tuple(surface.surface_id for surface in handoff.packet.surfaces),
        dimensions=tuple(ReviewDimension(name=name, passed=True) for name in REVIEW_DIMENSIONS),
    )
    review = validate_proposal_review(
        handoff.packet,
        attestation,
        handoff.case,
        handoff.evidence,
        handoff.analysis,
        authenticated_reviewer_id="fixture-only-reviewer",
    )
    assert review.status == "pass"
    before = current(client)
    assert before["pending"] is not None
    assert before["decisions"] == []
    assert [entry["role"] for entry in before["log"]] == ["user"]
    response = decide(client, pending, review_result=review.model_dump(mode="json"))
    assert response.status_code == 422
    assert response.json() == {"detail": "RequestInvalid"}
    assert current(client) == before


@pytest.mark.parametrize("decision", ["approve", "reject", "edit"])
def test_same_revision_case_content_drift_blocks_every_decision(client, monkeypatch, decision):
    install(monkeypatch, [bundle(source())], [answer()])
    pending = send(client)["pending"]
    case = api._cases["review-case"]
    case.state = case.state.model_copy(update={"unknowns": ("new_uncommitted_unknown",)})
    extra = {"edited_draft": "An edited draft."} if decision == "edit" else {}
    assert_rejected_without_release(client, pending, decision=decision, **extra)


@pytest.mark.parametrize(
    "path, replacement",
    [
        (("user_draft",), "private-source-marker"),
        (("maintainer_summary",), "private-source-marker"),
        (("rationale",), "private-source-marker"),
        (("decision",), "escalate"),
        (("missing_info",), ["private-source-marker"]),
        (("warnings",), ["private-source-marker"]),
        (("checks_suggested",), ["private-source-marker"]),
        (("facts_delta",), []),
        (("model_attempts",), 2),
        (("retrieval_rounds",), 2),
        (("steps",), 8),
        (("synthetic",), False),
        (("edited",), True),
        (("analysis", "user_draft"), "private-source-marker"),
        (("review_handoff", "analysis", "user_draft"), "private-source-marker"),
        (("review_handoff", "evidence", "hits", 0, "excerpt"), "private-source-marker"),
        (("review_handoff", "evidence", "hits", 1, "excerpt"), "private-source-marker"),
        (("review_handoff", "packet", "packet_sha256"), "0" * 64),
        (("review_handoff", "source_inventory", 0, "content_sha256"), "0" * 64),
        (("review_handoff", "handoff_sha256"), "0" * 64),
        (("evidence", 0, "source_commit"), "private-source-marker"),
        (("evidence", 0, "applicable_versions"), ["1.49.0"]),
    ],
)
def test_pending_projection_tamper_cannot_release_a_different_proposal(
    client, monkeypatch, path, replacement
):
    install(monkeypatch, [bundle(source(), source("uncited-source"))], [answer(rich=True)])
    pending = send(client)["pending"]
    stored = api.tracker.get_session_state("review-case")["proposed_action"]
    target = stored
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement
    assert_rejected_without_release(client, pending)


def test_authoritative_handoff_damage_is_rejected_even_when_display_still_matches(
    client, monkeypatch
):
    install(monkeypatch, [bundle(source())], [answer()])
    pending = send(client)["pending"]
    case = api._cases["review-case"]
    altered = case.pending_handoff.evidence.hits[0].model_copy(
        update={"excerpt": "private-source-marker"}
    )
    case.pending_handoff = case.pending_handoff.model_copy(
        update={"evidence": case.pending_handoff.evidence.model_copy(update={"hits": (altered,)})}
    )
    assert_rejected_without_release(client, pending)


def test_edit_rebuilds_complete_review_binding_and_stale_original_cannot_be_approved(client):
    pending = send(client, scenario="ask")["pending"]
    original = ProposalHandoff.model_validate(pending["review_handoff"])
    response = decide(client, pending, "edit", edited_draft="Which Streamlit version do you use?")
    assert response.status_code == 200
    edited = response.json()["pending"]
    updated = ProposalHandoff.model_validate(edited["review_handoff"])
    assert updated.proposal_id == edited["proposal_id"] != original.proposal_id
    assert updated.handoff_sha256 != original.handoff_sha256
    assert updated.packet.packet_sha256 != original.packet.packet_sha256
    assert updated.packet.analysis_sha256 != original.packet.analysis_sha256
    assert updated.analysis.user_draft == updated.analysis.next_question == edited["user_draft"]
    assert updated.evidence == original.evidence
    assert updated.case == original.case
    assert updated.reasoning_context == original.reasoning_context
    assert decide(client, pending).status_code == 409
    assert [entry["role"] for entry in current(client)["log"]] == ["user", "system"]
    approved = decide(client, edited)
    assert approved.status_code == 200
    assert approved.json()["log"][-1]["text"] == "Which Streamlit version do you use?"


def test_identical_text_edit_still_requires_approval_for_new_proposal_id(client):
    pending = send(client, scenario="ask")["pending"]
    original = ProposalHandoff.model_validate(pending["review_handoff"])
    revised = decide(client, pending, "edit", edited_draft=pending["user_draft"]).json()["pending"]
    updated = ProposalHandoff.model_validate(revised["review_handoff"])
    assert updated.analysis == original.analysis
    assert updated.packet == original.packet
    assert updated.proposal_id != original.proposal_id
    assert updated.handoff_sha256 != original.handoff_sha256
    before = current(client)
    assert decide(client, pending).status_code == 409
    assert current(client) == before
    assert decide(client, revised).status_code == 200


def test_correction_binds_new_review_to_new_version_and_old_proposal_is_unusable(
    client, monkeypatch
):
    evidence = bundle(source(version="1.50.0"), source("other-version", version="1.49.1"))
    install(monkeypatch, [evidence], [answer()])
    first = send(
        client,
        turn_id="first-version",
        expected_revision=0,
        reported_facts=[{"name": "streamlit_version", "value": "1.50.0"}],
    )["pending"]
    original = ProposalHandoff.model_validate(first["review_handoff"])
    second = send(
        client,
        message="Correction: the affected installation uses Streamlit 1.49.1.",
        turn_id="corrected-version",
        expected_revision=1,
        reported_facts=[{"name": "streamlit_version", "value": "1.49.1"}],
    )["pending"]
    corrected = ProposalHandoff.model_validate(second["review_handoff"])
    assert corrected.case.case_revision == original.case.case_revision + 1
    assert [(fact.value, fact.status) for fact in corrected.case.facts] == [
        ("1.50.0", "superseded"),
        ("1.49.1", "active"),
    ]
    assert [entry.version_scope for entry in corrected.source_inventory] == [
        "historical_or_other_version",
        "exact_metadata_match",
    ]
    assert corrected.packet.case_sha256 != original.packet.case_sha256
    assert corrected.handoff_sha256 != original.handoff_sha256
    before = deepcopy(current(client))
    assert decide(client, first).status_code == 409
    assert current(client) == before


def test_captured_frame_does_not_depend_on_fake_reasoner_private_inputs(client, monkeypatch):
    class MinimalReasoner:
        def analyze(self, case, user_message, evidence, *, context):
            return answer()

    retriever = FakeRetriever([bundle(source())])
    monkeypatch.setattr(
        api,
        "_adapters",
        lambda _scenario: api.RunAdapters(retriever, MinimalReasoner(), snapshot_id=SNAPSHOT_ID),
    )
    pending = send(client)["pending"]
    handoff = ProposalHandoff.model_validate(pending["review_handoff"])
    assert handoff.proposal_id == pending["proposal_id"]
    assert len(retriever.requests) == 1
    assert handoff.analysis == answer()


@pytest.mark.parametrize(
    "failure", ["malformed", "wrong-case", "wrong-message", "raises", "mutated-error-code"]
)
def test_invalid_caller_grounded_supplier_stops_safely_and_replay_does_not_rerun(
    client, monkeypatch, failure
):
    evidence = bundle(source())
    retriever = FakeRetriever([evidence])
    reasoner = FakeReasoner([answer()])
    supplied = []

    def supplier():
        supplied.append(failure)
        if failure == "raises":
            raise RuntimeError("private-source-marker in an adapter exception")
        if failure == "mutated-error-code":
            error = HandoffRejected("GroundedContextMismatch")
            error.code = "private-source-marker"
            raise error
        if failure == "malformed":
            return {"untrusted": "private-source-marker"}
        case = CaseState(case_id="review-case", case_revision=1)
        if failure == "wrong-case":
            case = case.model_copy(update={"case_id": "other-case"})
        message = "A different user message." if failure == "wrong-message" else "Fixture input."
        return make_grounded_request(case, message, evidence)

    monkeypatch.setattr(
        api,
        "_adapters",
        lambda _scenario: api.RunAdapters(
            retriever,
            reasoner,
            snapshot_id=SNAPSHOT_ID,
            grounded_request_supplier=supplier,
        ),
    )
    request = {
        "message": "Fixture input.",
        "scenario": "answer",
        "turn_id": "supplier-failure-event",
        "expected_revision": 0,
    }
    response = client.post("/cases/review-case/messages", json=request)
    assert response.status_code == 200
    view = response.json()
    assert view["pending"] is None
    assert view["case_revision"] == 1
    assert view["status"] == "open"
    assert view["decisions"] == []
    assert [entry["role"] for entry in view["log"]] == ["user", "system"]
    assert "private-source-marker" not in response.text
    assert api._cases["review-case"].pending_handoff is None
    replay = client.post("/cases/review-case/messages", json=request)
    assert replay.status_code == 200
    assert replay.json()["intake"]["replayed"] is True
    assert replay.json()["log"] == view["log"]
    assert replay.json()["case_revision"] == 1
    assert replay.json()["pending"] is None
    assert len(reasoner.inputs) == len(retriever.requests) == len(supplied) == 1


@pytest.mark.parametrize("damage", ["proposal_id", "case_revision", "not-a-mapping"])
def test_malformed_tracker_projection_cannot_bypass_the_typed_guard(client, monkeypatch, damage):
    install(monkeypatch, [bundle(source())], [answer()])
    original = send(client)["pending"]
    session = api.tracker.get_session_state("review-case")
    if damage == "not-a-mapping":
        session["proposed_action"] = ["private-source-marker"]
    else:
        del session["proposed_action"][damage]
    before = deepcopy(api._cases["review-case"].log)
    rejected = decide(client, original)
    assert rejected.status_code == 409
    assert rejected.json() == {"detail": "PendingProposalMismatch"}
    assert client.get("/cases/review-case").status_code == 409
    assert session["history"] == []
    assert api._cases["review-case"].log == before
