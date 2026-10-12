from uuid import uuid4

import streamlit as st

from agent_app import ui_client
from agent_app.orchestration.intake import STREAMLIT_VERSION_QUESTION

SCENARIOS = {
    "ask": "Ask a follow-up question",
    "ask_version": "Ask for the Streamlit version",
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
VERSION_SCOPES = {
    "exact_metadata_match": ("Version matches", "green"),
    "historical_or_other_version": ("Other version", "orange"),
    "unconfirmed": ("Version unconfirmed", "gray"),
}
FACT_ROW_COUNT = 3


@st.cache_resource(scope="session")
def get_client() -> ui_client.BackendClient:
    return ui_client.make_client()


def new_case_id() -> str:
    return f"case-{uuid4().hex[:8]}"


def reset_view_state() -> None:
    st.session_state.active_case_id = st.session_state.case_id
    st.session_state.editing = False
    st.session_state.notice = None
    # Rejected forms retain their widgets. Their values belong to the old case,
    # so switching starts a fresh generation instead of sending those corrections
    # under the newly selected case ID.
    if "form_gen" in st.session_state:
        st.session_state.form_gen += 1
    st.session_state.pop("version_reply", None)
    st.session_state.pop("edited_draft", None)


if "cases" not in st.session_state:
    first = new_case_id()
    # Only cases opened in this browser session are listed; the API holds others too.
    st.session_state.cases = [first]
    st.session_state.case_id = first
    # An unsent event stays with the case it was built for, so switching is safe.
    st.session_state.unsent = {}
    reset_view_state()

if "case_id" not in st.session_state:
    # Widget state is removed when health failure stops before the switcher is
    # rendered. Its disappearance must not reset the browser's cases or retries.
    st.session_state.case_id = st.session_state.get("active_case_id", st.session_state.cases[0])
st.session_state.setdefault("active_case_id", st.session_state.case_id)

# Old browser sessions may predate durable review support. Requests are public
# immutable operations; credentials remain only in the session-scoped client.
st.session_state.setdefault("unsent_reviews", {})

client = get_client()
try:
    capabilities = client.discover_capabilities()
except ui_client.BackendError as error:
    st.error(str(error), icon=":material/cloud_off:")
    st.caption("Start a supported backend in a separate terminal.")
    st.code("uv run uvicorn agent_app.api:app --host 127.0.0.1 --port 8000", language="bash")
    st.stop()


def start_new_case() -> None:
    case_id = new_case_id()
    st.session_state.cases.append(case_id)
    st.session_state.case_id = case_id
    reset_view_state()


def unsent_event() -> dict | None:
    return st.session_state.unsent.get(st.session_state.case_id)


def unsent_review() -> ui_client.ReviewOperation | None:
    return st.session_state.unsent_reviews.get(st.session_state.case_id)


def deliver(event: dict) -> bool:
    """Keep the identical event when its delivery or acknowledgment is uncertain."""
    case_id = st.session_state.case_id
    try:
        view = client.send_event(case_id, event)
    except ui_client.BackendError as error:
        if error.retryable:
            st.session_state.unsent[case_id] = event
        else:
            st.session_state.unsent.pop(case_id, None)
        st.session_state.notice = ("error", str(error))
        return False
    st.session_state.unsent.pop(case_id, None)
    st.session_state.editing = False
    if view["intake"] and view["intake"]["replayed"]:
        st.session_state.notice = (
            "info",
            "Already received. The original message receipt is confirmed; showing the current case.",
        )
    return True


def retry_unsent() -> None:
    deliver(unsent_event())


def submit_reply(revision: int, proposal_id: str) -> None:
    reply = st.session_state.version_reply.strip()
    if not reply:
        return
    event = ui_client.new_event(
        reply,
        expected_revision=revision,
        scenario=st.session_state.scenario,
        reply_to_proposal_id=proposal_id,
    )
    if deliver(event):
        st.session_state.version_reply = ""


def decide(proposal: dict, decision: str) -> None:
    if unsent_review():
        return  # An uncertain operation must be resolved before a fresh review.
    edited = st.session_state.get("edited_draft") if decision == "edit" else None
    try:
        operation = client.prepare_review(
            st.session_state.case_id,
            proposal,
            decision,
            edited_draft=edited,
        )
    except ui_client.BackendError as error:
        st.session_state.notice = ("error", str(error))
        return
    if operation.durable:
        # Save before submitting: the action may commit while its reply is lost.
        st.session_state.unsent_reviews[operation.case_id] = operation
    deliver_review(operation)


def deliver_review(operation: ui_client.ReviewOperation) -> None:
    try:
        view = client.send_review(operation)
    except ui_client.BackendError as error:
        if operation.durable:
            st.session_state.editing = False
        if not error.retryable and error.code not in {
            "ReviewerUnauthorized",
            "BackendCapabilityMismatch",
            "BackendCapabilitiesInvalid",
        }:
            st.session_state.unsent_reviews.pop(operation.case_id, None)
        st.session_state.notice = ("error", str(error))
        return
    st.session_state.unsent_reviews.pop(operation.case_id, None)
    st.session_state.editing = False
    if operation.durable and view["review"]["replayed"]:
        st.session_state.notice = (
            "info",
            "The original review is confirmed. Showing the current case; no new action was created.",
        )
        return
    st.session_state.notice = {
        "approve": ("success", "Approved. The draft was released to the local case log."),
        "reject": ("info", "Rejected. Nothing was sent."),
        "edit": ("info", "Edited draft saved as a new proposal. It still needs approval."),
    }[operation.payload()["decision"]]


def retry_review() -> None:
    operation = unsent_review()
    if operation is not None:
        deliver_review(operation)


def set_editing(value: bool) -> None:
    st.session_state.editing = value


def bullet_list(label: str, items: list[str], empty: str = "None.") -> None:
    st.markdown(f"**{label}**")
    if items:
        st.markdown("\n".join(f"- {item}" for item in items))
    else:
        st.caption(empty)


def render_case(view: dict) -> None:
    with st.container(border=True):
        status_label, status_color = STATUSES[view["status"]]
        st.subheader("Case status")
        with st.container(horizontal=True):
            st.badge(status_label, color=status_color)
            st.badge(f"Revision {view['case_revision']}", color="gray")
            if capabilities.durable_reviews:
                st.badge("SQLite · durable", color="gray")
        outcome = view.get("run_outcome")
        if outcome and outcome.get("status") != "proposal_staged":
            status = outcome.get("status")
            if status == "interrupted":
                st.warning(
                    "This update is recorded without a completed outcome; a run may still be "
                    "in progress. Retrying confirms its receipt and does not resume the agent. "
                    "After checking the current run, a new update can start another run."
                )
            else:
                st.caption(
                    f"Recorded run outcome: {status} · {outcome.get('error_code') or 'none'}"
                )
        st.markdown("**Facts**")
        if view["facts"]:
            st.dataframe(
                [
                    {
                        "Name": fact["name"],
                        "Value": fact["value"],
                        "Status": fact["status"],
                        "From": fact["provenance_kind"],
                        "Turn": fact["turn_id"],
                    }
                    for fact in view["facts"]
                ],
                hide_index=True,
                alt="Case facts with their status and provenance",
            )
            st.caption("Superseded facts stay visible as history; only active ones count.")
        else:
            st.caption("No facts reported yet. Free text alone is not a confirmed fact.")
        bullet_list("Unknowns", view["unknowns"], "None recorded.")
        bullet_list("Checks performed", view["checks_performed"], "None recorded.")
        intake = view["intake"]
        if intake:
            with st.expander("Last accepted update"):
                st.markdown(
                    f"- Event `{intake['turn_id']}` committed revision "
                    f"{intake['committed_revision']} ({intake['preparation']})\n"
                    f"- Changed facts: {', '.join(intake['changed_fact_names']) or 'none'}\n"
                    f"- Context changed: {'yes' if intake['context_changed'] else 'no'}\n"
                    f"- Invalidated checks: {', '.join(intake['invalidated_checks']) or 'none'}"
                )


def render_sources(proposal: dict) -> None:
    handoff = proposal["review_handoff"]
    bundle = handoff["evidence"]
    cited: dict[str, list[str]] = {}
    for link in proposal["analysis"]["evidence_links"]:
        cited.setdefault(link["chunk_id"], []).append(link["claim"])
    scopes = {entry["chunk_id"]: entry["version_scope"] for entry in handoff["source_inventory"]}
    st.markdown(f"**Sources ({len(bundle['hits'])} supplied, {len(cited)} cited)**")
    if not bundle["hits"]:
        st.caption("No sources were supplied to the agent.")
    for hit in bundle["hits"]:
        scope_label, scope_color = VERSION_SCOPES[scopes.get(hit["chunk_id"], "unconfirmed")]
        with st.container(border=True):
            title = hit["source_span"] or hit["chunk_id"]
            st.markdown(f"[{title}]({hit['source_url']}) · {hit['source_type']}")
            with st.container(horizontal=True):
                if hit["chunk_id"] in cited:
                    st.badge("Cited", color="green", icon=":material/format_quote:")
                else:
                    st.badge("Not cited", color="gray")
                st.badge(scope_label, color=scope_color)
            if hit["chunk_id"] in cited:
                for claim in cited[hit["chunk_id"]]:
                    st.caption(f"Claim: {claim}")
            st.caption(f"Excerpt: {hit['excerpt']}")
            meta = [f"Chunk `{hit['chunk_id']}`"]
            if hit["source_commit"]:
                meta.append(f"commit `{hit['source_commit']}`")
            if hit["applicable_versions"]:
                meta.append("versions " + ", ".join(hit["applicable_versions"]))
            st.caption(" · ".join(meta))
    for warning in proposal["warnings"]:
        st.caption(f":material/warning: {warning}")
    if bundle["queries_used"]:
        st.caption(
            f"Retrieval round {bundle['retrieval_round']}, queries: "
            + "; ".join(bundle["queries_used"])
        )


def render_gaps(proposal: dict) -> None:
    grounded = proposal["review_handoff"].get("grounded_request")
    if not grounded:
        return
    if grounded["gaps"]:
        st.markdown("**Gaps**")
        for gap in grounded["gaps"]:
            kind = "User information" if gap["kind"] == "user" else "Source coverage"
            text = f"- **{kind}: {gap['name']}**: {gap['description']} ({gap['necessity']})"
            if gap["question"]:
                text += f"  \n  Question: {gap['question']}"
            st.markdown(text)
    if grounded["conflict_groups"]:
        bullet_list(
            "Conflicting sources",
            [", ".join(f"`{chunk}`" for chunk in group) for group in grounded["conflict_groups"]],
        )


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
        if proposal["next_question"] and proposal["next_question"] != proposal["user_draft"]:
            st.markdown(f"**Next question:** {proposal['next_question']}")
        bullet_list("Missing information", proposal["missing_info"])
        st.markdown("**Maintainer summary**")
        st.markdown(proposal["maintainer_summary"] or "_None._")
        render_gaps(proposal)
        render_sources(proposal)

        with st.expander("Rationale, suggestions and run details"):
            st.markdown(proposal["rationale"])
            bullet_list("Suggested checks", proposal["checks_suggested"])
            bullet_list("Requested searches", proposal["retrieval_queries"])
            bullet_list(
                "Facts proposed by the agent (not applied to the case)",
                [f"{fact['name']}: {fact['value']}" for fact in proposal["facts_delta"]],
            )
            with st.container(horizontal=True):
                st.metric("Model attempts", proposal["model_attempts"])
                st.metric("Retrieval rounds", proposal["retrieval_rounds"])
                st.metric("Steps", proposal["steps"])
            st.caption(
                f"Proposal `{proposal['proposal_id']}` · revision {proposal['case_revision']} · "
                f"handoff `{proposal['review_handoff']['handoff_sha256'][:12]}`"
            )

        if proposal["stale"]:
            return
        review_blocked = bool(unsent_review()) or (
            capabilities.durable_reviews and not client.reviewer_configured
        )
        if review_blocked:
            if unsent_review():
                st.caption("Confirm the pending review receipt before making a new review.")
            else:
                st.warning(
                    "Maintainer authorization is not configured. Chat and corrections remain available."
                )
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
                        disabled=review_blocked,
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
                    disabled=review_blocked,
                )
                st.button(
                    "Edit",
                    icon=":material/edit:",
                    key="edit",
                    on_click=set_editing,
                    args=(True,),
                    disabled=review_blocked,
                )
                st.button(
                    "Reject",
                    icon=":material/close:",
                    key="reject",
                    on_click=decide,
                    args=(proposal, "reject"),
                    disabled=review_blocked,
                )
        st.caption("Approval only updates this local case log. No external action is taken.")


