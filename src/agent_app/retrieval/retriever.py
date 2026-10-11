import chromadb
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
from data_scripts.data_loader import StreamlitDataLoader
from data_scripts.chunking import StreamlitDocChunker

class StreamlitRetriever:
    def __init__(self, base_path: str, db_path: str = "./.chroma_db"):
        self.base_path = base_path
        self.client = chromadb.PersistentClient(path=db_path)
        self.docs_collection = self.client.get_or_create_collection(name="streamlit_docs")
        self.issues_collection = self.client.get_or_create_collection(name="streamlit_issues")
        
    def index_data(self):
        print("Indexing Documents into ChromaDB...")
        chunker = StreamlitDocChunker(self.base_path)
        all_docs = chunker.extract_docstring_chunks() + chunker.extract_markdown_chunks()
        
        if all_docs:
            self.docs_collection.add(
                ids=[str(doc["id"]) for doc in all_docs],
                documents=[doc["text"] for doc in all_docs],
                metadatas=[doc["metadata"] for doc in all_docs]
            )
            print(f"Successfully indexed {len(all_docs)} documents.")

        print("Indexing Issues into ChromaDB...")
        issues = StreamlitDataLoader(self.base_path).build_full_issue_context()
        
        if issues:
            issue_ids, issue_texts, issue_metas = [], [], []
            for issue in issues:
                issue_ids.append(str(issue["issue_number"]))
                issue_texts.append(f"Issue #{issue['issue_number']}: {issue['title']}\n{issue['body']}")
                issue_metas.append({
                    "type": "issue",
                    "state": issue["state"],
                    "html_url": issue["html_url"]
                })
            
            self.issues_collection.add(
                ids=issue_ids,
                documents=issue_texts,
                metadatas=issue_metas
            )
            print(f"Successfully indexed {len(issues)} issues.")

    def search(self, query: str, n_results: int = 3):
        print(f"\n[Search Query]: '{query}'")
        return {
            "docs": self.docs_collection.query(query_texts=[query], n_results=n_results),
            "issues": self.issues_collection.query(query_texts=[query], n_results=n_results)
        }

if __name__ == "__main__":
    BASE_PATH = "./streamlit-data-for-dev-test"
    retriever = StreamlitRetriever(base_path=BASE_PATH)
    retriever.index_data()
    
    results = retriever.search("st.session_state callbacks")
    print("\n--- Top Document Match ---")
    if results["docs"]["documents"][0]:
        print(results["docs"]["documents"][0][0][:200], "...\nMetadata:", results["docs"]["metadatas"][0][0])
