"""Fixture gateway lifecycle/isolation at the reusable HTTP composition seam."""

import json
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import httpx
import pytest

from agent_app.contracts import (
    CaseState,
    EvidenceBundle,
    EvidenceHit,
    Fact,
    GroundedPlan,
    GroundedSourceRef,
)
from agent_app.llm.budget import BudgetLedger
from agent_app.llm.config import MetisConfig
from agent_app.orchestration import SupportEngine
from agent_app.orchestration.handoff import ReasoningCapture, build_handoff
from agent_app.reasoning.grounding import make_grounded_request, source_content_sha256
from agent_app.testing.fakes import FakeRetriever
from agent_app.testing.grounded_http_binding import GroundedHttpBinding, runtime_catalog
from agent_app.testing.http_pilot_runtime import offline_network


def bundle(chunk="source:current", version="1.50.0"):
    return EvidenceBundle(
        snapshot_id="fixture:grounded-http",
        hits=(
            EvidenceHit(
                chunk_id=chunk,
                source_id="docs:fixture",
                source_type="doc",
                source_url="https://example.org/fixture",
                excerpt="A supplied excerpt; no application's cause or fix is established.",
                applicable_versions=(version,),
            ),
        ),
    )


def case(name="case:grounded-http", *, version=None):
    facts = ()
    if version:
        facts = (Fact(name="streamlit_version", value=version, source_ref="user:1", turn_id="t:1"),)
    return CaseState(case_id=name, facts=facts)


class CurrentPlanner:
    """Authored fixture routing, using only the actual emitted grounded input."""

    def plan(self, request, *, context):
        if any(gap.name == "streamlit_version" for gap in request.gaps):
            return GroundedPlan(
                context_sha256=request.context_sha256,
                decision="ask",
                question_name="streamlit_version",
            )
        hit = request.evidence.hits[0]
        return GroundedPlan(
            context_sha256=request.context_sha256,
            decision="answer",
            sources=(
                GroundedSourceRef(chunk_id=hit.chunk_id, content_sha256=source_content_sha256(hit)),
            ),
        )


@pytest.fixture
def ledger(tmp_path):
    return BudgetLedger.create(
        tmp_path / "fixture-ledger.sqlite3", limit_usd=Decimal("1"), opening_spend_usd=Decimal("0")
    )


def binding(ledger, **options):
    return GroundedHttpBinding(
        ledger,
        snapshot_id="fixture:grounded-http",
        retriever_factory=options.pop("retriever_factory", lambda: FakeRetriever([bundle()])),
        planner_factory=options.pop("planner_factory", CurrentPlanner),
        **options,
    )


def run(binding, current=None, *, run_id="run:grounded-http"):
    ports = binding.adapters("not-a-planner-option")
    capture = ReasoningCapture(ports.reasoner)
    try:
        result = SupportEngine(ports.retriever, capture, snapshot_id=ports.snapshot_id).run(
            current or case(), "The widget resets after rerun.", run_id=run_id
        )
        handoff = None
        if result.analysis is not None:
            handoff = build_handoff(
                result, capture.last, grounded_request=ports.grounded_request_supplier()
            )
        return result, handoff
    finally:
        ports.cleanup()


def test_runtime_catalog_uses_only_active_user_version_and_current_metadata():
    original = case(version="1.50.0")
    corrected = original.model_copy(
        update={
            "facts": (
                original.facts[0].model_copy(update={"status": "superseded"}),
                Fact(name="streamlit_version", value="1.49.0", source_ref="user:2", turn_id="t:2"),
            ),
            "case_revision": 1,
        }
    )
    first = runtime_catalog(original, "The widget resets.", bundle())
    second = runtime_catalog(corrected, "Actually 1.49.0.", bundle())
    assert first.gaps == ()
    assert [gap.name for gap in second.gaps] == ["exact_version_documentation"]
    assert second.gaps[0].kind == "source" and second.gaps[0].question is None
    assert first.context_sha256 != second.context_sha256
    inferred = case().model_copy(
        update={"facts": (original.facts[0].model_copy(update={"provenance_kind": "evidence"}),)}
    )
    assert (
        runtime_catalog(inferred, "The widget resets.", bundle()).gaps[0].name
        == "streamlit_version"
    )
    withdrawn = corrected.model_copy(
        update={
            "facts": tuple(f.model_copy(update={"status": "superseded"}) for f in corrected.facts)
        }
    )
    assert runtime_catalog(withdrawn, "The version is unknown.", bundle()).gaps[0].kind == "user"


