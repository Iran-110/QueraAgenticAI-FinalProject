"""Controlled repetitions use synthetic providers and disposable halted ledgers.

These controls verify experiment integrity, not model quality or a manual UI smoke.
The team's real ledger and credentials are never opened.
"""

import hashlib
import importlib.util
import json
import shutil
import sys
from collections import Counter
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from agent_app.evaluation.runner import collect
from agent_app.llm.budget import BudgetLedger
from agent_app.llm.config import MetisConfig
from agent_app.llm.pricing import get_price
from agent_app.reasoning.catalog import load_user_gap_vocabulary
from agent_app.testing import stability_probe as probe
from agent_app.testing.http_pilot_runtime import offline_network

ROOT = Path(__file__).resolve().parents[1]
DEV = ROOT / "data/evaluation/dev-three-v1"


def preparation(tmp_path):
    ledger_path = tmp_path / "runtime/budget.sqlite3"
    ledger_path.parent.mkdir(parents=True)
    ledger = BudgetLedger.create(
        ledger_path, limit_usd=Decimal("4.5"), opening_spend_usd=Decimal("0")
    )
    ledger.reserve(
        request_id="synthetic-old-quarantine",
        run_id="synthetic-old-run",
        case_id="synthetic-old-case",
        case_revision=0,
        attempt=1,
        model="gpt-4.1-mini",
        phase="development",
        amount_usd=Decimal("0.02"),
    )
    ledger.mark_uncertain("synthetic-old-quarantine", error_code="ProviderModelMismatch")
    ledger.halt()
    ledger.authorize_continuation(
        authorization_id="synthetic-old-grant",
        authorization_ref="synthetic-historical-user-authorization",
        expected_request_id="synthetic-old-quarantine",
        held_usd=Decimal("0.02"),
        additional_cap_usd=Decimal("0.01"),
    )
    fixtures = {
        item.case["case_id"]: item
        for item in collect([ROOT / path for path in probe.FIXTURE_PATHS], mode="live")
    }
    definitions = load_user_gap_vocabulary(str(DEV / "user-gap-vocabulary-v1.json"))
    protocol = {
        "experiment_id": "synthetic-independent-four-rounds",
        "protocol_id": "core-stability-v1",
        "authorization_ref": "synthetic-current-user-authorization",
        "parent_authorization_id": "synthetic-old-grant",
        "input_pins": {},
        "batches": probe.stable_batches(),
    }
    for batch in protocol["batches"]:
        batch["scope_id"] = "synthetic-scope-" + batch["batch_id"]
        batch["request_slots_sha256"] = probe.slots_sha256(
            probe.slots_for_batch(protocol, batch, fixtures)
        )
    return protocol, fixtures, definitions, ledger


def authorize(protocol, batch, fixtures, ledger):
    slots = probe.slots_for_batch(protocol, batch, fixtures)
    ledger.authorize_experiment_scope(
        authorization_id=batch["scope_id"],
        authorization_ref=protocol["authorization_ref"],
        parent_authorization_id=protocol["parent_authorization_id"],
        protocol_sha256=probe.sha(batch["batch_id"].encode()),
        request_slots=slots,
        additional_cap_usd=probe.CAP,
    )
    config = MetisConfig(
        api_key="synthetic-stability-noncredential",
        live_enabled=True,
        model=probe.MODEL,
        phase="development",
        response_mode="grounded_plan",
        continuation_id=batch["scope_id"],
        grounded_source_gap_handoff=True,
        input_token_reserve=probe.INPUT_RESERVE,
        max_output_tokens=probe.OUTPUT_LIMIT,
        max_request_usd=get_price(probe.MODEL).cost(probe.INPUT_RESERVE, probe.OUTPUT_LIMIT),
    )
    return config


