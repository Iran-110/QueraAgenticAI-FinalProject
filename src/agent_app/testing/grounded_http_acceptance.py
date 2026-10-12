"""Preregistered persistent HTTP/gateway control; authored choices are not quality."""

import argparse
import copy
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import tarfile
import types
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
from fastapi.testclient import TestClient

from agent_app import persistent_api, ui_client
from agent_app.contracts import EvidenceBundle, GroundedRequest, ProposalHandoff, ReasoningContext
from agent_app.llm.budget import BudgetLedger
from agent_app.llm.metis import request_id_for
from agent_app.reasoning.grounding import make_grounded_request
from agent_app.testing.fakes import FakeRetriever
from agent_app.testing.grounded_http_binding import GroundedHttpBinding
from agent_app.testing.http_pilot_runtime import offline_network
from agent_app.tracker.sqlite_tracker import SQLiteCaseTracker

PROTOCOL = "experiments/grounded_http_acceptance/protocol-v1.json"
PROTOCOL_SHA256 = "83e8ed0178892bba6ffca9b6d3833228aa0498074604de992e14fe0dd9f1362d"
TOKEN = "public-synthetic-grounded-http-review-token"
REVIEWERS = {"fixture-maintainer": TOKEN}
CODE_PATHS = (
    PROTOCOL,
    "experiments/review_handoff/case-current-state-latest-evidence.json",
    "experiments/review_handoff/expected-analysis-v1.json",
    "experiments/review_handoff/replay.py",
    "src/agent_app/testing/grounded_http_acceptance.py",
    "src/agent_app/testing/grounded_http_binding.py",
    "src/agent_app/testing/http_pilot_runtime.py",
    "src/agent_app/testing/fakes.py",
    "src/agent_app/api.py",
    "src/agent_app/persistent_api.py",
    "src/agent_app/ui_client.py",
    "src/agent_app/contracts.py",
    "src/agent_app/orchestration/service.py",
    "src/agent_app/orchestration/engine.py",
    "src/agent_app/orchestration/conversation.py",
    "src/agent_app/orchestration/handoff.py",
    "src/agent_app/orchestration/intake.py",
    "src/agent_app/orchestration/turns.py",
    "src/agent_app/orchestration/ports.py",
    "src/agent_app/orchestration/validation.py",
    "src/agent_app/reasoning/grounding.py",
    "src/agent_app/reasoning/output.py",
    "src/agent_app/reasoning/review.py",
    "src/agent_app/reasoning/code_checks.py",
    "src/agent_app/reasoning/proposal_checks.py",
    "src/agent_app/reasoning/prompts.py",
    "src/agent_app/tracker/sqlite_tracker.py",
    "src/agent_app/tracker/dummy_tracker.py",
    "src/agent_app/demo.py",
    "experiments/user_intake/case-widget-version-correction.json",
    "experiments/decision_quality/cases-controlled-v8.json",
    "src/agent_app/llm/budget.py",
    "src/agent_app/llm/config.py",
    "src/agent_app/llm/grounded.py",
    "src/agent_app/llm/metis.py",
    "src/agent_app/llm/pricing.py",
    "uv.lock",
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def code_manifest(root: Path) -> dict[str, str]:
    return {name: digest((root / name).read_bytes()) for name in CODE_PATHS}


def load_protocol(root: Path, path: Path | None = None) -> dict:
    payload = (path or root / PROTOCOL).read_bytes()
    if digest(payload) != PROTOCOL_SHA256:
        raise ValueError("RegisteredGroundedHttpProtocolMismatch")
    protocol = json.loads(payload)
    for name in ("inherited_fixture", "inherited_exact_analysis_oracle"):
        reference = protocol[name]
        if digest((root / reference["path"]).read_bytes()) != reference["sha256"]:
            raise ValueError("GroundedHttpInheritedEvidenceMismatch")
    return protocol


def _c3_module(root: Path):
    spec = importlib.util.spec_from_file_location(
        "_grounded_http_c3_fixture", root / "experiments/review_handoff/replay.py"
    )
    if spec is None or spec.loader is None:
        raise ValueError("GroundedHttpFixtureUnavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _baseline_module(root: Path, protocol: dict):
    registered = protocol["baseline"]
    archive = subprocess.run(
        ["git", "archive", registered["git_commit"], *registered["modules"]],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout
    modules, hashes = [], {}
    service_name = "agent_app.orchestration.service"
    original_service = sys.modules.get(service_name)
    try:
        with tarfile.open(fileobj=io.BytesIO(archive)) as contents:
            for index, path in enumerate(registered["modules"]):
                file = contents.extractfile(path)
                if file is None:
                    raise ValueError("GroundedHttpBaselineUnavailable")
                payload = file.read()
                name = f"_grounded_http_released_module_{index}"
                module = types.ModuleType(name)
                module.__spec__ = importlib.util.spec_from_loader(name, loader=None)
                sys.modules[name] = module
                exec(compile(payload, path, "exec"), module.__dict__)
                modules.append(module)
                hashes[path] = digest(payload)
                if index == 0:
                    sys.modules[service_name] = module
    finally:
        if original_service is None:
            sys.modules.pop(service_name, None)
        else:
            sys.modules[service_name] = original_service
    return modules[-1], hashes


def _ledger(path: Path) -> BudgetLedger:
    return BudgetLedger.create(path, limit_usd=Decimal("1"), opening_spend_usd=Decimal("0"))


def _plain(value):
    return json.loads(
        json.dumps(
            value, default=lambda item: str(item) if isinstance(item, Decimal) else asdict(item)
        )
    )


class LostReviewAck:
    """One committed review loses its response, without copying HTTP headers."""

    def __init__(self, http):
        self.http = http
        self.lose_next = False
        self.dropped = False

    def request(self, method, path, **arguments):
        response = self.http.request(method, path, **arguments)
        if (
            self.lose_next
            and method == "POST"
            and path.endswith("/decision")
            and response.status_code == 200
        ):
            self.lose_next = False
            self.dropped = True
            raise httpx.ReadTimeout("Synthetic committed review acknowledgment lost")
        return response


def _app(module, path, adapters, *, baseline):
    tracker = SQLiteCaseTracker(path, reviewer_tokens=REVIEWERS)
    arguments = {"reviewer_tokens": REVIEWERS, "adapters": adapters}
    if not baseline:
        arguments["reasoning_label"] = "grounded_fake_gateway"
    return tracker, module.create_app(tracker, **arguments)


def _binding(
    c3, fixture, ledger, turn, all_bindings, all_retrievers, *, fault="normal", conflict=None
):
    def retriever_factory():
        retriever = FakeRetriever(
            [
                EvidenceBundle.model_validate(fixture["evidence_bundles"][name])
                for name in turn["bundles"]
            ]
        )
        all_retrievers.append(retriever)
        return retriever

    def request_factory(case, message, evidence):
        request = c3.catalog(fixture, case, message, evidence)
        if conflict:
            request = make_grounded_request(
                case, message, evidence, gaps=request.gaps, conflict_groups=(tuple(conflict),)
            )
        return request

    binding = GroundedHttpBinding(
        ledger,
        snapshot_id=fixture["evidence_bundles"]["official-mixed"]["snapshot_id"],
        retriever_factory=retriever_factory,
        planner_factory=lambda: c3.AuthoredPlanner(turn["authored_plan_sequence"]),
        request_factory=request_factory,
        fault=fault,
    )
    all_bindings.append(binding)
    return binding


def _wire_request(record) -> GroundedRequest:
    context = ReasoningContext.model_validate(record["context"])
    assert record["request_id"] == request_id_for(context)
    before = record["reservation_before_response"]
    assert before["status"] == "reserved" and before["request_id"] == record["request_id"]
    payload = record["provider_payload"]
    assert set(payload) == {"model", "messages", "max_tokens", "stream"}
    assert payload["model"] == "gpt-4o-mini" and payload["stream"] is False
    data = json.loads(payload["messages"][1]["content"])
    assert set(data) == {
        "capacity",
        "repair_issue_codes",
        "request",
        "response_schema",
        "source_references",
    }
    assert data["response_schema"]["title"] == "GroundedPlan"
    return GroundedRequest.model_validate(data["request"])


def _decision_request(operation) -> dict:
    return operation.payload()


def _fresh_old_review_rejects(http, case_id, operation):
    payload = _decision_request(operation)
    payload["review_id"] = "fresh-stale-grounded-review"
    response = http.post(
        f"/cases/{case_id}/decision", json=payload, headers={"Authorization": f"Bearer {TOKEN}"}
    )
    assert response.status_code == 409
    assert response.json()["detail"] in {"StaleRevision", "PendingProposalMismatch"}


def _primary(module, root, directory, fixture, c3, protocol, checks, all_bindings, *, baseline):
    ledger = _ledger(directory / "primary-ledger.sqlite3")
    database = directory / "primary-tracker.sqlite3"
    retrievers, primary_bindings, observations, original_events = [], [], [], []
    index = 0

    def adapters(scenario):
        binding = _binding(c3, fixture, ledger, fixture["turns"][index], all_bindings, retrievers)
        primary_bindings.append(binding)
        return binding.adapters(scenario)

    tracker, app = _app(module, database, adapters, baseline=baseline)
    case_id = fixture["initial_case"]["case_id"]
    oracle = c3.load_expected_analyses()
    approved_question = None
    old_operation = None
    old_receipt = None
    old_body = None
    with TestClient(app) as http:
        health = http.get("/health").json()
        checks["truthful_reasoning_label"] = (
            health.get("reasoning_label") == "grounded_fake_gateway"
        )
        transport = LostReviewAck(http)
        client = ui_client.BackendClient(transport, reviewer_token=TOKEN)
        capabilities = client.discover_capabilities()
        checks["truthful_reasoning_label"] &= (
            capabilities.reasoning_label == "grounded_fake_gateway"
        )
        for index, turn in enumerate(fixture["turns"]):
            event = copy.deepcopy(turn["wire_request"])
            if "reply_to_proposal_id" in event:
                event["reply_to_proposal_id"] = approved_question
            original_events.append(copy.deepcopy(event))
            view = client.send_event(case_id, event)
            checks["truthful_reasoning_label"] &= (
                view.get("reasoning_label") == "grounded_fake_gateway"
            )
            assert view["quality_claim"] is False
            assert len(view["actions"]) == (0 if index == 0 else 1 if index == 1 else 2)
            assert view["pending"] is not None, "GroundedHttpFinalProposalMissing"
            handoff = ProposalHandoff.model_validate(view["pending"]["review_handoff"])
            c3._assert_handoff(handoff, turn["expected"])
            assert handoff.analysis == oracle[turn["id"]], "GroundedHttpCompleteAnalysisMismatch"
            cited = set(turn["authored_plan_sequence"][-1].get("source_ids", ()))
            c3._assert_whole_quotes(handoff, cited)
            binding = primary_bindings[-1]
            assert len(binding.records) == turn["expected"]["model_attempts"]
            sent = [_wire_request(record) for record in binding.records]
            assert sent[-1] == handoff.grounded_request
            assert all(request.case == handoff.case for request in sent)
            assert view["pending"]["user_draft"] == handoff.analysis.user_draft
            assert view["pending"]["next_question"] == handoff.analysis.next_question
            if index == 0:
                assert handoff.user_message == event["message"]
                assert handoff.analysis.next_question == fixture["question_catalog"][0]["question"]
            else:
                assert (
                    "Original user problem (historical context; not current facts):"
                    in handoff.user_message
                )
                assert fixture["turns"][0]["wire_request"]["message"] in handoff.user_message
                assert handoff.user_message.endswith(event["message"])
            if handoff.analysis.next_question:
                gap = next(
                    g
                    for g in handoff.grounded_request.gaps
                    if g.question == handoff.analysis.next_question
                )
                assert gap.kind == "user" and gap.necessity
                assert gap.name not in c3._active(handoff.case)
                assert gap.name != "python_version"
            if index == 0:
                operation = client.prepare_review(case_id, view["pending"], "approve")
                approved = client.send_review(operation)
                approved_question = handoff.proposal_id
                assert approved["status"] == "awaiting_user" and len(approved["actions"]) == 1
            elif index == 1:
                old_operation = client.prepare_review(case_id, view["pending"], "approve")
                old_body = old_operation.body_json
                transport.lose_next = True
                try:
                    client.send_review(old_operation)
                except ui_client.BackendError as error:
                    assert error.retryable and transport.dropped
                else:
                    raise AssertionError("GroundedHttpAckLossNotObserved")
                committed = http.get(f"/cases/{case_id}").json()
                old_receipt = committed["review"]
                assert len(committed["actions"]) == 2
            elif index == 2:
                assert old_operation is not None
                _fresh_old_review_rejects(http, case_id, old_operation)
                assert "1.50.0" in handoff.user_message
                assert c3._active(handoff.case)["streamlit_version"] == "1.49.1"
                assert len(sent) == 2 and [len(request.evidence.hits) for request in sent] == [5, 4]
                assert "release-150-multiselect-key-identity-v8" not in {
                    h.chunk_id for h in handoff.evidence.hits
                }
                assert not any(
                    s.version_scope == "exact_metadata_match" for s in handoff.source_inventory
                )
                assert handoff.grounded_request.context_sha256 != sent[0].context_sha256
                checks["fresh_stale_approval_rejected"] = True
                checks["final_retrieval_only_no_retired_evidence"] = True
            elif index == 3:
                assert "streamlit_version" not in c3._active(handoff.case)
                assert any(
                    f.name == "streamlit_version" and f.status != "active"
                    for f in handoff.case.facts
                )
            observations.append({"turn_id": turn["id"], "handoff": handoff.model_dump(mode="json")})
    before_calls = sum(len(b.records) for b in primary_bindings)
    tracker, app = _app(module, database, adapters, baseline=baseline)
    with TestClient(app) as http:
        client = ui_client.BackendClient(http, reviewer_token=TOKEN)
        assert old_operation is not None and old_receipt is not None
        current_before = client.get_case(case_id)
        retried = client.send_review(old_operation)
        assert old_operation.body_json == old_body
        assert retried["review"] == {**old_receipt, "replayed": True}
        assert retried["case_revision"] == 4 and len(retried["actions"]) == 2
        assert retried["pending"] == current_before["pending"]
        assert sum(len(b.records) for b in primary_bindings) == before_calls
        checks["original_review_retry_after_recreation_is_same_receipt_action"] = True
        for event in original_events:
            replay = client.send_event(case_id, event)
            assert replay["intake"]["replayed"] is True and replay["case_revision"] == 4
            assert replay["pending"] == current_before["pending"]
        assert sum(len(b.records) for b in primary_bindings) == before_calls
        assert len(primary_bindings) == 4
        checks["event_replays_do_not_repeat_gateway"] = True
        # An edit creates a separate candidate; rejecting it must not release an action.
        proposal = current_before["pending"]
        edited = client.send_review(
            client.prepare_review(
                case_id,
                proposal,
                "edit",
                edited_draft="Which Streamlit version is installed in the affected environment?",
            )
        )
        assert edited["pending"]["proposal_id"] != proposal["proposal_id"]
        assert len(edited["actions"]) == 2 and edited["pending"]["edited"]
        obsolete = client.prepare_review(case_id, proposal, "approve")
        try:
            client.send_review(obsolete)
        except ui_client.BackendError as error:
            assert error.code in {"PendingProposalMismatch", "StaleRevision"}
        else:
            raise AssertionError("GroundedHttpOldEditedApprovalAccepted")
        rejected = client.send_review(client.prepare_review(case_id, edited["pending"], "reject"))
        assert rejected["pending"] is None and len(rejected["actions"]) == 2
    records = [record for binding in primary_bindings for record in binding.records]
    assert len(records) == protocol["expected_current"]["primary_gateway_calls"]
    assert sum(len(retriever.requests) for retriever in retrievers) == 5
    assert len(tracker.comments(case_id)) == 2
    assert all(ledger.get(record["request_id"]).status == "settled" for record in records)
    checks["actual_provider_payload_equals_captured_handoff_request"] = True
    checks["complete_analysis_and_source_quote_oracle"] = True
    checks["necessary_answerable_question_and_user_source_gap_separation"] = True
    checks["history_and_active_correction_scope"] = True
    return {
        "turns": observations,
        "provider_attempts": records,
        "simulated_ledger": _plain(ledger.snapshot()),
        "actions": 2,
        "gateway_calls": len(records),
        "retrieval_calls": 5,
        "event_replays": 4,
        "restart_scope": "application_and_tracker_recreation_same_interpreter",
    }


def _controls(module, directory, fixture, c3, protocol, all_bindings, *, baseline):
    observations = []
    for control in protocol["controls"]:
        name = control["id"]
        ledger = _ledger(directory / f"{name}-ledger.sqlite3")
        turn = copy.deepcopy(fixture["turns"][0])
        if name == "malformed_first":
            # The malformed first completion consumes one authored response.
            turn["authored_plan_sequence"] *= 2
        conflict = control.get("conflict_group")
        if conflict:
            turn["authored_plan_sequence"] = control["authored_plan_sequence"]
        binding = _binding(
            c3,
            fixture,
            ledger,
            turn,
            all_bindings,
            [],
            fault="normal" if conflict else name,
            conflict=conflict,
        )
        tracker, app = _app(
            module, directory / f"{name}-tracker.sqlite3", binding.adapters, baseline=baseline
        )
        event = copy.deepcopy(turn["wire_request"])
        event["turn_id"] = f"grounded-control-{name}"
        case_id = f"grounded-control-{name}"
        with TestClient(app) as http:
            response = http.post(f"/cases/{case_id}/messages", json=event)
            assert response.status_code == 200
            view = response.json()
            if control["expected_error"]:
                assert view["pending"] is None
                assert view["run_outcome"]["error_code"] == control["expected_error"]
                assert view["run_outcome"]["result"]["model_attempts"] == 1
            else:
                assert view["pending"] is not None
                handoff = ProposalHandoff.model_validate(view["pending"]["review_handoff"])
                assert handoff.reasoning_context.attempt_index == 2
                assert handoff.grounded_request == _wire_request(binding.records[-1])
                if conflict:
                    assert handoff.analysis.decision == "escalate"
                    c3._assert_whole_quotes(handoff, set(conflict))
                    assert (
                        view["run_outcome"]["result"]["output_issues"][0]["code"]
                        == "grounded_conflict_unresolved"
                    )
                else:
                    assert handoff.analysis == c3.load_expected_analyses()["handoff-1"]
            before = len(binding.records)
            replay = http.post(f"/cases/{case_id}/messages", json=event)
            assert replay.status_code == 200 and replay.json()["intake"]["replayed"] is True
            assert len(binding.records) == before
            assert not tracker.comments(case_id)
        assert len(binding.records) == control["expected_transport_calls"]
        accounting = binding.snapshot()
        assert accounting["settled_reservations"] == control["expected_settled"]
        assert accounting["uncertain_reservations"] == control["expected_uncertain"]
        assert accounting["reserved_reservations"] == 0
        assert accounting["ledger"]["halted"] is control["expected_halted"]
        for record in binding.records:
            _wire_request(record)
        observations.append(
            {
                "control_id": name,
                "provider_attempts": binding.records,
                "accounting": accounting,
                "run_outcome": view["run_outcome"],
                "pending": view["pending"],
            }
        )
    return observations


def run(root: Path, state_dir: Path, *, baseline=False, protocol_path: Path | None = None) -> dict:
    if not __debug__:
        raise RuntimeError("AssertionChecksDisabled")
    protocol = load_protocol(root, protocol_path)
    sources = code_manifest(root)
    c3 = _c3_module(root)
    fixture = c3.load_fixture()
    state_dir.mkdir(parents=True, exist_ok=True)
    if any(state_dir.iterdir()):
        raise ValueError("GroundedHttpFreshStateRequired")
    if baseline:
        module, baseline_sha = _baseline_module(root, protocol)
    else:
        module, baseline_sha = persistent_api, None
    checks = dict.fromkeys(protocol["checks"], False)
    bindings = []
    try:
        with offline_network():
            primary = _primary(
                module, root, state_dir, fixture, c3, protocol, checks, bindings, baseline=baseline
            )
            controls = _controls(
                module, state_dir, fixture, c3, protocol, bindings, baseline=baseline
            )
            checks["per_run_gateway_clients_closed_before_failsafe_cleanup"] = all(
                binding.all_clients_closed for binding in bindings
            )
            attempts = primary["provider_attempts"] + [
                record for control in controls for record in control["provider_attempts"]
            ]
            assert len(attempts) == protocol["expected_current"]["total_gateway_calls"]
            for record in attempts:
                context = ReasoningContext.model_validate(record["context"])
                assert context.attempt_index <= 2
                serialized = json.dumps(record["provider_payload"])
                for forbidden in (
                    TOKEN,
                    "public-synthetic-persistent-grounded-key",
                    "authored_plan_sequence",
                    "acceptable_decisions",
                    "expected-analysis-v1.json",
                ):
                    assert forbidden not in serialized
                assert not any(
                    "header" in name.lower() or "authorization" in name.lower() for name in record
                )
            checks["no_credentials_or_expected_labels_in_wire_or_receipt"] = True
            checks["bounded_gateway_attempts_and_simulated_accounting"] = True
            if sources != code_manifest(root):
                raise RuntimeError("GroundedHttpCodeChangedDuringReplay")
            expected = protocol["baseline"] if baseline else protocol["expected_current"]
            failures = sorted(name for name, passed in checks.items() if not passed)
            expected_failures = (
                sorted(protocol["baseline"]["expected_failures"]) if baseline else []
            )
            assert failures == expected_failures, "GroundedHttpUnexpectedAcceptanceResult"
            assert (
                sum(checks.values())
                == expected["checks_passed" if not baseline else "expected_checks_passed"]
            )
            receipt = {
                "schema_version": 1,
                "protocol_id": protocol["protocol_id"],
                "mode": "baseline" if baseline else "current",
                "protocol_sha256": PROTOCOL_SHA256,
                "source_commit": subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=root,
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout.strip(),
                "source_clean": not subprocess.run(
                    ["git", "status", "--porcelain"],
                    cwd=root,
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout.strip(),
                "source_hashes": sources,
                "baseline_module_sha256": baseline_sha,
                "baseline_commit": protocol["baseline"]["git_commit"] if baseline else None,
                "primary": primary,
                "controls": controls,
                "checks": checks,
                "summary": {
                    "checks_passed": sum(checks.values()),
                    "checks_total": len(checks),
                    "expected_comparison_matched": True,
                    "primary_gateway_calls": 5,
                    "control_gateway_calls": 6,
                    "actual_paid_requests": 0,
                    "actual_API_cost_USD": "0",
                    "real_model_calls": 0,
                    "quality_claim": False,
                },
                "limitations": protocol["limitations"],
            }
            assert TOKEN not in json.dumps(receipt)
            return receipt
    finally:
        for binding in bindings:
            binding.close()
        assert all(binding.all_clients_closed for binding in bindings)


def write_receipt(path: Path, receipt: dict) -> None:
    with path.open("x", encoding="utf-8") as file:
        json.dump(receipt, file, ensure_ascii=False, indent=2)
        file.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        root = Path(__file__).resolve().parents[3]
        with TemporaryDirectory(prefix="offline-grounded-http-") as directory:
            receipt = run(root, Path(directory), baseline=arguments.baseline)
        write_receipt(arguments.output, receipt)
    except Exception as error:
        code = (
            "AssertionChecksDisabled"
            if str(error) == "AssertionChecksDisabled"
            else "GroundedHttpAcceptanceFailed"
        )
        print(json.dumps({"error_code": code}))
        return 2
    print(json.dumps({"mode": receipt["mode"], **receipt["summary"]}))
    return 0
