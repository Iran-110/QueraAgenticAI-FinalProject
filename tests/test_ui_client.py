import json
from copy import deepcopy
from dataclasses import FrozenInstanceError

import httpx
import pytest

from agent_app import api, ui_client
from agent_app.contracts import CaseState, Fact
from agent_app.orchestration.engine import SupportEngine
from agent_app.orchestration.handoff import ReasoningCapture, build_handoff


def client_for(handler):
    return ui_client.BackendClient(
        httpx.Client(base_url="http://backend", transport=httpx.MockTransport(handler))
    )


def test_reported_facts_keeps_withdrawals_and_skips_blank_rows():
    rows = [
        {"name": " streamlit_version ", "value": " 1.50.0 ", "withdraw": False},
        {"name": "python_version", "value": "", "withdraw": True},
        {"name": "", "value": "orphan", "withdraw": False},
        {"name": "browser", "value": "", "withdraw": False},
    ]
    assert ui_client.reported_facts(rows) == [
        {"name": "streamlit_version", "value": "1.50.0"},
        {"name": "python_version", "value": None},
    ]


def test_reply_event_carries_no_structured_updates():
    event = ui_client.new_event(
        "1.50.0", expected_revision=2, scenario="ask", reply_to_proposal_id="p-1"
    )
    assert set(event) == {
        "message",
        "scenario",
        "turn_id",
        "expected_revision",
        "reply_to_proposal_id",
    }


def test_new_events_get_distinct_ids():
    first = ui_client.new_event("a", expected_revision=0, scenario="ask")
    second = ui_client.new_event("a", expected_revision=0, scenario="ask")
    assert first["turn_id"] != second["turn_id"]


def test_known_code_maps_to_readable_text():
    client = client_for(lambda request: httpx.Response(409, json={"detail": "StaleRevision"}))
    with pytest.raises(ui_client.BackendError) as caught:
        client.get_case("c")
    assert caught.value.code == "StaleRevision"
    assert not caught.value.retryable
    assert "case changed" in str(caught.value)


@pytest.mark.parametrize(
    ("handler", "retryable"),
    [
        (lambda request: httpx.Response(500, text="boom"), True),
        (lambda request: httpx.Response(404, text="missing"), False),
    ],
)
def test_retryable_only_when_delivery_is_uncertain(handler, retryable):
    with pytest.raises(ui_client.BackendError) as caught:
        client_for(handler).get_case("c")
    assert caught.value.retryable is retryable


def test_network_failure_is_retryable():
    def fail(request):
        raise httpx.ConnectError("down")

    with pytest.raises(ui_client.BackendError) as caught:
        client_for(fail).get_case("c")
    assert caught.value.retryable


def durable_health(**extra):
    return {
        "status": "ok",
        "mode": "synthetic_offline_sqlite",
        "tracker_backend": "sqlite_case_tracker",
        "capabilities": {
            "stable_event_ids": True,
            "durable_reviews": True,
            "reviewer_auth": "bearer",
        },
        "retrieval_label": "scripted",
        "reasoning_label": "scripted",
        "quality_claim": False,
        **extra,
    }


def proposal(version=None):
    ports = api._adapters("answer")
    capture = ReasoningCapture(ports.reasoner)
    result = SupportEngine(ports.retriever, capture, snapshot_id=ports.snapshot_id).run(
        CaseState(
            case_id="c",
            case_revision=1,
            facts=(
                Fact(
                    name="streamlit_version",
                    value=version,
                    source_ref="user:initial",
                    turn_id="initial",
                ),
            )
            if version is not None
            else (),
        ),
        "How can I keep a counter?",
        run_id="p-1",
    )
    return {**api._proposal(build_handoff(result, capture.last), result), "stale": False}


def empty_view(case_id="c"):
    return {
        "case_id": case_id,
        "case_revision": 1,
        "status": "open",
        "log": [],
        "facts": [],
        "unknowns": [],
        "checks_performed": [],
        "evidence_refs": [],
        "decisions": [],
        "pending": None,
        "awaiting_reply": None,
        "intake": None,
    }


