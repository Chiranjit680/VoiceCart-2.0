"""The first node of every turn: fetch what this shopper has told us in earlier conversations."""
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from ..memory_client import recall
from ..state import AgentState
from ..toolresult import text
from ..trace import note as trace_note

NAME = "memory"


async def memory_node(state: AgentState, config: RunnableConfig) -> dict:
    """Look up the shopper's memories that fit what they just said, and put them in the state for the agents.

    The shopper is the VERIFIED user id the request handler puts in the run's config (`configurable.user_id`);
    it is never taken from the conversation. `memories` is always written, even when empty, so one turn's
    memories can never linger into the next. A memory service that is off or slow just means none this turn.
    """
    profile = state.get("profile")
    trace_note(config, "PROFILE: " + ("not loaded (none fetched yet)" if profile is None else "empty" if not profile else f"loaded: {profile}"))
    user_id = (config.get("configurable") or {}).get("user_id")
    latest = next((m for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), None)

    if user_id is None or latest is None:
        trace_note(config, "MEMORY: no verified shopper or nothing said yet, none fetched")
        return {"memories": []}

    memories = await recall(user_id, text(latest.content))
    trace_note(config, f"MEMORY: fetched {len(memories)} for shopper {user_id}" + (": " + " | ".join(memories) if memories else ""))
    return {"memories": memories}
