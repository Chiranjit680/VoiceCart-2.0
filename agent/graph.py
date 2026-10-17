from typing import List

from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from . import prompts
from .agents import make_agent_node, make_shopping_list_node
from .llm import get_llm
from .state import AgentState
from .supervisor import AGENTS, make_supervisor
from .tools.display import show_products
from .tools.recipes import RECIPE_TOOLS

# Agents that can put product photo cards on the user's screen.
AGENTS_WITH_CARDS = {"product", "cart"}

# MCP tools each subagent may use. Admin, login/register and create_order tools are deliberately left out.
AGENT_TOOLS = {
    "product": ["search_products", "list_products", "get_product", "get_product_stock", "list_categories"],
    "cart": ["get_cart", "get_cart_total", "add_to_cart", "update_cart_item", "remove_from_cart", "clear_cart", "search_products"],
    "order": ["checkout", "list_orders", "get_order", "update_order"],
    "review": ["get_product_reviews", "get_user_reviews", "create_review", "update_review", "delete_review", "search_products"],
}

AGENT_PROMPTS = {
    "product": prompts.PRODUCT_PROMPT,
    "cart": prompts.CART_PROMPT,
    "order": prompts.ORDER_PROMPT,
    "review": prompts.REVIEW_PROMPT,
}


def build_graph(mcp_tools: List[BaseTool], checkpointer: BaseCheckpointSaver):
    llm = get_llm()
    by_name = {t.name: t for t in mcp_tools}

    builder = StateGraph(AgentState)
    builder.add_node("supervisor", make_supervisor(llm), destinations=(*AGENTS, END))

    for name, tool_names in AGENT_TOOLS.items():
        tools = [by_name[n] for n in tool_names if n in by_name]
        if name in AGENTS_WITH_CARDS:
            tools.append(show_products)
        builder.add_node(name, make_agent_node(name, llm, tools, AGENT_PROMPTS[name]), destinations=("supervisor",))

    builder.add_node(
        "recipe", make_agent_node("recipe", llm, RECIPE_TOOLS, prompts.RECIPE_PROMPT), destinations=("supervisor",)
    )
    builder.add_node(
        "shopping_list",
        make_shopping_list_node(llm, by_name["search_products"], by_name["add_to_cart"]),
        destinations=("supervisor",),
    )

    builder.add_edge(START, "supervisor")
    return builder.compile(checkpointer=checkpointer)
