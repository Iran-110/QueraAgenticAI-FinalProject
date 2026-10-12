"""One explicitly registered compatibility probe, never a general live backend.

Default execution checks eligibility read-only. Only --live loads the explicitly
supplied ignored environment file and uses the existing immutable continuation.
Receipts omit credentials, prompts, raw provider responses and error messages.
"""

import argparse
import hashlib
import io
import json
import sqlite3
import subprocess
from collections.abc import Iterator
from contextlib import closing, redirect_stderr, redirect_stdout
from copy import deepcopy
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

from agent_app import api
from agent_app.contracts import EvidenceBundle, GroundedGap
from agent_app.llm.budget import BudgetLedger, _configuration, _continuation_status, _totals
from agent_app.llm.config import METIS_CHAT_URL, MetisConfig
from agent_app.llm.grounded import MetisGroundedPlanner
from agent_app.llm.metis import request_id_for
from agent_app.llm.pricing import get_price, same_verified_price
from agent_app.orchestration.ports import ReasoningStopped
from agent_app.reasoning.grounding import (
    GroundedReasoner,
    build_grounded_messages,
    make_grounded_request,
)
from agent_app.testing.fakes import FakeRetriever
from agent_app.tracker.sqlite_tracker import SQLiteCaseTracker

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = Path("experiments/grounded_http_acceptance/live-protocol-v1.json")
FIXTURE = Path("experiments/review_handoff/case-current-state-latest-evidence.json")
GRANT = "user-continuation-2026-10-07-v3"
MODEL = "gpt-4o-mini"
INPUT_RESERVE = 16384
OUTPUT_LIMIT = 768
REQUEST_BOUND = Decimal("0.003210240")
BATCH_BOUND = Decimal("0.006420480")
MAX_SENDS = 2
SOURCE_PATHS = (
    "scripts/grounded_live_probe.py",
    str(PROTOCOL),
    str(FIXTURE),
    "src/agent_app/persistent_api.py",
    "src/agent_app/api.py",
    "src/agent_app/orchestration/service.py",
    "src/agent_app/orchestration/engine.py",
    "src/agent_app/orchestration/handoff.py",
    "src/agent_app/reasoning/grounding.py",
    "src/agent_app/llm/metis.py",
    "src/agent_app/llm/grounded.py",
    "src/agent_app/llm/config.py",
    "src/agent_app/llm/pricing.py",
    "src/agent_app/llm/budget.py",
    "src/agent_app/tracker/sqlite_tracker.py",
    "src/agent_app/contracts.py",
)


class ProbeRejected(ValueError):
    def __init__(self):
        super().__init__("GroundedLiveProbeRejected")


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _plain(value):
    return json.loads(
        json.dumps(
            value, default=lambda item: str(item) if isinstance(item, Decimal) else asdict(item)
        )
    )


def ledger_observation(path: Path, grant: str = GRANT):
    """Read-only snapshot and exact original quarantine identity, never initialize."""

    def fingerprints():
        return {
            suffix or "db": _sha(part.read_bytes()) if part.exists() else None
            for suffix in ("", "-wal", "-shm")
            for part in (Path(str(path) + suffix),)
        }

    before = fingerprints()
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        limit, opening, halted = _configuration(connection)
        settled, reserved, uncertain = _totals(connection)
        status = _continuation_status(connection, grant)
        unknown = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM reservations WHERE status='uncertain' ORDER BY request_id"
            )
        ]
        counts = dict(
            connection.execute(
                "SELECT status, COUNT(*) FROM reservations GROUP BY status"
            ).fetchall()
        )
        connection.rollback()
    after = fingerprints()
    if before != after:
        raise ProbeRejected()

    def usd(amount):
        return str(Decimal(amount) / Decimal(1_000_000_000))

    return {
        "fingerprints": after,
        "halted": halted,
        "limit_usd": usd(limit),
        "opening_usd": usd(opening),
        "settled_estimated_usd": usd(settled),
        "reserved_usd": usd(reserved),
        "uncertain_usd": usd(uncertain),
        "available_bound_usd": usd(max(0, limit - opening - settled - reserved - uncertain)),
        "counts": counts,
        "unknown_records_sha256": _sha(
            json.dumps(unknown, sort_keys=True, separators=(",", ":")).encode()
        ),
        "unknown_models": [row["model"] for row in unknown],
        "unknown_error_codes": [row["error_code"] for row in unknown],
        "continuation": _plain(status),
        "account_charge_usd": None,
        "provider_balance_usd": None,
    }


