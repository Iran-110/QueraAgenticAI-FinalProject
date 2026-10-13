"""Synthetic packet integrity checks; these are not curated evaluation cases."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from agent_app.evaluation import preflight


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def bundle(tmp_path):
    rubric_hash = write(
        tmp_path / "rubric.json", {"rubric_id": "synthetic-test-only", "status": "frozen"}
    )
    witness = {"type": "human", "reviewer": "synthetic-test-witness", "rubric_sha256": rubric_hash}
    exposed = sorted(preflight.KNOWN_EXPOSURE)
    exposure = {
        "status": "reviewed_complete",
        "review": witness,
        "issue_numbers": exposed,
        "families": [{"issue_ids": [issue], "review_status": "complete"} for issue in exposed],
    }
    exposure_hash = write(tmp_path / "exposure.json", exposure)
    selected, families, pins, paths, all_issues = {"dev": [], "test": []}, [], [], [], []
    for index in range(30):
        split = "dev" if index < 15 else "test"
        case_id, family_id, issue = f"{split}-{index}", f"family-{index}", 50001 + index
        selected[split].append(case_id)
        all_issues.append(issue)
        families.append(
            {
                "family_id": family_id,
                "issue_ids": [issue],
                "split": split,
                "review_status": "complete",
            }
        )
        multi = index < 5 or 15 <= index < 20
        turns = [
            {
                "id": "first",
                "visible": {"message": f"Synthetic report {index}; version unknown."},
                "conversation_source": "developer_authored_synthetic_test",
                "gold": {
                    "acceptable_decisions": ["ask", "escalate"] if multi else ["escalate"],
                    "gaps": [
                        {
                            "kind": "user",
                            "name": "streamlit_version",
                            "question": "Which version?",
                            "necessity": "Select the applicable source version.",
                        }
                    ],
                },
            }
        ]
        routes = [{"from_turn": "first", "to_turn": None, "guard": {"decision": "escalate"}}]
        if multi:
            turns.append(
                {
                    "id": "second",
                    "visible": {"message": "Version is 1.50.0."},
                    "conversation_source": "developer_authored_synthetic_test",
                    "gold": {"acceptable_decisions": ["answer", "escalate"]},
                }
            )
            routes.extend(
                [
                    {
                        "from_turn": "first",
                        "to_turn": "second",
                        "guard": {"decision": "ask", "question_target": "streamlit_version"},
                    },
                    {"from_turn": "second", "to_turn": None, "guard": {"decision": "answer"}},
                    {"from_turn": "second", "to_turn": None, "guard": {"decision": "escalate"}},
                ]
            )
        fixture = {
            "fixture_id": case_id + "-v1",
            "registered_before_first_run": True,
            "case": {
                "case_id": case_id,
                "split": split,
                "family_id": family_id,
                "family_issue_ids": [issue],
                "origin_url": f"https://github.com/streamlit/streamlit/issues/{issue}",
                "test_eligible": split == "test",
            },
            "turns": turns,
            "evaluation": {
                "coverage": {
                    "status": "reviewed_complete",
                    "review": witness,
                    "turn_ids": [turn["id"] for turn in turns],
                    "routes": routes,
                }
            },
        }
        relative = f"{split}/{case_id}.json"
        path = tmp_path / relative
        digest = write(path, fixture)
        paths.append(path)
        pins.append({"case_id": case_id, "path": relative, "sha256": digest})
    excluded = exposed + all_issues
    corpus = {
        "corpus_id": "synthetic-metadata-only",
        "status": "frozen",
        "sources": [
            {
                "source_id": "docs-api",
                "kind": "documentation",
                "sha256": "1" * 64,
                "provenance": {
                    "url": "https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state",
                    "source_revision": "synthetic-commit",
                    "pointer": "$.body",
                },
            }
        ],
        "exclusions": {
            "status": "reviewed_complete",
            "review": witness,
            "excluded_issue_ids": excluded,
            "duplicate_review": {"status": "complete", "review": witness, "issue_ids": excluded},
            "direct_answer_review": {
                "status": "complete",
                "review": witness,
                "corpus_source_ids": ["docs-api"],
                "excluded_source_ids": [],
            },
        },
    }
    corpus_hash = write(tmp_path / "corpus.json", corpus)
    manifest = {
        "packet_id": "frozen_final_v1",
        "manifest_id": "synthetic-final-integrity-test",
        "status": "frozen",
        "review": witness,
        "family_review_complete": True,
        "selected": selected,
        "families": families,
        "fixtures": pins,
        "rubric": {"path": "rubric.json", "sha256": rubric_hash},
        "exposure": {"path": "exposure.json", "sha256": exposure_hash},
        "corpus": {"path": "corpus.json", "sha256": corpus_hash},
    }
    write(tmp_path / "manifest.json", manifest)
    return {
        "root": tmp_path,
        "manifest": manifest,
        "corpus": corpus,
        "exposure": exposure,
        "paths": paths,
    }


def run(bundle, paths=None):
    root = bundle["root"]
    return preflight.validate_final_bundle(
        bundle["paths"] if paths is None else paths,
        root / "manifest.json",
        root / "corpus.json",
        rubric=root / "rubric.json",
        exposure=root / "exposure.json",
        trusted_root=root,
    )


def save(bundle, artifact="manifest"):
    digest = write(bundle["root"] / f"{artifact}.json", bundle[artifact])
    if artifact != "manifest":
        bundle["manifest"][artifact]["sha256"] = digest
        save(bundle)


def change_fixture(bundle, index, change, *, repin=True):
    path = bundle["paths"][index]
    fixture = json.loads(path.read_text())
    change(fixture)
    digest = write(path, fixture)
    if repin:
        bundle["manifest"]["fixtures"][index]["sha256"] = digest
        save(bundle)


def rejected(report, diagnostic):
    assert report["accepted"] is False
    assert report["quality_claim"] is False
    assert report["diagnostics"] == [diagnostic]


def test_complete_synthetic_packet_is_only_mechanically_eligible(bundle):
    report = run(bundle)
    assert report["accepted"] is True
    assert report["quality_claim"] is False
    assert report["eligibility_scope"] == "mechanical_frozen_artifact_eligibility_only"
    assert report["counts"] == {
        "dev": 15,
        "test": 15,
        "multi_turn": 10,
        "multi_turn_test": 5,
        "families": 30,
        "corpus_sources": 1,
    }
    assert len(report["hashes"]["fixtures"]) == 30
    assert "synthetic-test-witness" not in json.dumps(report)


def test_existing_one_dev_zero_test_manifest_is_not_silently_upgraded():
    root = Path(__file__).resolve().parents[1]
    report = preflight.validate_final_bundle(
        [root / "data/evaluation/dev"],
        root / "data/evaluation/split-manifest.json",
        root / "experiments/corpus/pilot-allowlist.json",
        trusted_root=root,
    )
    rejected(report, "ManifestNotFrozen")


@pytest.mark.parametrize("artifact", ["rubric", "exposure", "corpus"])
def test_mutated_pinned_artifact_fails_before_any_adapter_exists(bundle, artifact):
    path = bundle["root"] / f"{artifact}.json"
    path.write_bytes(path.read_bytes() + b"\n")
    rejected(run(bundle), "ArtifactHashMismatch")


def test_mutated_fixture_requires_new_pin(bundle):
    change_fixture(
        bundle,
        0,
        lambda data: data["turns"][0]["visible"].update(message="SECRET-RAW-MESSAGE"),
        repin=False,
    )
    report = run(bundle)
    rejected(report, "ArtifactHashMismatch")
    assert "SECRET-RAW-MESSAGE" not in json.dumps(report)


@pytest.mark.parametrize("issue", [9031, 11012, 17030, 12782])
def test_known_exposure_closure_cannot_be_laundered_as_independent_test(bundle, issue):
    bundle["manifest"]["families"][15]["issue_ids"] = [issue]
    save(bundle)
    rejected(run(bundle), "ExposedTestFamily")


def test_exposure_file_cannot_omit_a_known_duplicate(bundle):
    bundle["exposure"]["issue_numbers"].remove(9031)
    save(bundle, "exposure")
    rejected(run(bundle), "ExposureClosureIncomplete")


@pytest.mark.parametrize("issue", [9031, 11012, 17030])
def test_repinned_exposed_origin_cannot_hide_behind_false_family_numbers(bundle, issue):
    change_fixture(
        bundle,
        15,
        lambda fixture: fixture["case"].update(
            origin_url=f"https://github.com/streamlit/streamlit/issues/{issue}"
        ),
    )
    rejected(run(bundle), "FixtureOriginRejected")


@pytest.mark.parametrize(
    "origin",
    [
        None,
        True,
        "",
        "https://github.com/streamlit/streamlit/issues/50001",
        "https://github.com/streamlit/streamlit/issues/0",
        "https://github.com/streamlit/streamlit/issues/050016",
        "https://github.com/other/streamlit/issues/50016",
        "https://github.com/streamlit/streamlit/issues/50016?issue=9031",
        "https://github.com/streamlit/streamlit/issues/50016#issuecomment-1",
    ],
)
def test_origin_must_be_canonical_and_a_declared_family_member(bundle, origin):
    change_fixture(bundle, 15, lambda fixture: fixture["case"].update(origin_url=origin))
    report = run(bundle)
    rejected(report, "FixtureOriginRejected")
    assert "issuecomment" not in json.dumps(report)


def test_exposure_family_review_must_cover_declared_numbers(bundle):
    bundle["exposure"]["families"].pop()
    save(bundle, "exposure")
    rejected(run(bundle), "ExposureClosureIncomplete")


def test_same_issue_cannot_appear_in_distinct_families(bundle):
    bundle["manifest"]["families"][15]["issue_ids"] = bundle["manifest"]["families"][0]["issue_ids"]
    save(bundle)
    rejected(run(bundle), "FamilyOverlap")


@pytest.mark.parametrize("field", ["review", "family_review_complete"])
def test_frozen_label_without_human_family_review_is_insufficient(bundle, field):
    bundle["manifest"].pop(field)
    save(bundle)
    rejected(run(bundle), "HumanReviewRequired" if field == "review" else "FamilyReviewRequired")


def test_witness_must_bind_the_actual_rubric(bundle):
    bundle["manifest"]["review"] = {"type": "human", "reviewer": "test", "rubric_sha256": "0" * 64}
    save(bundle)
    rejected(run(bundle), "HumanReviewRequired")


@pytest.mark.parametrize("mode", ["omit", "duplicate", "unknown"])
def test_fixture_paths_are_exact_frozen_membership(bundle, mode):
    paths = bundle["paths"][:-1] if mode == "omit" else bundle["paths"] + [bundle["paths"][0]]
    if mode == "unknown":
        extra = bundle["root"] / "extra.json"
        write(extra, {"case": {"case_id": "unknown"}})
        paths = bundle["paths"] + [extra]
    rejected(run(bundle, paths), "FixtureMembershipRejected")


def test_two_cases_from_same_family_do_not_count_as_independent_cases(bundle):
    change_fixture(
        bundle,
        1,
        lambda fixture: fixture["case"].update(family_id="family-0", family_issue_ids=[50001]),
    )
    rejected(run(bundle), "FixtureMembershipRejected")


def test_thirty_count_only_placeholders_are_not_registered_multiturn_coverage(bundle):
    for index in range(30):
        change_fixture(bundle, index, lambda fixture: fixture["evaluation"].pop("coverage"))
    rejected(run(bundle), "FixtureCoverageRejected")


def test_declared_multi_turn_count_cannot_replace_actual_turns(bundle):
    for index in range(30):

        def truncate(fixture):
            fixture["turns"] = fixture["turns"][:1]
            fixture["turns"][0]["gold"]["acceptable_decisions"] = ["escalate"]
            coverage = fixture["evaluation"]["coverage"]
            coverage.update(
                turn_ids=["first"],
                multi_turn=True,
                routes=[{"from_turn": "first", "to_turn": None, "guard": {"decision": "escalate"}}],
            )

        change_fixture(bundle, index, truncate)
    rejected(run(bundle), "MultiTurnCoverageInsufficient")


@pytest.mark.parametrize(
    "mutation",
    [
        "unreachable",
        "cycle",
        "missing_decision",
        "missing_question_target",
        "known_gap",
        "duplicate_guard",
        "unknown_guard",
    ],
)
def test_conditional_route_coverage_is_validated(bundle, mutation):
    def mutate(fixture):
        routes = fixture["evaluation"]["coverage"]["routes"]
        if mutation == "unreachable":
            routes[1]["to_turn"] = None
        elif mutation == "cycle":
            routes[1]["to_turn"] = "first"
        elif mutation == "missing_decision":
            routes.pop()
        elif mutation == "missing_question_target":
            routes[1]["guard"].pop("question_target")
        elif mutation == "duplicate_guard":
            routes.append(
                {
                    "from_turn": "first",
                    "to_turn": None,
                    "guard": {"decision": "ask", "question_target": "streamlit_version"},
                }
            )
        elif mutation == "unknown_guard":
            routes[1]["guard"]["unsupported_condition"] = "SECRET-CONDITION"
        else:
            fixture["turns"][0]["gold"]["gaps"][0]["kind"] = "source"

    change_fixture(bundle, 0, mutate)
    rejected(run(bundle), "FixtureRoutesRejected")


def test_route_declaration_order_does_not_change_graph_coverage(bundle):
    change_fixture(bundle, 0, lambda fixture: fixture["evaluation"]["coverage"]["routes"].reverse())
    assert run(bundle)["accepted"] is True


def test_repeated_placeholder_messages_do_not_count_as_multiturn(bundle):
    change_fixture(
        bundle,
        0,
        lambda fixture: fixture["turns"][1]["visible"].update(
            message=fixture["turns"][0]["visible"]["message"]
        ),
    )
    rejected(run(bundle), "FixtureCoverageRejected")


@pytest.mark.parametrize("kind", ["issue", "comment", "outcome", "documentation"])
def test_heldout_issue_metadata_is_not_allowed_in_any_source_kind(bundle, kind):
    bundle["corpus"]["sources"][0].update(kind=kind, issue_id=50016)
    save(bundle, "corpus")
    rejected(run(bundle), "CorpusLeakDetected")


def test_family_metadata_and_issue_url_cannot_bypass_exclusion(bundle):
    source = bundle["corpus"]["sources"][0]
    source["provenance"]["url"] = (
        "https://github.com/streamlit/streamlit/issues/50016#issuecomment-1"
    )
    save(bundle, "corpus")
    rejected(run(bundle), "CorpusLeakDetected")
    source["provenance"]["url"] = "https://docs.streamlit.io/"
    source["family_id"] = "family-15"
    save(bundle, "corpus")
    rejected(run(bundle), "CorpusLeakDetected")


@pytest.mark.parametrize(
    "mutation", ["empty", "provenance", "missing_issue_id", "duplicate_source"]
)
def test_empty_or_uninspectable_corpus_cannot_be_accepted(bundle, mutation):
    sources = bundle["corpus"]["sources"]
    if mutation == "empty":
        sources.clear()
    elif mutation == "provenance":
        sources[0]["provenance"].pop("source_revision")
    elif mutation == "missing_issue_id":
        sources[0]["kind"] = "comment"
    else:
        sources.append(dict(sources[0]))
    save(bundle, "corpus")
    rejected(
        run(bundle),
        "CorpusSourcesRejected"
        if mutation in {"empty", "duplicate_source"}
        else "CorpusProvenanceRequired",
    )


@pytest.mark.parametrize("review", ["duplicate_review", "direct_answer_review"])
def test_explicit_duplicate_and_direct_answer_reviews_are_required(bundle, review):
    bundle["corpus"]["exclusions"].pop(review)
    save(bundle, "corpus")
    rejected(
        run(bundle),
        "DuplicateReviewRequired" if review == "duplicate_review" else "DirectAnswerReviewRequired",
    )


def test_direct_answer_review_covers_every_indexed_source(bundle):
    bundle["corpus"]["exclusions"]["direct_answer_review"]["corpus_source_ids"] = []
    save(bundle, "corpus")
    rejected(run(bundle), "DirectAnswerReviewRequired")


def test_direct_answer_excluded_source_cannot_also_be_indexed(bundle):
    bundle["corpus"]["exclusions"]["direct_answer_review"]["excluded_source_ids"] = ["docs-api"]
    save(bundle, "corpus")
    rejected(run(bundle), "CorpusLeakDetected")


@pytest.mark.parametrize("invalid", [True, "50016", 0])
def test_issue_identifiers_are_strict_integers_without_coercion(bundle, invalid):
    bundle["corpus"]["sources"][0]["issue_id"] = invalid
    save(bundle, "corpus")
    rejected(run(bundle), "CorpusSourcesRejected")


def test_exclusion_must_cover_all_frozen_case_families(bundle):
    bundle["corpus"]["exclusions"]["excluded_issue_ids"].remove(50016)
    save(bundle, "corpus")
    rejected(run(bundle), "CorpusExclusionIncomplete")


def test_reference_cannot_escape_trusted_root_even_through_symlink(bundle, tmp_path):
    external = tmp_path.parent / (tmp_path.name + "-outside.json")
    digest = write(external, {"status": "frozen", "rubric_id": "outside"})
    link = bundle["root"] / "rubric-link.json"
    try:
        link.symlink_to(external)
    except OSError:
        pytest.skip("This host does not allow creating test symlinks.")
    bundle["manifest"]["rubric"] = {"path": "rubric-link.json", "sha256": digest}
    save(bundle)
    rejected(run(bundle), "ArtifactPathRejected")


def test_artifact_rewritten_during_preflight_cannot_pass_from_first_read(bundle, monkeypatch):
    real_read = preflight._read
    last = bundle["paths"][-1]
    changed = False

    def mutate_after_last(path):
        nonlocal changed
        result = real_read(path)
        if path == last and not changed:
            changed = True
            bundle["paths"][0].write_bytes(bundle["paths"][0].read_bytes() + b"\n")
        return result

    monkeypatch.setattr(preflight, "_read", mutate_after_last)
    rejected(run(bundle), "ArtifactChangedDuringPreflight")


@pytest.mark.parametrize(
    "malformed",
    [
        None,
        [],
        "SECRET-RAW-INPUT",
        {"status": "frozen", "packet_id": "frozen_final_v1", "rubric": []},
    ],
)
def test_untrusted_shapes_produce_only_allowlisted_diagnostics(bundle, malformed):
    write(bundle["root"] / "manifest.json", malformed)
    report = run(bundle)
    assert report["accepted"] is False and report["quality_claim"] is False
    assert report["diagnostics"][0] in {
        "ArtifactUnreadable",
        "ManifestNotFrozen",
        "ArtifactPinRequired",
    }
    assert "SECRET-RAW-INPUT" not in json.dumps(report)


def test_cli_receipt_and_exit_status_are_machine_readable(bundle):
    root = bundle["root"]
    command = [
        sys.executable,
        "-m",
        "agent_app.evaluation.preflight",
        "--manifest",
        str(root / "manifest.json"),
        "--corpus-manifest",
        str(root / "corpus.json"),
        "--trusted-root",
        str(root),
        str(root / "dev"),
        str(root / "test"),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    assert completed.returncode == 0
    assert json.loads(completed.stdout)["quality_claim"] is False
    bundle["manifest"]["status"] = "draft_not_frozen"
    save(bundle)
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    assert completed.returncode == 1
    rejected(json.loads(completed.stdout), "ManifestNotFrozen")
