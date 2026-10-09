# TODO: Import LangGraph agent, state manager, and local tracker utilities
import streamlit as st
from streamlit_option_menu import option_menu
import os

st.set_page_config(
    page_title="Streamlit Support Assistant",
    page_icon="🤖",
    layout="wide"
)

# Apply Vazirmatn font and auto-RTL direction for Persian text support
st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Vazirmatn:wght@100..900&display=swap');
        
        html, body, [class*="st-"], .stApp {
            font-family: 'Vazirmatn', sans-serif !important;
        }
        
        * {
            font-family: 'Vazirmatn', sans-serif !important;
        }
        
        /* Auto-detect RTL/LTR direction based on paragraph content */
        .stTitle, .stHeader, .stSubheader,
        div[data-testid="stMarkdownContainer"] p,
        div[data-testid="stMarkdownContainer"] ul,
        div[data-testid="stMarkdownContainer"] ol,
        div[data-testid="stMarkdownContainer"] li,
        div[data-testid="stMarkdownContainer"] h1,
        div[data-testid="stMarkdownContainer"] h2,
        div[data-testid="stMarkdownContainer"] h3,
        div[data-testid="stMarkdownContainer"] h4,
        div[data-testid="stMarkdownContainer"] h5,
        div[data-testid="stMarkdownContainer"] h6,
        div[data-testid="stMarkdownContainer"] table,
        div[data-testid="stMarkdownContainer"] blockquote,
        div[data-testid="stText"] {
            unicode-bidi: plaintext;
            text-align: start;
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
    
    if "session_id" not in st.session_state:
        st.session_state.session_id = "session_1"

    # Call FastAPI to get state
    try:
        import requests
        state_response = requests.get(f"http://127.0.0.1:8000/state/{st.session_state.session_id}")
        if state_response.status_code == 200:
            agent_state = state_response.json()
            is_paused = agent_state.get("is_paused", False)
            proposed_action = agent_state.get("proposed_action")
            
            if is_paused and proposed_action:
                st.warning("⚠️ Action Requires Maintainer Approval")
                with st.expander("View Proposed Action", expanded=True):
                    if "reasoning" in proposed_action:
                        st.write(f"**Reasoning:** {proposed_action['reasoning']}")
                    st.json(proposed_action)
                
                # Edit functionality
                st.session_state.is_editing = st.session_state.get("is_editing", False)
                if st.session_state.is_editing:
                    edited_str = st.text_area("Edit Action (JSON format)", value=str(proposed_action), height=150)
                    col_save, col_cancel = st.columns(2)
                    with col_save:
                        if st.button("Save & Approve", type="primary", use_container_width=True):
                            import ast
                            try:
                                parsed_edit = ast.literal_eval(edited_str)
                                requests.post("http://127.0.0.1:8000/action", json={
                                    "session_id": st.session_state.session_id,
                                    "decision": "edit",
                                    "edited_action": parsed_edit
                                })
                                st.session_state.is_editing = False
                                st.rerun()
                            except Exception as e:
                                st.error(f"Invalid format: {e}")
                    with col_cancel:
                        if st.button("Cancel", use_container_width=True):
                            st.session_state.is_editing = False
                            st.rerun()
                else:
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        if st.button("Approve", use_container_width=True, type="primary"):
                            requests.post("http://127.0.0.1:8000/action", json={
                                "session_id": st.session_state.session_id,
                                "decision": "approve"
                            })
                            st.rerun()
                    with col2:
                        if st.button("Reject", use_container_width=True):
                            requests.post("http://127.0.0.1:8000/action", json={
                                "session_id": st.session_state.session_id,
                                "decision": "reject"
                            })
                            st.rerun()
                    with col3:
                        if st.button("Edit", use_container_width=True):
                            st.session_state.is_editing = True
                            st.rerun()
            else:
                st.success("System Status: Active (No pending approvals)")
                
        else:
            st.error("Failed to fetch state from backend.")
    except Exception as e:
        st.error(f"Backend not running: {e}")

    if st.button("Reset Session"):
        st.session_state.messages = []
        try:
            requests.get("http://127.0.0.1:8000/state/reset") # Mock endpoint for reset if needed
        except:
            pass
        st.rerun()
        
    st.divider()

    view = option_menu(
        menu_title="Navigation",
        options=[
            "Support Assistant", 
            "Project Definition", 
            "Project Plan", 
            "Member 1 Todo", 
            "Member 2 Todo", 
            "Member 3 Todo", 
            "Member 4 Todo"
        ],
        icons=["chat-text", "file-earmark-text", "calendar-event", "person-badge", "person-badge", "person-badge", "person-badge"],
        menu_icon="compass",
        default_index=0,
    )

# Main Area Rendering based on selected view
if view == "Support Assistant":
    st.title("Streamlit Support Assistant")
    st.markdown("Welcome to the Agentic AI Support Assistant for Streamlit issues.")

    # Initialize chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Display chat messages from history on app rerun
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            # Display sources if any
            if "sources" in message and message["sources"]:
                with st.expander("📚 Sources & Evidence", expanded=False):
                    for src in message["sources"]:
                        st.markdown(f"- [{src.get('title', 'Link')}]({src.get('url', '#')})")
            
            # Display action status if any
            if "action_status" in message and message["action_status"]:
                st.info(f"Status: {message['action_status']}")

    # React to user input
    if prompt := st.chat_input("Describe your Streamlit issue..."):
        # Display user message in chat message container
        st.chat_message("user").markdown(prompt)
        # Add user message to chat history
        st.session_state.messages.append({"role": "user", "content": prompt})

        # Display an empty placeholder for the assistant response while waiting
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            message_placeholder.markdown("Thinking...")
            
            try:
                import requests
                # Invoke FastAPI backend
                response = requests.post("http://127.0.0.1:8000/chat", json={
                    "session_id": st.session_state.session_id,
                    "message": prompt
                })
                
                sources = []
                action_status = ""
                
                if response.status_code == 200:
                    data = response.json()
                    bot_msg = data.get("message", "Error: No message returned")
                    sources = data.get("sources", [])
                    if data.get("status") == "paused":
                        action_status = "Awaiting Maintainer Approval"
                else:
                    bot_msg = f"Backend Error: {response.status_code}"
            except Exception as e:
                bot_msg = f"Failed to connect to backend: {e}"
                sources = []
                action_status = ""

            message_placeholder.markdown(bot_msg)
            if sources:
                with st.expander("📚 Sources & Evidence", expanded=False):
                    for src in sources:
                        st.markdown(f"- [{src.get('title', 'Link')}]({src.get('url', '#')})")
            if action_status:
                st.info(f"Status: {action_status}")
            
        # Add assistant response to chat history
        st.session_state.messages.append({
            "role": "assistant", 
            "content": bot_msg,
            "sources": sources,
            "action_status": action_status
        })
        
        # Rerun to update sidebar state (if it got paused)
        st.rerun()

elif view == "Project Definition":
    st.markdown(read_md("QBC13_AgenticAI_FinalProject.md"))

elif view == "Project Plan":
    st.markdown(read_md("plan/plan.md"))

elif view == "Member 1 Todo":
    st.markdown(read_md("plan/member_1_todo.md"))

elif view == "Member 2 Todo":
    st.markdown(read_md("plan/member_2_todo.md"))

elif view == "Member 3 Todo":
    st.markdown(read_md("plan/member_3_todo.md"))

elif view == "Member 4 Todo":
    st.markdown(read_md("plan/member_4_todo.md"))
