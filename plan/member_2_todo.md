# Member 2 Todo List (Agent & Workflow Architect)

- [ ] **Day 1**: Kickoff meeting. Select a specific domain (e.g., "Session State" or "Deployment"). Configure `pyproject.toml`. Define Pydantic models/schemas for the data (e.g., `Issue`, `Comment`, `AnalysisResult`).
- [ ] **Day 2**: Write the core LLM prompts. Instruct the LLM *never* to hallucinate missing information (like OS or Python versions). Output must differentiate between known facts, evidence (with citations), and missing info.
- [ ] **Day 3**: Build the LangGraph workflow. Define specific Python tools: `search_docs(query)`, `ask_user_for_info(question)`, `update_ticket(status)`.
- [ ] **Day 4**: Handle edge cases in the graph: prevent infinite loops, handle 404 tool errors, and manage scenarios where the maintainer rejects a proposal.
- [ ] **Day 5**: Run the 15 Dev cases. Tune prompts and retrieval parameters based on failures.
- [ ] **Day 6**: Code freeze. Review code quality, ensure the README explains how to reset the local tracker and run the agent.
