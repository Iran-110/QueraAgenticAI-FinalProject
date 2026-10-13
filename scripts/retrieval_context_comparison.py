"""Compare registered initial-query composition without model or ledger calls.

Legacy history-prefix, latest-only and current-state/topic query variants use
the same committed state and conversation. Optional retrieval reads only an
existing verified pilot index. Returned ranks are observations, not RAG quality.
"""

import argparse
import ast
import hashlib
import json
import subprocess
from copy import deepcopy
from functools import partial
from pathlib import Path

from agent_app.contracts import CaseState, RetrievalRequest, TurnConversation
from agent_app.orchestration.conversation import build_reasoning_message
from agent_app.orchestration.engine import build_initial_query
from agent_app.retrieval.adapter import ChromaRetrieverAdapter
from agent_app.retrieval.offline_index import open_verified_index
from agent_app.retrieval.retriever import StreamlitRetriever
from agent_app.testing.http_pilot_runtime import offline_network

ROOT = Path(__file__).resolve().parents[1]
REGISTERED = ROOT / "experiments/retrieval_context"
SCRIPT = Path(__file__).resolve()
VARIANTS = ("legacy_history_prefix", "latest_only", "current_state_topics")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_pins():
    return {
        str(path.relative_to(ROOT)): digest(path)
        for path in sorted((ROOT / "src/agent_app").rglob("*.py"))
    }


def load_legacy_query(protocol):
    """Execute only the exact pinned repository function, with current contracts.

    This does not replay an old whole release. No downloaded/user/source snippet
    is executable input; the sole function comes from a registered Git commit.
    """
    raw = subprocess.check_output(
        ["git", "show", protocol["baseline_commit"] + ":src/agent_app/orchestration/engine.py"],
        cwd=ROOT,
    )
    if hashlib.sha256(raw).hexdigest() != protocol["baseline_engine_sha256"]:
        raise ValueError("RetrievalComparisonBaselineChanged")
    functions = [
        node
        for node in ast.parse(raw).body
        if isinstance(node, ast.FunctionDef) and node.name == "build_initial_query"
    ]
    if len(functions) != 1 or functions[0].decorator_list:
        raise ValueError("RetrievalComparisonBaselineChanged")
    module = ast.Module(body=functions, type_ignores=[])
    namespace = {"CaseState": CaseState}
    exec(compile(module, "registered-legacy-query", "exec"), namespace)
    return namespace["build_initial_query"]


def registration(protocol_path=None):
    protocol_path = protocol_path or REGISTERED / "protocol-v1.json"
    raw = protocol_path.read_bytes()
    protocol = json.loads(raw)
    fixture_path = REGISTERED / "fixture-v1.json"
    paths = {"protocol": protocol_path, "fixture": fixture_path, "comparison_script": SCRIPT}
    pins = {name: digest(path) for name, path in paths.items()}
    if (
        pins["protocol"] != hashlib.sha256(raw).hexdigest()
        or pins["fixture"] != protocol["fixture_sha256"]
        or pins["comparison_script"] != protocol["script_sha256"]
    ):
        raise ValueError("RetrievalComparisonRegistrationChanged")
    fixture = json.loads(fixture_path.read_bytes())
    state = {
        "protocol": protocol,
        "fixture": fixture,
        "paths": paths,
        "pins": pins,
        "source_pins": source_pins(),
    }
    check_registration(state)
    return state


def check_registration(state):
    if {name: digest(path) for name, path in state["paths"].items()} != state["pins"]:
        raise ValueError("RetrievalComparisonRegistrationChanged")
    if source_pins() != state["source_pins"]:
        raise ValueError("RetrievalComparisonSourceChanged")


def current_query(case, conversation):
    from agent_app.orchestration.retrieval_context import build_current_query

    return build_current_query(case, conversation)


class RecordingCollection:
    """Observe the verified collection seam; never substitute rows or queries."""

    def __init__(self, collection, name, records):
        self.collection, self.name, self.records = collection, name, records

    @property
    def metadata(self):
        return self.collection.metadata

    def query(self, *, query_texts, n_results, where=None):
        arguments = {"query_texts": deepcopy(query_texts), "n_results": n_results}
        if where is not None:
            arguments["where"] = deepcopy(where)
        result = self.collection.query(**arguments)
        self.records.append(
            {
                "collection": self.name,
                "query_texts": list(query_texts),
                "n_results": n_results,
                "where": deepcopy(where),
                "returned_ids": deepcopy(result["ids"]),
                "distances": deepcopy(result["distances"]),
            }
        )
        return result


class RecordingClient:
    def __init__(self, verified, records):
        self.verified, self.records = verified, records

    def get_collection(self, *, name):
        return RecordingCollection(self.verified.get_collection(name=name), name, self.records)


