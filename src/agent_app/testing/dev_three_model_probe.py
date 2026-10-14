"""Pre-registered dev-only model comparison; no ordinary live halt exception.

The existing conditional HTTP runner is reused with an explicit accounting scope.
Evidence is fixed, not searched: these observations concern core decisions only.
Future turns, gold and scripted answers remain local to the fixture controller.
"""

import hashlib
import json
import sqlite3
import subprocess
from contextlib import closing
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from uuid import NAMESPACE_URL, uuid5

import httpx
from fastapi.testclient import TestClient

from agent_app import api
from agent_app.contracts import GroundedPlan, ReasoningContext
from agent_app.evaluation.live import _DecodedStream
from agent_app.evaluation.routes import RouteGraph
from agent_app.evaluation.runner import CaseRun, Usage, _decide, collect
from agent_app.llm.config import METIS_CHAT_URL, MetisConfig
from agent_app.llm.grounded import MetisGroundedPlanner
from agent_app.llm.metis import request_id_for
from agent_app.llm.pricing import get_price
from agent_app.orchestration.ports import ReasoningStopped
from agent_app.reasoning.catalog import caller_catalog, load_user_gap_vocabulary
from agent_app.reasoning.grounding import GroundedReasoner, build_grounded_messages
from agent_app.testing.fakes import FakeRetriever
from agent_app.testing.plan_observation import observe_plan_output
from agent_app.tracker.dummy_tracker import DummyTracker

PROTOCOL = Path("experiments/dev_three_baseline/model-protocol-v1.json")
MODEL = "gpt-4o-mini"
INPUT_RESERVE = 16384
OUTPUT_LIMIT = 1024
MAX_SENDS = 24
CAP = Decimal("0.10")
ARMS = ("runtime_catalog", "reviewed_user_gaps")
INPUT_PROFILES = {"dev-case-a": INPUT_RESERVE, "dev-case-b": INPUT_RESERVE, "dev-case-c": 24576}


class DevProbeRejected(ValueError):
    def __init__(self):
        super().__init__("DevThreeModelProbeRejected")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def contains_secret(value, secret):
    if isinstance(value, str):
        return secret in value
    if isinstance(value, dict):
        return any(
            contains_secret(key, secret) or contains_secret(item, secret)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(contains_secret(item, secret) for item in value)
    return False


def source_observation(root, protocol_path=PROTOCOL):
    paths = sorted(
        set(
            [path.relative_to(root).as_posix() for path in (root / "src/agent_app").rglob("*.py")]
            + ["scripts/dev_three_model_probe.py", "pyproject.toml", "uv.lock"]
            + [
                path.relative_to(root).as_posix()
                for path in (root / "data/evaluation/dev-three-v1").rglob("*.json")
            ]
            + [protocol_path.as_posix()]
            + [
                path.relative_to(root).as_posix()
                for path in (root / "experiments/dev_three_baseline").glob(
                    "model-live-receipt-*.json"
                )
            ]
            + [
                "streamlit-data-for-dev-test/sources/docs_scope_candidates.jsonl",
                "streamlit-data-for-dev-test/sources/docstrings_scope_candidates.jsonl",
            ]
        )
    )
    hashes = {name: sha((root / name).read_bytes()) for name in paths}
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    clean = not subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=root, text=True
    ).strip()
    for name, digest in hashes.items():
        actual = subprocess.check_output(
            ["git", "show", f"HEAD:{name}"], cwd=root, stderr=subprocess.DEVNULL
        )
        if sha(actual) != digest:
            raise DevProbeRejected()
    return {"source_commit": commit, "source_clean": clean, "source_hashes": hashes}


