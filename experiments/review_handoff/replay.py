"""Registered offline C3 handoff replay; authored decisions are not model quality."""

import argparse
import copy
import hashlib
import html
import io
import json
import re
import subprocess
import sys
import tarfile
import tempfile
from importlib.metadata import version as metadata_version
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import NAMESPACE_URL, uuid5

from fastapi.testclient import TestClient

from agent_app import api
from agent_app.contracts import (
    AnalysisResult,
    CaseState,
    EvidenceBundle,
    GroundedGap,
    GroundedPlan,
    GroundedRequest,
    GroundedSourceRef,
    ProposalHandoff,
    ReviewAttestation,
    ReviewDimension,
    RunResult,
)
from agent_app.orchestration import engine as engine_module
from agent_app.orchestration.handoff import (
    HandoffRejected,
    ReasoningCapture,
    ReasoningFrame,
    build_handoff,
    ensure_handoff_current,
    validate_handoff,
)
from agent_app.reasoning.grounding import (
    GroundedReasoner,
    make_grounded_request,
    render_grounded_plan,
    source_content_sha256,
    source_scope,
)
from agent_app.reasoning.review import REVIEW_DIMENSIONS, validate_proposal_review
from agent_app.testing.fakes import FakeRetriever
from agent_app.tracker.dummy_tracker import DummyTracker

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = Path(__file__).with_name("case-current-state-latest-evidence.json")
FIXTURE_SHA256 = "00af34231e7e4b252bdd8e88bf815d20249135f976cef7cc358ebc34d2e110d9"
REGISTRATION_COMMIT = "b085f7d"
EXPECTED_PATH = Path(__file__).with_name("expected-analysis-v1.json")
EXPECTED_SHA256 = "81e45b0212cd5f9f27a88b0bced255d74dcdc6da9fb7bdf6bdc3ce63bf0cdadc"
EXPECTED_REGISTRATION_COMMIT = "057a4d3"
CODE_PATHS = (
    "experiments/review_handoff/replay.py",
    "experiments/review_handoff/expected-analysis-v1.json",
    "experiments/review_handoff/results-review-handoff-v1.json",
    "src/agent_app/api.py",
    "src/agent_app/contracts.py",
    "src/agent_app/orchestration/engine.py",
    "src/agent_app/orchestration/handoff.py",
    "src/agent_app/orchestration/intake.py",
    "src/agent_app/orchestration/turns.py",
    "src/agent_app/orchestration/ports.py",
    "src/agent_app/reasoning/grounding.py",
    "src/agent_app/reasoning/review.py",
    "src/agent_app/reasoning/output.py",
    "src/agent_app/reasoning/code_checks.py",
    "src/agent_app/reasoning/proposal_checks.py",
    "src/agent_app/testing/fakes.py",
    "src/agent_app/tracker/dummy_tracker.py",
    "uv.lock",
)


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def code_manifest() -> dict[str, str]:
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in CODE_PATHS}


def load_fixture(path: Path = FIXTURE_PATH) -> dict[str, Any]:
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != FIXTURE_SHA256:
        raise ValueError("RegisteredHandoffFixtureMismatch")
    fixture = json.loads(payload)
    provenance = fixture["provenance"]
    old_path = ROOT / provenance["intake_fixture"]
    if hashlib.sha256(old_path.read_bytes()).hexdigest() != provenance["intake_fixture_sha256"]:
        raise ValueError("RegisteredSourceFixtureMismatch")
    old = json.loads(old_path.read_bytes())
    assert (
        fixture["evidence_bundles"]["official-mixed"]
        == old["evidence_bundles"]["official-mixed-v8"]
    )
    assert fixture["execution_boundary"]["offline_only"]
    assert fixture["execution_boundary"]["paid_requests"] == 0
    assert not fixture["execution_boundary"]["quality_claim"]
    assert len(fixture["turns"]) == 4
    CaseState.model_validate(fixture["initial_case"])
    for bundle in fixture["evidence_bundles"].values():
        EvidenceBundle.model_validate(bundle)
    for turn in fixture["turns"]:
        api.MessageRequest.model_validate(
            {
                **turn["wire_request"],
                **(
                    {"reply_to_proposal_id": "registered-question"}
                    if "reply_to_proposal_id" in turn["wire_request"]
                    else {}
                ),
            }
        )
        for field in (
            "known_information_after_user_input",
            "user_clarifiable_gaps",
            "documentation_or_evidence_gaps",
            "acceptable_decisions",
            "claim_acceptance",
            "question_acceptance",
        ):
            assert turn["inventory"][field]
    return fixture


