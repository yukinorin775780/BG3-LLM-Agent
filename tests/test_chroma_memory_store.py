from core.memory.chroma_store import ChromaMemoryStore
from core.memory.models import MemoryQuery, MemoryRecord


class FakeCollection:
    def __init__(self):
        self.add_calls = []
        self.query_calls = []

    def count(self):
        return 1

    def add(self, documents, metadatas, ids):
        self.add_calls.append((documents, metadatas, ids))

    def query(self, query_texts, n_results, include=None):
        self.query_calls.append((query_texts, n_results, include))
        return {
            "documents": [["记忆A"]],
            "metadatas": [[{"memory_id": "m1", "scope": "world", "memory_type": "episodic"}]],
            "distances": [[0.2]],
        }


class FakeClient:
    def __init__(self):
        self.collections = {}

    def get_or_create_collection(self, name):
        self.collections.setdefault(name, FakeCollection())
        return self.collections[name]

    def delete_collection(self, name):
        self.collections.pop(name, None)


def test_store_writes_world_record_to_world_collection():
    client = FakeClient()
    store = ChromaMemoryStore(client=client)

    record = MemoryRecord(
        memory_id="m1",
        text="世界线推进",
        scope="world",
        memory_type="quest",
        owner_actor_id=None,
        participants=("player", "shadowheart"),
        location_id="camp_fire",
        turn_index=10,
        importance=3,
    )

    store.upsert(record)

    assert "bg3_mem_world" in client.collections
    collection = client.collections["bg3_mem_world"]
    assert len(collection.add_calls) == 1


def test_store_queries_private_scope_from_private_collection():
    client = FakeClient()
    store = ChromaMemoryStore(client=client)

    query = MemoryQuery(
        actor_id="shadowheart",
        query_text="artifact",
        current_location="camp_fire",
        turn_index=12,
        top_k=3,
    )

    store.query_scope(scope_key="actor_private:shadowheart", query=query, top_k=3)

    assert "bg3_mem_actor_shadowheart" in client.collections
    collection = client.collections["bg3_mem_actor_shadowheart"]
    assert collection.query_calls == [
        (
            ["artifact"],
            1,
            ["documents", "metadatas", "distances"],
        )
    ]
