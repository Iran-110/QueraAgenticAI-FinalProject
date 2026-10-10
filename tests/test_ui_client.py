import httpx
import pytest

from agent_app import ui_client


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
