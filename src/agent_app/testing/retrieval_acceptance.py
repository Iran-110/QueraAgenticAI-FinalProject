"""Reusable retrieval-port acceptance with fixed evidence and no real index.

Factories receive only a read backend and its configured snapshot. Expected
decisions/reviews remain in the runner. A candidate binding must inject this
backend into the actual adapter, retaining its production mapping/search code.
"""

import hashlib
import inspect
import json
from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_app.contracts import (
    AnalysisResult,
    CaseState,
    EvidenceBundle,
    EvidenceHit,
    RetrievalRequest,
)
from agent_app.orchestration.engine import SupportEngine
from agent_app.orchestration.ports import Retriever
from agent_app.testing.fakes import FakeReasoner

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FIXTURE = ROOT / "experiments/retrieval_acceptance/fixture-v1.json"
PRIVATE_SENTINEL = "PRIVATE_FIXTURE_BACKEND_ERROR"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class FixtureReadBackend:
    """Canonical fixed rows; query order is authored, not a relevance metric.

    select_round is controlled only by the capture harness, never the adapter.
    Returned rows are detached. Calls stay in memory; receipts export counts
    and predefined checks rather than raw query/error text.
    """

    def __init__(self, fixture, round_ids=None, fault=None):
        self.rows = {hit["chunk_id"]: deepcopy(hit) for hit in fixture["hits"]}
        self.query_results = deepcopy(fixture["query_results"])
        self.round_ids = round_ids
        self.fault = fault
        self.round = 0
        self.calls: list[dict] = []

    def select_round(self, index: int) -> None:
        if self.round_ids is not None and index >= len(self.round_ids):
            raise RuntimeError("FixtureRoundExhausted")
        self.round = index

    def search(
        self,
        query: str,
        *,
        top_k: int,
        filters: Mapping[str, str | tuple[str, ...]] | None = None,
    ) -> list[dict]:
        if type(query) is not str or type(top_k) is not int or not 1 <= top_k <= 50:
            raise ValueError("InvalidFixtureBackendRequest")
        filters = dict(filters or {})
        if filters:
            raise ValueError("UnsupportedFixtureFilter")
        self.calls.append({"query": query, "top_k": top_k, "filters": filters, "round": self.round})
        if self.fault == "failure":
            raise RuntimeError(PRIVATE_SENTINEL)
        ids = (
            self.round_ids[self.round]
            if self.round_ids is not None
            else self.query_results.get(query, ())
        )
        rows = [deepcopy(self.rows[chunk]) for chunk in ids[:top_k]]
        if self.fault == "malformed_url":
            rows[0]["source_url"] = "not-a-url"
        if self.fault == "unknown_metadata":
            for row in rows:
                row.update(
                    source_commit=None,
                    source_span=None,
                    applicable_versions=[],
                    score=None,
                    score_kind=None,
                )
        if self.fault in {"boundary", "oversize"}:
            rows = [
                {
                    "chunk_id": "synthetic:excerpt-boundary",
                    "source_id": "synthetic:excerpt-boundary",
                    "excerpt": "x" * (20_000 if self.fault == "boundary" else 20_001),
                    "source_url": "https://example.org/offline-rag-boundary",
                    "source_type": "doc",
                    "source_span": "Authored character-boundary fixture; no real source claim.",
                    "source_commit": None,
                    "applicable_versions": [],
                }
            ]
        return rows


@dataclass(frozen=True)
class RetrievalProbe:
    snapshot_id: str
    backend: FixtureReadBackend


type AdapterFactory = Callable[[RetrievalProbe], Retriever]


def build_probe(
    fixture: dict,
    *,
    round_ids: tuple[tuple[str, ...], ...] | None = None,
    fault: str | None = None,
) -> RetrievalProbe:
    return RetrievalProbe(fixture["snapshot_id"], FixtureReadBackend(fixture, round_ids, fault))


