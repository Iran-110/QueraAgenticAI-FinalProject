from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
DOCS = {
    "Project definition": "QBC13_AgenticAI_FinalProject.md",
    "Project plan": "plan/plan.md",
    "Member 1 todo": "plan/member_1_todo.md",
    "Member 2 todo": "plan/member_2_todo.md",
    "Member 3 todo": "plan/member_3_todo.md",
    "Member 4 todo": "plan/member_4_todo.md",
}

choice = st.selectbox("Document", list(DOCS), key="doc_choice")
path = ROOT / DOCS[choice]
if path.exists():
    st.markdown(path.read_text(encoding="utf-8"))
else:
    st.warning(f"File not found: `{DOCS[choice]}`")
