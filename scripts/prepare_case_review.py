"""Build a human review sheet for the curated cases of one split manifest.

The sheet puts each case's cached Issue, all cached comments, seed cross-links,
the visible turns and the runner-only gold side by side, and writes an empty
JSON template plus a Persian right-to-left HTML version of the sheet. It runs no
model, retrieval or tracker and never fills a judgment: every review field
starts as null.

    uv run python scripts/prepare_case_review.py \
        --manifest data/evaluation/dev-three-v1/split-manifest.json \
        --output runtime/case-review-FRESH
"""

import argparse
import hashlib
import html
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
    if gold.get("required_sources"):
        lines.append(f"- required sources: {', '.join(gold['required_sources'])}")
    return lines + [""]


def _questions(questions):
    return [f"- [ ] `{key}` — {text}" for key, text in questions.items()]


def _fixture_paths(manifest):
    """Older packets list fixture_paths; split-e1 manifests register them per split."""
    if "fixture_paths" in manifest:
        return manifest["fixture_paths"]
    registered = manifest["registered_fixtures"]
    return [row["path"] for split in ("dev", "test") for row in registered.get(split, [])]


def build(manifest_path):
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    exposure_path = manifest_path.parent / EXPOSURE_REVIEW
    exposure = (
        json.loads(exposure_path.read_text(encoding="utf-8")) if exposure_path.exists() else {}
    )
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
    entries = []
    for fixture_rel in _fixture_paths(manifest):
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
        entries.append({"fixture": fixture, "path": fixture_rel, "cross": cross, "docs": docs})
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
                f"accept_case_for_{case['split']}": None,
                "notes": None,
            }
        )
    return (
        "\n".join(sheet) + "\n",
        template,
        render_html(manifest["manifest_id"], entries, issues, comments),
    )


FA_QUESTIONS = {
    "family_confirmed": "خانواده کامل است (duplicate، umbrella، ادامه‌ها)؟",
    "missing_family_issue_ids": "Issueهایی که باید به خانواده اضافه شوند (روی GitHub، بیرون از seed هم).",
    "external_duplicates_checked": "روی GitHub دنبال duplicate بیرون از seed گشتی؟",
    "initial_message_faithful": "پیام اول با آنچه گزارش‌دهنده در شروع می‌دانست می‌خواند؟",
    "no_answer_leak_in_visible_input": "هیچ نوبت قابل‌مشاهده‌ای جواب، تشخیص یا comment بعدی را لو نمی‌دهد؟",
    "direct_answer_documents_listed": "همهٔ سندهایی که مستقیم جواب این case را می‌دهند برای exclusion ثبت شده‌اند؟",
    "stratum_agreed": "stratum این نوبت درست است؟",
    "acceptable_decisions_agreed": "تصمیم‌های قابل قبول و شرط‌هایشان درست و روشن‌اند؟",
    "gaps_agreed": "gapهای کاربر/منبع درست‌اند و هر سؤال لازم و قابل پاسخ است؟",
    "unacceptable_claims_complete": "ادعاهای غیرقابل قبول، پاسخ‌های غلط محتمل را پوشش می‌دهند؟",
}
STRATA_FA = {"answerable": "قابل پاسخ", "ambiguous": "مبهم", "needs_escalation": "نیاز به ارجاع"}
STYLE = """
:root{--bg:#f7f7f5;--card:#fff;--ink:#1d1d1f;--muted:#5f6368;--line:#e3e3df;--accent:#0b6e4f;--warnbg:#fff4e0;--warn:#a15c00}
@media (prefers-color-scheme:dark){:root{--bg:#141414;--card:#1e1e1e;--ink:#ececec;--muted:#a0a0a0;--line:#333;--accent:#4cc38a;--warnbg:#2e2412;--warn:#f0b35a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:"Vazirmatn",system-ui,sans-serif;line-height:1.85;font-size:15px}
main{max-width:1100px;margin:0 auto;padding:24px 16px 64px}h1{font-size:1.5rem;margin:0}h2{font-size:1.15rem;margin:0}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 18px;margin:12px 0}
.warn{background:var(--warnbg);border-color:var(--warn)}.muted{color:var(--muted);font-size:.85rem}
a{color:var(--accent)}code,pre,.ltr{direction:ltr;text-align:left;unicode-bidi:isolate;font-family:ui-monospace,Menlo,monospace;font-size:.85rem}
pre{white-space:pre-wrap;background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:10px;margin:6px 0}
table{width:100%;border-collapse:collapse}th,td{text-align:start;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600}.scroll{overflow-x:auto}details>summary{cursor:pointer;font-weight:600;padding:4px 0}
.tag{display:inline-block;padding:0 8px;border-radius:99px;font-size:.78rem;background:var(--bg);border:1px solid var(--line)}
.en{direction:ltr;text-align:left;unicode-bidi:isolate}ul{padding-inline-start:22px;margin:4px 0}
"""


def _issue_link(number):
    return (
        f'<a href="https://github.com/streamlit/streamlit/issues/{number}" target="_blank" '
        f'rel="noopener">#{number}</a>'
    )


def _pre(text):
    return f"<pre>{html.escape((text or '(empty)').strip())}</pre>"


