"""Reserve metadata-only evaluation candidates; never freeze or label a split."""

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = {
    "issues": "sources/github-snapshot-2026-10-06/catalog/issue_records.jsonl",
    "selection": "sources/github-snapshot-2026-10-06/selection.json",
    "links": "sources/github-snapshot-2026-10-06/catalog/family_review_candidates.json",
    "exposure": "development_exposure.json",
}
DOMAINS = ("session_state", "widgets", "rerun", "callbacks")
ALGORITHM = "metadata-round-robin-sha256-v1"
CONFIRMED_DEV_FAMILY = (12629, 12782)
REVIEW_TASKS = (
    "review_whole_family_links_and_duplicates_including_outside_seed",
    "curate_initial_visible_report_and_record_later_edits_separately",
    "register_user_and_source_gaps_and_conditional_acceptable_decisions",
    "register_reply_routes_and_real_or_authored_conversation_provenance",
    "review_sources_direct_answer_documents_and_corpus_exclusion",
    "keep_gold_outcomes_and_future_turns_out_of_runtime_and_index",
)


class CandidateReservationRejected(ValueError):
    """Fixed diagnostics without source contents."""


def _reject(code):
    raise CandidateReservationRejected(code)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _ids(values):
    if (
        type(values) is not list
        or any(type(value) is not int or value <= 0 for value in values)
        or len(set(values)) != len(values)
    ):
        _reject("CandidateMetadataInvalid")
    return values


def _read_metadata(seed):
    try:
        manifest_raw = (seed / "manifest.json").read_bytes()
        manifest = json.loads(manifest_raw)
        declared = {entry["path"]: entry for entry in manifest["files"]}
        raw = {name: (seed / relative).read_bytes() for name, relative in FILES.items()}
        for name, content in raw.items():
            entry = declared[FILES[name]]
            if entry["sha256"] != _sha(content) or entry["bytes"] != len(content):
                _reject("CandidateChecksumMismatch")
        # Project only public metadata. Bodies, comments, outcomes, labels and
        # even titles are never inspected or used to assign a split.
        issues = {}
        for line in raw["issues"].decode("utf-8").splitlines():
            record = json.loads(line)
            number, url, count = record["number"], record["html_url"], record["comments"]
            if (
                type(number) is not int
                or number <= 0
                or number in issues
                or url != f"https://github.com/streamlit/streamlit/issues/{number}"
                or type(count) is not int
                or count < 0
            ):
                _reject("CandidateMetadataInvalid")
            issues[number] = {"issue_id": number, "source_url": url, "comment_count": count}
        selection = json.loads(raw["selection"])
        if set(_ids(selection["issue_numbers"])) != set(issues):
            _reject("CandidateMetadataInvalid")
        scopes = {}
        if set(selection["matches"]) != {str(number) for number in issues}:
            _reject("CandidateMetadataInvalid")
        for number, matches in selection["matches"].items():
            if type(matches) is not list or not matches or any(type(x) is not str for x in matches):
                _reject("CandidateMetadataInvalid")
            names = {value.rpartition("-")[0] for value in matches}
            if not names <= set(DOMAINS):
                _reject("CandidateMetadataInvalid")
            scopes[int(number)] = names
        links = json.loads(raw["links"])
        if type(links) is not list:
            _reject("CandidateMetadataInvalid")
        edges = []
        for row in links:
            number = row["number"]
            targets = _ids(row["linked_selected_issue_numbers"])
            if type(number) is not int or number not in issues or not set(targets) <= set(issues):
                _reject("CandidateMetadataInvalid")
            edges.extend((number, target) for target in targets)
        exposure = _ids(json.loads(raw["exposure"])["issue_numbers"])
    except CandidateReservationRejected:
        raise
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, AttributeError):
        _reject("CandidateSourceUnavailableOrInvalid")
    hashes = {FILES[name]: _sha(content) for name, content in raw.items()}
    hashes["manifest.json"] = _sha(manifest_raw)
    return issues, scopes, edges, exposure, hashes


def _components(numbers, edges):
    parents = {number: number for number in numbers}

    def find(number):
        while parents[number] != number:
            parents[number] = parents[parents[number]]
            number = parents[number]
        return number

    for left, right in edges:
        a, b = find(left), find(right)
        parents[max(a, b)] = min(a, b)
    components = {}
    for number in sorted(parents):
        components.setdefault(find(number), []).append(number)
    return [tuple(group) for group in components.values()]


def _rank(group):
    return _sha(f"{ALGORITHM}|{','.join(map(str, group))}".encode("ascii"))


