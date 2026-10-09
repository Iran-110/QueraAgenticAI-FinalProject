import json
from typing import Dict, Any, Optional

class DummyTracker:
    """
    A dummy tracker to mock the state of a Human-in-the-Loop (HITL) pause mechanism.
    TODO(Member 3): Implement the actual SQLite/JSON tracker to persist the execution state,
    handle deduplication, and atomically manage approval states.
    """
    def __init__(self):
        # In a real app, this would be a DB query. We mock it in memory for now.
        self._mock_db = {
            "session_1": {
                "is_paused": False,
                "proposed_action": None,
                "history": []
            }
        }

    def get_session_state(self, session_id: str) -> Dict[str, Any]:
        """
        Retrieves the current state of a session.
        TODO(Member 3): Read from durable storage.
        """
        return self._mock_db.get(session_id, {"is_paused": False, "proposed_action": None, "history": []})

    def pause_for_approval(self, session_id: str, proposed_action: Dict[str, Any]):
        """
        Pauses the graph execution and saves the proposed action.
        TODO(Member 3): Save state to DB and halt execution.
        """
        if session_id not in self._mock_db:
            self._mock_db[session_id] = {"history": []}
        
        self._mock_db[session_id]["is_paused"] = True
        self._mock_db[session_id]["proposed_action"] = proposed_action

    def submit_decision(self, session_id: str, decision: str, edited_action: Optional[Dict[str, Any]] = None):
        """
        Submits the human decision ('approve', 'reject', 'edit') and resumes execution.
        TODO(Member 3): Update DB, validate stale approvals, and trigger agent resumption.
        """
        if session_id not in self._mock_db:
            return False
        
        self._mock_db[session_id]["is_paused"] = False
        action = edited_action if decision == "edit" else self._mock_db[session_id]["proposed_action"]
        
        # Record the decision in history
        self._mock_db[session_id]["history"].append({
            "action": action,
            "decision": decision
        })
        
        self._mock_db[session_id]["proposed_action"] = None
        return True

# Global instance for the FastAPI app to use
tracker = DummyTracker()
