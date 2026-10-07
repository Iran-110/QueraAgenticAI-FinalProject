"""Synthetic in-memory user turns; no tracker, model access, or paid calls."""

from agent_app.contracts import AnalysisResult, CaseState, ReportedFact, UserTurn
from agent_app.demo import SNAPSHOT_ID, _answer, _ask, _evidence
from agent_app.orchestration import SupportEngine
from agent_app.orchestration.turns import propose_user_turn
from agent_app.testing.fakes import FakeReasoner, FakeRetriever


def run_turn_demo() -> dict:
    state = CaseState(
        case_id="synthetic-turn-case",
        unknowns=("streamlit_version", "widget_definition"),
        pending_proposal_id="synthetic-old-proposal",
    )
    turns = (
        UserTurn(
            case_id=state.case_id,
            expected_revision=0,
            turn_id="turn-1",
            source_ref="user:turn-1",
            message="My widget loses its value after a rerun.",
        ),
        UserTurn(
            case_id=state.case_id,
            expected_revision=1,
            turn_id="turn-2",
            source_ref="user:turn-2",
            message="The affected app uses version 1.50 and text_input with key search.",
            reported_facts=(
                ReportedFact(name="streamlit_version", value="1.50"),
                ReportedFact(name="widget_definition", value="text_input with key search"),
            ),
            checks_performed=("Checked the widget key in this environment.",),
        ),
        UserTurn(
            case_id=state.case_id,
            expected_revision=2,
            turn_id="turn-3",
            source_ref="user:turn-3",
            message="Correction: that app uses version 1.51.",
            reported_facts=(ReportedFact(name="streamlit_version", value="1.51"),),
        ),
    )
    scripted: tuple[AnalysisResult, ...] = (
        _ask(),
        _answer("synthetic-turn-evidence"),
        _answer("synthetic-turn-evidence"),
    )
    previews = []
    for turn, analysis in zip(turns, scripted, strict=True):
        transition = propose_user_turn(state, turn)
        # Simulate progression in memory only. Production must commit through
        # the tracker and read the authoritative state before invoking the engine.
        state = transition.candidate
        retriever = FakeRetriever(
            [_evidence("synthetic-turn-evidence", "Synthetic counter-persistence example.")]
        )
        engine = SupportEngine(retriever, FakeReasoner([analysis]), snapshot_id=SNAPSHOT_ID)
        result = engine.run(state, turn.message, run_id=f"synthetic-run:{turn.turn_id}")
        previews.append(
            {
                "transition": transition.model_dump(mode="json"),
                "retrieval_query": retriever.requests[0].queries[0],
                "result": result.model_dump(mode="json"),
            }
        )
    return {
        "mode": "synthetic_in_memory_turns",
        "state_persisted": False,
        "real_api_calls": 0,
        "paid_cost_usd": 0,
        "turns": previews,
        "result": previews[-1]["result"],
    }