class FixtureRetriever:
    """Reference fixture port only; not an implementation of production RAG."""

    def __init__(self, probe: RetrievalProbe):
        self.probe = probe

    def search(self, request: RetrievalRequest) -> EvidenceBundle:
        if request.snapshot_id != self.probe.snapshot_id:
            raise ValueError("FixtureSnapshotMismatch")
        hits = {}
        for query in request.queries:
            rows = self.probe.backend.search(query, top_k=request.top_k, filters=request.filters)
            for row in rows:
                hit = EvidenceHit.model_validate(row)
                hits.setdefault(hit.chunk_id, hit)
        return EvidenceBundle(
            snapshot_id=self.probe.snapshot_id,
            hits=tuple(hits.values())[: request.top_k],
            queries_used=request.queries,
        )


def fixture_factory(probe: RetrievalProbe) -> Retriever:
    return FixtureRetriever(probe)


class CapturedRetriever:
    """Observe the actual port result without fixing or validating it for core."""

    def __init__(self, factory: AdapterFactory, probe: RetrievalProbe):
        self.probe = probe
        self.delegate = factory(probe)
        if not callable(getattr(self.delegate, "search", None)):
            raise ValueError("AdapterPortMissing")
        self.requests: list[RetrievalRequest] = []
        self.outputs: list[EvidenceBundle] = []

    def search(self, request: RetrievalRequest):
        self.probe.backend.select_round(len(self.requests))
        self.requests.append(request.model_copy(deep=True))
        result = self.delegate.search(request)
        if isinstance(result, EvidenceBundle):
            self.outputs.append(result.model_copy(deep=True))
        return result


def load_fixture(path: Path = DEFAULT_FIXTURE) -> dict:
    fixture = json.loads(path.read_bytes())
    # These are registered inputs, not a corpus builder. Keep original sources
    # and exposure labels inspectable; no fixture oracle reaches a factory.
    for entry in fixture["provenance"]["source_refs"]:
        if _sha((ROOT / entry["path"]).read_bytes()) != entry["sha256"]:
            raise ValueError("AcceptanceSourceChanged")
    EvidenceBundle(snapshot_id=fixture["snapshot_id"], hits=fixture["hits"])
    source = json.loads((ROOT / fixture["provenance"]["source_refs"][0]["path"]).read_bytes())
    canonical = source["evidence_bundles"]["official-mixed"]["hits"]
    if fixture["hits"] != canonical:
        raise ValueError("AcceptanceEvidenceChanged")
    if fixture["boundaries"]["quality_claim"] is not False:
        raise ValueError("AcceptanceBoundaryInvalid")
    return fixture


def _factory_identity(factory) -> dict:
    try:
        subject = (
            factory if inspect.isfunction(factory) or inspect.isclass(factory) else type(factory)
        )
        path = inspect.getsourcefile(subject)
        fingerprint = _sha(Path(path).read_bytes()) if path else None
    except (TypeError, OSError):
        fingerprint = None
    return {
        "module": getattr(factory, "__module__", "unknown"),
        "name": getattr(factory, "__qualname__", type(factory).__name__),
        "source_sha256": fingerprint,
        "source_available": fingerprint is not None,
    }


def _question() -> AnalysisResult:
    question = "Which Streamlit version is installed in the affected environment?"
    return AnalysisResult(
        decision="ask",
        user_draft=question,
        next_question=question,
        missing_info=("streamlit_version",),
        maintainer_summary="Authored acceptance question; no model judgment.",
        rationale="Authored acceptance question; no model judgment.",
    )


