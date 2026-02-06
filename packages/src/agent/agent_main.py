
import operator
import json
from typing import TypedDict, Annotated, Literal, List, Optional
import uuid
import uuid

from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from sqlalchemy import Integer

class AgentConfig(BaseModel):
    name: str = Field(..., description="The name of the agent.")
    description: str = Field(..., description="A brief description of the agent's purpose and capabilities.")
    tools: List[str] = Field(..., description="A list of tools that the agent can use to accomplish its tasks.")

class AgentState(TypedDict):
    """State shared across all agents"""
    
    messages: Annotated[list[BaseMessage], "Conversation messages"]
    current_agent: Annotated[str, "Currently active agent"]
    agent_thoughts: Annotated[str, "Thoughts and reasoning of the current agent"]
    task_type: Annotated[str, "Type of task to perform"]
    context: Annotated[dict, "Additional context and metadata"]
    thread_id: Annotated[str, "Thread identifier for persistence"]
    memory_context: Annotated[list, "Retrieved long-term memory"]
    