@pytest.mark.parametrize("retrieval", ["scripted", "local_chroma_hash"])
def test_health_discovers_durable_protocol_and_retrieval_label(retrieval):
    client = client_for(
        lambda _request: httpx.Response(200, json=durable_health(retrieval_label=retrieval))
    )
    capabilities = client.discover_capabilities()
    assert capabilities.durable_reviews
    assert capabilities.retrieval_label == retrieval


def test_known_legacy_health_preserves_memory_protocol():
    client = client_for(
        lambda _request: httpx.Response(200, json={"status": "ok", "mode": "synthetic_offline"})
    )
    assert not client.discover_capabilities().durable_reviews


@pytest.mark.parametrize(
    "health",
    [
        {"status": "ok", "mode": "unknown"},
        {"status": "ok", "mode": "synthetic_offline_sqlite"},
        durable_health(
            capabilities={
                "stable_event_ids": True,
                "durable_reviews": False,
                "reviewer_auth": "bearer",
            }
        ),
        durable_health(
            capabilities={"stable_event_ids": 1, "durable_reviews": True, "reviewer_auth": "bearer"}
        ),
        durable_health(retrieval_label=["private"]),
        durable_health(quality_claim=True),
    ],
)
def test_unknown_or_incomplete_health_fails_closed(health):
    client = client_for(lambda _request: httpx.Response(200, json=health))
    with pytest.raises(ui_client.BackendError) as caught:
        client.discover_capabilities()
    assert caught.value.code == "BackendCapabilitiesInvalid"
    assert "private" not in str(caught.value)


@pytest.mark.parametrize("decision", ["approve", "reject", "edit"])
def test_durable_review_immutable_payload_and_private_header(decision):
    sent = []
    token = "synthetic-client-maintainer-credential"

    def handler(request):
        sent.append(request)
        if request.url.path == "/health":
            return httpx.Response(200, json=durable_health())
        payload = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                **empty_view(),
                "review": {
                    "case_id": "c",
                    "review_id": payload["review_id"],
                    "proposal_id": payload["proposal_id"],
                    "revision": payload["case_revision"],
                    "decision": payload["decision"],
                    "reviewer_id": "synthetic-maintainer",
                    "status": "open",
                    "action_id": None,
                    "new_proposal_id": None,
                    "replayed": sum(item.method == "POST" for item in sent) > 1,
                },
            },
        )

    client = ui_client.BackendClient(
        httpx.Client(base_url="http://backend", transport=httpx.MockTransport(handler)),
        reviewer_token=token,
    )
    displayed = proposal()
    original_digest = displayed["review_handoff"]["handoff_sha256"]
    operation = client.prepare_review("c", displayed, decision, edited_draft="Original edit.")
    payload = operation.payload()
    displayed["proposal_id"] = "p-new"
    displayed["review_handoff"]["handoff_sha256"] = "b" * 64
    detached = operation.payload()
    detached["edited_draft"] = "Later widget edit."
    with pytest.raises(FrozenInstanceError):
        operation.case_id = "another"
    first = client.send_review(operation)
    second = client.send_review(operation)
    assert not first["review"]["replayed"] and second["review"]["replayed"]
    posts = [item for item in sent if item.method == "POST"]
    assert posts[0].content == posts[1].content
    assert json.loads(posts[0].content) == payload
    assert payload["expected_handoff_sha256"] == original_digest
    assert payload["review_id"].startswith("ui-review-")
    assert payload["edited_draft"] == ("Original edit." if decision == "edit" else None)
    assert all("authorization" not in item.headers for item in sent if item.method == "GET")
    assert posts[0].headers["authorization"] == f"Bearer {token}"
    assert token not in operation.body_json and token not in repr(operation)
    assert "reviewer_id" not in payload and "reviewer_token" not in payload


def test_missing_trusted_credential_rejects_review_before_post():
    sent = []
    client = client_for(
        lambda request: sent.append(request) or httpx.Response(200, json=durable_health())
    )
    with pytest.raises(ui_client.BackendError) as caught:
        client.prepare_review("c", proposal(), "approve")
    assert caught.value.code == "ReviewerUnauthorized"
    assert [request.method for request in sent] == ["GET"]