def ledger_observation(path):
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        meta = dict(db.execute("SELECT * FROM ledger_meta").fetchone())
        unknown = [
            dict(row)
            for row in db.execute(
                "SELECT * FROM reservations WHERE status='uncertain' ORDER BY request_id"
            )
        ]
        grants = [
            dict(row)
            for row in db.execute("SELECT * FROM ledger_continuations ORDER BY authorization_id")
        ]
        counts = dict(db.execute("SELECT status, count(*) FROM reservations GROUP BY status"))
    return {
        "db_sha256": sha(path.read_bytes()),
        "meta_sha256": sha(json.dumps(meta, sort_keys=True).encode()),
        "unknown_sha256": sha(json.dumps(unknown, sort_keys=True).encode()),
        "old_grants_sha256": sha(json.dumps(grants, sort_keys=True).encode()),
        "halted": bool(meta["halted"]),
        "limit_nanos": meta["limit_nanos"],
        "counts": counts,
        "quarantined_request_id": unknown[0]["request_id"] if len(unknown) == 1 else None,
    }


def invocation(protocol, arm):
    return f"{protocol['experiment_id']}:{arm}"


def execution_jobs(protocol, fixtures):
    by_id = {fixture.case["case_id"]: fixture for fixture in fixtures}
    if "jobs" not in protocol:
        return tuple((arm, fixture) for arm in ARMS for fixture in fixtures)
    definitions = protocol["jobs"]
    if type(definitions) is not list or not 1 <= len(definitions) <= 6:
        raise DevProbeRejected()
    pairs = []
    for item in definitions:
        if (
            type(item) is not dict
            or set(item) != {"arm", "case_id"}
            or item["arm"] not in ARMS
            or item["case_id"] not in by_id
        ):
            raise DevProbeRejected()
        pair = (item["arm"], item["case_id"])
        if pair in pairs:
            raise DevProbeRejected()
        pairs.append(pair)
    return tuple((arm, by_id[case_id]) for arm, case_id in pairs)


def request_slots(protocol, fixtures):
    """Freeze exact caller contexts before authorization, including repair slots."""
    from agent_app.llm.budget import ExperimentRequestSlot

    slots = []
    for arm, fixture in execution_jobs(protocol, fixtures):
        for revision, turn in enumerate(fixture.data["turns"], start=1):
            case_id = fixture.case["case_id"]
            input_reserve = INPUT_PROFILES[case_id]
            bound = get_price(MODEL).cost(input_reserve, OUTPUT_LIMIT)
            identity = (
                f"{invocation(protocol, arm)}:{fixture.data['fixture_id']}:{case_id}:{turn['id']}"
            )
            run_id = str(uuid5(NAMESPACE_URL, identity))
            for attempt in (1, 2):
                context = ReasoningContext(
                    run_id=run_id,
                    case_id=case_id,
                    case_revision=revision,
                    attempt_index=attempt,
                )
                slots.append(
                    ExperimentRequestSlot(
                        request_id=request_id_for(context),
                        run_id=run_id,
                        case_id=case_id,
                        case_revision=revision,
                        attempt=attempt,
                        model=MODEL,
                        phase="development",
                        input_token_reserve=input_reserve,
                        max_output_tokens=OUTPUT_LIMIT,
                        amount_usd=bound,
                    )
                )
    if not 1 <= len(slots) <= MAX_SENDS or sum(slot.amount_usd for slot in slots) > CAP:
        raise DevProbeRejected()
    return tuple(slots)


