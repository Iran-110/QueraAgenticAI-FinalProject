"""Dev-only amendment custody; prose review remains separate from runtime scoring."""

import hashlib
import json
from pathlib import Path

import pytest

from agent_app.contracts import CaseState, EvidenceBundle, EvidenceHit, Fact
from agent_app.evaluation.evidence_observation import (
    PassageRequirement,
    passage_requirements_sha256,
)
from agent_app.evaluation.routes import RouteGraph
from agent_app.reasoning.catalog import runtime_catalog

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "data/evaluation/split-e1-v1/native/"
V1_REGISTRATION = PREFIX + "native-registration-dev-v1.json"
V1_REVIEW = PREFIX + "native-dev-gold-review-v1.json"
V2_REGISTRATION = PREFIX + "native-registration-dev-v2.json"
AMENDMENT = PREFIX + "native-dev-gold-amendment-v2.json"
V1_REGISTRATION_SHA256 = "c8f5a04521d064828ee7582f4d3defbe5dcc298a622173969020708ee621a406"
V1_REVIEW_SHA256 = "8bed9ba7400de3759a47dd17aa7253540c79966049cd7411837a4adc4c56ce38"
POINTER = "/turns/0/gold/decision_conditions/escalate"
REPLACEMENTS = {
    "dev-case-m": "fragment-rerun-9180",
    "dev-case-i": "tabs-blank-9259",
}


def _path(name):
    """Reject a misdirected registration before any protected content is read."""
    assert type(name) is str
    path = (ROOT / name).resolve()
    assert path.is_relative_to(ROOT) and path.suffix == ".json"
    metadata = {
        V1_REGISTRATION,
        V1_REVIEW,
        V2_REGISTRATION,
        AMENDMENT,
        "data/evaluation/split-e1-v1/split-manifest.json",
    }
    fixture_directories = {
        ROOT / PREFIX / "dev",
        ROOT / PREFIX / "dev-v2",
        ROOT / "data/evaluation/split-e1-v1/dev",
        ROOT / "data/evaluation/dev-three-v2/cases",
    }
    assert path.relative_to(ROOT).as_posix() == name
    assert name in metadata or path.parent in fixture_directories
    return path


def _load(name):
    return json.loads(_path(name).read_bytes())


def _sha(name):
    return hashlib.sha256(_path(name).read_bytes()).hexdigest()


def _entries(registration):
    entries = registration["fixtures"]
    assert len(entries) == 16
    assert len({entry["case_id"] for entry in entries}) == 16
    assert len({entry["path"] for entry in entries}) == 16
    return {entry["case_id"]: entry for entry in entries}


def _changes(before, after, pointer=""):
    if type(before) is not type(after):
        return {pointer}
    if type(before) is dict:
        changed = {pointer + "/" + key for key in before.keys() ^ after.keys()}
        for key in before.keys() & after.keys():
            changed |= _changes(before[key], after[key], pointer + "/" + key)
        return changed
    if type(before) is list:
        if len(before) != len(after):
            return {pointer}
        return set().union(
            *(
                _changes(old, new, pointer + f"/{index}")
                for index, (old, new) in enumerate(zip(before, after, strict=True))
            )
        )
    return set() if before == after else {pointer}


def test_all_eighteen_original_native_artifacts_remain_at_the_reviewed_bytes():
    assert _sha(V1_REGISTRATION) == V1_REGISTRATION_SHA256
    assert _sha(V1_REVIEW) == V1_REVIEW_SHA256
    old = _entries(_load(V1_REGISTRATION))
    review = {item["case_id"]: item for item in _load(V1_REVIEW)["items"]}
    assert set(review) == set(old)
    for case_id, entry in old.items():
        assert _sha(entry["path"]) == entry["sha256"] == review[case_id]["final_sha256"]


def test_selected_registration_has_fourteen_exact_entries_and_two_replacements():
    old, new = _load(V1_REGISTRATION), _load(V2_REGISTRATION)
    before, after = _entries(old), _entries(new)
    assert set(before) == set(after)
    changed = {case_id for case_id in before if before[case_id] != after[case_id]}
    assert changed == set(REPLACEMENTS)
    assert new["registration_id"] == "split-e1-v1-native-dev-v2"
    for case_id, entry in after.items():
        fixture = _load(entry["path"])
        assert fixture["case"]["split"] == "dev"
        assert fixture["case"]["case_id"] == case_id
        assert _sha(entry["path"]) == entry["sha256"]
        assert entry["native_of"] == before[case_id]["native_of"]
        if case_id in REPLACEMENTS:
            assert entry["path"] == PREFIX + "dev-v2/" + REPLACEMENTS[case_id] + "-native-v2.json"
        else:
            assert entry == before[case_id]
    for field in (
        "schema_version",
        "registered_on",
        "registered_before_first_run",
        "split_manifest",
        "split_manifest_sha256",
        "evidence_condition",
        "rubric_id",
        "observer",
        "observer_sha256",
        "pins",
        "test",
    ):
        assert new[field] == old[field]
    assert _sha(new["split_manifest"]) == new["split_manifest_sha256"]
    observer = ROOT / new["observer"]
    assert observer == ROOT / "src/agent_app/evaluation/evidence_observation.py"
    assert hashlib.sha256(observer.read_bytes()).hexdigest() == new["observer_sha256"]
    assert new["pins"]["build"] == "pending_final_build"
    assert all(value is None for key, value in new["pins"].items() if key != "build")


