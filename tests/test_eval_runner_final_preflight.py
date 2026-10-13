"""Final-packet gates precede factories; all data here is synthetic test data."""

import hashlib
import json
from pathlib import Path

import pytest
from test_evaluation_preflight import bundle as bundle
from test_evaluation_preflight import change_fixture, save

from agent_app.evaluation import runner
from agent_app.testing.http_pilot_runtime import offline_network

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def runnable_bundle(bundle, monkeypatch):
    root = bundle["root"]
    evidence = (REPO / "data/evaluation/evidence/synthetic-v1.json").read_bytes()
    (root / "evidence.json").write_bytes(evidence)
    digest = hashlib.sha256(evidence).hexdigest()
    for index in range(30):

        def enrich(fixture):
            fixture["schema_version"] = 1
            fixture["evidence_source"] = {
                "path": "evidence.json",
                "sha256": digest,
                "bundles_used": ["counter"],
            }
            for turn_index, turn in enumerate(fixture["turns"]):
                turn["evidence_bundle"] = "counter"
                turn["maintainer"] = {"decision": "none"}
                turn["agent_script"] = {
                    "decision": "escalate",
                    "user_draft": "Synthetic operational next step.",
                    "maintainer_summary": "Synthetic operational fixture; no model quality claim.",
                    "rationale": "Test only the artifact and execution boundaries.",
                }
                turn["expect"] = {"revision": turn_index + 1, "pending_decision": "escalate"}

        change_fixture(bundle, index, enrich)
    monkeypatch.setattr(runner, "ROOT", root)
    return bundle


def preflight(bundle, selected=None):
    return runner.final_preflight(
        selected or [bundle["paths"][0]],
        bundle["root"] / "manifest.json",
        bundle["root"] / "corpus.json",
        bundle_paths=bundle["paths"],
        trusted_root=bundle["root"],
    )


def cli(bundle, selected=None):
    root = bundle["root"]
    return [str(path) for path in (selected or [bundle["paths"][0]])] + [
        "--mode",
        "live",
        "--adapters",
        "forbidden_provider:factory",
        "--final-manifest",
        str(root / "manifest.json"),
        "--final-corpus-manifest",
        str(root / "corpus.json"),
        "--final-bundle",
        *[str(path) for path in bundle["paths"]],
    ]


def forbid_factory(monkeypatch):
    calls = []

    def forbidden(spec):
        calls.append(spec)
        raise AssertionError("An invalid final packet constructed a live factory.")

    monkeypatch.setattr(runner, "_load_live", forbidden)
    return calls


def test_all_thirty_final_fixtures_are_loaded_before_subset_is_eligible(runnable_bundle):
    report = preflight(runnable_bundle)
    assert report["accepted"] is True and report["quality_claim"] is False
    assert report["fixture_loader_validated"] is True
    assert len(report["hashes"]["fixtures"]) == 30
    assert report["execution_fixture_hashes"] == [
        hashlib.sha256(runnable_bundle["paths"][0].read_bytes()).hexdigest()
    ]


def test_actual_offline_subset_receipt_retains_whole_packet_and_execution_hashes(runnable_bundle):
    root = runnable_bundle["root"]
    selected = [runnable_bundle["paths"][0], runnable_bundle["paths"][5]]
    with offline_network():
        receipt = runner.run(
            selected,
            final_manifest=root / "manifest.json",
            final_corpus_manifest=root / "corpus.json",
            final_bundle=runnable_bundle["paths"],
            trusted_root=root,
        )
    assert receipt["summary"]["failed"] == 0
    assert receipt["summary"]["cases"] == 2
    assert receipt["summary"]["coverage_complete"] is True
    assert receipt["quality_claim"] is False
    packet = receipt["final_artifact_preflight"]
    assert packet["counts"]["dev"] == packet["counts"]["test"] == 15
    assert packet["execution_fixture_hashes"] == [
        case["fixture_sha256"] for case in receipt["cases"]
    ]
    assert packet["execution_fixture_hashes"] == [
        hashlib.sha256(path.read_bytes()).hexdigest() for path in selected
    ]


