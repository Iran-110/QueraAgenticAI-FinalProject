"""Explicit local persistent composition; never loads .env or a model provider.

The optional docs index uses local lexical hashing. Routing is scripted and
conservative: this launcher cannot establish retrieval or decision quality.
"""

import os
import re
from collections.abc import Mapping
from pathlib import Path

from fastapi import FastAPI

from agent_app import api
from agent_app.contracts import AnalysisResult, Identifier, ReasoningContext
from agent_app.orchestration.intake import STREAMLIT_VERSION_QUESTION
from agent_app.persistent_api import create_app
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


def configured_app(config: Mapping[str, str]) -> FastAPI:
    """Resolve only explicit local config. No credentials in responses or errors."""
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
        adapters = None
        label = "scripted"
        if index is not None:
            if type(index) is not str or not index.strip():
                raise ValueError
            from agent_app.retrieval.adapter import ChromaRetrieverAdapter
            from agent_app.retrieval.offline_index import open_verified_index
            from agent_app.retrieval.retriever import StreamlitRetriever

            client, snapshot = open_verified_index(Path(index))
            retriever = ChromaRetrieverAdapter(
                "",
                snapshot_id=snapshot,
                core_retriever=StreamlitRetriever("", snapshot_id=snapshot, client=client),
            )

            def indexed_adapters(_scenario):
                return api.RunAdapters(retriever, PilotReasoner(), snapshot_id=snapshot)

            adapters = indexed_adapters
            label = "local_chroma_hash"
        tokens = {reviewer: token}
        tracker = SQLiteCaseTracker(Path(database), reviewer_tokens=tokens)
        return create_app(tracker, reviewer_tokens=tokens, adapters=adapters, retrieval_label=label)
    except Exception:
        raise ValueError("OfflineBackendConfigurationInvalid") from None


def application_factory() -> FastAPI:
    """Uvicorn --factory entrypoint; use loopback and a private reviewer console."""
    return configured_app(os.environ)
