"""Independent preflight counterexamples; temporary storage and GET mock only."""

import hashlib
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from test_budget_quarantine_scope import multiple_holds as multiple_holds
from test_presentation_healthcheck import CHECK
from test_presentation_healthcheck import artifacts as artifacts
from test_presentation_healthcheck import session as session
from test_presentation_release_watch import watched as watched
from test_presentation_runtime import final_v3 as final_v3
from test_presentation_runtime import registered as registered


def inspect_backend(session, *, health_change=None, failing_surface=None):
    """Keep real case projections valid while one independent surface regresses."""
    seen = []
    with TestClient(session[2]) as backend:

        def dispatch(request):
            seen.append(request)
            assert request.method == "GET"
            assert "authorization" not in request.headers
            if request.url.port in {8502, 8503}:
                if request.url.port == failing_surface:
                    return httpx.Response(
                        302, headers={"Location": "https://untrusted.invalid/private"}
                    )
                return httpx.Response(200, content=b"ok")
            response = backend.get(request.url.path)
            value = response.json()
            if request.url.path == "/health" and health_change is not None:
                health_change(value)
            return httpx.Response(response.status_code, json=value)

        report = CHECK.session_checks(
            "unused-protocol",
            api_url="http://127.0.0.1:8001",
            ui_url="http://127.0.0.1:8502",
            viewer_url="http://127.0.0.1:8503",
            transport=httpx.MockTransport(dispatch),
        )
    return report, seen


@pytest.mark.parametrize(
    "change",
    [
        lambda h: h.update(status="error"),
        lambda h: h.update(tracker_backend="in_memory"),
        lambda h: h["capabilities"].update(durable_reviews=False),
        lambda h: h["capabilities"].update(stable_event_ids=1),
        lambda h: h["capabilities"].update(reviewer_auth="basic"),
    ],
    ids=["unhealthy", "volatile-tracker", "non-durable", "integer-not-bool", "wrong-auth"],
)
def test_live_labels_do_not_override_broken_operational_capabilities(session, change):
    report, seen = inspect_backend(session, health_change=change)
    assert not report["ready"], "Labels alone must not attest durable operational readiness"
    assert seen and all(request.url.host == "127.0.0.1" for request in seen)


@pytest.mark.parametrize("surface", [8502, 8503], ids=["operator-ui", "judges-view"])
def test_non_api_surface_redirect_is_not_followed_or_accepted(session, surface):
    report, seen = inspect_backend(session, failing_surface=surface)
    assert not report["ready"]
    assert all(request.url.host == "127.0.0.1" for request in seen)
    assert seen[-1].url.port == surface


@pytest.mark.parametrize("malformed", ["x" * 13, dict.fromkeys(range(13), "wrong"), [None] * 13])
def test_matching_qa_hash_does_not_make_non_slide_content_a_valid_deck(artifacts, malformed):
    directory, qa_path = artifacts
    content = directory / CHECK.ARTIFACTS[2]
    content.write_text(json.dumps(malformed))
    qa = json.loads(qa_path.read_text())
    qa["output_sha256"][content.name] = hashlib.sha256(content.read_bytes()).hexdigest()
    qa_path.write_text(json.dumps(qa))
    assert not CHECK.artifact_checks(directory, qa_path)["verified"]


@pytest.mark.parametrize("missing", ["path", "digest"])
def test_partial_release_watch_pair_stops_before_ledger_or_http(session, monkeypatch, missing):
    def no_ledger(_):
        pytest.fail("Invalid public watch pair must fail before any ledger open")

    monkeypatch.setattr(CHECK, "BudgetLedger", no_ledger)
    report = CHECK.session_checks(
        "unused-protocol",
        api_url="http://127.0.0.1:8001",
        ui_url="http://127.0.0.1:8502",
        watch_path=None if missing == "path" else "/nonexistent/release-watch.json",
        watch_sha256=None if missing == "digest" else "a" * 64,
        transport=httpx.MockTransport(lambda _: pytest.fail("No HTTP before public rejection")),
    )
    assert not report["ready"]
    assert report["error_code"] == "PresentationSessionUnverified"


def test_changed_additive_source_is_rejected_before_ledger_or_http(watched, monkeypatch):
    _, protocol_path, _, _, source, watch_path, digest = watched
    dependency = source / "src/agent_app/tracker/sqlite_tracker.py"
    dependency.write_bytes(dependency.read_bytes() + b"\n# temporary independent review drift\n")

    def no_ledger(_):
        pytest.fail("Changed public source must fail before any ledger open")

    monkeypatch.setattr(CHECK, "BudgetLedger", no_ledger)
    report = CHECK.session_checks(
        protocol_path,
        api_url="http://127.0.0.1:8001",
        ui_url="http://127.0.0.1:8502",
        watch_path=watch_path,
        watch_sha256=digest,
        transport=httpx.MockTransport(lambda _: pytest.fail("No HTTP on source drift")),
    )
    assert not report["ready"]
    assert report["error_code"] == "PresentationSessionUnverified"


def test_public_report_does_not_echo_arbitrary_transport_body(session):
    marker = "synthetic-private-marker-do-not-display"
    report = CHECK.session_checks(
        "unused-protocol",
        api_url="http://127.0.0.1:8001",
        ui_url="http://127.0.0.1:8502",
        transport=httpx.MockTransport(lambda _: httpx.Response(503, text=marker)),
    )
    assert not report["ready"] and marker not in json.dumps(report)
    assert report["error_code"] == "PresentationSessionUnverified"


@pytest.mark.parametrize("name", ["reviewer-token.txt", "budget.sqlite3", ".env"])
def test_non_qa_private_role_is_rejected_before_any_payload_read(
    artifacts, tmp_path, monkeypatch, name
):
    directory, _ = artifacts
    private_standin = tmp_path / name
    private_standin.write_text("synthetic private marker, never an actual credential")
    original = type(private_standin).read_bytes
    reads = []

    def observe(path):
        if path == private_standin:
            reads.append(path.name)
        return original(path)

    monkeypatch.setattr(type(private_standin), "read_bytes", observe)
    assert not CHECK.artifact_checks(directory, private_standin)["verified"]
    assert not reads


@pytest.mark.parametrize("change", ["list", "string", "manual-null", "hashes-list"])
def test_malformed_qa_shape_returns_sanitized_report_instead_of_crashing(artifacts, change):
    directory, qa_path = artifacts
    qa = json.loads(qa_path.read_text())
    if change == "list":
        qa = []
    elif change == "string":
        qa = "synthetic invalid QA metadata"
    elif change == "manual-null":
        qa["manual_visual_review"] = None
    else:
        qa["output_sha256"] = []
    qa_path.write_text(json.dumps(qa))
    report = CHECK.artifact_checks(directory, qa_path)
    assert report == {
        "verified": False,
        "visual_review_replaced": False,
        "error_code": "PresentationArtifactsUnverified",
    }
