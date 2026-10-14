"""A new split must have its own verified index epoch, leaving PR35 unchanged."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from agent_app.retrieval.offline_index import build_index
from agent_app.retrieval.pilot_corpus import build_pilot_corpus
from agent_app.testing.http_pilot_runtime import offline_network

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/dev_three_index_acceptance.py"
SPLIT = "data/evaluation/dev-three-v1/split-manifest.json"
HISTORICAL_SPLIT = "data/evaluation/split-manifest.json"
HISTORICAL_PROTOCOL = "experiments/retrieval_acceptance/pr35/protocol-v1.json"
ALLOWLIST = "experiments/corpus/pilot-allowlist.json"
OLD_SNAPSHOT = "docs-pilot-87bdaf9a3dadcefff48a6775ef616f3d3dd5bf1c8cb23a9521b0e11ccaae160c"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def runner():
    spec = importlib.util.spec_from_file_location("dev_three_index_acceptance", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def packet(tmp_path_factory, runner):
    """Synthetic test fixtures exercise the runner; never pretend to be real dev cases."""
    directory = tmp_path_factory.mktemp("dev-three-epoch-controls")
    for relative in (SPLIT, HISTORICAL_SPLIT, HISTORICAL_PROTOCOL, ALLOWLIST):
        path = directory / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / relative).read_bytes())
    for relative in runner.PACKET_PATHS:
        path = directory / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / relative).read_bytes())
    split = json.loads((directory / SPLIT).read_bytes())
    cases = []
    for index, (case_id, relative) in enumerate(
        zip(runner.CASE_IDS, split["fixture_paths"], strict=True)
    ):
        visible = {
            "message": (
                "My widget resets and the version is unknown."
                if index == 0
                else "Can a button icon use a custom image?"
                if index == 1
                else "Enum equality fails in Session State on Streamlit 1.31.0."
            ),
            "reported_facts": [{"name": "streamlit_version", "value": "1.31.0"}]
            if index == 2
            else [],
            "unknowns": [] if index == 2 else ["streamlit_version"],
        }
        fixture = {"case": {"case_id": case_id}, "turns": [{"visible": visible}]}
        path = directory / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(fixture), encoding="utf-8")
        cases.append(
            {
                "case_id": case_id,
                "fixture_path": relative,
                "fixture_sha256": sha(path),
                "queries": ["session state widget rerun", "button icon image"],
                "http_expected_first_decision": "escalate" if index == 2 else "ask",
            }
        )
    corpus = build_pilot_corpus(
        ROOT / "streamlit-data-for-dev-test", directory / SPLIT, directory / ALLOWLIST
    )
    protocol = {
        "protocol_id": "dev-three-docs-index-epoch-v1",
        "quality_claim": False,
        "held_out_test": False,
        "real_provider_requests": 0,
        "expected_sources": 14,
        "expected_chunks": 30,
        "expected_snapshot_id": corpus.snapshot_id,
        "file_sha256": {
            relative: sha(directory / relative)
            for relative in (SPLIT, HISTORICAL_SPLIT, HISTORICAL_PROTOCOL, ALLOWLIST)
        },
        "packet_sha256": {relative: sha(directory / relative) for relative in runner.PACKET_PATHS},
        "source_pins": corpus.manifest["corpus"]["source_pins"],
        "cases": cases,
    }
    protocol_path = directory / "index-protocol.json"
    protocol_path.write_text(json.dumps(protocol), encoding="utf-8")
    first, second, old = directory / "index-a", directory / "index-b", directory / "old-index"
    with offline_network():
        build_index(corpus, first)
        build_index(corpus, second)
        historical = build_pilot_corpus(
            ROOT / "streamlit-data-for-dev-test", ROOT / HISTORICAL_SPLIT, ROOT / ALLOWLIST
        )
        build_index(historical, old)
    return directory, protocol_path, first, second, old, corpus


def test_historical_manifest_and_pr35_protocol_bytes_are_preserved():
    assert (
        sha(ROOT / HISTORICAL_SPLIT)
        == "78e630cbef86937f2838795a2329ee56e16ea0beef7900db5c63d5fede6404ff"
    )
    assert (
        sha(ROOT / HISTORICAL_PROTOCOL)
        == "33ab264f46239ab0dcdab24ecafe5b41e2e39a8b518bcd2abf0185b6534ff974"
    )
    assert (
        json.loads((ROOT / HISTORICAL_PROTOCOL).read_bytes())["expected_snapshot_id"]
        == OLD_SNAPSHOT
    )


def test_new_split_retains_reservations_family_exclusion_and_draft_scope():
    manifest = json.loads((ROOT / SPLIT).read_bytes())
    reservations = json.loads(
        (ROOT / "data/evaluation/candidates/reservations-v1.json").read_bytes()
    )
    assert len(manifest["selected"]["dev"]) == 3
    assert manifest["selected"]["test"] == []
    assert manifest["status"] == "draft_not_frozen"
    assert manifest["targets"]["dev_cases"] == manifest["targets"]["test_cases"] == 15
    assert set(reservations["partial_corpus_denylist"]["issue_ids"]) <= set(
        manifest["exposure_reserved_issue_ids"]
    )
    assert {2379, 8129, 8180, 9455, 9770, 12629, 12782} <= set(
        manifest["development_exposure_issue_ids"]
    )
    assert [family["issue_ids"] for family in manifest["families"]] == [
        [12629, 12782],
        [9770],
        [2379, 8129, 8180],
    ]
    assert manifest["corpus_review"]["final_corpus_approved"] is False


def test_new_epoch_actual_native_adapter_http_correction_and_retry(runner, packet, monkeypatch):
    directory, protocol, first, second, _, corpus = packet
    monkeypatch.setattr(runner, "ROOT", directory)
    receipt = runner.verify(first, second, protocol)
    assert receipt["accepted"] is True
    assert receipt["checks_passed"] == receipt["checks_total"]
    assert receipt["snapshot_id"] == corpus.snapshot_id != OLD_SNAPSHOT
    assert receipt["actual_index_tested"] is True
    assert receipt["real_provider_requests"] == 0
    assert receipt["quality_claim"] is False
    assert len(receipt["public_handoffs"]) == 3
    assert len(receipt["native_collection_queries"]) >= 32
    assert receipt["checks"]["enum:stale_approval_rejected"] is True
    assert receipt["checks"]["enum:recreation_retry_once"] is True
    assert runner.TOKEN not in json.dumps(receipt)
    for version in ("1.31.0", "1.39.0"):
        search = next(
            item for item in receipt["searches"] if item["condition"] == "version-" + version
        )
        assert search["bundle"]["hits"] == []


@pytest.mark.parametrize("kind", ["same-path", "old-epoch"])
def test_different_epoch_or_same_build_cannot_be_accepted(runner, packet, monkeypatch, kind):
    directory, protocol, first, second, old, _ = packet
    monkeypatch.setattr(runner, "ROOT", directory)
    with pytest.raises(ValueError, match="^DevThreeIndexAcceptanceRejected$"):
        runner.verify(
            first if kind == "same-path" else old,
            first if kind == "same-path" else second,
            protocol,
        )


@pytest.mark.parametrize("mutation", ["split-pin", "fixture-pin", "packet-pin", "protocol-id"])
def test_wrong_registration_rejected_before_index_io(
    runner, packet, monkeypatch, tmp_path, mutation
):
    directory, protocol_path, first, second, _, _ = packet
    monkeypatch.setattr(runner, "ROOT", directory)
    protocol = json.loads(protocol_path.read_bytes())
    if mutation == "split-pin":
        protocol["file_sha256"][SPLIT] = "0" * 64
    elif mutation == "fixture-pin":
        protocol["cases"][0]["fixture_sha256"] = "0" * 64
    elif mutation == "packet-pin":
        protocol["packet_sha256"]["data/evaluation/dev-three-v1/evidence-v1.json"] = "0" * 64
    else:
        protocol["protocol_id"] = "unregistered-epoch"
    path = tmp_path / "bad-protocol.json"
    path.write_text(json.dumps(protocol), encoding="utf-8")
    calls = []

    def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError("RegistrationMustRunFirst")

    monkeypatch.setattr(runner, "open_verified_index", forbidden)
    with pytest.raises(ValueError, match="^DevThreeIndexAcceptanceRejected$"):
        runner.verify(first, second, path)
    assert calls == []


def test_manifest_only_adapter_cannot_claim_native_queries(runner, packet, monkeypatch):
    directory, protocol, first, second, _, corpus = packet
    monkeypatch.setattr(runner, "ROOT", directory)
    chunks = corpus.manifest["corpus"]["chunks"][:5]

    def fake_search(*args, **kwargs):
        return {
            "docs": {
                "ids": [[row["chunk_id"] for row in chunks]],
                "documents": [[row["document"] for row in chunks]],
                "metadatas": [[row["metadata"] for row in chunks]],
            },
            "issues": {"ids": [[]], "documents": [[]], "metadatas": [[]]},
        }

    monkeypatch.setattr(runner.StreamlitRetriever, "search", fake_search)
    with pytest.raises(ValueError, match="^DevThreeIndexAcceptanceRejected$"):
        runner.verify(first, second, protocol)


def test_ignoring_native_version_filter_is_rejected(runner, packet, monkeypatch):
    directory, protocol, first, second, _, _ = packet
    monkeypatch.setattr(runner, "ROOT", directory)
    native = runner.StreamlitRetriever.search

    def ignoring(self, query, n_results=3, *, filters=None):
        return native(self, query, n_results, filters={})

    monkeypatch.setattr(runner.StreamlitRetriever, "search", ignoring)
    with pytest.raises(ValueError, match="^DevThreeIndexAcceptanceRejected$"):
        runner.verify(first, second, protocol)


def test_existing_receipt_is_preserved_before_registration(runner, tmp_path, monkeypatch, capsys):
    output = tmp_path / "existing.json"
    output.write_bytes(b"historical receipt\n")

    def forbidden(*args, **kwargs):
        raise AssertionError("ExistingReceiptMustNotStartWork")

    monkeypatch.setattr(runner, "release_identity", forbidden)
    assert runner.main(["--index", "a", "--rebuild-index", "b", "--output", str(output)]) == 1
    assert output.read_bytes() == b"historical receipt\n"
    assert json.loads(capsys.readouterr().out)["diagnostic"] == "ReceiptAlreadyExists"


def test_private_runtime_failure_is_not_exported(runner, tmp_path, monkeypatch, capsys):
    private = "PRIVATE_RUNTIME_ERROR_WITH_UNTRUSTED_INPUT"
    monkeypatch.setattr(runner, "release_identity", lambda _: {})

    def forbidden(*args, **kwargs):
        print(private)
        raise RuntimeError(private)

    monkeypatch.setattr(runner, "verify", forbidden)
    output = tmp_path / "failed.json"
    assert runner.main(["--index", "a", "--rebuild-index", "b", "--output", str(output)]) == 1
    streams = capsys.readouterr()
    assert private not in output.read_text() + streams.out + streams.err
    assert json.loads(output.read_bytes())["diagnostic"] == "DevThreeIndexAcceptanceRejected"