def preflight(root, ledger_path, protocol_path=PROTOCOL):
    protocol_path = Path(protocol_path)
    resolved = (root / protocol_path).resolve()
    if (
        not resolved.is_relative_to((root / "experiments/dev_three_baseline").resolve())
        or resolved.suffix != ".json"
    ):
        raise DevProbeRejected()
    protocol_path = resolved.relative_to(root)
    raw = resolved.read_bytes()
    protocol = json.loads(raw)
    before = ledger_observation(ledger_path)
    source = source_observation(root, protocol_path)
    if (
        protocol["protocol_id"]
        not in {
            "dev-three-controlled-model-v1",
            "dev-three-controlled-model-v2",
            "dev-three-controlled-model-v3",
        }
        or ledger_path.resolve() != (root / "runtime/budget.sqlite3").resolve()
        or protocol["ledger_before_sha256"] != before["db_sha256"]
        or not before["halted"]
        or before["counts"].get("reserved", 0)
        or before["counts"].get("uncertain", 0) != 1
        or before["limit_nanos"] != 4_500_000_000
        or not source["source_clean"]
        or protocol["gateway"]
        != {
            "model": MODEL,
            "input_token_reserve": INPUT_RESERVE,
            "input_profiles": INPUT_PROFILES,
            "max_output_tokens": OUTPUT_LIMIT,
            "max_sends": MAX_SENDS,
            "experiment_cap_usd": str(CAP),
        }
        or protocol["arms"] != list(ARMS)
    ):
        raise DevProbeRejected()
    for name, digest in protocol["input_pins"].items():
        path = (root / name).resolve()
        if (
            not path.is_relative_to((root / "data/evaluation/dev-three-v1").resolve())
            or sha(path.read_bytes()) != digest
        ):
            raise DevProbeRejected()
    paths = [(root / name).resolve() for name in protocol["fixture_paths"]]
    if len(paths) != 3 or any(
        path.as_posix().removeprefix(root.as_posix() + "/") not in protocol["input_pins"]
        for path in paths
    ):
        raise DevProbeRejected()
    fixtures = collect(paths, mode="live")
    for fixture in fixtures:
        if fixture.case["split"] != "dev" or len(fixture.data["turns"]) != 2:
            raise DevProbeRejected()
        RouteGraph.from_fixture(fixture.data)
        evidence_name = fixture.data["evidence_source"]["path"]
        if evidence_name not in protocol["input_pins"]:
            raise DevProbeRejected()
        evidence_payload = json.loads((root / evidence_name).read_bytes())
        for name, expected in evidence_payload["source_pins"].items():
            path = (root / name).resolve()
            if (
                not path.is_relative_to((root / "streamlit-data-for-dev-test").resolve())
                or sha(path.read_bytes()) != expected
            ):
                raise DevProbeRejected()
    vocabulary_name = protocol["user_gap_vocabulary_path"]
    vocabulary_path = (root / vocabulary_name).resolve()
    if vocabulary_name not in protocol["input_pins"] or not vocabulary_path.is_relative_to(
        (root / "data/evaluation/dev-three-v1").resolve()
    ):
        raise DevProbeRejected()
    if protocol["protocol_id"] == "dev-three-controlled-model-v2":
        predecessor = protocol["predecessor"]
        previous_path = (root / predecessor["receipt_path"]).resolve()
        if (
            not previous_path.is_relative_to((root / "experiments/dev_three_baseline").resolve())
            or sha(previous_path.read_bytes()) != predecessor["sha256"]
        ):
            raise DevProbeRejected()
        previous = json.loads(previous_path.read_bytes())
        if (
            previous["protocol_id"] != "dev-three-controlled-model-v1"
            or previous["scope_closed"] is not True
        ):
            raise DevProbeRejected()
        observed = {(case["arm"], case["case_id"]) for case in previous["cases"]}
        all_jobs = {(arm, fixture.case["case_id"]) for arm in ARMS for fixture in fixtures}
        requested = {
            (arm, fixture.case["case_id"]) for arm, fixture in execution_jobs(protocol, fixtures)
        }
        if (
            requested != all_jobs - observed
            or protocol.get("continue_independent_jobs") is not True
        ):
            raise DevProbeRejected()
        if any(
            previous["registration"]["source_hashes"].get(name) != digest
            for name, digest in protocol["input_pins"].items()
        ):
            raise DevProbeRejected()
    elif protocol["protocol_id"] == "dev-three-controlled-model-v3":
        predecessor = protocol["predecessor"]
        previous_path = (root / predecessor["receipt_path"]).resolve()
        if (
            not previous_path.is_relative_to((root / "experiments/dev_three_baseline").resolve())
            or sha(previous_path.read_bytes()) != predecessor["sha256"]
        ):
            raise DevProbeRejected()
        previous = json.loads(previous_path.read_bytes())
        if (
            previous["protocol_id"] != "dev-three-controlled-model-v2"
            or previous["scope_closed"] is not True
            or protocol.get("grounded_decision_contracts") is not True
            or protocol.get("continue_independent_jobs") is not True
            or protocol["treatment_id"] != "current-decision-field-contracts-v1"
            or {(arm, f.case["case_id"]) for arm, f in execution_jobs(protocol, fixtures)}
            != {("reviewed_user_gaps", f.case["case_id"]) for f in fixtures}
            or any(
                previous["registration"]["source_hashes"].get(name) != digest
                for name, digest in protocol["input_pins"].items()
            )
        ):
            raise DevProbeRejected()
    elif "jobs" in protocol or protocol.get("continue_independent_jobs"):
        raise DevProbeRejected()
    if (
        protocol["protocol_id"] != "dev-three-controlled-model-v3"
        and protocol.get("grounded_decision_contracts", False) is not False
    ):
        raise DevProbeRejected()
    definitions = load_user_gap_vocabulary(str(vocabulary_path))
    slots = request_slots(protocol, fixtures)
    slots_sha256 = sha(
        json.dumps([asdict(slot) for slot in slots], default=str, sort_keys=True).encode()
    )
    if protocol["request_slots_sha256"] != slots_sha256:
        raise DevProbeRejected()
    return (
        protocol,
        fixtures,
        definitions,
        slots,
        {
            **source,
            "protocol_path": protocol_path.as_posix(),
            "protocol_sha256": sha(raw),
            "ledger_before": before,
            "request_slots_sha256": slots_sha256,
        },
    )


