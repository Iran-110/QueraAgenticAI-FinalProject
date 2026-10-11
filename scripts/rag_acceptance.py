"""Run fixed-evidence adapter conformance; no production RAG quality claim.

Default execution imports only the offline reference fixture adapter. An optional
module:callable binding must be reviewed to inject the fixture read backend into
its real adapter mapping, without index creation, embeddings or provider calls.
Candidate AST checks are static only and do not establish runtime readiness.
"""

import argparse
import ast
import contextlib
import hashlib
import importlib
import io
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_FACTORY_PATTERN = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*\Z", re.ASCII)


class AcceptanceStartupRejected(ValueError):
    """Only runner-owned error codes are exported; exception text is discarded."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _candidate_preflight(path: Path) -> dict:
    if not path.is_file():
        raise AcceptanceStartupRejected("CandidateMissing")
    try:
        content = path.read_bytes()
    except OSError:
        raise AcceptanceStartupRejected("CandidateReadFailed") from None
    if not content.strip():
        raise AcceptanceStartupRejected("CandidateEmpty")
    try:
        tree = ast.parse(content.decode("utf-8-sig"))
    except (SyntaxError, UnicodeError):
        raise AcceptanceStartupRejected("CandidateSyntaxInvalid") from None
    found = any(
        isinstance(node, ast.ClassDef)
        and node.name == "ChromaRetrieverAdapter"
        and any(
            isinstance(method, ast.FunctionDef) and method.name == "search" for method in node.body
        )
        for node in tree.body
    )
    if not found:
        raise AcceptanceStartupRejected("CandidateInterfaceMissing")
    return {
        "status": "passed",
        "mode": "static_ast_only",
        "candidate_source_sha256": _sha(content),
        "candidate_imported_by_preflight": False,
        "runtime_readiness_proved": False,
    }


def _resolve_factory(specification: str | None):
    if specification is None:
        from agent_app.testing.retrieval_acceptance import fixture_factory

        return fixture_factory
    if not _FACTORY_PATTERN.fullmatch(specification):
        raise AcceptanceStartupRejected("AdapterFactoryInvalid")
    module_name, callable_name = specification.split(":")
    try:
        module = importlib.import_module(module_name)
        factory = getattr(module, callable_name)
    except Exception:
        raise AcceptanceStartupRejected("AdapterFactoryUnavailable") from None
    if not callable(factory):
        raise AcceptanceStartupRejected("AdapterFactoryInvalid")
    return factory


def _release_identity() -> dict:
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
        dirty = bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
            ).strip()
        )
        paths = sorted((ROOT / "src/agent_app").rglob("*.py")) + [Path(__file__).resolve()]
        sources = {path.relative_to(ROOT).as_posix(): _sha(path.read_bytes()) for path in paths}
    except Exception:
        raise AcceptanceStartupRejected("ReleaseIdentityUnavailable") from None
    return {"git_commit": commit, "git_dirty": dirty, "source_sha256": sources}


def _summary(receipt: dict) -> dict:
    return {
        "protocol": "retrieval-core-acceptance-v1",
        "accepted": receipt["accepted"],
        "mode": receipt["mode"],
        "checks_passed": receipt.get("checks_passed", 0),
        "checks_total": receipt.get("checks_total", 0),
        "error_code": receipt.get("error_code"),
        "quality_claim": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, required=True, help="Fresh JSON receipt; never overwritten."
    )
    parser.add_argument(
        "--factory", help="Reviewed offline binding as module:callable; defaults to fixture port."
    )
    parser.add_argument(
        "--check-candidate",
        type=Path,
        help="Optional static candidate file check; never imports it.",
    )
    options = parser.parse_args(argv)
    try:
        destination = options.output.open("x", encoding="utf-8")
    except FileExistsError:
        print(
            json.dumps(
                _summary(
                    {"accepted": False, "mode": "not_run", "error_code": "ReceiptAlreadyExists"}
                )
            )
        )
        return 1
    except OSError:
        print(
            json.dumps(
                _summary({"accepted": False, "mode": "not_run", "error_code": "ReceiptUnavailable"})
            )
        )
        return 1

    receipt = {
        "schema_version": 1,
        "protocol": "retrieval-core-acceptance-v1",
        "accepted": False,
        "mode": "not_run",
        "quality_claim": False,
        "production_index_or_embedding_tested": False,
        "real_model_tested": False,
        "actual_rag_accepted": False,
        "factory_override_requested": options.factory is not None,
        "candidate_preflight": None,
    }
    stdout, stderr = io.StringIO(), io.StringIO()
    with destination:
        try:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                receipt["release_before"] = _release_identity()
                if options.check_candidate is not None:
                    receipt["candidate_preflight"] = _candidate_preflight(options.check_candidate)
                factory = _resolve_factory(options.factory)
                from agent_app.testing.retrieval_acceptance import run_acceptance

                receipt.update(run_acceptance(factory))
                receipt["release_after"] = _release_identity()
                unchanged = (
                    receipt["release_before"]["source_sha256"]
                    == receipt["release_after"]["source_sha256"]
                )
                receipt["source_unchanged_during_run"] = unchanged
                if not unchanged:
                    receipt["accepted"] = False
                    receipt["error_code"] = "SourceChangedDuringRun"
                elif not receipt["accepted"]:
                    receipt["error_code"] = "AdapterAcceptanceFailed"
        except AcceptanceStartupRejected as error:
            receipt["accepted"] = False
            receipt["error_code"] = error.code
        except Exception:
            receipt["accepted"] = False
            receipt["error_code"] = "AcceptanceStartupFailed"
        receipt["adapter_stdout_captured"] = bool(stdout.getvalue())
        receipt["adapter_stderr_captured"] = bool(stderr.getvalue())
        destination.write(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(_summary(receipt)))
    return 0 if receipt["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
