"""Actual named profile/renderer path with native index and intercepted provider."""

import json
from copy import deepcopy

import httpx
import pytest
from test_budget_quarantine_scope import multiple_holds as multiple_holds
from test_real_index_probe import ARMS, ROOT, prepare
from test_real_index_probe import native_indexes as native_indexes

from agent_app.contracts import ProposalHandoff
from agent_app.evaluation.routes import ConditionalRoutesRejected, RouteGraph
from agent_app.orchestration.handoff import edit_handoff
from agent_app.reasoning.catalog import load_user_gap_vocabulary
from agent_app.testing.dev_three_model_probe import DevProbeRejected, ledger_observation
from agent_app.testing.http_pilot_runtime import offline_network
from agent_app.testing.real_index_probe import run_real_index_batch
from agent_app.testing.stability_probe import VOCABULARY


def prepared(multiple_holds):
    values = prepare(multiple_holds, "dev-case-a", arms=("candidate_profile",))
    job = values[2]["jobs"][0]
    job.update(
        compact_plan=True,
        repair_repeated_queries=True,
        record_native_candidates=True,
        retrieval_candidate_multiplier=5,
        retrieval_selection_policy="query_relevance_v1",
        evidence_utf8_budget_bytes=12000,
        retrieval_profile="candidate_relevance_v1",
        ask_source_background=True,
    )
    return values


def test_named_profile_survives_actual_quality_runner_and_canonical_followup(
    multiple_holds, native_indexes
):
    ledger, protocol, batch, fixtures, config = prepared(multiple_holds)
    before = ledger_observation(ledger._path)
    payloads = []

    def respond(request):
        payload = json.loads(json.loads(request.content)["messages"][1]["content"])
        payloads.append(payload)
        assert payload["wire_format"] == "grounded-indexed-plan-v1"
        current = payload["request"]
        assert "ask_source_background" not in payload and "retrieval_profile" not in current
        known = any(
            fact["name"] == "streamlit_version"
            and fact["status"] == "active"
            and fact["provenance_kind"] == "user"
            for fact in current["case"]["facts"]
        )
        selected = (
            [
                index
                for index, hit in enumerate(current["evidence"]["hits"])
                if "streamlit.fragment" in hit["source_id"]
                and "1.50.0" in hit["applicable_versions"]
            ][:1]
            if known
            else []
        )
        if known:
            assert selected
        plan = {
            "context_sha256": current["context_sha256"],
            "decision": "ask",
            "question_name": "parent_callback_code" if known else "streamlit_version",
            "sources": selected,
        }
        return httpx.Response(
            200,
            json={
                "model": "gpt-4o-mini-2024-07-18",
                "usage": {"prompt_tokens": 100, "completion_tokens": 70, "total_tokens": 170},
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": json.dumps(plan)},
                    }
                ],
            },
        )

    with offline_network():
        result = run_real_index_batch(
            protocol,
            batch,
            fixtures,
            load_user_gap_vocabulary(str(ROOT / VOCABULARY)),
            ledger,
            config,
            before,
            {"candidate_profile": native_indexes[ARMS[1]]},
            underlying=httpx.MockTransport(respond),
        )
    assert result["actual_sends"] == len(payloads) == 2
    assert result["completed_routes"] == 1 and not result["stopped_early"]
    assert all(
        native["n_results"] == 25
        for retrieval in result["actual_retrievals"]
        for native in retrieval["native_calls"]
    )
    steps = result["jobs"][0]["steps"]
    initial, followup = [step["proposal"]["review_handoff"]["analysis"] for step in steps]
    assert initial["user_draft"] == initial["next_question"]
    assert followup["user_draft"].startswith(followup["next_question"] + "\n\n")
    assert "Selected source background" in followup["user_draft"]
    assert "fragment" in followup["user_draft"]
    assert followup["missing_info"] == ["parent_callback_code"]
    step = steps[-1]
    proposal = step["proposal"]
    view = {
        "case_id": proposal["case_id"],
        "case_revision": proposal["case_revision"],
        "pending": proposal,
    }
    graph = RouteGraph.from_fixture(fixtures["dev-case-a"].data, allow_source_background=True)
    assert graph.select("version", step, view) is not None
    assert (
        RouteGraph.from_fixture(fixtures["dev-case-a"].data).select("version", step, view) is None
    )
    # Even a valid, freshly rebound human edit with the canonical question as
    # prefix must not unlock an authored branch through arbitrary extra prose.
    original = ProposalHandoff.model_validate(proposal["review_handoff"])
    edited = edit_handoff(
        original,
        "synthetic-human-edit",
        original.analysis.model_copy(
            update={"user_draft": original.analysis.user_draft + "\nUnregistered extra claim."}
        ),
    )
    altered = deepcopy(step)
    edited_proposal = deepcopy(proposal)
    edited_proposal.update(
        proposal_id=edited.proposal_id,
        analysis=edited.analysis.model_dump(mode="json"),
        review_handoff=edited.model_dump(mode="json"),
    )
    altered["edited_proposal"] = edited_proposal
    assert graph.select("version", altered, {**view, "pending": edited_proposal}) is None
    corrupt = deepcopy(step)
    corrupt["proposal"]["review_handoff"]["handoff_sha256"] = "0" * 64
    assert graph.select("version", corrupt, {**view, "pending": corrupt["proposal"]}) is None


@pytest.mark.parametrize(
    "change",
    [
        {"ask_source_background": 1},
        {"retrieval_profile": "arbitrary"},
        {"retrieval_candidate_multiplier": 1},
        {"evidence_utf8_budget_bytes": 10000},
        {"retrieval_selection_policy": "native"},
        {"repair_repeated_queries": False},
    ],
)
def test_mislabelled_job_rejects_before_provider(multiple_holds, native_indexes, change):
    ledger, protocol, batch, fixtures, config = prepared(multiple_holds)
    before = ledger_observation(ledger._path)
    batch["jobs"][0].update(change)
    sent = []
    with offline_network(), pytest.raises(DevProbeRejected):
        run_real_index_batch(
            protocol,
            batch,
            fixtures,
            load_user_gap_vocabulary(str(ROOT / VOCABULARY)),
            ledger,
            config,
            before,
            {"candidate_profile": native_indexes[ARMS[1]]},
            underlying=httpx.MockTransport(lambda request: sent.append(request)),
        )
    assert not sent and ledger_observation(ledger._path) == before


@pytest.mark.parametrize("bad", [None, "true", 1, [], {}])
def test_route_background_option_is_strict_caller_configuration(bad):
    data = json.loads(
        (ROOT / "data/evaluation/dev-three-v1/cases/pilot-12782-v1.json").read_bytes()
    )
    with pytest.raises(ConditionalRoutesRejected):
        RouteGraph.from_fixture(data, allow_source_background=bad)
