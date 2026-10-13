"""One preregistered query comparison using the existing bounded development grant.

No ordinary live factory, ledger reset, new grant or global unhalt is involved.
Default execution verifies source/accounting and both real-index prompts without
credentials or provider allocation. Only the root operator runs explicit --live.
"""

import argparse
import hashlib
import io
import json
import re
import sqlite3
import subprocess
from contextlib import closing, redirect_stderr, redirect_stdout
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import httpx

from agent_app.contracts import (
    CaseState,
    ReasoningContext,
    RetrievalRequest,
    RunLimits,
    TurnConversation,
)
from agent_app.evaluation.live import _DecodedStream
from agent_app.llm.budget import BudgetLedger, _configuration, _continuation_status, _totals
from agent_app.llm.config import METIS_CHAT_URL, MetisConfig
from agent_app.llm.grounded import MetisGroundedPlanner
from agent_app.llm.metis import request_id_for
from agent_app.llm.pricing import get_price
from agent_app.orchestration import SupportEngine
from agent_app.orchestration.conversation import build_reasoning_message
from agent_app.orchestration.engine import build_initial_query
from agent_app.orchestration.handoff import ReasoningCapture, build_handoff
from agent_app.orchestration.ports import ReasoningStopped
from agent_app.reasoning.catalog import caller_catalog, validate_user_gaps
from agent_app.reasoning.grounding import GroundedReasoner, build_grounded_messages
from agent_app.retrieval.adapter import ChromaRetrieverAdapter
from agent_app.retrieval.offline_index import open_verified_index
from agent_app.retrieval.pilot_corpus import MANIFEST_NAME
from agent_app.retrieval.retriever import StreamlitRetriever

ROOT = Path(__file__).resolve().parents[3]
PROTOCOL = Path("experiments/retrieval_context/live-protocol-v1.json")
GRANT = "user-continuation-2026-10-07-v3"
MODEL = "gpt-4o-mini"
INPUT_RESERVE = 16384
OUTPUT_LIMIT = 384
REQUEST_BOUND = Decimal("0.002956800")
BATCH_BOUND = Decimal("0.005913600")
MAX_SENDS = 2
TOP_K = 1


class ProbeRejected(ValueError):
    def __init__(self):
        super().__init__("RetrievalContextLiveProbeRejected")


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _plain(value):
    return json.loads(
        json.dumps(
            value, default=lambda item: str(item) if isinstance(item, Decimal) else asdict(item)
        )
    )


def ledger_observation(path):
    """Existing ledger only, read-only stable snapshot; raw incident rows stay private."""

    def fingerprints():
        return {
            suffix or "db": _sha(part.read_bytes()) if part.exists() else None
            for suffix in ("", "-wal", "-shm")
            for part in (Path(str(path) + suffix),)
        }

    before = fingerprints()
    with closing(
        sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    ) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        limit, opening, halted = _configuration(connection)
        settled, reserved, uncertain = _totals(connection)
        scope = _continuation_status(connection, GRANT)
        unknown = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM reservations WHERE status='uncertain' ORDER BY request_id"
            )
        ]
        original = dict(
            connection.execute(
                "SELECT * FROM reservations WHERE request_id=?", (scope.expected_request_id,)
            ).fetchone()
        )
        counts = dict(
            connection.execute(
                "SELECT status,COUNT(*) FROM reservations GROUP BY status"
            ).fetchall()
        )
        connection.rollback()
    after = fingerprints()
    if before != after:
        raise ProbeRejected()

    def usd(value):
        return str(Decimal(value) / Decimal(1_000_000_000))

    return {
        "fingerprints": after,
        "halted": halted,
        "limit_usd": usd(limit),
        "opening_usd": usd(opening),
        "settled_estimated_usd": usd(settled),
        "reserved_usd": usd(reserved),
        "uncertain_usd": usd(uncertain),
        "counts": counts,
        "unknown_records_sha256": _sha(
            json.dumps(unknown, sort_keys=True, separators=(",", ":")).encode()
        ),
        "original_quarantine_sha256": _sha(
            json.dumps(original, sort_keys=True, separators=(",", ":")).encode()
        ),
        "unknown_models": [row["model"] for row in unknown],
        "unknown_error_codes": [row["error_code"] for row in unknown],
        "continuation": _plain(scope),
        "actual_account_charge_usd": None,
        "provider_balance_usd": None,
    }


