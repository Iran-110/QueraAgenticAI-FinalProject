"""Opt-in structural source units; no semantic or online quality assertion."""

import hashlib
import json
from pathlib import Path

import pytest
from test_claim_plan import Planner, context, evidence, gap, plan, state

from agent_app.contracts import (
    CaseState,
    Fact,
    GroundedRequest,
    ProposalRequirements,
    ReasoningContext,
)
from agent_app.orchestration import SupportEngine
from agent_app.reasoning.claim_plan import (
    ClaimPlanRejected,
    ClaimReasoner,
    build_claim_messages,
    build_claim_request,
    claim_block_has_body,
    partition_claim_sections,
    render_claim_plan,
    validate_claim_request,
)
from agent_app.reasoning.grounding import GroundingRejected, make_grounded_request
from agent_app.reasoning.output import InvalidAnalysis
from agent_app.testing.fakes import FakeRetriever

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("content", ["---", "***", "___", "===", "<hr/>"])
def test_nonempty_fenced_content_is_body_even_when_it_looks_like_markup(content):
    assert claim_block_has_body("```text\n" + content + "\n```")


def request(text, *, block_mode="sections", case=None, gaps=()):
    bundle = evidence().model_copy(
        update={"hits": (evidence().hits[0].model_copy(update={"excerpt": text}),)}
    )
    return build_claim_request(
        make_grounded_request(case or state(), "A current report.", bundle, gaps=gaps),
        block_mode=block_mode,
    )


def texts(text):
    return [text[span.start : span.end] for span in partition_claim_sections(text)]


