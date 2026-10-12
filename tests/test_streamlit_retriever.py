"""Read-only collection injection: no Chroma client, embedding, or index."""

import builtins
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from agent_app.retrieval.retriever import StreamlitRetriever

SNAPSHOT = "fixture-snapshot-v1"
NAMES = ("streamlit_docs", "streamlit_issues")


class Collection:
    def __init__(self, metadata=None):
        self.metadata = {"snapshot_id": SNAPSHOT} if metadata is None else metadata
        self.calls = []
        self.fail = False
        self.mutate_filter = False
        self.on_query = None

    def query(self, **arguments):
        self.calls.append(deepcopy(arguments))
        if self.fail:
            raise RuntimeError("PRIVATE_BACKEND_EXCEPTION_SENTINEL")
        if self.on_query:
            self.on_query()
        if self.mutate_filter:
            arguments["where"].clear()
        return {"ids": [[]], "documents": [[]], "metadatas": [[]]}


class Client:
    def __init__(self):
        self.collections = {name: Collection() for name in NAMES}
        self.lookups = []
        self.fail_name = None

    def get_collection(self, *, name):
        self.lookups.append(name)
        if name == self.fail_name:
            raise RuntimeError("PRIVATE_COLLECTION_EXCEPTION_SENTINEL")
        return self.collections[name]

    def get_or_create_collection(self, **arguments):
        pytest.fail("Read constructor must never create collections")


def make_retriever(client=None):
    return StreamlitRetriever(
        "unused-fixture-path", snapshot_id=SNAPSHOT, client=client or Client()
    )


def test_import_and_injected_constructor_do_not_load_chroma():
    script = """
import builtins
import json
import sys
original = builtins.__import__
def blocked(name, *args, **kwargs):
    if name == 'chromadb' or name.startswith('chromadb.'):
        raise AssertionError('Chroma import attempted')
    return original(name, *args, **kwargs)
builtins.__import__ = blocked
from agent_app.retrieval.retriever import StreamlitRetriever
class Collection:
    metadata = {'snapshot_id': 'offline-v1'}
class Client:
    def get_collection(self, **kwargs):
        return Collection()
StreamlitRetriever('unused', snapshot_id='offline-v1', client=Client())
print(json.dumps({'chroma_imported': any(k.startswith('chromadb') for k in sys.modules)}))
"""
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=True
    )
    assert json.loads(result.stdout) == {"chroma_imported": False}


@pytest.mark.parametrize("snapshot", ["", "bad snapshot", 7, None])
def test_invalid_snapshot_rejected_before_client_lookup(snapshot):
    client = Client()
    with pytest.raises(ValueError, match="^InvalidRetrievalConfiguration$"):
        StreamlitRetriever("unused", snapshot_id=snapshot, client=client)
    assert client.lookups == []


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("metadata", [{}, {"snapshot_id": "stale-v0"}, None])
def test_constructor_rejects_missing_or_stale_collection_snapshot(name, metadata):
    client = Client()
    client.collections[name].metadata = metadata
    with pytest.raises(RuntimeError, match="^RetrievalSnapshotMismatch$"):
        make_retriever(client)
    assert all(collection.calls == [] for collection in client.collections.values())


@pytest.mark.parametrize("name", NAMES)
def test_search_refreshes_replaced_collection_and_stops_before_query(name):
    client = Client()
    retriever = make_retriever(client)
    old_collections = tuple(client.collections.values())
    client.collections[name] = Collection({"snapshot_id": "replaced-v2"})
    with pytest.raises(RuntimeError, match="^RetrievalSnapshotMismatch$"):
        retriever.search("widget issue")
    assert all(collection.calls == [] for collection in old_collections)
    assert all(collection.calls == [] for collection in client.collections.values())
    assert client.lookups == [*NAMES, *NAMES]


@pytest.mark.parametrize("name", NAMES)
def test_missing_collection_uses_fixed_error(name):
    client = Client()
    client.fail_name = name
    with pytest.raises(RuntimeError, match="^RetrievalUnavailable$") as error:
        make_retriever(client)
    assert "PRIVATE" not in str(error.value)
    assert all(collection.calls == [] for collection in client.collections.values())


def test_missing_collection_after_constructor_stops_before_query():
    client = Client()
    retriever = make_retriever(client)
    del client.collections["streamlit_issues"]
    with pytest.raises(RuntimeError, match="^RetrievalUnavailable$"):
        retriever.search("widget issue")
    assert client.collections["streamlit_docs"].calls == []


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("change", ["metadata", "replacement"])
def test_snapshot_changed_during_query_is_rejected_before_return(name, change):
    client = Client()
    retriever = make_retriever(client)

    def invalidate():
        if change == "replacement":
            client.collections[name] = Collection({"snapshot_id": "changed-v2"})
        else:
            client.collections[name].metadata["snapshot_id"] = "changed-v2"

    client.collections["streamlit_docs"].on_query = invalidate
    with pytest.raises(RuntimeError, match="^RetrievalSnapshotMismatch$"):
        retriever.search("widget issue")
    assert client.lookups == [*NAMES, *NAMES, *NAMES]


