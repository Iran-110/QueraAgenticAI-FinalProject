"""Actual native arm membership is checked before keys, scopes or transports."""

import hashlib
import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest

from agent_app.retrieval.offline_index import build_index
from agent_app.retrieval.pilot_corpus import MANIFEST_NAME, build_pilot_corpus
from agent_app.testing.http_pilot_runtime import offline_network

ROOT = Path(__file__).resolve().parents[1]
ARMS = ("historical_14_sources", "new_18_sources")


@pytest.fixture
def runner(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    specification = importlib.util.spec_from_file_location(
        "native_registered_arm_guard", ROOT / "scripts/dev_rag_model_probe.py"
    )
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)

    def forbidden(*args, **kwargs):
        raise AssertionError("ArmGuardMustNeverAccessCredentialsOrLedger")

    monkeypatch.setattr(module, "credential", forbidden)
    monkeypatch.setattr(module, "BudgetLedger", forbidden)
    return module


@pytest.fixture(scope="module")
def indexes(tmp_path_factory):
    root = tmp_path_factory.mktemp("actual-arm-membership")
    profiles = {
        ARMS[0]: (
            ROOT / "data/evaluation/dev-three-v1/split-manifest.json",
            ROOT / "experiments/corpus/pilot-allowlist.json",
        ),
        ARMS[1]: (
            ROOT / "experiments/dev_rag_coverage_v1/split-manifest.json",
            ROOT / "experiments/dev_rag_coverage_v1/allowlist.json",
        ),
        "old_profile_as_candidate": (
            ROOT / "data/evaluation/dev-three-v1/split-manifest.json",
            ROOT / "experiments/corpus/pilot-allowlist.json",
        ),
        "old_wrong_split": (
            ROOT / "data/evaluation/split-manifest.json",
            ROOT / "experiments/corpus/pilot-allowlist.json",
        ),
    }
    modified = json.loads(profiles[ARMS[1]][0].read_bytes())
    modified["updated_on"] = "2000-01-01"
    changed_split = root / "different-current-split.json"
    changed_split.write_text(json.dumps(modified), encoding="utf-8")
    profiles["new_wrong_split"] = (changed_split, profiles[ARMS[1]][1])
    bindings = {}
    with offline_network():
        for label, (split, allowlist) in profiles.items():
            corpus = build_pilot_corpus(ROOT / "streamlit-data-for-dev-test", split, allowlist)
            directory = root / label
            snapshot = build_index(corpus, directory)
            bindings[label] = {
                "path": str(directory),
                "snapshot_id": snapshot,
                "manifest_sha256": hashlib.sha256(
                    (directory / MANIFEST_NAME).read_bytes()
                ).hexdigest(),
            }
    return bindings


def actual_pair(indexes):
    return {arm: deepcopy(indexes[arm]) for arm in ARMS}


def test_correct_arm_names_bind_exact_native_profiles_without_key_or_ledger(runner, indexes):
    with offline_network():
        assert runner.validate_registered_indexes(ROOT, actual_pair(indexes)) == actual_pair(
            indexes
        )


@pytest.mark.parametrize(
    "mutation",
    ["swapped", "same-new", "same-old", "extra-arm", "missing-arm"],
)
def test_arm_swaps_aliases_or_unregistered_names_are_rejected(runner, indexes, mutation):
    pair = actual_pair(indexes)
    if mutation == "swapped":
        pair = {ARMS[0]: pair[ARMS[1]], ARMS[1]: pair[ARMS[0]]}
    elif mutation == "same-new":
        pair[ARMS[0]] = deepcopy(pair[ARMS[1]])
    elif mutation == "same-old":
        pair[ARMS[1]] = deepcopy(pair[ARMS[0]])
    elif mutation == "extra-arm":
        pair["unregistered-arm"] = deepcopy(pair[ARMS[1]])
    else:
        del pair[ARMS[1]]
    with offline_network(), pytest.raises(ValueError, match="^RealIndexRegistrationRejected$"):
        runner.validate_registered_indexes(ROOT, pair)


@pytest.mark.parametrize(
    "arm,substitute",
    [
        (ARMS[1], "old_profile_as_candidate"),
        (ARMS[1], "new_wrong_split"),
        (ARMS[0], "old_wrong_split"),
    ],
)
def test_valid_native_storage_with_wrong_profile_or_split_cannot_enter_trial(
    runner, indexes, arm, substitute
):
    pair = actual_pair(indexes)
    pair[arm] = deepcopy(indexes[substitute])
    # A generic read binding accepts each native corpus independently; the arm
    # guard must also compare its whole manifest with the registered expected one.
    with offline_network():
        runner.validate_index_bindings(pair)
        with pytest.raises(ValueError, match="^RealIndexRegistrationRejected$"):
            runner.validate_registered_indexes(ROOT, pair)


def test_claimed_count_cannot_replace_actual_profile_validation(runner, indexes):
    pair = actual_pair(indexes)
    pair[ARMS[1]] = deepcopy(indexes["old_profile_as_candidate"])
    with offline_network(), pytest.raises(ValueError, match="^RealIndexRegistrationRejected$"):
        # The receipt may declare 18/36 elsewhere, but native corpus here is 14/30.
        runner.validate_registered_indexes(ROOT, pair)
