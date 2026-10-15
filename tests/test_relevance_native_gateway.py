"""Native retrieval through compact mocked provider HTTP; synthetic ledger only."""

import hashlib
import json

import httpx
import pytest
from test_budget_quarantine_scope import multiple_holds as multiple_holds
from test_real_index_probe import ARMS as INDEX_ARMS
from test_real_index_probe import ROOT, prepare
from test_real_index_probe import native_indexes as native_indexes

from agent_app.contracts import GroundedRequest, ReasoningContext
from agent_app.llm.metis import request_id_for
from agent_app.reasoning.catalog import load_user_gap_vocabulary
from agent_app.reasoning.compact_plan import expand_compact_plan
from agent_app.reasoning.grounding import source_content_sha256
from agent_app.testing.dev_three_model_probe import DevProbeRejected, ledger_observation
from agent_app.testing.http_pilot_runtime import offline_network
from agent_app.testing.quality_probe import quality_slots
from agent_app.testing.real_index_probe import RealIndexProbeRejected, run_real_index_batch
from agent_app.testing.stability_probe import VOCABULARY

ARMS = ("native_top5", "candidate_relevance")
BUTTON = "docstring:1.39.0:streamlit.button"


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def prepared_arms(multiple_holds):
    prepared = prepare(multiple_holds, "dev-case-b", arms=ARMS)
    _, protocol, batch, fixtures, _ = prepared
    registered = quality_slots(protocol, batch, fixtures)
    for job in batch["jobs"]:
        treatment = job["arm"] == ARMS[1]
        job.update(
            compact_plan=True,
            repair_repeated_queries=True,
            record_native_candidates=True,
            retrieval_candidate_multiplier=5 if treatment else 1,
            retrieval_selection_policy="query_relevance_v1" if treatment else "native",
            evidence_utf8_budget_bytes=12000 if treatment else None,
        )
    assert quality_slots(protocol, batch, fixtures) == registered
    return prepared


