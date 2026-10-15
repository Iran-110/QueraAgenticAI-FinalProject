"""Whole-output capacity controls, not claims about model support or RAG quality."""

import itertools
import json
from pathlib import Path

import pytest
from test_evaluation_live import KEY
from test_grounded_resource_guidance import (
    GAP,
    SOURCE_GAP,
    _context,
    _gateway,
    _plan,
    _request,
    _response,
)

from agent_app.contracts import Fact, GroundedRequest, ReasoningContext
from agent_app.llm.config import MetisConfig
from agent_app.llm.metis import configured_grounded_messages
from agent_app.orchestration import SupportEngine
from agent_app.reasoning.grounding import (
    UNRESOLVED_SOURCE_CONFLICT,
    GroundedReasoner,
    GroundingRejected,
    build_grounded_messages,
    make_grounded_request,
    render_grounded_plan,
)
from agent_app.reasoning.source_capacity import add_source_capacity, source_capacity
from agent_app.testing.http_pilot_runtime import offline_network

ROOT = Path(__file__).resolve().parents[1]
MODES = (
    {},
    {"source_gap_handoff": True},
    {"source_gap_handoff": True, "source_gap_investigation": True},
)


def sized_request(sizes, **changes):
    original = _request(count=len(sizes), **changes)
    return make_grounded_request(
        original.case,
        original.user_message,
        original.evidence.model_copy(
            update={
                "hits": tuple(
                    hit.model_copy(update={"excerpt": ("<code>&_*`فارسی\n" * size)[:size]})
                    for hit, size in zip(original.evidence.hits, sizes, strict=True)
                )
            }
        ),
        gaps=original.gaps,
        conflict_groups=original.conflict_groups,
    )


def wire(request, **flags):
    original = build_grounded_messages(request, _context(request), decision_contracts=True)
    return original, add_source_capacity(original, request, enabled=True, **flags)


@pytest.mark.parametrize("flags", MODES)
@pytest.mark.parametrize(
    "sizes", [(4000,) * 5, (100, 500, 5000, 6000), (500,) * 8, (15000, 500, 500)]
)
def test_every_subset_within_common_bound_renders_whole_escaped_sources(sizes, flags):
    request = sized_request(sizes)
    bound = source_capacity(request, **flags)
    if bound is None:
        # At least one large singleton cannot fit, so guidance must remain absent.
        assert wire(request, **flags)[0] == wire(request, **flags)[1]
        return
    ids = [h.chunk_id for h in request.evidence.hits]
    for count in range(min(bound, len(ids)) + 1):
        for selected in itertools.combinations(ids, count):
            for decision, question in (("answer", None), ("ask", GAP.name), ("escalate", None)):
                if decision == "answer" and not selected:
                    continue
                result = render_grounded_plan(
                    request, _plan(request, decision, selected, question), **flags
                )
                assert {r.chunk_id for r in result.evidence_links} == set(selected)
                assert len(result.maintainer_summary) <= 20000
                assert len(result.user_draft) <= 20000
                assert len(result.rationale) <= 2000


def test_count_bound_is_conservative_not_optimal_source_selection():
    request = _request(count=3, gaps=())
    request = make_grounded_request(
        request.case,
        request.user_message,
        request.evidence.model_copy(
            update={
                "hits": tuple(
                    h.model_copy(update={"excerpt": "a" * n})
                    for h, n in zip(request.evidence.hits, (19000, 500, 500), strict=True)
                )
            }
        ),
    )
    assert source_capacity(request) == 1
    ids = [h.chunk_id for h in request.evidence.hits]
    render_grounded_plan(request, _plan(request, "answer", ids[1:]))
    with pytest.raises(GroundingRejected, match="grounded_render_too_large"):
        render_grounded_plan(request, _plan(request, "answer", ids[:2]))


@pytest.mark.parametrize("kind", ["empty", "conflict", "prior_conflict", "singleton", "base"])
def test_unsupported_capacity_preserves_payload_and_original_guard(kind):
    if kind == "empty":
        request = _request(count=0)
    elif kind == "conflict":
        request = _request(conflicts=True, size=12000)
    elif kind == "prior_conflict":
        request = _request(gaps=(UNRESOLVED_SOURCE_CONFLICT,))
    elif kind == "singleton":
        request = sized_request((19000, 200))
    else:
        request = _request(gaps=(GAP.model_copy(update={"necessity": "&" * 500}),))
    assert source_capacity(request) is None
    original, candidate = wire(request)
    assert candidate is original
    if kind == "conflict":
        with pytest.raises(GroundingRejected, match="grounded_render_too_large"):
            render_grounded_plan(request, _plan(request, "escalate"))


