from uuid import uuid4

import streamlit as st

from agent_app import ui_client

SCENARIOS = {
    "ask": "Ask a follow-up question",
    "answer": "Answer with a source",
    "refine": "Search again, then answer",
    "escalate": "Escalate to a maintainer",
    "error": "Retrieval failure",
}
DECISIONS = {
    "ask": ("Follow-up question", "blue", ":material/help:"),
    "answer": ("Answer", "green", ":material/check_circle:"),
    "escalate": ("Escalation", "orange", ":material/priority_high:"),
}
STATUSES = {
    "new": ("New", "gray"),
    "awaiting_review": ("Awaiting maintainer review", "orange"),
    "awaiting_user": ("Waiting for the user", "blue"),
    "answer_sent": ("Answer sent, not confirmed solved", "green"),
    "escalated": ("Escalated", "red"),
    "open": ("Open", "gray"),
}


@st.cache_resource
def get_client() -> ui_client.BackendClient:
    return ui_client.make_client()


def new_case_id() -> str:
    return f"case-{uuid4().hex[:8]}"


if "case_id" not in st.session_state:
    st.session_state.case_id = new_case_id()
    st.session_state.editing = False
    st.session_state.notice = None

client = get_client()


def start_new_case() -> None:
    st.session_state.case_id = new_case_id()
    st.session_state.editing = False
    st.session_state.notice = None


def decide(proposal: dict, decision: str) -> None:
    edited = st.session_state.get("edited_draft") if decision == "edit" else None
    try:
        client.decide(
            st.session_state.case_id,
            proposal_id=proposal["proposal_id"],
            case_revision=proposal["case_revision"],
            decision=decision,
            edited_draft=edited,
        )
    except ui_client.BackendError as error:
        st.session_state.notice = ("error", str(error))
        return
    st.session_state.editing = False
    st.session_state.notice = {
        "approve": ("success", "Approved. The draft was released to the local case log."),
        "reject": ("info", "Rejected. Nothing was sent."),
        "edit": ("info", "Edited draft saved as a new proposal. It still needs approval."),
    }[decision]


def set_editing(value: bool) -> None:
    st.session_state.editing = value


def render_proposal(proposal: dict) -> None:
    label, color, icon = DECISIONS[proposal["decision"]]
    with st.container(border=True):
        st.subheader("Proposal awaiting review")
        with st.container(horizontal=True):
            st.badge(label, color=color, icon=icon)
            if proposal["edited"]:
                st.badge("Edited by maintainer", color="violet", icon=":material/edit:")
            if proposal["synthetic"]:
                st.badge("Synthetic", color="gray", icon=":material/science:")

        if proposal["stale"]:
            st.warning(
                "The case changed after this proposal was made, so it can no longer be "
                "approved. Send a new message to get a fresh proposal.",
                icon=":material/history:",
            )

        st.markdown("**Draft reply to the user**")
        with st.container(border=True):
            st.markdown(proposal["user_draft"] or "_No user-facing draft._")
        if proposal["missing_info"]:
            st.markdown("**Missing information:** " + ", ".join(proposal["missing_info"]))
        st.markdown("**Maintainer summary**")
        st.markdown(proposal["maintainer_summary"] or "_None._")

        st.markdown("**Evidence**")
        if not proposal["evidence"]:
            st.caption("No sources cited.")
        for item in proposal["evidence"]:
            title = item["source_span"] or item["chunk_id"]
            st.markdown(f"- [{title}]({item['source_url']}) · {item['source_type']}")
            st.caption(f"Claim: {item['claim']} — Excerpt: {item['excerpt']}")
        for warning in proposal["warnings"]:
            st.caption(f":material/warning: {warning}")

        with st.expander("Rationale and run details"):
            st.markdown(proposal["rationale"])
            with st.container(horizontal=True):
                st.metric("Model attempts", proposal["model_attempts"])
                st.metric("Retrieval rounds", proposal["retrieval_rounds"])
                st.metric("Steps", proposal["steps"])

        if proposal["stale"]:
            return
        if st.session_state.editing:
            with st.form("edit_form", border=False):
                st.text_area(
                    "Edited draft", value=proposal["user_draft"], height=150, key="edited_draft"
                )
                with st.container(horizontal=True):
                    st.form_submit_button(
                        "Save as new proposal",
                        type="primary",
                        icon=":material/save:",
                        on_click=decide,
                        args=(proposal, "edit"),
                    )
                    st.form_submit_button("Cancel", on_click=set_editing, args=(False,))
        else:
            with st.container(horizontal=True):
                st.button(
                    "Approve",
                    type="primary",
                    icon=":material/check:",
                    key="approve",
                    on_click=decide,
                    args=(proposal, "approve"),
                )
                st.button(
                    "Edit",
                    icon=":material/edit:",
                    key="edit",
                    on_click=set_editing,
                    args=(True,),
                )
                st.button(
                    "Reject",
                    icon=":material/close:",
                    key="reject",
                    on_click=decide,
                    args=(proposal, "reject"),
                )
        st.caption("Approval only updates this local case log. No external action is taken.")