def _active(case: CaseState) -> dict[str, str]:
    return {
        fact.name: fact.value
        for fact in case.facts
        if fact.status == "active" and fact.provenance_kind == "user"
    }


def load_expected_analyses(path: Path = EXPECTED_PATH) -> dict[str, AnalysisResult]:
    """Posthoc source-inspected exact outputs, independently frozen before v2.

    This catches shared-renderer additions for these five controlled outputs.
    It is not a semantic judge, human gold or a pre-first-replay output oracle.
    """
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != EXPECTED_SHA256:
        raise ValueError("ReviewedAnalysisFixtureMismatch")
    oracle = json.loads(payload)
    assert oracle["introduced_after_first_replay"] is True
    assert oracle["scenario_preregistration_commit"] == REGISTRATION_COMMIT
    source_receipt = (ROOT / oracle["source_receipt"]).read_bytes()
    assert hashlib.sha256(source_receipt).hexdigest() == oracle["source_receipt_file_sha256"]
    assert json.loads(source_receipt)["receipt_sha256"] == oracle["source_receipt_sha256"]
    assert set(oracle["analyses"]) == {
        "handoff-1",
        "handoff-2",
        "handoff-3",
        "handoff-4",
        "conflict-control",
    }
    return {
        name: AnalysisResult.model_validate(value) for name, value in oracle["analyses"].items()
    }


def catalog(
    fixture: dict[str, Any], case: CaseState, message: str, evidence: EvidenceBundle
) -> GroundedRequest:
    """Caller preparation uses current explicit facts and the actual latest bundle."""
    active = _active(case)
    questions = {item["name"]: item["question"] for item in fixture["question_catalog"]}
    gaps = []
    for name, description, necessity in (
        (
            "streamlit_version",
            "The installed Streamlit version is unknown.",
            "The user can inspect the affected package version to select applicable records.",
        ),
        (
            "parent_callback_code",
            "The parent selector callback and state-update path are not supplied.",
            "The failing full-app path differs from the working reduction; its code can narrow it.",
        ),
    ):
        if name not in active:
            gaps.append(
                GroundedGap(
                    name=name,
                    kind="user",
                    description=description,
                    necessity=necessity,
                    question=questions[name],
                )
            )
    sources = {item["name"]: item for item in fixture["source_gap_catalog"]}
    if not any(source_scope(case, hit) == "exact_metadata_match" for hit in evidence.hits):
        gaps.append(GroundedGap.model_validate(sources["exact_version_documentation"]))
    gaps.append(GroundedGap.model_validate(sources["full_app_cause_and_fix"]))
    if "release-150-multiselect-key-identity-v8" not in {hit.chunk_id for hit in evidence.hits}:
        gaps.append(GroundedGap.model_validate(sources["pinned_release_record"]))
    return make_grounded_request(case, message, evidence, gaps=tuple(gaps))


class AuthoredPlanner:
    """A fixture picker, never an independent model or a semantic judge."""

    def __init__(self, sequence: list[dict[str, Any]]) -> None:
        self.sequence = copy.deepcopy(sequence)
        self.calls: list[dict[str, Any]] = []

    def plan(self, request, *, context):
        index = len(self.calls)
        self.calls.append(
            {"request": request.model_dump(mode="json"), "context": context.model_dump(mode="json")}
        )
        template = self.sequence[index]
        hits = {hit.chunk_id: hit for hit in request.evidence.hits}
        return GroundedPlan(
            context_sha256=request.context_sha256,
            decision=template["decision"],
            sources=tuple(
                GroundedSourceRef(chunk_id=name, content_sha256=source_content_sha256(hits[name]))
                for name in template.get("source_ids", ())
            ),
            question_name=template.get("question_name"),
            retrieval_queries=tuple(template.get("retrieval_queries", ())),
        )


