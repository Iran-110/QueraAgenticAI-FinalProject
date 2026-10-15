"""Question-preserving complete source background; no model-quality assertion."""

import json
from copy import deepcopy
from decimal import Decimal

import httpx
import pytest
from fastapi.testclient import TestClient

from agent_app import api
from agent_app.contracts import (
    CaseState,
    EvidenceBundle,
    EvidenceHit,
    Fact,
    GroundedGap,
    GroundedPlan,
    ReasoningContext,
    UserTurn,
)
from agent_app.llm.budget import BudgetLedger
from agent_app.llm.config import MetisConfig
from agent_app.llm.grounded import MetisGroundedPlanner
from agent_app.llm.metis import configured_grounded_messages, request_id_for
from agent_app.orchestration.intake import STREAMLIT_VERSION_QUESTION, prepare_version_reply
from agent_app.persistent_api import create_app
from agent_app.reasoning.grounding import (
    UNRESOLVED_SOURCE_CONFLICT,
    GroundedReasoner,
    GroundingRejected,
    _source_block,
    make_grounded_request,
    render_grounded_plan,
    source_content_sha256,
)
from agent_app.reasoning.output import InvalidAnalysis
from agent_app.testing.fakes import FakeRetriever
from agent_app.testing.http_pilot_runtime import offline_network
from agent_app.tracker.sqlite_tracker import SQLiteCaseTracker

CALLBACK = GroundedGap(
    name="parent_callback_code",
    kind="user",
    description="The failing parent callback is not recorded.",
    necessity="The USER can supply the callback needed to inspect actual state changes.",
    question="Can you share the failing parent callback?",
)
VERSION = GroundedGap(
    name=STREAMLIT_VERSION_QUESTION.name,
    kind="user",
    description="The installed version is not recorded.",
    necessity="The USER can report the release needed to choose applicable sources.",
    question=STREAMLIT_VERSION_QUESTION.question,
)
SOURCE_GAP = GroundedGap(
    name="diagnosis_documentation",
    kind="source",
    description="The supplied text does not establish an application diagnosis.",
    necessity="Further source investigation remains necessary.",
)


def _fact(version="1.50.0", **changes):
    return Fact(
        **(
            {
                "name": "streamlit_version",
                "value": version,
                "source_ref": "user:version",
                "turn_id": "turn:version",
            }
            | changes
        )
    )


def _case(*, facts=None, **changes):
    return CaseState(
        **(
            {
                "case_id": "ask-background-case",
                "case_revision": 2,
                "facts": (_fact(),) if facts is None else facts,
            }
            | changes
        )
    )


def _hit(name="current", versions=("1.50.0",), **changes):
    return EvidenceHit(
        **(
            {
                "chunk_id": f"chunk:{name}",
                "source_id": f"source:{name}",
                "source_type": "doc",
                "source_url": f"https://example.org/{name}",
                "applicable_versions": versions,
                "source_span": "complete supplied synthetic record",
                "excerpt": f"Complete {name} background. This does NOT establish a fix.",
            }
            | changes
        )
    )


def _request(*, case=None, hits=None, gaps=(CALLBACK,), conflicts=()):
    return make_grounded_request(
        case or _case(),
        "The full application loses its selection.",
        EvidenceBundle(
            snapshot_id="ask-background-fixture", hits=(_hit(),) if hits is None else hits
        ),
        gaps=gaps,
        conflict_groups=conflicts,
    )


def _plan(request, decision="ask", *, selected=None, question=CALLBACK.name):
    references = request.evidence.hits if selected is None else selected
    return GroundedPlan(
        context_sha256=request.context_sha256,
        decision=decision,
        sources=tuple(
            {"chunk_id": hit.chunk_id, "content_sha256": source_content_sha256(hit)}
            for hit in references
        )
        if decision != "retrieve_more"
        else (),
        question_name=question if decision == "ask" else None,
        retrieval_queries=("Streamlit fragment current documentation",)
        if decision == "retrieve_more"
        else (),
    )


def _context(request, **changes):
    return ReasoningContext(
        **(
            {
                "run_id": "ask-background-run",
                "case_id": request.case.case_id,
                "case_revision": request.case.case_revision,
                "attempt_index": 1,
                "remaining_model_attempts": 1,
                "remaining_retrieval_rounds": 1,
                "can_refine": True,
            }
            | changes
        )
    )


