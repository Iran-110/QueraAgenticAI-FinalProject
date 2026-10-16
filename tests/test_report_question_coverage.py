"""Authored neutral fixtures only; default checks never open held-out data."""

import hashlib
import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest

from agent_app.contracts import GroundedGap
from agent_app.orchestration.intake import STREAMLIT_VERSION_QUESTION
from agent_app.reasoning.catalog import load_user_gap_vocabulary

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "report_question_coverage", ROOT / "scripts/report_question_coverage.py"
)
coverage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(coverage)
QUESTION = "Please provide a minimal reproduction."
VERSION = STREAMLIT_VERSION_QUESTION.name


def _vocabulary():
    return tuple(
        GroundedGap(
            name=name,
            kind="user",
            description="Caller-declared missing information.",
            necessity="The user can supply this information.",
            question=QUESTION,
        )
        for name in ("code_sample", "runtime_context")
    )


def _turn(identifier, acceptable, *, gaps=(), maintainer=None, case_id=None, **visible):
    turn = {
        "id": identifier,
        "visible": {"message": "Neutral user update."} | visible,
        "gold": {
            "acceptable_decisions": acceptable,
            "gaps": [
                {
                    "name": name,
                    "kind": "user",
                    "question": STREAMLIT_VERSION_QUESTION.question
                    if name == VERSION
                    else QUESTION,
                    "necessity": "The user can supply this information.",
                }
                for name in gaps
            ],
        },
        "maintainer": maintainer or {"decision": "none"},
    }
    if case_id is not None:
        turn["case_id"] = case_id
    return turn


def _fixture(turns, routes, *, extra_cases=()):
    return {
        "registered_before_first_run": True,
        "case": {"case_id": "neutral-case", "extra_case_ids": list(extra_cases)},
        "turns": turns,
        "evaluation": {"coverage": {"turn_ids": [turn["id"] for turn in turns], "routes": routes}},
    }


def _ask(source, target, name):
    return {
        "from_turn": source,
        "to_turn": target,
        "guard": {"decision": "ask", "question_target": name},
    }


def _answer(source, target=None):
    return {"from_turn": source, "to_turn": target, "guard": {"decision": "answer"}}


def _single(**visible):
    return _fixture(
        [_turn("initial", ["ask"], gaps=("code_sample",), unknowns=["code_sample"], **visible)],
        [_ask("initial", None, "code_sample")],
    )


def _rows(fixture):
    return coverage.branch_rows(fixture, _vocabulary())


def test_incoming_ask_does_not_make_an_explicitly_unanswered_target_known():
    fixture = _fixture(
        [
            _turn(
                "initial",
                ["ask"],
                gaps=("code_sample",),
                unknowns=["code_sample"],
                maintainer={"decision": "approve"},
            ),
            _turn("unanswered", ["ask"], gaps=("code_sample",), unknowns=["code_sample"]),
        ],
        [_ask("initial", "unanswered", "code_sample"), _ask("unanswered", None, "code_sample")],
    )
    assert [row["availability"] for row in _rows(fixture)] == ["all", "all"]


def test_sibling_facts_do_not_leak_and_merge_reports_mixed_path_availability():
    fixture = _fixture(
        [
            _turn(
                "initial",
                ["ask"],
                gaps=("code_sample", "runtime_context"),
                unknowns=["code_sample", "runtime_context"],
                maintainer={"decision": "approve"},
            ),
            _turn(
                "branch-a",
                ["answer"],
                reported_facts=[{"name": "code_sample", "value": "neutral code"}],
            ),
            _turn(
                "branch-b",
                ["answer"],
                reported_facts=[{"name": "runtime_context", "value": "neutral environment"}],
            ),
            _turn("merged", ["ask"], gaps=("code_sample",), unknowns=["code_sample"]),
        ],
        [
            _ask("initial", "branch-a", "code_sample"),
            _ask("initial", "branch-b", "runtime_context"),
            _answer("branch-a", "merged"),
            _answer("branch-b", "merged"),
            _ask("merged", None, "code_sample"),
        ],
    )
    merged = _rows(fixture)[-1]
    assert merged["availability"] == "some"
    assert merged["projected_path_states"] == 2
    assert merged["available_path_states"] == 1


def test_fact_name_whitespace_normalizes_and_active_user_fact_suppresses_question():
    fixture = _single(reported_facts=[{"name": " Code_Sample ", "value": "current code"}])
    assert _rows(fixture)[0]["availability"] == "none"


