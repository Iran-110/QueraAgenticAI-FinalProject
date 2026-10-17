"""Additive release guard tests on a temporary source tree/index/SQLite ledger.

No frozen project source, funded meeting scope, credential or held-out payload is
modified/read. The old 21-file boundary remains exact and is measured separately.
"""

import json
import shutil
import time
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import httpx
import pytest
from fastapi.testclient import TestClient
from test_budget_quarantine_scope import multiple_holds as multiple_holds
from test_core_delivery_http import authored_response
from test_presentation_runtime import AUTH, KEY, ROOT, TOKEN, body, sha
from test_presentation_runtime import final_v3 as final_v3
from test_presentation_runtime import registered as registered

from agent_app import presentation_release as release
from agent_app import presentation_runtime as runtime
from agent_app.testing.http_pilot_runtime import offline_network


@pytest.fixture
def watched(tmp_path, registered, monkeypatch):
    ledger, protocol_path, protocol, values = registered
    copy = tmp_path / "source-copy"
    selected = {
        *runtime.BOUND_SOURCE_FILES,
        *release.PUBLIC_FILES,
        "src/agent_app/presentation_release.py",
        "src/agent_app/retrieval/retriever.py",
        "src/agent_app/tracker/sqlite_tracker.py",
        "src/agent_app/contracts.py",
        "experiments/final_corpus_v1/build-receipt-v3.json",
    }
    for relative in selected:
        destination = copy / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)
    monkeypatch.setattr(runtime, "ROOT", copy)
    monkeypatch.setattr(release, "ROOT", copy)
    path = tmp_path / "release-watch.json"
    digest = release.write_watch(protocol_path, path)
    return ledger, protocol_path, protocol, values, copy, path, digest


class SecretTrap(Mapping):
    def __init__(self):
        self.reads = []

    def __getitem__(self, key):
        self.reads.append(key)
        raise AssertionError("No private mapping lookup is allowed before public rejection")

    def __iter__(self):
        return iter(())

    def __len__(self):
        return 0


def test_old_guard_does_not_cover_changed_unlisted_runtime_source_but_watch_does(watched):
    _, protocol_path, _, _, copy, watch_path, digest = watched
    missing = "src/agent_app/retrieval/retriever.py"
    assert missing not in runtime.BOUND_SOURCE_FILES
    _, old_digest, _ = runtime.read_protocol(protocol_path)
    source = copy / missing
    source.write_bytes(source.read_bytes() + b"\n# synthetic release drift\n")
    # This is a real file mutation in a disposable source tree. Historical
    # checks remain unchanged; only the new explicit sidecar rejects it.
    assert runtime.read_protocol(protocol_path)[1] == old_digest
    with pytest.raises(ValueError, match="PresentationReleaseWatchRejected"):
        release.validate_watch(protocol_path, watch_path, expected_sha256=digest)


@pytest.mark.parametrize("change", ["unlisted_source", "new_module", "wrong_watch_hash"])
def test_public_release_drift_stops_before_any_credential_lookup(watched, change):
    _, protocol_path, _, _, copy, watch_path, digest = watched
    if change == "unlisted_source":
        path = copy / "src/agent_app/tracker/sqlite_tracker.py"
        path.write_bytes(path.read_bytes() + b"\n# synthetic source change\n")
    elif change == "new_module":
        (copy / "src/agent_app/new_unreviewed.py").write_text("pass\n")
    else:
        digest = "0" * 64
    trap = SecretTrap()
    with pytest.raises(ValueError, match="PresentationReleaseWatchRejected"):
        release.configured_app(
            protocol_path, trap, watch_path=watch_path, expected_watch_sha256=digest
        )
    assert trap.reads == []


@pytest.mark.parametrize("alias", ["leaf_symlink", "directory_symlink", "hardlink"])
def test_source_aliases_are_rejected_without_reading_the_aliased_payload(
    watched, alias, monkeypatch
):
    _, protocol_path, _, _, copy, watch_path, digest = watched
    path = copy / "src/agent_app/retrieval/retriever.py"
    target = copy.parent / "private-stand-in.txt"
    target.write_text("synthetic private content must remain unopened")
    if alias == "leaf_symlink":
        path.unlink()
        path.symlink_to(target)
    elif alias == "directory_symlink":
        (copy / "src/agent_app/untrusted_directory").symlink_to(
            copy.parent, target_is_directory=True
        )
    else:
        path.unlink()
        path.hardlink_to(target)
    original = Path.read_bytes
    reads = []

    def observe(self):
        reads.append(self)
        return original(self)

    monkeypatch.setattr(Path, "read_bytes", observe)
    with pytest.raises(ValueError, match="PresentationReleaseWatchRejected"):
        release.validate_watch(protocol_path, watch_path, expected_sha256=digest)
    assert target not in reads
    if alias in {"leaf_symlink", "hardlink"}:
        assert path not in reads


