"""Finite presentation composition on disposable ledger/index and mocked wires.

No team ledger, credential, paid transport, held-out payload or .env is read.
The real registered final corpus is independently built in a temporary folder.
"""

import hashlib
import json
import shutil
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from test_budget_quarantine_scope import multiple_holds as multiple_holds
from test_budget_quarantine_scope import old_rows
from test_core_delivery_http import ObservedValues, authored_response

from agent_app import presentation_runtime as runtime
from agent_app.contracts import CaseState, ReasoningContext
from agent_app.llm.budget import ExperimentRequestSlot
from agent_app.llm.metis import request_id_for
from agent_app.llm.pricing import get_price
from agent_app.orchestration.core_delivery import PREFILTER_DELIVERY_PROFILE_ID, delivery_recipe
from agent_app.retrieval import offline_index
from agent_app.retrieval.pilot_corpus import MANIFEST_NAME, build_final_corpus
from agent_app.testing.http_pilot_runtime import offline_network

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "synthetic-presentation-reviewer-token"
KEY = "synthetic-presentation-provider-key"
AUTH = {"Authorization": "Bearer " + TOKEN}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def final_v3(tmp_path_factory):
    path = tmp_path_factory.mktemp("presentation-final-native") / "index"
    with offline_network():
        corpus = build_final_corpus(
            ROOT / "streamlit-data-for-dev-test",
            ROOT / "experiments/final_corpus_v1/allowlist.json",
            ROOT / "experiments/final_corpus_v1/exclusion-v2.json",
        )
        snapshot = offline_index.build_index(corpus, path)
        offline_index._persistent_client(path)._system.stop()
    pins = json.loads((ROOT / "experiments/final_corpus_v1/build-receipt-v3.json").read_bytes())[
        "native_pins"
    ]
    assert snapshot == pins["index_snapshot"]
    assert sha(path / MANIFEST_NAME) == pins["index_manifest_sha256"]
    return {
        "path": str(path),
        "snapshot_id": snapshot,
        **{
            k: v
            for k, v in pins.items()
            if k not in {"index_snapshot", "corpus_manifest_sha256", "corpus_manifest_note"}
        },
    }


@pytest.fixture
def registered(tmp_path, final_v3, multiple_holds):
    ledger, ledger_path, _ = multiple_holds
    disposable = tmp_path / "reader-index"
    shutil.copytree(final_v3["path"], disposable)
    final_v3 = {**final_v3, "path": str(disposable)}
    slots = []
    cases = []
    for index, count in enumerate((3, 2, 2)):
        case_id = f"synthetic-presentation-{index}"
        cases.append({"case_id": case_id, "revisions": list(range(1, count + 1))})
        for revision in range(1, count + 1):
            for attempt in (1, 2):
                context = ReasoningContext(
                    case_id=case_id,
                    case_revision=revision,
                    run_id=f"synthetic-presentation-{index}-r{revision}",
                    attempt_index=attempt,
                )
                slots.append(
                    ExperimentRequestSlot(
                        request_id=request_id_for(context),
                        run_id=context.run_id,
                        case_id=case_id,
                        case_revision=revision,
                        attempt=attempt,
                        input_token_reserve=32768,
                        amount_usd=get_price("gpt-4o-mini").cost(32768, 1024),
                    )
                )
    protocol = {
        "schema_version": 1,
        "profile_id": runtime.PROFILE_ID,
        "phase_label": "rehearsal",
        "session_id": "synthetic-presentation",
        "scope_id": "synthetic-presentation-scope",
        "model": "gpt-4o-mini",
        "max_scope_usd": "0.10",
        "recipe_sha256": delivery_recipe(profile_id=PREFILTER_DELIVERY_PROFILE_ID)["recipe_sha256"],
        "recipe_file_sha256": sha(ROOT / runtime.RECIPE_PATH),
        "vocabulary_file_sha256": sha(ROOT / runtime.VOCABULARY_PATH),
        "source_sha256": {name: sha(ROOT / name) for name in runtime.BOUND_SOURCE_FILES},
        "index": final_v3,
        "ledger_path": str(ledger_path),
        "tracker_path": str(tmp_path / "tracker.sqlite3"),
        "receipt_dir": str(tmp_path / "private-receipts"),
        "cases": cases,
        "slots": [asdict(slot) for slot in slots],
    }
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(protocol, default=str), encoding="utf-8")
    observed = ledger.quarantine_observation()
    ledger.authorize_quarantine_scope(
        authorization_id=protocol["scope_id"],
        authorization_ref="synthetic-presentation-user-authorized",
        expected_unknown_ids=observed.unknown_ids,
        expected_unknown_fingerprints=observed.unknown_fingerprints,
        expected_meta_sha256=observed.meta_sha256,
        expected_authorization_history_sha256=observed.authorization_history_sha256,
        protocol_sha256=sha(path),
        request_slots=tuple(slots),
        additional_cap_usd=Decimal("0.10"),
        allow_full_context=True,
    )
    values = ObservedValues(METIS_API_KEY=KEY, AGENT_REVIEWER_TOKEN=TOKEN)
    return ledger, path, protocol, values


