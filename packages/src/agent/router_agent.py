
from langgraph.prebuilt import create_react_agent
import operator
import json
from typing import TypedDict, Annotated, Literal, List, Optional, Dict
import uuid

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from agent_main import AgentState

SYSTEM_PROMPT = '''You are a router agent responsible for directing user requests to the appropriate agent based on the content of the request.
You have access to the following agents:
{agent_list}

output schema:
{{
    "agent": "name of the agent to route to",
    "reasoning": "a brief explanation of why you chose this agent"
}}

When a user request comes in, analyze the content of the request and determine which agent is best suited to handle it. Consider the capabilities and tools of each agent when making your decision.'''


def router_agent_system_prompt(agent_list: str) -> str:
    return SYSTEM_PROMPT.format(agent_list=agent_list)


def router_agent(agent_list: str):
    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0)
    system_prompt = router_agent_system_prompt(agent_list)
    
    agent = create_react_agent(model=llm, prompt=system_prompt, tools=[])
    return agent


class RouterAgent:
    def __init__(self, llm, memory):
        self.llm = llm
        self.memory = memory
        self.agent=router_agent(agent_list="")  # Placeholder, will be set in __call__

    def __call__(self, input: str, state: AgentState) -> str:
        """Route the input to the appropriate agent based on the state and input."""
        system_prompt = router_agent_system_prompt(
            state.get("context", {}).get("agent_list", "")
        )
        response = self.llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=input),
        ])
        result = json.loads(response.content)
