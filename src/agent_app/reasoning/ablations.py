"""Registered four-cell development ablation; validation is offline by default.

This sequential single-runner comparison preserves paired inputs and the existing
gateway. It neither authorizes a continuation nor establishes semantic quality.
"""

import argparse
import hashlib
import json
import os
from collections.abc import Callable, Mapping
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal

import httpx
from pydantic import Field, StringConstraints, model_validator

from agent_app.contracts import Contract, Identifier, ReasoningContext, Text
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

type SuiteVariant = Literal["original", "enriched", "normalized"]
type CellID = Literal["A", "B", "C", "D"]


class SuiteReference(Contract):
    filename: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")]
    sha256: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
    content_sha256: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]


class NormalizationDeclaration(Contract):
    """Explicit caller-assigned fixture attribution, not a persisted user event."""

    source_ref: Identifier
    turn_id: Identifier
    fact_names: tuple[
        Annotated[str, StringConstraints(pattern=r"^reported_[a-z0-9_]{1,100}$")], ...
    ] = ()
    checks_added: tuple[Text, ...] = ()


class AblationCell(Contract):
    cell_id: CellID
    suite: SuiteVariant
    policy: Literal["structured_rules", "diagnostic_rules"]


CELLS = (
    AblationCell(cell_id="A", suite="original", policy="structured_rules"),
    AblationCell(cell_id="B", suite="enriched", policy="structured_rules"),
    AblationCell(cell_id="C", suite="normalized", policy="structured_rules"),
    AblationCell(cell_id="D", suite="normalized", policy="diagnostic_rules"),
)


class AblationPlan(ExperimentPlan):
    model: Literal["gpt-4o-mini"] = "gpt-4o-mini"
    input_token_reserve: Literal[32768] = 32768
    cap_usd: Decimal = Decimal("0.10")
    policies: tuple[Literal["structured_rules", "diagnostic_rules"], ...] = (
        "structured_rules",
        "diagnostic_rules",
    )
    cells: tuple[AblationCell, ...] = CELLS
    case_count: Annotated[int, Field(strict=True, ge=1, le=8)]
    suites: dict[SuiteVariant, SuiteReference]
    source_change_case_ids: tuple[Identifier, ...]
    normalizations: dict[Identifier, NormalizationDeclaration]

    @model_validator(mode="after")
    def fixed_grid_and_registration(self):
        if self.cells != CELLS or self.policies != ("structured_rules", "diagnostic_rules"):
            raise ValueError("The registered four-cell design cannot change")
        if set(self.suites) != {"original", "enriched", "normalized"}:
            raise ValueError("All three registered input suites are required")
        if self.suite_sha256 != self.suites["original"].sha256:
            raise ValueError("Original suite hash must match the parent protocol")
        if not self.cap_usd.is_finite() or not 0 < self.cap_usd <= Decimal("0.10"):
            raise ValueError("The whole ablation cap must be at most 0.10 USD")
        if len(set(self.source_change_case_ids)) != len(self.source_change_case_ids):
            raise ValueError("Source change declarations must be unique")
        return self


def suite_content_sha256(suite: ProbeSuite) -> str:
    return hashlib.sha256(suite.model_dump_json().encode()).hexdigest()