def body(message, revision, turn, **updates):
    return {"message": message, "expected_revision": revision, "turn_id": turn, **updates}


def test_real_index_http_scoped_provider_and_retry_keep_old_holds(registered):
    ledger, path, protocol, values = registered
    historical = old_rows(Path(protocol["ledger_path"]))
    records = []
    app = runtime.configured_app(
        path,
        values,
        transport_factory=lambda: httpx.MockTransport(
            lambda request: authored_response(request, records)
        ),
    )
    owner = app.state.presentation_runtime
    try:
        with TestClient(app) as client, offline_network():
            payload = body(
                "Presentation arbitrary question: what does st.button return?", 0, "first"
            )
            endpoint = "/cases/synthetic-presentation-0/messages"
            result = client.post(endpoint, json=payload, headers=AUTH)
            assert result.status_code == 200, result.text
            view = result.json()
            assert view["case_revision"] == 1 and view["pending"] is not None
            assert records and "Presentation arbitrary question" in str(records[0]["payload"])
            assert records[0]["body"]["model"] == "gpt-4o-mini"
            assert (
                records[0]["payload"]["request"]["evidence"]["snapshot_id"]
                == protocol["index"]["snapshot_id"]
            )
            assert len(records[0]["payload"]["request"]["evidence"]["hits"]) <= 5
            count = len(records)
            assert client.post(endpoint, json=payload, headers=AUTH).status_code == 200
            assert len(records) == count
            assert client.post(endpoint, json=body("unauthorized", 1, "bad")).status_code == 401
            assert len(records) == count
            request_id = owner.observations[0]["request_id"]
            assert ledger.get(request_id).status == "settled"
            receipt = json.loads(next(Path(protocol["receipt_dir"]).glob("*.json")).read_bytes())
            assert receipt["canonical_plan"] is not None
            assert receipt["ledger"]["status"] == "settled"
            assert KEY not in json.dumps(receipt) and TOKEN not in json.dumps(receipt)
            assert app.state.presentation_binding["profile_id"] == "presentation_scoped_v1"
            assert owner.config.continuation_id == protocol["scope_id"]
    finally:
        owner.close()
    assert ledger.snapshot().halted and ledger.snapshot().limit_usd == Decimal("4.50")
    assert old_rows(Path(protocol["ledger_path"])) == historical


@pytest.mark.parametrize("field", ["recipe_file_sha256", "vocabulary_file_sha256", "recipe_sha256"])
def test_public_pin_changes_reject_before_credentials(registered, field):
    _, path, protocol, values = registered
    protocol[field] = "0" * 64
    path.write_text(json.dumps(protocol, default=str), encoding="utf-8")
    with pytest.raises(ValueError, match="PresentationConfigurationRejected"):
        runtime.PresentationRuntime(path, values)
    assert values.key_reads == []


def test_protocol_edit_after_registration_and_case_slot_are_rejected(registered):
    _, path, protocol, values = registered
    owner = runtime.PresentationRuntime(path, values)
    with pytest.raises(ValueError, match="PresentationSlotUnavailable"):
        owner.run_id_for("unregistered", 1)
    with pytest.raises(ValueError, match="PresentationSlotUnavailable"):
        owner.run_id_for(protocol["cases"][0]["case_id"], 4)
    protocol["session_id"] = "changed-after-registration"
    path.write_text(json.dumps(protocol, default=str), encoding="utf-8")
    with pytest.raises(ValueError, match="PresentationScopeUnavailable"):
        owner.for_case(CaseState(case_id="synthetic-presentation-0", case_revision=1))
    owner.close()