def test_existing_watch_is_not_overwritten_or_automatically_rebased(watched):
    _, protocol_path, _, _, _, watch_path, digest = watched
    before = watch_path.read_bytes()
    with pytest.raises(ValueError, match="PresentationReleaseWatchRejected"):
        release.write_watch(protocol_path, watch_path)
    assert watch_path.read_bytes() == before and sha(watch_path) == digest


@pytest.mark.parametrize(
    "alias", ["dotenv_name", "source_tree", "symlink", "hardlink", "oversized"]
)
def test_watch_file_role_and_alias_rejection_precedes_any_payload_read(watched, alias, monkeypatch):
    _, protocol_path, _, _, copy, watch_path, digest = watched
    folder = copy.parent / "invalid-watch"
    folder.mkdir()
    path = folder / "release-watch.json"
    if alias == "dotenv_name":
        path = folder / ".env"
    elif alias == "source_tree":
        path = copy / "data/evaluation/split-e1-v1/test/release-watch.json"
    elif alias == "symlink":
        path.symlink_to(watch_path)
    elif alias == "hardlink":
        path.hardlink_to(watch_path)
    else:
        with path.open("wb") as stream:
            stream.truncate(2_000_001)
    reads = []

    def forbidden(self):
        reads.append(self)
        raise AssertionError("No payload may be read for this invalid role")

    monkeypatch.setattr(Path, "read_bytes", forbidden)
    with pytest.raises(ValueError, match="PresentationReleaseWatchRejected"):
        release.validate_watch(protocol_path, path, expected_sha256=digest)
    assert reads == []


def test_audit_alias_to_ledger_is_refused_before_credential_or_ledger_write(watched):
    _, protocol_path, protocol, _, _, watch_path, digest = watched
    ledger_path = Path(protocol["ledger_path"])
    before = ledger_path.read_bytes()
    audit = Path(protocol["receipt_dir"]).parent / "release-watch-audit.jsonl"
    audit.hardlink_to(ledger_path)
    trap = SecretTrap()
    with pytest.raises(ValueError, match="PresentationReleaseWatchRejected"):
        release.configured_app(
            protocol_path, trap, watch_path=watch_path, expected_watch_sha256=digest
        )
    assert trap.reads == []
    assert ledger_path.read_bytes() == before


def test_watch_cannot_be_reused_with_different_protocol_bytes(watched):
    _, protocol_path, _, _, copy, watch_path, digest = watched
    changed = json.loads(protocol_path.read_bytes())
    changed["session_id"] = "another-operator-session"
    other = copy.parent / "other-protocol/protocol.json"
    other.parent.mkdir()
    other.write_text(json.dumps(changed))
    assert runtime.read_protocol(other)[1] != runtime.read_protocol(protocol_path)[1]
    with pytest.raises(ValueError, match="PresentationReleaseWatchRejected"):
        release.validate_watch(other, watch_path, expected_sha256=digest)


def test_unreadable_subtree_is_rejected_instead_of_silently_omitted(watched, monkeypatch):
    _, protocol_path, _, _, _, watch_path, digest = watched

    def unreadable_walk(_folder, *, followlinks, onerror):
        assert followlinks is False and callable(onerror)
        onerror(PermissionError("Synthetic unreadable source directory"))
        return iter(())

    monkeypatch.setattr(release.os, "walk", unreadable_walk)
    with pytest.raises(ValueError, match="PresentationReleaseWatchRejected"):
        release.validate_watch(protocol_path, watch_path, expected_sha256=digest)


def test_watched_http_keeps_original_model_scope_slot_and_private_payloads(watched):
    ledger, protocol_path, protocol, values, _, watch_path, digest = watched
    records = []
    before_protocol = protocol_path.read_bytes()
    app = release.configured_app(
        protocol_path,
        values,
        watch_path=watch_path,
        expected_watch_sha256=digest,
        transport_factory=lambda: httpx.MockTransport(
            lambda request: authored_response(request, records)
        ),
    )
    owner = app.state.presentation_runtime
    watch = app.state.presentation_release_watch
    try:
        with TestClient(app) as client, offline_network():
            response = client.post(
                "/cases/synthetic-presentation-0/messages",
                json=body("What does st.button return?", 0, "first"),
                headers=AUTH,
            )
            assert response.status_code == 200 and response.json()["pending"] is not None
            assert len(records) == 1
            assert owner.observations[0]["request_id"] == protocol["slots"][0]["request_id"]
            assert owner.config.continuation_id == protocol["scope_id"]
            assert records[0]["body"]["model"] == "gpt-4o-mini"
            assert records[0]["body"]["max_tokens"] == 1024
            assert app.state.presentation_binding["profile_id"] == "presentation_scoped_v1"
            assert app.state.presentation_release_binding["profile_id"] == release.PROFILE
            assert any(row["stage"] == "dispatch" and row["accepted"] for row in watch.observations)
            assert any(row["delegate_started"] for row in watch.observations)
    finally:
        owner.close()
    assert protocol_path.read_bytes() == before_protocol
    assert ledger.snapshot().halted
    audit = watch.audit_path.read_text()
    assert KEY not in audit and TOKEN not in audit
    assert "messages" not in audit and "headers" not in audit
    assert ledger.quarantine_scope_status(protocol["scope_id"]).consumed_requests == 1


