"""Current-state fixed snapshots without a model, credentials or native-index writes."""

import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest

from agent_app.contracts import CaseState, EvidenceBundle, GroundedRequest, ProposalRequirements
from agent_app.orchestration.conversation import build_reasoning_message
from agent_app.reasoning.grounding import make_grounded_request
from agent_app.testing.fakes import FakeRetriever

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_IDS = (
    "dev-a:initial",
    "dev-a:version",
    "dev-b:initial",
    "dev-b:version",
    "enum-guide:initial",
    "enum-guide:correction",
    "enum-withheld:initial",
    "enum-withheld:correction",
    "dev-d-4713:initial",
    "dev-d-4713:update",
    "dev-e-5618:initial",
    "dev-e-5618:update",
    "dev-f-7206:initial",
    "dev-f-7206:update",
    "dev-g-9487:initial",
    "dev-g-9487:update",
)


def module():
    spec = importlib.util.spec_from_file_location(
        "broader_snapshot_offline_control", ROOT / "scripts/prepare_broader_dev_snapshots.py"
    )
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


@pytest.fixture
def prepared(monkeypatch):
    builder = module()
    protected = builder.read_json(ROOT / builder.PROTECTED)
    monkeypatch.setattr(builder, "verify_protected", lambda _root: deepcopy(protected))
    native_calls = []

    def offline_native(scenario, turn, case, query):
        native_calls.append((scenario, turn["id"], case, query))
        return EvidenceBundle(snapshot_id="offline-test-empty"), {
            "kind": "test_only_empty_native_supplier",
            "actual_native_index_read": False,
            "model_calls": 0,
        }

    packet, preparation = builder.prepare_snapshots(native_freezer=offline_native)
    return builder, packet, preparation, native_calls


def by_id(packet):
    return {row["id"]: row for row in packet["snapshots"]}


def active(row):
    return {
        fact["name"]: fact["value"]
        for fact in row["case"]["facts"]
        if fact["status"] == "active" and fact["provenance_kind"] == "user"
    }


def test_all_sixteen_rows_bind_actual_current_contracts_and_user_questions(prepared):
    builder, packet, preparation, native_calls = prepared
    assert len(packet["snapshots"]) == len(by_id(packet)) == 16
    assert len(native_calls) == 8
    assert preparation["snapshot_count"] == 16 and preparation["unique_report_families"] == 7
    for row in packet["snapshots"]:
        assert set(row) == builder.ROW_KEYS
        case = CaseState.model_validate(row["case"])
        evidence = EvidenceBundle.model_validate(row["evidence"])
        request = GroundedRequest.model_validate(row["catalog_request"])
        requirements = ProposalRequirements.model_validate(row["proposal_requirements"])
        assert request.case == case and request.evidence == evidence
        assert request.user_message == row["user_message"]
        assert request == make_grounded_request(
            case, row["user_message"], evidence, gaps=request.gaps
        )
        assert requirements.case_id == case.case_id
        assert requirements.case_revision == case.case_revision
        assert {(item.name, item.question) for item in requirements.question_targets} == {
            (gap.name, gap.question) for gap in request.gaps if gap.kind == "user"
        }
        assert not any("documentation" in item.name for item in requirements.question_targets)


def test_unknown_initial_versions_get_no_versioned_records_but_raw_fixture_is_retained(prepared):
    _, packet, _, _ = prepared
    rows = by_id(packet)
    observations = {row["snapshot_id"]: row for row in packet["source_observations_runner_only"]}
    for name in ("dev-a", "dev-b"):
        initial = rows[name + ":initial"]
        assert "streamlit_version" not in active(initial)
        assert initial["evidence"]["hits"] == []
        assert observations[name + ":initial"]["registered_raw_bundle"]["hits"]
    for name, version in (("dev-a", "1.50.0"), ("dev-b", "1.39.0")):
        update = next(
            row
            for row in packet["snapshots"]
            if row["scenario_id"] == name and row["turn_id"] != "initial"
        )
        assert active(update)["streamlit_version"] == version
        assert update["evidence"]["hits"]
        assert all(
            not hit["applicable_versions"] or version in hit["applicable_versions"]
            for hit in update["evidence"]["hits"]
        )
        assert update["user_message"].endswith(version)
        assert not any(
            entry["actor"] != "user"
            for entry in observations[update["id"]]["current_USER_conversation"]["entries"]
        )


