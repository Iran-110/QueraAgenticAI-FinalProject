"""Replay operational acceptance on two existing, independently built docs indexes.

Expected decisions follow the registered authored pilot policy, not relevance gold.
No index is built here; no environment, provider key or production ledger is read.
"""

import argparse
import contextlib
import hashlib
import io
import json
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from agent_app.contracts import ProposalHandoff, RetrievalRequest
from agent_app.offline_backend import configured_app
from agent_app.orchestration.handoff import validate_handoff
from agent_app.orchestration.intake import STREAMLIT_VERSION_QUESTION
from agent_app.retrieval.adapter import ChromaRetrieverAdapter, RetrievalAdapterRejected
from agent_app.retrieval.offline_index import open_verified_index
from agent_app.retrieval.pilot_corpus import MANIFEST_NAME, canonical_json
from agent_app.retrieval.retriever import StreamlitRetriever
from agent_app.testing.http_pilot_runtime import offline_network
from agent_app.tracker.sqlite_tracker import SQLiteCaseTracker
from agent_app.ui_client import BackendClient, BackendError

ROOT = Path(__file__).resolve().parents[2]
TOKEN = "synthetic-existing-index-review-credential-for-offline-replay"


def release_identity():
    paths = sorted((ROOT / "src/agent_app").rglob("*.py")) + [Path(__file__).resolve()]
    return {
        "git_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "git_dirty": bool(
            subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()
        ),
        "source_sha256": {
            path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in paths
        },
    }


