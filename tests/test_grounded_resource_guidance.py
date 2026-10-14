"""Exact renderer costs and bounded mock wires; no model-quality claim."""

import hashlib
import itertools
import json
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from test_evaluation_live import KEY, CountedMock, provider_response, run
from test_evaluation_live import index as index
from test_grounded_configuration_flags import configuration

from agent_app.contracts import (
    CaseState,
    EvidenceBundle,
    EvidenceHit,
    Fact,
    GroundedGap,
    GroundedPlan,
    OutputFeedback,
    OutputIssue,
    ReasoningContext,
)
from agent_app.evaluation import live
from agent_app.llm.budget import BudgetLedger
from agent_app.llm.config import MetisConfig
from agent_app.llm.grounded import MetisGroundedPlanner
from agent_app.llm.metis import request_id_for
from agent_app.orchestration import SupportEngine
from agent_app.orchestration.ports import ReasoningStopped
from agent_app.reasoning.catalog import caller_catalog
from agent_app.reasoning.grounding import (
    UNRESOLVED_SOURCE_CONFLICT,
    GroundedReasoner,
    GroundingRejected,
    build_grounded_messages,
    make_grounded_request,
    render_grounded_plan,
    source_content_sha256,
)
from agent_app.reasoning.resource_guidance import RESOURCE_GUIDANCE, add_resource_guidance
from agent_app.reasoning.source_selection import add_source_selection_reminder
from agent_app.testing.http_pilot_runtime import offline_network

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ("user_draft", "maintainer_summary", "rationale")
GAP = GroundedGap(
    name="streamlit_version",
    kind="user",
    description="Installed release is not supplied.",
    necessity="The USER can report the affected release to select applicable sources.",
    question="Which Streamlit release is installed?",
)
SOURCE_GAP = GroundedGap(
    name="exact_version_documentation",
    kind="source",
    description="No supplied source establishes a successful fix.",
    necessity="Investigate applicable documentation or the reproduction.",
)


def _request(*, count=3, size=100, conflicts=False, gaps=(GAP, SOURCE_GAP), case=None):
    hits = tuple(
        EvidenceHit(
            chunk_id=f"resource:{i}",
            source_id=f"resource-source:{i}",
            excerpt=("A <rule> with `code`, *scope*, & qualification. فارسی\n" * size)[:size],
            source_url=f"https://example.org/rule/{i}",
            source_type="doc",
            applicable_versions=("1.50.0",),
            source_span=f"whole record {i}",
        )
        for i in range(count)
    )
    return make_grounded_request(
        case or CaseState(case_id="resource-case", case_revision=2),
        "The reported full application fails; no cause is established.",
        EvidenceBundle(
            snapshot_id="resource-snapshot", hits=hits, queries_used=("Streamlit  session_state",)
        ),
        gaps=gaps,
        conflict_groups=((hits[0].chunk_id, hits[1].chunk_id),) if conflicts else (),
    )


