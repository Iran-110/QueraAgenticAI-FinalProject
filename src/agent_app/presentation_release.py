"""Additive release source watch over the unchanged finite presentation runtime.

The original funded protocol/21-file receipt remain unchanged. This explicitly
selected sidecar additionally watches project runtime Python and named public
inputs. It does not attest installed wheels/native libraries, authenticate code,
settle old uncertainty or authorize any request. Every base guard still runs.
"""

import argparse
import asyncio
import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping
from contextlib import asynccontextmanager
from pathlib import Path
from threading import RLock
from uuid import uuid4

import httpx
from fastapi import FastAPI

from agent_app.llm.config import METIS_CHAT_URL
from agent_app.orchestration.ports import ReasoningStopped

ROOT = Path(__file__).resolve().parents[2]
PROFILE = "presentation_release_watch_v1"
LIFESPAN_POLICY = "close_ingress_then_drain_runs_without_owner_lock_v1"
TREES = ("src/agent_app", "app_pages")
PUBLIC_FILES = (
    "app.py",
    "pyproject.toml",
    "uv.lock",
    "config/core-delivery-grounded-prefilter-v2.json",
    "config/user-gap-support-dev-v1.json",
)
_ERROR = "PresentationReleaseWatchRejected"


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(_ERROR)
        result[key] = value
    return result


def _regular(path, *, maximum=10_000_000):
    info = path.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or info.st_size > maximum
        or not path.resolve().is_relative_to(ROOT)
    ):
        raise ValueError(_ERROR)


def source_inventory():
    """Closed filesystem selection: no dotenv, data, test fixture or runtime DB."""
    try:
        selected = set(PUBLIC_FILES)

        def unreadable(error):
            raise error

        for relative in TREES:
            folder = ROOT / relative
            if folder.is_symlink() or not folder.is_dir():
                raise ValueError
            for current, directories, files in os.walk(
                folder, followlinks=False, onerror=unreadable
            ):
                directory = Path(current)
                if any((directory / name).is_symlink() for name in directories):
                    raise ValueError
                for name in files:
                    path = directory / name
                    if path.is_symlink():
                        raise ValueError
                    if path.suffix == ".py":
                        selected.add(path.relative_to(ROOT).as_posix())
        if "src/agent_app/presentation_release.py" not in selected:
            raise ValueError
        result = {}
        for relative in sorted(selected):
            path = ROOT / relative
            # Check every parent before resolving/reading a selected public file.
            if any(parent.is_symlink() for parent in (path, *path.parents) if parent != ROOT):
                raise ValueError
            _regular(path)
            result[relative] = _sha(path.read_bytes())
        return result
    except Exception:
        raise ValueError(_ERROR) from None


def _protocol(path):
    # Import only after the inventory helper itself has selected explicit public
    # paths; this import never loads a key or starts a live adapter.
    from agent_app.presentation_runtime import read_protocol

    value, digest, _ = read_protocol(path)
    return value, digest


