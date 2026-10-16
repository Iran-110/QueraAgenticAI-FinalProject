"""Neutral passage-custody observations; no fixtures, model calls or gold labels."""

import builtins
import json
import socket
import sqlite3
from copy import deepcopy
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from agent_app.contracts import (
    AnalysisResult,
    CaseState,
    EvidenceBundle,
    EvidenceHit,
    EvidenceLink,
    Fact,
    ReasoningContext,
    RunResult,
)
from agent_app.evaluation.evidence_observation import (
    EvidenceObservationRejected,
    PassageAnchor,
    PassageRequirement,
    observe_required_passages,
    passage_requirements_sha256,
)
from agent_app.llm.config import MetisConfig
from agent_app.orchestration.handoff import ReasoningFrame, build_handoff
from agent_app.reasoning.grounding import make_grounded_request, source_content_sha256


def hit(**updates):
    return EvidenceHit(
        **(
            {
                "chunk_id": "neutral-chunk",
                "source_id": "neutral-source",
                "source_commit": None,
                "source_url": "https://example.org/neutral",
                "source_type": "doc",
                "excerpt": "Prefix. A neutral required passage. Suffix.",
                "applicable_versions": ("1.0.0",),
                "score": 1.0,
                "score_kind": "lexical",
            }
            | updates
        )
    )


def anchor(**updates):
    return PassageAnchor(
        **(
            {
                "source_id": "neutral-source",
                "source_commit": None,
                "source_url": "https://example.org/neutral",
                "passage": "A neutral required passage.",
            }
            | updates
        )
    )


def requirements(*anchors):
    return (
        PassageRequirement(
            requirement_id="neutral-requirement", alternatives=anchors or (anchor(),)
        ),
    )


def handoff(*, hits=None, case=None, analysis=None, grounded=False):
    case = case or CaseState(
        case_id="neutral-case",
        case_revision=2,
        facts=(
            Fact(
                name="streamlit_version",
                value="1.0.0",
                source_ref="user:version",
                turn_id="version",
            ),
        ),
    )
    evidence = EvidenceBundle(
        snapshot_id="neutral-snapshot", hits=(hit(),) if hits is None else hits
    )
    analysis = analysis or AnalysisResult(
        decision="answer",
        user_draft="A neutral proposed response.",
        maintainer_summary="Neutral summary.",
        rationale="Neutral rationale.",
    )
    context = ReasoningContext(
        run_id="neutral-proposal",
        case_id=case.case_id,
        case_revision=case.case_revision,
        attempt_index=1,
    )
    result = RunResult(
        run_id=context.run_id,
        case_id=case.case_id,
        case_revision=case.case_revision,
        status="awaiting_approval",
        analysis=analysis,
        model_attempts=1,
        retrieval_rounds=1,
    )
    message = "Private neutral user message."
    return build_handoff(
        result,
        ReasoningFrame(case, message, evidence, context),
        grounded_request=make_grounded_request(case, message, evidence) if grounded else None,
    )


def observe(value=None, criteria=None, **updates):
    value = handoff() if value is None else value
    criteria = requirements() if criteria is None else criteria
    kwargs = {
        "expected_handoff_sha256": value.handoff_sha256,
        "requirements_sha256": passage_requirements_sha256(criteria),
    } | updates
    return observe_required_passages(value, criteria, **kwargs)


def matches(report, group=0, alternative=0):
    return report["requirements"][group]["alternatives"][alternative]["matches"]


def test_required_source_identity_is_not_passage_presence_and_empty_bundle_is_distinct():
    wrong = observe(handoff(hits=(hit(excerpt="Only unrelated text."),)))
    empty = observe(handoff(hits=()))
    assert wrong["all_requirements_observed"] is empty["all_requirements_observed"] is False
    assert matches(wrong) == matches(empty) == []
    assert empty["requirement_count"] == 1
    assert empty["missing_scope"] == "not_observed_in_this_supplied_bundle_only"


def test_or_alternatives_with_and_groups_retain_each_result():
    first = PassageRequirement(
        requirement_id="first", alternatives=(anchor(passage="Unavailable alternative."), anchor())
    )
    second = PassageRequirement(requirement_id="second", alternatives=(anchor(passage="Suffix."),))
    report = observe(criteria=(first, second))
    assert report["all_requirements_observed"] is True
    assert report["observed_requirement_count"] == 2
    assert [item["observed"] for item in report["requirements"][0]["alternatives"]] == [False, True]
    missing = second.model_copy(update={"alternatives": (anchor(passage="Absent second group."),)})
    report = observe(criteria=(first, missing))
    assert report["all_requirements_observed"] is False
    assert report["observed_requirement_count"] == 1


