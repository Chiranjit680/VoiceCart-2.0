"""Housekeeping for chat sessions: close idle ones, delete expired ones, and remove the agent's saved state."""
import asyncio
import logging
from datetime import timedelta
from typing import List

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from .. import database, models
from ..config import settings

logger = logging.getLogger("voicecart.chat")

# Tables created by LangGraph's PostgresSaver (agent service). The agent uses a session's id as its thread id.
CHECKPOINT_TABLES = ("checkpoint_writes", "checkpoint_blobs", "checkpoints")


def delete_checkpoints(db: Session, thread_ids: List[str]) -> None:
    """Remove the agent's saved conversation state. A no-op until the agent has created its tables."""
    if not thread_ids:
        return
    for table in CHECKPOINT_TABLES:
        if db.execute(text("SELECT to_regclass(:name)"), {"name": f"public.{table}"}).scalar():
            db.execute(
                text(f"DELETE FROM {table} WHERE thread_id = ANY(CAST(:ids AS text[]))"),  # table names are constants
                {"ids": thread_ids},
            )


def delete_sessions(db: Session, session_ids: List[str]) -> None:
    """Delete sessions with their transcripts and agent state. The caller commits."""
    if not session_ids:
        return
    delete_checkpoints(db, session_ids)
    db.query(models.ChatSession).filter(models.ChatSession.id.in_(session_ids)).delete(synchronize_session=False)


def close_idle_sessions(db: Session) -> int:
    """Close sessions nobody has touched for `chat_idle_minutes` (e.g. the gateway crashed without ending them)."""
    closed = (
        db.query(models.ChatSession)
        .filter(
            models.ChatSession.ended_at.is_(None),
            models.ChatSession.last_activity_at < func.now() - timedelta(minutes=settings.chat_idle_minutes),
        )
        .update({"ended_at": func.now(), "end_reason": "idle"}, synchronize_session=False)
    )
    db.commit()
    return closed


def purge_old_sessions(db: Session) -> int:
    """Delete sessions that started more than `chat_retention_days` ago."""
    if settings.chat_retention_days <= 0:  # 0 disables retention
        return 0
    ids = [
        row.id
        for row in db.query(models.ChatSession.id).filter(
            models.ChatSession.started_at < func.now() - timedelta(days=settings.chat_retention_days)
        )
    ]
    delete_sessions(db, ids)
    db.commit()
    return len(ids)


def _run_once(purge: bool) -> None:
    db = database.SessionLocal()
    try:
        closed = close_idle_sessions(db)
        if closed:
            logger.info("Closed %d idle chat session(s)", closed)
        if purge:
            purged = purge_old_sessions(db)
            if purged:
                logger.info("Deleted %d chat session(s) past retention", purged)
    except Exception:
        db.rollback()
        logger.exception("Chat maintenance failed")
    finally:
        db.close()


async def maintenance_loop(interval_seconds: int = 60, purge_every: int = 60) -> None:
    """Close idle sessions every minute and purge expired ones about hourly, until cancelled."""
    tick = 0
    while True:
        await asyncio.to_thread(_run_once, tick % purge_every == 0)
        tick += 1
        await asyncio.sleep(interval_seconds)