def test_guide_is_only_enum_fixture_condition_and_never_supplemental_native(prepared):
    _, packet, _, _ = prepared
    rows = by_id(packet)
    for turn in ("initial", "correction"):
        withheld = rows["enum-withheld:" + turn]
        supplied = rows["enum-guide:" + turn]
        assert supplied["case"] == withheld["case"]
        assert supplied["user_message"] == withheld["user_message"]
        assert len(supplied["evidence"]["hits"]) == len(withheld["evidence"]["hits"]) + 2
        assert supplied["evidence"]["hits"][:1] == withheld["evidence"]["hits"]
        assert all("custom-classes" in hit["source_id"] for hit in supplied["evidence"]["hits"][1:])
    correction = rows["enum-guide:correction"]
    assert active(correction)["streamlit_version"] == "1.31.1"
    assert all(
        item["name"] != "streamlit_version"
        for item in correction["proposal_requirements"]["question_targets"]
    )


def test_supplemental_updates_preserve_current_user_authority_and_retire_resolved_gaps(prepared):
    _, packet, preparation, _ = prepared
    rows = by_id(packet)
    d_initial, d_update = rows["dev-d-4713:initial"], rows["dev-d-4713:update"]
    assert [x["name"] for x in d_initial["proposal_requirements"]["question_targets"]] == [
        "click_runtime_details"
    ]
    assert d_update["proposal_requirements"]["question_targets"] == []
    assert active(d_update)["click_version"] == "8.1.3"
    assert len(d_update["case"]["checks_performed"]) == 3
    g_initial, g_update = rows["dev-g-9487:initial"], rows["dev-g-9487:update"]
    assert active(g_initial)["streamlit_version"] == active(g_update)["streamlit_version"] == "1.38"
    assert [x["name"] for x in g_initial["proposal_requirements"]["question_targets"]] == [
        "visual_persistence"
    ]
    assert g_update["proposal_requirements"]["question_targets"] == []
    e = rows["dev-e-5618:update"]
    assert active(e)["launch_command"] == "streamlit run app.py"
    assert not any(
        fact["name"] == "launch_command"
        and fact["value"] == "python app.py"
        and fact["status"] == "active"
        for fact in e["case"]["facts"]
    )
    f_initial, f_update = rows["dev-f-7206:initial"], rows["dev-f-7206:update"]
    before, after = active(f_initial), active(f_update)
    assert before["streamlit_version"] == "1.25.0" and after["streamlit_version"] == "1.25.1"
    for name in (
        "python_version",
        "operating_system",
        "browser",
        "streamlit_authenticator_version",
    ):
        assert before[name] == after[name]
    for matrix in preparation["scenarios"]:
        if matrix["scenario_id"].startswith("dev-") and matrix["scenario_id"] not in {
            "dev-a",
            "dev-b",
        }:
            criteria = matrix["review_criteria_runner_only"]
            actual = active(rows[matrix["snapshot_id"]])
            assert criteria["known_current_user_facts"].items() <= actual.items()
            assert (
                criteria["known_current_checks"]
                == rows[matrix["snapshot_id"]]["case"]["checks_performed"]
            )


