"""Prepare/read-only check first; --live consumes one frozen finite experiment."""

import argparse
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

from core_ask_background_model_probe import payload_preflight

# Share the closed campaign's read-only journal/identity controls; no old scope
# or method is resumed. These helpers accept the exact fresh identities below.
from core_repeat_model_probe import (
    close_owned_scope,
    ledger_journal_snapshot,
    validate_fresh_identities,
    validate_ledger_journal,
)
from core_stability_probe import credential, write_new
from dev_rag_model_probe import (
    batch_complete,
    source_matches,
)
from dev_rag_model_probe import (
    build_method as coverage_build_method,
)
from dev_rag_model_probe import (
    validate_registered_indexes as validate_coverage_indexes,
)

from agent_app.contracts import ReasoningContext
from agent_app.llm.budget import BudgetLedger, LedgerConflict
from agent_app.llm.config import MetisConfig
from agent_app.llm.metis import request_id_for
from agent_app.llm.pricing import get_price
from agent_app.reasoning.catalog import load_user_gap_vocabulary
from agent_app.testing.dev_three_model_probe import ledger_observation, sha
from agent_app.testing.quality_probe import quality_slots
from agent_app.testing.real_index_probe import run_real_index_batch, validate_index_bindings
from agent_app.testing.stability_probe import (
    VOCABULARY,
    fixtures_for,
    slots_sha256,
    source_observation,
)

ROOT = Path(__file__).resolve().parents[1]
COVERAGE_FOLDER = Path("experiments/dev_rag_coverage_v1")
FOLDER = Path("experiments/core_json_readability_v1")
PARENT_FOLDER = Path("experiments/core_ask_background_v1")
PROTOCOL_SHA256 = "9d4f1a61c3fcb0ff012a37546262b4172803aaff966e585c8c33ed0645d07060"
METHOD = FOLDER / "live-method-v1.json"


def registered_protocol(root):
    """Use the exact prospectively committed protocol; no implicit schema upgrades."""
    raw = (root / FOLDER / "protocol-v1.json").read_bytes()
    if sha(raw) != PROTOCOL_SHA256:
        raise ValueError("JsonReadabilityRegistrationRejected")
    value = json.loads(raw)
    if (
        type(value["schema_version"]) is not int
        or value["schema_version"] != 1
        or value["protocol_id"] != "core-json-readability-v1"
        or value["registered_before_implementation"] is not True
        or value["registered_before_paid_calls"] is not True
    ):
        raise ValueError("JsonReadabilityRegistrationRejected")
    return value


