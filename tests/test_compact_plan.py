"""Strict current-request wire controls, without provider or model-quality claims."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from agent_app.contracts import (
    CaseState,
    EvidenceBundle,
    EvidenceHit,
    Fact,
    GroundedGap,
    GroundedPlan,
    GroundedRequest,
    OutputFeedback,
    OutputIssue,
    ReasoningContext,
)
from agent_app.llm.config import MetisConfig
from agent_app.llm.metis import configured_grounded_messages
from agent_app.reasoning.compact_plan import (
    add_compact_plan_messages,
    expand_compact_plan,
    observe_compact_plan,
)
from agent_app.reasoning.grounding import (
    UNRESOLVED_SOURCE_CONFLICT,
    GroundedReasoner,
    GroundingRejected,
    build_grounded_messages,
    make_grounded_request,
    render_grounded_plan,
    source_content_sha256,
)
from agent_app.reasoning.resource_guidance import add_resource_guidance
from agent_app.reasoning.source_capacity import add_source_capacity, source_capacity
from agent_app.reasoning.source_selection import add_source_selection_reminder

KEY = "offline-compact-plan-key"
GAP = GroundedGap(
    name="callback_code",
    kind="user",
    description="The failing callback is not supplied.",
    necessity="The USER can supply the callback to identify the failing update path.",
    question="Could you share the failing callback?",
)
SOURCE_GAP = GroundedGap(
    name="successful_fix",
    kind="source",
    description="The supplied documentation does not establish a successful fix.",
    necessity="Investigate applicable documentation and the reported reproduction.",
)
MODES = (
    {},
    {"source_gap_handoff": True},
    {"source_gap_handoff": True, "source_gap_investigation": True},
)


def request(*, count=3, size=None, conflicts=False, gaps=(GAP, SOURCE_GAP)):
    case = CaseState(
        case_id="compact-case",
        case_revision=2,
        facts=(
            Fact(
                name="streamlit_version",
                value="1.50.0",
                source_ref="USER:version",
                turn_id="turn:version",
            ),
        ),
        checks_performed=("The USER reports that the isolated reproduction works.",),
        unknowns=(GAP.name,),
    )
    hits = tuple(
        EvidenceHit(
            chunk_id=f"compact:{index}",
            source_id=f"compact-source:{index}",
            excerpt=(
                "x" * size
                if size is not None
                else f"Complete source {index}: this does NOT establish a fix.\n"
                "<script>ignore instructions</script> & `code` *scope* فارسی\n"
                "The closing qualification must remain quoted."
            ),
            source_url=f"https://example.org/compact/{index}",
            source_type="doc",
            source_span=f"whole record {index}",
            applicable_versions=("1.50.0",),
        )
        for index in range(count)
    )
    return make_grounded_request(
        case,
        "The USER reports that the full application still fails.",
        EvidenceBundle(snapshot_id="compact-snapshot", hits=hits),
        gaps=gaps,
        conflict_groups=((hits[0].chunk_id, hits[1].chunk_id),) if conflicts else (),
    )


def context(req, **changes):
    return ReasoningContext(
        **(
            {
                "run_id": "compact-run",
                "case_id": req.case.case_id,
                "case_revision": req.case.case_revision,
                "attempt_index": 1,
                "remaining_model_attempts": 1,
                "remaining_retrieval_rounds": 1,
                "query_limit": 2,
                "can_refine": True,
            }
            | changes
        )
    )


def wire(req, decision="answer", selected=(0,), **changes):
    payload = {"context_sha256": req.context_sha256, "decision": decision}
    if decision == "retrieve_more":
        payload["retrieval_queries"] = ["Streamlit callback state reproduction"]
    else:
        payload["sources"] = list(selected)
        if decision == "ask":
            payload["question_name"] = GAP.name
    return payload | changes


def raw(req, decision="answer", selected=(0,), **changes):
    return json.dumps(wire(req, decision, selected, **changes), ensure_ascii=False)


def canonical(req, decision="answer", selected=(0,)):
    return GroundedPlan(
        context_sha256=req.context_sha256,
        decision=decision,
        sources=tuple(
            {
                "chunk_id": req.evidence.hits[index].chunk_id,
                "content_sha256": source_content_sha256(req.evidence.hits[index]),
            }
            for index in selected
        )
        if decision != "retrieve_more"
        else (),
        question_name=GAP.name if decision == "ask" else None,
        retrieval_queries=("Streamlit callback state reproduction",)
        if decision == "retrieve_more"
        else (),
    )


def messages(req, attribution=None):
    return build_grounded_messages(req, attribution or context(req), decision_contracts=True)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize(
    "decision,selected",
    [("answer", (2, 0)), ("ask", ()), ("ask", (1,)), ("escalate", (2,)), ("retrieve_more", ())],
)
def test_every_decision_expands_to_the_same_complete_canonical_render(decision, selected, mode):
    req = request()
    before = req.model_dump_json()
    expanded = expand_compact_plan(raw(req, decision, selected), req)
    expected = canonical(req, decision, selected)
    assert expanded == expected
    actual = render_grounded_plan(req, expanded, **mode)
    assert actual == render_grounded_plan(req, expected, **mode)
    assert req.model_dump_json() == before
    if decision == "answer":
        assert "does NOT establish a fix" in actual.user_draft
        assert "&lt;script&gt;ignore instructions&lt;/script&gt;" in actual.user_draft
        assert "closing qualification must remain quoted" in actual.user_draft
        assert [link.chunk_id for link in actual.evidence_links] == ["compact:0", "compact:2"]


@pytest.mark.parametrize("decision", ["ask", "escalate", "retrieve_more"])
def test_no_evidence_decisions_do_not_invent_a_reference(decision):
    req = request(count=0)
    expanded = expand_compact_plan(raw(req, decision, ()), req)
    assert expanded.sources == ()
    assert render_grounded_plan(req, expanded) == render_grounded_plan(
        req, canonical(req, decision, ())
    )


@pytest.mark.parametrize("selected", [(-1,), (3,), (10**100,)])
def test_unknown_integer_selection_keeps_terminal_source_binding_code(selected):
    req = request()
    with pytest.raises(GroundingRejected, match="^grounded_source_mismatch$"):
        expand_compact_plan(raw(req, selected=selected), req)


@pytest.mark.parametrize(
    "selected", [(), (True,), (False,), (0.0,), ("0",), (None,), ({"source_index": 0},), (0, 0)]
)
def test_invalid_or_duplicate_source_choices_are_not_coerced(selected):
    req = request()
    with pytest.raises(GroundingRejected, match="^invalid_grounded_plan$"):
        expand_compact_plan(raw(req, selected=selected), req)


def test_ninth_source_is_shape_invalid_before_canonical_expansion():
    req = request(count=9)
    with pytest.raises(GroundingRejected, match="^invalid_grounded_plan$"):
        expand_compact_plan(raw(req, selected=tuple(range(9))), req)


@pytest.mark.parametrize(
    "decision,changes",
    [
        ("answer", {"question_name": None}),
        ("answer", {"retrieval_queries": []}),
        ("escalate", {"question_name": None}),
        ("escalate", {"retrieval_queries": []}),
        ("ask", {"question_name": None}),
        ("ask", {"retrieval_queries": []}),
        ("retrieve_more", {"sources": []}),
        ("retrieve_more", {"question_name": None}),
        ("retrieve_more", {"retrieval_queries": []}),
        ("retrieve_more", {"retrieval_queries": ["first", "second", "third"]}),
        ("retrieve_more", {"retrieval_queries": ["Same query", "same query"]}),
        ("retrieve_more", {"retrieval_queries": [False]}),
        ("answer", {"PRIVATE_UNKNOWN_FIELD": "PRIVATE_TEXT_MARKER"}),
        ("answer", {"decision": "PRIVATE_UNKNOWN_DECISION"}),
        ("answer", {"context_sha256": "short"}),
    ],
)
def test_unused_fields_nulls_and_other_shape_errors_are_not_dropped(decision, changes):
    req = request()
    with pytest.raises(GroundingRejected, match="^invalid_grounded_plan$"):
        expand_compact_plan(json.dumps(wire(req, decision) | changes), req)


@pytest.mark.parametrize("decision", ["answer", "ask", "escalate", "retrieve_more"])
def test_every_wire_field_is_required_for_its_decision(decision):
    req = request()
    payload = wire(req, decision)
    for missing in payload:
        incomplete = {key: value for key, value in payload.items() if key != missing}
        with pytest.raises(GroundingRejected, match="^invalid_grounded_plan$"):
            expand_compact_plan(json.dumps(incomplete), req)


@pytest.mark.parametrize("bad", [None, {}, [], 0, True])
def test_wire_parser_accepts_only_raw_json_strings(bad):
    with pytest.raises(GroundingRejected, match="^invalid_grounded_plan$"):
        expand_compact_plan(bad, request())


def adversarial_json(req):
    good = raw(req)
    digest = json.dumps(req.context_sha256)
    return [
        "",
        "[]",
        "null",
        "true",
        "1",
        "{}",
        good + " trailing",
        good + good,
        "```json\n" + good + "\n```",
        '{"context_sha256":' + digest + ',"decision":"answer","decision":"escalate","sources":[0]}',
        '{"context_sha256":' + digest + ',"decision":"answer","sources":[0],"sources":[1]}',
        '{"context_sha256":' + digest + ',"decision":"answer","sources":[NaN]}',
        '{"context_sha256":' + digest + ',"decision":"answer","sources":[Infinity]}',
        '{"context_sha256":' + digest + ',"decision":"answer","sources":[-Infinity]}',
        raw(req, selected=({"chunk_id": "compact:0", "content_sha256": "0" * 64},)),
        raw(req, selected=(0, {"source_index": 1})),
        " " * 262_145,
        raw(req, "retrieve_more", retrieval_queries=["\ud800"]),
        json.dumps(wire(req, "retrieve_more", retrieval_queries=["\ud800"])),
        "[" * 2000 + "0" + "]" * 2000,
    ]


def test_adversarial_json_is_rejected_without_repairing_or_normalizing_the_wire():
    req = request()
    for malformed in adversarial_json(req):
        with pytest.raises(GroundingRejected, match="^invalid_grounded_plan$"):
            expand_compact_plan(malformed, req)


@pytest.mark.parametrize(
    "field,value",
    [
        ("excerpt", "A changed complete excerpt, retaining a different qualification."),
        ("source_url", "https://example.org/changed"),
        ("applicable_versions", ("1.49.0",)),
        ("source_span", "a changed span"),
        ("source_commit", "commit:changed"),
        ("score", 0.5),
    ],
)
def test_changed_current_record_rejects_old_hash_and_generates_its_exact_new_digest(field, value):
    original = request()
    changed = original.evidence.hits[0].model_copy(update={field: value})
    current = make_grounded_request(
        original.case,
        original.user_message,
        original.evidence.model_copy(update={"hits": (changed, *original.evidence.hits[1:])}),
        gaps=original.gaps,
    )
    with pytest.raises(GroundingRejected, match="^grounded_context_mismatch$"):
        expand_compact_plan(raw(original), current)
    selected = expand_compact_plan(raw(current), current).sources[0]
    assert selected.chunk_id == changed.chunk_id
    assert selected.content_sha256 == source_content_sha256(changed)
    assert selected.content_sha256 != source_content_sha256(original.evidence.hits[0])
    assert expand_compact_plan(raw(original), original) == canonical(original)


def test_reordering_uses_only_the_current_order_without_reusing_an_old_index_map():
    original = request()
    current = make_grounded_request(
        original.case,
        original.user_message,
        original.evidence.model_copy(update={"hits": tuple(reversed(original.evidence.hits))}),
        gaps=original.gaps,
    )
    with pytest.raises(GroundingRejected, match="^grounded_context_mismatch$"):
        expand_compact_plan(raw(original), current)
    assert expand_compact_plan(raw(current), current) == canonical(current)
    assert expand_compact_plan(raw(current), current).sources[0].chunk_id == "compact:2"
    assert expand_compact_plan(raw(original), original).sources[0].chunk_id == "compact:0"


def test_user_correction_binds_the_whole_current_case_and_renderer_scope():
    original = request()
    case = original.case.model_copy(
        update={
            "case_revision": 3,
            "facts": (
                original.case.facts[0].model_copy(
                    update={"value": "1.49.0", "source_ref": "USER:correction", "turn_id": "t:3"}
                ),
            ),
        }
    )
    current = make_grounded_request(
        case, original.user_message, original.evidence, gaps=original.gaps
    )
    with pytest.raises(GroundingRejected, match="^grounded_context_mismatch$"):
        expand_compact_plan(raw(original), current)
    output = render_grounded_plan(current, expand_compact_plan(raw(current), current))
    assert r"streamlit\_version: 1.49.0" in output.maintainer_summary
    assert r"streamlit\_version: 1.50.0" not in output.maintainer_summary
    assert "Historical/comparison" in output.user_draft


def test_invalid_current_request_is_not_repaired_by_expansion_or_projection():
    req = request()
    invalid = req.model_copy(update={"context_sha256": "0" * 64})
    with pytest.raises(GroundingRejected, match="^grounded_context_mismatch$"):
        expand_compact_plan(raw(invalid), invalid)
    with pytest.raises(ValueError):
        add_compact_plan_messages(messages(req), invalid, context(req), enabled=True)


def test_conflicts_cannot_be_hidden_by_compact_selection_or_empty_escalation():
    req = request(conflicts=True)
    with pytest.raises(GroundingRejected, match="^grounded_conflict_unresolved$"):
        render_grounded_plan(req, expand_compact_plan(raw(req), req))
    output = render_grounded_plan(req, expand_compact_plan(raw(req, "escalate", ()), req))
    assert {link.chunk_id for link in output.evidence_links} == {"compact:0", "compact:1"}
    assert "Complete source 0" in output.maintainer_summary
    assert "Complete source 1" in output.maintainer_summary


def test_same_run_conflict_continues_without_old_quotes_when_wire_request_changes():
    first = request(conflicts=True)
    changed_hit = first.evidence.hits[0].model_copy(update={"excerpt": "Only the current excerpt."})
    second = first.evidence.model_copy(update={"hits": (changed_hit,), "retrieval_round": 2})
    supplied = []

    class Planner:
        def plan(self, req, *, context):
            supplied.append(req)
            decision = "retrieve_more" if len(supplied) == 1 else "escalate"
            return expand_compact_plan(raw(req, decision), req).model_dump_json()

    def factory(case, message, evidence):
        return make_grounded_request(
            case,
            message,
            evidence,
            gaps=first.gaps,
            conflict_groups=first.conflict_groups if evidence.retrieval_round == 1 else (),
        )

    reasoner = GroundedReasoner(Planner(), request_factory=factory)
    assert (
        reasoner.analyze(
            first.case, first.user_message, first.evidence, context=context(first)
        ).decision
        == "retrieve_more"
    )
    output = reasoner.analyze(
        first.case,
        first.user_message,
        second,
        context=context(
            first,
            attempt_index=2,
            remaining_model_attempts=0,
            remaining_retrieval_rounds=0,
            can_refine=False,
        ),
    )
    assert UNRESOLVED_SOURCE_CONFLICT in supplied[1].gaps
    assert supplied[1].context_sha256 != supplied[0].context_sha256
    assert "Only the current excerpt" in output.maintainer_summary
    assert "Complete source" not in output.maintainer_summary
    assert "remains unresolved" in output.maintainer_summary


def test_projection_preserves_current_request_and_existing_policy_suffix_without_mutation():
    req = request()
    attribution = context(req)
    base = messages(req, attribution)
    original = add_source_selection_reminder(base, True)
    original = add_resource_guidance(original, req, enabled=True)
    before = deepcopy(original)
    projected = add_compact_plan_messages(original, req, attribution, enabled=True)
    payload = json.loads(projected[1]["content"])
    assert original == before
    assert payload["request"] == req.model_dump(mode="json")
    assert payload["capacity"] == json.loads(original[1]["content"])["capacity"]
    assert payload["render_resources"] == json.loads(original[1]["content"])["render_resources"]
    assert payload["source_references"] == [
        {"source_index": index, "chunk_id": hit.chunk_id}
        for index, hit in enumerate(req.evidence.hits)
    ]
    suffix = original[0]["content"][len(base[0]["content"]) :]
    assert projected[0]["content"].endswith(suffix)
    assert "Copy the complete chunk_id and content_sha256" not in projected[0]["content"]


def test_projected_schema_has_exact_decision_fields_and_current_index_choices():
    req = request()
    projected = add_compact_plan_messages(messages(req), req, context(req), enabled=True)
    payload = json.loads(projected[1]["content"])
    branches = payload["response_schema"]["oneOf"]
    expected_fields = {
        "answer": {"context_sha256", "decision", "sources"},
        "ask": {"context_sha256", "decision", "sources", "question_name"},
        "escalate": {"context_sha256", "decision", "sources"},
        "retrieve_more": {"context_sha256", "decision", "retrieval_queries"},
    }
    assert len(branches) == len(expected_fields)
    for branch in branches:
        properties = branch["properties"]
        decision = properties["decision"]["const"]
        assert set(properties) == set(branch["required"]) == expected_fields[decision]
        assert branch["additionalProperties"] is False
        if "sources" in properties:
            assert properties["sources"]["items"] == {"type": "integer", "enum": [0, 1, 2]}
            assert properties["sources"]["uniqueItems"] is True
        else:
            assert properties["retrieval_queries"]["maxItems"] == 2
        assert "sources" not in payload["decision_contracts"]["rules"]["retrieve_more"]


def test_capacity_composition_preserves_every_complete_source_and_renderer_authority():
    req = request(count=5, size=4500, gaps=())
    attribution = context(req)
    bound = source_capacity(req)
    assert bound is not None and 1 <= bound < 5
    limited = add_source_capacity(messages(req), req, enabled=True)
    projected = add_compact_plan_messages(limited, req, attribution, enabled=True)
    payload = json.loads(projected[1]["content"])
    assert payload["request"] == req.model_dump(mode="json")
    for branch in payload["response_schema"]["oneOf"]:
        sources = branch["properties"].get("sources")
        if sources is not None:
            assert sources["maxItems"] == bound
    # The wire hint may be ignored by a model; only the renderer grants feasibility.
    render_grounded_plan(req, expand_compact_plan(raw(req, selected=tuple(range(bound))), req))
    with pytest.raises(GroundingRejected, match="^grounded_render_too_large$"):
        render_grounded_plan(req, expand_compact_plan(raw(req, selected=tuple(range(5))), req))


def test_projection_rejects_stale_messages_and_mismatched_caller_context():
    req = request()
    changed = make_grounded_request(req.case, "A different current USER message", req.evidence)
    with pytest.raises(ValueError):
        add_compact_plan_messages(messages(req), changed, context(changed), enabled=True)
    wrong_context = context(req, case_revision=3)
    with pytest.raises(ValueError):
        add_compact_plan_messages(messages(req), req, wrong_context, enabled=True)


def test_default_and_false_preserve_complete_message_bytes_and_return_identity():
    req = request()
    original = messages(req)
    assert add_compact_plan_messages(original, req, context(req)) is original
    assert add_compact_plan_messages(original, req, context(req), enabled=False) is original
    config = MetisConfig(
        api_key=KEY, response_mode="grounded_plan", grounded_decision_contracts=True
    )
    assert not config.grounded_compact_plan
    assert configured_grounded_messages(config, req, context(req)) == original
    assert (
        configured_grounded_messages(
            config.model_copy(update={"grounded_compact_plan": False}), req, context(req)
        )
        == original
    )


def test_all_archived_current_and_repair_prompts_keep_the_existing_input_guard():
    root = Path(__file__).resolve().parents[1]
    checked = 0
    for folder in (
        "dev_rag_coverage_v1",
        "core_resource_guidance_v1",
        "core_repeat_repair_v1",
        "core_source_capacity_v1",
    ):
        receipt = json.loads(
            (root / "experiments" / folder / "model-live-receipt-v1.json").read_bytes()
        )
        for batch in receipt["batches"]:
            for attempt in batch["attempts"]:
                req = GroundedRequest.model_validate(attempt["request"])
                actual_context = ReasoningContext.model_validate(attempt["context"])
                repair_context = actual_context.model_copy(
                    update={
                        "attempt_index": 2,
                        "remaining_model_attempts": 0,
                        "can_refine": False,
                        "output_feedback": OutputFeedback(
                            issues=(OutputIssue(code="invalid_grounded_plan"),)
                        ),
                    }
                )
                for attribution in (actual_context, repair_context):
                    original = add_source_selection_reminder(messages(req, attribution), True)
                    assert (
                        add_compact_plan_messages(original, req, attribution, enabled=False)
                        is original
                    )
                    projected = add_compact_plan_messages(original, req, attribution, enabled=True)
                    assert len(json.dumps(projected, ensure_ascii=False).encode()) + 1024 <= 32768
                    payload = json.loads(projected[1]["content"])
                    assert payload["request"] == req.model_dump(mode="json")
                    assert payload["capacity"] == json.loads(original[1]["content"])["capacity"]
                    checked += 1
    assert checked == 214


@pytest.mark.parametrize("value", [None, 0, 1, "true", [], {}])
def test_compact_opt_in_is_strict_boolean(value):
    req = request()
    with pytest.raises(ValueError):
        add_compact_plan_messages(messages(req), req, context(req), enabled=value)
    with pytest.raises(ValueError):
        MetisConfig(api_key=KEY, grounded_compact_plan=value)


def test_compact_config_requires_decision_contracts_and_never_enables_live_calls():
    with pytest.raises(ValueError):
        MetisConfig(api_key=KEY, response_mode="grounded_plan", grounded_compact_plan=True)
    with pytest.raises(ValueError):
        MetisConfig(api_key=KEY, grounded_compact_plan=True)
    configured = MetisConfig(
        api_key=KEY,
        response_mode="grounded_plan",
        grounded_decision_contracts=True,
        grounded_compact_plan=True,
    )
    assert configured.grounded_compact_plan and not configured.live_enabled


@pytest.mark.parametrize("bad", ["TRUE", "1", "true ", ""])
def test_compact_env_does_not_silently_coerce_an_invalid_flag(monkeypatch, bad):
    monkeypatch.setenv("METIS_API_KEY", KEY)
    monkeypatch.setenv("METIS_RESPONSE_MODE", "grounded_plan")
    monkeypatch.setenv("METIS_GROUNDED_DECISION_CONTRACTS", "true")
    monkeypatch.setenv("METIS_GROUNDED_COMPACT_PLAN", bad)
    with pytest.raises(ValueError):
        MetisConfig.from_env()


@pytest.mark.parametrize("enabled", ["true", "false"])
def test_compact_env_flag_is_explicit_and_mode_bound(monkeypatch, enabled):
    monkeypatch.setenv("METIS_API_KEY", KEY)
    monkeypatch.setenv("METIS_RESPONSE_MODE", "grounded_plan")
    monkeypatch.setenv("METIS_GROUNDED_DECISION_CONTRACTS", "true")
    monkeypatch.setenv("METIS_GROUNDED_COMPACT_PLAN", enabled)
    assert MetisConfig.from_env().grounded_compact_plan is (enabled == "true")


@pytest.mark.parametrize("kind", ["valid", "shape", "context", "source", "duplicate_keys"])
def test_observation_keeps_raw_hash_and_safe_diagnostics_even_when_expansion_fails(kind):
    req = request()
    payload = wire(req)
    expected = None
    if kind == "shape":
        payload["PRIVATE_UNKNOWN_FIELD"] = "PRIVATE_PROVIDER_TEXT"
        expected = "invalid_grounded_plan"
    elif kind == "context":
        payload["context_sha256"] = "0" * 64
        expected = "grounded_context_mismatch"
    elif kind == "source":
        payload["sources"] = [-1]
        expected = "grounded_source_mismatch"
    value = json.dumps(payload)
    if kind == "duplicate_keys":
        value = value[:-1] + ',"sources":[1]}'
        expected = "invalid_grounded_plan"
    observed = observe_compact_plan(value, req)
    assert observed["raw_output_sha256"] == hashlib.sha256(value.encode()).hexdigest()
    assert observed["raw_utf8_bytes"] == len(value.encode())
    assert observed["rejection_code"] == expected
    assert observed["wire_schema_valid"] is (kind in {"valid", "context", "source"})
    assert observed["canonical_binding_valid"] is (kind == "valid")
    exported = json.dumps(observed)
    assert "PRIVATE_UNKNOWN_FIELD" not in exported
    assert "PRIVATE_PROVIDER_TEXT" not in exported
    assert req.user_message not in exported
    assert req.evidence.hits[0].excerpt not in exported


def test_observer_does_not_export_queries_or_unbounded_index_values():
    req = request()
    value = raw(req, "retrieve_more", retrieval_queries=["PRIVATE_QUERY_MARKER"])
    observed = observe_compact_plan(value, req)
    assert observed["wire_schema_valid"] and observed["canonical_binding_valid"]
    assert "PRIVATE_QUERY_MARKER" not in json.dumps(observed)
    for selection in (-1, 100, 10**100):
        observed = observe_compact_plan(raw(req, selected=(selection,)), req)
        assert observed["rejection_code"] == "grounded_source_mismatch"
        assert observed["selected_indexes"] in (None, [])
