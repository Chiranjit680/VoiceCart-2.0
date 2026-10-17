"""
Long-term memory service.

A background loop that looks at conversation turns nobody has looked at yet (chat_turns.checked = false),
decides whether each one belongs in long-term memory, saves those that do to Chroma, and flags the row:

    checked  = true      the service has looked at this turn (so it is never looked at again)
    longterm = true      the turn was saved to long-term memory

Only what the shopper said can become a memory; the assistant's replies are marked checked straight away.
A turn the judge fails on (for example the model is unreachable) stays unchecked and is tried again.

Run it from the repo root:
    python -m longterm_memory.memory               keep running, polling for new turns
    python -m longterm_memory.memory --once        process one batch and stop
    python -m longterm_memory.memory --dry-run     show what it WOULD remember; changes nothing

Settings (environment or agent/.env): MEMORY_POLL_SECONDS (60), MEMORY_BATCH_SIZE (20),
MEMORY_CONTEXT_TURNS (4, how many earlier turns the judge sees), MEMORY_DATABASE_URL (default: the
root .env's database_url). Chroma's location is set in vector_db.py.

The columns are added by the Product Service when it starts (Product Service/app/migrations.py).
"""
import argparse
import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Sequence

import psycopg
from dotenv import dotenv_values

from .models import Judge, MemoryStore, Turn

logger = logging.getLogger("voicecart.memory")

ROOT_ENV = Path(__file__).resolve().parent.parent / ".env"

UNCHECKED_SQL = """
    SELECT t.id, t.session_id, t.seq, t.role, t.content, s.user_id
    FROM chat_turns t
    JOIN chat_sessions s ON s.id = t.session_id
    WHERE t.checked = false
    ORDER BY t.id
    LIMIT %s
"""

CONTEXT_SQL = """
    SELECT t.id, t.session_id, t.seq, t.role, t.content, s.user_id
    FROM chat_turns t
    JOIN chat_sessions s ON s.id = t.session_id
    WHERE t.session_id = %s AND t.seq < %s
    ORDER BY t.seq DESC
    LIMIT %s
"""

MARK_SQL = "UPDATE chat_turns SET checked = true, longterm = %s WHERE id = %s"


class SchemaError(RuntimeError):
    pass


@dataclass
class BatchResult:
    checked: int = 0  # turns flagged as looked at
    remembered: int = 0  # of those, saved to long-term memory
    failed: int = 0  # left unchecked to be tried again


class NullStore:
    """Stands in for the real store in a dry run."""

    def add(self, **_: object) -> None:
        pass


