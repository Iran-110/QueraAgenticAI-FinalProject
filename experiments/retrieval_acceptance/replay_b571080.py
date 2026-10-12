"""Replay the unmodified restored PR23 source against the current fixed kit.

Candidate imports, constructors and mapper remain literal. Only the Chroma
client is replaced with native-shape fixed collections. The optional namespace
alias is a separately labelled diagnostic, never a candidate readiness result.
No real Chroma, credentials, index, embeddings, or provider are used.
"""

import argparse
import hashlib
import importlib
import json
import socket
import subprocess
import sys
import tempfile
import types
from pathlib import Path

from agent_app.testing.chroma_binding import FixedClient
from agent_app.testing.retrieval_acceptance import run_acceptance

ROOT = Path(__file__).resolve().parents[2]
CANDIDATE = "b571080d93830b88a045ab9374860859e92baec3"
PATHS = (
    "src/agent_app/retrieval/adapter.py",
    "src/agent_app/retrieval/retriever.py",
    "data_scripts/chunking.py",
    "data_scripts/data_loader.py",
    "src/agent_app/contracts.py",
    "src/agent_app/__init__.py",
)
ACTIVE_PROBE = None


def _git(*arguments):
    return subprocess.check_output(["git", "-C", str(ROOT), *arguments])


def _sha(data):
    return hashlib.sha256(data).hexdigest()


class LegacyFixedClient(FixedClient):
    def get_or_create_collection(self, *, name):
        # The old constructor calls this; the double never creates storage.
        return self.get_collection(name=name)


def _client(*, path):
    if ACTIVE_PROBE is None:
        raise ValueError("UnboundFixtureClient")
    return LegacyFixedClient(ACTIVE_PROBE)


def factory(probe):
    global ACTIVE_PROBE
    ACTIVE_PROBE = probe
    try:
        from src.agent_app.retrieval.adapter import ChromaRetrieverAdapter

        return ChromaRetrieverAdapter(base_path="unused-offline-fixture")
    finally:
        ACTIVE_PROBE = None


def _no_network(*args, **kwargs):
    raise RuntimeError("NetworkForbiddenInBaselineReplay")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--namespace-diagnostic", action="store_true")
    options = parser.parse_args(argv)
    # Exclusive output before any candidate execution; historical receipts stay.
    with options.output.open("x", encoding="utf-8") as destination:
        with tempfile.TemporaryDirectory(prefix="rag-pinned-baseline-") as directory:
            staged = Path(directory)
            sources = {}
            for path in PATHS:
                data = _git("show", f"{CANDIDATE}:{path}")
                target = staged / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                sources[path] = {"sha256": _sha(data), "bytes": len(data)}
            sys.dont_write_bytecode = True
            sys.path.insert(0, str(staged))
            module = types.ModuleType("chromadb")
            module.PersistentClient = _client
            sys.modules["chromadb"] = module
            socket.socket.connect = _no_network
            socket.socket.connect_ex = _no_network
            socket.create_connection = _no_network
            if options.namespace_diagnostic:
                sys.modules["src.agent_app.contracts"] = importlib.import_module(
                    "agent_app.contracts"
                )
            receipt = run_acceptance(factory)
            receipt.update(
                candidate_commit=CANDIDATE,
                source_identity=sources,
                core_commit=_git("rev-parse", "HEAD").decode().strip(),
                core_dirty=bool(_git("status", "--porcelain")),
                binding_sha256=_sha(Path(__file__).read_bytes()),
                contract_namespace_alias_applied=options.namespace_diagnostic,
                baseline_interpretation="diagnostic_alias_masks_import_defect"
                if options.namespace_diagnostic
                else "literal_candidate_imports",
                real_chroma_imported=False,
                production_ledger_access=False,
                real_credential_access=False,
            )
            destination.write(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "accepted": receipt["accepted"],
                "checks_passed": receipt["checks_passed"],
                "checks_total": receipt["checks_total"],
                "contract_namespace_alias_applied": options.namespace_diagnostic,
                "quality_claim": False,
            }
        )
    )
    # A reproduced baseline rejection is a successful experiment, not readiness.
    return 0 if not receipt["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
