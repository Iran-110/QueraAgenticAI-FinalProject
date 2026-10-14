"""Preregistered catalog truth controls; no model, ledger, index or UI claim.

The same frozen controls replay against the original archived implementation
and the corrected implementation. Synthetic excerpts do not establish a fix.
"""

import json
import re
from pathlib import Path

import pytest

from agent_app.contracts import (
    CaseState,
    EvidenceBundle,
    EvidenceHit,
    Fact,
    GroundedGap,
    GroundedPlan,
)
from agent_app.orchestration.intake import STREAMLIT_VERSION_QUESTION
from agent_app.reasoning import catalog
from agent_app.reasoning.grounding import (
    render_grounded_plan,
    source_content_sha256,
    source_scope,
    validate_grounded_request,
)
from agent_app.testing.http_pilot_runtime import offline_network

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "experiments/core_stability_adversarial/catalog-version-truth-protocol-v1.json"
PACKET = json.loads(PROTOCOL.read_text(encoding="utf-8"))


@pytest.mark.parametrize("control", PACKET["controls"], ids=lambda row: row["control_id"])
def test_version_confirmation_and_documentary_gap_are_truthful_on_all_rendered_surfaces(control):
    # A baseline archive must import its own production implementation, even
    # when using the current venv's pytest and dependencies.
    assert Path(catalog.__file__).resolve() == ROOT / "src/agent_app/reasoning/catalog.py"
    supplied = control["input"]
    case = CaseState(
        case_id="synthetic:" + control["control_id"],
        case_revision=2,
        facts=tuple(Fact.model_validate(row) for row in supplied["facts"]),
        unknowns=tuple(supplied["unknowns"]),
    )
    evidence = EvidenceBundle(
        snapshot_id="synthetic:catalog-version-truth",
        hits=tuple(
            EvidenceHit.model_validate(PACKET["records"][name]) for name in supplied["record_ids"]
        ),
    )
    definitions = tuple(GroundedGap.model_validate(row) for row in PACKET["caller_user_vocabulary"])
    observations = []

    def check(condition, message):
        if not condition:
            observations.append(message)

    with offline_network():
        if control["catalog"] == "caller":
            request = catalog.caller_catalog(
                case, supplied["message"], evidence, definitions=definitions
            )
        else:
            request = catalog.runtime_catalog(case, supplied["message"], evidence)
        assert validate_grounded_request(request) == request
        assert request.case == case and request.evidence == evidence
        actual_gaps = {gap.name: gap.kind for gap in request.gaps}
        check(actual_gaps == control["expected_gaps"], f"gap kinds differ: {actual_gaps}")
        source_gap = next((gap for gap in request.gaps if gap.kind == "source"), None)
        expected_description = control["expected_source_gap_description"]
        check(
            (source_gap.description if source_gap else None) == expected_description,
            "source coverage description differs from the preregistered knowledge boundary",
        )
        refs = tuple(
            {"chunk_id": hit.chunk_id, "content_sha256": source_content_sha256(hit)}
            for hit in evidence.hits
        )
        for decision in control["acceptable_render_decisions"]:
            plan = GroundedPlan(
                context_sha256=request.context_sha256,
                decision=decision,
                sources=refs if decision == "answer" else (),
                question_name="streamlit_version" if decision == "ask" else None,
            )
            result = render_grounded_plan(request, plan, source_gap_handoff=True)
            surfaces = {
                "user_draft": result.user_draft,
                "maintainer_summary": result.maintainer_summary,
                "rationale": result.rationale,
            }
            for name, text in surfaces.items():
                if control["known_user_version"] is None:
                    check(
                        re.search(r"\bconfirmed version\b", text, flags=re.I) is None,
                        f"{decision}/{name} incorrectly claims a confirmed user version",
                    )
                if expected_description is None:
                    check(
                        "Caller-declared source gaps" not in text,
                        f"{decision}/{name} invents a version-documentation gap",
                    )
                elif decision != "ask" or name != "user_draft":
                    check(
                        expected_description in text,
                        f"{decision}/{name} loses the honest documentary gap",
                    )
            if decision == "ask":
                check(
                    result.user_draft
                    == result.next_question
                    == STREAMLIT_VERSION_QUESTION.question,
                    "canonical version question changed or acquired fabricated source claims",
                )
                check(result.missing_info == ("streamlit_version",), "wrong question target")
            if decision == "answer":
                check(
                    len(result.evidence_links) == len(evidence.hits),
                    "selected source references were lost",
                )
                for hit in evidence.hits:
                    check(hit.excerpt in result.user_draft, "whole supplied excerpt was altered")
                    check(
                        f"scope={source_scope(case, hit)}"
                        in next(
                            link.claim
                            for link in result.evidence_links
                            if link.chunk_id == hit.chunk_id
                        ),
                        "source scope no longer follows current active user facts",
                    )
            active_user_facts = [
                fact
                for fact in case.facts
                if fact.status == "active" and fact.provenance_kind == "user"
            ]
            for fact in active_user_facts:
                check(fact.value in result.maintainer_summary, "active user facts were lost")
            check(result.decision == decision, "catalog change altered the authored decision")
    assert observations == [], observations
