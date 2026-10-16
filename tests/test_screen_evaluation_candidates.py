import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "screen_evaluation_candidates", ROOT / "scripts/screen_evaluation_candidates.py"
)
screen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(screen)
MANIFEST = ROOT / "data/evaluation/split-e1-v1/split-manifest.json"


def test_screen_covers_seed_and_flags_exposure():
    rows = {row["issue_id"]: row for row in screen.screen()}

    assert len(rows) == 240
    assert rows[12782]["development_exposed"] and rows[12782]["used_in_dev_three"]
    assert rows[8129]["kind"] in {"bug", "regression", "feature_request", "other"}
    assert 2379 in rows[8129]["linked_issue_ids"]


def test_split_manifest_keeps_families_and_exposure_apart():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    families = manifest["families"]
    dev = {i for f in families if f["split"] == "dev" for i in f["exclude_issue_ids"]}
    test = {i for f in families if f["split"] == "test" for i in f["exclude_issue_ids"]}
    exposed = set(
        json.loads(
            (ROOT / "data/evaluation/dev-three-v1/split-manifest.json").read_text(encoding="utf-8")
        )["development_exposure_issue_ids"]
    )

    assert not dev & test
    assert not test & exposed
    assert manifest["counts"]["dev_families"] >= manifest["targets"]["dev_cases"]
    assert manifest["counts"]["test_families"] >= manifest["targets"]["test_cases"]
    assert dev | test <= set(manifest["index_exclusion"]["issue_ids"])
