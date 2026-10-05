import streamlit as st

st.title("Session State in Streamlit 🔄")
st.write("Streamlit re-runs the entire script from top to bottom every time you interact with a widget. "
         "To remember variables across re-runs, we use `st.session_state`.")

# Initialize the counter in session state
if "counter" not in st.session_state:
    st.session_state.counter = 0

st.write(f"Current count: **{st.session_state.counter}**")

col1, col2 = st.columns(2)

with col1:
    if st.button("Increment ➕"):
        st.session_state.counter += 1
        st.rerun() # Force a rerun to update the UI immediately

with col2:
    if st.button("Reset 🗑️"):
        st.session_state.counter = 0
        st.rerun()