def source_observation(root, fixture_relative):
    paths = [
        str(path.relative_to(root)) for path in sorted((root / "src/agent_app").rglob("*.py"))
    ] + [
        "scripts/retrieval_context_live_probe.py",
        str(PROTOCOL),
        fixture_relative,
        "pyproject.toml",
        "uv.lock",
    ]
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    upstream = subprocess.check_output(
        ["git", "rev-parse", "@{upstream}"], cwd=root, text=True, stderr=subprocess.DEVNULL
    ).strip()
    return {
        "source_commit": head,
        "upstream_commit": upstream,
        "source_clean": not subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=root, text=True
        ).strip(),
        "source_pushed": head == upstream,
        "source_hashes": {relative: _sha((root / relative).read_bytes()) for relative in paths},
    }


def _immutable_accounting_preserved(now, before):
    """Settlements may consume the grant; its authorization and incident cannot change."""
    return (
        Decimal(now["limit_usd"]) == Decimal(before["limit_usd"]) == Decimal("4.5")
        and Decimal(now["opening_usd"]) == Decimal(before["opening_usd"])
        and now["original_quarantine_sha256"] == before["original_quarantine_sha256"]
        and all(
            now["continuation"][field] == before["continuation"][field]
            for field in (
                "authorization_id",
                "authorization_ref",
                "expected_request_id",
                "allowed_model",
                "additional_cap_usd",
                "held_usd",
            )
        )
    )


def load_registration(root, ledger_path):
    raw = (root / PROTOCOL).read_bytes()
    protocol = json.loads(raw)
    relative = protocol["fixture"]["path"]
    fixture_path = (root / relative).resolve()
    if not fixture_path.is_relative_to(root.resolve()) or fixture_path.suffix != ".json":
        raise ProbeRejected()
    fixture_bytes = fixture_path.read_bytes()
    source = source_observation(root, relative)
    ledger = ledger_observation(ledger_path)
    index_path = Path(protocol["index"]["path"]).resolve()
    manifest_sha = _sha((index_path / MANIFEST_NAME).read_bytes())
    if (
        protocol["protocol_id"] != "retrieval-context-live-comparison-v1"
        or re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", protocol["experiment_id"]) is None
        or protocol["continuation_id"] != GRANT
        or protocol["ledger"]["path"] != "runtime/budget.sqlite3"
        or Path(ledger_path).resolve() != (root / "runtime/budget.sqlite3").resolve()
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
        or ledger["continuation"]["allowed_model"] != MODEL
        or Decimal(ledger["continuation"]["remaining_usd"]) < BATCH_BOUND
        or get_price(MODEL).cost(INPUT_RESERVE, OUTPUT_LIMIT) != REQUEST_BOUND
        or _sha(fixture_bytes) != protocol["fixture"]["sha256"]
        or manifest_sha != protocol["index"]["manifest_sha256"]
        or protocol["index"]["top_k"] != TOP_K
        or protocol["gateway"]
        != {
            "model": MODEL,
            "phase": "development",
            "input_token_reserve": INPUT_RESERVE,
            "max_output_tokens": OUTPUT_LIMIT,
            "max_request_usd": str(REQUEST_BOUND),
            "batch_max_reserved_usd": str(BATCH_BOUND),
            "max_actual_sends_including_repair": MAX_SENDS,
        }
        or not source["source_clean"]
        or not source["source_pushed"]
    ):
        raise ProbeRejected()
    for relative, digest in source["source_hashes"].items():
        committed = subprocess.check_output(
            ["git", "show", f"HEAD:{relative}"], cwd=root, stderr=subprocess.DEVNULL
        )
        if _sha(committed) != digest:
            raise ProbeRejected()
    return (
        protocol,
        json.loads(fixture_bytes),
        {
            **source,
            "fixture_path": protocol["fixture"]["path"],
            "fixture_sha256": _sha(fixture_bytes),
            "protocol_sha256": _sha(raw),
            "ledger_before": ledger,
            "index_manifest_sha256": manifest_sha,
        },
    )


class _BoundedRetriever:
    def __init__(self, adapter):
        self.adapter, self.reads = adapter, []

    def search(self, request):
        bounded = RetrievalRequest.model_validate(
            {**request.model_dump(), "top_k": min(TOP_K, request.top_k)}
        )
        evidence = self.adapter.search(bounded)
        self.reads.append(
            {
                "request": bounded.model_dump(mode="json"),
                "evidence": evidence.model_dump(mode="json"),
                "evidence_sha256": _sha(evidence.model_dump_json().encode()),
            }
        )
        return evidence


