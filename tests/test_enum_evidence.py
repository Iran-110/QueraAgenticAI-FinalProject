"""Controlled source availability, exact scope and bounded offline integration.

The official guide remains excluded from RAG. Scripted selections here prove
input/output integrity and operation, not model quality or a verified Enum fix.
"""

import hashlib
import itertools
import json
from copy import deepcopy
from decimal import Decimal

import httpx
import pytest
from fastapi.testclient import TestClient

from agent_app import api
from agent_app.contracts import (
    CaseState,
    GroundedPlan,
    OutputFeedback,
    OutputIssue,
    ReasoningContext,
    RetrievalRequest,
    UserTurn,
)
from agent_app.evaluation.runner import load_fixture
from agent_app.llm.budget import BudgetLedger
from agent_app.llm.config import MetisConfig
from agent_app.llm.grounded import MetisGroundedPlanner
from agent_app.llm.metis import configured_grounded_messages
from agent_app.orchestration.turns import propose_user_turn
from agent_app.persistent_api import create_app
from agent_app.reasoning.catalog import caller_catalog
from agent_app.reasoning.grounding import (
    GroundedReasoner,
    GroundingRejected,
    _source_block,
    render_grounded_plan,
    source_content_sha256,
)
from agent_app.testing.enum_evidence import (
    ARMS,
    CASE_PATHS,
    PACKET_PATH,
    RAW_SHA256,
    ROOT,
    SECTIONS,
    EnumEvidenceRejected,
    fixture_retriever_factory,
    load_source_packet,
    offline_boundary_report,
    validate_packet,
)
from agent_app.testing.http_pilot_runtime import offline_network
from agent_app.tracker.sqlite_tracker import SQLiteCaseTracker


@pytest.fixture
def packet():
    return load_source_packet(ROOT / PACKET_PATH)


@pytest.fixture
def fixtures():
    return {case: load_fixture(ROOT / path) for case, path in CASE_PATHS.items()}


def _retrieve(factory, job, turn, queries=("Streamlit current issue evidence",)):
    supplier, snapshot = factory(job, turn)
    return supplier.search(RetrievalRequest(snapshot_id=snapshot, queries=queries))


def _states(fixture):
    state = CaseState(case_id=fixture.case["case_id"])
    for turn in fixture.data["turns"]:
        state = propose_user_turn(
            state,
            UserTurn(
                case_id=state.case_id,
                expected_revision=state.case_revision,
                turn_id=turn["id"],
                source_ref="USER:" + turn["id"],
                **{
                    key: value
                    for key, value in turn["visible"].items()
                    if key != "reply_to_approved_question"
                },
            ),
        ).candidate
        yield turn, state


def _config():
    return MetisConfig(
        api_key="public-synthetic-enum-evidence-mock-key",
        live_enabled=True,
        response_mode="grounded_plan",
        input_token_reserve=32768,
        max_output_tokens=1024,
        grounded_json_object=True,
        grounded_decision_contracts=True,
        grounded_source_selection_reminder=True,
        grounded_compact_plan=True,
        grounded_source_gap_handoff=True,
        grounded_source_gap_investigation=True,
        grounded_source_capacity=True,
    )