def render_reply(view: dict) -> None:
    awaiting = view["awaiting_reply"]
    if not awaiting:
        return
    question = awaiting["question"]
    canonical = question["next_question"] == STREAMLIT_VERSION_QUESTION.question and question[
        "missing_info"
    ] == [STREAMLIT_VERSION_QUESTION.name]
    if not canonical:
        st.caption(
            ":material/info: Answers to this question are recorded as text only. "
            "Use **Report facts and corrections** to confirm values."
        )
        return
    with st.form("reply_form", border=True):
        st.markdown(f"**Reply to:** {question['next_question']}")
        st.text_input("Streamlit version", placeholder="1.50.0", key="version_reply")
        st.form_submit_button(
            "Send reply",
            type="primary",
            icon=":material/reply:",
            on_click=submit_reply,
            args=(view["case_revision"], awaiting["proposal_id"]),
        )


def render_update_form(view: dict) -> None:
    # Widgets are keyed by generation so a successful send starts a blank form,
    # while a rejected one keeps what the user typed.
    gen = st.session_state.setdefault("form_gen", 0)
    with st.expander("Report facts and corrections", icon=":material/edit_note:"):
        with st.form(f"update_form_{gen}", border=False):
            message = st.text_area(
                "Message",
                placeholder="Correction: the deployed app uses Streamlit 1.49.1.",
                key=f"update_message_{gen}",
            )
            st.markdown("**Facts**")
            st.caption(
                "Reusing a fact name replaces its value. Tick withdraw to mark it unknown again."
            )
            rows = []
            for index in range(FACT_ROW_COUNT):
                name_col, value_col, withdraw_col = st.columns(
                    [2, 2, 1], vertical_alignment="bottom"
                )
                rows.append(
                    {
                        "name": name_col.text_input(
                            "Name",
                            placeholder="streamlit_version" if index == 0 else "",
                            key=f"fact_name_{index}_{gen}",
                            label_visibility="visible" if index == 0 else "collapsed",
                        ),
                        "value": value_col.text_input(
                            "Value",
                            placeholder="1.49.1" if index == 0 else "",
                            key=f"fact_value_{index}_{gen}",
                            label_visibility="visible" if index == 0 else "collapsed",
                        ),
                        "withdraw": withdraw_col.checkbox(
                            "Withdraw", key=f"fact_withdraw_{index}_{gen}"
                        ),
                    }
                )
            checks = st.text_area("Checks performed (one per line)", key=f"update_checks_{gen}")
            unknowns = st.text_area("New unknowns (one per line)", key=f"update_unknowns_{gen}")
            context_changed = st.toggle(
                "Different environment",
                key=f"update_context_{gen}",
                help="Earlier unconfirmed facts and checks no longer apply.",
            )
            submitted = st.form_submit_button("Send update", type="primary", icon=":material/send:")
    if not submitted:
        return
    if not message.strip():
        st.session_state.notice = ("warning", "Describe the update in the message field.")
        st.rerun()
    event = ui_client.new_event(
        message.strip(),
        expected_revision=view["case_revision"],
        scenario=st.session_state.scenario,
        reported_facts=ui_client.reported_facts(rows),
        checks_performed=ui_client.lines(checks),
        unknowns=ui_client.lines(unknowns),
        context_changed=context_changed,
    )
    if deliver(event):
        st.session_state.form_gen = gen + 1
    st.rerun()


