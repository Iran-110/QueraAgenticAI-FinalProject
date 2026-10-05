import streamlit as st

st.title("Welcome to Streamlit! 👋")
st.write("This is a basic Streamlit app.")

name = st.text_input("What is your name?")
if name:
    st.success(f"Hello, {name}!")
