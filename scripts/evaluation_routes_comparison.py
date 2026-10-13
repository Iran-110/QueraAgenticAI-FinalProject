"""Controlled old-runner/new-runner comparison with identical mocked ports.

Only the runner module is replaced for the baseline; current core/shared helper
stay fixed. This is an operational coverage experiment, never a quality score.
"""

import argparse
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import tarfile
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_app.evaluation import runner
from agent_app.testing.http_pilot_runtime import offline_network

ROOT = Path(__file__).resolve().parents[1]
REGISTERED = ROOT / "experiments/evaluation_routes"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compare():
    protocol = json.loads((REGISTERED / "protocol-v1.json").read_text(encoding="utf-8"))
    fixture = REGISTERED / "fixture-v1.json"
    helper = ROOT / "tests/test_eval_conditional_routes.py"
    if (
        digest(fixture) != protocol["fixture_sha256"]
        or digest(helper) != protocol["test_helper_sha256"]
    ):
        raise ValueError("RouteComparisonRegistrationChanged")
    # The same committed development-only mock helper serves both runners.
    # No gold or fixture object is supplied to for_case().
    sys.path.insert(0, str(ROOT / "tests"))
    from test_eval_conditional_routes import MockLive

    source_before = runner._source_hashes()
    wire_cases = []
    with TemporaryDirectory(prefix="registered-runner-comparison-") as temp:
        directory = Path(temp)
        archive_bytes = subprocess.check_output(
            ["git", "archive", protocol["baseline_commit"]], cwd=ROOT
        )
        baseline_root = directory / "baseline"
        baseline_root.mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive_bytes)) as archive:
            archive.extractall(baseline_root, filter="data")
        baseline_path = baseline_root / "src/agent_app/evaluation/runner.py"
        if digest(baseline_path) != protocol["baseline_runner_sha256"]:
            raise ValueError("RouteComparisonBaselineChanged")
        name = "agent_app.evaluation._registered_route_baseline"
        spec = importlib.util.spec_from_file_location(name, baseline_path)
        baseline = importlib.util.module_from_spec(spec)
        sys.modules[name] = baseline
        try:
            spec.loader.exec_module(baseline)
            with offline_network():
                for target in protocol["targets"]:
                    paired = {}
                    for variant, module in (
                        ("baseline_runner", baseline),
                        ("conditional_runner", runner),
                    ):
                        work = directory / target / variant
                        work.mkdir(parents=True)
                        adapters = MockLive(work, target)
                        kwargs = {"conditional_routes": True} if module is runner else {}
                        try:
                            receipt = module.run([fixture], mode="live", live=adapters, **kwargs)
                            steps = receipt["cases"][0]["steps"]
                            visited = [row["turn"] for row in steps if "usage" in row]
                            expected = protocol["acceptable_selected_paths"][target]
                            failed = [
                                {"step": check["step"], "check": check["check"]}
                                for check in receipt["cases"][0]["checks"]
                                if not check["passed"]
                            ]
                            paired[variant] = {
                                "visited_turn_ids": visited,
                                "registered_expected_path": expected,
                                "selected_path_matches": visited == expected,
                                "coverage_complete": receipt["summary"]["coverage_complete"],
                                "fixture_branches_unavailable": receipt["summary"][
                                    "fixture_branches_unavailable"
                                ],
                                "checks": receipt["summary"]["checks"],
                                "failed_checks": failed,
                                "mock_provider_sends": len(adapters.wire),
                                "simulated_settled_usd": receipt["summary"]["settled_usd_total"],
                                "original_receipt_quality_claim": receipt["quality_claim"],
                                "all_allocated_clients_closed": all(
                                    port.client.is_closed for port in adapters.ports
                                ),
                                "controlled_path_pass": visited == expected
                                and receipt["summary"]["coverage_complete"]
                                and not failed,
                            }
                        finally:
                            for port in adapters.ports:
                                port.close()
                    wire_cases.append({"mock_choice": target, **paired})
        finally:
            sys.modules.pop(name, None)
    after = runner._source_hashes()
    if source_before != after:
        raise ValueError("RouteComparisonSourceChanged")
    return {
        "schema_version": 1,
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": digest(REGISTERED / "protocol-v1.json"),
        "fixture_sha256": digest(fixture),
        "test_helper_sha256": digest(helper),
        "baseline_commit": protocol["baseline_commit"],
        "baseline_runner_sha256": protocol["baseline_runner_sha256"],
        "current_commit": runner._git_commit(),
        "current_source_sha256": source_before,
        "source_unchanged_during_run": True,
        "scope": protocol["scope"],
        "quality_claim": False,
        "real_api_calls": 0,
        "paid_cost_usd": "0",
        "case_count_for_final_evaluation": 0,
        "baseline_path_passes": sum(
            row["baseline_runner"]["controlled_path_pass"] for row in wire_cases
        ),
        "conditional_path_passes": sum(
            row["conditional_runner"]["controlled_path_pass"] for row in wire_cases
        ),
        "comparisons": wire_cases,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("RouteComparisonOutputExists")
    result = compare()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "quality_claim",
                    "real_api_calls",
                    "paid_cost_usd",
                    "baseline_path_passes",
                    "conditional_path_passes",
                )
            }
        )
    )


if __name__ == "__main__":
    main()
