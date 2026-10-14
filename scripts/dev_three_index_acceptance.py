"""Verify a separately registered three-dev docs index epoch without paid calls.

The historical PR35 protocol and split remain immutable. Registered queries and
authored HTTP policy checks exercise wiring, never semantic RAG/model quality.
"""

import argparse
import contextlib
import hashlib
import io
import json
import re
import subprocess
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from agent_app.contracts import ProposalHandoff, RetrievalRequest
from agent_app.offline_backend import configured_app
from agent_app.orchestration.handoff import validate_handoff
from agent_app.orchestration.intake import STREAMLIT_VERSION_QUESTION
from agent_app.retrieval.adapter import ChromaRetrieverAdapter, RetrievalAdapterRejected
from agent_app.retrieval.offline_index import open_verified_index
from agent_app.retrieval.pilot_corpus import (
    COLLECTION_NAMES,
    MANIFEST_NAME,
    canonical_json,
    embedding_sha256,
    lexical_embedding,
)
from agent_app.retrieval.retriever import StreamlitRetriever
from agent_app.testing.http_pilot_runtime import offline_network
from agent_app.ui_client import BackendClient, BackendError

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "experiments/dev_three_baseline/index-protocol-v1.json"
SPLIT_PATH = "data/evaluation/dev-three-v1/split-manifest.json"
HISTORICAL_SPLIT = "data/evaluation/split-manifest.json"
HISTORICAL_PROTOCOL = "experiments/retrieval_acceptance/pr35/protocol-v1.json"
ALLOWLIST = "experiments/corpus/pilot-allowlist.json"
CASE_IDS = ("dev-case-a", "dev-case-b", "dev-case-c")
PACKET_PATHS = {
    "data/evaluation/dev-three-v1/evidence-v1.json",
    "data/evaluation/dev-three-v1/scenario-review-v1.json",
    "data/evaluation/dev-three-v1/exposure-review-v1.json",
    "data/evaluation/dev-three-v1/user-gap-vocabulary-v1.json",
}
TOKEN = "synthetic-three-dev-index-epoch-review-credential"
DIAGNOSTIC = "DevThreeIndexAcceptanceRejected"


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _path(value):
    if not isinstance(value, str) or "\\" in value:
        raise ValueError(DIAGNOSTIC)
    path = ROOT / value
    if path.resolve().is_relative_to(ROOT.resolve()) is False or not path.is_file():
        raise ValueError(DIAGNOSTIC)
    return path


def registered_protocol(path=PROTOCOL_PATH):
    """Resolve reviewed byte pins before opening or querying native storage."""
    protocol = json.loads(path.read_bytes())
    if (
        protocol.get("protocol_id") != "dev-three-docs-index-epoch-v1"
        or protocol.get("quality_claim") is not False
        or protocol.get("held_out_test") is not False
        or type(protocol.get("real_provider_requests")) is not int
        or protocol["real_provider_requests"] != 0
        or type(protocol.get("expected_sources")) is not int
        or protocol["expected_sources"] != 14
        or type(protocol.get("expected_chunks")) is not int
        or protocol["expected_chunks"] != 30
        or not isinstance(protocol.get("expected_snapshot_id"), str)
        or re.fullmatch(r"docs-pilot-[0-9a-f]{64}", protocol["expected_snapshot_id"]) is None
        or set(protocol.get("file_sha256", {}))
        != {SPLIT_PATH, HISTORICAL_SPLIT, HISTORICAL_PROTOCOL, ALLOWLIST}
        or set(protocol.get("packet_sha256", {})) != PACKET_PATHS
        or [case.get("case_id") for case in protocol.get("cases", [])] != list(CASE_IDS)
    ):
        raise ValueError(DIAGNOSTIC)
    for relative, digest in protocol["file_sha256"].items():
        if _sha(_path(relative)) != digest:
            raise ValueError(DIAGNOSTIC)
    for relative, digest in protocol["packet_sha256"].items():
        if _sha(_path(relative)) != digest:
            raise ValueError(DIAGNOSTIC)
    manifest = json.loads(_path(SPLIT_PATH).read_bytes())
    if (
        manifest["manifest_id"] != "split-dev-three-docs-epoch-v1"
        or manifest["status"] != "draft_not_frozen"
        or manifest["selected"] != {"dev": list(CASE_IDS), "test": []}
        or not {2379, 8129, 8180, 9455, 9770, 12629, 12782}
        <= set(manifest["exposure_reserved_issue_ids"])
    ):
        raise ValueError(DIAGNOSTIC)
    fixtures = []
    for case in protocol["cases"]:
        queries = case.get("queries")
        if (
            not isinstance(queries, list)
            or len(queries) != 2
            or any(not isinstance(query, str) or not query.strip() for query in queries)
            or case.get("http_expected_first_decision") not in {"ask", "escalate"}
            or case.get("fixture_path") not in manifest["fixture_paths"]
            or _sha(_path(case["fixture_path"])) != case.get("fixture_sha256")
        ):
            raise ValueError(DIAGNOSTIC)
        fixture = json.loads(_path(case["fixture_path"]).read_bytes())
        if fixture["case"]["case_id"] != case["case_id"]:
            raise ValueError(DIAGNOSTIC)
        fixtures.append(fixture)
    return protocol, fixtures, _sha(path)