@pytest.mark.parametrize("missing", ["manifest", "corpus", "both_with_bundle"])
def test_incomplete_final_gate_arguments_cannot_be_ignored(runnable_bundle, missing):
    root = runnable_bundle["root"]
    manifest = None if missing in {"manifest", "both_with_bundle"} else root / "manifest.json"
    corpus = None if missing in {"corpus", "both_with_bundle"} else root / "corpus.json"
    with pytest.raises(ValueError, match="^FinalEvaluationPreflightRejected$"):
        runner.final_preflight(
            [runnable_bundle["paths"][0]], manifest, corpus, bundle_paths=runnable_bundle["paths"]
        )


def test_draft_packet_rejected_before_live_factory(runnable_bundle, monkeypatch, capsys):
    calls = forbid_factory(monkeypatch)
    runnable_bundle["manifest"]["status"] = "draft_not_frozen"
    save(runnable_bundle)
    assert runner.main(cli(runnable_bundle)) == 1
    assert calls == []
    assert json.loads(capsys.readouterr().err) == {"code": "FinalEvaluationPreflightRejected"}


def test_changed_fixture_rejected_before_live_factory(runnable_bundle, monkeypatch):
    calls = forbid_factory(monkeypatch)
    runnable_bundle["paths"][-1].write_bytes(runnable_bundle["paths"][-1].read_bytes() + b"\n")
    assert runner.main(cli(runnable_bundle)) == 1
    assert calls == []


def test_unused_test_fixture_must_still_be_loader_compatible_before_factory(
    runnable_bundle, monkeypatch
):
    calls = forbid_factory(monkeypatch)
    change_fixture(
        runnable_bundle, 29, lambda fixture: fixture["turns"][0].update(evidence_bundle="unknown")
    )
    assert runner.main(cli(runnable_bundle)) == 1
    assert calls == []


def test_changed_transitive_evidence_rejected_before_factory(runnable_bundle, monkeypatch):
    calls = forbid_factory(monkeypatch)
    path = runnable_bundle["root"] / "evidence.json"
    path.write_bytes(path.read_bytes() + b"\n")
    assert runner.main(cli(runnable_bundle)) == 1
    assert calls == []


@pytest.mark.parametrize("escape", ["traversal", "absolute", "symlink"])
def test_evidence_escape_is_rejected_before_factory(runnable_bundle, monkeypatch, escape):
    calls = forbid_factory(monkeypatch)
    root = runnable_bundle["root"]
    outside = root.parent / (root.name + "-public-evidence.json")
    outside.write_bytes((root / "evidence.json").read_bytes())
    source_path = "../" + outside.name
    if escape == "absolute":
        source_path = str(outside)
    elif escape == "symlink":
        try:
            (root / "external-evidence.json").symlink_to(outside)
        except OSError:
            pytest.skip("This host does not allow creating test symlinks.")
        source_path = "external-evidence.json"
    change_fixture(
        runnable_bundle, 29, lambda fixture: fixture["evidence_source"].update(path=source_path)
    )
    assert runner.main(cli(runnable_bundle)) == 1
    assert calls == []


def test_selected_path_cannot_escape_whole_packet(runnable_bundle, monkeypatch):
    calls = forbid_factory(monkeypatch)
    external = runnable_bundle["root"] / "unknown.json"
    external.write_bytes(runnable_bundle["paths"][0].read_bytes())
    assert runner.main(cli(runnable_bundle, [external])) == 1
    assert calls == []


def test_fixture_rewritten_between_packet_validation_and_loader_is_refused(
    runnable_bundle, monkeypatch
):
    real_validate = runner.validate_final_bundle

    def rewrite_after_validation(*args, **kwargs):
        report = real_validate(*args, **kwargs)
        path = runnable_bundle["paths"][0]
        path.write_bytes(path.read_bytes() + b"\n")
        return report

    monkeypatch.setattr(runner, "validate_final_bundle", rewrite_after_validation)
    with pytest.raises(ValueError, match="^FinalEvaluationPreflightRejected$"):
        preflight(runnable_bundle)