def write_watch(protocol_path, destination):
    """Write a NEW sidecar for explicit operator review; never replace or re-pin."""
    try:
        destination = Path(destination)
        if (
            destination.name != "release-watch.json"
            or destination.exists()
            or destination.is_symlink()
            or destination.resolve().is_relative_to(ROOT)
        ):
            raise ValueError
        protocol, digest = _protocol(protocol_path)
        material = {
            "schema_version": 1,
            "profile_id": PROFILE,
            "base_profile_id": "presentation_scoped_v1",
            "protocol_sha256": digest,
            "scope_id": protocol["scope_id"],
            "selection": {"python_trees": list(TREES), "public_files": list(PUBLIC_FILES)},
            "files": source_inventory(),
            "installed_dependencies_attested": False,
            "native_libraries_attested": False,
            "financial_authorization": False,
            "quality_claim": False,
            "application_lifespan_policy": LIFESPAN_POLICY,
        }
        raw = (json.dumps(material, sort_keys=True, indent=2) + "\n").encode()
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(
            destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
        return _sha(raw)
    except Exception:
        raise ValueError(_ERROR) from None


def validate_watch(protocol_path, watch_path, *, expected_sha256):
    """Compare the explicit review hash, base protocol and complete selected set."""
    try:
        if (
            type(expected_sha256) is not str
            or re.fullmatch(r"[a-f0-9]{64}", expected_sha256) is None
        ):
            raise ValueError
        path = Path(watch_path)
        if (
            path.name != "release-watch.json"
            or path.is_symlink()
            or path.resolve().is_relative_to(ROOT)
        ):
            raise ValueError
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 2_000_000:
            raise ValueError
        raw = path.read_bytes()
        if _sha(raw) != expected_sha256:
            raise ValueError
        observed = json.loads(raw, object_pairs_hook=_unique)
        protocol, digest = _protocol(protocol_path)
        expected = {
            "schema_version": 1,
            "profile_id": PROFILE,
            "base_profile_id": "presentation_scoped_v1",
            "protocol_sha256": digest,
            "scope_id": protocol["scope_id"],
            "selection": {"python_trees": list(TREES), "public_files": list(PUBLIC_FILES)},
            "files": source_inventory(),
            "installed_dependencies_attested": False,
            "native_libraries_attested": False,
            "financial_authorization": False,
            "quality_claim": False,
            "application_lifespan_policy": LIFESPAN_POLICY,
        }
        # Exact canonical JSON comparison distinguishes bool from integer values.
        if json.dumps(observed, sort_keys=True) != json.dumps(expected, sort_keys=True):
            raise ValueError
        return protocol, expected
    except Exception:
        raise ValueError(_ERROR) from None


class ReleaseWatch:
    """Repeated bounded observations, separate from old funded configuration."""

    def __init__(self, protocol_path, watch_path, *, expected_sha256):
        self.protocol_path = Path(protocol_path)
        self.watch_path = Path(watch_path)
        self.expected_sha256 = expected_sha256
        protocol, self.binding = validate_watch(
            self.protocol_path, self.watch_path, expected_sha256=expected_sha256
        )
        self.audit_path = Path(protocol["receipt_dir"]).parent / "release-watch-audit.jsonl"
        self._protected_paths = (
            self.protocol_path,
            self.watch_path,
            Path(protocol["ledger_path"]),
            Path(protocol["tracker_path"]),
            ROOT / ".env",
            *(path for path in Path(protocol["index"]["path"]).rglob("*") if path.is_file()),
        )
        self._lock = RLock()
        self._observations = []
        self.check("startup")

    def event(self, *, stage, accepted, delegate_started=False, dispatch_id=None):
        record = {
            "schema_version": 1,
            "profile_id": PROFILE,
            "watch_sha256": self.expected_sha256,
            "protocol_sha256": self.binding["protocol_sha256"],
            "stage": stage,
            "accepted": accepted,
            "delegate_started": delegate_started,
            "dispatch_id": dispatch_id,
        }
        with self._lock:
            if self.audit_path.resolve().is_relative_to(ROOT) or any(
                self.audit_path.resolve() == path.resolve()
                or (self.audit_path.exists() and path.exists() and self.audit_path.samefile(path))
                for path in self._protected_paths
            ):
                raise ValueError(_ERROR)
            self.audit_path.parent.mkdir(parents=True, exist_ok=True)
            if self.audit_path.exists():
                info = self.audit_path.lstat()
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise ValueError(_ERROR)
            descriptor = os.open(
                self.audit_path, os.O_CREAT | os.O_APPEND | os.O_WRONLY | os.O_NOFOLLOW, 0o600
            )
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "a") as stream:
                stream.write(json.dumps(record, sort_keys=True) + "\n")
            self._observations.append(dict(record))

    def check(self, stage, *, dispatch_id=None):
        try:
            validate_watch(
                self.protocol_path, self.watch_path, expected_sha256=self.expected_sha256
            )
        except Exception:
            self.event(stage=stage, accepted=False, dispatch_id=dispatch_id)
            raise ValueError(_ERROR) from None
        self.event(stage=stage, accepted=True, dispatch_id=dispatch_id)

    @property
    def observations(self):
        with self._lock:
            return [dict(record) for record in self._observations]