def _unchanged_except_draft(before, after):
    assert after.model_dump(exclude={"user_draft"}) == before.model_dump(exclude={"user_draft"})


@pytest.mark.parametrize("decision", ["ask", "answer", "escalate", "retrieve_more"])
@pytest.mark.parametrize(
    "flags",
    [
        {},
        {"source_gap_handoff": True},
        {"source_gap_handoff": True, "source_gap_investigation": True},
    ],
)
def test_default_and_explicit_false_have_identical_complete_output_bytes(decision, flags):
    request = _request(gaps=(CALLBACK, SOURCE_GAP))
    plan = _plan(request, decision)
    before = render_grounded_plan(request, plan, **flags)
    after = render_grounded_plan(request, plan, ask_source_background=False, **flags)
    assert after.model_dump_json() == before.model_dump_json()
    if decision != "ask":
        assert (
            render_grounded_plan(
                request, plan, ask_source_background=True, **flags
            ).model_dump_json()
            == before.model_dump_json()
        )


@pytest.mark.parametrize("bad", [None, "true", "false", 0, 1, [], {}])
def test_background_flag_is_strict_boolean_at_both_trusted_boundaries(bad):
    request = _request()
    with pytest.raises(GroundingRejected, match="grounded_context_mismatch"):
        render_grounded_plan(request, _plan(request), ask_source_background=bad)
    with pytest.raises(GroundingRejected, match="grounded_context_mismatch"):
        GroundedReasoner(object(), ask_source_background=bad)


@pytest.mark.parametrize(
    "flags",
    [
        {},
        {"source_gap_handoff": True},
        {"source_gap_handoff": True, "source_gap_investigation": True},
    ],
)
def test_question_first_background_keeps_every_other_output_field_and_complete_sources(flags):
    hits = (_hit("first"), _hit("second", source_type="issue"))
    request = _request(hits=hits, gaps=(CALLBACK, SOURCE_GAP))
    plan = _plan(request, selected=tuple(reversed(hits)))
    frozen = (request.model_dump_json(), plan.model_dump_json())
    before = render_grounded_plan(request, plan, **flags)
    after = render_grounded_plan(request, plan, ask_source_background=True, **flags)
    assert after.user_draft.startswith(CALLBACK.question + "\n\n")
    assert "the follow-up still needs your reply" in after.user_draft
    assert "cause of the application's failure" in after.user_draft
    assert after.user_draft.index(_source_block(request.case, hits[0])) < after.user_draft.index(
        _source_block(request.case, hits[1])
    )
    assert after.next_question == CALLBACK.question
    assert after.missing_info == (CALLBACK.name,)
    _unchanged_except_draft(before, after)
    assert (request.model_dump_json(), plan.model_dump_json()) == frozen
    assert "Caller-declared source gaps" not in after.user_draft


def test_only_model_selected_exact_current_version_sources_enter_user_background():
    current = _hit("selected-current")
    old = _hit("selected-old", ("1.49.0",))
    unconfirmed = _hit("selected-unconfirmed", ())
    unselected = _hit("unselected-current")
    request = _request(hits=(old, unselected, current, unconfirmed))
    plan = _plan(request, selected=(old, current, unconfirmed))
    before = render_grounded_plan(request, plan)
    after = render_grounded_plan(request, plan, ask_source_background=True)
    assert _source_block(request.case, current) in after.user_draft
    for hit in (old, unconfirmed, unselected):
        assert hit.excerpt not in after.user_draft
    assert old.excerpt in after.maintainer_summary
    assert unconfirmed.excerpt in after.maintainer_summary
    _unchanged_except_draft(before, after)


@pytest.mark.parametrize(
    "facts",
    [
        (),
        (_fact(status="superseded"),),
        (_fact(provenance_kind="evidence", source_ref="doc:reported-version"),),
        (_fact(name="inferred_version"),),
        (_fact("1.49.0"),),
        (_fact("1.50"),),
        (_fact("1.50.1"),),
    ],
)
def test_metadata_or_query_does_not_supply_user_version_or_patch_equivalence(facts):
    request = _request(case=_case(facts=facts))
    plan = _plan(request)
    before = render_grounded_plan(request, plan)
    after = render_grounded_plan(request, plan, ask_source_background=True)
    assert after.model_dump_json() == before.model_dump_json()
    assert after.user_draft == CALLBACK.question


