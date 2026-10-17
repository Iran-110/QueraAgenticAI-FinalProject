"""Independent preparation/funding/private-file controls on synthetic data only."""

import hashlib
import os
import shutil
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

import pytest
from test_budget_quarantine_scope import multiple_holds as multiple_holds
from test_budget_quarantine_scope import slot
from test_presentation_runtime import final_v3 as final_v3

from agent_app import presentation_runtime as runtime
from agent_app import presentation_session as session


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@pytest.fixture
def three_holds(multiple_holds):
    ledger, path, _ = multiple_holds
    observed = ledger.quarantine_observation()
    request = slot(900)
    ledger.authorize_quarantine_scope(
        authorization_id="synthetic-third-hold-scope",
        authorization_ref="synthetic-third-hold-test",
        expected_unknown_ids=observed.unknown_ids,
        expected_unknown_fingerprints=observed.unknown_fingerprints,
        expected_meta_sha256=observed.meta_sha256,
        expected_authorization_history_sha256=observed.authorization_history_sha256,
        protocol_sha256="9" * 64,
        request_slots=(request,),
        additional_cap_usd=Decimal("0.10"),
    )
    ledger.reserve(**asdict(request), continuation_id="synthetic-third-hold-scope")
    ledger.mark_uncertain(request.request_id, error_code="ProviderRequestFailed")
    assert len(ledger.quarantine_observation().unknown_ids) == 3
    return ledger, path


@pytest.fixture
def source_index(tmp_path, final_v3):
    path = tmp_path / "source-index-copy"
    shutil.copytree(final_v3["path"], path)
    return {**final_v3, "path": str(path)}


@pytest.fixture
def prepared(tmp_path, three_holds, source_index):
    ledger, ledger_path = three_holds
    protocols = session.prepare_sessions(
        output_dir=tmp_path / "sessions",
        ledger_path=ledger_path,
        index_path=source_index["path"],
    )
    return ledger, ledger_path, protocols


def test_prepare_two_fresh_protocols_never_funds_or_changes_ledger(
    tmp_path, three_holds, source_index
):
    ledger, ledger_path = three_holds
    before = ledger_path.read_bytes()
    old_rows = session.ledger_rows(ledger_path)
    protocols = session.prepare_sessions(
        output_dir=tmp_path / "fresh-sessions",
        ledger_path=ledger_path,
        index_path=source_index["path"],
    )
    assert ledger_path.read_bytes() == before
    assert session.ledger_rows(ledger_path) == old_rows
    assert ledger.snapshot().halted
    assert [record["phase"] for record in protocols] == ["rehearsal", "meeting"]
    identities, case_ids = set(), set()
    for record in protocols:
        protocol, digest, slots = runtime.read_protocol(record["protocol"])
        assert digest == record["sha256"]
        assert len(slots) == 14
        assert len({(slot.case_id, slot.case_revision) for slot in slots}) == 7
        assert len(protocol["cases"]) == 3
        assert len({slot.request_id for slot in slots}) == 14
        assert all(slot.request_id not in identities for slot in slots)
        identities.update(slot.request_id for slot in slots)
        ids = {case["case_id"] for case in protocol["cases"]}
        assert case_ids.isdisjoint(ids)
        case_ids.update(ids)
        assert Path(protocol["index"]["path"]) != Path(source_index["path"])
        assert (
            sha(Path(protocol["index"]["path"]) / "pilot-manifest.json")
            == source_index["index_manifest_sha256"]
        )
        assert not Path(protocol["tracker_path"]).exists()
        assert protocol["authority"]["c5_reconciled"] is False
        assert protocol["source_commit"] and len(protocol["source_commit"]) == 40


def test_existing_output_is_refused_without_ledger_change(tmp_path, three_holds, source_index):
    _, ledger_path = three_holds
    destination = tmp_path / "already-exists"
    destination.mkdir()
    before = ledger_path.read_bytes()
    with pytest.raises(ValueError, match="PresentationFreshOutputRequired"):
        session.prepare_sessions(
            output_dir=destination, ledger_path=ledger_path, index_path=source_index["path"]
        )
    assert ledger_path.read_bytes() == before
    assert list(destination.iterdir()) == []


def test_wrong_authorization_digest_writes_nothing(prepared):
    _, ledger_path, protocols = prepared
    before = ledger_path.read_bytes()
    with pytest.raises(ValueError, match="PresentationAuthorizationMismatch"):
        session.authorize_protocol(protocols[0]["protocol"], expected_sha256="0" * 64)
    assert ledger_path.read_bytes() == before


