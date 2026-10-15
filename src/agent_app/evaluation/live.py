"""Explicit development live adapters; no fixture, default key loading or halt bypass.

The no-argument CLI factory uses the designated existing ledger. Programmatic
callers can supply a disposable ledger and MockTransport for offline verification.
This docs-only lexical index integration is not a final-corpus quality claim.
"""

import hashlib
import json
import os
import re
import sqlite3
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import closing
from copy import deepcopy
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from threading import RLock
from typing import get_args

import httpx
from pydantic import TypeAdapter

from agent_app import api
from agent_app.contracts import GroundedGap, Identifier, ReasoningContext, RetrievalRequest
from agent_app.llm.budget import BudgetLedger
from agent_app.llm.config import METIS_CHAT_URL, MetisConfig
from agent_app.llm.grounded import MetisGroundedPlanner
from agent_app.llm.metis import configured_grounded_messages, request_id_for
from agent_app.llm.pricing import get_price, same_verified_price
from agent_app.orchestration.ports import ReasoningStopCode, ReasoningStopped
from agent_app.orchestration.retrieval_profile import validate_retrieval_profile
from agent_app.reasoning.catalog import caller_catalog, load_user_gap_vocabulary, validate_user_gaps
from agent_app.reasoning.grounding import GroundedReasoner
from agent_app.retrieval.adapter import ChromaRetrieverAdapter
from agent_app.retrieval.offline_index import open_verified_index
from agent_app.retrieval.pilot_corpus import MANIFEST_NAME
from agent_app.retrieval.retriever import StreamlitRetriever

ROOT = Path(__file__).resolve().parents[3]
_CODES = frozenset(get_args(ReasoningStopCode.__value__))


def _budget_guard(ledger):
    if not isinstance(ledger, BudgetLedger):
        raise ValueError("LiveLedgerRequired")
    try:
        state = ledger.snapshot()
    except Exception:
        raise ValueError("LiveLedgerUnavailable") from None
    if state.limit_usd > Decimal("5"):
        raise ValueError("LiveLedgerLimitInvalid")
    if state.halted:
        raise ValueError("LiveLedgerHalted")
    try:
        with closing(sqlite3.connect(ledger._path.as_uri() + "?mode=ro", uri=True)) as connection:
            connection.execute("PRAGMA query_only=ON")
            unresolved = (
                connection.execute(
                    "SELECT 1 FROM reservations WHERE status IN ('reserved', 'uncertain') LIMIT 1"
                ).fetchone()
                is not None
            )
    except Exception:
        raise ValueError("LiveLedgerUnavailable") from None
    if state.reserved_usd or state.uncertain_usd or unresolved:
        raise ValueError("LiveAccountingUnresolved")
    if state.available_usd <= 0:
        raise ValueError("LiveBudgetUnavailable")
    return state


