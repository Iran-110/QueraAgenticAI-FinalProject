"""Registration/observation unit tests, never the registered experiment itself."""

import hashlib
import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest

from agent_app.contracts import EvidenceBundle, EvidenceHit

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/retrieval_context_comparison.py"
SPEC = importlib.util.spec_from_file_location("retrieval_context_comparison_test", SCRIPT)
comparison = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(comparison)


@pytest.fixture
def pins(tmp_path, monkeypatch):
    registered = tmp_path / "experiments/retrieval_context"
    registered.mkdir(parents=True)
    script = tmp_path / "comparison.py"
    script.write_text("# Unit-test script bytes\n")
    fixture = registered / "fixture-v1.json"
    fixture.write_text(json.dumps({"scenarios": []}))
    protocol = registered / "protocol-v1.json"
    protocol.write_text(
        json.dumps(
            {
                "fixture_sha256": comparison.digest(fixture),
                "script_sha256": comparison.digest(script),
            }
        )
    )
    monkeypatch.setattr(comparison, "REGISTERED", registered)
    monkeypatch.setattr(comparison, "SCRIPT", script)
    monkeypatch.setattr(comparison, "source_pins", lambda: {"engine.py": "initial"})
    return comparison.registration()


@pytest.mark.parametrize("name", ["protocol", "fixture", "comparison_script"])
def test_registration_rejects_byte_changes_without_replacing_initial_pins(pins, name):
    original = deepcopy(pins["pins"])
    path = pins["paths"][name]
    path.write_bytes(path.read_bytes() + b"\nMutation after initial verification")
    with pytest.raises(ValueError, match="^RetrievalComparisonRegistrationChanged$"):
        comparison.check_registration(pins)
    assert pins["pins"] == original


def test_source_change_stops_before_any_new_query(pins, monkeypatch):
    monkeypatch.setattr(comparison, "source_pins", lambda: {"engine.py": "changed"})
    with pytest.raises(ValueError, match="^RetrievalComparisonSourceChanged$"):
        comparison.check_registration(pins)


def test_legacy_source_hash_is_checked_before_function_execution(monkeypatch):
    source = b"def build_initial_query(case, user_message):\n    raise RuntimeError('Executed')\n"
    monkeypatch.setattr(comparison.subprocess, "check_output", lambda *args, **kwargs: source)
    with pytest.raises(ValueError, match="^RetrievalComparisonBaselineChanged$"):
        comparison.load_legacy_query(
            {"baseline_commit": "registered-test", "baseline_engine_sha256": "0" * 64}
        )


def test_pinned_legacy_function_runs_without_importing_other_old_module_code(monkeypatch):
    source = (
        b"raise RuntimeError('Unrelated module top level must not execute')\n"
        b"def build_initial_query(case: CaseState, user_message: str) -> str:\n"
        b"    return case.case_id + ':' + user_message\n"
    )
    monkeypatch.setattr(comparison.subprocess, "check_output", lambda *args, **kwargs: source)
    function = comparison.load_legacy_query(
        {
            "baseline_commit": "registered-test",
            "baseline_engine_sha256": hashlib.sha256(source).hexdigest(),
        }
    )
    assert function(comparison.CaseState(case_id="unit"), "latest") == "unit:latest"


class Collection:
    def __init__(self):
        self.calls = []
        self.metadata = {"snapshot_id": "unit"}
        self.result = {"ids": [["source-row"]], "distances": [[0.75]]}

    def query(self, **arguments):
        self.calls.append(deepcopy(arguments))
        return deepcopy(self.result)


def test_collection_observer_preserves_exact_request_result_and_distance():
    collection, records = Collection(), []
    observed = comparison.RecordingCollection(collection, "streamlit_docs", records)
    result = observed.query(query_texts=["current_version=1.49.0"], n_results=1)
    assert collection.calls == [{"query_texts": ["current_version=1.49.0"], "n_results": 1}]
    assert result == collection.result
    assert records == [
        {
            "collection": "streamlit_docs",
            "query_texts": ["current_version=1.49.0"],
            "n_results": 1,
            "where": None,
            "returned_ids": [["source-row"]],
            "distances": [[0.75]],
        }
    ]
    result["ids"][0][0] = "caller-mutated"
    assert records[0]["returned_ids"] == [["source-row"]]


