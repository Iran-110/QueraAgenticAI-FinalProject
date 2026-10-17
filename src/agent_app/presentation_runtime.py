"""Finite presentation-only live composition; ordinary live guards stay unchanged.

An operator registers the exact protocol in the existing quarantine ledger before
construction. This module never loads .env, registers funding, clears a halt or
reconciles an uncertain request. Every provider attempt retains the gateway's
normal reservation and uncertainty rules.
"""

import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping
from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from threading import RLock

import httpx
from fastapi import FastAPI
from pydantic import SecretStr, TypeAdapter

from agent_app import api
from agent_app.contracts import CaseState, Identifier, ReasoningContext
from agent_app.evaluation.live import _BoundedRetriever, _ObservedTransport, _verified_index
from agent_app.llm.budget import BudgetLedger, ExperimentRequestSlot
from agent_app.llm.config import MetisConfig
from agent_app.llm.grounded import MetisGroundedPlanner
from agent_app.llm.metis import configured_grounded_messages, request_id_for
from agent_app.llm.pricing import get_price
from agent_app.orchestration.core_delivery import PREFILTER_DELIVERY_PROFILE_ID, delivery_recipe
from agent_app.orchestration.ports import ReasoningStopped
from agent_app.persistent_api import create_app
from agent_app.reasoning.catalog import caller_catalog, load_user_gap_vocabulary
from agent_app.reasoning.grounding import GroundedReasoner
from agent_app.retrieval.adapter import ChromaRetrieverAdapter
from agent_app.retrieval.retriever import StreamlitRetriever
from agent_app.tracker.sqlite_tracker import SQLiteCaseTracker