def test_closed_scope_blocks_before_credential_and_no_replacement_is_registered(registered):
    ledger, path, protocol, values = registered
    ledger.close_quarantine_scope(protocol["scope_id"])
    with pytest.raises(ValueError, match="PresentationScopeUnavailable"):
        runtime.PresentationRuntime(path, values)
    assert values.key_reads == []


def test_timeout_is_uncertain_and_blocks_further_attempts(registered):
    ledger, path, protocol, values = registered
    sends = []

    def timeout(request):
        sends.append(request)
        raise httpx.ReadTimeout("synthetic lost response")

    app = runtime.configured_app(
        path, values, transport_factory=lambda: httpx.MockTransport(timeout)
    )
    owner = app.state.presentation_runtime
    try:
        with TestClient(app) as client, offline_network():
            result = client.post(
                "/cases/synthetic-presentation-0/messages",
                json=body("Need help with st.button", 0, "timeout"),
                headers=AUTH,
            )
            assert result.status_code == 200
            assert len(sends) == 1
            assert owner.observations[0]["ledger"]["status"] == "uncertain"
            assert not ledger.quarantine_scope_status(protocol["scope_id"]).active
            assert (
                client.post(
                    "/cases/synthetic-presentation-0/messages",
                    json=body("Try another message", 1, "new"),
                    headers=AUTH,
                ).status_code
                == 200
            )
            assert len(sends) == 1
    finally:
        owner.close()
    assert ledger.snapshot().halted


def test_runtime_binding_mutation_fails_without_dispatch(registered):
    _, path, _, values = registered
    owner = runtime.PresentationRuntime(path, values)
    owner.binding["retrieval_profile"] = "native"
    with pytest.raises(ValueError, match="PresentationScopeUnavailable"):
        owner.for_case(CaseState(case_id="synthetic-presentation-0", case_revision=1))
    owner.close()


@pytest.mark.parametrize("kind", ["dotenv", "held_out", "symlink", "hardlink", "oversized"])
def test_protocol_path_rejected_before_any_payload_bytes(tmp_path, monkeypatch, kind):
    if kind == "dotenv":
        path = tmp_path / ".env"
    elif kind == "held_out":
        # Merely construct the protected path: do not stat/create/open it.
        path = ROOT / "data/evaluation/split-e1-v1/test/protocol.json"
    elif kind == "symlink":
        target = tmp_path / "target.txt"
        target.write_text("synthetic private payload")
        path = tmp_path / "protocol.json"
        path.symlink_to(target)
    elif kind == "hardlink":
        target = tmp_path / "target.txt"
        target.write_text("synthetic private payload")
        path = tmp_path / "protocol.json"
        path.hardlink_to(target)
    else:
        path = tmp_path / "protocol.json"
        with path.open("wb") as stream:
            stream.truncate(2_000_001)
    reads = []

    def forbidden(self):
        reads.append(self)
        raise AssertionError("Payload bytes must remain unopened")

    monkeypatch.setattr(Path, "read_bytes", forbidden)
    with pytest.raises(ValueError, match="PresentationConfigurationRejected"):
        runtime.read_protocol(path)
    assert reads == []


@pytest.mark.parametrize("secret", [KEY, TOKEN])
def test_private_secret_in_current_prompt_never_reaches_provider(registered, secret):
    ledger, path, protocol, values = registered
    sends = []
    app = runtime.configured_app(
        path,
        values,
        transport_factory=lambda: httpx.MockTransport(lambda request: sends.append(request)),
    )
    owner = app.state.presentation_runtime
    try:
        with TestClient(app) as client, offline_network():
            response = client.post(
                "/cases/synthetic-presentation-0/messages",
                json=body("Accidental credential paste: " + secret, 0, "secret"),
                headers=AUTH,
            )
            assert response.status_code == 200
            assert sends == owner.observations == []
            assert ledger.quarantine_scope_status(protocol["scope_id"]).consumed_requests == 0
            assert not list(Path(protocol["receipt_dir"]).glob("*.json"))
            assert KEY not in repr(owner.config)
            assert TOKEN not in repr(owner._secrets)
    finally:
        owner.close()