@pytest.mark.parametrize("withdrawal", [False, True])
def test_real_context_switch_and_explicit_withdrawal_restore_question(withdrawal):
    visible = (
        {"reported_facts": [{"name": "CODE_SAMPLE", "value": None}]}
        if withdrawal
        else {"context_changed": True}
    )
    fixture = _fixture(
        [
            _turn(
                "initial", ["answer"], reported_facts=[{"name": "code_sample", "value": "old code"}]
            ),
            _turn("changed", ["ask"], gaps=("code_sample",), **visible),
        ],
        [_answer("initial", "changed"), _ask("changed", None, "code_sample")],
    )
    assert _rows(fixture)[0]["availability"] == "all"


def test_ordinary_correction_keeps_other_user_facts():
    fixture = _fixture(
        [
            _turn(
                "initial",
                ["answer"],
                reported_facts=[
                    {"name": "code_sample", "value": "old code"},
                    {"name": "runtime_context", "value": "old environment"},
                ],
            ),
            _turn(
                "changed",
                ["ask"],
                gaps=("code_sample",),
                unknowns=["code_sample"],
                reported_facts=[{"name": "runtime_context", "value": "new environment"}],
            ),
        ],
        [_answer("initial", "changed"), _ask("changed", None, "code_sample")],
    )
    assert _rows(fixture)[0]["availability"] == "none"


def test_unvisited_other_case_never_inherits_facts():
    fixture = _fixture(
        [
            _turn(
                "case-a",
                ["answer"],
                reported_facts=[{"name": "code_sample", "value": "case A code"}],
            ),
            _turn(
                "case-b",
                ["ask"],
                gaps=("code_sample",),
                case_id="neutral-other",
                unknowns=["code_sample"],
            ),
        ],
        [_answer("case-a", "case-b"), _ask("case-b", None, "code_sample")],
        extra_cases=("neutral-other",),
    )
    row = _rows(fixture)[0]
    assert row["case_id"] == "neutral-other"
    assert row["availability"] == "all"


def _version_fixture(*, flagged=True, message="1.50.0", maintainer=None, **visible):
    return _fixture(
        [
            _turn(
                "initial",
                ["ask"],
                gaps=(VERSION,),
                unknowns=["code_sample"],
                maintainer=maintainer or {"decision": "approve"},
            ),
            _turn(
                "reply",
                ["ask"],
                gaps=("code_sample",),
                message=message,
                reply_to_approved_question=flagged,
                **visible,
            ),
        ],
        [_ask("initial", "reply", VERSION), _ask("reply", None, "code_sample")],
    )


def test_canonical_approved_version_reply_uses_actual_intake_and_preserves_other_unknowns():
    fixture = _version_fixture(message="Streamlit 1.50.0")
    rows = _rows(fixture)
    assert [row["availability"] for row in rows] == ["all", "all"]
    _, states = coverage._states(fixture, _vocabulary())
    assert VERSION not in states["reply"][0]
    assert "code_sample" in states["reply"][0]


def test_unflagged_version_number_is_not_inferred_as_a_fact():
    fixture = _version_fixture(flagged=False)
    _, states = coverage._states(fixture, _vocabulary())
    assert VERSION in states["reply"][0]


def test_exact_question_edit_then_approval_is_supported_for_canonical_reply():
    maintainer = {
        "decision": "edit",
        "edited_draft": STREAMLIT_VERSION_QUESTION.question,
        "then": "approve",
    }
    assert _rows(_version_fixture(maintainer=maintainer))[1]["availability"] == "all"


@pytest.mark.parametrize(
    "mutation", ["unclear", "structured", "unapproved", "edited", "wrong_incoming", "no_incoming"]
)
def test_unsupported_reply_or_approval_workflows_fail_closed(mutation):
    fixture = _version_fixture()
    if mutation == "unclear":
        fixture["turns"][1]["visible"]["message"] = "possibly several versions"
    elif mutation == "structured":
        fixture["turns"][1]["visible"]["unknowns"] = ["code_sample"]
    elif mutation == "unapproved":
        fixture["turns"][0]["maintainer"] = {"decision": "none"}
    elif mutation == "edited":
        fixture["turns"][0]["maintainer"] = {
            "decision": "edit",
            "edited_draft": "Changed wording",
            "then": "approve",
        }
    elif mutation == "wrong_incoming":
        fixture["turns"][0]["gold"]["acceptable_decisions"] = ["answer"]
        fixture["evaluation"]["coverage"]["routes"][0] = _answer("initial", "reply")
    else:
        fixture = _single(reply_to_approved_question=True)
    with pytest.raises(coverage.QuestionCoverageRejected, match="^QuestionCoverageRejected$"):
        _rows(fixture)