def validate_paired_suites(suites: Mapping[str, ProbeSuite], plan: AblationPlan) -> None:
    """Reject accidental changes to users, labels, original facts or evidence."""
    if set(suites) != set(plan.suites):
        raise ValueError("Input variants do not match the registered suites")
    for variant, suite in suites.items():
        if suite_content_sha256(suite) != plan.suites[variant].content_sha256:
            raise ValueError("Suite content changed after protocol registration")
        if len(suite.cases) != plan.case_count:
            raise ValueError("Case count changed after protocol registration")
    original, enriched, normalized = (
        suites[name] for name in ("original", "enriched", "normalized")
    )
    case_ids = tuple(probe.id for probe in original.cases)
    if not set(plan.source_change_case_ids) <= set(case_ids) or not set(plan.normalizations) <= set(
        case_ids
    ):
        raise ValueError("A change declaration references an unknown case")
    for candidate in (enriched, normalized):
        if tuple(probe.id for probe in candidate.cases) != case_ids:
            raise ValueError("Ordered case IDs must remain identical")
        if candidate.model_dump(exclude={"cases", "purpose"}) != original.model_dump(
            exclude={"cases", "purpose"}
        ):
            raise ValueError("Snapshot and quarantine boundaries must remain identical")
    source_changes = set()
    normalization_changes = set()
    for base, sources, facts in zip(original.cases, enriched.cases, normalized.cases, strict=True):
        skeleton = base.model_dump(exclude={"bundles", "case_state"})
        if any(
            probe.model_dump(exclude={"bundles", "case_state"}) != skeleton
            for probe in (sources, facts)
        ):
            raise ValueError("User messages, labels and reviewer context cannot change")
        if sources.case_state != base.case_state:
            raise ValueError("Source enrichment cannot change the user state")
        for before, after in zip(base.bundles, sources.bundles, strict=True):
            if before.model_dump(exclude={"hits"}) != after.model_dump(exclude={"hits"}):
                raise ValueError("Enrichment may only append evidence hits")
            if after.hits[: len(before.hits)] != before.hits:
                raise ValueError("Original evidence must stay intact and in order")
            additions = after.hits[len(before.hits) :]
            if additions:
                source_changes.add(base.id)
            for hit in additions:
                expected_url = f"https://github.com/streamlit/docs/blob/{original.docs_commit}/"
                if (
                    hit.source_type != "doc"
                    or hit.source_commit != original.docs_commit
                    or not hit.source_url.startswith(expected_url)
                ):
                    raise ValueError(
                        "Added evidence must retain the frozen official docs provenance"
                    )
        if facts.bundles != sources.bundles:
            raise ValueError("Normalization must use exactly the enriched evidence")
        before, after = base.case_state, facts.case_state
        if before.model_dump(exclude={"facts", "checks_performed"}) != after.model_dump(
            exclude={"facts", "checks_performed"}
        ):
            raise ValueError("Normalization cannot change unknowns, revisions or approvals")
        if (
            after.facts[: len(before.facts)] != before.facts
            or after.checks_performed[: len(before.checks_performed)] != before.checks_performed
        ):
            raise ValueError("Original facts and checks must be preserved")
        added_facts = after.facts[len(before.facts) :]
        added_checks = after.checks_performed[len(before.checks_performed) :]
        if added_facts or added_checks:
            normalization_changes.add(base.id)
            declaration = plan.normalizations.get(base.id)
            if declaration is None or (
                tuple(fact.name for fact in added_facts) != declaration.fact_names
                or added_checks != declaration.checks_added
            ):
                raise ValueError("User normalization must match its explicit change declaration")
            if any(
                fact.provenance_kind != "user"
                or fact.status != "active"
                or (fact.source_ref, fact.turn_id) != (declaration.source_ref, declaration.turn_id)
                for fact in added_facts
            ):
                raise ValueError("Normalized reports need the declared user attribution")
    if source_changes != set(plan.source_change_case_ids) or normalization_changes != set(
        plan.normalizations
    ):
        raise ValueError("Actual changes do not match the registered change scopes")


def validate_ablation_inputs(plan_path: Path) -> tuple[dict[str, ProbeSuite], AblationPlan]:
    plan = AblationPlan.model_validate_json(plan_path.read_text())
    if plan.price_verified_on != PRICE_VERIFIED_ON:
        raise ValueError("Registered prices no longer match the gateway")
    suites = {}
    for variant, reference in plan.suites.items():
        path = plan_path.parent / reference.filename
        if sha256_file(path) != reference.sha256:
            raise ValueError("Suite file changed after protocol registration")
        suites[variant] = load_suite(path)
    validate_paired_suites(suites, plan)
    return suites, plan


