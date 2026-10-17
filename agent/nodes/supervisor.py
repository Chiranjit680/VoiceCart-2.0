"""
The supervisor: after the memory node, and again after every specialist, decides who handles the next step
or that the turn is finished. It never calls a tool itself.
"""
from typing import Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END
from langgraph.types import Command
from pydantic import BaseModel, Field

from ..state import AgentState, recent
from ..trace import note as trace_note
from .shopping_list import describe_list

NAME = "supervisor"

# The specialists it can hand over to (graph.py checks these match the nodes it builds).
SPECIALIST_NAMES = ("product", "cart", "order", "review", "recipe", "shopping_list")
MAX_HOPS = 4  # specialists per turn, a guard against loops

PROMPT = """You coordinate VoiceCart, a voice shopping assistant. Decide which specialist handles the next step of the user's latest request.

Specialists:
- product: find and browse products, product details, price, stock, categories
- cart: show the cart and its total, add items, change quantities, remove items, clear the cart
- order: check out / place an order, order history and status, cancel an order
- review: read a product's reviews, write, edit or delete the user's own reviews
- recipe: find recipes and their ingredients, meal ideas
- shopping_list: turn a recipe or goal into a shopping list, match it to store products and add it to the cart after the user confirms; also handles the user's yes / no / changes to a pending list

Rules:
- Messages after the latest user message are what specialists already did this turn. Choose FINISH as soon as the request is fully handled.
- Pick one specialist per step; chain specialists when the request needs it (e.g. recipe, then shopping_list).
- Each specialist runs at most once per turn.
- If a specialist asked the user a question (e.g. which product they mean), choose FINISH and wait for the answer. Exception: if the user's latest message already asked for the next step (e.g. "find a recipe and make a shopping list"), continue with it instead of waiting.
- When the user's message answers a specialist's question (e.g. "the cheaper one", "yes"), route back to the specialist that asked, or to the one that can act on the answer (an offer to add to cart goes to cart).
- Adding, changing or removing cart items always goes to cart, even when the product still has to be found; cart can search.
- For greetings, thanks or anything outside shopping, choose FINISH and put a short friendly spoken answer in `reply`. Otherwise leave `reply` empty.
- `task` is a one-sentence instruction for the specialist with the concrete details it needs (product names, quantities, address) taken from the conversation.
{pending}"""

PENDING_LIST_NOTE = """
A shopping list is waiting for the user's confirmation:
{items}
If the latest user message confirms, changes or cancels this list, route to shopping_list."""


class Route(BaseModel):
    next: Literal["product", "cart", "order", "review", "recipe", "shopping_list", "FINISH"]
    task: str = Field(default="", description="Instruction for the chosen specialist.")
    reply: str = Field(default="", description="Spoken answer, only when FINISH is chosen without any specialist.")


def make_supervisor_node(llm: BaseChatModel):
    router = llm.with_structured_output(Route, method="function_calling")

    # `config` is passed on to the model call explicitly: on Python 3.10 async code does not inherit it,
    # and without it the trace (and any other callback) would not see this call.
    async def supervisor(state: AgentState, config: RunnableConfig) -> Command:
        if state.get("hops", 0) >= MAX_HOPS:
            trace_note(config, f"SUPERVISOR DECISION: ending the turn, step limit ({MAX_HOPS}) reached")
            return Command(goto=END)
        last = state["messages"][-1]

        pending = state.get("pending_list")
        pending_note = PENDING_LIST_NOTE.format(items=describe_list(pending)) if pending else ""
        route: Route = await router.ainvoke(
            [SystemMessage(PROMPT.format(pending=pending_note)), *recent(state["messages"])], config
        )

        visited = state.get("visited") or []
        if route.next == "FINISH" or route.next in visited:
            why = "finished" if route.next == "FINISH" else f"'{route.next}' already ran this turn"
            # Nothing has answered the user yet this turn (chit-chat), so speak the supervisor's reply.
            if route.reply and not isinstance(last, AIMessage):
                trace_note(config, f"SUPERVISOR DECISION: end ({why}), answering directly: {route.reply}")
                return Command(goto=END, update={"messages": [AIMessage(route.reply, name=NAME)]})
            trace_note(config, f"SUPERVISOR DECISION: end ({why})")
            return Command(goto=END)

        trace_note(config, f"SUPERVISOR DECISION: hand over to '{route.next}' with task: {route.task}")
        return Command(
            goto=route.next,
            update={"task": route.task, "hops": state.get("hops", 0) + 1, "visited": [*visited, route.next]},
        )

    return supervisor
