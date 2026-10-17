"""Cart specialist: shows and changes the shopper's cart."""
from ..prompts import CARDS_RULES, VOICE_RULES
from .base import tool_agent

PROMPT = (
    "You are VoiceCart's cart specialist. Manage the user's cart with your tools. You need a product id to add, "
    "update or remove an item: take it from the data below, call get_cart for items already in the cart, or find a "
    "product the user names with search_products. If several products match equally well, ask the user which one. "
    "After a change, confirm what changed."
)

SPEC = tool_agent(
    name="cart",
    prompt=PROMPT + CARDS_RULES + VOICE_RULES,
    tool_names=(
        "get_cart", "get_cart_total", "add_to_cart", "update_cart_item", "remove_from_cart", "clear_cart",
        "search_products", "show_products",
    ),
)
