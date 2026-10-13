"""Registered real-index development probe; default is read-only eligibility.

This consumes the existing immutable continuation, never clears the global halt,
and allows at most two actual sends across both turns, including repairs.
"""

import argparse
import hashlib
import importlib.util
import io
import json
import re
import subprocess
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

from agent_app import api
from agent_app.contracts import GroundedGap, ProposalHandoff, RetrievalRequest
from agent_app.llm.budget import BudgetLedger
from agent_app.llm.config import MetisConfig
from agent_app.llm.grounded import MetisGroundedPlanner
from agent_app.orchestration.handoff import validate_handoff
from agent_app.orchestration.ports import ReasoningStopped
from agent_app.persistent_api import create_app
from agent_app.reasoning.grounding import GroundedReasoner, make_grounded_request
from agent_app.retrieval.adapter import ChromaRetrieverAdapter
from agent_app.retrieval.offline_index import open_verified_index
from agent_app.retrieval.pilot_corpus import MANIFEST_NAME, PilotCorpus
from agent_app.retrieval.retriever import StreamlitRetriever
from agent_app.testing.grounded_http_binding import runtime_catalog
from agent_app.tracker.sqlite_tracker import SQLiteCaseTracker

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = Path("experiments/grounded_http_acceptance/connected-live-protocol-v1.json")
SPEC = importlib.util.spec_from_file_location(
    "shared_live_probe", ROOT / "scripts/grounded_live_probe.py"
)
SHARED = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SHARED)
TOP_K = 1
DEVELOPMENT_USER_GAPS = (
    {
        "name": "parent_callback_code",
        "kind": "user",
        "description": "The parent selector callback was not supplied.",
        "necessity": "User-supplied callback code is needed to inspect the app's actual state-update order; documentation cannot establish its cause or fix.",
        "question": "Can you share the parent selector callback that resets Session State?",
    },
    {
        "name": "minimal_failing_reproduction",
        "kind": "user",
        "description": "The reduction works; no failing parent-selector example was supplied.",
        "necessity": "The user can supply a failing parent/callback example; repeating the working reduction cannot reproduce the reported failure.",
        "question": "Can you share a minimal failing example that keeps the parent selector/callback interaction? The supplied reduced example works.",
    },
)


def _development_catalog(case, message, evidence):
    """Caller-curated vocabulary matched only to current explicit unknowns.

    This does not infer missing facts from prose or discover necessary questions.
    No gold labels, future turn or source answer participates in this catalog.
    """
    registered = runtime_catalog(case, message, evidence)
    unknowns = {name.casefold() for name in case.unknowns}
    known = {
        fact.name.casefold()
        for fact in case.facts
        if fact.status == "active" and fact.provenance_kind == "user" and fact.value
    }
    extras = tuple(
        GroundedGap.model_validate(definition)
        for definition in DEVELOPMENT_USER_GAPS
        if definition["name"] in unknowns and definition["name"] not in known
    )
    return make_grounded_request(
        case,
        message,
        evidence,
        gaps=registered.gaps + extras,
        conflict_groups=registered.conflict_groups,
    )


class ProbeRejected(ValueError):
    def __init__(self):
        super().__init__("ConnectedLiveDevProbeRejected")


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def source_observation(root):
    paths = (
        [str(path.relative_to(root)) for path in sorted((root / "src/agent_app").rglob("*.py"))]
        + ["scripts/connected_live_dev_probe.py", "scripts/grounded_live_probe.py", str(PROTOCOL)]
        + ["pyproject.toml", "uv.lock"]
    )
    return {
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip(),
        "source_hashes": {relative: _sha((root / relative).read_bytes()) for relative in paths},
        "source_clean": not subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=root, text=True
        ).strip(),
    }


