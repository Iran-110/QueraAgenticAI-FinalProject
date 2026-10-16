"""Screen the seed Issues for E1 case selection; never selects or freezes a split.

Reads only the packaged seed (Issue bodies and metadata, comment links) and the
existing candidate reservations. For each Issue it records signals a curator
uses to judge whether the Issue can become a support case: bug vs feature
request, a reproduction, a reported version, closure reason, seed-linked
neighbours and exposure. Comment *texts* are only scanned for Issue references
(family links); answers and outcomes are not summarised.

    uv run python scripts/screen_evaluation_candidates.py --output runtime/e1-screen-FRESH
"""

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "streamlit-data-for-dev-test"
CATALOG = SEED / "sources/github-snapshot-2026-10-06/catalog"
RESERVATIONS = ROOT / "data/evaluation/candidates/reservations-v1.json"
DEV_THREE = ROOT / "data/evaluation/dev-three-v1/split-manifest.json"
ISSUE_REF = re.compile(r"(?:#|streamlit/streamlit/issues/)(\d{2,5})\b")
VERSION = re.compile(r"Streamlit version:?\**\s*`?v?(\d+\.\d+(?:\.\d+)?)", re.I)


def _jsonl(path):
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _labels(issue):
    return [
        label if isinstance(label, str) else label["name"] for label in issue.get("labels") or []
    ]


def _kind(labels):
    if "type:regression" in labels:
        return "regression"
    if "type:bug" in labels:
        return "bug"
    if "type:enhancement" in labels:
        return "feature_request"
    return "other"


def screen():
    issues = {issue["number"]: issue for issue in _jsonl(CATALOG / "issue_records.jsonl")}
    links = defaultdict(set)
    for comment in _jsonl(CATALOG / "comment_records.jsonl"):
        number = int(comment["issue_url"].rsplit("/", 1)[1])
        for ref in ISSUE_REF.findall(comment.get("body") or ""):
            if int(ref) != number:
                links[number].add(int(ref))
    for number, issue in issues.items():
        for ref in ISSUE_REF.findall(issue.get("body") or ""):
            if int(ref) != number:
                links[number].add(int(ref))
    for entry in json.loads(
        (CATALOG / "family_review_candidates.json").read_text(encoding="utf-8")
    ):
        links[entry["number"]].update(entry["linked_selected_issue_numbers"])

    reservations = json.loads(RESERVATIONS.read_text(encoding="utf-8"))
    reserved = {
        issue_id: candidate["proposed_split"]
        for candidate in reservations["candidates"]
        for issue_id in candidate["issue_ids"]
    }
    dev_three = json.loads(DEV_THREE.read_text(encoding="utf-8"))
    exposed = set(dev_three["development_exposure_issue_ids"])
    used = {i for family in dev_three["families"] for i in family["issue_ids"]}

    rows = []
    for number, issue in sorted(issues.items()):
        body = issue.get("body") or ""
        labels = _labels(issue)
        version = VERSION.search(body)
        neighbours = sorted(links[number])
        rows.append(
            {
                "issue_id": number,
                "title": issue["title"],
                "url": issue["html_url"],
                "created_at": issue["created_at"][:10],
                "state": issue["state"],
                "state_reason": issue.get("state_reason"),
                "kind": _kind(labels),
                "features": [label for label in labels if label.startswith(("feature:", "area:"))],
                "comment_count": issue.get("comments"),
                "has_code": "```" in body,
                "reported_version": version.group(1) if version else None,
                "linked_issue_ids": neighbours,
                "linked_in_seed": [n for n in neighbours if n in issues],
                "reserved_split": reserved.get(number),
                "development_exposed": number in exposed,
                "used_in_dev_three": number in used,
            }
        )
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error(f"{args.output} exists; choose a fresh directory")
    rows = screen()
    args.output.mkdir(parents=True)
    (args.output / "screen.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(rows)} rows to {args.output}/screen.json")


if __name__ == "__main__":
    main()