class ScopedUsage:
    """The controlled driver gates by exact scope; accounting uses the real ledger.

    `ledger=None` prevents CaseRun's ordinary-live/global-halt preflight; this
    bespoke path performs scope eligibility before every planner reserve/send.
    It never disguises the ledger snapshot or changes ordinary runner behavior.
    """

    ledger = None

    def __init__(self, ledger):
        self.actual = Usage(ledger)

    def measure(self, contexts):
        return self.actual.measure(contexts)


class ScopeTransport(httpx.BaseTransport):
    def __init__(self, underlying, ledger, scope_id, before):
        self.underlying, self.ledger, self.scope_id, self.before = (
            underlying,
            ledger,
            scope_id,
            before,
        )
        self.current = None
        self.records = []
        self.on_send = None

    def handle_request(self, request):
        reservation = self.ledger.get(self.current) if self.current else None
        scope = self.ledger.experiment_scope_status(self.scope_id)
        now = ledger_observation(self.ledger._path)
        if (
            len(self.records) >= MAX_SENDS
            or str(request.url) != METIS_CHAT_URL
            or request.method != "POST"
            or reservation is None
            or reservation.status != "reserved"
            or reservation.model != MODEL
            or reservation.phase != "development"
            or reservation.amount_usd
            != get_price(MODEL).cost(
                INPUT_PROFILES.get(reservation.case_id, INPUT_RESERVE), OUTPUT_LIMIT
            )
            or scope.block_reason != "PendingRequest"
            or now["counts"].get("reserved") != 1
            or any(
                now[name] != self.before[name]
                for name in ("meta_sha256", "unknown_sha256", "old_grants_sha256")
            )
        ):
            raise ReasoningStopped("BudgetExceeded", "budget_stopped")
        record = {
            "request_id": self.current,
            "http_send_started": False,
            "verified_returned_model": None,
        }
        self.records.append(record)
        if self.on_send is not None:
            self.on_send()
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


class SharedTransport(httpx.BaseTransport):
    def __init__(self, counted):
        self.counted = counted

    def handle_request(self, request):
        return self.counted.handle_request(request)

    def close(self):
        pass


