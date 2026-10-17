"""What the tool-calling specialists share: the loop that runs the agent and reports back to the supervisor."""
import json
import logging
from dataclasses import dataclass
from typing import Callable, Dict, List, Sequence, Tuple

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.types import Command

from ..cards import collect_cards, merge_cards
from ..prompts import AGENT_CONTEXT, memory_block
from ..state import AgentState, recent
from ..toolresult import text

SCRATCH_LIMIT = 4000

logger = logging.getLogger("voicecart.agent")

# A graph node: reads the state, returns a Command (where to go next + what to change).
Node = Callable[[AgentState, RunnableConfig], "object"]


@dataclass(frozen=True)
class Specialist:
    """A specialist node: its graph name, the MCP tools it may call, and how to build it."""

    name: str
    tool_names: Tuple[str, ...]  # an allow-list of MCP tool names; admin and login tools are never listed
    build: Callable[[BaseChatModel, Dict[str, BaseTool]], Node]  # (model, its tools by name) -> node


def log_agent_input(name: str, messages: List[BaseMessage]) -> None:
    logger.info(
        "[%s] sending to agent: %s",
        name,
        json.dumps(
            [{"type": message.type, "content": message.content} for message in messages],
            ensure_ascii=False,
            default=str,
        ),
    )


def tool_agent(name: str, prompt: str, tool_names: Sequence[str]) -> Specialist:
    """A specialist that is a model with tools: it calls them as needed, answers, and hands back to the supervisor."""

    def build(llm: BaseChatModel, tools: Dict[str, BaseTool]) -> Node:
        agent = create_agent(llm, [tools[n] for n in tool_names])

        async def node(state: AgentState, config: RunnableConfig) -> Command:
            system = prompt + AGENT_CONTEXT.format(
                task=state.get("task") or "Handle the user's latest message.",
                scratch=state.get("scratch") or "none",
                memories=memory_block(state.get("memories")),
            )
            history = recent(state["messages"])
            # `config` is passed on explicitly: on Python 3.10 async code does not inherit it.
            messages = [SystemMessage(system), *history]
            log_agent_input(name, messages)
            result = await agent.ainvoke({"messages": messages}, config)
            new_messages = result["messages"][len(history) + 1:]
            for m in new_messages:
                for call in getattr(m, "tool_calls", None) or []:
                    logger.info("[%s] tool %s %s", name, call["name"], json.dumps(call["args"]))

            # Only the final answer joins the shared conversation; tool output is kept as scratch
            # so the next step can resolve product ids without bloating the history.
            tool_output = "\n".join(text(m.content) for m in new_messages if isinstance(m, ToolMessage))
            update = {"messages": [AIMessage(text(result["messages"][-1].content), name=name)]}
            if tool_output:
                update["scratch"] = tool_output[:SCRATCH_LIMIT]
            cards = collect_cards(new_messages)
            if cards:
                update["products"] = merge_cards(state.get("products"), cards)
            return Command(goto="supervisor", update=update)

        return node

    return Specialist(name=name, tool_names=tuple(tool_names), build=build)