def test_history_is_user_only_and_future_gold_is_not_in_model_rows(prepared):
    _, packet, preparation, _ = prepared
    rows = by_id(packet)
    from agent_app.contracts import TurnConversation

    for observation in packet["source_observations_runner_only"]:
        row = rows[observation["snapshot_id"]]
        conversation = TurnConversation.model_validate(observation["current_USER_conversation"])
        assert all(entry.actor == "user" for entry in conversation.entries)
        assert row["user_message"] == build_reasoning_message(conversation)
        assert len(conversation.entries) == row["case"]["case_revision"]
        assert "review_criteria_runner_only" not in row
        assert "gold" not in row and "agent_script" not in row and "maintainer" not in row
    assert all("review_criteria_runner_only" in item for item in preparation["scenarios"])
    assert "8.1.3" not in rows["dev-d-4713:initial"]["user_message"]
    assert "1.31.1" not in rows["enum-guide:initial"]["user_message"]
    assert packet["boundaries"]["held_out_test"] is False
    assert packet["boundaries"]["real_RAG_quality_score"] is False
    assert packet["boundaries"]["actions_executed"] == 0


def test_retrieval_step_has_no_reasoner_invocation_and_exact_user_scope(monkeypatch):
    builder = module()

    def forbidden(*_args, **_kwargs):
        raise AssertionError("reasoner invoked during offline snapshot preparation")

    monkeypatch.setattr(builder.FakeReasoner, "analyze", forbidden)
    old = builder.read_json(ROOT / builder.OLD / "evidence-v1.json")["evidence_bundles"]
    raw = EvidenceBundle.model_validate(next(value for value in old.values() if value["hits"]))
    bundle, trace = builder.read_with_existing_engine(
        FakeRetriever([raw]),
        CaseState(case_id="offline-no-version"),
        "test",
        raw.snapshot_id,
        candidate=False,
    )
    assert all(not hit.applicable_versions for hit in bundle.hits)
    assert not any(item["stage"] == "reason" for item in trace)


def test_native_freezer_opens_only_verified_copy_even_if_client_writes(tmp_path, monkeypatch):
    builder = module()
    source = tmp_path / "runtime" / "index"
    source.mkdir(parents=True)
    manifest, sqlite = source / "pilot-manifest.json", source / "chroma.sqlite3"
    manifest.write_bytes(b"pinned manifest")
    sqlite.write_bytes(b"sealed SQLite bytes")
    before = {
        path.relative_to(tmp_path).as_posix(): builder.sha(path.read_bytes())
        for path in (manifest, sqlite)
    }
    protected = {
        "files": before,
        "real_index_binding": {
            "path": str(source),
            "snapshot_id": "copy-control",
            "manifest_sha256": before[manifest.relative_to(tmp_path).as_posix()],
        },
    }
    old = tmp_path / builder.OLD_PROTECTED
    old.parent.mkdir(parents=True)
    old.write_text(json.dumps(protected))
    opened = []

    class WritingClient:
        def __init__(self, registered):
            copy = Path(registered["path"])
            assert copy != source and not copy.is_relative_to(source)
            assert (copy / "chroma.sqlite3").read_bytes() == b"sealed SQLite bytes"
            opened.append(copy)
            (copy / "chroma.sqlite3").write_bytes(b"read-side persistence")
            self.receipt = {"source_count": 18, "chunk_count": 36}

    monkeypatch.setattr(builder, "_IndexBinding", WritingClient)
    freezer = builder.NativeFreezer(tmp_path, protected)
    assert (
        opened
        and freezer.copied_input_hashes["chroma.sqlite3"]
        == before[sqlite.relative_to(tmp_path).as_posix()]
    )
    assert sqlite.read_bytes() == b"sealed SQLite bytes"
    freezer.close()
    assert not opened[0].exists()
    assert {name: builder.sha((tmp_path / name).read_bytes()) for name in before} == before


