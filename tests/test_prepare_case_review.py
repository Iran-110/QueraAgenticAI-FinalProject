import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data/evaluation/dev-three-v1/split-manifest.json"
spec = importlib.util.spec_from_file_location(
    "prepare_case_review", ROOT / "scripts/prepare_case_review.py"
)
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


def test_template_starts_unjudged_and_binds_inputs():
    sheet, template = review.build(MANIFEST)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert [case["fixture_path"] for case in template["cases"]] == manifest["fixture_paths"]
    assert template["reviewer_kind"] == "human"
    for case in template["cases"]:
        assert case["accept_case_for_dev"] is None
        assert case["family_confirmed"] is None
        assert case["missing_family_issue_ids"] == []
        assert all(
            value is None
            for turn in case["turns"]
            for key, value in turn.items()
            if key != "turn_id"
        )
        assert f"## {case['case_id']}" in sheet


def test_seed_cross_links_find_mentions_outside_family():
    issues, comments, links = review._seed()

    assert "#8129 mentions #2379" in review._cross_links([2379], issues, comments, links)
    assert review._cross_links([2379, 8129, 8180], issues, comments, links) == []


def test_refuses_existing_output(tmp_path):
    with pytest.raises(SystemExit):
        review.main(["--manifest", str(MANIFEST), "--output", str(tmp_path)])
