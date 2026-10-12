import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from src.agent_app.contracts import EvidenceBundle, EvidenceHit, RetrievalRequest
from src.agent_app.retrieval.retriever import StreamlitRetriever


class ChromaRetrieverAdapter:
    def __init__(self, base_path: str):
        self.base_path = base_path
        self.core_retriever = StreamlitRetriever(base_path=base_path)

    def _truncate_text(self, text: str, max_chars: int = 19900) -> str:
        if len(text) > max_chars:
            return text[:max_chars] + "\n\n...[TRUNCATED DUE TO LENGTH]"
        return text

    def search(self, request: RetrievalRequest) -> EvidenceBundle:
        all_hits = []
        warnings = []
        for query in request.queries:
            raw_results = self.core_retriever.search(query=query, n_results=request.top_k)
            if raw_results["docs"]["documents"] and raw_results["docs"]["documents"][0]:
                for i in range(len(raw_results["docs"]["documents"][0])):
                    doc_text = self._truncate_text(raw_results["docs"]["documents"][0][i])
                    doc_meta = raw_results["docs"]["metadatas"][0][i]
                    doc_id = raw_results["docs"]["ids"][0][i]
                    versions = (doc_meta["version"],) if "version" in doc_meta else ()
                    hit = EvidenceHit(
                        chunk_id=f"doc:{doc_id}",
                        source_id=str(doc_id),
                        excerpt=doc_text,
                        source_url=doc_meta.get("source_url", "https://docs.streamlit.io"),
                        source_type="doc",
                        applicable_versions=versions,
                        source_span=f"Function/Concept: {doc_meta.get('function_name', doc_meta.get('title', 'Unknown'))}",
                    )
                    all_hits.append(hit)
            if raw_results["issues"]["documents"] and raw_results["issues"]["documents"][0]:
                for i in range(len(raw_results["issues"]["documents"][0])):
                    issue_text = self._truncate_text(raw_results["issues"]["documents"][0][i])
                    issue_meta = raw_results["issues"]["metadatas"][0][i]
                    issue_id = raw_results["issues"]["ids"][0][i]
                    hit = EvidenceHit(
                        chunk_id=f"issue:{issue_id}",
                        source_id=f"issue-{issue_id}",
                        excerpt=issue_text,
                        source_url=issue_meta.get(
                            "html_url", f"https://github.com/streamlit/streamlit/issues/{issue_id}"
                        ),
                        source_type="issue",
                        source_span=f"State: {issue_meta.get('state', 'Unknown')}",
                    )
                    all_hits.append(hit)
        unique_hits = {hit.chunk_id: hit for hit in all_hits}.values()
        final_hits = tuple(list(unique_hits)[: request.top_k])
        if not final_hits:
            warnings.append("هیچ نتیجه‌ای در دیتابیس ChromaDB یافت نشد.")
        return EvidenceBundle(
            snapshot_id=request.snapshot_id,
            hits=final_hits,
            queries_used=request.queries,
            warnings=tuple(warnings),
        )
