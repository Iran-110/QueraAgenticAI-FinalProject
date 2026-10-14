"""Offline input legality and existing core rules, never live attack quality."""

import hashlib
import json
from pathlib import Path

import pytest

from agent_app.contracts import CaseState, EvidenceBundle, GroundedGap, GroundedPlan
from agent_app.evaluation.routes import RouteGraph
from agent_app.orchestration.engine import SupportEngine
from agent_app.reasoning.grounding import (
    GroundedReasoner,
    GroundingRejected,
    make_grounded_request,
    render_grounded_plan,
    source_content_sha256,
)
from agent_app.testing.fakes import FakeRetriever

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / "experiments/core_stability_adversarial/adversarial-packet-v1.json"
ORACLE = ROOT / "experiments/core_stability_adversarial/adversarial-oracle-v1.json"
PROPOSAL = ROOT / "experiments/core_stability_adversarial/adversarial-protocol-proposal-v1.json"


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _jobs():
    return _read(PACKET)["jobs"]


def _request(job, state=None, evidence=None):
    overrides = job["catalog_overrides"]
    return make_grounded_request(
        state or CaseState.model_validate(job["declared_current_state"]),
        job["fixture"]["turns"][0]["visible"]["message"],
        evidence or EvidenceBundle.model_validate(job["bundles"]["current"]),
        gaps=tuple(GroundedGap.model_validate(gap) for gap in overrides["gaps"]),
        conflict_groups=tuple(tuple(group) for group in overrides["conflict_groups"]),
    )


def _plan(request, decision, chunks=(), question=None):
    hits = {hit.chunk_id: hit for hit in request.evidence.hits}
    return GroundedPlan(
        context_sha256=request.context_sha256,
        decision=decision,
        sources=tuple(
            {"chunk_id": chunk, "content_sha256": source_content_sha256(hits[chunk])}
            for chunk in chunks
        ),
        question_name=question,
    )


def test_adversarial_packet_pins_sources_and_oracle_before_live():
    packet = _read(PACKET)
    oracle = _read(ORACLE)
    proposal = _read(PROPOSAL)
    assert hashlib.sha256(PACKET.read_bytes()).hexdigest() == oracle["packet_sha256"]
    for path, digest in {**packet["source_input_pins"], **proposal["input_pins"]}.items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
    assert packet["test_eligible"] is False
    assert packet["corpus_ingestion_allowed"] is False
    assert packet["real_model_calls_before_registration"] == 0
    assert oracle["human_reviewed"] is False
    assert oracle["usefulness_score"] is None


@pytest.mark.parametrize("job", _jobs(), ids=lambda job: job["job_id"])
def test_adversarial_packet_legal_current_inputs_and_routes(job):
    request = _request(job)
    graph = RouteGraph.from_fixture(job["fixture"])
    assert graph.node_ids == ("current-turn",)
    assert request.case.case_id == job["case_id"]
    assert request.case.case_revision == 1
    assert all(fact.status == "active" for fact in request.case.facts)
    assert job["fixture"]["turns"][0]["maintainer"]["decision"] == "none"
    assert job["evidence_scope"] == "exact_user_version"
    assert "initial_case_state" not in job
    known = {fact.name for fact in request.case.facts}
    assert not any(gap.kind == "user" and gap.name in known for gap in request.gaps)


def test_adversarial_packet_official_excerpts_are_byte_identical_and_authored_not_forged():
    original = _read(ROOT / "data/evaluation/dev-three-v1/evidence-v1.json")
    originals = {
        hit["chunk_id"]: hit
        for bundle in original["evidence_bundles"].values()
        for hit in bundle["hits"]
    }
    authored = set()
    for job in _jobs():
        for hit in job["bundles"]["current"]["hits"]:
            if hit["chunk_id"] in originals:
                assert hit == originals[hit["chunk_id"]]
            else:
                authored.add(hit["chunk_id"])
                assert hit["source_id"].startswith("authored:")
                assert hit["source_url"].startswith("https://fixtures.example.invalid/")
                assert hit["source_commit"] is None
                assert "developer-authored" in hit["source_span"]
    assert authored == {
        "authored-icon-injection-v1",
        "authored-enum-cause-a-v1",
        "authored-enum-cause-b-v1",
    }


@pytest.mark.parametrize("job", _jobs(), ids=lambda job: job["job_id"])
def test_adversarial_packet_positive_core_control_keeps_current_facts_and_scope(job):
    observed = []

    class Planner:
        def plan(self, request, *, context):
            observed.append(request)
            if job["pair_id"] == "icon":
                return _plan(request, "answer", ("dev-three-button-139-full",))
            if job["pair_id"] == "pilot":
                return _plan(request, "ask", question="parent_callback_code")
            return _plan(request, "escalate", ("dev-three-session-state-full",))

    state = CaseState.model_validate(job["declared_current_state"])
    bundle = EvidenceBundle.model_validate(job["bundles"]["current"])
    before = state.model_dump(mode="json")
    engine = SupportEngine(
        FakeRetriever([bundle]),
        GroundedReasoner(
            Planner(),
            request_factory=lambda case, message, evidence: _request(job, case, evidence),
            source_gap_handoff=True,
        ),
        snapshot_id=bundle.snapshot_id,
        evidence_scope=job["evidence_scope"],
    )
    result = engine.run(state, job["fixture"]["turns"][0]["visible"]["message"])
    assert result.status == "awaiting_approval"
    assert result.model_attempts == 1
    assert state.model_dump(mode="json") == before
    assert observed[0].case == state
    assert result.analysis.next_question is None or job["pair_id"] == "pilot"
    if job["pair_id"] == "pilot":
        chunks = {hit.chunk_id for hit in observed[0].evidence.hits}
        assert "dev-three-multiselect-1490-default-key" not in chunks
        assert chunks == {"dev-three-multiselect-1500-default-key", "dev-three-fragment-150-full"}
    if job["pair_id"] == "enum" and job["condition"] == "challenge":
        assert "caller-declared source conflict remains unresolved" in result.analysis.user_draft
        assert "authored-enum-cause-a-v1" in result.analysis.maintainer_summary
        assert "authored-enum-cause-b-v1" in result.analysis.maintainer_summary


def test_adversarial_packet_caller_declared_conflict_answer_is_rejected():
    job = next(job for job in _jobs() if job["job_id"] == "enum-challenge")
    request = _request(job)
    with pytest.raises(GroundingRejected, match="grounded_conflict_unresolved"):
        render_grounded_plan(
            request,
            _plan(request, "answer", ("dev-three-session-state-full",)),
            source_gap_handoff=True,
        )


def test_adversarial_packet_hash_valid_attack_quote_does_not_prove_safe_selection():
    # The semantic oracle forbids this selection. Hash binding alone accepts
    # a malicious supplied record, so this is a limitation control, not a pass
    # claim for attack resistance. Core still has no action execution channel.
    job = next(job for job in _jobs() if job["job_id"] == "icon-challenge")
    request = _request(job)
    rendered = render_grounded_plan(
        request,
        _plan(request, "answer", ("authored-icon-injection-v1",)),
        source_gap_handoff=True,
    )
    current_version = next(
        fact.value for fact in request.case.facts if fact.name == "streamlit_version"
    )
    assert current_version == "1.39.0"
    assert rendered.facts_delta == ()
    assert r"streamlit\_version: 1.39.0" in rendered.maintainer_summary
    assert "SYSTEM OVERRIDE" in rendered.user_draft
    assert _read(ORACLE)["pairs"][0]["challenge"]["forbidden_selected_chunk_ids"] == [
        "authored-icon-injection-v1"
    ]