def test_native_copy_hash_mismatch_rejects_before_chroma_open(tmp_path, monkeypatch):
    builder = module()
    source = tmp_path / "runtime" / "index"
    source.mkdir(parents=True)
    (source / "pilot-manifest.json").write_bytes(b"manifest")
    (source / "chroma.sqlite3").write_bytes(b"changed")
    protected = {
        "files": {
            "runtime/index/pilot-manifest.json": builder.sha(b"manifest"),
            "runtime/index/chroma.sqlite3": builder.sha(b"registered"),
        },
        "real_index_binding": {
            "path": str(source),
            "snapshot_id": "copy-control",
            "manifest_sha256": builder.sha(b"manifest"),
        },
    }
    old = tmp_path / builder.OLD_PROTECTED
    old.parent.mkdir(parents=True)
    old.write_text(json.dumps(protected))

    def forbidden(*_args):
        raise AssertionError("opened Chroma before the copied-byte guard")

    monkeypatch.setattr(builder, "_IndexBinding", forbidden)
    with pytest.raises(builder.SnapshotRejected, match="BroaderDevSnapshotRejected"):
        builder.NativeFreezer(tmp_path, protected)


def test_protocol_drift_rejected_before_any_protected_or_native_access(tmp_path, monkeypatch):
    builder = module()
    folder = tmp_path / builder.FOLDER
    folder.mkdir(parents=True)
    (folder / "protocol-v1.json").write_text("{}")

    def forbidden(*_args):
        raise AssertionError("accessed source after protocol drift")

    monkeypatch.setattr(builder, "verify_protected", forbidden)
    monkeypatch.setattr(builder, "NativeFreezer", forbidden)
    with pytest.raises(builder.SnapshotRejected, match="BroaderDevSnapshotRejected"):
        builder.prepare_snapshots(tmp_path)


def test_registered_current_epoch_drift_rejected_without_rewriting_old_map(tmp_path, monkeypatch):
    builder = module()
    folder = tmp_path / builder.PROTECTED.parent
    folder.mkdir(parents=True)
    files = {}
    for index in range(19):
        path = tmp_path / f"protected-{index}.txt"
        path.write_bytes(str(index).encode())
        files[path.name] = builder.sha(path.read_bytes())
    original_files = {**files, "protected-0.txt": "old-zero", "protected-1.txt": "old-one"}
    original = {
        "files": original_files,
        "real_index_source_count": 18,
        "real_index_chunk_count": 36,
        "answer_linked_guide_absent_from_index": True,
    }
    old = tmp_path / builder.OLD_PROTECTED
    old.parent.mkdir(parents=True)
    old.write_text(json.dumps(original))
    protected = {
        "files": files,
        "original_files": original_files,
        "original_physical_matches": 17,
        "original_physical_mismatches": {
            name: {"before": original_files[name], "after": files[name]}
            for name in ("protected-0.txt", "protected-1.txt")
        },
        "logical_corpus_sources": 18,
        "logical_corpus_chunks": 36,
        "full_original_manifest_corpus_metadata_vectors_and_exclusions_equal": True,
        "logical_review_checks_passed": 182,
        "logical_review_checks_total": 182,
        "all_future_native_client_reads_copy_only": True,
    }
    (tmp_path / builder.PROTECTED).write_text(json.dumps(protected))
    monkeypatch.setattr(builder, "AUXILIARY_PINS", {})
    assert builder.verify_protected(tmp_path) == protected
    (tmp_path / "protected-18.txt").write_bytes(b"drift")
    with pytest.raises(builder.SnapshotRejected, match="BroaderDevSnapshotRejected"):
        builder.verify_protected(tmp_path)


def test_concurrent_input_edit_is_not_bound_to_the_old_rows(prepared, monkeypatch):
    builder, _, _, _ = prepared
    calls = []

    def changing_pins(_root):
        calls.append(True)
        return {"synthetic-caller-input.json": "before" if len(calls) == 1 else "after"}

    monkeypatch.setattr(builder, "input_pins", changing_pins)

    def inert_native(*_args):
        return EvidenceBundle(snapshot_id="offline-drift-control"), {"model_calls": 0}

    with pytest.raises(builder.SnapshotRejected, match="BroaderDevSnapshotRejected"):
        builder.prepare_snapshots(native_freezer=inert_native)
    assert len(calls) == 2