def test_packet_keeps_full_official_source_and_only_complete_registered_spans(packet):
    source = packet["raw_source"]
    raw = source["raw_text"].encode()
    assert len(raw) == source["raw_utf8_bytes"] == 15170
    assert len(source["raw_text"]) == source["raw_unicode_codepoints"] == 15158
    assert hashlib.sha256(raw).hexdigest() == RAW_SHA256
    assert packet["boundaries"]["corpus_ingestion_allowed"] is False
    assert packet["boundaries"]["official_guide_is_answer_linked"] is True
    assert packet["boundaries"]["answer_informed_exposed_dev"] is True
    assert packet["boundaries"]["held_out_test_eligible"] is False
    assert packet["boundaries"]["actual_search"] is False
    assert len(packet["source_records"]) == 2
    for record, (_, start, end, digest) in zip(packet["source_records"], SECTIONS, strict=True):
        assert record["hit"]["excerpt"] == source["raw_text"][start:end]
        assert record["hit"]["excerpt"] == record["hit"]["excerpt"].strip()
        assert hashlib.sha256(record["hit"]["excerpt"].encode()).hexdigest() == digest
        assert record["hit"]["applicable_versions"] == []
        assert record["hit"]["source_commit"] == source["source_commit"]
    pattern, enum = [record["hit"]["excerpt"] for record in packet["source_records"]]
    assert "unless you are actively editing your app" in pattern
    assert "start a new session or restart your Streamlit server" in pattern
    assert "widget's returned values" in enum
    assert "set to a stricter set of matching criteria" in enum
    assert sum(len(text) for text in (pattern, enum)) == 4762
    assert "github.com/streamlit/streamlit/issues/" not in source["raw_text"]
    assert all(
        not ({"gold", "agent_script", "visible", "expected_decision"} & set(pin))
        for pin in packet["baseline_inputs"].values()
    )


@pytest.mark.parametrize(
    "mutation",
    ["raw", "span", "excerpt", "version", "source", "scope", "bool", "extra", "record"],
)
def test_packet_rejects_any_changed_raw_span_source_scope_or_extra_payload(packet, mutation):
    if mutation == "raw":
        packet["raw_source"]["raw_text"] += "\n"
    elif mutation == "span":
        packet["source_records"][0]["span"]["end"] -= 1
    elif mutation == "excerpt":
        packet["source_records"][1]["hit"]["excerpt"] += " Guaranteed fix."
    elif mutation == "version":
        packet["source_records"][0]["hit"]["applicable_versions"] = ["1.31.1"]
    elif mutation == "source":
        packet["raw_source"]["source_commit"] = "another-commit"
    elif mutation == "scope":
        packet["boundaries"]["corpus_ingestion_allowed"] = True
    elif mutation == "bool":
        packet["boundaries"]["actual_search"] = 0
    elif mutation == "extra":
        packet["gold"] = {"acceptable_decisions": ["answer"]}
    else:
        packet["source_records"].append(deepcopy(packet["source_records"][0]))
    with pytest.raises(EnumEvidenceRejected, match="^EnumEvidencePacketRejected$"):
        validate_packet(packet)


def test_fixed_supplier_preserves_controls_and_never_uses_queries_as_retrieval(packet, fixtures):
    records = []
    factory = fixture_retriever_factory(packet, fixtures, records)
    for arm, (case_id, fixture) in itertools.product(ARMS, fixtures.items()):
        for turn in fixture.data["turns"]:
            bundle = _retrieve(factory, {"arm": arm, "case_id": case_id}, turn)
            original = fixture.bundles[turn["evidence_bundle"]]
            if arm == "fixed_guide_added" and case_id == "dev-case-c":
                assert len(bundle.hits) == 3
                assert bundle.hits[: len(original.hits)] == original.hits
                assert tuple(hit.model_dump(mode="json") for hit in bundle.hits[1:]) == tuple(
                    record["hit"] for record in packet["source_records"]
                )
                assert bundle.model_copy(update={"hits": original.hits}) == original
            else:
                assert bundle.model_dump_json() == original.model_dump_json()
            assert records[-1]["actual_search"] is False
            assert records[-1]["turn_id"] == turn["id"]
    turn = fixtures["dev-case-c"].data["turns"][0]
    supplier, snapshot = factory({"arm": ARMS[1], "case_id": "dev-case-c"}, turn)
    first = supplier.search(RetrievalRequest(snapshot_id=snapshot, queries=("Enum identities",)))
    second = supplier.search(RetrievalRequest(snapshot_id=snapshot, queries=("unrelated query",)))
    assert first.model_dump_json() == second.model_dump_json()
    assert records[-2]["requested_queries"] != records[-1]["requested_queries"]
    with pytest.raises(EnumEvidenceRejected):
        supplier.search(RetrievalRequest(snapshot_id=snapshot, queries=("third query",)))
    other, _ = factory({"arm": ARMS[0], "case_id": "dev-case-c"}, turn)
    with pytest.raises(EnumEvidenceRejected):
        other.search(RetrievalRequest(snapshot_id="wrong-snapshot", queries=("Enum",)))


