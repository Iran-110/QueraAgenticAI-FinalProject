"""Finite, preregistered fixed-evidence repetitions; no ordinary live bypass.

The historical three-dev probe and production ports are unchanged. The existing
HTTP conditional runner controls future replies; only current inputs reach the
planner. Four separate paired rounds have immutable request identities.
"""

import json
import sqlite3
import subprocess
from contextlib import closing
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch
from uuid import NAMESPACE_URL, uuid5

import httpx
from fastapi.testclient import TestClient

from agent_app import api
from agent_app.contracts import EvidenceBundle, GroundedGap, ReasoningContext
from agent_app.evaluation.routes import RouteGraph
from agent_app.evaluation.runner import CaseRun, Fixture, Usage, _decide, collect
from agent_app.llm.budget import ExperimentRequestSlot
from agent_app.llm.config import MetisConfig
from agent_app.llm.grounded import MetisGroundedPlanner
from agent_app.llm.metis import request_id_for
from agent_app.llm.pricing import get_price
from agent_app.orchestration import SupportEngine
from agent_app.reasoning.catalog import caller_catalog, load_user_gap_vocabulary
from agent_app.reasoning.grounding import GroundedReasoner, make_grounded_request
from agent_app.testing.dev_three_model_probe import (
    CAP,
    INPUT_PROFILES,
    MODEL,
    OUTPUT_LIMIT,
    DevProbeRejected,
    ScopedPlanner,
    ScopedUsage,
    ScopeTransport,
    SharedTransport,
    ledger_observation,
    sha,
)
from agent_app.testing.dev_three_model_probe import (
    INPUT_RESERVE as INPUT_RESERVE,
)
from agent_app.testing.fakes import FakeRetriever
from agent_app.tracker.dummy_tracker import DummyTracker

PACKET = Path("experiments/core_stability_adversarial")
PROTOCOL = PACKET / "stability-protocol-v1.json"
FIXTURE_PATHS = (
    "data/evaluation/dev-three-v1/cases/pilot-12782-v1.json",
    "data/evaluation/dev-three-v1/cases/icon-9770-v1.json",
    "data/evaluation/dev-three-v1/cases/enum-8129-v1.json",
)
VOCABULARY = "data/evaluation/dev-three-v1/user-gap-vocabulary-v1.json"
ARMS = ("B_reviewed_gaps", "C_decision_guidance")


def stable_batches():
    """Counterbalance each family twice in each order, without selective reruns."""
    families = ("dev-case-a", "dev-case-b", "dev-case-c")
    batches = []
    for repetition in range(1, 5):
        offset = (repetition - 1) % 3
        order = families[offset:] + families[:offset]
        arms = ARMS if repetition % 2 else tuple(reversed(ARMS))
        jobs = [
            {
                "job_id": f"r{repetition}:{case_id}:{arm}",
                "case_id": case_id,
                "arm": arm,
                "round": repetition,
                "decision_contracts": arm == ARMS[1],
            }
            for case_id in order
            for arm in arms
        ]
        batches.append({"batch_id": f"stability-r{repetition}", "kind": "stability", "jobs": jobs})
    return batches


def invocation(protocol, job):
    return f"{protocol['experiment_id']}:{job['job_id']}"


def adversarial_jobs(packet, proposal):
    by_id = {job["job_id"]: job for job in packet["jobs"]}
    order = proposal["balanced_job_order"]
    if len(order) != 6 or len(by_id) != 6 or set(order) != set(by_id):
        raise DevProbeRejected()
    return [
        {
            "job_id": job["job_id"],
            "fixture_id": job["fixture"]["fixture_id"],
            "case_id": job["case_id"],
            "arm": job["condition"],
            "round": 1,
            "decision_contracts": True,
            "conflict_groups": job["conflict_groups"],
            "catalog_overrides": job["catalog_overrides"],
            "evidence_scope": job["evidence_scope"],
        }
        for job in (by_id[name] for name in order)
    ]


