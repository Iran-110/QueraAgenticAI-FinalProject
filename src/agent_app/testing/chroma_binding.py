"""Fixed native collection reads injected into the actual RAG constructors.

Only backend rows are translated. Production adapter search and evidence mapping
remain intact. No gold, decisions, future user turns, or result fixes reach them.
"""

import json

from agent_app.retrieval.adapter import ChromaRetrieverAdapter
from agent_app.retrieval.retriever import StreamlitRetriever
from agent_app.testing.retrieval_acceptance import RetrievalProbe


class FixedCollection:
    def __init__(self, probe: RetrievalProbe, *, name: str):
        self.probe = probe
        self.name = name
        self.metadata = {"snapshot_id": probe.snapshot_id}

    def query(self, *, query_texts, n_results, where=None):
        # The matrix uses no filters; do not pretend this double exercises
        # real Chroma's filter/relevance semantics.
        if where or len(query_texts) != 1:
            raise ValueError("UnsupportedFixtureCollectionRequest")
        rows = self.probe.backend.search(query_texts[0], top_k=n_results)
        rows = [
            row
            for row in rows
            if (row["source_type"] in {"doc", "release_note"}) == (self.name == "streamlit_docs")
        ]
        metadatas = []
        for row in rows:
            metadata = {
                key: value
                for key, value in row.items()
                if key not in {"excerpt", "applicable_versions"} and value is not None
            }
            metadata["applicable_versions"] = json.dumps(row.get("applicable_versions", []))
            if len(row.get("applicable_versions", [])) == 1:
                metadata["version"] = row["applicable_versions"][0]
            metadatas.append(metadata)
        return {
            "ids": [[row["chunk_id"] for row in rows]],
            "documents": [[row["excerpt"] for row in rows]],
            "metadatas": [metadatas],
        }


class FixedClient:
    def __init__(self, probe: RetrievalProbe):
        self.collections = {
            name: FixedCollection(probe, name=name)
            for name in ("streamlit_docs", "streamlit_issues")
        }

    def get_collection(self, *, name):
        return self.collections[name]


def factory(probe: RetrievalProbe) -> ChromaRetrieverAdapter:
    backend = StreamlitRetriever(
        base_path="unused-offline-fixture",
        snapshot_id=probe.snapshot_id,
        client=FixedClient(probe),
    )
    return ChromaRetrieverAdapter(
        base_path="unused-offline-fixture",
        snapshot_id=probe.snapshot_id,
        core_retriever=backend,
    )