def verify(index: Path, rebuild_index: Path) -> dict:
    checks, searches, handoffs = {}, [], []

    def check(name, condition):
        checks[name] = bool(condition)
        if not condition:
            raise ValueError("PilotIndexAcceptanceRejected")

    with offline_network(), TemporaryDirectory(prefix="rag-existing-index-replay-") as temporary:
        check("distinct_build_paths", index.resolve() != rebuild_index.resolve())
        client, snapshot = open_verified_index(index)
        rebuilt, second_snapshot = open_verified_index(rebuild_index)
        manifest = client.manifest
        check("rebuild_snapshot_identical", snapshot == second_snapshot)
        check("rebuild_canonical_manifest_identical", manifest == rebuilt.manifest)
        manifest_hash = hashlib.sha256(canonical_json(manifest).encode()).hexdigest()
        check(
            "rebuild_manifest_bytes_identical",
            (index / MANIFEST_NAME).read_bytes() == (rebuild_index / MANIFEST_NAME).read_bytes(),
        )
        corpus = manifest["corpus"]
        check("registered_docs_only", len(corpus["sources"]) == 14 and len(corpus["chunks"]) == 30)
        check(
            "no_issue_comment_membership",
            corpus["exclusions"]["indexed_issue_count"] == 0
            and corpus["exclusions"]["indexed_comment_count"] == 0
            and all(chunk["metadata"]["source_type"] == "doc" for chunk in corpus["chunks"]),
        )
        chunks = {chunk["chunk_id"]: chunk for chunk in corpus["chunks"]}

        def material(bundle):
            return all(
                hit.excerpt == chunks[hit.chunk_id]["document"].strip()
                and all(
                    getattr(hit, field) == chunks[hit.chunk_id]["metadata"][field]
                    for field in (
                        "source_id",
                        "source_type",
                        "source_url",
                        "source_commit",
                        "source_span",
                    )
                )
                and hit.applicable_versions
                == tuple(json.loads(chunks[hit.chunk_id]["metadata"]["applicable_versions"]))
                for hit in bundle.hits
            )

        retriever = StreamlitRetriever("", snapshot_id=snapshot, client=client)
        native_search, backend_queries = retriever.search, []

        def observed_search(*args, **kwargs):
            backend_queries.append(
                {
                    "query": kwargs["query"],
                    "filters": kwargs["filters"],
                    "n_results": kwargs["n_results"],
                }
            )
            return native_search(*args, **kwargs)

        retriever.search = observed_search
        adapter = ChromaRetrieverAdapter("", snapshot_id=snapshot, core_retriever=retriever)
        for label, filters in [("multiquery", {})] + [
            (version, {"version": version}) for version in ("1.49.0", "1.50.0", "1.64.0", "9.99.0")
        ]:
            request = RetrievalRequest(
                snapshot_id=snapshot,
                queries=("session state widget rerun", "button click reset"),
                top_k=5,
                filters=filters,
            )
            before = request.model_dump(mode="json")
            prior_queries = len(backend_queries)
            bundle = adapter.search(request)
            check(
                f"{label}:both_native_queries",
                backend_queries[prior_queries:]
                == [
                    {"query": query, "filters": dict(request.filters), "n_results": request.top_k}
                    for query in request.queries
                ],
            )
            check(
                f"{label}:snapshot_queries_request",
                bundle.snapshot_id == snapshot
                and bundle.queries_used == request.queries
                and request.model_dump(mode="json") == before,
            )
            check(
                f"{label}:unique_global_cap",
                len(bundle.hits) <= 5
                and len({hit.chunk_id for hit in bundle.hits}) == len(bundle.hits),
            )
            check(f"{label}:exact_material", material(bundle))
            check(
                f"{label}:native_filter",
                bool(bundle.hits)
                if not filters
                else (
                    not bundle.hits
                    if label == "9.99.0"
                    else bool(bundle.hits)
                    and all(hit.applicable_versions == (label,) for hit in bundle.hits)
                ),
            )
            searches.append(
                {"id": label, "request": before, "bundle": bundle.model_dump(mode="json")}
            )
        prior_queries = len(backend_queries)
        try:
            adapter.search(RetrievalRequest(snapshot_id="wrong-snapshot", queries=("widget",)))
        except RetrievalAdapterRejected as error:
            check("wrong_snapshot_rejected", str(error) == "RetrievalSnapshotMismatch")
        else:
            check("wrong_snapshot_rejected", False)
        check("wrong_snapshot_before_backend_query", len(backend_queries) == prior_queries)

        config = {
            "AGENT_TRACKER_DB": str(Path(temporary) / "cases.sqlite3"),
            "AGENT_REVIEWER_TOKEN": TOKEN,
            "AGENT_PILOT_INDEX": str(index),
            "AGENT_PILOT_SNAPSHOT": snapshot,
            "AGENT_PILOT_REASONING": "grounded_fake_gateway",
        }
        case_id = "rag-index-review-pilot"

        def handoff(view, decision, revision):
            value = validate_handoff(
                ProposalHandoff.model_validate(view["pending"]["review_handoff"])
            )
            check(
                f"turn{revision}:current_grounded_context",
                value.grounded_request is not None
                and value.grounded_request.case == value.case
                and value.grounded_request.evidence == value.evidence
                and value.grounded_request.user_message == value.user_message
                and value.case.case_revision == revision
                and view["case_revision"] == revision,
            )
            check(f"turn{revision}:authored_policy", value.analysis.decision == decision)
            check(
                f"turn{revision}:existing_index_material",
                value.evidence.snapshot_id == snapshot
                and bool(value.evidence.hits)
                and material(value.evidence),
            )
            check(
                f"turn{revision}:truthful_mode",
                view["reasoning_label"] == "grounded_fake_gateway"
                and view["retrieval_label"] == "local_chroma_hash"
                and view["quality_claim"] is False,
            )
            handoffs.append(value.model_dump(mode="json"))
            return value

        first_event = {
            "message": "My widget resets on rerun; the installed version is unknown.",
            "turn_id": "index-original",
            "expected_revision": 0,
        }
        with TestClient(configured_app(config)) as http:
            backend = BackendClient(http, reviewer_token=TOKEN)
            initial = backend.send_event(case_id, first_event)
            first = handoff(initial, "ask", 1)
            check(
                "canonical_answerable_question",
                first.analysis.next_question == STREAMLIT_VERSION_QUESTION.question
                and initial["actions"] == [],
            )
            approved = backend.send_review(
                backend.prepare_review(case_id, initial["pending"], "approve")
            )
            check("question_approval_one_action", len(approved["actions"]) == 1)
            reply_event = {
                "message": "1.50.0",
                "turn_id": "index-version",
                "expected_revision": 1,
                "reply_to_proposal_id": first.proposal_id,
            }
            known = backend.send_event(case_id, reply_event)
            previous = handoff(known, "escalate", 2)
            check(
                "short_reply_bound_to_problem",
                first_event["message"] in previous.user_message
                and previous.user_message.endswith("1.50.0")
                and bool(previous.analysis.evidence_links),
            )
            operation = backend.prepare_review(case_id, known["pending"], "approve")
            stale = backend.prepare_review(case_id, known["pending"], "approve")
            committed = backend.send_review(operation)
            original_body = operation.body_json
            check("second_approval_two_actions", len(committed["actions"]) == 2)
            corrected = backend.send_event(
                case_id,
                {
                    "message": "Correction: the installed version is 1.49.0.",
                    "turn_id": "index-correction",
                    "expected_revision": 2,
                    "reported_facts": [{"name": "streamlit_version", "value": "1.49.0"}],
                    "context_changed": True,
                },
            )
            current = handoff(corrected, "escalate", 3)
            check(
                "correction_current_fact_and_fresh_proposal",
                current.proposal_id != previous.proposal_id
                and any(
                    f.name == "streamlit_version" and f.value == "1.49.0" and f.status == "active"
                    for f in current.case.facts
                )
                and not any(
                    f.name == "streamlit_version" and f.value == "1.50.0" and f.status == "active"
                    for f in current.case.facts
                ),
            )
            before_stale = backend.get_case(case_id)
            try:
                backend.send_review(stale)
            except BackendError as error:
                check(
                    "stale_fresh_approval_rejected",
                    error.code in {"StaleRevision", "PendingProposalMismatch"},
                )
            else:
                check("stale_fresh_approval_rejected", False)
            check("stale_approval_no_mutation", before_stale == backend.get_case(case_id))
        with TestClient(configured_app(config)) as http:
            backend = BackendClient(http, reviewer_token=TOKEN)
            replay = backend.send_review(operation)
            check(
                "review_retry_after_backend_recreation",
                operation.body_json == original_body
                and replay["review"] == {**committed["review"], "replayed": True}
                and replay["pending"] == corrected["pending"]
                and replay["case_revision"] == 3
                and len(replay["actions"]) == 2,
            )
            for event in (first_event, reply_event):
                duplicate = backend.send_event(case_id, event)
                check(
                    f"{event['turn_id']}:exact_event_retry",
                    duplicate["intake"]["replayed"] is True
                    and duplicate["pending"] == corrected["pending"]
                    and len(duplicate["actions"]) == 2,
                )
            withdrawal = backend.send_event(
                case_id,
                {
                    "message": "I cannot confirm the installed version now.",
                    "turn_id": "index-withdrawal",
                    "expected_revision": 3,
                    "reported_facts": [{"name": "streamlit_version", "value": None}],
                    "unknowns": ["streamlit_version"],
                    "context_changed": True,
                },
            )
            last = handoff(withdrawal, "ask", 4)
            check(
                "withdrawal_removes_active_version",
                last.analysis.next_question == STREAMLIT_VERSION_QUESTION.question
                and not any(
                    f.name == "streamlit_version" and f.status == "active" for f in last.case.facts
                ),
            )
            check("withdrawal_no_automatic_action", len(withdrawal["actions"]) == 2)
        check(
            "durable_two_local_actions",
            len(SQLiteCaseTracker(config["AGENT_TRACKER_DB"]).comments(case_id)) == 2,
        )
        client.verify()
        rebuilt.verify()
    receipt = {
        "protocol": "existing-docs-pilot-index-acceptance-v1",
        "accepted": True,
        "snapshot_id": snapshot,
        "canonical_manifest_sha256": manifest_hash,
        "source_pins": corpus["source_pins"],
        "exclusions": corpus["exclusions"],
        "config": corpus["config"],
        "checks": checks,
        "checks_passed": sum(checks.values()),
        "checks_total": len(checks),
        "searches": searches,
        "native_backend_queries": backend_queries,
        "public_handoffs": handoffs,
        "actual_index_tested": True,
        "reasoning_label": "grounded_fake_gateway",
        "actual_provider_requests": 0,
        "actual_api_cost_usd": "0",
        "simulated_gateway_cost": {"collected": False, "actual_charge": False},
        "quality_claim": False,
        "held_out_test": False,
        "limitations": [
            "Local lexical vectors; no semantic relevance or ranking gold.",
            "Authored ask/escalate policy; no model decision-quality score.",
            "ASGI backend recreation in one interpreter; no browser or process-restart claim.",
            "Docs-only allowlist, draft split; final family exclusion remains open.",
        ],
    }
    check("no_review_credential_in_receipt", TOKEN not in canonical_json(receipt))
    receipt["checks_passed"], receipt["checks_total"] = sum(checks.values()), len(checks)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--rebuild-index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args(argv)
    if options.output.exists():
        print(json.dumps({"accepted": False, "diagnostic": "ReceiptAlreadyExists"}))
        return 1
    receipt = {
        "accepted": False,
        "diagnostic": "PilotIndexAcceptanceRejected",
        "quality_claim": False,
    }
    try:
        before = release_identity()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            receipt = verify(options.index, options.rebuild_index)
        after = release_identity()
        if (
            before["source_sha256"] != after["source_sha256"]
            or before["git_commit"] != after["git_commit"]
        ):
            raise ValueError
        receipt.update(release_before=before, release_after=after, source_unchanged_during_run=True)
    except Exception:
        receipt = {
            "accepted": False,
            "diagnostic": "PilotIndexAcceptanceRejected",
            "quality_claim": False,
        }
    try:
        with options.output.open("x", encoding="utf-8") as destination:
            json.dump(receipt, destination, ensure_ascii=False, sort_keys=True, indent=2)
            destination.write("\n")
    except FileExistsError:
        print(json.dumps({"accepted": False, "diagnostic": "ReceiptAlreadyExists"}))
        return 1
    except OSError:
        print(json.dumps({"accepted": False, "diagnostic": "ReceiptUnavailable"}))
        return 1
    print(
        json.dumps(
            {
                key: receipt[key]
                for key in ("accepted", "checks_passed", "checks_total")
                if key in receipt
            }
        )
    )
    return 0 if receipt["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
