"""Chroma client for VoiceCart's long-term memory.

The data is kept on disk, so it survives restarts. Where it lives:
    LONGTERM_MEMORY_DIR   folder for the database (default: longterm_memory/chroma_data next to this file)

A persistent Chroma database belongs to one process at a time. Use `get_client()` everywhere instead of
creating clients, so the process shares a single one.
"""
import os
from functools import lru_cache
from pathlib import Path

import chromadb
from chromadb.api import ClientAPI
from chromadb.config import Settings

from .user_memory import UserMemory

DEFAULT_PERSIST_PATH = Path(__file__).resolve().parent / "chroma_data"


def persist_path() -> Path:
    """Folder where Chroma stores its data."""
    return Path(os.getenv("LONGTERM_MEMORY_DIR") or DEFAULT_PERSIST_PATH).expanduser().resolve()


MEMORIES_COLLECTION = "user_memories"


@lru_cache(maxsize=1)
def get_client() -> ClientAPI:
    """The process-wide persistent Chroma client. Creates the folder on first use."""
    path = persist_path()
    path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(
        path=str(path),
        # Memories are personal data: never send usage statistics anywhere.
        settings=Settings(anonymized_telemetry=False),
    )


def get_memories_collection():
    """The one collection that holds every shopper's memories. Reach it only through `UserMemory`."""
    return get_client().get_or_create_collection(MEMORIES_COLLECTION)


class ChromaMemoryStore:
    """Where the memory service saves memories. Writes go through `UserMemory`, which tags and prefixes each one
    with its shopper, so reading them back is always limited to one shopper too."""

    def __init__(self, collection=None):
        self._collection = collection  # tests pass their own; otherwise it is opened on first use

    @property
    def collection(self):
        if self._collection is None:
            self._collection = get_memories_collection()
        return self._collection

    def add(self, *, memory_id: str, user_id: int, text: str, kind: str, source: dict) -> None:
        # Saving the same memory_id again replaces it, so a retry never creates a duplicate.
        UserMemory(self.collection, user_id).add(memory_id=memory_id, text=text, kind=kind, source=source)
