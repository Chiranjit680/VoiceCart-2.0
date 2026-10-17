"""
Memory service: the background judge plus a small HTTP API over the memories.

This process is the only one that opens Chroma (a persistent Chroma folder belongs to one process), so the agent
and the Product Service reach memories through the routes below instead of touching the folder.

Run from the repo root, on this machine only:
    uvicorn longterm_memory.api:create_app --factory --host 127.0.0.1 --port 8005

Every request must carry `X-Memory-Key: <MEMORY_SERVICE_KEY>`. The shopper's id is in the path and is trusted
because only callers that hold the key (the agent and the Product Service) can reach the API, and they take the id
from a verified login. The service refuses to start without a key.
"""
import hmac
import logging
import threading
from contextlib import asynccontextmanager
from typing import Any, Callable, List, Optional

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Path, Query, Request, Response
from pydantic import BaseModel, Field

from .memory import build_service, service_key
from .user_memory import MAX_RESULTS, Memory, UserMemory

logger = logging.getLogger("voicecart.memory")


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    k: int = Field(default=5, ge=1, le=MAX_RESULTS)


class MemoryOut(BaseModel):
    id: str
    text: str
    kind: str
    created_at: float
    distance: Optional[float] = None


def _out(memory: Memory) -> MemoryOut:
    return MemoryOut(id=memory.id, text=memory.text, kind=memory.kind, created_at=memory.created_at, distance=memory.distance)


def require_key(request: Request, x_memory_key: Optional[str] = Header(default=None)) -> None:
    expected: str = request.app.state.key
    if not x_memory_key or not hmac.compare_digest(x_memory_key.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Missing or wrong memory service key")


router = APIRouter(dependencies=[Depends(require_key)])


def _memory(request: Request, user_id: int) -> UserMemory:
    return UserMemory(request.app.state.get_collection(), user_id)


@router.post("/users/{user_id}/search", response_model=List[MemoryOut])
def search(request: Request, body: SearchRequest, user_id: int = Path(ge=1)):
    """The shopper's memories closest in meaning to the query, best first."""
    return [_out(m) for m in _memory(request, user_id).search(body.query, body.k)]


@router.get("/users/{user_id}/memories", response_model=List[MemoryOut])
def list_memories(request: Request, user_id: int = Path(ge=1), limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
    return [_out(m) for m in _memory(request, user_id).list(limit, offset)]


@router.delete("/users/{user_id}/memories/{memory_id}", status_code=204)
def delete_memory(request: Request, memory_id: str = Path(pattern=r"^[A-Za-z0-9_:-]{1,64}$"), user_id: int = Path(ge=1)):
    if not _memory(request, user_id).delete(memory_id):
        raise HTTPException(status_code=404, detail="No such memory")
    return Response(status_code=204)


@router.delete("/users/{user_id}/memories")
def forget_everything(request: Request, user_id: int = Path(ge=1)):
    return {"deleted": _memory(request, user_id).delete_all()}


def create_app(
    *,
    key: Optional[str] = None,
    get_collection: Optional[Callable[[], Any]] = None,
    run_poller: bool = True,
) -> FastAPI:
    """Build the app. Tests pass their own key and collection and switch the poller off."""
    key = key or service_key()
    if not key:
        raise RuntimeError(
            "Set MEMORY_SERVICE_KEY (environment or the root .env). Generate one with: "
            'python -c "import secrets; print(secrets.token_urlsafe(32))"'
        )
    if get_collection is None:
        from .vector_db import get_memories_collection

        get_collection = get_memories_collection

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        stop = threading.Event()
        poller: Optional[threading.Thread] = None
        if run_poller:
            service = build_service()
            service.ensure_schema()  # fail at startup, with the fix, if the Product Service has not added the columns
            poller = threading.Thread(target=service.run_forever, args=(stop,), name="memory-poller", daemon=True)
            poller.start()
        app.state.poller = poller
        yield
        stop.set()
        if poller:
            poller.join(timeout=5)

    app = FastAPI(title="VoiceCart memory service", lifespan=lifespan)
    app.state.key = key
    app.state.poller = None  # set at startup when the poller runs
    app.state.get_collection = get_collection
    app.include_router(router)

    @app.get("/health")
    def health(request: Request):
        poller = request.app.state.poller
        return {"ok": True, "poller_running": bool(poller and poller.is_alive())}

    return app