def load_registration(root: Path, ledger_path: Path):
    protocol_bytes = (root / PROTOCOL).read_bytes()
    protocol = json.loads(protocol_bytes)
    fixture_bytes = (root / FIXTURE).read_bytes()
    if (
        protocol["protocol_id"] != "grounded-http-live-compatibility-v1"
        or protocol["continuation_id"] != GRANT
        or _sha(fixture_bytes) != protocol["input"]["fixture_sha256"]
        or protocol["gateway"]["model"] != MODEL
        or Decimal(protocol["gateway"]["batch_max_reserved_usd"]) != BATCH_BOUND
        or protocol["gateway"]["max_actual_sends_including_repair"] != MAX_SENDS
        or ledger_path.resolve() != (root / protocol["ledger"]["path"]).resolve()
    ):
        raise ProbeRejected()
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    source_hashes = {}
    for relative in SOURCE_PATHS:
        data = (root / relative).read_bytes()
        committed = subprocess.check_output(
            ["git", "show", f"HEAD:{relative}"], cwd=root, stderr=subprocess.DEVNULL
        )
        if data != committed:
            raise ProbeRejected()
        source_hashes[relative] = _sha(data)
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True).strip():
        raise ProbeRejected()
    observation = ledger_observation(ledger_path)
    if (
        observation["fingerprints"]["db"] != protocol["ledger"]["sha256_before"]
        or not observation["halted"]
        or observation["counts"].get("reserved", 0) != 0
        or observation["counts"].get("uncertain", 0) != 1
        or observation["unknown_models"] != ["gpt-4.1-mini"]
        or observation["unknown_error_codes"] != ["ProviderModelMismatch"]
        or Decimal(observation["uncertain_usd"]) != Decimal("0.02")
        or not observation["continuation"]["active"]
        or observation["continuation"]["allowed_model"] != MODEL
        or Decimal(observation["continuation"]["remaining_usd"]) < BATCH_BOUND
        or get_price(MODEL).cost(INPUT_RESERVE, OUTPUT_LIMIT) != REQUEST_BOUND
    ):
        raise ProbeRejected()
    return (
        protocol,
        json.loads(fixture_bytes),
        {
            "source_commit": commit,
            "source_hashes": source_hashes,
            "protocol_sha256": _sha(protocol_bytes),
            "ledger_before": observation,
        },
    )


def first_turn_catalog(fixture, case, message, evidence):
    """Only inherited caller metadata; gold/expected/templates stay outside prompt."""
    gaps = tuple(
        GroundedGap(
            name=item["name"],
            kind="user",
            description="The affected installation's version is unknown."
            if item["name"] == "streamlit_version"
            else "The affected parent callback and state-update path were not supplied.",
            necessity="The user can supply this missing environment fact or application code.",
            question=item["question"],
        )
        for item in fixture["question_catalog"]
    ) + tuple(GroundedGap.model_validate(item) for item in fixture["source_gap_catalog"][:2])
    return make_grounded_request(case, message, evidence, gaps=gaps)


class _ObservedStream(httpx.SyncByteStream):
    def __init__(self, stream, record):
        self.stream, self.record = stream, record

    def __iter__(self) -> Iterator[bytes]:
        bounded = bytearray()
        for chunk in self.stream:
            if len(bounded) + len(chunk) <= 262_144:
                bounded.extend(chunk)
            else:
                bounded.clear()
                self.record["response_too_large"] = True
            yield chunk
        if not self.record.get("response_too_large"):
            try:
                value = json.loads(bounded).get("model")
                if isinstance(value, str) and same_verified_price(MODEL, value):
                    self.record["verified_returned_model"] = value
            except (ValueError, TypeError, AttributeError):
                pass

    def close(self):
        self.stream.close()