def _retriever(client, snapshot):
    return _BoundedRetriever(
        ChromaRetrieverAdapter(
            "",
            snapshot_id=snapshot,
            core_retriever=StreamlitRetriever("", snapshot_id=snapshot, client=client),
        )
    )


def prepare_inputs(protocol, fixture):
    """Real-index retrieval and complete prompt sizing for BOTH arms before a key."""
    from agent_app.orchestration.retrieval_context import build_current_query

    if set(fixture) - {"case", "conversation", "user_message", "provenance"}:
        raise ProbeRejected()
    case = CaseState.model_validate(fixture["case"])
    conversation = TurnConversation.model_validate(fixture["conversation"])
    message = build_reasoning_message(conversation)
    if (
        case.pending_proposal_id is not None
        or case.case_revision != conversation.committed_revision
        or ("user_message" in fixture and fixture["user_message"] != message)
    ):
        raise ProbeRejected()
    gaps = validate_user_gaps(protocol["user_gap_definitions"])
    client, snapshot = open_verified_index(protocol["index"]["path"])
    if (
        snapshot != protocol["index"]["snapshot_id"]
        or _sha((Path(protocol["index"]["path"]) / MANIFEST_NAME).read_bytes())
        != protocol["index"]["manifest_sha256"]
    ):
        raise ProbeRejected()
    queries = {
        "legacy": build_initial_query(case, message),
        "current": build_current_query(case, conversation),
    }
    if "expected_queries" in protocol and queries != protocol["expected_queries"]:
        raise ProbeRejected()
    arms = {}
    for name, query in queries.items():
        retriever = _retriever(client, snapshot)
        evidence = retriever.search(
            RetrievalRequest(queries=(query,), snapshot_id=snapshot, top_k=TOP_K)
        )
        request = caller_catalog(case, message, evidence, definitions=gaps)
        context = ReasoningContext(
            run_id=f"dry-{protocol['experiment_id']}-{name}",
            case_id=case.case_id,
            case_revision=case.case_revision,
            attempt_index=1,
            can_refine=False,
            remaining_model_attempts=0,
            remaining_retrieval_rounds=0,
            query_limit=2,
        )
        size = (
            len(json.dumps(build_grounded_messages(request, context), ensure_ascii=False).encode())
            + 1024
        )
        if size > INPUT_RESERVE:
            raise ProbeRejected()
        arms[name] = {
            "query": query,
            "query_sha256": _sha(query.encode()),
            "evidence": evidence,
            "request": request,
            "prompt_bytes_plus_margin": size,
        }
    return {
        "case": case,
        "conversation": conversation,
        "message": message,
        "gaps": gaps,
        "client": client,
        "snapshot": snapshot,
        "arms": arms,
    }


class _ScopedTransport(httpx.BaseTransport):
    def __init__(self, underlying, ledger, before):
        self.underlying, self.ledger, self.before = underlying, ledger, before
        self.records, self.current = [], None

    def guard(self):
        now = ledger_observation(self.ledger._path)
        if (
            not now["halted"]
            or not _immutable_accounting_preserved(now, self.before)
            or now["counts"].get("reserved", 0)
            or now["unknown_records_sha256"] != self.before["unknown_records_sha256"]
            or not now["continuation"]["active"]
            or now["continuation"]["allowed_model"] != MODEL
            or len(self.records) >= MAX_SENDS
            or Decimal(now["continuation"]["remaining_usd"]) < REQUEST_BOUND
            or Decimal(now["settled_estimated_usd"])
            - Decimal(self.before["settled_estimated_usd"])
            + REQUEST_BOUND
            > BATCH_BOUND
        ):
            raise ReasoningStopped("BudgetExceeded", "budget_stopped")

    def handle_request(self, request):
        record = self.current
        row = self.ledger.get(record["request_id"]) if record else None
        now = ledger_observation(self.ledger._path)
        if (
            record is None
            or len(self.records) >= MAX_SENDS
            or request.method != "POST"
            or str(request.url) != METIS_CHAT_URL
            or row is None
            or row.status != "reserved"
            or row.model != MODEL
            or row.phase != "development"
            or row.amount_usd != REQUEST_BOUND
            or not now["halted"]
            or not _immutable_accounting_preserved(now, self.before)
            or now["counts"].get("reserved", 0) != 1
            or now["unknown_records_sha256"] != self.before["unknown_records_sha256"]
            or now["continuation"]["block_reason"] != "PendingRequest"
            or Decimal(now["settled_estimated_usd"])
            - Decimal(self.before["settled_estimated_usd"])
            + Decimal(now["reserved_usd"])
            > BATCH_BOUND
        ):
            raise ReasoningStopped("BudgetExceeded", "budget_stopped")
        self.records.append(record)
        record["http_send_started"] = True
        response = self.underlying.handle_request(request)
        record["http_status"] = response.status_code
        headers = dict(response.headers)
        headers.pop("content-encoding", None)
        headers.pop("content-length", None)
        return httpx.Response(
            response.status_code,
            headers=headers,
            stream=_DecodedStream(response, record, MODEL),
            extensions=response.extensions,
            request=request,
        )

    def close(self):
        self.underlying.close()