def _assert_handoff(handoff: ProposalHandoff, expected: dict[str, Any]) -> None:
    validate_handoff(handoff)
    request = handoff.grounded_request
    assert request is not None, "Prepared catalog is absent from the handoff"
    assert request.case == handoff.case and request.evidence == handoff.evidence
    assert request.user_message == handoff.user_message
    assert handoff.case.pending_proposal_id is None
    assert handoff.analysis.decision == expected["decision"]
    assert handoff.case.case_revision == expected["case_revision"]
    assert _active(handoff.case).get("streamlit_version") == expected["active_user_version"]
    assert sorted(gap.name for gap in request.gaps if gap.kind == "source") == sorted(
        expected["source_gaps"]
    )
    assert any(gap.name == "streamlit_version" for gap in request.gaps) == (
        expected["active_user_version"] is None
    )
    assert (
        sum(item.version_scope == "exact_metadata_match" for item in handoff.source_inventory)
        == expected["exact_version_source_count"]
    )
    assert len(handoff.source_inventory) == len(handoff.evidence.hits)
    for item, hit in zip(handoff.source_inventory, handoff.evidence.hits, strict=True):
        assert item.chunk_id == hit.chunk_id
        assert item.content_sha256 == source_content_sha256(hit)
        assert item.version_scope == source_scope(handoff.case, hit)
    assert handoff.reasoning_context.attempt_index == expected["model_attempts"]
    assert handoff.evidence.retrieval_round == expected["retrieval_rounds"]


def _rejected(call, code: str) -> None:
    try:
        call()
    except HandoffRejected as error:
        assert error.code == code
    else:
        raise AssertionError("Changed or stale handoff was accepted")


def _assert_whole_quotes(handoff: ProposalHandoff, selected_ids: set[str]) -> None:
    """Independently inspect quoted bytes; rerendering alone shares renderer bugs."""
    analysis = handoff.analysis
    assert {link.chunk_id for link in analysis.evidence_links} == selected_ids
    hits = {hit.chunk_id: hit for hit in handoff.evidence.hits}
    surfaces = [analysis.maintainer_summary]
    if analysis.decision == "answer":
        surfaces.append(analysis.user_draft)
    for text in surfaces:
        groups = re.findall(r"(?:^>[^\n]*(?:\n|$))+", text, flags=re.MULTILINE)
        quoted = []
        for group in groups:
            lines = [line[2:] if line.startswith("> ") else line[1:] for line in group.splitlines()]
            rendered = "\n".join(lines)
            rendered = re.sub(r"\\([\\`*_{}\[\]()#!|~])", r"\1", rendered)
            quoted.append(html.unescape(rendered))
        for chunk_id in selected_ids:
            assert hits[chunk_id].excerpt in quoted, "Whole registered source excerpt missing"


def _review(handoff: ProposalHandoff) -> ReviewAttestation:
    # Authored positive mechanics only; this fixture does not authenticate a person
    # or discover material claims. Approval remains a separate tracker action.
    return ReviewAttestation(
        reviewer_id="offline-authored-reviewer",
        packet_sha256=handoff.packet.packet_sha256,
        disposition="approved",
        reviewed_surfaces=tuple(surface.surface_id for surface in handoff.packet.surfaces),
        dimensions=tuple(ReviewDimension(name=name, passed=True) for name in REVIEW_DIMENSIONS),
    )


