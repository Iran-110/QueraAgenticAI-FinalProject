"""Real local Chroma/persistent HTTP; every provider wire is mocked."""

import importlib.util
import json
import sys
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from agent_app.contracts import CaseState, EvidenceBundle, Fact
from agent_app.llm.budget import BudgetLedger
from agent_app.llm.config import MetisConfig
from agent_app.retrieval.offline_index import build_index
from agent_app.retrieval.pilot_corpus import MANIFEST_NAME, build_pilot_corpus
from agent_app.testing.http_pilot_runtime import offline_network

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "connected_live_dev_probe", ROOT / "scripts/connected_live_dev_probe.py"
)
PROBE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROBE)


@pytest.fixture(scope="module")
def index(tmp_path_factory):
    directory = tmp_path_factory.mktemp("connected-live-index") / "index"
    with offline_network():
        corpus = build_pilot_corpus(
            ROOT / "streamlit-data-for-dev-test",
            ROOT / "data/evaluation/split-manifest.json",
            ROOT / "experiments/corpus/pilot-allowlist.json",
        )
        snapshot = build_index(corpus, directory)
    return directory, snapshot


@pytest.fixture
def ledger(tmp_path):
    directory = tmp_path / "root/runtime"
    directory.mkdir(parents=True)
    path = directory / "budget.sqlite3"
    ledger = BudgetLedger.create(path, limit_usd=Decimal("4.5"), opening_spend_usd=Decimal("0"))
    ledger.reserve(
        request_id="call:old-mismatch",
        run_id="run:old",
        case_id="case:old",
        case_revision=1,
        attempt=1,
        model="gpt-4.1-mini",
        phase="development",
        amount_usd=Decimal("0.008"),
    )
    ledger.mark_uncertain("call:old-mismatch", error_code="ProviderModelMismatch")
    ledger.halt()
    ledger.authorize_continuation(
        authorization_id=PROBE.SHARED.GRANT,
        authorization_ref="test:explicit-authorized-development",
        expected_request_id="call:old-mismatch",
        held_usd=Decimal("0.02"),
        additional_cap_usd=Decimal("0.1"),
    )
    return path, ledger


def protocol(index, ledger):
    directory, snapshot = index
    before = PROBE.SHARED.ledger_observation(ledger[0])
    return {
        "protocol_id": "connected-live-dev-pilot-v1",
        "experiment_id": "test-connected-index-two-turns",
        "continuation_id": PROBE.SHARED.GRANT,
        "ledger": {
            "path": "runtime/budget.sqlite3",
            "sha256_before": before["fingerprints"]["db"],
            "unknown_records_sha256": before["unknown_records_sha256"],
        },
        "index": {
            "path": str(directory),
            "snapshot_id": snapshot,
            "manifest_sha256": PROBE._sha((directory / MANIFEST_NAME).read_bytes()),
            "top_k": 1,
        },
        "gateway": {
            "model": PROBE.SHARED.MODEL,
            "phase": "development",
            "input_token_reserve": PROBE.SHARED.INPUT_RESERVE,
            "max_output_tokens": PROBE.SHARED.OUTPUT_LIMIT,
            "max_request_usd": str(PROBE.SHARED.REQUEST_BOUND),
            "batch_max_reserved_usd": str(PROBE.SHARED.BATCH_BOUND),
            "max_actual_sends_including_repair": 2,
        },
        "turns": [
            {
                "visible": {
                    "message": "My multiselect in a fragment loses its default after the parent selector resets session state. My reduced example works and the parent callback is not provided. Streamlit 1.50.0, Python 3.12.9.",
                    "reported_facts": [
                        {"name": "streamlit_version", "value": "1.50.0"},
                        {"name": "python_version", "value": "3.12.9"},
                    ],
                    "unknowns": ["parent_callback_code", "minimal_failing_reproduction"],
                    "scenario": "answer",
                    "context_changed": False,
                }
            },
            {
                "visible": {
                    "message": "Correction: Streamlit is 1.49.0. The reduced example still works; I have not provided the parent callback.",
                    "reported_facts": [{"name": "streamlit_version", "value": "1.49.0"}],
                    "context_changed": True,
                    "scenario": "answer",
                }
            },
        ],
    }