def index_ports(index_path, protocol):
    expected = protocol["index"]
    manifest_path = index_path / "pilot-manifest.json"
    if digest(manifest_path) != expected["manifest_sha256"]:
        raise ValueError("RetrievalComparisonIndexChanged")
    verified, snapshot = open_verified_index(index_path)
    if snapshot != expected["snapshot_id"]:
        raise ValueError("RetrievalComparisonIndexChanged")
    records = []
    backend = StreamlitRetriever(
        base_path=str(index_path), snapshot_id=snapshot, client=RecordingClient(verified, records)
    )
    adapter = ChromaRetrieverAdapter(
        base_path=str(index_path), snapshot_id=snapshot, core_retriever=backend
    )
    return verified, adapter, records


def retrieve_query(adapter, records, query, protocol):
    first = len(records)
    request = RetrievalRequest(
        queries=(query,),
        snapshot_id=protocol["index"]["snapshot_id"],
        top_k=protocol["index"]["top_k"],
        filters={},
    )
    bundle = adapter.search(request)
    actual = records[first:]
    if (
        bundle.queries_used != request.queries
        or [row["collection"] for row in actual] != ["streamlit_docs", "streamlit_issues"]
        or any(row["query_texts"] != [query] or row["where"] is not None for row in actual)
    ):
        raise ValueError("RetrievalComparisonQueryChanged")
    return {
        "request": request.model_dump(mode="json"),
        "verified_collection_reads": deepcopy(actual),
        "returned_sources": [
            {
                "chunk_id": hit.chunk_id,
                "source_id": hit.source_id,
                "source_span": hit.source_span,
                "applicable_versions": list(hit.applicable_versions),
                "excerpt_sha256": hashlib.sha256(hit.excerpt.encode("utf-8")).hexdigest(),
            }
            for hit in bundle.hits
        ],
        "source_quality_measured": False,
    }


def validate_fixture(state):
    protocol, fixture = state["protocol"], state["fixture"]
    if (
        tuple(protocol["variants"]) != VARIANTS
        or protocol["quality_claim"] is not False
        or protocol["real_api_calls"] != 0
        or protocol["final_evaluation_cases"] != 0
        or fixture["provenance"]["quality_claim"] is not False
        or fixture["provenance"]["final_evaluation_case_count"] != 0
        or not fixture["provenance"]["exposed_development_only"]
    ):
        raise ValueError("RetrievalComparisonScopeChanged")
    identifiers = set()
    for scenario in fixture["scenarios"]:
        if scenario["id"] in identifiers:
            raise ValueError("RetrievalComparisonDuplicateScenario")
        identifiers.add(scenario["id"])
        case = CaseState.model_validate(scenario["case_state"])
        conversation = TurnConversation.model_validate(scenario["conversation"])
        if case.case_revision != conversation.committed_revision:
            raise ValueError("RetrievalComparisonConversationMismatch")
        # Conversation validation preserves exact raw history/code; it does not
        # compose or execute a retrieval query in validate-only mode.
        build_reasoning_message(conversation)
        expected = scenario["expectations"]
        for name in (
            "must_contain",
            "must_not_contain",
            "latest_needles",
            "topic_needles",
            "reasoning_contains",
        ):
            if not isinstance(expected[name], list) or any(
                not isinstance(value, str) or not value for value in expected[name]
            ):
                raise ValueError("RetrievalComparisonExpectationInvalid")
    if not identifiers:
        raise ValueError("RetrievalComparisonEmptyFixture")
    return len(identifiers)


def query_checks(query, expected):
    """Inspect declared literal controls only, without inferring semantic quality."""
    normalized = " ".join(query.split()).casefold()
    checks = [
        {"control": "query_shape_and_limit", "passed": bool(query.strip()) and len(query) <= 500}
    ]
    for name, presence in (
        ("must_contain", True),
        ("must_not_contain", False),
        ("latest_needles", True),
        ("topic_needles", True),
    ):
        for number, needle in enumerate(expected[name], 1):
            present = " ".join(needle.split()).casefold() in normalized
            checks.append({"control": f"{name}/{number}", "passed": present == presence})
    return checks


def version_scope_counts(sources, case):
    version = next(
        (
            fact.value
            for fact in case.facts
            if fact.name.casefold() == "streamlit_version"
            and fact.status == "active"
            and fact.provenance_kind == "user"
        ),
        None,
    )
    return {
        "active_user_version": version,
        "matching_active_user_version": sum(
            bool(version) and version in source["applicable_versions"] for source in sources
        ),
        "other_explicit_version": sum(
            bool(version)
            and bool(source["applicable_versions"])
            and version not in source["applicable_versions"]
            for source in sources
        ),
        "unversioned": sum(not source["applicable_versions"] for source in sources),
        "meaning": "Metadata scope counts only, not claim applicability or relevance scores.",
    }


