"""Build and inspect a registered native docs index; no provider or ledger access."""

import argparse
import contextlib
import hashlib
import io
import json
import subprocess
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from agent_app.contracts import RetrievalRequest
from agent_app.retrieval.adapter import ChromaRetrieverAdapter, RetrievalAdapterRejected
from agent_app.retrieval.offline_index import (
    OfflineIndexRejected,
    build_index,
    open_verified_index,
)
from agent_app.retrieval.pilot_corpus import (
    COLLECTION_NAMES,
    MANIFEST_NAME,
    build_pilot_corpus,
    embedding_sha256,
    lexical_embedding,
)
from agent_app.retrieval.retriever import StreamlitRetriever
from agent_app.testing.http_pilot_runtime import offline_network

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / "experiments/dev_rag_coverage_v1"
PROTOCOL_PATH = PACKET / "protocol-v1.json"
PROTOCOL_SHA = "81baa4820a0a3c0653aba744e0e1ab367454b2528ca06ab989d94b8ace054483"
OLD_PROTOCOL_PATH = ROOT / "experiments/dev_three_baseline/index-protocol-v1.json"
OLD_PROTOCOL_SHA = "dbaffa940605201afa85a4e0a05b060b9bb9c96ea0aa297f2a92a2aec47a6b49"
OLD_SPLIT = ROOT / "data/evaluation/dev-three-v1/split-manifest.json"
OLD_ALLOWLIST = ROOT / "experiments/corpus/pilot-allowlist.json"
NEW_SPLIT = PACKET / "split-manifest.json"
NEW_ALLOWLIST = PACKET / "allowlist.json"
SEED = ROOT / "streamlit-data-for-dev-test"
DIAGNOSTIC = "DevRagCoverageAcceptanceRejected"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def registered_inputs(protocol_path=None):
    """Validate frozen protocols and unchanged inputs before creating any index."""
    path = PROTOCOL_PATH if protocol_path is None else Path(protocol_path)
    raw = path.read_bytes()
    if sha(raw) != PROTOCOL_SHA or sha(OLD_PROTOCOL_PATH.read_bytes()) != OLD_PROTOCOL_SHA:
        raise ValueError(DIAGNOSTIC)
    protocol = json.loads(raw)
    if protocol["protocol_id"] != "dev-real-rag-coverage-v1":
        raise ValueError(DIAGNOSTIC)
    for relative, digest in protocol["unchanged_input_sha256"].items():
        target = ROOT / relative
        if not target.resolve().is_relative_to(ROOT) or sha(target.read_bytes()) != digest:
            raise ValueError(DIAGNOSTIC)
    split = json.loads(NEW_SPLIT.read_bytes())
    previous = json.loads(OLD_SPLIT.read_bytes())
    if (
        split["status"] != "draft_not_frozen"
        or split["selected"] != previous["selected"]
        or split["fixture_paths"] != previous["fixture_paths"]
        or split["families"] != previous["families"]
        or split["exposure_reserved_issue_ids"] != previous["exposure_reserved_issue_ids"]
        or len(set(split["exposure_reserved_issue_ids"])) != 46
        or not set(protocol["exclusion"]["required_family_ids"])
        <= set(split["exposure_reserved_issue_ids"])
    ):
        raise ValueError(DIAGNOSTIC)
    historical = json.loads(OLD_PROTOCOL_PATH.read_bytes())
    paths = [
        path,
        OLD_PROTOCOL_PATH,
        NEW_SPLIT,
        NEW_ALLOWLIST,
        *[ROOT / relative for relative in protocol["unchanged_input_sha256"]],
        *sorted((ROOT / "src/agent_app").rglob("*.py")),
        SEED / "manifest.json",
        *[
            SEED / item["path"]
            for item in json.loads((SEED / "manifest.json").read_bytes())["files"]
        ],
        Path(__file__),
    ]
    pins = {str(target.resolve()): sha(target.read_bytes()) for target in paths}
    return protocol, historical, pins


@contextlib.contextmanager
def native_queries():
    """Observe the real collection method, including complete returned source rows."""
    from chromadb.api.models.Collection import Collection

    original, calls = Collection.query, []

    def observed(collection, *args, **kwargs):
        record = {
            "collection": collection.name,
            "query_embedding_sha256": [
                embedding_sha256(vector) for vector in kwargs["query_embeddings"]
            ],
            "n_results": kwargs["n_results"],
            "where": deepcopy(kwargs.get("where")),
        }
        calls.append(record)
        result = original(collection, *args, **kwargs)
        record["result"] = {
            key: deepcopy(result[key]) for key in ("ids", "documents", "metadatas", "distances")
        }
        return result

    with patch.object(Collection, "query", observed):
        yield calls


