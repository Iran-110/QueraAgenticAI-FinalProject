"""Offline raw-source default audit; optional full source verification, no imports/execution.

The bundled projection is portable. A supplied full raw document or implementation
file is verified against the recorded physical hash before membership/AST checks.
Nothing is written to corpus, old evidence, index, ledger or runtime configuration.
"""

import argparse
import ast
import hashlib
import json
import stat
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.core_parameter_focus_v1.parameters import parse_parameter_record  # noqa: E402
from experiments.core_parameter_focus_v1.replay import (  # noqa: E402
    run_replay as run_original_replay,
)
from experiments.core_parameter_focus_v1.replay import write_new_report  # noqa: E402
from experiments.core_raw_defaults_v1.normalization import (  # noqa: E402
    canonical_entry_sha256,
    normalize_raw_defaults,
    validate_raw_default_normalization,
)

PACKAGE = Path(__file__).resolve().parent
_ERROR = "RawDefaultReplayRejected"


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _invalid_constant(_value):
    raise ValueError


def _json(raw):
    return json.loads(raw, object_pairs_hook=_unique, parse_constant=_invalid_constant)


def _read(path, limit=1_000_000):
    info = path.lstat()
    if path.is_symlink() or info.st_nlink != 1 or not stat.S_ISREG(info.st_mode):
        raise ValueError
    if info.st_size > limit:
        raise ValueError
    return path.read_bytes()


def verify_raw_document(raw, snapshot):
    """Hash/pointer equality against recorded pins; never a source-truth score."""
    if type(raw) is not bytes or len(raw) > 64_000_000:
        raise ValueError
    if _sha(raw) != snapshot["source_file_sha256"]:
        raise ValueError
    document = _json(raw)
    for item in snapshot["records"]:
        entry = document[item["version"]][item["function"]]
        if canonical_entry_sha256(entry) != item["raw_entry_sha256"]:
            raise ValueError
    return True


def verify_implementation_source(raw, check):
    """Parse only the pinned class method; never load or execute third-party code."""
    if type(raw) is not bytes or _sha(raw) != check["sha256"]:
        raise ValueError
    source = raw.decode("utf-8")
    class_name, function_name = check["qualified_function"].split(".")
    module = ast.parse(source)
    classes = [x for x in module.body if isinstance(x, ast.ClassDef) and x.name == class_name]
    if len(classes) != 1:
        raise ValueError
    functions = [
        x for x in classes[0].body if isinstance(x, ast.FunctionDef) and x.name == function_name
    ]
    if len(functions) != 1:
        raise ValueError
    args = functions[0].args
    defaults = dict(zip((item.arg for item in args.kwonlyargs), args.kw_defaults, strict=True))
    for name, expected in check["declared_defaults"].items():
        node = defaults[name]
        if (
            not isinstance(node, ast.Constant)
            or type(node.value) is not type(expected["value"])
            or node.value != expected["value"]
            or ast.get_source_segment(source, node) != expected["source_token"]
            or type(expected["line"]) is not int
            or node.lineno != expected["line"]
        ):
            raise ValueError
    return True