def load_registration(root, ledger_path, index_path):
    """No Chroma client, credential, provider transport or ledger write here."""
    raw = (root / PROTOCOL).read_bytes()
    protocol = json.loads(raw)
    ledger = SHARED.ledger_observation(ledger_path)
    manifest_bytes = (index_path / MANIFEST_NAME).read_bytes()
    corpus = PilotCorpus.from_manifest(json.loads(manifest_bytes))
    source = source_observation(root)
    if (
        protocol["protocol_id"] != "connected-live-dev-pilot-v1"
        or re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", protocol["experiment_id"]) is None
        or protocol["continuation_id"] != SHARED.GRANT
        or ledger_path.resolve() != (root / "runtime/budget.sqlite3").resolve()
        or protocol["ledger"]["path"] != "runtime/budget.sqlite3"
        or ledger["fingerprints"]["db"] != protocol["ledger"]["sha256_before"]
        or ledger["unknown_records_sha256"] != protocol["ledger"]["unknown_records_sha256"]
        or not ledger["halted"]
        or Decimal(ledger["limit_usd"]) != Decimal("4.5")
        or ledger["counts"].get("reserved", 0) != 0
        or ledger["counts"].get("uncertain", 0) != 1
        or ledger["unknown_models"] != ["gpt-4.1-mini"]
        or ledger["unknown_error_codes"] != ["ProviderModelMismatch"]
        or Decimal(ledger["uncertain_usd"]) != Decimal("0.02")
        or not ledger["continuation"]["active"]
        or ledger["continuation"]["allowed_model"] != SHARED.MODEL
        or Decimal(ledger["continuation"]["remaining_usd"]) < SHARED.BATCH_BOUND
        or SHARED.get_price(SHARED.MODEL).cost(SHARED.INPUT_RESERVE, SHARED.OUTPUT_LIMIT)
        != SHARED.REQUEST_BOUND
        or index_path.resolve() != Path(protocol["index"]["path"]).resolve()
        or not (index_path / "chroma.sqlite3").is_file()
        or corpus.snapshot_id != protocol["index"]["snapshot_id"]
        or _sha(manifest_bytes) != protocol["index"]["manifest_sha256"]
        or protocol["index"]["top_k"] != TOP_K
        or protocol["gateway"]
        != {
            "model": SHARED.MODEL,
            "phase": "development",
            "input_token_reserve": SHARED.INPUT_RESERVE,
            "max_output_tokens": SHARED.OUTPUT_LIMIT,
            "max_request_usd": str(SHARED.REQUEST_BOUND),
            "batch_max_reserved_usd": str(SHARED.BATCH_BOUND),
            "max_actual_sends_including_repair": SHARED.MAX_SENDS,
        }
        or len(protocol["turns"]) != 2
        or not source["source_clean"]
    ):
        raise ProbeRejected()
    for relative, digest in source["source_hashes"].items():
        committed = subprocess.check_output(
            ["git", "show", f"HEAD:{relative}"], cwd=root, stderr=subprocess.DEVNULL
        )
        if _sha(committed) != digest:
            raise ProbeRejected()
    for revision, (turn, version) in enumerate(
        zip(protocol["turns"], ("1.50.0", "1.49.0"), strict=True)
    ):
        visible = turn["visible"]
        if set(visible) - {
            "message",
            "reported_facts",
            "unknowns",
            "checks_performed",
            "context_changed",
            "scenario",
        }:
            raise ProbeRejected()
        request = api.MessageRequest.model_validate(
            {**visible, "turn_id": f"check-{revision}", "expected_revision": revision}
        )
        versions = [
            fact.value
            for fact in request.reported_facts
            if fact.name.casefold() == "streamlit_version"
        ]
        if versions != [version] or (revision == 1 and not request.context_changed):
            raise ProbeRejected()
    return protocol, {
        **source,
        "protocol_sha256": _sha(raw),
        "ledger_before": ledger,
        "index_manifest_sha256": _sha(manifest_bytes),
        "snapshot_id": corpus.snapshot_id,
        "index_storage_verification": "deferred until explicit live execution; default reads manifest only",
    }


class _SharedTransport(httpx.BaseTransport):
    """Per-turn client closes itself; the run owns its counted provider transport."""

    def __init__(self, counted):
        self.counted = counted

    def handle_request(self, request):
        return self.counted.handle_request(request)

    def close(self):
        pass


class _IndexedRetriever:
    def __init__(self, adapter, records):
        self.adapter, self.records = adapter, records

    def search(self, request):
        bounded = RetrievalRequest.model_validate(
            {**request.model_dump(), "top_k": min(TOP_K, request.top_k)}
        )
        evidence = self.adapter.search(bounded)
        self.records.append(
            {
                "requested": request.model_dump(mode="json"),
                "executed": bounded.model_dump(mode="json"),
                "evidence": evidence.model_dump(mode="json"),
            }
        )
        return evidence


