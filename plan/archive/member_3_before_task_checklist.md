# Member 3 Todo List (System & Tracker Lead)

- [ ] **Day 1**: Review the selected domain.
- [ ] **Day 1**: Set up the local database structure (`sqlite` or JSON) to track ticket states (the "local tracker").
- [ ] **Day 2**: Implement durable event deduplication and atomic approval handling in the local tracker.
- [ ] **Day 3**: Connect the core agent to the local SQLite/JSON tracker. Ensure state persists if the script is restarted.
- [ ] **Day 4**: Curate the 15 "Test" cases. Make some of these *adversarial* (e.g., the user gives a wrong version and later corrects it, or the required info is missing).
- [ ] **Day 5**: Execute the evaluation on the 15 unseen Test cases. Ensure no data leakage occurred between Dev and Test sets.
- [ ] **Day 6**: Code freeze. Finalize the evaluation report. Include trace examples, cost logs (proving <$5 spent), and failure analyses.