def build_method(root, ledger_path):
    """Freeze the canary and all six balanced pairs before the first request."""
    protocol = registered_protocol(root)
    planned = protocol["live"]
    parent_path = root / PARENT_FOLDER / "model-live-receipt-v1.json"
    if sha(parent_path.read_bytes()) != protocol["offline"]["receipt_sha256"]:
        raise ValueError("JsonReadabilityRegistrationRejected")
    prior = coverage_build_method(root, ledger_path)
    method = {
        **prior,
        "protocol_id": planned["protocol_id"],
        "experiment_id": planned["experiment_id"],
        "authorization_ref": protocol["authorization_ref"],
        "baseline_main_commit": protocol["baseline_commit"],
        "baseline_model_receipt": parent_path.relative_to(root).as_posix(),
        "treatment_protocol": protocol,
        "offline_payload_preflight": payload_preflight(root),
        "scope_cap_usd": planned["paired_scope_cap_usd"],
        "canary_scope_cap_usd": planned["canary"]["scope_cap_usd"],
        "campaign_scope_cap_usd": planned["campaign_cap_usd"],
        "canary_batch_id": planned["canary"]["batch_id"],
        "renderer_ask_source_background": True,
        "renderer_concise_user_draft": True,
        "no_model_prompt_treatment": True,
        "named_profile_through_http": True,
        "json_object_transport_comparison": True,
        "resource_guidance": False,
    }
    pins = method["input_pins"]
    for name in (
        (FOLDER / "protocol-v1.json").as_posix(),
        (FOLDER / "offline-render-replay-v1.json").as_posix(),
        (FOLDER / "semantic-review-preparation-v1.json").as_posix(),
        (PARENT_FOLDER / "protocol-v1.json").as_posix(),
        (PARENT_FOLDER / "model-live-receipt-v1.json").as_posix(),
        (PARENT_FOLDER / "route-display-amendment-v1.json").as_posix(),
        (PARENT_FOLDER / "semantic-review-preparation-v1.json").as_posix(),
        "experiments/retrieval_relevance_v1/semantic-review-preparation-v1.json",
        "experiments/dev_rag_coverage_v1/model-live-receipt-v1.json",
        "experiments/core_resource_guidance_v1/model-live-receipt-v1.json",
        "experiments/core_repeat_repair_v1/model-live-receipt-v1.json",
        "experiments/core_source_capacity_v1/model-live-receipt-v1.json",
        "docs/pr55-evidence-review.fa.md",
        "scripts/core_json_readability_probe.py",
        "scripts/json_readability_render_replay.py",
        "scripts/core_ask_background_model_probe.py",
        "scripts/retrieval_relevance_model_probe.py",
        "scripts/core_repeat_model_probe.py",
        "scripts/core_compact_model_probe.py",
        "scripts/core_source_capacity_model_probe.py",
    ):
        pins[name] = sha((root / name).read_bytes())
    arms = [planned["canary"]["arm"], *planned["paired_arms"]]
    binding = prior["indexes"]["new_18_sources"]
    method["indexes"] = {arm: dict(binding) for arm in arms}
    method["retrieval_scope"] = {
        **prior["retrieval_scope"],
        "same_index_as_R4c_treatment": True,
        "ranking_backfill_added": True,
        "named_profile": "candidate_relevance_v1",
        "retrieval_candidate_multiplier": 5,
        "evidence_utf8_budget_bytes": 12000,
        "record_actual_native_candidates": True,
    }
    method["batches"] = []
    method["ledger_journal_before"] = ledger_journal_snapshot(ledger_path)
    fixtures = fixtures_for(root, {"protocol_id": "core-stability-v1"})

    def job(case_id, arm, round_number):
        return {
            "job_id": f"r{round_number}:{case_id}:{arm}",
            "case_id": case_id,
            "arm": arm,
            "round": round_number,
            "decision_contracts": True,
            "source_selection_reminder": True,
            "ask_source_background": True,
            "concise_user_draft": True,
            "grounded_json_object": arm != "json_object_off",
            "repair_repeated_queries": True,
            "source_capacity": False,
            "compact_plan": True,
            "retrieval_candidate_multiplier": 5,
            "record_native_candidates": True,
            "evidence_utf8_budget_bytes": 12000,
            "retrieval_selection_policy": "query_relevance_v1",
            "retrieval_profile": "candidate_relevance_v1",
            "resource_guidance": False,
            "max_output_tokens": 1024,
            "input_token_reserve": 32768,
        }

    definitions = [
        (
            planned["canary"]["batch_id"],
            "canary",
            planned["canary"]["scope_cap_usd"],
            [job(planned["canary"]["case_id"], planned["canary"]["arm"], 0)],
        )
    ]
    pair_index = 0
    for round_number, order in enumerate(planned["case_order"], start=1):
        for case_id in order:
            definitions.append(
                (
                    f"json-readability-r{round_number}-{case_id}",
                    "paired",
                    planned["paired_scope_cap_usd"],
                    [
                        job(case_id, arm, round_number)
                        for arm in planned["paired_arm_order"][pair_index]
                    ],
                )
            )
            pair_index += 1
    ids = []
    for name, stage, cap, jobs in definitions:
        batch = {
            "batch_id": name,
            "stage": stage,
            "kind": "real_index",
            "scope_id": "user-core-json-readability-v1-" + name,
            "scope_cap_usd": cap,
            "jobs": jobs,
        }
        slots = quality_slots(method, batch, fixtures)
        total = sum(slot.amount_usd for slot in slots)
        if len(slots) != 4 * len(jobs) or total > Decimal(cap):
            raise ValueError("JsonReadabilityRegistrationRejected")
        batch["request_slots_sha256"] = slots_sha256(slots)
        batch["max_request_slots"] = len(slots)
        batch["worst_reserved_usd"] = str(total)
        ids.extend(slot.request_id for slot in slots)
        method["batches"].append(batch)
    if (
        len(ids) != 52
        or len(set(ids)) != 52
        or len(method["batches"]) != 7
        or sum(len(b["jobs"]) for b in method["batches"]) != 13
        or sum(Decimal(b["scope_cap_usd"]) for b in method["batches"]) != Decimal("0.39")
        or sum(Decimal(b["worst_reserved_usd"]) for b in method["batches"]) > Decimal("0.39")
    ):
        raise ValueError("JsonReadabilityRegistrationRejected")
    method["fresh_request_ids"] = ids
    method["fresh_scope_ids"] = [batch["scope_id"] for batch in method["batches"]]
    validate_fresh_identities(ledger_path, set(ids), set(method["fresh_scope_ids"]))
    validate_registered_indexes(root, method["indexes"])
    return json.loads(json.dumps(method, default=str))