class CountedTransport(httpx.BaseTransport):
    """Check scope and a durable reservation before every actual provider send."""

    def __init__(self, underlying, ledger, before):
        self.underlying, self.ledger, self.before = underlying, ledger, before
        self.records = []
        self.current_request_id = None

    def check_scope(self):
        snapshot = self.ledger.snapshot()
        scope = self.ledger.continuation_status(GRANT)
        if (
            not scope.active
            or not snapshot.halted
            or snapshot.uncertain_usd != Decimal("0.02")
            or scope.allowed_model != MODEL
            or scope.used_usd - Decimal(self.before["continuation"]["used_usd"]) > BATCH_BOUND
        ):
            raise ReasoningStopped("BudgetExceeded", "budget_stopped")

    def handle_request(self, request):
        # During a send a pending reservation is expected; continuation_status
        # would reject pending, so check it before reserve in planner.plan instead.
        snapshot = self.ledger.snapshot()
        row = self.ledger.get(self.current_request_id) if self.current_request_id else None
        guarded = ledger_observation(self.ledger._path)
        if (
            len(self.records) >= MAX_SENDS
            or str(request.url) != METIS_CHAT_URL
            or request.method != "POST"
            or row is None
            or row.status != "reserved"
            or row.model != MODEL
            or row.phase != "development"
            or row.amount_usd != REQUEST_BOUND
            or not snapshot.halted
            or snapshot.uncertain_usd != Decimal("0.02")
            or guarded["unknown_records_sha256"] != self.before["unknown_records_sha256"]
            or guarded["continuation"]["block_reason"] != "PendingRequest"
            or guarded["counts"].get("reserved", 0) != 1
            or snapshot.settled_usd
            - Decimal(self.before["settled_estimated_usd"])
            + snapshot.reserved_usd
            > BATCH_BOUND
        ):
            raise ReasoningStopped("BudgetExceeded", "budget_stopped")
        record = {
            "request_id": row.request_id,
            "http_send_started": True,
            "verified_returned_model": None,
        }
        self.records.append(record)
        response = self.underlying.handle_request(request)
        record["http_status"] = response.status_code
        return httpx.Response(
            response.status_code,
            headers=response.headers,
            stream=_ObservedStream(response.stream, record),
            extensions=response.extensions,
            request=request,
        )

    def close(self):
        self.underlying.close()


class _Planner:
    def __init__(self, gateway, counted):
        self.gateway, self.counted = gateway, counted
        self.latest = None
        self.latest_context = None
        self.attempts = []

    def plan(self, request, *, context):
        if self.gateway.reasoner.client.is_closed:
            raise ReasoningStopped("LiveCallsDisabled")
        self.counted.check_scope()
        if len(self.attempts) >= MAX_SENDS or len(self.counted.records) >= MAX_SENDS:
            raise ReasoningStopped("BudgetExceeded", "budget_stopped")
        size = (
            len(json.dumps(build_grounded_messages(request, context), ensure_ascii=False).encode())
            + 1024
        )
        if size > INPUT_RESERVE:
            raise ReasoningStopped("ContextLimitExceeded")
        self.latest = request.model_copy(deep=True)
        self.latest_context = context.model_copy(deep=True)
        request_id = request_id_for(context)
        self.attempts.append(
            {
                "request_id": request_id,
                "attempt_index": context.attempt_index,
                "run_id": context.run_id,
                "prompt_bytes_plus_margin": size,
            }
        )
        self.counted.current_request_id = request_id
        try:
            return self.gateway.plan(request, context=context)
        finally:
            self.counted.current_request_id = None


