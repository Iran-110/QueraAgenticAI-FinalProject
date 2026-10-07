"""Registered synthetic guard comparison; offline validation is the default."""

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

from agent_app.contracts import Contract, Identifier, ProposalRequirements, ReasoningContext
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

type VariantID = Literal["A", "B", "C"]
type FileName = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")]
type Digest = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
CONTINUATION_ID = "user-continuation-2026-10-07-v3"


class QualityVariant(Contract):
    variant_id: VariantID
    policy: Literal["structured_rules", "grounded_rules"]
    use_catalog: Annotated[bool, Field(strict=True)]
    proposal_checks: Annotated[bool, Field(strict=True)]


VARIANTS = (
    QualityVariant(
        variant_id="A", policy="structured_rules", use_catalog=False, proposal_checks=False
    ),
    QualityVariant(
        variant_id="B", policy="grounded_rules", use_catalog=True, proposal_checks=False
    ),
    QualityVariant(variant_id="C", policy="grounded_rules", use_catalog=True, proposal_checks=True),
)


class QualityExperimentPlan(ExperimentPlan):
    model: Literal["gpt-4o-mini"] = "gpt-4o-mini"
    policies: tuple[Literal["structured_rules", "grounded_rules"], ...] = (
        "structured_rules",
        "grounded_rules",
    )
    input_token_reserve: Literal[32768] = 32768
    cap_usd: Decimal = Decimal("0.055")
    continuation_id: Literal["user-continuation-2026-10-07-v3"] = CONTINUATION_ID
    variants: tuple[QualityVariant, ...] = VARIANTS
    case_count: Annotated[int, Field(strict=True, ge=1, le=9)]
    suite_filename: FileName = "cases-guards-v4.json"
    suite_content_sha256: Digest
    requirements_filename: FileName = "requirements-guards-v4.json"
    requirements_sha256: Digest
    requirements_content_sha256: Digest
    catalog: dict[Identifier, ProposalRequirements]

    @model_validator(mode="after")
    def registered_design(self):
        if self.variants != VARIANTS or self.policies != ("structured_rules", "grounded_rules"):
            raise ValueError("The registered three-variant design cannot change")
        if not self.cap_usd.is_finite() or not 0 < self.cap_usd <= Decimal("0.055"):
            raise ValueError("The whole comparison cap must be at most 0.055 USD")
        if catalog_content_sha256(self.catalog) != self.requirements_content_sha256:
            raise ValueError("Registered catalog contents do not match their hash")
        return self


def suite_content_sha256(suite: ProbeSuite) -> str:
    return hashlib.sha256(suite.model_dump_json().encode()).hexdigest()


def catalog_content_sha256(catalog: Mapping[str, ProposalRequirements]) -> str:
    payload = {name: value.model_dump(mode="json") for name, value in catalog.items()}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def validate_quality_data(
    suite: ProbeSuite,
    catalog: Mapping[str, ProposalRequirements],
    plan: QualityExperimentPlan,
) -> None:
    if suite_content_sha256(suite) != plan.suite_content_sha256:
        raise ValueError("Suite content changed after protocol registration")
    if len(suite.cases) != plan.case_count:
        raise ValueError("Case count changed after protocol registration")
    if set(catalog) != {probe.id for probe in suite.cases} or dict(catalog) != plan.catalog:
        raise ValueError("Caller catalog changed after protocol registration")
    if catalog_content_sha256(catalog) != plan.requirements_content_sha256:
        raise ValueError("Caller catalog contents do not match their hash")
    for probe in suite.cases:
        if probe.kind != "synthetic" or any(
            value is not None
            for value in (probe.origin_url, probe.origin_issue_id, probe.origin_created_at)
        ):
            raise ValueError("This comparison requires synthetic development inputs")
        requirements = catalog[probe.id]
        case = probe.case_state
        if (requirements.case_id, requirements.case_revision) != (
            case.case_id,
            case.case_revision,
        ):
            raise ValueError("Caller requirements must match the case revision")
        known_user_names = {
            fact.name.casefold()
            for fact in case.facts
            if fact.status == "active" and fact.provenance_kind == "user"
        }
        unknown_names = {name.casefold() for name in case.unknowns}
        if any(
            target.name.casefold() in known_user_names
            or target.name.casefold() not in unknown_names
            for target in requirements.question_targets
        ):
            raise ValueError("Question targets must be explicitly missing user details")


def validate_quality_inputs(
    plan_path: Path,
) -> tuple[ProbeSuite, dict[str, ProposalRequirements], QualityExperimentPlan]:
    plan = QualityExperimentPlan.model_validate_json(plan_path.read_text())
    if plan.price_verified_on != PRICE_VERIFIED_ON:
        raise ValueError("Registered prices no longer match the gateway")
    suite_path = plan_path.parent / plan.suite_filename
    requirements_path = plan_path.parent / plan.requirements_filename
    if sha256_file(suite_path) != plan.suite_sha256:
        raise ValueError("Suite file changed after protocol registration")
    if sha256_file(requirements_path) != plan.requirements_sha256:
        raise ValueError("Requirements file changed after protocol registration")
    suite = load_suite(suite_path)
    raw_catalog = json.loads(requirements_path.read_text())
    catalog = {
        name: ProposalRequirements.model_validate(value) for name, value in raw_catalog.items()
    }
    validate_quality_data(suite, catalog, plan)
    return suite, catalog, plan