def test_only_existing_count_bounds_change_no_prompt_growth_or_source_mutation():
    request = sized_request((4000,) * 5)
    original, candidate = wire(request)
    before, after = [json.loads(m[1]["content"]) for m in (original, candidate)]
    assert candidate[0] == original[0]
    assert len(json.dumps(candidate, ensure_ascii=False).encode()) <= len(
        json.dumps(original, ensure_ascii=False).encode()
    )
    bound = after["response_schema"]["properties"]["sources"]["maxItems"]
    assert 1 <= bound < 5
    after["response_schema"]["properties"]["sources"]["maxItems"] = 8
    for decision, rule in after["decision_contracts"]["rules"].items():
        assert rule["sources"]["maxItems"] == (0 if decision == "retrieve_more" else bound)
        rule["sources"]["maxItems"] = before["decision_contracts"]["rules"][decision]["sources"][
            "maxItems"
        ]
    assert before == after
    assert add_source_capacity(original, request) is original
    assert add_source_capacity(original, request, enabled=False) is original


def test_actual_archived_failure_is_not_rewritten_and_all_smaller_subsets_fit():
    receipt = json.loads(
        (ROOT / "experiments/core_repeat_repair_v1/model-live-receipt-v1.json").read_bytes()
    )
    batch = next(b for b in receipt["batches"] if b["batch_id"] == "repeat-r2-dev-case-c")
    attempt = batch["attempts"][1]
    request = GroundedRequest.model_validate(attempt["request"])
    flags = MODES[-1]
    assert source_capacity(request, **flags) == 3
    with pytest.raises(GroundingRejected, match="grounded_render_too_large"):
        render_grounded_plan(request, attempt["plan"], **flags)
    ids = [h.chunk_id for h in request.evidence.hits]
    for selected in itertools.combinations(ids, 3):
        render_grounded_plan(request, _plan(request, "answer", selected), **flags)


def test_archived_false_bytes_exact_and_on_never_increases_input_size():
    from agent_app.reasoning.source_selection import add_source_selection_reminder

    checked = 0
    for folder in ("dev_rag_coverage_v1", "core_resource_guidance_v1", "core_repeat_repair_v1"):
        receipt = json.loads(
            (ROOT / f"experiments/{folder}/model-live-receipt-v1.json").read_bytes()
        )
        for batch in receipt["batches"]:
            for attempt in batch["attempts"]:
                request = GroundedRequest.model_validate(attempt["request"])
                context = ReasoningContext.model_validate(attempt["context"])
                baseline = add_source_selection_reminder(
                    build_grounded_messages(request, context, decision_contracts=True), True
                )
                config = MetisConfig(
                    api_key=KEY,
                    response_mode="grounded_plan",
                    grounded_decision_contracts=True,
                    grounded_source_selection_reminder=True,
                    grounded_source_gap_handoff=True,
                    grounded_source_gap_investigation=True,
                )
                assert configured_grounded_messages(config, request, context) == baseline
                candidate = configured_grounded_messages(
                    config.model_copy(update={"grounded_source_capacity": True}), request, context
                )

                def size(messages):
                    return len(json.dumps(messages, ensure_ascii=False).encode()) + 1024

                assert size(candidate) <= size(baseline) <= 32768
                checked += 1
    assert checked == 79


def test_correction_recomputes_using_current_user_facts_without_cached_evidence():
    request = sized_request((4000,) * 5)
    case = request.case.model_copy(
        update={
            "case_revision": 3,
            "facts": (
                Fact(
                    name="streamlit_version",
                    value="1.49.0",
                    source_ref="USER:correction",
                    turn_id="correction",
                ),
            ),
        }
    )
    corrected = make_grounded_request(
        case,
        request.user_message,
        request.evidence.model_copy(update={"hits": request.evidence.hits[:1]}),
        gaps=(SOURCE_GAP,),
    )
    old, _ = wire(request)
    original, candidate = wire(corrected)
    assert candidate is original  # Whole current pool now fits; no stale cap retained.
    payload = json.loads(candidate[1]["content"])
    assert payload["request"]["case"]["case_revision"] == 3
    assert len(payload["source_references"]) == 1
    with pytest.raises(ValueError, match="SourceCapacityMessagesInvalid"):
        add_source_capacity(old, corrected, enabled=True)