def run_probe(fixture, *, ledger_path, state_dir, config, before, underlying=None):
    """Explicit composition, called only after live gate or from mock tests."""
    from agent_app.persistent_api import create_app

    ledger = BudgetLedger(ledger_path)
    counted = CountedTransport(underlying or httpx.HTTPTransport(retries=0), ledger, before)
    gateway = MetisGroundedPlanner(config, ledger, transport=counted)
    planner = _Planner(gateway, counted)
    factories = []
    bundle = EvidenceBundle.model_validate(fixture["evidence_bundles"]["official-mixed"])

    def adapters(_scenario):
        factories.append(1)
        return api.RunAdapters(
            FakeRetriever([bundle, bundle]),
            GroundedReasoner(
                planner,
                request_factory=lambda case, message, evidence: first_turn_catalog(
                    fixture, case, message, evidence
                ),
            ),
            snapshot_id=bundle.snapshot_id,
            grounded_request_supplier=lambda: planner.latest,
            cleanup=gateway.close,
        )

    tokens = {"live-probe-maintainer": "private-local-probe-review-" + uuid4().hex}
    suffix = uuid4().hex
    case_id = "live-grounded-" + suffix
    wire = {**deepcopy(fixture["turns"][0]["wire_request"]), "turn_id": "live-event-" + suffix}
    checks = {}
    view, pending = {}, None
    try:
        tracker = SQLiteCaseTracker(state_dir / "cases.sqlite3", reviewer_tokens=tokens)
        application = create_app(
            tracker,
            reviewer_tokens=tokens,
            adapters=adapters,
            reasoning_label="metis_grounded_live",
        )
        with TestClient(application) as client:
            response = client.post(f"/cases/{case_id}/messages", json=wire)
            if response.status_code != 200:
                raise ProbeRejected()
            view = response.json()
            pending = view["pending"]
            checks["gateway_closed_before_runner_failsafe"] = gateway.reasoner.client.is_closed
            checks["pending_or_explicit_stop"] = (
                pending is not None or view["run_outcome"] is not None
            )
            checks["no_local_actions"] = view["actions"] == []
            checks["no_auto_release"] = not any(
                entry.get("role") == "assistant" for entry in view["log"]
            )
            if pending is not None:
                refused = client.post(
                    f"/cases/{case_id}/decision",
                    json={
                        "proposal_id": pending["proposal_id"],
                        "case_revision": view["case_revision"],
                        "decision": "approve",
                        "review_id": "unauthorized-" + suffix,
                        "expected_handoff_sha256": pending["review_handoff"]["handoff_sha256"],
                    },
                )
                checks["unauthorized_review_refused"] = refused.status_code == 401
            else:
                checks["unauthorized_review_refused"] = None
            sends_before, factories_before = len(counted.records), len(factories)
            replay = client.post(f"/cases/{case_id}/messages", json=wire)
            replay_view = replay.json()
            checks["exact_replay_without_new_gateway_or_ports"] = (
                replay.status_code == 200
                and replay_view["intake"]["replayed"] is True
                and len(counted.records) == sends_before
                and len(factories) == factories_before
            )
            checks["replay_preserves_projection"] = {
                k: v for k, v in replay_view.items() if k != "intake"
            } == {k: v for k, v in view.items() if k != "intake"}
        reopened = create_app(
            SQLiteCaseTracker(state_dir / "cases.sqlite3", reviewer_tokens=tokens),
            reviewer_tokens=tokens,
            adapters=adapters,
            reasoning_label="metis_grounded_live",
        )
        with TestClient(reopened) as client:
            reopened_replay = client.post(f"/cases/{case_id}/messages", json=wire)
            checks["application_recreation_replay_no_new_send"] = (
                reopened_replay.status_code == 200
                and reopened_replay.json()["intake"]["replayed"] is True
                and len(counted.records) == sends_before
                and len(factories) == factories_before
            )
        checks["persistent_http_path_completed"] = True
    except Exception:
        # Preserve any already sent/settled attempt in a failed receipt. Never
        # turn an HTTP/staging/replay failure into another paid attempt.
        checks["persistent_http_path_completed"] = False
    finally:
        gateway.close()
    # A terminal/closed invocation must never reserve fresh credit even when
    # called directly outside HTTP. This negative probe cannot reach transport.
    negative_before = ledger_observation(ledger_path)
    guard_sends_before = len(counted.records)
    if planner.latest is not None:
        try:
            planner.plan(planner.latest, context=planner.latest_context)
        except ReasoningStopped as error:
            checks["closed_invocation_guard_before_reserve_or_send"] = (
                error.code == "LiveCallsDisabled"
                and len(counted.records) == guard_sends_before
                and ledger_observation(ledger_path) == negative_before
            )
        else:
            checks["closed_invocation_guard_before_reserve_or_send"] = False
    after = ledger_observation(ledger_path)
    checks["original_halt_and_uncertainty_preserved"] = (
        after["halted"] and after["unknown_records_sha256"] == before["unknown_records_sha256"]
    )
    checks["bounded_sends_including_repair"] = 0 < len(counted.records) <= MAX_SENDS
    checks["gateway_closed"] = gateway.reasoner.client.is_closed
    for record in counted.records:
        row = ledger.get(record["request_id"])
        record["reservation"] = _plain(row)
    return {
        "schema_version": 1,
        "protocol_id": "grounded-http-live-compatibility-v1",
        "case_id": case_id,
        "event_id": wire["turn_id"],
        "checks": checks,
        "accepted_operations": all(value is True for value in checks.values() if value is not None),
        "actual_sends": len(counted.records),
        "reasoning_attempts": planner.attempts,
        "provider_observations": counted.records,
        "ledger_after": after,
        "new_cost_estimated_usd": str(
            Decimal(after["settled_estimated_usd"]) - Decimal(before["settled_estimated_usd"])
        ),
        "actual_account_charge_usd": None,
        "canonical_pending_handoff": pending["review_handoff"] if pending else None,
        "registered_decision_check": {
            "observed_decision": pending["decision"] if pending else None,
            "matches_preregistered_acceptable_decisions": pending["decision"] in {"ask", "escalate"}
            if pending
            else None,
            "whole_proposal_semantic_review": "pending separate source-backed review",
            "not_part_of_operational_acceptance": True,
        },
        "run_outcome": view.get("run_outcome"),
        "proposal_auto_approved": False,
        "retrieval_mode": "fixed_C3_official_excerpt_fixture",
        "restart_scope": "same_interpreter_application_recreation",
        "exposed_answer_informed_development_case": True,
        "same_issue_answer_used_as_evidence": False,
        "c5_reconciled": False,
        "quality_claim": False,
        "heldout_claim": False,
    }


