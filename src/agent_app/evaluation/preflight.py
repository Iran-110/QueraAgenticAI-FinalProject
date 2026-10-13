"""Mechanical eligibility only for NEW ``frozen_final_v1`` packets.
No historical upgrade, paid-work authorization or model/index/network operation;
review declarations do not establish authenticity, semantic truth or quality.
Eligibility does not establish runnable fixtures or runtime/index binding.
"""

import argparse
import hashlib
import json
import re
from pathlib import Path

KNOWN_EXPOSURE = frozenset({8061, 8901, 9031, 11012, 12629, 12782, 16914, 17030})
DECISIONS = frozenset({"answer", "ask", "escalate"})
SOURCE_KINDS = frozenset({"documentation", "release_note", "issue", "comment", "outcome"})


class Rejected(Exception):
    pass


def _need(condition, code):
    if not condition:
        raise Rejected(code)


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _hash(value):
    return isinstance(value, str) and re.fullmatch("[0-9a-f]{64}", value) is not None


def _ids(value, code):
    _need(isinstance(value, list) and bool(value), code)
    _need(all(type(x) is int and x > 0 for x in value) and len(value) == len(set(value)), code)
    return set(value)


def _strings(value, code):
    _need(isinstance(value, list) and all(_text(x) for x in value), code)
    _need(len(value) == len(set(value)), code)
    return set(value)


def _read(path):
    raw = path.read_bytes()
    _need(len(raw) <= 10000000, "ArtifactUnreadable")
    return (json.loads(raw), hashlib.sha256(raw).hexdigest())


def _witness(value, rubric_hash):
    _need(isinstance(value, dict), "HumanReviewRequired")
    _need(value.get("type") == "human" and _text(value.get("reviewer")), "HumanReviewRequired")
    _need(value.get("rubric_sha256") == rubric_hash, "HumanReviewRequired")


def _reference(pin, explicit, root):
    _need(isinstance(pin, dict) and _hash(pin.get("sha256")), "ArtifactPinRequired")
    _need(_text(pin.get("path")), "ArtifactPinRequired")
    path = (root / pin["path"]).resolve()
    _need(path.is_relative_to(root) and path.suffix == ".json", "ArtifactPathRejected")
    _need(explicit is None or Path(explicit).resolve() == path, "ArtifactPathRejected")
    value, digest = _read(path)
    _need(digest == pin["sha256"], "ArtifactHashMismatch")
    return (value, digest, path)


def _coverage(fixture, rubric_hash):
    coverage_error, route_error = ("FixtureCoverageRejected", "FixtureRoutesRejected")
    _need(fixture.get("registered_before_first_run") is True, "FixtureRegistrationRequired")
    turns = fixture.get("turns")
    _need(isinstance(turns, list) and bool(turns), coverage_error)
    ids = [t.get("id") for t in turns]
    _need(all(_text(x) for x in ids) and len(set(ids)) == len(ids), coverage_error)
    _need(all(_text(t.get("visible", {}).get("message")) for t in turns), coverage_error)
    _need(all(_text(t.get("conversation_source")) for t in turns), coverage_error)
    coverage = fixture.get("evaluation", {}).get("coverage", {})
    _need(coverage.get("status") == "reviewed_complete", coverage_error)
    _witness(coverage.get("review"), rubric_hash)
    _need(_strings(coverage.get("turn_ids"), coverage_error) == set(ids), coverage_error)
    routes = coverage.get("routes")
    _need(isinstance(routes, list) and bool(routes), route_error)
    outgoing, edges, guards = {x: set() for x in ids}, [], set()
    for route in routes:
        source, target = (route.get("from_turn"), route.get("to_turn"))
        decision = route.get("guard", {}).get("decision")
        guard = route.get("guard", {})
        _need(set(guard) <= {"decision", "question_target"}, route_error)
        identity = (source, decision, guard.get("question_target"))
        _need(identity not in guards, route_error)
        guards.add(identity)
        _need(source in outgoing and decision in DECISIONS, route_error)
        _need(target is None or target in outgoing, route_error)
        _need(target is None or ids.index(target) > ids.index(source), route_error)
        if target is not None:
            edges.append((source, target))
        outgoing[source].add(decision)
        if decision == "ask":
            gaps = turns[ids.index(source)].get("gold", {}).get("gaps", [])
            name = route.get("guard", {}).get("question_target")
            _need(_text(name), route_error)
            matching = (g for g in gaps if g.get("kind") == "user" and g.get("name") == name)
            _need(
                any(_text(g.get("question")) and _text(g.get("necessity")) for g in matching),
                route_error,
            )
    reached = {ids[0]}
    for source, target in sorted(edges, key=lambda pair: ids.index(pair[0])):
        if source in reached:
            reached.add(target)
    _need(reached == set(ids), route_error)
    for turn in turns:
        allowed = _strings(turn.get("gold", {}).get("acceptable_decisions"), route_error)
        _need(
            bool(allowed) and allowed <= DECISIONS and (outgoing[turn["id"]] == allowed),
            route_error,
        )
    if len(turns) > 1:
        _need(len({t["visible"]["message"].strip() for t in turns}) > 1, coverage_error)
    return len(turns) > 1


