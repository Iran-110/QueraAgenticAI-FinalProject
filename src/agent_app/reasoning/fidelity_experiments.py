"""Registered two-policy fidelity trials; validation is offline by default."""

import argparse
import hashlib
import json
import os
from collections.abc import Callable, Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal

import httpx
from pydantic import Field, StringConstraints, model_validator

from agent_app.contracts import Contract, Identifier, ReasoningContext
from agent_app.llm.budget import BudgetLedger
from agent_app.llm.config import MetisConfig
from agent_app.llm.metis import MetisReasoner, request_id_for
from agent_app.llm.pricing import PRICE_SOURCE, PRICE_VERIFIED_ON
from agent_app.orchestration.ports import ReasoningStopped
from agent_app.reasoning.experiments import (
    ExperimentGate,
    ExperimentPlan,
    GatedReasoner,
    exposure,
    sha256_file,
    snapshot_json,
    write_private,
)
from agent_app.reasoning.probes import ProbeSuite, load_suite, run_probe, summarize

type FidelityPolicy = Literal["structured_rules", "fidelity_rules"]
type Digest = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
type FileName = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")]
CONTINUATION_ID = "user-continuation-2026-10-07-v3"
POLICIES = ("structured_rules", "fidelity_rules")


class FidelityScheduleEntry(Contract):
    case_id: Identifier
    replicate: Annotated[int, Field(strict=True, ge=1, le=2)]
    policy: FidelityPolicy


def suite_content_sha256(suite: ProbeSuite) -> str:
    return hashlib.sha256(suite.model_dump_json().encode()).hexdigest()


def schedule_content_sha256(schedule: Sequence[FidelityScheduleEntry]) -> str:
    payload = [entry.model_dump(mode="json") for entry in schedule]
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def fidelity_schedule(suite: ProbeSuite) -> tuple[FidelityScheduleEntry, ...]:
    """Complete one paired draw per case before repeating; reverse order on repeat."""
    entries = []
    for replicate in (1, 2):
        for index, probe in enumerate(suite.cases):
            offset = (index + replicate - 1) % len(POLICIES)
            for policy in POLICIES[offset:] + POLICIES[:offset]:
                entries.append(
                    FidelityScheduleEntry(case_id=probe.id, replicate=replicate, policy=policy)
                )
    return tuple(entries)


class FidelityExperimentPlan(ExperimentPlan):
    model: Literal["gpt-4o-mini"] = "gpt-4o-mini"
    policies: tuple[FidelityPolicy, ...] = POLICIES
    input_token_reserve: Annotated[int, Field(strict=True, ge=32768, le=32768)] = 32768
    max_output_tokens: Annotated[int, Field(strict=True, ge=768, le=768)] = 768
    cap_usd: Decimal = Decimal("0.030")
    continuation_id: Literal["user-continuation-2026-10-07-v3"] = CONTINUATION_ID
    case_count: Annotated[int, Field(strict=True, ge=1, le=6)]
    replicates: Annotated[int, Field(strict=True, ge=2, le=2)] = 2
    proposal_checks: Annotated[bool, Field(strict=True)] = False
    suite_filename: FileName = "cases-fidelity-v7.json"
    suite_content_sha256: Digest
    schedule: tuple[FidelityScheduleEntry, ...]
    schedule_sha256: Digest

    @model_validator(mode="after")
    def fixed_design(self):
        if self.policies != POLICIES or self.proposal_checks:
            raise ValueError("The registered two-policy design cannot change")
        if not self.cap_usd.is_finite() or not 0 < self.cap_usd <= Decimal("0.030"):
            raise ValueError("The whole comparison cap must be at most 0.030 USD")
        if schedule_content_sha256(self.schedule) != self.schedule_sha256:
            raise ValueError("Registered schedule does not match its hash")
        return self


def validate_fidelity_data(suite: ProbeSuite, plan: FidelityExperimentPlan) -> None:
    if suite_content_sha256(suite) != plan.suite_content_sha256:
        raise ValueError("Suite content changed after protocol registration")
    if len(suite.cases) != plan.case_count:
        raise ValueError("Case count changed after protocol registration")
    if fidelity_schedule(suite) != plan.schedule:
        raise ValueError("Registered schedule differs from the fixed case/order design")
    for probe in suite.cases:
        if probe.kind != "synthetic" or any(
            value is not None
            for value in (probe.origin_url, probe.origin_issue_id, probe.origin_created_at)
        ):
            raise ValueError("This comparison requires synthetic development inputs")


