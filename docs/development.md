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
uv run agent-app gateway-demo --scenario repair
uv run agent-app turn-demo
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

All demo scenarios run offline, using synthetic evidence and scripted decisions. The `error` scenario intentionally returns exit status 1 with `RetrievalUnavailable`; this is the expected failure path. The Streamlit UI calls the local FastAPI backend; start both with the commands in [README](../README.md). This is an offline prototype with fake retrieval/reasoning and in-memory case storage, so credentials are not needed. The first dependency sync needs package downloads unless cached.

Ruff checks the Python core, API and tests; `app.py` and `streamlit_examples/` remain excluded by the current configuration. UI/API tests still run in the full pytest suite.

## Automatic checks

GitHub Actions runs the locked install, Ruff lint/format checks, the full test suite, and offline refinement, gateway accounting and user-turn demos on every branch push and PR update. It needs no API key and makes no paid calls. Review results in the PR checks or repository Actions tab.

The workflow must be present in a branch to check its pushes. After the foundation PR is merged, update existing feature branches from `main`; new branches then inherit the same checks. Future modules should add their behavioral tests to `tests/` so CI picks them up. Making a successful check mandatory for merging is a separate repository setting for the maintainer.

## Branches and handoff

Read the shared [team checklist](../plan/plan.md) before starting. Update your feature branch from current main after preserving local work. Each owner updates their task status with evidence in the implementation PR; include the task ID and introduce the PR to the team.

Suggested branch names: `feat/agent-core-foundation`, `feat/data-rag`, `feat/local-tracker`, `feat/ui-evaluation`. Create your own branch from the agreed integration branch:

```bash
git status --short
git switch main
git pull --ff-only
git switch -c feat/data-rag
```

Replace the branch name with your work area. Start with a clean checkout, or preserve local work on its existing branch first. Never force-push a teammate's branch. Use a PR with the behavior changed, relevant checks, and known gaps; let another owner review shared interfaces before merging.

Before implementation, agree on a valid input/output example. Build against a small mock for the other module instead of changing its files. Contracts are shared; propose changes early and adapt consumers together.

The [integration guide](integration.md) has a runnable adapter example and the retrieval, tracker and UI handoff rules. It works without another teammate's module or a real key.

Commit when a coherent part works: contracts, an orchestration behavior, a verified integration, or useful docs. Stage the intended paths explicitly, inspect the staged diff, and use a short factual message such as `feat(core): bound retrieval refinement`. Do not split a trivial edit into many commits or alter timestamps to create activity.

## Data and cost

Raw datasets, downloaded documentation, databases, caches, and credentials do not belong in code commits. Check in the collection recipe and snapshot metadata; coordinate where the team shares the actual snapshot. Existing local downloads outside the repo are working material, not automatically part of a teammate's clone.

Use mocks and synthetic responses for daily development. Small live compatibility checks now validate question, source-referenced answer and repair behavior, using synthetic inputs. They do not evaluate real support quality. Keep one designated live runner and one authoritative ledger, as described in [the gateway guide](model-gateway.md). Before broader live work, agree on the model, price basis, run limit, remaining budget and a single place to record spending; reconcile estimates with account billing. The USD 5 ceiling includes the bonus and evaluation; separate local demos from paid results in every report.

Evaluation owns the dev/test split before retrieval builds the index. Do not tune prompts, models, or retrieval on the test set. Each outcome should be supported by saved evidence and actual tracker state, not just the model's explanation.

## Instructions for coding agents

Maintain one shared [AGENTS.md](../AGENTS.md). [CLAUDE.md](../CLAUDE.md) imports it with `@AGENTS.md`, so rules do not drift across tools. This follows [OpenAI's project instructions guide](https://learn.chatgpt.com/docs/agent-configuration/agents-md) and [Claude Code's shared-file guidance](https://code.claude.com/docs/en/memory#share-one-file-with-other-coding-tools). No custom skill or global tool configuration is needed for this foundation.