def test_real_mock_wire_retains_exact_supplied_request_and_closes_after_handoff(
    ledger, monkeypatch
):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Real transports and environment config are forbidden")

    monkeypatch.setattr(httpx.HTTPTransport, "__init__", forbidden)
    monkeypatch.setattr(MetisConfig, "from_env", forbidden)
    test_binding = binding(ledger)
    with offline_network():
        result, handoff = run(test_binding)
    assert result.status == "awaiting_approval" and handoff.analysis.decision == "ask"
    records = test_binding.records
    sent = json.loads(records[0]["provider_payload"]["messages"][1]["content"])
    assert sent["request"] == handoff.grounded_request.model_dump(mode="json")
    assert sent["response_schema"]["title"] == "GroundedPlan"
    assert records[0]["reservation_before_response"]["status"] == "reserved"
    assert records[0]["reservation_after_attempt"]["status"] == "settled"
    assert test_binding.all_clients_closed
    assert ledger.snapshot().settled_usd == Decimal("0.000070125")
    serialized = json.dumps(records)
    assert "public-synthetic-persistent-grounded-key" not in serialized
    assert "Authorization" not in serialized and "headers" not in serialized
    records[0]["context"]["run_id"] = "caller-mutated"
    assert test_binding.records[0]["context"]["run_id"] == "run:grounded-http"
    assert test_binding.snapshot()["actual_paid_requests"] == 0


def test_repair_uses_same_run_next_attempt_and_same_latest_request(ledger):
    test_binding = binding(ledger, fault="malformed_first")
    with offline_network():
        result, handoff = run(test_binding)
    assert result.model_attempts == 2 and result.status == "awaiting_approval"
    first, second = test_binding.records
    assert first["context"]["run_id"] == second["context"]["run_id"]
    assert [r["context"]["attempt_index"] for r in (first, second)] == [1, 2]
    assert first["request_id"] != second["request_id"]
    sent = json.loads(second["provider_payload"]["messages"][1]["content"])
    assert sent["repair_issue_codes"] == ["invalid_grounded_plan"]
    assert sent["request"] == handoff.grounded_request.model_dump(mode="json")
    assert test_binding.snapshot()["settled_reservations"] == 2
    assert test_binding.all_clients_closed


@pytest.mark.parametrize(
    ("fault", "error", "halted"),
    [
        ("timeout", "ProviderRequestFailed", False),
        ("model_mismatch", "ProviderModelMismatch", True),
    ],
)
def test_terminal_fault_closes_without_retry_and_preserves_uncertain_reservation(
    ledger, fault, error, halted
):
    test_binding = binding(ledger, fault=fault)
    with offline_network():
        result, handoff = run(test_binding)
    assert handoff is None and result.error_code == error and result.model_attempts == 1
    snapshot = test_binding.snapshot()
    assert snapshot["transport_calls"] == snapshot["uncertain_reservations"] == 1
    assert snapshot["settled_reservations"] == snapshot["reserved_reservations"] == 0
    assert snapshot["ledger"]["halted"] is halted
    assert Decimal(snapshot["ledger"]["uncertain_usd"]) > 0
    assert test_binding.all_clients_closed


def test_refinement_captures_actual_latest_bundle_not_first_sources(ledger):
    class RefinePlanner(CurrentPlanner):
        def plan(self, request, *, context):
            if context.attempt_index == 1:
                return GroundedPlan(
                    context_sha256=request.context_sha256,
                    decision="retrieve_more",
                    retrieval_queries=("Search for the corrected version source",),
                )
            return super().plan(request, context=context)

    test_binding = binding(
        ledger,
        planner_factory=RefinePlanner,
        retriever_factory=lambda: FakeRetriever([bundle("source:old"), bundle("source:latest")]),
    )
    with offline_network():
        result, handoff = run(test_binding, case(version="1.50.0"))
    assert result.model_attempts == result.retrieval_rounds == 2
    assert handoff.grounded_request.evidence.hits[0].chunk_id == "source:latest"
    assert handoff.grounded_request.evidence.retrieval_round == 2
    before, after = [
        json.loads(record["provider_payload"]["messages"][1]["content"])["request"]
        for record in test_binding.records
    ]
    assert before["context_sha256"] != after["context_sha256"]
    assert before["evidence"]["hits"][0]["chunk_id"] == "source:old"
    assert "source:old" not in handoff.analysis.user_draft
    assert test_binding.all_clients_closed


def test_concurrent_cases_have_independent_requests_clients_and_attempt_ids(ledger):
    test_binding = binding(ledger)
    with offline_network(), ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(run, test_binding, case("case:" + name), run_id="run:" + name)
            for name in ("one", "two")
        ]
        outputs = [future.result() for future in futures]
    assert {handoff.case.case_id for _, handoff in outputs} == {"case:one", "case:two"}
    records = test_binding.records
    assert len(records) == 2 and len({record["request_id"] for record in records}) == 2
    for record in records:
        sent = json.loads(record["provider_payload"]["messages"][1]["content"])
        assert sent["request"]["case"]["case_id"] == record["context"]["case_id"]
        assert record["context"]["attempt_index"] == 1
    assert test_binding.all_clients_closed