def baseline_probe(fixture: dict[str, Any]) -> dict[str, Any]:
    """Import the actual old code from Git, preserving the shared checkout."""
    revision = fixture["baseline_git_commit"]
    archive = subprocess.run(
        ["git", "archive", revision, "src"], cwd=ROOT, check=True, capture_output=True
    ).stdout
    with tempfile.TemporaryDirectory(prefix="core-handoff-baseline-") as directory:
        with tarfile.open(fileobj=io.BytesIO(archive)) as handle:
            handle.extractall(directory, filter="data")
        script = r"""
import hashlib,json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from agent_app import api
from agent_app.contracts import AnalysisResult,CaseState,EvidenceBundle,EvidenceLink,GroundedGap,GroundedPlan,RunResult
from agent_app.reasoning.grounding import make_grounded_request,render_grounded_plan
from agent_app.reasoning.review import build_proposal_review_packet
fixture=json.loads(sys.stdin.read())
bundle=EvidenceBundle.model_validate(fixture['evidence_bundles']['official-mixed'])
hit=bundle.hits[3]
analysis=AnalysisResult(decision='answer',user_draft='Attributed record only.',maintainer_summary='Complete review required.',rationale='No app cause established.',evidence_links=(EvidenceLink(claim='Attributed record',chunk_id=hit.chunk_id),),checks_suggested=('Inspect the version mismatch.',))
result=RunResult(run_id='baseline-proposal',case_id='baseline-case',case_revision=1,status='awaiting_approval',analysis=analysis)
proposal=api._proposal(result,[bundle])
case=CaseState(case_id='baseline-case')
gap=GroundedGap.model_validate(fixture['source_gap_catalog'][0])
requests=[make_grounded_request(case,'report',bundle),make_grounded_request(case,'report',bundle,gaps=(gap,))]
outputs=[render_grounded_plan(req,GroundedPlan(context_sha256=req.context_sha256,decision='escalate')) for req in requests]
print(json.dumps({'api_source_sha256':hashlib.sha256(Path(api.__file__).read_bytes()).hexdigest(),'missing_source_fields':sorted(set(hit.model_dump(mode='json'))-set(proposal['evidence'][0])),'missing_analysis_fields':sorted(set(analysis.model_dump(mode='json'))-set(proposal)),'complete_case_absent':'case' not in proposal,'latest_bundle_absent':'latest_evidence' not in proposal,'review_handoff_absent':'review_handoff' not in proposal,'source_gap_context_changes':requests[0].context_sha256!=requests[1].context_sha256,'source_gap_analysis_unchanged':outputs[0]==outputs[1],'source_gap_packet_unchanged':build_proposal_review_packet(case,bundle,outputs[0])==build_proposal_review_packet(case,bundle,outputs[1])}))
"""
        completed = subprocess.run(
            [sys.executable, "-c", script, str(Path(directory) / "src")],
            input=json.dumps(fixture),
            text=True,
            capture_output=True,
            check=True,
            cwd=ROOT,
        )
    observation = json.loads(completed.stdout)
    assert observation["missing_source_fields"] == [
        "applicable_versions",
        "score",
        "score_kind",
        "source_commit",
        "source_id",
    ]
    assert observation["missing_analysis_fields"] == [
        "checks_suggested",
        "evidence_links",
        "facts_delta",
        "retrieval_queries",
    ]
    assert observation["complete_case_absent"] and observation["latest_bundle_absent"]
    assert observation["review_handoff_absent"]
    assert observation["source_gap_context_changes"]
    assert (
        observation["source_gap_analysis_unchanged"] and observation["source_gap_packet_unchanged"]
    )
    return {"git_commit": revision, "actual_git_archive_import": True, **observation}