with st.sidebar:
    st.subheader("Cases")
    statuses = {}
    for case_id in st.session_state.cases:
        try:
            statuses[case_id] = client.get_case(case_id)["status"]
        except ui_client.BackendError:
            pass  # The main area explains a missing backend.
    st.selectbox(
        "Active case",
        st.session_state.cases,
        # Streamlit deserializes formatted option text. A status change must not
        # turn an old label into a case ID and reset another form's callback.
        # Status belongs in the case panel and review counter.
        key="case_id",
        on_change=reset_view_state,
        help="Cases opened in this browser session. Each keeps its own state and proposals.",
    )
    waiting = sum(status == "awaiting_review" for status in statuses.values())
    if waiting:
        st.caption(f":material/pending_actions: {waiting} case(s) awaiting review")
    st.button("New case", icon=":material/add:", on_click=start_new_case, width="stretch")
    if capabilities.reasoning_label != "scripted":
        st.subheader("GroundedPlan pilot")
        st.session_state.scenario = "ask"
        if capabilities.reasoning_label == "grounded_fake_gateway":
            st.caption(
                "GroundedPlan · mocked provider · offline · zero API cost · no model quality result."
            )
        else:
            st.caption(
                "GroundedPlan · bounded live development probe · human approval required · "
                "not final evaluation."
            )
        st.caption(
            "Retrieval: "
            + (
                "local indexed docs"
                if capabilities.retrieval_label == "local_chroma_hash"
                else "fixture"
            )
        )
    elif capabilities.retrieval_label == "local_chroma_hash":
        st.subheader("Offline indexed pilot")
        st.session_state.scenario = "ask"
        st.caption(
            "Local indexed docs · scripted ask-then-escalate policy · offline · no model quality result."
        )
    else:
        st.subheader("Offline scenario")
        st.selectbox(
            "Scripted agent behavior",
            list(SCENARIOS),
            format_func=SCENARIOS.get,
            key="scenario",
        )
        st.caption("Synthetic adapters: no retrieval index, no model calls, no cost.")
    if capabilities.durable_reviews:
        st.caption(
            "SQLite tracker · maintainer authorization "
            + ("configured" if client.reviewer_configured else "missing")
        )

