"""The receipt runner must reject broken provenance and preserve previous evidence."""

import importlib.util
import json
from pathlib import Path

import pytest

from agent_app.retrieval.offline_index import build_index
from agent_app.retrieval.pilot_corpus import build_pilot_corpus
from agent_app.testing.http_pilot_runtime import offline_network

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "experiments/retrieval_acceptance/verify_pilot_index.py"
PRIVATE = "PRIVATE_RUNNER_ERROR_MUST_NOT_APPEAR"


@pytest.fixture(scope="module")
def runner():
    specification = importlib.util.spec_from_file_location("pilot_index_receipt_runner", SCRIPT)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def indexes(tmp_path_factory):
    directory = tmp_path_factory.mktemp("receipt-real-indexes")
    with offline_network():
        corpus = build_pilot_corpus(
            ROOT / "streamlit-data-for-dev-test",
            ROOT / "data/evaluation/split-manifest.json",
            ROOT / "experiments/corpus/pilot-allowlist.json",
        )
        first, second = directory / "first", directory / "second"
        build_index(corpus, first)
        build_index(corpus, second)
    return first, second, corpus, directory


def arguments(indexes, output):
    return ["--index", str(indexes[0]), "--rebuild-index", str(indexes[1]), "--output", str(output)]


def test_actual_existing_indexes_http_replay_and_scope_are_inspectable(
    runner, indexes, tmp_path, capsys
):
    output = tmp_path / "receipt.json"
    assert runner.main(arguments(indexes, output)) == 0
    receipt = json.loads(output.read_text())
    assert receipt["accepted"] is True and receipt["checks_passed"] == receipt["checks_total"]
    assert receipt["actual_index_tested"] is True
    assert receipt["actual_provider_requests"] == 0 and receipt["actual_api_cost_usd"] == "0"
    assert receipt["quality_claim"] is receipt["held_out_test"] is False
    assert receipt["simulated_gateway_cost"] == {"collected": False, "actual_charge": False}
    assert receipt["exclusions"]["split_status"] == "draft_not_frozen"
    assert [handoff["analysis"]["decision"] for handoff in receipt["public_handoffs"]] == [
        "ask",
        "escalate",
        "escalate",
        "ask",
    ]
    assert len(receipt["native_backend_queries"]) == 10
    assert receipt["checks"]["wrong_snapshot_before_backend_query"] is True
    assert receipt["checks"]["review_retry_after_backend_recreation"] is True
    assert receipt["source_unchanged_during_run"] is True
    assert len(receipt["release_before"]["git_commit"]) == 40
    assert runner.TOKEN not in output.read_text()
    assert json.loads(capsys.readouterr().out)["accepted"] is True


def test_same_index_cannot_be_reported_as_independent_rebuild(runner, indexes):
    with pytest.raises(ValueError, match="^PilotIndexAcceptanceRejected$"):
        runner.verify(indexes[0], indexes[0])


def test_real_rebuild_with_changed_split_pin_is_rejected(runner, indexes):
    first, _, _, directory = indexes
    split = json.loads((ROOT / "data/evaluation/split-manifest.json").read_text())
    split["updated_on"] = "2000-01-01"
    path = directory / "modified-split.json"
    path.write_text(json.dumps(split))
    with offline_network():
        changed = build_pilot_corpus(
            ROOT / "streamlit-data-for-dev-test",
            path,
            ROOT / "experiments/corpus/pilot-allowlist.json",
        )
        target = directory / "changed-index"
        build_index(changed, target)
    with pytest.raises(ValueError, match="^PilotIndexAcceptanceRejected$"):
        runner.verify(first, target)


def test_well_formed_adapter_material_with_substituted_url_is_not_accepted(
    runner, indexes, monkeypatch
):
    original = runner.ChromaRetrieverAdapter.search

    def substituted(self, request):
        bundle = original(self, request)
        if bundle.hits:
            hit = bundle.hits[0].model_copy(update={"source_url": "https://example.invalid/source"})
            return bundle.model_copy(update={"hits": (hit, *bundle.hits[1:])})
        return bundle

    monkeypatch.setattr(runner.ChromaRetrieverAdapter, "search", substituted)
    with pytest.raises(ValueError, match="^PilotIndexAcceptanceRejected$"):
        runner.verify(indexes[0], indexes[1])


def test_missing_index_does_not_create_chroma_storage(runner, indexes, tmp_path, capsys):
    absent = tmp_path / "missing-index"
    output = tmp_path / "rejected.json"
    assert runner.main(arguments((absent, indexes[1]), output)) == 1
    assert not absent.exists()
    assert json.loads(output.read_text())["diagnostic"] == "PilotIndexAcceptanceRejected"
    assert capsys.readouterr().err == ""


def test_echoed_queries_do_not_hide_native_query_substitution(runner, indexes, monkeypatch):
    original = runner.ChromaRetrieverAdapter.search

    def rerouted(self, request):
        bundle = original(
            self, request.model_copy(update={"queries": ("bogus query", "bogus second query")})
        )
        return bundle.model_copy(update={"queries_used": request.queries})

    monkeypatch.setattr(runner.ChromaRetrieverAdapter, "search", rerouted)
    with pytest.raises(ValueError, match="^PilotIndexAcceptanceRejected$"):
        runner.verify(indexes[0], indexes[1])


def test_native_backend_ignoring_version_filter_is_rejected(runner, indexes, monkeypatch):
    original = runner.StreamlitRetriever.search

    def ignoring_filter(self, query, n_results=3, *, filters=None):
        return original(self, query, n_results, filters={})

    monkeypatch.setattr(runner.StreamlitRetriever, "search", ignoring_filter)
    with pytest.raises(ValueError, match="^PilotIndexAcceptanceRejected$"):
        runner.verify(indexes[0], indexes[1])


def test_existing_output_is_preserved_before_any_identity_or_index_read(
    runner, tmp_path, monkeypatch, capsys
):
    output = tmp_path / "existing.json"
    output.write_bytes(b"previous receipt\n")

    def forbidden():
        raise AssertionError("NoWorkForExistingReceipt")

    monkeypatch.setattr(runner, "release_identity", forbidden)
    assert runner.main(arguments((tmp_path / "absent-a", tmp_path / "absent-b"), output)) == 1
    assert output.read_bytes() == b"previous receipt\n"
    assert json.loads(capsys.readouterr().out)["diagnostic"] == "ReceiptAlreadyExists"


def test_unexpected_runtime_output_and_exception_are_not_exported(
    runner, tmp_path, monkeypatch, capsys
):
    output = tmp_path / "failed.json"

    def private_failure(*args):
        print(PRIVATE)
        raise RuntimeError(PRIVATE)

    monkeypatch.setattr(runner, "verify", private_failure)
    assert runner.main(arguments((tmp_path / "a", tmp_path / "b"), output)) == 1
    streams = capsys.readouterr()
    assert PRIVATE not in output.read_text() + streams.out + streams.err
    assert json.loads(output.read_text())["accepted"] is False