def canary_gate(result):
    """Observe transport/schema/accounting only; no success or support is inferred."""
    try:
        sends, attempts, jobs = result["provider_sends"], result["attempts"], result["jobs"]
        request_ids = {item["request_id"] for item in sends}
        accounting = result["accounting"]
        wire = (
            1 <= len(sends) <= 4
            and len(request_ids) == len(sends) == result["actual_sends"]
            and all(
                item.get("http_send_started") is True
                and item.get("wire_response_format") == "json_object"
                and item.get("http_status") == 200
                and item.get("finish_reason") == "stop"
                and item.get("verified_returned_model") == "gpt-4o-mini-2024-07-18"
                for item in sends
            )
        )
        attempt_ids = [
            request_id_for(ReasoningContext.model_validate(item["context"])) for item in attempts
        ]
        schema = (
            len(attempts) == len(sends)
            and len(set(attempt_ids)) == len(attempt_ids)
            and set(attempt_ids) == request_ids
            and {item.get("wire_output", {}).get("request_id") for item in attempts} == request_ids
            and all(
                item.get("error_code") is None
                and item.get("plan") is not None
                and item.get("wire_output", {}).get("wire_schema_valid") is True
                and item.get("wire_output", {}).get("canonical_binding_valid") is True
                and item.get("wire_output", {}).get("request_id") == request_id
                for item, request_id in zip(attempts, attempt_ids, strict=True)
            )
        )
        known_cost = (
            accounting["accounting_complete"] is True
            and accounting["cost_usd"] is not None
            and 0 <= Decimal(accounting["cost_usd"]) <= Decimal("0.03")
            and sum(Decimal(item["cost_usd"]) for item in accounting["requests"])
            == Decimal(accounting["cost_usd"])
            and {item["request_id"] for item in accounting["requests"]} == request_ids
            and all(
                item["status"] == "settled" and item["cost_usd"] is not None
                for item in accounting["requests"]
            )
        )
        fresh_turns = []
        if len(jobs) == 1:
            for step in jobs[0]["steps"]:
                if "request" not in step:
                    continue
                proposal = step.get("proposal")
                fresh_turns.append(
                    type(proposal) is dict
                    and proposal.get("stale") is False
                    and proposal.get("review_handoff") is not None
                    and proposal["case_revision"] == step["request"]["expected_revision"] + 1
                )
        route = (
            batch_complete(result)
            and result["planned_jobs"] == 1
            and result["completed_routes"] == 1
            and fresh_turns == [True, True]
        )
        checks = {
            "wire_argument_and_provider_envelope": wire,
            "raw_schema_and_canonical_binding": schema,
            "known_complete_accounting": known_cost,
            "fresh_complete_two_turn_route": route,
        }
        return {"passed": all(checks.values()), "checks": checks, "semantic_quality_claim": False}
    except (TypeError, KeyError, ValueError, AttributeError, ArithmeticError):
        return {
            "passed": False,
            "checks": {"safe_observation_shape": False},
            "semantic_quality_claim": False,
        }