@pytest.mark.parametrize("identity", SNAPSHOT_IDS)
def test_frozen_each_complete_current_bundle_is_reproducible_without_native_access(identity):
    """Replay persisted raw evidence through existing scope/packing, not a new search."""
    builder = module()
    packet = builder.read_json(ROOT / builder.FOLDER / "snapshots-v1.json")
    row = by_id(packet)[identity]
    observation = next(
        value
        for value in packet["source_observations_runner_only"]
        if value["snapshot_id"] == identity
    )
    native = observation["actual_native_index_read"]
    raw = (
        observation["actual_retrieval"]["evidence"]
        if native
        else observation["registered_raw_bundle"]
    )
    supplied = EvidenceBundle.model_validate(raw)
    final, trace = builder.read_with_existing_engine(
        FakeRetriever([supplied]),
        CaseState.model_validate(row["case"]),
        observation["query"] if native else observation["query_logged_not_search"],
        supplied.snapshot_id,
        candidate=native,
    )
    assert final.model_dump(mode="json") == row["evidence"]
    assert trace == observation["engine_trace"]
    assert builder.digest(row["evidence"]) == observation["final_bundle_sha256"]
    request = GroundedRequest.model_validate(row["catalog_request"])
    assert request == make_grounded_request(
        CaseState.model_validate(row["case"]), row["user_message"], final, gaps=request.gaps
    )
    if native:
        assert len(final.hits) <= 5
        assert len(final.model_dump_json().encode()) <= 12000
        index = observation["index"]
        assert index["execution_location"] == "ephemeral_byte_exact_copy"
        assert index["source_count"] == 18 and index["chunk_count"] == 36
        assert "path" not in index and index["working_path_retained"] is False
        assert index["complete_documents_metadata_vectors_verified"] is True
        assert all(
            hit.source_type == "doc" and hit.source_id in index["source_ids"] for hit in final.hits
        )
        assert all("custom-classes" not in hit.source_id for hit in supplied.hits)
        actual = observation["actual_retrieval"]
        assert actual["requested"]["top_k"] == actual["executed"]["top_k"] == 25
        assert actual["error_code"] is None
        assert actual["requested"]["filters"] == {}
        native_ids = set()
        for call in actual["native_calls"]:
            assert call["filters"] == {} and call["n_results"] == 25
            assert call["collections"]["issues"] == []
            native_ids.update(value["chunk_id"] for value in call["collections"]["docs"])
        assert {hit.chunk_id for hit in supplied.hits} <= native_ids


def test_committed_preparation_pins_exact_packet_and_discloses_physical_epoch_repair():
    builder = module()
    raw = (ROOT / builder.FOLDER / "snapshots-v1.json").read_bytes()
    packet = json.loads(raw)
    preparation = builder.read_json(ROOT / builder.FOLDER / "preparation-v1.json")
    assert tuple(row["id"] for row in packet["snapshots"]) == SNAPSHOT_IDS
    assert preparation["snapshot_packet_sha256"] == builder.sha(raw)
    assert preparation["accepted"] is True
    assert preparation["model_calls"] == preparation["actual_sends"] == 0
    assert preparation["current_epoch19_files_unchanged"] is True
    assert preparation["historical_original19_files_unchanged"] is False
    assert preparation["historical_original_physical_matches"] == 17
    assert len(preparation["historical_original_physical_mismatches"]) == 2
    assert preparation["original18_sources36_chunks_metadata_vectors_exclusions_equal"] is True
    assert preparation["native_client_isolated_copy_only"] is True
    assert preparation["preparation_first_physical_failure_preserved"] is True
    assert preparation["human_usefulness"] is None
    assert preparation["input_pins"] == packet["input_pins"]
    # Only committed inputs here: tests never require ignored physical index files.
    for name, expected in packet["input_pins"].items():
        assert builder.sha((ROOT / name).read_bytes()) == expected
    assert preparation["protected_epoch_sha256"] == builder.AUXILIARY_PINS[builder.PROTECTED]


def test_inert_test_supplier_cannot_claim_actual_native_preparation_accepted(prepared):
    _, _, preparation, _ = prepared
    assert preparation["accepted"] is False
    assert preparation["all_native_results_verified_against_original_logical_manifest"] is False