def _conflict_control(
    fixture: dict[str, Any], expected_analyses: dict[str, AnalysisResult]
) -> dict[str, Any]:
    probe = next(
        p for p in fixture["registered_probes"] if p["id"] == "caller_declared_conflict_control"
    )
    case = CaseState(case_id="conflict-routing-control")
    bundle = EvidenceBundle.model_validate(fixture["evidence_bundles"]["official-mixed"])
    prepared = []

    def factory(current, message, evidence):
        base = catalog(fixture, current, message, evidence)
        request = make_grounded_request(
            current,
            message,
            evidence,
            gaps=base.gaps,
            conflict_groups=(tuple(probe["group"]),),
        )
        prepared.append(request)
        return request

    planner = AuthoredPlanner(
        [
            {"decision": "answer", "source_ids": [probe["group"][0]]},
            {"decision": "escalate", "source_ids": [probe["group"][0]]},
        ]
    )
    capture = ReasoningCapture(GroundedReasoner(planner, request_factory=factory))
    result = engine_module.SupportEngine(
        FakeRetriever([bundle]), capture, snapshot_id=bundle.snapshot_id
    ).run(
        case,
        "Authored conflict-routing control; no actual document contradiction is claimed.",
        run_id="conflict-routing-proposal",
    )
    assert result.status == "awaiting_approval" and result.analysis.decision == "escalate"
    assert result.model_attempts == probe["expected_attempts"]
    assert result.retrieval_rounds == probe["expected_retrieval_rounds"]
    assert result.output_issues[0].code == "grounded_conflict_unresolved"
    assert set(probe["group"]) == {link.chunk_id for link in result.analysis.evidence_links}
    handoff = build_handoff(result, capture.last, grounded_request=prepared[-1])
    validate_handoff(handoff)
    _assert_whole_quotes(handoff, set(probe["group"]))
    assert handoff.analysis == expected_analyses["conflict-control"], (
        "Reviewed complete analysis mismatch"
    )
    return {
        "control_type": probe["type"],
        "model_attempts": result.model_attempts,
        "retrieval_rounds": result.retrieval_rounds,
        "rejected_answer_code": result.output_issues[0].code,
        "final_handoff": handoff.model_dump(mode="json"),
    }


