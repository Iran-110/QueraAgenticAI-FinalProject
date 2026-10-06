# Development together

Use Python 3.13 and the checked-in uv lockfile. Run commands from the repository root. Keep the original UI and plan usable while adding each module.

## Local setup and checks

```bash
uv sync --locked --group dev
uv run agent-app demo --scenario ask
uv run agent-app demo --scenario answer
uv run agent-app demo --scenario escalate
uv run agent-app demo --scenario refine
uv run agent-app demo --scenario error
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

All demo scenarios run offline, using synthetic evidence and scripted decisions. The `error` scenario intentionally returns exit status 1 with `RetrievalUnavailable`; this is the expected failure path. `uv run streamlit run app.py` starts the original UI placeholder. Credentials are not needed for either workflow yet. The first dependency sync needs package downloads unless cached.

Ruff currently checks the new Python core and tests; the unchanged `app.py` and `streamlit_examples/` are excluded until their owner updates them.

## Branches and handoff

Suggested branch names: `feat/agent-core-foundation`, `feat/data-rag`, `feat/local-tracker`, `feat/ui-evaluation`. Create your own branch from the agreed integration branch:

```bash
git status --short
git switch main
git pull --ff-only
git switch -c feat/data-rag
```

Replace the branch name with your work area. Start with a clean checkout, or preserve local work on its existing branch first. Never force-push a teammate's branch. Use a PR with the behavior changed, relevant checks, and known gaps; let another owner review shared interfaces before merging.

Before implementation, agree on a valid input/output example. Build against a small mock for the other module instead of changing its files. Contracts are shared; propose changes early and adapt consumers together.

Commit when a coherent part works: contracts, an orchestration behavior, a verified integration, or useful docs. Stage the intended paths explicitly, inspect the staged diff, and use a short factual message such as `feat(core): bound retrieval refinement`. Do not split a trivial edit into many commits or alter timestamps to create activity.

## Data and cost

Raw datasets, downloaded documentation, databases, caches, and credentials do not belong in code commits. Check in the collection recipe and snapshot metadata; coordinate where the team shares the actual snapshot. Existing local downloads outside the repo are working material, not automatically part of a teammate's clone.

Use mocks and recorded responses for daily development. The paid adapter and the team's shared cost ledger are pending. Before its first real run, agree on the model, price basis, small pilot limit, remaining budget, and a single place to record spending. The USD 5 ceiling includes the bonus and evaluation; separate local demos from paid results in every report.

Evaluation owns the dev/test split before retrieval builds the index. Do not tune prompts, models, or retrieval on the test set. Each outcome should be supported by saved evidence and actual tracker state, not just the model's explanation.

## Instructions for coding agents

Maintain one shared [AGENTS.md](../AGENTS.md). [CLAUDE.md](../CLAUDE.md) imports it with `@AGENTS.md`, so rules do not drift across tools. This follows [OpenAI's project instructions guide](https://learn.chatgpt.com/docs/agent-configuration/agents-md) and [Claude Code's shared-file guidance](https://code.claude.com/docs/en/memory#share-one-file-with-other-coding-tools). No custom skill or global tool configuration is needed for this foundation.