with st.sidebar:
    st.subheader("Case")
    st.caption(f"Case ID: `{st.session_state.case_id}`")
    st.button("New case", icon=":material/add:", on_click=start_new_case, width="stretch")
    st.subheader("Offline scenario")
    st.selectbox(
        "Scripted agent behavior",
        list(SCENARIOS),
        format_func=SCENARIOS.get,
        key="scenario",
    )
    st.caption("Synthetic adapters: no retrieval index, no model calls, no cost.")

st.title("Streamlit support assistant")
st.caption(
    "Describe a Streamlit problem. The agent drafts an answer, a follow-up question or an "
    "escalation. A maintainer must approve each draft before the user sees it."
)

if st.session_state.notice:
    kind, text = st.session_state.notice
    getattr(st, kind)(text)
    st.session_state.notice = None

try:
    view = client.get_case(st.session_state.case_id)
except ui_client.BackendError as error:
    st.error(f"{error} Start it in a separate terminal:", icon=":material/cloud_off:")
    st.code("uv run uvicorn agent_app.api:app --host 127.0.0.1 --port 8000", language="bash")
    st.stop()

chat_col, case_col = st.columns(2, gap="large")

with chat_col:
    if not view["log"]:
        st.caption("No messages yet.")
    for entry in view["log"]:
        if entry["role"] == "system":
            st.caption(f":material/info: {entry['text']}")
            continue
        with st.chat_message(entry["role"]):
            st.markdown(entry["text"])
            if entry["role"] == "assistant":
                note = "Sent after maintainer approval"
                if entry.get("edited"):
                    note += " (edited)"
                st.caption(note)

with case_col:
    with st.container(border=True):
        status_label, status_color = STATUSES[view["status"]]
        st.subheader("Case status")
        with st.container(horizontal=True):
            st.badge(status_label, color=status_color)
            st.badge(f"Revision {view['case_revision']}", color="gray")
        active_facts = [fact for fact in view["facts"] if fact["status"] == "active"]
        st.markdown("**Known facts**")
        if active_facts:
            for fact in active_facts:
                st.markdown(f"- {fact['name']}: {fact['value']}")
        else:
            st.caption("None confirmed by the user.")
        st.markdown("**Unknowns**")
        st.caption(", ".join(view["unknowns"]) or "None recorded.")

    if view["pending"]:
        render_proposal(view["pending"])
    else:
        st.info("No proposal is awaiting review.", icon=":material/inbox:")

    if view["decisions"]:
        with st.expander(f"Review history ({len(view['decisions'])})"):
            for item in view["decisions"]:
                action = item.get("action") or {}
                st.markdown(f"- **{item['decision']}** · {action.get('decision', '?')} proposal")

if prompt := st.chat_input("Describe your Streamlit issue...", submit_mode="disable"):
    with chat_col, st.spinner("Running the agent..."):
        try:
            client.send_message(st.session_state.case_id, prompt, st.session_state.scenario)
        except ui_client.BackendError as error:
            st.session_state.notice = ("error", str(error))
    st.session_state.editing = False
    st.rerun()