def run_replay(*, raw_document=None, implementation_source=None):
    try:
        protocol_raw = _read(PACKAGE / "protocol-v1.json")
        protocol = _json(protocol_raw)
        snapshot_raw = _read(PACKAGE / "raw-api-snapshot-v1.json")
        provenance_raw = _read(PACKAGE / "source-provenance-v1.json")
        if (
            _sha(snapshot_raw) != protocol["source_snapshot_sha256"]
            or _sha(provenance_raw) != protocol["source_provenance_sha256"]
            or type(protocol["provider_calls_planned"]) is not int
            or protocol["provider_calls_planned"] != 0
            or type(protocol["ledger_writes_planned"]) is not int
            or protocol["ledger_writes_planned"] != 0
            or protocol["runtime_adoption"] is not False
        ):
            raise ValueError
        snapshot, provenance = _json(snapshot_raw), _json(provenance_raw)
        if provenance["source_snapshot_sha256"] != _sha(snapshot_raw):
            raise ValueError
        full_raw_checked = raw_document is not None and verify_raw_document(raw_document, snapshot)
        implementation_checked = implementation_source is not None and verify_implementation_source(
            implementation_source, provenance["implementation_source_1_49_0"]
        )
        previous = run_original_replay()
        rows, by_source = [], {}
        for item in snapshot["records"]:
            if item["json_pointer"] != f"/{item['version']}/{item['function']}":
                raise ValueError
            report = normalize_raw_defaults(
                item["raw_entry"],
                item["legacy_seed_text"],
                version=item["version"],
                function=item["function"],
                expected_version=item["version"],
                expected_function=item["function"],
                docs_commit=snapshot["docs_commit"],
                raw_file_sha256=snapshot["source_file_sha256"],
                expected_entry_sha256=item["raw_entry_sha256"],
            )
            validate_raw_default_normalization(report)
            if report.original_text_sha256 != item["legacy_seed_text_sha256"]:
                raise ValueError
            before, after = (
                parse_parameter_record(report.original_text),
                parse_parameter_record(report.derived_text),
            )
            for left, right in zip(before.parameters, after.parameters, strict=True):
                old_body = report.original_text[left.start : left.end].splitlines(keepends=True)[1:]
                new_body = report.derived_text[right.start : right.end].splitlines(keepends=True)[
                    1:
                ]
                if old_body != new_body:
                    raise ValueError
            if (
                report.original_text[: before.prefix_span[1]]
                != report.derived_text[: after.prefix_span[1]]
                or report.original_text[before.suffix_span[0] :]
                != report.derived_text[after.suffix_span[0] :]
            ):
                raise ValueError
            if item["version"] == protocol["primary_version"]:
                expected = provenance["implementation_source_1_49_0"]["declared_defaults"]
                observed = {entry.name: entry for entry in report.observations}
                for name in protocol["primary_parameters"]:
                    if observed[name].signature_token != expected[name]["source_token"]:
                        raise ValueError
            changed = [
                asdict(observation)
                for observation in report.observations
                if observation.old_text != observation.replacement
            ]
            rows.append(
                {
                    "version": item["version"],
                    "function": item["function"],
                    "changed_headers": changed,
                    "all_legacy_parameter_bodies_and_global_context_preserved": True,
                    "normalization": asdict(report),
                }
            )
            source_id = item["legacy_seed_source_id"]
            if source_id in by_source:
                raise ValueError
            by_source[source_id] = (item, report)
        links = []
        for old in previous["rows"]:
            candidate = old["projection"].get("candidate")
            if candidate is None:
                continue
            for quotation in candidate["quotations"]:
                item, report = by_source[quotation["source_id"]]
                if (
                    _sha(item["legacy_seed_text"].strip().encode("utf-8"))
                    != quotation["source_text_sha256"]
                ):
                    raise ValueError
                observed = next(
                    row for row in report.observations if row.name == quotation["parameter_name"]
                )
                links.append(
                    {
                        "turn": old["turn"],
                        "candidate_context_sha256": candidate["context_sha256"],
                        "parameter": observed.name,
                        "raw_entry_pointer": item["json_pointer"],
                        "raw_metadata_default_json": observed.raw_default_json,
                        "signature_declared_default": observed.signature_token,
                        "basis": report.basis,
                        "source_normalization_matches_historical_supplied_excerpt": True,
                        "new_model_choice_or_approval": False,
                    }
                )
        return {
            "schema_version": 1,
            "experiment_id": "core_raw_defaults_v1",
            "protocol_sha256": _sha(protocol_raw),
            "source_snapshot_sha256": _sha(snapshot_raw),
            "source_provenance_sha256": _sha(provenance_raw),
            "full_raw_file_hash_and_pointer_membership_verified_in_this_run": bool(
                full_raw_checked
            ),
            "pinned_python_declaration_ast_verified_in_this_run": bool(implementation_checked),
            "portable_projection_is_not_full_raw_authentication": True,
            "original_attempts_retained": previous["attempt_rows"],
            "original_final_turns_retained": previous["final_turns_retained"],
            "old_artifacts_or_drafts_rewritten": False,
            "provider_calls": 0,
            "ledger_writes": 0,
            "runtime_adoption": False,
            "actual_installed_runtime_verified": False,
            "model_quality_improvement_established": False,
            "human_usefulness": None,
            "derived_records_are_not_complete_raw_documentation": True,
            "historical_candidate_source_links": links,
            "rows": rows,
            "limits": protocol["non_goals"],
        }
    except Exception:
        raise ValueError(_ERROR) from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--raw-document", type=Path)
    parser.add_argument("--implementation-source", type=Path)
    args = parser.parse_args()
    try:
        report = run_replay(
            raw_document=_read(args.raw_document, 64_000_000) if args.raw_document else None,
            implementation_source=_read(args.implementation_source)
            if args.implementation_source
            else None,
        )
        write_new_report(args.output, report)
        print(json.dumps({key: value for key, value in report.items() if key != "rows"}))
        return 0
    except Exception:
        print(json.dumps({"error_code": _ERROR}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
