from typing import Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage
from langgraph.graph import END
from langgraph.types import Command
from pydantic import BaseModel, Field

from .prompts import PENDING_LIST_NOTE, SUPERVISOR_PROMPT
from .state import AgentState, recent

AGENTS = ("product", "cart", "order", "review", "recipe", "shopping_list")
MAX_HOPS = 4


class Route(BaseModel):
    next: Literal["product", "cart", "order", "review", "recipe", "shopping_list", "FINISH"]
    task: str = Field(default="", description="Instruction for the chosen specialist.")
    reply: str = Field(default="", description="Spoken answer, only when FINISH is chosen without any specialist.")


def describe_list(items) -> str:
    lines = []
    for i in items:
        match = f"{i['product_name']} at {i['price']:,.0f} rupees" if i["product_id"] else "no match in store"
        lines.append(f"- {i['qty']} x {i['item']} -> {match}")
    return "\n".join(lines)


def make_supervisor(llm: BaseChatModel):
    router = llm.with_structured_output(Route, method="function_calling")

    async def supervisor(state: AgentState) -> Command:
        if state.get("hops", 0) >= MAX_HOPS:
            return Command(goto=END)
        last = state["messages"][-1]

        pending = state.get("pending_list")
        note = PENDING_LIST_NOTE.format(items=describe_list(pending)) if pending else ""
        route: Route = await router.ainvoke(
            [SystemMessage(SUPERVISOR_PROMPT.format(pending=note)), *recent(state["messages"])]
        )

        visited = state.get("visited") or []
        if route.next == "FINISH" or route.next in visited:
            # Nothing has answered the user yet this turn (chit-chat), so speak the supervisor's reply.
            if route.reply and not isinstance(last, AIMessage):
                return Command(goto=END, update={"messages": [AIMessage(route.reply, name="supervisor")]})
            return Command(goto=END)

        return Command(
            goto=route.next,
            update={"task": route.task, "hops": state.get("hops", 0) + 1, "visited": [*visited, route.next]},
        )

    return supervisor