@pytest.mark.parametrize("value", [None, 0, 1, "true", [], {}])
def test_strict_opt_in(value):
    with pytest.raises(ValueError):
        add_source_capacity(object(), object(), enabled=value)
    with pytest.raises(ValueError):
        MetisConfig(api_key=KEY, grounded_source_capacity=value)


@pytest.mark.parametrize("raw", ["true", "false", "TRUE", "1", "", "true "])
def test_env_and_dependencies(monkeypatch, raw):
    monkeypatch.setenv("METIS_API_KEY", KEY)
    monkeypatch.setenv("METIS_RESPONSE_MODE", "grounded_plan")
    monkeypatch.setenv("METIS_GROUNDED_DECISION_CONTRACTS", "true")
    monkeypatch.setenv("METIS_GROUNDED_SOURCE_CAPACITY", raw)
    if raw not in ("true", "false"):
        with pytest.raises(ValueError):
            MetisConfig.from_env()
    else:
        assert MetisConfig.from_env().grounded_source_capacity is (raw == "true")
    with pytest.raises(ValueError):
        MetisConfig(api_key=KEY, response_mode="grounded_plan", grounded_source_capacity=True)


def test_actual_gateway_guidance_is_not_authority_and_ignored_bound_stops_at_two_attempts(tmp_path):
    request = _request(count=5, size=4500, gaps=())
    request = make_grounded_request(
        request.case,
        request.user_message,
        request.evidence.model_copy(
            update={
                "hits": tuple(
                    h.model_copy(update={"excerpt": "a" * 4500}) for h in request.evidence.hits
                )
            }
        ),
    )

    class Retriever:
        def search(self, supplied):
            return request.evidence.model_copy(update={"queries_used": supplied.queries})

    def ignore_bound(wire):
        payload = json.loads(json.loads(wire.content)["messages"][1]["content"])
        assert payload["response_schema"]["properties"]["sources"]["maxItems"] < 5
        return _response(
            payload["request"], "answer", selected=[h.chunk_id for h in request.evidence.hits]
        )

    gateway, ledger, calls = _gateway(tmp_path, ignore_bound, grounded_source_capacity=True)
    with gateway, offline_network():
        result = SupportEngine(
            Retriever(), GroundedReasoner(gateway), snapshot_id=request.evidence.snapshot_id
        ).run(request.case, "Short query")
    assert result.error_code == "ModelOutputInvalid"
    assert result.model_attempts == len(calls) == 2
    assert [i.code for i in result.output_issues] == ["grounded_render_too_large"] * 2
    assert ledger.snapshot().uncertain_usd == 0


@pytest.mark.parametrize("raw", ["true", "false", "TRUE", "1", "true "])
def test_configured_factory_validates_flag_before_key_and_keeps_it(tmp_path, monkeypatch, raw):
    from test_grounded_configuration_flags import configuration

    from agent_app.evaluation import live

    ledger, values = configuration(tmp_path, ("synthetic", "snapshot", "a" * 64), monkeypatch)
    monkeypatch.setattr(live, "_verified_index", lambda *_: None)
    values["METIS_GROUNDED_SOURCE_CAPACITY"] = raw
    values["METIS_GROUNDED_DECISION_CONTRACTS"] = "true"
    reads = []

    class Sensitive(dict):
        def get(self, key, *args):
            if key == "METIS_API_KEY":
                reads.append(key)
            return super().get(key, *args)

    with offline_network():
        if raw not in ("true", "false"):
            with pytest.raises(ValueError):
                live.configured_factory(Sensitive(values))
            assert not reads
        else:
            factory = live.configured_factory(Sensitive(values))
            assert factory._config.grounded_source_capacity is (raw == "true")
    ledger.halt()
    with offline_network(), pytest.raises(ValueError, match="LiveLedgerHalted"):
        live.configured_factory(values)
