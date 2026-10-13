"""Explicit local live composition, blocked by the existing accounting halt.

No .env is loaded, no database is reset, and app startup sends no model request.
The UI uses the same persistent HTTP endpoints and existing SQLite tracker.
"""

import os
import re
from collections.abc import Callable, Mapping
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from pydantic import TypeAdapter

from agent_app.contracts import Identifier
from agent_app.evaluation.live import LiveEvaluationAdapters, configured_factory
from agent_app.persistent_api import create_app
from agent_app.tracker.sqlite_tracker import SQLiteCaseTracker


def configured_app(
    values: Mapping[str, str],
    *,
    adapters_factory: Callable[[Mapping[str, str]], LiveEvaluationAdapters] = configured_factory,
) -> FastAPI:
    """Pin the backend explicitly; credentials are never part of public state.

    ``adapters_factory`` is caller-owned injection for controlled tests or an
    approved vocabulary configuration, never selected by a user/model message.
    The ordinary configured factory checks the designated ledger and index
    before key lookup; C5 remains blocked. Caller configuration is not proof of
    a reviewed final corpus, independent evaluation or semantic quality.
    """
    factory = None
    try:
        database = values["AGENT_TRACKER_DB"]
        token = values["AGENT_REVIEWER_TOKEN"]
        reviewer = values.get("AGENT_REVIEWER_ID", "local-maintainer")
        if (
            type(database) is not str
            or not database.strip()
            or database == ":memory:"
            or type(token) is not str
            or not 32 <= len(token) <= 512
            or re.fullmatch(r"[A-Za-z0-9._~+/-]+={0,}", token) is None
            or not callable(adapters_factory)
        ):
            raise ValueError
        TypeAdapter(Identifier).validate_python(reviewer)
        # Fail a halted/invalid ordinary live configuration before creating the
        # tracker database. Construction must allocate no provider client/send.
        factory = adapters_factory(values)
        if not isinstance(factory, LiveEvaluationAdapters):
            raise ValueError
        database_path = Path(database).resolve()
        ledger_path = factory.ledger._path.resolve()
        index_path = factory.index_path
        protected_files = (ledger_path, *(path for path in index_path.rglob("*") if path.is_file()))
        if database_path.is_relative_to(index_path) or any(
            database_path == path or (database_path.exists() and database_path.samefile(path))
            for path in protected_files
        ):
            raise ValueError
        tokens = {reviewer: token}
        tracker = SQLiteCaseTracker(database_path, reviewer_tokens=tokens)
        app = create_app(
            tracker,
            reviewer_tokens=tokens,
            case_adapters=lambda case, _scenario: factory.for_case(case.case_id),
            retrieval_label="local_chroma_hash",
            reasoning_label="metis_grounded_live",
            evidence_scope="exact_user_version",
        )

        @asynccontextmanager
        async def lifespan(_app):
            try:
                yield
            finally:
                factory.close()

        app.router.lifespan_context = lifespan
        return app
    except Exception:
        if factory is not None:
            try:
                factory.close()
            except Exception:
                pass
        raise ValueError("LiveBackendConfigurationInvalid") from None


def app_factory() -> FastAPI:
    """Uvicorn factory using explicitly installed private environment settings."""
    return configured_app(os.environ)
