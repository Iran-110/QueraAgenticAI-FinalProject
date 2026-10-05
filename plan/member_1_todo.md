# Member 1 Todo List (Data & RAG Engineer)

- [ ] **Day 1**: Review the selected domain (e.g., "Session State" or "Deployment").
- [ ] **Day 1**: Write `scripts/fetch_data.py`. Use a GitHub Personal Access Token to bypass rate limits. Clone `streamlit/docs` at commit `695e6ce...`. Cache all fetched data to `data/raw/`.
- [ ] **Day 2**: Implement vector embeddings. Ensure every chunk has metadata (`source_url`, `commit_hash`, `type`). Implement Self-Querying Retrieval to filter irrelevant chunks before LLM synthesis.
- [ ] **Day 3**: Refine the RAG pipeline to handle contradictory information and ensure citations map correctly to the original GitHub/Doc URLs.
- [ ] **Day 4**: Implement strict cost tracking (e.g., using `get_openai_callback`). Monitor the $5 budget limit closely.
- [ ] **Day 5**: Run the 15 Dev cases. Tune prompts and retrieval parameters based on failures.
- [ ] **Day 6**: Code freeze. Clean up data collection scripts. Ensure instructions for reproducing the exact dataset are clear.
