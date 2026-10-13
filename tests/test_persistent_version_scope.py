"""Version filtering through durable HTTP with actual SQLite and offline ports."""

import pytest
from fastapi.testclient import TestClient

from agent_app import api
from agent_app.contracts import AnalysisResult, EvidenceBundle, EvidenceHit, EvidenceLink
from agent_app.persistent_api import create_app
from agent_app.testing.fakes import FakeReasoner, FakeRetriever
from agent_app.tracker.sqlite_tracker import SQLiteCaseTracker

CASE = "persistent-scope-case"
SNAPSHOT = "synthetic-persistent-version-snapshot"
REVIEWERS = {"fixture-maintainer": "public-offline-version-scope-review-token"}


def hit(name, versions=()):
    return EvidenceHit(
        chunk_id=name,
        source_id=f"source:{name}",
        excerpt="Synthetic text mentions 1.49.0; its applicable versions are metadata only.",
        source_url="https://example.org/synthetic-version-scope",
        source_type="doc",
        applicable_versions=versions,
    )


def escalation():
    return AnalysisResult(
        decision="escalate",
        user_draft="Please have a maintainer review the synthetic issue.",
        maintainer_summary="This authored fixture establishes no fix.",
        rationale="Source applicability and an actual resolution remain separate judgments.",
    )


def event(name="initial", revision=0, version="1.49.0", **extra):
    return {
        "message": "A multiselect loses its selection after a parent callback. Streamlit 1.49.0.",
        "scenario": "escalate",
        "turn_id": name,
        "expected_revision": revision,
        "reported_facts": [{"name": "streamlit_version", "value": version}]
        if version is not None
        else [],
        **extra,
    }


def runtime(tmp_path, hits, *, outputs=None, scope="exact_user_version", binding="scenario"):
    bundle = EvidenceBundle(snapshot_id=SNAPSHOT, hits=hits)
    outputs = outputs if outputs is not None else [escalation(), escalation()]
    retriever = FakeRetriever([bundle for _ in outputs])
    reasoner = FakeReasoner(outputs)
    calls = []
    tracker = SQLiteCaseTracker(tmp_path / "scope.sqlite3", reviewer_tokens=REVIEWERS)

    def ports(*arguments):
        calls.append(arguments)
        return api.RunAdapters(retriever, reasoner, snapshot_id=SNAPSHOT)

    options = {"adapters" if binding == "scenario" else "case_adapters": ports}
    if scope is not None:
        options["evidence_scope"] = scope
    app = create_app(tracker, reviewer_tokens=REVIEWERS, **options)
    return app, tracker, retriever, reasoner, calls, bundle


def send(client, payload=None):
    response = client.post(f"/cases/{CASE}/messages", json=payload or event())
    assert response.status_code == 200
    return response.json()


def supplied(reasoner, index=-1):
    return {source.chunk_id for source in reasoner.inputs[index][2].hits}


def scopes(handoff):
    return {source["chunk_id"]: source["version_scope"] for source in handoff["source_inventory"]}


@pytest.mark.parametrize("binding", ["scenario", "case"])
def test_exact_policy_excludes_wrong_version_before_reasoning_and_durable_handoff(
    tmp_path, binding
):
    app, tracker, retriever, reasoner, calls, original = runtime(
        tmp_path, (hit("only-1.64", ("1.64.0",)),), binding=binding
    )
    with TestClient(app) as client:
        body = send(client)
    assert len(calls) == len(retriever.requests) == len(reasoner.inputs) == 1
    assert supplied(reasoner) == set()
    assert reasoner.inputs[0][0].facts[0].value == "1.49.0"
    handoff = body["pending"]["review_handoff"]
    assert handoff["evidence"]["hits"] == [] and scopes(handoff) == {}
    assert tracker.read_case(CASE)["pending_handoff"] == handoff
    assert body["actions"] == [] and original.hits[0].applicable_versions == ("1.64.0",)


@pytest.mark.parametrize("version", [None, "1.49", "1.49.0"])
def test_exact_filter_uses_confirmed_literal_version_metadata_instead_of_raw_prose(
    tmp_path, version
):
    app, tracker, _retriever, reasoner, _calls, _bundle = runtime(
        tmp_path,
        (
            hit("other-version", ("1.64.0",)),
            hit("exact-1.49", ("1.49.0",)),
            hit("unversioned"),
        ),
    )
    with TestClient(app) as client:
        body = send(client, event(version=version))
    wanted = {"unversioned", "exact-1.49"} if version == "1.49.0" else {"unversioned"}
    assert supplied(reasoner) == wanted
    handoff = body["pending"]["review_handoff"]
    assert {source["chunk_id"] for source in handoff["evidence"]["hits"]} == wanted
    assert scopes(handoff)["unversioned"] == "unconfirmed"
    if version == "1.49.0":
        assert scopes(handoff)["exact-1.49"] == "exact_metadata_match"
    if version is None:
        assert tracker.read_case(CASE)["state"]["facts"] == []


def test_multiple_declared_versions_keep_an_exact_match_without_promoting_unversioned_source(
    tmp_path,
):
    app, _tracker, _retriever, reasoner, _calls, _bundle = runtime(
        tmp_path,
        (
            hit("multi-version", ("1.64.0", "1.49.0")),
            hit("range-only", (">=1.40.0",)),
            hit("unversioned"),
        ),
    )
    with TestClient(app) as client:
        body = send(client)
    assert supplied(reasoner) == {"multi-version", "unversioned"}
    assert scopes(body["pending"]["review_handoff"]) == {
        "multi-version": "exact_metadata_match",
        "unversioned": "unconfirmed",
    }


