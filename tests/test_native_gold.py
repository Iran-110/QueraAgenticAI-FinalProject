import hashlib
import json
from pathlib import Path

from agent_app.evaluation.evidence_observation import (
    PassageRequirement,
    passage_requirements_sha256,
)

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "data/evaluation/split-e1-v1/native"
REGISTRATION = NATIVE / "native-registration-dev-v1.json"
SEED = ROOT / "streamlit-data-for-dev-test/sources"


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _seed():
    records = {}
    for name in ("docs_scope_candidates.jsonl", "docstrings_scope_candidates.jsonl"):
        for line in (SEED / name).open(encoding="utf-8"):
            record = json.loads(line)
            records[record["source_id"]] = record
    return records


def _sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def test_registration_pins_every_native_dev_fixture():
    registration = _load(REGISTRATION)
    registered = {entry["path"]: entry["sha256"] for entry in registration["fixtures"]}
    on_disk = sorted(str(p.relative_to(ROOT)) for p in (NATIVE / "dev").glob("*.json"))

    assert sorted(registered) == on_disk
    assert all(_sha(path) == sha for path, sha in registered.items())
    assert registration["pins"]["build"] == "pending_final_build"
    assert registration["split_manifest_sha256"] == _sha(registration["split_manifest"])


def test_native_fixture_keeps_the_fixed_case_and_only_changes_gold():
    manifest = _load(ROOT / "data/evaluation/split-e1-v1/split-manifest.json")
    fixed = {entry["path"]: entry["sha256"] for entry in manifest["registered_fixtures"]["dev"]}
    for entry in _load(REGISTRATION)["fixtures"]:
        native = _load(ROOT / entry["path"])
        source = native["native_of"]
        original = _load(ROOT / source["path"])

        assert fixed[source["path"]] == source["sha256"] == _sha(source["path"])
        assert native["fixture_id"] != original["fixture_id"]
        assert native["case"] == original["case"]
        assert [t["visible"] for t in native["turns"]] == [t["visible"] for t in original["turns"]]
        assert all(t["gold"]["evidence_condition"] == "native_index" for t in native["turns"])
        assert native["native_scope"]["build"] == "pending_final_build"


def test_passage_requirements_validate_hash_and_exist_in_seed_text():
    seed = _seed()
    for entry in _load(REGISTRATION)["fixtures"]:
        for turn in _load(ROOT / entry["path"])["turns"]:
            passages = turn["gold"]["native_passages"]
            for kind in ("answer_required", "optional_claim_support"):
                block = passages[kind]
                if block is None:
                    continue
                models = tuple(PassageRequirement.model_validate(r) for r in block["requirements"])
                assert passage_requirements_sha256(models) == block["requirements_sha256"]
                for requirement in block["requirements"]:
                    for anchor in requirement["alternatives"]:
                        record = seed[anchor["source_id"]]
                        assert anchor["passage"] in record["text"]
                        assert anchor["source_commit"] == record["docs_commit"]
                        assert anchor["source_url"] == record["pinned_source_url"]


def test_review_covers_every_fixture_at_its_final_bytes():
    review = _load(NATIVE / "native-dev-gold-review-v1.json")
    final = {item["fixture_path"]: item for item in review["items"]}

    assert sorted(final) == sorted(e["path"] for e in _load(REGISTRATION)["fixtures"])
    for path, item in final.items():
        assert item["final_sha256"] == _sha(path)
        assert item["final_verdict"] == "correct"
        assert (item["reviewed_sha256"] == item["final_sha256"]) or item.get("amendment")