def _html_turn(turn):
    visible, gold = turn["visible"], turn.get("gold", {})
    parts = [
        f'<h3 class="ltr">turn: {html.escape(turn["id"])} '
        f'<span class="tag">{html.escape(turn.get("conversation_source", ""))}</span></h3>',
        "<div>آنچه agent می‌بیند:</div>",
        _pre(visible.get("message")),
    ]
    facts = [
        f"<li class='en'><code>{html.escape(f['name'])}</code> = {html.escape(str(f.get('value')))}</li>"
        for f in visible.get("reported_facts", [])
    ]
    if facts:
        parts.append("<ul>" + "".join(facts) + "</ul>")
    rows = [
        f"<li>stratum: <b>{STRATA_FA.get(gold.get('stratum'), gold.get('stratum'))}</b> "
        f"<span class='muted'>({html.escape(str(gold.get('stratum')))})</span></li>"
    ]
    rows += [
        f"<li class='en'><b>{html.escape(d)}</b>: {html.escape(c)}</li>"
        for d, c in gold.get("decision_conditions", {}).items()
    ]
    rows += [
        f"<li class='en'>gap <code>{html.escape(g['name'])}</code> ({html.escape(g['kind'])}): "
        f"{html.escape(g['description'])} — <i>{html.escape(str(g.get('question')))}</i></li>"
        for g in gold.get("gaps", [])
    ]
    rows += [f"<li class='en'>✗ {html.escape(c)}</li>" for c in gold.get("unacceptable_claims", [])]
    if gold.get("required_sources"):
        rows.append(
            "<li class='en'>required sources: "
            + html.escape(", ".join(gold["required_sources"]))
            + "</li>"
        )
    parts += ["<div>gold (فقط برای داور):</div>", "<ul>" + "".join(rows) + "</ul>"]
    return "\n".join(parts)


def render_html(manifest_id, entries, issues, comments):
    summary, sections = [], []
    for entry in entries:
        fixture = entry["fixture"]
        case = fixture["case"]
        cid = html.escape(case["case_id"])
        first = fixture["turns"][0]["gold"].get("stratum")
        family = " ".join(_issue_link(n) for n in case["family_issue_ids"])
        summary.append(
            f"<tr><td><a href='#{cid}'>{cid}</a></td><td>{html.escape(case['split'])}</td>"
            f"<td class='ltr'>{family}</td><td>{STRATA_FA.get(first, first)}</td>"
            f"<td>{len(fixture['turns'])}</td></tr>"
        )
        cross = (
            "".join(f"<li class='en'>{html.escape(row)}</li>" for row in entry["cross"])
            or "<li>—</li>"
        )
        threads = []
        for number in case["family_issue_ids"]:
            issue = issues.get(number)
            if issue is None:
                threads.append(f"<p>{_issue_link(number)} — در seed نیست؛ روی GitHub ببین.</p>")
                continue
            body = [
                f"<p class='en'>{_issue_link(number)} — {html.escape(issue['title'])} "
                f"<span class='muted'>{issue['created_at'][:10]} · {issue.get('state')}</span></p>",
                _pre(issue.get("body")),
            ]
            body += [
                f"<div class='muted en'>comment {c['created_at'][:10]} · {c.get('author_association')}</div>"
                + _pre(c.get("body"))
                for c in comments.get(number, [])
            ]
            threads.append("\n".join(body))
        checklist = "".join(f"<li>{FA_QUESTIONS[k]} <code>{k}</code></li>" for k in CASE_QUESTIONS)
        turn_checklist = "".join(
            f"<li>{FA_QUESTIONS[k]} <code>{k}</code></li>" for k in TURN_QUESTIONS
        )
        sections.append(f"""
<section class="card" id="{cid}">
<h2><span class="ltr">{cid}</span> · {html.escape(case["split"])} · {family}</h2>
<p class="en muted">{html.escape(fixture.get("purpose", ""))} — <code>{html.escape(entry["path"])}</code></p>
<details><summary>لینک‌های seed به این خانواده</summary><ul>{cross}</ul></details>
{"".join(_html_turn(t) for t in fixture["turns"])}
<details><summary>سؤال‌های بازبینی (جواب‌ها در فایل JSON)</summary>
<div>برای کل case:</div><ul>{checklist}</ul><div>برای هر نوبت:</div><ul>{turn_checklist}</ul></details>
<details><summary>متن کامل Issue و commentها (شامل جواب — فقط داور)</summary>{"".join(threads)}</details>
</section>""")
    return f"""<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>بازبینی caseها</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;600;800&display=swap" rel="stylesheet">
<style>{STYLE}</style></head><body><main>
<h1>بازبینی انسانی caseها — <span class="ltr">{html.escape(manifest_id)}</span></h1>
<div class="card warn">پیش‌نویس gold را دستیار نوشته است. هر case را بخوان و جواب‌ها را در
<code>case-review.json</code> (کپی <code>case-review-template.json</code>) با <code>true</code>/<code>false</code>
و یادداشت ثبت کن. caseهای test را با هیچ‌کس از تیم core به اشتراک نگذار.
<div class="en muted">The assistant drafted the gold. Record your judgments in case-review.json; keep test cases away from core developers.</div></div>
<div class="card scroll"><table><tr><th>case</th><th>split</th><th>خانواده</th><th>stratum اول</th><th>نوبت</th></tr>
{"".join(summary)}</table></div>
{"".join(sections)}
</main></body></html>
"""


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    manifest = args.manifest.resolve()
    if args.output.exists():
        parser.error(f"{args.output} exists; choose a fresh directory")
    sheet, template, page = build(manifest)
    args.output.mkdir(parents=True)
    (args.output / "review-sheet.md").write_text(sheet, encoding="utf-8")
    (args.output / "review-sheet.html").write_text(page, encoding="utf-8")
    (args.output / "case-review-template.json").write_text(
        json.dumps(template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"wrote review-sheet.md, review-sheet.html and case-review-template.json to {args.output}"
    )


if __name__ == "__main__":
    main()