def run_probe(protocol, *, ledger_path, index_path, state_dir, config, before, underlying=None):
    """Actual verified index + persistent HTTP; MockTransport mandatory in tests."""
    client, snapshot = open_verified_index(index_path)
    if snapshot != protocol["index"]["snapshot_id"]:
        raise ProbeRejected()
    ledger = BudgetLedger(ledger_path)
    counted = SHARED.CountedTransport(underlying or httpx.HTTPTransport(retries=0), ledger, before)
    runs, views, steps, checks = [], [], [], {}
    tokens = {"connected-dev-maintainer": "private-connected-review-" + uuid4().hex}
    case_id = "connected-live-" + protocol["experiment_id"]
    wire_events = []

    def adapters(_scenario):
        gateway = MetisGroundedPlanner(config, ledger, transport=_SharedTransport(counted))
        planner = SHARED._Planner(gateway, counted)
        record = {"gateway": gateway, "planner": planner, "retrieval": []}
        runs.append(record)
        try:
            native = StreamlitRetriever("", snapshot_id=snapshot, client=client)
            retriever = _IndexedRetriever(
                ChromaRetrieverAdapter("", snapshot_id=snapshot, core_retriever=native),
                record["retrieval"],
            )
            return api.RunAdapters(
                retriever,
                GroundedReasoner(planner, request_factory=_development_catalog),
                snapshot_id=snapshot,
                grounded_request_supplier=lambda: planner.latest,
                cleanup=gateway.close,
            )
        except Exception:
            gateway.close()
            raise

    def application():
        return create_app(
            SQLiteCaseTracker(state_dir / "cases.sqlite3", reviewer_tokens=tokens),
            reviewer_tokens=tokens,
            adapters=adapters,
            retrieval_label="local_chroma_hash",
            reasoning_label="metis_grounded_live",
        )

    try:
        with TestClient(application()) as http:
            for revision, turn in enumerate(protocol["turns"]):
                if revision and (
                    not views[-1].get("pending")
                    or not ledger.continuation_status(SHARED.GRANT).active
                ):
                    steps.append(
                        {
                            "turn_index": revision,
                            "runner_stop": "PreviousTurnStopped",
                            "coverage_complete": False,
                        }
                    )
                    break
                wire = {
                    **deepcopy(turn["visible"]),
                    "turn_id": f"{protocol['experiment_id']}-turn-{revision + 1}",
                    "expected_revision": revision,
                }
                wire_events.append(wire)
                sends_before = len(counted.records)
                response = http.post(f"/cases/{case_id}/messages", json=wire)
                if response.status_code != 200:
                    raise ProbeRejected()
                view = response.json()
                views.append(view)
                pending = view["pending"]
                if pending:
                    handoff = validate_handoff(
                        ProposalHandoff.model_validate(pending["review_handoff"])
                    )
                    if handoff.grounded_request is None:
                        raise ProbeRejected()
                factories_before, sends_after = len(runs), len(counted.records)
                replay = http.post(f"/cases/{case_id}/messages", json=wire)
                replay_view = replay.json()
                steps.append(
                    {
                        "turn_index": revision,
                        "wire_request": wire,
                        "case_revision": view["case_revision"],
                        "canonical_pending_handoff": pending["review_handoff"] if pending else None,
                        "run_outcome": view.get("run_outcome"),
                        "new_sends": sends_after - sends_before,
                        "coverage_complete": pending is not None,
                        "checks": {
                            "same_case_current_revision": view["case_id"] == case_id
                            and view["case_revision"] == revision + 1,
                            "no_local_actions_or_auto_release": view["actions"] == []
                            and not any(entry.get("role") == "assistant" for entry in view["log"]),
                            "exact_ingress_retry_without_new_ports_or_sends": replay.status_code
                            == 200
                            and replay_view["intake"]["replayed"] is True
                            and len(runs) == factories_before
                            and len(counted.records) == sends_after,
                            "retry_preserves_current_projection": {
                                k: v for k, v in replay_view.items() if k != "intake"
                            }
                            == {k: v for k, v in view.items() if k != "intake"},
                        },
                    }
                )
                if pending:
                    refused = http.post(
                        f"/cases/{case_id}/decision",
                        json={
                            "proposal_id": pending["proposal_id"],
                            "case_revision": revision + 1,
                            "decision": "approve",
                            "review_id": f"unauthorized-{revision}",
                            "expected_handoff_sha256": pending["review_handoff"]["handoff_sha256"],
                        },
                    )
                    steps[-1]["checks"]["unauthenticated_approval_refused"] = (
                        refused.status_code == 401
                    )
            checks["persistent_http_path_completed"] = True
        factories_before, sends_before = len(runs), len(counted.records)
        latest_projection = {key: value for key, value in views[-1].items() if key != "intake"}
        with TestClient(application()) as http:
            latest_returned = True
            for wire in wire_events:
                replay = http.post(f"/cases/{case_id}/messages", json=wire)
                if replay.status_code != 200 or replay.json()["intake"]["replayed"] is not True:
                    raise ProbeRejected()
                latest_returned = (
                    latest_returned
                    and {key: value for key, value in replay.json().items() if key != "intake"}
                    == latest_projection
                )
            checks["recreation_retries_return_latest_projection"] = latest_returned
            checks["recreation_retry_without_new_ports_or_sends"] = (
                len(runs) == factories_before and len(counted.records) == sends_before
            )
        client.verify()
        checks["verified_index_after_execution"] = True
    except Exception:
        checks["persistent_http_path_completed"] = False
    finally:
        for run in runs:
            run["gateway"].close()
        counted.close()
    negative_before = SHARED.ledger_observation(ledger_path)
    closed_guard = True
    for run in runs:
        planner = run["planner"]
        if planner.latest is None:
            continue
        try:
            planner.plan(planner.latest, context=planner.latest_context)
        except ReasoningStopped as error:
            closed_guard = closed_guard and error.code == "LiveCallsDisabled"
        else:
            closed_guard = False
    checks["closed_invocations_stop_before_reserve_or_send"] = (
        closed_guard and SHARED.ledger_observation(ledger_path) == negative_before
    )
    after = SHARED.ledger_observation(ledger_path)
    checks["all_per_turn_clients_closed"] = all(
        run["gateway"].reasoner.client.is_closed for run in runs
    )
    checks["original_halt_and_quarantine_preserved"] = (
        after["halted"] and after["unknown_records_sha256"] == before["unknown_records_sha256"]
    )
    checks["bounded_actual_sends_including_repair"] = 0 < len(counted.records) <= SHARED.MAX_SENDS
    checks["estimated_settlement_within_registered_batch"] = (
        Decimal(after["settled_estimated_usd"]) - Decimal(before["settled_estimated_usd"])
        <= SHARED.BATCH_BOUND
    )
    complete = len(steps) == 2 and all(step.get("coverage_complete") for step in steps)
    checks["both_version_turns_have_current_proposals"] = complete
    if complete:
        facts = steps[-1]["canonical_pending_handoff"]["case"]["facts"]
        checks["correction_supersedes_old_user_version"] = any(
            f["name"] == "streamlit_version" and f["value"] == "1.49.0" and f["status"] == "active"
            for f in facts
        ) and any(
            f["name"] == "streamlit_version"
            and f["value"] == "1.50.0"
            and f["status"] == "superseded"
            for f in facts
        )
        checks["fresh_proposal_for_corrected_revision"] = (
            steps[0]["canonical_pending_handoff"]["proposal_id"]
            != steps[1]["canonical_pending_handoff"]["proposal_id"]
        )
    for record in counted.records:
        record["reservation"] = SHARED._plain(ledger.get(record["request_id"]))
    operational = all(value is True for value in checks.values()) and all(
        value is True for step in steps for value in step.get("checks", {}).values()
    )
    return {
        "schema_version": 1,
        "protocol_id": protocol["protocol_id"],
        "experiment_id": protocol["experiment_id"],
        "case_id": case_id,
        "accepted_complete_pilot": operational,
        "coverage_complete": complete,
        "actual_sends": len(counted.records),
        "checks": checks,
        "steps": steps,
        "runs": [
            {
                "reasoning_attempts": run["planner"].attempts,
                "retrieval": run["retrieval"],
                "last_grounded_request": run["planner"].latest.model_dump(mode="json")
                if run["planner"].latest
                else None,
                "closed": run["gateway"].reasoner.client.is_closed,
            }
            for run in runs
        ],
        "provider_observations": counted.records,
        "ledger_after": after,
        "new_cost_estimated_usd": str(
            Decimal(after["settled_estimated_usd"]) - Decimal(before["settled_estimated_usd"])
        ),
        "actual_account_charge_usd": None,
        "retrieval_mode": "verified_real_chroma_local_lexical_hash",
        "retrieval_policy": "Explicit top_k=1 source row per query to retain whole excerpts and current user-gap catalog inside the registered 16384 input reserve; no gold-informed selection.",
        "development_user_gap_definitions": deepcopy(DEVELOPMENT_USER_GAPS),
        "question_catalog_limitation": "Caller-curated installed-version/source gaps plus parent_callback_code/minimal_failing_reproduction only when present in current explicit unknowns and not already supplied. This does not discover necessary questions from natural language or establish question quality.",
        "restart_scope": "same_interpreter_application_recreation",
        "proposal_auto_approved": False,
        "whole_proposal_semantic_review": "pending separate source-backed review",
        "exposed_answer_informed_development_case": True,
        "same_issue_answer_used_as_evidence": False,
        "c5_reconciled": False,
        "quality_claim": False,
        "heldout_claim": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, default=ROOT / "runtime/budget.sqlite3")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    try:
        protocol, registration = load_registration(ROOT, args.ledger, args.index)
        if not args.live:
            print(
                json.dumps(
                    {
                        "eligible_read_only": True,
                        "paid_requests": 0,
                        "max_sends": SHARED.MAX_SENDS,
                        "batch_cap_usd": str(SHARED.BATCH_BOUND),
                        "index_storage_verification": registration["index_storage_verification"],
                        "c5_reconciled": False,
                    }
                )
            )
            return
        if args.env_file is None or args.output_dir is None:
            raise ProbeRejected()
        destination = args.output_dir.resolve()
        if (
            destination.is_relative_to(ROOT)
            and subprocess.run(
                ["git", "check-ignore", "--quiet", "--", str(destination)], cwd=ROOT
            ).returncode
            != 0
        ):
            raise ProbeRejected()
        destination.mkdir(parents=True, exist_ok=False, mode=0o700)
        (destination / "registration.json").write_text(
            json.dumps(registration, indent=2) + "\n", encoding="utf-8"
        )
        # Verify persisted index content before credentials or provider allocation.
        verified, snapshot = open_verified_index(args.index)
        if snapshot != registration["snapshot_id"]:
            raise ProbeRejected()
        verified.verify()
        if SHARED.ledger_observation(args.ledger) != registration[
            "ledger_before"
        ] or source_observation(ROOT) != {
            key: registration[key] for key in ("source_commit", "source_hashes", "source_clean")
        }:
            raise ProbeRejected()
        config = MetisConfig(
            api_key=SHARED._credential(ROOT, args.env_file),
            live_enabled=True,
            model=SHARED.MODEL,
            phase="development",
            response_mode="grounded_plan",
            continuation_id=SHARED.GRANT,
            input_token_reserve=SHARED.INPUT_RESERVE,
            max_output_tokens=SHARED.OUTPUT_LIMIT,
            max_request_usd=SHARED.REQUEST_BOUND,
        )
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            receipt = run_probe(
                protocol,
                ledger_path=args.ledger,
                index_path=args.index,
                state_dir=destination,
                config=config,
                before=registration["ledger_before"],
            )
        try:
            after = source_observation(ROOT)
            unchanged = after == {key: registration[key] for key in after}
        except Exception:
            after, unchanged = None, False
        receipt["registration"] = registration
        receipt["source_after"] = after
        receipt["checks"]["registered_checkout_unchanged"] = unchanged
        receipt["accepted_complete_pilot"] = receipt["accepted_complete_pilot"] and unchanged
        with (destination / "receipt.json").open("x", encoding="utf-8") as stream:
            json.dump(receipt, stream, ensure_ascii=True, indent=2)
            stream.write("\n")
        print(
            json.dumps(
                {
                    "actual_sends": receipt["actual_sends"],
                    "coverage_complete": receipt["coverage_complete"],
                    "accepted_complete_pilot": receipt["accepted_complete_pilot"],
                    "new_cost_estimated_usd": receipt["new_cost_estimated_usd"],
                    "actual_account_charge_usd": None,
                    "quality_claim": False,
                    "c5_reconciled": False,
                }
            )
        )
        if not receipt["accepted_complete_pilot"]:
            raise ProbeRejected()
    except Exception:
        print(json.dumps({"code": "ConnectedLiveDevProbeRejected", "automatic_retry": False}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