def test_invalid_catalog_does_not_send_or_reserve_and_is_cleaned_up(ledger):
    def mismatched(current, message, evidence):
        return make_grounded_request(current, message + " unexpected", evidence)

    test_binding = binding(ledger, request_factory=mismatched)
    with offline_network():
        result, handoff = run(test_binding)
    assert handoff is None and result.error_code == "GroundedContextMismatch"
    assert test_binding.records == [] and ledger.snapshot().settled_usd == 0
    assert test_binding.all_clients_closed


def test_close_is_idempotent_and_prevents_new_resources(ledger):
    test_binding = binding(ledger)
    ports = test_binding.adapters("anything")
    assert not test_binding.all_clients_closed
    ports.cleanup()
    test_binding.close()
    test_binding.close()
    assert test_binding.all_clients_closed
    with pytest.raises(ValueError, match="GroundedBindingClosed"):
        test_binding.adapters("anything")
    assert test_binding.records == []


def test_unknown_fault_configuration_fails_with_safe_diagnostic(ledger):
    with pytest.raises(ValueError, match="InvalidGroundedBindingConfiguration") as caught:
        binding(ledger, fault="private-unrecognized-value")
    assert "private" not in str(caught.value)


def test_exhausted_repair_stops_at_two_attempts_and_closes_clients(ledger):
    test_binding = binding(ledger, fault="malformed_all")
    with offline_network():
        result, handoff = run(test_binding)
    assert handoff is None and result.error_code == "ModelOutputInvalid"
    assert result.model_attempts == len(test_binding.records) == 2
    assert test_binding.snapshot()["settled_reservations"] == 2
    assert test_binding.all_clients_closed


def test_duplicate_attempt_does_not_send_again_or_double_count_settlement(ledger):
    test_binding = binding(ledger)
    with offline_network():
        first, handoff = run(test_binding)
        second, repeated = run(test_binding)
    assert first.status == "awaiting_approval" and handoff is not None
    assert repeated is None and second.error_code == "DuplicateModelRequest"
    assert len(test_binding.records) == 2
    assert test_binding.snapshot()["transport_calls"] == 1
    assert test_binding.snapshot()["settled_reservations"] == 1
    assert ledger.snapshot().settled_usd == Decimal("0.000070125")
    assert test_binding.all_clients_closed


def test_reused_planner_is_rejected_without_closing_other_runs_resource(ledger):
    class ClosablePlanner(CurrentPlanner):
        closed = 0

        def close(self):
            self.closed += 1

    planner = ClosablePlanner()
    test_binding = binding(ledger, planner_factory=lambda: planner)
    ports = test_binding.adapters("first")
    with pytest.raises(ValueError, match="InvalidGroundedBindingConfiguration"):
        test_binding.adapters("second")
    assert planner.closed == 0 and not test_binding.all_clients_closed
    ports.cleanup()
    test_binding.close()
    assert planner.closed == 1 and test_binding.all_clients_closed


def test_gateway_allocation_failure_closes_authored_planner(ledger, monkeypatch):
    from agent_app.testing import grounded_http_binding

    class ClosablePlanner(CurrentPlanner):
        closed = 0

        def close(self):
            self.closed += 1

    planner = ClosablePlanner()
    test_binding = binding(ledger, planner_factory=lambda: planner)

    def allocation_failure(*_args, **_kwargs):
        raise ValueError("Fixture allocation failure")

    monkeypatch.setattr(grounded_http_binding.MetisGroundedPlanner, "__init__", allocation_failure)
    with pytest.raises(ValueError, match="Fixture allocation failure"):
        test_binding.adapters("first")
    assert planner.closed == 1 and test_binding.records == []
    assert test_binding.all_clients_closed


def test_non_recording_launcher_releases_finished_case_resources_without_resetting_ledger(ledger):
    test_binding = binding(ledger, retain_records=False)
    with offline_network():
        for index in range(20):
            result, handoff = run(
                test_binding, case(f"case:release-{index}"), run_id=f"run:release-{index}"
            )
            assert result.status == "awaiting_approval" and handoff is not None
            assert test_binding.records == [] and test_binding.all_clients_closed
            assert test_binding._bridges == test_binding._retrievers == []
    assert ledger.snapshot().settled_usd == 20 * Decimal("0.000070125")
    assert not test_binding.snapshot()["records_retained"]
    test_binding.close()


def test_non_recording_cleanup_failure_releases_actual_closed_gateway_and_propagates(ledger):
    class BrokenCleanupPlanner(CurrentPlanner):
        def close(self):
            raise ValueError("Fixture authored cleanup failed")

    test_binding = binding(ledger, retain_records=False, planner_factory=BrokenCleanupPlanner)
    with offline_network(), pytest.raises(ValueError, match="Fixture authored cleanup failed"):
        run(test_binding)
    assert test_binding.all_clients_closed and test_binding.records == []
    assert test_binding._bridges == test_binding._retrievers == []
    assert ledger.snapshot().settled_usd == Decimal("0.000070125")
    test_binding.close()