class _SharedTransport(httpx.BaseTransport):
    def __init__(self, scoped):
        self.scoped = scoped

    def handle_request(self, request):
        return self.scoped.handle_request(request)

    def close(self):
        pass


class _Planner:
    def __init__(self, gateway, scoped, expected):
        self.gateway, self.scoped, self.expected = gateway, scoped, expected
        self.latest, self.attempts = None, []

    def plan(self, request, *, context):
        if self.gateway.reasoner.client.is_closed:
            raise ReasoningStopped("LiveCallsDisabled")
        if self.attempts or context.attempt_index != 1 or request != self.expected:
            raise ReasoningStopped("ProviderRequestFailed")
        size = (
            len(json.dumps(build_grounded_messages(request, context), ensure_ascii=False).encode())
            + 1024
        )
        if size > INPUT_RESERVE:
            raise ReasoningStopped("ContextLimitExceeded")
        self.scoped.guard()
        self.latest = request.model_copy(deep=True)
        record = {
            "request_id": request_id_for(context),
            "run_id": context.run_id,
            "case_id": context.case_id,
            "case_revision": context.case_revision,
            "attempt_index": context.attempt_index,
            "prompt_bytes_plus_margin": size,
            "verified_returned_model": None,
            "http_send_started": False,
        }
        self.attempts.append(record)
        self.scoped.current = record
        try:
            return self.gateway.plan(request, context=context)
        finally:
            self.scoped.current = None


def _new_request_accounting(records):
    """Attribute costs to actual sends, retaining unknown costs as unknown."""
    settled, reserved, uncertain = Decimal(0), Decimal(0), Decimal(0)
    incomplete = []
    for record in records:
        row = record["reservation"]
        if row is None or any(
            row[field] != expected
            for field, expected in (
                ("request_id", record["request_id"]),
                ("run_id", record["run_id"]),
                ("case_id", record["case_id"]),
                ("case_revision", record["case_revision"]),
                ("attempt", record["attempt_index"]),
                ("model", MODEL),
                ("phase", "development"),
            )
        ):
            incomplete.append(record["request_id"])
            continue
        if row["status"] == "settled":
            known_cost = get_price(MODEL).cost(row["input_tokens"], row["output_tokens"])
            if known_cost != Decimal(row["cost_usd"]):
                incomplete.append(record["request_id"])
                continue
            settled += known_cost
        elif row["status"] in {"reserved", "uncertain"}:
            if row["status"] == "reserved":
                reserved += Decimal(row["amount_usd"])
            else:
                uncertain += Decimal(row["amount_usd"])
            incomplete.append(record["request_id"])
        elif row["status"] != "released":
            incomplete.append(record["request_id"])
    return {
        "new_settled_estimated_usd": str(settled),
        "new_reserved_usd": str(reserved),
        "new_uncertain_usd": str(uncertain),
        "new_cost_estimated_usd": str(settled) if not incomplete else None,
        "new_request_accounting_complete": not incomplete,
        "unaccounted_request_ids": incomplete,
    }


