"""Preflight never substitutes money remaining for actual turn capacity."""

import hashlib
import importlib.util
import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from agent_app.persistent_api import create_app
from agent_app.tracker.sqlite_tracker import SQLiteCaseTracker

SPEC = importlib.util.spec_from_file_location(
    "presentation_healthcheck",
    Path(__file__).resolve().parents[1] / "scripts/presentation_healthcheck.py",
)
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)


def verified_index_observation():
    """Explicit fake only for GET/capacity controls; physical tests run a child."""
    return {
        "schema_version": 1,
        "verified": True,
        "blocked": [],
        "network_connect_attempts": 0,
        "client_close_available": False,
        "cleanup": "verifier_process_exit",
        "audit_scope": "child Python audit events; native calls not attested",
    }


@pytest.fixture
def artifacts(tmp_path):
    root = tmp_path / "public"
    root.mkdir()
    files = {
        CHECK.ARTIFACTS[0]: b"%PDF-1.4\nSynthetic signature-only artifact for hash binding.",
        CHECK.ARTIFACTS[1]: (
            '<html><style>.x:after{content:"A1"}</style>'
            + '<section class="slide"><p>محصول</p></section>' * 13
            + '<script>const hidden="A1";</script></html>'
        ).encode(),
        CHECK.ARTIFACTS[2]: json.dumps(
            [dict(title="محصول", body="", eyebrow="", foot="", cls="")] * 13
        ).encode(),
    }
    for name, raw in files.items():
        (root / name).write_bytes(raw)
    qa = tmp_path / "judges-v2-qa.json"
    qa.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "parent_content_review_accepted": True,
                "layout_overflow_pages": [],
                "manual_visual_review": {
                    "all13_actual_pdf_pages_poppler_rendered_and_inspected": True
                },
                "pdf_pages": 13,
                "output_sha256": {
                    name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()
                },
            }
        )
    )
    return root, qa


def test_artifact_hash_binding_does_not_claim_visual_semantics(artifacts):
    report = CHECK.artifact_checks(*artifacts)
    assert report["verified"] and not report["visual_review_replaced"]
    root, _ = artifacts
    (root / CHECK.ARTIFACTS[0]).write_bytes(b"%PDF-different-export")
    assert not CHECK.artifact_checks(*artifacts)["verified"]


def test_visible_test_prompts_refused_even_with_new_matching_hash(artifacts):
    root, qa = artifacts
    path = root / CHECK.ARTIFACTS[1]
    path.write_text(path.read_text().replace("محصول", "A1", 1))
    metadata = json.loads(qa.read_text())
    metadata["output_sha256"][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    qa.write_text(json.dumps(metadata))
    assert not CHECK.artifact_checks(*artifacts)["verified"]


def test_artifact_symlink_refused_without_reading_target(artifacts, monkeypatch):
    root, _ = artifacts
    file = root / CHECK.ARTIFACTS[0]
    target = file.with_name("private-document")
    file.rename(target)
    file.symlink_to(target)
    original = Path.read_bytes

    def read(path):
        assert path != file and path != target
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", read)
    assert not CHECK.artifact_checks(*artifacts)["verified"]


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1:8001",
        "http://example.org:8001",
        "http://user:secret@127.0.0.1:8001",
        "http://127.0.0.1:8001/health",
        "http://127.0.0.1:8001?token=x",
        "http://127.0.0.1:8001#unsafe",
        "http://127.0.0.1:invalid",
    ],
)
def test_external_or_credentialed_targets_refused(url):
    with pytest.raises(ValueError):
        CHECK.loopback_url(url)


@pytest.fixture
def session(tmp_path, monkeypatch):
    cases = [
        {"case_id": f"safe-{n}", "revisions": list(range(1, turns + 1))}
        for n, turns in enumerate((3, 2, 2))
    ]
    protocol = {
        "ledger_path": "never-opened",
        "scope_id": "safe-scope",
        "cases": cases,
        "index": {
            "path": "never-opened-index",
            "snapshot_id": "mock-snapshot",
            "index_manifest_sha256": "a" * 64,
        },
    }
    status = SimpleNamespace(
        active=True,
        protocol_sha256="a" * 64,
        max_requests=14,
        consumed_requests=0,
        remaining_usd=Decimal("0.09"),
    )
    slots = [
        SimpleNamespace(
            amount_usd=Decimal("0.006"),
            request_id=f"{case['case_id']}-r{revision}-a{attempt}",
            case_id=case["case_id"],
            case_revision=revision,
            attempt=attempt,
        )
        for case in cases
        for revision in case["revisions"]
        for attempt in (1, 2)
    ]
    monkeypatch.setattr(
        CHECK,
        "read_protocol",
        lambda _: (protocol, "a" * 64, slots),
    )
    ledger = SimpleNamespace(
        quarantine_scope_status=lambda _: status,
        snapshot=lambda: SimpleNamespace(halted=True),
        records={},
    )
    ledger.get = ledger.records.get
    monkeypatch.setattr(CHECK, "BudgetLedger", lambda _: ledger)
    # This fixture isolates GET/capacity controls. Independent runtime-review
    # tests below use the real verifier and disposable registered Chroma files.
    monkeypatch.setattr(
        CHECK,
        "_verify_physical_index",
        lambda *_: verified_index_observation(),
    )
    tracker = SQLiteCaseTracker(tmp_path / "state.sqlite3", reviewer_tokens={"tester": "t" * 32})
    app = create_app(
        tracker,
        reviewer_tokens={"tester": "t" * 32},
        require_message_auth=True,
        case_adapters=lambda *_: pytest.fail("A GET must never allocate reasoning adapters"),
        retrieval_label="local_chroma_hash",
        reasoning_label="metis_grounded_live",
    )
    return cases, status, app, ledger, slots


