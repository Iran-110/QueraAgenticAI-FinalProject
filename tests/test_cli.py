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