@pytest.mark.parametrize("scope", ["all", None])
@pytest.mark.parametrize("binding", ["scenario", "case"])
def test_explicit_all_and_legacy_default_preserve_historical_comparison_sources(
    tmp_path, scope, binding
):
    app, _tracker, _retriever, reasoner, _calls, _bundle = runtime(
        tmp_path,
        (hit("other-version", ("1.64.0",)), hit("unversioned")),
        scope=scope,
        binding=binding,
    )
    with TestClient(app) as client:
        body = send(client)
    assert supplied(reasoner) == {"other-version", "unversioned"}
    assert scopes(body["pending"]["review_handoff"]) == {
        "other-version": "historical_or_other_version",
        "unversioned": "unconfirmed",
    }


def test_correction_retires_old_version_and_filters_again_before_new_pending_proposal(tmp_path):
    app, tracker, _retriever, reasoner, calls, _bundle = runtime(
        tmp_path, (hit("old-installation-only", ("1.64.0",)),)
    )
    with TestClient(app) as client:
        original = send(client, event(version="1.64.0", message="Initial installation report."))
        corrected = send(
            client,
            event("corrected", 1, "1.49.0", message="The installed version was misreported."),
        )
        handoff = corrected["pending"]["review_handoff"]
        assert supplied(reasoner, 0) == {"old-installation-only"}
        assert supplied(reasoner, 1) == set()
        assert handoff["evidence"]["hits"] == []
        assert corrected["pending"]["proposal_id"] != original["pending"]["proposal_id"]
        active = [fact for fact in handoff["case"]["facts"] if fact["status"] == "active"]
        assert [(fact["name"], fact["value"]) for fact in active] == [
            ("streamlit_version", "1.49.0")
        ]
        before = client.get(f"/cases/{CASE}").json()
        replay = send(client, event(version="1.64.0", message="Initial installation report."))
        assert replay["intake"]["replayed"] and client.get(f"/cases/{CASE}").json() == before
    assert len(calls) == len(reasoner.inputs) == 2
    assert tracker.read_case(CASE)["pending_handoff"] == handoff


def test_filtered_source_cannot_be_cited_even_by_a_scripted_answer(tmp_path):
    wrong = AnalysisResult(
        decision="answer",
        user_draft="A synthetic fix is claimed from the excluded document.",
        maintainer_summary="Deliberately invalid authored answer.",
        rationale="This tests reference rejection, not model judgment.",
        evidence_links=(EvidenceLink(chunk_id="only-1.64", claim="Synthetic unsupported fix"),),
    )
    app, tracker, _retriever, reasoner, _calls, _bundle = runtime(
        tmp_path, (hit("only-1.64", ("1.64.0",)),), outputs=[wrong, wrong]
    )
    with TestClient(app) as client:
        body = send(client)
    assert len(reasoner.inputs) == 1 and not reasoner.inputs[0][2].hits
    assert body["pending"] is None and body["actions"] == []
    assert body["run_outcome"]["error_code"] == "UnknownEvidenceReference"
    assert tracker.read_case(CASE)["pending_handoff"] is None


def test_refinement_filters_its_own_bundle_and_does_not_restore_first_round_evidence(tmp_path):
    refine = AnalysisResult(
        decision="retrieve_more",
        user_draft="",
        maintainer_summary="",
        rationale="The synthetic first source is insufficient.",
        retrieval_queries=("multiselect callback installed version 1.49.0",),
    )
    retriever = FakeRetriever(
        [
            EvidenceBundle(snapshot_id=SNAPSHOT, hits=(hit("first-unversioned"),)),
            EvidenceBundle(snapshot_id=SNAPSHOT, hits=(hit("second-other-version", ("1.64.0",)),)),
        ]
    )
    reasoner = FakeReasoner([refine, escalation()])
    tracker = SQLiteCaseTracker(tmp_path / "refinement.sqlite3", reviewer_tokens=REVIEWERS)
    app = create_app(
        tracker,
        reviewer_tokens=REVIEWERS,
        evidence_scope="exact_user_version",
        adapters=lambda _scenario: api.RunAdapters(retriever, reasoner, snapshot_id=SNAPSHOT),
    )
    with TestClient(app) as client:
        body = send(client)
    assert len(retriever.requests) == len(reasoner.inputs) == 2
    assert supplied(reasoner, 0) == {"first-unversioned"} and supplied(reasoner, 1) == set()
    handoff = body["pending"]["review_handoff"]
    assert handoff["evidence"]["hits"] == [] and handoff["source_inventory"] == []
    assert handoff["evidence"]["retrieval_round"] == 2
    assert tracker.read_case(CASE)["pending_handoff"] == handoff


@pytest.mark.parametrize("scope", ["exact", "", True, 1, None, [], {}, {"exact_user_version"}])
def test_invalid_version_scope_config_fails_before_factory_ports_or_case_ingress(tmp_path, scope):
    tracker = SQLiteCaseTracker(tmp_path / "invalid-scope.sqlite3", reviewer_tokens=REVIEWERS)
    calls = []
    retriever, reasoner = FakeRetriever([]), FakeReasoner([])

    def ports(_scenario):
        calls.append(True)
        return api.RunAdapters(retriever, reasoner, snapshot_id=SNAPSHOT)

    before = tracker.read_case(CASE)
    with pytest.raises(ValueError):
        create_app(tracker, reviewer_tokens=REVIEWERS, adapters=ports, evidence_scope=scope)
    assert calls == [] and retriever.requests == reasoner.inputs == []
    assert tracker.read_case(CASE) == before
