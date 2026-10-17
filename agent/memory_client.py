"""Asks the memory service what a shopper has told us in earlier conversations.

Memory is a nicety: if the service is off, slow or misconfigured, the shopper simply gets no memories and the
conversation carries on.
"""
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

import httpx
from dotenv import dotenv_values

logger = logging.getLogger("voicecart.agent")

ROOT_ENV = Path(__file__).resolve().parent.parent / ".env"
TIMEOUT_SECONDS = 1.5  # this sits in front of every reply, so it must be quick
MAX_MEMORY_CHARS = 200


@lru_cache(maxsize=1)
def _configured_key() -> Optional[str]:
    return os.getenv("MEMORY_SERVICE_KEY") or dotenv_values(ROOT_ENV).get("MEMORY_SERVICE_KEY") or None


def _configured_url() -> str:
    return os.getenv("MEMORY_SERVICE_URL", "http://127.0.0.1:8005").rstrip("/")


async def recall(
    user_id: int,
    query: str,
    *,
    k: int = 5,
    key: Optional[str] = None,
    url: Optional[str] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> List[str]:
    """The shopper's memories closest in meaning to `query`, as short sentences.

    `user_id` must be the VERIFIED id (from the Product Service's session check), never one taken from a URL.
    """
    key = key if key is not None else _configured_key()
    if not key:  # long-term memory is not set up
        return []
    base = (url or _configured_url()).rstrip("/")
    try:
        owns_client = client is None
        client = client or httpx.AsyncClient(timeout=TIMEOUT_SECONDS)
        try:
            response = await client.post(
                f"{base}/users/{int(user_id)}/search", json={"query": query, "k": k}, headers={"X-Memory-Key": key}
            )
        finally:
            if owns_client:
                await client.aclose()
        response.raise_for_status()
        texts = (str(item.get("text", "")).strip() for item in response.json())
        return [t[:MAX_MEMORY_CHARS] for t in texts if t]
    except Exception as error:
        logger.warning("No long-term memory this turn (%s: %s)", type(error).__name__, error)
        return []
