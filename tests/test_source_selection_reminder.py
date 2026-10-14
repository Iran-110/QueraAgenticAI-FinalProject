"""Frozen prompt treatment preserves inputs; this is not model resistance."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from agent_app.contracts import (
    CaseState,
    EvidenceBundle,
    GroundedGap,
    GroundedPlan,
    ReasoningContext,
)
from agent_app.reasoning.grounding import (
    build_grounded_messages,
    make_grounded_request,
    render_grounded_plan,
    source_content_sha256,
)
from agent_app.reasoning.source_selection import (
    SOURCE_SELECTION_REMINDER,
    add_source_selection_reminder,
)

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "experiments/core_quality_followup/adversarial-live-protocol-v1.json"
PACKET = ROOT / "experiments/core_stability_adversarial/adversarial-packet-v1.json"


def _packet():
    return json.loads(PACKET.read_text(encoding="utf-8"))


def _request(job):
    overrides = job["catalog_overrides"]
    return make_grounded_request(
        CaseState.model_validate(job["declared_current_state"]),
        job["fixture"]["turns"][0]["visible"]["message"],
        EvidenceBundle.model_validate(job["bundles"]["current"]),
        gaps=tuple(GroundedGap.model_validate(gap) for gap in overrides["gaps"]),
        conflict_groups=tuple(tuple(group) for group in overrides["conflict_groups"]),
    )


def test_source_selection_text_exactly_matches_preimplementation_protocol():
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    candidate = protocol["candidate"]
    assert SOURCE_SELECTION_REMINDER == candidate["candidate_text"]
    assert (
        hashlib.sha256(SOURCE_SELECTION_REMINDER.encode()).hexdigest()
        == candidate["candidate_text_sha256"]
    )
    assert candidate["default_enabled"] is False
    assert candidate["not_a_hard_guard"] is True
    assert protocol["gateway"]["max_output_tokens"] == 2048
    assert len(protocol["batches"]) == 2
    assert all(len(batch["jobs"]) == 6 for batch in protocol["batches"])


@pytest.mark.parametrize("job", _packet()["jobs"], ids=lambda job: job["job_id"])
def test_source_selection_default_unchanged_and_candidate_only_changes_system(job):
    request = _request(job)
    context = ReasoningContext(
        run_id="source-selection-control-" + job["job_id"],
        case_id=request.case.case_id,
        case_revision=request.case.case_revision,
        attempt_index=1,
        remaining_model_attempts=1,
        remaining_retrieval_rounds=1,
        can_refine=True,
    )
    original = build_grounded_messages(request, context, decision_contracts=True)
    before = deepcopy(original)
    assert add_source_selection_reminder(original) is original
    assert add_source_selection_reminder(original, False) is original
    candidate = add_source_selection_reminder(original, True)
    assert original == before
    assert len(candidate) == len(original) == 2
    assert candidate[0]["role"] == original[0]["role"] == "system"
    assert candidate[0]["content"] == original[0]["content"] + "\n\n" + SOURCE_SELECTION_REMINDER
    assert candidate[1] == original[1]
    assert candidate[1]["content"] == original[1]["content"]
    # Copies prevent a later caller from changing the input's original objects.
    candidate[1]["content"] = "changed isolated copy"
    assert original == before
    payload = json.loads(original[1]["content"])
    assert payload["request"] == request.model_dump(mode="json")
    assert "gold" not in payload and "oracle" not in payload


@pytest.mark.parametrize("enabled", [None, 0, 1, "false", "true", [], {}])
def test_source_selection_requires_boolean_before_observing_message_contents(enabled):
    class UntrustedMessages:
        def __len__(self):
            pytest.fail("Invalid configuration must stop before messages are inspected")

    with pytest.raises(ValueError, match="^SourceSelectionFlagInvalid$"):
        add_source_selection_reminder(UntrustedMessages(), enabled)


@pytest.mark.parametrize(
    "messages",
    [
        (),
        ({"role": "user", "content": "role impersonation"}, {"role": "user", "content": "x"}),
        ({"role": "system", "content": "x"}, {"role": "system", "content": "second policy"}),
        (
            {"role": "system", "content": "x", "extra": "untrusted"},
            {"role": "user", "content": "y"},
        ),
    ],
)
def test_source_selection_enabled_rejects_ambiguous_policy_message_placement(messages):
    with pytest.raises(ValueError, match="^SourceSelectionMessagesInvalid$"):
        add_source_selection_reminder(messages, True)


def test_source_selection_guidance_does_not_rewrite_or_certify_attack_source():
    job = next(job for job in _packet()["jobs"] if job["job_id"] == "icon-challenge")
    request = _request(job)
    context = ReasoningContext(
        run_id="source-selection-known-limitation",
        case_id=request.case.case_id,
        case_revision=request.case.case_revision,
        attempt_index=1,
    )
    original = build_grounded_messages(request, context, decision_contracts=True)
    candidate = add_source_selection_reminder(original, True)
    assert candidate[1]["content"] == original[1]["content"]
    attack = next(
        hit for hit in request.evidence.hits if hit.chunk_id == "authored-icon-injection-v1"
    )
    assert (
        attack.excerpt
        in json.loads(candidate[1]["content"])["request"]["evidence"]["hits"][0]["excerpt"]
    )
    # This authored forbidden choice remains renderer-valid: a prompt treatment
    # cannot itself enforce relevance, authenticity or semantic entailment.
    plan = GroundedPlan(
        context_sha256=request.context_sha256,
        decision="answer",
        sources=({"chunk_id": attack.chunk_id, "content_sha256": source_content_sha256(attack)},),
    )
    rendered = render_grounded_plan(request, plan, source_gap_handoff=True)
    assert "SYSTEM OVERRIDE" in rendered.user_draft
    assert rendered.facts_delta == ()
    assert r"streamlit\_version: 1.39.0" in rendered.maintainer_summary
