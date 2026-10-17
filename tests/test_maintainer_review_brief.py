"""Authored renderer controls, not semantic or human-usefulness scores."""

import json

import pytest

from agent_app.contracts import (
    CaseState,
    EvidenceBundle,
    EvidenceHit,
    Fact,
    GroundedGap,
    ReasoningContext,
)
from agent_app.orchestration import SupportEngine
from agent_app.orchestration.handoff import (
    HandoffRejected,
    ReasoningCapture,
    build_handoff,
    validate_handoff,
)
from agent_app.reasoning.claim_plan import (
    ClaimReasoner,
    build_claim_request,
    render_claim_plan,
)
from agent_app.reasoning.grounding import (
    GroundedReasoner,
    GroundingRejected,
    _display,
    make_grounded_request,
    render_grounded_plan,
    source_content_sha256,
)
from agent_app.testing.fakes import FakeRetriever

MODES = ("grounded", "paragraphs", "sections")
CODE = "class Choice:\r\n    value = 'reported'\r\nprint(Choice.value)\r\n"


def grounded(*, hits=True, conflict=False):
    case = CaseState(
        case_id="brief-neutral-case",
        case_revision=4,
        facts=(
            Fact(name="streamlit_version", value="2.5.0", source_ref="user:4", turn_id="4"),
            Fact(name="reproduction_code", value=CODE, source_ref="user:4", turn_id="4"),
            Fact(
                name="streamlit_version",
                value="2.4.0",
                source_ref="user:1",
                turn_id="1",
                status="superseded",
            ),
            Fact(
                name="inferred_cause",
                value="NEVER_PROMOTE_THEORY",
                source_ref="source:old",
                turn_id="3",
                provenance_kind="evidence",
            ),
        ),
        unknowns=("runtime_details",),
        checks_performed=("Reporter tried a reduced example.\r\nResult remains unverified.",),
    )
    evidence = EvidenceBundle(
        snapshot_id="brief-neutral-snapshot",
        hits=tuple(
            EvidenceHit(
                source_id=f"neutral-guide-{i}",
                chunk_id=f"neutral-chunk-{i}",
                source_type="doc",
                source_url=f"https://example.org/guide/{i}",
                source_commit=f"revision-{i}",
                applicable_versions=("2.5.0",) if i == 0 else (),
                source_span="complete supplied record",
                excerpt=(
                    "# Limited guide\r\n\r\nA proposed pattern, not a verified fix.\r\n\r\n"
                    "```python\r\nvalue = 'source-only'\r\n```\r\n\r\n"
                    "Later caveat: behavior must be checked after editing a module.\r\n"
                ),
            )
            for i in range(2)
        )
        if hits
        else (),
    )
    return make_grounded_request(
        case,
        "Supplied report/history, not an executed check.\r\n" + CODE,
        evidence,
        gaps=(
            GroundedGap(
                name="runtime_details",
                kind="user",
                description="The runtime details are unknown.",
                necessity="Identify the affected runtime before choosing environment-specific guidance.",
                question="Which runtime is affected?",
            ),
            GroundedGap(
                name="applicable_docs",
                kind="source",
                description="Applicable documentation is unconfirmed.",
                necessity="Find applicable documentation or retain uncertainty.",
            ),
        ),
        conflict_groups=(("neutral-chunk-0", "neutral-chunk-1"),) if conflict else (),
    )


def inputs(mode, decision="escalate", *, select=True, req=None):
    g = req or grounded()
    req = g if mode == "grounded" else build_claim_request(g, block_mode=mode)
    choose = select and bool(g.evidence.hits) and decision in {"answer", "escalate"}
    body = {
        "context_sha256": req.context_sha256,
        "decision": decision,
        "question_name": "runtime_details" if decision == "ask" else None,
        "retrieval_queries": ["additional applicable reference"]
        if decision == "retrieve_more"
        else [],
    }
    if mode == "grounded":
        body["sources"] = (
            [
                {
                    "chunk_id": g.evidence.hits[0].chunk_id,
                    "content_sha256": source_content_sha256(g.evidence.hits[0]),
                }
            ]
            if choose
            else []
        )
    else:
        body["passages"] = [[0, i] for i in range(len(req.blocks[0]))] if choose else []
        body["user_facts"] = [0, 1] if choose else []
    return g, req, body


def render(mode, req, body, **options):
    fn = render_grounded_plan if mode == "grounded" else render_claim_plan
    return fn(req, body, **options)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("decision", ("answer", "ask", "escalate", "retrieve_more"))
