# Member 3 Todo List (System & Evaluation Lead)

- [ ] **Day 1**: Kickoff meeting. Select a specific domain (e.g., "Session State" or "Deployment"). Configure `pyproject.toml`. Set up the local database structure (`sqlite` or JSON) to track ticket states (the "local tracker").
- [ ] **Day 2**: Manually curate the 15 "Development" cases from the raw dataset for immediate prompt tuning.
- [ ] **Day 3**: Connect the LangGraph agent to the local SQLite/JSON tracker. Ensure state persists if the script is restarted.
- [ ] **Day 4**: Curate the 15 "Test" cases. Make some of these *adversarial* (e.g., the user gives a wrong version and later corrects it, or the required info is simply missing).
- [ ] **Day 5**: Execute the evaluation on the 15 unseen Test cases. Calculate `context_relevancy` and `faithfulness` (using RAGAS or LLM-as-a-judge). Ensure no data leakage occurred between Dev and Test sets.
- [ ] **Day 6**: Code freeze. Finalize the evaluation report. Include trace examples of the LangGraph execution, cost logs (proving <$5 spent), and failure analyses.
