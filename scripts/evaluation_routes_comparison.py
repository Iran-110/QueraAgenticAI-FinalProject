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

from agent_app.contracts import ConversationEntry, TurnConversation
from agent_app.evaluation import runner
from agent_app.orchestration.conversation import build_reasoning_message
from agent_app.orchestration.intake import STREAMLIT_VERSION_QUESTION
from agent_app.testing.http_pilot_runtime import offline_network

ROOT = Path(__file__).resolve().parents[1]
REGISTERED = ROOT / "experiments/evaluation_routes"
SCRIPT = Path(__file__).resolve()
PRIVATE_GOLD = "GOLD_NOT_A_MODEL_INPUT"
FUTURE_MARKERS = {
    "callback": "FUTURE_CALLBACK_RESPONSE",
    "correction": "FUTURE_CORRECTION_MARKER",
    "version": "1.50.0",
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def registration(protocol_path=None):
    """Capture the exact bytes parsed and require the registered script pin."""
    protocol_path = protocol_path or REGISTERED / "protocol-v3.json"
    raw = protocol_path.read_bytes()
    protocol = json.loads(raw)
    fixture = REGISTERED / "fixture-v1.json"
    paths = {
        "protocol": protocol_path,
        "fixture": fixture,
        "test_helper": ROOT / "tests/test_eval_conditional_routes.py",
        "comparison_script": SCRIPT,
    }
    pins = {name: digest(path) for name, path in paths.items()}
    try:
        valid = (
            pins["protocol"] == hashlib.sha256(raw).hexdigest()
            and pins["fixture"] == protocol["fixture_sha256"]
            and pins["test_helper"] == protocol["test_helper_sha256"]
            and pins["comparison_script"] == protocol["script_sha256"]
        )
    except KeyError:
        valid = False
    if not valid:
        raise ValueError("RouteComparisonRegistrationChanged")
    state = {
        "protocol": protocol,
        "fixture": json.loads(fixture.read_bytes()),
        "paths": paths,
        "pins": pins,
        "source_pins": runner._source_hashes(),
    }
    check_registration(state)
    return state


def check_registration(state):
    """Refuse input or source drift before another runner is allowed to run."""
    if {name: digest(path) for name, path in state["paths"].items()} != state["pins"]:
        raise ValueError("RouteComparisonRegistrationChanged")
    if runner._source_hashes() != state["source_pins"]:
        raise ValueError("RouteComparisonSourceChanged")


def registered_message(submitted, position, turns, selected_path):
    """Compose only the registered user inputs actually submitted by this step.

    This uses the same current conversation contract as the API. The input is
    reconstructed from registered visible turns, not copied from the prompt or
    handoff. Only a released, bound canonical question can supply an assistant
    entry. The exact current message and complete prior user text are preserved.
    """
    entries = []
    for prior, contexts in submitted[: position + 1]:
        identifier = prior["turn"]
        if identifier not in selected_path:
            raise ValueError("UnselectedSubmittedTurn")
        visible = turns[identifier]["visible"]
        request = prior["request"]
        identities = {(context["case_id"], context["case_revision"]) for context in contexts}
        if (
            len(identities) != 1
            or request["message"] != visible["message"]
            or request.get("turn_id", identifier) != identifier
            or bool(request.get("reply_to_proposal_id"))
            != bool(visible.get("reply_to_approved_question"))
        ):
            raise ValueError("SubmittedTurnMismatch")
        _, revision = next(iter(identities))
        # Earlier approved questions are omitted because the composer does not
        # include them unless the latest committed input is their bound reply.
        if prior is submitted[position][0] and request.get("reply_to_proposal_id"):
            previous = submitted[position - 1][0] if position else {}
            proposal_id = request["reply_to_proposal_id"]
            if not (
                previous.get("proposal", {}).get("proposal_id") == proposal_id
                and any(
                    released.get("text") == STREAMLIT_VERSION_QUESTION.question
                    for released in previous.get("released_outputs", [])
                )
            ):
                raise ValueError("UnboundApprovedQuestion")
            entries.append(
                ConversationEntry(
                    actor="assistant",
                    reference_id=proposal_id,
                    revision=revision - 1,
                    text=STREAMLIT_VERSION_QUESTION.question,
                )
            )
        entries.append(
            ConversationEntry(
                actor="user", reference_id=identifier, revision=revision, text=visible["message"]
            )
        )
    latest = entries[-1]
    return build_reasoning_message(
        TurnConversation(
            entries=tuple(entries),
            latest_turn_id=latest.reference_id,
            committed_revision=latest.revision,
            latest_message=latest.text,
            reply_to_proposal_id=submitted[position][0]["request"].get("reply_to_proposal_id"),
        )
    )


def wire_audit(wires, steps, fixture, selected_path):
    """Audit each captured prompt against inputs actually submitted by then.

    The registered selected path is the allowed branch. A legacy runner feeding
    another branch therefore fails this control, even if that text was sent as
    a real event. Only safe booleans, marker names and indices leave this helper.
    """
    turns = {turn["id"]: turn for turn in fixture["turns"]}
    submitted = []
    expected_send_positions = []
    for step in steps:
        if "usage" in step:
            contexts = [row["context"] for row in step["usage"]["requests"]]
            # In this registered MockLive helper each settled request is one
            # captured MockTransport send, including malformed-output repairs.
            # This is not a general claim about live/uncertain HTTP accounting.
            expected_send_positions.extend(
                len(submitted)
                for row in step["usage"]["requests"]
                if row.get("status") == "settled"
            )
            submitted.append((step, contexts))
    checks = []
    for index, wire in enumerate(wires):
        serialized = json.dumps(wire, ensure_ascii=False)
        matched, handoff_matched, registered_matched, send_order_matched = (
            False,
            False,
            False,
            False,
        )
        metadata_absent, forbidden = False, []
        try:
            payload = json.loads(wire["messages"][-1]["content"])
            prompt_case = payload["case"]
            # Retrieved version metadata can legitimately mention the same
            # number before a user replies. Only user-state payload fields are
            # audited as future-turn leakage; private gold checks the full wire.
            user_state = json.dumps(
                {
                    name: payload[name]
                    for name in (
                        "case",
                        "user_message",
                        "conversation",
                        "conversation_history",
                        "history",
                    )
                    if name in payload
                },
                ensure_ascii=False,
            )
            forbidden = [name for name, marker in FUTURE_MARKERS.items() if marker in user_state]
            identities = [
                position
                for position, (_, contexts) in enumerate(submitted)
                if any(
                    context["case_id"] == prompt_case["case_id"]
                    and context["case_revision"] == prompt_case["case_revision"]
                    for context in contexts
                )
            ]
            if len(identities) == 1:
                position = identities[0]
                send_order_matched = (
                    index < len(expected_send_positions)
                    and expected_send_positions[index] == position
                )
                step = submitted[position][0]
                identifier = step["turn"]
                handoff = step.get("proposal", {}).get("review_handoff", {})
                handoff_matched = payload["user_message"] == handoff.get(
                    "user_message"
                ) and prompt_case == handoff.get("case")
                if identifier in selected_path:
                    registered_matched = payload["user_message"] == registered_message(
                        submitted, position, turns, selected_path
                    )
                matched = (
                    identifier in selected_path
                    and handoff_matched
                    and registered_matched
                    and send_order_matched
                )
                available = json.dumps(
                    [
                        turns[prior["turn"]]["visible"]
                        for prior, _ in submitted[: position + 1]
                        if prior["turn"] in selected_path
                    ],
                    ensure_ascii=False,
                )
                forbidden = [
                    name
                    for name, marker in FUTURE_MARKERS.items()
                    if marker in user_state and marker not in available
                ]
            metadata_absent = not {
                "gold",
                "evaluation",
                "routes",
                "agent_script",
                "expect",
            }.intersection(payload)
        except (KeyError, TypeError, ValueError, IndexError):
            pass  # A malformed/unattributed captured prompt is a failed audit.
        checks.append(
            {
                "prompt_index": index + 1,
                "matches_submitted_selected_turn": matched,
                "matches_same_step_handoff": handoff_matched,
                "matches_registered_accumulated_message": registered_matched,
                "matches_captured_send_order": send_order_matched,
                "private_gold_absent": PRIVATE_GOLD not in serialized,
                "fixture_metadata_absent": metadata_absent,
                "unavailable_markers_absent": not forbidden,
                "unavailable_marker_names": forbidden,
            }
        )
    count_matched = len(wires) == len(expected_send_positions)
    passed = (
        bool(checks)
        and count_matched
        and all(
            row["matches_submitted_selected_turn"]
            and row["private_gold_absent"]
            and row["fixture_metadata_absent"]
            and row["unavailable_markers_absent"]
            for row in checks
        )
    )
    return {
        "scope": "Gold marker in entire wire; future markers in case/user message/history only, "
        "excluding retrieved evidence/version metadata. Prompt case/message must match its "
        "same-step handoff and conversation composed only from already-submitted registered "
        "selected inputs. Not general semantic leakage detection.",
        "captured_prompts": len(checks),
        "settled_mock_requests_match_capture_count": count_matched,
        "all_passed": passed,
        "checks": checks,
    }


def compare(protocol_path=None):
    state = registration(protocol_path)
    protocol = state["protocol"]
    fixture = state["paths"]["fixture"]
    # The same committed development-only mock helper serves both runners.
    # No gold or fixture object is supplied to for_case().
    sys.path.insert(0, str(ROOT / "tests"))
    from test_eval_conditional_routes import MockLive

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
                    check_registration(state)
                    paired = {}
                    for variant, module in (
                        ("baseline_runner", baseline),
                        ("conditional_runner", runner),
                    ):
                        check_registration(state)
                        work = directory / target / variant
                        work.mkdir(parents=True)
                        adapters = MockLive(work, target)
                        kwargs = {"conditional_routes": True} if module is runner else {}
                        try:
                            receipt = module.run([fixture], mode="live", live=adapters, **kwargs)
                            steps = receipt["cases"][0]["steps"]
                            visited = [row["turn"] for row in steps if "usage" in row]
                            expected = protocol["acceptable_selected_paths"][target]
                            audit = wire_audit(adapters.wire, steps, state["fixture"], expected)
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
                                "wire_privacy_audit": audit,
                                "simulated_settled_usd": receipt["summary"]["settled_usd_total"],
                                "original_receipt_quality_claim": receipt["quality_claim"],
                                "all_allocated_clients_closed": all(
                                    port.client.is_closed for port in adapters.ports
                                ),
                                "controlled_path_pass": visited == expected
                                and receipt["summary"]["coverage_complete"]
                                and not failed
                                and audit["all_passed"],
                            }
                        finally:
                            for port in adapters.ports:
                                port.close()
                    wire_cases.append({"mock_choice": target, **paired})
        finally:
            sys.modules.pop(name, None)
    check_registration(state)
    return {
        "schema_version": 2,
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": state["pins"]["protocol"],
        "fixture_sha256": state["pins"]["fixture"],
        "test_helper_sha256": state["pins"]["test_helper"],
        "script_sha256": state["pins"]["comparison_script"],
        "initial_input_sha256": state["pins"],
        "registered_inputs_unchanged_during_run": True,
        "baseline_commit": protocol["baseline_commit"],
        "baseline_runner_sha256": protocol["baseline_runner_sha256"],
        "current_commit": runner._git_commit(),
        "current_source_sha256": state["source_pins"],
        "source_unchanged_during_run": True,
        "scope": protocol["scope"],
        "quality_claim": False,
        "real_api_calls": 0,
        "paid_cost_usd": "0",
        "case_count_for_final_evaluation": 0,
        "wire_privacy_measured": True,
        "baseline_path_passes": sum(
            row["baseline_runner"]["controlled_path_pass"] for row in wire_cases
        ),
        "conditional_path_passes": sum(
            row["conditional_runner"]["controlled_path_pass"] for row in wire_cases
        ),
        "comparisons": wire_cases,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, default=REGISTERED / "protocol-v3.json")
    args = parser.parse_args(argv)
    if args.output.exists():
        raise ValueError("RouteComparisonOutputExists")
    result = compare(args.protocol)
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
