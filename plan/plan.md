# 6-Day Enriched Evidence-Based Project Plan: Streamlit Agentic Support Assistant

This document outlines a 6-day sprint plan for a 4-person team to complete the Quera Agentic AI Final Project. This version has been enriched with specific technical requirements, architectural decisions, and actionable steps derived from the project constraints.

## Team Roles & Technical Responsibilities

To maximize efficiency, the workload is divided into four primary roles. Team members should collaborate closely but take ownership of their specific domains.

*   **Member 1 (Data & RAG Engineer):** 
    *   **Focus:** Fetching data via GitHub API, cleaning, chunking, and embeddings.
    *   **Tech Stack:** Python `requests` (with GitHub PAT), ChromaDB/FAISS, LangChain `ContextualCompressionRetriever`.
*   **Member 2 (Agent & Workflow Architect):** 
    *   **Focus:** Core AI orchestration, state management, and multi-turn flow.
    *   **Tech Stack:** LangGraph (for cyclic `Analyze -> Draft -> Wait -> Execute` workflow), LangChain `@tool` decorator.
*   **Member 3 (System & Evaluation Lead):** 
    *   **Focus:** Local state tracking, curating 30 adversarial evaluation cases, and metrics.
    *   **Tech Stack:** SQLite/JSON for local state, RAGAS (or custom LLM-as-a-judge) for evaluation, `get_openai_callback` for strict cost tracking.
*   **Member 4 (Integration, UI & Bonus):** 
    *   **Focus:** User Interface (CLI/Web), Human-in-the-Loop (HITL) mechanism, bonus implementation (e.g., Durable Execution).
    *   **Tech Stack:** Streamlit/FastAPI (for UI), LangGraph `interrupt_before` (for HITL).

---

## Done

*   [x] Configure `pyproject.toml`.
*   [x] Build the basic scaffold for the CLI/Web UI and create the skeleton for the final report.

---

## Meetings & Decisions

### Next Meeting (To Be Discussed)
*   **Crucial Decision:** Select a specific domain to keep the dataset under 300 issues.
    *   *Options to discuss:* Session State, Deployment, Caching, UI Components.

### Meeting Todos (To Be Judged)
*   *(Empty for today)*

---

## Daily Schedule

### Day 1: Foundation, Domain Selection & Data Pipeline
**Goal:** Setup the environment, choose a domain, and acquire the raw data locally.
*   **All:** [ ] Review the selected domain and architecture before coding starts.
*   **Member 1:** [ ] Write `scripts/fetch_data.py`. Use a GitHub Personal Access Token to bypass rate limits. Clone `streamlit/docs` at commit `695e6ce...`. **Rule:** Cache all fetched data to `data/raw/`—no web calls during evaluation.
*   **Member 2:** [ ] Define Pydantic models/schemas for the data (e.g., `Issue`, `Comment`, `AnalysisResult`).
*   **Member 3:** [ ] Set up the local database structure (`sqlite` or JSON) to track ticket states (the "local tracker").
*   **Member 4:** [ ] Add the HITL pause mechanism UI placeholders in the built scaffold.

### Day 2: Advanced Retrieval & Prompt Engineering (Problem 1)
**Goal:** Build a robust retrieval system and a single-turn analysis agent.
*   **Member 1:** Implement vector embeddings. **Crucial Step:** Ensure every chunk has metadata (`source_url`, `commit_hash`, `type`). Implement Self-Querying Retrieval to filter irrelevant chunks before LLM synthesis.
*   **Member 2:** Write the core LLM prompts. **Strict Rule:** Instruct the LLM *never* to hallucinate missing information (like OS or Python versions). Output must differentiate between known facts, evidence (with citations), and missing info.
*   **Member 3:** [ ] Use agent to curate the 15 "Development" cases from the raw dataset for immediate prompt tuning.
*   **Member 4:** Implement the HITL pause mechanism in the UI, allowing a user to accept, reject, or edit a proposed action.

### Day 3: LangGraph Multi-turn Agent & State Management (Problem 2)
**Goal:** Transition to a stateful, multi-turn agent capable of tool execution.
*   **Member 1:** Refine the RAG pipeline to handle contradictory information and ensure citations map correctly to the original GitHub/Doc URLs.
*   **Member 2:** Build the LangGraph workflow. Define specific Python tools: `search_docs(query)`, `ask_user_for_info(question)`, `update_ticket(status)`.
*   **Member 3:** Connect the LangGraph agent to the local SQLite/JSON tracker. Ensure state persists if the script is restarted.
*   **Member 4:** Begin implementing the chosen **Bonus Section** (e.g., transferring the tool layer to MCP or adding Temporal for Durable Execution) in a separate branch.

### Day 4: Edge Cases, Adversarial Testing & Cost Control
**Goal:** Make the system robust against failures and prepare the final evaluation framework.
*   **Member 1:** Implement strict cost tracking (e.g., using `get_openai_callback`). Monitor the $5 budget limit closely.
*   **Member 2:** Handle edge cases in the graph: prevent infinite loops, handle 404 tool errors, and manage scenarios where the maintainer rejects a proposal.
*   **Member 3:** Curate the 15 "Test" cases. **Crucial Step:** Make some of these *adversarial* (e.g., the user gives a wrong version and later corrects it, or the required info is simply missing).
*   **Member 4:** Integrate the bonus feature into the main pipeline (if stable) and refine the UI for the evaluation phase.

### Day 5: System Evaluation & RAG Assessment
**Goal:** Run the 30 cases, gather quantitative metrics, and freeze the code.
*   **Member 1 & 2:** Run the 15 Dev cases. Tune prompts and retrieval parameters based on failures.
*   **Member 3:** Execute the evaluation on the 15 unseen Test cases. Calculate `context_relevancy` and `faithfulness` (using RAGAS or LLM-as-a-judge). Ensure no data leakage occurred between Dev and Test sets.
*   **Member 4:** Analyze operational success (Did the agent update the DB correctly? Did it stop when rejected?). Draft these findings for the final report.

### Day 6: Polish, Documentation & Presentation
**Goal:** Finalize all deliverables, ensuring reproducibility.
*   **All:** Code freeze. No new features.
*   **Member 1:** Clean up data collection scripts. Ensure instructions for reproducing the exact dataset are clear.
*   **Member 2:** Review code quality, ensure the README explains how to reset the local tracker and run the agent.
*   **Member 3:** Finalize the evaluation report. Include trace examples of the LangGraph execution, cost logs (proving <$5 spent), and failure analyses.
*   **Member 4:** Create the final presentation slides. Focus on the architecture (LangGraph), the HITL design, the evaluation metrics, and the bonus feature.

---

## Critical Checkpoints
*   **Budget Constraint:** The total budget is $5. Do not run heavy evaluations until prompts are mostly stable on small samples.
*   **Human-in-the-Loop:** The system must fundamentally rely on human approval before executing state-changing tools.
*   **No Real Modifications:** Ensure the agent *never* attempts to make real API calls to modify the Streamlit GitHub repository. All actions must be simulated in the local tracker.