def test_both_exact_scopes_are_additive_and_authorization_is_idempotent(prepared):
    ledger, ledger_path, protocols = prepared
    old_rows = session.ledger_rows(ledger_path)
    old_unknown = ledger.quarantine_observation()
    for record in protocols:
        status = session.authorize_protocol(record["protocol"], expected_sha256=record["sha256"])
        assert status["active"] and status["max_requests"] == 14
        assert Decimal(status["additional_cap_usd"]) == Decimal("0.10")
        before = session.ledger_rows(ledger_path)
        repeat = session.authorize_protocol(record["protocol"], expected_sha256=record["sha256"])
        assert repeat == status
        assert session.ledger_rows(ledger_path) == before
    assert session.previous_rows_preserved(old_rows, session.ledger_rows(ledger_path))
    assert ledger.quarantine_observation() == old_unknown
    assert ledger.snapshot().halted and ledger.snapshot().limit_usd == Decimal("4.50")


def test_new_uncertainty_stops_both_prepared_phases(prepared):
    ledger, _, protocols = prepared
    parsed = []
    for record in protocols:
        session.authorize_protocol(record["protocol"], expected_sha256=record["sha256"])
        parsed.append(runtime.read_protocol(record["protocol"]))
    protocol, _, slots = parsed[0]
    request = slots[0]
    ledger.reserve(**asdict(request), continuation_id=protocol["scope_id"])
    ledger.mark_uncertain(request.request_id, error_code="ProviderRequestFailed")
    assert len(ledger.quarantine_observation().unknown_ids) == 4
    for protocol, _, _ in parsed:
        assert not ledger.quarantine_scope_status(protocol["scope_id"]).active
    assert ledger.snapshot().halted


@pytest.fixture
def private_paths(tmp_path, monkeypatch):
    fake_root = tmp_path / "synthetic-repository"
    fake_root.mkdir()
    monkeypatch.setattr(session, "ROOT", fake_root)
    dotenv = fake_root / ".env"
    dotenv.write_text("METIS_API_KEY=synthetic-only-provider-key\n", encoding="utf-8")
    dotenv.chmod(0o600)
    token = tmp_path / "reviewer-token.txt"
    token.write_text("synthetic-only-reviewer-token", encoding="utf-8")
    token.chmod(0o600)
    index = tmp_path / "index"
    index.mkdir()
    protocol_path = tmp_path / "protocol.json"
    protocol_path.write_text("{}", encoding="utf-8")
    protocol = {
        "index": {"path": str(index)},
        "receipt_dir": str(tmp_path / "receipts"),
        "ledger_path": str(tmp_path / "ledger.sqlite3"),
        "tracker_path": str(tmp_path / "tracker.sqlite3"),
    }
    return protocol_path, protocol, dotenv, token


def test_private_settings_is_lazy_and_reads_only_on_secret_lookup(private_paths, monkeypatch):
    protocol_path, protocol, dotenv, token = private_paths
    reads = []
    original = Path.read_text

    def read_text(path, *args, **kwargs):
        reads.append(path)
        return original(path, *args, **kwargs)

    def dotenv_values(path):
        reads.append(path)
        return {"METIS_API_KEY": "synthetic-only-provider-key"}

    import dotenv as dotenv_module

    monkeypatch.setattr(Path, "read_text", read_text)
    monkeypatch.setattr(dotenv_module, "dotenv_values", dotenv_values)
    values = session.PrivateSettings(protocol_path, protocol, dotenv_path=dotenv, token_file=token)
    assert reads == []
    assert values["AGENT_REVIEWER_ID"] == "presentation-maintainer"
    assert reads == []
    assert values["METIS_API_KEY"] == "synthetic-only-provider-key"
    assert reads == [dotenv, token]
    assert values["AGENT_REVIEWER_TOKEN"] == "synthetic-only-reviewer-token"
    assert reads == [dotenv, token]


def test_private_token_hardlink_is_rejected_without_content_read(
    private_paths, tmp_path, monkeypatch
):
    protocol_path, protocol, dotenv, token = private_paths
    os.link(token, tmp_path / "token-hardlink")
    reads = []

    def forbidden(path, *args, **kwargs):
        reads.append(path)
        raise AssertionError("Private bytes must not be read")

    monkeypatch.setattr(Path, "read_text", forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    with pytest.raises(ValueError, match="PresentationPrivatePathRejected"):
        session.PrivateSettings(protocol_path, protocol, dotenv_path=dotenv, token_file=token)
    assert reads == []


def test_closed_serve_rejects_before_private_file_construction(prepared, monkeypatch):
    ledger, _, protocols = prepared
    record = protocols[0]
    session.authorize_protocol(record["protocol"], expected_sha256=record["sha256"])
    protocol, _, _ = runtime.read_protocol(record["protocol"])
    ledger.close_quarantine_scope(protocol["scope_id"])

    def forbidden(*args, **kwargs):
        raise AssertionError("Closed scope must not consult private settings")

    monkeypatch.setattr(session, "PrivateSettings", forbidden)
    with pytest.raises(ValueError, match="PresentationScopeUnavailable"):
        session.serve(
            record["protocol"],
            dotenv_path="must-not-read",
            reviewer_token_file="must-not-read",
            port=8001,
        )