def test_correction_changes_eligible_sources_and_withdrawal_removes_all_background():
    old, current = _hit("old", ("1.49.0",)), _hit("current")
    original = _request(case=_case(facts=(_fact("1.49.0"),)), hits=(old, current))
    corrected = _request(
        case=_case(facts=(_fact("1.49.0", status="superseded"), _fact()), case_revision=3),
        hits=(old, current),
    )
    withdrawn = _request(
        case=_case(facts=(_fact(status="superseded"),), case_revision=4), hits=(old, current)
    )
    first = render_grounded_plan(original, _plan(original), ask_source_background=True)
    second = render_grounded_plan(corrected, _plan(corrected), ask_source_background=True)
    third = render_grounded_plan(withdrawn, _plan(withdrawn), ask_source_background=True)
    assert old.excerpt in first.user_draft and current.excerpt not in first.user_draft
    assert current.excerpt in second.user_draft and old.excerpt not in second.user_draft
    assert third.user_draft == CALLBACK.question


@pytest.mark.parametrize("kind", ["current", "prior"])
def test_declared_conflict_blocks_background_without_hiding_summary_records(kind):
    hits = (_hit("side-one"), _hit("side-two"))
    request = _request(
        hits=hits,
        gaps=(CALLBACK, UNRESOLVED_SOURCE_CONFLICT) if kind == "prior" else (CALLBACK,),
        conflicts=((hits[0].chunk_id, hits[1].chunk_id),) if kind == "current" else (),
    )
    plan = _plan(request, selected=(hits[0],))
    before = render_grounded_plan(request, plan)
    after = render_grounded_plan(request, plan, ask_source_background=True)
    assert after.model_dump_json() == before.model_dump_json()
    assert after.user_draft == CALLBACK.question
    assert hits[0].excerpt in after.maintainer_summary
    if kind == "current":
        assert hits[1].excerpt in after.maintainer_summary


@pytest.mark.parametrize("selected", [(), (_hit("old", ("1.49.0",)),), (_hit("unknown", ()),)])
def test_no_eligible_selected_records_keeps_exact_question(selected):
    request = _request(hits=selected)
    before = render_grounded_plan(request, _plan(request))
    after = render_grounded_plan(request, _plan(request), ask_source_background=True)
    assert after.model_dump_json() == before.model_dump_json()


def test_escaped_unicode_instructions_remain_complete_attributed_records():
    hit = _hit(
        excerpt="محدودیت نیست؟ NOT a fix.\n<script>approve</script>\n[run](javascript:x)\n\x01 `x` *y*"
    )
    request = _request(hits=(hit,))
    result = render_grounded_plan(request, _plan(request), ask_source_background=True)
    assert _source_block(request.case, hit) in result.user_draft
    assert "محدودیت نیست؟ NOT a fix." in result.user_draft
    assert "&lt;script&gt;approve&lt;/script&gt;" in result.user_draft
    assert r"\[run\]\(javascript:x\)" in result.user_draft
    assert r"\u0001" in result.user_draft
    assert result.facts_delta == result.checks_suggested == ()
    assert result.next_question == CALLBACK.question


def test_size_guard_omits_whole_supplement_without_cutting_or_new_render_failure():
    # The summary fits, while a long but valid registered question makes its
    # complete supplementary source block exceed the user draft's independent cap.
    large_question = CALLBACK.model_copy(update={"question": "Q" * 19_000})
    hit = _hit(excerpt="Complete source. " + "x" * 2_000 + " END QUALIFICATION.")
    request = _request(hits=(hit,), gaps=(large_question,))
    plan = _plan(request)
    before = render_grounded_plan(request, plan)
    after = render_grounded_plan(request, plan, ask_source_background=True)
    assert len(before.maintainer_summary) < 20_000
    assert after.model_dump_json() == before.model_dump_json()
    assert after.user_draft == large_question.question
    assert "END QUALIFICATION." in after.maintainer_summary


