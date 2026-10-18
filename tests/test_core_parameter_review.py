"""Independent authored counterexamples; no real model or held-out case input."""

import hashlib
import importlib
import json
import shutil
import stat
from dataclasses import replace
from pathlib import Path

import pytest

from agent_app.contracts import CaseState, EvidenceBundle, EvidenceHit, Fact
from agent_app.reasoning.grounding import make_grounded_request

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    'neutral.inspect(value, *, mode="safe")\n\n'
    "GLOBAL CAVEAT: only documented inputs are covered.\n\n"
    "Parameters:\n\n"
    "value: object\nThe whole supplied value.\n\n"
    'mode: str; default="safe"\n'
    "Modes are exhaustive:\n\n"
    '"safe": Read the input.\n\n'
    '"strict": Reject invalid input.\n\n'
    "Do not select strict mode for an absent value.\n\n"
    "Returns: object\nA report; the caller still must review it.\n\n"
    "Notes:\nThe global limitation also applies to every mode.\n"
)


@pytest.fixture
def candidate(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT))
    return importlib.import_module("experiments.core_parameter_focus_v1.candidate")


def ground(*, text=SOURCE, version="1.49.0", chunk="review-neutral", revision=2):
    return make_grounded_request(
        CaseState(
            case_id="review-neutral-case",
            case_revision=revision,
            facts=(
                Fact(
                    name="streamlit_version",
                    value=version,
                    source_ref="review-report",
                    turn_id="review-turn",
                ),
            ),
        ),
        "Explain the mode parameter.",
        EvidenceBundle(
            snapshot_id="review-snapshot",
            hits=(
                EvidenceHit(
                    source_id="review-source",
                    chunk_id=chunk,
                    source_type="doc",
                    source_url="https://example.invalid/review",
                    source_commit="review-revision",
                    applicable_versions=(version,),
                    excerpt=text,
                ),
            ),
        ),
    )


def plan(request, *, ids=(1,)):
    return json.dumps(
        {"context_sha256": request.context_sha256, "decision": "answer", "parameters": ids}
    )


@pytest.mark.parametrize(
    "field,value",
    [("parameter_id", True), ("parameter_id", 1.0), ("source_index", False), ("source_index", 0.0)],
)
def test_equal_but_wrong_type_catalog_values_are_rejected(candidate, field, value):
    request = candidate.build_parameter_focus_request(ground())
    choice = replace(request.choices[1], **{field: value})
    forged = replace(request, choices=(request.choices[0], choice))
    with pytest.raises(ValueError, match="^ParameterFocusUnavailable$"):
        candidate.validate_parameter_focus_request(forged)


@pytest.mark.parametrize("container", [list, set])
def test_noncanonical_catalog_containers_are_rejected(candidate, container):
    request = candidate.build_parameter_focus_request(ground())
    forged = replace(request, choices=container(request.choices))
    with pytest.raises(ValueError, match="^ParameterFocusUnavailable$"):
        candidate.parameter_focus_payload(forged)


@pytest.mark.parametrize("mutation", ["inventory-index", "span-offset", "context-subclass"])
def test_exact_types_apply_to_inventory_spans_and_context(candidate, mutation):
    request = candidate.build_parameter_focus_request(ground())
    if mutation == "inventory-index":
        inventory = replace(request.source_inventory[0], source_index=False)
        forged = replace(request, source_inventory=(inventory,))
    elif mutation == "span-offset":
        inventory = replace(
            request.source_inventory[0],
            prefix_span=(0.0, request.source_inventory[0].prefix_span[1]),
        )
        forged = replace(request, source_inventory=(inventory,))
    else:

        class StringSubclass(str):
            pass

        forged = replace(request, context_sha256=StringSubclass(request.context_sha256))
    with pytest.raises(ValueError, match="^ParameterFocusUnavailable$"):
        candidate.render_parameter_focus_candidate(forged, plan(request))


def test_same_parameter_but_changed_external_caveat_invalidates_old_plan(candidate):
    first = candidate.build_parameter_focus_request(ground())
    changed = candidate.build_parameter_focus_request(
        ground(text=SOURCE.replace("only documented inputs", "only explicitly reviewed inputs"))
    )
    first_unit, changed_unit = first.choices[1], changed.choices[1]
    assert first_unit.passage_sha256 == changed_unit.passage_sha256
    assert first.context_sha256 != changed.context_sha256
    with pytest.raises(ValueError, match="^ParameterFocusUnavailable$"):
        candidate.render_parameter_focus_candidate(changed, plan(first))