def slots_for_batch(protocol, batch, fixtures):
    slots = []
    for job in batch["jobs"]:
        fixture = fixtures[job.get("fixture_id", job["case_id"])]
        case_id = fixture.case["case_id"]
        reserve = INPUT_PROFILES[case_id]
        for revision, turn in enumerate(fixture.data["turns"], start=1):
            identity = (
                f"{invocation(protocol, job)}:{fixture.data['fixture_id']}:{case_id}:{turn['id']}"
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
                        input_token_reserve=reserve,
                        max_output_tokens=OUTPUT_LIMIT,
                        amount_usd=get_price(MODEL).cost(reserve, OUTPUT_LIMIT),
                    )
                )
    if (
        not 1 <= len(slots) <= 24
        or len({slot.request_id for slot in slots}) != len(slots)
        or sum(slot.amount_usd for slot in slots) > CAP
    ):
        raise DevProbeRejected()
    return tuple(slots)


def slots_sha256(slots):
    return sha(json.dumps([asdict(slot) for slot in slots], default=str, sort_keys=True).encode())


def source_observation(root, protocol_path, pins):
    names = sorted(
        {
            *(path.relative_to(root).as_posix() for path in (root / "src/agent_app").rglob("*.py")),
            "scripts/core_stability_probe.py",
            "pyproject.toml",
            "uv.lock",
            protocol_path.as_posix(),
            *pins,
        }
    )
    hashes = {name: sha((root / name).read_bytes()) for name in names}
    for name, digest in hashes.items():
        raw = subprocess.check_output(
            ["git", "show", f"HEAD:{name}"], cwd=root, stderr=subprocess.DEVNULL
        )
        if sha(raw) != digest:
            raise DevProbeRejected()
    return {
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip(),
        "source_clean": not subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=root, text=True
        ).strip(),
        "source_hashes": hashes,
    }


def fixtures_for(root, protocol):
    fixtures = {
        f.case["case_id"]: f for f in collect([root / p for p in FIXTURE_PATHS], mode="live")
    }
    if protocol["protocol_id"] == "core-stability-v1":
        return fixtures
    packet_path = root / PACKET / "adversarial-packet-v1.json"
    packet = json.loads(packet_path.read_bytes())
    for job in packet["jobs"]:
        data = job["fixture"]
        fixture = Fixture(
            packet_path,
            data,
            {
                name: EvidenceBundle.model_validate(bundle)
                for name, bundle in job["bundles"].items()
            },
            sha(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()),
        )
        if fixture.case["split"] != "dev" or fixture.case["test_eligible"] is not False:
            raise DevProbeRejected()
        RouteGraph.from_fixture(data)
        fixtures[data["fixture_id"]] = fixture
    return fixtures