@pytest.mark.parametrize(
    ("filters", "where"),
    [
        (None, None),
        ({}, None),
        ({"version": "1.49.1"}, {"version": "1.49.1"}),
        ({"version": ("1.49.0", "1.49.1")}, {"version": {"$in": ["1.49.0", "1.49.1"]}}),
        (
            {"version": ("1.49.0", "1.49.1"), "source_type": "doc"},
            {"$and": [{"version": {"$in": ["1.49.0", "1.49.1"]}}, {"source_type": "doc"}]},
        ),
    ],
)
def test_metadata_filters_are_applied_to_each_collection(filters, where):
    client = Client()
    retriever = make_retriever(client)
    original = deepcopy(filters)
    result = retriever.search("widget issue", n_results=2, filters=filters)
    expected = {"query_texts": ["widget issue"], "n_results": 2}
    if where is not None:
        expected["where"] = where
    assert set(result) == {"docs", "issues"}
    assert all(collection.calls == [expected] for collection in client.collections.values())
    assert filters == original


@pytest.mark.parametrize(
    ("filters", "code"),
    [
        ({"version": ()}, "InvalidRetrievalFilter"),
        ({"$and": "unsafe"}, "InvalidRetrievalFilter"),
        ({"version": 149}, "InvalidRetrievalRequest"),
        ({"version": ""}, "InvalidRetrievalRequest"),
        ({"": "doc"}, "InvalidRetrievalRequest"),
    ],
)
def test_invalid_filters_stop_before_collection_reads(filters, code):
    client = Client()
    retriever = make_retriever(client)
    with pytest.raises(ValueError, match=f"^{code}$"):
        retriever.search("widget issue", filters=filters)
    assert client.lookups == list(NAMES)
    assert all(collection.calls == [] for collection in client.collections.values())


@pytest.mark.parametrize(("query", "n_results"), [("", 3), ("issue", 0), ("issue", True)])
def test_invalid_query_or_result_limit_does_not_read_collections(query, n_results):
    client = Client()
    retriever = make_retriever(client)
    with pytest.raises(ValueError, match="^InvalidRetrievalRequest$"):
        retriever.search(query, n_results)
    assert client.lookups == list(NAMES)


def test_backend_cannot_mutate_caller_filter_or_other_collection_filter():
    client = Client()
    client.collections["streamlit_docs"].mutate_filter = True
    retriever = make_retriever(client)
    filters = {"version": ("1.49.0", "1.49.1"), "source_type": "doc"}
    before = deepcopy(filters)
    retriever.search("issue", filters=filters)
    assert filters == before
    assert (
        client.collections["streamlit_docs"].calls == client.collections["streamlit_issues"].calls
    )


@pytest.mark.parametrize("name", NAMES)
def test_backend_failure_never_exports_raw_exception(name):
    client = Client()
    client.collections[name].fail = True
    retriever = make_retriever(client)
    with pytest.raises(RuntimeError, match="^RetrievalUnavailable$") as error:
        retriever.search("widget issue")
    assert "PRIVATE" not in str(error.value)


def test_index_build_is_explicitly_disabled():
    client = Client()
    retriever = make_retriever(client)
    before = list(client.lookups)
    with pytest.raises(RuntimeError, match="^UnsupportedIndexBuild$"):
        retriever.index_data()
    assert client.lookups == before
    assert all(collection.calls == [] for collection in client.collections.values())


def test_default_client_is_imported_lazily_and_receives_database_path(monkeypatch, tmp_path):
    client = Client()
    imports = []
    paths = []
    original = builtins.__import__

    class Chroma:
        @staticmethod
        def PersistentClient(*, path):
            paths.append(path)
            return client

    def controlled_import(name, *arguments, **keywords):
        if name == "chromadb":
            imports.append(name)
            return Chroma
        return original(name, *arguments, **keywords)

    monkeypatch.setattr(builtins, "__import__", controlled_import)
    database = str(tmp_path / "existing-db")
    retriever = StreamlitRetriever("unused", db_path=database, snapshot_id=SNAPSHOT)
    assert retriever.client is client
    assert imports == ["chromadb"]
    assert paths == [database]
    assert not Path(database).exists()


def test_lazy_client_import_failure_has_fixed_error(monkeypatch):
    original = builtins.__import__

    def controlled_import(name, *arguments, **keywords):
        if name == "chromadb":
            raise ImportError("PRIVATE_IMPORT_FAILURE_SENTINEL")
        return original(name, *arguments, **keywords)

    monkeypatch.setattr(builtins, "__import__", controlled_import)
    with pytest.raises(RuntimeError, match="^RetrievalUnavailable$"):
        StreamlitRetriever("unused", snapshot_id=SNAPSHOT)