def schedule_ablation(suites: Mapping[str, ProbeSuite], plan: AblationPlan):
    """Each case receives all four cells; condition order rotates across cases."""
    for index in range(plan.case_count):
        offset = index % len(plan.cells)
        for cell in plan.cells[offset:] + plan.cells[:offset]:
            yield suites[cell.suite].cases[index], cell


def ablation_run_id(experiment_id: str, cell_id: CellID, probe_id: str) -> str:
    identity = json.dumps([experiment_id, cell_id, probe_id], separators=(",", ":"))
    return "ablation:" + hashlib.sha256(identity.encode()).hexdigest()


def run_ablation(
    suites: Mapping[str, ProbeSuite],
    plan: AblationPlan,
    *,
    config: MetisConfig,
    ledger: BudgetLedger,
    output_dir: Path,
    transport: httpx.BaseTransport | None = None,
    progress: Callable[[dict], None] | None = None,
) -> dict:
    plan = AblationPlan.model_validate(plan.model_dump(warnings=False))
    suites = {
        name: ProbeSuite.model_validate(suite.model_dump(warnings=False))
        for name, suite in suites.items()
    }
    validate_paired_suites(suites, plan)
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
            "suite_content_sha256": {
                name: suite_content_sha256(suite) for name, suite in suites.items()
            },
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
    for index, (probe, cell) in enumerate(schedule_ablation(suites, plan)):
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
                "prompt_policy": cell.policy,
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
                snapshot_id=suites[cell.suite].snapshot_id,
                run_id=ablation_run_id(plan.experiment_id, cell.cell_id, probe.id),
            )
        entries = []
        for context_data in observation["contexts"]:
            entry = ledger.get(request_id_for(ReasoningContext.model_validate(context_data)))
            if entry is not None:
                entries.append(
                    {
                        key: str(value) if isinstance(value, Decimal) else value
                        for key, value in asdict(entry).items()
                    }
                )
        observation.update(
            cell_id=cell.cell_id,
            suite=cell.suite,
            policy=cell.policy,
            ledger_entries=entries,
            http_attempts=http_attempts,
        )
        observations.append(observation)
        write_private(output_dir / f"observation-{index:02d}.json", observation)
        if progress:
            progress(
                {
                    "index": index + 1,
                    "case_id": probe.id,
                    "cell_id": cell.cell_id,
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
    # Three cells share a prompt; retain cell-level results instead of pooling factors.
    summary = summarize([dict(item, policy=item["cell_id"]) for item in observations])
    observed_cells = {}
    for item in observations:
        observed_cells.setdefault(item["case_id"], set()).add(item["cell_id"])
    summary.update(
        experiment_id=plan.experiment_id,
        cells=[cell.model_dump() for cell in plan.cells],
        completed_observations=len(observations),
        planned_observations=plan.case_count * len(plan.cells),
        paired_completed_case_ids=[
            probe.id
            for probe in suites["original"].cases
            if observed_cells.get(probe.id) == {cell.cell_id for cell in plan.cells}
        ],
        stop_reason=stop_reason,
        estimated_exposure_delta_usd=str(exposure(closing) - exposure(opening)),
        closing_ledger=snapshot_json(closing),
        account_deductions_reconciled=False,
        comparisons="A/B sources; B/C user normalization; C/D prompt; correlated development only",
    )
    write_private(output_dir / "summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--plan", type=Path, default=Path("experiments/decision_quality/protocol-ablation-v3.json")
    )
    parser.add_argument("--ledger", type=Path, default=Path("runtime/budget.sqlite3"))
    parser.add_argument("--live", action="store_true", help="Explicitly run the registered batch")
    args = parser.parse_args()
    try:
        suites, plan = validate_ablation_inputs(args.plan)
        if not args.live:
            print(
                json.dumps(
                    {
                        "validated": True,
                        "cases": plan.case_count,
                        "cells": [cell.model_dump() for cell in plan.cells],
                        "planned_observations": plan.case_count * len(plan.cells),
                        "input_token_reserve": plan.input_token_reserve,
                        "cap_usd": str(plan.cap_usd),
                        "paid_requests": 0,
                    }
                )
            )
            return
        summary = run_ablation(
            suites,
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