def preflight(root, ledger_path, protocol_path=PROTOCOL):
    path = (root / protocol_path).resolve()
    if not path.is_relative_to((root / PACKET).resolve()) or path.suffix != ".json":
        raise DevProbeRejected()
    relative = path.relative_to(root)
    protocol = json.loads(path.read_bytes())
    before = ledger_observation(ledger_path)
    if (
        protocol["protocol_id"] not in ("core-stability-v1", "core-adversarial-v1")
        or protocol["ledger_before_sha256"] != before["db_sha256"]
        or ledger_path.resolve() != (root / "runtime/budget.sqlite3").resolve()
        or not before["halted"]
        or before["counts"].get("reserved", 0)
        or before["counts"].get("uncertain", 0) != 1
        or before["limit_nanos"] != 4_500_000_000
        or protocol["renderer_source_gap_handoff"] is not True
        or protocol["model"] != MODEL
        or protocol["max_output_tokens"] != OUTPUT_LIMIT
        or protocol["scope_cap_usd"] != str(CAP)
        or protocol["user_gap_vocabulary_path"] != VOCABULARY
    ):
        raise DevProbeRejected()
    pins = protocol["input_pins"]
    for name, digest in pins.items():
        pin = (root / name).resolve()
        if (
            not any(
                pin.is_relative_to((root / allowed).resolve())
                for allowed in ("data/evaluation/dev-three-v1", PACKET)
            )
            or sha(pin.read_bytes()) != digest
        ):
            raise DevProbeRejected()
    if not {*FIXTURE_PATHS, VOCABULARY} <= set(pins):
        raise DevProbeRejected()
    source = source_observation(root, relative, pins)
    if not source["source_clean"]:
        raise DevProbeRejected()
    fixtures = fixtures_for(root, protocol)
    for fixture in fixtures.values():
        if fixture.case["test_eligible"] is not False or fixture.case["split"] != "dev":
            raise DevProbeRejected()
        source_name = fixture.data.get("evidence_source", {}).get("path")
        if source_name and source_name not in pins:
            raise DevProbeRejected()
    evidence = json.loads((root / "data/evaluation/dev-three-v1/evidence-v1.json").read_bytes())
    for name, digest in evidence["source_pins"].items():
        pin = (root / name).resolve()
        if (
            not pin.is_relative_to((root / "streamlit-data-for-dev-test").resolve())
            or sha(pin.read_bytes()) != digest
        ):
            raise DevProbeRejected()
    if protocol["protocol_id"] == "core-stability-v1":
        expected = stable_batches()
        actual = [
            {key: b[key] for key in ("batch_id", "kind", "jobs")} for b in protocol["batches"]
        ]
        if actual != expected:
            raise DevProbeRejected()
    else:
        packet = json.loads((root / PACKET / "adversarial-packet-v1.json").read_bytes())
        proposal = json.loads(
            (root / PACKET / "adversarial-protocol-proposal-v1.json").read_bytes()
        )
        jobs = adversarial_jobs(packet, proposal)
        if (
            len(protocol["batches"]) != 1
            or protocol["batches"][0]["kind"] != "adversarial"
            or protocol["batches"][0]["jobs"] != jobs
        ):
            raise DevProbeRejected()
    slots = {b["batch_id"]: slots_for_batch(protocol, b, fixtures) for b in protocol["batches"]}
    scope_ids = [b["scope_id"] for b in protocol["batches"]]
    if len(set(scope_ids)) != len(scope_ids) or any(
        slots_sha256(slots[b["batch_id"]]) != b["request_slots_sha256"] for b in protocol["batches"]
    ):
        raise DevProbeRejected()
    with closing(sqlite3.connect(ledger_path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        existing = {row[0] for row in db.execute("SELECT authorization_id FROM experiment_scopes")}
    if set(scope_ids) & existing:
        raise DevProbeRejected()
    definitions = load_user_gap_vocabulary(str(root / VOCABULARY))
    return (
        protocol,
        fixtures,
        definitions,
        slots,
        {
            **source,
            "protocol_path": relative.as_posix(),
            "protocol_sha256": sha(path.read_bytes()),
            "ledger_before": before,
        },
    )


def run_batch(
    protocol,
    batch,
    fixtures,
    definitions,
    ledger,
    config,
    before,
    *,
    underlying=None,
    checkpoint=None,
):
    if config.continuation_id != batch["scope_id"] or not config.grounded_source_gap_handoff:
        raise DevProbeRejected()
    counted = ScopeTransport(
        underlying or httpx.HTTPTransport(retries=0), ledger, batch["scope_id"], before
    )
    jobs, attempts = [], []
    stopped = False
    if checkpoint:
        counted.on_send = lambda: checkpoint(
            {
                "event": "reserved_before_transport",
                "jobs": jobs,
                "attempts": attempts,
                "provider_sends": counted.records,
            }
        )
    try:
        for job in batch["jobs"]:
            if not ledger.experiment_scope_status(batch["scope_id"]).active:
                stopped = True
                break
            fixture = fixtures[job.get("fixture_id", job["case_id"])]
            ports = []
            start = len(attempts)

            def adapters(_case_id, turn, fixture=fixture, job=job, ports=ports):
                bundle = fixture.bundles[turn["evidence_bundle"]]
                reserve = INPUT_PROFILES[fixture.case["case_id"]]
                case_config = MetisConfig.model_validate(
                    {
                        **config.model_dump(),
                        "grounded_decision_contracts": job["decision_contracts"],
                        "input_token_reserve": reserve,
                        "max_request_usd": get_price(MODEL).cost(reserve, OUTPUT_LIMIT),
                    }
                )
                gateway = MetisGroundedPlanner(
                    case_config, ledger, transport=SharedTransport(counted)
                )
                ports.append(gateway)
                planner = ScopedPlanner(gateway, counted, attempts)

                def request_factory(case, message, evidence):
                    request = caller_catalog(case, message, evidence, definitions=definitions)
                    overrides = job.get("catalog_overrides")
                    gaps = (
                        tuple(GroundedGap.model_validate(gap) for gap in overrides["gaps"])
                        if overrides is not None
                        else request.gaps
                    )
                    groups = tuple(tuple(group) for group in job.get("conflict_groups", ()))
                    if groups or overrides is not None:
                        request = make_grounded_request(
                            case, message, evidence, gaps=gaps, conflict_groups=groups
                        )
                    return request

                return api.RunAdapters(
                    retriever=FakeRetriever([bundle, bundle]),
                    reasoner=GroundedReasoner(
                        planner, request_factory=request_factory, source_gap_handoff=True
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
                invocation_id=invocation(protocol, job),
                route_graph=RouteGraph.from_fixture(fixture.data),
            )
            try:

                def scoped_engine(*args, **kwargs):
                    return SupportEngine(*args, **kwargs, evidence_scope="exact_user_version")

                engine_factory = scoped_engine if batch["kind"] == "adversarial" else SupportEngine
                with (
                    patch.object(api, "_cases", {}),
                    patch.object(api, "tracker", DummyTracker()),
                    patch.object(api, "SupportEngine", engine_factory),
                ):
                    with TestClient(api.app) as client:
                        case_run.run(client)
                        if (
                            len(fixture.data["turns"]) > 1
                            and fixture.data["turns"][1]["expect"].get(
                                "previous_proposal_now_stale"
                            )
                            and len(case_run.steps) >= 2
                        ):
                            first = case_run.steps[0].get("proposal", {})
                            if first.get("proposal_id"):
                                previous = client.get(f"/cases/{fixture.case['case_id']}").json()
                                wires = len(counted.records)
                                refused = _decide(client, fixture.case["case_id"], first, "approve")
                                case_run.record.check(
                                    "correction",
                                    "stale approval rejected without mutation or new model send",
                                    refused.status_code == 409
                                    and client.get(f"/cases/{fixture.case['case_id']}").json()
                                    == previous
                                    and len(counted.records) == wires,
                                    refused.status_code,
                                )
            finally:
                for gateway in ports:
                    gateway.reasoner.client.close()
            for step in case_run.steps:
                step.pop("view_after", None)
            jobs.append(
                {
                    **job,
                    "fixture_id": fixture.data["fixture_id"],
                    "fixture_sha256": fixture.sha256,
                    "coverage_complete": case_run.route_complete,
                    "selected_turns": case_run.route_visits,
                    "checks": case_run.record.checks,
                    "steps": case_run.steps,
                    "run_ids": list(
                        dict.fromkeys(a["context"]["run_id"] for a in attempts[start:])
                    ),
                }
            )
            if checkpoint:
                checkpoint({"jobs": jobs, "attempts": attempts, "provider_sends": counted.records})
            if not ledger.experiment_scope_status(batch["scope_id"]).active and len(jobs) < len(
                batch["jobs"]
            ):
                stopped = True
                break
    finally:
        counted.close()
    after = ledger_observation(ledger._path)
    return {
        "batch_id": batch["batch_id"],
        "kind": batch["kind"],
        "scope_id": batch["scope_id"],
        "jobs": jobs,
        "attempts": attempts,
        "provider_sends": counted.records,
        "actual_sends": sum(item["http_send_started"] for item in counted.records),
        "accounting": Usage(ledger).measure(
            [ReasoningContext.model_validate(a["context"]) for a in attempts]
        ),
        "planned_jobs": len(batch["jobs"]),
        "visited_jobs": len(jobs),
        "completed_routes": sum(j["coverage_complete"] for j in jobs),
        "stopped_early": stopped,
        "ledger_after": after,
        "original_accounting_preserved": all(
            after[name] == before[name]
            for name in ("meta_sha256", "unknown_sha256", "old_grants_sha256")
        ),
    }
