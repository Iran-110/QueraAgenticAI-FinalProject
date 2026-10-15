"""Freeze proposal-only current snapshots; no model, key or ledger is accessed.

Only the supplemental D--G evidence is read from the already built local index.
Those reads use the existing candidate/profile engine path once, offline. Later
model refinement receives the same frozen complete records, not another search.
"""

import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from agent_app.contracts import (
    CaseState,
    ConversationEntry,
    EvidenceBundle,
    ProposalRequirements,
    RunLimits,
    TurnConversation,
    UserTurn,
)
from agent_app.orchestration.conversation import build_reasoning_message
from agent_app.orchestration.engine import SupportEngine, _Progress
from agent_app.orchestration.retrieval_context import build_current_query
from agent_app.orchestration.turns import propose_user_turn
from agent_app.reasoning.catalog import caller_catalog, validate_user_gaps
from agent_app.testing.enum_evidence import CASE_PATHS, load_source_packet
from agent_app.testing.fakes import FakeReasoner, FakeRetriever
from agent_app.testing.real_index_probe import _IndexBinding, _ObservedIndexedRetriever

ROOT = Path(__file__).resolve().parents[1]
FOLDER = Path("experiments/core_broader_dev_v1")
PROTOCOL_SHA256 = "504d34bac87142adf9a09b2ab56117d3c752ea7b6b306b2a89ba61acf003b3f6"
SUPPLEMENT = Path("data/evaluation/supplemental-core-dev-v1")
OLD = Path("data/evaluation/dev-three-v1")
OLD_PROTECTED = Path("experiments/core_enum_evidence_v1/protected-inputs-v1.json")
PROTECTED = FOLDER / "protected-inputs-v1.json"
GUIDE = Path("experiments/core_enum_evidence_v1/source-packet-v1.json")
AUXILIARY_PINS = {
    PROTECTED: "658583614304bf99c6890973274d2e683068302fd897422b64e1942773506727",
    OLD_PROTECTED: "b4fa80865c6e604cf40ef925297a684c28a674ef9b9b7c9efb37e5cb15b1c35c",
    FOLDER
    / "bound-amendment-v1.json": "bec06875449f7940e5490207108c4459ebe0e3bda37d7b67c150e75bf00adcdd",
    FOLDER
    / "preparation-amendment-v1.json": "ebfd1aee7d9b002f7ff5b95769288bb70e878fbd4f0632d1086f3a627eafa7bb",
    FOLDER
    / "index-recovery-review-v1.json": "f65beb377b41762d7ccb1be9a99224217c80408c4fc2085eaa977f629ddd1128",
    FOLDER
    / "preparation-first-failure-v1.json": "a6bbdb09abc64423ffa6b0fe22ce635fe6c3e71c439b3928803d79a939407e05",
}
ROW_KEYS = {
    "id",
    "scenario_id",
    "turn_id",
    "case",
    "user_message",
    "evidence",
    "catalog_request",
    "proposal_requirements",
}


class SnapshotRejected(ValueError):
    def __init__(self):
        super().__init__("BroaderDevSnapshotRejected")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    return sha(json.dumps(value, sort_keys=True, ensure_ascii=False).encode())


def read_json(path):
    return json.loads(Path(path).read_bytes())


def input_pins(root):
    names = [
        FOLDER / "protocol-v1.json",
        GUIDE,
        *AUXILIARY_PINS,
        OLD / "evidence-v1.json",
        OLD / "user-gap-vocabulary-v1.json",
        *(Path(path) for path in CASE_PATHS.values()),
        SUPPLEMENT / "input-cases-v1.json",
        SUPPLEMENT / "exposure-v1.json",
        SUPPLEMENT / "review-criteria-v1.json",
    ]
    return {path.as_posix(): sha((root / path).read_bytes()) for path in names}