def test_selected_fixture_hash_is_rechecked_before_actual_run(runnable_bundle, monkeypatch):
    real_preflight = runner.final_preflight

    def rewrite_after_preflight(*args, **kwargs):
        report = real_preflight(*args, **kwargs)
        path = runnable_bundle["paths"][0]
        path.write_bytes(path.read_bytes() + b"\n")
        return report

    monkeypatch.setattr(runner, "final_preflight", rewrite_after_preflight)
    root = runnable_bundle["root"]
    with pytest.raises(ValueError, match="^FinalEvaluationPreflightRejected$"):
        runner.run(
            [runnable_bundle["paths"][0]],
            final_manifest=root / "manifest.json",
            final_corpus_manifest=root / "corpus.json",
            final_bundle=runnable_bundle["paths"],
        )


def test_valid_cli_constructs_factory_only_after_whole_bundle_loader(runnable_bundle, monkeypatch):
    real_collect = runner.collect
    events = []

    def observe_collect(paths, *, mode):
        loaded = real_collect(paths, mode=mode)
        events.append(("loaded", len(loaded)))
        return loaded

    def construct(spec):
        assert events == [("loaded", 30)]
        events.append(("factory", spec))
        return object()

    def stub_run(paths, **kwargs):
        assert kwargs["live"] is not None
        return {"summary": {"failed": 0, "coverage_complete": True}, "cases": []}

    monkeypatch.setattr(runner, "collect", observe_collect)
    monkeypatch.setattr(runner, "_load_live", construct)
    monkeypatch.setattr(runner, "run", stub_run)
    assert runner.main(cli(runnable_bundle)) == 0
    assert events[-1][0] == "factory"


def test_ordinary_development_without_final_packet_is_unblocked():
    path = REPO / "data/evaluation/dev/pilot-12782.json"
    assert runner.final_preflight([path], None, None) is None
    with offline_network():
        receipt = runner.run([path])
    assert receipt["summary"]["failed"] == 0
    assert receipt["final_artifact_preflight"] is None
    assert receipt["quality_claim"] is False


@pytest.mark.parametrize("reply", ["false", "true", 0, 1, None])
def test_reply_binding_requires_boolean_before_factory(runnable_bundle, monkeypatch, reply):
    calls = forbid_factory(monkeypatch)
    change_fixture(
        runnable_bundle,
        29,
        lambda fixture: fixture["turns"][0]["visible"].update(reply_to_approved_question=reply),
    )
    assert runner.main(cli(runnable_bundle)) == 1
    assert calls == []


@pytest.mark.parametrize(
    "invalid", ["missing", "not_mapping", "unknown_decision", "edit_without_text"]
)
def test_malformed_maintainer_is_not_allowed_to_reach_a_live_factory(
    runnable_bundle, monkeypatch, invalid
):
    calls = forbid_factory(monkeypatch)

    def mutate(fixture):
        turn = fixture["turns"][0]
        if invalid == "missing":
            turn.pop("maintainer")
        elif invalid == "not_mapping":
            turn["maintainer"] = None
        elif invalid == "unknown_decision":
            turn["maintainer"] = {"decision": "unregistered_action"}
        else:
            turn["maintainer"] = {"decision": "edit", "then": "approve"}

    change_fixture(runnable_bundle, 29, mutate)
    assert runner.main(cli(runnable_bundle)) == 1
    assert calls == []


def test_missing_execution_fixture_id_is_rejected_before_factory(runnable_bundle, monkeypatch):
    calls = forbid_factory(monkeypatch)
    change_fixture(runnable_bundle, 29, lambda fixture: fixture.pop("fixture_id"))
    assert runner.main(cli(runnable_bundle)) == 1
    assert calls == []
