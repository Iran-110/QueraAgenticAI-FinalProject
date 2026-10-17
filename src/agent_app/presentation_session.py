"""Explicit preparation, funding and launch of the finite presentation protocol.

Preparation/status never read credentials or send requests. Funding uses the
existing ledger, with the exact fresh protocol approved by Sasan; no hold is
released and no historical authorization is resumed. Only ``serve`` reads the
explicit private dotenv/token files, after public scope/index guards pass.
"""

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import subprocess
from collections.abc import Mapping
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from agent_app.contracts import ReasoningContext
from agent_app.llm.budget import BudgetLedger, ExperimentRequestSlot
from agent_app.llm.metis import request_id_for
from agent_app.llm.pricing import get_price

ROOT = Path(__file__).resolve().parents[2]
CAP = Decimal("0.10")
AUTHORIZATION_REF = "sasan-approved-presentation-plan-20261017"


class PrivateSettings(Mapping):
    """Lazy credential access: runtime verifies public scope/index before lookup."""

    def __init__(self, protocol_path, protocol, *, dotenv_path, token_file):
        original_env, original_token = Path(dotenv_path), Path(token_file)
        self._dotenv = original_env.resolve(strict=True)
        self._token_file = original_token.resolve(strict=True)
        index = Path(protocol["index"]["path"]).resolve()
        receipt_dir = Path(protocol["receipt_dir"]).resolve()
        protected = [
            Path(protocol_path).resolve(),
            Path(protocol["ledger_path"]).resolve(),
            Path(protocol["tracker_path"]).resolve(),
            *(p for p in index.rglob("*") if p.is_file()),
        ]
        if (
            original_env.is_symlink()
            or original_token.is_symlink()
            or self._dotenv != ROOT / ".env"
            or self._token_file.name != "reviewer-token.txt"
            or ROOT in self._token_file.parents
            or index in self._token_file.parents
            or receipt_dir in self._token_file.parents
            or self._dotenv == self._token_file
        ):
            raise ValueError("PresentationPrivatePathRejected")
        for path in (self._dotenv, self._token_file):
            info = path.stat()
            if not path.is_file() or info.st_nlink != 1 or info.st_size > 65536:
                raise ValueError("PresentationPrivatePathRejected")
            if any(p.exists() and path.samefile(p) for p in protected):
                raise ValueError("PresentationPrivatePathRejected")
        if self._token_file.stat().st_mode & 0o077:
            raise ValueError("PresentationPrivateTokenRequired")
        self._loaded = None

    def __iter__(self):
        return iter(("METIS_API_KEY", "AGENT_REVIEWER_TOKEN", "AGENT_REVIEWER_ID"))

    def __len__(self):
        return 3

    def __getitem__(self, name):
        if name not in tuple(self):
            raise KeyError(name)
        if name == "AGENT_REVIEWER_ID":
            return "presentation-maintainer"
        if self._loaded is None:
            from dotenv import dotenv_values

            private = dotenv_values(self._dotenv)
            self._loaded = {
                "METIS_API_KEY": private.get("METIS_API_KEY", ""),
                "AGENT_REVIEWER_TOKEN": self._token_file.read_text().strip(),
            }
        return self._loaded[name]


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _plain(value):
    return json.loads(json.dumps(value, default=str))


def _write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    with path.open("xb") as stream:
        stream.write(raw)
    return hashlib.sha256(raw).hexdigest()


def ledger_rows(path):
    """Read-only logical baseline; never dump credentials or touch an old row."""
    path = Path(path).resolve()
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        names = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        result = {}
        for name in names:
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) is None:
                raise ValueError("PresentationLedgerRejected")
            result[name] = [
                dict(row) for row in connection.execute(f'SELECT * FROM "{name}" ORDER BY rowid')
            ]
        return result


def previous_rows_preserved(before, after):
    """Additive ledger writes are permitted; existing logical records stay exact."""
    for table, rows in before.items():
        observed = {
            json.dumps(row, sort_keys=True, separators=(",", ":")) for row in after.get(table, ())
        }
        if any(
            json.dumps(row, sort_keys=True, separators=(",", ":")) not in observed for row in rows
        ):
            return False
    return True