def payload_keys(value):
    if isinstance(value, dict):
        return set(value).union(*(payload_keys(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(payload_keys(item) for item in value))
    return set()


def test_real_index_relevance_reaches_compact_gateway_and_http_without_fixture_answers(
    multiple_holds, native_indexes, monkeypatch
):
    from chromadb.api.models.Collection import Collection

    native_calls = []
    original = Collection.query

    def observed(collection, *args, **kwargs):
        result = original(collection, *args, **kwargs)
        native_calls.append((collection.name, kwargs, result))
        return result

    monkeypatch.setattr(Collection, "query", observed)
    prepared = prepared_arms(multiple_holds)
    ledger, protocol, batch, fixtures, config = prepared
    indexes = {arm: native_indexes[INDEX_ARMS[1]] for arm in ARMS}
    before = ledger_observation(ledger._path)
    wires, raw_outputs = [], []

    def respond(request):
        wire = json.loads(request.content)
        payload = json.loads(wire["messages"][1]["content"])
        supplied = payload["request"]
        wires.append(wire)
        assert payload["wire_format"] == "grounded-indexed-plan-v1"
        active = [
            fact["value"]
            for fact in supplied["case"]["facts"]
            if fact["name"] == "streamlit_version" and fact["status"] == "active"
        ]
        output = {"context_sha256": supplied["context_sha256"], "sources": []}
        if not active:
            assert any(
                gap["kind"] == "user" and gap["name"] == "streamlit_version"
                for gap in supplied["gaps"]
            )
            output.update(decision="ask", question_name="streamlit_version")
        else:
            assert active == ["1.39.0"]
            # Select only a record actually present in this current model request.
            selected = next(
                (
                    index
                    for index, hit in enumerate(supplied["evidence"]["hits"])
                    if hit["source_id"] == BUTTON
                ),
                None,
            )
            output.update(
                decision="answer" if selected is not None else "escalate",
                sources=[selected] if selected is not None else [],
            )
        raw_outputs.append(json.dumps(output, ensure_ascii=False, indent=2))
        return httpx.Response(
            200,
            json={
                "model": "gpt-4o-mini-2024-07-18",
                "usage": {"prompt_tokens": 100, "completion_tokens": 80, "total_tokens": 180},
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": raw_outputs[-1]},
                    }
                ],
            },
        )

    with offline_network():
        receipt = run_real_index_batch(
            protocol,
            batch,
            fixtures,
            load_user_gap_vocabulary(str(ROOT / VOCABULARY)),
            ledger,
            config,
            before,
            indexes,
            underlying=httpx.MockTransport(respond),
        )
    assert receipt["visited_jobs"] == receipt["completed_routes"] == 2
    assert receipt["actual_sends"] == len(wires) == len(raw_outputs) == 4
    assert not receipt["stopped_early"] and receipt["original_accounting_preserved"]
    assert receipt["fixed_fixture_evidence_used"] is False
    assert not receipt["human_reviewed"] and not receipt["held_out_test"]
    assert receipt["index_bindings"][ARMS[1]]["source_count"] == 18
    assert receipt["index_bindings"][ARMS[1]]["chunk_count"] == 36

    records = receipt["actual_retrievals"]
    assert len(records) == 4
    actual_call = iter(native_calls)
    for record in records:
        window = 25 if record["arm"] == ARMS[1] else 5
        assert record["error_code"] is None
        assert record["logical_retrieval_round"] == 1
        assert record["requested"] == record["executed"]
        assert record["requested"]["top_k"] == window
        assert record["requested"]["filters"] == {}
        assert len(record["evidence"]["hits"]) <= window
        assert len(record["native_calls"]) == len(record["requested"]["queries"])
        for call, query in zip(record["native_calls"], record["requested"]["queries"], strict=True):
            assert call["query"] == query and call["n_results"] == window
            assert call["filters"] == {}
            for name, collection_name in (
                ("docs", "streamlit_docs"),
                ("issues", "streamlit_issues"),
            ):
                actual_name, arguments, result = next(actual_call)
                assert actual_name == collection_name
                assert arguments["n_results"] == window and "where" not in arguments
                rows = call["collections"][name]
                assert len(rows) <= window
                for rank, (row, text, metadata) in enumerate(
                    zip(rows, result["documents"][0], result["metadatas"][0], strict=True), 1
                ):
                    assert row == {
                        "rank": rank,
                        "chunk_id": metadata["chunk_id"],
                        "source_id": metadata["source_id"],
                        "text_sha256": sha(text),
                        "metadata_sha256": sha(json.dumps(metadata, sort_keys=True)),
                    }
    assert next(actual_call, None) is None

    forbidden = {
        "gold",
        "agent_script",
        "expect",
        "maintainer",
        "turns",
        "evaluation",
        "evidence_bundle",
        "acceptable_decisions",
        "unacceptable_claims",
        "reply_to_approved_question",
    }
    native_text = {
        metadata["chunk_id"]: text
        for _, _, result in native_calls
        for text, metadata in zip(result["documents"][0], result["metadatas"][0], strict=True)
    }
    final_requests = {}
    for attempt, wire, raw, transport in zip(
        receipt["attempts"], wires, raw_outputs, receipt["provider_sends"], strict=True
    ):
        request = GroundedRequest.model_validate(attempt["request"])
        context = ReasoningContext.model_validate(attempt["context"])
        payload = json.loads(wire["messages"][1]["content"])
        assert payload["request"] == request.model_dump(mode="json")
        assert not (forbidden & payload_keys(payload))
        assert wire["max_tokens"] == 1024
        assert transport["wire_messages_sha256"] == sha(
            json.dumps(wire["messages"], ensure_ascii=False, sort_keys=True)
        )
        assert len(request.evidence.hits) <= 5
        assert request.evidence.snapshot_id == native_indexes[INDEX_ARMS[1]]["snapshot_id"]
        active = [
            fact
            for fact in request.case.facts
            if fact.name == "streamlit_version" and fact.status == "active"
        ]
        if context.case_revision == 1:
            assert not active
            assert (
                request.user_message
                == fixtures["dev-case-b"].data["turns"][0]["visible"]["message"]
            )
            assert json.loads(raw)["decision"] == "ask"
        else:
            assert context.case_revision == 2 and request.user_message.splitlines()[-1] == "1.39.0"
            assert [(fact.value, fact.provenance_kind) for fact in active] == [("1.39.0", "user")]
            assert all(
                not hit.applicable_versions or "1.39.0" in hit.applicable_versions
                for hit in request.evidence.hits
            )
            arm = next(job["arm"] for job in receipt["jobs"] if context.run_id in job["run_ids"])
            final_requests[arm] = request
        record = next(
            record
            for record in records
            if record["job_id"]
            == next(job["job_id"] for job in receipt["jobs"] if context.run_id in job["run_ids"])
            and record["turn_id"] == ("initial" if context.case_revision == 1 else "version")
        )
        candidates = {
            row["chunk_id"]: row
            for call in record["native_calls"]
            for rows in call["collections"].values()
            for row in rows
        }
        for hit in request.evidence.hits:
            assert hit.chunk_id in candidates
            # EvidenceHit's existing Text contract strips only outer whitespace.
            assert hit.excerpt == native_text[hit.chunk_id].strip()
        if record["arm"] == ARMS[1]:
            assert len(request.evidence.model_dump_json().encode()) <= 12000
        expanded = expand_compact_plan(raw, request)
        assert attempt["plan"] == expanded.model_dump(mode="json")
        assert attempt["output_sha256"] == sha(expanded.model_dump_json()) != sha(raw)
        observation = attempt["wire_output"]
        assert observation["request_id"] == transport["request_id"] == request_id_for(context)
        assert observation["raw_output_sha256"] == sha(raw)
        assert observation["raw_utf8_bytes"] == len(raw.encode())
        assert observation["selected_indexes"] == json.loads(raw)["sources"]
        assert observation["wire_schema_valid"] and observation["canonical_binding_valid"]
        assert observation["rejection_code"] is None
        for reference, index in zip(expanded.sources, json.loads(raw)["sources"], strict=True):
            hit = request.evidence.hits[index]
            assert reference.chunk_id == hit.chunk_id
            assert reference.content_sha256 == source_content_sha256(hit)

    assert not any(hit.source_id == BUTTON for hit in final_requests[ARMS[0]].evidence.hits)
    assert any(hit.source_id == BUTTON for hit in final_requests[ARMS[1]].evidence.hits)
    assert [job["steps"][-1]["proposal"]["decision"] for job in receipt["jobs"]] == [
        "escalate",
        "answer",
    ]
    assert ledger.snapshot().halted and ledger.snapshot().reserved_usd == 0
    assert len(ledger.quarantine_observation().unknown_ids) == 2
    assert receipt["ledger_after"]["counts"].get("settled") == 4
    assert "synthetic-index-probe-key" not in json.dumps(receipt)


