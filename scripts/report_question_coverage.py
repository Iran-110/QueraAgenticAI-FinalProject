"""Check registered ask branches against the fixed question vocabulary (E1/E2).

The current core never writes a free question. It asks for the Streamlit
version while no active USER version fact exists (``reasoning/catalog.py``), and
offers a vocabulary question only when its name is in the case's current
``unknowns``. For every registered ``ask`` route this script records whether the
needed question is the built-in version question, a vocabulary entry, or
missing from the vocabulary (a system limitation), and whether it would be
available on that turn. Case state follows ``orchestration/turns.py`` in
simplified form: unknowns and active USER facts carry over between turns, a
reported value retires the unknown, a null value adds it, ``context_changed``
retires user facts that are not restated, and a reply to an asked question
makes its target known.

Dev rows are written in full. Test rows are reduced to counts so the committed
report does not reveal held-out questions; ``--show-test`` prints the test rows
to stdout for the evaluation owner only and never writes them.

    uv run python scripts/report_question_coverage.py
"""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data/evaluation/split-e1-v1/split-manifest.json"
VOCABULARY = ROOT / "config/user-gap-support-dev-v1.json"
OUTPUT = ROOT / "data/evaluation/split-e1-v1/question-coverage-v1.json"
VERSION = "streamlit_version"


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _states(fixture):
    """Active USER fact names and unknowns at the start of each turn's decision."""
    routes = fixture["evaluation"]["coverage"]["routes"]
    known, unknowns, states = set(), set(), {}
    for turn in fixture["turns"]:
        visible = turn["visible"]
        for route in routes:
            guard = route["guard"]
            if route["to_turn"] == turn["id"] and guard["decision"] == "ask":
                known.add(guard["question_target"].casefold())
        reported = {
            fact["name"].casefold(): fact["value"] for fact in visible.get("reported_facts", [])
        }
        if visible.get("context_changed"):
            unknowns |= known - {name for name, value in reported.items() if value is not None}
            known &= {name for name, value in reported.items() if value is not None}
        unknowns |= {name.casefold() for name in visible.get("unknowns", [])}
        for name, value in reported.items():
            (known.add if value is not None else known.discard)(name)
            if value is None:
                unknowns.add(name)
        unknowns -= known
        states[turn["id"]] = (frozenset(known), frozenset(unknowns))
    return states


def branch_rows(fixture, vocabulary):
    """One row per registered ask route of one fixture."""
    states = _states(fixture)
    rows = []
    for route in fixture["evaluation"]["coverage"]["routes"]:
        guard = route["guard"]
        if guard["decision"] != "ask":
            continue
        target = guard["question_target"]
        known, unknowns = states[route["from_turn"]]
        if target == VERSION:
            source = "built_in_version"
            available = VERSION not in known
        elif target in vocabulary:
            source = "vocabulary"
            available = target.casefold() in unknowns
        else:
            source = "not_in_vocabulary"
            available = False
        rows.append(
            {
                "case_id": fixture["case"]["case_id"],
                "turn_id": route["from_turn"],
                "question_target": target,
                "question_source": source,
                "available_on_turn": available,
            }
        )
    return rows


def unused_user_gaps(fixture, vocabulary):
    """Gold user gaps with a question that no registered route asks for."""
    asked = {
        (route["from_turn"], route["guard"].get("question_target"))
        for route in fixture["evaluation"]["coverage"]["routes"]
        if route["guard"]["decision"] == "ask"
    }
    return [
        {
            "case_id": fixture["case"]["case_id"],
            "turn_id": turn["id"],
            "gap": gap["name"],
            "in_vocabulary": gap["name"] in vocabulary or gap["name"] == VERSION,
        }
        for turn in fixture["turns"]
        for gap in turn["gold"]["gaps"]
        if gap["kind"] == "user" and gap.get("question") and (turn["id"], gap["name"]) not in asked
    ]


def unneeded_offers(fixture, vocabulary):
    """Turns where a question is on offer although gold does not accept ``ask``."""
    states = _states(fixture)
    rows = []
    for turn in fixture["turns"]:
        known, unknowns = states[turn["id"]]
        offered = sorted(
            ([VERSION] if VERSION not in known else [])
            + [name for name in vocabulary if name.casefold() in unknowns]
        )
        if offered and "ask" not in turn["gold"]["acceptable_decisions"]:
            rows.append(
                {"case_id": fixture["case"]["case_id"], "turn_id": turn["id"], "offered": offered}
            )
    return rows


def _summary(rows, extra, offers):
    return {
        "ask_branches": len(rows),
        "by_question_source": dict(sorted(Counter(row["question_source"] for row in rows).items())),
        "available_on_turn": sum(row["available_on_turn"] for row in rows),
        "distinct_targets_not_in_vocabulary": len(
            {
                row["question_target"]
                for row in rows
                if row["question_source"] == "not_in_vocabulary"
            }
        ),
        "gold_user_gaps_without_ask_route": len(extra),
        "turns_offering_a_question_where_ask_is_not_acceptable": len(offers),
    }


def build(splits=("dev", "test"), manifest_path=MANIFEST, vocabulary_path=VOCABULARY):
    manifest = _load(manifest_path)
    vocabulary = {gap["name"] for gap in _load(vocabulary_path)["user_gaps"]}
    report = {
        "schema_version": 1,
        "report_id": "split-e1-v1-question-coverage-v1",
        "manifest_path": str(manifest_path.relative_to(ROOT)),
        "manifest_sha256": _sha256(manifest_path),
        "vocabulary_path": str(vocabulary_path.relative_to(ROOT)),
        "vocabulary_sha256": _sha256(vocabulary_path),
        "vocabulary_names": sorted(vocabulary),
        "rule": (
            "built-in version question while no active USER version fact; a vocabulary "
            "question only when its name is in the case's current unknowns"
        ),
        "splits": {},
    }
    details = {}
    for split in splits:
        rows, extra, offers, checked = [], [], [], 0
        for entry in manifest["registered_fixtures"][split]:
            path = ROOT / entry["path"]
            if _sha256(path) != entry["sha256"]:
                raise SystemExit(f"fixture hash differs from manifest: {entry['path']}")
            fixture = _load(path)
            rows += branch_rows(fixture, vocabulary)
            extra += unused_user_gaps(fixture, vocabulary)
            offers += unneeded_offers(fixture, vocabulary)
            checked += 1
        rows_by_kind = {
            "ask_branches": rows,
            "gold_user_gaps_without_ask_route": extra,
            "question_offered_where_ask_is_not_acceptable": offers,
        }
        section = {"fixtures_checked": checked, "summary": _summary(rows, extra, offers)}
        if split == "dev":
            section.update(rows_by_kind)
        report["splits"][split] = section
        details[split] = rows_by_kind
    return report, details


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument(
        "--show-test", action="store_true", help="print held-out rows; never written"
    )
    args = parser.parse_args()
    report, details = build()
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")
    for split, section in report["splits"].items():
        print(split, json.dumps(section["summary"]))
    if args.show_test:
        print(json.dumps(details["test"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
