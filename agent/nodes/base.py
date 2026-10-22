"""What the tool-calling specialists share: the loop that runs the agent and reports back to the supervisor."""
import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Callable, Dict, List, Sequence, Tuple

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.types import Command

from ..cards import collect_cards, merge_cards
from ..prompts import AGENT_CONTEXT, memory_block, profile_block
from ..state import AgentState, recent
from ..toolresult import text

SCRATCH_LIMIT = 4000
MAX_TOOL_ROUNDS = 5  # rounds of "model asks for tools, tools answer" before the model must answer

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


async def _call_tool(tools_by_name: Dict[str, BaseTool], call: dict, config: RunnableConfig) -> ToolMessage:
    """Run one tool call. A failure becomes a message the model can read and recover from, never a crash."""
    name, call_id = call["name"], call["id"]
    tool = tools_by_name.get(name)
    if tool is None:
        return ToolMessage(content=f"Error: there is no tool called {name}.", name=name, tool_call_id=call_id, status="error")
    try:
        result = await tool.ainvoke(call, config)
    except Exception as error:
        logger.warning("Tool %s failed: %s", name, error)
        return ToolMessage(content=f"Error calling {name}: {error}", name=name, tool_call_id=call_id, status="error")
    return result if isinstance(result, ToolMessage) else ToolMessage(content=text(result), name=name, tool_call_id=call_id)


async def run_tool_loop(
    llm: BaseChatModel, tools: Sequence[BaseTool], messages: List[BaseMessage], config: RunnableConfig
) -> List[BaseMessage]:
    """Let the model call tools until it answers. Returns the new messages: its tool calls, their results, the answer.

    The loop is written out here, instead of using a ready-made agent, so that `config` reaches every model and
    tool call. That is what ties them to the turn they belong to in a LangSmith trace: on Python 3.10 async code
    does not inherit the config, and the ready-made agent's internal model call would show up as a trace of its own.
    """
    tools_by_name = {tool.name: tool for tool in tools}
    model = llm.bind_tools(list(tools))
    new: List[BaseMessage] = []
    for _ in range(MAX_TOOL_ROUNDS):
        reply = await model.ainvoke([*messages, *new], config)
        new.append(reply)
        invalid = reply.invalid_tool_calls
        if not reply.tool_calls and not invalid:
            return new
        new.extend(await asyncio.gather(*(_call_tool(tools_by_name, call, config) for call in reply.tool_calls)))
        # Every tool call needs an answer, even one whose arguments the model garbled.
        new.extend(
            ToolMessage(content=f"Error: could not read the arguments for {c.get('name')}.", name=c.get("name") or "?", tool_call_id=c.get("id") or "", status="error")
            for c in invalid
        )
    # Out of rounds: make it answer with what it has found.
    new.append(await llm.ainvoke([*messages, *new], config))
    return new


def tool_agent(name: str, prompt: str, tool_names: Sequence[str]) -> Specialist:
    """A specialist that is a model with tools: it calls them as needed, answers, and hands back to the supervisor."""

    def build(llm: BaseChatModel, tools: Dict[str, BaseTool]) -> Node:
        agent_tools = [tools[n] for n in tool_names]

        async def node(state: AgentState, config: RunnableConfig) -> Command:
            system = prompt + AGENT_CONTEXT.format(
                task=state.get("task") or "Handle the user's latest message.",
                scratch=state.get("scratch") or "none",
                memories=memory_block(state.get("memories")) + profile_block(state.get("profile")),
            )
            history = recent(state["messages"])
            messages = [SystemMessage(system), *history]
            log_agent_input(name, messages)
            new_messages = await run_tool_loop(llm, agent_tools, messages, config)
            for m in new_messages:
                for call in getattr(m, "tool_calls", None) or []:
                    logger.info("[%s] tool %s %s", name, call["name"], json.dumps(call["args"]))

            # Only the final answer joins the shared conversation; tool output is kept as scratch
            # so the next step can resolve product ids without bloating the history.
            tool_output = "\n".join(text(m.content) for m in new_messages if isinstance(m, ToolMessage))
            update = {"messages": [AIMessage(text(new_messages[-1].content), name=name)]}
            if tool_output:
                update["scratch"] = tool_output[:SCRATCH_LIMIT]
            cards = collect_cards(new_messages)
            if cards:
                update["products"] = merge_cards(state.get("products"), cards)
            return Command(goto="supervisor", update=update)

        return node

    return Specialist(name=name, tool_names=tuple(tool_names), build=build)