def run_acceptance(
    factory: AdapterFactory = fixture_factory,
    *,
    fixture_path: Path = DEFAULT_FIXTURE,
    include_pilot: bool = True,
) -> dict:
    """Run the same protocol with the reference or a caller-bound real adapter.

    Ranking is not prescribed. Every returned hit must faithfully preserve a
    selected fixture source; optional unknown metadata remains unknown.
    Malformed indexed data fail closed in these registered fault scenarios.
    """
    fixture = load_fixture(fixture_path)
    checks: dict[str, bool] = {}
    cases = []
    identities = []
    probes = []

    def check(name, condition):
        checks[name] = bool(condition)

    def adapter(probe):
        port = CapturedRetriever(factory, probe)
        identities.append(_factory_identity(type(port.delegate)))
        probes.append(probe)
        return port

    def scenario(name, execute):
        previous = set(checks)
        error = None
        try:
            execute()
        except Exception:
            check(f"{name}:completed", False)
            error = "AdapterAcceptanceFailed"
        selected = {key: value for key, value in checks.items() if key not in previous}
        cases.append(
            {
                "id": name,
                "status": "passed" if selected and all(selected.values()) else "failed",
                "error_code": error,
            }
        )

    queries = fixture["probe_queries"]
    expected = {
        hit.chunk_id: hit
        for hit in EvidenceBundle(snapshot_id=fixture["snapshot_id"], hits=fixture["hits"]).hits
    }

    def direct(name, selected_queries, top_k, fault=None):
        probe = build_probe(fixture, fault=fault)
        port = adapter(probe)
        request = RetrievalRequest(
            queries=tuple(selected_queries), snapshot_id=probe.snapshot_id, top_k=top_k
        )
        before = request.model_dump(mode="json")
        raw = port.search(request)
        check(f"{name}:typed_bundle", isinstance(raw, EvidenceBundle))
        bundle = EvidenceBundle.model_validate(
            raw.model_dump(warnings=False) if isinstance(raw, EvidenceBundle) else raw
        )
        check(f"{name}:request_unchanged", request.model_dump(mode="json") == before)
        check(f"{name}:snapshot", bundle.snapshot_id == probe.snapshot_id)
        check(f"{name}:global_top_k", len(bundle.hits) <= top_k)
        check(f"{name}:unique_ids", len({h.chunk_id for h in bundle.hits}) == len(bundle.hits))
        used = tuple(call["query"] for call in probe.backend.calls)
        check(f"{name}:queries_consumed", set(used) == set(selected_queries))
        check(f"{name}:queries_used", set(bundle.queries_used) == set(used))
        candidates = {
            chunk for query in selected_queries for chunk in fixture["query_results"].get(query, ())
        }
        expected_count = 1 if fault == "boundary" else min(top_k, len(candidates))
        check(f"{name}:result_count", len(bundle.hits) == expected_count)
        if fault == "unknown_metadata":
            check(
                f"{name}:metadata",
                bool(bundle.hits)
                and all(
                    h.source_commit is None
                    and h.source_span is None
                    and h.applicable_versions == ()
                    and h.score is None
                    and h.score_kind is None
                    and h.excerpt == expected[h.chunk_id].excerpt
                    and h.source_url == expected[h.chunk_id].source_url
                    and h.source_id == expected[h.chunk_id].source_id
                    and h.source_type == expected[h.chunk_id].source_type
                    for h in bundle.hits
                ),
            )
        elif fault == "boundary":
            boundary_hit = EvidenceHit(
                chunk_id="synthetic:excerpt-boundary",
                source_id="synthetic:excerpt-boundary",
                excerpt="x" * 20_000,
                source_url="https://example.org/offline-rag-boundary",
                source_type="doc",
                source_span="Authored character-boundary fixture; no real source claim.",
            )
            check(
                f"{name}:exact_excerpt",
                bundle.hits == (boundary_hit,),
            )
        else:
            check(f"{name}:metadata", all(h == expected.get(h.chunk_id) for h in bundle.hits))
        if name == "empty":
            check("empty:hits", bundle.hits == ())

    def stopped(name, fault=None, *, snapshot=None):
        probe = build_probe(fixture, fault=fault)
        port = adapter(probe)
        if name == "response_snapshot":

            class WrongResponseSnapshot:
                def search(self, request):
                    output = port.search(request)
                    return (
                        output.model_copy(update={"snapshot_id": "authored-wrong-snapshot"})
                        if isinstance(output, EvidenceBundle)
                        else output
                    )

            engine_port = WrongResponseSnapshot()
        else:
            engine_port = port
        reasoner = FakeReasoner([_question()])
        result = SupportEngine(
            engine_port, reasoner, snapshot_id=snapshot or probe.snapshot_id
        ).run(CaseState(case_id=f"acceptance-{name}"), queries["single"])
        check(
            f"{name}:stop_before_model",
            result.status == "error"
            and result.error_code in {"RetrievalUnavailable", "RetrievalResultInvalid"}
            and result.model_attempts == 0
            and not reasoner.inputs,
        )
        check(f"{name}:safe_diagnostics", PRIVATE_SENTINEL not in result.model_dump_json())
        if name == "snapshot":
            check("snapshot:no_backend_calls", probe.backend.calls == [])

    scenario("single", lambda: direct("single", [queries["single"]], 5))
    scenario("multi", lambda: direct("multi", queries["multi"], 5))
    scenario("cap", lambda: direct("cap", queries["multi"], 1))
    for registered_id, name in (
        ("known-version-release-source", "known_version"),
        ("corrected-version-latest-bundle", "corrected_version"),
    ):
        registered = next(s for s in fixture["scenarios"] if s["id"] == registered_id)
        scenario(
            name,
            lambda name=name, registered=registered: direct(
                name, registered["request"]["queries"], registered["request"]["top_k"]
            ),
        )
    scenario("unknown", lambda: direct("unknown", [queries["single"]], 5, "unknown_metadata"))
    scenario("empty", lambda: direct("empty", [queries["empty"]], 5))
    scenario("boundary", lambda: direct("boundary", [queries["single"]], 5, "boundary"))
    scenario("oversize", lambda: stopped("oversize", "oversize"))
    scenario("malformed_url", lambda: stopped("malformed_url", "malformed_url"))
    scenario("failure", lambda: stopped("failure", "failure"))
    scenario("snapshot", lambda: stopped("snapshot", snapshot="wrong-configured-snapshot"))
    scenario("response_snapshot", lambda: stopped("response_snapshot"))

    pilot = None
    if include_pilot:

        def execute_pilot():
            nonlocal pilot
            from agent_app.testing.retrieval_acceptance_pilot import run_pilot

            with TemporaryDirectory(prefix="rag-acceptance-sqlite-") as directory:
                pilot = run_pilot(factory, fixture, Path(directory) / "case.sqlite3")
            for name, value in pilot["checks"].items():
                check(f"pilot:{name}", value)

        scenario("core_pilot", execute_pilot)

    return {
        "schema_version": 1,
        "protocol": "retrieval-core-acceptance-v1",
        "accepted": bool(checks) and all(checks.values()),
        "checks": checks,
        "checks_passed": sum(checks.values()),
        "checks_total": len(checks),
        "cases": cases,
        "factory": _factory_identity(factory),
        "delegate_sources": identities,
        "fixture_sha256": _sha(fixture_path.read_bytes()),
        "source_provenance": fixture["provenance"],
        "fixture_backend_calls": sum(len(probe.backend.calls) for probe in probes),
        "pilot": pilot,
        "mode": "reference_fixture_adapter"
        if factory is fixture_factory
        else "candidate_adapter_with_fixture_backend",
        "quality_claim": False,
        "fixture_backend": True,
        "production_index_or_embedding_tested": False,
        "real_model_tested": False,
        "actual_cost_usd": 0,
        "limitations": [
            "Fixed evidence and authored backend ordering; no retrieval relevance or model quality measurement.",
            "A candidate binding must retain the actual adapter mapping and inject only its read backend.",
            "HTTP, persistence lifecycle CAS/journal, ingestion segmentation, and final corpus exclusion are not covered.",
            "Nonempty request filters are not covered by this protocol.",
        ],
    }
