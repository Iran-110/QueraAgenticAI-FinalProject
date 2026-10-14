"""A durable budget ledger for one shared runner and one SQLite database.

Reservations survive process failure. An ambiguous HTTP outcome remains charged
against the limit until its observed cost is reconciled; there is no expiry or
automatic refund. This ledger does not coordinate independent database copies.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import asdict, dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, InvalidOperation, localcontext
from pathlib import Path
from typing import Literal

from agent_app.llm.pricing import get_price

__all__ = [
    "BudgetDenied",
    "BudgetLedger",
    "BudgetSnapshot",
    "ContinuationStatus",
    "ExperimentRequestSlot",
    "ExperimentScopeStatus",
    "LedgerConflict",
    "LedgerUnavailable",
    "QuarantineObservation",
    "QuarantineScopeStatus",
    "Reservation",
]

_NANO = Decimal("0.000000001")
_SCALE = Decimal("1000000000")
_MAX_INTEGER = 2**63 - 1
_MAX_MONEY = Decimal("9223372036.854775807")
_MAX_LIMIT = Decimal("5")
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}\Z")
_PHASE = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
_REQUEST_COLUMNS = (
    "request_id, run_id, case_id, case_revision, attempt, model, phase, "
    "amount_nanos, status, cost_nanos, cost_decimal, input_tokens, output_tokens, error_code"
)
_QUARANTINE_TERMINAL_TRIGGER_SQL = """CREATE TRIGGER quarantine_scope_terminal_immutable
    BEFORE UPDATE OF terminal_status,terminal_reason,terminal_fingerprint ON quarantine_scopes
    WHEN OLD.terminal_status IS NOT NULL
    BEGIN SELECT RAISE(ABORT,'Immutable quarantine terminal state'); END"""
_QUARANTINE_DELETE_TRIGGER_SQL = """CREATE TRIGGER quarantine_scope_registration_undeletable
    BEFORE DELETE ON quarantine_scopes
    BEGIN SELECT RAISE(ABORT,'Immutable quarantine registration'); END"""


class BudgetDenied(Exception):
    def __init__(self) -> None:
        super().__init__("Budget reservation denied.")


class LedgerConflict(Exception):
    def __init__(self) -> None:
        super().__init__("Budget ledger request conflict.")


class LedgerUnavailable(Exception):
    def __init__(self) -> None:
        super().__init__("Budget ledger unavailable.")


@dataclass(frozen=True, slots=True)
class Reservation:
    request_id: str
    run_id: str
    case_id: str
    case_revision: int
    attempt: int
    model: str
    phase: str
    amount_usd: Decimal
    status: Literal["reserved", "settled", "uncertain", "released"]
    cost_usd: Decimal | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class BudgetSnapshot:
    limit_usd: Decimal
    opening_spend_usd: Decimal
    settled_usd: Decimal
    reserved_usd: Decimal
    uncertain_usd: Decimal
    available_usd: Decimal
    halted: bool


@dataclass(frozen=True, slots=True)
class ContinuationStatus:
    """Usable scope of an explicit user-authorized exception to a global halt."""

    authorization_id: str
    authorization_ref: str
    expected_request_id: str
    allowed_model: str
    additional_cap_usd: Decimal
    held_usd: Decimal
    used_usd: Decimal
    remaining_usd: Decimal
    active: bool
    block_reason: str | None


@dataclass(frozen=True, slots=True)
class ExperimentRequestSlot:
    """Caller-owned identity and limits frozen before one paid experiment."""

    request_id: str
    run_id: str
    case_id: str
    case_revision: int
    attempt: int
    model: str = "gpt-4o-mini"
    phase: str = "development"
    input_token_reserve: int = 16384
    max_output_tokens: int = 1024
    amount_usd: Decimal = Decimal("0.003379200")


@dataclass(frozen=True, slots=True)
class ExperimentScopeStatus(ContinuationStatus):
    parent_authorization_id: str
    protocol_sha256: str
    max_requests: int
    consumed_requests: int


@dataclass(frozen=True, slots=True)
class QuarantineObservation:
    """Read-only binding to all unresolved holds and historical authorizations."""

    unknown_ids: tuple[str, ...]
    unknown_fingerprints: tuple[tuple[str, str], ...]
    meta_sha256: str
    authorization_history_sha256: str
    held_usd: Decimal


@dataclass(frozen=True, slots=True)
class QuarantineScopeStatus:
    """A new finite exception, never a revived singleton or reconciliation."""

    authorization_id: str
    authorization_ref: str
    unknown_ids: tuple[str, ...]
    allowed_model: str
    additional_cap_usd: Decimal
    held_usd: Decimal
    used_usd: Decimal
    remaining_usd: Decimal
    active: bool
    block_reason: str | None
    protocol_sha256: str
    max_requests: int
    consumed_requests: int
    terminal_status: Literal["closed", "revoked"] | None


def _identifier(value: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError("Invalid ledger identifier.")
    return value


def _counter(value: int, *, minimum: int = 0, maximum: int = _MAX_INTEGER) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("Invalid ledger counter.")
    return value


def _money(value: Decimal, *, ceiling: bool = True) -> int:
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise ValueError("Invalid ledger money.")
    if value > _MAX_MONEY:
        raise ValueError("Invalid ledger money.")
    with localcontext() as context:
        context.prec = 32
        rounded = value.quantize(_NANO, rounding=ROUND_CEILING if ceiling else ROUND_FLOOR)
        return int(rounded * _SCALE)


def _usd(nanos: int) -> Decimal:
    with localcontext() as context:
        context.prec = max(32, len(str(nanos)) + 9)
        return Decimal(nanos) / _SCALE


def _path(path: str | os.PathLike[str]) -> Path:
    try:
        return Path(path).resolve()
    except (OSError, TypeError, ValueError):
        raise LedgerUnavailable() from None


def _connect(path: Path) -> sqlite3.Connection:
    try:
        connection = sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection
    except (OSError, ValueError, sqlite3.Error):
        raise LedgerUnavailable() from None


@contextmanager
def _transaction(path: Path, *, write: bool = False) -> Iterator[sqlite3.Connection]:
    connection = _connect(path)
    try:
        connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        yield connection
        connection.commit()
    except sqlite3.Error:
        with suppress(sqlite3.Error):
            connection.rollback()
        raise LedgerUnavailable() from None
    except Exception:
        with suppress(sqlite3.Error):
            connection.rollback()
        raise
    finally:
        with suppress(sqlite3.Error):
            connection.close()


def _configuration(connection: sqlite3.Connection) -> tuple[int, int, bool]:
    rows = connection.execute(
        "SELECT singleton, schema_version, limit_nanos, opening_nanos, halted FROM ledger_meta"
    ).fetchall()
    if len(rows) != 1:
        raise LedgerUnavailable()
    row = rows[0]
    if (
        row["singleton"] != 1
        or row["schema_version"] != 1
        or type(row["limit_nanos"]) is not int
        or type(row["opening_nanos"]) is not int
        or not 0 <= row["opening_nanos"] <= row["limit_nanos"] <= 5_000_000_000
        or row["halted"] not in (0, 1)
    ):
        raise LedgerUnavailable()
    return row["limit_nanos"], row["opening_nanos"], bool(row["halted"])


def _reservation(row: sqlite3.Row) -> Reservation:
    _validate_row(row)
    return Reservation(
        request_id=row["request_id"],
        run_id=row["run_id"],
        case_id=row["case_id"],
        case_revision=row["case_revision"],
        attempt=row["attempt"],
        model=row["model"],
        phase=row["phase"],
        amount_usd=_usd(row["amount_nanos"]),
        status=row["status"],
        cost_usd=_usd(row["cost_nanos"]) if row["cost_nanos"] is not None else None,
        input_tokens=row["input_tokens"],
        output_tokens=row["output_tokens"],
        error_code=row["error_code"],
    )


def _validate_row(row: sqlite3.Row) -> None:
    try:
        for field in ("request_id", "run_id", "case_id", "model"):
            _identifier(row[field])
        _counter(row["case_revision"])
        _counter(row["attempt"], minimum=1, maximum=2)
        _counter(row["amount_nanos"])
        if not isinstance(row["phase"], str) or _PHASE.fullmatch(row["phase"]) is None:
            raise ValueError
        if row["status"] not in ("reserved", "settled", "uncertain", "released"):
            raise ValueError
        if row["status"] == "settled":
            _counter(row["cost_nanos"])
            _counter(row["input_tokens"])
            _counter(row["output_tokens"])
            if _money(Decimal(row["cost_decimal"])) != row["cost_nanos"]:
                raise ValueError
            if row["error_code"] is not None:
                raise ValueError
        else:
            for field in ("cost_nanos", "cost_decimal", "input_tokens", "output_tokens"):
                if row[field] is not None:
                    raise ValueError
            if row["status"] == "reserved":
                if row["error_code"] is not None:
                    raise ValueError
            else:
                _identifier(row["error_code"])
    except (IndexError, KeyError, InvalidOperation, TypeError, ValueError):
        raise LedgerUnavailable() from None


def _find(connection: sqlite3.Connection, request_id: str) -> sqlite3.Row | None:
    row = connection.execute(
        f"SELECT {_REQUEST_COLUMNS} FROM reservations WHERE request_id = ?", (request_id,)
    ).fetchone()
    if row is not None:
        _validate_row(row)
    return row


def _required(connection: sqlite3.Connection, request_id: str) -> sqlite3.Row:
    row = _find(connection, request_id)
    if row is None:
        raise LedgerConflict()
    return row


def _audit(
    connection: sqlite3.Connection, request_id: str, status: str, error_code: str | None = None
) -> None:
    connection.execute(
        "INSERT INTO ledger_events (request_id, status, error_code) VALUES (?, ?, ?)",
        (request_id, status, error_code),
    )


def _totals(connection: sqlite3.Connection) -> tuple[int, int, int]:
    settled = reserved = uncertain = 0
    # Sum in Python: multiple overrun settlements must not overflow SQLite SUM.
    for row in connection.execute(f"SELECT {_REQUEST_COLUMNS} FROM reservations"):
        _validate_row(row)
        if row["status"] == "settled":
            settled += row["cost_nanos"]
        elif row["status"] == "reserved":
            reserved += row["amount_nanos"]
        elif row["status"] == "uncertain":
            uncertain += row["amount_nanos"]
    return settled, reserved, uncertain


def _continuations_exist(connection: sqlite3.Connection) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'ledger_continuations'"
        ).fetchone()
        is not None
    )


def _continuation_schema(connection: sqlite3.Connection) -> None:
    """Add controls only during explicit authorization, never reset existing data."""
    connection.execute(
        """CREATE TABLE IF NOT EXISTS ledger_continuations (
        authorization_id TEXT PRIMARY KEY,
        authorization_ref TEXT NOT NULL,
        expected_request_id TEXT NOT NULL UNIQUE REFERENCES reservations(request_id),
        allowed_model TEXT NOT NULL CHECK (allowed_model = 'gpt-4o-mini'),
        cap_nanos INTEGER NOT NULL CHECK (cap_nanos > 0),
        held_nanos INTEGER NOT NULL CHECK (held_nanos >= 20000000),
        prior_held_nanos INTEGER NOT NULL CHECK (prior_held_nanos >= 0),
        quarantine_fingerprint TEXT NOT NULL,
        active INTEGER NOT NULL CHECK (active IN (0, 1)),
        revocation_code TEXT,
        recorded_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        )"""
    )
    connection.execute(
        """CREATE TABLE IF NOT EXISTS continuation_requests (
        request_id TEXT PRIMARY KEY REFERENCES reservations(request_id),
        authorization_id TEXT NOT NULL REFERENCES ledger_continuations(authorization_id)
        )"""
    )
    connection.execute(
        """CREATE TABLE IF NOT EXISTS continuation_events (
        event_id INTEGER PRIMARY KEY,
        authorization_id TEXT NOT NULL REFERENCES ledger_continuations(authorization_id),
        status TEXT NOT NULL,
        reason_code TEXT NOT NULL,
        recorded_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        )"""
    )


def _quarantine_fingerprint(row: sqlite3.Row) -> str:
    return hashlib.sha256(
        json.dumps(dict(row), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _find_continuation(connection: sqlite3.Connection, authorization_id: str) -> sqlite3.Row:
    if not _continuations_exist(connection):
        raise LedgerConflict()
    row = connection.execute(
        "SELECT * FROM ledger_continuations WHERE authorization_id = ?", (authorization_id,)
    ).fetchone()
    if row is None:
        raise LedgerConflict()
    try:
        for key in (
            "authorization_id",
            "authorization_ref",
            "expected_request_id",
            "allowed_model",
        ):
            _identifier(row[key])
        _counter(row["cap_nanos"], minimum=1, maximum=5_000_000_000)
        _counter(row["held_nanos"], minimum=20_000_000)
        _counter(row["prior_held_nanos"])
        if (
            row["allowed_model"] != "gpt-4o-mini"
            or row["held_nanos"] < row["prior_held_nanos"]
            or not isinstance(row["quarantine_fingerprint"], str)
            or re.fullmatch(r"[a-f0-9]{64}", row["quarantine_fingerprint"]) is None
            or row["active"] not in (0, 1)
        ):
            raise ValueError
        if row["active"]:
            if row["revocation_code"] is not None:
                raise ValueError
        else:
            _identifier(row["revocation_code"])
    except (IndexError, KeyError, TypeError, ValueError):
        raise LedgerUnavailable() from None
    return row


def _observed_overrun(connection: sqlite3.Connection) -> bool:
    for row in connection.execute(f"SELECT {_REQUEST_COLUMNS} FROM reservations"):
        _validate_row(row)
        if row["status"] == "settled" and row["cost_nanos"] > row["amount_nanos"]:
            return True
    return False


def _continuation_usage(connection: sqlite3.Connection, authorization_id: str) -> int:
    used = 0
    rows = connection.execute(
        f"""SELECT {_REQUEST_COLUMNS} FROM reservations WHERE request_id IN
        (SELECT request_id FROM continuation_requests WHERE authorization_id = ?)""",
        (authorization_id,),
    ).fetchall()
    count = connection.execute(
        "SELECT COUNT(*) FROM continuation_requests WHERE authorization_id = ?", (authorization_id,)
    ).fetchone()[0]
    if len(rows) != count:
        raise LedgerUnavailable()
    for row in rows:
        _validate_row(row)
        if row["model"] != "gpt-4o-mini" or row["phase"] != "development":
            raise LedgerUnavailable()
        if row["status"] == "settled":
            used += row["cost_nanos"]
        elif row["status"] in ("reserved", "uncertain"):
            used += row["amount_nanos"]
    return used


def _continuation_status(
    connection: sqlite3.Connection, authorization_id: str
) -> ContinuationStatus:
    row = _find_continuation(connection, authorization_id)
    _, _, halted = _configuration(connection)
    _totals(connection)
    pending = (
        connection.execute(
            "SELECT 1 FROM reservations WHERE status = 'reserved' LIMIT 1"
        ).fetchone()
        is not None
    )
    quarantined = _required(connection, row["expected_request_id"])
    unknown_ids = [
        item[0]
        for item in connection.execute(
            "SELECT request_id FROM reservations WHERE status = 'uncertain'"
        )
    ]
    used = _continuation_usage(connection, authorization_id)
    remaining = max(0, row["cap_nanos"] - used)
    block_reason = None
    if not row["active"]:
        block_reason = row["revocation_code"]
    elif not halted:
        block_reason = "GlobalHaltChanged"
    elif _quarantine_fingerprint(quarantined) != row["quarantine_fingerprint"]:
        block_reason = "QuarantineChanged"
    elif unknown_ids != [row["expected_request_id"]]:
        block_reason = "UncertaintyChanged"
    elif _observed_overrun(connection):
        block_reason = "CostOverrun"
    elif pending:
        block_reason = "PendingRequest"
    elif remaining == 0:
        block_reason = "ContinuationCapExceeded"
    return ContinuationStatus(
        authorization_id=row["authorization_id"],
        authorization_ref=row["authorization_ref"],
        expected_request_id=row["expected_request_id"],
        allowed_model=row["allowed_model"],
        additional_cap_usd=_usd(row["cap_nanos"]),
        held_usd=_usd(row["held_nanos"]),
        used_usd=_usd(used),
        remaining_usd=_usd(remaining),
        active=block_reason is None,
        block_reason=block_reason,
    )


def _experiment_scopes_exist(connection: sqlite3.Connection) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='experiment_scopes'"
        ).fetchone()
        is not None
    )


def _experiment_scope_schema(connection: sqlite3.Connection) -> None:
    """Add a separate experiment allowance; historical grants remain immutable."""
    connection.execute("""CREATE TABLE IF NOT EXISTS experiment_scopes (
        authorization_id TEXT PRIMARY KEY,
        authorization_ref TEXT NOT NULL,
        parent_authorization_id TEXT NOT NULL REFERENCES ledger_continuations(authorization_id),
        expected_request_id TEXT NOT NULL REFERENCES reservations(request_id),
        protocol_sha256 TEXT NOT NULL UNIQUE,
        cap_nanos INTEGER NOT NULL CHECK(cap_nanos BETWEEN 1 AND 100000000),
        held_nanos INTEGER NOT NULL CHECK(held_nanos >= 20000000),
        parent_fingerprint TEXT NOT NULL,
        quarantine_fingerprint TEXT NOT NULL,
        max_requests INTEGER NOT NULL CHECK(max_requests BETWEEN 1 AND 24),
        slots_fingerprint TEXT NOT NULL,
        registration_fingerprint TEXT NOT NULL,
        recorded_at TEXT NOT NULL DEFAULT(strftime('%Y-%m-%dT%H:%M:%fZ','now'))
    )""")
    connection.execute("""CREATE TABLE IF NOT EXISTS experiment_scope_slots (
        request_id TEXT PRIMARY KEY,
        authorization_id TEXT NOT NULL REFERENCES experiment_scopes(authorization_id),
        slot_index INTEGER NOT NULL,
        run_id TEXT NOT NULL,
        case_id TEXT NOT NULL,
        case_revision INTEGER NOT NULL,
        attempt INTEGER NOT NULL,
        model TEXT NOT NULL,
        phase TEXT NOT NULL,
        input_token_reserve INTEGER NOT NULL,
        max_output_tokens INTEGER NOT NULL,
        amount_nanos INTEGER NOT NULL,
        UNIQUE(authorization_id, slot_index),
        UNIQUE(run_id, case_id, case_revision, attempt)
    )""")
    connection.execute("""CREATE TABLE IF NOT EXISTS experiment_scope_requests (
        request_id TEXT PRIMARY KEY REFERENCES reservations(request_id),
        authorization_id TEXT NOT NULL REFERENCES experiment_scopes(authorization_id)
    )""")
    connection.execute("""CREATE TABLE IF NOT EXISTS experiment_scope_events (
        event_id INTEGER PRIMARY KEY,
        authorization_id TEXT NOT NULL REFERENCES experiment_scopes(authorization_id),
        status TEXT NOT NULL CHECK(status IN ('authorized','revoked','closed')),
        reason_code TEXT NOT NULL,
        recorded_at TEXT NOT NULL DEFAULT(strftime('%Y-%m-%dT%H:%M:%fZ','now'))
    )""")


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _experiment_slots_fingerprint(slots: tuple[ExperimentRequestSlot, ...]) -> str:
    # Money identity uses exact nanoUSD, independent of Decimal trailing zeros.
    return _digest([{**asdict(slot), "amount_usd": _money(slot.amount_usd)} for slot in slots])


def _validated_experiment_slots(
    slots: tuple[ExperimentRequestSlot, ...],
) -> tuple[ExperimentRequestSlot, ...]:
    return _validated_request_slots(slots, outputs=(1024,), exact_request_id=False)


def _validated_request_slots(
    slots: tuple[ExperimentRequestSlot, ...], *, outputs: tuple[int, ...], exact_request_id: bool
) -> tuple[ExperimentRequestSlot, ...]:
    if type(slots) is not tuple or not 1 <= len(slots) <= 24:
        raise ValueError("Invalid experiment request slots.")
    identities = set()
    request_ids = set()
    price = get_price("gpt-4o-mini")
    for slot in slots:
        if type(slot) is not ExperimentRequestSlot:
            raise ValueError("Invalid experiment request slot.")
        for value in (slot.request_id, slot.run_id, slot.case_id):
            _identifier(value)
        _counter(slot.case_revision)
        _counter(slot.attempt, minimum=1, maximum=2)
        bound = (
            price.cost(slot.input_token_reserve, slot.max_output_tokens)
            if price is not None
            and type(slot.input_token_reserve) is int
            and slot.input_token_reserve in (16384, 24576)
            and type(slot.max_output_tokens) is int
            and slot.max_output_tokens in outputs
            else None
        )
        if (
            slot.model != "gpt-4o-mini"
            or slot.phase != "development"
            or type(slot.input_token_reserve) is not int
            or slot.input_token_reserve not in (16384, 24576)
            or type(slot.max_output_tokens) is not int
            or slot.max_output_tokens not in outputs
            or not isinstance(slot.amount_usd, Decimal)
            or not slot.amount_usd.is_finite()
            or slot.amount_usd != bound
        ):
            raise ValueError("Invalid experiment request bounds.")
        if exact_request_id:
            # Import contracts only; importing the gateway would be circular.
            from agent_app.contracts import ReasoningContext

            context = ReasoningContext(
                run_id=slot.run_id,
                case_id=slot.case_id,
                case_revision=slot.case_revision,
                attempt_index=slot.attempt,
            )
            identity_json = context.model_dump_json(
                include={"run_id", "case_id", "case_revision", "attempt_index"}
            )
            if slot.request_id != "call:" + hashlib.sha256(identity_json.encode()).hexdigest():
                raise ValueError("Invalid caller request identity.")
        identity = (slot.run_id, slot.case_id, slot.case_revision, slot.attempt)
        if identity in identities or slot.request_id in request_ids:
            raise ValueError("Duplicate experiment request slot.")
        identities.add(identity)
        request_ids.add(slot.request_id)
    return slots


def _experiment_slot(row: sqlite3.Row) -> ExperimentRequestSlot:
    _counter(row["amount_nanos"], minimum=1)
    return ExperimentRequestSlot(
        request_id=row["request_id"],
        run_id=row["run_id"],
        case_id=row["case_id"],
        case_revision=row["case_revision"],
        attempt=row["attempt"],
        model=row["model"],
        phase=row["phase"],
        input_token_reserve=row["input_token_reserve"],
        max_output_tokens=row["max_output_tokens"],
        amount_usd=_usd(row["amount_nanos"]),
    )


def _find_experiment_scope(connection: sqlite3.Connection, authorization_id: str) -> sqlite3.Row:
    if not _experiment_scopes_exist(connection):
        raise LedgerConflict()
    row = connection.execute(
        "SELECT * FROM experiment_scopes WHERE authorization_id=?", (authorization_id,)
    ).fetchone()
    if row is None:
        raise LedgerConflict()
    try:
        for key in (
            "authorization_id",
            "authorization_ref",
            "parent_authorization_id",
            "expected_request_id",
        ):
            _identifier(row[key])
        for key in (
            "protocol_sha256",
            "parent_fingerprint",
            "quarantine_fingerprint",
            "slots_fingerprint",
            "registration_fingerprint",
        ):
            if not isinstance(row[key], str) or re.fullmatch(r"[a-f0-9]{64}", row[key]) is None:
                raise ValueError
        _counter(row["cap_nanos"], minimum=1, maximum=100_000_000)
        _counter(row["held_nanos"], minimum=20_000_000)
        _counter(row["max_requests"], minimum=1, maximum=24)
        registered = {
            key: row[key]
            for key in row.keys()
            if key not in ("recorded_at", "registration_fingerprint")
        }
        if _digest(registered) != row["registration_fingerprint"]:
            raise ValueError
        slot_rows = connection.execute(
            "SELECT * FROM experiment_scope_slots WHERE authorization_id=? ORDER BY slot_index",
            (authorization_id,),
        ).fetchall()
        if [slot["slot_index"] for slot in slot_rows] != list(range(row["max_requests"])):
            raise ValueError
        slots = _validated_experiment_slots(tuple(_experiment_slot(slot) for slot in slot_rows))
        if _experiment_slots_fingerprint(slots) != row["slots_fingerprint"]:
            raise ValueError
        if sum(_money(slot.amount_usd) for slot in slots) > row["cap_nanos"]:
            raise ValueError
    except (IndexError, KeyError, InvalidOperation, TypeError, ValueError):
        raise LedgerUnavailable() from None
    return row


def _experiment_scope_usage(
    connection: sqlite3.Connection, authorization_id: str
) -> tuple[int, int]:
    return _scope_usage(connection, authorization_id, "experiment")


def _scope_usage(
    connection: sqlite3.Connection, authorization_id: str, kind: str
) -> tuple[int, int]:
    if kind not in ("experiment", "quarantine"):
        raise LedgerUnavailable()
    used = count = 0
    for mapped in connection.execute(
        f"SELECT request_id FROM {kind}_scope_requests WHERE authorization_id=?",
        (authorization_id,),
    ):
        count += 1
        row = _required(connection, mapped["request_id"])
        slot_row = connection.execute(
            f"SELECT * FROM {kind}_scope_slots WHERE authorization_id=? AND request_id=?",
            (authorization_id, row["request_id"]),
        ).fetchone()
        if slot_row is None or any(
            row[key] != slot_row[key]
            for key in (
                "run_id",
                "case_id",
                "case_revision",
                "attempt",
                "model",
                "phase",
                "amount_nanos",
            )
        ):
            raise LedgerUnavailable()
        if row["status"] == "settled":
            used += row["cost_nanos"]
        elif row["status"] in ("reserved", "uncertain"):
            used += row["amount_nanos"]
    return used, count


def _experiment_scope_status(
    connection: sqlite3.Connection, authorization_id: str
) -> ExperimentScopeStatus:
    row = _find_experiment_scope(connection, authorization_id)
    parent = _find_continuation(connection, row["parent_authorization_id"])
    _, _, halted = _configuration(connection)
    _totals(connection)
    quarantine = _required(connection, row["expected_request_id"])
    events = connection.execute(
        "SELECT status, reason_code FROM experiment_scope_events WHERE authorization_id=? ORDER BY event_id",
        (authorization_id,),
    ).fetchall()
    if (
        len(events) not in (1, 2)
        or events[0]["status"] != "authorized"
        or events[0]["reason_code"] != "UserAuthorizedExperimentScope"
    ):
        raise LedgerUnavailable()
    if len(events) == 2:
        if events[1]["status"] not in ("revoked", "closed"):
            raise LedgerUnavailable()
        try:
            _identifier(events[1]["reason_code"])
        except ValueError:
            raise LedgerUnavailable() from None
    used, consumed = _experiment_scope_usage(connection, authorization_id)
    if consumed > row["max_requests"]:
        raise LedgerUnavailable()
    unknown_ids = [
        item[0]
        for item in connection.execute(
            "SELECT request_id FROM reservations WHERE status='uncertain'"
        )
    ]
    pending = (
        connection.execute("SELECT 1 FROM reservations WHERE status='reserved' LIMIT 1").fetchone()
        is not None
    )
    remaining = max(0, row["cap_nanos"] - used)
    reason = None
    if len(events) == 2:
        reason = events[1]["reason_code"]
    elif not halted:
        reason = "GlobalHaltChanged"
    elif _digest(dict(parent)) != row["parent_fingerprint"]:
        reason = "ParentAuthorizationChanged"
    elif _quarantine_fingerprint(quarantine) != row["quarantine_fingerprint"]:
        reason = "QuarantineChanged"
    elif unknown_ids != [row["expected_request_id"]]:
        reason = "UncertaintyChanged"
    elif _observed_overrun(connection):
        reason = "CostOverrun"
    elif pending:
        reason = "PendingRequest"
    elif not remaining:
        reason = "ExperimentCapExceeded"
    elif consumed == row["max_requests"]:
        reason = "ExperimentRequestsExhausted"
    return ExperimentScopeStatus(
        authorization_id=row["authorization_id"],
        authorization_ref=row["authorization_ref"],
        expected_request_id=row["expected_request_id"],
        allowed_model="gpt-4o-mini",
        additional_cap_usd=_usd(row["cap_nanos"]),
        held_usd=_usd(row["held_nanos"]),
        used_usd=_usd(used),
        remaining_usd=_usd(remaining),
        active=reason is None,
        block_reason=reason,
        parent_authorization_id=row["parent_authorization_id"],
        protocol_sha256=row["protocol_sha256"],
        max_requests=row["max_requests"],
        consumed_requests=consumed,
    )


def _quarantine_scopes_exist(connection: sqlite3.Connection) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='quarantine_scopes'"
        ).fetchone()
        is not None
    )


def _quarantine_schema(connection: sqlite3.Connection) -> None:
    """New tables only, created by a fresh explicit authorization transaction."""
    connection.execute("""CREATE TABLE IF NOT EXISTS quarantine_scopes (
        authorization_id TEXT PRIMARY KEY,
        authorization_ref TEXT NOT NULL,
        protocol_sha256 TEXT NOT NULL UNIQUE,
        cap_nanos INTEGER NOT NULL CHECK(cap_nanos BETWEEN 1 AND 100000000),
        held_nanos INTEGER NOT NULL CHECK(held_nanos > 0),
        unknown_binding TEXT NOT NULL,
        meta_sha256 TEXT NOT NULL,
        history_sha256 TEXT NOT NULL,
        max_requests INTEGER NOT NULL CHECK(max_requests BETWEEN 1 AND 24),
        slots_fingerprint TEXT NOT NULL,
        registration_fingerprint TEXT NOT NULL,
        terminal_status TEXT CHECK(terminal_status IN ('closed','revoked')),
        terminal_reason TEXT,
        terminal_fingerprint TEXT,
        recorded_at TEXT NOT NULL DEFAULT(strftime('%Y-%m-%dT%H:%M:%fZ','now')),
        CHECK (
            (terminal_status IS NULL AND terminal_reason IS NULL AND terminal_fingerprint IS NULL)
            OR (terminal_status IS NOT NULL AND terminal_reason IS NOT NULL AND terminal_fingerprint IS NOT NULL)
        )
    )""")
    connection.execute("""CREATE TABLE IF NOT EXISTS quarantine_scope_slots (
        request_id TEXT PRIMARY KEY,
        authorization_id TEXT NOT NULL REFERENCES quarantine_scopes(authorization_id),
        slot_index INTEGER NOT NULL,
        run_id TEXT NOT NULL,
        case_id TEXT NOT NULL,
        case_revision INTEGER NOT NULL,
        attempt INTEGER NOT NULL,
        model TEXT NOT NULL,
        phase TEXT NOT NULL,
        input_token_reserve INTEGER NOT NULL,
        max_output_tokens INTEGER NOT NULL,
        amount_nanos INTEGER NOT NULL,
        UNIQUE(authorization_id,slot_index),
        UNIQUE(run_id,case_id,case_revision,attempt)
    )""")
    connection.execute("""CREATE TABLE IF NOT EXISTS quarantine_scope_requests (
        request_id TEXT PRIMARY KEY REFERENCES reservations(request_id),
        authorization_id TEXT NOT NULL REFERENCES quarantine_scopes(authorization_id)
    )""")
    connection.execute("""CREATE TABLE IF NOT EXISTS quarantine_scope_events (
        event_id INTEGER PRIMARY KEY,
        authorization_id TEXT NOT NULL REFERENCES quarantine_scopes(authorization_id),
        status TEXT NOT NULL CHECK(status IN ('authorized','closed','revoked')),
        reason_code TEXT NOT NULL,
        recorded_at TEXT NOT NULL DEFAULT(strftime('%Y-%m-%dT%H:%M:%fZ','now'))
    )""")
    connection.execute(
        _QUARANTINE_TERMINAL_TRIGGER_SQL.replace(
            "CREATE TRIGGER ", "CREATE TRIGGER IF NOT EXISTS ", 1
        )
    )
    connection.execute(
        _QUARANTINE_DELETE_TRIGGER_SQL.replace(
            "CREATE TRIGGER ", "CREATE TRIGGER IF NOT EXISTS ", 1
        )
    )


def _quarantine_guards(connection: sqlite3.Connection) -> None:
    for name, sql in (
        ("quarantine_scope_terminal_immutable", _QUARANTINE_TERMINAL_TRIGGER_SQL),
        ("quarantine_scope_registration_undeletable", _QUARANTINE_DELETE_TRIGGER_SQL),
    ):
        guard = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='trigger' AND name=? AND tbl_name='quarantine_scopes'",
            (name,),
        ).fetchone()
        if (
            guard is None
            or type(guard["sql"]) is not str
            or " ".join(guard["sql"].split()) != " ".join(sql.split())
        ):
            raise LedgerUnavailable()


def _valid_digest(value: str) -> str:
    if type(value) is not str or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        raise ValueError("Invalid authorization fingerprint.")
    return value


def _unknown_binding(ids: tuple[str, ...], fingerprints: tuple[tuple[str, str], ...]) -> str:
    if (
        type(ids) is not tuple
        or not 1 <= len(ids) <= 24
        or any(type(identity) is not str for identity in ids)
        or ids != tuple(sorted(set(ids)))
        or type(fingerprints) is not tuple
        or len(fingerprints) != len(ids)
    ):
        raise ValueError("Invalid quarantine binding.")
    for identity, pair in zip(ids, fingerprints, strict=True):
        _identifier(identity)
        if type(pair) is not tuple or len(pair) != 2 or pair[0] != identity:
            raise ValueError("Invalid quarantine binding.")
        _valid_digest(pair[1])
    return json.dumps(
        {"ids": ids, "fingerprints": fingerprints}, sort_keys=True, separators=(",", ":")
    )


def _historical_authorizations_digest(connection: sqlite3.Connection) -> str:
    """Legacy authorization history only; new standalone scope rows are separate."""
    names = (
        "ledger_continuations",
        "continuation_requests",
        "continuation_events",
        "experiment_scopes",
        "experiment_scope_slots",
        "experiment_scope_requests",
        "experiment_scope_events",
    )
    if _continuations_exist(connection):
        for row in connection.execute("SELECT authorization_id FROM ledger_continuations"):
            _find_continuation(connection, row["authorization_id"])
    if _experiment_scopes_exist(connection):
        for row in connection.execute("SELECT authorization_id FROM experiment_scopes"):
            _find_experiment_scope(connection, row["authorization_id"])
    rows = {}
    for name in names:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
        rows[name] = (
            [dict(row) for row in connection.execute(f"SELECT * FROM {name} ORDER BY rowid")]
            if exists
            else None
        )
    # Bind the uncertainty audit trail, without including future new-request
    # settled/reserved events that would invalidate normal authorized work.
    rows["quarantined_request_audit"] = [
        dict(row)
        for row in connection.execute("""SELECT * FROM ledger_events WHERE request_id IN
            (SELECT request_id FROM reservations WHERE status='uncertain') ORDER BY event_id""")
    ]
    return _digest(rows)


def _quarantine_observation(connection: sqlite3.Connection) -> QuarantineObservation:
    _configuration(connection)
    _totals(connection)
    rows = connection.execute(
        f"SELECT {_REQUEST_COLUMNS} FROM reservations WHERE status='uncertain' ORDER BY request_id"
    ).fetchall()
    return QuarantineObservation(
        unknown_ids=tuple(row["request_id"] for row in rows),
        unknown_fingerprints=tuple(
            (row["request_id"], _quarantine_fingerprint(row)) for row in rows
        ),
        meta_sha256=_digest(dict(connection.execute("SELECT * FROM ledger_meta").fetchone())),
        authorization_history_sha256=_historical_authorizations_digest(connection),
        held_usd=_usd(sum(row["amount_nanos"] for row in rows)),
    )


def _find_quarantine_scope(connection: sqlite3.Connection, authorization_id: str) -> sqlite3.Row:
    if not _quarantine_scopes_exist(connection):
        raise LedgerConflict()
    row = connection.execute(
        "SELECT * FROM quarantine_scopes WHERE authorization_id=?", (authorization_id,)
    ).fetchone()
    if row is None:
        raise LedgerConflict()
    try:
        _quarantine_guards(connection)
        _identifier(row["authorization_id"])
        _identifier(row["authorization_ref"])
        for key in (
            "protocol_sha256",
            "meta_sha256",
            "history_sha256",
            "slots_fingerprint",
            "registration_fingerprint",
        ):
            _valid_digest(row[key])
        _counter(row["cap_nanos"], minimum=1, maximum=100_000_000)
        _counter(row["held_nanos"], minimum=1)
        _counter(row["max_requests"], minimum=1, maximum=24)
        binding = json.loads(row["unknown_binding"])
        if (
            set(binding) != {"ids", "fingerprints"}
            or _unknown_binding(
                tuple(binding["ids"]), tuple(tuple(pair) for pair in binding["fingerprints"])
            )
            != row["unknown_binding"]
        ):
            raise ValueError
        registered = {
            key: row[key]
            for key in row.keys()
            if key
            not in (
                "recorded_at",
                "registration_fingerprint",
                "terminal_status",
                "terminal_reason",
                "terminal_fingerprint",
            )
        }
        if _digest(registered) != row["registration_fingerprint"]:
            raise ValueError
        marker = (row["terminal_status"], row["terminal_reason"], row["terminal_fingerprint"])
        if marker[0] is None:
            if marker != (None, None, None):
                raise ValueError
        else:
            if marker[0] not in ("closed", "revoked"):
                raise ValueError
            _identifier(marker[1])
            _valid_digest(marker[2])
            if marker[2] != _digest(
                {
                    "authorization_id": authorization_id,
                    "registration_fingerprint": row["registration_fingerprint"],
                    "terminal_status": marker[0],
                    "terminal_reason": marker[1],
                }
            ):
                raise ValueError
        slot_rows = connection.execute(
            "SELECT * FROM quarantine_scope_slots WHERE authorization_id=? ORDER BY slot_index",
            (authorization_id,),
        ).fetchall()
        if [slot["slot_index"] for slot in slot_rows] != list(range(row["max_requests"])):
            raise ValueError
        slots = _validated_request_slots(
            tuple(_experiment_slot(slot) for slot in slot_rows),
            outputs=(1024, 2048),
            exact_request_id=True,
        )
        if (
            _experiment_slots_fingerprint(slots) != row["slots_fingerprint"]
            or sum(_money(slot.amount_usd) for slot in slots) > row["cap_nanos"]
        ):
            raise ValueError
    except (IndexError, KeyError, InvalidOperation, TypeError, ValueError):
        raise LedgerUnavailable() from None
    return row


def _quarantine_scope_status(
    connection: sqlite3.Connection, authorization_id: str
) -> QuarantineScopeStatus:
    row = _find_quarantine_scope(connection, authorization_id)
    observed = _quarantine_observation(connection)
    binding = json.loads(row["unknown_binding"])
    events = connection.execute(
        "SELECT status,reason_code FROM quarantine_scope_events WHERE authorization_id=? ORDER BY event_id",
        (authorization_id,),
    ).fetchall()
    if not 1 <= len(events) <= 2 or tuple(events[0]) != (
        "authorized",
        "UserAuthorizedQuarantineScope",
    ):
        raise LedgerUnavailable()
    if len(events) == 2 and (
        events[1]["status"] not in ("closed", "revoked")
        or events[1]["reason_code"]
        not in (
            "ExperimentClosed",
            "NewUncertainty",
            "HaltedAgain",
            "CostOverrun",
            "QuarantineChanged",
        )
    ):
        raise LedgerUnavailable()
    if row["terminal_status"] is None:
        if len(events) != 1:
            raise LedgerUnavailable()
    elif len(events) != 2 or (events[1]["status"], events[1]["reason_code"]) != (
        row["terminal_status"],
        row["terminal_reason"],
    ):
        raise LedgerUnavailable()
    used, consumed = _scope_usage(connection, authorization_id, "quarantine")
    if consumed > row["max_requests"]:
        raise LedgerUnavailable()
    pending = (
        connection.execute("SELECT 1 FROM reservations WHERE status='reserved' LIMIT 1").fetchone()
        is not None
    )
    remaining = max(0, row["cap_nanos"] - used)
    reason = None
    if len(events) == 2:
        reason = events[1]["reason_code"]
    elif not _configuration(connection)[2]:
        reason = "GlobalHaltChanged"
    elif observed.meta_sha256 != row["meta_sha256"]:
        reason = "LedgerConfigurationChanged"
    elif observed.unknown_ids != tuple(binding["ids"]):
        reason = "UncertaintyChanged"
    elif observed.unknown_fingerprints != tuple(tuple(pair) for pair in binding["fingerprints"]):
        reason = "QuarantineChanged"
    elif observed.authorization_history_sha256 != row["history_sha256"]:
        reason = "AuthorizationHistoryChanged"
    elif _observed_overrun(connection):
        reason = "CostOverrun"
    elif pending:
        reason = "PendingRequest"
    elif not remaining:
        reason = "ExperimentCapExceeded"
    elif consumed == row["max_requests"]:
        reason = "ExperimentRequestsExhausted"
    return QuarantineScopeStatus(
        authorization_id=row["authorization_id"],
        authorization_ref=row["authorization_ref"],
        unknown_ids=tuple(binding["ids"]),
        allowed_model="gpt-4o-mini",
        additional_cap_usd=_usd(row["cap_nanos"]),
        held_usd=_usd(row["held_nanos"]),
        used_usd=_usd(used),
        remaining_usd=_usd(remaining),
        active=reason is None,
        block_reason=reason,
        protocol_sha256=row["protocol_sha256"],
        max_requests=row["max_requests"],
        consumed_requests=consumed,
        terminal_status=row["terminal_status"],
    )


def _quarantine_allowances(connection: sqlite3.Connection) -> int:
    if not _quarantine_scopes_exist(connection):
        return 0
    total = 0
    for row in connection.execute("SELECT authorization_id FROM quarantine_scopes"):
        status = _quarantine_scope_status(connection, row["authorization_id"])
        if status.active or status.block_reason == "PendingRequest":
            total += _money(status.remaining_usd, ceiling=False)
    return total


def _all_allowances(connection: sqlite3.Connection) -> int:
    total = _quarantine_allowances(connection)
    for exists, table, read_status in (
        (_continuations_exist(connection), "ledger_continuations", _continuation_status),
        (_experiment_scopes_exist(connection), "experiment_scopes", _experiment_scope_status),
    ):
        if exists:
            for row in connection.execute(f"SELECT authorization_id FROM {table}"):
                status = read_status(connection, row["authorization_id"])
                if status.active or status.block_reason == "PendingRequest":
                    total += _money(status.remaining_usd, ceiling=False)
    return total


def _claimed_scope_identity(connection: sqlite3.Connection, slot: ExperimentRequestSlot) -> bool:
    if (
        _find(connection, slot.request_id) is not None
        or connection.execute(
            "SELECT 1 FROM reservations WHERE run_id=? AND case_id=? AND case_revision=? AND attempt=?",
            (slot.run_id, slot.case_id, slot.case_revision, slot.attempt),
        ).fetchone()
    ):
        return True
    for exists, kind in (
        (_experiment_scopes_exist(connection), "experiment"),
        (_quarantine_scopes_exist(connection), "quarantine"),
    ):
        if (
            exists
            and connection.execute(
                f"SELECT 1 FROM {kind}_scope_slots WHERE request_id=? OR (run_id=? AND case_id=? AND case_revision=? AND attempt=?)",
                (slot.request_id, slot.run_id, slot.case_id, slot.case_revision, slot.attempt),
            ).fetchone()
        ):
            return True
    return False


def _authorization_status(
    connection: sqlite3.Connection, authorization_id: str
) -> ContinuationStatus | QuarantineScopeStatus:
    try:
        _find_continuation(connection, authorization_id)
    except LedgerConflict:
        try:
            return _experiment_scope_status(connection, authorization_id)
        except LedgerConflict:
            return _quarantine_scope_status(connection, authorization_id)
    return _continuation_status(connection, authorization_id)


def _revoke_experiment_scopes(connection: sqlite3.Connection, reason_code: str) -> None:
    if not _experiment_scopes_exist(connection):
        return
    scopes = connection.execute("""SELECT authorization_id FROM experiment_scopes s WHERE NOT EXISTS
        (SELECT 1 FROM experiment_scope_events e WHERE e.authorization_id=s.authorization_id AND e.status IN ('revoked','closed'))""").fetchall()
    for row in scopes:
        _find_experiment_scope(connection, row["authorization_id"])
        connection.execute(
            "INSERT INTO experiment_scope_events(authorization_id,status,reason_code) VALUES (?,'revoked',?)",
            (row["authorization_id"], reason_code),
        )


def _revoke_continuations(connection: sqlite3.Connection, reason_code: str) -> None:
    if _continuations_exist(connection):
        for row in connection.execute(
            "SELECT authorization_id FROM ledger_continuations WHERE active = 1"
        ).fetchall():
            _find_continuation(connection, row["authorization_id"])
            connection.execute(
                "UPDATE ledger_continuations SET active = 0, revocation_code = ? WHERE authorization_id = ?",
                (reason_code, row["authorization_id"]),
            )
            connection.execute(
                "INSERT INTO continuation_events (authorization_id, status, reason_code) VALUES (?, 'revoked', ?)",
                (row["authorization_id"], reason_code),
            )
    _revoke_experiment_scopes(connection, reason_code)
    _revoke_quarantine_scopes(connection, reason_code)


def _revoke_quarantine_scopes(connection: sqlite3.Connection, reason_code: str) -> None:
    if not _quarantine_scopes_exist(connection):
        return
    rows = connection.execute("""SELECT authorization_id FROM quarantine_scopes s WHERE NOT EXISTS
        (SELECT 1 FROM quarantine_scope_events e WHERE e.authorization_id=s.authorization_id AND e.status IN ('closed','revoked'))""").fetchall()
    for row in rows:
        _quarantine_scope_status(connection, row["authorization_id"])
        _terminal_quarantine_scope(connection, row["authorization_id"], "revoked", reason_code)


def _terminal_quarantine_scope(
    connection: sqlite3.Connection, authorization_id: str, status: str, reason: str
) -> None:
    row = _find_quarantine_scope(connection, authorization_id)
    if row["terminal_status"] is not None:
        raise LedgerUnavailable()
    marker = _digest(
        {
            "authorization_id": authorization_id,
            "registration_fingerprint": row["registration_fingerprint"],
            "terminal_status": status,
            "terminal_reason": reason,
        }
    )
    connection.execute(
        "INSERT INTO quarantine_scope_events(authorization_id,status,reason_code) VALUES (?,?,?)",
        (authorization_id, status, reason),
    )
    changed = connection.execute(
        """UPDATE quarantine_scopes SET terminal_status=?,terminal_reason=?,terminal_fingerprint=?
        WHERE authorization_id=? AND terminal_status IS NULL""",
        (status, reason, marker, authorization_id),
    ).rowcount
    if changed != 1:
        raise LedgerUnavailable()


class BudgetLedger:
    """Open an existing ledger; use create explicitly for its first initialization."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self._path = _path(path)
        with _transaction(self._path) as connection:
            _configuration(connection)
            connection.execute(f"SELECT {_REQUEST_COLUMNS} FROM reservations LIMIT 0")
            connection.execute("SELECT request_id, status, error_code FROM ledger_events LIMIT 0")
            _totals(connection)

    @classmethod
    def create(
        cls,
        path: str | os.PathLike[str],
        *,
        limit_usd: Decimal,
        opening_spend_usd: Decimal,
    ) -> BudgetLedger:
        limit = _money(limit_usd, ceiling=False)
        opening = _money(opening_spend_usd)
        if limit_usd > _MAX_LIMIT or opening > limit:
            raise ValueError("Invalid ledger initialization.")
        ledger_path = _path(path)
        try:
            descriptor = os.open(ledger_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(descriptor)
        except FileExistsError:
            raise LedgerConflict() from None
        except OSError:
            raise LedgerUnavailable() from None

        committed = False
        try:
            with _transaction(ledger_path, write=True) as connection:
                connection.execute(
                    """CREATE TABLE ledger_meta (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
                    limit_nanos INTEGER NOT NULL CHECK (limit_nanos BETWEEN 0 AND 5000000000),
                    opening_nanos INTEGER NOT NULL CHECK (opening_nanos BETWEEN 0 AND limit_nanos),
                    halted INTEGER NOT NULL CHECK (halted IN (0, 1))
                    )"""
                )
                connection.execute(
                    """CREATE TABLE reservations (
                    request_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    case_id TEXT NOT NULL,
                    case_revision INTEGER NOT NULL CHECK (case_revision >= 0),
                    attempt INTEGER NOT NULL CHECK (attempt BETWEEN 1 AND 2),
                    model TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    amount_nanos INTEGER NOT NULL CHECK (amount_nanos >= 0),
                    status TEXT NOT NULL CHECK (status IN ('reserved','settled','uncertain','released')),
                    cost_nanos INTEGER CHECK (cost_nanos >= 0),
                    cost_decimal TEXT,
                    input_tokens INTEGER CHECK (input_tokens >= 0),
                    output_tokens INTEGER CHECK (output_tokens >= 0),
                    error_code TEXT,
                    CHECK (
                      (status = 'settled' AND cost_nanos IS NOT NULL AND cost_decimal IS NOT NULL
                       AND input_tokens IS NOT NULL AND output_tokens IS NOT NULL)
                      OR (status != 'settled' AND cost_nanos IS NULL AND cost_decimal IS NULL
                          AND input_tokens IS NULL AND output_tokens IS NULL)
                    ),
                    CHECK ((status = 'reserved' AND error_code IS NULL)
                           OR status = 'settled'
                           OR (status IN ('uncertain','released') AND error_code IS NOT NULL))
                    )"""
                )
                connection.execute(
                    """CREATE TABLE ledger_events (
                    event_id INTEGER PRIMARY KEY,
                    request_id TEXT NOT NULL REFERENCES reservations(request_id),
                    status TEXT NOT NULL,
                    error_code TEXT,
                    recorded_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                    )"""
                )
                connection.execute(
                    "INSERT INTO ledger_meta VALUES (1, 1, ?, ?, 0)", (limit, opening)
                )
            committed = True
            return cls(ledger_path)
        finally:
            if not committed:
                with suppress(OSError):
                    ledger_path.unlink()

    def authorize_continuation(
        self,
        *,
        authorization_id: str,
        authorization_ref: str,
        expected_request_id: str,
        held_usd: Decimal,
        allowed_model: str = "gpt-4o-mini",
        additional_cap_usd: Decimal,
    ) -> ContinuationStatus:
        """Record a caller-verified human exception; never clear the global halt.

        The caller must hold explicit human authorization for this exact scope.
        A larger held allocation is not provider usage evidence or reconciliation.
        One immutable grant is allowed per quarantined incident; replay cannot
        refresh its budget or resurrect a revoked grant.
        """
        authorization_id, authorization_ref, expected_request_id = map(
            _identifier, (authorization_id, authorization_ref, expected_request_id)
        )
        held = _money(held_usd)
        cap = _money(additional_cap_usd, ceiling=False)
        if allowed_model != "gpt-4o-mini" or held < 20_000_000 or not 0 < cap <= 5_000_000_000:
            raise ValueError("Invalid continuation scope.")
        with _transaction(self._path, write=True) as connection:
            limit, opening, halted = _configuration(connection)
            _totals(connection)
            if (
                _quarantine_scopes_exist(connection)
                and connection.execute(
                    "SELECT 1 FROM quarantine_scopes WHERE authorization_id=?", (authorization_id,)
                ).fetchone()
            ):
                raise LedgerConflict()
            _continuation_schema(connection)
            existing = connection.execute(
                "SELECT authorization_id FROM ledger_continuations WHERE authorization_id = ?",
                (authorization_id,),
            ).fetchone()
            if existing:
                row = _find_continuation(connection, authorization_id)
                if (
                    row["authorization_ref"] != authorization_ref
                    or row["expected_request_id"] != expected_request_id
                    or row["allowed_model"] != allowed_model
                    or row["held_nanos"] != held
                    or row["cap_nanos"] != cap
                ):
                    raise LedgerConflict()
                return _continuation_status(connection, authorization_id)
            if connection.execute(
                "SELECT 1 FROM ledger_continuations WHERE expected_request_id = ?",
                (expected_request_id,),
            ).fetchone():
                raise LedgerConflict()
            row = _required(connection, expected_request_id)
            unknown_ids = [
                item[0]
                for item in connection.execute(
                    "SELECT request_id FROM reservations WHERE status = 'uncertain'"
                )
            ]
            pending = (
                connection.execute(
                    "SELECT 1 FROM reservations WHERE status = 'reserved' LIMIT 1"
                ).fetchone()
                is not None
            )
            if (
                not halted
                or row["status"] != "uncertain"
                or row["error_code"] != "ProviderModelMismatch"
                or row["model"] != "gpt-4.1-mini"
                or unknown_ids != [expected_request_id]
                or pending
                or _observed_overrun(connection)
            ):
                raise BudgetDenied()
            if held < row["amount_nanos"]:
                raise ValueError("An unresolved hold cannot decrease.")
            settled, _, _ = _totals(connection)
            if opening + settled + held + cap > limit:
                raise BudgetDenied()
            prior_held = row["amount_nanos"]
            connection.execute(
                "UPDATE reservations SET amount_nanos = ? WHERE request_id = ?",
                (held, expected_request_id),
            )
            fingerprint = _quarantine_fingerprint(_required(connection, expected_request_id))
            connection.execute(
                """INSERT INTO ledger_continuations
                (authorization_id, authorization_ref, expected_request_id, allowed_model,
                 cap_nanos, held_nanos, prior_held_nanos, quarantine_fingerprint, active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                (
                    authorization_id,
                    authorization_ref,
                    expected_request_id,
                    allowed_model,
                    cap,
                    held,
                    prior_held,
                    fingerprint,
                ),
            )
            _audit(connection, expected_request_id, "held_increased", "UserAuthorizedContinuation")
            connection.execute(
                """INSERT INTO continuation_events (authorization_id, status, reason_code)
                VALUES (?, 'authorized', 'UserAuthorizedContinuation')""",
                (authorization_id,),
            )
            return _continuation_status(connection, authorization_id)

    def continuation_status(
        self, authorization_id: str
    ) -> ContinuationStatus | QuarantineScopeStatus:
        authorization_id = _identifier(authorization_id)
        with _transaction(self._path) as connection:
            return _authorization_status(connection, authorization_id)

    def quarantine_observation(self) -> QuarantineObservation:
        """Capture exact unresolved records/configuration/history without writes."""
        with _transaction(self._path) as connection:
            return _quarantine_observation(connection)

    def authorize_quarantine_scope(
        self,
        *,
        authorization_id: str,
        authorization_ref: str,
        expected_unknown_ids: tuple[str, ...],
        expected_unknown_fingerprints: tuple[tuple[str, str], ...],
        expected_meta_sha256: str,
        expected_authorization_history_sha256: str,
        protocol_sha256: str,
        request_slots: tuple[ExperimentRequestSlot, ...],
        additional_cap_usd: Decimal,
    ) -> QuarantineScopeStatus:
        """Record a newly authorized finite experiment over all held uncertainty.

        The trusted caller must have fresh human authorization for these exact
        immutable inputs. This independent scope neither reconciles a request
        nor reactivates/refills historical authorizations or clears global halt.
        """
        authorization_id, authorization_ref = map(
            _identifier, (authorization_id, authorization_ref)
        )
        protocol_sha256 = _valid_digest(protocol_sha256)
        expected_meta_sha256 = _valid_digest(expected_meta_sha256)
        expected_authorization_history_sha256 = _valid_digest(expected_authorization_history_sha256)
        binding = _unknown_binding(expected_unknown_ids, expected_unknown_fingerprints)
        cap = _money(additional_cap_usd, ceiling=False)
        if not 0 < additional_cap_usd <= Decimal("0.10") or not cap:
            raise ValueError("Invalid quarantine funding cap.")
        slots = _validated_request_slots(request_slots, outputs=(1024, 2048), exact_request_id=True)
        slots_fingerprint = _experiment_slots_fingerprint(slots)
        if sum(_money(slot.amount_usd) for slot in slots) > cap:
            raise ValueError("Quarantine slots exceed funding cap.")
        with _transaction(self._path, write=True) as connection:
            limit, opening, halted = _configuration(connection)
            settled, reserved, uncertain = _totals(connection)
            for exists, table in (
                (_continuations_exist(connection), "ledger_continuations"),
                (_experiment_scopes_exist(connection), "experiment_scopes"),
            ):
                if (
                    exists
                    and connection.execute(
                        f"SELECT 1 FROM {table} WHERE authorization_id=?", (authorization_id,)
                    ).fetchone()
                ):
                    raise LedgerConflict()
            if _quarantine_scopes_exist(connection):
                _quarantine_guards(connection)
                existing = connection.execute(
                    "SELECT 1 FROM quarantine_scopes WHERE authorization_id=?", (authorization_id,)
                ).fetchone()
                if existing:
                    row = _find_quarantine_scope(connection, authorization_id)
                    if any(
                        row[key] != value
                        for key, value in (
                            ("authorization_ref", authorization_ref),
                            ("protocol_sha256", protocol_sha256),
                            ("unknown_binding", binding),
                            ("meta_sha256", expected_meta_sha256),
                            ("history_sha256", expected_authorization_history_sha256),
                            ("cap_nanos", cap),
                            ("slots_fingerprint", slots_fingerprint),
                        )
                    ):
                        raise LedgerConflict()
                    return _quarantine_scope_status(connection, authorization_id)
            observed = _quarantine_observation(connection)
            if (
                not halted
                or reserved
                or _observed_overrun(connection)
                or observed.unknown_ids != expected_unknown_ids
                or observed.unknown_fingerprints != expected_unknown_fingerprints
                or observed.meta_sha256 != expected_meta_sha256
                or observed.authorization_history_sha256 != expected_authorization_history_sha256
            ):
                raise BudgetDenied()
            for exists, table in (
                (_experiment_scopes_exist(connection), "experiment_scopes"),
                (_quarantine_scopes_exist(connection), "quarantine_scopes"),
            ):
                if (
                    exists
                    and connection.execute(
                        f"SELECT 1 FROM {table} WHERE protocol_sha256=?", (protocol_sha256,)
                    ).fetchone()
                ):
                    raise LedgerConflict()
            if opening + settled + reserved + uncertain + _all_allowances(connection) + cap > limit:
                raise BudgetDenied()
            if any(_claimed_scope_identity(connection, slot) for slot in slots):
                raise LedgerConflict()
            _quarantine_schema(connection)
            registered = {
                "authorization_id": authorization_id,
                "authorization_ref": authorization_ref,
                "protocol_sha256": protocol_sha256,
                "cap_nanos": cap,
                "held_nanos": _money(observed.held_usd),
                "unknown_binding": binding,
                "meta_sha256": expected_meta_sha256,
                "history_sha256": expected_authorization_history_sha256,
                "max_requests": len(slots),
                "slots_fingerprint": slots_fingerprint,
            }
            columns = ",".join(registered) + ",registration_fingerprint"
            marks = ",".join("?" for _ in range(len(registered) + 1))
            connection.execute(
                f"INSERT INTO quarantine_scopes({columns}) VALUES ({marks})",
                (*registered.values(), _digest(registered)),
            )
            for index, slot in enumerate(slots):
                connection.execute(
                    """INSERT INTO quarantine_scope_slots
                    (request_id,authorization_id,slot_index,run_id,case_id,case_revision,attempt,model,phase,input_token_reserve,max_output_tokens,amount_nanos)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        slot.request_id,
                        authorization_id,
                        index,
                        slot.run_id,
                        slot.case_id,
                        slot.case_revision,
                        slot.attempt,
                        slot.model,
                        slot.phase,
                        slot.input_token_reserve,
                        slot.max_output_tokens,
                        _money(slot.amount_usd),
                    ),
                )
            connection.execute(
                "INSERT INTO quarantine_scope_events(authorization_id,status,reason_code) VALUES (?,'authorized','UserAuthorizedQuarantineScope')",
                (authorization_id,),
            )
            return _quarantine_scope_status(connection, authorization_id)

    def quarantine_scope_status(self, authorization_id: str) -> QuarantineScopeStatus:
        authorization_id = _identifier(authorization_id)
        with _transaction(self._path) as connection:
            return _quarantine_scope_status(connection, authorization_id)

    def close_quarantine_scope(self, authorization_id: str) -> QuarantineScopeStatus:
        authorization_id = _identifier(authorization_id)
        with _transaction(self._path, write=True) as connection:
            status = _quarantine_scope_status(connection, authorization_id)
            terminal = connection.execute(
                "SELECT 1 FROM quarantine_scope_events WHERE authorization_id=? AND status IN ('closed','revoked')",
                (authorization_id,),
            ).fetchone()
            if terminal is None:
                _terminal_quarantine_scope(
                    connection, authorization_id, "closed", "ExperimentClosed"
                )
                status = _quarantine_scope_status(connection, authorization_id)
            return status

    def authorize_experiment_scope(
        self,
        *,
        authorization_id: str,
        authorization_ref: str,
        parent_authorization_id: str,
        protocol_sha256: str,
        request_slots: tuple[ExperimentRequestSlot, ...],
        additional_cap_usd: Decimal,
    ) -> ExperimentScopeStatus:
        """Record a new human-authorized experiment, never refill its parent grant.

        This trusted caller operation requires explicit human authorization for
        the registered protocol and request slots. It does not reconcile the
        old incident, clear the halt, or permit ordinary live factory requests.
        A protocol is authorized once; exact replay cannot create new credit.
        """
        authorization_id, authorization_ref, parent_authorization_id = map(
            _identifier, (authorization_id, authorization_ref, parent_authorization_id)
        )
        if (
            not isinstance(protocol_sha256, str)
            or re.fullmatch(r"[a-f0-9]{64}", protocol_sha256) is None
        ):
            raise ValueError("Invalid experiment protocol fingerprint.")
        cap = _money(additional_cap_usd, ceiling=False)
        if not 0 < additional_cap_usd <= Decimal("0.10") or not cap:
            raise ValueError("Invalid experiment funding cap.")
        slots = _validated_experiment_slots(request_slots)
        slots_fingerprint = _experiment_slots_fingerprint(slots)
        if sum(_money(slot.amount_usd) for slot in slots) > cap:
            raise ValueError("Experiment request slots exceed funding cap.")
        with _transaction(self._path, write=True) as connection:
            limit, opening, _ = _configuration(connection)
            settled, reserved, uncertain = _totals(connection)
            if (
                _quarantine_scopes_exist(connection)
                and connection.execute(
                    "SELECT 1 FROM quarantine_scopes WHERE authorization_id=? OR protocol_sha256=?",
                    (authorization_id, protocol_sha256),
                ).fetchone()
            ):
                raise LedgerConflict()
            if (
                _continuations_exist(connection)
                and connection.execute(
                    "SELECT 1 FROM ledger_continuations WHERE authorization_id=?",
                    (authorization_id,),
                ).fetchone()
            ):
                raise LedgerConflict()
            if _experiment_scopes_exist(connection):
                existing = connection.execute(
                    "SELECT 1 FROM experiment_scopes WHERE authorization_id=?", (authorization_id,)
                ).fetchone()
                if existing:
                    row = _find_experiment_scope(connection, authorization_id)
                    if any(
                        row[key] != value
                        for key, value in (
                            ("authorization_ref", authorization_ref),
                            ("parent_authorization_id", parent_authorization_id),
                            ("protocol_sha256", protocol_sha256),
                            ("cap_nanos", cap),
                            ("slots_fingerprint", slots_fingerprint),
                        )
                    ):
                        raise LedgerConflict()
                    return _experiment_scope_status(connection, authorization_id)
            try:
                parent = _find_continuation(connection, parent_authorization_id)
            except LedgerConflict:
                raise BudgetDenied() from None
            parent_status = _continuation_status(connection, parent_authorization_id)
            if parent_status.block_reason not in (None, "ContinuationCapExceeded"):
                raise BudgetDenied()
            quarantine = _required(connection, parent["expected_request_id"])
            if (
                quarantine["model"] != "gpt-4.1-mini"
                or quarantine["error_code"] != "ProviderModelMismatch"
            ):
                raise BudgetDenied()
            # Back every outstanding allowance under the same original ceiling,
            # rather than promising the same unspent global credit twice.
            allowances = 0
            for row in connection.execute("SELECT authorization_id FROM ledger_continuations"):
                status = _continuation_status(connection, row["authorization_id"])
                if status.active:
                    allowances += _money(status.remaining_usd, ceiling=False)
            if _experiment_scopes_exist(connection):
                if connection.execute(
                    "SELECT 1 FROM experiment_scopes WHERE protocol_sha256=?", (protocol_sha256,)
                ).fetchone():
                    raise LedgerConflict()
                for row in connection.execute("SELECT authorization_id FROM experiment_scopes"):
                    status = _experiment_scope_status(connection, row["authorization_id"])
                    if status.active:
                        allowances += _money(status.remaining_usd, ceiling=False)
            allowances += _quarantine_allowances(connection)
            if opening + settled + reserved + uncertain + allowances + cap > limit:
                raise BudgetDenied()
            for slot in slots:
                if _quarantine_scopes_exist(connection) and _claimed_scope_identity(
                    connection, slot
                ):
                    raise LedgerConflict()
                if (
                    _find(connection, slot.request_id) is not None
                    or connection.execute(
                        "SELECT 1 FROM reservations WHERE run_id=? AND case_id=? AND case_revision=? AND attempt=?",
                        (slot.run_id, slot.case_id, slot.case_revision, slot.attempt),
                    ).fetchone()
                ):
                    raise LedgerConflict()
                if (
                    _experiment_scopes_exist(connection)
                    and connection.execute(
                        "SELECT 1 FROM experiment_scope_slots WHERE request_id=? OR (run_id=? AND case_id=? AND case_revision=? AND attempt=?)",
                        (
                            slot.request_id,
                            slot.run_id,
                            slot.case_id,
                            slot.case_revision,
                            slot.attempt,
                        ),
                    ).fetchone()
                ):
                    raise LedgerConflict()
            _experiment_scope_schema(connection)
            registration = {
                "authorization_id": authorization_id,
                "authorization_ref": authorization_ref,
                "parent_authorization_id": parent_authorization_id,
                "expected_request_id": parent["expected_request_id"],
                "protocol_sha256": protocol_sha256,
                "cap_nanos": cap,
                "held_nanos": parent["held_nanos"],
                "parent_fingerprint": _digest(dict(parent)),
                "quarantine_fingerprint": _quarantine_fingerprint(quarantine),
                "max_requests": len(slots),
                "slots_fingerprint": slots_fingerprint,
            }
            columns = ",".join(registration) + ",registration_fingerprint"
            marks = ",".join("?" for _ in range(len(registration) + 1))
            connection.execute(
                f"INSERT INTO experiment_scopes({columns}) VALUES ({marks})",
                (*registration.values(), _digest(registration)),
            )
            for index, slot in enumerate(slots):
                connection.execute(
                    """INSERT INTO experiment_scope_slots
                    (request_id,authorization_id,slot_index,run_id,case_id,case_revision,attempt,model,phase,input_token_reserve,max_output_tokens,amount_nanos)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        slot.request_id,
                        authorization_id,
                        index,
                        slot.run_id,
                        slot.case_id,
                        slot.case_revision,
                        slot.attempt,
                        slot.model,
                        slot.phase,
                        slot.input_token_reserve,
                        slot.max_output_tokens,
                        _money(slot.amount_usd),
                    ),
                )
            connection.execute(
                "INSERT INTO experiment_scope_events(authorization_id,status,reason_code) VALUES (?,'authorized','UserAuthorizedExperimentScope')",
                (authorization_id,),
            )
            return _experiment_scope_status(connection, authorization_id)

    def experiment_scope_status(self, authorization_id: str) -> ExperimentScopeStatus:
        authorization_id = _identifier(authorization_id)
        with _transaction(self._path) as connection:
            return _experiment_scope_status(connection, authorization_id)

    def close_experiment_scope(self, authorization_id: str) -> ExperimentScopeStatus:
        """Append a permanent close event; pending requests and history stay held."""
        authorization_id = _identifier(authorization_id)
        with _transaction(self._path, write=True) as connection:
            status = _experiment_scope_status(connection, authorization_id)
            terminal = connection.execute(
                "SELECT 1 FROM experiment_scope_events WHERE authorization_id=? AND status IN ('closed','revoked')",
                (authorization_id,),
            ).fetchone()
            if terminal is None:
                connection.execute(
                    "INSERT INTO experiment_scope_events(authorization_id,status,reason_code) VALUES (?,'closed','ExperimentClosed')",
                    (authorization_id,),
                )
                status = _experiment_scope_status(connection, authorization_id)
            return status

    def reserve(
        self,
        *,
        request_id: str,
        run_id: str,
        case_id: str,
        case_revision: int,
        attempt: int,
        model: str,
        phase: str,
        amount_usd: Decimal,
        continuation_id: str | None = None,
        input_token_reserve: int | None = None,
        max_output_tokens: int | None = None,
    ) -> Reservation:
        request_id = _identifier(request_id)
        with _transaction(self._path, write=True) as connection:
            limit, opening, halted = _configuration(connection)
            if _find(connection, request_id) is not None:
                raise LedgerConflict()
            run_id, case_id, model = map(_identifier, (run_id, case_id, model))
            case_revision = _counter(case_revision)
            attempt = _counter(attempt, minimum=1, maximum=2)
            if not isinstance(phase, str) or _PHASE.fullmatch(phase) is None:
                raise ValueError("Invalid ledger phase.")
            amount = _money(amount_usd)
            settled, reserved, uncertain = _totals(connection)
            if continuation_id is not None:
                continuation_id = _identifier(continuation_id)
                try:
                    scope = _authorization_status(connection, continuation_id)
                except LedgerConflict:
                    raise BudgetDenied() from None
                if (
                    not scope.active
                    or model != scope.allowed_model
                    or phase != "development"
                    or amount > 20_000_000
                    or amount > _money(scope.remaining_usd, ceiling=False)
                ):
                    raise BudgetDenied()
                if isinstance(scope, (ExperimentScopeStatus, QuarantineScopeStatus)):
                    if type(input_token_reserve) is not int or type(max_output_tokens) is not int:
                        raise BudgetDenied()
                    kind = (
                        "quarantine" if isinstance(scope, QuarantineScopeStatus) else "experiment"
                    )
                    slot = connection.execute(
                        f"SELECT * FROM {kind}_scope_slots WHERE authorization_id=? AND request_id=?",
                        (continuation_id, request_id),
                    ).fetchone()
                    if (
                        slot is None
                        or amount_usd != _usd(slot["amount_nanos"])
                        or any(
                            slot[key] != value
                            for key, value in (
                                ("run_id", run_id),
                                ("case_id", case_id),
                                ("case_revision", case_revision),
                                ("attempt", attempt),
                                ("model", model),
                                ("phase", phase),
                                ("amount_nanos", amount),
                                ("input_token_reserve", input_token_reserve),
                                ("max_output_tokens", max_output_tokens),
                            )
                        )
                    ):
                        raise BudgetDenied()
            elif halted:
                raise BudgetDenied()
            if opening + settled + reserved + uncertain + amount > limit:
                raise BudgetDenied()
            if (
                _quarantine_scopes_exist(connection)
                and opening + settled + reserved + uncertain + _all_allowances(connection) > limit
            ):
                raise BudgetDenied()
            connection.execute(
                """INSERT INTO reservations
                (request_id, run_id, case_id, case_revision, attempt, model, phase, amount_nanos, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'reserved')""",
                (request_id, run_id, case_id, case_revision, attempt, model, phase, amount),
            )
            if continuation_id is not None:
                connection.execute(
                    "INSERT INTO quarantine_scope_requests (request_id, authorization_id) VALUES (?, ?)"
                    if isinstance(scope, QuarantineScopeStatus)
                    else "INSERT INTO experiment_scope_requests (request_id, authorization_id) VALUES (?, ?)"
                    if isinstance(scope, ExperimentScopeStatus)
                    else "INSERT INTO continuation_requests (request_id, authorization_id) VALUES (?, ?)",
                    (request_id, continuation_id),
                )
            _audit(connection, request_id, "reserved")
            return _reservation(_required(connection, request_id))

    def settle(
        self,
        request_id: str,
        *,
        cost_usd: Decimal,
        input_tokens: int,
        output_tokens: int,
    ) -> Reservation:
        request_id = _identifier(request_id)
        cost = _money(cost_usd)
        input_tokens, output_tokens = _counter(input_tokens), _counter(output_tokens)
        with _transaction(self._path, write=True) as connection:
            _configuration(connection)
            row = _required(connection, request_id)
            if row["status"] == "settled":
                try:
                    same_cost = Decimal(row["cost_decimal"]) == cost_usd
                except (InvalidOperation, TypeError, ValueError):
                    raise LedgerUnavailable() from None
                if (
                    not same_cost
                    or row["input_tokens"] != input_tokens
                    or row["output_tokens"] != output_tokens
                ):
                    raise LedgerConflict()
                return _reservation(row)
            if row["status"] not in ("reserved", "uncertain"):
                raise LedgerConflict()
            connection.execute(
                """UPDATE reservations SET status = 'settled', cost_nanos = ?, cost_decimal = ?,
                input_tokens = ?, output_tokens = ?, error_code = NULL WHERE request_id = ?""",
                (cost, str(cost_usd), input_tokens, output_tokens, request_id),
            )
            if cost > row["amount_nanos"]:
                connection.execute("UPDATE ledger_meta SET halted = 1 WHERE singleton = 1")
                _revoke_continuations(connection, "CostOverrun")
            elif (
                _continuations_exist(connection)
                and connection.execute(
                    "SELECT 1 FROM ledger_continuations WHERE expected_request_id = ? AND active = 1",
                    (request_id,),
                ).fetchone()
            ):
                _revoke_continuations(connection, "QuarantineChanged")
            if row["status"] == "uncertain":
                _revoke_quarantine_scopes(connection, "QuarantineChanged")
            _audit(connection, request_id, "settled")
            return _reservation(_required(connection, request_id))

    def mark_uncertain(self, request_id: str, *, error_code: str) -> Reservation:
        request_id, error_code = _identifier(request_id), _identifier(error_code)
        with _transaction(self._path, write=True) as connection:
            _configuration(connection)
            row = _required(connection, request_id)
            if row["status"] == "uncertain" and row["error_code"] == error_code:
                return _reservation(row)
            if row["status"] != "reserved":
                raise LedgerConflict()
            connection.execute(
                "UPDATE reservations SET status = 'uncertain', error_code = ? WHERE request_id = ?",
                (error_code, request_id),
            )
            _revoke_continuations(connection, "NewUncertainty")
            _audit(connection, request_id, "uncertain", error_code)
            return _reservation(_required(connection, request_id))

    def release_unsent(self, request_id: str, *, error_code: str) -> Reservation:
        """Release only after the caller established that no HTTP send occurred."""
        request_id, error_code = _identifier(request_id), _identifier(error_code)
        with _transaction(self._path, write=True) as connection:
            _configuration(connection)
            row = _required(connection, request_id)
            if row["status"] != "reserved":
                raise LedgerConflict()
            connection.execute(
                "UPDATE reservations SET status = 'released', error_code = ? WHERE request_id = ?",
                (error_code, request_id),
            )
            _audit(connection, request_id, "released", error_code)
            return _reservation(_required(connection, request_id))

    def snapshot(self) -> BudgetSnapshot:
        with _transaction(self._path) as connection:
            limit, opening, halted = _configuration(connection)
            settled, reserved, uncertain = _totals(connection)
            available = max(0, limit - opening - settled - reserved - uncertain)
            return BudgetSnapshot(
                limit_usd=_usd(limit),
                opening_spend_usd=_usd(opening),
                settled_usd=_usd(settled),
                reserved_usd=_usd(reserved),
                uncertain_usd=_usd(uncertain),
                available_usd=_usd(available),
                halted=halted,
            )

    def halt(self) -> None:
        """Persist a stop on new requests without blocking known-cost reconciliation."""
        with _transaction(self._path, write=True) as connection:
            _configuration(connection)
            connection.execute("UPDATE ledger_meta SET halted = 1 WHERE singleton = 1")
            _revoke_continuations(connection, "HaltedAgain")

    def get(self, request_id: str) -> Reservation | None:
        request_id = _identifier(request_id)
        with _transaction(self._path) as connection:
            _configuration(connection)
            row = _find(connection, request_id)
            return _reservation(row) if row is not None else None