def wire_arguments_match(batch, result):
    """Every real send retains the registered ON/OFF transport value."""
    try:
        sends = result["provider_sends"]
        if not sends:
            return result["actual_sends"] == 0
        jobs = {run: job for job in result["jobs"] for run in job["run_ids"]}
        contexts = {
            request_id_for(ReasoningContext.model_validate(item["context"])): item["context"]
            for item in result["attempts"]
        }
        expected_jobs = {job["job_id"]: job for job in batch["jobs"]}
        for item in sends:
            context = contexts[item["request_id"]]
            observed_job = jobs[context["run_id"]]
            registered_job = expected_jobs[observed_job["job_id"]]
            expected = "json_object" if registered_job["grounded_json_object"] else "absent"
            if item.get("wire_response_format") != expected:
                return False
        return len(sends) == result["actual_sends"] and len(
            {item["request_id"] for item in sends}
        ) == len(sends)
    except (TypeError, KeyError, ValueError, AttributeError, ArithmeticError):
        return False


def validate_registered_indexes(root, indexes):
    """The one paid arm must use the frozen R4c native18/36 binding."""
    try:
        if type(indexes) is not dict or set(indexes) != {
            "json_object_canary",
            "json_object_off",
            "json_object_on",
        }:
            raise ValueError
        receipt = json.loads((root / COVERAGE_FOLDER / "index-receipt-v1.json").read_bytes())
        coverage = {
            arm: receipt["indexes"][arm] for arm in ("historical_14_sources", "new_18_sources")
        }
        checked = validate_coverage_indexes(root, coverage)
        expected = checked["new_18_sources"]
        if any(binding != expected for binding in indexes.values()):
            raise ValueError
        return validate_index_bindings(indexes)
    except Exception:
        raise ValueError("JsonReadabilityRegistrationRejected") from None


