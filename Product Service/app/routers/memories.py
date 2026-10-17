"""
What the shopper can see and delete of their own long-term memory.

The memory service is not reachable from a browser (it needs a secret key), so these routes sit in front of it:
the shopper's login decides whose memories are touched, and the service is called with that verified id.
"""
import logging
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path, Response, status

from .. import oauth2, schemas
from ..config import settings

logger = logging.getLogger("voicecart.memories")

router = APIRouter(prefix="/memories", tags=["memories"])


def call_memory_service(method: str, path: str) -> httpx.Response:
    """One request to the memory service with the shared key. A separate function so tests can replace it."""
    if not settings.memory_service_key:
        raise HTTPException(status_code=503, detail="Long-term memory is not set up")
    try:
        with httpx.Client(base_url=settings.memory_service_url, timeout=5.0) as client:
            return client.request(method, path, headers={"X-Memory-Key": settings.memory_service_key})
    except httpx.HTTPError:
        logger.exception("Memory service unreachable")
        raise HTTPException(status_code=503, detail="Long-term memory is not available right now")


def _checked(response: httpx.Response) -> httpx.Response:
    if response.status_code in (401, 403):  # our key is wrong: a setup problem, not the shopper's
        logger.error("Memory service refused our key")
        raise HTTPException(status_code=503, detail="Long-term memory is not set up correctly")
    return response


@router.get("")
def list_my_memories(current_user: schemas.UserOut = Depends(oauth2.get_current_user)) -> Any:
    """Everything remembered about the logged-in shopper, newest first."""
    response = _checked(call_memory_service("GET", f"/users/{current_user.id}/memories"))
    response.raise_for_status()
    return response.json()


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
def forget_one(memory_id: str = Path(pattern=r"^[A-Za-z0-9_:-]{1,64}$"), current_user: schemas.UserOut = Depends(oauth2.get_current_user)):
    response = _checked(call_memory_service("DELETE", f"/users/{current_user.id}/memories/{memory_id}"))
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="No such memory")
    response.raise_for_status()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("")
def forget_everything(current_user: schemas.UserOut = Depends(oauth2.get_current_user)) -> Any:
    """Forget everything about the logged-in shopper."""
    response = _checked(call_memory_service("DELETE", f"/users/{current_user.id}/memories"))
    response.raise_for_status()
    return response.json()