def provider_response(request, payloads, *, reject_pilot=False):
    wire = json.loads(request.content)
    payload = json.loads(wire["messages"][1]["content"])
    payloads.append(payload)
    current = payload["request"]
    gaps = [gap for gap in current["gaps"] if gap["kind"] == "user"]
    if reject_pilot and current["case"]["case_id"] == "dev-case-a":
        content = "{}"
    else:
        plan = {
            "context_sha256": current["context_sha256"],
            "sources": [],
            "question_name": None,
            "retrieval_queries": [],
        }
        if gaps:
            question = next((gap for gap in gaps if gap["name"] == "streamlit_version"), gaps[0])
            plan.update(decision="ask", question_name=question["name"])
        else:
            plan.update(decision="answer", sources=payload["source_references"])
        content = json.dumps(plan)
    return httpx.Response(
        200,
        json={
            "model": "gpt-4o-mini-2024-07-18",
            "choices": [
                {"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
            ],
            "usage": {"prompt_tokens": 1000, "completion_tokens": 180, "total_tokens": 1180},
        },
    )


def test_four_rounds_counterbalance_pairs_and_allocate_finite_disjoint_request_identities(tmp_path):
    protocol, fixtures, _definitions, _ledger = preparation(tmp_path)
    seen_request_ids, seen_job_ids = set(), set()
    family_orders = {family: [] for family in fixtures}
    for round_number, batch in enumerate(protocol["batches"], start=1):
        assert len(batch["jobs"]) == 6
        assert Counter(job["case_id"] for job in batch["jobs"]) == {
            "dev-case-a": 2,
            "dev-case-b": 2,
            "dev-case-c": 2,
        }
        for index in (0, 2, 4):
            pair = batch["jobs"][index : index + 2]
            assert pair[0]["case_id"] == pair[1]["case_id"]
            assert {job["arm"] for job in pair} == {"B_reviewed_gaps", "C_decision_guidance"}
            family_orders[pair[0]["case_id"]].append(tuple(job["arm"] for job in pair))
        assert all(job["round"] == round_number for job in batch["jobs"])
        jobs = {job["job_id"] for job in batch["jobs"]}
        assert len(jobs) == 6 and not seen_job_ids & jobs
        seen_job_ids.update(jobs)
        slots = probe.slots_for_batch(protocol, batch, fixtures)
        request_ids = {slot.request_id for slot in slots}
        assert len(slots) == len(request_ids) == 24
        assert not request_ids & seen_request_ids
        seen_request_ids.update(request_ids)
        assert sum(slot.amount_usd for slot in slots) <= Decimal("0.10")
        assert all(slot.phase == "development" and slot.model == "gpt-4o-mini" for slot in slots)
        by_run = {}
        for slot in slots:
            by_run.setdefault(slot.run_id, []).append(slot.attempt)
        assert all(attempts == [1, 2] for attempts in by_run.values())
    assert len(seen_request_ids) == 96
    assert all(
        Counter(orders)
        == {
            ("B_reviewed_gaps", "C_decision_guidance"): 2,
            ("C_decision_guidance", "B_reviewed_gaps"): 2,
        }
        for orders in family_orders.values()
    )


def test_mocked_four_rounds_share_current_inputs_withhold_future_turns_and_keep_old_halt(tmp_path):
    protocol, fixtures, definitions, ledger = preparation(tmp_path)
    original = probe.ledger_observation(ledger._path)
    payloads, receipts = [], []
    with offline_network():
        for batch in protocol["batches"]:
            config = authorize(protocol, batch, fixtures, ledger)
            before = probe.ledger_observation(ledger._path)
            receipt = probe.run_batch(
                protocol,
                batch,
                fixtures,
                definitions,
                ledger,
                config,
                before,
                underlying=httpx.MockTransport(lambda req: provider_response(req, payloads)),
            )
            receipts.append(receipt)
            assert receipt["actual_sends"] == 12
            assert receipt["completed_routes"] == 6 and not receipt["stopped_early"]
            assert receipt["accounting"]["accounting_complete"] is True
            assert receipt["original_accounting_preserved"] is True
            assert all(check["passed"] for job in receipt["jobs"] for check in job["checks"])
            assert ledger.experiment_scope_status(batch["scope_id"]).consumed_requests == 12
            ledger.close_experiment_scope(batch["scope_id"])
    assert len(payloads) == 48
    assert (
        len({run for receipt in receipts for job in receipt["jobs"] for run in job["run_ids"]})
        == 48
    )
    # Compare paired initial calls at the actual gateway payload, not pre-enrichment inputs.
    for batch_start in range(0, len(payloads), 12):
        for pair_start in (0, 4, 8):
            first = payloads[batch_start + pair_start]
            second = payloads[batch_start + pair_start + 2]
            assert first["request"] == second["request"]
            assert first["source_references"] == second["source_references"]
            assert first["capacity"] == second["capacity"]
            assert ("decision_contracts" in first) != ("decision_contracts" in second)
    for payload in payloads:
        current = payload["request"]
        assert set(current) == {
            "case",
            "user_message",
            "evidence",
            "gaps",
            "conflict_groups",
            "context_sha256",
        }
        assert "gold" not in payload and "agent_script" not in payload
        if current["case"]["case_id"] == "dev-case-c" and current["case"]["case_revision"] == 1:
            assert "1.31.1" not in json.dumps(current["case"]["facts"])
            assert "1.31.1" not in current["user_message"]
        if current["case"]["case_id"] == "dev-case-a" and current["case"]["case_revision"] == 1:
            assert "1.50.0" not in json.dumps(current["case"]["facts"])
            assert "1.50.0" not in current["user_message"]
    # Both arms use the same explicit renderer improvement; it cannot explain their delta.
    enum_jobs = [
        job for receipt in receipts for job in receipt["jobs"] if job["case_id"] == "dev-case-c"
    ]
    assert {job["arm"] for job in enum_jobs} == {"B_reviewed_gaps", "C_decision_guidance"}
    for job in enum_jobs:
        assert any(
            "stale approval" in check["check"] and check["passed"] for check in job["checks"]
        )
        for step in job["steps"]:
            proposal = step["proposal"]
            assert "Caller-declared source gaps" in proposal["user_draft"]
            assert "maintainer investigation" in proposal["user_draft"]
    after = probe.ledger_observation(ledger._path)
    for key in ("meta_sha256", "unknown_sha256", "old_grants_sha256"):
        assert after[key] == original[key]
    assert ledger.snapshot().halted and ledger.snapshot().uncertain_usd == Decimal("0.02")
    assert ledger.continuation_status("synthetic-old-grant").used_usd == Decimal("0")


def test_failed_case_attempts_are_retained_once_and_closed_scope_cannot_rerun(tmp_path):
    protocol, fixtures, definitions, ledger = preparation(tmp_path)
    batch = protocol["batches"][0]
    config = authorize(protocol, batch, fixtures, ledger)
    before = probe.ledger_observation(ledger._path)
    payloads = []
    with offline_network():
        receipt = probe.run_batch(
            protocol,
            batch,
            fixtures,
            definitions,
            ledger,
            config,
            before,
            underlying=httpx.MockTransport(
                lambda req: provider_response(req, payloads, reject_pilot=True)
            ),
        )
    assert receipt["visited_jobs"] == 6 and receipt["completed_routes"] == 4
    assert receipt["stopped_early"] is False and receipt["actual_sends"] == 12
    failures = [attempt for attempt in receipt["attempts"] if attempt["plan"] is None]
    assert len(failures) == 4
    failed_runs = Counter(item["context"]["run_id"] for item in failures)
    assert len(failed_runs) == 2 and set(failed_runs.values()) == {2}
    assert all(not item["schema_observation"]["syntactic_valid"] for item in failures)
    assert any(not check["passed"] for job in receipt["jobs"] for check in job["checks"])
    assert receipt["accounting"]["accounting_complete"] is True
    ledger.close_experiment_scope(batch["scope_id"])
    closed_before = probe.ledger_observation(ledger._path)
    with offline_network():
        replay = probe.run_batch(
            protocol,
            batch,
            fixtures,
            definitions,
            ledger,
            config,
            closed_before,
            underlying=httpx.MockTransport(lambda req: pytest.fail("Closed scope cannot send")),
        )
    assert replay["visited_jobs"] == replay["actual_sends"] == 0
    assert replay["stopped_early"] is True
    assert probe.ledger_observation(ledger._path) == closed_before


def test_duplicate_job_request_slots_are_rejected_before_authorization(tmp_path):
    protocol, fixtures, _definitions, ledger = preparation(tmp_path)
    batch = deepcopy(protocol["batches"][0])
    batch["jobs"][1] = deepcopy(batch["jobs"][0])
    before = probe.ledger_observation(ledger._path)
    with pytest.raises(probe.DevProbeRejected):
        probe.slots_for_batch(protocol, batch, fixtures)
    assert probe.ledger_observation(ledger._path) == before


def test_failed_checkpoint_before_transport_preserves_uncertain_hold_and_stops_batch(tmp_path):
    protocol, fixtures, definitions, ledger = preparation(tmp_path)
    batch = protocol["batches"][0]
    config = authorize(protocol, batch, fixtures, ledger)
    before = probe.ledger_observation(ledger._path)
    calls = []

    def failed_checkpoint(value):
        if "event" in value:
            assert value["provider_sends"][0]["http_send_started"] is False
            raise OSError("synthetic-before-provider-journal-failure")

    with offline_network():
        receipt = probe.run_batch(
            protocol,
            batch,
            fixtures,
            definitions,
            ledger,
            config,
            before,
            underlying=httpx.MockTransport(lambda request: calls.append(request)),
            checkpoint=failed_checkpoint,
        )
    assert calls == [] and receipt["actual_sends"] == 0
    assert receipt["visited_jobs"] == 1 and receipt["stopped_early"] is True
    assert receipt["accounting"]["accounting_complete"] is False
    assert len(receipt["provider_sends"]) == 1
    assert receipt["provider_sends"][0]["http_send_started"] is False
    assert ledger.snapshot().halted and ledger.snapshot().uncertain_usd > Decimal("0.02")
    after = probe.ledger_observation(ledger._path)
    assert after["meta_sha256"] == before["meta_sha256"]
    # New uncertainty deliberately revokes the previous grant, without
    # replenishing it or releasing its unresolved original hold.
    parent = ledger.continuation_status("synthetic-old-grant")
    assert not parent.active and parent.block_reason == "NewUncertainty"
    assert parent.used_usd == Decimal("0") and parent.held_usd == Decimal("0.02")
    assert parent.additional_cap_usd == Decimal("0.01")
    assert "synthetic-before-provider-journal-failure" not in json.dumps(receipt)
    ledger.close_experiment_scope(batch["scope_id"])


def cli_module():
    spec = importlib.util.spec_from_file_location(
        "core_stability_cli_unit", ROOT / "scripts/core_stability_probe.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_authorization_journal_failure_closes_scope_without_call_or_private_error(
    tmp_path, monkeypatch, capsys
):
    protocol, fixtures, definitions, ledger = preparation(tmp_path)
    source = {"source_commit": "synthetic-source", "source_clean": True, "source_hashes": {}}
    registration = {
        **source,
        "protocol_path": probe.PROTOCOL.as_posix(),
        "protocol_sha256": "a" * 64,
        "ledger_before": probe.ledger_observation(ledger._path),
    }
    slots = {
        batch["batch_id"]: probe.slots_for_batch(protocol, batch, fixtures)
        for batch in protocol["batches"]
    }
    module = cli_module()
    monkeypatch.setattr(
        module, "preflight", lambda *args: (protocol, fixtures, definitions, slots, registration)
    )
    monkeypatch.setattr(module, "source_observation", lambda *args: source)
    monkeypatch.setattr(module, "credential", lambda *args: "synthetic-cli-noncredential")
    monkeypatch.setattr(
        module, "run_batch", lambda *args, **kwargs: pytest.fail("Journal failed before provider")
    )
    original_write = module.write_new

    def fail_authorization(path, value, *args):
        if path.name == "authorization.json":
            raise OSError("synthetic-private-journal-error")
        return original_write(path, value, *args)

    monkeypatch.setattr(module, "write_new", fail_authorization)
    destination = tmp_path / "private-output"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stability",
            "--live",
            "--ledger",
            str(ledger._path),
            "--env-file",
            str(tmp_path / "unused.env"),
            "--output-dir",
            str(destination),
        ],
    )
    with offline_network():
        assert module.main() == 1
    assert (
        ledger.experiment_scope_status(protocol["batches"][0]["scope_id"]).block_reason
        == "ExperimentClosed"
    )
    assert ledger.snapshot().halted and ledger.snapshot().uncertain_usd == Decimal("0.02")
    assert "synthetic-private-journal-error" not in capsys.readouterr().out
    assert "synthetic-private-journal-error" not in (destination / "failure.json").read_text(
        encoding="utf-8"
    )
    assert probe.ledger_observation(ledger._path)["counts"] == {"uncertain": 1}