@pytest.mark.parametrize(
    "detail", ["TrackerUnavailable", "RunOutcomeUnavailable", "private-server-data"]
)
def test_structured_503_keeps_delivery_uncertain_and_sanitizes_unknown_detail(detail):
    client = client_for(lambda _request: httpx.Response(503, json={"detail": detail}))
    with pytest.raises(ui_client.BackendError) as caught:
        client.send_event("c", {"message": "a"})
    assert caught.value.retryable
    assert "private-server-data" not in str(caught.value)
    assert caught.value.code == (detail if detail in ui_client.ERROR_TEXT else None)


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="private-corrupt-success"),
        httpx.Response(200, json=["private-corrupt-success"]),
        httpx.Response(200, json={"private-corrupt-success": "content"}),
        httpx.Response(200, json={**empty_view(), "case_id": "foreign-case"}),
        httpx.Response(200, json={**empty_view(), "log": [{"role": "private-invalid-role"}]}),
    ],
)
def test_unreadable_success_is_sanitized_and_retryable(response):
    with pytest.raises(ui_client.BackendError) as caught:
        client_for(lambda _request: response).send_event("c", {"message": "a"})
    assert caught.value.code == "BackendResponseInvalid"
    assert caught.value.retryable
    assert "private" not in str(caught.value)


@pytest.mark.parametrize(
    "body", [["private-detail"], {"detail": "private-detail"}, {"detail": {"private": "detail"}}]
)
def test_unknown_error_shapes_never_export_backend_text(body):
    with pytest.raises(ui_client.BackendError) as caught:
        client_for(lambda _request: httpx.Response(409, json=body)).get_case("c")
    assert not caught.value.retryable
    assert "private" not in str(caught.value)


def test_network_failure_does_not_display_private_base_url():
    def fail(_request):
        raise httpx.ReadTimeout("private-transport-diagnostic")

    client = ui_client.BackendClient(
        httpx.Client(
            base_url="http://private-user:private-password@backend",
            transport=httpx.MockTransport(fail),
        )
    )
    with pytest.raises(ui_client.BackendError) as caught:
        client.get_case("c")
    assert "private" not in str(caught.value)
    assert caught.value.retryable


def test_make_client_loads_only_explicit_environment_credential(monkeypatch):
    monkeypatch.setenv("AGENT_REVIEWER_TOKEN", "synthetic-env-maintainer")
    monkeypatch.setenv("AGENT_API_URL", "http://backend")
    client = ui_client.make_client()
    assert client.reviewer_configured
    assert "synthetic-env-maintainer" not in repr(client)
    client._http.close()


@pytest.mark.parametrize("entrypoint", ["get_case", "prepare_review"])
@pytest.mark.parametrize(
    "field,changed",
    [
        (("user_draft",), "private-unreviewed-draft"),
        (("decision",), "escalate"),
        (("analysis", "evidence_links", 0, "claim"), "private-unreviewed-claim"),
        (("review_handoff", "evidence", "hits", 0, "excerpt"), "private-unreviewed-source"),
        (("review_handoff", "source_inventory", 0, "version_scope"), "exact_metadata_match"),
        (("evidence", 0, "source_url"), "https://private-unreviewed.example/docs"),
        (("warnings",), ["private-unreviewed-warning"]),
        (("case_revision",), 2),
    ],
)
def test_displayed_proposal_must_match_the_complete_handoff_before_review(
    entrypoint, field, changed
):
    displayed = deepcopy(proposal())
    selected = displayed
    for key in field[:-1]:
        selected = selected[key]
    selected[field[-1]] = changed
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path == "/health":
            return httpx.Response(200, json=durable_health())
        return httpx.Response(200, json={**empty_view(), "pending": displayed})

    client = ui_client.BackendClient(
        httpx.Client(base_url="http://backend", transport=httpx.MockTransport(handler)),
        reviewer_token="synthetic-projection-token",
    )
    with pytest.raises(ui_client.BackendError) as caught:
        if entrypoint == "get_case":
            client.get_case("c")
        else:
            client.prepare_review("c", displayed, "approve")
    assert caught.value.code == "BackendResponseInvalid"
    assert caught.value.retryable
    assert "private" not in str(caught.value)
    assert all(request.method == "GET" for request in requests)


