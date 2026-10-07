"""Sequential development comparison; explicit live opt-in, private local receipts.

The experiment cap is conservative for a single designated runner. Global ledger
reservations remain atomic; independent runners need their own coordination.
"""

import argparse
import hashlib
import json
import os
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal

import httpx
from pydantic import StringConstraints, model_validator

from agent_app.contracts import Contract, ReasoningContext
from agent_app.llm.budget import BudgetLedger, BudgetSnapshot
from agent_app.llm.config import MetisConfig
from agent_app.llm.metis import MetisReasoner, request_id_for
from agent_app.llm.pricing import PRICE_SOURCE, PRICE_VERIFIED_ON, get_price
from agent_app.orchestration.ports import ReasoningStopped
from agent_app.reasoning.probes import ProbeSuite, load_suite, run_probe, summarize
from agent_app.reasoning.prompts import PromptPolicy


class ExperimentPlan(Contract):
    schema_version: Literal[1] = 1
    experiment_id: Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")]
    suite_sha256: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
    model: Literal["gpt-4o-mini", "gpt-4.1-mini"] = "gpt-4o-mini"
    policies: tuple[PromptPolicy, ...] = ("baseline", "decision_rubric", "bounded_rubric")
    input_token_reserve: Literal[16384, 32768] = 16384
    max_output_tokens: Literal[768] = 768
    cap_usd: Decimal = Decimal("0.16")
    price_verified_on: Literal["2026-10-07"] = "2026-10-07"
    continuation_id: (
        Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")] | None
    ) = None
    scope: str

    @model_validator(mode="after")
    def check_plan(self):
        if not self.policies or len(set(self.policies)) != len(self.policies):
            raise ValueError("Policies must be nonempty and unique")
        if not self.cap_usd.is_finite() or not 0 < self.cap_usd <= Decimal("0.16"):
            raise ValueError("Development experiment cap must be at most 0.16 USD")
        return self


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_inputs(suite_path: Path, plan_path: Path) -> tuple[ProbeSuite, ExperimentPlan]:
    suite = load_suite(suite_path)
    plan = ExperimentPlan.model_validate_json(plan_path.read_text())
    if sha256_file(suite_path) != plan.suite_sha256:
        raise ValueError("Suite changed after protocol registration")
    if plan.price_verified_on != PRICE_VERIFIED_ON:
        raise ValueError("Registered prices no longer match the gateway")
    return suite, plan


def exposure(snapshot: BudgetSnapshot) -> Decimal:
    return snapshot.limit_usd - snapshot.available_usd


def snapshot_json(snapshot: BudgetSnapshot) -> dict:
    return {
        key: str(value) if isinstance(value, Decimal) else value
        for key, value in asdict(snapshot).items()
    }


