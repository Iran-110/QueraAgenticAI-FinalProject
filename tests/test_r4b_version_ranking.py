"""R4b regression controls for the PR50 review findings; offline, zero API.

Covers the three reviewed defects end to end through the real adapter and
engine: newest-first displacement of the current release, missing backend
over-fetch, and `since_version` treated as exact applicability. Version
labels below are synthetic metadata; no case/source-ID filter selects evidence.
"""

import importlib.util
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_chroma_retrieval_adapter import RawReadBackend, result, row

from agent_app.contracts import (
    AnalysisResult,
    CaseState,
    EvidenceBundle,
    EvidenceHit,
    Fact,
    RetrievalRequest,
)
from agent_app.orchestration import SupportEngine
from agent_app.retrieval.adapter import ChromaRetrieverAdapter
from agent_app.testing.fakes import FakeReasoner

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = "offline-adapter-snapshot"
QUERY = "st.multiselect st.button st.fragment default value"


def proposal():
    return AnalysisResult(
        decision="escalate",
        user_draft="The supplied sources do not establish the full application cause.",
        maintainer_summary="Version scope is tested without a generated model response.",
        rationale="A version filter does not establish source entailment.",
    )


def version_fact(value, *, status="active", turn="initial"):
    return Fact(
        name="streamlit_version",
        value=value,
        source_ref=f"user:{turn}",
        turn_id=turn,
        status=status,
    )


def case(*facts):
    return CaseState(case_id="r4b-case", facts=facts)


def versioned(chunk, source, version, excerpt):
    return row(
        chunk,
        source_id=source,
        excerpt=excerpt,
        applicable_versions=json.dumps([version]),
        version=version,
    )


# One complete record per release identity, plus one unversioned guide.
CORPUS = (
    versioned("button-139", "docstring:1.39.0:streamlit.button", "1.39.0", "st.button icon"),
    versioned(
        "multiselect-149",
        "docstring:1.49.0:streamlit.multiselect",
        "1.49.0",
        "st.multiselect default value",
    ),
    versioned(
        "multiselect-150",
        "docstring:1.50.0:streamlit.multiselect",
        "1.50.0",
        "st.multiselect default value",
    ),
    versioned("fragment-150", "docstring:1.50.0:streamlit.fragment", "1.50.0", "st.fragment"),
    versioned("text-input-164", "docstring:1.64.0:streamlit.text_input", "1.64.0", "st.text_input"),
    row("guide", source_id="docs:widget-behavior.md", excerpt="Widget default value behavior."),
)


def run(state, rows=CORPUS, *, top_k=5, multiplier=5, query=QUERY):
    backend = RawReadBackend({query: result(docs=rows)})
    adapter = ChromaRetrieverAdapter(
        "unused-offline-path",
        snapshot_id=SNAPSHOT,
        core_retriever=backend,
        selection_policy="query_relevance_v1",
    )
    reasoner = FakeReasoner([proposal()])
    engine = SupportEngine(
        adapter,
        reasoner,
        snapshot_id=SNAPSHOT,
        top_k=top_k,
        evidence_scope="exact_user_version",
        retrieval_candidate_multiplier=multiplier,
        evidence_utf8_budget_bytes=12000,
    )
    outcome = engine.run(state, "Synthetic reported problem.", initial_query=query)
    hits = reasoner.inputs[0][2].hits if reasoner.inputs else ()
    return outcome, backend, {hit.chunk_id for hit in hits}


def test_review_control_keeps_current_release_instead_of_newer_unrelated_releases():
    """The archived PR50 control: top_k=2, user 1.39.0, two later releases."""
    review = json.loads(
        (ROOT / "experiments/rag_pr50_review/review-head-7581dcc-v1.json").read_bytes()
    )["ranking_control"]
    rows = deepcopy(review["native_backend_rows"])
    query = review["request"]["queries"][0]

    class Backend:
        def __init__(self):
            self.calls = []

        def search(self, query, n_results=3, *, filters=None):
            self.calls.append((query, n_results))
            return deepcopy(rows)

    backend = Backend()
    reasoner = FakeReasoner([proposal()])
    engine = SupportEngine(
        ChromaRetrieverAdapter(
            "", snapshot_id=SNAPSHOT, core_retriever=backend, selection_policy="query_relevance_v1"
        ),
        reasoner,
        snapshot_id=SNAPSHOT,
        top_k=2,
        evidence_scope="exact_user_version",
        retrieval_candidate_multiplier=5,
    )
    engine.run(CaseState.model_validate(review["case"]), "Synthetic.", initial_query=query)
    assert backend.calls == [(query, 10)]
    assert [hit.chunk_id for hit in reasoner.inputs[0][2].hits] == ["current"]