def verify(index_root, protocol_path=None):
    protocol, historical, input_pins = registered_inputs(protocol_path)
    index_root = Path(index_root).resolve()
    if index_root.exists():
        raise ValueError(DIAGNOSTIC)
    checks, searches = {}, []

    def check(name, condition):
        checks[name] = bool(condition)
        if not condition:
            raise ValueError(DIAGNOSTIC)

    with offline_network(), native_queries() as native:
        old = build_pilot_corpus(SEED, OLD_SPLIT, OLD_ALLOWLIST)
        new = build_pilot_corpus(SEED, NEW_SPLIT, NEW_ALLOWLIST)
        check(
            "historical_snapshot_unchanged", old.snapshot_id == historical["expected_snapshot_id"]
        )
        check(
            "historical_membership",
            len(old.manifest["corpus"]["sources"]) == 14
            and len(old.manifest["corpus"]["chunks"]) == 30,
        )
        corpus = new.manifest["corpus"]
        check("new_membership", len(corpus["sources"]) == 18 and len(corpus["chunks"]) == 36)
        old_ids = {source["source_id"] for source in old.manifest["corpus"]["sources"]}
        new_ids = {source["source_id"] for source in corpus["sources"]}
        check(
            "four_explicit_additions",
            new_ids - old_ids == set(protocol["new_profile"]["additional_sources"])
            and old_ids <= new_ids,
        )
        new_chunks = {chunk["chunk_id"]: chunk for chunk in corpus["chunks"]}
        check(
            "all_historical_chunks_retained_exactly",
            all(
                new_chunks.get(chunk["chunk_id"]) == chunk
                for chunk in old.manifest["corpus"]["chunks"]
            ),
        )
        check(
            "all_conservative_reservations",
            corpus["exclusions"]["reserved_issue_ids"]
            == sorted(json.loads(OLD_SPLIT.read_bytes())["exposure_reserved_issue_ids"]),
        )
        check(
            "all_index_material_docs",
            all(chunk["metadata"]["source_type"] == "doc" for chunk in corpus["chunks"])
            and corpus["exclusions"]["indexed_issue_count"]
            == corpus["exclusions"]["indexed_comment_count"]
            == 0,
        )
        raw_records = [
            json.loads(line)
            for line in (SEED / "sources/docstrings_scope_candidates.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        source_proofs = []
        for source_id, pin in protocol["new_profile"]["additional_sources"].items():
            records = [record for record in raw_records if record["source_id"] == source_id]
            check(source_id + ":unique_raw_record", len(records) == 1)
            record = records[0]
            chunks = [
                chunk for chunk in corpus["chunks"] if chunk["metadata"]["source_id"] == source_id
            ]
            text = record["text"]
            check(
                source_id + ":raw_provenance",
                sha(text.encode("utf-8")) == pin["text_sha256"] == record["text_sha256"]
                and len(text) == pin["characters"]
                and all(
                    record[key] == pin[key]
                    for key in ("json_pointer", "pinned_source_url", "source_url")
                ),
            )
            check(
                source_id + ":complete_ordered_spans",
                "".join(chunk["document"] for chunk in chunks) == text
                and all(
                    chunk["document"] == text[chunk["span"]["start"] : chunk["span"]["end"]]
                    for chunk in chunks
                ),
            )
            check(
                source_id + ":separate_version_identity",
                all(
                    chunk["metadata"]["version"] == record["version"]
                    and chunk["metadata"]["applicable_versions"]
                    == json.dumps([record["version"]], separators=(",", ":"))
                    for chunk in chunks
                ),
            )
            source_proofs.append(
                {
                    "source_id": source_id,
                    **pin,
                    "version": record["version"],
                    "chunks": [
                        {
                            "chunk_id": chunk["chunk_id"],
                            "span": chunk["span"],
                            "text_sha256": chunk["text_sha256"],
                        }
                        for chunk in chunks
                    ],
                }
            )
        index_root.mkdir(parents=True, exist_ok=False)
        paths = {
            "historical_14_sources": index_root / "historical-14",
            "new_18_sources": index_root / "coverage-18",
            "independent_new_rebuild": index_root / "coverage-18-rebuild",
        }
        clients, indexes, index_counts = {}, {}, {}
        for label, path in paths.items():
            built = build_index(old if label == "historical_14_sources" else new, path)
            client, opened = open_verified_index(path)
            check(label + ":native_storage_verified", built == opened)
            clients[label] = client
            indexes[label] = {
                "path": str(path),
                "snapshot_id": opened,
                "manifest_sha256": sha((path / MANIFEST_NAME).read_bytes()),
            }
            index_counts[label] = {
                "source_count": len(client.manifest["corpus"]["sources"]),
                "chunk_count": len(client.manifest["corpus"]["chunks"]),
            }
        check(
            "independent_new_builds_equal",
            indexes["new_18_sources"]["snapshot_id"]
            == indexes["independent_new_rebuild"]["snapshot_id"]
            and (paths["new_18_sources"] / MANIFEST_NAME).read_bytes()
            == (paths["independent_new_rebuild"] / MANIFEST_NAME).read_bytes(),
        )
        check(
            "historical_canonical_manifest_unchanged",
            sha(
                json.dumps(
                    old.manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ).encode()
            )
            == historical["expected_canonical_manifest_sha256"],
        )

        def search(label, condition, queries, filters=None):
            client = clients[label]
            adapter = ChromaRetrieverAdapter(
                "",
                snapshot_id=client.snapshot_id,
                core_retriever=StreamlitRetriever(
                    "", snapshot_id=client.snapshot_id, client=client
                ),
            )
            request = RetrievalRequest(
                snapshot_id=client.snapshot_id,
                queries=tuple(queries),
                top_k=5,
                filters=filters or {},
            )
            offset = len(native)
            bundle = adapter.search(request)
            check(
                label + ":" + condition + ":unique_global_cap",
                len(bundle.hits) <= request.top_k
                and len({hit.chunk_id for hit in bundle.hits}) == len(bundle.hits),
            )
            expected = [
                {
                    "collection": collection,
                    "query_embedding_sha256": [embedding_sha256(lexical_embedding(query))],
                    "n_results": 5,
                    "where": StreamlitRetriever._where(request.filters),
                }
                for query in request.queries
                for collection in COLLECTION_NAMES
            ]
            check(
                label + ":" + condition + ":native_io",
                [{key: call[key] for key in expected[0]} for call in native[offset:]] == expected,
            )
            rows = {chunk["chunk_id"]: chunk for chunk in client.manifest["corpus"]["chunks"]}
            check(
                label + ":" + condition + ":full_material",
                bundle.snapshot_id == client.snapshot_id
                and bundle.queries_used == request.queries
                and all(
                    hit.chunk_id in rows
                    and hit.excerpt == rows[hit.chunk_id]["document"].strip()
                    and all(
                        getattr(hit, field) == rows[hit.chunk_id]["metadata"][field]
                        for field in (
                            "source_id",
                            "source_type",
                            "source_commit",
                            "source_span",
                            "source_url",
                        )
                    )
                    and hit.applicable_versions
                    == tuple(json.loads(rows[hit.chunk_id]["metadata"]["applicable_versions"]))
                    for hit in bundle.hits
                ),
            )
            searches.append(
                {
                    "arm": label,
                    "condition": condition,
                    "control_filters_not_model_inputs": bool(filters),
                    "request": request.model_dump(mode="json"),
                    "bundle": bundle.model_dump(mode="json"),
                }
            )
            return bundle

        for label in ("historical_14_sources", "new_18_sources"):
            for case in historical["cases"]:
                search(label, case["case_id"], case["queries"])
        for source_id in protocol["new_profile"]["additional_sources"]:
            version = source_id.split(":")[1]
            bundle = search(
                "new_18_sources",
                "direct:" + source_id,
                ("API documentation",),
                {"source_id": source_id, "version": version},
            )
            expected_ids = {
                chunk["chunk_id"]
                for chunk in corpus["chunks"]
                if chunk["metadata"]["source_id"] == source_id
            }
            check(
                source_id + ":native_filtered_coverage",
                {hit.chunk_id for hit in bundle.hits} == expected_ids,
            )
            bundle = search(
                "new_18_sources",
                "wrong-version:" + source_id,
                ("API documentation",),
                {"source_id": source_id, "version": "9.99.0"},
            )
            check(source_id + ":wrong_version_empty", not bundle.hits)
        absent = search(
            "new_18_sources",
            "wrong-source",
            ("API documentation",),
            {"source_id": "docs:not-allowlisted"},
        )
        check("wrong_source_empty", not absent.hits)
        adapter = ChromaRetrieverAdapter(
            "",
            snapshot_id=new.snapshot_id,
            core_retriever=StreamlitRetriever(
                "", snapshot_id=new.snapshot_id, client=clients["new_18_sources"]
            ),
        )
        offset = len(native)
        try:
            adapter.search(RetrievalRequest(snapshot_id="wrong-snapshot", queries=("widget",)))
        except RetrievalAdapterRejected:
            check("wrong_snapshot_before_native_io", len(native) == offset)
        else:
            check("wrong_snapshot_before_native_io", False)

        second = clients["independent_new_rebuild"]
        second.verify()
        chunk = corpus["chunks"][0]
        second._client.get_collection(name="streamlit_docs", embedding_function=None).update(
            ids=[chunk["chunk_id"]],
            documents=[chunk["document"] + " tampered"],
            embeddings=[lexical_embedding(chunk["document"])],
        )
        try:
            second.verify()
        except OfflineIndexRejected:
            check("same_snapshot_content_tamper_rejected", True)
        else:
            check("same_snapshot_content_tamper_rejected", False)
        collection = second._client.get_collection(name="streamlit_docs", embedding_function=None)
        collection.update(
            ids=[chunk["chunk_id"]],
            documents=[chunk["document"]],
            embeddings=[lexical_embedding(chunk["document"])],
        )
        second.verify()
        for field, value in (("source_id", "docs:not-approved"), ("version", "9.99.0")):
            collection.update(
                ids=[chunk["chunk_id"]], metadatas=[{**chunk["metadata"], field: value}]
            )
            try:
                second.verify()
            except OfflineIndexRejected:
                check("same_snapshot_" + field + "_tamper_rejected", True)
            else:
                check("same_snapshot_" + field + "_tamper_rejected", False)
            collection.update(ids=[chunk["chunk_id"]], metadatas=[chunk["metadata"]])
            # Chroma merges metadata, so the injected field is explicitly removed
            # when the original unversioned row did not contain it.
            if field not in chunk["metadata"]:
                collection.update(ids=[chunk["chunk_id"]], metadatas=[{field: None}])
            second.verify()
        manifest_path = paths["independent_new_rebuild"] / MANIFEST_NAME
        manifest_path.write_bytes(manifest_path.read_bytes() + b" ")
        try:
            second.verify()
        except OfflineIndexRejected:
            check("same_snapshot_manifest_bytes_tamper_rejected", True)
        else:
            check("same_snapshot_manifest_bytes_tamper_rejected", False)
        clients["new_18_sources"].verify()
        check(
            "authoritative_new_index_untouched",
            sha((paths["new_18_sources"] / MANIFEST_NAME).read_bytes())
            == indexes["new_18_sources"]["manifest_sha256"],
        )
        check(
            "all_registered_inputs_unchanged",
            all(sha(Path(path).read_bytes()) == digest for path, digest in input_pins.items()),
        )
    return {
        "schema_version": 1,
        "accepted": True,
        "registered_protocol_id": protocol["protocol_id"],
        "registered_protocol_sha256": PROTOCOL_SHA,
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "source_unchanged_during_run": True,
        "actual_index_tested": True,
        "embedding": "lexical_hash_v1",
        "actual_provider_requests": 0,
        "actual_api_cost_usd": "0",
        "held_out_test": False,
        "quality_claim": False,
        "human_reviewed": False,
        "checks": checks,
        "checks_total": len(checks),
        "checks_passed": sum(checks.values()),
        "indexes": indexes,
        "index_counts": index_counts,
        "source_proofs": source_proofs,
        "exclusions": corpus["exclusions"],
        "sources": corpus["sources"],
        "native_collection_queries": native,
        "searches": searches,
        "independent_rebuild_after_tamper": "invalid_by_design_do_not_use_for_model",
        "limits": [
            "Direct source/version filters verify corpus coverage only; unfiltered case searches may miss relevant material.",
            "Three exposed development families; lexical index operations do not establish semantic retrieval quality or held-out success.",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args(argv)
    if options.output.exists():
        print(json.dumps({"accepted": False, "diagnostic": "ReceiptAlreadyExists"}))
        return 1
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            receipt = verify(options.index_root)
    except Exception:
        receipt = {"accepted": False, "diagnostic": DIAGNOSTIC}
    try:
        options.output.parent.mkdir(parents=True, exist_ok=True)
        with options.output.open("x", encoding="utf-8") as output:
            json.dump(receipt, output, ensure_ascii=False, indent=2)
            output.write("\n")
    except FileExistsError:
        print(json.dumps({"accepted": False, "diagnostic": "ReceiptAlreadyExists"}))
        return 1
    print(
        json.dumps(
            {
                key: receipt[key]
                for key in ("accepted", "checks_passed", "checks_total", "diagnostic")
                if key in receipt
            }
        )
    )
    return 0 if receipt["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