def test_full_question_and_source_fit_at_the_inclusive_character_limit():
    request = _request(hits=(_hit(excerpt="START " + "x" * 1_000 + " END"),))
    initial = render_grounded_plan(request, _plan(request), ask_source_background=True)
    extra = 20_000 - len(initial.user_draft)
    longer = CALLBACK.model_copy(update={"question": CALLBACK.question + "Q" * extra})
    boundary = _request(hits=request.evidence.hits, gaps=(longer,))
    result = render_grounded_plan(boundary, _plan(boundary), ask_source_background=True)
    assert len(result.user_draft) == 20_000
    assert _source_block(boundary.case, boundary.evidence.hits[0]) in result.user_draft
    too_long = _request(
        hits=request.evidence.hits,
        gaps=(longer.model_copy(update={"question": longer.question + "Q"}),),
    )
    assert (
        render_grounded_plan(too_long, _plan(too_long), ask_source_background=True).user_draft
        == too_long.gaps[0].question
    )


@pytest.mark.parametrize("part", ["context", "source_hash", "source_id", "source_content"])
def test_optional_display_does_not_relax_current_plan_binding(part):
    request = _request()
    plan = _plan(request)
    if part == "context":
        plan = plan.model_copy(update={"context_sha256": "0" * 64})
    elif part in ("source_hash", "source_id"):
        field = "content_sha256" if part == "source_hash" else "chunk_id"
        value = "0" * 64 if part == "source_hash" else "chunk:unselected"
        plan = plan.model_copy(
            update={"sources": (plan.sources[0].model_copy(update={field: value}),)}
        )
    else:
        request = _request(hits=(_hit(excerpt="Changed current source."),))
        plan = plan.model_copy(update={"context_sha256": request.context_sha256})
    with pytest.raises(GroundingRejected):
        render_grounded_plan(request, plan, ask_source_background=True)


def test_canonical_version_question_remains_exact_and_narrow_reply_is_still_accepted():
    request = _request(
        case=_case(facts=(), pending_proposal_id="version-proposal"), gaps=(VERSION,)
    )
    result = render_grounded_plan(
        request,
        _plan(request, question=VERSION.name),
        ask_source_background=True,
    )
    assert result.user_draft == result.next_question == VERSION.question
    turn = UserTurn(
        case_id=request.case.case_id,
        expected_revision=request.case.case_revision,
        turn_id="reply:version",
        source_ref="user:reply-version",
        message="1.50.0",
    )
    prepared = prepare_version_reply(
        request.case, turn, proposal_id="version-proposal", question=result
    )
    assert prepared.reported_facts[0].name == "streamlit_version"
    assert prepared.reported_facts[0].value == "1.50.0"


class _CurrentPlanner:
    def __init__(self):
        self.requests = []

    def plan(self, request, *, context):
        self.requests.append(request.model_copy(deep=True))
        return _plan(request)


def test_reasoner_opt_in_forwards_only_rendering_and_keeps_same_planner_request():
    request = _request()
    planners = (_CurrentPlanner(), _CurrentPlanner())
    results = []
    for enabled, planner in zip((False, True), planners, strict=True):
        reasoner = GroundedReasoner(
            planner,
            request_factory=lambda *_args: request,
            ask_source_background=enabled,
        )
        results.append(
            reasoner.analyze(
                request.case, request.user_message, request.evidence, context=_context(request)
            )
        )
    assert planners[0].requests == planners[1].requests == [request]
    assert results[0].user_draft == CALLBACK.question
    assert request.evidence.hits[0].excerpt in results[1].user_draft
    _unchanged_except_draft(*results)


def test_inherited_same_run_conflict_suppresses_background_after_refinement():
    initial_hits = (_hit("side-one"), _hit("side-two"))
    initial = _request(
        hits=initial_hits, conflicts=((initial_hits[0].chunk_id, initial_hits[1].chunk_id),)
    )
    latest = _request(hits=(_hit("current-only"),))
    requests = iter((initial, latest))

    class Planner:
        observed = []

        def plan(self, request, *, context):
            self.observed.append(request)
            return _plan(request, "retrieve_more" if context.attempt_index == 1 else "ask")

    planner = Planner()
    reasoner = GroundedReasoner(
        planner, request_factory=lambda *_args: next(requests), ask_source_background=True
    )
    first = reasoner.analyze(
        initial.case, initial.user_message, initial.evidence, context=_context(initial)
    )
    second = reasoner.analyze(
        latest.case,
        latest.user_message,
        latest.evidence,
        context=_context(
            latest,
            attempt_index=2,
            remaining_model_attempts=0,
            remaining_retrieval_rounds=0,
            can_refine=False,
        ),
    )
    assert first.decision == "retrieve_more"
    assert second.user_draft == CALLBACK.question
    assert UNRESOLVED_SOURCE_CONFLICT in planner.observed[1].gaps
    assert latest.evidence.hits[0].excerpt in second.maintainer_summary
    assert all(hit.excerpt not in second.maintainer_summary for hit in initial_hits)


