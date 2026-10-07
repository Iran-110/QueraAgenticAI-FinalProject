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
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, InvalidOperation, localcontext
from pathlib import Path
from typing import Literal

__all__ = [
    "BudgetDenied",
    "BudgetLedger",
    "BudgetSnapshot",
    "ContinuationStatus",
    "LedgerConflict",
    "LedgerUnavailable",
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


def _revoke_continuations(connection: sqlite3.Connection, reason_code: str) -> None:
    if not _continuations_exist(connection):
        return
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

    def continuation_status(self, authorization_id: str) -> ContinuationStatus:
        authorization_id = _identifier(authorization_id)
        with _transaction(self._path) as connection:
            return _continuation_status(connection, authorization_id)

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
                    scope = _continuation_status(connection, continuation_id)
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
            elif halted:
                raise BudgetDenied()
            if opening + settled + reserved + uncertain + amount > limit:
                raise BudgetDenied()
            connection.execute(
                """INSERT INTO reservations
                (request_id, run_id, case_id, case_revision, attempt, model, phase, amount_nanos, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'reserved')""",
                (request_id, run_id, case_id, case_revision, attempt, model, phase, amount),
            )
            if continuation_id is not None:
                connection.execute(
                    "INSERT INTO continuation_requests (request_id, authorization_id) VALUES (?, ?)",
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