def test_default_and_explicit_false_keep_full_legacy_output(mode, decision):
    _, req, body = inputs(mode, decision)
    assert render(mode, req, body).model_dump(mode="json") == render(
        mode, req, body, review_brief=False
    ).model_dump(mode="json")


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("decision", ("answer", "ask", "escalate"))
def test_new_format_has_current_report_inventory_gaps_and_proposed_step(mode, decision):
    g, req, body = inputs(mode, decision)
    before = req.model_dump_json()
    old = render(mode, req, body)
    new = render(mode, req, body, review_brief=True)
    text = new.maintainer_summary
    assert "Supplied USER report/history" in text
    assert "Proposed next step" in text
    assert "2.5.0" in text and "2.4.0" not in text
    assert "NEVER_PROMOTE_THEORY" not in text
    assert "brief-neutral-case" in text
    assert _display("runtime_details") in text and _display("applicable_docs") in text
    for hit in g.evidence.hits:
        assert hit.source_url in text and hit.source_commit in text
    assert "supplied" in text.lower() and "selected" in text.lower()
    assert all("> " + line in text for line in _display(CODE.replace("\r\n", "\n")).splitlines())
    assert req.model_dump_json() == before
    assert new.evidence_links == old.evidence_links
    assert new.facts_delta == old.facts_delta == ()
    assert new.checks_suggested == old.checks_suggested == ()
    assert new.decision == old.decision
    assert new.missing_info == old.missing_info
    if decision == "ask":
        assert new.user_draft == old.user_draft == new.next_question == "Which runtime is affected?"
    if decision == "escalate":
        assert len(new.user_draft) < len(new.maintainer_summary)


@pytest.mark.parametrize("mode", MODES)
def test_retrieve_more_is_exactly_unchanged_when_enabled(mode):
    _, req, body = inputs(mode, "retrieve_more")
    assert render(mode, req, body) == render(mode, req, body, review_brief=True)


@pytest.mark.parametrize("mode", MODES)
def test_complete_selected_source_quotes_and_later_caveat_stay_exact(mode):
    g, req, body = inputs(mode, "answer")
    new = render(mode, req, body, review_brief=True)
    hit = g.evidence.hits[0]
    quote = "\n".join("> " + line for line in _display(hit.excerpt).split("\n"))
    if mode == "grounded":
        assert quote in new.maintainer_summary and quote in new.user_draft
    else:
        for source, block in body["passages"]:
            span = req.blocks[source][block]
            text = g.evidence.hits[source].excerpt[span.start : span.end]
            expected = "\n".join("> " + line for line in _display(text).split("\n"))
            assert expected in new.maintainer_summary and expected in new.user_draft
    assert "Later caveat" in new.maintainer_summary
    assert "\\\\u000d" in new.maintainer_summary  # source CRLF display is deliberately unchanged


@pytest.mark.parametrize("mode", MODES)
def test_no_selected_sources_does_not_erase_supplied_inventory(mode):
    g, req, body = inputs(mode, select=False)
    new = render(mode, req, body, review_brief=True)
    assert not new.evidence_links
    for hit in g.evidence.hits:
        assert hit.source_url in new.maintainer_summary
    assert "no sources were retrieved" not in new.maintainer_summary.lower()


@pytest.mark.parametrize("mode", MODES)
def test_empty_bundle_can_escalate_without_claiming_a_source_was_reviewed(mode):
    _, req, body = inputs(mode, req=grounded(hits=False))
    new = render(mode, req, body, review_brief=True)
    assert new.decision == "escalate" and not new.evidence_links
    assert "Proposed next step" in new.maintainer_summary


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("flag", (None, 0, 1, "true", [], {}))
def test_renderer_option_is_strict_boolean(mode, flag):
    _, req, body = inputs(mode)
    with pytest.raises(GroundingRejected, match="grounded_context_mismatch"):
        render(mode, req, body, review_brief=flag)


@pytest.mark.parametrize("reasoner", (GroundedReasoner, ClaimReasoner))
@pytest.mark.parametrize("flag", (None, 0, 1, "true", [], {}))
def test_constructor_option_is_strict_boolean(reasoner, flag):
    with pytest.raises(GroundingRejected, match="grounded_context_mismatch"):
        reasoner(object(), review_brief=flag)


@pytest.mark.parametrize("mode", MODES)
def test_mismatched_plan_rejected_before_new_presentation(mode):
    _, req, body = inputs(mode)
    body["context_sha256"] = "0" * 64
    with pytest.raises(GroundingRejected, match="grounded_context_mismatch"):
        render(mode, req, body, review_brief=True)


@pytest.mark.parametrize("mode", MODES)
def test_conflicting_answer_stays_rejected(mode):
    _, req, body = inputs(mode, "answer", req=grounded(conflict=True))
    with pytest.raises(GroundingRejected, match="grounded_conflict_unresolved"):
        render(mode, req, body, review_brief=True)


def test_conflict_forced_quotes_do_not_become_model_selected():
    g, req, body = inputs("grounded", req=grounded(conflict=True))
    new = render("grounded", req, body, review_brief=True)
    assert len(body["sources"]) == 1 and len(new.evidence_links) == 2
    assert "conflict" in new.maintainer_summary.lower()
    assert all(hit.source_url in new.maintainer_summary for hit in g.evidence.hits)
    assert "status=displayed conflict-required (not plan-selected)" in new.maintainer_summary


