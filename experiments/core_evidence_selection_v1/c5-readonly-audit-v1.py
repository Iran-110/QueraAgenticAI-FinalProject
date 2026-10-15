"""Read-only three-incident C5 inventory; never reconciles or authorizes a call.

Only existing allowlisted artifacts and SQLite URI mode=ro/query_only are read.
No app/gateway/ledger constructor, credentials, network or payload is used.
Public output uses opaque private-source aliases and hashes, never private paths.
"""

import argparse
import hashlib
import json
import os
import sqlite3
from collections import Counter
from contextlib import closing
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / "experiments/core_evidence_selection_v1"
LEDGER = ROOT / "runtime/budget.sqlite3"
PRIVATE = ROOT.parents[1] / "output/core-turn-coordinator-2026-10-11/reconciliation"
HISTORICAL = ROOT / "runtime/decision-quality/core-decision-2026-10-07-model-41"
EXPECTED_LEDGER_SHA = "141c3536fb864595d94e0d0dd4a55976418def1012402b70f313c92050222785"
IDENTITY_ID = "call:00d470ec94177a11f66c6cb3dbbb6c83069dd1385ddd6ac7b1e3df96fa50f7fa"
STABILITY_ID = "call:99512367628b4700a171466d2390b6be8ac708d62bb11ab2f354130ec2118817"
CLAIM_ID = "call:0377ef42aff047e95aca155ea1f66c1c09d34b9ed89ba2428bb17e54df950432"
NANO = Decimal(1_000_000_000)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def digest(value):
    return sha(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    )


def file_inventory():
    return {
        "private:designated-ledger" + suffix: {
            "exists": path.exists(),
            "sha256": sha(path.read_bytes()) if path.exists() else None,
            "bytes": path.stat().st_size if path.exists() else None,
        }
        for suffix in ("", "-wal", "-shm", "-journal")
        for path in (Path(str(LEDGER) + suffix),)
    }


def snapshot(db):
    schema = [
        dict(row)
        for row in db.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
        )
    ]
    tables = {}
    for item in schema:
        if item["type"] != "table":
            continue
        name = item["name"]
        if not name.replace("_", "").isalnum():
            raise ValueError("C5AuditTableRejected")
        rows = [dict(row) for row in db.execute(f'SELECT * FROM "{name}"')]
        tables[name] = {"rows": len(rows), "row_sha256": sorted(digest(row) for row in rows)}
    return {"schema_sha256": digest(schema), "tables": tables}