@pytest.mark.parametrize("case_id", REPLACEMENTS)
def test_fixture_delta_is_only_the_initial_escalation_and_declared_versioning(case_id):
    old_entry = _entries(_load(V1_REGISTRATION))[case_id]
    entry = _entries(_load(V2_REGISTRATION))[case_id]
    old, new = _load(old_entry["path"]), _load(entry["path"])
    assert _changes(old, new) == {"/fixture_id", "/supersedes", POINTER}
    assert new["fixture_id"] == old["fixture_id"][:-2] + "v2"
    assert new["supersedes"] == {
        "path": old_entry["path"],
        "sha256": old_entry["sha256"],
        "fixture_id": old["fixture_id"],
        "changed_gold_json_pointers": [POINTER],
    }
    assert new["turns"][0]["gold"]["decision_conditions"]["escalate"].strip()
    # The exact delta also preserves USER turns, routes, scripts, evidence,
    # answers, native anchors and the tabs follow-up without reauthoring them.
    assert new["evaluation"] == old["evaluation"]
    assert new["evidence_source"] == old["evidence_source"]
    assert _sha(new["native_of"]["path"]) == new["native_of"]["sha256"]


def test_amendment_hash_graph_keeps_new_review_distinct_from_human_history():
    registration, review = _load(V2_REGISTRATION), _load(AMENDMENT)
    assert (
        registration["supersedes"]
        == review["prior_registration"]
        == {
            "path": V1_REGISTRATION,
            "sha256": V1_REGISTRATION_SHA256,
        }
    )
    assert registration["review"] == AMENDMENT
    assert registration["review_sha256"] == _sha(AMENDMENT)
    historical = registration["historical_human_review"]
    assert historical == review["historical_human_review"]
    assert historical["path"] == V1_REVIEW and historical["sha256"] == V1_REVIEW_SHA256
    assert review["reviewer_kind"] == "assistant" and review["human_review_claim"] is False
    assert set(registration["human_confirmation_pending"]) == set(REPLACEMENTS)
    items = {item["case_id"]: item for item in review["items"]}
    assert len(review["items"]) == len(items) == 2 and set(items) == set(REPLACEMENTS)
    selected = _entries(registration)
    for case_id, item in items.items():
        fixture = _load(selected[case_id]["path"])
        assert item["fixture_path"] == selected[case_id]["path"]
        assert item["final_sha256"] == selected[case_id]["sha256"] == _sha(item["fixture_path"])
        assert item["supersedes"] == fixture["supersedes"]
        assert item["reviewed_json_pointer"] == POINTER
        assert item["reviewer_kind"] == "assistant"
        assert item["human_confirmation"] == "pending"
        assert "final_verdict" not in item and "usefulness_score" not in item
        assert all(turn["gold"]["human_reviewed"] is False for turn in fixture["turns"])
        assert all(turn["gold"]["usefulness_score"] is None for turn in fixture["turns"])


def test_selected_routes_and_complete_passage_requirements_stay_valid():
    turns = routes = requirements = anchors = 0
    for entry in _entries(_load(V2_REGISTRATION)).values():
        fixture = _load(entry["path"])
        graph = RouteGraph.from_fixture(fixture)
        turns += len(fixture["turns"])
        routes += len(graph.routes)
        for turn in fixture["turns"]:
            assert turn["gold"]["evidence_condition"] == "native_index"
            for kind in ("answer_required", "optional_claim_support"):
                block = turn["gold"]["native_passages"][kind]
                if block is not None:
                    models = tuple(
                        PassageRequirement.model_validate(row) for row in block["requirements"]
                    )
                    assert passage_requirements_sha256(models) == block["requirements_sha256"]
                    requirements += len(models)
                    anchors += sum(len(model.alternatives) for model in models)
    assert (turns, routes, requirements, anchors) == (23, 52, 20, 46)


@pytest.mark.parametrize("case_id", REPLACEMENTS)
@pytest.mark.parametrize("evidence_kind", ["absent", "wrong_version"])
def test_real_catalog_retains_known_user_version_when_documentary_support_is_missing(
    case_id, evidence_kind
):
    fixture = _load(_entries(_load(V2_REGISTRATION))[case_id]["path"])
    visible = fixture["turns"][0]["visible"]
    case = CaseState(
        case_id=case_id,
        facts=tuple(
            Fact(
                **fact,
                source_ref="amendment-visible-user-turn",
                turn_id=fixture["turns"][0]["id"],
            )
            for fact in visible["reported_facts"]
        ),
        unknowns=tuple(visible["unknowns"]),
    )
    assert next(fact.value for fact in case.facts if fact.name == "streamlit_version") == "1.37.0"
    hits = (
        ()
        if evidence_kind == "absent"
        else (
            EvidenceHit(
                chunk_id="neutral-wrong-version",
                source_id="neutral-source",
                source_commit=None,
                source_url="https://example.org/neutral",
                source_type="doc",
                excerpt="Neutral API text.",
                applicable_versions=("1.38.0",),
                score=1.0,
                score_kind="lexical",
            ),
        )
    )
    request = runtime_catalog(
        case, visible["message"], EvidenceBundle(snapshot_id="neutral", hits=hits)
    )
    assert {(gap.name, gap.kind) for gap in request.gaps} == {
        ("exact_version_documentation", "source")
    }
    assert request.case == case
    # This exercises the existing source/user boundary. It neither evaluates the
    # English gold condition nor selects/escalates/scores an agent response.