@pytest.mark.parametrize(
    "updates",
    [
        {"source_id": "other-source"},
        {"source_commit": "other-revision"},
        {"source_url": "https://example.org/other"},
        {"source_url": "https://example.org/neutral?revision=other"},
        {"passage": "a neutral required passage."},
        {"passage": "A neutral required passage.  "},
    ],
)
def test_each_anchor_identity_and_exact_passage_field_matters(updates):
    assert observe(criteria=requirements(anchor(**updates)))["all_requirements_observed"] is False


def test_explicit_none_revision_is_exact_not_wildcard():
    value = handoff(hits=(hit(source_commit="revision-one"),))
    assert observe(value)["all_requirements_observed"] is False
    assert (
        observe(value, requirements(anchor(source_commit="revision-one")))[
            "all_requirements_observed"
        ]
        is True
    )
    with pytest.raises(ValidationError):
        PassageAnchor(
            source_id="neutral-source", source_url="https://example.org/neutral", passage="Text"
        )


def test_passages_are_never_stitched_across_chunks():
    value = handoff(
        hits=(
            hit(chunk_id="first", excerpt="First part"),
            hit(chunk_id="second", excerpt="second part"),
        )
    )
    report = observe(value, requirements(anchor(passage="First part second part")))
    assert report["all_requirements_observed"] is False


def test_all_matching_chunks_and_alternatives_are_observed_without_rank_dependency():
    value = handoff(hits=(hit(chunk_id="second", score=0.1), hit(chunk_id="first", score=20.0)))
    report = observe(value)
    assert [row["chunk_id"] for row in matches(report)] == ["second", "first"]
    changed = handoff(hits=(hit(chunk_id="second", score=30.0), hit(chunk_id="first", score=-5.0)))
    later = observe(changed)
    assert later["requirements_sha256"] == report["requirements_sha256"]
    assert later["all_requirements_observed"] is True
    assert matches(later)[0]["content_sha256"] != matches(report)[0]["content_sha256"]


def test_unicode_offsets_are_codepoints_and_first_occurrence_per_hit_is_explicit():
    quote = "متن🙂\n  exact"
    excerpt = f"α🙂 {quote} / {quote}"
    value = handoff(hits=(hit(excerpt=excerpt),))
    report = observe(value, requirements(anchor(passage=quote)))
    (row,) = matches(report)
    assert (row["start"], row["end"]) == (3, 3 + len(quote))
    assert excerpt[row["start"] : row["end"]] == quote
    assert row["content_sha256"] == source_content_sha256(value.evidence.hits[0])
    assert report["occurrence_scope"] == "first_exact_unicode_codepoint_occurrence_per_matching_hit"


def test_one_character_repetition_reports_one_bounded_span_per_hit():
    report = observe(handoff(hits=(hit(excerpt="x" * 20_000),)), requirements(anchor(passage="x")))
    assert len(matches(report)) == 1
    assert (matches(report)[0]["start"], matches(report)[0]["end"]) == (0, 1)


@pytest.mark.parametrize("text", ["", " ", "\n\t"])
def test_blank_passages_reject_and_unstripped_nonblank_passages_remain_exact(text):
    invalid = anchor().model_copy(update={"passage": text})
    with pytest.raises(EvidenceObservationRejected):
        passage_requirements_sha256(requirements(invalid))
    exact = anchor(passage=" required ")
    assert exact.passage == " required "


def test_safe_attempt_identifiers_are_bound_to_the_handoff():
    value = handoff()
    report = observe(value)
    assert report["run_id"] == value.reasoning_context.run_id
    assert report["attempt_index"] == value.reasoning_context.attempt_index
    assert report["grounded_context_sha256"] is None
    grounded = handoff(grounded=True)
    assert observe(grounded)["grounded_context_sha256"] == grounded.grounded_request.context_sha256


@pytest.mark.parametrize(
    "version,status,provenance,metadata,expected",
    [
        ("1.0.0", "active", "user", ("1.0.0",), "exact_metadata_match"),
        ("2.0.0", "active", "user", ("1.0.0",), "historical_or_other_version"),
        ("1.0.0", "superseded", "user", ("1.0.0",), "unconfirmed"),
        ("1.0.0", "active", "evidence", ("1.0.0",), "unconfirmed"),
        ("1.0.0", "active", "user", (), "unconfirmed"),
    ],
)
def test_version_metadata_scope_is_separate_from_presence(
    version, status, provenance, metadata, expected
):
    case = CaseState(
        case_id="neutral-case",
        facts=(
            Fact(
                name="streamlit_version",
                value=version,
                source_ref="neutral:version",
                turn_id="version",
                status=status,
                provenance_kind=provenance,
            ),
        ),
    )
    report = observe(handoff(case=case, hits=(hit(applicable_versions=metadata),)))
    assert report["all_requirements_observed"] is True
    assert matches(report)[0]["version_scope"] == expected
    assert report["claim_support"] == "unassessed"