def preflight(root, ledger_path, method_path):
    method = json.loads(method_path.read_bytes())
    if method != build_method(root, ledger_path):
        raise ValueError("JsonReadabilityRegistrationRejected")
    observation = method["ledger_before"]
    if (
        not observation["halted"]
        or observation["counts"].get("reserved", 0)
        or observation["counts"].get("uncertain", 0) != 2
        or observation["limit_nanos"] != 4_500_000_000
    ):
        raise ValueError("JsonReadabilityRegistrationRejected")
    for name, digest in method["input_pins"].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or sha(path.read_bytes()) != digest:
            raise ValueError("JsonReadabilityRegistrationRejected")
    source = source_observation(root, method_path.relative_to(root), method["input_pins"])
    if not source["source_clean"]:
        raise ValueError("JsonReadabilityRegistrationRejected")
    validate_registered_indexes(root, method["indexes"])
    return method, {
        **source,
        "method_sha256": sha(method_path.read_bytes()),
        "quarantine_before": method["quarantine_before"],
        "ledger_before": observation,
        "ledger_journal_before": method["ledger_journal_before"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--method", type=Path, default=ROOT / METHOD)
    parser.add_argument("--ledger", type=Path, default=ROOT / "runtime/budget.sqlite3")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    destination, secret, ledger, active = None, None, None, None
    active_digest, active_ref = None, None
    batches, registration = [], None
    canary_status = {"passed": False, "observed": False}
    try:
        if args.ledger.resolve() != (ROOT / "runtime/budget.sqlite3").resolve():
            raise ValueError("JsonReadabilityLedgerPathRejected")
        if args.method.resolve() != (ROOT / METHOD).resolve():
            raise ValueError("JsonReadabilityMethodPathRejected")
        if args.prepare:
            if args.live:
                raise ValueError("JsonReadabilityRegistrationRejected")
            write_new(
                args.method,
                build_method(ROOT, args.ledger),
            )
            print(json.dumps({"prepared": True, "actual_sends": 0}))
            return 0
        method, registration = preflight(ROOT, args.ledger, args.method)
        if not args.live:
            print(
                json.dumps(
                    {
                        "eligible_read_only": True,
                        "batches": len(method["batches"]),
                        "max_sends": sum(b["max_request_slots"] for b in method["batches"]),
                        "cap_usd": str(
                            sum(Decimal(b.get("scope_cap_usd", "0.06")) for b in method["batches"])
                        ),
                        "actual_sends": 0,
                        "c5_reconciled": False,
                    }
                )
            )
            return 0
        if args.env_file is None or args.output_dir is None:
            raise ValueError("JsonReadabilityRegistrationRejected")
        candidate = args.output_dir.resolve()
        if candidate.is_relative_to(ROOT):
            raise ValueError("JsonReadabilityPrivateOutputRequired")
        candidate.mkdir(parents=True, exist_ok=False, mode=0o700)
        destination = candidate
        write_new(destination / "registration.json", registration)
        if (
            not source_matches(
                registration,
                source_observation(ROOT, args.method.relative_to(ROOT), method["input_pins"]),
            )
            or ledger_observation(args.ledger) != method["ledger_before"]
        ):
            raise ValueError("JsonReadabilityRegistrationRejected")
        validate_registered_indexes(ROOT, method["indexes"])
        validate_ledger_journal(
            args.ledger,
            method["ledger_journal_before"],
            set(method["fresh_request_ids"]),
            set(method["fresh_scope_ids"]),
        )
        validate_fresh_identities(
            args.ledger, set(method["fresh_request_ids"]), set(method["fresh_scope_ids"])
        )
        secret = credential(args.env_file)
        ledger = BudgetLedger(args.ledger)
        fixtures = fixtures_for(ROOT, {"protocol_id": "core-stability-v1"})
        definitions = load_user_gap_vocabulary(str(ROOT / VOCABULARY))
        if ledger_observation(args.ledger) != method["ledger_before"]:
            raise ValueError("JsonReadabilityRegistrationRejected")
        for batch in method["batches"]:
            if batch.get("stage") == "paired" and not canary_status["passed"]:
                break
            if not source_matches(
                registration,
                source_observation(ROOT, args.method.relative_to(ROOT), method["input_pins"]),
            ):
                raise ValueError("JsonReadabilityRegistrationRejected")
            # Prior finite scopes can close, but no new uncertainty/history is silently accepted.
            observed = json.loads(json.dumps(asdict(ledger.quarantine_observation()), default=str))
            if observed != method["quarantine_before"]:
                break
            validate_registered_indexes(ROOT, method["indexes"])
            validate_ledger_journal(
                args.ledger,
                method["ledger_journal_before"],
                set(method["fresh_request_ids"]),
                set(method["fresh_scope_ids"]),
            )
            slots = quality_slots(method, batch, fixtures)
            before = ledger_observation(args.ledger)
            scope_registration = {
                "method_sha256": registration["method_sha256"],
                "batch": batch,
                "source_commit": registration["source_commit"],
                "source_hashes": registration["source_hashes"],
                "ledger_before": before,
                "quarantine_before": observed,
            }
            digest = sha(json.dumps(scope_registration, sort_keys=True).encode())
            folder = destination / batch["batch_id"]
            folder.mkdir(mode=0o700)
            write_new(folder / "registration.json", scope_registration, secret)
            try:
                ledger.quarantine_scope_status(batch["scope_id"])
            except LedgerConflict:
                pass
            else:
                raise ValueError("JsonReadabilityScopeAlreadyRegistered")
            # Own cleanup before the committing call can be interrupted; close
            # only a registration with our exact digest/ref, never a foreign ID.
            active, active_digest, active_ref = (
                batch["scope_id"],
                digest,
                method["authorization_ref"],
            )
            ledger.authorize_quarantine_scope(
                authorization_id=batch["scope_id"],
                authorization_ref=method["authorization_ref"],
                expected_unknown_ids=tuple(observed["unknown_ids"]),
                expected_unknown_fingerprints=tuple(
                    tuple(pair) for pair in observed["unknown_fingerprints"]
                ),
                expected_meta_sha256=observed["meta_sha256"],
                expected_authorization_history_sha256=observed["authorization_history_sha256"],
                protocol_sha256=digest,
                request_slots=slots,
                additional_cap_usd=Decimal(batch.get("scope_cap_usd", "0.06")),
                allow_full_context=True,
            )
            config = MetisConfig(
                api_key=secret,
                live_enabled=True,
                model="gpt-4o-mini",
                phase="development",
                response_mode="grounded_plan",
                continuation_id=active,
                grounded_decision_contracts=True,
                grounded_source_gap_handoff=True,
                grounded_source_gap_investigation=True,
                grounded_resource_guidance=False,
                input_token_reserve=32768,
                max_output_tokens=1024,
                max_request_usd=get_price("gpt-4o-mini").cost(32768, 1024),
            )
            checkpoints = []

            def checkpoint(
                value,
                checkpoints=checkpoints,
                folder=folder,
                scope_id=active,
                scope_digest=active_digest,
                scope_ref=active_ref,
            ):
                if value.get("event") == "reserved_before_transport":
                    if not source_matches(
                        registration,
                        source_observation(
                            ROOT, args.method.relative_to(ROOT), method["input_pins"]
                        ),
                    ):
                        raise ValueError("JsonReadabilityRegistrationRejected")
                    status = ledger.quarantine_scope_status(scope_id)
                    if (
                        status.protocol_sha256 != scope_digest
                        or status.authorization_ref != scope_ref
                        or json.loads(
                            json.dumps(asdict(ledger.quarantine_observation()), default=str)
                        )
                        != method["quarantine_before"]
                    ):
                        raise ValueError("JsonReadabilityRegistrationRejected")
                    validate_registered_indexes(ROOT, method["indexes"])
                    journal = validate_ledger_journal(
                        args.ledger,
                        method["ledger_journal_before"],
                        set(method["fresh_request_ids"]),
                        set(method["fresh_scope_ids"]),
                    )
                    value = {
                        **value,
                        "ledger_before_transport": ledger_observation(args.ledger),
                        "ledger_journal_sha256": sha(json.dumps(journal, sort_keys=True).encode()),
                    }
                checkpoints.append(len(checkpoints))
                write_new(folder / f"checkpoint-{len(checkpoints):03d}.json", value, secret)

            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                result = run_real_index_batch(
                    method,
                    batch,
                    fixtures,
                    definitions,
                    ledger,
                    config,
                    before,
                    method["indexes"],
                    checkpoint=checkpoint,
                )
            disposition = close_owned_scope(ledger, active, active_digest, active_ref)
            result["scope_disposition"] = json.loads(json.dumps(asdict(disposition), default=str))
            if batch.get("stage") == "canary":
                canary_status = {**canary_gate(result), "observed": True}
                result["canary_gate"] = canary_status
            result["wire_arguments_match_registration"] = wire_arguments_match(batch, result)
            batches.append(result)
            write_new(folder / "receipt.json", result, secret)
            active = None
            print(
                json.dumps(
                    {
                        "batch": batch["batch_id"],
                        "visited_jobs": result["visited_jobs"],
                        "completed_routes": result["completed_routes"],
                        "actual_sends": result["actual_sends"],
                        "stopped_early": result["stopped_early"],
                    }
                ),
                flush=True,
            )
            if (
                not batch_complete(result)
                or result["wire_arguments_match_registration"] is not True
                or batch.get("stage") == "canary"
                and not canary_status["passed"]
            ):
                break
        validate_registered_indexes(ROOT, method["indexes"])
        validate_ledger_journal(
            args.ledger,
            method["ledger_journal_before"],
            set(method["fresh_request_ids"]),
            set(method["fresh_scope_ids"]),
        )
        source_after = source_observation(ROOT, args.method.relative_to(ROOT), method["input_pins"])
        quarantine_preserved = (
            json.loads(json.dumps(asdict(ledger.quarantine_observation()), default=str))
            == method["quarantine_before"]
        )
        after = ledger_observation(args.ledger)
        no_pending = after["counts"].get("reserved", 0) == 0
        scopes_closed_cleanly = all(
            batch["scope_disposition"]["block_reason"] == "ExperimentClosed" for batch in batches
        )
        receipt = {
            "protocol_id": method["protocol_id"],
            "registration": registration,
            "method": method,
            "batches": batches,
            "completed_batches": len(batches),
            "planned_batches": len(method["batches"]),
            "ledger_after": after,
            "renderer_source_gap_investigation": True,
            "renderer_ask_source_background": True,
            "no_model_prompt_treatment": True,
            "renderer_concise_user_draft": True,
            "json_object_transport_comparison": True,
            "canary_gate": canary_status,
            "named_profile_through_http": True,
            "compact_plan": True,
            "source_capacity": False,
            "repair_repeated_queries": True,
            "resource_guidance": False,
            "old_journal_preserved": True,
            "old_holds_and_authorization_history_preserved": quarantine_preserved,
            "no_pending_reservations": no_pending,
            "own_scopes_closed_without_new_block": scopes_closed_cleanly,
            "same_native_index_as_R4c_treatment": True,
            "real_index_retrieval": True,
            "embedding": "lexical_hash_v1",
            "held_out_test": False,
            "c5_reconciled": False,
            "human_reviewed": False,
            "human_usefulness": None,
            "source_after": source_after,
            "source_unchanged": source_matches(registration, source_after),
        }
        write_new(destination / "receipt.json", receipt, secret)
        print(
            json.dumps(
                {
                    "receipt_saved": True,
                    "completed_batches": len(batches),
                    "actual_sends": sum(b["actual_sends"] for b in batches),
                    "c5_reconciled": False,
                }
            )
        )
        return (
            0
            if len(batches) == len(method["batches"])
            and all(batch_complete(b) for b in batches)
            and all(b["wire_arguments_match_registration"] for b in batches)
            and (
                not any(b.get("stage") == "canary" for b in method["batches"])
                or canary_status["passed"]
            )
            and receipt["source_unchanged"]
            and quarantine_preserved
            and no_pending
            and scopes_closed_cleanly
            else 2
        )
    except BaseException:
        if destination is not None:
            disposition = None
            if active is not None and ledger is not None:
                try:
                    disposition = json.loads(
                        json.dumps(
                            asdict(close_owned_scope(ledger, active, active_digest, active_ref)),
                            default=str,
                        )
                    )
                except Exception:
                    disposition = {"status": "unknown; reservation retained"}
            try:
                write_new(
                    destination / "failure.json",
                    {
                        "error_code": "JsonReadabilityExperimentStopped",
                        "registration": registration,
                        "batches": batches,
                        "active_scope_disposition": disposition,
                        "ledger_after": ledger_observation(args.ledger),
                    },
                    secret,
                )
            except Exception:
                pass
        print(
            json.dumps(
                {
                    "error_code": "JsonReadabilityExperimentStopped",
                    "raw_diagnostics_exported": False,
                }
            )
        )
        return 2
    finally:
        if active is not None and ledger is not None:
            try:
                status = close_owned_scope(ledger, active, active_digest, active_ref)
                if destination is not None:
                    write_new(
                        destination / "cleanup.json",
                        json.loads(json.dumps(asdict(status), default=str)),
                        secret,
                    )
            except BaseException:
                # Pending/uncertain reservations remain durable even if cleanup cannot finish.
                pass


if __name__ == "__main__":
    raise SystemExit(main())
