# TODO: Import LangGraph agent, state manager, and local tracker utilities
import streamlit as st
import os

st.set_page_config(
    page_title="Streamlit Support Assistant",
    page_icon="🤖",
    layout="wide"
)

# Apply Vazirmatn font for Persian text support
st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Vazirmatn:wght@100..900&display=swap');
        
        html, body, [class*="st-"], .stApp {
            font-family: 'Vazirmatn', sans-serif !important;
        }
        
        * {
            font-family: 'Vazirmatn', sans-serif !important;
        }
    </style>
""", unsafe_allow_html=True)

def read_md(file_path):
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    return f"*File not found: {file_path}*"

# Sidebar Navigation and Controls
with st.sidebar:
    st.header("Agent Controls")
    st.info("This is where Human-in-the-Loop (HITL) approval actions will appear.")
    
    # TODO: Check if the LangGraph agent is paused at an `interrupt_before` node
    # TODO: Display the proposed action and provide "Approve", "Reject", and "Edit" buttons
    # TODO: Resume the agent execution with the human's feedback

    if st.button("Reset Session"):
        st.session_state.messages = []
        st.rerun()
        
    st.divider()

    st.header("Navigation")
    view = st.radio(
        "Select View",
        [
            "💬 Support Assistant", 
            "📋 Project Definition", 
            "📅 Project Plan", 
            "👤 Member 1 Todo", 
            "👤 Member 2 Todo", 
            "👤 Member 3 Todo", 
            "👤 Member 4 Todo"
        ]
    )

# Main Area Rendering based on selected view
if view == "💬 Support Assistant":
    st.title("Streamlit Support Assistant")
    st.markdown("Welcome to the Agentic AI Support Assistant for Streamlit issues.")

    # TODO: Connect to local SQLite/JSON tracker to load existing issue state and history
    # Initialize chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Display chat messages from history on app rerun
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # React to user input
    if prompt := st.chat_input("Describe your Streamlit issue..."):
        # Display user message in chat message container
        st.chat_message("user").markdown(prompt)
        # Add user message to chat history
        st.session_state.messages.append({"role": "user", "content": prompt})

        # TODO: Invoke the LangGraph agent with the user's prompt and current state
        # TODO: Stream the agent's intermediate steps (thought process, tool calls) to the UI
        # Placeholder for agent response
        response = f"Agent is processing your issue: {prompt}\n\n*Note: LangGraph integration is pending.*"
        
        # Display assistant response in chat message container
        with st.chat_message("assistant"):
            st.markdown(response)
        # Add assistant response to chat history
        st.session_state.messages.append({"role": "assistant", "content": response})

elif view == "📋 Project Definition":
    st.markdown(read_md("QBC13_AgenticAI_FinalProject.md"))

elif view == "📅 Project Plan":
    st.markdown(read_md("plan/plan.md"))

elif view == "👤 Member 1 Todo":
    st.markdown(read_md("plan/member_1_todo.md"))

elif view == "👤 Member 2 Todo":
    st.markdown(read_md("plan/member_2_todo.md"))

elif view == "👤 Member 3 Todo":
    st.markdown(read_md("plan/member_3_todo.md"))

elif view == "👤 Member 4 Todo":
    st.markdown(read_md("plan/member_4_todo.md"))