def _context(request, **changes):
    return ReasoningContext(
        **(
            {
                "run_id": "resource-run",
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


def _messages(request, context=None, **flags):
    return add_resource_guidance(
        build_grounded_messages(request, context or _context(request), decision_contracts=True),
        request,
        enabled=True,
        **flags,
    )


def _resources(request, **flags):
    return json.loads(_messages(request, **flags)[1]["content"])["render_resources"]


def _plan(request, decision, selected=(), question=None):
    return GroundedPlan(
        context_sha256=request.context_sha256,
        decision=decision,
        sources=tuple(
            {"chunk_id": hit.chunk_id, "content_sha256": source_content_sha256(hit)}
            for hit in request.evidence.hits
            if hit.chunk_id in selected
        ),
        question_name=question,
    )


def _expected(resources, decision, selected=(), question=None, *, request):
    key = f"ask:{question}" if question is not None else decision
    base = resources["bases"][key]
    assert type(base) is list
    selected = {i for i, hit in enumerate(request.evidence.hits) if hit.chunk_id in selected} | set(
        resources["mandatory"]
    )
    q = (
        sum(resources["source_chars"][chunk] for chunk in selected) + 2 * (len(selected) - 1)
        if selected
        else 0
    )
    return [
        base[0] + (q if decision == "answer" else 0),
        base[1] + (q + 2 if selected else 0),
        base[2],
    ]


@pytest.mark.parametrize(
    "flags",
    [
        {},
        {"source_gap_handoff": True},
        {"source_gap_handoff": True, "source_gap_investigation": True},
    ],
)
@pytest.mark.parametrize("conflicts", [False, True])
def test_exact_lengths_reconstruct_every_complete_source_subset_and_renderer_mode(flags, conflicts):
    request = _request(conflicts=conflicts)
    resources = _resources(request, **flags)
    ids = [hit.chunk_id for hit in request.evidence.hits]
    assert resources["limits"] == [20_000, 20_000, 2_000]
    assert resources["mandatory"] == ([0, 1] if conflicts else [])
    for size in range(len(ids) + 1):
        for selected in itertools.combinations(ids, size):
            for decision, question in (("answer", None), ("ask", GAP.name), ("escalate", None)):
                if decision == "answer" and (not selected or conflicts):
                    continue
                actual = render_grounded_plan(
                    request, _plan(request, decision, selected, question), **flags
                )
                assert _expected(resources, decision, selected, question, request=request) == [
                    len(getattr(actual, field)) for field in FIELDS
                ]
    if conflicts:
        assert resources["bases"]["answer"] == "grounded_conflict_unresolved"


def test_only_optional_metadata_and_system_append_change_original_input_and_schema():
    request = _request()
    original = build_grounded_messages(request, _context(request), decision_contracts=True)
    before = json.dumps(original, ensure_ascii=False)
    assert add_resource_guidance(original, request) is original
    assert add_resource_guidance(original, request, enabled=False) is original
    candidate = _messages(request)
    assert candidate[0]["content"] == original[0]["content"] + "\n\n" + RESOURCE_GUIDANCE
    payload = json.loads(candidate[1]["content"])
    payload.pop("render_resources")
    assert payload == json.loads(original[1]["content"])
    assert json.dumps(original, ensure_ascii=False) == before
    assert "queries_used" in candidate[0]["content"]
    assert "casefold" in candidate[0]["content"]
    assert "split/join" in candidate[0]["content"]
    # No redundant query/source text is copied into the guidance metadata.
    assert request.evidence.queries_used[0] not in json.dumps(_resources(request))
    assert request.evidence.hits[0].excerpt not in json.dumps(_resources(request))


def test_all_archived_c4g_actual_requests_keep_false_prompt_bytes_exact():
    receipt = json.loads(
        (ROOT / "experiments/dev_rag_coverage_v1/model-live-receipt-v1.json").read_bytes()
    )
    observed = 0
    from agent_app.contracts import GroundedRequest

    for batch in receipt["batches"]:
        for attempt in batch["attempts"]:
            request = GroundedRequest.model_validate(attempt["request"])
            context = ReasoningContext.model_validate(attempt["context"])
            original = add_source_selection_reminder(
                build_grounded_messages(request, context, decision_contracts=True), True
            )
            false = add_resource_guidance(
                original,
                request,
                enabled=False,
                source_gap_handoff=True,
                source_gap_investigation=True,
            )
            assert false is original
            assert (
                json.dumps(false, ensure_ascii=False).encode()
                == json.dumps(original, ensure_ascii=False).encode()
            )
            observed += 1
    assert observed == 29


@pytest.mark.parametrize("enabled", [None, 0, 1, "true", [], {}])
def test_guidance_boolean_is_strict_before_data_inspection(enabled):
    with pytest.raises(ValueError, match="^ResourceGuidanceFlagInvalid$"):
        add_resource_guidance(object(), object(), enabled=enabled)


@pytest.mark.parametrize("field", ["source_gap_handoff", "source_gap_investigation"])
@pytest.mark.parametrize("bad", [None, 0, "true"])
def test_renderer_mode_flags_are_strict(field, bad):
    with pytest.raises(ValueError, match="^ResourceGuidanceFlagInvalid$"):
        add_resource_guidance(object(), object(), **{field: bad})


def test_investigation_requires_handoff():
    with pytest.raises(ValueError, match="^ResourceGuidanceFlagInvalid$"):
        add_resource_guidance(object(), object(), source_gap_investigation=True)


@pytest.mark.parametrize("bad", [None, 0, 1, "true"])
def test_config_flag_requires_boolean_and_plan_mode(bad):
    with pytest.raises(ValueError):
        MetisConfig(api_key=KEY, response_mode="grounded_plan", grounded_resource_guidance=bad)


def test_resource_config_does_not_silently_authorize_live_or_analysis():
    with pytest.raises(ValueError):
        MetisConfig(api_key=KEY, grounded_resource_guidance=True)
    config = MetisConfig(
        api_key=KEY, response_mode="grounded_plan", grounded_resource_guidance=True
    )
    assert config.grounded_resource_guidance and not config.live_enabled


@pytest.mark.parametrize("raw", ["true", "false"])
def test_env_flag_round_trips_explicit_value(monkeypatch, raw):
    monkeypatch.setenv("METIS_API_KEY", KEY)
    monkeypatch.setenv("METIS_RESPONSE_MODE", "grounded_plan")
    monkeypatch.setenv("METIS_GROUNDED_RESOURCE_GUIDANCE", raw)
    assert MetisConfig.from_env().grounded_resource_guidance is (raw == "true")


@pytest.mark.parametrize("raw", ["", "TRUE", "1", "true "])
def test_bad_env_flag_is_not_coerced(monkeypatch, raw):
    monkeypatch.setenv("METIS_API_KEY", KEY)
    monkeypatch.setenv("METIS_GROUNDED_RESOURCE_GUIDANCE", raw)
    with pytest.raises(ValueError):
        MetisConfig.from_env()


@pytest.mark.parametrize("raw", ["", "TRUE", "1", "true "])
def test_bad_configured_flag_stops_before_credentials(tmp_path, index, monkeypatch, raw):
    _, values = configuration(tmp_path, index, monkeypatch)
    values["METIS_GROUNDED_RESOURCE_GUIDANCE"] = raw
    reads = []

    class Sensitive(dict):
        def get(self, key, *args):
            if key == "METIS_API_KEY":
                reads.append(key)
            return super().get(key, *args)

    with offline_network(), pytest.raises(ValueError):
        live.configured_factory(Sensitive(values))
    assert reads == []


def test_new_configured_flag_preserves_ordinary_ledger_halt(tmp_path, index, monkeypatch):
    ledger, values = configuration(tmp_path, index, monkeypatch)
    ledger.halt()
    values["METIS_GROUNDED_RESOURCE_GUIDANCE"] = "true"
    with offline_network(), pytest.raises(ValueError, match="LiveLedgerHalted"):
        live.configured_factory(values)


def test_measured_overflow_is_predicted_without_shortening_quotations():
    request = _request(count=5, size=4500)
    resources = _resources(request, source_gap_handoff=True, source_gap_investigation=True)
    selected = [hit.chunk_id for hit in request.evidence.hits]
    expected = _expected(resources, "answer", selected, request=request)
    assert expected[0] > resources["limits"][0] or expected[1] > resources["limits"][1]
    with pytest.raises(GroundingRejected) as failure:
        render_grounded_plan(
            request,
            _plan(request, "answer", selected),
            source_gap_handoff=True,
            source_gap_investigation=True,
        )
    assert failure.value.code == "grounded_render_too_large"
    assert json.loads(_messages(request)[1]["content"])["request"] == request.model_dump(
        mode="json"
    )


def test_unmeasurable_base_reports_fixed_error_and_later_fitting_singleton_is_used():
    request = _request(count=1, size=18_000)
    resources = _resources(request)
    assert resources["bases"]["answer"] == "grounded_render_too_large"
    assert type(resources["bases"]["escalate"]) is list
    short = request.evidence.hits[0].model_copy(
        update={"chunk_id": "resource:short", "excerpt": "Short complete excerpt."}
    )
    request = make_grounded_request(
        request.case,
        request.user_message,
        request.evidence.model_copy(update={"hits": (*request.evidence.hits, short)}),
        gaps=request.gaps,
    )
    resources = _resources(request)
    assert type(resources["bases"]["answer"]) is list
    actual = render_grounded_plan(request, _plan(request, "answer", (short.chunk_id,)))
    assert _expected(resources, "answer", (short.chunk_id,), request=request) == [
        len(getattr(actual, field)) for field in FIELDS
    ]


def test_prior_conflict_empty_evidence_and_many_hits_remain_bounded():
    prior = _request(gaps=(UNRESOLVED_SOURCE_CONFLICT,))
    assert _resources(prior)["bases"]["answer"] == "grounded_conflict_unresolved"
    empty = _request(count=0)
    assert set(_resources(empty)["bases"]) == {"escalate", f"ask:{GAP.name}"}
    many = _request(count=100)
    resources = _resources(many)
    assert len(resources["source_chars"]) == 100
    assert len(resources["bases"]) == 3
    assert GroundedPlan.model_json_schema()["properties"]["sources"]["maxItems"] == 8


def test_feedback_and_current_correction_use_current_data_and_keep_billable_identity():
    request = _request()
    first = _context(request)
    repair = _context(
        request,
        attempt_index=2,
        remaining_model_attempts=0,
        can_refine=False,
        output_feedback=OutputFeedback(issues=(OutputIssue(code="grounded_render_too_large"),)),
    )
    payload = json.loads(_messages(request, repair)[1]["content"])
    assert payload["repair_issue_codes"] == ["grounded_render_too_large"]
    assert not payload["capacity"]["can_refine"]
    assert _resources(request) == payload["render_resources"]
    assert request_id_for(first) == request_id_for(first.model_copy(update={"can_refine": False}))
    corrected = request.case.model_copy(
        update={
            "case_revision": 3,
            "facts": (
                Fact(
                    name="streamlit_version",
                    value="1.49.0",
                    source_ref="USER:correction",
                    turn_id="turn:correction",
                ),
            ),
        }
    )
    current = caller_catalog(corrected, request.user_message, request.evidence)
    payload = json.loads(_messages(current)[1]["content"])
    assert f"ask:{GAP.name}" not in payload["render_resources"]["bases"]
    assert payload["request"]["case"]["facts"][0]["value"] == "1.49.0"
    assert payload["render_resources"]["source_chars"] != _resources(request)["source_chars"]


def _gateway(tmp_path, respond, **changes):
    ledger = BudgetLedger.create(
        tmp_path / "resource-ledger.sqlite3", limit_usd=Decimal("1"), opening_spend_usd=Decimal("0")
    )
    config = MetisConfig(
        api_key=KEY,
        live_enabled=True,
        response_mode="grounded_plan",
        grounded_decision_contracts=True,
        grounded_resource_guidance=True,
        **changes,
    )
    calls = []

    def intercepted(request):
        calls.append(request)
        return respond(request)

    return (
        MetisGroundedPlanner(config, ledger, transport=httpx.MockTransport(intercepted)),
        ledger,
        calls,
    )


def test_guidance_preserves_normalized_repeat_guard_and_consumes_no_extra_attempt(tmp_path):
    request = _request()

    class Retriever:
        calls = 0

        def search(self, supplied):
            self.calls += 1
            return request.evidence.model_copy(update={"queries_used": supplied.queries})

    def repeat(wire):
        supplied = json.loads(json.loads(wire.content)["messages"][1]["content"])["request"]
        query = supplied["evidence"]["queries_used"][0]
        repeated = "  ".join(query.swapcase().split())
        return _response(supplied, "retrieve_more", queries=[repeated])

    gateway, ledger, calls = _gateway(tmp_path, repeat)
    retriever = Retriever()
    with gateway, offline_network():
        result = SupportEngine(
            retriever, GroundedReasoner(gateway), snapshot_id=request.evidence.snapshot_id
        ).run(request.case, "Short query")
    assert result.error_code == "RepeatedQuery" and result.model_attempts == 1
    assert result.retrieval_rounds == retriever.calls == len(calls) == 1
    assert ledger.snapshot().uncertain_usd == 0
    assert "render_resources" in json.loads(json.loads(calls[0].content)["messages"][1]["content"])


def _response(supplied, decision, *, queries=(), selected=()):
    refs = [
        {
            "chunk_id": hit["chunk_id"],
            "content_sha256": source_content_sha256(EvidenceHit.model_validate(hit)),
        }
        for hit in supplied["evidence"]["hits"]
        if hit["chunk_id"] in selected
    ]
    plan = {
        "context_sha256": supplied["context_sha256"],
        "decision": decision,
        "sources": refs,
        "question_name": None,
        "retrieval_queries": list(queries),
    }
    return httpx.Response(
        200,
        json={
            "model": "gpt-4o-mini-2024-07-18",
            "usage": {"prompt_tokens": 100, "completion_tokens": 80, "total_tokens": 180},
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": json.dumps(plan)},
                }
            ],
        },
    )


def test_ignored_size_guidance_still_stops_after_original_two_attempts(tmp_path):
    request = _request(count=5, size=4500, gaps=())
    request = make_grounded_request(
        request.case,
        request.user_message,
        request.evidence.model_copy(
            update={
                "hits": tuple(
                    hit.model_copy(update={"excerpt": "a" * 4500}) for hit in request.evidence.hits
                )
            }
        ),
    )

    class Retriever:
        def search(self, supplied):
            return request.evidence.model_copy(update={"queries_used": supplied.queries})

    def all_sources(wire):
        supplied = json.loads(json.loads(wire.content)["messages"][1]["content"])["request"]
        return _response(
            supplied, "answer", selected=[hit["chunk_id"] for hit in supplied["evidence"]["hits"]]
        )

    gateway, ledger, calls = _gateway(tmp_path, all_sources)
    with gateway, offline_network():
        result = SupportEngine(
            Retriever(), GroundedReasoner(gateway), snapshot_id=request.evidence.snapshot_id
        ).run(request.case, "Short query")
    assert result.error_code == "ModelOutputInvalid"
    assert result.model_attempts == len(calls) == 2
    assert [issue.code for issue in result.output_issues] == ["grounded_render_too_large"] * 2
    assert ledger.snapshot().uncertain_usd == 0


def test_utf8_input_guard_remains_before_reservation_or_provider_send(tmp_path):
    request = _request(size=3000)
    gateway, ledger, calls = _gateway(tmp_path, provider_response, input_token_reserve=4096)
    with gateway, offline_network(), pytest.raises(ReasoningStopped) as failure:
        gateway.plan(request, context=_context(request))
    assert failure.value.code == "ContextLimitExceeded"
    assert calls == [] and ledger.snapshot().reserved_usd == ledger.snapshot().settled_usd == 0


def test_real_configured_adapter_wire_hash_matches_full_enriched_guidance(tmp_path, index):
    ledger = BudgetLedger.create(
        tmp_path / "live-ledger.sqlite3", limit_usd=Decimal("1"), opening_spend_usd=Decimal("0")
    )
    wires = []

    def respond(request):
        wires.append(json.loads(request.content))
        return provider_response(request)

    config = MetisConfig(
        api_key=KEY,
        live_enabled=True,
        response_mode="grounded_plan",
        grounded_decision_contracts=True,
        grounded_source_gap_handoff=True,
        grounded_source_gap_investigation=True,
        grounded_source_selection_reminder=True,
        grounded_resource_guidance=True,
    )
    factory = live.LiveEvaluationAdapters(
        index_path=index[0],
        snapshot_id=index[1],
        manifest_sha256=index[2],
        ledger=ledger,
        config=config,
        transport_factory=lambda: CountedMock(respond),
    )
    with offline_network():
        result, _, _, frame = run(
            factory, CaseState(case_id="live-resource-case"), "Need help with state"
        )
    assert result.status == "awaiting_approval"
    usage = factory.observations_for_contexts((frame.context,))
    assert len(wires) == len(usage) == 1
    assert "render_resources" in json.loads(wires[0]["messages"][1]["content"])
    expected_hash = hashlib.sha256(
        json.dumps(wires[0]["messages"], ensure_ascii=False).encode()
    ).hexdigest()
    assert usage[0]["prompt_sha256"] == expected_hash
    assert usage[0]["http_send_started"] and usage[0]["ledger_status"] == "settled"
    factory.close()


@pytest.mark.parametrize(
    "bad",
    [
        (),
        ({"role": "system", "content": "secret"}, {"role": "system", "content": "secret"}),
        (
            {"role": "system", "content": "secret"},
            {"role": "user", "content": "{broken-private-input"},
        ),
    ],
)
def test_bad_messages_export_only_fixed_diagnostic(bad):
    with pytest.raises(ValueError, match="^ResourceGuidanceMessagesInvalid$") as failure:
        add_resource_guidance(bad, _request(), enabled=True)
    assert "secret" not in str(failure.value)
