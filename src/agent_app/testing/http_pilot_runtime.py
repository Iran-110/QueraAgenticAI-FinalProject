"""Reviewed offline HTTP bindings and observations for the exposed development pilot.

The default binding isolates both memory owners. It deliberately cannot recover
state from ``state_dir``; a fresh interpreter must reveal that limitation.
"""

import importlib
import io
import re
import socket
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import patch

from fastapi import FastAPI

from agent_app import api
from agent_app.contracts import CaseState, EvidenceBundle, ReasoningContext, RetrievalRequest
from agent_app.orchestration.ports import Reasoner, ReasoningOutput, Retriever
from agent_app.tracker.dummy_tracker import DummyTracker

DEFAULT_FACTORY = "agent_app.testing.http_pilot_runtime:memory_factory"
_FACTORY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*:[A-Za-z_][A-Za-z0-9_]*")
_BACKEND = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,99}")


class HTTPRuntimeRejected(ValueError):
    """Fixed diagnostics only; factory exceptions and configuration stay private."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class HTTPRuntime:
    app: FastAPI
    tracker_backend: str
    durable_review: bool = False
    review_headers: dict[str, str] = field(default_factory=dict, repr=False)
    local_actions_supplier: Callable[[str], list[dict]] | None = field(default=None, repr=False)


@contextmanager
def memory_factory(state_dir: Path) -> Iterator[HTTPRuntime]:
    """Fresh process-memory API; no copying, loading or pretending to persist state."""
    del state_dir  # The memory backend has no durable storage to reopen.
    with patch.object(api, "_cases", {}), patch.object(api, "tracker", DummyTracker()):
        yield HTTPRuntime(api.app, "process_memory_dummy_tracker")


@contextmanager
def load_runtime(spec: str, state_dir: Path) -> Iterator[HTTPRuntime]:
    """Load an already-reviewed context-manager factory, without diagnostic leakage.

    Factories must bind the actual api.app and its api._adapters injection seam.
    The caller reviews that wiring before execution; neither app identity nor
    a backend label proves durable actions. This is not an import sandbox.
    """
    if type(spec) is not str or len(spec) > 300 or not _FACTORY.fullmatch(spec):
        raise HTTPRuntimeRejected("HTTPFactoryInvalid")
    if not isinstance(state_dir, Path):
        raise HTTPRuntimeRejected("HTTPRuntimeInvalid")
    module_name, factory_name = spec.split(":")
    # Imports, context entry, routes and cleanup can print; none of that output
    # belongs in an acceptance receipt or should reach the invoking terminal.
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        try:
            factory = getattr(importlib.import_module(module_name), factory_name)
            if not callable(factory):
                raise ValueError("HTTPFactoryUnavailable")
            manager = factory(state_dir)
            runtime = manager.__enter__()
        except Exception:
            raise HTTPRuntimeRejected("HTTPFactoryUnavailable") from None
        try:
            if (
                not isinstance(runtime, HTTPRuntime)
                or not isinstance(runtime.app, FastAPI)
                or runtime.app is not api.app
                or type(runtime.tracker_backend) is not str
                or not _BACKEND.fullmatch(runtime.tracker_backend)
                or type(runtime.durable_review) is not bool
                or type(runtime.review_headers) is not dict
                or any(
                    type(k) is not str or type(v) is not str
                    for k, v in runtime.review_headers.items()
                )
                or (
                    runtime.local_actions_supplier is not None
                    and not callable(runtime.local_actions_supplier)
                )
            ):
                raise HTTPRuntimeRejected("HTTPRuntimeInvalid")
            yield runtime
        except BaseException:
            # A factory cannot suppress a failing probe by returning True from
            # __exit__. Give cleanup its real exception context, then propagate.
            try:
                manager.__exit__(*sys.exc_info())
            except Exception:
                raise HTTPRuntimeRejected("HTTPFactoryUnavailable") from None
            raise
        else:
            try:
                manager.__exit__(None, None, None)
            except Exception:
                raise HTTPRuntimeRejected("HTTPFactoryUnavailable") from None


def _network_disabled(*_args: Any, **_kwargs: Any) -> Any:
    raise RuntimeError("OfflineNetworkBlocked")


@contextmanager
def offline_network() -> Iterator[None]:
    """Reject actual connections and name resolution; keep ASGI/socketpair usable."""
    with (
        patch.object(socket.socket, "connect", _network_disabled),
        patch.object(socket.socket, "connect_ex", _network_disabled),
        patch.object(socket, "create_connection", _network_disabled),
        patch.object(socket, "getaddrinfo", _network_disabled),
    ):
        yield


@dataclass
class Observations:
    """Count actual port invocation, including failed calls, independently of output."""

    factory_calls: int = 0
    retrieval_calls: int = 0
    reasoning_calls: int = 0
    observed_inputs: list[dict[str, Any]] = field(default_factory=list)

    def snapshot(self) -> dict[str, int]:
        return {
            "factory_calls": self.factory_calls,
            "retrieval_calls": self.retrieval_calls,
            "reasoning_calls": self.reasoning_calls,
        }

    def wrap(self, ports: api.RunAdapters) -> api.RunAdapters:
        self.factory_calls += 1
        return api.RunAdapters(
            _ObservedRetriever(ports.retriever, self),
            _ObservedReasoner(ports.reasoner, self),
            snapshot_id=ports.snapshot_id,
            grounded_request_supplier=ports.grounded_request_supplier,
        )


@dataclass
class _ObservedRetriever:
    retriever: Retriever
    observations: Observations

    def search(self, request: RetrievalRequest) -> EvidenceBundle:
        self.observations.retrieval_calls += 1
        return self.retriever.search(request)


@dataclass
class _ObservedReasoner:
    reasoner: Reasoner
    observations: Observations

    def analyze(
        self,
        case: CaseState,
        user_message: str,
        evidence: EvidenceBundle,
        *,
        context: ReasoningContext,
    ) -> ReasoningOutput:
        self.observations.reasoning_calls += 1
        self.observations.observed_inputs.append(
            {
                "case_id": case.case_id,
                "case_revision": case.case_revision,
                "case": case.model_dump(mode="json"),
                "user_message": user_message,
                "evidence_snapshot_id": evidence.snapshot_id,
                "evidence_chunk_ids": [hit.chunk_id for hit in evidence.hits],
            }
        )
        return self.reasoner.analyze(case, user_message, evidence, context=context)
