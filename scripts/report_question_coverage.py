"""Project registered question availability with core intake/state/catalog rules.

This is bounded static projection over authored route hypotheses, not actual
model choices, approval/release evidence, path reachability or answer quality.
Ordinary runner execution follows fixture order; registered conditional routes
require the runner's separate --conditional-routes option. No agent is run here.
The immutable v1 report is historical. The default v2 rebuild reads dev only;
held-out processing requires explicit evaluation-owner opt-in and exports counts
only, including through the Python return value. No test detail display exists.
"""

import argparse
import hashlib
import json
import sys
from collections import Counter, deque
from pathlib import Path

from agent_app.contracts import (
    AnalysisResult,
    ApprovedReplyQuestion,
    CaseState,
    EvidenceBundle,
    UserTurn,
)
from agent_app.evaluation.routes import RouteGraph
from agent_app.orchestration.intake import (
    STREAMLIT_VERSION_QUESTION,
    prepare_approved_version_reply,
)
from agent_app.orchestration.turns import propose_user_turn
from agent_app.reasoning.catalog import caller_catalog, validate_user_gaps

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data/evaluation/split-e1-v1/split-manifest.json"
VOCABULARY = ROOT / "config/user-gap-support-dev-v1.json"
OUTPUT = ROOT / "data/evaluation/split-e1-v1/question-coverage-dev-v2.json"
LEGACY_OUTPUT = ROOT / "data/evaluation/split-e1-v1/question-coverage-v1.json"
VERSION = STREAMLIT_VERSION_QUESTION.name
MAX_PROJECTED_STATES = 1024
MAX_PROJECTED_PATHS = 256
ERROR = "QuestionCoverageRejected"
_VISIBLE = {
    "message",
    "reported_facts",
    "unknowns",
    "checks_performed",
    "context_changed",
    "reply_to_approved_question",
}
_STRUCTURED = ("reported_facts", "unknowns", "checks_performed", "context_changed")


class QuestionCoverageRejected(ValueError):
    def __init__(self):
        super().__init__(ERROR)


def _need(condition):
    if not condition:
        raise QuestionCoverageRejected()


def _read(path):
    raw = path.read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def _vocabulary(path):
    """Same bounded strict vocabulary format, validated and hashed from one read."""

    def unique(pairs):
        result = dict(pairs)
        _need(len(result) == len(pairs))
        return result

    def reject_constant(_value):
        raise QuestionCoverageRejected()

    with path.open("rb") as source:
        raw = source.read(32769)
    _need(len(raw) <= 32768)
    payload = json.loads(
        raw.decode("utf-8"), object_pairs_hook=unique, parse_constant=reject_constant
    )
    _need(type(payload) is dict and set(payload) == {"schema_version", "user_gaps"})
    _need(type(payload["schema_version"]) is int and payload["schema_version"] == 1)
    _need(type(payload["user_gaps"]) is list)
    return validate_user_gaps(payload["user_gaps"]), hashlib.sha256(raw).hexdigest()


def _protected(path):
    relative = path.relative_to(ROOT.resolve())
    return (
        relative.parts[:4] == ("data", "evaluation", "split-e1-v1", "test")
        or path.name.startswith("evidence-test")
        or path.name == "test-card-review-v1.json"
    )


def _input_path(path, *, allow_test=False):
    resolved = path.resolve()
    _need(resolved.is_relative_to(ROOT.resolve()) and resolved.suffix == ".json")
    _need(allow_test or not _protected(resolved))
    return resolved


def _maintainer(turn, route):
    """Check the limited canonical-question workflow this projection supports."""
    value = turn["maintainer"]
    _need(type(value) is dict and value.get("decision") in {"none", "approve", "reject", "edit"})
    decision = value["decision"]
    if "note" in value:
        _need(type(value["note"]) is str and len(value["note"]) <= 20_000)
    if decision == "edit":
        _need(set(value) <= {"decision", "edited_draft", "then", "note"})
        _need(type(value["edited_draft"]) is str and bool(value["edited_draft"].strip()))
        _need(value.get("then") in {None, "approve"})
    else:
        _need(set(value) <= {"decision", "note"})
    if route.decision == "ask":
        _need(decision != "reject")
        if decision == "edit":
            _need(value["edited_draft"].strip() == route.question)
        if route.target is not None:
            _need(decision == "approve" or (decision == "edit" and value.get("then") == "approve"))


