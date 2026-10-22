import streamlit as st

st.set_page_config(
    page_title="Streamlit support assistant",
    page_icon=":material/support_agent:",
    layout="wide",
)

# Let mixed Persian/English text pick its own direction. Fonts come from
# .streamlit/config.toml; overriding them here would break Streamlit's icons.
st.html(
    """
    <style>
        div[data-testid="stMarkdownContainer"] :is(p, li, h1, h2, h3, h4, h5, h6, blockquote),
        div[data-testid="stText"] {
            unicode-bidi: plaintext;
            text-align: start;
        }
    </style>
    """
)

page = st.navigation(
    [
        st.Page(
            "app_pages/assistant.py",
            title="Support assistant",
            icon=":material/support_agent:",
            default=True,
        ),
        st.Page("app_pages/usage.py", title="Usage and cost", icon=":material/receipt_long:"),
        st.Page("app_pages/project_docs.py", title="Project docs", icon=":material/description:"),
    ]
)
page.run()
