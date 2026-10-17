"""
The only way to read or write a shopper's long-term memories.

`UserMemory(collection, user_id)` is bound to ONE shopper. Every call it makes to Chroma carries that shopper's
filter, so a caller cannot forget it, and nothing outside this module should touch the collection directly.

Three layers keep shoppers apart, so a slip in one does not leak:
  1. every query, listing and delete is filtered on the shopper's id;
  2. a memory's id inside Chroma is prefixed with the shopper's id, so one shopper can never overwrite or delete
     another's memory, even by guessing its id;
  3. anything that comes back and is not this shopper's is dropped.
"""
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("voicecart.memory")

MAX_RESULTS = 10  # most memories one search returns
MAX_TEXT = 500  # longest memory text kept

_RESERVED = {"user_id", "kind", "created_at"}  # metadata keys this class owns; callers cannot set them


class InvalidUserError(ValueError):
    """The user id is not a positive whole number."""


def user_key(user_id: Any) -> str:
    """The id as stored: a positive integer written as text. Anything else is refused, never guessed at."""
    if isinstance(user_id, bool) or not isinstance(user_id, (int, str)):
        raise InvalidUserError(f"not a user id: {user_id!r}")
    text = str(user_id).strip()
    if not text.isdigit() or int(text) <= 0:
        raise InvalidUserError(f"not a user id: {user_id!r}")
    return str(int(text))  # "007" and 7 are the same shopper


@dataclass(frozen=True)
class Memory:
    id: str
    text: str
    kind: str
    created_at: float
    source: Dict[str, Any] = field(default_factory=dict)
    distance: Optional[float] = None  # for search results: smaller means closer to the query


class UserMemory:
    def __init__(self, collection: Any, user_id: Any):
        self._collection = collection
        self.user_key = user_key(user_id)
        self._where = {"user_id": self.user_key}
        self._prefix = f"u{self.user_key}:"

    def _stored_id(self, memory_id: str) -> str:
        return f"{self._prefix}{memory_id}"

    def _to_memory(self, stored_id: str, text: Optional[str], metadata: Optional[dict], distance: Optional[float] = None) -> Optional[Memory]:
        metadata = metadata or {}
        if metadata.get("user_id") != self.user_key:  # layer 3: never hand back someone else's memory
            logger.error("Dropped a memory that is not shopper %s's (id %s)", self.user_key, stored_id)
            return None
        return Memory(
            id=stored_id[len(self._prefix):] if stored_id.startswith(self._prefix) else stored_id,
            text=text or "",
            kind=str(metadata.get("kind", "other")),
            created_at=float(metadata.get("created_at", 0.0)),
            source={k: v for k, v in metadata.items() if k not in _RESERVED},
            distance=distance,
        )

    def add(self, memory_id: str, text: str, kind: str = "other", source: Optional[Dict[str, Any]] = None) -> str:
        """Save a memory, or replace the one with this id. Returns the id."""
        text = text.strip()[:MAX_TEXT]
        if not text:
            raise ValueError("A memory needs some text")
        # `source` goes first so it can never override the keys this class owns.
        metadata = {**(source or {}), "user_id": self.user_key, "kind": kind, "created_at": time.time()}
        self._collection.upsert(ids=[self._stored_id(memory_id)], documents=[text], metadatas=[metadata])
        return memory_id

    def search(self, query: str, k: int = 5) -> List[Memory]:
        """This shopper's memories closest in meaning to `query`, best first."""
        query = query.strip()
        if not query:
            return []
        result = self._collection.query(
            query_texts=[query],
            n_results=max(1, min(int(k), MAX_RESULTS)),
            where=self._where,
            include=["documents", "metadatas", "distances"],
        )
        found = zip(result["ids"][0], result["documents"][0], result["metadatas"][0], result["distances"][0])
        return [m for m in (self._to_memory(i, d, md, dist) for i, d, md, dist in found) if m]

    def list(self, limit: int = 100, offset: int = 0) -> List[Memory]:
        """This shopper's memories, newest first. (One shopper has few, so they are sorted here rather than in Chroma.)"""
        result = self._collection.get(where=self._where, include=["documents", "metadatas"])
        memories = [m for m in (self._to_memory(i, d, md) for i, d, md in zip(result["ids"], result["documents"], result["metadatas"])) if m]
        memories.sort(key=lambda m: m.created_at, reverse=True)
        return memories[max(0, offset): max(0, offset) + max(0, limit)]

    def count(self) -> int:
        return len(self._collection.get(where=self._where, include=[])["ids"])

    def delete(self, memory_id: str) -> bool:
        """Delete one of this shopper's memories. False if there is no such memory of theirs."""
        stored = self._stored_id(memory_id)
        if not self._collection.get(ids=[stored], where=self._where, include=[])["ids"]:
            return False
        self._collection.delete(ids=[stored], where=self._where)
        return True

    def delete_all(self) -> int:
        """Forget everything about this shopper. Returns how many memories were deleted."""
        ids = self._collection.get(where=self._where, include=[])["ids"]
        if ids:
            self._collection.delete(ids=ids, where=self._where)
        return len(ids)