def prepare_sessions(*, output_dir, ledger_path, index_path):
    """Create two fresh immutable protocols/copies; no funding or key lookup."""
    from agent_app.orchestration.core_delivery import (
        PREFILTER_DELIVERY_PROFILE_ID,
        delivery_recipe,
    )
    from agent_app.presentation_runtime import (
        BOUND_SOURCE_FILES,
        RECIPE_PATH,
        VOCABULARY_PATH,
        read_protocol,
    )
    from agent_app.retrieval.offline_index import open_verified_index

    output_dir = Path(output_dir).resolve()
    ledger_path = Path(ledger_path).resolve()
    index_path = Path(index_path).resolve()
    if output_dir.exists() or output_dir == ROOT or ROOT in output_dir.parents:
        raise ValueError("PresentationFreshOutputRequired")
    accepted = json.loads((ROOT / "experiments/final_corpus_v1/build-receipt-v3.json").read_bytes())
    pins = accepted["native_pins"]
    if _sha(index_path / "pilot-manifest.json") != pins["index_manifest_sha256"]:
        raise ValueError("PresentationIndexMismatch")
    client, snapshot = open_verified_index(index_path)
    client.verify()
    if snapshot != pins["index_snapshot"]:
        raise ValueError("PresentationIndexMismatch")
    ledger = BudgetLedger(ledger_path)
    state = ledger.snapshot()
    observation = _plain(asdict(ledger.quarantine_observation()))
    if (
        not state.halted
        or state.limit_usd != Decimal("4.50")
        or state.reserved_usd
        or len(observation["unknown_ids"]) != 3
        or state.available_usd < 2 * CAP
    ):
        raise ValueError("PresentationLedgerRejected")
    output_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
    _write_new(output_dir / "ledger-before.json", ledger_rows(ledger_path))
    _write_new(
        output_dir / "baseline.json",
        {
            "ledger_sha256": _sha(ledger_path),
            "snapshot": _plain(asdict(state)),
            "quarantine_before": observation,
            "old_rows_file": "ledger-before.json",
        },
    )
    recipe = delivery_recipe(profile_id=PREFILTER_DELIVERY_PROFILE_ID)
    protocols = []
    for label in ("rehearsal", "meeting"):
        identifier = f"p261018-{label}-{uuid4().hex[:12]}"
        folder = output_dir / label
        folder.mkdir(mode=0o700)
        copied = folder / "index-v3"
        shutil.copytree(index_path, copied)
        cases, slots = [], []
        for suffix, count in (("a", 3), ("b", 2), ("c", 2)):
            case_id = f"{identifier}-{suffix}"
            cases.append({"case_id": case_id, "revisions": list(range(1, count + 1))})
            for revision in range(1, count + 1):
                run_id = f"{case_id}-r{revision}"
                for attempt in (1, 2):
                    context = ReasoningContext(
                        run_id=run_id,
                        case_id=case_id,
                        case_revision=revision,
                        attempt_index=attempt,
                    )
                    slot = ExperimentRequestSlot(
                        request_id=request_id_for(context),
                        run_id=run_id,
                        case_id=case_id,
                        case_revision=revision,
                        attempt=attempt,
                        input_token_reserve=32768,
                        max_output_tokens=1024,
                        amount_usd=get_price("gpt-4o-mini").cost(32768, 1024),
                    )
                    slots.append(_plain(asdict(slot)))
        protocol = {
            "schema_version": 1,
            "profile_id": "presentation_scoped_v1",
            "phase_label": label,
            "session_id": identifier,
            "scope_id": identifier,
            "model": "gpt-4o-mini",
            "max_scope_usd": str(CAP),
            "source_commit": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "source_sha256": {name: _sha(ROOT / name) for name in BOUND_SOURCE_FILES},
            "recipe_sha256": recipe["recipe_sha256"],
            "recipe_file_sha256": _sha(ROOT / RECIPE_PATH),
            "vocabulary_file_sha256": _sha(ROOT / VOCABULARY_PATH),
            "quarantine_before": observation,
            "ledger_path": str(ledger_path),
            "tracker_path": str(folder / "tracker.sqlite3"),
            "receipt_dir": str(folder / "requests"),
            "index": {
                "path": str(copied),
                "build": pins["build"],
                "snapshot_id": pins["index_snapshot"],
                "index_manifest_sha256": pins["index_manifest_sha256"],
                "allowlist_sha256": pins["allowlist_sha256"],
                "exclusion_manifest_sha256": pins["exclusion_manifest_sha256"],
            },
            "cases": cases,
            "slots": slots,
            "authority": {
                "authorization_ref": AUTHORIZATION_REF,
                "user_approved_plan": True,
                "arbitrary_typed_queries_within_pool": True,
                "new_uncertainty_stops_both_phases": True,
                "c5_reconciled": False,
                "clear_halt": False,
                "refill_or_reuse_historical_ids": False,
            },
        }
        destination = folder / "protocol.json"
        digest = _write_new(destination, protocol)
        read_protocol(destination)
        protocols.append({"phase": label, "protocol": str(destination), "sha256": digest})
    _write_new(
        output_dir / "sessions.json", {"protocols": protocols, "maximum_new_cap_usd": "0.20"}
    )
    return protocols