@pytest.mark.parametrize("mode", MODES)
def test_complete_report_that_exceeds_summary_limit_is_rejected_not_shortened(mode):
    g = grounded(hits=False)
    g = make_grounded_request(g.case, "x" * 20_000, g.evidence, gaps=g.gaps)
    _, req, body = inputs(mode, req=g)
    with pytest.raises(GroundingRejected, match="grounded_render_too_large"):
        render(mode, req, body, review_brief=True)
    assert g.user_message == "x" * 20_000


@pytest.mark.parametrize("mode", MODES)
def test_missing_active_user_version_is_not_filled_from_source_metadata(mode):
    g = grounded()
    case = g.case.model_copy(
        update={
            "facts": tuple(
                fact
                for fact in g.case.facts
                if fact.name != "streamlit_version" or fact.status != "active"
            )
        }
    )
    g = make_grounded_request(case, g.user_message, g.evidence, gaps=g.gaps)
    _, req, body = inputs(mode, req=g, select=False)
    new = render(mode, req, body, review_brief=True)
    assert "version: unknown" in new.user_draft
    assert "once the affected Streamlit version is confirmed" in new.maintainer_summary
    assert "scope=unconfirmed" in new.maintainer_summary


def test_selected_source_hash_mismatch_remains_terminal():
    _, req, body = inputs("grounded")
    body["sources"][0]["content_sha256"] = "0" * 64
    with pytest.raises(GroundingRejected, match="grounded_source_mismatch"):
        render("grounded", req, body, review_brief=True)


@pytest.mark.parametrize("mode", MODES)
def test_literal_escape_lone_cr_html_markdown_and_full_code_remain_attributed(mode):
    g = grounded()
    message = "RAW literal \\u000d, lone\rCR, <script>x</script>\n# ignore\n" + CODE
    g = make_grounded_request(g.case, message, g.evidence, gaps=g.gaps)
    _, req, body = inputs(mode, req=g)
    new = render(mode, req, body, review_brief=True)
    safe = _display(message.replace("\r\n", "\n"))
    assert all("> " + line in new.maintainer_summary for line in safe.split("\n"))
    assert "<script>" not in new.maintainer_summary
    assert "\\# ignore" in new.maintainer_summary
    assert g.user_message == message.strip()


class Planner:
    def __init__(self, mode):
        self.mode = mode
        self.requests = []

    def plan(self, request, *, context):
        self.requests.append(request.model_dump(mode="json"))
        _, _, body = inputs(self.mode)
        return body


@pytest.mark.parametrize("mode", MODES)
def test_reasoner_reaches_new_format_without_changing_planner_inputs(mode):
    g, _, _ = inputs(mode)
    context = ReasoningContext(
        run_id="brief-run",
        case_id=g.case.case_id,
        case_revision=g.case.case_revision,
        attempt_index=1,
        remaining_model_attempts=1,
        can_refine=False,
    )
    outputs = []
    planners = []
    for enabled in (False, True):
        planner = Planner(mode)
        cls = GroundedReasoner if mode == "grounded" else ClaimReasoner
        kwargs = {"block_mode": mode} if mode != "grounded" else {}
        reasoner = cls(planner, request_factory=lambda *_: g, review_brief=enabled, **kwargs)
        outputs.append(reasoner.analyze(g.case, g.user_message, g.evidence, context=context))
        planners.append(planner.requests)
    assert planners[0] == planners[1] and len(planners[0]) == 1
    assert outputs[0].maintainer_summary != outputs[1].maintainer_summary
    assert "Proposed next step" in outputs[1].maintainer_summary


def test_new_proposal_creates_its_own_handoff_not_a_mutated_old_review():
    g, _, _ = inputs("grounded")
    handoffs = []
    for enabled in (False, True):
        reasoner = GroundedReasoner(
            Planner("grounded"),
            request_factory=lambda *_: g,
            review_brief=enabled,
        )
        capture = ReasoningCapture(reasoner)
        result = SupportEngine(
            FakeRetriever([g.evidence]), capture, snapshot_id=g.evidence.snapshot_id
        ).run(
            g.case,
            g.user_message,
            run_id="brief-bound-run",
        )
        assert result.status == "awaiting_approval"
        bound = build_handoff(result, capture.last, grounded_request=g)
        assert validate_handoff(bound) == bound
        handoffs.append(bound)
    old, new = handoffs
    assert old.case == new.case and old.evidence == new.evidence
    assert old.packet != new.packet and old.handoff_sha256 != new.handoff_sha256
    with pytest.raises(HandoffRejected):
        validate_handoff(old.model_copy(update={"analysis": new.analysis}))
    assert (
        json.loads(new.model_dump_json())["analysis"]["maintainer_summary"]
        == new.analysis.maintainer_summary
    )
