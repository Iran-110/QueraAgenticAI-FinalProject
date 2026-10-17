"""Optional GET-only judges view; the normal operator UI is unchanged."""

import os
import unicodedata
from itertools import count

import streamlit as st

from agent_app import ui_client
from agent_app.presentation_view import PresentationViewer, source_link

st.set_page_config(page_title="دستیار پشتیبانی | نمای ارائه", page_icon="🔎", layout="wide")
st.html(
    """<style>
    .stApp :is(h1,h2,h3,h4,p,li) {direction:rtl;text-align:right;}
    [data-testid="stText"] {direction:rtl;text-align:right;unicode-bidi:plaintext;}
    [data-testid="stCode"] {direction:ltr;text-align:left;}
    [class*="st-key-plain-ltr"] :is(div,p,pre) {direction:ltr;text-align:left;unicode-bidi:plaintext;}
    [class*="st-key-plain-rtl"] :is(div,p,pre) {direction:rtl;text-align:right;unicode-bidi:plaintext;}
    .block-container {padding-top:4rem;max-width:1400px;}
    @media(max-width:800px) {
      [data-testid="stHorizontalBlock"] {flex-direction:column;}
      [data-testid="stColumn"] {width:100%;flex:1 1 100%;}
    }
    </style>"""
)


@st.cache_resource(scope="session", on_release=lambda client: client.close())
def viewer(base_url, cases):
    return PresentationViewer(base_url, cases)


DECISIONS = {"ask": "یک سؤال تکمیلی", "answer": "پاسخ همراه منبع", "escalate": "ارجاع به نگهدارنده"}
STATUSES = {
    "new": "پروندهٔ تازه",
    "open": "باز",
    "awaiting_review": "منتظر بررسی انسانی",
    "awaiting_user": "منتظر پاسخ کاربر",
    "answer_sent": "پاسخ تأیید شده؛ حل مسئله هنوز تأیید نشده",
    "escalated": "ارجاع ثبت شده",
}
SCOPES = {
    "exact_metadata_match": "نسخهٔ ثبت‌شدهٔ منبع با نسخهٔ کاربر برابر است",
    "historical_or_other_version": "منبع متعلق به نسخهٔ دیگر است",
    "unconfirmed": "تطابق نسخهٔ این منبع تأیید نشده",
}


_plain_ids = count()


def plain(value):
    value = value or "—"
    first = next(
        (
            unicodedata.bidirectional(char)
            for char in value
            if unicodedata.bidirectional(char) in {"L", "R", "AL"}
        ),
        "R",
    )
    direction = "ltr" if first == "L" else "rtl"
    with st.container(key=f"plain-{direction}-{next(_plain_ids)}"):
        st.text(value)


try:
    cases = ui_client.presentation_cases()
    if cases is None:
        raise ValueError
    client = viewer(os.environ.get("AGENT_API_URL", "http://127.0.0.1:8001"), cases)
except (ValueError, ui_client.BackendError):
    st.error("این نما باید با نشانی backend محلی و فهرست مشخص پرونده‌ها اجرا شود.")
    st.stop()

st.title("دستیار پشتیبانی Streamlit")
st.caption("اول اطلاعات روشن می‌شود؛ بعد پیشنهاد مستند ساخته و انسان آن را بررسی می‌کند.")
with st.expander("انتخاب پرونده و به‌روزرسانی", expanded=False):
    st.subheader("پرونده‌ها")
    case_id = st.selectbox("پروندهٔ انتخاب‌شده", cases, key="judge_case_id")
    st.button("به‌روزرسانی نما", icon=":material/refresh:")
    st.caption("این صفحه فقط می‌خواند؛ پیام، تأیید یا درخواست مدل ارسال نمی‌کند.")
    st.caption("برای گفت‌وگو و تأیید، از صفحهٔ اصلی اپراتور استفاده کنید.")

try:
    snapshot = client.load(case_id)
except (ValueError, ui_client.BackendError):
    st.error("خواندن وضعیت معتبر پرونده ممکن نشد. هیچ درخواستی برای مدل ارسال نشده است.")
    st.stop()
view = snapshot.view

if snapshot.origin == "recorded_rehearsal":
    st.info("پروندهٔ ثبت‌شده در اجرای پذیرش · نمایش ضبط‌شده؛ اجرای تازهٔ مدل نیست.")
else:
    st.caption(
        "خواندن وضعیت از API · مسیر live پیکربندی شده"
        if snapshot.capabilities.reasoning_label == "metis_grounded_live"
        else "خواندن وضعیت از API · مسیر آفلاین"
    )
with st.container(border=True):
    st.subheader(STATUSES[view["status"]])
    st.caption(f"Revision {view['case_revision']} · {view['case_id']}")
    if snapshot.active_user_facts:
        st.markdown("**اطلاعات فعلی که کاربر گفته است**")
        for fact in snapshot.active_user_facts:
            plain(f"{fact['name']}: {fact['value']}")
    else:
        st.info("هنوز اطلاعاتی به‌صورت تأییدشده از کاربر ثبت نشده است.")
    retired = [fact for fact in view["facts"] if fact["status"] == "superseded"]
    if retired:
        with st.expander("اطلاعات قبلی که با اصلاح کاربر کنار گذاشته شدند"):
            for fact in retired:
                plain(f"{fact['name']}: {fact['value']}")