def verify_protected(root):
    """Guard the explicit repaired epoch, preserving historical physical failure."""
    if any(sha((root / name).read_bytes()) != pin for name, pin in AUXILIARY_PINS.items()):
        raise SnapshotRejected()
    protected = read_json(root / PROTECTED)
    original = read_json(root / OLD_PROTECTED)
    changed = {
        name: {"before": original["files"][name], "after": value}
        for name, value in protected["files"].items()
        if name in original["files"] and original["files"][name] != value
    }
    if (
        len(protected["files"]) != 19
        or set(protected["files"]) != set(original["files"])
        or protected["original_files"] != original["files"]
        or protected["original_physical_matches"] != 17
        or len(changed) != 2
        or protected["original_physical_mismatches"] != changed
        or original["real_index_source_count"] != 18
        or original["real_index_chunk_count"] != 36
        or original["answer_linked_guide_absent_from_index"] is not True
        or protected["logical_corpus_sources"] != 18
        or protected["logical_corpus_chunks"] != 36
        or protected["full_original_manifest_corpus_metadata_vectors_and_exclusions_equal"]
        is not True
        or protected["logical_review_checks_passed"] != 182
        or protected["logical_review_checks_total"] != 182
        or protected["all_future_native_client_reads_copy_only"] is not True
        or any(
            sha((root / name).read_bytes()) != value for name, value in protected["files"].items()
        )
    ):
        raise SnapshotRejected()
    return protected


def current_states(case_id, turns):
    """Use actual state/correction semantics and USER-only historical context."""
    state, entries = CaseState(case_id=case_id), []
    for turn in turns:
        visible = dict(turn["visible"])
        # Old authored replies become explicit current USER version updates.
        # No assistant question, approval or conditional route is manufactured.
        visible.pop("reply_to_approved_question", None)
        event = UserTurn(
            case_id=case_id,
            expected_revision=state.case_revision,
            turn_id=turn["id"],
            source_ref="USER:" + turn["id"],
            **visible,
        )
        transition = propose_user_turn(state, event)
        state = transition.candidate
        entries.append(
            ConversationEntry(
                actor="user",
                reference_id=event.turn_id,
                revision=state.case_revision,
                text=event.message,
            )
        )
        conversation = TurnConversation(
            entries=tuple(entries),
            latest_turn_id=event.turn_id,
            committed_revision=state.case_revision,
            latest_message=event.message,
        )
        yield turn, state, conversation, transition


def read_with_existing_engine(retriever, case, query, snapshot_id, *, candidate):
    """Run only the existing retrieval step: no reasoner method is invoked."""
    progress = _Progress(RunLimits())
    engine = SupportEngine(
        retriever,
        FakeReasoner([]),
        snapshot_id=snapshot_id,
        top_k=5,
        evidence_scope="exact_user_version",
        retrieval_candidate_multiplier=5 if candidate else 1,
        evidence_utf8_budget_bytes=12000 if candidate else None,
        repair_repeated_queries=candidate,
    )
    evidence = engine._retrieve(case, (query,), set(), progress)
    if progress.model_attempts or progress.retrieval_rounds != 1:
        raise SnapshotRejected()
    return evidence, [entry.model_dump(mode="json") for entry in progress.trace]