def release_identity(protocol_path):
    protocol, _, _ = registered_protocol(protocol_path)
    paths = sorted((ROOT / "src/agent_app").rglob("*.py")) + [
        Path(__file__).resolve(),
        protocol_path,
        *(_path(path) for path in protocol["file_sha256"]),
        *(_path(path) for path in protocol["packet_sha256"]),
        *(_path(case["fixture_path"]) for case in protocol["cases"]),
    ]
    return {
        "git_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "git_dirty": bool(
            subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()
        ),
        "source_sha256": {path.relative_to(ROOT).as_posix(): _sha(path) for path in paths},
    }


@contextlib.contextmanager
def observe_native_collections():
    from chromadb.api.models.Collection import Collection

    original, calls = Collection.query, []

    def observed(collection, *args, **kwargs):
        calls.append(
            {
                "collection": collection.name,
                "query_embedding_sha256": [
                    embedding_sha256(vector) for vector in kwargs["query_embeddings"]
                ],
                "n_results": kwargs["n_results"],
                "where": deepcopy(kwargs.get("where")),
            }
        )
        return original(collection, *args, **kwargs)

    with patch.object(Collection, "query", observed):
        yield calls


def verify(index, rebuild_index, protocol_path=PROTOCOL_PATH):
    protocol, fixtures, protocol_sha = registered_protocol(protocol_path)
    checks, searches, handoffs = {}, [], []

    def check(name, condition):
        checks[name] = bool(condition)
        if not condition:
            raise ValueError(DIAGNOSTIC)

    with offline_network(), observe_native_collections() as native, TemporaryDirectory() as temp:
        check("distinct_build_paths", index.resolve() != rebuild_index.resolve())
        client, snapshot = open_verified_index(index)
        rebuilt, second = open_verified_index(rebuild_index)
        check("registered_epoch_snapshot", snapshot == second == protocol["expected_snapshot_id"])
        corpus = client.manifest["corpus"]
        check("independent_manifest_equal", client.manifest == rebuilt.manifest)
        check(
            "independent_manifest_bytes_equal",
            (index / MANIFEST_NAME).read_bytes() == (rebuild_index / MANIFEST_NAME).read_bytes(),
        )
        check(
            "split_and_allowlist_byte_pins",
            corpus["source_pins"]["split_manifest_sha256"] == protocol["file_sha256"][SPLIT_PATH]
            and corpus["source_pins"]["allowlist_sha256"] == protocol["file_sha256"][ALLOWLIST],
        )
        check("registered_corpus_source_pins", corpus["source_pins"] == protocol["source_pins"])
        check(
            "limited_docs_only_membership",
            len(corpus["sources"]) == 14
            and len(corpus["chunks"]) == 30
            and all(chunk["metadata"]["source_type"] == "doc" for chunk in corpus["chunks"])
            and corpus["exclusions"]["indexed_issue_count"] == 0
            and corpus["exclusions"]["indexed_comment_count"] == 0,
        )
        check(
            "conservative_families_reserved",
            {2379, 8129, 8180, 9455, 9770, 12629, 12782}
            <= set(corpus["exclusions"]["reserved_issue_ids"])
            and corpus["exclusions"]["split_manifest_id"] == "split-dev-three-docs-epoch-v1",
        )
        check(
            "draft_scope_retained",
            corpus["exclusions"]["split_status"] == "draft_not_frozen"
            and corpus["exclusions"]["family_review_complete"] is False,
        )
        chunks = {chunk["chunk_id"]: chunk for chunk in corpus["chunks"]}

        def material(bundle):
            return all(
                hit.chunk_id in chunks
                and hit.excerpt == chunks[hit.chunk_id]["document"].strip()
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

        adapter = ChromaRetrieverAdapter(
            "",
            snapshot_id=snapshot,
            core_retriever=StreamlitRetriever("", snapshot_id=snapshot, client=client),
        )
        conditions = [(case["case_id"], tuple(case["queries"]), {}) for case in protocol["cases"]]
        conditions += [
            (
                "version-" + version,
                ("button icon image", "session state rerun"),
                {"version": version},
            )
            for version in ("1.49.0", "1.50.0", "1.64.0", "1.31.0", "1.39.0")
        ]
        for label, queries, filters in conditions:
            request = RetrievalRequest(
                snapshot_id=snapshot, queries=queries, filters=filters, top_k=5
            )
            before = request.model_dump(mode="json")
            offset = len(native)
            bundle = adapter.search(request)
            check(
                label + ":native_collection_io",
                native[offset:]
                == [
                    {
                        "collection": name,
                        "query_embedding_sha256": [embedding_sha256(lexical_embedding(query))],
                        "n_results": 5,
                        "where": filters or None,
                    }
                    for query in queries
                    for name in COLLECTION_NAMES
                ],
            )
            check(
                label + ":request_snapshot_queries",
                bundle.snapshot_id == snapshot
                and bundle.queries_used == queries
                and request.model_dump(mode="json") == before,
            )
            check(
                label + ":unique_cap",
                len(bundle.hits) <= 5
                and len({hit.chunk_id for hit in bundle.hits}) == len(bundle.hits),
            )
            check(label + ":approved_exact_material", material(bundle))
            absent = filters.get("version") in {"1.31.0", "1.39.0"}
            check(
                label + ":version_scope",
                not bundle.hits
                if absent
                else bool(bundle.hits)
                and all(
                    not filters or hit.applicable_versions == (filters["version"],)
                    for hit in bundle.hits
                ),
            )
            searches.append(
                {"condition": label, "request": before, "bundle": bundle.model_dump(mode="json")}
            )
        offset = len(native)
        try:
            adapter.search(RetrievalRequest(snapshot_id="wrong-epoch", queries=("widget",)))
        except RetrievalAdapterRejected:
            check("wrong_snapshot_no_native_io", len(native) == offset)
        else:
            check("wrong_snapshot_no_native_io", False)

        config = {
            "AGENT_TRACKER_DB": str(Path(temp) / "cases.sqlite3"),
            "AGENT_REVIEWER_TOKEN": TOKEN,
            "AGENT_PILOT_INDEX": str(index),
            "AGENT_PILOT_SNAPSHOT": snapshot,
            "AGENT_PILOT_REASONING": "grounded_fake_gateway",
        }
        views = {}
        with TestClient(configured_app(config)) as http:
            backend = BackendClient(http, reviewer_token=TOKEN)
            for registered, fixture in zip(protocol["cases"], fixtures, strict=True):
                case_id = registered["case_id"]
                visible = fixture["turns"][0]["visible"]
                event = {
                    key: visible[key]
                    for key in (
                        "message",
                        "reported_facts",
                        "unknowns",
                        "checks_performed",
                        "context_changed",
                    )
                    if key in visible
                }
                event.update(turn_id="epoch-first-" + case_id, expected_revision=0)
                view = backend.send_event(case_id, event)
                handoff = validate_handoff(
                    ProposalHandoff.model_validate(view["pending"]["review_handoff"])
                )
                check(
                    case_id + ":bound_current_index",
                    handoff.evidence.snapshot_id == snapshot
                    and bool(handoff.evidence.hits)
                    and material(handoff.evidence)
                    and handoff.case.case_revision == 1
                    and handoff.grounded_request is not None,
                )
                check(
                    case_id + ":authored_policy",
                    handoff.analysis.decision == registered["http_expected_first_decision"],
                )
                check(
                    case_id + ":proposal_only",
                    view["actions"] == [] and view["quality_claim"] is False,
                )
                if handoff.analysis.decision == "ask":
                    check(
                        case_id + ":canonical_version_question",
                        handoff.analysis.next_question == STREAMLIT_VERSION_QUESTION.question,
                    )
                for other_id, previous in views.items():
                    check(case_id + ":isolates:" + other_id, backend.get_case(other_id) == previous)
                views[case_id] = view
                handoffs.append(handoff.model_dump(mode="json"))
            enum_id = CASE_IDS[2]
            stale = backend.prepare_review(enum_id, views[enum_id]["pending"], "approve")
            corrected = backend.send_event(
                enum_id,
                {
                    "message": "Correction: the affected environment is Streamlit 1.31.1.",
                    "turn_id": "epoch-enum-version-correction",
                    "expected_revision": 1,
                    "reported_facts": [{"name": "streamlit_version", "value": "1.31.1"}],
                    "context_changed": False,
                },
            )
            current = validate_handoff(
                ProposalHandoff.model_validate(corrected["pending"]["review_handoff"])
            )
            check(
                "enum:correction_current_fact",
                current.case.case_revision == 2
                and any(
                    f.name == "streamlit_version" and f.value == "1.31.1" and f.status == "active"
                    for f in current.case.facts
                )
                and not any(
                    f.name == "streamlit_version" and f.value == "1.31.0" and f.status == "active"
                    for f in current.case.facts
                ),
            )
            retained_names = {
                fact.name
                for fact in current.case.facts
                if fact.status == "active" and fact.provenance_kind == "user"
            }
            check(
                "enum:partial_correction_keeps_code_and_environment",
                {"reported_reproduction_code", "python_version", "browser"} <= retained_names,
            )
            before = backend.get_case(enum_id)
            try:
                backend.send_review(stale)
            except BackendError as error:
                check(
                    "enum:stale_approval_rejected",
                    error.code in {"StaleRevision", "PendingProposalMismatch"},
                )
            else:
                check("enum:stale_approval_rejected", False)
            check("enum:stale_approval_no_mutation", backend.get_case(enum_id) == before)
            operation = backend.prepare_review(enum_id, corrected["pending"], "approve")
            approved = backend.send_review(operation)
            check("enum:approved_once", len(approved["actions"]) == 1)
        with TestClient(configured_app(config)) as http:
            backend = BackendClient(http, reviewer_token=TOKEN)
            retried = backend.send_review(operation)
            check(
                "enum:recreation_retry_once",
                len(retried["actions"]) == 1
                and retried["review"] == {**approved["review"], "replayed": True},
            )
            for case_id in CASE_IDS[:2]:
                check("restart:isolates:" + case_id, backend.get_case(case_id) == views[case_id])
        client.verify()
        rebuilt.verify()
    receipt = {
        "protocol_id": protocol["protocol_id"],
        "registered_protocol_sha256": protocol_sha,
        "accepted": True,
        "snapshot_id": snapshot,
        "source_pins": corpus["source_pins"],
        "exclusions": corpus["exclusions"],
        "config": corpus["config"],
        "checks": checks,
        "searches": searches,
        "native_collection_queries": native,
        "public_handoffs": handoffs,
        "actual_index_tested": True,
        "reasoning_label": "grounded_fake_gateway",
        "real_provider_requests": 0,
        "actual_api_cost_usd": "0",
        "quality_claim": False,
        "held_out_test": False,
        "limitations": [
            "14-source docs-only corpus and local lexical vectors, no semantic ranking gold.",
            "1.31.0 and 1.39.0 exact API sources are absent; fixed-fixture coverage is separate.",
            "Three exposed dev cases, no final split or final corpus approval.",
            "Authored ask/escalate gateway; no real-model decision-quality score.",
            "ASGI backend recreation in one interpreter, no OS process/browser claim.",
        ],
    }
    check("no_review_credential_in_receipt", TOKEN not in canonical_json(receipt))
    receipt.update(checks_passed=sum(checks.values()), checks_total=len(checks))
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--rebuild-index", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, default=PROTOCOL_PATH)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args(argv)
    if options.output.exists():
        print(json.dumps({"accepted": False, "diagnostic": "ReceiptAlreadyExists"}))
        return 1
    try:
        before = release_identity(options.protocol)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            receipt = verify(options.index, options.rebuild_index, options.protocol)
        after = release_identity(options.protocol)
        if before != after:
            raise ValueError(DIAGNOSTIC)
        receipt.update(release_before=before, release_after=after, source_unchanged_during_run=True)
    except Exception:
        receipt = {"accepted": False, "diagnostic": DIAGNOSTIC, "quality_claim": False}
    try:
        with options.output.open("x", encoding="utf-8") as output:
            json.dump(receipt, output, ensure_ascii=False, indent=2)
            output.write("\n")
    except (FileExistsError, OSError):
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