def test_change_after_reservation_is_blocked_before_underlying_http_and_keeps_uncertainty(
    watched, monkeypatch
):
    ledger, protocol_path, protocol, values, copy, watch_path, digest = watched
    records = []
    app = release.configured_app(
        protocol_path,
        values,
        watch_path=watch_path,
        expected_watch_sha256=digest,
        transport_factory=lambda: httpx.MockTransport(
            lambda request: authored_response(request, records)
        ),
    )
    owner = app.state.presentation_runtime
    watch = app.state.presentation_release_watch
    reserve = owner.ledger.reserve
    held_before = ledger.quarantine_observation().unknown_ids
    source = copy / "src/agent_app/retrieval/retriever.py"

    def reserve_then_change(**arguments):
        result = reserve(**arguments)
        source.write_bytes(source.read_bytes() + b"\n# synthetic post-reservation change\n")
        return result

    monkeypatch.setattr(owner.ledger, "reserve", reserve_then_change)
    try:
        with TestClient(app) as client, offline_network():
            response = client.post(
                "/cases/synthetic-presentation-0/messages",
                json=body("What does st.button return?", 0, "late-drift"),
                headers=AUTH,
            )
            assert response.status_code == 200 and response.json()["pending"] is None
            assert records == []
            assert owner.observations[0]["ledger"]["status"] == "uncertain"
            assert not ledger.quarantine_scope_status(protocol["scope_id"]).active
            assert set(held_before).issubset(ledger.quarantine_observation().unknown_ids)
            assert len(ledger.quarantine_observation().unknown_ids) == len(held_before) + 1
            assert any(
                row["stage"] == "dispatch" and row["accepted"] is False
                for row in watch.observations
            )
            assert not any(row["delegate_started"] for row in watch.observations)
    finally:
        owner.close()


def test_wrapped_asgi_shutdown_drains_inflight_record_without_owner_lock_cycle(watched):
    ledger, protocol_path, protocol, values, _, watch_path, digest = watched
    entered, release_provider = Event(), Event()
    records = []

    def provider(request):
        entered.set()
        assert release_provider.wait(10)
        return authored_response(request, records)

    app = release.configured_app(
        protocol_path,
        values,
        watch_path=watch_path,
        expected_watch_sha256=digest,
        transport_factory=lambda: httpx.MockTransport(provider),
    )
    owner = app.state.presentation_runtime
    original_close = owner.close
    client = TestClient(app)
    client.__enter__()
    exited = False
    try:
        with offline_network(), ThreadPoolExecutor(2) as pool:
            request = pool.submit(
                client.post,
                "/cases/synthetic-presentation-0/messages",
                json=body("What does st.button return?", 0, "lifespan-close"),
                headers=AUTH,
            )
            assert entered.wait(10)
            closing = pool.submit(client.__exit__, None, None, None)
            for _ in range(100):
                if owner._closed:
                    break
                time.sleep(0.01)
            assert owner._closed
            # The old path held this owner lock while waiting for run.lock.
            # Here it remains available for record() to persist the result.
            acquired = owner._lock.acquire(blocking=False)
            assert acquired
            owner._lock.release()
            assert not closing.done()
            release_provider.set()
            result = request.result(timeout=10)
            closing.result(timeout=10)
            exited = True
            assert result.status_code == 200
            assert len(records) == 1 and owner.observations[0]["ledger"]["status"] == "settled"
            assert owner._active == set()
            # No class swap or direct Runtime.close monkeypatch was introduced.
            assert owner.close == original_close
            assert (
                app.state.presentation_release_binding["application_lifespan_policy"]
                == release.LIFESPAN_POLICY
            )
            assert ledger.quarantine_scope_status(protocol["scope_id"]).consumed_requests == 1
    finally:
        release_provider.set()
        if not exited:
            client.__exit__(None, None, None)
        owner.close()