st.title("Streamlit support assistant")
st.caption(
    "Describe a Streamlit problem. The agent drafts an answer, a follow-up question or an "
    "escalation. A maintainer must approve each draft before the user sees it."
)

if st.session_state.notice:
    kind, text = st.session_state.notice
    getattr(st, kind)(text)
    st.session_state.notice = None

if unsent_event():
    with st.container(horizontal=True, vertical_alignment="center"):
        st.warning(
            "Your last message is unconfirmed; it may already be recorded.",
            icon=":material/sync_problem:",
        )
        st.button("Retry sending", icon=":material/refresh:", on_click=retry_unsent)

if operation := unsent_review():
    payload = operation.payload()
    st.warning(
        "This review is unconfirmed; it may already be recorded.", icon=":material/sync_problem:"
    )
    st.caption(
        f"Original {payload['decision']} · proposal `{payload['proposal_id']}` · "
        f"revision {payload['case_revision']}. Retry confirms this operation, not a newer proposal."
    )
    st.button(
        "Retry review",
        icon=":material/refresh:",
        on_click=retry_review,
        disabled=not capabilities.durable_reviews or not client.reviewer_configured,
    )

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
    render_reply(view)

with case_col:
    render_case(view)
    if view["pending"]:
        render_proposal(view["pending"])
    else:
        st.info("No proposal is awaiting review.", icon=":material/inbox:")

    if view["decisions"]:
        with st.expander(f"Review history ({len(view['decisions'])})"):
            for item in view["decisions"]:
                if capabilities.durable_reviews:
                    receipt = item["receipt"]
                    st.markdown(
                        f"- **{item['decision']}** · proposal `{receipt['proposal_id']}` · revision {receipt['revision']}"
                    )
                else:
                    action = item.get("action") or {}
                    st.markdown(
                        f"- **{item['decision']}** · {action.get('decision', '?')} proposal"
                    )

# Full width so the fact editor's columns stay readable.
render_update_form(view)

if prompt := st.chat_input("Describe your Streamlit issue...", submit_mode="disable"):
    with chat_col, st.spinner("Running the agent..."):
        deliver(
            ui_client.new_event(
                prompt,
                expected_revision=view["case_revision"],
                scenario=st.session_state.scenario,
            )
        )
    st.rerun()