def test_reasoner_keeps_invalid_reference_terminal_before_optional_display():
    request = _request()

    class Planner:
        def plan(self, request, *, context):
            return _plan(request).model_copy(update={"context_sha256": "0" * 64})

    reasoner = GroundedReasoner(
        Planner(), request_factory=lambda *_args: request, ask_source_background=True
    )
    with pytest.raises(InvalidAnalysis) as error:
        reasoner.analyze(
            request.case, request.user_message, request.evidence, context=_context(request)
        )
    assert [issue.code for issue in error.value.issues] == ["grounded_context_mismatch"]


def test_full_background_is_bound_to_durable_http_approval_correction_restart_and_retry(tmp_path):
    token = "offline-question-background-review-token"
    reviewers = {"fixture-maintainer": token}
    auth = {"Authorization": f"Bearer {token}"}
    path = tmp_path / "ask-background-http.sqlite3"
    records = []
    evidence = EvidenceBundle(
        snapshot_id="ask-background-fixture", hits=(_hit(), _hit("old", ("1.49.0",)))
    )

    def adapters(_case, _scenario):
        planner = _CurrentPlanner()

        def current_request(case, message, bundle):
            request = make_grounded_request(case, message, bundle, gaps=(CALLBACK,))
            records.append(request)
            return request

        return api.RunAdapters(
            retriever=FakeRetriever([evidence]),
            reasoner=GroundedReasoner(
                planner, request_factory=current_request, ask_source_background=True
            ),
            snapshot_id=evidence.snapshot_id,
            grounded_request_supplier=lambda: planner.requests[-1] if planner.requests else None,
        )

    def fresh():
        tracker = SQLiteCaseTracker(path, reviewer_tokens=reviewers)
        app = create_app(
            tracker,
            reviewer_tokens=reviewers,
            case_adapters=adapters,
            evidence_scope="exact_user_version",
        )
        return tracker, app

    def event(event_id, revision, version):
        return {
            "message": f"Reported version {version}; the full application fails.",
            "turn_id": event_id,
            "expected_revision": revision,
            "reported_facts": [{"name": "streamlit_version", "value": version}],
        }

    def review(proposal, review_id):
        return {
            "proposal_id": proposal["proposal_id"],
            "case_revision": proposal["case_revision"],
            "expected_handoff_sha256": proposal["review_handoff"]["handoff_sha256"],
            "review_id": review_id,
            "decision": "approve",
        }

    tracker, app = fresh()
    route = "/cases/background-http"
    with TestClient(app) as client:
        first = client.post(route + "/messages", json=event("initial", 0, "1.50.0"))
        assert first.status_code == 200
        initial = first.json()["pending"]
        assert initial is not None and _hit().excerpt in initial["user_draft"]
        assert initial["next_question"] == CALLBACK.question
        assert tracker.comments("background-http") == []
        old_approval = review(initial, "old-review")
        wrong = deepcopy(old_approval)
        wrong["expected_handoff_sha256"] = "0" * 64
        response = client.post(route + "/decision", json=wrong, headers=auth)
        assert response.status_code == 409
        assert tracker.comments("background-http") == []

        corrected = client.post(route + "/messages", json=event("correction", 1, "1.49.0"))
        assert corrected.status_code == 200
        current = corrected.json()["pending"]
        assert current["case_revision"] == 2
        assert _hit("old", ("1.49.0",)).excerpt in current["user_draft"]
        assert _hit().excerpt not in current["user_draft"]
        assert client.post(route + "/decision", json=old_approval, headers=auth).status_code == 409
        approval = review(current, "current-review")
        approved = client.post(route + "/decision", json=approval, headers=auth)
        assert approved.status_code == 200
        assert approved.json()["log"][-1]["text"] == current["user_draft"]
        assert len(tracker.comments("background-http")) == 1
        assert len(records) == 2

    reopened, recreated = fresh()
    with TestClient(recreated) as client:
        assert client.get(route).json()["log"][-1]["text"] == current["user_draft"]
        retry = client.post(route + "/decision", json=approval, headers=auth)
        assert retry.status_code == 200
        assert len(reopened.comments("background-http")) == 1
        assert len(records) == 2
        assert json.loads(json.dumps(retry.json()))["pending"] is None


