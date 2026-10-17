"""
The conversation graph, one turn at a time:

    START -> memory -> supervisor -> (product | cart | order | review | recipe | shopping_list) -> supervisor -> ... -> END

`memory` fetches what the shopper has told us before. The `supervisor` picks a specialist, each specialist reports
back to it, and it ends the turn when the request is handled. Every tool a specialist uses comes from the MCP
server; each specialist has an allow-list of which ones (see its module in agent/nodes/).
"""
from typing import List, Optional

from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from .llm import get_llm
from .nodes import cart, order, product, recipe, review, shopping_list, supervisor
from .nodes.memory import NAME as MEMORY, memory_node
from .state import AgentState
from .trace import TurnTrace

SPECIALISTS = (product.SPEC, cart.SPEC, order.SPEC, review.SPEC, recipe.SPEC, shopping_list.SPEC)


class MissingToolsError(RuntimeError):
    """The MCP server does not offer tools the agents need (usually an MCP server that has not been restarted)."""


def build_graph(mcp_tools: List[BaseTool], checkpointer: BaseCheckpointSaver, trace: Optional[TurnTrace] = None):
    by_name = {tool.name: tool for tool in mcp_tools}

    missing = sorted({name for spec in SPECIALISTS for name in spec.tool_names} - by_name.keys())
    if missing:
        raise MissingToolsError(f"The MCP server is missing tools the agents need: {', '.join(missing)}. Restart the MCP server.")

    base_llm = get_llm()

    def llm_for(node: str):
        """The model a node uses: the shared one, or a copy that logs its calls when this turn is traced."""
        return trace.model_for(base_llm, node) if trace else base_llm

    builder = StateGraph(AgentState)
    builder.add_node(MEMORY, memory_node)
    builder.add_node(supervisor.NAME, supervisor.make_supervisor_node(llm_for(supervisor.NAME)), destinations=(*supervisor.SPECIALIST_NAMES, END))
    for spec in SPECIALISTS:
        node = spec.build(llm_for(spec.name), {name: by_name[name] for name in spec.tool_names})
        builder.add_node(spec.name, node, destinations=(supervisor.NAME,))

    builder.add_edge(START, MEMORY)
    builder.add_edge(MEMORY, supervisor.NAME)
    return builder.compile(checkpointer=checkpointer)
