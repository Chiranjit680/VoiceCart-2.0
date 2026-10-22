"""
Shopping list specialist: turns a recipe or goal into a list of store products, and adds them to the cart only
after the shopper confirms.

Not a free-running tool agent: the model drafts what is wanted, the code matches each item to a real product and
keeps the list pending in the state, and the next turn's yes / no / change decides what happens to it.
"""
import asyncio
import re
from typing import Dict, List, Literal, Optional, Tuple

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.types import Command
from pydantic import BaseModel, Field

from ..cards import card_from, merge_cards
from ..prompts import memory_block, profile_block
from ..state import AgentState, ListItem, recent
from ..toolresult import parse
from .base import Node, Specialist, log_agent_input

NAME = "shopping_list"
TOOL_NAMES = ("search_products", "add_to_cart")

DRAFT_PROMPT = """You build grocery shopping lists for VoiceCart. From the conversation, list the items the user needs to buy for their request. If a recipe was discussed, use its ingredients. Skip pantry basics like water, salt and pepper unless the user asks for them. Each `item` is a short store search term (e.g. "chicken breast", "basmati rice"); `qty` is the number of store units to buy (usually 1).{current}

Task from the coordinator: {task}

Data from the previous step:
{scratch}{memories}"""

DECIDE_PROMPT = """A shopping list is waiting for the user's confirmation:
{items}

Classify the user's latest message:
- confirm: they want the list added to their cart as is
- cancel: they don't want it
- modify: they want to add, remove or change items"""


class ItemRequest(BaseModel):
    item: str = Field(description='Short store search term, e.g. "chicken breast".')
    qty: int = Field(default=1, ge=1)


class Draft(BaseModel):
    items: List[ItemRequest]


class Decision(BaseModel):
    action: Literal["confirm", "modify", "cancel"]


def describe_list(items) -> str:
    """The list as lines of text, for prompts."""
    lines = []
    for i in items:
        match = f"{i['product_name']} at {i['price']:,.0f} rupees" if i["product_id"] else "no match in store"
        lines.append(f"- {i['qty']} x {i['item']} -> {match}")
    return "\n".join(lines)


def _words(text: str) -> set:
    """Lower-case words of 3+ letters, singularised by dropping a trailing 's'."""
    return {w.rstrip("s") for w in re.findall(r"[a-z]{3,}", text.lower())}


def item_matches(item: str, product_name: str) -> bool:
    """Whether a product really is the wanted item.

    Search also matches descriptions, so a product counts only if its name has every word of the item, or at
    least two of them ("green chilli" must not match "Green Apples").
    """
    wanted = _words(item)
    shared = wanted & _words(product_name)
    return bool(shared) and (shared == wanted or len(shared) >= 2)


def _reply(text: str, **update) -> Command:
    return Command(goto="supervisor", update={"messages": [AIMessage(text, name=NAME)], **update})


def build(llm: BaseChatModel, tools: Dict[str, BaseTool]) -> Node:
    search_tool, add_tool = tools["search_products"], tools["add_to_cart"]
    drafter = llm.with_structured_output(Draft, method="function_calling")
    decider = llm.with_structured_output(Decision, method="function_calling")

    async def match(request: ItemRequest) -> Tuple[ListItem, Optional[dict]]:
        """The store product for one wanted item, plus the card to show for it (None when nothing matched)."""
        item: ListItem = {"item": request.item, "qty": request.qty, "product_id": None, "product_name": None, "price": None}
        try:
            found = parse(await search_tool.ainvoke({"query": request.item, "limit": 5}))
        except Exception:
            return item, None
        products = [found] if isinstance(found, dict) else found if isinstance(found, list) else []
        in_stock = [
            p for p in products
            if isinstance(p, dict) and p.get("for_sale", True) and p.get("stock", 0) >= request.qty
            and item_matches(request.item, p["name"])
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
                result = parse(await add_tool.ainvoke({"product_id": item["product_id"], "quantity": item["qty"]}))
                (added if isinstance(result, dict) else failed).append(item["product_name"])
            except Exception:
                failed.append(item["product_name"])

        reply = f"Added {len(added)} items to your cart."
        if failed:
            reply += f" I couldn't add {', '.join(failed)}."
        return _reply(reply, pending_list=None)

    async def propose(state: AgentState, current: Optional[List[ListItem]], config: RunnableConfig) -> Command:
        current_note = f"\n\nThe current list, which the user wants to change:\n{describe_list(current)}" if current else ""
        system = DRAFT_PROMPT.format(
            current=current_note,
            task=state.get("task") or "Build a shopping list for the user's request.",
            scratch=state.get("scratch") or "none",
            memories=memory_block(state.get("memories")) + profile_block(state.get("profile")),
        )
        messages = [SystemMessage(system), *recent(state["messages"])]
        log_agent_input("shopping_list.drafter", messages)
        draft: Draft = await drafter.ainvoke(messages, config)
        results = await asyncio.gather(*(match(r) for r in draft.items))
        items = [item for item, _ in results]
        cards = [card for _, card in results if card]

        matched = [i for i in items if i["product_id"]]
        missing = [i["item"] for i in items if not i["product_id"]]
        if not matched:
            return _reply("I couldn't find any of those items in the store.", pending_list=None)

        total = sum(i["price"] * i["qty"] for i in matched)
        reply = f"I found {len(matched)} of {len(items)} items for about {total:,.0f} rupees: {', '.join(i['product_name'] for i in matched)}."
        if missing:
            reply += f" I couldn't find {', '.join(missing)}."
        reply += " Should I add them to your cart?"
        return _reply(
            reply,
            pending_list=items,
            scratch=describe_list(items),
            products=merge_cards(state.get("products"), cards),
        )

    async def node(state: AgentState, config: RunnableConfig) -> Command:
        pending = state.get("pending_list")
        if not pending:
            return await propose(state, None, config)

        last_user = next(m for m in reversed(state["messages"]) if isinstance(m, HumanMessage))
        messages = [SystemMessage(DECIDE_PROMPT.format(items=describe_list(pending))), last_user]
        log_agent_input("shopping_list.decider", messages)
        decision: Decision = await decider.ainvoke(messages, config)
        if decision.action == "confirm":
            return await add_all(pending)
        if decision.action == "cancel":
            return _reply("Okay, I've dropped that shopping list.", pending_list=None)
        return await propose(state, pending, config)  # modify: draft again, starting from the current list

    return node


SPEC = Specialist(name=NAME, tool_names=TOOL_NAMES, build=build)