@pytest.mark.parametrize(
    "field,bad",
    [
        ("retrieval_candidate_multiplier", True),
        ("retrieval_candidate_multiplier", 2),
        ("retrieval_selection_policy", "gold_lookup"),
        ("evidence_utf8_budget_bytes", True),
        ("evidence_utf8_budget_bytes", 2047),
        ("evidence_utf8_budget_bytes", 32769),
        ("record_native_candidates", "true"),
    ],
)
def test_invalid_relevance_job_stops_before_provider_allocation_or_new_ledger_rows(
    multiple_holds, native_indexes, monkeypatch, field, bad
):
    ledger, protocol, batch, fixtures, config = prepared_arms(multiple_holds)
    batch["jobs"][1][field] = bad
    before = ledger_observation(ledger._path)
    allocated = []

    def forbidden(*_args, **_kwargs):
        allocated.append(True)
        raise AssertionError("Provider allocation forbidden")

    monkeypatch.setattr(httpx, "HTTPTransport", forbidden)
    with offline_network(), pytest.raises((RealIndexProbeRejected, DevProbeRejected)):
        run_real_index_batch(
            protocol,
            batch,
            fixtures,
            (),
            ledger,
            config,
            before,
            {arm: native_indexes[INDEX_ARMS[1]] for arm in ARMS},
        )
    assert not allocated and ledger_observation(ledger._path) == before
