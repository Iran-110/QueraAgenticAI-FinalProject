"""Native coverage receipts keep corpus availability separate from model quality."""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/dev_rag_coverage_acceptance.py"


@pytest.fixture(scope="module")
def runner():
    specification = importlib.util.spec_from_file_location("dev_rag_coverage_acceptance", SCRIPT)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def receipt(runner, tmp_path_factory):
    return runner.verify(tmp_path_factory.mktemp("coverage-receipt") / "fresh-indexes")


def test_native_builds_source_pins_exclusions_and_tamper_are_inspectable(receipt):
    assert receipt["accepted"] is True
    assert receipt["checks_passed"] == receipt["checks_total"]
    assert receipt["actual_index_tested"] is True
    assert receipt["quality_claim"] is receipt["held_out_test"] is False
    assert receipt["actual_provider_requests"] == 0
    assert receipt["actual_api_cost_usd"] == "0"
    assert receipt["source_unchanged_during_run"] is True
    assert receipt["checks"]["same_snapshot_content_tamper_rejected"] is True
    assert receipt["checks"]["authoritative_new_index_untouched"] is True
    assert len(receipt["exclusions"]["reserved_issue_ids"]) == 46
    assert {2379, 8129, 8180, 9770, 12629, 12782} <= set(
        receipt["exclusions"]["reserved_issue_ids"]
    )
    assert len(receipt["sources"]) == 18
    first = receipt["indexes"]["new_18_sources"]
    second = receipt["indexes"]["independent_new_rebuild"]
    assert first["path"] != second["path"]
    assert first["snapshot_id"] == second["snapshot_id"]
    assert first["manifest_sha256"] == second["manifest_sha256"]
    assert receipt["index_counts"]["historical_14_sources"]["chunk_count"] == 30
    assert receipt["index_counts"]["new_18_sources"]["chunk_count"] == 36
    assert set(first) == {"path", "snapshot_id", "manifest_sha256"}


def test_full_native_material_and_direct_filters_are_distinct_from_unfiltered_cases(receipt):
    unfiltered = [search for search in receipt["searches"] if not search["request"]["filters"]]
    assert len(unfiltered) == 6
    assert {search["condition"] for search in unfiltered} == {
        "dev-case-a",
        "dev-case-b",
        "dev-case-c",
    }
    assert all(not search["control_filters_not_model_inputs"] for search in unfiltered)
    filtered = [search for search in receipt["searches"] if search["request"]["filters"]]
    assert len(filtered) == 9
    assert all(search["control_filters_not_model_inputs"] for search in filtered)
    assert all("result" in call for call in receipt["native_collection_queries"])
    assert {call["collection"] for call in receipt["native_collection_queries"]} == {
        "streamlit_docs",
        "streamlit_issues",
    }
    assert all(
        not call["result"]["ids"][0]
        for call in receipt["native_collection_queries"]
        if call["collection"] == "streamlit_issues"
    )
    multi = [proof for proof in receipt["source_proofs"] if "multiselect" in proof["source_id"]]
    assert len(multi) == 2 and multi[0]["text_sha256"] == multi[1]["text_sha256"]
    assert multi[0]["version"] != multi[1]["version"]
    assert {chunk["chunk_id"] for chunk in multi[0]["chunks"]}.isdisjoint(
        chunk["chunk_id"] for chunk in multi[1]["chunks"]
    )


def test_changed_frozen_protocol_is_rejected_before_build(runner, tmp_path, monkeypatch):
    value = json.loads(runner.PROTOCOL_PATH.read_bytes())
    value["retrieval"]["top_k"] = 4
    path = tmp_path / "altered-protocol.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    calls = []
    monkeypatch.setattr(runner, "build_pilot_corpus", lambda *args: calls.append(True))
    root = tmp_path / "must-not-create"
    with pytest.raises(ValueError, match="^DevRagCoverageAcceptanceRejected$"):
        runner.verify(root, path)
    assert calls == [] and not root.exists()