def _apply(turn, previous, incoming):
    visible = turn["visible"]
    _need(type(visible) is dict and not set(visible) - _VISIBLE)
    flag = visible.get("reply_to_approved_question", False)
    _need(type(flag) is bool)
    fields = {name: visible[name] for name in _STRUCTURED if name in visible}
    if flag:
        _need(not any(fields.values()))
        _need(incoming is not None and incoming.decision == "ask")
        _need(
            incoming.question_target == VERSION
            and incoming.question == STREAMLIT_VERSION_QUESTION.question
        )
        fields = {}
    # Same stable event/source prefix and 195-character ID allowance as API
    # MessageRequest.user_turn; no question edge supplies a reported value.
    _need(type(turn["id"]) is str and len(turn["id"]) <= 195)
    event = UserTurn(
        case_id=previous.case_id,
        expected_revision=previous.case_revision,
        turn_id=turn["id"],
        source_ref=f"user:{turn['id']}",
        message=visible["message"],
        **fields,
    )
    if flag:
        question = AnalysisResult(
            decision="ask",
            user_draft=incoming.question,
            maintainer_summary=incoming.question,
            rationale="Registered canonical question projection only.",
            missing_info=(VERSION,),
            next_question=incoming.question,
        )
        reply = ApprovedReplyQuestion(
            case_id=previous.case_id,
            case_revision=previous.case_revision,
            proposal_id="projected-question",
            question=question,
        )
        event = prepare_approved_version_reply(
            previous, event, reply=reply, proposal_id=reply.proposal_id
        )
    return propose_user_turn(previous, event).candidate, event.message


def _states(fixture, vocabulary):
    """Independent core snapshots for each registered incoming path prefix."""
    graph = RouteGraph.from_fixture(fixture)
    primary = fixture["case"]["case_id"]
    cases = [primary, *fixture["case"].get("extra_case_ids", [])]
    _need(len(cases) == len(set(cases)))
    initial = {name: CaseState(case_id=name) for name in cases}
    turns = {turn["id"]: turn for turn in fixture["turns"]}
    outgoing = {name: [] for name in graph.node_ids}
    for route in graph.routes:
        _maintainer(turns[route.source], route)
        outgoing[route.source].append(route)
    pending = deque([(graph.node_ids[0], initial, None)])
    queued, terminals = 1, 0
    _need(queued <= MAX_PROJECTED_STATES)
    states = {name: [] for name in graph.node_ids}
    evidence = EvidenceBundle(snapshot_id="question-coverage-projection")
    while pending:
        node, prior, incoming = pending.popleft()
        turn = turns[node]
        case_id = turn.get("case_id", primary)
        _need(case_id in prior)
        state, message = _apply(turn, prior[case_id], incoming)
        updated = dict(prior)
        updated[case_id] = state
        request = caller_catalog(state, message, evidence, definitions=vocabulary)
        offered = {gap.name: gap.question for gap in request.gaps if gap.kind == "user"}
        states[node].append(offered)
        for route in outgoing[node]:
            if route.target is None:
                terminals += 1
                _need(terminals <= MAX_PROJECTED_PATHS)
            else:
                queued += 1
                _need(queued <= MAX_PROJECTED_STATES)  # Bound work before enqueue.
                pending.append((route.target, updated, route))
    return graph, states


def _analyze(fixture, vocabulary):
    vocabulary = validate_user_gaps(vocabulary)
    graph, states = _states(fixture, vocabulary)
    names = {gap.name.casefold() for gap in vocabulary}
    definitions = {gap.name: gap.question for gap in vocabulary} | {
        VERSION: STREAMLIT_VERSION_QUESTION.question
    }
    primary = fixture["case"]["case_id"]
    turns = {turn["id"]: turn for turn in fixture["turns"]}
    rows = []
    for route in graph.routes:
        if route.decision != "ask":
            continue
        options = states[route.source]
        _need(bool(options))
        count = sum(offered.get(route.question_target) == route.question for offered in options)
        source = (
            "built_in_version"
            if route.question_target.casefold() == VERSION
            else "vocabulary"
            if route.question_target.casefold() in names
            else "not_in_vocabulary"
        )
        rows.append(
            {
                "case_id": turns[route.source].get("case_id", primary),
                "turn_id": route.source,
                "question_target": route.question_target,
                "question_source": source,
                "definition_matches_route": definitions.get(route.question_target)
                == route.question,
                "projected_path_states": len(options),
                "available_path_states": count,
                "availability": "all" if count == len(options) else "some" if count else "none",
            }
        )
    asked = {
        (route.source, route.question_target) for route in graph.routes if route.decision == "ask"
    }
    extra, offers = [], []
    for turn in fixture["turns"]:
        case_id, node = turn.get("case_id", primary), turn["id"]
        for gap in turn["gold"]["gaps"]:
            if gap["kind"] == "user" and gap.get("question") and (node, gap["name"]) not in asked:
                extra.append(
                    {
                        "case_id": case_id,
                        "turn_id": node,
                        "gap": gap["name"],
                        "in_vocabulary": gap["name"] in definitions,
                    }
                )
        options = states[node]
        available = [set(option) for option in options]
        if any(available) and "ask" not in turn["gold"]["acceptable_decisions"]:
            offers.append(
                {
                    "case_id": case_id,
                    "turn_id": node,
                    "projected_path_states": len(options),
                    "paths_offering_question": sum(bool(option) for option in options),
                    "offered_on_any_path": sorted(set.union(*available)),
                    "offered_on_all_paths": sorted(set.intersection(*available)),
                }
            )
    return rows, extra, offers


