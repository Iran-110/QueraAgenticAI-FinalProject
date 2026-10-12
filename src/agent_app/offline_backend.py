"""Explicit local persistent composition; never loads .env or a model provider.

The optional docs index uses local lexical hashing. Reasoning is scripted or an
explicitly mocked GroundedPlan gateway; neither establishes decision quality.
"""

import os
import re
from collections.abc import Mapping
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import FastAPI

from agent_app import api
from agent_app.contracts import (
    AnalysisResult,
    GroundedPlan,
    GroundedSourceRef,
    Identifier,
    ReasoningContext,
)
from agent_app.orchestration.intake import STREAMLIT_VERSION_QUESTION
from agent_app.persistent_api import create_app
from agent_app.reasoning.grounding import source_content_sha256
from agent_app.tracker.sqlite_tracker import SQLiteCaseTracker


class PilotReasoner:
    """No gold data, expected output or model requests enter this scripted port."""

    def analyze(self, case, user_message, evidence, *, context: ReasoningContext):
        if not any(
            f.name.casefold() == "streamlit_version" and f.status == "active" and f.value
            for f in case.facts
        ):
            target = STREAMLIT_VERSION_QUESTION
            return AnalysisResult(
                decision="ask",
                user_draft=target.question,
                next_question=target.question,
                missing_info=(target.name,),
                maintainer_summary="Scripted pilot: the user has not confirmed a version.",
                rationale="The user can supply the version; documentation cannot supply it.",
            )
        return AnalysisResult(
            decision="escalate",
            user_draft="A maintainer should review the retrieved documentation for this case.",
            maintainer_summary=(
                "Scripted pilot: documentation was searched, but this offline routing rule "
                "does not establish that a source answers the issue."
            ),
            rationale="The pilot verifies integration; semantic support requires separate review.",
        )


class PilotGroundedPlanner:
    """Authored transport response for wiring; never model decision quality."""

    def plan(self, request, *, context):
        question = next((gap for gap in request.gaps if gap.kind == "user"), None)
        return GroundedPlan(
            context_sha256=request.context_sha256,
            decision="ask" if question else "escalate",
            question_name=question.name if question else None,
            sources=tuple(
                GroundedSourceRef(chunk_id=hit.chunk_id, content_sha256=source_content_sha256(hit))
                for hit in request.evidence.hits[:1]
            )
            if not question
            else (),
        )


def configured_app(config: Mapping[str, str]) -> FastAPI:
    """Resolve only explicit local config. No credentials in responses or errors."""
    temporary = None
    binding = None
    try:
        database = config["AGENT_TRACKER_DB"]
        token = config["AGENT_REVIEWER_TOKEN"]
        reviewer = config.get("AGENT_REVIEWER_ID", "local-maintainer")
        if (
            type(database) is not str
            or not database.strip()
            or database == ":memory:"
            or type(token) is not str
            or len(token) < 32
            or len(token) > 512
            or re.fullmatch(r"[A-Za-z0-9._~+/-]+={0,}", token) is None
        ):
            raise ValueError
        from pydantic import TypeAdapter

        TypeAdapter(Identifier).validate_python(reviewer)
        index = config.get("AGENT_PILOT_INDEX")
        reasoning_label = config.get("AGENT_PILOT_REASONING", "scripted")
        if reasoning_label not in {"scripted", "grounded_fake_gateway"}:
            raise ValueError
        expected_snapshot = config.get("AGENT_PILOT_SNAPSHOT")
        adapters = None
        label = "scripted"
        if index is not None:
            if (
                type(index) is not str
                or not index.strip()
                or type(expected_snapshot) is not str
                or re.fullmatch(r"docs-pilot-[0-9a-f]{64}", expected_snapshot) is None
            ):
                raise ValueError
            from agent_app.retrieval.adapter import ChromaRetrieverAdapter
            from agent_app.retrieval.offline_index import open_verified_index
            from agent_app.retrieval.retriever import StreamlitRetriever

            client, snapshot = open_verified_index(Path(index))
            if snapshot != expected_snapshot:
                raise ValueError

            def retriever_factory():
                return ChromaRetrieverAdapter(
                    "",
                    snapshot_id=snapshot,
                    core_retriever=StreamlitRetriever("", snapshot_id=snapshot, client=client),
                )

            def indexed_adapters(_scenario):
                return api.RunAdapters(retriever_factory(), PilotReasoner(), snapshot_id=snapshot)

            adapters = indexed_adapters
            label = "local_chroma_hash"
        elif expected_snapshot is not None:
            raise ValueError
        if reasoning_label == "grounded_fake_gateway":
            from agent_app.llm.budget import BudgetLedger
            from agent_app.testing.grounded_http_binding import GroundedHttpBinding

            temporary = TemporaryDirectory(prefix="agent-grounded-fake-")
            ledger = BudgetLedger.create(
                Path(temporary.name) / "mock-ledger.sqlite3",
                limit_usd=Decimal("1"),
                opening_spend_usd=Decimal("0"),
            )
            binding = GroundedHttpBinding(
                ledger,
                retriever_factory=(
                    retriever_factory
                    if index is not None
                    else lambda: api._adapters("ask").retriever
                ),
                snapshot_id=snapshot if index is not None else api.SNAPSHOT_ID,
                planner_factory=PilotGroundedPlanner,
                retain_records=False,
            )
            adapters = binding.adapters
        tokens = {reviewer: token}
        tracker = SQLiteCaseTracker(Path(database), reviewer_tokens=tokens)
        application = create_app(
            tracker,
            reviewer_tokens=tokens,
            adapters=adapters,
            retrieval_label=label,
            reasoning_label=reasoning_label,
        )
        if binding is not None:

            @asynccontextmanager
            async def lifespan(_app):
                try:
                    yield
                finally:
                    try:
                        binding.close()
                    finally:
                        temporary.cleanup()

            application.router.lifespan_context = lifespan
        return application
    except Exception:
        if binding is not None:
            try:
                binding.close()
            except Exception:
                pass
        if temporary is not None:
            temporary.cleanup()
        raise ValueError("OfflineBackendConfigurationInvalid") from None


def application_factory() -> FastAPI:
    """Uvicorn --factory entrypoint; use loopback and a private reviewer console."""
    return configured_app(os.environ)