def validate_fidelity_inputs(plan_path: Path) -> tuple[ProbeSuite, FidelityExperimentPlan]:
    plan = FidelityExperimentPlan.model_validate_json(plan_path.read_text())
    if plan.price_verified_on != PRICE_VERIFIED_ON:
        raise ValueError("Registered prices no longer match the gateway")
    suite_path = plan_path.parent / plan.suite_filename
    if sha256_file(suite_path) != plan.suite_sha256:
        raise ValueError("Suite file changed after protocol registration")
    suite = load_suite(suite_path)
    validate_fidelity_data(suite, plan)
    return suite, plan


def fidelity_run_id(
    experiment_id: str, replicate: int, policy: FidelityPolicy, probe_id: str
) -> str:
    identity = json.dumps([experiment_id, replicate, policy, probe_id], separators=(",", ":"))
    return "fidelity:" + hashlib.sha256(identity.encode()).hexdigest()


def _decimal_json(value) -> dict:
    return {
        key: str(item) if isinstance(item, Decimal) else item for key, item in asdict(value).items()
    }


def _pairing_summary(suite: ProbeSuite, observations: list[dict]) -> dict:
    observed = {}
    accepted = {}
    for item in observations:
        observed.setdefault((item["case_id"], item["replicate"]), set()).add(item["policy"])
        if item["automatic"]["accepted"]:
            accepted.setdefault((item["case_id"], item["replicate"]), set()).add(item["policy"])
    pairs = [
        {"case_id": probe.id, "replicate": replicate}
        for replicate in (1, 2)
        for probe in suite.cases
        if observed.get((probe.id, replicate)) == set(POLICIES)
    ]
    return {
        "completed_case_replicate_pairs": pairs,
        "pair_completion_means_recorded_engine_invocations": True,
        "accepted_case_replicate_pairs": [
            pair
            for pair in pairs
            if accepted.get((pair["case_id"], pair["replicate"])) == set(POLICIES)
        ],
        "fully_repeated_case_ids": [
            probe.id
            for probe in suite.cases
            if all(observed.get((probe.id, replicate)) == set(POLICIES) for replicate in (1, 2))
        ],
    }