def show_conversation():
    st.subheader("گفت‌وگوی ثبت‌شده")
    if not view["log"]:
        st.caption("هنوز پیامی در این پرونده ثبت نشده است.")
    for entry in view["log"]:
        if entry["role"] == "system":
            with st.expander("وضعیت اجرای قبلی"):
                plain(entry["text"])
            continue
        with st.chat_message(entry["role"]):
            if entry["role"] == "assistant":
                st.caption("پیامی که پس از تأیید نگهدارنده ثبت شده؛ تأیید حل مسئله نیست.")
            if len(entry["text"]) > 800:
                st.caption(f"متن کامل بدون بازنویسی · {len(entry['text'])} نویسه")
                with st.expander("نمایش متن کامل پیام"):
                    plain(entry["text"])
            else:
                plain(entry["text"])


def show_proposal():
    pending = view["pending"]
    approved_reference = None
    if pending is None:
        approved = [
            review
            for review in view["decisions"]
            if review.get("receipt", {}).get("decision") == "approve"
        ]
        if approved:
            approved_reference = approved[-1]["action"]["review_handoff"]
            # Display the approved artifact as history. Do not turn it into a new
            # pending proposal, or reinterpret its source scope for the current case.
            pending = {
                **approved_reference["analysis"],
                "analysis": approved_reference["analysis"],
                "review_handoff": approved_reference,
                "stale": False,
            }
    if pending is not None:
        with st.container(border=True):
            st.subheader(
                "آخرین پیام ثبت‌شده پس از تأیید نگهدارنده"
                if approved_reference is not None
                else "پیشنهاد فعلی ایجنت؛ هنوز برای کاربر ارسال نشده"
            )
            if approved_reference is not None:
                st.caption(
                    "این بخش سابقهٔ تأیید است، پیشنهاد تازه نیست. "
                    f"Revision {approved_reference['case']['case_revision']}"
                )
            st.markdown(f"**{DECISIONS[pending['decision']]}**")
            st.caption("این عنوان خلاصهٔ وضعیت رابط است؛ متن پاسخ مدل را بازنویسی نمی‌کند.")
            if pending["stale"]:
                st.warning("این پیشنهاد مربوط به وضعیت قدیمی پرونده است و قابل تأیید نیست.")
            if pending["next_question"]:
                plain(pending["next_question"])
            st.caption(f"متن پیشنهادی کامل: {len(pending['user_draft'])} نویسه")
            with st.expander("متن کامل پیشنهادی؛ دقیقاً همان متن صفحهٔ بررسی"):
                plain(pending["user_draft"])
            with st.expander("یادداشت کامل برای نگهدارنده"):
                plain(pending["maintainer_summary"])
            selected = {link["chunk_id"] for link in pending["analysis"]["evidence_links"]}
            handoff = pending["review_handoff"]
            hits = handoff["evidence"]["hits"]
            inventory = {item["chunk_id"]: item for item in handoff["source_inventory"]}
            st.markdown(f"**منابع: {len(hits)} منبع رسیده؛ {len(selected)} منبع انتخاب شده**")
            st.caption("وجود منبع یا نقل‌قول دقیق، به‌تنهایی درستی و مفید بودن پاسخ را ثابت نمی‌کند.")
            for number, hit in enumerate(hits, 1):
                chosen = hit["chunk_id"] in selected
                label = f"منبع {number} · " + ("انتخاب‌شده" if chosen else "انتخاب‌نشده")
                if chosen:
                    st.caption(label + " · بخشی از منبع؛ برای متن کامل باز کنید")
                    plain(hit["excerpt"][:180])
                with st.expander(label, expanded=False):
                    plain(SCOPES[inventory[hit["chunk_id"]]["version_scope"]])
                    link = source_link(hit["source_url"])
                    if link is not None:
                        st.link_button("باز کردن منبع", link)
                    else:
                        st.caption("نشانی این منبع فقط به‌صورت متن نمایش داده می‌شود.")
                        plain(hit["source_url"])
                    plain(hit["source_id"])
                    plain(hit["excerpt"])
            with st.expander("اطلاعات فنی و محدودیت‌های این نما"):
                st.caption(
                    "Backend mode فقط پیکربندی مسیر را نشان می‌دهد. رسید خصوصی provider شاهد اجرای واقعی هر درخواست است."
                )
                plain(
                    f"reasoning={snapshot.capabilities.reasoning_label}\n"
                    f"retrieval={snapshot.capabilities.retrieval_label}\n"
                    f"legacy synthetic label={pending.get('synthetic', 'not recorded in approved artifact')}"
                )
                st.caption("برچسب legacy بالا معیار تشخیص مدل واقعی از fixture نیست.")
                st.caption(
                    "این نمای اختیاری بخشی از binding مالی backend نیست؛ فقط وضعیت را می‌خواند."
                )
                st.json(handoff)
    else:
        st.info("در حال حاضر پیشنهادی منتظر بررسی نیست.")


conversation_panel, proposal_panel = st.columns([1.1, 1], gap="large")
with conversation_panel:
    show_conversation()
with proposal_panel:
    show_proposal()

st.caption(
    "حل شدن واقعی مسئله و کیفیت پاسخ به بررسی مستقل نیاز دارد. این نما هیچ امتیاز کیفیتی تولید نمی‌کند."
)