def config():
    return MetisConfig(
        api_key="public-synthetic-connected-dev-key",
        live_enabled=True,
        model=PROBE.SHARED.MODEL,
        phase="development",
        response_mode="grounded_plan",
        continuation_id=PROBE.SHARED.GRANT,
        input_token_reserve=PROBE.SHARED.INPUT_RESERVE,
        max_output_tokens=PROBE.SHARED.OUTPUT_LIMIT,
        max_request_usd=PROBE.SHARED.REQUEST_BOUND,
    )


def response(
    request,
    *,
    malformed=False,
    model="gpt-4o-mini-2024-07-18",
    decision="escalate",
    question_name=None,
):
    payload = json.loads(request.content)
    data = json.loads(payload["messages"][1]["content"])
    plan = {"context_sha256": data["request"]["context_sha256"], "decision": decision}
    if decision == "ask":
        plan["question_name"] = question_name
    elif decision == "retrieve_more":
        plan["retrieval_queries"] = ["fragment session state reset widget identity"]
    else:
        plan["sources"] = data["source_references"][:1]
    return httpx.Response(
        200,
        json={
            "model": model,
            "usage": {"prompt_tokens": 125, "completion_tokens": 75, "total_tokens": 200},
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": "{broken" if malformed else json.dumps(plan),
                    },
                }
            ],
        },
    )


def execute(tmp_path, index, ledger, respond):
    state = tmp_path / "private-state"
    state.mkdir()
    with offline_network():
        return PROBE.run_probe(
            protocol(index, ledger),
            ledger_path=ledger[0],
            index_path=index[0],
            state_dir=state,
            config=config(),
            before=PROBE.SHARED.ledger_observation(ledger[0]),
            underlying=httpx.MockTransport(respond),
        )


def test_actual_index_two_turns_current_correction_and_retries_without_reexecution(
    tmp_path, index, ledger
):
    seen = []

    def respond(request):
        data = json.loads(json.loads(request.content)["messages"][1]["content"])["request"]
        seen.append(data)
        assert all("expected" not in gap and "gold" not in gap for gap in data["gaps"])
        return response(request)

    receipt = execute(tmp_path, index, ledger, respond)
    assert receipt["accepted_complete_pilot"] is True, receipt
    assert receipt["actual_sends"] == 2 and receipt["coverage_complete"] is True
    assert all(receipt["checks"].values())
    assert [step["case_revision"] for step in receipt["steps"]] == [1, 2]
    assert len(seen) == 2
    assert all(run["closed"] and run["retrieval"] for run in receipt["runs"])
    assert all(
        read["executed"]["top_k"] == 1 for run in receipt["runs"] for read in run["retrieval"]
    )
    assert all(
        len(run["last_grounded_request"]["evidence"]["hits"]) <= 1 for run in receipt["runs"]
    )
    assert all(
        record["verified_returned_model"] == "gpt-4o-mini-2024-07-18"
        for record in receipt["provider_observations"]
    )
    assert Decimal(receipt["new_cost_estimated_usd"]) == Decimal("0.000140250")
    assert (
        receipt["ledger_after"]["halted"] is True
        and receipt["ledger_after"]["uncertain_usd"] == "0.02"
    )
    assert receipt["actual_account_charge_usd"] is None
    exported = json.dumps(receipt)
    assert "public-synthetic-connected-dev-key" not in exported and "Authorization" not in exported
    assert receipt["quality_claim"] is False and receipt["heldout_claim"] is False


@pytest.mark.parametrize("definition", PROBE.DEVELOPMENT_USER_GAPS)
def test_model_can_ask_current_missing_callback_or_failing_parent_example(
    tmp_path, index, ledger, definition
):
    inputs = []

    def respond(request):
        data = json.loads(json.loads(request.content)["messages"][1]["content"])["request"]
        inputs.append(data)
        gaps = {gap["name"]: gap for gap in data["gaps"]}
        assert definition["name"] in gaps
        assert "streamlit_version" not in gaps and "python_version" not in gaps
        return response(request, decision="ask", question_name=definition["name"])

    receipt = execute(tmp_path, index, ledger, respond)
    assert receipt["accepted_complete_pilot"] is True
    assert receipt["actual_sends"] == 2 and len(inputs) == 2
    for step in receipt["steps"]:
        analysis = step["canonical_pending_handoff"]["analysis"]
        assert analysis["next_question"] == definition["question"]
        assert analysis["missing_info"] == [definition["name"]]
        assert analysis["evidence_links"] == []
    assert receipt["checks"]["correction_supersedes_old_user_version"] is True
    assert receipt["checks"]["fresh_proposal_for_corrected_revision"] is True
    failing_question = PROBE.DEVELOPMENT_USER_GAPS[1]["question"]
    assert "failing example" in failing_question
    assert "parent selector/callback interaction" in failing_question
    assert "The supplied reduced example works." in failing_question