def test_collection_failure_does_not_fabricate_successful_query_observation():
    class FailingCollection(Collection):
        def query(self, **arguments):
            raise ValueError("unit backend failure")

    records = []
    observed = comparison.RecordingCollection(FailingCollection(), "streamlit_docs", records)
    with pytest.raises(ValueError):
        observed.query(query_texts=["current"], n_results=1)
    assert records == []


def test_existing_output_is_rejected_before_comparison_or_index_open(tmp_path, monkeypatch):
    output = tmp_path / "original.json"
    output.write_text("Preserved original artifact")
    monkeypatch.setattr(comparison, "index_ports", lambda *_: pytest.fail("No index open"))
    with pytest.raises(ValueError, match="^RetrievalComparisonOutputExists$"):
        comparison.main(["--output", str(output)])
    assert output.read_text() == "Preserved original artifact"


def literal_expectations(**changes):
    return {
        "must_contain": ["streamlit_version=1.49.0"],
        "must_not_contain": ["1.50.0"],
        "latest_needles": ["Current correction"],
        "topic_needles": ["multiselect"],
        "reasoning_contains": ["1.50.0"],
        **changes,
    }


def test_literal_controls_keep_latest_topic_and_retired_values_separate():
    checks = comparison.query_checks(
        "streamlit_version=1.49.0 | Current correction | topic: multiselect", literal_expectations()
    )
    assert all(row["passed"] for row in checks)
    contaminated = comparison.query_checks(
        "streamlit_version=1.49.0 Current correction multiselect old 1.50.0", literal_expectations()
    )
    assert [row["control"] for row in contaminated if not row["passed"]] == ["must_not_contain/1"]
    latest_only = comparison.query_checks(
        "streamlit_version=1.49.0 Current correction", literal_expectations()
    )
    assert [row["control"] for row in latest_only if not row["passed"]] == ["topic_needles/1"]


def test_authored_latest_old_new_comparison_is_not_reclassified_as_stale_contamination():
    expected = literal_expectations(
        must_contain=["1.50.0", "1.49.0"],
        must_not_contain=[],
        latest_needles=['old = "1.50.0"'],
        topic_needles=[],
    )
    controls = comparison.query_checks('Compare 1.50.0 and 1.49.0; old = "1.50.0"', expected)
    assert all(row["passed"] for row in controls)


def synthetic_state(pins):
    state = deepcopy(pins)
    state["protocol"].update(
        protocol_id="unit-query-context",
        variants=list(comparison.VARIANTS),
        quality_claim=False,
        real_api_calls=0,
        final_evaluation_cases=0,
        baseline_commit="unit-baseline",
        baseline_engine_sha256="unit-source",
        scope="Initial-query unit control only",
        index={"snapshot_id": "unit"},
    )
    state["fixture"].update(
        fixture_id="unit-fixture",
        provenance={
            "quality_claim": False,
            "final_evaluation_case_count": 0,
            "exposed_development_only": True,
        },
        scenarios=[
            {
                "id": "unit-correction",
                "case_state": {
                    "case_id": "unit-case",
                    "case_revision": 2,
                    "facts": [
                        {
                            "name": "streamlit_version",
                            "value": "1.49.0",
                            "source_ref": "user:latest",
                            "turn_id": "latest",
                            "provenance_kind": "user",
                            "status": "active",
                        }
                    ],
                },
                "conversation": {
                    "entries": [
                        {
                            "actor": "user",
                            "reference_id": "initial",
                            "revision": 1,
                            "text": "My multiselect resets in Streamlit 1.50.0.",
                        },
                        {
                            "actor": "user",
                            "reference_id": "latest",
                            "revision": 2,
                            "text": "Current correction: Streamlit 1.49.0.",
                        },
                    ],
                    "latest_turn_id": "latest",
                    "committed_revision": 2,
                    "latest_message": "Current correction: Streamlit 1.49.0.",
                },
                "expectations": literal_expectations(),
            }
        ],
    )
    return state