def observe(session, *, revisions=(0, 0, 0), redirect=False, cross_case=False):
    cases, _, app, _, _ = session
    seen = []
    with TestClient(app) as backend:

        def transport(request):
            seen.append(request)
            assert request.method == "GET" and "authorization" not in request.headers
            if redirect:
                return httpx.Response(302, headers={"Location": "https://external.invalid"})
            if request.url.port == 8502:
                return httpx.Response(200, content=b"ok")
            response = backend.get(request.url.path)
            value = response.json()
            if request.url.path.startswith("/cases/"):
                index = [c["case_id"] for c in cases].index(value["case_id"])
                value["case_revision"] = revisions[index]
                if cross_case:
                    value["case_id"] = "different-case"
            return httpx.Response(response.status_code, json=value)

        report = CHECK.session_checks(
            "not-opened",
            api_url="http://127.0.0.1:8001",
            ui_url="http://127.0.0.1:8502",
            transport=httpx.MockTransport(transport),
        )
    return report, seen


def test_fresh_pool_get_only_and_no_credential(session):
    report, requests = observe(session)
    assert report["ready"] and report["remaining_message_turns"] == 7
    assert len(requests) == 5
    assert report["provider_probe"] == "not_performed"


def test_unused_second_attempts_do_not_create_new_turns(session):
    session[1].consumed_requests = 8
    for slot in [s for s in session[4] if s.attempt == 1] + [session[4][1]]:
        session[3].records[slot.request_id] = SimpleNamespace(case_revision=slot.case_revision)
    report, _ = observe(session, revisions=(3, 2, 2))
    assert report["scope_active"] and report["remaining_usd"] == "0.09"
    assert not report["ready"] and report["remaining_message_turns"] == 0
    assert report["error_code"] == "PresentationTurnPoolExhausted"


def test_reset_tracker_cannot_reuse_already_spent_revision(session):
    slot = session[4][0]
    session[3].records[slot.request_id] = SimpleNamespace(case_revision=slot.case_revision)
    session[1].consumed_requests = 1
    report, requests = observe(session)
    assert not report["ready"] and len(requests) == 2
    assert report["error_code"] == "PresentationTrackerBehindLedger"


def test_cross_case_payload_is_not_screened_as_ready(session):
    report, _ = observe(session, cross_case=True)
    assert not report["ready"]


def test_redirect_never_follows_external_location(session):
    report, requests = observe(session, redirect=True)
    assert not report["ready"] and len(requests) == 1


def test_inactive_scope_prevents_any_http(session):
    session[1].active = False
    report, requests = observe(session)
    assert not report["ready"] and not requests


def test_physical_index_probe_finishes_before_any_ledger_or_http_access(session, monkeypatch):
    order = []
    original_ledger = CHECK.BudgetLedger

    def index(*_):
        order.append("verify-index-child-completed")
        return verified_index_observation()

    def ledger(path):
        order.append("open-ledger")
        return original_ledger(path)

    monkeypatch.setattr(CHECK, "_verify_physical_index", index)
    monkeypatch.setattr(CHECK, "BudgetLedger", ledger)
    report, requests = observe(session)
    assert report["ready"] and requests
    assert order == ["verify-index-child-completed", "open-ledger"]
    assert report["index_probe"] == verified_index_observation()


def test_failed_physical_probe_stops_before_budget_or_http(session, monkeypatch):
    def invalid(*_):
        raise ValueError("Synthetic native validation failure")

    monkeypatch.setattr(CHECK, "_verify_physical_index", invalid)
    monkeypatch.setattr(CHECK, "BudgetLedger", lambda *_: pytest.fail("Opened before probe passed"))
    report, requests = observe(session)
    assert not report["ready"] and not requests