def _validate(paths, manifest, corpus, rubric, exposure, root, report):
    membership_error = "FixtureMembershipRejected"
    source_error, direct_error = ("CorpusSourcesRejected", "DirectAnswerReviewRequired")
    provenance_error, duplicate_error = ("CorpusProvenanceRequired", "DuplicateReviewRequired")
    local_manifest = manifest.resolve().is_relative_to(root) and manifest.suffix == ".json"
    _need(local_manifest, "ArtifactPathRejected")
    packet, packet_hash = _read(manifest)
    frozen = packet.get("packet_id") == "frozen_final_v1" and packet.get("status") == "frozen"
    _need(frozen, "ManifestNotFrozen")
    _need(_text(packet.get("manifest_id")), "ManifestNotFrozen")
    rubric_data, rubric_hash, rubric_path = _reference(packet.get("rubric"), rubric, root)
    frozen = rubric_data.get("status") == "frozen" and _text(rubric_data.get("rubric_id"))
    _need(frozen, "RubricNotFrozen")
    _witness(packet.get("review"), rubric_hash)
    _need(packet.get("family_review_complete") is True, "FamilyReviewRequired")
    exposure_data, exposure_hash, exposure_path = _reference(packet.get("exposure"), exposure, root)
    _need(exposure_data.get("status") == "reviewed_complete", "ExposureReviewRequired")
    _witness(exposure_data.get("review"), rubric_hash)
    exposed = _ids(exposure_data.get("issue_numbers"), "ExposureReviewRequired")
    _need(KNOWN_EXPOSURE <= exposed, "ExposureClosureIncomplete")
    reviewed_exposure = set()
    for family in exposure_data.get("families", []):
        issues = _ids(family.get("issue_ids"), "ExposureClosureIncomplete")
        reviewed = family.get("review_status") == "complete" and not issues & reviewed_exposure
        _need(reviewed, "ExposureClosureIncomplete")
        reviewed_exposure |= issues
    _need(reviewed_exposure == exposed, "ExposureClosureIncomplete")
    corpus_data, corpus_hash, corpus_path = _reference(packet.get("corpus"), corpus, root)
    report["hashes"] = dict(
        manifest=packet_hash, rubric=rubric_hash, exposure=exposure_hash, corpus=corpus_hash
    )
    observed = {
        manifest.resolve(): packet_hash,
        rubric_path: rubric_hash,
        exposure_path: exposure_hash,
        corpus_path: corpus_hash,
    }
    report["hashes"]["fixtures"] = []
    selected = packet.get("selected", {})
    dev = _strings(selected.get("dev"), "SplitRejected")
    test = _strings(selected.get("test"), "SplitRejected")
    _need(len(dev) >= 15 and len(test) >= 15 and (not dev & test), "SplitRejected")
    families, occupied = ({}, set())
    for family in packet.get("families", []):
        name, split = (family.get("family_id"), family.get("split"))
        issues = _ids(family.get("issue_ids"), "FamilyOverlap")
        _need(_text(name) and name not in families and (split in {"dev", "test"}), "FamilyOverlap")
        _need(
            family.get("review_status") == "complete" and (not issues & occupied), "FamilyOverlap"
        )
        _need(split != "test" or not issues & exposed, "ExposedTestFamily")
        families[name] = (split, issues)
        occupied |= issues
    pins = packet.get("fixtures", [])
    _need(isinstance(pins, list) and len(pins) == len(dev | test), membership_error)
    pinned, actual_paths, used_families, multidev, multitest = (set(), set(), set(), 0, 0)
    for pin in pins:
        fixture, digest, path = _reference(pin, None, root)
        case = fixture.get("case", {})
        name, split, family = (case.get("case_id"), case.get("split"), case.get("family_id"))
        _need(name == pin.get("case_id") and name not in pinned, membership_error)
        _need(
            name in (dev if split == "dev" else test) and split in {"dev", "test"}, membership_error
        )
        _need(family in families and family not in used_families, membership_error)
        fixture_ids = _ids(case.get("family_issue_ids"), "FamilyOverlap")
        _need(families[family] == (split, fixture_ids), "FamilyOverlap")
        origin = case.get("origin_url")
        _need(_text(origin), "FixtureOriginRejected")
        match = re.fullmatch(r"https://github.com/streamlit/streamlit/issues/([1-9]\d*)", origin)
        _need(match is not None and int(match[1]) in fixture_ids, "FixtureOriginRejected")
        _need(split != "test" or case.get("test_eligible") is True, "ExposedTestFamily")
        multi = _coverage(fixture, rubric_hash)
        multidev += multi and split == "dev"
        multitest += multi and split == "test"
        pinned.add(name)
        actual_paths.add(path)
        used_families.add(family)
        report["hashes"]["fixtures"].append(digest)
        observed[path] = digest
    _need(pinned == dev | test and used_families == set(families), membership_error)
    supplied = []
    for path in paths:
        supplied.extend(sorted(path.glob("*.json")) if path.is_dir() else [path])
    resolved = [p.resolve() for p in supplied]
    _need(len(resolved) == len(set(resolved)) and set(resolved) == actual_paths, membership_error)
    _need(multidev + multitest >= 10 and multitest >= 5, "MultiTurnCoverageInsufficient")
    exclusions = corpus_data.get("exclusions", {})
    frozen = corpus_data.get("status") == "frozen" and _text(corpus_data.get("corpus_id"))
    _need(frozen, "CorpusNotFrozen")
    _need(exclusions.get("status") == "reviewed_complete", "CorpusExclusionRequired")
    _witness(exclusions.get("review"), rubric_hash)
    blocked = occupied | exposed
    excluded = _ids(exclusions.get("excluded_issue_ids"), "CorpusExclusionRequired")
    _need(blocked <= excluded, "CorpusExclusionIncomplete")
    duplicate = exclusions.get("duplicate_review", {})
    _need(duplicate.get("status") == "complete", duplicate_error)
    _witness(duplicate.get("review"), rubric_hash)
    _need(blocked <= _ids(duplicate.get("issue_ids"), duplicate_error), duplicate_error)
    sources = corpus_data.get("sources")
    _need(isinstance(sources, list) and bool(sources), source_error)
    source_ids = set()
    for source in sources:
        name, kind = (source.get("source_id"), source.get("kind"))
        _need(_text(name) and name not in source_ids and (kind in SOURCE_KINDS), source_error)
        _need(_hash(source.get("sha256")), source_error)
        provenance = source.get("provenance", {})
        complete = all(_text(provenance.get(x)) for x in ("url", "source_revision", "pointer"))
        _need(complete, provenance_error)
        issue = source.get("issue_id")
        _need(issue is None or (type(issue) is int and issue > 0), source_error)
        _need(kind not in {"issue", "comment", "outcome"} or issue is not None, provenance_error)
        linked = re.findall("github\\.com/streamlit/streamlit/issues/(\\d+)", provenance["url"])
        _need(
            issue not in excluded and (not {int(x) for x in linked} & excluded),
            "CorpusLeakDetected",
        )
        _need(source.get("family_id") not in families, "CorpusLeakDetected")
        source_ids.add(name)
    direct = exclusions.get("direct_answer_review", {})
    _need(direct.get("status") == "complete", direct_error)
    _witness(direct.get("review"), rubric_hash)
    _need(_strings(direct.get("corpus_source_ids"), direct_error) == source_ids, direct_error)
    _need(
        not _strings(direct.get("excluded_source_ids"), direct_error) & source_ids,
        "CorpusLeakDetected",
    )
    stable = all(_read(path)[1] == digest for path, digest in observed.items())
    _need(stable, "ArtifactChangedDuringPreflight")
    report["counts"] = dict(
        dev=len(dev),
        test=len(test),
        multi_turn=multidev + multitest,
        multi_turn_test=multitest,
        families=len(families),
        corpus_sources=len(sources),
    )


def validate_final_bundle(
    paths, manifest, corpus, *, rubric=None, exposure=None, trusted_root=None
):
    """Return safe mechanical eligibility only; never send any fixture to a model."""
    report = dict(
        accepted=False,
        quality_claim=False,
        eligibility_scope="mechanical_frozen_artifact_eligibility_only",
        diagnostics=[],
        hashes={},
        counts={},
    )
    root = (trusted_root or Path.cwd()).resolve()
    try:
        _validate(
            [Path(p) for p in paths], Path(manifest), Path(corpus), rubric, exposure, root, report
        )
        report["accepted"] = True
    except Rejected as error:
        report["diagnostics"] = [str(error)]
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
        report["diagnostics"] = ["ArtifactUnreadable"]
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixtures", nargs="+", type=Path)
    for flag in ("manifest", "corpus-manifest", "rubric", "exposure", "trusted-root"):
        parser.add_argument(
            "--" + flag, type=Path, required=flag in {"manifest", "corpus-manifest"}
        )
    args = vars(parser.parse_args())
    report = validate_final_bundle(
        args.pop("fixtures"), args.pop("manifest"), args.pop("corpus_manifest"), **args
    )
    print(json.dumps(report, sort_keys=True))
    return 0 if report["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