@pytest.mark.parametrize(
    "failure,expected_exit",
    [("stopped", 2), ("accounting", 2), ("original_accounting", 2), ("route", 0)],
)
def test_cli_last_batch_integrity_controls_exit_and_authorization_binds_initial_ledger(
    tmp_path, monkeypatch, capsys, failure, expected_exit
):
    protocol, fixtures, definitions, ledger = preparation(tmp_path)
    protocol["batches"] = protocol["batches"][:1]
    original = probe.ledger_observation(ledger._path)
    source = {
        "source_commit": "synthetic-frozen-source",
        "source_clean": True,
        "source_hashes": {"src/agent_app/testing/stability_probe.py": "b" * 64},
    }
    registration = {
        **source,
        "protocol_path": probe.PROTOCOL.as_posix(),
        "protocol_sha256": "a" * 64,
        "ledger_before": original,
    }
    slots = {
        batch["batch_id"]: probe.slots_for_batch(protocol, batch, fixtures)
        for batch in protocol["batches"]
    }
    result = {
        "batch_id": protocol["batches"][0]["batch_id"],
        "actual_sends": 0,
        "completed_routes": 0,
        "stopped_early": failure == "stopped",
        "accounting": {"accounting_complete": failure != "accounting"},
        "original_accounting_preserved": failure != "original_accounting",
        "jobs": [{"checks": [{"check": "recorded failed route", "passed": False}]}],
    }
    module = cli_module()
    monkeypatch.setattr(
        module, "preflight", lambda *args: (protocol, fixtures, definitions, slots, registration)
    )
    monkeypatch.setattr(module, "source_observation", lambda *args: source)
    monkeypatch.setattr(module, "credential", lambda *args: "synthetic-cli-noncredential")
    monkeypatch.setattr(module, "run_batch", lambda *args, **kwargs: deepcopy(result))
    destination = tmp_path / "private-output"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stability",
            "--live",
            "--ledger",
            str(ledger._path),
            "--env-file",
            str(tmp_path / "unused.env"),
            "--output-dir",
            str(destination),
        ],
    )
    with offline_network():
        assert module.main() == expected_exit
    assert json.loads(capsys.readouterr().out)["receipt_written"] is True
    final = json.loads((destination / "receipt.json").read_text(encoding="utf-8"))
    # Model failure is retained; only accounting/control loss fails the run.
    assert final["batches"][0]["jobs"] == result["jobs"]
    assert final["quality_claim"] is False and final["actual_sends"] == 0
    batch = protocol["batches"][0]
    signed = json.loads(
        (destination / batch["batch_id"] / "registration.json").read_text(encoding="utf-8")
    )
    digest = signed.pop("registration_sha256")
    assert signed["ledger_before"] == original
    assert signed["source_commit"] == source["source_commit"]
    assert signed["source_hashes"] == source["source_hashes"]
    assert digest == hashlib.sha256(json.dumps(signed, sort_keys=True).encode()).hexdigest()
    status = ledger.experiment_scope_status(batch["scope_id"])
    assert status.protocol_sha256 == digest and status.block_reason == "ExperimentClosed"
    changed_ledger = deepcopy(signed)
    changed_ledger["ledger_before"]["db_sha256"] = "c" * 64
    assert hashlib.sha256(json.dumps(changed_ledger, sort_keys=True).encode()).hexdigest() != digest
    assert ledger.snapshot().halted and ledger.snapshot().uncertain_usd == Decimal("0.02")


