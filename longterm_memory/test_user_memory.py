"""
Tests that shoppers' memories stay separate. Run from the repo root:  python -m longterm_memory.test_user_memory

Two kinds of test:
  - "recording" tests use a stand-in collection that notes every call, to prove each call carries the shopper's
    filter. They need nothing installed.
  - "chroma" tests run the same ideas against real Chroma in a temporary folder, with a deterministic embedding
    (no model download). They are skipped when chromadb is not installed.
"""
import hashlib
import math
import re
import shutil
import sys
import tempfile
import traceback

from .user_memory import MAX_RESULTS, InvalidUserError, Memory, UserMemory, user_key


class Skip(Exception):
    pass


class RecordingCollection:
    """Stands in for a Chroma collection: records each call and returns canned answers."""

    def __init__(self, ids=(), documents=(), metadatas=(), distances=None):
        self.calls = []  # (method, kwargs)
        self._ids, self._documents, self._metadatas = list(ids), list(documents), list(metadatas)
        self._distances = list(distances) if distances is not None else [0.1 * (n + 1) for n in range(len(self._ids))]

    def upsert(self, **kwargs):
        self.calls.append(("upsert", kwargs))

    def query(self, **kwargs):
        self.calls.append(("query", kwargs))
        return {"ids": [self._ids], "documents": [self._documents], "metadatas": [self._metadatas], "distances": [self._distances]}

    def get(self, **kwargs):
        self.calls.append(("get", kwargs))
        return {"ids": self._ids, "documents": self._documents, "metadatas": self._metadatas}

    def delete(self, **kwargs):
        self.calls.append(("delete", kwargs))


def meta(user_id, **extra):
    return {"user_id": str(user_id), "kind": "dietary", "created_at": 100.0, **extra}


# --- recording tests (no chromadb needed) ---

def test_user_ids_must_be_positive_whole_numbers():
    for bad in (None, 0, -3, "", "abc", "1.5", 1.5, True, False, [], "7; drop", " "):
        try:
            user_key(bad)
        except InvalidUserError:
            continue
        raise AssertionError(f"{bad!r} was accepted as a user id")
    assert user_key(7) == user_key("7") == user_key(" 007 ") == "7"


def test_every_read_and_delete_carries_the_shoppers_filter():
    collection = RecordingCollection(ids=["u7:a"], documents=["Is vegetarian."], metadatas=[meta(7)])
    memory = UserMemory(collection, 7)
    memory.search("vegetarian")
    memory.list()
    memory.count()
    memory.delete("a")
    memory.delete_all()
    reads_and_deletes = [(name, kw) for name, kw in collection.calls if name != "upsert"]
    assert len(reads_and_deletes) >= 7
    for name, kwargs in reads_and_deletes:
        assert kwargs.get("where") == {"user_id": "7"}, f"{name} was called without the shopper's filter: {kwargs}"


def test_saving_tags_and_prefixes_the_memory_with_its_shopper():
    collection = RecordingCollection()
    UserMemory(collection, 7).add("turn-5", "Is vegetarian.", kind="dietary", source={"session_id": "s1", "turn_id": 5})
    (name, kwargs), = collection.calls
    assert name == "upsert"
    assert kwargs["ids"] == ["u7:turn-5"]  # another shopper's "turn-5" is a different record
    assert kwargs["documents"] == ["Is vegetarian."]
    assert kwargs["metadatas"][0]["user_id"] == "7"
    assert kwargs["metadatas"][0]["session_id"] == "s1"


def test_the_source_cannot_override_the_owner_or_the_kind():
    collection = RecordingCollection()
    UserMemory(collection, 7).add("m", "x", kind="dietary", source={"user_id": "99", "kind": "hack", "created_at": 1})
    metadata = collection.calls[0][1]["metadatas"][0]
    assert metadata["user_id"] == "7" and metadata["kind"] == "dietary" and metadata["created_at"] > 1_000_000


def test_delete_looks_for_the_memory_among_the_shoppers_own_first():
    collection = RecordingCollection(ids=[])  # nothing of theirs matches
    assert UserMemory(collection, 7).delete("someone-elses") is False
    assert [name for name, _ in collection.calls] == ["get"]  # never reached delete()


def test_a_result_that_is_not_the_shoppers_is_dropped_even_if_chroma_returns_it():
    collection = RecordingCollection(
        ids=["u7:mine", "u8:theirs"], documents=["Mine.", "Not mine."], metadatas=[meta(7), meta(8)]
    )
    memory = UserMemory(collection, 7)
    assert [m.text for m in memory.search("anything")] == ["Mine."]
    assert [m.text for m in memory.list()] == ["Mine."]


def test_search_results_come_back_with_the_plain_memory_id():
    collection = RecordingCollection(ids=["u7:turn-3"], documents=["Prefers Amul."], metadatas=[meta(7, session_id="s")])
    (found,) = UserMemory(collection, 7).search("amul")
    assert isinstance(found, Memory)
    assert (found.id, found.text, found.kind) == ("turn-3", "Prefers Amul.", "dietary")
    assert found.source == {"session_id": "s"}


def test_search_asks_for_at_most_the_maximum_and_ignores_a_blank_query():
    collection = RecordingCollection()
    memory = UserMemory(collection, 7)
    assert memory.search("   ") == []
    assert collection.calls == []  # a blank query does not reach Chroma
    memory.search("x", k=500)
    memory.search("x", k=-4)
    sizes = [kw["n_results"] for name, kw in collection.calls if name == "query"]
    assert sizes == [MAX_RESULTS, 1]