@pytest.mark.parametrize("top_k,expected", [(1, 5), (5, 25), (10, 50), (20, 50)])
def test_backend_actually_receives_bounded_overfetch(top_k, expected):
    _, backend, _ = run(case(version_fact("1.50.0")), top_k=top_k)
    assert [call[1] for call in backend.calls] == [expected]


def test_multiplier_one_keeps_legacy_backend_count():
    _, backend, _ = run(case(version_fact("1.50.0")), multiplier=1)
    assert [call[1] for call in backend.calls] == [5]


@pytest.mark.parametrize(
    "state,expected",
    [
        # Unknown version: no versioned record is presented as applicable.
        (case(), {"guide"}),
        # Older installation: newer releases are excluded, not ranked first.
        (case(version_fact("1.39.0")), {"button-139", "guide"}),
        (case(version_fact("1.49.0")), {"multiselect-149", "guide"}),
        (case(version_fact("1.50.0")), {"multiselect-150", "fragment-150", "guide"}),
        # A version with no indexed release keeps only unversioned material.
        (case(version_fact("1.31.1")), {"guide"}),
    ],
)
def test_final_evidence_matches_the_active_user_version(state, expected):
    outcome, _, final = run(state)
    assert outcome.status == "awaiting_approval"
    assert final == expected


def test_correction_replaces_scope_without_reusing_the_superseded_version():
    corrected = case(
        version_fact("1.50.0", status="superseded"),
        version_fact("1.49.0", turn="correction"),
    )
    _, _, final = run(corrected)
    assert final == {"multiselect-149", "guide"}


def test_relevant_current_release_survives_more_than_top_k_newer_records():
    """Five newer same-API releases cannot crowd out the user's 1.39.0 record."""
    newer = tuple(
        versioned(
            f"button-1{minor}",
            f"docstring:1.{minor}.0:streamlit.button",
            f"1.{minor}.0",
            "st.button icon",
        )
        for minor in range(50, 56)
    )
    rows = (*newer, CORPUS[0])
    outcome, backend, final = run(case(version_fact("1.39.0")), rows=rows, query="st.button icon")
    assert backend.calls[0][1] == 25
    assert final == {"button-139"}


@pytest.mark.parametrize(
    "metadata",
    [
        {"since_version": "1.39.0"},
        {"since_version": "1.39.0", "version": None},
        {"since_version": "1.39.0", "applicable_versions": "[]"},
    ],
)
def test_since_version_is_introduction_metadata_not_exact_applicability(metadata):
    since = row("since", source_id="docs:since.md", excerpt="st.multiselect", **metadata)
    # A 1.39.0 user must not receive it as an exact 1.39.0 record, and a
    # 1.50.0 user must not lose it as a mismatched exact record either.
    for version in ("1.39.0", "1.50.0"):
        _, _, final = run(case(version_fact(version)), rows=(since,), query="st.multiselect")
        assert final == {"since"}
    backend = RawReadBackend({"st.multiselect": result(docs=(since,))})
    bundle = ChromaRetrieverAdapter(
        "", snapshot_id=SNAPSHOT, core_retriever=backend, selection_policy="query_relevance_v1"
    ).search(RetrievalRequest(queries=("st.multiselect",), snapshot_id=SNAPSHOT))
    assert bundle.hits[0].applicable_versions == ()


