import json
import os
from typing import List, Dict, Any

class StreamlitDocChunker:
    def __init__(self, base_path: str):
        self.base_path = base_path
        self.docstrings_path = os.path.join(base_path, "sources", "docstrings_scope_candidates.jsonl")
        self.markdown_path = os.path.join(base_path, "sources", "docs_scope_candidates.jsonl")
        
    def load_jsonl(self, file_path: str) -> List[Dict[str, Any]]:
        data = []
        if not os.path.exists(file_path): return data
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip(): data.append(json.loads(line))
        return data

    def extract_docstring_chunks(self) -> List[Dict[str, Any]]:
        chunks = []
        for item in self.load_jsonl(self.docstrings_path):
             context_sentence = f"Documentation for Streamlit API '{item.get('function')}' in version {item.get('version')}."
             chunks.append({
                 "id": item.get("source_id"),
                 "text": f"{context_sentence}\n\n{item.get('text', '')}",
                 "metadata": {
                     "type": "docstring",
                     "version": item.get("version"),
                     "function_name": item.get("function"),
                     "source_url": item.get("pinned_source_url", item.get("source_url")),
                     "keywords": f"{item.get('function')}, api, {item.get('version')}"
                 }
             })
        return chunks
        
    def extract_markdown_chunks(self) -> List[Dict[str, Any]]:
        chunks = []
        for item in self.load_jsonl(self.markdown_path):
             context_sentence = f"Streamlit official documentation concept: {item.get('title')}."
             chunks.append({
                 "id": item.get("source_id"),
                 "text": f"{context_sentence}\n\n{item.get('text', '')}",
                 "metadata": {
                     "type": "markdown",
                     "title": item.get("title"),
                     "source_url": item.get("pinned_source_url", item.get("source_url")),
                     "keywords": f"{item.get('title')}, concept"
                 }
             })
        return chunks
