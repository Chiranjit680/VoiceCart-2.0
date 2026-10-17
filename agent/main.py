"""
VoiceCart agent service (port 8002).

POST /agent/{user_id}  {"msg": "..."}
    Authorization: Bearer <user jwt>
    X-Session-Id: <chat session id from the Product Service>
  -> {"response": "...", "products": [product cards to show, see cards.py]}

Each request loads the Product Service tools from the MCP server with the user's token, so every
tool call acts as that user. Conversation state is checkpointed in Postgres under the session id,
so it survives restarts, and the readable transcript is saved through the Product Service.

Run from the VoiceCart-2.0 folder (the loop option is needed on Windows, see agent/loop.py):
    uvicorn agent.main:app --port 8002 --loop agent.loop:selector_loop_factory
"""
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

import httpx
from dotenv import dotenv_values
from fastapi import FastAPI, Header, Request
from langchain_core.messages import AIMessage, HumanMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel

from . import llm  # noqa: F401  (loads agent/.env)
from .graph import build_graph

ROOT_ENV = Path(__file__).resolve().parent.parent / ".env"
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8004/mcp")
PRODUCT_SERVICE_URL = os.getenv("PRODUCT_SERVICE_URL", "http://localhost:8000").rstrip("/")

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger("voicecart.agent")


def database_url() -> str:
    """Postgres URL for the conversation store: AGENT_DATABASE_URL, else the repo's root .env `database_url`."""
    url = os.getenv("AGENT_DATABASE_URL") or dotenv_values(ROOT_ENV).get("database_url")
    if not url:
        raise RuntimeError("Set AGENT_DATABASE_URL in agent/.env (or database_url in the root .env).")
    # SQLAlchemy-style driver suffixes are not valid for psycopg itself.
    return url.replace("postgresql+psycopg2://", "postgresql://").replace("postgresql+psycopg://", "postgresql://")


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = AsyncConnectionPool(
        database_url(),
        open=False,
        min_size=1,
        max_size=5,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    )
    await pool.open(wait=True, timeout=15)
    app.state.checkpointer = AsyncPostgresSaver(pool)
    await app.state.checkpointer.setup()  # creates the checkpoint tables on first run
    logger.info("Conversation store ready (Postgres)")
    yield
    await pool.close()


app = FastAPI(lifespan=lifespan)


class AgentRequest(BaseModel):
    msg: str


async def check_session(session_id: str, authorization: str) -> Optional[str]:
    """Ask the Product Service whether this token owns the session. Returns a sentence to speak if not."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{PRODUCT_SERVICE_URL}/chat/sessions/{session_id}/status", headers={"Authorization": authorization}
            )
    except httpx.HTTPError:
        logger.exception("Product Service unreachable")
        return "Sorry, the store is not reachable right now. Please try again in a moment."
    if response.status_code == 401:
        return "Your login has expired. Please log in again."
    if response.status_code == 404:
        return "That conversation is no longer available. Please reconnect."
    if response.status_code >= 400:
        logger.error("Session check failed: %s %s", response.status_code, response.text[:200])
        return "Sorry, something went wrong on my side. Please try again."
    return None


async def save_turns(session_id: str, authorization: str, turns: List[dict]) -> None:
    """Write the exchange to the transcript. Best effort: a failure here must never cost the user their answer."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{PRODUCT_SERVICE_URL}/chat/sessions/{session_id}/turns",
                json={"messages": turns},
                headers={"Authorization": authorization},
            )
            response.raise_for_status()
    except Exception:
        logger.exception("Could not save transcript for session %s", session_id)


@app.post("/agent/{user_id}")
async def run_agent(
    user_id: str,
    body: AgentRequest,
    request: Request,
    authorization: Optional[str] = Header(default=None),
    x_session_id: str = Header(),
):
    if not authorization or not authorization.lower().startswith("bearer "):
        return {"response": "Please log in first so I can help with your shopping."}

    problem = await check_session(x_session_id, authorization)
    if problem:
        return {"response": problem}

    client = MultiServerMCPClient(
        {"voicecart": {"transport": "streamable_http", "url": MCP_SERVER_URL, "headers": {"Authorization": authorization}}}
    )
    # The session id is the thread: every connection starts fresh, a quick reconnect continues it.
    config = {"configurable": {"thread_id": x_session_id}, "recursion_limit": 40}
    user_turn = {"role": "user", "content": body.msg}

    try:
        graph = build_graph(await client.get_tools(), request.app.state.checkpointer)
        before = len((await graph.aget_state(config)).values.get("messages", []))
        result = await graph.ainvoke(
            {"messages": [HumanMessage(body.msg)], "hops": 0, "visited": [], "products": []}, config
        )
    except Exception:
        logger.exception("Agent run failed for user %s", user_id)
        apology = "Sorry, something went wrong on my side. Please try again."
        await save_turns(x_session_id, authorization, [user_turn, {"role": "assistant", "content": apology}])
        return {"response": apology}

    # Everything the agents said this turn, e.g. a recipe followed by its shopping list.
    new_messages = result["messages"][before + 1:]
    replies = [m for m in new_messages if isinstance(m, AIMessage) and m.content]
    for m in new_messages:
        logger.info("[%s] %s", getattr(m, "name", None) or m.type, m.content)

    response = " ".join(m.content for m in replies) or "Sorry, I didn't catch that. Could you say it again?"
    await save_turns(
        x_session_id,
        authorization,
        [user_turn, *({"role": "assistant", "agent": m.name, "content": m.content} for m in replies)]
        if replies
        else [user_turn, {"role": "assistant", "content": response}],
    )
    return {"response": response, "products": result.get("products", [])}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("agent.main:app", port=8002, loop="agent.loop:selector_loop_factory")