def test_historical_split_cannot_substitute_three_family_exclusion(runner, tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "NEW_SPLIT", ROOT / "data/evaluation/split-manifest.json")
    calls = []
    monkeypatch.setattr(runner, "build_pilot_corpus", lambda *args: calls.append(True))
    root = tmp_path / "must-not-create"
    with pytest.raises(ValueError, match="^DevRagCoverageAcceptanceRejected$"):
        runner.verify(root)
    assert calls == [] and not root.exists()


def test_adapter_quote_with_substituted_provenance_is_rejected(runner, tmp_path, monkeypatch):
    original = runner.ChromaRetrieverAdapter.search

    def changed(self, request):
        bundle = original(self, request)
        if bundle.hits:
            hit = bundle.hits[0].model_copy(update={"source_url": "https://example.invalid/other"})
            return bundle.model_copy(update={"hits": (hit, *bundle.hits[1:])})
        return bundle

    monkeypatch.setattr(runner.ChromaRetrieverAdapter, "search", changed)
    with pytest.raises(ValueError, match="^DevRagCoverageAcceptanceRejected$"):
        runner.verify(tmp_path / "fresh-indexes")


def test_approved_manifest_only_rows_do_not_count_as_native_search(runner, tmp_path, monkeypatch):
    def material_without_search(self, query, n_results=3, *, filters=None):
        chunks = self.client.manifest["corpus"]["chunks"][:n_results]
        return {
            "docs": {
                "ids": [[chunk["chunk_id"] for chunk in chunks]],
                "documents": [[chunk["document"] for chunk in chunks]],
                "metadatas": [[chunk["metadata"] for chunk in chunks]],
            },
            "issues": {"ids": [[]], "documents": [[]], "metadatas": [[]]},
        }

    monkeypatch.setattr(runner.StreamlitRetriever, "search", material_without_search)
    with pytest.raises(ValueError, match="^DevRagCoverageAcceptanceRejected$"):
        runner.verify(tmp_path / "fresh-indexes")


def test_native_search_ignoring_source_and_version_filters_is_rejected(
    runner, tmp_path, monkeypatch
):
    original = runner.StreamlitRetriever.search

    def ignoring(self, query, n_results=3, *, filters=None):
        return original(self, query, n_results, filters={})

    monkeypatch.setattr(runner.StreamlitRetriever, "search", ignoring)
    with pytest.raises(ValueError, match="^DevRagCoverageAcceptanceRejected$"):
        runner.verify(tmp_path / "fresh-indexes")


def test_existing_index_root_is_never_rebuilt_or_overwritten(runner, tmp_path):
    root = tmp_path / "existing"
    root.mkdir()
    sentinel = root / "previous.txt"
    sentinel.write_bytes(b"preserve original artifact")
    with pytest.raises(ValueError, match="^DevRagCoverageAcceptanceRejected$"):
        runner.verify(root)
    assert sentinel.read_bytes() == b"preserve original artifact"
    assert list(root.iterdir()) == [sentinel]


def test_existing_receipt_stops_before_build_or_protocol_read(
    runner, tmp_path, monkeypatch, capsys
):
    output = tmp_path / "existing.json"
    output.write_bytes(b"original receipt")

    def forbidden(*args):
        raise AssertionError("ExistingReceiptMustStopBeforeWork")

    monkeypatch.setattr(runner, "verify", forbidden)
    root = tmp_path / "not-created"
    assert runner.main(["--index-root", str(root), "--output", str(output)]) == 1
    assert output.read_bytes() == b"original receipt"
    assert not root.exists()
    assert json.loads(capsys.readouterr().out)["diagnostic"] == "ReceiptAlreadyExists"


def test_private_failure_output_is_suppressed(runner, tmp_path, monkeypatch, capsys):
    private = "PRIVATE_SOURCE_OR_PROVIDER_ERROR"

    def failure(*args):
        print(private)
        raise RuntimeError(private)

    monkeypatch.setattr(runner, "verify", failure)
    output = tmp_path / "failure.json"
    assert runner.main(["--index-root", str(tmp_path / "indexes"), "--output", str(output)]) == 1
    result = json.loads(output.read_bytes())
    assert result == {"accepted": False, "diagnostic": runner.DIAGNOSTIC}
    streams = capsys.readouterr()
    assert private not in streams.out + streams.err + output.read_text(encoding="utf-8")