ROOT = Path(__file__).resolve().parents[2]
PROFILE_ID = "presentation_scoped_v1"
RETRIEVAL_PROFILE = "candidate_version_prefilter_v1"
RECIPE_PATH = "config/core-delivery-grounded-prefilter-v2.json"
VOCABULARY_PATH = "config/user-gap-support-dev-v1.json"
BOUND_SOURCE_FILES = (
    "src/agent_app/presentation_runtime.py",
    "src/agent_app/presentation_session.py",
    "src/agent_app/persistent_api.py",
    "src/agent_app/ui_client.py",
    "app_pages/assistant.py",
    "src/agent_app/evaluation/live.py",
    "src/agent_app/orchestration/service.py",
    "src/agent_app/orchestration/engine.py",
    "src/agent_app/orchestration/core_delivery.py",
    "src/agent_app/orchestration/retrieval_profile.py",
    "src/agent_app/reasoning/grounding.py",
    "src/agent_app/reasoning/prompts.py",
    "src/agent_app/reasoning/catalog.py",
    "src/agent_app/reasoning/compact_plan.py",
    "src/agent_app/llm/config.py",
    "src/agent_app/llm/budget.py",
    "src/agent_app/llm/pricing.py",
    "src/agent_app/llm/metis.py",
    "src/agent_app/llm/grounded.py",
    "src/agent_app/retrieval/adapter.py",
    "src/agent_app/retrieval/offline_index.py",
)
_ERROR = "PresentationConfigurationRejected"


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _digest(value):
    return _sha(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(_ERROR)
        result[key] = value
    return result


def read_protocol(path):
    """Validate public local protocol before any credential mapping is consulted."""
    try:
        requested = Path(path)
        if requested.name != "protocol.json" or requested.is_symlink():
            raise ValueError
        path = requested.resolve()
        if path.name != "protocol.json" or path == ROOT or ROOT in path.parents:
            raise ValueError
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 2_000_000:
            raise ValueError
        raw = path.read_bytes()
        if len(raw) > 2_000_000:
            raise ValueError
        value = json.loads(raw, object_pairs_hook=_unique)
        recipe = delivery_recipe(profile_id=PREFILTER_DELIVERY_PROFILE_ID)
        if (
            type(value) is not dict
            or type(value.get("schema_version")) is not int
            or value["schema_version"] != 1
            or value["profile_id"] != PROFILE_ID
            or value["phase_label"] not in {"rehearsal", "meeting"}
            or value["model"] != "gpt-4o-mini"
            or value["recipe_sha256"] != recipe["recipe_sha256"]
            or value["recipe_file_sha256"] != _sha((ROOT / RECIPE_PATH).read_bytes())
            or value["vocabulary_file_sha256"] != _sha((ROOT / VOCABULARY_PATH).read_bytes())
            or json.loads((ROOT / RECIPE_PATH).read_bytes()) != recipe
            or Decimal(value["max_scope_usd"]) != Decimal("0.10")
            or set(value["source_sha256"]) != set(BOUND_SOURCE_FILES)
            or any(
                _sha((ROOT / name).read_bytes()) != digest
                for name, digest in value["source_sha256"].items()
            )
        ):
            raise ValueError
        for key in ("ledger_path", "tracker_path", "receipt_dir"):
            if not Path(value[key]).is_absolute():
                raise ValueError
        index_path = Path(value["index"]["path"])
        if not index_path.is_absolute():
            raise ValueError
        index_path = index_path.resolve()
        ledger_path = Path(value["ledger_path"]).resolve()
        tracker_path = Path(value["tracker_path"]).resolve()
        receipt_dir = Path(value["receipt_dir"]).resolve()
        if (
            ledger_path == tracker_path
            or any(
                p == index_path or index_path in p.parents
                for p in (ledger_path, tracker_path, receipt_dir)
            )
            or receipt_dir == ROOT
            or ROOT in receipt_dir.parents
            or receipt_dir in (ledger_path, tracker_path)
            or receipt_dir in ledger_path.parents
            or receipt_dir in tracker_path.parents
            or path in (ledger_path, tracker_path)
            or path == index_path
            or index_path in path.parents
            or path.name == ".env"
        ):
            raise ValueError
        protected = (ledger_path, *(p for p in index_path.rglob("*") if p.is_file()))
        if any(
            tracker_path == p or (tracker_path.exists() and tracker_path.samefile(p))
            for p in protected
        ) or any(path.exists() and path.samefile(p) for p in protected):
            raise ValueError
        accepted = json.loads(
            (ROOT / "experiments/final_corpus_v1/build-receipt-v3.json").read_bytes()
        )["native_pins"]
        index = value["index"]
        if any(
            index[key] != accepted[accepted_key]
            for key, accepted_key in (
                ("snapshot_id", "index_snapshot"),
                ("index_manifest_sha256", "index_manifest_sha256"),
                ("allowlist_sha256", "allowlist_sha256"),
                ("exclusion_manifest_sha256", "exclusion_manifest_sha256"),
                ("build", "build"),
            )
        ):
            raise ValueError
        slots = tuple(
            ExperimentRequestSlot(**{**slot, "amount_usd": Decimal(slot["amount_usd"])})
            for slot in value["slots"]
        )
        if len(slots) != 14 or len({slot.request_id for slot in slots}) != 14:
            raise ValueError
        expected = {}
        for case in value["cases"]:
            if set(case) != {"case_id", "revisions"} or case["case_id"] in expected:
                raise ValueError
            revisions = case["revisions"]
            if revisions not in ([1, 2, 3], [1, 2]) or any(type(v) is not int for v in revisions):
                raise ValueError
            expected[case["case_id"]] = revisions
            CaseState(case_id=case["case_id"])
        if len(expected) != 3 or sorted(map(len, expected.values())) != [2, 2, 3]:
            raise ValueError
        contexts = {}
        for slot in slots:
            context = ReasoningContext(
                run_id=slot.run_id,
                case_id=slot.case_id,
                case_revision=slot.case_revision,
                attempt_index=slot.attempt,
            )
            if (
                slot.case_id not in expected
                or slot.case_revision not in expected[slot.case_id]
                or slot.attempt not in (1, 2)
                or slot.request_id != request_id_for(context)
                or slot.model != "gpt-4o-mini"
                or slot.phase != "development"
                or type(slot.input_token_reserve) is not int
                or slot.input_token_reserve != 32768
                or type(slot.max_output_tokens) is not int
                or slot.max_output_tokens != 1024
                or slot.amount_usd != get_price(slot.model).cost(32768, 1024)
            ):
                raise ValueError
            pair = (slot.case_id, slot.case_revision)
            current = contexts.setdefault(pair, (slot.run_id, set()))
            if current[0] != slot.run_id or slot.attempt in current[1]:
                raise ValueError
            current[1].add(slot.attempt)
        if len(contexts) != 7 or any(attempts != {1, 2} for _, attempts in contexts.values()):
            raise ValueError
        return deepcopy(value), _sha(raw), slots
    except Exception:
        raise ValueError(_ERROR) from None


def _public(config):
    return config.model_dump(mode="json", exclude={"api_key"})


class _DispatchGuardTransport(httpx.BaseTransport):
    """Last check after reservation and immediately before a possible socket send."""

    def __init__(self, run, underlying):
        self.run, self.underlying = run, underlying

    def handle_request(self, request):
        record = self.run.transport.current
        if record is not None:
            record["http_send_started"] = False
        try:
            self.run.owner.guard(pending_request_id=record["request_id"])
            if any(
                _public(config) != self.run.owner.binding["observed_metis"]
                for config in (
                    self.run.gateway.config,
                    self.run.gateway.reasoner.config,
                    self.run.transport.config,
                )
            ):
                raise ValueError
        except Exception:
            raise ReasoningStopped("ProviderRequestFailed") from None
        record["http_send_started"] = True
        return self.underlying.handle_request(request)

    def close(self):
        self.underlying.close()


class _Run:
    def __init__(self, owner, case, underlying):
        self.owner, self.case = owner, case.model_copy(deep=True)
        self.transport = _ObservedTransport(
            _DispatchGuardTransport(self, underlying), owner.ledger, owner.config
        )
        self.gateway = MetisGroundedPlanner(owner.config, owner.ledger, transport=self.transport)
        self.latest, self.closed, self.reasoner = None, False, None
        self.lock = RLock()

    def supplied_request(self):
        return self.latest.model_copy(deep=True) if self.latest is not None else None

    def plan(self, request, *, context):
        with self.lock:
            if self.closed:
                raise ReasoningStopped("LiveCallsDisabled")
            try:
                self.owner.guard()
                registered = self.owner.slots.get(request_id_for(context))
                if (
                    registered is None
                    or context.run_id != registered.run_id
                    or context.case_id != self.case.case_id
                    or context.case_revision != self.case.case_revision
                    or request.case != self.case
                    or self.reasoner.source_gap_handoff is not True
                    or self.reasoner.source_gap_investigation is not True
                    or self.reasoner.ask_source_background is not False
                    or self.reasoner.concise_user_draft is not False
                    or self.reasoner.review_brief is not False
                    or any(
                        _public(config) != self.owner.binding["observed_metis"]
                        for config in (
                            self.gateway.config,
                            self.gateway.reasoner.config,
                            self.transport.config,
                        )
                    )
                ):
                    raise ValueError
                self.owner.assert_no_secrets(request.model_dump(mode="json"))
                self.owner.assert_no_secrets(context.model_dump(mode="json"))
            except Exception:
                raise ReasoningStopped("ProviderRequestFailed") from None
            self.latest = request.model_copy(deep=True)
            record = {
                "request_id": registered.request_id,
                "context": context.model_dump(mode="json"),
                "grounded_request": request.model_dump(mode="json"),
                "prompt_sha256": _digest(
                    configured_grounded_messages(self.owner.config, request, context)
                ),
                "binding_sha256": self.owner.binding["binding_sha256"],
                "requested_model": self.owner.config.model,
                "verified_returned_model": None,
                "http_send_started": False,
                "http_status": None,
                "canonical_plan": None,
                "wire_observation": None,
                "ledger": None,
                "error_code": None,
            }
            self.transport.current = record
            try:
                output = self.gateway.plan(request, context=context)
                self.owner.assert_no_secrets(output)
                record["canonical_plan"] = output
                return output
            except ReasoningStopped as error:
                record["error_code"] = error.code
                raise
            finally:
                self.transport.current = None
                record["wire_observation"] = self.gateway.latest_wire_observation(context)
                row = self.owner.ledger.get(registered.request_id)
                if row is not None:
                    record["ledger"] = {
                        key: str(value) if isinstance(value, Decimal) else value
                        for key, value in asdict(row).items()
                    }
                self.owner.record(record)

    def close(self):
        with self.lock:
            if not self.closed:
                self.closed = True
                self.gateway.close()
                self.owner._active.discard(self)


class PresentationRuntime:
    """Caller-owned finite live ports with explicit phase/scope/build binding."""

    def __init__(self, protocol_path, values: Mapping[str, str], *, transport_factory=None):
        self.protocol_path = Path(protocol_path).resolve()
        self.protocol, self.protocol_sha256, slots = read_protocol(self.protocol_path)
        self.ledger = BudgetLedger(self.protocol["ledger_path"])
        self.slots = {slot.request_id: slot for slot in slots}
        self._run_ids = {(s.case_id, s.case_revision): s.run_id for s in slots}
        self._active, self._observations = set(), []
        self._closed, self._lock = False, RLock()
        self._transport_factory = transport_factory or (lambda: httpx.HTTPTransport(retries=0))
        self._public = {
            **delivery_recipe(profile_id=PREFILTER_DELIVERY_PROFILE_ID)["metis"],
            "continuation_id": self.protocol["scope_id"],
            "phase": "development",
        }
        self._public["max_request_usd"] = Decimal(self._public["max_request_usd"])
        self.guard(check_config=False)
        self.index_path = Path(self.protocol["index"]["path"]).resolve()
        self._client = _verified_index(
            self.index_path,
            self.protocol["index"]["snapshot_id"],
            self.protocol["index"]["index_manifest_sha256"],
        )
        self._gaps = load_user_gap_vocabulary(str(ROOT / VOCABULARY_PATH))
        self._gap_digest = _digest([gap.model_dump(mode="json") for gap in self._gaps])
        # Public protocol/index/scope checks above precede the first secret lookup.
        token = values.get("AGENT_REVIEWER_TOKEN", "")
        if (
            type(token) is not str
            or not 32 <= len(token) <= 512
            or re.fullmatch(r"[A-Za-z0-9._~+/-]+={0,}", token) is None
        ):
            raise ValueError(_ERROR)
        self._reviewer_token = SecretStr(token)
        self.config = MetisConfig(api_key=values.get("METIS_API_KEY", ""), **self._public)
        self._secrets = (self._reviewer_token, self.config.api_key)
        self.binding = {
            "schema_version": 1,
            "profile_id": PROFILE_ID,
            "base_recipe_sha256": self.protocol["recipe_sha256"],
            "protocol_sha256": self.protocol_sha256,
            "phase_label": self.protocol["phase_label"],
            "scope_id": self.protocol["scope_id"],
            "observed_metis": _public(self.config),
            "index": deepcopy(self.protocol["index"]),
            "source_sha256": deepcopy(self.protocol["source_sha256"]),
            "retrieval_profile": RETRIEVAL_PROFILE,
            "quality_claim": False,
            "scope": "presentation_constructor_and_each_attempt_checks",
        }
        self.binding["binding_sha256"] = _digest(self.binding)
        self._binding_digest = _digest(self.binding)
        self.receipt_dir = Path(self.protocol["receipt_dir"])
        self.receipt_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.receipt_dir.chmod(0o700)
        self.guard()

    def guard(self, *, check_config=True, pending_request_id=None):
        try:
            if self._closed:
                raise ValueError
            current, digest, _ = read_protocol(self.protocol_path)
            if digest != self.protocol_sha256 or current != self.protocol:
                raise ValueError
            status = self.ledger.quarantine_scope_status(self.protocol["scope_id"])
            permitted_pending = False
            if pending_request_id is not None:
                slot = self.slots.get(pending_request_id)
                reservation = self.ledger.get(pending_request_id)
                permitted_pending = (
                    slot is not None
                    and reservation is not None
                    and reservation.status == "reserved"
                    and reservation.run_id == slot.run_id
                    and reservation.case_id == slot.case_id
                    and reservation.case_revision == slot.case_revision
                    and reservation.attempt == slot.attempt
                    and reservation.model == slot.model
                    and reservation.phase == slot.phase
                    and reservation.amount_usd == slot.amount_usd
                    and status.block_reason == "PendingRequest"
                    and status.terminal_status is None
                )
            if (
                not (status.active or permitted_pending)
                or status.protocol_sha256 != digest
                or status.allowed_model != "gpt-4o-mini"
                or status.additional_cap_usd != Decimal("0.10")
                or status.max_requests != len(self.slots)
                or status.remaining_usd < get_price("gpt-4o-mini").cost(32768, 1024)
            ):
                raise ValueError
            if check_config and (
                _digest(self.binding) != self._binding_digest
                or _public(self.config) != self.binding["observed_metis"]
                or self.config.continuation_id != self.protocol["scope_id"]
                or _digest([gap.model_dump(mode="json") for gap in self._gaps]) != self._gap_digest
            ):
                raise ValueError
            if hasattr(self, "_client"):
                self._client.verify()
        except Exception:
            raise ValueError("PresentationScopeUnavailable") from None

    def run_id_for(self, case_id, revision):
        try:
            if type(revision) is not int:
                raise ValueError
            return self._run_ids[(case_id, revision)]
        except Exception:
            raise ValueError("PresentationSlotUnavailable") from None

    def for_case(self, case, _scenario="ask"):
        with self._lock:
            self.guard()
            self.run_id_for(case.case_id, case.case_revision)
            underlying = self._transport_factory()
            if not isinstance(underlying, httpx.BaseTransport):
                raise ValueError(_ERROR)
            run = _Run(self, case, underlying)
            self._active.add(run)
            reasoner = GroundedReasoner(
                run,
                source_gap_handoff=True,
                source_gap_investigation=True,
                request_factory=lambda state, message, evidence: caller_catalog(
                    state, message, evidence, definitions=self._gaps
                ),
            )
            run.reasoner = reasoner
            native = StreamlitRetriever(
                "", snapshot_id=self.protocol["index"]["snapshot_id"], client=self._client
            )
            retriever = _BoundedRetriever(
                ChromaRetrieverAdapter(
                    "",
                    snapshot_id=self.protocol["index"]["snapshot_id"],
                    core_retriever=native,
                    selection_policy="query_relevance_v1",
                ),
                25,
            )
            return api.RunAdapters(
                retriever,
                reasoner,
                snapshot_id=self.protocol["index"]["snapshot_id"],
                grounded_request_supplier=run.supplied_request,
                cleanup=run.close,
                retrieval_profile=RETRIEVAL_PROFILE,
            )

    def record(self, record):
        with self._lock:
            # These private local receipts deliberately retain the complete current
            # input/evidence and canonical output, but never credentials/headers.
            raw = json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2).encode()
            self.assert_no_secrets(record)
            destination = self.receipt_dir / (record["request_id"].replace(":", "-") + ".json")
            if destination.exists():
                if destination.read_bytes() != raw:
                    raise ValueError("PresentationReceiptConflict")
            else:
                with destination.open("xb") as stream:
                    os.fchmod(stream.fileno(), 0o600)
                    stream.write(raw)
            self._observations.append(deepcopy(record))

    @property
    def observations(self):
        return deepcopy(self._observations)

    def assert_no_secrets(self, value):
        pending = [value]
        while pending:
            observed = pending.pop()
            if isinstance(observed, str):
                if any(secret.get_secret_value() in observed for secret in self._secrets):
                    raise ReasoningStopped("ProviderResponseInvalid")
                # Canonical plans are JSON strings: also inspect decoded fields so
                # escaping a quote/backslash cannot conceal a credential echo.
                if observed.startswith(("{", "[")):
                    try:
                        decoded = json.loads(observed)
                    except (ValueError, RecursionError):
                        continue
                    if isinstance(decoded, (dict, list)):
                        pending.append(decoded)
            elif isinstance(observed, dict):
                pending.extend(observed.keys())
                pending.extend(observed.values())
            elif isinstance(observed, (tuple, list)):
                pending.extend(observed)

    def close(self):
        with self._lock:
            self._closed = True
            for run in tuple(self._active):
                run.close()


