"""Full authored gateway wire composes with durable review, never a live model."""

import json
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from agent_app.llm.budget import BudgetLedger
from agent_app.llm.config import MetisConfig
from agent_app.testing import grounded_http_acceptance as acceptance

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def receipts(tmp_path_factory):
    return {
        name: acceptance.run(
            ROOT, tmp_path_factory.mktemp(f"grounded-{name}"), baseline=name == "baseline"
        )
        for name in ("baseline", "current")
    }


def test_same_registered_inputs_preserve_baseline_functions_and_expose_only_label_lifecycle(
    receipts,
):
    baseline, current = (receipts[name] for name in ("baseline", "current"))
    assert baseline["summary"]["checks_passed"] == 10
    assert current["summary"]["checks_passed"] == current["summary"]["checks_total"] == 12
    assert {name for name, passed in baseline["checks"].items() if not passed} == {
        "truthful_reasoning_label",
        "per_run_gateway_clients_closed_before_failsafe_cleanup",
    }
    assert (
        baseline["baseline_module_sha256"]["src/agent_app/persistent_api.py"]
        != current["source_hashes"]["src/agent_app/persistent_api.py"]
    )
    for receipt in receipts.values():
        assert receipt["primary"]["gateway_calls"] == receipt["primary"]["retrieval_calls"] == 5
        assert receipt["primary"]["actions"] == 2
        assert receipt["summary"]["actual_API_cost_USD"] == "0"
        assert receipt["summary"]["quality_claim"] is False


def test_persistent_history_and_final_sources_bind_actual_provider_request(receipts):
    primary = receipts["current"]["primary"]
    turns = primary["turns"]
    assert [item["handoff"]["case"]["case_revision"] for item in turns] == [1, 2, 3, 4]
    assert [item["handoff"]["analysis"]["decision"] for item in turns] == [
        "ask",
        "answer",
        "escalate",
        "ask",
    ]
    corrected = turns[2]["handoff"]
    assert corrected["user_message"].endswith(
        "The reduced example still works; the parent callback is not supplied."
    )
    assert "1.50.0" in corrected["user_message"]
    assert len(corrected["evidence"]["hits"]) == 4
    assert "release-150-multiselect-key-identity-v8" not in {
        hit["chunk_id"] for hit in corrected["evidence"]["hits"]
    }
    sent = json.loads(primary["provider_attempts"][3]["provider_payload"]["messages"][1]["content"])
    assert sent["request"] == corrected["grounded_request"]
    assert corrected["evidence"] == sent["request"]["evidence"]


def test_repairs_conflicts_and_terminal_gateway_uncertainty_never_create_actions(receipts):
    controls = {control["control_id"]: control for control in receipts["current"]["controls"]}
    assert controls["malformed_first"]["accounting"]["settled_reservations"] == 2
    for name in ("model_mismatch", "timeout"):
        assert controls[name]["pending"] is None
        assert controls[name]["accounting"]["transport_calls"] == 1
        assert controls[name]["accounting"]["uncertain_reservations"] == 1
    conflict = controls["caller_declared_conflict"]["pending"]
    assert conflict["decision"] == "escalate"
    assert len(conflict["analysis"]["evidence_links"]) == 2


def test_live_transport_environment_config_and_real_ledger_are_unavailable(tmp_path, monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Live I/O is forbidden")

    original = BudgetLedger.create
    created = []

    def isolated(path, *args, **kwargs):
        assert Path(path).parent == tmp_path
        created.append(Path(path))
        return original(path, *args, **kwargs)

    monkeypatch.setattr(httpx.HTTPTransport, "__init__", forbidden)
    monkeypatch.setattr(MetisConfig, "from_env", forbidden)
    monkeypatch.setattr(BudgetLedger, "create", isolated)
    assert acceptance.run(ROOT, tmp_path)["summary"]["checks_passed"] == 12
    assert len(created) == 5


def test_protocol_drift_state_reuse_and_exclusive_receipt_fail_closed(tmp_path, receipts):
    protocol = acceptance.load_protocol(ROOT)
    protocol["expected_current"]["primary_gateway_calls"] = 99
    path = tmp_path / "drift.json"
    path.write_text(json.dumps(protocol))
    with pytest.raises(ValueError, match="RegisteredGroundedHttpProtocolMismatch"):
        acceptance.run(ROOT, tmp_path / "new", protocol_path=path)
    state = tmp_path / "used"
    state.mkdir()
    (state / "occupied").touch()
    with pytest.raises(ValueError, match="GroundedHttpFreshStateRequired"):
        acceptance.run(ROOT, state)
    output = tmp_path / "receipt.json"
    acceptance.write_receipt(output, receipts["current"])
    original = output.read_bytes()
    with pytest.raises(FileExistsError):
        acceptance.write_receipt(output, {})
    assert output.read_bytes() == original


def test_disabled_assertions_never_write_success_receipt(tmp_path):
    output = tmp_path / "disabled.json"
    process = subprocess.run(
        [
            sys.executable,
            "-O",
            str(ROOT / "scripts/grounded_http_acceptance.py"),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == 2
    assert json.loads(process.stdout) == {"error_code": "AssertionChecksDisabled"}
    assert not output.exists()


def test_runtime_code_change_cannot_receive_success_receipt(tmp_path, monkeypatch):
    original, calls = acceptance.code_manifest, 0

    def changed(root):
        nonlocal calls
        calls += 1
        result = original(root)
        if calls > 1:
            result["src/agent_app/llm/metis.py"] = "0" * 64
        return result

    monkeypatch.setattr(acceptance, "code_manifest", changed)
    with pytest.raises(RuntimeError, match="GroundedHttpCodeChangedDuringReplay"):
        acceptance.run(ROOT, tmp_path)


def test_same_json_and_citation_ids_with_incomplete_source_quote_cannot_pass(tmp_path, monkeypatch):
    from agent_app.reasoning import grounding

    original = grounding.render_grounded_plan

    def altered(request, raw):
        analysis = original(request, raw)
        if analysis.decision == "answer":
            return analysis.model_copy(update={"user_draft": "The issue is definitely fixed."})
        return analysis

    monkeypatch.setattr(grounding, "render_grounded_plan", altered)
    with pytest.raises(AssertionError, match="GroundedHttpCompleteAnalysisMismatch"):
        acceptance.run(ROOT, tmp_path)


def test_wire_substitution_cannot_receive_success_receipt(tmp_path, monkeypatch):
    from agent_app.llm import metis

    original = metis.build_grounded_messages

    def substituted(request, context):
        messages = list(original(request, context))
        data = json.loads(messages[1]["content"])
        data["request"]["user_message"] += " Uncommitted wire substitution."
        messages[1] = {**messages[1], "content": json.dumps(data)}
        return messages

    monkeypatch.setattr(metis, "build_grounded_messages", substituted)
    with pytest.raises(AssertionError, match="GroundedHttpFinalProposalMissing"):
        acceptance.run(ROOT, tmp_path)