def test_all_sixteen_registered_defaults_keep_context_messages_and_rendered_bytes():
    baseline = json.loads(
        (ROOT / "experiments/core_evidence_selection_v1/default-baseline-v1.json").read_bytes()
    )
    snapshots = json.loads(
        (ROOT / "experiments/core_broader_dev_v1/snapshots-v1.json").read_bytes()
    )["snapshots"]
    expected = {row["snapshot_id"]: row for row in baseline["rows"]}
    assert len(expected) == len(snapshots) == 16
    for row in snapshots:
        grounded = GroundedRequest.model_validate(row["catalog_request"])
        implicit = build_claim_request(grounded)
        explicit = build_claim_request(grounded, block_mode="paragraphs")
        assert implicit == explicit
        assert implicit.context_sha256 == expected[row["id"]]["claim_context_sha256"]
        ctx = ReasoningContext(
            run_id="offline-selection-baseline",
            case_id=grounded.case.case_id,
            case_revision=grounded.case.case_revision,
            attempt_index=1,
            remaining_model_attempts=1,
            remaining_retrieval_rounds=1,
            can_refine=True,
            proposal_requirements=ProposalRequirements.model_validate(row["proposal_requirements"]),
        )
        wire = json.dumps(
            build_claim_messages(implicit, ctx),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        assert hashlib.sha256(wire).hexdigest() == expected[row["id"]]["messages_sha256"]
        selection = plan(
            implicit,
            decision="escalate",
            passages=[[0, 0]] if implicit.blocks else [],
            user_facts=[],
        )
        rendered = render_claim_plan(implicit, selection).model_dump_json().encode()
        assert hashlib.sha256(rendered).hexdigest() == expected[row["id"]]["rendered_sha256"]


def test_root_sections_retain_every_descendant_body_code_and_later_qualification():
    text = (
        "Preamble.\n\n"
        "## First root\n\nA documented general pattern.\n\n"
        "### A nested example\n\n```python\nx = 1\n\ny = 2\n```\n\n"
        "#### A deeper qualification\n\nOnly while this condition holds.\n\n"
        "## Second root\n\nA separate whole body.\n"
    )
    units = texts(text)
    assert len(units) == 3
    assert units[0] == "Preamble.\n\n"
    assert "A documented general pattern." in units[1]
    assert "x = 1\n\ny = 2" in units[1]
    assert "Only while this condition holds." in units[1]
    assert units[2].startswith("## Second root")
    assert "".join(units) == text


@pytest.mark.parametrize(
    "text",
    [
        "# Root\n\nBody.\n\n## Child\n\nQualification.\n",
        "First title\n===========\n\nBody.\n\nSecond title\n============\n\nBody.\n",
        "First title\n-----------\n\nBody.\n\nSecond title\n------------\n\nBody.\n",
        "First title\r\n===========\r\n\r\nفارسی 🧪.\r\n\r\nSecond\r\n======\r\n\r\nBody.\r\n",
        "A multiline\nsetext title\n============\n\nBody.\n\nNext\n====\n\nBody.\n",
        "---\ntitle: Source metadata\nslug: /neutral-source\n---\n\n# Source\n\nBody.\n",
        "No heading.\n\nAn entire plain record, including its caveat.\n",
        "```python\n# An apparent heading\n\n## Still code\n```\n\n# Actual heading\n\nBody.\n",
        "~~~text\nFake setext\n============\n~~~\n\nActual title\n============\n\nBody.\n",
        "# Root\n\n````text\n```\n## A fake peer\n````\n\n# Real peer\n\nBody.\n",
        "# Root\n\n```unclosed\n\n# Not a peer\n\nRest of code.\n",
        "\n\nPrefix.\n\n# Title\n\nBody.\n",
    ],
)
def test_every_source_character_separator_and_fence_is_preserved(text):
    spans = partition_claim_sections(text)
    assert spans[0].start == 0 and spans[-1].end == len(text)
    assert all(left.end == right.start for left, right in zip(spans, spans[1:], strict=False))
    assert "".join(text[span.start : span.end] for span in spans).encode() == text.encode()
    assert validate_claim_request(request(text)).block_mode == "sections"


def test_fence_heading_lines_do_not_create_section_boundaries():
    text = (
        "## Outer\n\n```python\n# A fake root\n## A fake peer\n\n"
        "A fake setext\n=============\n```\n\nA later caveat.\n\n"
        "## Actual peer\n\nOther body."
    )
    units = texts(text)
    assert len(units) == 2
    assert "A later caveat." in units[0]
    assert "# A fake root" in units[0]
    assert units[1] == "## Actual peer\n\nOther body."


@pytest.mark.parametrize("underline", ["-", "--", "=", "=="])
def test_short_setext_underlines_do_not_make_overlapping_heading_spans(underline):
    first = f"First title\n{underline}\n"
    second = f"Second title\n{underline}\n"
    assert texts(first + second) == [first, second]
    assert not claim_block_has_body(first + second)


def test_no_heading_means_one_whole_record_without_paragraph_shortening():
    text = "A complete record.\n\nIts condition is in the next paragraph.\n\n```python\nx = 1\n```"
    assert texts(text) == [text]
    req = request(text)
    out = render_claim_plan(req, plan(req, passages=[[0, 0]], user_facts=[]))
    assert "Its condition is in the next paragraph." in out.user_draft


@pytest.mark.parametrize(
    "text",
    [
        "# A title only",
        "## A title\n\n### Child title\n",
        "A setext title\n===============\n",
        "A multiline\nsetext title\n-------------\n",
        "---\ntitle: Metadata only\nslug: /not-prose\n---",
        "---\ntitle: Metadata only\n---\n\n# A title\n\n***\n",
        "```python\n\n```",
        "***\n\n___\n\n<hr />",
        "",
    ],
)
def test_heading_metadata_delimiters_and_separators_do_not_count_as_body(text):
    assert not claim_block_has_body(text)


@pytest.mark.parametrize(
    "text",
    [
        "A complete source observation.",
        "# A title\n\nAn actual body with its limitation.",
        "```python\nx = 1\n```",
        "```text\n# This line is fenced content, not an outside heading.\n```",
        "---\nA paragraph after a lone thematic rule.",
        "---\ntitle: Metadata\n---\n\nA complete source body.",
        "- A substantive list item.\n- A condition.",
    ],
)
def test_body_is_only_structural_presence_not_an_entailment_or_relevance_test(text):
    assert claim_block_has_body(text)


def test_heading_only_answer_rejected_only_in_opt_in_mode_and_with_bounded_feedback():
    text = "## A title without explanatory body"
    sections = request(text)
    with pytest.raises(ClaimPlanRejected) as error:
        render_claim_plan(sections, plan(sections, passages=[[0, 0]], user_facts=[]))
    assert error.value.code == "invalid_grounded_plan"
    assert len(error.value.issues) == 1 and error.value.issues[0].field == "decision"
    paragraphs = request(text, block_mode="paragraphs")
    assert (
        render_claim_plan(paragraphs, plan(paragraphs, passages=[[0, 0]], user_facts=[])).decision
        == "answer"
    )


def test_a_heading_only_selection_cannot_hide_behind_another_source_body():
    original = request("## A title only")
    hit = (
        evidence()
        .hits[0]
        .model_copy(
            update={"chunk_id": "second-neutral-chunk", "excerpt": "A complete source body."}
        )
    )
    bundle = original.grounded.evidence.model_copy(
        update={"hits": (*original.grounded.evidence.hits, hit)}
    )
    req = build_claim_request(
        make_grounded_request(state(), "A current report.", bundle), block_mode="sections"
    )
    with pytest.raises(ClaimPlanRejected):
        render_claim_plan(req, plan(req, passages=[[0, 0], [1, 0]], user_facts=[]))


def test_sections_do_not_automatically_import_peer_or_cross_source_qualifications():
    text = "## A documented pattern\n\nUseful body.\n\n## Peer qualification\n\nA condition in a peer section."
    req = request(text)
    out = render_claim_plan(req, plan(req, passages=[[0, 0]], user_facts=[]))
    assert "Useful body." in out.user_draft
    assert "A condition in a peer section." not in out.user_draft
    assert req.grounded.evidence.hits[0].excerpt == text


def test_irrelevant_body_is_not_misclassified_as_semantically_verified():
    req = request("# Completely different topic\n\nAn unrelated observation.")
    out = render_claim_plan(req, plan(req, passages=[[0, 0]], user_facts=[]))
    assert "An unrelated observation." in out.user_draft
    assert "Applicability to this environment is unconfirmed" in out.user_draft
    assert "not establish semantic support" in out.evidence_links[0].claim


def test_mode_and_source_changes_cannot_reuse_paragraph_or_old_section_context():
    old = request("# A root\n\nA documented observation.", block_mode="paragraphs")
    current = build_claim_request(old.grounded, block_mode="sections")
    assert old.context_sha256 != current.context_sha256
    with pytest.raises(GroundingRejected, match="grounded_context_mismatch"):
        render_claim_plan(current, plan(old, passages=[[0, 0]], user_facts=[]))
    tampered = current.model_copy(update={"block_mode": "paragraphs"})
    with pytest.raises(GroundingRejected, match="grounded_context_mismatch"):
        validate_claim_request(tampered)
    changed = request("# A root\n\nDifferent source content under the same identifier.")
    with pytest.raises(GroundingRejected, match="grounded_context_mismatch"):
        render_claim_plan(changed, plan(current, passages=[[0, 0]], user_facts=[]))


def test_whole_record_modes_still_have_distinct_context_bindings():
    paragraph = request("Single whole record.", block_mode="paragraphs")
    section = build_claim_request(paragraph.grounded, block_mode="sections")
    assert paragraph.blocks == section.blocks
    assert paragraph.context_sha256 != section.context_sha256


@pytest.mark.parametrize("mode", [None, True, "unknown", "Sections"])
def test_only_explicit_registered_private_modes_are_valid(mode):
    grounded = request("Body.").grounded
    with pytest.raises(GroundingRejected, match="grounded_context_mismatch"):
        build_claim_request(grounded, block_mode=mode)
    with pytest.raises(GroundingRejected, match="grounded_context_mismatch"):
        ClaimReasoner(Planner(), block_mode=mode)


def test_current_correction_retires_old_version_and_stale_section_plan():
    old = request("# A root\n\nA complete documented pattern.")
    changed_case = CaseState(
        case_id=state().case_id,
        case_revision=4,
        facts=(Fact(name="streamlit_version", value="2.5", source_ref="user:4", turn_id="turn:4"),),
    )
    fresh = request(old.grounded.evidence.hits[0].excerpt, case=changed_case)
    with pytest.raises(GroundingRejected, match="grounded_context_mismatch"):
        render_claim_plan(fresh, plan(old, passages=[[0, 0]], user_facts=[]))
    out = render_claim_plan(fresh, plan(fresh, passages=[[0, 0]], user_facts=[]))
    assert "2.5" in out.user_draft and "version: 2.4" not in out.user_draft


def test_large_complete_section_stops_instead_of_truncating_or_changing_limits():
    text = "# Large whole section\n\n" + "<" * 6000 + "\n\nA required later limitation."
    req = request(text)
    with pytest.raises(GroundingRejected, match="grounded_render_too_large"):
        render_claim_plan(req, plan(req, passages=[[0, 0]], user_facts=[]))
    assert req.grounded.evidence.hits[0].excerpt == text
    assert len(req.blocks[0]) == 1


def test_reasoner_opt_in_returns_whole_selected_unit_without_new_model_attempts():
    text = "## A principle\n\nThe complete body.\n\n### A qualification\n\nA later required caveat."
    original = request(text)
    planner = Planner(lambda req, ctx: plan(req, passages=[[0, 0]], user_facts=[]))
    reasoner = ClaimReasoner(planner, block_mode="sections")
    result = SupportEngine(
        retriever=FakeRetriever([original.grounded.evidence]),
        reasoner=reasoner,
        snapshot_id=original.grounded.evidence.snapshot_id,
        evidence_scope="all",
    ).run(state(), "A current report.")
    assert result.status == "awaiting_approval" and result.model_attempts == 1
    assert "The complete body." in result.analysis.user_draft
    assert "A later required caveat." in result.analysis.user_draft
    assert reasoner.last_request.block_mode == "sections"
    assert reasoner.last_request.grounded.evidence == original.grounded.evidence
    assert not reasoner._conflicts


def test_heading_only_retry_is_bounded_and_does_not_invent_missing_source_body():
    original = request("# A source heading only")
    planner = Planner(lambda req, ctx: plan(req, passages=[[0, 0]], user_facts=[]))
    result = SupportEngine(
        retriever=FakeRetriever([original.grounded.evidence]),
        reasoner=ClaimReasoner(planner, block_mode="sections"),
        snapshot_id=original.grounded.evidence.snapshot_id,
        evidence_scope="all",
    ).run(state(), "A current report.")
    assert result.status == "error" and result.model_attempts == len(planner.calls) == 2
    assert result.error_code == "ModelOutputInvalid"
    assert len(planner.calls[1][1].output_feedback.issues) == 1


def test_section_mode_preserves_registered_questions_and_source_gap_separation():
    req = request("# A heading only", gaps=(gap(), gap("source")))
    out = render_claim_plan(
        req, plan(req, decision="ask", question_name=gap().name, passages=[[0, 0]], user_facts=[])
    )
    assert out.user_draft == gap().question
    assert out.missing_info == (gap().name,)
    with pytest.raises(GroundingRejected, match="grounded_question_invalid"):
        render_claim_plan(
            req,
            plan(req, decision="ask", question_name=gap("source").name, passages=[], user_facts=[]),
        )


def test_same_run_conflict_survives_section_repair_without_old_source_content():
    count = 0
    original = request("## First\n\nA whole documented body.")
    hit = (
        evidence()
        .hits[0]
        .model_copy(update={"chunk_id": "conflict-neutral", "excerpt": "OLD CONFLICT TEXT"})
    )
    first = original.grounded.evidence.model_copy(
        update={"hits": (*original.grounded.evidence.hits, hit)}
    )

    def factory(c, m, e):
        nonlocal count
        count += 1
        return make_grounded_request(
            c, m, e, conflict_groups=(("neutral-chunk", "conflict-neutral"),) if count == 1 else ()
        )

    planner = Planner(
        lambda req, ctx: (
            "malformed" if ctx.attempt_index == 1 else plan(req, passages=[[0, 0]], user_facts=[])
        )
    )
    reasoner = ClaimReasoner(planner, request_factory=factory, block_mode="sections")
    with pytest.raises(InvalidAnalysis):
        reasoner.analyze(state(), "A current report.", first, context=context())
    with pytest.raises(InvalidAnalysis) as error:
        reasoner.analyze(
            state(),
            "A current report.",
            original.grounded.evidence,
            context=context(
                attempt_index=2,
                remaining_model_attempts=0,
                remaining_retrieval_rounds=0,
                can_refine=False,
            ),
        )
    assert error.value.issues[0].code == "grounded_conflict_unresolved"
    assert "OLD CONFLICT TEXT" not in json.dumps(reasoner.last_request.model_dump(mode="json"))
    assert not reasoner._conflicts
