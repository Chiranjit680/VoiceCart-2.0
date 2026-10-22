from typing import List, Optional, TypedDict

from langchain_core.messages import BaseMessage, trim_messages
from langgraph.graph import MessagesState


class ListItem(TypedDict):
    item: str
    qty: int
    product_id: Optional[int]
    product_name: Optional[str]
    price: Optional[float]


class AgentState(MessagesState):
    # Supervisor hops taken in the current turn (reset on every user message).
    hops: int
    # Specialists already run in the current turn (reset on every user message).
    visited: List[str]
    # Instruction the supervisor wrote for the subagent it routed to.
    task: str
    # Raw tool output from the last subagent step, so later steps can resolve "that one".
    scratch: str
    # What this shopper told us in earlier conversations (from the memory service), fetched at the start of each turn.
    memories: List[str]
    # What the shopper entered in their own profile (age, preferences, medical conditions), as a short paragraph.
    # Fetched once at the start of the conversation: None = not fetched yet, "" = fetched and empty.
    profile: Optional[str]
    # Product cards the reply should show, rebuilt every turn (see cards.py).
    products: List[dict]
    # Shopping list waiting for the user to confirm, change or cancel.
    pending_list: Optional[List[ListItem]]


def recent(messages: List[BaseMessage], max_messages: int = 20) -> List[BaseMessage]:
    """Last few messages of the conversation, starting on a user message."""
    return trim_messages(
        messages, strategy="last", token_counter=len, max_tokens=max_messages, start_on="human"
    )