def authorize_protocol(path, *, expected_sha256):
    from agent_app.presentation_runtime import read_protocol

    protocol, digest, slots = read_protocol(path)
    if digest != expected_sha256 or protocol["authority"]["authorization_ref"] != AUTHORIZATION_REF:
        raise ValueError("PresentationAuthorizationMismatch")
    ledger = BudgetLedger(protocol["ledger_path"])
    before = protocol["quarantine_before"]
    observed = _plain(asdict(ledger.quarantine_observation()))
    if observed != before:
        raise ValueError("PresentationAccountingChanged")
    status = ledger.authorize_quarantine_scope(
        authorization_id=protocol["scope_id"],
        authorization_ref=AUTHORIZATION_REF,
        expected_unknown_ids=tuple(before["unknown_ids"]),
        expected_unknown_fingerprints=tuple(tuple(pair) for pair in before["unknown_fingerprints"]),
        expected_meta_sha256=before["meta_sha256"],
        expected_authorization_history_sha256=before["authorization_history_sha256"],
        protocol_sha256=digest,
        request_slots=slots,
        additional_cap_usd=CAP,
        allow_full_context=True,
    )
    return _plain(asdict(status))


def serve(path, *, dotenv_path, reviewer_token_file, port):
    """Load private settings only after all public registration checks pass."""
    from agent_app.presentation_runtime import configured_app, read_protocol

    protocol, digest, _ = read_protocol(path)
    status = BudgetLedger(protocol["ledger_path"]).quarantine_scope_status(protocol["scope_id"])
    if not status.active or status.protocol_sha256 != digest:
        raise ValueError("PresentationScopeUnavailable")
    values = PrivateSettings(
        path, protocol, dotenv_path=dotenv_path, token_file=reviewer_token_file
    )
    app = configured_app(path, values)
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=port)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--output-dir", type=Path, required=True)
    prepare.add_argument("--ledger", type=Path, default=ROOT / "runtime/budget.sqlite3")
    prepare.add_argument("--index", type=Path, required=True)
    fund = sub.add_parser("authorize")
    fund.add_argument("--protocol", type=Path, required=True)
    fund.add_argument("--expected-sha256", required=True)
    status = sub.add_parser("status")
    status.add_argument("--protocol", type=Path, required=True)
    close = sub.add_parser("close")
    close.add_argument("--protocol", type=Path, required=True)
    server = sub.add_parser("serve")
    server.add_argument("--protocol", type=Path, required=True)
    server.add_argument("--dotenv", type=Path, required=True)
    server.add_argument("--reviewer-token-file", type=Path, required=True)
    server.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            result = prepare_sessions(
                output_dir=args.output_dir, ledger_path=args.ledger, index_path=args.index
            )
        elif args.command == "authorize":
            result = authorize_protocol(args.protocol, expected_sha256=args.expected_sha256)
        elif args.command == "serve":
            serve(
                args.protocol,
                dotenv_path=args.dotenv,
                reviewer_token_file=args.reviewer_token_file,
                port=args.port,
            )
            return 0
        else:
            from agent_app.presentation_runtime import read_protocol

            protocol, digest, _ = read_protocol(args.protocol)
            ledger = BudgetLedger(protocol["ledger_path"])
            if args.command == "close":
                result = _plain(asdict(ledger.close_quarantine_scope(protocol["scope_id"])))
            else:
                result = {
                    "protocol_sha256": digest,
                    "scope": _plain(asdict(ledger.quarantine_scope_status(protocol["scope_id"]))),
                    "ledger": _plain(asdict(ledger.snapshot())),
                }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception:
        print("PresentationSessionRejected")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