class MemoryService:
    def __init__(
        self,
        connect: Callable[[], "psycopg.Connection"],
        judge: Judge,
        store: MemoryStore,
        batch_size: int = 20,
        context_turns: int = 4,
        poll_seconds: float = 60.0,
    ):
        self.connect = connect  # returns a new autocommit connection
        self.judge = judge
        self.store = store
        self.batch_size = batch_size
        self.context_turns = context_turns
        self.poll_seconds = poll_seconds

    def ensure_schema(self) -> None:
        """Fail early, with the fix, if the columns have not been added yet."""
        with self.connect() as conn:
            found = conn.execute(
                "SELECT count(*) FROM pg_attribute WHERE attrelid = to_regclass('chat_turns') "
                "AND attname IN ('checked', 'longterm') AND NOT attisdropped"
            ).fetchone()[0]
        if found != 2:
            raise SchemaError(
                "chat_turns has no checked/longterm columns yet. Start the Product Service once: "
                "it adds them when it starts (Product Service/app/migrations.py)."
            )

    def _context(self, conn: "psycopg.Connection", turn: Turn) -> List[Turn]:
        rows = conn.execute(CONTEXT_SQL, (turn.session_id, turn.seq, self.context_turns)).fetchall()
        return [Turn(*row) for row in reversed(rows)]  # oldest first

    def process_batch(self, dry_run: bool = False) -> BatchResult:
        """Look at up to `batch_size` unchecked turns. With dry_run nothing is saved or flagged."""
        result = BatchResult()
        with self.connect() as conn:
            turns = [Turn(*row) for row in conn.execute(UNCHECKED_SQL, (self.batch_size,)).fetchall()]
            for turn in turns:
                remember = False
                if turn.role == "user":
                    try:
                        verdict = self.judge.judge(turn, self._context(conn, turn))
                        remember = verdict.remember and bool(verdict.memory.strip())
                        if remember and not dry_run:
                            # A fixed id per turn, so saving it again after a crash replaces rather than duplicates.
                            self.store.add(
                                memory_id=f"turn-{turn.id}",
                                user_id=turn.user_id,
                                text=verdict.memory.strip(),
                                kind=verdict.kind,
                                source={"session_id": turn.session_id, "turn_id": turn.id},
                            )
                    except Exception:
                        logger.exception("Could not judge turn %s; it stays unchecked", turn.id)
                        result.failed += 1
                        continue
                    logger.info(
                        "turn %s (user %s): %s  <- %r",
                        turn.id, turn.user_id, f"REMEMBER [{verdict.kind}] {verdict.memory.strip()!r}" if remember else "skip", turn.content[:100],
                    )

                if not dry_run:
                    conn.execute(MARK_SQL, (remember, turn.id))  # autocommit: flagged as soon as it is done
                result.checked += 1
                result.remembered += remember
        return result

    def run_forever(self, stop: threading.Event) -> None:
        logger.info("Long-term memory service running (every %.0fs, batches of %d)", self.poll_seconds, self.batch_size)
        while not stop.is_set():
            wait = self.poll_seconds
            try:
                result = self.process_batch()
                if result.checked or result.failed:
                    logger.info("batch: %d checked, %d remembered, %d failed", result.checked, result.remembered, result.failed)
                if result.checked >= self.batch_size:
                    wait = 0  # a full batch means there is probably more waiting
                elif result.failed and not result.checked:
                    wait = self.poll_seconds * 2  # everything failed: the model or database is probably down
            except Exception:
                logger.exception("Batch failed")
                wait = self.poll_seconds * 2
            stop.wait(wait)


def database_url() -> str:
    url = os.getenv("MEMORY_DATABASE_URL") or dotenv_values(ROOT_ENV).get("database_url")
    if not url:
        raise RuntimeError("Set MEMORY_DATABASE_URL (or database_url in the root .env).")
    # SQLAlchemy-style driver suffixes are not valid for psycopg itself.
    return url.replace("postgresql+psycopg2://", "postgresql://").replace("postgresql+psycopg://", "postgresql://")


def _number(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


def service_key() -> Optional[str]:
    """The secret the web API requires from its callers (MEMORY_SERVICE_KEY, in the environment or the root .env)."""
    return os.getenv("MEMORY_SERVICE_KEY") or dotenv_values(ROOT_ENV).get("MEMORY_SERVICE_KEY") or None


def build_service(dry_run: bool = False, limit: Optional[int] = None) -> MemoryService:
    """The service wired to the real database, model and Chroma, with settings from the environment."""
    from .judge import LLMJudge  # imported here: it loads agent/.env and the model client

    url = database_url()
    if dry_run:
        store: MemoryStore = NullStore()  # a preview needs neither Chroma nor its install
    else:
        from .vector_db import ChromaMemoryStore

        store = ChromaMemoryStore()

    return MemoryService(
        connect=lambda: psycopg.connect(url, autocommit=True),
        judge=LLMJudge(),
        store=store,
        batch_size=limit or int(_number("MEMORY_BATCH_SIZE", 20)),
        context_turns=int(_number("MEMORY_CONTEXT_TURNS", 4)),
        poll_seconds=_number("MEMORY_POLL_SECONDS", 60),
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="VoiceCart long-term memory service")
    parser.add_argument("--once", action="store_true", help="process one batch, then stop")
    parser.add_argument("--dry-run", action="store_true", help="show what would be remembered; save and flag nothing")
    parser.add_argument("--limit", type=int, help="turns to look at in that batch (default MEMORY_BATCH_SIZE)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

    service = build_service(dry_run=args.dry_run, limit=args.limit)
    service.ensure_schema()

    if args.once or args.dry_run:
        result = service.process_batch(dry_run=args.dry_run)
        label = "would be" if args.dry_run else "were"
        print(f"{result.checked} turns {'looked at' if args.dry_run else 'checked'}, {result.remembered} {label} remembered, {result.failed} failed")
        return 0

    stop = threading.Event()
    try:
        service.run_forever(stop)
    except KeyboardInterrupt:
        stop.set()
        logger.info("Stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