def compare(protocol_path=None, *, index_path=None, validate_only=False):
    state = registration(protocol_path)
    scenario_count = validate_fixture(state)
    legacy_query = load_legacy_query(state["protocol"])
    header = {
        "schema_version": 1,
        "protocol_id": state["protocol"]["protocol_id"],
        "fixture_id": state["fixture"]["fixture_id"],
        "initial_input_sha256": state["pins"],
        "baseline_commit": state["protocol"]["baseline_commit"],
        "baseline_engine_sha256": state["protocol"]["baseline_engine_sha256"],
        "current_source_sha256": state["source_pins"],
        "scope": state["protocol"]["scope"],
        "scenarios": scenario_count,
        "variants": list(VARIANTS),
        "quality_claim": False,
        "real_api_calls": 0,
        "paid_cost_usd": "0",
        "final_evaluation_cases": 0,
        "model_decisions_compared": False,
        "initial_query_only": True,
        "expectations": "Predeclared author literal controls; no human gold, "
        "semantic relevance, entailment, or decision-quality score.",
    }
    if validate_only:
        check_registration(state)
        return {**header, "comparison_executed": False, "index_queried": False}
    observations, summaries = (
        [],
        {
            variant: {
                "controls_passed": 0,
                "controls_failed": 0,
                "scenarios_all_controls": 0,
                "latest_coverage": 0,
                "topic_coverage": 0,
            }
            for variant in VARIANTS
        },
    )
    verified, adapter, records = None, None, None
    with offline_network():
        if index_path is not None:
            verified, adapter, records = index_ports(index_path, state["protocol"])
        for scenario in state["fixture"]["scenarios"]:
            check_registration(state)
            case = CaseState.model_validate(scenario["case_state"])
            conversation = TurnConversation.model_validate(scenario["conversation"])
            originals = (case.model_dump(mode="json"), conversation.model_dump(mode="json"))
            reasoning = build_reasoning_message(conversation)
            paired = {}
            composers = {
                "legacy_history_prefix": partial(legacy_query, case, reasoning),
                "latest_only": partial(build_initial_query, case, conversation.latest_message),
                "current_state_topics": partial(current_query, case, conversation),
            }
            for variant in VARIANTS:
                check_registration(state)
                query = composers[variant]()
                controls = query_checks(query, scenario["expectations"])
                preserved = (
                    originals
                    == (case.model_dump(mode="json"), conversation.model_dump(mode="json"))
                    and reasoning == build_reasoning_message(conversation)
                    and all(
                        needle in reasoning
                        for needle in scenario["expectations"]["reasoning_contains"]
                    )
                )
                controls.append(
                    {"control": "exact_reasoning_and_inputs_preserved", "passed": preserved}
                )
                paired[variant] = {
                    "query": query,
                    "query_characters": len(query),
                    "literal_controls": controls,
                    "exact_reasoning_preserved": preserved,
                    "reasoning_sha256": hashlib.sha256(reasoning.encode("utf-8")).hexdigest(),
                    "latest_raw_input_sha256": hashlib.sha256(
                        conversation.latest_message.encode("utf-8")
                    ).hexdigest(),
                }
                if adapter is not None:
                    returned = retrieve_query(adapter, records, query, state["protocol"])
                    returned["returned_version_scope_counts"] = version_scope_counts(
                        returned["returned_sources"], case
                    )
                    paired[variant]["existing_index"] = returned
                summary = summaries[variant]
                summary["controls_passed"] += sum(row["passed"] for row in controls)
                summary["controls_failed"] += sum(not row["passed"] for row in controls)
                summary["scenarios_all_controls"] += all(row["passed"] for row in controls)
                for group, field in (
                    ("latest_needles/", "latest_coverage"),
                    ("topic_needles/", "topic_coverage"),
                ):
                    summary[field] += all(
                        row["passed"] for row in controls if row["control"].startswith(group)
                    )
            observations.append({"scenario_id": scenario["id"], "variants": paired})
        if verified is not None:
            verified.verify()
            if (
                digest(index_path / "pilot-manifest.json")
                != state["protocol"]["index"]["manifest_sha256"]
            ):
                raise ValueError("RetrievalComparisonIndexChanged")
    check_registration(state)
    return {
        **header,
        "comparison_executed": True,
        "registered_inputs_and_sources_unchanged": True,
        "index_queried": index_path is not None,
        "index": state["protocol"]["index"] if index_path is not None else None,
        "verified_collection_reads": len(records) if records is not None else 0,
        "index_quality_measured": False,
        "summaries": summaries,
        "observations": observations,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=REGISTERED / "protocol-v1.json")
    parser.add_argument("--index", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--output", type=Path)
    options = parser.parse_args(argv)
    if options.output and options.output.exists():
        raise ValueError("RetrievalComparisonOutputExists")
    result = compare(
        options.protocol, index_path=options.index, validate_only=options.validate_only
    )
    if options.output:
        options.output.parent.mkdir(parents=True, exist_ok=True)
        with options.output.open("x", encoding="utf-8") as output:
            json.dump(result, output, ensure_ascii=False, indent=2, allow_nan=False)
            output.write("\n")
    aggregate_fields = (
        "protocol_id",
        "scenarios",
        "variants",
        "comparison_executed",
        "index_queried",
        "quality_claim",
        "real_api_calls",
        "paid_cost_usd",
        "final_evaluation_cases",
        "verified_collection_reads",
        "summaries",
    )
    print(
        json.dumps(
            {key: result[key] for key in aggregate_fields if key in result},
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
