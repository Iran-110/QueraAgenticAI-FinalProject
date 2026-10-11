"""Reproduce one candidate RAG/core contract failure, entirely offline.

Run with the project's already installed Python dependencies:
    uv run python /absolute/path/to/probe_rag_core.py --repo "$PWD" --output /new/receipt.json

This imports the core from a temporary archive of its pinned commit. It compiles
only the reviewed candidate class definition, skips its Chroma constructor, and
injects two in-memory collection doubles. It does not test Chroma, embeddings,
index relevance, corpus quality, provider output, or final held-out evaluation.
No repository checkout, dependencies, credentials, or production ledger change.
"""

import argparse
import ast
import contextlib
import hashlib
import io
import json
import subprocess
import sys
import tarfile
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

sys.dont_write_bytecode = True

MAIN = "37ce74aeec462343ea091b05078116a2f6728781"
RAG = "c0d450a57769b4513b6b99f2e75ed506c483363d"
RAG_PATH = "src/agent_app/retrieval/retriever.py"
RAG_SOURCE_SHA256 = "ac2c184852c2175e63475fb20ffb6680f02ef2e36fd957fcdcf7cdbf51ea1575"


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args])


def digest(data):
    return hashlib.sha256(data).hexdigest()


def probe(repo):
    if git(repo, "rev-parse", MAIN).decode().strip() != MAIN:
        raise RuntimeError("PinnedCoreCommitMissing")
    if git(repo, "rev-parse", RAG).decode().strip() != RAG:
        raise RuntimeError("PinnedCandidateCommitMissing")
    source = git(repo, "show", f"{RAG}:{RAG_PATH}")
    if digest(source) != RAG_SOURCE_SHA256:
        raise RuntimeError("PinnedCandidateSourceMismatch")
    parsed = ast.parse(source.decode("utf-8-sig"))
    candidate = next(
        node
        for node in parsed.body
        if isinstance(node, ast.ClassDef) and node.name == "StreamlitRetriever"
    )
    if candidate.decorator_list or not all(
        isinstance(item, ast.FunctionDef) for item in candidate.body
    ):
        raise RuntimeError("ReviewedClassShapeChanged")
    # No module imports, __main__, Chroma constructor, ingestion, or source
    # snippets are executed. Only the pinned repository class was reviewed.
    namespace = {}
    exec(
        compile(ast.Module(body=[candidate], type_ignores=[]), "<reviewed-rag-class>", "exec"),
        namespace,
    )

    archive_bytes = git(repo, "archive", MAIN, "src/agent_app")
    with TemporaryDirectory(prefix="rag-core-offline-audit-") as directory:
        archive_root = Path(directory).resolve()
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:") as archive:
            archive.extractall(archive_root, filter="data")
        sys.path.insert(0, str(archive_root / "src"))
        import agent_app.orchestration.engine as engine_module
        from agent_app.contracts import CaseState
        from agent_app.demo import _answer
        from agent_app.orchestration import SupportEngine
        from agent_app.testing.fakes import FakeReasoner

        if not Path(engine_module.__file__).resolve().is_relative_to(archive_root):
            raise RuntimeError("CoreImportNotPinnedArchive")

        class CollectionDouble:
            def __init__(self):
                self.calls = []

            def query(self, **kwargs):
                self.calls.append(kwargs)
                return {
                    "ids": [["doc-1"]],
                    "documents": [["Authored offline excerpt."]],
                    "metadatas": [
                        [
                            {
                                "type": "markdown",
                                "source_url": "https://docs.streamlit.io/example",
                            }
                        ]
                    ],
                    "distances": [[0.1]],
                }

        retriever = namespace["StreamlitRetriever"].__new__(namespace["StreamlitRetriever"])
        retriever.docs_collection = CollectionDouble()
        retriever.issues_collection = CollectionDouble()
        reasoner = FakeReasoner([_answer("doc-1")])
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            result = SupportEngine(
                retriever, reasoner, snapshot_id="fixture-snapshot", top_k=1
            ).run(
                CaseState(case_id="rag-audit"),
                "Authored widget complaint.",
                run_id="offline-rag-contract-probe",
            )
        collections = {}
        for name in ("docs", "issues"):
            calls = getattr(retriever, f"{name}_collection").calls
            collections[name] = [
                {
                    "query_input_types": [type(value).__name__ for value in call["query_texts"]],
                    "request_top_k": call["query_texts"][0].top_k,
                    "n_results": call["n_results"],
                    "query_count": len(call["query_texts"][0].queries),
                }
                for call in calls
            ]
        if result.status != "error" or result.error_code != "RetrievalResultInvalid":
            raise RuntimeError("ExpectedContractFailureNotObserved")
        if reasoner.inputs or result.model_attempts != 0 or result.retrieval_rounds != 1:
            raise RuntimeError("UnexpectedPortAttemptCount")
        if "chromadb" in sys.modules:
            raise RuntimeError("ChromaImportNotAllowed")
        core_sources = {}
        for path in sorted((archive_root / "src/agent_app").rglob("*.py")):
            core_sources[str(path.relative_to(archive_root))] = digest(path.read_bytes())
        return {
            "schema_version": 1,
            "executed_at_utc": datetime.now(UTC).isoformat(),
            "main_commit": MAIN,
            "rag_commit": RAG,
            "candidate_source": RAG_PATH,
            "candidate_source_sha256": digest(source),
            "core_archive_sha256": digest(archive_bytes),
            "core_sources_sha256": core_sources,
            "script_sha256": digest(Path(__file__).read_bytes()),
            "mode": "offline_candidate_contract_probe",
            "candidate_execution": "Reviewed class AST only; constructor skipped",
            "backend": "Two injected in-memory collection doubles; not Chroma",
            "collections": collections,
            "result": result.model_dump(mode="json"),
            "model_calls": len(reasoner.inputs),
            "raw_request_logged": "fixture-snapshot" in stdout.getvalue(),
            "chroma_imported": False,
            "persistent_client_constructed": False,
            "real_index_created_or_queried": False,
            "embedding_or_model_downloads": 0,
            "provider_calls": 0,
            "production_ledger_access": False,
            "real_credential_access": False,
            "actual_cost_usd": "0",
            "quality_claim": False,
            "limitations": [
                "A collection double accepts the RetrievalRequest object so the outer result failure is observable.",
                "Actual Chroma may reject that input earlier; it was neither imported nor exercised.",
                "Per-collection n_results is the candidate requested value, not a measured actual result count.",
                "No retrieval quality, embedding behavior, corpus exclusion, or model quality was measured.",
            ],
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path, default=Path(__file__).with_name("rag-core-search-audit-v1.json")
    )
    options = parser.parse_args()
    receipt = probe(options.repo)
    # Preserve existing receipts; repeat runs must choose a fresh output path.
    with options.output.open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(
        json.dumps(
            {
                "receipt": str(options.output.resolve()),
                "status": receipt["result"]["status"],
                "error_code": receipt["result"]["error_code"],
                "model_calls": receipt["model_calls"],
                "actual_cost_usd": receipt["actual_cost_usd"],
            }
        )
    )


if __name__ == "__main__":
    main()