def configured_app(protocol_path, values: Mapping[str, str], *, transport_factory=None) -> FastAPI:
    """Compose only the finite authorized path; no implicit .env or credentials."""
    runtime = PresentationRuntime(protocol_path, values, transport_factory=transport_factory)
    try:
        token = runtime._reviewer_token.get_secret_value()
        reviewer = values.get("AGENT_REVIEWER_ID", "presentation-maintainer")
        if (
            type(token) is not str
            or not 32 <= len(token) <= 512
            or re.fullmatch(r"[A-Za-z0-9._~+/-]+={0,}", token) is None
        ):
            raise ValueError(_ERROR)
        TypeAdapter(Identifier).validate_python(reviewer)
        tracker = SQLiteCaseTracker(
            runtime.protocol["tracker_path"], reviewer_tokens={reviewer: token}
        )
        app = create_app(
            tracker,
            reviewer_tokens={reviewer: token},
            case_adapters=runtime.for_case,
            run_id_resolver=runtime.run_id_for,
            require_message_auth=True,
            evidence_scope="exact_user_version",
            retrieval_label="local_chroma_hash",
            reasoning_label="metis_grounded_live",
        )
        app.state.presentation_runtime = runtime
        app.state.presentation_binding = deepcopy(runtime.binding)

        @asynccontextmanager
        async def lifespan(_app):
            try:
                yield
            finally:
                runtime.close()

        app.router.lifespan_context = lifespan
        return app
    except Exception:
        runtime.close()
        raise ValueError(_ERROR) from None