def propose(seed=ROOT / "streamlit-data-for-dev-test", *, dev_count=15, test_count=15):
    if type(dev_count) is not int or dev_count < 1 or type(test_count) is not int or test_count < 1:
        _reject("CandidateTargetsInvalid")
    issues, scopes, edges, exposed, hashes = _read_metadata(Path(seed))
    if 12782 not in issues:
        _reject("KnownDevelopmentFamilyMissing")
    groups = _components(
        set(issues) | set(exposed) | set(CONFIRMED_DEV_FAMILY),
        [*edges, CONFIRMED_DEV_FAMILY],
    )
    reserved = set(exposed) | set(CONFIRMED_DEV_FAMILY)
    exposure_closure = sorted(
        number for group in groups if reserved.intersection(group) for number in group
    )
    known_dev = next(group for group in groups if 12782 in group)
    available = sorted(
        (
            group
            for group in groups
            if not reserved.intersection(group) and set(group) <= set(issues)
        ),
        key=_rank,
    )
    if len(available) < dev_count + test_count - 1:
        _reject("InsufficientEligibleCandidateFamilies")
    assigned = {"dev": [(known_dev, "previously_exposed_development")], "test": []}
    selected = {known_dev}
    domain_indices = {"dev": 0, "test": 0}
    while len(assigned["dev"]) < dev_count or len(assigned["test"]) < test_count:
        for split, target in (("test", test_count), ("dev", dev_count)):
            if len(assigned[split]) >= target:
                continue
            domain = DOMAINS[domain_indices[split] % len(DOMAINS)]
            domain_indices[split] += 1
            remaining = [group for group in available if group not in selected]
            group = next(
                (g for g in remaining if any(domain in scopes[number] for number in g)),
                remaining[0],
            )
            assigned[split].append((group, domain))
            selected.add(group)
    candidates = []
    for split in ("dev", "test"):
        for group, domain in assigned[split]:
            family_id = (
                "fam-12782" if group == known_dev else f"candidate-family-{_rank(group)[:16]}"
            )
            primary = (
                12782
                if group == known_dev
                else min(
                    (number for number in group if domain in scopes[number]), default=min(group)
                )
            )
            candidates.append(
                {
                    "candidate_case_id": f"{split}-candidate-{primary}",
                    "candidate_family_id": family_id,
                    "proposed_split": split,
                    "issue_ids": list(group),
                    "sampling_domain": domain,
                    "linkage_status": "candidate_component_not_confirmed_duplicate_family",
                    "known_exposed_dev_family": group == known_dev,
                    "source_refs": [
                        issues[number] | {"available_in_seed": True}
                        if number in issues
                        else {
                            "issue_id": number,
                            "source_url": f"https://github.com/streamlit/streamlit/issues/{number}",
                            "comment_count": None,
                            "available_in_seed": False,
                        }
                        for number in group
                    ],
                    "family_review": "pending_human_review",
                    "fixture_and_gold": "not_created",
                    "multi_turn": "pending_fixture_and_route_review",
                }
            )
    deny = sorted(set(exposure_closure) | {number for group in selected for number in group})
    return {
        "schema_version": 1,
        "reservation_id": "evaluation-family-reservations-v1",
        "status": "candidate_reservations_not_frozen",
        "e1_complete": False,
        "quality_claim": False,
        "validated_multi_turn_cases": 0,
        "reservation_counts": {split: len(assigned[split]) for split in assigned},
        "required_multi_turn_counts": {"total_min": 10, "test_min": 5},
        "source": {
            "input_sha256": hashes,
            "generator_sha256": _sha(Path(__file__).read_bytes()),
            "integrity_scope": "Only the four metadata sources; not the entire seed or a corpus audit.",
        },
        "selection_algorithm": {
            "id": ALGORITHM,
            "domains": list(DOMAINS),
            "uses": [
                "public_issue_ids",
                "source_urls",
                "comment_counts",
                "cached_query_scope",
                "cached_linkage",
            ],
            "rules": "Reserve exposed pilot as dev; exclude all other exposed candidate components; alternate test/dev and query domains; choose remaining components by SHA-256 of sorted IDs.",
            "comment_counts_are_not_multi_turn_labels": True,
            "known_external_duplicate_edge": list(CONFIRMED_DEV_FAMILY),
            "no_outcome_or_question_text_used": True,
        },
        "known_exposure_candidate_closure": exposure_closure,
        "candidates": candidates,
        "human_review_tasklist": [
            {
                "candidate_case_id": candidate["candidate_case_id"],
                "candidate_family_id": candidate["candidate_family_id"],
                "proposed_split": candidate["proposed_split"],
                "reviewer": "unassigned",
                "status": "pending",
                "tasks": list(REVIEW_TASKS),
            }
            for candidate in candidates
        ],
        "partial_corpus_denylist": {
            "issue_ids": deny,
            "scope": "These Issues, comments and outcomes; expanded reviewed families and direct-answer documents remain pending.",
            "complete": False,
            "final_corpus_approved": False,
            "may_be_used_as_final_allowlist": False,
        },
        "limitations": [
            "Cached selected links are incomplete and do not prove duplicate relationships or complete families.",
            "No initial user messages, evidence labels, acceptable decisions, gold, reply branches or semantic judgments were authored.",
            "Reservation counts do not satisfy E1 or the multi-turn requirement; existing split and registered fixtures are unchanged.",
            "Test questions and outcomes must remain separate from tuning; human family/chronology review is required before freeze.",
        ],
    }


def encoded(reservation):
    return (json.dumps(reservation, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=Path, default=ROOT / "streamlit-data-for-dev-test")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        _reject("CandidateOutputAlreadyExists")
    reservation = propose(args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as target:
        target.write(encoded(reservation))
    print(
        json.dumps(
            {
                "status": reservation["status"],
                "reservation_counts": reservation["reservation_counts"],
                "e1_complete": False,
            }
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CandidateReservationRejected as error:
        raise SystemExit(str(error)) from None