def test_active_corrected_user_version_controls_observed_scope():
    case = CaseState(
        case_id="neutral-case",
        facts=(
            Fact(
                name="streamlit_version",
                value="1.0.0",
                source_ref="user:old",
                turn_id="old",
                status="superseded",
            ),
            Fact(
                name="streamlit_version",
                value="2.0.0",
                source_ref="user:current",
                turn_id="current",
            ),
        ),
    )
    report = observe(handoff(case=case))
    assert matches(report)[0]["version_scope"] == "historical_or_other_version"


def test_source_level_citation_is_distinct_from_presence_and_entailment():
    analysis = AnalysisResult(
        decision="answer",
        user_draft="An unsupported assertion.",
        maintainer_summary="Neutral.",
        rationale="Neutral.",
        evidence_links=(EvidenceLink(chunk_id="cited", claim="An unsupported assertion."),),
    )
    report = observe(
        handoff(hits=(hit(chunk_id="cited"), hit(chunk_id="uncited")), analysis=analysis)
    )
    assert [row["cited_by_analysis"] for row in matches(report)] == [True, False]
    assert report["claim_support"] == report["whole_answer_sufficiency"] == "unassessed"


@pytest.mark.parametrize("decision", ["answer", "ask", "escalate"])
def test_all_matches_never_selects_decision_or_closes_user_gaps(decision):
    case = CaseState(case_id="neutral-case", unknowns=("neutral_user_gap",))
    analysis = AnalysisResult(
        decision=decision,
        user_draft="Neutral response.",
        maintainer_summary="Neutral summary.",
        rationale="Neutral rationale.",
        next_question="Please provide neutral details." if decision == "ask" else None,
    )
    report = observe(handoff(case=case, analysis=analysis))
    assert report["all_requirements_observed"] is True
    assert report["decision_judgment"] == "unassessed"
    assert report["quality_claim"] is report["actual_model_consumption_verified"] is False


def test_output_contains_no_private_passage_url_or_user_text():
    report = observe()
    text = json.dumps(report, ensure_ascii=False)
    for private in (
        "https://example.org",
        "A neutral required passage.",
        "Private neutral user message.",
        "A neutral proposed response.",
    ):
        assert private not in text
    assert all(
        report[name] is False
        for name in (
            "quality_claim",
            "actual_model_consumption_verified",
            "physical_build_verified",
            "source_authenticity_verified",
            "preregistration_verified",
        )
    )


def test_complete_ordered_requirements_and_alternatives_are_hash_bound():
    first = PassageRequirement(
        requirement_id="first", alternatives=(anchor(), anchor(passage="Suffix."))
    )
    second = PassageRequirement(requirement_id="second", alternatives=(anchor(passage="Prefix."),))
    original = passage_requirements_sha256((first, second))
    assert passage_requirements_sha256((second, first)) != original
    reversed_alternatives = first.model_copy(
        update={"alternatives": tuple(reversed(first.alternatives))}
    )
    assert passage_requirements_sha256((reversed_alternatives, second)) != original


@pytest.mark.parametrize(
    "kind", ["handoff_hash", "requirements_hash", "bad_hash", "missing_handoff", "tampered_handoff"]
)
def test_independent_bindings_and_actual_handoff_integrity_reject(kind):
    value, criteria = handoff(), requirements()
    kwargs = {
        "expected_handoff_sha256": value.handoff_sha256,
        "requirements_sha256": passage_requirements_sha256(criteria),
    }
    if kind == "handoff_hash":
        kwargs["expected_handoff_sha256"] = "a" * 64
    elif kind == "requirements_hash":
        kwargs["requirements_sha256"] = "a" * 64
    elif kind == "bad_hash":
        kwargs["requirements_sha256"] = "sensitive-invalid"
    elif kind == "missing_handoff":
        value = None
    else:
        value = value.model_copy(update={"user_message": "sensitive changed input"})
    with pytest.raises(EvidenceObservationRejected) as error:
        observe_required_passages(value, criteria, **kwargs)
    assert str(error.value) == "EvidenceObservationRejected"
    assert "sensitive" not in repr(error.value)