def registered_packet(tmp_path, protocol, ledger):
    shutil.copytree(DEV, tmp_path / "data/evaluation/dev-three-v1")
    evidence = json.loads((DEV / "evidence-v1.json").read_bytes())
    for name in evidence["source_pins"]:
        destination = tmp_path / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
    names = (
        *probe.FIXTURE_PATHS,
        probe.VOCABULARY,
        "data/evaluation/dev-three-v1/evidence-v1.json",
    )
    protocol.update(
        ledger_before_sha256=probe.ledger_observation(ledger._path)["db_sha256"],
        renderer_source_gap_handoff=True,
        model=probe.MODEL,
        max_output_tokens=probe.OUTPUT_LIMIT,
        scope_cap_usd=str(probe.CAP),
        user_gap_vocabulary_path=probe.VOCABULARY,
        input_pins={name: probe.sha((tmp_path / name).read_bytes()) for name in names},
    )
    target = tmp_path / probe.PROTOCOL
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(protocol), encoding="utf-8")
    return target


def test_valid_preregistration_read_only_returns_all_frozen_slots_without_credential_or_ledger_write(
    tmp_path, monkeypatch, capsys
):
    protocol, fixtures, _definitions, ledger = preparation(tmp_path)
    # Match a real historical ledger that already has experiment tables, using
    # a distinct completed registration; its identities are never re-used.
    previous = deepcopy(protocol["batches"][0])
    previous.update(batch_id="synthetic-prior", scope_id="synthetic-prior-scope")
    for job in previous["jobs"]:
        job["job_id"] = "prior:" + job["job_id"]
    authorize(protocol, previous, fixtures, ledger)
    ledger.close_experiment_scope(previous["scope_id"])
    target = registered_packet(tmp_path, protocol, ledger)
    source = {"source_commit": "synthetic", "source_clean": True, "source_hashes": {}}
    monkeypatch.setattr(probe, "source_observation", lambda *args: source)
    before = probe.ledger_observation(ledger._path)
    actual, loaded, definitions, slots, registration = probe.preflight(
        tmp_path, ledger._path, target
    )
    assert actual["protocol_id"] == "core-stability-v1"
    assert set(loaded) == {"dev-case-a", "dev-case-b", "dev-case-c"}
    assert {item.name for item in definitions} == {"parent_callback_code", "state_update_order"}
    assert len(slots) == 4 and all(len(registered) == 24 for registered in slots.values())
    assert registration["ledger_before"] == before
    module = cli_module()
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(
        module, "credential", lambda *args: pytest.fail("Read-only cannot read key")
    )
    monkeypatch.setattr(
        sys, "argv", ["stability", "--protocol", str(target), "--ledger", str(ledger._path)]
    )
    with offline_network():
        assert module.main() == 0
    output = json.loads(capsys.readouterr().out)
    assert output["eligible_read_only"] is True
    assert output["batches"] == 4 and output["max_sends"] == 96 and output["actual_sends"] == 0
    assert probe.ledger_observation(ledger._path) == before