def test_factory_detaches_supplied_fixture_and_packet_snapshots(packet, fixtures):
    factory = fixture_retriever_factory(packet, fixtures, [])
    turn = deepcopy(fixtures["dev-case-c"].data["turns"][0])
    before = _retrieve(factory, {"arm": ARMS[1], "case_id": "dev-case-c"}, turn)
    packet["source_records"][0]["hit"]["excerpt"] = "changed after binding"
    fixtures["dev-case-c"].data["turns"][0]["visible"]["message"] = "changed after binding"
    after = _retrieve(factory, {"arm": ARMS[1], "case_id": "dev-case-c"}, turn)
    assert after.model_dump_json() == before.model_dump_json()


@pytest.mark.parametrize("kind", ["arm", "case", "turn", "visible", "bundle", "fixture"])
def test_fixed_factory_rejects_unregistered_identity_or_changed_fixture(packet, fixtures, kind):
    job = {"arm": ARMS[0], "case_id": "dev-case-c"}
    turn = deepcopy(fixtures["dev-case-c"].data["turns"][0])
    if kind == "fixture":
        fixtures["dev-case-c"].data["turns"][0]["visible"]["message"] += " changed"
        with pytest.raises(EnumEvidenceRejected):
            fixture_retriever_factory(packet, fixtures, [])
        return
    factory = fixture_retriever_factory(packet, fixtures, [])
    if kind == "arm":
        job["arm"] = "real_index"
    elif kind == "case":
        job["case_id"] = "undeclared-case"
    elif kind == "turn":
        turn["id"] = "future-or-unregistered-turn"
    elif kind == "visible":
        turn["visible"]["message"] += " forged continuation"
    else:
        turn["evidence_bundle"] = "pilot-confirmed-150"
    with pytest.raises(EnumEvidenceRejected):
        factory(job, turn)


@pytest.mark.parametrize("arm", ARMS)
def test_every_current_enum_source_subset_and_normal_repair_prompt_fits(packet, fixtures, arm):
    factory = fixture_retriever_factory(packet, fixtures, [])
    fixture = fixtures["dev-case-c"]
    for turn, state in _states(fixture):
        bundle = _retrieve(factory, {"arm": arm, "case_id": "dev-case-c"}, turn)
        request = caller_catalog(state, turn["visible"]["message"], bundle)
        assert {gap.kind for gap in request.gaps} == {"source"}
        assert all(hit.applicable_versions == () for hit in request.evidence.hits)
        for repair in (False, True):
            context = ReasoningContext(
                run_id="offline-enum-source-preflight",
                case_id=state.case_id,
                case_revision=state.case_revision,
                attempt_index=2 if repair else 1,
                remaining_model_attempts=0 if repair else 1,
                remaining_retrieval_rounds=0 if repair else 1,
                can_refine=not repair,
                output_feedback=OutputFeedback(issues=(OutputIssue(code="invalid_shape"),))
                if repair
                else None,
            )
            messages = configured_grounded_messages(_config(), request, context)
            assert len(json.dumps(messages, ensure_ascii=False).encode()) + 1024 <= 32768
            wire = json.loads(messages[1]["content"])
            assert len(wire["request"]["evidence"]["hits"]) == len(bundle.hits)
            assert wire["repair_issue_codes"] == (["invalid_shape"] if repair else [])
            bound = wire["decision_contracts"]["rules"]["answer"]["sources"]["maxItems"]
            assert bound == (2 if arm == ARMS[1] and turn["id"] == "initial" else 8)
        for count in range(len(bundle.hits) + 1):
            for selected in itertools.combinations(bundle.hits, count):
                for decision in ("answer", "escalate"):
                    if decision == "answer" and not selected:
                        continue
                    plan = GroundedPlan(
                        context_sha256=request.context_sha256,
                        decision=decision,
                        sources=tuple(
                            {"chunk_id": h.chunk_id, "content_sha256": source_content_sha256(h)}
                            for h in selected
                        ),
                    )

                    def render(request=request, plan=plan):
                        return render_grounded_plan(
                            request,
                            plan,
                            source_gap_handoff=True,
                            source_gap_investigation=True,
                            ask_source_background=True,
                            concise_user_draft=True,
                        )

                    if count > bound:
                        # The unchanged renderer still rejects the archived
                        # all-three selection; no text is clipped to fit.
                        with pytest.raises(GroundingRejected, match="grounded_render_too_large"):
                            render()
                        continue
                    output = render()
                    assert len(output.user_draft) <= 20000
                    assert len(output.maintainer_summary) <= 20000
                    assert len(output.rationale) <= 2000
                    assert output.next_question is None
                    assert all(
                        _source_block(request.case, h) in output.maintainer_summary
                        for h in selected
                    )
                    if decision == "answer":
                        assert all(
                            _source_block(request.case, h) in output.user_draft for h in selected
                        )


