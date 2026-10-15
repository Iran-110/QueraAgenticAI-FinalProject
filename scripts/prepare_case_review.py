"""Build a human review sheet for the curated dev cases of one split manifest.

The sheet puts each case's cached Issue, all cached comments, seed cross-links,
the visible turns and the runner-only gold side by side, and writes an empty
JSON template for the reviewer. It runs no model, retrieval or tracker and
never fills a judgment: every review field starts as null.

    uv run python scripts/prepare_case_review.py \
        --manifest data/evaluation/dev-three-v1/split-manifest.json \
        --output runtime/case-review-FRESH
"""

import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "streamlit-data-for-dev-test/sources/github-snapshot-2026-10-06/catalog"
EXPOSURE_REVIEW = "exposure-review-v1.json"

CASE_QUESTIONS = {
    "family_confirmed": "Are the listed family Issue IDs the whole family (duplicates, umbrella, follow-ups)?",
    "missing_family_issue_ids": "Issue IDs to add to the family (checked on GitHub, outside the seed too).",
    "external_duplicates_checked": "Did you search GitHub for duplicates outside the seed?",
    "initial_message_faithful": "Does the first visible message match what the reporter knew at the start?",
    "no_answer_leak_in_visible_input": "Is every visible turn free of answers, diagnoses or later comments?",
    "direct_answer_documents_listed": "Are all docs that directly answer the case listed for index exclusion?",
}
TURN_QUESTIONS = {
    "stratum_agreed": "Is the stratum (answerable / ambiguous / needs_escalation) right for this turn?",
    "acceptable_decisions_agreed": "Is the set of acceptable decisions right, and are the conditions clear?",
    "gaps_agreed": "Are the user and source gaps right, and is each question necessary and answerable?",
    "unacceptable_claims_complete": "Do the unacceptable claims cover the likely wrong answers?",
}


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _jsonl(path):
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _mentions(text, numbers):
    found = {int(n) for n in re.findall(r"(?:#|/issues/)(\d+)", text or "")}
    return sorted(found & numbers)


def _seed():
    issues = {issue["number"]: issue for issue in _jsonl(CATALOG / "issue_records.jsonl")}
    comments = {}
    for comment in _jsonl(CATALOG / "comment_records.jsonl"):
        number = int(comment["issue_url"].rsplit("/", 1)[1])
        comments.setdefault(number, []).append(comment)
    for thread in comments.values():
        thread.sort(key=lambda comment: comment["created_at"])
    links = json.loads((CATALOG / "family_review_candidates.json").read_text(encoding="utf-8"))
    return issues, comments, links


def _cross_links(family, issues, comments, links):
    """Seed Issues/comments outside the family that mention a family member."""
    numbers = set(family)
    rows = []
    for number, issue in issues.items():
        if number in numbers:
            continue
        hits = _mentions(issue.get("body"), numbers)
        hits += [n for c in comments.get(number, []) for n in _mentions(c.get("body"), numbers)]
        if hits:
            rows.append(f"#{number} mentions {', '.join(f'#{n}' for n in sorted(set(hits)))}")
    for entry in links:
        linked = set(entry["linked_selected_issue_numbers"]) | {entry["number"]}
        if linked & numbers and not linked <= numbers:
            rows.append(
                f"family_review_candidates: #{entry['number']} -> {entry['linked_selected_issue_numbers']}"
            )
    return rows


def _fence(text):
    return "~~~~text\n" + (text or "(empty)").strip() + "\n~~~~"


def _issue_section(number, issues, comments):
    issue = issues.get(number)
    if issue is None:
        return [f"#### #{number} — not in the seed snapshot; review it on GitHub", ""]
    lines = [
        f"#### #{number} — {issue['title']}",
        f"{issue['html_url']} · created {issue['created_at']} · updated {issue['updated_at']}"
        f" · state {issue.get('state')}",
        "",
        "Cached body (may include later edits):",
        _fence(issue.get("body")),
        "",
    ]
    for comment in comments.get(number, []):
        lines += [
            f"Comment {comment['id']} · {comment['created_at']} · {comment.get('author_association')}",
            _fence(comment.get("body")),
            "",
        ]
    return lines


