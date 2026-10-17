"""Order specialist: checks out and looks up orders. `create_order` is deliberately not on its list: checkout covers it."""
from ..prompts import VOICE_RULES
from .base import tool_agent

PROMPT = (
    "You are VoiceCart's order specialist. Use checkout to place an order for everything in the cart; pass the "
    "address only if the user gave one, otherwise the saved address is used. Use list_orders and get_order for "
    "history and status. Only use update_order to cancel an order (status \"Cancelled\"), and only when the user "
    "explicitly asked to cancel it. After checkout, tell the user the order total and that it was placed."
)

SPEC = tool_agent(
    name="order",
    prompt=PROMPT + VOICE_RULES,
    tool_names=("checkout", "list_orders", "get_order", "update_order"),
)