def _verified_index(path, snapshot_id, manifest_sha256):
    try:
        if (
            type(snapshot_id) is not str
            or re.fullmatch(r"docs-pilot-[0-9a-f]{64}", snapshot_id) is None
            or type(manifest_sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", manifest_sha256) is None
            or hashlib.sha256((Path(path) / MANIFEST_NAME).read_bytes()).hexdigest()
            != manifest_sha256
        ):
            raise ValueError
        client, actual = open_verified_index(path)
        if actual != snapshot_id:
            raise ValueError
        return client
    except Exception:
        raise ValueError("LiveIndexRejected") from None


class _DecodedStream(httpx.SyncByteStream):
    """Observe only an allowlisted serving ID from the same decoded envelope."""

    def __init__(self, response, record, requested_model):
        self.response, self.record, self.model = response, record, requested_model

    def __iter__(self) -> Iterator[bytes]:
        bounded = bytearray()
        overflow = False
        for chunk in self.response.iter_bytes():
            if len(bounded) + len(chunk) > 262_144:
                bounded.clear()
                overflow = True
            elif not overflow:
                bounded.extend(chunk)
            yield chunk
        if not overflow:
            try:
                model = json.loads(bounded).get("model")
                if isinstance(model, str) and same_verified_price(self.model, model):
                    self.record["verified_returned_model"] = model
            except (ValueError, AttributeError, TypeError):
                pass

    def close(self):
        self.response.close()


class _ObservedTransport(httpx.BaseTransport):
    def __init__(self, underlying, ledger, config):
        self.underlying, self.ledger, self.config = underlying, ledger, config
        self.current = None

    def handle_request(self, request):
        record = self.current
        reservation = self.ledger.get(record["request_id"]) if record else None
        if (
            record is None
            or reservation is None
            or reservation.status != "reserved"
            or reservation.model != self.config.model
            or reservation.phase != self.config.phase
            or str(request.url) != METIS_CHAT_URL
            or request.method != "POST"
        ):
            raise ReasoningStopped("ProviderRequestFailed")
        record["http_send_started"] = True
        response = self.underlying.handle_request(request)
        record["http_status"] = response.status_code
        headers = dict(response.headers)
        headers.pop("content-encoding", None)
        headers.pop("content-length", None)
        return httpx.Response(
            response.status_code,
            headers=headers,
            stream=_DecodedStream(response, record, self.config.model),
            extensions=response.extensions,
            request=request,
        )

    def close(self):
        self.underlying.close()


class _BoundedRetriever:
    def __init__(self, adapter, top_k):
        self.adapter, self.top_k = adapter, top_k

    def search(self, request):
        bounded = RetrievalRequest.model_validate(
            {**request.model_dump(), "top_k": min(self.top_k, request.top_k)}
        )
        return self.adapter.search(bounded)


class _Run:
    def __init__(self, owner, case_id, transport):
        self.owner, self.case_id, self.transport = owner, case_id, transport
        self.lock, self.closed, self.latest = RLock(), False, None
        self.gateway = MetisGroundedPlanner(owner._config, owner.ledger, transport=transport)

    def supplied_request(self):
        with self.lock:
            return self.latest.model_copy(deep=True) if self.latest else None

    def plan(self, request, *, context):
        with self.lock:
            if self.closed:
                raise ReasoningStopped("LiveCallsDisabled")
            if request.case.case_id != self.case_id or context.case_id != self.case_id:
                raise ReasoningStopped("ProviderRequestFailed")
            try:
                _budget_guard(self.owner.ledger)
            except ValueError:
                raise ReasoningStopped("BudgetExceeded", "budget_stopped") from None
            self.latest = request.model_copy(deep=True)
            record = {
                "request_id": request_id_for(context),
                "run_id": context.run_id,
                "case_id": context.case_id,
                "case_revision": context.case_revision,
                "attempt_index": context.attempt_index,
                "prompt_sha256": hashlib.sha256(
                    json.dumps(
                        configured_grounded_messages(self.owner._config, request, context),
                        ensure_ascii=False,
                    ).encode()
                ).hexdigest(),
                "requested_model": self.owner._config.model,
                "verified_returned_model": None,
                "http_send_started": False,
                "http_status": None,
                "ledger_status": None,
                "input_tokens": None,
                "output_tokens": None,
                "cost_estimated_usd": None,
                "held_usd": None,
                "error_code": None,
            }
            self.owner._observations.append(record)
            self.transport.current = record
            try:
                return self.gateway.plan(request, context=context)
            except ReasoningStopped as error:
                record["error_code"] = (
                    error.code
                    if type(error.code) is str and error.code in _CODES
                    else "ProviderRequestFailed"
                )
                raise
            finally:
                if self.owner._config.grounded_compact_plan:
                    record["wire_output"] = self.gateway.latest_wire_observation(context)
                self.transport.current = None
                try:
                    reservation = self.owner.ledger.get(record["request_id"])
                    if reservation is not None:
                        row = asdict(reservation)
                        record["ledger_status"] = row["status"]
                        record["input_tokens"] = row["input_tokens"]
                        record["output_tokens"] = row["output_tokens"]
                        record["cost_estimated_usd"] = (
                            str(row["cost_usd"]) if row["cost_usd"] is not None else None
                        )
                        record["held_usd"] = (
                            str(row["amount_usd"])
                            if row["status"] in {"reserved", "uncertain"}
                            else None
                        )
                        if row["error_code"] in _CODES:
                            record["error_code"] = row["error_code"]
                except Exception:
                    record["error_code"] = "LedgerUnavailable"

    def close(self):
        with self.lock:
            if self.closed:
                return
            self.closed = True
            try:
                self.gateway.close()
            finally:
                with self.owner._lock:
                    self.owner._active.discard(self)


class LiveEvaluationAdapters:
    """Fresh case-bound ports; caller vocabulary contains no fixture or gold fields."""

    def __init__(
        self,
        *,
        index_path: Path,
        snapshot_id: str,
        manifest_sha256: str,
        ledger: BudgetLedger,
        config: MetisConfig,
        user_gaps: Iterable[GroundedGap] = (),
        top_k: int = 1,
        retrieval_profile: str = "native",
        ask_source_background: bool = False,
        concise_user_draft: bool = False,
        transport_factory: Callable[[], httpx.BaseTransport] | None = None,
    ):
        try:
            retrieval_profile = validate_retrieval_profile(retrieval_profile, top_k=top_k)
            if type(ask_source_background) is not bool:
                raise ValueError
            if type(concise_user_draft) is not bool:
                raise ValueError
        except ValueError:
            raise ValueError("LiveEvaluationConfigurationInvalid") from None
        state = _budget_guard(ledger)
        try:
            self._index_path = Path(index_path).resolve()
        except (OSError, TypeError, ValueError):
            raise ValueError("LiveIndexRejected") from None
        self._client = _verified_index(self._index_path, snapshot_id, manifest_sha256)
        try:
            config = MetisConfig.model_validate(config.model_dump(warnings=False))
            price = get_price(config.model)
            if (
                not config.live_enabled
                or config.response_mode != "grounded_plan"
                or config.continuation_id is not None
                or config.phase not in {"development", "evaluation"}
                or price is None
                or price.cost(config.input_token_reserve, config.max_output_tokens)
                > config.max_request_usd
                or type(top_k) is not int
                or not 1 <= top_k <= 5
                or (transport_factory is not None and not callable(transport_factory))
            ):
                raise ValueError
            self._gaps = validate_user_gaps(user_gaps)
        except Exception:
            raise ValueError("LiveEvaluationConfigurationInvalid") from None
        if price.cost(config.input_token_reserve, config.max_output_tokens) > state.available_usd:
            raise ValueError("LiveBudgetUnavailable")
        self.ledger, self._config, self._snapshot, self._top_k = ledger, config, snapshot_id, top_k
        self._retrieval_profile = retrieval_profile
        self._ask_source_background = ask_source_background
        self._concise_user_draft = concise_user_draft
        self._transport_factory = transport_factory or (lambda: httpx.HTTPTransport(retries=0))
        self._observations, self._active = [], set()
        self._lock = RLock()
        self._closed = False

    @property
    def config(self):
        adapter_id = "verified_chroma_metis_grounded_v1"
        retriever_id = f"verified_chroma_lexical_hash_top{self._top_k}_v1"
        if self._retrieval_profile == "candidate_relevance_v1":
            adapter_id = "verified_chroma_metis_grounded_candidate_relevance_v1"
            retriever_id = (
                "verified_chroma_lexical_hash_candidate_relevance_top5_window25_bytes12000_v1"
            )
        if self._ask_source_background:
            adapter_id += "_ask_source_background_v1"
        if self._config.grounded_json_object:
            adapter_id += "_json_object_v1"
        if self._concise_user_draft:
            adapter_id += "_concise_draft_v1"
        return {
            "model": self._config.model,
            "snapshot_id": self._snapshot,
            "prompt_policy": self._config.prompt_policy,
            "response_mode": "grounded_plan",
            "phase": self._config.phase,
            "adapter_id": adapter_id,
            "retriever_id": retriever_id,
        }

    @property
    def index_path(self) -> Path:
        """Pinned resolved storage directory; callers can protect it from tracker writes."""
        return self._index_path

    @property
    def ask_source_background(self) -> bool:
        """Trusted display policy for conditional routes, never a USER setting."""
        return self._ask_source_background

    @property
    def concise_user_draft(self) -> bool:
        """Trusted local presentation policy; never model or USER authority."""
        return self._concise_user_draft

    def observations_for_contexts(self, contexts: tuple[ReasoningContext, ...]):
        identities = {
            (
                request_id_for(context),
                context.run_id,
                context.case_id,
                context.case_revision,
                context.attempt_index,
            )
            for context in contexts
        }
        return deepcopy(
            [
                row
                for row in self._observations
                if (
                    row["request_id"],
                    row["run_id"],
                    row["case_id"],
                    row["case_revision"],
                    row["attempt_index"],
                )
                in identities
            ]
        )

    @property
    def active_clients(self):
        with self._lock:
            return len(self._active)

    def for_case(self, case_id: str) -> api.RunAdapters:
        with self._lock:
            return self._allocate_case(case_id)

    def _allocate_case(self, case_id: str) -> api.RunAdapters:
        if self._closed:
            raise ValueError("LiveEvaluationFactoryClosed")
        try:
            case_id = TypeAdapter(Identifier).validate_python(case_id)
        except Exception:
            raise ValueError("LiveEvaluationCaseInvalid") from None
        _budget_guard(self.ledger)
        self._client.verify()
        run = None
        transport = None
        try:
            native = StreamlitRetriever("", snapshot_id=self._snapshot, client=self._client)
            retriever = _BoundedRetriever(
                ChromaRetrieverAdapter(
                    "",
                    snapshot_id=self._snapshot,
                    core_retriever=native,
                    selection_policy=(
                        "query_relevance_v1"
                        if self._retrieval_profile == "candidate_relevance_v1"
                        else "native"
                    ),
                ),
                25 if self._retrieval_profile == "candidate_relevance_v1" else self._top_k,
            )
            underlying = self._transport_factory()
            if not isinstance(underlying, httpx.BaseTransport):
                raise ValueError
            transport = _ObservedTransport(underlying, self.ledger, self._config)
            run = _Run(self, case_id, transport)
            self._active.add(run)
            return api.RunAdapters(
                retriever,
                GroundedReasoner(
                    run,
                    source_gap_handoff=self._config.grounded_source_gap_handoff,
                    source_gap_investigation=self._config.grounded_source_gap_investigation,
                    ask_source_background=self._ask_source_background,
                    **({"concise_user_draft": True} if self._concise_user_draft else {}),
                    request_factory=lambda case, message, evidence: caller_catalog(
                        case, message, evidence, definitions=self._gaps
                    ),
                ),
                snapshot_id=self._snapshot,
                grounded_request_supplier=run.supplied_request,
                cleanup=run.close,
                retrieval_profile=self._retrieval_profile,
            )
        except Exception:
            if run is not None:
                run.close()
            elif transport is not None:
                transport.close()
            raise ValueError("LiveEvaluationAdapterUnavailable") from None

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
            runs = tuple(self._active)
        failed = False
        for run in runs:
            try:
                run.close()
            except Exception:
                failed = True
        if failed:
            raise ValueError("LiveEvaluationCleanupFailed") from None


def configured_factory(values: Mapping[str, str]) -> LiveEvaluationAdapters:
    """Budget/index preflight precede the first credential lookup; never load .env."""
    try:
        if values.get("METIS_LIVE_ENABLED") != "true":
            raise ValueError("LiveCallsDisabled")
        top_k = int(values.get("AGENT_EVAL_TOP_K", "1"))
        retrieval_profile = validate_retrieval_profile(
            values.get("AGENT_RETRIEVAL_PROFILE", "native"), top_k=top_k
        )
        ask_source_background = values.get("AGENT_GROUNDED_ASK_SOURCE_BACKGROUND", "false")
        if type(ask_source_background) is not str or ask_source_background not in {"true", "false"}:
            raise ValueError("LiveEvaluationConfigurationInvalid")
        concise_user_draft = values.get("AGENT_GROUNDED_CONCISE_USER_DRAFT", "false")
        if type(concise_user_draft) is not str or concise_user_draft not in {"true", "false"}:
            raise ValueError("LiveEvaluationConfigurationInvalid")
        ledger_path = ROOT / "runtime/budget.sqlite3"
        if (
            Path(values.get("AGENT_EVAL_LEDGER", str(ledger_path))).resolve()
            != ledger_path.resolve()
        ):
            raise ValueError("LiveLedgerPathRejected")
        ledger = BudgetLedger(ledger_path)
        state = _budget_guard(ledger)
        index_path = Path(values["AGENT_EVAL_INDEX"])
        snapshot = values["AGENT_EVAL_SNAPSHOT"]
        manifest = values["AGENT_EVAL_MANIFEST_SHA256"]
        _verified_index(index_path, snapshot, manifest)
        user_gaps = (
            load_user_gap_vocabulary(values["AGENT_USER_GAP_CATALOG"])
            if "AGENT_USER_GAP_CATALOG" in values
            else ()
        )
        switches = {
            name: values.get(name, "false")
            for name in (
                "METIS_GROUNDED_DECISION_CONTRACTS",
                "METIS_GROUNDED_SOURCE_GAP_HANDOFF",
                "METIS_GROUNDED_SOURCE_GAP_INVESTIGATION",
                "METIS_GROUNDED_SOURCE_SELECTION_REMINDER",
                "METIS_GROUNDED_RESOURCE_GUIDANCE",
                "METIS_GROUNDED_SOURCE_CAPACITY",
                "METIS_GROUNDED_COMPACT_PLAN",
                "METIS_GROUNDED_JSON_OBJECT",
            )
        }
        if any(
            type(value) is not str or value not in {"true", "false"} for value in switches.values()
        ):
            raise ValueError("LiveEvaluationConfigurationInvalid")
        prepared = MetisConfig(
            api_key="public-placeholder-for-noncredential-config-validation",
            live_enabled=True,
            model=values.get("METIS_MODEL", "gpt-4o-mini"),
            response_mode="grounded_plan",
            grounded_decision_contracts=switches["METIS_GROUNDED_DECISION_CONTRACTS"] == "true",
            grounded_source_gap_handoff=switches["METIS_GROUNDED_SOURCE_GAP_HANDOFF"] == "true",
            grounded_source_gap_investigation=switches["METIS_GROUNDED_SOURCE_GAP_INVESTIGATION"]
            == "true",
            grounded_source_selection_reminder=switches["METIS_GROUNDED_SOURCE_SELECTION_REMINDER"]
            == "true",
            grounded_resource_guidance=switches["METIS_GROUNDED_RESOURCE_GUIDANCE"] == "true",
            grounded_source_capacity=switches["METIS_GROUNDED_SOURCE_CAPACITY"] == "true",
            grounded_compact_plan=switches["METIS_GROUNDED_COMPACT_PLAN"] == "true",
            grounded_json_object=switches["METIS_GROUNDED_JSON_OBJECT"] == "true",
            phase=values.get("AGENT_EVAL_PHASE", "development"),
            input_token_reserve=int(values.get("METIS_INPUT_TOKEN_RESERVE", "32768")),
            max_output_tokens=int(values.get("METIS_MAX_OUTPUT_TOKENS", "1024")),
            max_request_usd=Decimal(values.get("METIS_MAX_REQUEST_USD", "0.02")),
        )
        price = get_price(prepared.model)
        if (
            price is None
            or prepared.phase not in {"development", "evaluation"}
            or not 1 <= top_k <= 5
            or price.cost(prepared.input_token_reserve, prepared.max_output_tokens)
            > prepared.max_request_usd
        ):
            raise ValueError("LiveEvaluationConfigurationInvalid")
        if (
            price.cost(prepared.input_token_reserve, prepared.max_output_tokens)
            > state.available_usd
        ):
            raise ValueError("LiveBudgetUnavailable")
        config = MetisConfig(
            **prepared.model_dump(exclude={"api_key"}), api_key=values.get("METIS_API_KEY", "")
        )
        return LiveEvaluationAdapters(
            index_path=index_path,
            snapshot_id=snapshot,
            manifest_sha256=manifest,
            ledger=ledger,
            config=config,
            top_k=top_k,
            retrieval_profile=retrieval_profile,
            ask_source_background=ask_source_background == "true",
            concise_user_draft=concise_user_draft == "true",
            user_gaps=user_gaps,
        )
    except ValueError as error:
        if str(error) in {
            "LiveCallsDisabled",
            "LiveLedgerPathRejected",
            "LiveLedgerHalted",
            "LiveLedgerLimitInvalid",
            "LiveLedgerUnavailable",
            "LiveAccountingUnresolved",
            "LiveBudgetUnavailable",
            "LiveIndexRejected",
        }:
            raise ValueError(str(error)) from None
        raise ValueError("LiveEvaluationConfigurationInvalid") from None
    except Exception:
        raise ValueError("LiveEvaluationConfigurationInvalid") from None


def factory() -> LiveEvaluationAdapters:
    return configured_factory(os.environ)