def execute(protocol, prepared, *, ledger_path, config, before, underlying=None):
    """Caller-root execution; tests require a disposable ledger and MockTransport."""
    if (
        config.model != MODEL
        or config.phase != "development"
        or config.response_mode != "grounded_plan"
        or config.continuation_id != GRANT
        or not config.live_enabled
        or config.input_token_reserve != INPUT_RESERVE
        or config.max_output_tokens != OUTPUT_LIMIT
        or config.max_request_usd != REQUEST_BOUND
    ):
        raise ProbeRejected()
    ledger = BudgetLedger(ledger_path)
    scoped = _ScopedTransport(underlying or httpx.HTTPTransport(retries=0), ledger, before)
    results, gateways, planners = [], [], []
    try:
        for name, arm in prepared["arms"].items():
            scoped.guard()
            gateway = MetisGroundedPlanner(config, ledger, transport=_SharedTransport(scoped))
            gateways.append(gateway)
            planner = _Planner(gateway, scoped, arm["request"])
            planners.append(planner)
            retriever = _retriever(prepared["client"], prepared["snapshot"])
            capture = ReasoningCapture(
                GroundedReasoner(
                    planner,
                    request_factory=lambda case, message, evidence: caller_catalog(
                        case, message, evidence, definitions=prepared["gaps"]
                    ),
                )
            )
            handoff = None
            try:
                result = SupportEngine(
                    retriever,
                    capture,
                    snapshot_id=prepared["snapshot"],
                    limits=RunLimits(
                        max_model_attempts=1,
                        max_retrieval_rounds=1,
                        max_queries_per_round=2,
                        max_steps=8,
                    ),
                ).run(
                    prepared["case"],
                    prepared["message"],
                    run_id=f"query-{protocol['experiment_id']}-{name}-{uuid4().hex[:8]}",
                    initial_query=arm["query"],
                )
                if result.status == "awaiting_approval":
                    handoff = build_handoff(result, capture.last, grounded_request=planner.latest)
                results.append(
                    {
                        "arm": name,
                        "query": arm["query"],
                        "query_sha256": arm["query_sha256"],
                        "result": result.model_dump(mode="json"),
                        "canonical_handoff": handoff.model_dump(mode="json") if handoff else None,
                        "last_grounded_request": planner.latest.model_dump(mode="json")
                        if planner.latest
                        else None,
                        "retrieval": retriever.reads,
                        "reasoning_attempts": planner.attempts,
                    }
                )
            finally:
                gateway.close()
            if result.error_code in {
                "ProviderRequestFailed",
                "ProviderResponseInvalid",
                "ProviderUsageUnknown",
                "ProviderModelMismatch",
                "ContextLimitExceeded",
                "DuplicateModelRequest",
                "LedgerUnavailable",
                "LiveCallsDisabled",
                "UnknownPricing",
                "BudgetExceeded",
                "CostBoundExceeded",
            }:
                break
    except Exception:
        # Any already sent attempt remains charged/held in the original ledger.
        pass
    finally:
        for gateway in gateways:
            gateway.close()
        scoped.close()
    after = ledger_observation(ledger_path)
    # A pre-delegation guard failure can still leave a gateway reservation held.
    # Keep every attempted ID, including attempts that never reached the network.
    attempts = [record for planner in planners for record in planner.attempts]
    for record in attempts:
        record["reservation"] = _plain(ledger.get(record["request_id"]))
    accounting = _new_request_accounting(attempts)
    complete = len(results) == 2 and all(item["canonical_handoff"] is not None for item in results)
    checks = {
        "at_most_two_actual_sends": 0 < len(scoped.records) <= MAX_SENDS,
        "one_attempt_per_arm": all(len(item["reasoning_attempts"]) <= 1 for item in results),
        "clients_closed": all(gateway.reasoner.client.is_closed for gateway in gateways),
        "original_quarantine_preserved": after["original_quarantine_sha256"]
        == before["original_quarantine_sha256"],
        "original_halt_preserved": after["halted"],
        "immutable_grant_and_global_budget_preserved": _immutable_accounting_preserved(
            after, before
        ),
        "only_original_uncertainty": after["unknown_records_sha256"]
        == before["unknown_records_sha256"],
        "batch_estimated_cost_bound": Decimal(after["settled_estimated_usd"])
        - Decimal(before["settled_estimated_usd"])
        <= BATCH_BOUND,
        "both_registered_arms_completed": complete,
        "new_request_accounting_complete": accounting["new_request_accounting_complete"],
    }
    return {
        "schema_version": 1,
        "protocol_id": protocol["protocol_id"],
        "experiment_id": protocol["experiment_id"],
        "checks": checks,
        "accepted_operations": all(checks.values()),
        "comparison_complete": complete,
        "actual_sends": len(scoped.records),
        "arms": results,
        "provider_observations": scoped.records,
        "model_request_observations": attempts,
        "ledger_after": after,
        **accounting,
        "ledger_settled_delta_estimated_usd": str(
            Decimal(after["settled_estimated_usd"]) - Decimal(before["settled_estimated_usd"])
        ),
        "ledger_delta_scope": "Whole shared ledger between snapshots; new-request costs are attributed by exact send IDs separately.",
        "actual_account_charge_usd": None,
        "tracker_actions": 0,
        "tracker_staging": False,
        "proposal_auto_approved": False,
        "source_policy": "Same authoritative case, composed raw history and curated current-unknown catalog; only the initial retrieval query changes. Real docs-only lexical Chroma, top_k=1; no corpus/ranking/independent-quality claim.",
        "semantic_review": "pending separate whole-output/source-backed review",
        "exposed_development_only": True,
        "quality_claim": False,
        "heldout_claim": False,
        "c5_reconciled": False,
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
    keys = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        name, separator, value = line.strip().removeprefix("export ").partition("=")
        if separator and name.strip() == "METIS_API_KEY":
            value = value.strip()
            if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
                value = value[1:-1]
            keys.append(value)
    if len(keys) != 1:
        raise ProbeRejected()
    return keys[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=ROOT / "runtime/budget.sqlite3")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    try:
        protocol, fixture, registration = load_registration(ROOT, args.ledger)
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            prepared = prepare_inputs(protocol, fixture)
        registration["preflight_arms"] = {
            name: {
                "query": arm["query"],
                "query_sha256": arm["query_sha256"],
                "prompt_bytes_plus_margin": arm["prompt_bytes_plus_margin"],
                "evidence_sha256": _sha(arm["evidence"].model_dump_json().encode()),
            }
            for name, arm in prepared["arms"].items()
        }
        if ledger_observation(args.ledger) != registration["ledger_before"]:
            raise ProbeRejected()
        if not args.live:
            print(
                json.dumps(
                    {
                        "eligible_read_only": True,
                        "paid_requests": 0,
                        "batch_cap_usd": str(BATCH_BOUND),
                        "max_actual_sends": MAX_SENDS,
                        "both_prompts_fit": True,
                        "index_native_bookkeeping_byte_immutability_claim": False,
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
        source_before_key = source_observation(ROOT, registration["fixture_path"])
        if (
            source_before_key != {key: registration[key] for key in source_before_key}
            or ledger_observation(args.ledger) != registration["ledger_before"]
        ):
            raise ProbeRejected()
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
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            receipt = execute(
                protocol,
                prepared,
                ledger_path=args.ledger,
                config=config,
                before=registration["ledger_before"],
            )
        try:
            source_after = source_observation(ROOT, registration["fixture_path"])
            unchanged = source_after == {key: registration[key] for key in source_after}
        except Exception:
            source_after, unchanged = None, False
        receipt["registration"] = registration
        receipt["source_after"] = source_after
        receipt["checks"]["registered_pushed_source_unchanged"] = unchanged
        receipt["accepted_operations"] = receipt["accepted_operations"] and unchanged
        with (destination / "receipt.json").open("x", encoding="utf-8") as stream:
            json.dump(receipt, stream, ensure_ascii=True, indent=2)
            stream.write("\n")
        print(
            json.dumps(
                {
                    "actual_sends": receipt["actual_sends"],
                    "comparison_complete": receipt["comparison_complete"],
                    "accepted_operations": receipt["accepted_operations"],
                    "new_cost_estimated_usd": receipt["new_cost_estimated_usd"],
                    "new_settled_estimated_usd": receipt["new_settled_estimated_usd"],
                    "new_reserved_usd": receipt["new_reserved_usd"],
                    "new_uncertain_usd": receipt["new_uncertain_usd"],
                    "new_request_accounting_complete": receipt["new_request_accounting_complete"],
                    "quality_claim": False,
                    "actual_account_charge_usd": None,
                    "c5_reconciled": False,
                }
            )
        )
        if not receipt["accepted_operations"]:
            raise ProbeRejected()
    except Exception:
        print(json.dumps({"code": "RetrievalContextLiveProbeRejected", "automatic_retry": False}))
        raise SystemExit(1) from None