@pytest.mark.parametrize(
    "kind",
    [
        "empty",
        "list",
        "duplicate_id",
        "duplicate_anchor",
        "too_many_requirements",
        "too_many_alternatives",
        "too_many_total",
    ],
)
def test_nonempty_unique_finite_requirement_bounds(kind):
    criteria = requirements()
    if kind == "empty":
        criteria = ()
    elif kind == "list":
        criteria = list(criteria)
    elif kind == "duplicate_id":
        criteria = (
            criteria[0],
            PassageRequirement(
                requirement_id="NEUTRAL-REQUIREMENT", alternatives=(anchor(passage="Other."),)
            ),
        )
    elif kind == "duplicate_anchor":
        criteria = (
            criteria[0],
            PassageRequirement(requirement_id="other", alternatives=(anchor(),)),
        )
    elif kind == "too_many_requirements":
        criteria = tuple(
            PassageRequirement(
                requirement_id=f"group-{i}", alternatives=(anchor(passage=f"Passage {i}"),)
            )
            for i in range(21)
        )
    elif kind == "too_many_alternatives":
        criteria = (
            criteria[0].model_copy(
                update={"alternatives": tuple(anchor(passage=f"Passage {i}") for i in range(11))}
            ),
        )
    else:
        criteria = tuple(
            PassageRequirement(
                requirement_id=f"group-{i}",
                alternatives=tuple(anchor(passage=f"Passage {i}-{j}") for j in range(10)),
            )
            for i in range(11)
        )
    with pytest.raises(EvidenceObservationRejected):
        passage_requirements_sha256(criteria)


def test_exact_maximum_requirements_and_total_alternatives_are_accepted():
    criteria = tuple(
        PassageRequirement(
            requirement_id=f"group-{i}",
            alternatives=tuple(anchor(passage=f"Passage {i}-{j}") for j in range(5)),
        )
        for i in range(20)
    )
    report = observe(criteria=criteria)
    assert report["requirement_count"] == 20
    assert sum(len(row["alternatives"]) for row in report["requirements"]) == 100


@pytest.mark.parametrize("target", ["requirement", "anchor", "handoff", "hit"])
def test_hidden_typed_fields_reject_before_serialization(target):
    value, criteria = handoff(), requirements()
    digest = passage_requirements_sha256(criteria)
    item = {
        "requirement": criteria[0],
        "anchor": criteria[0].alternatives[0],
        "handoff": value,
        "hit": value.evidence.hits[0],
    }[target]
    object.__setattr__(item, "sensitive_hidden", "sensitive_value")
    with pytest.raises(EvidenceObservationRejected):
        observe_required_passages(
            value,
            criteria,
            expected_handoff_sha256=value.handoff_sha256,
            requirements_sha256=digest,
        )


@pytest.mark.parametrize(
    "url",
    [
        "file:///private",
        "https://name:secret@example.org",
        "https://example.org:invalid",
        "https://example.org/has space",
    ],
)
def test_bypassed_invalid_anchor_urls_reject_with_fixed_error(url):
    invalid = anchor().model_copy(update={"source_url": url})
    with pytest.raises(EvidenceObservationRejected, match="^EvidenceObservationRejected$"):
        passage_requirements_sha256(requirements(invalid))


def test_inputs_are_not_mutated_and_exported_rows_are_detached():
    value, criteria = handoff(), requirements()
    before_handoff = value.model_dump(mode="json")
    before_criteria = deepcopy(criteria)
    report = observe(value, criteria)
    assert value.model_dump(mode="json") == before_handoff
    assert criteria == before_criteria
    matches(report)[0]["chunk_id"] = "changed-export"
    assert (
        observe(value, criteria)["requirements"][0]["alternatives"][0]["matches"][0]["chunk_id"]
        == "neutral-chunk"
    )


def test_no_files_credentials_env_configuration_or_runtime_clients_are_loaded(monkeypatch):
    value, criteria = handoff(), requirements()
    digest = passage_requirements_sha256(criteria)

    def forbidden(*args, **kwargs):
        raise AssertionError("External state/configuration access is forbidden")

    with monkeypatch.context() as patch:
        patch.setattr(builtins, "open", forbidden)
        patch.setattr(Path, "open", forbidden)
        patch.setattr(Path, "read_bytes", forbidden)
        patch.setattr(Path, "read_text", forbidden)
        patch.setattr(SecretStr, "get_secret_value", forbidden)
        patch.setattr(MetisConfig, "from_env", forbidden)
        patch.setattr(sqlite3, "connect", forbidden)
        patch.setattr(socket, "socket", forbidden)
        patch.setattr(httpx, "Client", forbidden)
        report = observe_required_passages(
            value,
            criteria,
            expected_handoff_sha256=value.handoff_sha256,
            requirements_sha256=digest,
        )
    assert report["all_requirements_observed"] is True
