import asyncio
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from agent_app.tracker.dummy_tracker import tracker

app = FastAPI(title="Agentic AI Backend")


class ChatRequest(BaseModel):
    session_id: str
    message: str


class DecisionRequest(BaseModel):
    session_id: str
    decision: str  # 'approve', 'reject', 'edit'
    edited_action: dict[str, Any] | None = None


@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    """
    Receives a message and simulates the agent processing it.
    If it requires a tool, it might pause for HITL.
    """
    # Simulate processing delay
    await asyncio.sleep(1)

    # Mocking a condition where the agent decides to propose an action
    if "fix" in request.message.lower() or "code" in request.message.lower():
        tracker.pause_for_approval(
            request.session_id,
            proposed_action={
                "tool": "edit_file",
                "arguments": {"file": "app.py", "content": "st.session_state['count'] = 0"},
                "reasoning": "The user asked for a code fix, so I'm proposing an edit to app.py"
            },
        )
        return {
            "status": "paused", 
            "message": "I found a potential fix, but it requires maintainer approval.",
            "sources": [{"title": "Streamlit docs on session state", "url": "https://docs.streamlit.io/library/api-reference/session-state"}],
            "action_type": "propose_fix"
        }

    return {
        "status": "completed",
        "message": f"Based on the documentation, here is how you can resolve the issue with '{request.message}'.",
        "sources": [
            {"title": "Related GitHub Issue #1234", "url": "https://github.com/streamlit/streamlit/issues/1234"},
            {"title": "Streamlit API Reference", "url": "https://docs.streamlit.io/library/api-reference"}
        ],
        "action_type": "answer"
    }


@app.get("/state/{session_id}")
async def get_state(session_id: str):
    """
    Returns the current paused state for the UI sidebar.
    """
    state = tracker.get_session_state(session_id)
    return state


@app.post("/action")
async def action_endpoint(request: DecisionRequest):
    """
    Submits a HITL decision.
    """
    if request.decision not in ["approve", "reject", "edit"]:
        raise HTTPException(
            status_code=400, detail="Invalid decision. Must be approve, reject, or edit."
        )

    success = tracker.submit_decision(request.session_id, request.decision, request.edited_action)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found.")

    return {"status": "resumed", "message": f"Action {request.decision} processed successfully."}
