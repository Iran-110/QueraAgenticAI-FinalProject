import streamlit as st

st.set_page_config(layout="wide")

st.title("Advanced Layouts 🎨")

# Sidebar
st.sidebar.header("Settings")
theme = st.sidebar.selectbox("Choose a theme mode (simulated):", ["Light", "Dark"])
st.sidebar.write(f"You selected {theme} mode.")

# Columns
col1, col2, col3 = st.columns(3)

with col1:
    st.header("Column 1")
    st.info("This is the first column.")

with col2:
    st.header("Column 2")
    st.warning("This is the second column.")

with col3:
    st.header("Column 3")
    st.error("This is the third column.")

# Expander
with st.expander("Click to expand for more details!"):
    st.write("This content is hidden by default to save space on the main screen.")
    st.image("https://streamlit.io/images/brand/streamlit-logo-secondary-colormark-darktext.png", width=200)