class WatchedTransport(httpx.BaseTransport):
    """An additional last check; all original gateway/ledger guards still apply."""

    def __init__(self, underlying, watch):
        self.underlying, self.watch = underlying, watch

    def handle_request(self, request):
        dispatch_id = uuid4().hex
        try:
            if request.method != "POST" or str(request.url) != METIS_CHAT_URL:
                raise ValueError
            self.watch.check("dispatch", dispatch_id=dispatch_id)
            self.watch.event(
                stage="delegate_started",
                accepted=True,
                delegate_started=True,
                dispatch_id=dispatch_id,
            )
        except Exception:
            # A durable reservation already exists at this layer. The unchanged
            # gateway conservatively records uncertainty and stops all scopes;
            # this wrapper does not invent a zero-cost release/reconciliation.
            raise ReasoningStopped("ProviderRequestFailed") from None
        return self.underlying.handle_request(request)

    def close(self):
        self.underlying.close()


def _drain_runtime(runtime):
    """Application-owned shutdown order; the old direct close method is unchanged."""
    with runtime._lock:
        runtime._closed = True
        runs = tuple(runtime._active)
    # A planner may own run.lock while record() needs runtime._lock. Waiting
    # under the owner lock would invert that order. Stop new allocations above,
    # then let existing records finish while waiting outside the owner lock.
    failed = False
    for run in runs:
        try:
            run.close()
        except Exception:
            failed = True
    if failed:
        raise ValueError("PresentationReleaseCleanupFailed")


def configured_app(
    protocol_path,
    values: Mapping[str, str],
    *,
    watch_path,
    expected_watch_sha256,
    transport_factory=None,
) -> FastAPI:
    """Explicit additive bootstrap; model/config/IDs/scopes and payloads stay exact."""
    watch = ReleaseWatch(protocol_path, watch_path, expected_sha256=expected_watch_sha256)
    from agent_app.presentation_runtime import configured_app as base_app

    def transport():
        watch.check("allocation")
        underlying = (
            transport_factory() if transport_factory is not None else httpx.HTTPTransport(retries=0)
        )
        if not isinstance(underlying, httpx.BaseTransport):
            raise ValueError(_ERROR)
        return WatchedTransport(underlying, watch)

    app = base_app(protocol_path, values, transport_factory=transport)
    app.state.presentation_release_watch = watch
    app.state.presentation_release_binding = {
        **watch.binding,
        "watch_sha256": expected_watch_sha256,
    }
    base_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        async with base_lifespan(application):
            try:
                yield
            finally:
                await asyncio.to_thread(_drain_runtime, app.state.presentation_runtime)

    app.router.lifespan_context = lifespan
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    capture = sub.add_parser("capture")
    capture.add_argument("--protocol", type=Path, required=True)
    capture.add_argument("--destination", type=Path, required=True)
    for command in ("check", "serve"):
        child = sub.add_parser(command)
        child.add_argument("--protocol", type=Path, required=True)
        child.add_argument("--watch", type=Path, required=True)
        child.add_argument("--expected-sha256", required=True)
        if command == "serve":
            child.add_argument("--dotenv", type=Path, required=True)
            child.add_argument("--reviewer-token-file", type=Path, required=True)
            child.add_argument("--port", type=int, default=8001)
    arguments = parser.parse_args()
    try:
        if arguments.command == "capture":
            print(
                json.dumps({"watch_sha256": write_watch(arguments.protocol, arguments.destination)})
            )
        elif arguments.command == "check":
            _, binding = validate_watch(
                arguments.protocol, arguments.watch, expected_sha256=arguments.expected_sha256
            )
            print(
                json.dumps(
                    {
                        "watch_sha256": arguments.expected_sha256,
                        "files": len(binding["files"]),
                        "quality_claim": False,
                    }
                )
            )
        else:
            # Public watch and original scope checks precede lazy credential
            # construction, and base_app repeats its own complete guard chain.
            protocol, _ = validate_watch(
                arguments.protocol, arguments.watch, expected_sha256=arguments.expected_sha256
            )
            from agent_app.llm.budget import BudgetLedger
            from agent_app.presentation_session import PrivateSettings

            status = BudgetLedger(protocol["ledger_path"]).quarantine_scope_status(
                protocol["scope_id"]
            )
            if not status.active:
                raise ValueError
            private = PrivateSettings(
                arguments.protocol,
                protocol,
                dotenv_path=arguments.dotenv,
                token_file=arguments.reviewer_token_file,
            )
            app = configured_app(
                arguments.protocol,
                private,
                watch_path=arguments.watch,
                expected_watch_sha256=arguments.expected_sha256,
            )
            import uvicorn

            uvicorn.run(app, host="127.0.0.1", port=arguments.port)
        return 0
    except Exception:
        print(_ERROR)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
