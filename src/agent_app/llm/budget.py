"""A durable budget ledger for one shared runner and one SQLite database.

Reservations survive process failure. An ambiguous HTTP outcome remains charged
against the limit until its observed cost is reconciled; there is no expiry or
automatic refund. This ledger does not coordinate independent database copies.
"""

from __future__ import annotations

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
            if halted or opening + settled + reserved + uncertain + amount > limit:
                raise BudgetDenied()
            connection.execute(
                """INSERT INTO reservations
                (request_id, run_id, case_id, case_revision, attempt, model, phase, amount_nanos, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'reserved')""",
                (request_id, run_id, case_id, case_revision, attempt, model, phase, amount),
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

    def get(self, request_id: str) -> Reservation | None:
        request_id = _identifier(request_id)
        with _transaction(self._path) as connection:
            _configuration(connection)
            row = _find(connection, request_id)
            return _reservation(row) if row is not None else None
