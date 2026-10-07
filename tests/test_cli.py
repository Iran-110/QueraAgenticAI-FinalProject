"""The public demo interface is explicitly synthetic and spends no API credit."""

import json

import pytest

from agent_app.cli import main


@pytest.mark.parametrize(
    ("scenario", "decision", "attempts", "rounds", "exit_code"),
    [
        ("ask", "ask", 1, 1, 0),
        ("answer", "answer", 1, 1, 0),
        ("escalate", "escalate", 1, 1, 0),
        ("refine", "answer", 2, 2, 0),
        ("error", None, 0, 1, 1),
    ],
)
def test_cli_reports_preview_or_controlled_error_with_zero_paid_calls(
    scenario, decision, attempts, rounds, exit_code, capsys
):
    assert main(["demo", "--scenario", scenario]) == exit_code
    output = json.loads(capsys.readouterr().out)
    assert output["mode"] == "synthetic_mock"
    assert output["scenario"] == scenario
    assert output["real_api_calls"] == output["paid_cost_usd"] == output["case_mutations"] == 0
    result = output["result"]
    assert result["model_attempts"] == attempts
    assert result["retrieval_rounds"] == rounds
    if decision is None:
        assert result["status"] == "error"
        assert result["error_code"] == "RetrievalUnavailable"
        assert result["analysis"] is None
    else:
        assert result["status"] == "awaiting_approval"
        assert result["analysis"]["decision"] == decision
        assert result["error_code"] is None


def test_default_demo_is_the_ask_scenario(capsys):
    assert main(["demo"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["scenario"] == "ask"
    assert output["result"]["analysis"]["next_question"]


@pytest.mark.parametrize("args", [[], ["demo", "--scenario", "paid"], ["demo", "--live"]])
def test_cli_rejects_unknown_commands_scenarios_and_provider_flags(args, capsys):
    with pytest.raises(SystemExit) as stopped:
        main(args)
    assert stopped.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "usage:" in captured.err


@pytest.mark.parametrize(
    ("scenario", "sends", "status", "exit_code"),
    [
        ("success", 1, "awaiting_approval", 0),
        ("repair", 2, "awaiting_approval", 0),
        ("timeout", 1, "error", 1),
        ("budget", 0, "budget_stopped", 1),
    ],
)
def test_gateway_cli_exercises_accounting_without_real_requests(
    scenario, sends, status, exit_code, capsys
):
    assert main(["gateway-demo", "--scenario", scenario]) == exit_code
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "synthetic_http"
    assert payload["real_api_calls"] == payload["paid_cost_usd"] == 0
    assert payload["mock_http_requests"] == sends
    assert payload["result"]["status"] == status
    if scenario == "timeout":
        assert payload["simulated_ledger"]["uncertain_usd"] != "0"
    if scenario == "repair":
        assert payload["simulated_usage_cost_usd"] == "0.000297"


def test_budget_cli_preserves_existing_spend_and_refuses_reinitialization(tmp_path, capsys):
    path = str(tmp_path / "runtime" / "budget.sqlite3")
    arguments = [
        "budget",
        "init",
        "--path",
        path,
        "--limit-usd",
        "4.50",
        "--opening-spend-usd",
        "0.75",
    ]
    assert main(arguments) == 0
    initial = json.loads(capsys.readouterr().out)
    assert initial["available_usd"] == "3.75"
    assert main(arguments) == 1
    assert json.loads(capsys.readouterr().out)["error"] == "BudgetLedgerOperationFailed"
    assert main(["budget", "status", "--path", path]) == 0
    assert json.loads(capsys.readouterr().out) == initial


def test_reading_a_missing_budget_does_not_create_one(tmp_path, capsys):
    path = tmp_path / "budget.sqlite3"
    assert main(["budget", "status", "--path", str(path)]) == 1
    assert json.loads(capsys.readouterr().out)["error"] == "BudgetLedgerOperationFailed"
    assert not path.exists()