def replay_handoff(path: Path = FIXTURE_PATH) -> dict[str, Any]:
    if not __debug__:
        raise RuntimeError("AssertionChecksDisabled")
    fixture = load_fixture(path)
    expected_analyses = load_expected_analyses()
    code_at_start = code_manifest()
    baseline = baseline_probe(fixture)
    case_id = fixture["initial_case"]["case_id"]
    runs = []
    turn_index = 0
    prepared_question = None
    observations = []
    handoffs = []
    probes = []

    def adapters(_scenario):
        turn = fixture["turns"][turn_index]
        planner = AuthoredPlanner(turn["authored_plan_sequence"])
        prepared = []

        def factory(current, message, evidence):
            request = catalog(fixture, current, message, evidence)
            prepared.append(request)
            return request

        retriever = FakeRetriever(
            [
                EvidenceBundle.model_validate(fixture["evidence_bundles"][name])
                for name in turn["bundles"]
            ]
        )
        reasoner = GroundedReasoner(planner, request_factory=factory)
        runs.append({"planner": planner, "retriever": retriever, "prepared": prepared})
        return api.RunAdapters(
            retriever,
            reasoner,
            snapshot_id=fixture["evidence_bundles"]["official-mixed"]["snapshot_id"],
            grounded_request_supplier=lambda: prepared[-1] if prepared else None,
        )

    with (
        patch.object(api, "_cases", {}),
        patch.object(api, "tracker", DummyTracker()),
        patch.object(api, "_adapters", adapters),
        patch.object(
            engine_module,
            "uuid4",
            lambda: uuid5(
                NAMESPACE_URL, fixture["fixture_id"] + ":" + fixture["turns"][turn_index]["id"]
            ),
        ),
        patch.object(api, "uuid4", lambda: uuid5(NAMESPACE_URL, fixture["fixture_id"] + ":edit")),
        TestClient(api.app) as client,
    ):
        for turn_index, turn in enumerate(fixture["turns"]):
            request = copy.deepcopy(turn["wire_request"])
            if "reply_to_proposal_id" in request:
                assert prepared_question is not None
                request["reply_to_proposal_id"] = prepared_question
            before = client.get(f"/cases/{case_id}").json()
            response = client.post(f"/cases/{case_id}/messages", json=request)
            assert response.status_code == 200, "Registered HTTP turn was rejected"
            view = response.json()
            assert view["pending"] is not None, "Final proposal was lost"
            handoff = ProposalHandoff.model_validate(view["pending"]["review_handoff"])
            _assert_handoff(handoff, turn["expected"])
            # Check the entire registered output, not merely JSON or citation
            # IDs. This verifies authored-plan fidelity, not arbitrary claims.
            final_plan = AuthoredPlanner([turn["authored_plan_sequence"][-1]]).plan(
                handoff.grounded_request, context=handoff.reasoning_context
            )
            expected_analysis = render_grounded_plan(handoff.grounded_request, final_plan)
            assert handoff.analysis == expected_analysis, "Registered rendered output changed"
            _assert_whole_quotes(
                handoff, set(turn["authored_plan_sequence"][-1].get("source_ids", ()))
            )
            assert handoff.analysis == expected_analyses[turn["id"]], (
                "Reviewed complete analysis mismatch"
            )
            for name in ("user_draft", "maintainer_summary", "rationale", "next_question"):
                assert view["pending"][name] == getattr(handoff.analysis, name)
            assert handoff == validate_handoff(handoff)
            assert handoff.grounded_request == runs[-1]["prepared"][-1]
            ensure_handoff_current(handoff, api._cases[case_id].state, handoff.proposal_id)
            assistants_before = sum(item["role"] == "assistant" for item in before["log"])
            assert sum(item["role"] == "assistant" for item in view["log"]) == assistants_before
            final_bundle = fixture["evidence_bundles"][turn["bundles"][-1]]
            assert handoff.evidence == EvidenceBundle.model_validate(
                {**final_bundle, "retrieval_round": turn["expected"]["retrieval_rounds"]}
            ), "Review included an earlier retrieval bundle"
            if turn_index:
                previous = handoffs[-1]
                _rejected(
                    lambda previous=previous: ensure_handoff_current(
                        previous, api._cases[case_id].state, previous.proposal_id
                    ),
                    "StaleRevision",
                )
                rejected = client.post(
                    f"/cases/{case_id}/decision",
                    json={
                        "proposal_id": previous.proposal_id,
                        "case_revision": previous.case.case_revision,
                        "decision": "approve",
                    },
                )
                assert rejected.status_code == 409
            current = client.get(f"/cases/{case_id}").json()
            replayed = client.post(f"/cases/{case_id}/messages", json=request)
            assert replayed.status_code == 200 and replayed.json()["intake"]["replayed"]
            assert client.get(f"/cases/{case_id}").json() == current
            assert len(runs) == turn_index + 1
            assert len(runs[-1]["planner"].calls) == turn["expected"]["model_attempts"]
            if turn["expected"]["approved"]:
                approved = client.post(
                    f"/cases/{case_id}/decision",
                    json={
                        "proposal_id": handoff.proposal_id,
                        "case_revision": handoff.case.case_revision,
                        "decision": "approve",
                    },
                )
                assert approved.status_code == 200
                assert approved.json()["log"][-1]["text"] == handoff.analysis.user_draft
                if handoff.analysis.decision == "ask":
                    prepared_question = handoff.proposal_id
            handoffs.append(handoff)
            observations.append(
                {
                    "turn_id": turn["id"],
                    "wire_request": request,
                    "inventory_sha256": _digest(turn["inventory"]),
                    "intake": view["intake"],
                    "handoff": handoff.model_dump(mode="json"),
                    "planner_calls": runs[-1]["planner"].calls,
                    "retrieval_requests": [
                        item.model_dump(mode="json") for item in runs[-1]["retriever"].requests
                    ],
                }
            )

        corrected = handoffs[2]
        assert corrected.analysis.decision == "escalate"
        assert "release-150-multiselect-key-identity-v8" not in {
            hit.chunk_id for hit in corrected.evidence.hits
        }
        _rejected(
            lambda: validate_handoff(
                corrected.model_copy(update={"evidence": handoffs[1].evidence})
            ),
            "GroundedContextMismatch",
        )
        changed_hit = corrected.evidence.hits[0].model_copy(
            update={"excerpt": "Changed source under the same chunk identity."}
        )
        changed_bundle = corrected.evidence.model_copy(
            update={"hits": (changed_hit, *corrected.evidence.hits[1:])}
        )
        _rejected(
            lambda: validate_handoff(corrected.model_copy(update={"evidence": changed_bundle})),
            "GroundedContextMismatch",
        )
        altered_gaps = tuple(
            gap.model_copy(update={"description": "Changed caller-curated source-gap description."})
            if gap.kind == "source" and gap.name == "exact_version_documentation"
            else gap
            for gap in corrected.grounded_request.gaps
        )
        updated_request = make_grounded_request(
            corrected.case, corrected.user_message, corrected.evidence, gaps=altered_gaps
        )
        _rejected(
            lambda: validate_handoff(
                corrected.model_copy(update={"grounded_request": updated_request})
            ),
            "HandoffMismatch",
        )
        # Construct the legitimate new envelope with the same final analysis.
        # A legacy packet binds analysis/case/evidence; the outer handoff adds catalog.

        rebuilt = build_handoff(
            RunResult(
                run_id=corrected.proposal_id,
                case_id=corrected.case.case_id,
                case_revision=corrected.case.case_revision,
                status="awaiting_approval",
                analysis=corrected.analysis,
                model_attempts=2,
                retrieval_rounds=2,
            ),
            ReasoningFrame(
                corrected.case,
                corrected.user_message,
                corrected.evidence,
                corrected.reasoning_context,
            ),
            grounded_request=updated_request,
        )
        assert rebuilt.analysis == corrected.analysis and rebuilt.packet == corrected.packet
        assert rebuilt.handoff_sha256 != corrected.handoff_sha256
        assert rebuilt.grounded_request.context_sha256 != corrected.grounded_request.context_sha256
        probes.append(
            {
                "probe": "same_analysis_new_source_gap",
                "analysis_unchanged": True,
                "legacy_packet_unchanged": True,
                "outer_handoff_changes": True,
                "catalog_substitution_rejected": True,
            }
        )

        old = handoffs[-1]
        edited = client.post(
            f"/cases/{case_id}/decision",
            json={
                "proposal_id": old.proposal_id,
                "case_revision": old.case.case_revision,
                "decision": "edit",
                "edited_draft": "Please provide the installed version and relevant log.",
            },
        )
        assert edited.status_code == 200
        fresh = ProposalHandoff.model_validate(edited.json()["pending"]["review_handoff"])
        validate_handoff(fresh)
        assert fresh.proposal_id != old.proposal_id and fresh.analysis != old.analysis
        assert fresh.handoff_sha256 != old.handoff_sha256
        assert fresh.packet.packet_sha256 != old.packet.packet_sha256
        rejected = client.post(
            f"/cases/{case_id}/decision",
            json={
                "proposal_id": old.proposal_id,
                "case_revision": old.case.case_revision,
                "decision": "approve",
            },
        )
        assert rejected.status_code == 409
        review_result = validate_proposal_review(
            old.packet,
            _review(old),
            fresh.case,
            fresh.evidence,
            fresh.analysis,
            authenticated_reviewer_id="offline-authored-reviewer",
        )
        assert (
            review_result.status == "needs_review" and "ReviewPacketMismatch" in review_result.codes
        )
        before_reject = client.get(f"/cases/{case_id}").json()
        rejected_edit = client.post(
            f"/cases/{case_id}/decision",
            json={
                "proposal_id": fresh.proposal_id,
                "case_revision": fresh.case.case_revision,
                "decision": "reject",
            },
        )
        assert rejected_edit.status_code == 200
        final_view = rejected_edit.json()
        assert sum(item["role"] == "assistant" for item in final_view["log"]) == sum(
            item["role"] == "assistant" for item in before_reject["log"]
        )
        assert final_view["pending"] is None
        probes.append(
            {
                "probe": "edited_proposal",
                "new_handoff": fresh.model_dump(mode="json"),
                "old_review_codes": list(review_result.codes),
                "old_approval_status": 409,
                "rejection_releases_no_draft": True,
            }
        )
        total_reasoning = sum(len(run["planner"].calls) for run in runs)
        total_retrieval = sum(len(run["retriever"].requests) for run in runs)

    conflict = _conflict_control(fixture, expected_analyses)
    if code_manifest() != code_at_start:
        raise RuntimeError("CodeChangedDuringReplay")
    receipt = {
        "receipt_version": 2,
        "fixture_id": fixture["fixture_id"],
        "fixture_sha256": FIXTURE_SHA256,
        "fixture_registration_commit": REGISTRATION_COMMIT,
        "reviewed_output_oracle": {
            "path": "experiments/review_handoff/expected-analysis-v1.json",
            "sha256": EXPECTED_SHA256,
            "registration_commit": EXPECTED_REGISTRATION_COMMIT,
            "introduced_after_first_replay": True,
            "reviewer_kind": "assistant source inspection; no human evaluation claim",
            "scope": "Exact complete-output fidelity for the five controlled authored outputs; not general semantic entailment.",
            "historical_v1_receipt_preserved": True,
        },
        "executed_code_sha256": code_at_start,
        "code_sha256": _digest(code_at_start),
        "runtime": {
            "python": sys.version.split()[0],
            "packages": {
                name: metadata_version(name)
                for name in ("fastapi", "starlette", "pydantic", "httpx")
            },
        },
        "baseline": baseline,
        "result": "passed_registered_software_assertions",
        "turns": observations,
        "probes": probes,
        "conflict_routing_control": conflict,
        "final_view": final_view,
        "comparison": {
            "baseline_complete_source_metadata": False,
            "candidate_complete_source_metadata": True,
            "baseline_complete_analysis": False,
            "candidate_complete_analysis": True,
            "baseline_case_latest_evidence_handoff": False,
            "candidate_case_latest_evidence_handoff": True,
            "baseline_catalog_bound_review_envelope": False,
            "candidate_catalog_bound_review_envelope": True,
        },
        "summary": {
            "primary_turns": 4,
            "primary_reasoning_calls": total_reasoning,
            "primary_retrieval_calls": total_retrieval,
            "approved_releases": 2,
            "event_replays_without_additional_calls": 4,
            "conflict_control_reasoning_calls": conflict["model_attempts"],
            "conflict_control_retrieval_calls": conflict["retrieval_rounds"],
            "paid_requests": 0,
            "API_cost_USD": "0",
            "real_model_calls": 0,
            "real_RAG_queries": 0,
        },
        "reporting_boundary": fixture["reporting_boundary"],
    }
    receipt["receipt_sha256"] = _digest(receipt)
    return receipt