class ScopedPlanner:
    def __init__(self, gateway, counted, records):
        self.gateway, self.counted, self.records = gateway, counted, records
        self.latest = None

    def supplied_request(self):
        return self.latest.model_copy(deep=True) if self.latest else None

    def plan(self, request, *, context):
        record = {
            "context": context.model_dump(mode="json"),
            "request": request.model_dump(mode="json"),
            "plan": None,
            "error_code": None,
        }
        self.records.append(record)
        self.latest = request.model_copy(deep=True)
        try:
            if not self.counted.ledger.experiment_scope_status(self.counted.scope_id).active:
                raise ReasoningStopped("BudgetExceeded", "budget_stopped")
            if (
                len(
                    json.dumps(
                        build_grounded_messages(
                            request,
                            context,
                            decision_contracts=self.gateway.config.grounded_decision_contracts,
                        ),
                        ensure_ascii=False,
                    ).encode()
                )
                + 1024
                > self.gateway.config.input_token_reserve
            ):
                raise ReasoningStopped("ContextLimitExceeded")
            self.counted.current = request_id_for(context)
            plan = self.gateway.plan(request, context=context)
            record["output_sha256"] = sha(plan.encode())
            secret = self.gateway.config.api_key.get_secret_value()
            try:
                decoded = json.loads(plan)
            except ValueError:
                decoded = plan
            if contains_secret(decoded, secret):
                record["credential_echo_rejected"] = True
                raise ReasoningStopped("ProviderResponseInvalid")
            record["schema_observation"] = observe_plan_output(plan)
            try:
                record["plan"] = GroundedPlan.model_validate_json(plan).model_dump(mode="json")
            except ValueError:
                record["plan"] = None
            return plan
        except ReasoningStopped as error:
            record["error_code"] = error.code
            raise
        finally:
            self.counted.current = None


