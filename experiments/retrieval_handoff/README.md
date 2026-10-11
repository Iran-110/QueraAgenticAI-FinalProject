# First RAG/core handoff: pinned offline review

This is an integration baseline for PR #23 at
`c0d450a57769b4513b6b99f2e75ed506c483363d` against released core
`37ce74aeec462343ea091b05078116a2f6728781`. It does not implement the RAG
owner's adapter, connect HTTP, build an index, run embeddings, or measure
retrieval/model quality. The [Persian review](../../docs/rag-handoff-review-2026-10-11.fa.md)
lists the small next delivery and existing port example.

## Reproduce the contract baseline

The two commits must exist locally. Fetch the RAG branch if needed; preserve
your checkout and install only the released main dependencies. From the repo:

```bash
git fetch origin feat/rag-module
uv run python experiments/retrieval_handoff/probe_rag_core.py \
  --repo . --output /tmp/rag-core-contract-new.json
```

Choose a fresh output path on every run. The script archives the pinned core
into a temporary directory and compiles only the reviewed RAG class. Its
constructor, module imports, ingestion and `__main__` never execute. Two
in-memory collections accept its arguments so the outer core contract can be
tested without Chroma, an index, embeddings, downloads or an API key.

[Recorded result](results-core-port-c0d450a.json): each collection receives a
`RetrievalRequest` object inside `query_texts` and requests `n_results=3`, despite
the core's `top_k=1`. Core stops with `RetrievalResultInvalid` and zero model
attempts. This is the expected negative baseline. Actual Chroma may reject
the input earlier; its runtime behavior was not tested. Source/script hashes
and all pinned core source fingerprints are recorded. Raw request prints are
captured and reported as a boolean, not exported as query text.

## Reproduce the seed preview

Use the previously shared seed ZIP with SHA-256
`02408667f34d9d0ff4adc9c055685d8ba7fd6fbd3f45ea8b4bf4d88b2ef42d80`.
The seed and its extracted directory are outside Git. Extract into a separate
workspace first; the audit does not extract or modify the seed itself.

```bash
uv run python experiments/retrieval_handoff/data-audit.py \
  --repo-root . --seed-zip /path/to/streamlit-data-for-dev-test.zip \
  --seed-dir /path/to/streamlit-data-for-dev-test \
  --output /tmp/rag-seed-preview-new.json
```

The script executes only the pinned pure loader/chunker, imports only their
standard-library dependencies, and inspects the indexer as AST. Source data
and snippets are never executed. It checks all manifest hashes/sizes, compares
the extracted files with ZIP members and records unchanged file hashes.

[Recorded preview](results-data-c0d450a.json): 236 allowed issue contexts,
984 attached comments, 1,172 API records and 56 Markdown records. Five produced
Markdown chunks exceed the core excerpt limit. The absence of comment use in
indexing is a source-level observation; `actual_indexed_comment_count` is null
because no index ran. This is neither an approved corpus nor a frozen split.
The read-only preview does not close R1/R2/R3/P4.

These scripts deliberately remain pinned negative/preview baselines. The RAG
owner's next PR must add offline acceptance tests for the actual typed adapter;
changing these baselines to hide the original failures is not verification.