def test_development_catalog_requires_explicit_current_unknown_and_never_reasks_supplied_fact():
    version = Fact(
        name="streamlit_version", value="1.50.0", source_ref="user:known", turn_id="turn:known"
    )
    known_callback = Fact(
        name="parent_callback_code",
        value="The callback was supplied by the user.",
        source_ref="user:callback",
        turn_id="turn:callback",
    )
    evidence = EvidenceBundle(snapshot_id="catalog-only")
    case = CaseState(
        case_id="catalog-current-case",
        facts=(version, known_callback),
        unknowns=("parent_callback_code",),
    )
    registered = PROBE._development_catalog(
        case,
        "The callback is missing in this prose, but authoritative facts supplied it.",
        evidence,
    )
    assert not any(gap.kind == "user" for gap in registered.gaps)
    unknown = CaseState(case_id="catalog-no-explicit-unknown", facts=(version,))
    prose_only = PROBE._development_catalog(unknown, "My parent callback is missing.", evidence)
    assert not any(gap.kind == "user" for gap in prose_only.gaps)


def test_first_turn_repair_uses_whole_send_allowance_correction_is_prepared_without_paid_retry(
    tmp_path, index, ledger
):
    seen = []

    def respond(request):
        seen.append(1)
        return response(request, malformed=len(seen) == 1)

    receipt = execute(tmp_path, index, ledger, respond)
    assert receipt["actual_sends"] == len(seen) == 2
    assert receipt["accepted_complete_pilot"] is False and receipt["coverage_complete"] is False
    assert receipt["steps"][0]["canonical_pending_handoff"] is not None
    assert receipt["steps"][1]["case_revision"] == 2
    assert receipt["steps"][1]["new_sends"] == 0
    assert receipt["steps"][1]["canonical_pending_handoff"] is None
    assert receipt["steps"][1]["run_outcome"] is not None
    assert [attempt["attempt_index"] for attempt in receipt["runs"][0]["reasoning_attempts"]] == [
        1,
        2,
    ]
    assert receipt["ledger_after"]["counts"]["settled"] == 2


def test_refinement_consumes_global_allowance_without_fabricating_correction_coverage(
    tmp_path, index, ledger
):
    seen = []

    def respond(request):
        seen.append(1)
        return response(request, decision="retrieve_more" if len(seen) == 1 else "escalate")

    receipt = execute(tmp_path, index, ledger, respond)
    assert receipt["actual_sends"] == len(seen) == 2
    assert receipt["coverage_complete"] is False
    assert len(receipt["runs"][0]["retrieval"]) == 2
    assert receipt["steps"][1]["new_sends"] == 0


def test_terminal_model_mismatch_stops_before_correction_and_preserves_old_uncertainty(
    tmp_path, index, ledger
):
    original = ledger[1].get("call:old-mismatch")
    seen = []

    def respond(request):
        seen.append(1)
        return response(request, model="unverified-model")

    receipt = execute(tmp_path, index, ledger, respond)
    assert receipt["actual_sends"] == len(seen) == 1
    assert receipt["steps"][-1]["runner_stop"] == "PreviousTurnStopped"
    assert receipt["coverage_complete"] is False
    assert ledger[1].get("call:old-mismatch") == original
    assert receipt["ledger_after"]["counts"]["uncertain"] == 2
    assert receipt["ledger_after"]["continuation"]["active"] is False
    assert "unverified-model" not in json.dumps(receipt)


def test_timeout_keeps_reservation_and_never_retries_or_advances_case(tmp_path, index, ledger):
    seen = []

    def respond(request):
        seen.append(1)
        raise httpx.ReadTimeout("private-failure-detail", request=request)

    receipt = execute(tmp_path, index, ledger, respond)
    assert receipt["actual_sends"] == len(seen) == 1
    assert receipt["coverage_complete"] is False
    assert receipt["ledger_after"]["counts"]["uncertain"] == 2
    assert "private-failure-detail" not in json.dumps(receipt)