def write_private(path: Path, value: dict) -> None:
    """Exclusive creation prevents silent replacement or restart under a fresh receipt."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


class ExperimentGate:
    def __init__(self, ledger: BudgetLedger, plan: ExperimentPlan, opening: BudgetSnapshot):
        self.ledger = ledger
        self.plan = plan
        self.opening_exposure = exposure(opening)
        self.opening_grant_used = (
            ledger.continuation_status(plan.continuation_id).used_usd
            if plan.continuation_id
            else Decimal("0")
        )
        price = get_price(plan.model)
        assert price is not None
        self.request_reserve = price.cost(plan.input_token_reserve, plan.max_output_tokens)

    def check_accounting(self) -> None:
        snapshot = self.ledger.snapshot()
        if self.plan.continuation_id:
            grant = self.ledger.continuation_status(self.plan.continuation_id)
            if not grant.active or grant.allowed_model != self.plan.model or snapshot.reserved_usd:
                raise ReasoningStopped("LedgerUnavailable", "budget_stopped")
        elif snapshot.halted or snapshot.reserved_usd or snapshot.uncertain_usd:
            raise ReasoningStopped("LedgerUnavailable", "budget_stopped")

    def check(self) -> None:
        self.check_accounting()
        snapshot = self.ledger.snapshot()
        if self.plan.continuation_id:
            grant = self.ledger.continuation_status(self.plan.continuation_id)
            used = grant.used_usd - self.opening_grant_used
            if self.request_reserve > grant.remaining_usd:
                raise ReasoningStopped("BudgetExceeded", "budget_stopped")
        else:
            used = max(Decimal("0"), exposure(snapshot) - self.opening_exposure)
        if used + self.request_reserve > self.plan.cap_usd:
            raise ReasoningStopped("BudgetExceeded", "budget_stopped")


class GatedReasoner:
    def __init__(self, delegate: MetisReasoner, gate: ExperimentGate):
        self.delegate = delegate
        self.gate = gate

    def analyze(self, case, message, evidence, *, context):
        self.gate.check()
        return self.delegate.analyze(case, message, evidence, context=context)


def schedule(suite: ProbeSuite, plan: ExperimentPlan):
    """Rotate policy order across cases; all policies see identical fixed bundles."""
    for index, probe in enumerate(suite.cases):
        offset = index % len(plan.policies)
        for policy in plan.policies[offset:] + plan.policies[:offset]:
            yield probe, policy


def experiment_run_id(experiment_id: str, policy: PromptPolicy, probe_id: str) -> str:
    identity = json.dumps([experiment_id, policy, probe_id], separators=(",", ":"))
    return "experiment:" + hashlib.sha256(identity.encode()).hexdigest()


def run_experiment(
    suite: ProbeSuite,
    plan: ExperimentPlan,
    *,
    config: MetisConfig,
    ledger: BudgetLedger,
    output_dir: Path,
    transport: httpx.BaseTransport | None = None,
    progress: Callable[[dict], None] | None = None,
) -> dict:
    suite = ProbeSuite.model_validate(suite.model_dump(warnings=False))
    plan = ExperimentPlan.model_validate(plan.model_dump(warnings=False))
    config = MetisConfig.model_validate(config.model_dump(warnings=False))
    if not config.live_enabled:
        raise ValueError("Explicit live opt-in is required")
    opening = ledger.snapshot()
    gate = ExperimentGate(ledger, plan, opening)
    gate.check()
    # Never restart a partial batch automatically or invent fresh run IDs.
    output_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.chmod(output_dir, 0o700)
    code_paths = sorted(Path(__file__).parents[1].rglob("*.py"))
    code_digest = hashlib.sha256()
    for path in code_paths:
        code_digest.update(str(path.relative_to(Path(__file__).parents[1])).encode())
        code_digest.update(path.read_bytes())
    write_private(
        output_dir / "start.json",
        {
            "started_at": datetime.now(UTC).isoformat(),
            "plan": plan.model_dump(mode="json"),
            "suite_content_sha256": hashlib.sha256(suite.model_dump_json().encode()).hexdigest(),
            "code_sha256": code_digest.hexdigest(),
            "opening_ledger": snapshot_json(opening),
            "continuation": (
                {
                    key: str(value) if isinstance(value, Decimal) else value
                    for key, value in asdict(
                        ledger.continuation_status(plan.continuation_id)
                    ).items()
                }
                if plan.continuation_id
                else None
            ),
            "price_source": PRICE_SOURCE,
            "one_request_reserve_usd": str(gate.request_reserve),
            "account_deductions_reconciled": False,
            "sequential_designated_runner_only": True,
        },
    )
    observations = []
    stop_reason = None
    for index, (probe, policy) in enumerate(schedule(suite, plan)):
        try:
            gate.check()
        except ReasoningStopped as stopped:
            stop_reason = stopped.code
            break
        selected = config.model_copy(
            update={
                "model": plan.model,
                "max_output_tokens": plan.max_output_tokens,
                "input_token_reserve": plan.input_token_reserve,
                "prompt_policy": policy,
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
                probe,
                GatedReasoner(delegate, gate),
                snapshot_id=suite.snapshot_id,
                run_id=experiment_run_id(plan.experiment_id, policy, probe.id),
            )
        entries = []
        for context_data in observation["contexts"]:
            entry = ledger.get(request_id_for(ReasoningContext.model_validate(context_data)))
            if entry:
                entries.append(
                    {
                        key: str(value) if isinstance(value, Decimal) else value
                        for key, value in asdict(entry).items()
                    }
                )
        observation.update(policy=policy, ledger_entries=entries, http_attempts=http_attempts)
        observations.append(observation)
        write_private(output_dir / f"observation-{index:02d}.json", observation)
        if progress:
            progress(
                {
                    "index": index + 1,
                    "case_id": probe.id,
                    "policy": policy,
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
        except ReasoningStopped:
            stop_reason = "UnreconciledLedger"
            break
        if observation["result"]["status"] == "budget_stopped":
            stop_reason = observation["result"]["error_code"]
            break
    closing = ledger.snapshot()
    summary = summarize(observations)
    summary.update(
        experiment_id=plan.experiment_id,
        completed_observations=len(observations),
        planned_observations=len(suite.cases) * len(plan.policies),
        stop_reason=stop_reason,
        estimated_exposure_delta_usd=str(exposure(closing) - exposure(opening)),
        closing_ledger=snapshot_json(closing),
        account_deductions_reconciled=False,
    )
    write_private(output_dir / "summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--suite", type=Path, default=Path("experiments/decision_quality/cases.json")
    )
    parser.add_argument(
        "--plan", type=Path, default=Path("experiments/decision_quality/protocol.json")
    )
    parser.add_argument("--ledger", type=Path, default=Path("runtime/budget.sqlite3"))
    parser.add_argument(
        "--live", action="store_true", help="Explicitly opt in to the registered paid batch"
    )
    args = parser.parse_args()
    try:
        suite, plan = validate_inputs(args.suite, args.plan)
        if not args.live:
            print(
                json.dumps(
                    {
                        "validated": True,
                        "cases": len(suite.cases),
                        "policies": plan.policies,
                        "cap_usd": str(plan.cap_usd),
                        "paid_requests": 0,
                    }
                )
            )
            return
        config = MetisConfig.from_env().model_copy(update={"live_enabled": True})
        summary = run_experiment(
            suite,
            plan,
            config=config,
            ledger=BudgetLedger(args.ledger),
            output_dir=Path("runtime/decision-quality") / plan.experiment_id,
            progress=lambda value: print(json.dumps(value), flush=True),
        )
        print(json.dumps(summary), flush=True)
    except Exception as error:
        # Never print exception messages that may contain credentials/source data.
        print(json.dumps({"failed": True, "error_type": type(error).__name__}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