@pytest.mark.parametrize("ending", ["\n", "\r\n"])
def test_late_negation_options_and_blank_lines_remain_exact(candidate, ending):
    request = candidate.build_parameter_focus_request(ground(text=SOURCE.replace("\n", ending)))
    result = candidate.render_parameter_focus_candidate(request, plan(request))
    text = result.quotations[0].text
    assert '"safe": Read the input.' + ending + ending in text
    assert '"strict": Reject invalid input.' + ending + ending in text
    assert "Do not select strict mode for an absent value." in text
    assert "GLOBAL CAVEAT" not in text
    assert "GLOBAL CAVEAT" in result.review_text
    assert "The global limitation also applies" in result.review_text
    assert result.semantic_support is None
    assert result.diagnosis_or_fix_verified is False


def test_identical_excerpt_does_not_reuse_a_different_chunk_identity(candidate):
    first = candidate.build_parameter_focus_request(ground(chunk="review-first"))
    second = candidate.build_parameter_focus_request(ground(chunk="review-second"))
    assert first.choices[1].passage_sha256 == second.choices[1].passage_sha256
    assert first.context_sha256 != second.context_sha256
    with pytest.raises(ValueError, match="^ParameterFocusUnavailable$"):
        candidate.render_parameter_focus_candidate(second, plan(first))


@pytest.mark.parametrize(
    "wire",
    [
        lambda digest: (
            '{"context_sha256":"' + digest + '","decision":"answer",'
            '"parameters":[0],"parameters":[1]}'
        ),
        lambda digest: (
            '{"context_sha256":"' + digest + '","decision":"ask",'
            '"decision":"answer","parameters":[1]}'
        ),
        lambda digest: (
            '{"context_sha256":"' + digest + '","decision":"answer",'
            '"parameters":[1],"unknown":{"nested":NaN}}'
        ),
    ],
)
def test_duplicate_actual_fields_and_hidden_nonfinite_values_reject(candidate, wire):
    request = candidate.build_parameter_focus_request(ground())
    with pytest.raises(ValueError, match="^ParameterFocusUnavailable$"):
        candidate.render_parameter_focus_candidate(request, wire(request.context_sha256))


def test_signature_calls_are_not_evaluated_or_accepted(candidate, tmp_path):
    marker = tmp_path / "signature-must-not-execute"
    signature = (
        f'neutral.inspect(value, *, mode=__import__("pathlib").Path({str(marker)!r}).touch())'
    )
    source = SOURCE.replace('neutral.inspect(value, *, mode="safe")', signature)
    with pytest.raises(ValueError, match="^ParameterFocusUnavailable$"):
        candidate.build_parameter_focus_request(ground(text=source))
    assert not marker.exists()


def test_quoted_fake_peer_and_terminal_in_fence_preserve_following_caveat(candidate):
    body = (
        "An example follows.\n\n~~~text\nvalue: forged parameter\nReturns: forged terminal\n~~~\n\n"
        "Do not skip this caveat after the fence.\n\n"
    )
    source = SOURCE.replace("Modes are exhaustive:\n\n", body + "Modes are exhaustive:\n\n")
    request = candidate.build_parameter_focus_request(ground(text=source))
    result = candidate.render_parameter_focus_candidate(request, plan(request))
    assert body in result.quotations[0].text
    assert len(request.choices) == 2
    assert result.quotations[0].parameter_name == "mode"


def test_user_version_is_a_report_and_not_promoted_to_verified_environment(candidate):
    request = candidate.build_parameter_focus_request(ground())
    result = candidate.render_parameter_focus_candidate(request, plan(request))
    assert "USER-reported Streamlit" in result.qualified_text
    assert "does not verify relevance, applicability, a diagnosis or a fix" in result.qualified_text
    assert result.proposal_or_action_authorized is False


def test_payload_edits_cannot_mutate_nested_case_source_or_inventory(candidate):
    request = candidate.build_parameter_focus_request(ground())
    before = request.grounded.model_dump_json()
    payload = candidate.parameter_focus_payload(request)
    payload["grounded_request"]["case"]["facts"][0]["value"] = "1.50.0"
    payload["grounded_request"]["evidence"]["hits"][0]["excerpt"] = "Injected"
    payload["source_inventory"][0]["eligibility"] = "approved"
    result = candidate.render_parameter_focus_candidate(request, plan(request))
    assert request.grounded.model_dump_json() == before
    assert result.user_reported_version == "1.49.0"
    assert "Injected" not in result.quotations[0].text