class NativeFreezer:
    """Query a byte-exact isolated copy, never open the sealed native storage.

    Chroma's PersistentClient can update physical storage during a logical read.
    Therefore the sealed current epoch is hashed/copied before importing it, and
    only the disposable copy is opened. Full logical source/vector verification
    remains the existing _IndexBinding responsibility on every copied read.
    """

    def __init__(self, root, protected):
        registered = dict(read_json(root / OLD_PROTECTED)["real_index_binding"])
        manifests = [
            name
            for name, value in protected["files"].items()
            if value == registered["manifest_sha256"] and Path(name).name == "pilot-manifest.json"
        ]
        if len(manifests) != 1:
            raise SnapshotRejected()
        source = (root / manifests[0]).parent.resolve()
        self._temporary = tempfile.TemporaryDirectory(prefix="broader-dev-native-")
        copied = Path(self._temporary.name) / "index"
        shutil.copytree(source, copied)
        self.original_relative_path = source.relative_to(root).as_posix()
        self.copied_input_hashes = {}
        for name, expected in protected["files"].items():
            path = root / name
            if path.is_relative_to(source):
                relative = path.relative_to(source)
                if (
                    sha(path.read_bytes()) != expected
                    or sha((copied / relative).read_bytes()) != expected
                ):
                    self.close()
                    raise SnapshotRejected()
                self.copied_input_hashes[relative.as_posix()] = expected
        if not self.copied_input_hashes:
            self.close()
            raise SnapshotRejected()
        registered["path"] = str(copied)
        self.binding = _IndexBinding(registered)
        if self.binding.receipt["source_count"] != 18 or self.binding.receipt["chunk_count"] != 36:
            self.close()
            raise SnapshotRejected()

    def close(self):
        self._temporary.cleanup()

    def __call__(self, scenario, turn, case, query):
        records = []
        job = {
            "job_id": f"freeze:{scenario}:{turn['id']}",
            "arm": "freeze_native",
            "case_id": case.case_id,
            "retrieval_candidate_multiplier": 5,
            "retrieval_selection_policy": "query_relevance_v1",
            "record_native_candidates": True,
        }
        retriever = _ObservedIndexedRetriever(self.binding, job, turn, records)
        bundle, trace = read_with_existing_engine(
            retriever,
            case,
            query,
            self.binding.snapshot_id,
            candidate=True,
        )
        allowed = set(self.binding.receipt["source_ids"])
        if any(
            hit.source_type != "doc"
            or hit.source_id not in allowed
            or "custom-classes" in hit.source_id
            for hit in bundle.hits
        ):
            raise SnapshotRejected()
        if len(records) != 1 or records[0]["error_code"] is not None:
            raise SnapshotRejected()
        return bundle, {
            "kind": "offline_verified_existing_index_initial_read",
            "actual_native_index_read": True,
            "model_calls": 0,
            "query": query,
            "profile": "candidate_relevance_v1",
            "candidate_limit": 25,
            "final_top_k": 5,
            "exact_active_USER_scope": True,
            "whole_record_utf8_budget": 12000,
            "index": {
                **{key: value for key, value in self.binding.receipt.items() if key != "path"},
                "original_relative_path": self.original_relative_path,
                "execution_location": "ephemeral_byte_exact_copy",
                "working_path_retained": False,
                "copied_initial_protected_hashes": self.copied_input_hashes,
                "complete_documents_metadata_vectors_verified": True,
                "original_manifest_and_logical_source_identity_preserved": True,
            },
            "actual_retrieval": records[0],
            "engine_trace": trace,
        }


def _old_scenarios(root, guide):
    evidence = read_json(root / OLD / "evidence-v1.json")["evidence_bundles"]
    scenarios = []
    for scenario, key in (
        ("dev-a", "dev-case-a"),
        ("dev-b", "dev-case-b"),
        ("enum-guide", "dev-case-c"),
        ("enum-withheld", "dev-case-c"),
    ):
        relative = CASE_PATHS[key]
        original = read_json(root / relative)
        turns = []
        for item in original["turns"]:
            visible = dict(item["visible"])
            if visible.pop("reply_to_approved_question", False):
                visible["reported_facts"] = [
                    {"name": "streamlit_version", "value": visible["message"]}
                ]
            turns.append(
                {
                    "id": item["id"],
                    "visible": visible,
                    "raw_bundle": evidence[item["evidence_bundle"]],
                    "runner_gold": item["gold"],
                }
            )
        scenarios.append(
            {
                "scenario_id": scenario,
                "case_id": original["case"]["case_id"],
                "turns": turns,
                "original_fixture_path": relative,
                "guide_present": scenario == "enum-guide",
            }
        )
    return scenarios


def _supplement_criteria(review, scenario, turn_id):
    rows = review["snapshots"]
    matches = [row for row in rows if row["scenario_id"] == scenario and row["turn_id"] == turn_id]
    if len(matches) != 1:
        raise SnapshotRejected()
    return matches[0]