def _credential(root, path):
    if (
        subprocess.run(["git", "check-ignore", "--quiet", "--", str(path)], cwd=root).returncode
        != 0
        or subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", str(path)],
            cwd=root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    ):
        raise ProbeRejected()
    values = []
    for line in path.read_text(encoding="utf-8").splitlines():
        name, separator, value = line.strip().removeprefix("export ").partition("=")
        if separator and name.strip() == "METIS_API_KEY":
            value = value.strip()
            if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
                value = value[1:-1]
            values.append(value)
    if len(values) != 1:
        raise ProbeRejected()
    return values[0]


def source_observation(root):
    """Detect concurrent checkout edits/commits without reading unrelated files."""
    return {
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip(),
        "source_hashes": {
            relative: _sha((root / relative).read_bytes()) for relative in SOURCE_PATHS
        },
        "source_clean": not subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=root, text=True
        ).strip(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=ROOT / "runtime/budget.sqlite3")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    try:
        protocol, fixture, registration = load_registration(ROOT, args.ledger)
        if not args.live:
            print(
                json.dumps(
                    {
                        "eligible_read_only": True,
                        "paid_requests": 0,
                        "batch_cap_usd": str(BATCH_BOUND),
                        "max_sends": MAX_SENDS,
                        "c5_reconciled": False,
                    }
                )
            )
            return
        if args.env_file is None or args.output_dir is None:
            raise ProbeRejected()
        private_output = args.output_dir.resolve()
        if (
            private_output.is_relative_to(ROOT)
            and subprocess.run(
                ["git", "check-ignore", "--quiet", "--", str(private_output)], cwd=ROOT
            ).returncode
            != 0
        ):
            raise ProbeRejected()
        args.output_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
        # Pin the committed source/protocol and accounting before credentials.
        (args.output_dir / "registration.json").write_text(
            json.dumps(registration, indent=2) + "\n", encoding="utf-8"
        )
        config = MetisConfig(
            api_key=_credential(ROOT, args.env_file),
            live_enabled=True,
            model=MODEL,
            phase="development",
            response_mode="grounded_plan",
            continuation_id=GRANT,
            input_token_reserve=INPUT_RESERVE,
            max_output_tokens=OUTPUT_LIMIT,
            max_request_usd=REQUEST_BOUND,
        )
        # Nothing from dependencies or errors can print a key/header/prompt.
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            receipt = run_probe(
                fixture,
                ledger_path=args.ledger,
                state_dir=args.output_dir,
                config=config,
                before=registration["ledger_before"],
            )
        try:
            source_after = source_observation(ROOT)
            source_unchanged = (
                source_after["source_clean"]
                and source_after["source_commit"] == registration["source_commit"]
                and source_after["source_hashes"] == registration["source_hashes"]
            )
        except Exception:
            source_after, source_unchanged = None, False
        receipt["source_after"] = source_after
        receipt["checks"]["registered_checkout_unchanged"] = source_unchanged
        receipt["accepted_operations"] = receipt["accepted_operations"] and source_unchanged
        receipt["registration"] = registration
        receipt["protocol_sha256"] = _sha((ROOT / PROTOCOL).read_bytes())
        with (args.output_dir / "receipt.json").open("x", encoding="utf-8") as stream:
            json.dump(receipt, stream, ensure_ascii=True, indent=2)
            stream.write("\n")
        print(
            json.dumps(
                {
                    "actual_sends": receipt["actual_sends"],
                    "accepted_operations": receipt["accepted_operations"],
                    "new_cost_estimated_usd": receipt["new_cost_estimated_usd"],
                    "actual_account_charge_usd": None,
                    "quality_claim": False,
                    "c5_reconciled": False,
                }
            )
        )
        if not receipt["accepted_operations"]:
            raise ProbeRejected()
    except Exception:
        print(
            json.dumps(
                {
                    "failed": True,
                    "code": "GroundedLiveProbeRejected",
                    "no_ledger_reset_or_unhalt": True,
                }
            )
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
