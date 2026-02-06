import json
from typing import Dict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI


SYSTEM_PROMPT = '''You are a router agent responsible for directing user requests to the appropriate agent based on the content of the request.
You have access to the following agents:
{agent_list}

Return ONLY valid JSON (no markdown fences):
{{
    "agent": "name of the agent to route to",
    "reasoning": "a brief explanation of why you chose this agent"
}}

When a user request comes in, analyze the content of the request and determine which agent is best suited to handle it.'''


def router_agent_system_prompt(agent_list: str) -> str:
    return SYSTEM_PROMPT.format(agent_list=agent_list)


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def route(message: str, agent_list: str) -> Dict[str, str]:
    """Route a user message to the best agent. Returns {agent, reasoning}."""
    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0)
    resp = llm.invoke([
        SystemMessage(content=router_agent_system_prompt(agent_list)),
        HumanMessage(content=message),
    ])
    try:
        return json.loads(_strip_code_fences(resp.content))
    except json.JSONDecodeError:
        return {"agent": "general", "reasoning": resp.content.strip()}


class RouterAgent:
    """Stateful router that keeps a warm LLM handle."""

    def __init__(self, llm=None, memory=None):
        self.llm = llm or ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0)
        self.memory = memory

    def __call__(self, user_input: str, agent_list: str = "") -> Dict[str, str]:
        """Route the input to the appropriate agent."""
        resp = self.llm.invoke([
            SystemMessage(content=router_agent_system_prompt(agent_list)),
            HumanMessage(content=user_input),
        ])
        try:
            return json.loads(_strip_code_fences(resp.content))
        except json.JSONDecodeError:
            return {"agent": "general", "reasoning": resp.content.strip()}


if __name__ == "__main__":
    router = RouterAgent()
    result = router(
        "I want to add milk to my cart",
        agent_list="shopping_list, cart, order, general",
    )
    print(result)