@pytest.fixture
def receipt_control(tmp_path, monkeypatch):
    """Synthetic native-like files and an injected client; no Chroma import/read."""
    spec = importlib.util.spec_from_file_location(
        "r4b_receipt_control", ROOT / "scripts/r4b_version_ranking_receipt.py"
    )
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    index = tmp_path / "sealed-index"
    index.mkdir()
    files = {
        "pilot-manifest.json": b'{"synthetic":true}\n',
        "chroma.sqlite3": b"synthetic sqlite bytes; never a real database",
        "segment/header.bin": b"synthetic native header",
    }
    for name, content in files.items():
        target = index / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    archive = tmp_path / "archive.json"
    archive.write_text('{"batches":[]}', encoding="utf-8")
    registration = tmp_path / "registration.json"
    registration.write_text(
        json.dumps(
            {
                "indexes": {
                    "new_18_sources": {
                        "snapshot_id": SNAPSHOT,
                        "manifest_sha256": script.sha(files["pilot-manifest.json"]),
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(script, "ROOT", tmp_path)
    monkeypatch.setattr(script, "ARCHIVE", archive)
    monkeypatch.setattr(script, "REGISTRATION", registration)
    control = SimpleNamespace(
        script=script,
        index=index,
        files=files,
        paths=[],
        clients=[],
        require_copy=True,
        mutate_copy=False,
        mutate_original=False,
        failure=None,
    )

    class Native:
        def __init__(self, path):
            self.path, self.closed = path, False

        def close(self):
            self.closed = True

    def open_native(path):
        path = Path(path)
        control.paths.append(path)
        if control.require_copy:
            assert path != index, "Native clients must never open sealed storage"
        assert {name: (path / name).read_bytes() for name in files} == files
        native = Native(path)
        control.clients.append(native)
        if control.mutate_copy:
            (path / "chroma.sqlite3").write_bytes(b"simulated native read-time rewrite")
        return native

    class Verified:
        def __init__(self, path, native, corpus, raw):
            self._client = native
            if control.failure == "construction":
                raise RuntimeError("SyntheticVerificationFailure")

        def verify(self):
            if control.failure == "verify":
                raise RuntimeError("SyntheticVerificationFailure")
            if control.mutate_original:
                (index / "segment/header.bin").write_bytes(b"changed outside the replay")

    from agent_app.retrieval import offline_index

    monkeypatch.setattr(
        offline_index,
        "PilotCorpus",
        SimpleNamespace(from_manifest=lambda _: SimpleNamespace(snapshot_id=SNAPSHOT)),
    )
    monkeypatch.setattr(offline_index, "_persistent_client", open_native)
    monkeypatch.setattr(offline_index, "VerifiedChromaClient", Verified)
    return control


def test_receipt_native_reads_use_a_disposable_copy_and_preserve_every_original_file(
    receipt_control,
):
    control = receipt_control
    control.mutate_copy = True
    receipt = control.script.probe(control.index, None)
    expected = {name: control.script.sha(content) for name, content in control.files.items()}
    assert receipt["index"]["original_physical_files_before"] == expected
    assert receipt["index"]["original_physical_files_after"] == expected
    assert receipt["index"]["native_reads_disposable_copy_only"] is True
    assert receipt["index"]["unchanged"] is True
    assert {name: (control.index / name).read_bytes() for name in control.files} == control.files
    assert all(native.closed for native in control.clients)
    assert all(not path.exists() for path in control.paths)


def test_receipt_rejects_a_physical_change_even_when_the_manifest_is_unchanged(receipt_control):
    control = receipt_control
    control.require_copy = False
    control.mutate_original = True
    with pytest.raises(SystemExit) as error:
        control.script.probe(control.index, None)
    diagnostic = json.loads(str(error.value))
    assert diagnostic["error_code"] == "OriginalIndexChangedDuringReplay"
    assert diagnostic["changed_files"] == ["segment/header.bin"]
    assert diagnostic["before_sha256"] == {
        "segment/header.bin": control.script.sha(control.files["segment/header.bin"])
    }
    assert diagnostic["after_sha256"] == {
        "segment/header.bin": control.script.sha(b"changed outside the replay")
    }
    assert (control.index / "pilot-manifest.json").read_bytes() == control.files[
        "pilot-manifest.json"
    ]
    assert all(native.closed for native in control.clients)
    assert all(not path.exists() for path in control.paths)


@pytest.mark.parametrize("failure", ["construction", "verify"])
def test_receipt_closes_native_client_and_removes_copy_after_verification_failure(
    receipt_control, failure
):
    control = receipt_control
    control.require_copy = False
    control.failure = failure
    with pytest.raises(RuntimeError, match="SyntheticVerificationFailure"):
        control.script.probe(control.index, None)
    assert control.clients and all(native.closed for native in control.clients)
    assert all(not path.exists() for path in control.paths)
    assert {name: (control.index / name).read_bytes() for name in control.files} == control.files


def test_receipt_selection_diagnostics_separate_byte_packing_from_the_count_cap(
    receipt_control, monkeypatch
):
    script = receipt_control.script
    hits = tuple(
        EvidenceHit(
            chunk_id=name,
            source_id=f"docs:{name}",
            source_type="doc",
            source_url="https://docs.streamlit.io/develop",
            excerpt=text,
        )
        for name, text in (("first", "x" * 1000), ("too-large", "y" * 1000), ("small", "short"))
    )

    class Adapter:
        def __init__(self, *args, **kwargs):
            pass

        def search(self, request):
            return EvidenceBundle(snapshot_id=SNAPSHOT, hits=hits, queries_used=request.queries)

    monkeypatch.setattr(script, "RecordingBackend", lambda *_: SimpleNamespace(calls=[]))
    data = script.run_arm(
        "synthetic",
        Adapter,
        None,
        5,
        2048,
        None,
        SNAPSHOT,
        {"case": case(), "case_id": "synthetic", "round": 1, "queries": ("synthetic",)},
    )
    replay = data["selection_replay"]
    assert replay["matches_actual_final"] is True
    assert replay["final_count_cap_reached"] is False
    assert [item["eligible_rank"] for item in replay["candidates"]] == [1, 2, 3]
    assert [item["decision"] for item in replay["candidates"]] == [
        "selected",
        "byte_budget_exceeded",
        "selected",
    ]
    assert [hit["chunk_id"] for hit in data["final_hits"]] == ["first", "small"]
