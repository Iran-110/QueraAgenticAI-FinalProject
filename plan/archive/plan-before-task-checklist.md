# 6-Day Enriched Evidence-Based Project Plan: Streamlit Agentic Support Assistant

This document outlines a sprint plan for a 4-person team to complete the Quera Agentic AI Final Project. This version has been updated to reflect the actual core implementation, custom orchestration, strict cost accounting, and evidence-based design constraints (as documented in `docs/core-progress.md` and `README.md`).

## Team Roles & Technical Responsibilities

To maximize efficiency, the workload is divided into four primary roles. Team members should collaborate closely but take ownership of their specific domains.

*   **Member 1 (Data & RAG Engineer):** 
    *   **Focus:** Fetching data via GitHub API, cleaning, chunking, and embeddings.
    *   **Responsibilities:** Building the retrieval pipeline and frozen corpus. Providing inspectable sources, metadata, and dev retrieval measurements.
*   **Member 2 (Agent Core & Contracts):** *(Mostly Completed)*
    *   **Focus:** Core AI orchestration, state management, contracts, offline adapters, and budget accounting.
    *   **Responsibilities:** Maintain the shared contracts (`src/agent_app/contracts.py`), reasoning ports, and the SQLite model gateway ledger. Support integration.
*   **Member 3 (System & Tracker Lead):** 
    *   **Focus:** Local state tracking, durable execution, and tool safety.
    *   **Responsibilities:** Persisted state, restart, reject/edit/stale approval handling, and retry tests (`src/agent_app/tracker/` and `tools/`).
*   **Member 4 (UI, Evaluation & Bonus):** 
    *   **Focus:** Streamlit UI integration, evaluation cases, and reporting.
    *   **Responsibilities:** Connect UI to backend, live local flow, manage 15 dev + 15 test multi-turn cases, calculate metrics, and lead Adversarial Testing bonus.

---

## Status & Done

*   [x] Configure `pyproject.toml`.
*   [x] Build the basic scaffold for the CLI/Web UI.
*   [x] Agent core contracts, bounded retrieval refinement, and mocked offline tests.
*   [x] SQLite cost ledger and model gateway.
*   [x] Explicit user turns and prompt constraint experiments.
*   [x] Proposal static checks and callback arity verification.

*(See `docs/core-progress.md` for detailed historical progress.)*

---

## Daily Schedule

### Day 1: Foundation & Core Logic
**Goal:** Establish the architecture, shared contracts, and budget boundaries.
*   **All:** [x] Review the selected domain (Session State, Widgets, callback/rerun) and architecture before coding starts.
*   **Member 1:** [ ] Fetch data. Use a GitHub Personal Access Token to bypass rate limits. Cache all fetched data to `data/raw/`—no web calls during evaluation.
*   **Member 2:** [x] Define schemas and core reasoning loops. Implement the model gateway and SQLite ledger to enforce the $5 budget limit.
*   **Member 3:** [ ] Define the local database structure (`sqlite` or JSON) to track ticket states (the "local tracker").
*   **Member 4:** [x] Add the HITL pause mechanism UI placeholders in the built scaffold.

### Day 2: RAG Pipeline & Tracker Integration
**Goal:** Build a robust retrieval system and connect the tracker.
*   **Member 1:** Implement vector embeddings. **Crucial Step:** Ensure every chunk has metadata (`source_url`, `commit_hash`, `type`).
*   **Member 2:** [x] Write and refine the core LLM prompts. Handle parsing errors with repair feedback.
*   **Member 3:** Implement durable event deduplication and atomic approval handling in the local tracker.
*   **Member 4:** Use agent to curate the 15 "Development" cases from the raw dataset.

### Day 3: Multi-turn Workflows & Safety Guards
**Goal:** Transition to a stateful, multi-turn agent capable of safe tool execution.
*   **Member 1:** Refine the RAG pipeline to handle contradictory information and ensure citations map correctly.
*   **Member 2:** [x] Implement decision guardrails (e.g., source authority, callback/API static checks).
*   **Member 3:** Connect the core agent to the local SQLite/JSON tracker. Ensure state persists if the script is restarted.
*   **Member 4:** Implement the backend connection to the Streamlit UI, allowing a user to accept, reject, or edit a proposed action.

### Day 4: Edge Cases, Adversarial Testing & Cost Control
**Goal:** Make the system robust against failures and prepare the final evaluation framework.
*   **Member 1:** Evaluate retrieval quality locally without paid API calls.
*   **Member 2:** [x] Ensure terminal errors do not consume additional budget. Support teammate integration.
*   **Member 3:** Curate the 15 "Test" cases. **Crucial Step:** Make some of these *adversarial* (e.g., the user gives a wrong version and later corrects it, or the required info is simply missing).
*   **Member 4:** Begin implementing the chosen **Bonus Section** (Adversarial Testing) in a separate branch.

### Day 5: System Evaluation & Assessment
**Goal:** Run the 30 cases, gather quantitative metrics, and freeze the code.
*   **Member 1 & 2:** Run the 15 Dev cases. Tune prompts and retrieval parameters based on failures.
*   **Member 3:** Execute the evaluation on the 15 unseen Test cases. Ensure no data leakage occurred between Dev and Test sets.
*   **Member 4:** Analyze operational success (Did the agent update the DB correctly? Did it stop when rejected?). Draft these findings for the final report.

### Day 6: Polish, Documentation & Presentation
**Goal:** Finalize all deliverables, ensuring reproducibility.
*   **All:** Code freeze. No new features.
*   **Member 1:** Clean up data collection scripts. Ensure instructions for reproducing the exact dataset are clear.
*   **Member 2:** Ensure the README explains how to reset the local tracker and run the agent.
*   **Member 3:** Finalize the evaluation report. Include trace examples, cost logs (proving <$5 spent), and failure analyses.
*   **Member 4:** Create the final presentation slides. Focus on the architecture, the HITL design, the evaluation metrics, and the adversarial testing results.

---

## Critical Checkpoints
*   **Budget Constraint:** The total budget is $5. Heavy evaluations must be preceded by offline mock testing. Paid API calls go through the shared model gateway.
*   **Human-in-the-Loop:** The system must fundamentally rely on human approval before executing state-changing tools.
*   **No Real Modifications:** Ensure the agent *never* attempts to make real API calls to modify the Streamlit GitHub repository. All actions must be simulated in the local tracker.
*   **Offline First:** Default to offline mock execution for routine development.
