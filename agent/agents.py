import asyncio
import json
import logging
import re
from typing import Any, List, Literal, Optional, Tuple

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.types import Command
from pydantic import BaseModel, Field

from .cards import card_from, collect_cards, merge_cards
from .prompts import AGENT_CONTEXT, SHOPPING_DECIDE_PROMPT, SHOPPING_DRAFT_PROMPT
from .state import AgentState, ListItem, recent
from .supervisor import describe_list
from .toolresult import parse as _parse, text as _text

SCRATCH_LIMIT = 4000

logger = logging.getLogger("voicecart.agent")


def _words(text: str) -> set:
    """Lower-case words of 3+ letters, singularised by dropping a trailing 's'."""
    return {w.rstrip("s") for w in re.findall(r"[a-z]{3,}", text.lower())}


def make_agent_node(name: str, llm: BaseChatModel, tools: List[BaseTool], prompt: str):
    """Wrap a tool-calling agent as a graph node that reports back to the supervisor."""
    agent = create_agent(llm, tools)

    async def node(state: AgentState) -> Command:
        system = prompt + AGENT_CONTEXT.format(
            task=state.get("task") or "Handle the user's latest message.",
            scratch=state.get("scratch") or "none",
        )
        history = recent(state["messages"])
        result = await agent.ainvoke({"messages": [SystemMessage(system), *history]})
        new_messages = result["messages"][len(history) + 1:]
        for m in new_messages:
            for call in getattr(m, "tool_calls", None) or []:
                logger.info("[%s] tool %s %s", name, call["name"], json.dumps(call["args"]))

        # Only the final answer joins the shared conversation; tool output is kept as scratch
        # so the next step can resolve product ids without bloating the history.
        tool_output = "\n".join(_text(m.content) for m in new_messages if isinstance(m, ToolMessage))
        answer = _text(result["messages"][-1].content)
        update = {"messages": [AIMessage(answer, name=name)]}
        if tool_output:
            update["scratch"] = tool_output[:SCRATCH_LIMIT]
        cards = collect_cards(new_messages)
        if cards:
            update["products"] = merge_cards(state.get("products"), cards)
        return Command(goto="supervisor", update=update)

    return node


class ItemRequest(BaseModel):
    item: str = Field(description='Short store search term, e.g. "chicken breast".')
    qty: int = Field(default=1, ge=1)


class Draft(BaseModel):
    items: List[ItemRequest]


class Decision(BaseModel):
    action: Literal["confirm", "modify", "cancel"]


def make_shopping_list_node(llm: BaseChatModel, search_tool: BaseTool, add_tool: BaseTool):
    drafter = llm.with_structured_output(Draft, method="function_calling")
    decider = llm.with_structured_output(Decision, method="function_calling")

    async def match(request: ItemRequest) -> Tuple[ListItem, Optional[dict]]:
        """The store product for one wanted item, plus the card to show for it (None when nothing matched)."""
        item: ListItem = {"item": request.item, "qty": request.qty, "product_id": None, "product_name": None, "price": None}
        try:
            found = _parse(await search_tool.ainvoke({"query": request.item, "limit": 5}))
        except Exception:
            return item, None
        products = [found] if isinstance(found, dict) else found if isinstance(found, list) else []
        # Search also matches descriptions, so accept a product only if its name really is the item: it has
        # every word of the item, or at least two of them ("green chilli" must not match "Green Apples").
        item_words = _words(request.item)

        def is_the_item(name: str) -> bool:
            shared = item_words & _words(name)
            return bool(shared) and (shared == item_words or len(shared) >= 2)

        in_stock = [
            p for p in products
            if isinstance(p, dict) and p.get("for_sale", True) and p.get("stock", 0) >= request.qty
            and is_the_item(p["name"])
        ]
        if not in_stock:
            return item, None
        best = in_stock[0]  # search results are already sorted by relevance
        item.update(product_id=best["id"], product_name=best["name"], price=float(best["price"]))
        return item, card_from(best, quantity=request.qty)

    async def add_all(items: List[ListItem]) -> Command:
        added, failed = [], []
        for item in (i for i in items if i["product_id"]):
            try:
                result = _parse(await add_tool.ainvoke({"product_id": item["product_id"], "quantity": item["qty"]}))
                (added if isinstance(result, dict) else failed).append(item["product_name"])
            except Exception:
                failed.append(item["product_name"])

        reply = f"Added {len(added)} items to your cart."
        if failed:
            reply += f" I couldn't add {', '.join(failed)}."
        return Command(
            goto="supervisor",
            update={"messages": [AIMessage(reply, name="shopping_list")], "pending_list": None},
        )

    async def propose(state: AgentState, current: Optional[List[ListItem]]) -> Command:
        current_note = f"\n\nThe current list, which the user wants to change:\n{describe_list(current)}" if current else ""
        system = SHOPPING_DRAFT_PROMPT.format(
            current=current_note,
            task=state.get("task") or "Build a shopping list for the user's request.",
            scratch=state.get("scratch") or "none",
        )
        draft: Draft = await drafter.ainvoke([SystemMessage(system), *recent(state["messages"])])
        results = await asyncio.gather(*(match(r) for r in draft.items))
        items = [item for item, _ in results]
        cards = [card for _, card in results if card]

        matched = [i for i in items if i["product_id"]]
        missing = [i["item"] for i in items if not i["product_id"]]
        if not matched:
            reply = "I couldn't find any of those items in the store."
            return Command(goto="supervisor", update={"messages": [AIMessage(reply, name="shopping_list")], "pending_list": None})

        total = sum(i["price"] * i["qty"] for i in matched)
        reply = f"I found {len(matched)} of {len(items)} items for about {total:,.0f} rupees: {', '.join(i['product_name'] for i in matched)}."
        if missing:
            reply += f" I couldn't find {', '.join(missing)}."
        reply += " Should I add them to your cart?"
        return Command(
            goto="supervisor",
            update={
                "messages": [AIMessage(reply, name="shopping_list")],
                "pending_list": items,
                "scratch": describe_list(items),
                "products": merge_cards(state.get("products"), cards),
            },
        )

    async def node(state: AgentState) -> Command:
        pending = state.get("pending_list")
        if pending:
            last_user = next(m for m in reversed(state["messages"]) if isinstance(m, HumanMessage))
            decision: Decision = await decider.ainvoke(
                [SystemMessage(SHOPPING_DECIDE_PROMPT.format(items=describe_list(pending))), last_user]
            )
            if decision.action == "confirm":
                return await add_all(pending)
            if decision.action == "cancel":
                reply = "Okay, I've dropped that shopping list."
                return Command(goto="supervisor", update={"messages": [AIMessage(reply, name="shopping_list")], "pending_list": None})
            return await propose(state, pending)
        return await propose(state, None)

    return node
