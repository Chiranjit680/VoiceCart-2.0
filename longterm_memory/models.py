"""The small data types shared by the memory service's parts."""
from dataclasses import dataclass
from typing import Protocol, Sequence


@dataclass(frozen=True)
class Turn:
    """One row of chat_turns, with the user it belongs to."""
    id: int
    session_id: str
    seq: int
    role: str  # "user" | "assistant"
    content: str
    user_id: int


@dataclass(frozen=True)
class Verdict:
    remember: bool
    memory: str = ""  # one self-contained sentence about the shopper
    kind: str = "other"


class Judge(Protocol):
    def judge(self, turn: Turn, context: Sequence[Turn]) -> Verdict:
        """Whether `turn` (a shopper's message) belongs in long-term memory. `context` is what came before it."""


class MemoryStore(Protocol):
    def add(self, *, memory_id: str, user_id: int, text: str, kind: str, source: dict) -> None:
        """Save one memory. Saving the same `memory_id` again must replace it, not duplicate it."""