def test_an_empty_memory_is_refused_and_long_text_is_cut():
    memory = UserMemory(RecordingCollection(), 7)
    try:
        memory.add("m", "   ")
    except ValueError:
        pass
    else:
        raise AssertionError("empty memory accepted")
    collection = RecordingCollection()
    UserMemory(collection, 7).add("m", "x" * 5000)
    assert len(collection.calls[0][1]["documents"][0]) == 500


# --- real Chroma tests (skipped without chromadb) ---

def _hash_embedding_class():
    import chromadb

    class HashEmbedding(chromadb.EmbeddingFunction):
        """Deterministic bag-of-words vectors: texts sharing words are close. No model download."""

        def __init__(self):
            pass

        def __call__(self, input):
            vectors = []
            for text in input:
                vector = [0.0] * 64
                for word in re.findall(r"[a-z]+", text.lower()):
                    vector[int(hashlib.md5(word.encode()).hexdigest(), 16) % 64] += 1.0
                norm = math.sqrt(sum(v * v for v in vector)) or 1.0
                vectors.append([v / norm for v in vector])
            return vectors

        @staticmethod
        def name():
            return "voicecart-test-hash-embedding"

        def get_config(self):
            return {}

        @staticmethod
        def build_from_config(config):
            return HashEmbedding()

    return HashEmbedding


class chroma:
    """Context manager: a real, empty Chroma collection in a temporary folder."""

    def __enter__(self):
        try:
            import chromadb
            from chromadb.config import Settings
        except ImportError:
            raise Skip("chromadb is not installed")
        self.folder = tempfile.mkdtemp(prefix="memtest_chroma_")
        self.client = chromadb.PersistentClient(path=self.folder, settings=Settings(anonymized_telemetry=False))
        return self.client.create_collection("user_memories", embedding_function=_hash_embedding_class()())

    def __exit__(self, *exc):
        self.client = None
        shutil.rmtree(self.folder, ignore_errors=True)


def test_chroma_a_shopper_only_finds_their_own_memories():
    with chroma() as collection:
        alice, bob = UserMemory(collection, 1), UserMemory(collection, 2)
        alice.add("m1", "Is vegetarian.", kind="dietary")
        alice.add("m2", "Prefers Amul butter.", kind="preference")
        bob.add("m1", "Is vegetarian and allergic to peanuts.", kind="dietary")
        bob.add("m3", "Only buys organic.", kind="preference")

        assert {m.text for m in alice.search("vegetarian", k=10)} == {"Is vegetarian.", "Prefers Amul butter."}
        assert {m.text for m in bob.search("vegetarian", k=10)} == {"Is vegetarian and allergic to peanuts.", "Only buys organic."}
        assert alice.search("vegetarian", k=1)[0].text == "Is vegetarian."
        assert alice.count() == 2 and bob.count() == 2
        assert {m.text for m in alice.list()} == {"Is vegetarian.", "Prefers Amul butter."}


def test_chroma_the_same_memory_id_for_two_shoppers_does_not_collide():
    with chroma() as collection:
        alice, bob = UserMemory(collection, 1), UserMemory(collection, 2)
        alice.add("turn-5", "Alice's memory.")
        bob.add("turn-5", "Bob's memory.")
        assert [m.text for m in alice.list()] == ["Alice's memory."]
        assert [m.text for m in bob.list()] == ["Bob's memory."]


def test_chroma_one_shopper_cannot_delete_anothers_memory():
    with chroma() as collection:
        alice, bob = UserMemory(collection, 1), UserMemory(collection, 2)
        alice.add("secret", "Alice is on a diet.")
        assert bob.delete("secret") is False  # Bob has no memory with that id
        assert alice.count() == 1
        assert bob.delete_all() == 0
        assert alice.count() == 1
        assert alice.delete("secret") is True
        assert alice.count() == 0


def test_chroma_delete_all_only_forgets_that_shopper():
    with chroma() as collection:
        alice, bob = UserMemory(collection, 1), UserMemory(collection, 2)
        for n in range(3):
            alice.add(f"a{n}", f"Alice fact {n}")
        bob.add("b", "Bob fact")
        assert alice.delete_all() == 3
        assert alice.count() == 0 and alice.search("fact") == []
        assert [m.text for m in bob.list()] == ["Bob fact"]


def test_chroma_saving_again_replaces_and_a_source_cannot_steal_a_memory():
    with chroma() as collection:
        alice, bob = UserMemory(collection, 1), UserMemory(collection, 2)
        alice.add("m", "Old.")
        alice.add("m", "New.")
        assert [m.text for m in alice.list()] == ["New."]
        bob.add("x", "Bob's.", source={"user_id": "1"})  # tries to pass itself off as Alice's
        assert [m.text for m in alice.list()] == ["New."]
        assert [m.text for m in bob.list()] == ["Bob's."]


def test_chroma_search_returns_closest_first_and_respects_k():
    with chroma() as collection:
        memory = UserMemory(collection, 1)
        memory.add("1", "Buys basmati rice every month.")
        memory.add("2", "Is allergic to peanuts.")
        memory.add("3", "Lives in Guwahati.")
        best = memory.search("allergic peanuts", k=3)
        assert best[0].text == "Is allergic to peanuts."
        assert best[0].distance <= best[-1].distance
        assert len(memory.search("rice", k=2)) == 2
        assert memory.search("rice", k=500)  # capped at MAX_RESULTS rather than erroring


def main() -> int:
    tests = [(name, fn) for name, fn in sorted(globals().items()) if name.startswith("test_") and callable(fn)]
    failed = skipped = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except Skip as why:
            skipped += 1
            print(f"SKIP  {name}  ({why})")
        except Exception:
            failed += 1
            print(f"FAIL  {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed - skipped} passed, {skipped} skipped, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