def test_retained_initial_overflow_and_capacity_amendment_are_reproducible(packet, fixtures):
    initial = offline_boundary_report(packet, fixtures, source_capacity_enabled=False)
    final = offline_boundary_report(packet, fixtures, source_capacity_enabled=True)
    for report, name in (
        (initial, "offline-boundary-initial-v1.json"),
        (final, "offline-boundary-review-v1.json"),
    ):
        assert report == json.loads((ROOT / PACKET_PATH.parent / name).read_bytes())
        assert report["actual_sends"] == 0
        assert report["guide_rows"] == 16
        assert report["all_subset_rows"] == 20
        assert report["actual_renderer_rejections"] == 2
        assert report["max_observed_summary_chars"] == 20015
    assert initial["accepted"] is False and initial["permitted_bound_violations"] == 2
    assert final["accepted"] is True and final["permitted_bound_violations"] == 0
    for row in final["subset_outcomes"]:
        if row["arm"] == ARMS[1] and row["turn_id"] == "initial":
            assert row["advertised_max_sources"] == 2


@pytest.mark.parametrize("arm", ARMS)
def test_actual_http_gateway_keeps_complete_current_sources_and_rejects_old_approval(
    tmp_path, packet, fixtures, arm
):
    """Scripted provider responses exercise real guards; no network/model scoring."""
    fixture = fixtures["dev-case-c"]
    records, requests, contexts, bodies = [], [], [], []
    factory = fixture_retriever_factory(packet, fixtures, records)
    ledger = BudgetLedger.create(
        tmp_path / "mock-cost.sqlite3", limit_usd=Decimal("1"), opening_spend_usd=Decimal("0")
    )
    tracker_path = tmp_path / "case-state.sqlite3"
    reviewers = {"fixture-maintainer": "public-enum-fixture-review-token"}
    headers = {"Authorization": "Bearer public-enum-fixture-review-token"}
    current_turn = fixture.data["turns"][0]

    def respond(request):
        body = json.loads(request.content)
        bodies.append(body)
        assert body["response_format"] == {"type": "json_object"}
        assert len(json.dumps(body["messages"], ensure_ascii=False).encode()) + 1024 <= 32768
        payload = json.loads(body["messages"][1]["content"])
        current = payload["request"]
        assert not ({"gold", "agent_script", "expect", "boundaries"} & set(current))
        # The fixture controller deliberately asks for one repair; the same
        # complete evidence must survive the actual second-attempt gateway.
        count = len(current["evidence"]["hits"])
        bound = payload["decision_contracts"]["rules"]["answer"]["sources"]["maxItems"]
        indices = list(range(count)) if count <= bound else [1, 2]
        content = (
            "{}"
            if len(bodies) % 2
            else json.dumps(
                {
                    "context_sha256": current["context_sha256"],
                    "decision": "answer",
                    "sources": indices,
                }
            )
        )
        return httpx.Response(
            200,
            json={
                "model": "gpt-4o-mini",
                "usage": {"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": 130},
                "choices": [
                    {"finish_reason": "stop", "message": {"role": "assistant", "content": content}}
                ],
            },
        )

    def adapters(_case, _scenario):
        retriever, snapshot = factory({"arm": arm, "case_id": "dev-case-c"}, current_turn)
        gateway = MetisGroundedPlanner(_config(), ledger, transport=httpx.MockTransport(respond))

        class Planner:
            latest = None

            def plan(self, request, *, context):
                self.latest = request.model_copy(deep=True)
                requests.append(self.latest)
                contexts.append(context.model_copy(deep=True))
                return gateway.plan(request, context=context)

        planner = Planner()
        return api.RunAdapters(
            retriever,
            GroundedReasoner(
                planner,
                request_factory=caller_catalog,
                source_gap_handoff=True,
                source_gap_investigation=True,
                ask_source_background=True,
                concise_user_draft=True,
            ),
            snapshot_id=snapshot,
            grounded_request_supplier=lambda: planner.latest,
            cleanup=gateway.close,
        )

    def app():
        tracker = SQLiteCaseTracker(tracker_path, reviewer_tokens=reviewers)
        return tracker, create_app(
            tracker,
            reviewer_tokens=reviewers,
            case_adapters=adapters,
            evidence_scope="exact_user_version",
        )

    def review(pending, identity):
        return {
            "proposal_id": pending["proposal_id"],
            "case_revision": pending["case_revision"],
            "expected_handoff_sha256": pending["review_handoff"]["handoff_sha256"],
            "review_id": identity,
            "decision": "approve",
        }

    route = "/cases/dev-case-c"
    tracker, application = app()
    with offline_network(), TestClient(application) as client:
        pending = []
        for revision, turn in enumerate(fixture.data["turns"]):
            current_turn = turn
            response = client.post(
                route + "/messages",
                json={"turn_id": turn["id"], "expected_revision": revision, **turn["visible"]},
            )
            assert response.status_code == 200
            proposal = response.json()["pending"]
            assert proposal is not None, {
                "last_run": response.json().get("last_run"),
                "sends": len(bodies),
                "attempts": len(contexts),
            }
            pending.append(proposal)
            assert proposal["next_question"] is None
            expected = _retrieve(factory, {"arm": arm, "case_id": "dev-case-c"}, turn)
            assert requests[-1].evidence.hits == expected.hits
            assert requests[-2].evidence.hits == expected.hits
            assert contexts[-2].attempt_index == 1 and contexts[-1].attempt_index == 2
            assert contexts[-1].remaining_model_attempts == 0
        assert len(bodies) == len(requests) == 4
        assert (
            client.post(
                route + "/decision", json=review(pending[0], "stale-review"), headers=headers
            ).status_code
            == 409
        )
        accepted = review(pending[1], "current-review")
        assert client.post(route + "/decision", json=accepted, headers=headers).status_code == 200
        saved = tracker.comments("dev-case-c")
        assert len(saved) == 1
    restarted, application = app()
    with offline_network(), TestClient(application) as client:
        assert client.post(route + "/decision", json=accepted, headers=headers).status_code == 200
        assert restarted.comments("dev-case-c") == saved
        assert len(bodies) == 4
    active = {f.name: f.value for f in requests[-1].case.facts if f.status == "active"}
    assert active["streamlit_version"] == "1.31.1"
    assert "class Color(Enum):" in active["reported_reproduction_code"]
    assert any(f.value == "1.31.0" and f.status == "superseded" for f in requests[-1].case.facts)
    assert all(gap.kind == "source" for request in requests for gap in request.gaps)
    assert all("1.31.1" not in hit.applicable_versions for hit in requests[-1].evidence.hits)
    assert all(row["actual_search"] is False for row in records)