def schedule_quality(suite: ProbeSuite, plan: QualityExperimentPlan):
    for index, probe in enumerate(suite.cases):
        offset = index % len(plan.variants)
        for variant in plan.variants[offset:] + plan.variants[:offset]:
            yield probe, variant


def quality_run_id(experiment_id: str, variant_id: VariantID, probe_id: str) -> str:
    identity = json.dumps([experiment_id, variant_id, probe_id], separators=(",", ":"))
    return "quality:" + hashlib.sha256(identity.encode()).hexdigest()


def _decimal_json(value) -> dict:
    return {
        key: str(item) if isinstance(item, Decimal) else item for key, item in asdict(value).items()
    }


def run_quality_experiment(
    suite: ProbeSuite,
    catalog: Mapping[str, ProposalRequirements],
    plan: QualityExperimentPlan,
    *,
    config: MetisConfig,
    ledger: BudgetLedger,
    output_dir: Path,
    transport: httpx.BaseTransport | None = None,
    progress: Callable[[dict], None] | None = None,
) -> dict:
    suite = ProbeSuite.model_validate(suite.model_dump(warnings=False))
    catalog = {
        name: ProposalRequirements.model_validate(value.model_dump(warnings=False))
        for name, value in catalog.items()
    }
    plan = QualityExperimentPlan.model_validate(plan.model_dump(warnings=False))
    validate_quality_data(suite, catalog, plan)
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
            "requirements_content_sha256": catalog_content_sha256(catalog),
            "code_sha256": code_digest.hexdigest(),
            "opening_ledger": snapshot_json(opening),
            "continuation": _decimal_json(ledger.continuation_status(plan.continuation_id)),
            "price_source": PRICE_SOURCE,
            "one_request_reserve_usd": str(gate.request_reserve),
            "account_deductions_reconciled": False,
            "sequential_designated_runner_only": True,
            "caller_catalog_is_manual_not_production_extraction": True,
        },
    )
    observations = []
    stop_reason = None
    for index, (probe, variant) in enumerate(schedule_quality(suite, plan)):
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
                "prompt_policy": variant.policy,
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
                run_id=quality_run_id(plan.experiment_id, variant.variant_id, probe.id),
                proposal_requirements=catalog[probe.id] if variant.use_catalog else None,
                proposal_checks=variant.proposal_checks,
            )
        entries = []
        for context_data in observation["contexts"]:
            entry = ledger.get(request_id_for(ReasoningContext.model_validate(context_data)))
            if entry is not None:
                entries.append(_decimal_json(entry))
        observation.update(
            variant_id=variant.variant_id,
            policy=variant.policy,
            use_catalog=variant.use_catalog,
            proposal_checks=variant.proposal_checks,
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
                    "variant_id": variant.variant_id,
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
    summary = summarize([dict(item, policy=item["variant_id"]) for item in observations])
    observed_variants = {}
    for item in observations:
        observed_variants.setdefault(item["case_id"], set()).add(item["variant_id"])
    summary.update(
        experiment_id=plan.experiment_id,
        variants=[variant.model_dump() for variant in plan.variants],
        completed_observations=len(observations),
        planned_observations=plan.case_count * len(plan.variants),
        paired_completed_case_ids=[
            probe.id
            for probe in suite.cases
            if observed_variants.get(probe.id) == {variant.variant_id for variant in plan.variants}
        ],
        stop_reason=stop_reason,
        estimated_exposure_delta_usd=str(exposure(closing) - exposure(opening)),
        closing_ledger=snapshot_json(closing),
        account_deductions_reconciled=False,
        comparisons="A/B caller metadata plus prompt; B/C deterministic guards; synthetic development",
    )
    write_private(output_dir / "summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--plan", type=Path, default=Path("experiments/decision_quality/protocol-guards-v4.json")
    )
    parser.add_argument("--ledger", type=Path, default=Path("runtime/budget.sqlite3"))
    parser.add_argument("--live", action="store_true", help="Explicitly run the registered batch")
    args = parser.parse_args()
    try:
        suite, catalog, plan = validate_quality_inputs(args.plan)
        if not args.live:
            print(
                json.dumps(
                    {
                        "validated": True,
                        "cases": plan.case_count,
                        "variants": [variant.model_dump() for variant in plan.variants],
                        "planned_observations": plan.case_count * len(plan.variants),
                        "cap_usd": str(plan.cap_usd),
                        "paid_requests": 0,
                    }
                )
            )
            return
        summary = run_quality_experiment(
            suite,
            catalog,
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