@pytest.mark.parametrize("mutation", ["protocol", "duplicate_job", "slots_digest", "renderer"])
def test_invalid_preregistration_is_refused_before_cli_reads_credentials(
    tmp_path, monkeypatch, capsys, mutation
):
    protocol, _fixtures, _definitions, ledger = preparation(tmp_path)
    target = registered_packet(tmp_path, protocol, ledger)
    if mutation == "protocol":
        protocol["protocol_id"] = "unregistered-protocol"
    elif mutation == "duplicate_job":
        protocol["batches"][0]["jobs"][1] = deepcopy(protocol["batches"][0]["jobs"][0])
    elif mutation == "slots_digest":
        protocol["batches"][0]["request_slots_sha256"] = "b" * 64
    else:
        protocol["renderer_source_gap_handoff"] = False
    target.write_text(json.dumps(protocol), encoding="utf-8")
    before = probe.ledger_observation(ledger._path)
    source = {"source_commit": "synthetic", "source_clean": True, "source_hashes": {}}
    monkeypatch.setattr(probe, "source_observation", lambda *args: source)
    module = cli_module()
    monkeypatch.setattr(module, "ROOT", tmp_path)
    credential_calls = []
    monkeypatch.setattr(module, "credential", lambda *args: credential_calls.append(args))
    destination = tmp_path / "never-created-output"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stability",
            "--live",
            "--protocol",
            str(target),
            "--ledger",
            str(ledger._path),
            "--env-file",
            str(tmp_path / "never-read.env"),
            "--output-dir",
            str(destination),
        ],
    )
    with offline_network():
        assert module.main() == 1
    assert credential_calls == [] and not destination.exists()
    assert probe.ledger_observation(ledger._path) == before
    assert json.loads(capsys.readouterr().out)["diagnostic"] == "CoreStabilityProbeRejected"