def test_default_cli_never_opens_chroma_reads_env_or_creates_provider(monkeypatch, capsys):
    monkeypatch.setattr(
        PROBE, "load_registration", lambda *_args: ({}, {"index_storage_verification": "deferred"})
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["connected_live_dev_probe.py", "--index", "existing-index", "--env-file", "private.env"],
    )

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Default preflight is read only")

    monkeypatch.setattr(PROBE.SHARED, "_credential", forbidden)
    monkeypatch.setattr(PROBE, "open_verified_index", forbidden)
    monkeypatch.setattr(httpx.HTTPTransport, "__init__", forbidden)
    PROBE.main()
    assert json.loads(capsys.readouterr().out)["paid_requests"] == 0


def test_live_missing_required_paths_refuses_before_key_and_provider(monkeypatch, capsys):
    monkeypatch.setattr(PROBE, "load_registration", lambda *_args: ({}, {}))
    monkeypatch.setattr(
        sys, "argv", ["connected_live_dev_probe.py", "--index", "existing-index", "--live"]
    )

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Invalid live arguments must not read a key or open provider")

    monkeypatch.setattr(PROBE.SHARED, "_credential", forbidden)
    monkeypatch.setattr(PROBE, "open_verified_index", forbidden)
    with pytest.raises(SystemExit) as error:
        PROBE.main()
    assert error.value.code == 1
    assert json.loads(capsys.readouterr().out) == {
        "code": "ConnectedLiveDevProbeRejected",
        "automatic_retry": False,
    }


def test_registration_rejects_changed_ledger_before_key_and_never_touches_index(
    tmp_path, index, ledger, monkeypatch
):
    root = ledger[0].parents[1]
    target = root / PROBE.PROTOCOL
    target.parent.mkdir(parents=True)
    registered = protocol(index, ledger)
    target.write_text(json.dumps(registered), encoding="utf-8")
    monkeypatch.setattr(
        PROBE,
        "source_observation",
        lambda _root: {"source_commit": "committed", "source_hashes": {}, "source_clean": True},
    )
    before = ledger[0].read_bytes()
    _protocol, result = PROBE.load_registration(root, ledger[0], index[0])
    assert ledger[0].read_bytes() == before
    assert result["index_storage_verification"].startswith("deferred")
    changed = deepcopy(registered)
    changed["ledger"]["sha256_before"] = "0" * 64
    target.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(PROBE.ProbeRejected):
        PROBE.load_registration(root, ledger[0], index[0])
    assert ledger[0].read_bytes() == before


@pytest.mark.parametrize(
    "change",
    [
        "model",
        "send_cap",
        "index_snapshot",
        "manifest",
        "future_input",
        "wrong_version",
        "dirty_source",
    ],
)
def test_registration_rejects_scope_index_input_or_source_drift_before_execution(
    tmp_path, index, ledger, monkeypatch, change
):
    root = ledger[0].parents[1]
    target = root / PROBE.PROTOCOL
    target.parent.mkdir(parents=True)
    registered = protocol(index, ledger)
    source_clean = True
    if change == "model":
        registered["gateway"]["model"] = "gpt-4.1-mini"
    elif change == "send_cap":
        registered["gateway"]["max_actual_sends_including_repair"] = 3
    elif change == "index_snapshot":
        registered["index"]["snapshot_id"] = "docs-pilot-" + "0" * 64
    elif change == "manifest":
        registered["index"]["manifest_sha256"] = "0" * 64
    elif change == "future_input":
        registered["turns"][0]["visible"]["gold"] = {"decision": "answer"}
    elif change == "wrong_version":
        registered["turns"][0]["visible"]["reported_facts"][0]["value"] = "1.49.0"
    else:
        source_clean = False
    target.write_text(json.dumps(registered), encoding="utf-8")
    monkeypatch.setattr(
        PROBE,
        "source_observation",
        lambda _root: {
            "source_commit": "committed",
            "source_hashes": {},
            "source_clean": source_clean,
        },
    )
    with pytest.raises(PROBE.ProbeRejected):
        PROBE.load_registration(root, ledger[0], index[0])