def run_fidelity_experiment(
    suite: ProbeSuite,
    plan: FidelityExperimentPlan,
    *,
    config: MetisConfig,
    ledger: BudgetLedger,
    output_dir: Path,
    transport: httpx.BaseTransport | None = None,
    progress: Callable[[dict], None] | None = None,
) -> dict:
    suite = ProbeSuite.model_validate(suite.model_dump(warnings=False))
    plan = FidelityExperimentPlan.model_validate(plan.model_dump(warnings=False))
    validate_fidelity_data(suite, plan)
    config = MetisConfig.model_validate(config.model_dump(warnings=False))
    if not config.live_enabled:
        raise ValueError("Explicit live opt-in is required")
    opening = ledger.snapshot()
    gate = ExperimentGate(ledger, plan, opening)
    gate.check()
    output_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.chmod(output_dir, 0o700)
    code_digest = hashlib.sha256()
    for path in sorted(Path(__file__).parents[1].rglob("*.py")):
        code_digest.update(str(path.relative_to(Path(__file__).parents[1])).encode())
        code_digest.update(path.read_bytes())
    write_private(
        output_dir / "start.json",
        {
            "started_at": datetime.now(UTC).isoformat(),
            "plan": plan.model_dump(mode="json"),
            "suite_content_sha256": suite_content_sha256(suite),
            "schedule_sha256": schedule_content_sha256(plan.schedule),
            "code_sha256": code_digest.hexdigest(),
            "opening_ledger": snapshot_json(opening),
            "continuation": _decimal_json(ledger.continuation_status(plan.continuation_id)),
            "price_source": PRICE_SOURCE,
            "one_request_reserve_usd": str(gate.request_reserve),
            "account_deductions_reconciled": False,
            "sequential_designated_runner_only": True,
            "manual_question_catalog": False,
            "proposal_checks": False,
        },
    )
    probes = {probe.id: probe for probe in suite.cases}
    observations = []
    stop_reason = None
    for index, scheduled in enumerate(plan.schedule):
        try:
            gate.check()
        except ReasoningStopped as stopped:
            stop_reason = stopped.code
            break
        selected = MetisConfig.model_validate(
            config.model_dump(warnings=False)
            | {
                "model": plan.model,
                "max_output_tokens": plan.max_output_tokens,
                "input_token_reserve": plan.input_token_reserve,
                "prompt_policy": scheduled.policy,
                "phase": "development",
                "continuation_id": plan.continuation_id,
            }
        )
        http_attempts = []
        with MetisReasoner(selected, ledger, transport=transport) as delegate:
            delegate.client.event_hooks["request"] = [
                lambda _, events=http_attempts: events.append({"status": None})
            ]
            delegate.client.event_hooks["response"] = [
                lambda response, events=http_attempts: events[-1].update(
                    status=response.status_code
                )
            ]
            observation = run_probe(
                probes[scheduled.case_id],
                GatedReasoner(delegate, gate),
                snapshot_id=suite.snapshot_id,
                run_id=fidelity_run_id(
                    plan.experiment_id, scheduled.replicate, scheduled.policy, scheduled.case_id
                ),
                proposal_requirements=None,
                proposal_checks=False,
            )
        entries = []
        for context_data in observation["contexts"]:
            entry = ledger.get(request_id_for(ReasoningContext.model_validate(context_data)))
            if entry is not None:
                entries.append(_decimal_json(entry))
        observation.update(
            replicate=scheduled.replicate,
            policy=scheduled.policy,
            variant_id="A" if scheduled.policy == "structured_rules" else "B",
            proposal_checks=False,
            ledger_entries=entries,
            http_attempts=http_attempts,
        )
        observations.append(observation)
        write_private(output_dir / f"observation-{index:02d}.json", observation)
        if progress:
            progress(
                {
                    "index": index + 1,
                    "case_id": scheduled.case_id,
                    "replicate": scheduled.replicate,
                    "policy": scheduled.policy,
                    "status": observation["result"]["status"],
                    "decision": (observation["result"]["analysis"] or {}).get("decision"),
                    "http_attempts": len(http_attempts),
                    "estimated_usd": str(
                        sum((Decimal(item["cost_usd"] or "0") for item in entries), Decimal("0"))
                    ),
                }
            )
        try:
            gate.check_accounting()
        except ReasoningStopped as stopped:
            stop_reason = stopped.code
            break
        if observation["result"]["status"] == "budget_stopped":
            stop_reason = observation["result"]["error_code"]
            break
    closing = ledger.snapshot()
    summary = summarize(observations)
    for group in summary["automatic_results"].values():
        group["observations"] = group.pop("cases")
    summary.update(
        experiment_id=plan.experiment_id,
        completed_observations=len(observations),
        attempted_observations=len(observations),
        paid_http_requests=sum(len(item["http_attempts"]) for item in observations),
        accepted_observations=sum(item["automatic"]["accepted"] for item in observations),
        planned_observations=len(plan.schedule),
        **_pairing_summary(suite, observations),
        stop_reason=stop_reason,
        estimated_exposure_delta_usd=str(exposure(closing) - exposure(opening)),
        closing_ledger=snapshot_json(closing),
        closing_continuation=_decimal_json(ledger.continuation_status(plan.continuation_id)),
        account_deductions_reconciled=False,
        comparisons="Two fixed policies, two draws per synthetic case; no optional proposal checks",
        repeated_draws_are_independent_cases=False,
    )
    write_private(output_dir / "summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--plan", type=Path, default=Path("experiments/decision_quality/protocol-fidelity-v7.json")
    )
    parser.add_argument("--ledger", type=Path, default=Path("runtime/budget.sqlite3"))
    parser.add_argument("--live", action="store_true", help="Explicitly run the registered batch")
    args = parser.parse_args()
    try:
        suite, plan = validate_fidelity_inputs(args.plan)
        if not args.live:
            print(
                json.dumps(
                    {
                        "validated": True,
                        "cases": plan.case_count,
                        "policies": plan.policies,
                        "replicates": plan.replicates,
                        "planned_observations": len(plan.schedule),
                        "schedule_sha256": plan.schedule_sha256,
                        "cap_usd": str(plan.cap_usd),
                        "paid_requests": 0,
                    }
                )
            )
            return
        summary = run_fidelity_experiment(
            suite,
            plan,
            config=MetisConfig.from_env().model_copy(update={"live_enabled": True}),
            ledger=BudgetLedger(args.ledger),
            output_dir=Path("runtime/decision-quality") / plan.experiment_id,
            progress=lambda value: print(json.dumps(value), flush=True),
        )
        print(json.dumps(summary), flush=True)
    except Exception as error:
        print(json.dumps({"failed": True, "error_type": type(error).__name__}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
