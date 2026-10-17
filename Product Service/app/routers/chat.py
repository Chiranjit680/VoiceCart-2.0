"""
Voice chat sessions and transcripts.

A session is one voice conversation: a single WebSocket connection, or a reconnect within
`chat_resume_minutes` of the last disconnect (so a network blip doesn't wipe the conversation).
The manager opens/ends sessions; the agent appends turns. Every route is scoped to the
logged-in user, so nobody can read or write another user's sessions.
"""
import uuid
from datetime import timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from .. import database, models, oauth2, schemas
from ..config import settings
from ..utils.chat_maintenance import delete_sessions

router = APIRouter(prefix="/chat", tags=["chat"])


def _own_session(db: Session, session_id: str, user: models.User, lock: bool = False) -> models.ChatSession:
    query = db.query(models.ChatSession).filter(
        models.ChatSession.id == session_id, models.ChatSession.user_id == user.id
    )
    if lock:
        query = query.with_for_update()
    session = query.first()
    if session is None:
        # Same answer for "does not exist" and "belongs to someone else".
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.post("/sessions/open", response_model=schemas.ChatSessionOpened)
def open_session(db: Session = Depends(database.get_db), current_user: models.User = Depends(oauth2.get_current_user)):
    """Start a conversation, or continue the one that just ended if it ended within the resume window.

    Sessions that are still open are never reused, so two tabs get two separate conversations.
    """
    recent = (
        db.query(models.ChatSession)
        .filter(
            models.ChatSession.user_id == current_user.id,
            models.ChatSession.ended_at.isnot(None),
            models.ChatSession.ended_at >= func.now() - timedelta(minutes=settings.chat_resume_minutes),
        )
        .order_by(models.ChatSession.ended_at.desc())
        .with_for_update()
        .first()
    )
    if recent:
        recent.ended_at = None
        recent.end_reason = None
        recent.last_activity_at = func.now()
        db.commit()
        return schemas.ChatSessionOpened(id=recent.id, resumed=True)

    session = models.ChatSession(id=str(uuid.uuid4()), user_id=current_user.id)
    db.add(session)
    db.commit()
    return schemas.ChatSessionOpened(id=session.id, resumed=False)


@router.get("/sessions/{session_id}/status", response_model=schemas.ChatSessionStatus)
def session_status(
    session_id: str,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """Cheap ownership check the agent runs before spending model tokens on a request."""
    session = _own_session(db, session_id, current_user)
    return schemas.ChatSessionStatus(id=session.id, ended=session.ended_at is not None, user_id=session.user_id)


@router.post("/sessions/{session_id}/turns", status_code=status.HTTP_204_NO_CONTENT)
def add_turns(
    session_id: str,
    body: schemas.ChatTurnsIn,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    # The row lock serialises concurrent writers, so `seq` stays gap-free and unique.
    session = _own_session(db, session_id, current_user, lock=True)
    last_seq = (
        db.query(func.coalesce(func.max(models.ChatTurn.seq), 0))
        .filter(models.ChatTurn.session_id == session.id)
        .scalar()
    )
    for offset, message in enumerate(body.messages, start=1):
        db.add(
            models.ChatTurn(
                session_id=session.id,
                seq=last_seq + offset,
                role=message.role,
                agent=message.agent,
                content=message.content,
            )
        )
    session.turn_count += sum(1 for m in body.messages if m.role == "user")
    session.last_activity_at = func.now()
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/sessions/{session_id}/end", status_code=status.HTTP_204_NO_CONTENT)
def end_session(
    session_id: str,
    body: schemas.ChatSessionEnd = schemas.ChatSessionEnd(),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    session = _own_session(db, session_id, current_user, lock=True)
    if session.ended_at is None:  # ending twice is harmless
        session.ended_at = func.now()
        session.end_reason = body.reason
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/sessions", response_model=List[schemas.ChatSessionOut])
def list_sessions(
    limit: int = 20,
    skip: int = 0,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """The current user's conversations, newest first."""
    return (
        db.query(models.ChatSession)
        .filter(models.ChatSession.user_id == current_user.id)
        .order_by(models.ChatSession.started_at.desc())
        .offset(max(skip, 0))
        .limit(min(max(limit, 1), 100))
        .all()
    )


@router.get("/sessions/{session_id}", response_model=schemas.ChatSessionDetail)
def get_session(
    session_id: str,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    session = (
        db.query(models.ChatSession)
        .options(joinedload(models.ChatSession.turns))
        .filter(models.ChatSession.id == session_id, models.ChatSession.user_id == current_user.id)
        .first()
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    session_id: str,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """Delete a conversation: its transcript and the agent's saved state for it."""
    session = _own_session(db, session_id, current_user)
    delete_sessions(db, [session.id])
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
