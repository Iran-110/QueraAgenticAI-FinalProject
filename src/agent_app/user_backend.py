"""Live backend for real users, accounted on its own capped ledger.

This composes the existing selected core profile (``grounded_candidate_prefilter_v2``)
and the existing live adapters with a separate ledger, ``runtime/user-budget.sqlite3``.
The team ledger, its halt and holds are never opened or changed here. Every
request is still reserved against the user ledger's limit before transport;
an uncertain provider result halts the user ledger like any other.

The ledger is not created here: initialize it once with
``agent-app budget init --path runtime/user-budget.sqlite3 --limit-usd 1 --opening-spend-usd 0``.
Pinned core modules keep their phase vocabulary, so reservations carry the
existing ``development`` phase label; the separate ledger file identifies user use.
"""

import hmac
import os
import sqlite3
from collections.abc import Mapping
from contextlib import closing
from decimal import Decimal
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException

from agent_app.evaluation.live import LiveEvaluationAdapters
from agent_app.live_backend import configured_app
from agent_app.llm.budget import BudgetLedger
from agent_app.llm.config import MetisConfig
from agent_app.orchestration.core_delivery import PREFILTER_DELIVERY_PROFILE_ID, delivery_recipe
from agent_app.reasoning.catalog import load_user_gap_vocabulary

ROOT = Path(__file__).resolve().parents[2]
USER_LEDGER = ROOT / "runtime/user-budget.sqlite3"
TEAM_LEDGER = ROOT / "runtime/budget.sqlite3"
DEFAULT_INDEX = ROOT / "runtime/demo-final-corpus-v3"
DEFAULT_SNAPSHOT = "docs-pilot-20ab0d69d12f2c83fb424e0ced7a22561019b1d778c68071d4f1d4ce1f8277b6"
DEFAULT_MANIFEST_SHA256 = "933682e56386abc5b133565086058030e74783ef424bccd35f0193038d1908dc"
VOCABULARY = ROOT / "config/user-gap-support-dev-v1.json"
USER_LIMIT_USD = Decimal("1")
USAGE_ROWS = 200


def user_adapters(
    values: Mapping[str, str], *, ledger_path: Path = USER_LEDGER, transport_factory=None
):
    """Ledger checks precede the key; the adapters check budget/index before any send.

    ``transport_factory`` is caller-owned test injection, never an env setting.
    """
    try:
        if values.get("METIS_LIVE_ENABLED") != "true":
            raise ValueError("LiveCallsDisabled")
        ledger_path = Path(ledger_path).resolve()
        if ledger_path == TEAM_LEDGER.resolve() or not ledger_path.is_file():
            raise ValueError("UserLedgerUnavailable")
        ledger = BudgetLedger(ledger_path)
        if ledger.snapshot().limit_usd > USER_LIMIT_USD:
            raise ValueError("UserLedgerLimitInvalid")
        if not values.get("METIS_API_KEY"):
            raise ValueError("UserApiKeyMissing")
        recipe = delivery_recipe(profile_id=PREFILTER_DELIVERY_PROFILE_ID)
        config = MetisConfig(
            **{**recipe["metis"], "max_request_usd": Decimal(recipe["metis"]["max_request_usd"])},
            phase="development",
            api_key=values.get("METIS_API_KEY", ""),
        )
        return LiveEvaluationAdapters(
            index_path=Path(values.get("AGENT_EVAL_INDEX", str(DEFAULT_INDEX))),
            snapshot_id=values.get("AGENT_EVAL_SNAPSHOT", DEFAULT_SNAPSHOT),
            manifest_sha256=values.get("AGENT_EVAL_MANIFEST_SHA256", DEFAULT_MANIFEST_SHA256),
            ledger=ledger,
            config=config,
            top_k=recipe["adapter_top_k"],
            retrieval_profile=recipe["retrieval_profile"],
            user_gaps=load_user_gap_vocabulary(str(VOCABULARY)),
            core_profile=PREFILTER_DELIVERY_PROFILE_ID,
            transport_factory=transport_factory,
        )
    except ValueError as error:
        if str(error).startswith(("Live", "User", "CoreDelivery")):
            raise ValueError(str(error)) from None
        raise ValueError("UserBackendConfigurationInvalid") from None
    except Exception:
        raise ValueError("UserBackendConfigurationInvalid") from None


def _usd(nanos) -> str:
    return str(Decimal(nanos) / Decimal(1_000_000_000))


def usage_report(ledger_path: Path) -> dict:
    """Read-only view of the user ledger: totals and the latest model calls.

    Only accounting columns are returned; no prompt, output or credential is stored there.
    """
    ledger = BudgetLedger(ledger_path)
    snapshot = ledger.snapshot()
    with closing(
        sqlite3.connect(Path(ledger_path).resolve().as_uri() + "?mode=ro", uri=True)
    ) as db:
        db.execute("PRAGMA query_only=ON")
        count = db.execute("SELECT COUNT(*) FROM reservations").fetchone()[0]
        rows = db.execute(
            """SELECT
                 (SELECT MIN(recorded_at) FROM ledger_events e
                  WHERE e.request_id = r.request_id) AS started_at,
                 r.case_id, r.case_revision, r.attempt, r.model, r.status,
                 r.input_tokens, r.output_tokens, r.cost_nanos, r.amount_nanos, r.error_code
               FROM reservations r ORDER BY started_at DESC, r.rowid DESC LIMIT ?""",
            (USAGE_ROWS,),
        ).fetchall()
    return {
        "limit_usd": str(snapshot.limit_usd),
        "spent_usd": str(snapshot.settled_usd),
        "reserved_usd": str(snapshot.reserved_usd),
        "uncertain_usd": str(snapshot.uncertain_usd),
        "available_usd": str(snapshot.available_usd),
        "halted": snapshot.halted,
        "call_count": count,
        "calls": [
            {
                "started_at": started_at,
                "case_id": case_id,
                "case_revision": revision,
                "attempt": attempt,
                "model": model,
                "status": status,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": None if cost is None else _usd(cost),
                "reserved_usd": _usd(amount),
                "error_code": error_code,
            }
            for (
                started_at,
                case_id,
                revision,
                attempt,
                model,
                status,
                input_tokens,
                output_tokens,
                cost,
                amount,
                error_code,
            ) in rows
        ],
    }


def configured_user_app(
    values: Mapping[str, str], *, ledger_path: Path = USER_LEDGER, transport_factory=None
) -> FastAPI:
    app = configured_app(
        values,
        adapters_factory=lambda v: user_adapters(
            v, ledger_path=ledger_path, transport_factory=transport_factory
        ),
    )
    expected = "Bearer " + values["AGENT_REVIEWER_TOKEN"]

    @app.get("/usage")
    def usage(authorization: str | None = Header(default=None)) -> dict:
        if authorization is None or not hmac.compare_digest(authorization, expected):
            raise HTTPException(status_code=401, detail="ReviewerUnauthorized")
        try:
            return usage_report(ledger_path)
        except Exception:
            raise HTTPException(status_code=503, detail="UsageUnavailable") from None

    return app


def app_factory() -> FastAPI:
    """Uvicorn factory: ``uvicorn agent_app.user_backend:app_factory --factory``."""
    return configured_user_app(os.environ)