def test_vocabulary_registration_is_separate_from_exact_route_wording():
    fixture = _single()
    fixture["turns"][0]["gold"]["gaps"][0]["question"] = "Different registered wording?"
    row = _rows(fixture)[0]
    assert row["question_source"] == "vocabulary"
    assert row["definition_matches_route"] is False
    assert row["availability"] == "none"


def test_unknown_matching_is_case_insensitive_but_route_target_remains_exact():
    fixture = _single()
    fixture["turns"][0]["visible"]["unknowns"] = [" CODE_SAMPLE "]
    assert _rows(fixture)[0]["availability"] == "all"
    fixture["turns"][0]["gold"]["gaps"][0]["name"] = "Code_Sample"
    fixture["evaluation"]["coverage"]["routes"][0]["guard"]["question_target"] = "Code_Sample"
    row = _rows(fixture)[0]
    assert row["question_source"] == "vocabulary"
    assert row["availability"] == "none"


def test_missing_definition_and_unneeded_offers_are_distinct_observations():
    fixture = _single()
    row = coverage.branch_rows(fixture, ())[0]
    assert row["question_source"] == "not_in_vocabulary"
    assert row["availability"] == "none"
    answer = _fixture(
        [_turn("initial", ["answer"], unknowns=["code_sample"])], [_answer("initial")]
    )
    offers = coverage.unneeded_offers(answer, _vocabulary())
    assert offers[0]["offered_on_any_path"] == ["code_sample", VERSION]
    assert offers[0]["offered_on_all_paths"] == ["code_sample", VERSION]


def test_path_state_limit_is_checked_before_enqueue(monkeypatch):
    fixture = _version_fixture()
    calls = []
    real = coverage._apply

    def observed(*args):
        calls.append(args[0]["id"])
        return real(*args)

    monkeypatch.setattr(coverage, "_apply", observed)
    monkeypatch.setattr(coverage, "MAX_PROJECTED_STATES", 1)
    with pytest.raises(coverage.QuestionCoverageRejected):
        _rows(fixture)
    assert calls == ["initial"]


def test_terminal_path_limit_rejects_without_partial_counts(monkeypatch):
    fixture = _fixture(
        [
            _turn(
                "initial",
                ["ask"],
                gaps=("code_sample", "runtime_context"),
                unknowns=["code_sample", "runtime_context"],
            )
        ],
        [_ask("initial", None, "code_sample"), _ask("initial", None, "runtime_context")],
    )
    monkeypatch.setattr(coverage, "MAX_PROJECTED_PATHS", 1)
    with pytest.raises(coverage.QuestionCoverageRejected):
        _rows(fixture)


@pytest.mark.parametrize(
    "mutation", ["cycle", "case", "field", "duplicate", "malformed_fact", "reject_ask"]
)
def test_invalid_inputs_use_only_one_static_diagnostic(mutation):
    fixture = _single()
    if mutation == "cycle":
        fixture["evaluation"]["coverage"]["routes"][0]["to_turn"] = "initial"
    elif mutation == "case":
        fixture["turns"][0]["case_id"] = "sensitive-undeclared-case"
    elif mutation == "field":
        fixture["turns"][0]["visible"]["sensitive-extra-field"] = "sensitive-value"
    elif mutation == "duplicate":
        fixture["turns"][0]["visible"]["reported_facts"] = [
            {"name": "code_sample", "value": "one"},
            {"name": " CODE_SAMPLE ", "value": "two"},
        ]
    elif mutation == "malformed_fact":
        fixture["turns"][0]["visible"]["reported_facts"] = [
            {"name": "code_sample", "value": {"sensitive": "value"}}
        ]
    else:
        fixture["turns"][0]["maintainer"] = {"decision": "reject"}
    with pytest.raises(coverage.QuestionCoverageRejected) as error:
        _rows(fixture)
    assert str(error.value) == "QuestionCoverageRejected"
    assert "sensitive" not in repr(error.value)


def test_projection_is_deterministic_and_does_not_mutate_input():
    fixture = _version_fixture()
    original = deepcopy(fixture)
    assert _rows(fixture) == _rows(fixture)
    assert fixture == original