def observe():
    before_files = file_inventory()
    checks = []

    def check(name, passed):
        checks.append({"check": name, "passed": bool(passed)})

    check(
        "original_ledger_matches_closed_C4j_receipt",
        before_files["private:designated-ledger"]["sha256"] == EXPECTED_LEDGER_SHA,
    )
    sources = {}

    def source(alias, path, expected=None):
        raw = path.read_bytes()
        sources[alias] = {
            "sha256": sha(raw),
            "bytes": len(raw),
            "public": not alias.startswith("private:"),
        }
        if expected is not None:
            check("source_pin:" + alias, sha(raw) == expected)
        return json.loads(raw) if path.suffix == ".json" else raw

    prior = source(
        "private:C5-packet-2026-10-11",
        PRIVATE / "c5-local-reconciliation-v1.json",
        "402972621a4e873ee60dafe0f11f40f92859e7e29e9b43669c676e20401f4300",
    )
    initial = source(
        "private:model-identity-start-2026-10-07",
        HISTORICAL / "start.json",
        "b468b40d6cfdfe658cb7d525c0bfeab5001cb79db02567bb73ad046055b9e773",
    )
    observation = source(
        "private:model-identity-observation-00",
        HISTORICAL / "observation-00.json",
        "8f888468fad7cc85c6b17b74115e4c608f42c61c42e9e19f4a118fbc49253238",
    )
    source(
        "private:model-identity-summary-2026-10-07",
        HISTORICAL / "summary.json",
        "6ef21b130ad595721b17b51334fa2cf2c51da9eca4f1bb9bebc57930dd4ebb46",
    )
    stability_name = "experiments/core_stability_adversarial/stability-cost-reconciliation-v1.json"
    stability = source(stability_name, ROOT / stability_name)
    stability_receipt_name = stability["live_receipt_path"]
    stability_receipt = source(
        stability_receipt_name, ROOT / stability_receipt_name, stability["live_receipt_sha256"]
    )
    claim_name = "experiments/core_claim_boundary_v1/provider-stop-review-v1.json"
    claim = source(
        claim_name,
        ROOT / claim_name,
        "198831696a82d1d07ac383c13a19b042b6fd3d79dbf7b015cc07e9d28dba602a",
    )
    claim_receipt_name = "experiments/core_claim_boundary_v1/model-receipt-v1.json"
    claim_receipt = source(claim_receipt_name, ROOT / claim_receipt_name, claim["receipt_sha256"])
    for name in (
        "src/agent_app/llm/budget.py",
        "src/agent_app/llm/metis.py",
        "src/agent_app/llm/pricing.py",
        "src/agent_app/testing/provider_observation.py",
        "docs/live-reconciliation-2026-10-11.fa.md",
    ):
        source(name, ROOT / name)
    with closing(sqlite3.connect(LEDGER.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        check("SQLite_query_only_enabled", db.execute("PRAGMA query_only").fetchone()[0] == 1)
        before_rows = snapshot(db)
        meta = dict(db.execute("SELECT * FROM ledger_meta").fetchone())
        reservations = [
            dict(row) for row in db.execute("SELECT * FROM reservations ORDER BY request_id")
        ]
        uncertain = [row for row in reservations if row["status"] == "uncertain"]
        counts = Counter(row["status"] for row in reservations)
        settled = sum(
            (Decimal(row["cost_decimal"]) for row in reservations if row["status"] == "settled"),
            Decimal(0),
        )
        settled_nanos = sum(row["cost_nanos"] for row in reservations if row["status"] == "settled")
        held = sum((Decimal(row["amount_nanos"]) / NANO for row in uncertain), Decimal(0))
        check(
            "exact_three_public_uncertain_IDs",
            {row["request_id"] for row in uncertain} == {IDENTITY_ID, STABILITY_ID, CLAIM_ID},
        )
        check(
            "718rows_715settled_3uncertain_no_pending",
            len(reservations) == 718 and counts == {"settled": 715, "uncertain": 3},
        )
        check(
            "settled_decimal_and_nanos_agree",
            settled == Decimal(settled_nanos) / NANO == Decimal("0.599798760"),
        )
        check("three_holds_exact", held == Decimal("0.030137600"))
        check(
            "halt_ceiling_opening_unchanged",
            meta["halted"] == 1
            and meta["limit_nanos"] == 4_500_000_000
            and meta["opening_nanos"] == 0,
        )
        check(
            "all_uncertain_usage_costs_unknown_not_zero",
            all(
                all(
                    row[key] is None
                    for key in ("cost_nanos", "cost_decimal", "input_tokens", "output_tokens")
                )
                for row in uncertain
            ),
        )
        check("fourteen_tables_retained", len(before_rows["tables"]) == 14)
        incidents = []
        for row in sorted(uncertain, key=lambda value: value["request_id"]):
            rid = row["request_id"]
            events = [
                {key: event[key] for key in ("event_id", "status", "error_code", "recorded_at")}
                for event in db.execute(
                    "SELECT * FROM ledger_events WHERE request_id=? ORDER BY event_id", (rid,)
                )
            ]
            attribution = [
                {"kind": kind, "authorization_id": value["authorization_id"]}
                for kind, table in (
                    ("continuation", "continuation_requests"),
                    ("experiment", "experiment_scope_requests"),
                    ("quarantine", "quarantine_scope_requests"),
                )
                for value in db.execute(
                    f"SELECT authorization_id FROM {table} WHERE request_id=?", (rid,)
                )
            ]
            item = {
                "local_request_id": rid,
                "local_request_ID_is_provider_ID": False,
                "run_id": row["run_id"],
                "case_id": row["case_id"],
                "case_revision": row["case_revision"],
                "attempt": row["attempt"],
                "requested_model": row["model"],
                "phase": row["phase"],
                "status": row["status"],
                "error_code": row["error_code"],
                "held_reservation_usd": str(Decimal(row["amount_nanos"]) / NANO),
                "actual_charge_usd": None,
                "actual_input_tokens": None,
                "actual_output_tokens": None,
                "verified_serving_model": None,
                "provider_request_or_response_ID": None,
                "events": events,
                "scope_attribution": attribution,
                "provider_evidence_required": [
                    "A provider request/response record correlated to this exact UTC window, requested model and the owner's account/key alias; local caller SHA is not a provider ID.",
                    "Definitive received/not-received/completed/failed disposition, actual serving model, input/output usage and charge/rate/currency/discount/refund or authoritative zero-charge evidence.",
                    "Whole-account export including other team members, embeddings, evaluations and refunds; aggregate wallet delta alone does not allocate this request.",
                ],
            }
            if rid == IDENTITY_ID:
                old = prior["unresolved_incidents"][0]
                initial_entry = next(
                    entry for entry in observation["ledger_entries"] if entry["request_id"] == rid
                )
                check(
                    "first_incident_original_HTTP200_record",
                    observation["http_attempts"] == [{"status": 200}]
                    and initial_entry["error_code"] == "ProviderModelMismatch",
                )
                check(
                    "first_incident_initial_reserve_and_hold_increase",
                    Decimal(initial["one_request_reserve_usd"])
                    == Decimal(initial_entry["amount_usd"])
                    == Decimal("0.008560640")
                    and Decimal(old["held_usd"])
                    == Decimal(item["held_reservation_usd"])
                    == Decimal("0.02"),
                )
                item.update(
                    {
                        "evidence_refs": [
                            "private:model-identity-observation-00",
                            "private:model-identity-start-2026-10-07",
                            "private:C5-packet-2026-10-11",
                            "docs/live-reconciliation-2026-10-11.fa.md",
                        ],
                        "http_status_observed": 200,
                        "transport_category_observed": None,
                        "http200_is_model_or_charge_verification": False,
                        "initial_reserved_usd": "0.008560640",
                        "historically_increased_hold_usd": "0.020000000",
                        "interpretation": "Original primary receipt records HTTP200 and ProviderModelMismatch before usable usage was retained. Missing/unverified serving identity is established, not which different model actually served. Increased hold is not actual charge; serving model/usage/provider ID remain unretained.",
                    }
                )
            elif rid == STABILITY_ID:
                failure = stability["new_failure"]
                matching = [
                    send
                    for batch in stability_receipt["batches"]
                    for send in batch["provider_sends"]
                    if send["request_id"] == rid
                ]
                check(
                    "second_incident_receipt_dispatch_and_unknown_metadata",
                    len(matching) == 1
                    and matching[0]["http_send_started"] is True
                    and "http_status" not in matching[0]
                    and "transport_error_category" not in matching[0]
                    and failure["local_request_id"] == rid,
                )
                item.update(
                    {
                        "evidence_refs": [stability_name, stability_receipt_name],
                        "transport_attempt_started": True,
                        "http_status_observed": None,
                        "transport_category_observed": None,
                        "interpretation": "ProviderRequestFailed survived, with transport-attempt-started flag but no HTTP status, precise transport category, returned model or usage. Approximately30seconds between ledger events is not proof of read_timeout or provider receipt; network/status/stream/decoding cause and actual charge remain unproven.",
                    }
                )
            else:
                matching = [
                    send
                    for batch in claim_receipt["batches"]
                    for send in batch["provider_sends"]
                    if send["request_id"] == rid
                ]
                check(
                    "third_incident_allowlisted_connect_timeout",
                    len(matching) == 1
                    and matching[0]["http_send_started"] is True
                    and matching[0]["transport_error_category"]
                    == claim["observed_transport_error_category"]
                    == "connect_timeout"
                    and "http_status" not in matching[0]
                    and claim["input_within_bound"] is True,
                )
                item.update(
                    {
                        "evidence_refs": [claim_name, claim_receipt_name],
                        "transport_attempt_started": True,
                        "http_status_observed": None,
                        "transport_category_observed": "connect_timeout",
                        "input_bytes_plus_guard": claim["input_bytes_plus_guard"],
                        "interpretation": "Sanitized observer classified httpx.ConnectTimeout before an HTTP response/model/output/usage was observed. The pre-transport started flag is not proof of provider receipt; specific DNS/TLS/outage cause, billing and zero charge are not established. The input fit the existing32768 bound; no source/schema failure is established.",
                    }
                )
            incidents.append(item)
        continuations = [
            {key: row[key] for key in ("authorization_id", "active", "revocation_code")}
            for row in db.execute(
                "SELECT authorization_id,active,revocation_code FROM ledger_continuations"
            )
        ]
        quarantine = dict(
            db.execute(
                "SELECT terminal_status,count(*) FROM quarantine_scopes GROUP BY terminal_status"
            ).fetchall()
        )
        check(
            "no_active_continuation_or_quarantine",
            all(row["active"] == 0 for row in continuations) and None not in quarantine,
        )
        after_rows = snapshot(db)
    check("all14fullrow_fingerprints_unchanged_in_readonly_transaction", before_rows == after_rows)
    after_files = file_inventory()
    check("original_DB_and_sidecars_presence_bytes_unchanged", before_files == after_files)
    for alias, info in sources.items():
        check("source_observed_hash_shape:" + alias, len(info["sha256"]) == 64)
    return {
        "schema_version": 1,
        "packet_id": "C5-three-uncertain-readonly-2026-10-15-v1",
        "captured_at_utc": datetime.now(UTC).isoformat(),
        "read_only": True,
        "actual_provider_or_network_calls": 0,
        "credential_files_read": False,
        "app_budget_or_gateway_clients_created": 0,
        "Chroma_clients_created": 0,
        "ledger_mutations": 0,
        "reconciliations_performed": 0,
        "C5_resolved": False,
        "live_authorization_or_unhalt": False,
        "closed_study_IDs_reusable": False,
        "cost_kind": "Sanitized provider-observed usage times pinned local price for settled rows; uncertain amounts are retained reservations, not verified charges or provider account balance.",
        "ledger": {
            "total_reservations": len(reservations),
            "counts": dict(counts),
            "settled_local_estimate_usd": str(settled),
            "all_three_uncertain_hold_usd": str(held),
            "pending_usd": "0",
            "opening_spend_usd": "0",
            "halted": bool(meta["halted"]),
            "ceiling_usd": "4.50",
            "provider_account_reconciled": False,
            "whole_team_cross_laptop_cost_verified": False,
        },
        "unresolved_incidents": incidents,
        "authorization_disposition": {
            "continuations": continuations,
            "quarantine_terminal_counts": quarantine,
        },
        "existing_reconciliation_mechanisms_static_review": {
            "source_ref": "src/agent_app/llm/budget.py",
            "settle": "Accepts known nonnegative USD cost and actual input/output tokens for an existing reserved or uncertain request, even while halted; appends settled event. Cost overrun retains halt, and changed uncertainty invalidates exception scopes. It does not fetch/verify provider evidence itself and was not called here.",
            "release_unsent": "Only an existing reserved row may be released after proven no-send. All three current rows are uncertain, so this is not a release mechanism for them; a connect_timeout flag alone is insufficient zero-charge proof.",
            "halt": "No normal automatic unhalt/refund/reset operation is provided. Settlement is not live authorization; old closed/revoked studies remain closed. No command or code change to clear the halt is proposed.",
            "refund_or_currency": "External evidence must retain rate/currency/refund details. The ledger takes nonnegative USD/tokens; refund/account-wide adjustments are not automatically inferred or obtained by rewriting settled rows or opening a new ledger.",
            "future_action": "Only after independently correlated provider evidence, document the accounting decision and separately review any controlled existing-ledger settlement and later bounded authorization. This packet is evidence collection only.",
        },
        "provider_evidence_acquisition": {
            "safe_next_step": "Account owner obtains sanitized dashboard/provider-support request logs or exports for the three UTC windows and whole-account history; raw credential is unnecessary. No new model call is needed to investigate old charges.",
            "no_endpoint_discovery_in_this_review": True,
            "existing_docs_scope": "The older stability packet checked specific public provider docs. This offline audit makes no current universal claim that a billing/log API does or does not exist.",
            "local_request_hash_not_sent_provider_correlation_ID": True,
            "aggregate_balance_not_per_request_proof": True,
        },
        "ledger_files_before": before_files,
        "ledger_files_after": after_files,
        "ledger_files_unchanged": before_files == after_files,
        "ledger_schema_sha256": before_rows["schema_sha256"],
        "ledger_table_counts": {
            name: table["rows"] for name, table in before_rows["tables"].items()
        },
        "ledger_fullrow_snapshot_sha256": digest(before_rows),
        "ledger_fullrow_snapshot_unchanged": before_rows == after_rows,
        "source_refs": sources,
        "audit_script_sha256": sha(Path(__file__).read_bytes()),
        "checks": checks,
        "checks_passed": sum(row["passed"] for row in checks),
        "checks_total": len(checks),
        "all_checks_passed": all(row["passed"] for row in checks),
        "limitations": [
            "No provider/key/dashboard access, usage endpoint or account-wide invoice was queried.",
            "Historical raw response/serving model/category fields that were never retained cannot be reconstructed from caller hashes, elapsed time or a successful later request.",
            "This audit preserves all old receipts, reservations, holds and halt. Positive read-only custody controls do not resolve C5, grant live permission, measure model quality or establish final-test/RAG success.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=FOLDER / "c5-readonly-audit-v1.json")
    args = parser.parse_args()
    path = args.output.resolve()
    if path.parent != FOLDER.resolve() or not path.name.startswith("c5-readonly-") or path.exists():
        raise ValueError("C5FreshSanitizedOutputRequired")
    report = observe()
    # Public packet must never contain a machine-specific absolute source path.
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if any(marker in encoded for marker in ("/Users/", "Bearer ", "METIS_API_KEY=")):
        raise ValueError("C5PublicOutputRejected")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(encoded)
    print(
        json.dumps(
            {
                "checks_passed": report["checks_passed"],
                "checks_total": report["checks_total"],
                "all_checks_passed": report["all_checks_passed"],
                "packet_sha256": sha(path.read_bytes()),
                "C5_resolved": False,
                "provider_calls": 0,
            }
        )
    )
    return 0 if report["all_checks_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