def branch_rows(fixture, vocabulary):
    try:
        return _analyze(fixture, vocabulary)[0]
    except Exception:
        raise QuestionCoverageRejected() from None


def unused_user_gaps(fixture, vocabulary):
    try:
        return _analyze(fixture, vocabulary)[1]
    except Exception:
        raise QuestionCoverageRejected() from None


def unneeded_offers(fixture, vocabulary):
    try:
        return _analyze(fixture, vocabulary)[2]
    except Exception:
        raise QuestionCoverageRejected() from None


def _summary(rows, extra, offers):
    return {
        "ask_branches": len(rows),
        "by_question_source": dict(sorted(Counter(row["question_source"] for row in rows).items())),
        "by_path_availability": {
            name: sum(row["availability"] == name for row in rows)
            for name in ("all", "some", "none")
        },
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


def build(
    splits=("dev",),
    manifest_path=MANIFEST,
    vocabulary_path=VOCABULARY,
    *,
    evaluation_owner_test=False,
):
    try:
        _need(type(evaluation_owner_test) is bool)
        _need(type(splits) is tuple and bool(splits) and len(splits) == len(set(splits)))
        _need(set(splits) <= {"dev", "test"} and ("test" not in splits or evaluation_owner_test))
        manifest_path = _input_path(manifest_path)
        vocabulary_path = _input_path(vocabulary_path)
        manifest, manifest_hash = _read(manifest_path)
        vocabulary, vocabulary_hash = _vocabulary(vocabulary_path)
        report = {
            "schema_version": 2,
            "report_id": "split-e1-v1-question-coverage-v2",
            "quality_claim": False,
            "actual_execution": False,
            "projection_scope": "bounded registered-route hypotheses; not runtime reachability or model/approval outcomes",
            "runner_scope": "ordinary runner uses fixed fixture order; conditional routes require separate runner opt-in",
            "manifest_path": str(manifest_path.relative_to(ROOT)),
            "manifest_sha256": manifest_hash,
            "vocabulary_path": str(vocabulary_path.relative_to(ROOT)),
            "vocabulary_sha256": vocabulary_hash,
            "vocabulary_names": sorted(gap.name for gap in vocabulary),
            "max_projected_states_per_fixture": MAX_PROJECTED_STATES,
            "max_projected_terminal_paths_per_fixture": MAX_PROJECTED_PATHS,
            "splits": {},
        }
        details = {}
        for split in splits:
            rows, extra, offers, checked = [], [], [], 0
            for entry in manifest["registered_fixtures"][split]:
                path = _input_path(
                    ROOT / entry["path"], allow_test=split == "test" and evaluation_owner_test
                )
                fixture, digest = _read(path)
                _need(digest == entry["sha256"])
                _need(fixture["case"]["split"] == split)
                new_rows, new_extra, new_offers = _analyze(fixture, vocabulary)
                rows.extend(new_rows)
                extra.extend(new_extra)
                offers.extend(new_offers)
                checked += 1
            section = {"fixtures_checked": checked, "summary": _summary(rows, extra, offers)}
            if split == "dev":
                details[split] = {
                    "ask_branches": rows,
                    "gold_user_gaps_without_ask_route": extra,
                    "question_offered_where_ask_is_not_acceptable": offers,
                }
                section.update(details[split])
            report["splits"][split] = section
        return report, details
    except Exception:
        raise QuestionCoverageRejected() from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--include-test-evaluation-owner", action="store_true")
    args = parser.parse_args(argv)
    try:
        output = args.output or OUTPUT
        _need(output.resolve() != LEGACY_OUTPUT.resolve())
        _need(not output.exists())
        _need(
            not output.resolve().is_relative_to(ROOT.resolve()) or not _protected(output.resolve())
        )
        if args.include_test_evaluation_owner:
            _need(args.output is not None and output.resolve() != OUTPUT.resolve())
        splits = ("dev", "test") if args.include_test_evaluation_owner else ("dev",)
        report, _ = build(splits=splits, evaluation_owner_test=args.include_test_evaluation_owner)
        with output.open("x", encoding="utf-8") as destination:
            destination.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        for split, section in report["splits"].items():
            print(split, json.dumps(section["summary"], sort_keys=True))
        return 0
    except Exception:
        print(ERROR, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