@pytest.fixture
def packet(tmp_path, monkeypatch):
    monkeypatch.setattr(coverage, "ROOT", tmp_path)
    vocabulary = tmp_path / "vocabulary.json"
    vocabulary.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "user_gaps": [gap.model_dump(mode="json") for gap in _vocabulary()],
            }
        )
    )
    manifest = {"registered_fixtures": {}}
    paths = {}
    for split in ("dev", "test"):
        path = tmp_path / f"neutral-{split}.json"
        fixture = _single()
        fixture["case"]["split"] = split
        path.write_text(json.dumps(fixture))
        paths[split] = path
        manifest["registered_fixtures"][split] = [
            {"path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        ]
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    return manifest_path, vocabulary, paths


def test_build_default_reads_dev_only_and_test_requires_explicit_owner_opt_in(packet, monkeypatch):
    manifest, vocabulary, paths = packet
    real = Path.read_bytes

    def read(path):
        assert path != paths["test"], "Default build must not read a test fixture"
        return real(path)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "read_bytes", read)
        report, details = coverage.build(manifest_path=manifest, vocabulary_path=vocabulary)
    assert set(report["splits"]) == set(details) == {"dev"}
    with pytest.raises(coverage.QuestionCoverageRejected):
        coverage.build(splits=("test",), manifest_path=manifest, vocabulary_path=vocabulary)


@pytest.mark.parametrize("kind", ["test_directory", "evidence", "card", "symlink"])
def test_default_dev_rejects_redirected_protected_paths_before_reading(packet, monkeypatch, kind):
    manifest, vocabulary, _ = packet
    root = manifest.parent
    target = root / "data/evaluation/split-e1-v1/test/neutral.json"
    if kind == "evidence":
        target = root / "evidence-test-neutral.json"
    elif kind == "card":
        target = root / "test-card-review-v1.json"
    selected = target
    if kind == "symlink":
        selected = root / "neutral-dev-link.json"
        selected.symlink_to(target)
    value = json.loads(manifest.read_text())
    value["registered_fixtures"]["dev"][0]["path"] = str(selected.relative_to(root))
    manifest.write_text(json.dumps(value))
    real = Path.read_bytes
    attempts = []

    def guarded(path):
        if path == target or path == selected:
            attempts.append(path)
            raise PermissionError("Protected neutral target must not be opened")
        return real(path)

    monkeypatch.setattr(Path, "read_bytes", guarded)
    with pytest.raises(coverage.QuestionCoverageRejected):
        coverage.build(manifest_path=manifest, vocabulary_path=vocabulary)
    assert attempts == []


def test_fixture_declared_split_must_match_requested_split(packet):
    manifest, vocabulary, paths = packet
    value = json.loads(manifest.read_text())
    value["registered_fixtures"]["dev"] = value["registered_fixtures"]["test"]
    manifest.write_text(json.dumps(value))
    with pytest.raises(coverage.QuestionCoverageRejected):
        coverage.build(manifest_path=manifest, vocabulary_path=vocabulary)


def test_owner_opt_in_exports_only_numeric_test_summary_even_in_returned_details(packet):
    manifest, vocabulary, _ = packet
    report, details = coverage.build(
        splits=("dev", "test"),
        manifest_path=manifest,
        vocabulary_path=vocabulary,
        evaluation_owner_test=True,
    )
    assert set(report["splits"]["test"]) == {"fixtures_checked", "summary"}
    assert set(details) == {"dev"}
    assert "code_sample" not in json.dumps(report["splits"]["test"])
    assert all(
        type(value) is int
        for value in report["splits"]["test"]["summary"]["by_path_availability"].values()
    )


def test_cli_dev_default_and_explicit_separate_owner_output(packet, monkeypatch, tmp_path, capsys):
    manifest, vocabulary, _ = packet
    real = coverage.build
    monkeypatch.setattr(
        coverage,
        "build",
        lambda **kwargs: real(manifest_path=manifest, vocabulary_path=vocabulary, **kwargs),
    )
    output = tmp_path / "dev-v2.json"
    monkeypatch.setattr(coverage, "OUTPUT", output)
    assert coverage.main([]) == 0
    assert set(json.loads(output.read_text())["splits"]) == {"dev"}
    before = output.read_bytes()
    assert coverage.main(["--include-test-evaluation-owner"]) == 1
    assert output.read_bytes() == before
    owner = tmp_path / "owner-counts.json"
    assert coverage.main(["--include-test-evaluation-owner", "--output", str(owner)]) == 0
    assert set(json.loads(owner.read_text())["splits"]["test"]) == {"fixtures_checked", "summary"}
    assert "question_target" not in capsys.readouterr().out


def test_cli_refuses_to_overwrite_immutable_v1_before_any_build(monkeypatch):
    monkeypatch.setattr(
        coverage, "build", lambda **kwargs: pytest.fail("Must reject before reading fixtures")
    )
    assert coverage.main(["--output", str(coverage.LEGACY_OUTPUT)]) == 1


def test_cli_refuses_existing_output_before_build_and_preserves_bytes(monkeypatch, tmp_path):
    output = tmp_path / "existing.json"
    output.write_bytes(b"retained original bytes")
    monkeypatch.setattr(
        coverage, "build", lambda **kwargs: pytest.fail("No build before rejection")
    )
    assert coverage.main(["--output", str(output)]) == 1
    assert output.read_bytes() == b"retained original bytes"


@pytest.mark.parametrize("argument", ["manifest_path", "vocabulary_path"])
def test_protected_metadata_is_rejected_before_any_read(packet, monkeypatch, argument):
    manifest, vocabulary, _ = packet
    protected = manifest.parent / "data/evaluation/split-e1-v1/test/neutral.json"
    values = {"manifest_path": manifest, "vocabulary_path": vocabulary} | {argument: protected}
    attempts = []
    real_read, real_open = Path.read_bytes, Path.open

    def read(path):
        if path == protected:
            attempts.append("read")
            raise PermissionError("Not allowed")
        return real_read(path)

    def opened(path, *args, **kwargs):
        if path == protected:
            attempts.append("open")
            raise PermissionError("Not allowed")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", read)
    monkeypatch.setattr(Path, "open", opened)
    with pytest.raises(coverage.QuestionCoverageRejected):
        coverage.build(**values)
    assert attempts == []


def test_vocabulary_definitions_and_hash_bind_one_captured_read(packet, monkeypatch):
    _, vocabulary, _ = packet
    raw = vocabulary.read_bytes()
    expected = load_user_gap_vocabulary(str(vocabulary))
    definitions, digest = coverage._vocabulary(vocabulary)
    assert definitions == expected
    assert digest == hashlib.sha256(raw).hexdigest()
    real_open = Path.open
    calls = []

    def opened(path, *args, **kwargs):
        if path == vocabulary:
            calls.append(path)
            assert len(calls) == 1
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", opened)
    assert coverage._vocabulary(vocabulary) == (expected, digest)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "raw",
    [
        '{"schema_version":1,"schema_version":1,"user_gaps":[]}',
        '{"schema_version":true,"user_gaps":[]}',
        '{"schema_version":1,"user_gaps":[],"unknown":1}',
        '{"schema_version":1,"user_gaps":[NaN]}',
        '{"schema_version":1,"user_gaps":{}}',
    ],
)
def test_local_strict_vocabulary_parser_agrees_with_core_loader_rejections(tmp_path, raw):
    path = tmp_path / "neutral-vocabulary.json"
    path.write_text(raw)
    with pytest.raises(ValueError):
        load_user_gap_vocabulary(str(path))
    with pytest.raises(ValueError):
        coverage._vocabulary(path)


def test_nonoperational_maintainer_note_does_not_change_projection():
    fixture = _single()
    before = _rows(fixture)
    fixture["turns"][0]["maintainer"]["note"] = "Neutral historical annotation."
    assert _rows(fixture) == before


def test_committed_dev_v3_matches_explicit_dev_only_rebuild():
    path = ROOT / "data/evaluation/split-e1-v1/question-coverage-dev-v3.json"
    committed = json.loads(path.read_text(encoding="utf-8"))
    rebuilt, details = coverage.build(splits=("dev",))
    assert rebuilt == committed
    assert set(committed["splits"]) == set(details) == {"dev"}


def test_dev_v2_differs_from_v3_only_by_the_manifest_pin():
    # v2 was built before dev-three v2 replaced v1 in the manifest; the dev
    # projection itself is unchanged.
    reports = [
        json.loads(
            (ROOT / f"data/evaluation/split-e1-v1/question-coverage-dev-{v}.json").read_text(
                encoding="utf-8"
            )
        )
        for v in ("v2", "v3")
    ]
    assert reports[0]["manifest_sha256"] != reports[1]["manifest_sha256"]
    for report in reports:
        report.pop("manifest_sha256")
    assert reports[0] == reports[1]