def prepare_snapshots(root=ROOT, *, native_freezer=None):
    root = Path(root).resolve()
    protocol_raw = (root / FOLDER / "protocol-v1.json").read_bytes()
    if sha(protocol_raw) != PROTOCOL_SHA256:
        raise SnapshotRejected()
    protocol = json.loads(protocol_raw)
    pins = input_pins(root)
    protected_before = verify_protected(root)
    supplement = read_json(root / SUPPLEMENT / "input-cases-v1.json")
    review = read_json(root / SUPPLEMENT / "review-criteria-v1.json")
    if supplement["protocol_sha256"] != PROTOCOL_SHA256 or len(supplement["cases"]) != 4:
        raise SnapshotRejected()
    guide_path = root / GUIDE
    if sha(guide_path.read_bytes()) != protocol["inputs"]["old_Enum_source_packet_sha256"]:
        raise SnapshotRejected()
    guide = load_source_packet(guide_path)
    definitions = validate_user_gaps(
        (
            *read_json(root / OLD / "user-gap-vocabulary-v1.json")["user_gaps"],
            *supplement["user_gap_vocabulary"]["user_gaps"],
        )
    )
    scenarios = _old_scenarios(root, guide) + supplement["cases"]
    if [item["scenario_id"] for item in scenarios] != protocol["scenarios"]:
        raise SnapshotRejected()
    owns_native_freezer = False
    snapshots, provenance, matrix = [], [], []
    for scenario in scenarios:
        name = scenario["scenario_id"]
        if len(scenario["turns"]) != 2:
            raise SnapshotRejected()
        for turn, case, conversation, transition in current_states(
            scenario["case_id"], scenario["turns"]
        ):
            identity = name + ":" + turn["id"]
            message = build_reasoning_message(conversation)
            query = build_current_query(case, conversation)
            if "raw_bundle" in turn:
                raw = json.loads(json.dumps(turn["raw_bundle"]))
                if scenario["guide_present"]:
                    raw["hits"] += [record["hit"] for record in guide["source_records"]]
                validated = EvidenceBundle.model_validate(raw)
                evidence, trace = read_with_existing_engine(
                    FakeRetriever([validated]),
                    case,
                    query,
                    validated.snapshot_id,
                    candidate=False,
                )
                observation = {
                    "kind": "historical_static_fixture_then_exact_USER_scope",
                    "actual_native_index_read": False,
                    "model_calls": 0,
                    "query_logged_not_search": query,
                    "original_fixture_path": scenario["original_fixture_path"],
                    "registered_raw_bundle": raw,
                    "registered_raw_bundle_sha256": digest(raw),
                    "validated_raw_bundle_sha256": digest(validated.model_dump(mode="json")),
                    "raw_hit_count": len(validated.hits),
                    "engine_trace": trace,
                    "answer_linked_guide_supplied_fixture_only": scenario["guide_present"],
                }
                criteria = (
                    {
                        "acceptable_final_decisions": ["answer", "escalate"],
                        "condition": protocol["prospective_quality"]["Enum_guide_required"],
                    }
                    if scenario["guide_present"]
                    else {
                        "historical_gold_condition_only": turn["runner_gold"],
                        "original_fixture_path": scenario["original_fixture_path"],
                    }
                )
            else:
                if native_freezer is None:
                    native_freezer = NativeFreezer(root, protected_before)
                    owns_native_freezer = True
                evidence, observation = native_freezer(name, turn, case, query)
                criteria = _supplement_criteria(review, name, turn["id"])
            request = caller_catalog(case, message, evidence, definitions=definitions)
            requirements = ProposalRequirements(
                case_id=case.case_id,
                case_revision=case.case_revision,
                question_targets=tuple(
                    {"name": gap.name, "question": gap.question}
                    for gap in request.gaps
                    if gap.kind == "user"
                ),
            )
            row = {
                "id": identity,
                "scenario_id": name,
                "turn_id": turn["id"],
                "case": case.model_dump(mode="json"),
                "user_message": message,
                "evidence": evidence.model_dump(mode="json"),
                "catalog_request": request.model_dump(mode="json"),
                "proposal_requirements": requirements.model_dump(mode="json"),
            }
            if set(row) != ROW_KEYS:
                raise SnapshotRejected()
            snapshots.append(row)
            provenance.append(
                {
                    "snapshot_id": identity,
                    **observation,
                    "final_bundle_sha256": digest(row["evidence"]),
                    "current_USER_conversation": conversation.model_dump(mode="json"),
                    "transition_sha256": digest(transition.model_dump(mode="json")),
                    "changed_fact_names": list(transition.changed_fact_names),
                    "invalidated_checks": list(transition.invalidated_checks),
                    "post_scope_hit_count": len(evidence.hits),
                }
            )
            matrix.append(
                {
                    "snapshot_id": identity,
                    "scenario_id": name,
                    "turn_id": turn["id"],
                    "known_active_USER_facts": [
                        fact.model_dump(mode="json")
                        for fact in case.facts
                        if fact.status == "active" and fact.provenance_kind == "user"
                    ],
                    "recorded_checks": list(case.checks_performed),
                    "necessary_registered_USER_gaps": [
                        gap.model_dump(mode="json") for gap in request.gaps if gap.kind == "user"
                    ],
                    "caller_source_gaps": [
                        gap.model_dump(mode="json") for gap in request.gaps if gap.kind == "source"
                    ],
                    "actual_source_ids": [hit.source_id for hit in evidence.hits],
                    "review_criteria_runner_only": criteria,
                }
            )
    if len(snapshots) != 16 or len({row["id"] for row in snapshots}) != 16:
        raise SnapshotRejected()
    if owns_native_freezer:
        native_freezer.close()
    if verify_protected(root) != protected_before:
        raise SnapshotRejected()
    if input_pins(root) != pins:
        raise SnapshotRejected()
    packet = {
        "schema_version": 1,
        "packet_id": "core-broader-dev-snapshots-v1",
        "protocol_sha256": PROTOCOL_SHA256,
        "input_pins": pins,
        "boundaries": {
            "proposal_only": True,
            "model_calls": 0,
            "actions_executed": 0,
            "held_out_test": False,
            "real_RAG_quality_score": False,
            "guide_fixture_only": True,
            "future_gold_reviews_not_in_snapshot_rows": True,
            "rows_already_exact_active_USER_scoped": True,
            "paid_runner_evidence_scope": "all",
            "refinement_reuses_same_fixed_complete_bundle": True,
        },
        "snapshots": snapshots,
        "source_observations_runner_only": provenance,
    }
    native_observations = [
        item for item in provenance if item.get("actual_native_index_read") is True
    ]
    native_verified = len(native_observations) == 8 and all(
        item["index"]["execution_location"] == "ephemeral_byte_exact_copy"
        and item["index"]["complete_documents_metadata_vectors_verified"] is True
        and item["index"]["original_manifest_and_logical_source_identity_preserved"] is True
        and item["index"]["source_count"] == 18
        and item["index"]["chunk_count"] == 36
        and item["actual_retrieval"]["error_code"] is None
        for item in native_observations
    )
    preparation = {
        "schema_version": 1,
        "preparation_id": "core-broader-dev-preparation-v1",
        "accepted": native_verified,
        "protocol_sha256": PROTOCOL_SHA256,
        "protected_epoch_sha256": pins[PROTECTED.as_posix()],
        "registered_before_model": True,
        "model_calls": 0,
        "actual_sends": 0,
        "actions_executed": 0,
        "human_usefulness": None,
        "snapshot_count": 16,
        "unique_report_families": 7,
        "snapshot_packet_sha256": None,
        "input_pins": pins,
        "current_epoch19_files_unchanged": True,
        "historical_original19_files_unchanged": False,
        "historical_original_physical_matches": protected_before["original_physical_matches"],
        "historical_original_physical_mismatches": protected_before["original_physical_mismatches"],
        "original18_sources36_chunks_metadata_vectors_exclusions_equal": True,
        "native_client_isolated_copy_only": True,
        "preparation_first_physical_failure_preserved": True,
        "operational_bounds_amended_before_paid_calls": True,
        "all16_current_state_rows_frozen": True,
        "all16_evidence_and_catalog_contracts_constructed": True,
        "all_old_fixture_raw_records_retained_runner_only": True,
        "all_native_results_verified_against_original_logical_manifest": native_verified,
        "native_issues_comments_guide_excluded": native_verified,
        "model_payload_preflight_not_part_of_this_preparation": True,
        "raw_fixture_vs_actual_model_input": (
            "Original raw A/B/C bundles remain in runner-only provenance. Existing exact "
            "active-USER-version scope is applied before freezing model inputs: unknown-version "
            "A/B initially receive no versioned records; unversioned C records remain. "
            "D--G use one real initial candidate read/post-scope whole-record budget, frozen "
            "for both arms and any later refinement. No model has run and no gold/criteria "
            "or future reply is included in the eight-field snapshot rows."
        ),
        "scenarios": matrix,
    }
    return packet, preparation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    packet, preparation = prepare_snapshots()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    packet_raw = (json.dumps(packet, ensure_ascii=False, indent=2) + "\n").encode()
    preparation["snapshot_packet_sha256"] = sha(packet_raw)
    (args.output_dir / "snapshots-v1.json").write_bytes(packet_raw)
    (args.output_dir / "preparation-v1.json").write_text(
        json.dumps(preparation, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"snapshots": 16, "model_calls": 0, "actions_executed": 0}))


if __name__ == "__main__":
    main()