def _turn_section(turn):
    visible, gold = turn["visible"], turn.get("gold", {})
    lines = [
        f"#### Turn `{turn['id']}`",
        "",
        "Visible to the agent:",
        _fence(visible.get("message")),
        "",
    ]
    for fact in visible.get("reported_facts", []):
        lines.append(f"- fact `{fact['name']}` = {fact.get('value')!r}")
    for key in ("unknowns", "checks_performed"):
        if visible.get(key):
            lines.append(f"- {key}: {', '.join(map(str, visible[key]))}")
    lines += [
        "",
        "Runner-only gold:",
        f"- stratum: **{gold.get('stratum')}**",
        f"- acceptable decisions: {', '.join(gold.get('acceptable_decisions', []))}",
    ]
    for decision, condition in gold.get("decision_conditions", {}).items():
        lines.append(f"  - {decision}: {condition}")
    for gap in gold.get("gaps", []):
        lines.append(
            f"- gap `{gap['name']}` ({gap['kind']}): {gap['description']} Question: {gap.get('question')}"
        )
    for claim in gold.get("unacceptable_claims", []):
        lines.append(f"- unacceptable: {claim}")
    return lines + [""]


def _questions(questions):
    return [f"- [ ] `{key}` — {text}" for key, text in questions.items()]


def build(manifest_path):
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    exposure = json.loads((manifest_path.parent / EXPOSURE_REVIEW).read_text(encoding="utf-8"))
    linkage = {row["origin_issue_id"]: row for row in exposure.get("linkage_review", [])}
    excluded_docs = exposure.get("direct_answer_documents_excluded", [])
    issues, comments, links = _seed()

    sheet = [
        f"# Human case review — {manifest['manifest_id']}",
        "",
        "Fill `case-review.json` (copy of the template). Use `true`/`false` and notes;",
        "leave `null` only where you did not check. Model-output usefulness is scored",
        "separately with `scripts/prepare_semantic_review.py` (docs/evaluation-workbench.fa.md).",
        "",
    ]
    template = {
        "schema_version": 1,
        "review_id": None,
        "reviewer_id": None,
        "reviewer_kind": "human",
        "reviewed_on": None,
        "manifest_path": manifest_path.relative_to(ROOT).as_posix(),
        "manifest_sha256": _sha(manifest_path),
        "cases": [],
    }
    for fixture_rel in manifest["fixture_paths"]:
        fixture_path = ROOT / fixture_rel
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        case = fixture["case"]
        family = case["family_issue_ids"]
        origin = fixture["initial_report_provenance"]["issue_number"]
        sheet += [
            f"## {case['case_id']} — origin #{origin}, family {family}",
            "",
            f"Fixture `{fixture_rel}`. {fixture.get('purpose', '')}",
            "",
            "Assistant linkage review (not human approval):",
            "~~~~json",
            json.dumps(linkage.get(origin, {}), ensure_ascii=False, indent=1),
            "~~~~",
            "",
        ]
        docs = [doc["source_url"] for doc in excluded_docs if doc["origin_issue_id"] == origin]
        sheet.append(f"Direct-answer docs excluded so far: {', '.join(docs) or 'none listed'}")
        cross = _cross_links(family, issues, comments, links)
        sheet += [
            "",
            "Seed cross-links to check:",
            *([f"- {row}" for row in cross] or ["- none found in the seed"]),
            "",
        ]
        sheet += ["### Case questions", *_questions(CASE_QUESTIONS), ""]
        sheet += ["### Turns", ""]
        for turn in fixture["turns"]:
            sheet += _turn_section(turn)
            sheet += _questions(TURN_QUESTIONS) + [""]
        sheet += ["### Source thread (contains answers — reviewer only)", ""]
        for number in family:
            sheet += _issue_section(number, issues, comments)
        template["cases"].append(
            {
                "case_id": case["case_id"],
                "fixture_path": fixture_rel,
                "fixture_sha256": _sha(fixture_path),
                **{key: [] if key.startswith("missing") else None for key in CASE_QUESTIONS},
                "turns": [
                    {"turn_id": turn["id"], **dict.fromkeys(TURN_QUESTIONS), "notes": None}
                    for turn in fixture["turns"]
                ],
                "accept_case_for_dev": None,
                "notes": None,
            }
        )
    return "\n".join(sheet) + "\n", template


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    manifest = args.manifest.resolve()
    if args.output.exists():
        parser.error(f"{args.output} exists; choose a fresh directory")
    sheet, template = build(manifest)
    args.output.mkdir(parents=True)
    (args.output / "review-sheet.md").write_text(sheet, encoding="utf-8")
    (args.output / "case-review-template.json").write_text(
        json.dumps(template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {args.output}/review-sheet.md and case-review-template.json")


if __name__ == "__main__":
    main()