def run_trial(
    protocol, fixtures, definitions, ledger, config, before, *, underlying=None, checkpoint=None
):
    """Calls real model only with caller-created config/scope; tests intercept wire."""
    if (
        config.continuation_id != protocol["scope_id"]
        or config.model != MODEL
        or config.response_mode != "grounded_plan"
        or config.grounded_source_gap_handoff
        or config.grounded_decision_contracts != protocol.get("grounded_decision_contracts", False)
    ):
        raise DevProbeRejected()
    counted = ScopeTransport(
        underlying or httpx.HTTPTransport(retries=0), ledger, config.continuation_id, before
    )
    cases, attempts = [], []
    if checkpoint:
        counted.on_send = lambda: checkpoint(
            {
                "event": "provider_handoff_registered_after_reservation",
                "cases": cases,
                "attempts": attempts,
                "provider_sends": counted.records,
            }
        )
    stopped = False
    try:
        jobs = execution_jobs(protocol, fixtures)
        for arm, fixture in jobs:
            if not ledger.experiment_scope_status(config.continuation_id).active:
                stopped = True
                break
            ports = []

            def adapters(_case_id, turn, fixture=fixture, ports=ports, arm=arm):
                bundle = fixture.bundles[turn["evidence_bundle"]]
                reserve = INPUT_PROFILES[fixture.case["case_id"]]
                case_config = MetisConfig.model_validate(
                    {
                        **config.model_dump(),
                        "input_token_reserve": reserve,
                        "max_request_usd": get_price(MODEL).cost(reserve, OUTPUT_LIMIT),
                    }
                )
                gateway = MetisGroundedPlanner(
                    case_config, ledger, transport=SharedTransport(counted)
                )
                ports.append(gateway)
                planner = ScopedPlanner(gateway, counted, attempts)
                selected = definitions if arm == "reviewed_user_gaps" else ()
                return api.RunAdapters(
                    retriever=FakeRetriever([bundle, bundle]),
                    reasoner=GroundedReasoner(
                        planner,
                        request_factory=lambda case, message, evidence: caller_catalog(
                            case, message, evidence, definitions=selected
                        ),
                    ),
                    snapshot_id=bundle.snapshot_id,
                    grounded_request_supplier=planner.supplied_request,
                    cleanup=gateway.close,
                )

            case_run = CaseRun(
                fixture,
                adapters,
                ScopedUsage(ledger),
                mode="live",
                invocation_id=invocation(protocol, arm),
                route_graph=RouteGraph.from_fixture(fixture.data),
            )
            try:
                with (
                    patch.object(api, "_cases", {}),
                    patch.object(api, "tracker", DummyTracker()),
                ):
                    with TestClient(api.app) as client:
                        case_run.run(client)
                        if (
                            fixture.data["turns"][1]["expect"].get("previous_proposal_now_stale")
                            and len(case_run.steps) >= 2
                        ):
                            first = case_run.steps[0].get("proposal", {})
                            if first.get("proposal_id"):
                                view_before = client.get(f"/cases/{fixture.case['case_id']}").json()
                                wires_before = len(counted.records)
                                refused = _decide(client, fixture.case["case_id"], first, "approve")
                                case_run.record.check(
                                    "correction",
                                    "live stale unexecuted approval rejected",
                                    refused.status_code == 409,
                                    refused.status_code,
                                )
                                case_run.record.check(
                                    "correction",
                                    "stale approval leaves state and provider wire unchanged",
                                    client.get(f"/cases/{fixture.case['case_id']}").json()
                                    == view_before
                                    and len(counted.records) == wires_before,
                                )
            finally:
                for gateway in ports:
                    gateway.reasoner.client.close()
            for step in case_run.steps:
                step.pop("view_after", None)
            cases.append(
                {
                    "arm": arm,
                    "case_id": fixture.case["case_id"],
                    "fixture_id": fixture.data["fixture_id"],
                    "fixture_sha256": fixture.sha256,
                    "coverage_complete": case_run.route_complete,
                    "selected_turns": case_run.route_visits,
                    "checks": case_run.record.checks,
                    "steps": case_run.steps,
                }
            )
            if checkpoint:
                checkpoint(
                    {"cases": cases, "attempts": attempts, "provider_sends": counted.records}
                )
            # A stopped request/coverage gap is preserved, not silently rerun.
            if not case_run.route_complete and not protocol.get("continue_independent_jobs", False):
                stopped = True
                break
            if not ledger.experiment_scope_status(config.continuation_id).active and len(
                cases
            ) < len(jobs):
                stopped = True
                break
    finally:
        counted.close()
    after = ledger_observation(ledger._path)
    usage = Usage(ledger).measure(
        [ReasoningContext.model_validate(item["context"]) for item in attempts]
    )
    return {
        "schema_version": 1,
        "protocol_id": protocol["protocol_id"],
        "mode": "live_controlled_core",
        "quality_claim": False,
        "actual_rag_quality": False,
        "c5_reconciled": False,
        "human_review": False,
        "human_usefulness": None,
        "maintainer": "registered_fixture_script",
        "tracker": "process_memory_dummy_tracker",
        "evidence": "fixed_registered_source_bundles",
        "source_conditions": (
            "Fixed evidence/current inputs and reviewed vocabulary match V2; only opt-in decision field contracts differ."
            if config.grounded_decision_contracts
            else "same evidence per case/turn in both arms; only reviewed user vocabulary differs"
        ),
        "grounded_decision_contracts": config.grounded_decision_contracts,
        "scope_id": config.continuation_id,
        "cases": cases,
        "attempts": attempts,
        "provider_sends": counted.records,
        "actual_sends": sum(item["http_send_started"] for item in counted.records),
        "accounting": usage,
        "planned_case_arm_runs": len(jobs),
        "visited_case_arm_runs": len(cases),
        "executed_turns": sum("usage" in step for case in cases for step in case["steps"]),
        "completed_case_arm_runs": sum(item["coverage_complete"] for item in cases),
        "stopped_early": stopped,
        "ledger_after": after,
        "original_accounting_preserved": all(
            after[name] == before[name]
            for name in ("meta_sha256", "unknown_sha256", "old_grants_sha256")
        ),
    }