def test_validate_only_does_not_compose_queries_or_open_index(pins, monkeypatch):
    state = synthetic_state(pins)
    monkeypatch.setattr(comparison, "registration", lambda *_: state)
    monkeypatch.setattr(
        comparison, "load_legacy_query", lambda *_: lambda *_args: pytest.fail("No legacy query")
    )
    monkeypatch.setattr(comparison, "current_query", lambda *_: pytest.fail("No candidate query"))
    monkeypatch.setattr(comparison, "index_ports", lambda *_: pytest.fail("No index open"))
    result = comparison.compare(index_path=Path("unused"), validate_only=True)
    assert result["comparison_executed"] is result["index_queried"] is False


def test_synthetic_composition_reports_failures_without_retuning_controls(pins, monkeypatch):
    state = synthetic_state(pins)
    monkeypatch.setattr(comparison, "registration", lambda *_: state)
    monkeypatch.setattr(
        comparison,
        "load_legacy_query",
        lambda *_: lambda case, message: comparison.build_initial_query(case, message),
    )
    monkeypatch.setattr(comparison, "index_ports", lambda *_: pytest.fail("No implicit index open"))
    result = comparison.compare()
    assert result["quality_claim"] is result["model_decisions_compared"] is False
    assert result["final_evaluation_cases"] == result["real_api_calls"] == 0
    assert result["summaries"]["legacy_history_prefix"]["controls_failed"] > 0
    assert result["summaries"]["latest_only"]["topic_coverage"] == 0
    assert result["summaries"]["current_state_topics"]["scenarios_all_controls"] == 1
    variants = result["observations"][0]["variants"]
    assert len({row["reasoning_sha256"] for row in variants.values()}) == 1
    assert all(row["exact_reasoning_preserved"] for row in variants.values())


def test_mismatched_case_conversation_revision_is_rejected_before_composition(pins, monkeypatch):
    state = synthetic_state(pins)
    state["fixture"]["scenarios"][0]["case_state"]["case_revision"] = 99
    monkeypatch.setattr(comparison, "registration", lambda *_: state)
    monkeypatch.setattr(
        comparison, "current_query", lambda *_: pytest.fail("No invalid candidate query")
    )
    with pytest.raises(ValueError, match="^RetrievalComparisonConversationMismatch$"):
        comparison.compare()


def test_unverified_index_manifest_is_rejected_before_storage_open(tmp_path, monkeypatch):
    (tmp_path / "pilot-manifest.json").write_text("Unregistered manifest")
    monkeypatch.setattr(comparison, "open_verified_index", lambda *_: pytest.fail("No index open"))
    with pytest.raises(ValueError, match="^RetrievalComparisonIndexChanged$"):
        comparison.index_ports(tmp_path, {"index": {"manifest_sha256": "0" * 64}})


@pytest.mark.parametrize("corrupt", [False, True])
def test_returned_source_scope_and_distance_observation_keeps_physical_query(corrupt):
    records = []
    protocol = {"index": {"snapshot_id": "unit", "top_k": 1}}

    class Adapter:
        def search(self, request):
            for name in ("streamlit_docs", "streamlit_issues"):
                records.append(
                    {
                        "collection": name,
                        "query_texts": ["wrong"] if corrupt else list(request.queries),
                        "where": None,
                        "returned_ids": [["source"]] if name.endswith("docs") else [[]],
                        "distances": [[0.25]] if name.endswith("docs") else [[]],
                    }
                )
            return EvidenceBundle(
                snapshot_id="unit",
                queries_used=request.queries,
                hits=(
                    EvidenceHit(
                        chunk_id="source",
                        source_id="doc:unit",
                        source_type="doc",
                        source_url="https://example.org/unit",
                        source_span="unit-source-span",
                        excerpt="Unit source text",
                        applicable_versions=("1.49.0",),
                    ),
                ),
            )

    if corrupt:
        with pytest.raises(ValueError, match="^RetrievalComparisonQueryChanged$"):
            comparison.retrieve_query(Adapter(), records, "current", protocol)
    else:
        result = comparison.retrieve_query(Adapter(), records, "current", protocol)
        assert result["source_quality_measured"] is False
        assert result["returned_sources"][0]["applicable_versions"] == ["1.49.0"]
        assert result["verified_collection_reads"][0]["distances"] == [[0.25]]
        assert result["request"]["queries"] == ["current"]
