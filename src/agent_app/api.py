from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import asyncio

from src.agent_app.tracker.dummy_tracker import tracker

app = FastAPI(title="Agentic AI Backend")

class ChatRequest(BaseModel):
    session_id: str
    message: str

class DecisionRequest(BaseModel):
    session_id: str
    decision: str  # 'approve', 'reject', 'edit'
    edited_action: Optional[Dict[str, Any]] = None

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
        tracker.pause_for_approval(request.session_id, proposed_action={
            "tool": "edit_file",
            "arguments": {"file": "app.py", "content": "st.session_state['count'] = 0"}
        })
        return {"status": "paused", "message": "Agent paused for HITL approval."}
    
    return {"status": "completed", "message": f"Agent says: I understood '{request.message}'. How can I help further?"}

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
        raise HTTPException(status_code=400, detail="Invalid decision. Must be approve, reject, or edit.")
        
    success = tracker.submit_decision(request.session_id, request.decision, request.edited_action)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found.")
        
    return {"status": "resumed", "message": f"Action {request.decision} processed successfully."}