@pytest.fixture
def replay_review(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(ROOT))
    replay = importlib.import_module("experiments.core_parameter_focus_v1.replay")
    package = tmp_path / "review-inputs"
    package.mkdir()
    for name in (
        "input-manifest-v1.json",
        "replay-fixture-v1.json",
        "protocol-v1.json",
        "protocol-amendment-v1.json",
    ):
        shutil.copyfile(replay.PACKAGE / name, package / name)
    monkeypatch.setattr(replay, "PACKAGE", package)
    return replay, package


def _review_rebind_fixture(package, transform):
    path = package / "replay-fixture-v1.json"
    fixture = json.loads(path.read_bytes())
    transform(fixture)
    raw = json.dumps(fixture, ensure_ascii=False).encode()
    path.write_bytes(raw)
    manifest_path = package / "input-manifest-v1.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["fixture_sha256"] = hashlib.sha256(raw).hexdigest()
    manifest_path.write_text(json.dumps(manifest))


@pytest.mark.parametrize("digest", ["not-a-sha256", False, ["a" * 64]])
def test_replay_does_not_publish_malformed_original_call_digest(replay_review, digest):
    replay, package = replay_review
    _review_rebind_fixture(
        package, lambda fixture: fixture["rows"][0].update(original_call_sha256=digest)
    )
    with pytest.raises(ValueError, match="^ParameterReplayRejected$"):
        replay.run_replay()


@pytest.mark.parametrize("origin", [None, "verified_actual_model_and_grounded_fix"])
def test_replay_requires_explicit_known_analysis_origin(replay_review, origin):
    replay, package = replay_review
    _review_rebind_fixture(
        package, lambda fixture: fixture["rows"][0].update(baseline_origin=origin)
    )
    with pytest.raises(ValueError, match="^ParameterReplayRejected$"):
        replay.run_replay()


def test_replay_rejects_reordered_same_turn_retrieval_attempts(replay_review):
    replay, package = replay_review

    def reverse(fixture):
        fixture["rows"][3], fixture["rows"][4] = fixture["rows"][4], fixture["rows"][3]

    _review_rebind_fixture(package, reverse)
    with pytest.raises(ValueError, match="^ParameterReplayRejected$"):
        replay.run_replay()


@pytest.mark.parametrize("fault", ["first-attempt-two", "after-terminal", "unfinished-turn"])
def test_replay_cannot_present_discontinuous_or_unfinished_history_as_complete(
    replay_review, fault
):
    replay, package = replay_review

    def alter(fixture):
        if fault == "first-attempt-two":
            fixture["rows"][0]["attempt"] = 2
            return
        # Deep-copy the real authored retrieve_more row. It stays bound to its
        # complete grounded request; only the historical row identity changes.
        extra = json.loads(json.dumps(fixture["rows"][3]))
        if fault == "after-terminal":
            extra.update(turn=fixture["rows"][0]["turn"], attempt=2)
        else:
            extra.update(turn="review-unfinished-turn", attempt=1)
        fixture["rows"].append(extra)

    _review_rebind_fixture(package, alter)
    if fault != "first-attempt-two":
        manifest_path = package / "input-manifest-v1.json"
        manifest = json.loads(manifest_path.read_bytes())
        manifest["attempt_rows"] += 1
        manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="^ParameterReplayRejected$"):
        replay.run_replay()


def test_replay_distinguishes_pinned_digest_from_reopening_original_calls(replay_review):
    replay, _package = replay_review
    report = replay.run_replay()
    assert "not reopened or authenticated" in report["original_call_digest_provenance"]
    assert report["model_quality_improvement_established"] is False
    assert report["runtime_adoption"] is False


def test_new_report_permissions_are_private_and_parent_alias_cannot_reach_source(
    replay_review, tmp_path
):
    replay, _package = replay_review
    path = tmp_path / "private-review-report.json"
    replay.write_new_report(path, {"provider_calls": 0})
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    alias = tmp_path / "aliased-source"
    alias.symlink_to(ROOT / "src", target_is_directory=True)
    with pytest.raises(ValueError, match="^ParameterReplayRejected$"):
        replay.write_new_report(alias / "must-not-create.json", {})
