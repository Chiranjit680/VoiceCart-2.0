"""Reads the shopper's own profile (age, preferences, medical conditions) from the Product Service.

The request is made with the shopper's own token, so the Product Service decides whose profile comes back; the
agent never names a user. A failure is not fatal: the conversation just carries on without the profile.
"""
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger("voicecart.agent")

TIMEOUT_SECONDS = 3.0
MAX_ENTRIES = 30
MAX_ENTRY_CHARS = 80


def format_profile(data: dict) -> str:
    """The profile as one short paragraph for the prompt, or "" when the shopper has not filled anything in."""
    parts = []
    age = data.get("age")
    if isinstance(age, int) and not isinstance(age, bool):
        parts.append(f"Age: {age}.")
    for label, key in (("Preferences", "preferences"), ("Medical conditions", "medical_conditions")):
        entries = [" ".join(str(e).split())[:MAX_ENTRY_CHARS] for e in (data.get(key) or [])[:MAX_ENTRIES]]
        entries = [e for e in entries if e]
        if entries:
            parts.append(f"{label}: {'; '.join(entries)}.")
    return " ".join(parts)


async def fetch_profile(
    authorization: str, *, url: Optional[str] = None, client: Optional[httpx.AsyncClient] = None
) -> Optional[str]:
    """The formatted profile ("" if empty), or None if it could not be fetched (so the caller can try again later)."""
    base = (url or os.getenv("PRODUCT_SERVICE_URL", "http://localhost:8000")).rstrip("/")
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=TIMEOUT_SECONDS)
    try:
        response = await client.get(f"{base}/profile", headers={"Authorization": authorization})
        response.raise_for_status()
        data = response.json()
        return format_profile(data) if isinstance(data, dict) else None
    except (httpx.HTTPError, ValueError) as error:
        logger.warning("Could not fetch the shopper's profile: %s", type(error).__name__)  # never log the response
        return None
    finally:
        if owns_client:
            await client.aclose()