def test_review_refreshes_health_before_sending_saved_operation_or_credential():
    health = durable_health()
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=health)

    client = ui_client.BackendClient(
        httpx.Client(base_url="http://backend", transport=httpx.MockTransport(handler)),
        reviewer_token="synthetic-protocol-token",
    )
    operation = client.prepare_review("c", proposal(), "approve")
    original = operation.body_json
    health = {"status": "ok", "mode": "synthetic_offline"}
    with pytest.raises(ui_client.BackendError) as caught:
        client.send_review(operation)
    assert caught.value.code == "BackendCapabilityMismatch"
    assert operation.body_json == original
    assert all(
        request.method == "GET" and "authorization" not in request.headers for request in requests
    )


def test_unknown_operational_diagnostics_are_replaced_with_fixed_text():
    client = client_for(
        lambda _request: httpx.Response(
            200,
            json={
                **empty_view(),
                "log": [{"role": "system", "text": "private-server-exception"}],
                "run_outcome": {
                    "status": "core_stopped",
                    "error_code": "private-server-exception",
                    "result": None,
                },
            },
        )
    )
    view = client.get_case("c")
    assert view["run_outcome"]["error_code"] == "RunOutcomeUnavailable"
    assert "private" not in view["log"][0]["text"]


@pytest.mark.parametrize(
    "extra",
    [
        {"run_outcome": {"status": "private-status", "error_code": None, "result": None}},
        {"run_outcome": {"status": "core_stopped", "error_code": [], "result": None}},
        {"actions": [{"proposal_id": "p", "private": "diagnostic"}]},
        {"review": {"private": "diagnostic"}},
        {"intake": {"turn_id": "private-bad-receipt"}},
    ],
)
def test_malformed_operational_projection_fails_closed_without_diagnostics(extra):
    client = client_for(lambda _request: httpx.Response(200, json={**empty_view(), **extra}))
    with pytest.raises(ui_client.BackendError) as caught:
        client.get_case("c")
    assert caught.value.code == "BackendResponseInvalid"
    assert "private" not in str(caught.value)


@pytest.mark.parametrize("field", ["facts", "unknowns", "checks_performed", "evidence_refs"])
def test_current_case_display_must_match_the_handoff_reviewed_environment(field):
    pending = proposal(version="1.50.0")
    view = {
        **empty_view(),
        "pending": pending,
        "facts": deepcopy(pending["review_handoff"]["case"]["facts"]),
    }
    if field == "facts":
        view["facts"][0]["value"] = "1.49.1"
    else:
        view[field] = ["private-tampered-environment"]
    client = client_for(lambda _request: httpx.Response(200, json=view))
    with pytest.raises(ui_client.BackendError) as caught:
        client.get_case("c")
    assert caught.value.code == "BackendResponseInvalid"
    assert "private" not in str(caught.value)


@pytest.mark.parametrize("revision,flag", [(1, True), (2, False), (0, True)])
def test_stale_marker_is_derived_from_the_displayed_case_revision(revision, flag):
    pending = proposal()
    pending["stale"] = flag
    client = client_for(
        lambda _request: httpx.Response(
            200,
            json={
                **empty_view(),
                "pending": pending,
                "case_revision": revision,
            },
        )
    )
    with pytest.raises(ui_client.BackendError) as caught:
        client.get_case("c")
    assert caught.value.code == "BackendResponseInvalid"


def test_legitimate_stale_history_can_be_viewed_but_cannot_be_prepared_for_approval():
    pending = proposal(version="1.50.0")
    pending["stale"] = True
    latest_facts = deepcopy(pending["review_handoff"]["case"]["facts"])
    latest_facts[0]["value"] = "1.49.1"

    def handler(request):
        if request.url.path == "/health":
            return httpx.Response(200, json=durable_health())
        return httpx.Response(
            200,
            json={**empty_view(), "pending": pending, "case_revision": 2, "facts": latest_facts},
        )

    client = ui_client.BackendClient(
        httpx.Client(base_url="http://backend", transport=httpx.MockTransport(handler)),
        reviewer_token="synthetic-stale-token",
    )
    assert client.get_case("c")["pending"]["stale"]
    with pytest.raises(ui_client.BackendError) as caught:
        client.prepare_review("c", pending, "approve")
    assert caught.value.code == "StaleRevision"