def write_receipt(path: Path, receipt: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()
    try:
        if not __debug__:
            raise RuntimeError("AssertionChecksDisabled")
        if args.validate:
            fixture = load_fixture()
            load_expected_analyses()
            print(
                json.dumps(
                    {
                        "fixture_sha256": FIXTURE_SHA256,
                        "reviewed_output_oracle_sha256": EXPECTED_SHA256,
                        "primary_turns": len(fixture["turns"]),
                        "scenario_execution": False,
                        "paid_requests": 0,
                    }
                )
            )
            return 0
        receipt = replay_handoff()
        if args.output:
            write_receipt(args.output, receipt)
    except FileExistsError:
        print(json.dumps({"error_code": "OutputExists"}))
        return 2
    except RuntimeError as error:
        code = (
            str(error)
            if str(error) in {"AssertionChecksDisabled", "CodeChangedDuringReplay"}
            else "ReplayUnavailable"
        )
        print(json.dumps({"error_code": code}))
        return 2
    except AssertionError:
        print(json.dumps({"error_code": "RegisteredExpectationMismatch"}))
        return 2
    except Exception:
        print(json.dumps({"error_code": "ReplayUnavailable"}))
        return 2
    print(
        json.dumps(
            {
                "result": receipt["result"],
                "summary": receipt["summary"],
                "receipt_sha256": receipt["receipt_sha256"],
                "output": str(args.output) if args.output else None,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