@pytest.mark.parametrize(
    "oversized", [False, True], ids=["small-user-history", "large-user-history"]
)
def test_third_user_turn_keeps_background_durable_but_outside_model_authority_and_guard(
    tmp_path, oversized
):
    """Authored continuation controls, never a reply/gold for an evaluation case.

    The production conversation boundary excludes prior assistant quotations.
    A large USER-only history, rather than approved source background, exercises
    the real gateway's pre-reservation UTF8 guard. Mock transport is local only.
    """
    token = "offline-third-turn-background-review-token"
    reviewers = {"fixture-maintainer": token}
    auth = {"Authorization": f"Bearer {token}"}
    tracker_path = tmp_path / "third-turn-tracker.sqlite3"
    ledger = BudgetLedger.create(
        tmp_path / "third-turn-offline-ledger.sqlite3",
        limit_usd=Decimal("1"),
        opening_spend_usd=Decimal("0"),
    )
    config = MetisConfig(
        api_key="public-synthetic-third-turn-mock-key",
        live_enabled=True,
        response_mode="grounded_plan",
        grounded_decision_contracts=True,
        grounded_compact_plan=True,
        input_token_reserve=32768,
    )
    hit = _hit(excerpt="FULL APPROVED BACKGROUND: a synthetic rule does NOT establish a fix.")
    evidence = EvidenceBundle(snapshot_id="third-turn-background-fixture", hits=(hit,))
    original = "Offline authored original USER control; no diagnosis supplied."
    continuation = "Offline authored third USER control; no successful fix is asserted."
    if oversized:
        original += "🧪" * 3900
        continuation += "🧪" * 3900
    attempts, sends, gateways = [], [], []

    def respond(request):
        payload = json.loads(request.content)
        wire = json.loads(payload["messages"][1]["content"])
        sends.append(payload)
        current = wire["request"]
        revision = current["case"]["case_revision"]
        if revision <= 2:
            plan = {
                "context_sha256": current["context_sha256"],
                "decision": "ask",
                "sources": [] if revision == 1 else [0],
                "question_name": VERSION.name if revision == 1 else CALLBACK.name,
            }
        else:
            plan = {
                "context_sha256": current["context_sha256"],
                "decision": "escalate",
                "sources": [],
            }
        return httpx.Response(
            200,
            json={
                "model": "gpt-4o-mini",
                "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": json.dumps(plan)},
                    }
                ],
            },
        )

    def adapters(_case, _scenario):
        gateway = MetisGroundedPlanner(config, ledger, transport=httpx.MockTransport(respond))
        gateways.append(gateway)

        class ObservedPlanner:
            latest = None

            def plan(self, request, *, context):
                self.latest = request.model_copy(deep=True)
                attempts.append((self.latest, context.model_copy(deep=True)))
                return gateway.plan(request, context=context)

        planner = ObservedPlanner()

        def request_factory(case, message, current_evidence):
            gap = VERSION if case.case_revision == 1 else CALLBACK
            return make_grounded_request(case, message, current_evidence, gaps=(gap,))

        return api.RunAdapters(
            retriever=FakeRetriever([evidence]),
            reasoner=GroundedReasoner(
                planner,
                request_factory=request_factory,
                ask_source_background=True,
            ),
            snapshot_id=evidence.snapshot_id,
            grounded_request_supplier=lambda: planner.latest,
            cleanup=gateway.close,
        )

    def fresh():
        tracker = SQLiteCaseTracker(tracker_path, reviewer_tokens=reviewers)
        return tracker, create_app(
            tracker,
            reviewer_tokens=reviewers,
            case_adapters=adapters,
            evidence_scope="exact_user_version",
        )

    def approve(client, route, pending, review_id):
        response = client.post(
            route + "/decision",
            headers=auth,
            json={
                "review_id": review_id,
                "proposal_id": pending["proposal_id"],
                "case_revision": pending["case_revision"],
                "expected_handoff_sha256": pending["review_handoff"]["handoff_sha256"],
                "decision": "approve",
            },
        )
        assert response.status_code == 200
        return response.json()

    route = "/cases/third-turn-background"
    with offline_network():
        tracker, app = fresh()
        with TestClient(app) as client:
            response = client.post(
                route + "/messages",
                json={"message": original, "turn_id": "initial", "expected_revision": 0},
            )
            assert response.status_code == 200
            first = response.json()["pending"]
            assert first and first["user_draft"] == VERSION.question
            approve(client, route, first, "review-version")
            response = client.post(
                route + "/messages",
                json={
                    "message": "1.50.0",
                    "turn_id": "version",
                    "expected_revision": 1,
                    "reply_to_proposal_id": first["proposal_id"],
                },
            )
            assert response.status_code == 200
            second = response.json()["pending"]
            assert second and second["next_question"] == CALLBACK.question
            assert _source_block(_case(), hit) in second["user_draft"]
            approved = approve(client, route, second, "review-background")
            assert approved["log"][-1]["text"] == second["user_draft"]
            assert len(sends) == len(attempts) == 2
            before_ledger = ledger.snapshot()
            before_comments = tracker.comments("third-turn-background")
            assert len(before_comments) == 2

        # Recreated tracker/app deliberately load the approved text from SQLite.
        reopened, recreated = fresh()
        with TestClient(recreated) as client:
            before = client.get(route).json()
            assert before["log"][-1]["text"] == second["user_draft"]
            third_event = {
                "message": continuation,
                "turn_id": "third-authored-control",
                "expected_revision": 2,
            }
            response = client.post(route + "/messages", json=third_event)
            assert response.status_code == 200
            third = response.json()
            assert third["case_revision"] == 3
            assert len(attempts) == 3
            request, context = attempts[-1]
            # Complete USER history survives. Assistant history is deliberately
            # retained for review, not injected as fresh source/input authority.
            assert original in request.user_message
            assert "1.50.0" in request.user_message
            assert request.user_message.endswith(continuation)
            assert second["user_draft"] not in request.user_message
            assert CALLBACK.question not in request.user_message
            assert hit.excerpt not in request.user_message
            assert request.case.case_revision == 3
            assert request.evidence.hits == (hit,)
            persisted = reopened.read_case("third-turn-background")
            assert any(
                entry["actor"] == "assistant" and entry["text"] == second["user_draft"]
                for entry in persisted["history"]
            )
            assert [
                entry["text"] for entry in persisted["history"] if entry["actor"] == "user"
            ] == [original, "1.50.0", continuation]
            assert reopened.comments("third-turn-background") == before_comments
            wire_messages = configured_grounded_messages(config, request, context)
            guarded_size = len(json.dumps(wire_messages, ensure_ascii=False).encode("utf-8")) + 1024
            if oversized:
                assert guarded_size > config.input_token_reserve
                assert third["pending"] is None
                assert third["run_outcome"]["error_code"] == "ContextLimitExceeded"
                assert len(sends) == 2
                assert ledger.get(request_id_for(context)) is None
                assert ledger.snapshot() == before_ledger
                # The committed failed event replays without a third/fourth
                # model attempt, new reservation, repeated source send or action.
                assert client.post(route + "/messages", json=third_event).status_code == 200
                assert len(attempts) == 3 and len(sends) == 2
                assert ledger.snapshot() == before_ledger
            else:
                assert guarded_size <= config.input_token_reserve
                assert len(sends) == 3
                assert third["pending"] and third["pending"]["decision"] == "escalate"
                actual_wire = json.loads(sends[-1]["messages"][1]["content"])
                assert actual_wire["request"] == request.model_dump(mode="json")
                assert ledger.get(request_id_for(context)).status == "settled"
                assert third["pending"]["model_attempts"] == 1
            assert reopened.comments("third-turn-background") == before_comments
    assert len(gateways) == 3
    assert all(gateway.reasoner.client.is_closed for gateway in gateways)
