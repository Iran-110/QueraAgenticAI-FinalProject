"""Model calls and their cost, read from the user backend's ledger."""

import os
from decimal import Decimal

import httpx
import streamlit as st

from agent_app.ui_client import DEFAULT_BASE_URL

st.title("Usage and cost", anchor=False)
st.caption(
    "Every live model call is reserved on the user ledger before it is sent. "
    "Costs are the provider-reported amounts recorded after each call."
)


@st.cache_data(ttl=10, show_spinner=False)
def load_usage(base_url: str, token: str | None) -> tuple[dict | None, str | None]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        response = httpx.get(f"{base_url}/usage", headers=headers, timeout=10)
    except httpx.HTTPError:
        return None, "Cannot reach the backend."
    if response.status_code == 404:
        return None, "This backend does not report usage. Start the user live backend."
    if response.status_code == 401:
        return None, "Maintainer authorization is missing or was rejected."
    if not response.is_success:
        return None, f"The backend could not read usage (HTTP {response.status_code})."
    try:
        return response.json(), None
    except ValueError:
        return None, "The backend returned an unreadable response."


if st.button("Refresh", icon=":material/refresh:"):
    load_usage.clear()

usage, error = load_usage(
    os.environ.get("AGENT_API_URL", DEFAULT_BASE_URL), os.environ.get("AGENT_REVIEWER_TOKEN")
)
if error:
    st.error(error, icon=":material/error:")
    st.stop()

if usage["halted"]:
    st.warning(
        "The user ledger is halted after an uncertain provider result. "
        "No new calls are sent until a person reconciles it.",
        icon=":material/block:",
    )
if Decimal(usage["uncertain_usd"]) > 0:
    st.warning(
        f"${usage['uncertain_usd']} is held for calls whose cost the provider did not confirm.",
        icon=":material/help:",
    )

with st.container(horizontal=True):
    st.metric("Total cost", f"${Decimal(usage['spent_usd']):.6f}", border=True)
    st.metric(
        "Remaining",
        f"${Decimal(usage['available_usd']):.4f}",
        border=True,
        help=f"Of a ${usage['limit_usd']} limit, after reserved and uncertain amounts.",
    )
    st.metric("Model calls", usage["call_count"], border=True)

calls = usage["calls"]
if not calls:
    st.info("No model calls yet.", icon=":material/info:")
    st.stop()

if usage["call_count"] > len(calls):
    st.caption(f"Showing the latest {len(calls)} of {usage['call_count']} calls.")

st.dataframe(
    [
        {
            **call,
            "cost_usd": None if call["cost_usd"] is None else float(call["cost_usd"]),
            "reserved_usd": float(call["reserved_usd"]),
        }
        for call in calls
    ],
    column_order=(
        "started_at",
        "case_id",
        "attempt",
        "status",
        "input_tokens",
        "output_tokens",
        "cost_usd",
        "model",
        "error_code",
    ),
    column_config={
        "started_at": st.column_config.DatetimeColumn("Time", format="YYYY-MM-DD HH:mm:ss"),
        "case_id": "Case",
        "attempt": st.column_config.NumberColumn("Attempt", format="%d"),
        "status": "Status",
        "input_tokens": st.column_config.NumberColumn("Input tokens", format="%d"),
        "output_tokens": st.column_config.NumberColumn("Output tokens", format="%d"),
        "cost_usd": st.column_config.NumberColumn("Cost", format="$%.6f"),
        "model": "Model",
        "error_code": "Error",
    },
    hide_index=True,
    alt="Model calls with time, case, status, tokens and cost",
)
